import asyncio
import hashlib
import json
import os
import sqlite3
import ssl
import time
from collections.abc import Callable
from http.client import HTTPException
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ...core import Database
from .delivery_log import DeliveryLog, add_delivery_log, cancel_deliveries


class WebhookTarget(NamedTuple):
    url: str
    token: str | None = None


class DeliveryResult(NamedTuple):
    ok: bool
    status: int | None
    error: str | None


def create_delivery_table(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE x_deliveries (
            post_id TEXT PRIMARY KEY, destination TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0
        )
    """)
    db.execute("CREATE INDEX x_delivery_due ON x_deliveries(destination, next_attempt) WHERE status != 'sent'")


def valid_webhook_url(value: str) -> bool:
    if not isinstance(value, str) or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return False
    try:
        parts = urlsplit(value)
        port = parts.port
        return bool(parts.scheme == "https" and parts.hostname and parts.username is None and parts.password is None
                    and "#" not in value and "\\" not in value and port != 0)
    except ValueError:
        return False


def webhook_target_from_env() -> WebhookTarget | None:
    url = os.environ.get("PANTARHEI_X_WEBHOOK_URL", "").strip()
    if valid_webhook_url(url):
        return WebhookTarget(url, os.environ.get("PANTARHEI_X_WEBHOOK_TOKEN", "").strip() or None)
    return None


def delivery_configured() -> bool:
    return webhook_target_from_env() is not None


def _destination(target: WebhookTarget) -> str:
    return hashlib.sha256(target.url.encode()).hexdigest()


_FROM_ENV = object()


def enqueue_delivery(db: sqlite3.Connection, post: dict, target=_FROM_ENV) -> None:
    if target is _FROM_ENV:
        target = webhook_target_from_env()
    if not target or not post["signal"]:
        return
    post_id, handle = post["id"], post["handle"]
    payload = {
        "schemaVersion": 1, "event": "x.trade_signal", "eventId": f"x:post:{post_id}",
        "source": "x_public_post", "handle": handle, "postId": post_id,
        "url": f"https://x.com/{handle}/status/{post_id}", "publishedAt": post["publishedAt"],
        "signal": post["signal"],
    }
    db.execute("INSERT OR IGNORE INTO x_deliveries(post_id,destination,payload,created_at) VALUES (?,?,?,?)",
               (post_id, _destination(target), json.dumps(payload, ensure_ascii=False), time.time()))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _network_error(error: object) -> DeliveryResult:
    if isinstance(error, TimeoutError):
        message = "等待接收端响应超时"
    elif isinstance(error, ssl.SSLError):
        message = "无法验证接收端 TLS 连接"
    else:
        message = "无法连接 Webhook 接收端"
    return DeliveryResult(False, None, message)


def send_webhook(target: WebhookTarget, event_id: str, payload: str) -> DeliveryResult:
    if not valid_webhook_url(target.url):
        return DeliveryResult(False, None, "Webhook 地址无效")
    try:
        request = Request(target.url, data=payload.encode(), method="POST",
                          headers={"Content-Type": "application/json", "Idempotency-Key": event_id})
        if target.token:
            request.add_unredirected_header("Authorization", "Bearer " + target.token)
        with build_opener(_NoRedirect()).open(request, timeout=5) as response:
            if 200 <= response.status < 300:
                return DeliveryResult(True, response.status, None)
            return DeliveryResult(False, response.status, f"接收端返回 HTTP {response.status}")
    except HTTPError as error:
        with error:
            return DeliveryResult(False, error.code, f"接收端返回 HTTP {error.code}")
    except URLError as error:
        return _network_error(error.reason)
    except (OSError, ValueError, HTTPException) as error:
        return _network_error(error)


class DeliveryWorker:
    def __init__(self, database: Database, target: Callable[[], WebhookTarget | None] = webhook_target_from_env):
        self.log = DeliveryLog(database)
        self.target = target
        self._lock = asyncio.Lock()

    def page(self, status: str, before: int | None) -> dict:
        target = self.target()
        return self.log.page(status, before, _destination(target) if target else None)

    def _deliver(self, post_id: str | None, expected: int | None = None) -> tuple[bool, str] | None:
        target = self.target()
        if not target:
            return (False, "请先配置原 Webhook 接收地址") if post_id else None
        claim, reason = self.log.claim(_destination(target), post_id, expected)
        if not claim:
            return (False, reason) if reason else None
        result = send_webhook(target, f"x:post:{claim.post_id}", claim.payload)
        self.log.finish(claim, result.ok, result.status, result.error)
        return result.ok, result.error or f"投递成功（HTTP {result.status}）"

    def retry(self, post_id: str, expected: int | None) -> dict:
        ok, message = self._deliver(post_id, expected)
        return {"ok": ok, "message": message}

    async def flush(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            for _ in range(12):
                if await asyncio.to_thread(self._deliver, None) is None:
                    break
