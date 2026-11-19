"""Notifier registry and construction from configuration."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

from crypto_tracking.config import Settings
from crypto_tracking.notifiers.base import Notifier, NotifierNotConfigured
from crypto_tracking.notifiers.email import EmailNotifier
from crypto_tracking.notifiers.log import LogNotifier
from crypto_tracking.notifiers.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class UnknownChannelError(KeyError):
    """Raised when an alert references a channel that is not registered."""


class NotifierRegistry:
    """A name -> :class:`Notifier` registry.

    Channels are instantiated eagerly when the registry is built so missing
    credentials are known at start-up rather than at alert time.
    """

    def __init__(self) -> None:
        self._notifiers: dict[str, Notifier] = {}

    def register(self, notifier: Notifier) -> None:
        if not isinstance(notifier, Notifier):
            raise TypeError(f"Notifier must implement the Notifier interface: {notifier!r}")
        channel = notifier.channel.strip().lower()
        if not channel:
            raise ValueError("Notifier channel must not be empty")
        self._notifiers[channel] = notifier

    def get(self, channel: str) -> Notifier:
        try:
            return self._notifiers[channel.strip().lower()]
        except KeyError as exc:
            raise UnknownChannelError(channel) from exc

    def has(self, channel: str) -> bool:
        return channel.strip().lower() in self._notifiers

    def channels(self) -> list[str]:
        return sorted(self._notifiers)

    def describe(self) -> list[dict[str, str]]:
        return [{"name": name, "class": type(notifier).__name__} for name, notifier in sorted(self._notifiers.items())]


def build_notifier_registry(
    settings: Settings,
    *,
    factories: dict[str, Callable[[], Notifier]] | None = None,
) -> NotifierRegistry:
    """Build the registry from env credentials and configured plugins.

    ``factories`` is mainly a testing hook: pass ``{"telegram": fake_factory}``
    to override a built-in channel without touching the environment.
    """
    registry = NotifierRegistry()
    overrides = factories or {}

    builtins: dict[str, Callable[[], Notifier]] = {
        "log": LogNotifier,
        "telegram": TelegramNotifier,
        "email": EmailNotifier,
    }
    builtins.update(overrides)

    for name, factory in builtins.items():
        try:
            registry.register(factory())
        except NotifierNotConfigured as exc:
            logger.warning("Notifier %s is not configured: %s", name, exc)
        except Exception:
            logger.exception("Could not initialise notifier %s", name)

    for spec in settings.notifier_plugins:
        try:
            notifier_class = load_notifier_class(spec)
            registry.register(notifier_class())
            logger.info("Loaded notifier plugin: %s", spec)
        except Exception:
            logger.exception("Could not load notifier plugin %s", spec)

    if not registry.channels():
        # This should be impossible because LogNotifier is unconditional, but
        # keeping the fallback makes the intent explicit.
        registry.register(LogNotifier())

    available = set(registry.channels())
    settings.default_channels = [channel for channel in settings.default_channels if channel in available]
    if not settings.default_channels:
        settings.default_channels = ["log"]

    return registry


def load_notifier_class(spec: str) -> type[Notifier]:
    """Import a notifier class from ``module:Class`` or ``module.Class``."""
    module_name, separator, attribute = spec.partition(":")
    if not separator:
        module_name, _, attribute = spec.rpartition(".")

    if not module_name or not attribute:
        raise ValueError(f"Invalid notifier plugin path: {spec!r}")

    module = importlib.import_module(module_name)
    candidate = getattr(module, attribute)
    if not isinstance(candidate, type) or not issubclass(candidate, Notifier):
        raise TypeError(f"{spec!r} is not a Notifier subclass")
    return candidate
