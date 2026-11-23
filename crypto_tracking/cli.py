"""Command-line entry point.

Examples::

    crypto-track serve                     # poller + dashboard + alert engine
    crypto-track serve --no-poller         # offline dashboard from local data
    crypto-track poll --once               # fetch one round and evaluate alerts
    crypto-track check                     # evaluate alerts once
    crypto-track import-csv data/old.csv   # import legacy timestamp,source,buy,sell
    crypto-track export-csv prices.csv     # export history
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from crypto_tracking.alerts.engine import AlertEngine
from crypto_tracking.config import Settings, load_settings
from crypto_tracking.domain import range_since, utcnow
from crypto_tracking.importer import import_csv
from crypto_tracking.logging_config import configure_logging
from crypto_tracking.notifiers.registry import NotifierRegistry, build_notifier_registry
from crypto_tracking.poller import CycleCallback, Poller
from crypto_tracking.providers.base import PriceProvider
from crypto_tracking.providers.registry import build_providers
from crypto_tracking.storage.database import Database
from crypto_tracking.storage.repositories import AlertRepository, PriceRepository
from crypto_tracking.web.app import create_app

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    settings: Settings
    database: Database
    prices: PriceRepository
    alerts: AlertRepository
    notifiers: NotifierRegistry
    engine: AlertEngine
    providers: list[PriceProvider]


def build_context(settings: Settings) -> AppContext:
    configure_logging(settings.project_root, settings.log_level)

    database = Database(settings.database_url)
    database.create_all()

    prices = PriceRepository(database)
    alerts = AlertRepository(database)
    notifiers = build_notifier_registry(settings)
    engine = AlertEngine(alerts, prices, notifiers)
    providers = build_providers(settings)

    logger.info("Database: %s", settings.database_url)
    logger.info("Providers: %s", ", ".join(provider.name for provider in providers) or "none")
    logger.info("Notifiers: %s", ", ".join(notifiers.channels()) or "none")

    return AppContext(
        settings=settings,
        database=database,
        prices=prices,
        alerts=alerts,
        notifiers=notifiers,
        engine=engine,
        providers=providers,
    )


def prune_old_prices(settings: Settings, prices: PriceRepository, *, days: int | None = None) -> int:
    """Delete price rows older than the retention window (no-op when disabled)."""
    retention_days = settings.retention_days if days is None else days
    if retention_days <= 0:
        return 0

    cutoff = utcnow() - timedelta(days=retention_days)
    deleted = prices.prune(cutoff)
    if deleted:
        logger.info("Retention: deleted %d price row(s) older than %s days", deleted, retention_days)
    else:
        logger.debug("Retention: nothing to delete (keep %s days)", retention_days)
    return deleted


def make_maintenance(settings: Settings, prices: PriceRepository) -> CycleCallback | None:
    if settings.retention_days <= 0:
        return None
    return lambda: prune_old_prices(settings, prices)


# --------------------------------------------------------------------- commands
def command_serve(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    if args.debug:
        settings.debug = True

    context = build_context(settings)
    offline = bool(args.no_poller or args.offline)
    stop_event = threading.Event()
    poller_thread: threading.Thread | None = None

    if offline:
        logger.info("Offline mode: poller disabled; serving the dashboard from local data")
    else:
        poller = Poller(
            context.providers,
            context.prices,
            settings.poll_interval_seconds,
            on_cycle=context.engine.evaluate,
            maintenance=make_maintenance(settings, context.prices),
        )
        poller_thread = threading.Thread(
            target=poller.run,
            args=(stop_event,),
            name="crypto-poller",
            daemon=True,
        )
        poller_thread.start()

    app = create_app(
        settings=settings,
        prices=context.prices,
        alerts=context.alerts,
        engine=context.engine,
        notifiers=context.notifiers,
    )

    logger.info("Dashboard: http://%s:%s/", settings.host, settings.port)
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=settings.debug,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        stop_event.set()
        if poller_thread is not None:
            poller_thread.join(timeout=10)
        context.database.dispose()

    return 0


def command_poll(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    poller = Poller(
        context.providers,
        context.prices,
        settings.poll_interval_seconds,
        on_cycle=context.engine.evaluate,
        maintenance=make_maintenance(settings, context.prices),
    )

    if args.once:
        quotes = poller.poll_once()
        events = context.engine.evaluate()
        print(f"Fetched {len(quotes)} quote(s); triggered {len(events)} alert(s).")
        context.database.dispose()
        return 0

    try:
        poller.run()
    except KeyboardInterrupt:
        logger.info("Poller interrupted")
    finally:
        context.database.dispose()
    return 0


def command_check(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    events = context.engine.evaluate()

    if not events:
        print("No alerts triggered.")
    else:
        for event in events:
            print(event.message)

    context.database.dispose()
    return 0


def command_init_db(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    print(f"Database ready: {settings.database_url}")
    print(
        f"Prices: {context.prices.count()} | Alerts: {context.alerts.count_alerts()}"
        f" | Events: {context.alerts.count_events()}"
    )
    context.database.dispose()
    return 0


def command_status(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    print(f"Database: {settings.database_url}")
    print(
        f"Prices: {context.prices.count()} | Alerts: {context.alerts.count_alerts()}"
        f" | Events: {context.alerts.count_events()}"
    )
    print(f"Providers: {', '.join(provider.name for provider in context.providers) or 'none'}")
    print(f"Notifiers: {', '.join(context.notifiers.channels()) or 'none'}")
    retention = f"{settings.retention_days} day(s)" if settings.retention_days else "keep forever"
    print(f"Retention: {retention}")
    oldest = context.prices.oldest_timestamp()
    if oldest is not None:
        print(f"Oldest price: {oldest.isoformat()}")

    pairs = context.prices.pairs()
    if pairs:
        print("\nPairs:")
        for row in pairs:
            print(f"  {row['asset']}/{row['quote_currency']}: {row['count']} row(s), latest {row['last_timestamp']}")
    else:
        print("\nNo price data yet.")

    context.database.dispose()
    return 0


def command_prune(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    days = args.days if args.days is not None else settings.retention_days
    if days <= 0:
        print("Nothing to do: retention is disabled. Pass --days N to prune older rows.")
        context.database.dispose()
        return 0

    cutoff = utcnow() - timedelta(days=days)
    affected = context.prices.prune(cutoff, dry_run=args.dry_run)
    verb = "Would delete" if args.dry_run else "Deleted"
    print(f"{verb} {affected} price row(s) older than {cutoff.isoformat()} ({days} day(s)).")
    if not args.dry_run and affected and args.vacuum:
        context.prices.vacuum()
        print("Vacuumed the database.")

    context.database.dispose()
    return 0


def command_import_csv(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)
    inserted = import_csv(
        args.path,
        context.prices,
        default_asset=args.asset,
        default_quote_currency=args.quote,
        default_source=args.source,
    )
    print(f"Imported {inserted} new price row(s) from {args.path}.")
    context.database.dispose()
    return 0


def command_export_csv(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    context = build_context(settings)

    since = range_since(args.range)
    if args.asset and args.quote:
        pairs = [(args.asset.upper(), args.quote.upper())]
    else:
        pairs = [(str(row["asset"]), str(row["quote_currency"])) for row in context.prices.pairs()]

    output_path = Path(args.output).expanduser()
    rows = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "asset", "quote_currency", "source", "price", "bid", "ask", "volume"])
        for asset, quote in pairs:
            for quote_row in context.prices.history(asset, quote, since=since, limit=None):
                writer.writerow(
                    [
                        quote_row.timestamp.isoformat(),
                        quote_row.asset,
                        quote_row.quote_currency,
                        quote_row.source,
                        quote_row.price,
                        quote_row.bid if quote_row.bid is not None else "",
                        quote_row.ask if quote_row.ask is not None else "",
                        quote_row.volume if quote_row.volume is not None else "",
                    ]
                )
                rows += 1

    print(f"Exported {rows} row(s) to {output_path}.")
    context.database.dispose()
    return 0


# ------------------------------------------------------------------ arg parsing
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-track",
        description="Track crypto prices locally, set thresholds and receive alerts.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a TOML config file (default: config.toml in the project root).",
    )

    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the poller, alert engine and dashboard.")
    serve.add_argument("--host", help="Bind address (default from config).")
    serve.add_argument("--port", type=int, help="Port (default from config).")
    serve.add_argument("--debug", action="store_true", help="Enable Flask debug mode.")
    serve.add_argument("--no-poller", action="store_true", help="Serve the dashboard without fetching prices.")
    serve.add_argument("--offline", action="store_true", help="Alias for --no-poller.")
    serve.set_defaults(handler=command_serve)

    poll = subparsers.add_parser("poll", help="Run the price poller.")
    poll.add_argument("--once", action="store_true", help="Fetch one round, evaluate alerts and exit.")
    poll.set_defaults(handler=command_poll)

    check = subparsers.add_parser("check", help="Evaluate all enabled alerts once.")
    check.set_defaults(handler=command_check)

    init_db = subparsers.add_parser("init-db", help="Create the database tables.")
    init_db.set_defaults(handler=command_init_db)

    status = subparsers.add_parser("status", help="Show database, provider and pair status.")
    status.set_defaults(handler=command_status)

    prune = subparsers.add_parser("prune", help="Delete price rows older than the retention window.")
    prune.add_argument("--days", type=int, help="Retention in days (default: storage.retention_days).")
    prune.add_argument("--dry-run", action="store_true", help="Only report how many rows would be deleted.")
    prune.add_argument("--vacuum", action="store_true", help="Reclaim disk space afterwards (SQLite).")
    prune.set_defaults(handler=command_prune)

    import_parser = subparsers.add_parser("import-csv", help="Import prices from a CSV file.")
    import_parser.add_argument("path", help="CSV file to import.")
    import_parser.add_argument("--asset", default="USDT", help="Default asset when the CSV has no asset column.")
    import_parser.add_argument("--quote", default="ARS", help="Default quote currency.")
    import_parser.add_argument("--source", default="csv", help="Default source when the CSV has no source column.")
    import_parser.set_defaults(handler=command_import_csv)

    export = subparsers.add_parser("export-csv", help="Export stored prices to a CSV file.")
    export.add_argument("output", help="Output CSV path.")
    export.add_argument("--asset", help="Restrict export to one asset.")
    export.add_argument("--quote", help="Restrict export to one quote currency.")
    export.add_argument("--range", default="all", choices=["1h", "6h", "24h", "7d", "30d", "all"])
    export.set_defaults(handler=command_export_csv)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if logging.getLogger().handlers:
            logger.exception("Unhandled error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def serve_main() -> int:
    """Console-script wrapper for ``crypto-track serve``."""
    return main(["serve"])


def poll_main() -> int:
    """Console-script wrapper for ``crypto-track poll``."""
    return main(["poll"])


if __name__ == "__main__":
    raise SystemExit(main())
