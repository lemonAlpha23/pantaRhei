import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient

from app.core import Database, create_application
from app.plugins.xmonitor import create_xmonitor_plugin, service
from app.plugins.xmonitor.delivery import DeliveryWorker
from app.plugins.xmonitor.provider import XSourceError


BASE = "/api/x-monitor"
STAMP = "2026-11-26T03:00:00.000Z"


@pytest.fixture(autouse=True)
def isolated_webhook(monkeypatch):
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_TOKEN", raising=False)


def post(number):
    return {"id": str(number), "text": "I bought 10 shares of $AAPL at $180.", "publishedAt": STAMP}


class Timeline:
    configured = True

    def __init__(self):
        self.pages = {}
        self.lookups = []
        self.requests = []

    def resolve(self, handle):
        self.lookups.append(handle)
        if handle == "missing":
            raise XSourceError("找不到此 X 账号或时间线")
        return "42"

    def timeline(self, user, since, token):
        assert user == "42"
        self.requests.append((since, token))
        page = self.pages.get((since, token), ([], None))
        if isinstance(page, Exception):
            raise page
        return page


def make_app(path, provider, token=""):
    return create_application((create_xmonitor_plugin(provider),), data_dir=path, token=token)


def test_accounts_cache_and_local_session_without_credentials(tmp_path):
    timeline = Timeline()
    timeline.configured = False
    with TestClient(make_app(tmp_path, timeline, "secret")) as client:
        for method, path, data in [("GET", "", None), ("POST", "/accounts", {"handle": "AbC"}),
                                    ("POST", "/refresh", None), ("DELETE", "/accounts/abc", None),
                                    ("PATCH", "/accounts/abc", {"enabled": True})]:
            assert client.request(method, BASE + path, json=data).status_code == 401
        client.headers["Authorization"] = "Bearer secret"
        for handle in ["", "@@", "a b", "/history", "a" * 16, "中文"]:
            assert client.post(BASE + "/accounts", json={"handle": handle}).status_code == 422
        client.post(BASE + "/accounts", json={"handle": " @AbC "}).raise_for_status()
        response = client.post(BASE + "/accounts", json={"handle": "ABC"}).json()
        assert response["configured"] is False and len(response["accounts"]) == 1
        assert response["accounts"][0]["handle"] == "abc"
        assert client.post(BASE + "/refresh").json()["posts"] == []
        assert not timeline.lookups
        assert client.patch(BASE + "/accounts/abc", json={"enabled": 0}).status_code == 422
        assert client.delete(BASE + "/accounts/missing").status_code == 404
        paused = client.patch(BASE + "/accounts/ABC", json={"enabled": False}).json()["accounts"]
    assert TestClient(make_app(tmp_path, timeline)).get(BASE).json()["accounts"] == paused


def test_baseline_incremental_cursor_persistence_and_subscription_history(tmp_path, monkeypatch):
    timeline = Timeline()
    timeline.pages = {
        (None, None): ([post(10)], "older"),
        ("10", None): ([post(24), post(23)], "next"),
        ("10", "next"): ([post(23), post(11)], None),
    }
    monkeypatch.setattr(service, "PAGE_BUDGET", 1)
    # The real outbox is created atomically with the post. No test payload leaves the process.
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://signals.example.test/events")

    async def hold_delivery(_worker):
        pass

    monkeypatch.setattr(DeliveryWorker, "flush", hold_delivery)
    client = TestClient(make_app(tmp_path, timeline))
    client.post(BASE + "/accounts", json={"handle": "trader"})
    client.post(BASE + "/accounts", json={"handle": "missing"})
    baseline = client.post(BASE + "/refresh").json()
    assert [(item["id"], item["delivery"]) for item in baseline["posts"]] == [("10", None)]
    assert baseline["accounts"][0]["error"] and timeline.requests == [(None, None)]
    first = client.post(BASE + "/refresh").json()
    assert first["deliveryConfigured"]
    assert [(row["id"], row["delivery"]) for row in first["posts"]] == [
        ("24", "pending"), ("23", "pending"), ("10", None)]

    reopened = TestClient(make_app(tmp_path, timeline))
    records = reopened.post(BASE + "/refresh").json()["posts"]
    assert timeline.requests[-1] == ("10", "next") and len(records) == 4
    assert [r["id"] for r in records if r["delivery"] == "pending"] == ["24", "23", "11"]
    reopened.post(BASE + "/refresh").raise_for_status()
    assert timeline.requests[-1] == ("24", None)
    with Database(tmp_path).connection() as db:
        assert db.execute("SELECT COUNT(*) FROM x_deliveries").fetchone() == (3,)
        db.execute("UPDATE x_deliveries SET status='sent' WHERE post_id='23'")
    paused = reopened.patch(BASE + "/accounts/trader", json={"enabled": False}).json()
    assert [p["id"] for p in paused["posts"] if p["delivery"]] == ["23"]
    reopened.patch(BASE + "/accounts/trader", json={"enabled": True})
    timeline.pages[(None, None)] = ([post(50)], "old")
    resumed = reopened.post(BASE + "/refresh").json()
    assert resumed["posts"][0]["id"] == "50" and resumed["posts"][0]["delivery"] is None
    deleted = reopened.delete(BASE + "/accounts/trader").json()
    assert deleted["posts"] == resumed["posts"] and [a["handle"] for a in deleted["accounts"]] == ["missing"]


def test_cooldown_persists_and_expired_page_restarts_from_last_complete_cursor(tmp_path, monkeypatch):
    timeline = Timeline()
    client = TestClient(make_app(tmp_path, timeline))
    client.post(BASE + "/accounts", json={"handle": "trader"})
    monkeypatch.setattr(service, "PAGE_BUDGET", 1)
    timeline.pages[(None, None)] = ([post(10)], None)
    client.post(BASE + "/refresh").raise_for_status()
    timeline.pages[("10", None)] = ([post(22)], "expired")
    client.post(BASE + "/refresh").raise_for_status()
    timeline.pages[("10", "expired")] = XSourceError("分页已过期", invalid_cursor=True)
    assert client.post(BASE + "/refresh").json()["accounts"][0]["error"] == "分页已过期"
    timeline.pages[("10", None)] = XSourceError("X 已限流", retry_after=300)
    assert client.post(BASE + "/refresh").json()["accounts"][0]["error"] == "X 已限流"
    count = len(timeline.requests)
    reopened = TestClient(make_app(tmp_path, timeline))
    reopened.post(BASE + "/refresh").raise_for_status()
    assert len(timeline.requests) == count
    with Database(tmp_path).connection() as db:
        db.execute("UPDATE x_rate_limit SET until=0")
    timeline.pages[("10", None)] = ([post(24), post(22), post(12)], None)
    page = reopened.post(BASE + "/refresh").json()
    assert not page["accounts"][0]["error"] and [p["id"] for p in page["posts"]] == ["24", "22", "12", "10"]


def test_empty_baseline_does_not_forward_preexisting_posts_found_later(tmp_path, monkeypatch):
    timeline = Timeline()
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://signals.example.test/events")
    async def hold_delivery(_worker):
        pass
    monkeypatch.setattr(DeliveryWorker, "flush", hold_delivery)
    client = TestClient(make_app(tmp_path, timeline))
    client.post(BASE + "/accounts", json={"handle": "trader"})
    timeline.pages[(None, None)] = ([], "older")
    assert client.post(BASE + "/refresh").json()["posts"] == []
    timeline.pages[(None, None)] = ([{**post(3), "publishedAt": "2001-01-01T00:00:00.000Z"}], None)
    assert client.post(BASE + "/refresh").json()["posts"][0]["delivery"] is None


def test_slow_manual_sync_returns_snapshot_then_finishes_in_background(tmp_path, monkeypatch):
    timeline = Timeline()
    proceed = threading.Event()
    def delayed(*_):
        assert proceed.wait(timeout=3)
        return [post(15)], None
    timeline.timeline = delayed
    monkeypatch.setattr(service, "MANUAL_WAIT", 0.03)
    app = make_app(tmp_path, timeline)

    async def run():
        async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
            await client.post(BASE + "/accounts", json={"handle": "trader"})
            try:
                state = (await client.post(BASE + "/refresh")).json()
                assert state["syncing"] and state["posts"] == []
            finally:
                proceed.set()
            deadline = time.monotonic() + 3
            while state["syncing"] and time.monotonic() < deadline:
                await asyncio.sleep(0.02)
                state = (await client.get(BASE)).json()
            assert not state["syncing"] and state["posts"][0]["id"] == "15"
    asyncio.run(run())


def test_inflight_refresh_shared_and_late_page_cannot_restore_removed_account(tmp_path):
    timeline = Timeline()
    entered, proceed = threading.Event(), threading.Event()

    def delayed(*args):
        timeline.requests.append(args)
        entered.set()
        assert proceed.wait(timeout=4)
        return [post(100)], None

    timeline.timeline = delayed
    app = make_app(tmp_path, timeline)

    async def run():
        async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
            await client.post(BASE + "/accounts", json={"handle": "trader"})
            runs = [asyncio.create_task(client.post(BASE + "/refresh")) for _ in range(3)]
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                assert (await client.get(BASE)).json()["syncing"]
                await client.delete(BASE + "/accounts/trader")
                await client.post(BASE + "/accounts", json={"handle": "trader"})
            finally:
                proceed.set()
            for response in await asyncio.gather(*runs):
                assert response.json()["posts"] == []
            assert len(timeline.requests) == 1

    asyncio.run(run())


def test_worker_runs_without_a_page_and_stops_on_shutdown(tmp_path, monkeypatch):
    timeline = Timeline()
    timeline.pages[(None, None)] = ([post(10)], None)
    monkeypatch.setattr(service, "POLL_INTERVAL", 0.025)
    with TestClient(make_app(tmp_path, timeline)) as client:
        client.post(BASE + "/accounts", json={"handle": "trader"})
        deadline = time.monotonic() + 3
        while not client.get(BASE).json()["posts"] and time.monotonic() < deadline:
            time.sleep(0.015)
        assert client.get(BASE).json()["posts"][0]["id"] == "10"
    previous = len(timeline.requests)
    time.sleep(0.08)
    assert len(timeline.requests) == previous
