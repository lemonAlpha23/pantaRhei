import asyncio
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.core import Database, create_application
from app.plugins.xmonitor import create_xmonitor_plugin
from app.plugins.xmonitor import delivery


def test_outbox_persists_retries_and_binds_destination(tmp_path, monkeypatch):
    url = "https://receiver.example/events"
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", url)
    database = Database(tmp_path)
    post = {"id": "11", "handle": "author", "publishedAt": "2026-11-26T03:00:00Z", "text": "private test text",
            "signal": {"kind": "order", "orderType": "limit", "action": "buy", "symbol": "AAPL", "quantity": 1, "price": 10}}
    with database.connection() as db:
        delivery.create_delivery_table(db)
        delivery.add_delivery_log(db)
        delivery.enqueue_delivery(db, post)
        delivery.enqueue_delivery(db, post)
        delivery.enqueue_delivery(db, {**post, "id": "12", "signal": None})
    send = Mock(side_effect=[delivery.DeliveryResult(False, 503, "接收端返回 HTTP 503"),
                             delivery.DeliveryResult(True, 204, None)])
    monkeypatch.setattr(delivery, "send_webhook", send)
    now = 1000
    monkeypatch.setattr(delivery.time, "time", lambda: now)
    asyncio.run(delivery.DeliveryWorker(database).flush())
    with database.connection() as db:
        assert db.execute("SELECT status, attempts FROM x_deliveries").fetchall() == [("failed", 1)]
    asyncio.run(delivery.DeliveryWorker(database).flush())
    now += 61
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://another.example/events")
    asyncio.run(delivery.DeliveryWorker(database).flush())
    assert send.call_count == 1
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", url)
    asyncio.run(delivery.DeliveryWorker(database).flush())
    asyncio.run(delivery.DeliveryWorker(database).flush())
    assert send.call_count == 2 and send.call_args_list[0] == send.call_args_list[1]
    _, _, body = send.call_args.args
    data = json.loads(body)
    assert data["eventId"] == "x:post:11" and data["url"] == "https://x.com/author/status/11"
    assert data["signal"] == post["signal"] and "text" not in data
    with database.connection() as db:
        assert db.execute("SELECT status, attempts FROM x_deliveries").fetchall() == [("sent", 2)]


def test_webhook_requires_valid_explicit_endpoint(monkeypatch):
    for value in ["", "http://unknown.example", "https://name:pass@remote.example", "https://remote.example:65536",
                  "https://remote.example/#fragment", "https://remote.example/\nreject"]:
        monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", value)
        assert not delivery.delivery_configured()
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://receiver.example/hook")
    db = sqlite3.connect(":memory:")
    try:
        delivery.create_delivery_table(db)
        delivery.add_delivery_log(db)
        db.commit()
        db.execute("BEGIN")
        delivery.enqueue_delivery(db, {"id": "12", "handle": "author", "publishedAt": "", "signal": {"kind": "order"}})
        db.rollback()
        assert not db.execute("SELECT * FROM x_deliveries").fetchall()
    finally:
        db.close()


def test_upgraded_outbox_and_paginated_history(tmp_path, monkeypatch):
    database = Database(tmp_path)
    url = "https://receiver.example/secret-path"
    target = delivery.WebhookTarget(url, "secret")
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", url)
    with database.connection() as db:
        delivery.create_delivery_table(db)
        db.execute("""
            INSERT INTO x_deliveries(post_id,destination,payload,status,attempts,next_attempt)
            VALUES ('1',?,?,'failed',3,42)
        """, (delivery._destination(target), json.dumps({"handle": "trader"})))
        delivery.add_delivery_log(db)
        for i in range(2, 33):
            delivery.enqueue_delivery(db, {"id": str(i), "handle": "trader", "signal": {"kind": "order"}, "publishedAt": ""})
    worker = delivery.DeliveryWorker(database)
    page = worker.page("all", None)
    assert [r["id"] for r in page["items"]] == [str(i) for i in range(32, 2, -1)]
    assert [r["id"] for r in worker.page("all", page["nextCursor"])["items"]] == ["2", "1"]
    legacy = worker.page("failed", None)["items"][0]
    assert legacy["attempts"] == 3 and legacy["retryable"]
    assert all(legacy[key] is None for key in ("createdAt", "lastAttemptAt", "httpStatus", "error"))
    assert worker.log.history("1") == {"items": []}
    monkeypatch.setattr(delivery, "send_webhook", lambda *_: delivery.DeliveryResult(True, 202, None))
    assert worker.retry("1", 3)["ok"]
    assert worker.log.history("1")["items"][0]["number"] == 4
    assert not worker.retry("1", 4)["ok"]
    assert not worker.retry("2", 0)["ok"]
    assert "secret" not in json.dumps(worker.page("sent", None))


def test_manual_and_scheduled_attempts_share_the_lease_and_stable_event_id(tmp_path, monkeypatch):
    database = Database(tmp_path)
    target = delivery.WebhookTarget("https://old.example/hook")
    worker = delivery.DeliveryWorker(database, lambda: target)
    with database.connection() as db:
        delivery.create_delivery_table(db)
        delivery.add_delivery_log(db)
        db.execute("CREATE TABLE x_posts(id TEXT, handle TEXT)")
        db.execute("INSERT INTO x_posts VALUES ('10','trader')")
        delivery.enqueue_delivery(db, {"id": "10", "handle": "trader", "signal": {"kind": "order"}, "publishedAt": ""}, target)
    failure = delivery.DeliveryResult(False, 503, "接收端返回 HTTP 503")
    monkeypatch.setattr(delivery, "send_webhook", lambda *_: failure)
    asyncio.run(worker.flush())
    changed = delivery.DeliveryWorker(database, lambda: delivery.WebhookTarget("https://new.example/hook"))
    assert not changed.page("failed", None)["items"][0]["retryable"]
    assert not changed.retry("10", 1)["ok"]
    entered, finish = threading.Event(), threading.Event()
    def slow_send(actual, key, body):
        assert actual == target and key == json.loads(body)["eventId"] == "x:post:10"
        entered.set()
        assert finish.wait(4)
        return failure
    monkeypatch.setattr(delivery, "send_webhook", slow_send)
    with ThreadPoolExecutor() as pool:
        first = pool.submit(worker.retry, "10", 1)
        try:
            assert entered.wait(4)
            peer = delivery.DeliveryWorker(database, lambda: target)
            assert not peer.retry("10", 1)["ok"]
            asyncio.run(peer.flush())
            assert peer.log.history("10")["items"][0]["status"] == "sending"
        finally:
            finish.set()
        assert not first.result()["ok"]
    assert not worker.retry("10", 1)["ok"]
    with database.connection() as db:
        delivery.cancel_deliveries(db, "trader")
    assert not worker.retry("10", 2)["ok"]
    log = worker.log.history("10")["items"]
    assert [(r["number"], r["status"], r["httpStatus"]) for r in log] == [(2, "failed", 503), (1, "failed", 503)]
    assert worker.page("failed", None)["items"][0]["nextAttemptAt"] is None


def test_http_failures_are_sanitized_and_transport_sends_idempotency(monkeypatch):
    target = delivery.WebhookTarget("https://receiver.example/secret-path?token=secret", "secret")
    transport = Mock()
    transport.open.side_effect = HTTPError(target.url, 302, "secret", {}, BytesIO(b"secret"))
    monkeypatch.setattr(delivery, "build_opener", lambda _: transport)
    result = delivery.send_webhook(target, "x:test:1", "{}")
    assert result == delivery.DeliveryResult(False, 302, "接收端返回 HTTP 302")
    request = transport.open.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer secret"
    assert request.get_header("Idempotency-key") == "x:test:1"
    transport.open.side_effect = TimeoutError("secret")
    assert delivery.send_webhook(target, "x:test:2", "{}") == delivery.DeliveryResult(False, None, "等待接收端响应超时")


def test_authenticated_delivery_api_recovers_interrupted_attempt(tmp_path, monkeypatch):
    monkeypatch.delenv("PANTARHEI_X_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://receiver.example/events")
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_TOKEN", raising=False)
    database = Database(tmp_path)
    api = TestClient(create_application((create_xmonitor_plugin(),), data_dir=tmp_path, token="local"))
    base = "/api/x-monitor/deliveries"
    assert api.get(base).status_code == api.get(base + "/20/attempts").status_code == 401
    assert api.post(base + "/20/retry").status_code == 401
    api.headers.update({"Authorization": "Bearer local"})
    with database.connection() as db:
        delivery.enqueue_delivery(db, {"id": "20", "handle": "demo", "signal": {"kind": "order"}, "publishedAt": ""})
    assert api.get(base + "?status=invalid").status_code == 422
    assert api.get(base + "?before=0").status_code == 422
    assert api.post(base + "/20/retry", json={"attempts": True}).status_code == 422
    clock = 5000
    monkeypatch.setattr(delivery.time, "time", lambda: clock)
    worker = delivery.DeliveryWorker(database)
    destination = delivery._destination(delivery.webhook_target_from_env())
    first, _ = worker.log.claim(destination, None, None)
    assert first.number == 1
    assert api.get(base + "/20/attempts").json()["items"][0]["status"] == "sending"
    monkeypatch.setattr(delivery, "send_webhook", lambda *_: delivery.DeliveryResult(False, 500, "接收端返回 HTTP 500"))
    clock += 121
    assert api.get(base + "/20/attempts").json()["items"][0]["status"] == "unknown"
    asyncio.run(delivery.DeliveryWorker(database).flush())
    assert api.get(base + "?status=failed").json()["items"][0]["attempts"] == 2
    assert not api.post(base + "/20/retry", json={"attempts": 1}).json()["ok"]
    monkeypatch.setattr(delivery, "send_webhook", lambda *_: delivery.DeliveryResult(True, 202, None))
    assert api.post(base + "/20/retry", json={"attempts": 2}).json()["ok"]
    assert [r["status"] for r in api.get(base + "/20/attempts").json()["items"]] == ["sent", "failed", "unknown"]
    assert not api.post(base + "/20/retry").json()["ok"]
