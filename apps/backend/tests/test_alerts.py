import asyncio
import threading
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient

from app.api import create_app
from app.core import Database, create_application
from app.plugins.alerts import service, storage
from app.plugins.alerts.types import NewRule
from app.plugins.market import create_market_plugin
from app.plugins.market.provider import CHINA_STANDARD_TIME, MarketDataError, build_provider
from app.plugins.news import news_plugin


URL = "/api/alerts"
START = datetime(2026, 11, 26, 10, 15, tzinfo=CHINA_STANDARD_TIME)
RULE = {"symbol": "000001", "direction": "above", "target": 10.25}


def tick(symbol, price, stamp):
    return {"symbol": symbol, "price": price, "previousClose": None, "quotedAt": stamp.isoformat()}


def test_upgrade_from_previous_release_validation_and_session(tmp_path, monkeypatch):
    source = build_provider()
    monkeypatch.setattr(source, "quotes", lambda _: pytest.fail("没有启用规则不应请求报价"))
    with TestClient(create_application((create_market_plugin(source), news_plugin), data_dir=tmp_path)) as old:
        prior = old.delete("/api/watchlist/600519").json()
    with TestClient(create_app(provider=source, data_dir=tmp_path, token="secret")) as client:
        for route, method, body in [("", "GET", None), ("", "POST", RULE), ("/check", "POST", None),
                                    ("/1", "PATCH", {"enabled": False}), ("/1", "DELETE", None)]:
            assert client.request(method, URL + route, json=body).status_code == 401
        client.headers["Authorization"] = "Bearer secret"
        assert client.get("/api/watchlist").json() == prior
        assert client.post(URL + "/check").json() == {"rules": [], "events": [], "check": {"rules": 0, "evaluated": 0}}
        for field, value in [("symbol", "1e0000"), ("target", 0), ("target", -1), ("target", 2.001),
                             ("target", "10"), ("target", True), ("target", 1000000), ("direction", "up")]:
            assert client.post(URL, json={**RULE, field: value}).status_code == 422
        assert client.post(URL, content='{"symbol":"000001","direction":"above","target":1e309}',
                           headers={"Content-Type": "application/json"}).status_code == 422
        assert client.post(URL, json={**RULE, "symbol": "999999"}).status_code == 404
        assert client.patch(URL + "/1", json={"enabled": True}).status_code == 404
        assert client.patch(URL + "/1", json={"enabled": 1}).status_code == 422
        assert client.delete(URL + "/1").status_code == 404
        for rule_id in ["0", "-1", str(2**63), "1e3"]:
            assert client.delete(URL + "/" + rule_id).status_code == 422
        # Imported instruments are eligible without having to add them to the watchlist.
        info = {**source.instruments["600036"], "symbol": "600000"}
        monkeypatch.setattr(source, "download", lambda _: (info, source.history("600036")))
        client.post("/api/instruments/600000/import").raise_for_status()
        result = client.post(URL, json={**RULE, "symbol": "600000", "target": 999999.99})
        assert result.json()["rules"][0]["symbol"] == "600000"
        client.delete(URL + "/1").raise_for_status()
    with Database(tmp_path).connection() as db:
        assert dict(db.execute("SELECT name, version FROM plugin_schema")) == {"market": 4, "news": 1, "alerts": 1, "xmonitor": 4}


def test_thresholds_freshness_rearm_and_persistent_history(tmp_path, monkeypatch):
    source = build_provider()
    current = START
    monkeypatch.setattr(storage, "now", lambda: current)
    calls = []
    quotes = {}

    def fetch(symbols):
        calls.append(symbols)
        return quotes.copy()

    monkeypatch.setattr(source, "quotes", fetch)
    # Manually drive checks without starting the independent lifespan timer.
    client = TestClient(create_app(provider=source, data_dir=tmp_path, token=""))
    above = client.post(URL, json=RULE).json()["rules"][0]
    below = client.post(URL, json={**RULE, "direction": "below", "target": 8}).json()["rules"][0]
    symbol = RULE["symbol"]
    assert symbol not in client.get("/api/watchlist").json()

    def check(price, stamp):
        quotes[symbol] = tick(symbol, price, stamp)
        return client.post(URL + "/check").json()

    assert check(12, START - timedelta(seconds=1))["events"] == []  # before activation
    assert check(12, START + timedelta(seconds=1))["events"] == []  # future tick
    current += timedelta(minutes=7)
    assert check(12, START + timedelta(minutes=1))["events"] == []  # stale after a break
    without_hit = check(9, current)
    assert without_hit["events"] == [] and without_hit["check"] == {"rules": 2, "evaluated": 2}
    assert check(12, current - timedelta(seconds=1))["events"] == []  # out of order
    current += timedelta(seconds=1)
    fired = check(10.25, current)
    event = fired["events"][0]
    assert event == {**RULE, "id": event["id"], "ruleId": above["id"], "price": 10.25, "quotedAt": current.isoformat()}
    assert fired["rules"] == [below, {**above, "enabled": False}]
    assert fired["check"] == {"rules": 2, "evaluated": 2}
    assert check(10.25, current) == {**fired, "check": {"rules": 1, "evaluated": 0}}
    client.patch(f"{URL}/{above['id']}", json={"enabled": True}).raise_for_status()
    assert check(11, current)["events"] == [event]  # same tick cannot fire twice after rearming
    current += timedelta(seconds=1)
    second = check(7.8, current)
    assert second["events"][0]["ruleId"] == below["id"] and second["events"][1] == event
    assert all(batch == [symbol] for batch in calls)
    last = client.delete(f"{URL}/{below['id']}").json()
    assert last["rules"] == [above]
    assert last["events"][0] == {**second["events"][0], "ruleId": None}

    def offline(_):
        raise MarketDataError("offline")

    monkeypatch.setattr(source, "quotes", offline)
    with TestClient(create_app(provider=source, data_dir=tmp_path, token="")) as reopened:
        assert reopened.get(URL).json() == last
        assert reopened.post(URL + "/check").json() == {**last, "check": {"rules": 1, "evaluated": 0}}


def test_automatic_checks_without_an_open_page_stop_on_shutdown(tmp_path, monkeypatch):
    source = build_provider()
    monkeypatch.setattr(storage, "now", lambda: START)
    monkeypatch.setattr(service, "POLL_INTERVAL", 0.025)
    calls = []
    observed = threading.Event()

    def fetch(symbols):
        calls.append(symbols)
        observed.set()
        return {symbol: tick(symbol, 10.25, START) for symbol in symbols}

    monkeypatch.setattr(source, "quotes", fetch)
    app = create_app(provider=source, data_dir=tmp_path, token="")
    with TestClient(app) as client:
        assert calls == []
        client.post(URL, json=RULE).raise_for_status()
        assert observed.wait(timeout=3)
        deadline = time.monotonic() + 3
        while not (page := client.get(URL).json())["events"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert page["events"][0]["price"] == 10.25
        assert not page["rules"][0]["enabled"]
        assert calls == [[RULE["symbol"]]]
    TestClient(app).post(URL, json=RULE).raise_for_status()
    time.sleep(0.075)
    assert calls == [[RULE["symbol"]]]


def test_overlapping_monitor_and_rule_checks_pause_and_rearm(tmp_path, monkeypatch):
    source = build_provider()
    monkeypatch.setattr(storage, "now", lambda: START)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fetch(symbols):
        calls.append(symbols)
        started.set()
        assert release.wait(timeout=5)
        return {symbol: tick(symbol, 20, START) for symbol in symbols}

    monkeypatch.setattr(source, "quotes", fetch)
    app = create_app(provider=source, data_dir=tmp_path, token="")

    async def run():
        async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
            symbol = "600519"
            for other in (await client.get("/api/watchlist")).json():
                if other != symbol:
                    await client.delete("/api/watchlist/" + other)
            initial = (await client.post(URL, json={**RULE, "symbol": symbol})).json()["rules"][0]["id"]
            first = asyncio.create_task(client.post(URL + "/check"))
            try:
                assert await asyncio.to_thread(started.wait, 3)
                await client.patch(f"{URL}/{initial}", json={"enabled": False})
                await client.patch(f"{URL}/{initial}", json={"enabled": True})
                # The first check captured the previous activation, so its late reply must be ignored.
                update = asyncio.create_task(client.post("/api/monitor/refresh"))
                await asyncio.sleep(0.05)
            finally:
                release.set()
            old, watch = await asyncio.gather(first, update)
            assert old.json()["events"] == [] and old.json()["rules"][0]["enabled"]
            assert watch.json()["quotes"] == [tick(symbol, 20, START)]
            assert calls == [[symbol]]
            results = await asyncio.gather(*(client.post(URL + "/check") for _ in range(5)))
            assert all(len(response.json()["events"]) == 1 for response in results)
            assert (await client.get(URL)).json()["events"][0]["ruleId"] == initial

    asyncio.run(run())


def test_event_history_is_durable_and_page_shows_latest_hundred(tmp_path, monkeypatch):
    source = build_provider()
    app = create_app(provider=source, data_dir=tmp_path, token="")
    store = storage.AlertStore(Database(tmp_path))
    monkeypatch.setattr(storage, "now", lambda: START)
    rule = NewRule(**RULE)
    for _ in range(103):
        store.add(rule)
    active = tuple(store.armed())
    quote = tick(rule.symbol, rule.target, START)
    assert store.evaluate(active, {rule.symbol: quote}) == 103
    assert store.evaluate(active, {rule.symbol: quote}) == 0
    page = TestClient(app).get(URL).json()
    assert [event["id"] for event in page["events"]] == list(range(103, 3, -1))
    assert all(not rule["enabled"] for rule in page["rules"])
    with store.database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0] == 103
    assert store.delete(active[-1].id)
    store.add(rule)
    assert store.armed()[0].id > active[-1].id
