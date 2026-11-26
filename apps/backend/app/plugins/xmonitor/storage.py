import json
import re
import sqlite3
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ...core import Database
from .delivery import cancel_deliveries, create_delivery_table, enqueue_delivery
from .settings import XSettings
from .signals import extract_signal


def create_tables(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE x_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 1,
            user_id TEXT, initialized INTEGER NOT NULL DEFAULT 0, since_id TEXT,
            page_token TEXT, high_id TEXT, forward_after TEXT, checked_at TEXT, error TEXT
        )
    """)
    db.execute("""
        CREATE TABLE x_posts (
            id TEXT PRIMARY KEY, handle TEXT NOT NULL, text TEXT NOT NULL,
            published_at TEXT NOT NULL, signal TEXT
        )
    """)
    db.execute("CREATE INDEX x_posts_by_time ON x_posts(published_at DESC)")
    db.execute("CREATE INDEX x_posts_by_account ON x_posts(handle)")
    db.execute("CREATE TABLE x_rate_limit (singleton INTEGER PRIMARY KEY CHECK(singleton=1), until REAL NOT NULL)")
    create_delivery_table(db)


def normalize_handle(value: str) -> str:
    handle = value.strip().removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        raise ValueError("请输入 1 至 15 位的 X 用户名，可包含英文字母、数字和下划线")
    return handle.lower()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Account:
    id: int
    handle: str
    generation: int
    user_id: str | None
    initialized: bool
    since_id: str | None
    page_token: str | None
    high_id: str | None
    forward_after: str | None


class XStore:
    def __init__(self, database: Database):
        self.database = database
        self.settings = XSettings(database)

    def snapshot(self) -> dict:
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            accounts = db.execute("""
                SELECT handle, enabled, checked_at AS lastCheckedAt, error,
                    CASE WHEN notice_trades_since IS NOT NULL THEN 'all'
                         WHEN notice_orders_since IS NOT NULL THEN 'orders' ELSE 'off' END AS noticeMode
                FROM x_accounts ORDER BY handle
            """)
            items = [{**row, "enabled": bool(row["enabled"])} for row in accounts]
            posts = db.execute("""
                SELECT p.id, p.handle, p.text, p.published_at AS publishedAt, p.signal, d.status AS delivery
                FROM x_posts p LEFT JOIN x_deliveries d ON d.post_id = p.id
                ORDER BY p.published_at DESC, length(p.id) DESC, p.id DESC LIMIT 200
            """)
            return {"accounts": items, "posts": [
                {**row, "signal": json.loads(row["signal"]) if row["signal"] else None} for row in posts
            ]}

    def add(self, handle: str) -> None:
        with self.database.connection() as db:
            db.execute("INSERT INTO x_accounts(handle) VALUES (?) ON CONFLICT(handle) DO NOTHING", (handle,))

    def change(self, handle: str, enabled: bool | None) -> bool:
        with self.database.connection() as db:
            if enabled is None:
                changed = db.execute("DELETE FROM x_accounts WHERE handle = ?", (handle,))
            else:
                changed = db.execute("""
                    UPDATE x_accounts SET generation = generation + (enabled != ?), enabled = ? WHERE handle = ?
                """, (enabled, enabled, handle))
            if not enabled:
                if enabled is False:
                    db.execute("""
                        UPDATE x_accounts SET initialized=0, since_id=NULL, high_id=NULL, page_token=NULL, forward_after=NULL
                        WHERE handle=?
                    """, (handle,))
                cancel_deliveries(db, handle)
            return changed.rowcount == 1

    def active(self) -> list[Account]:
        with self.database.connection() as db:
            rows = db.execute("""
                SELECT id, handle, generation, user_id, initialized, since_id, page_token, high_id, forward_after
                FROM x_accounts WHERE enabled = 1 ORDER BY id
            """)
            return [Account(*row) for row in rows]

    def cooling_down(self) -> bool:
        with self.database.connection() as db:
            return db.execute("SELECT 1 FROM x_rate_limit WHERE until > ?", (time.time(),)).fetchone() is not None

    def failed(self, account: Account, error: str, retry_after: int | None, invalid_cursor: bool) -> None:
        with self.database.connection() as db:
            db.execute("""
                UPDATE x_accounts SET error = ?, checked_at = ?,
                    page_token = CASE WHEN ? THEN NULL ELSE page_token END,
                    high_id = CASE WHEN ? THEN NULL ELSE high_id END
                WHERE id = ? AND generation = ? AND enabled = 1 AND since_id IS ? AND page_token IS ?
            """, (error, timestamp(), invalid_cursor, invalid_cursor, account.id, account.generation,
                  account.since_id, account.page_token))
            if retry_after is not None:
                db.execute("""
                    INSERT INTO x_rate_limit(singleton, until) VALUES (1, ?)
                    ON CONFLICT(singleton) DO UPDATE SET until = max(until, excluded.until)
                """, (time.time() + retry_after,))

    def save_page(self, account: Account, user_id: str, posts: list[dict], next_token: str | None) -> Account | None:
        # A first visit establishes a baseline without forwarding historical trades.
        next_token = next_token if account.initialized else None
        ids = [post["id"] for post in posts] + [value for value in (account.high_id, account.since_id) if value]
        high = max(ids, key=int, default=None)
        # Without an eligible id on the baseline page, older posts may still exist on subsequent pages.
        forward_after = account.forward_after
        if not account.initialized and high is None:
            forward_after = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        state = replace(account, initialized=True, user_id=user_id, since_id=account.since_id if next_token else high,
                        page_token=next_token, high_id=high if next_token else None, forward_after=forward_after)
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            notice_starts = db.execute("""
                UPDATE x_accounts SET user_id = ?, initialized = 1, since_id = ?, page_token = ?,
                    high_id = ?, forward_after = ?, checked_at = ?, error = NULL
                WHERE id = ? AND generation = ? AND enabled = 1 AND initialized = ? AND since_id IS ? AND page_token IS ?
                RETURNING notice_orders_since, notice_trades_since
            """, (user_id, state.since_id, state.page_token, state.high_id, state.forward_after,
                  timestamp(), account.id, account.generation, account.initialized, account.since_id, account.page_token)).fetchone()
            if notice_starts is None:
                return None
            since_by_kind = dict(zip(("order", "trade"), notice_starts))
            webhook = self.settings.webhook_target(db)
            for post in posts:
                signal = extract_signal(post["text"])
                is_new_signal = (signal and account.initialized
                                 and (not account.since_id or int(post["id"]) > int(account.since_id))
                                 and (not forward_after or post["publishedAt"] > forward_after))
                notice_since = since_by_kind.get(signal["kind"]) if is_new_signal else None
                unread = notice_since is not None and post["publishedAt"] > notice_since
                inserted = db.execute("""
                    INSERT INTO x_posts(id, handle, text, published_at, signal, notice_read) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                """, (post["id"], account.handle, post["text"], post["publishedAt"],
                      json.dumps(signal, ensure_ascii=False) if signal else None, 0 if unread else None))
                if inserted.rowcount and is_new_signal and webhook:
                    enqueue_delivery(db, {**post, "handle": account.handle, "signal": signal}, target=webhook)
        return state
