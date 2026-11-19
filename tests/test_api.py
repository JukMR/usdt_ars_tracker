from __future__ import annotations

from datetime import timedelta

from crypto_tracking.domain import Quote, utcnow
from crypto_tracking.storage.repositories import PriceRepository


def _seed(
    prices: PriceRepository,
    *,
    asset="BTC",
    quote="USDT",
    source="test",
    price=100.0,
    minutes_ago=0,
    bid=None,
    ask=None,
):
    prices.add_quotes(
        [
            Quote(
                asset=asset,
                quote_currency=quote,
                source=source,
                price=price,
                bid=bid if bid is not None else price - 1,
                ask=ask if ask is not None else price + 1,
                timestamp=utcnow() - timedelta(minutes=minutes_ago),
            )
        ]
    )


def test_dashboard_and_health(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Crypto Tracker" in response.data

    health = client.get("/api/health").get_json()
    assert health["status"] == "ok"
    assert health["prices"] == 0


def test_config_endpoint(client):
    config = client.get("/api/config").get_json()
    assert "refresh_seconds" in config
    assert config["notifiers"] == [{"name": "log", "class": "LogNotifier"}]
    assert config["default_channels"] == ["log"]
    assert config["pairs"] == []


def test_overview_and_history(client, repos):
    prices, _ = repos
    _seed(prices, price=100, minutes_ago=2)
    _seed(prices, price=110, minutes_ago=1)
    _seed(prices, price=120, minutes_ago=0)

    overview = client.get("/api/overview?range=24h").get_json()
    assert len(overview["pairs"]) == 1
    pair = overview["pairs"][0]
    assert pair["pair"] == "BTC/USDT"
    assert pair["latest"]["price"] == 120
    assert pair["stats"]["count"] == 3
    assert pair["stats"]["min"] == 100
    assert pair["stats"]["max"] == 120
    assert pair["sources"] == ["test"]

    history = client.get("/api/prices/history?asset=BTC&quote_currency=USDT&range=24h").get_json()
    assert [point["price"] for point in history["points"]] == [100, 110, 120]

    stats = client.get("/api/prices/stats?asset=BTC&quote_currency=USDT&range=24h").get_json()
    assert stats["stats"]["count"] == 3


def test_history_validation(client):
    assert client.get("/api/prices/history?range=24h").status_code == 400
    assert client.get("/api/prices/history?asset=BTC&quote_currency=USDT&range=wat").status_code == 400
    assert client.get("/api/overview?range=wat").status_code == 400


def test_alert_crud_api(client):
    response = client.post(
        "/api/alerts",
        json={
            "asset": "btc",
            "quote_currency": "usdt",
            "metric": "price",
            "operator": ">",
            "threshold": 70000,
            "channels": ["log"],
            "cooldown_seconds": 120,
            "repeat": True,
            "label": "breakout",
        },
    )
    assert response.status_code == 201
    alert = response.get_json()["data"]
    assert alert["pair"] == "BTC/USDT"
    assert alert["channels"] == ["log"]
    assert alert["repeat"] is True
    assert alert["condition"] == "price > 70,000.00"

    listed = client.get("/api/alerts").get_json()["data"]
    assert len(listed) == 1

    updated = client.patch(
        f"/api/alerts/{alert['id']}",
        json={"threshold": 80000, "enabled": False, "channels": []},
    )
    assert updated.status_code == 200
    updated_alert = updated.get_json()["data"]
    assert updated_alert["threshold"] == 80000
    assert updated_alert["enabled"] is False
    assert updated_alert["channels"] == []

    deleted = client.delete(f"/api/alerts/{alert['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/alerts").get_json()["data"] == []


def test_alert_validation(client):
    assert client.post("/api/alerts", json={}).status_code == 400
    assert client.post("/api/alerts", data="nope", content_type="text/plain").status_code == 400
    assert (
        client.post(
            "/api/alerts",
            json={"asset": "BTC", "quote_currency": "USDT", "metric": "nope", "operator": ">", "threshold": 1},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/alerts",
            json={"asset": "BTC", "quote_currency": "USDT", "metric": "price", "operator": "!", "threshold": 1},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/alerts",
            json={"asset": "BTC", "quote_currency": "USDT", "metric": "price", "operator": ">", "threshold": "x"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/alerts",
            json={
                "asset": "BTC",
                "quote_currency": "USDT",
                "metric": "price",
                "operator": ">",
                "threshold": 1,
                "channels": ["telegram"],
            },
        ).status_code
        == 400
    )


def test_check_alerts_and_events(client, repos):
    prices, _ = repos
    _seed(prices, price=100)

    created = client.post(
        "/api/alerts",
        json={
            "asset": "BTC",
            "quote_currency": "USDT",
            "metric": "price",
            "operator": ">",
            "threshold": 50,
            "channels": ["log"],
        },
    ).get_json()["data"]

    result = client.post("/api/check", json={}).get_json()
    assert result["count"] == 1
    assert result["triggered"][0]["alert_id"] == created["id"]

    events = client.get("/api/events").get_json()["data"]
    assert len(events) == 1
    assert events[0]["deliveries"][0]["channel"] == "log"
    assert events[0]["deliveries"][0]["success"] is True

    # Edge-triggered: a second check does not fire again.
    assert client.post("/api/check", json={}).get_json()["count"] == 0


def test_legacy_thresholds_and_metrics(client, repos):
    prices, alerts = repos
    _seed(prices, asset="USDT", quote="ARS", source="criptoya:buenbit", price=95, bid=90, ask=100)

    response = client.post("/api/numbers", json={"min_num": 80, "max_num": 200, "currency_type": "buy"})
    assert response.status_code == 200
    assert "Min alert set successfully" in response.get_json()["message"]
    assert "Max alert set successfully" in response.get_json()["message"]

    stored = alerts.list_alerts()
    assert len(stored) == 2
    assert {alert.metric for alert in stored} == {"ask"}
    assert {alert.operator for alert in stored} == {"<", ">"}

    metrics = client.get("/metrics").get_json()
    assert metrics["data"]["pair"] == "USDT/ARS"
    assert metrics["data"]["price"] == 95

    assert client.post("/api/numbers", json={"currency_type": "nope"}).status_code == 400
    assert client.post("/api/numbers", json={"currency_type": "buy"}).status_code == 400

    first_id = stored[0].id
    assert client.delete(f"/delete/alert/{first_id}").status_code == 200
    assert client.delete("/delete/alerts").status_code == 200
    assert alerts.count_alerts() == 0


def test_legacy_thresholds_accept_form_data(client):
    response = client.post("/api/numbers", data={"min_num": "80", "currency_type": "sell"})
    assert response.status_code == 200
    assert "Min alert set successfully" in response.get_json()["message"]


def test_export_csv(client, repos):
    prices, _ = repos
    _seed(prices, price=100, minutes_ago=1)
    _seed(prices, price=110, minutes_ago=0)

    response = client.get("/api/prices/export.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    lines = response.data.decode().strip().splitlines()
    assert lines[0] == "timestamp,asset,quote_currency,source,price,bid,ask,volume"
    assert len(lines) == 3


def test_missing_alert_returns_404(client):
    assert client.delete("/api/alerts/999").status_code == 404
    assert client.patch("/api/alerts/999", json={"enabled": False}).status_code == 404


def test_delete_all_alerts(client, repos):
    _, alerts = repos
    for threshold in (10, 20):
        alerts.create_alert(asset="BTC", quote_currency="USDT", metric="price", operator=">", threshold=threshold)

    response = client.delete("/api/alerts")
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 2
    assert alerts.count_alerts() == 0


def test_legacy_pages_redirect(client):
    assert client.get("/alerts").status_code == 302
    assert client.get("/threshold").status_code == 302


def test_events_limit_is_clamped(client):
    assert client.get("/api/events?limit=0").status_code == 200
    assert client.get("/api/events?limit=abc").status_code == 200
