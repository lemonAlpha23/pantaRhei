import json
import sqlite3
from datetime import UTC, datetime
from typing import Literal

from ...core import Database


NoticeMode = Literal["off", "orders", "all"]


def add_inbox(db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE x_accounts ADD COLUMN notice_orders_since TEXT")
    db.execute("ALTER TABLE x_accounts ADD COLUMN notice_trades_since TEXT")
    # NULL keeps ordinary posts out of the inbox, including all posts predating this migration.
    db.execute("ALTER TABLE x_posts ADD COLUMN notice_read INTEGER CHECK (notice_read IN (0, 1))")
    db.execute("""
        CREATE INDEX x_posts_inbox ON x_posts(notice_read, published_at DESC, length(id) DESC, id DESC)
        WHERE notice_read IS NOT NULL
    """)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class NoticeInbox:
    def __init__(self, database: Database):
        self.database = database

    def configure(self, handle: str, mode: NoticeMode) -> bool:
        with self.database.connection() as db:
            # Widening a filter retains the original start time of any already enabled kind.
            updated = db.execute("""
                UPDATE x_accounts SET
                    notice_orders_since = CASE WHEN :mode != 'off' THEN COALESCE(notice_orders_since, :now) END,
                    notice_trades_since = CASE WHEN :mode = 'all' THEN COALESCE(notice_trades_since, :now) END
                WHERE handle = :handle
            """, {"mode": mode, "now": now_utc(), "handle": handle})
            return updated.rowcount == 1

    def page(self, limit: int = 100) -> dict:
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            unread = db.execute("SELECT count(*) FROM x_posts WHERE notice_read = 0").fetchone()[0]
            rows = db.execute("""
                SELECT id, handle, text, published_at AS publishedAt, signal, notice_read AS read
                FROM x_posts WHERE notice_read IS NOT NULL
                ORDER BY notice_read, published_at DESC, length(id) DESC, id DESC LIMIT ?
            """, (limit,))
            items = [{**row, "signal": json.loads(row["signal"]), "read": bool(row["read"])} for row in rows]
            return {"unread": unread, "items": items}

    def mark_read(self, post_id: str | None = None) -> dict:
        with self.database.connection() as db:
            if post_id is None:
                db.execute("UPDATE x_posts SET notice_read = 1 WHERE notice_read = 0")
            else:
                db.execute("UPDATE x_posts SET notice_read = 1 WHERE id = ? AND notice_read = 0", (post_id,))
        return self.page()
