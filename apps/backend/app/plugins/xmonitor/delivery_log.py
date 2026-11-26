import sqlite3
import time
from datetime import UTC, datetime
from typing import NamedTuple

from ...core import Database


PAGE_SIZE = 30
LEASE_SECONDS = 120


def add_delivery_log(db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE x_deliveries ADD COLUMN created_at REAL")
    db.execute("ALTER TABLE x_deliveries ADD COLUMN lease_until REAL NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE x_deliveries ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
    db.execute("UPDATE x_deliveries SET lease_until=next_attempt WHERE status='pending' AND attempts>0")
    db.execute("""
        CREATE TABLE x_delivery_attempts (
            post_id TEXT NOT NULL, number INTEGER NOT NULL, at REAL NOT NULL, status TEXT NOT NULL,
            http_status INTEGER, error TEXT, PRIMARY KEY (post_id, number)
        )
    """)


def cancel_deliveries(db: sqlite3.Connection, handle: str) -> None:
    # In-flight attempts retain their audit trail even if the subscription is removed.
    condition = "status != 'sent' AND post_id IN (SELECT id FROM x_posts WHERE handle=?)"
    db.execute("DELETE FROM x_deliveries WHERE attempts=0 AND " + condition, (handle,))
    db.execute("UPDATE x_deliveries SET cancelled=1 WHERE " + condition, (handle,))


def _stamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _blocked(row: sqlite3.Row, destination: str | None, now: float) -> str | None:
    if row["status"] != "failed":
        return "仅支持重试已失败的投递"
    if row["cancelled"]:
        return "该订阅已取消此投递"
    if row["lease_until"] > now:
        return "这条投递正在处理中"
    if not destination:
        return "请先配置原 Webhook 接收地址"
    if row["destination"] != destination:
        return "当前 Webhook 与原投递地址不同"
    return None


class Attempt(NamedTuple):
    post_id: str
    number: int
    payload: str


class DeliveryLog:
    def __init__(self, database: Database):
        self.database = database

    def page(self, status: str, before: int | None, destination: str | None) -> dict:
        filters, params = [], []
        if status != "all":
            filters.append("d.status=?")
            params.append(status)
        if before is not None:
            filters.append("d.rowid<?")
            params.append(before)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(f"""
                SELECT d.rowid AS cursor, d.post_id, json_extract(d.payload, '$.handle') AS handle,
                       d.status, d.attempts, d.created_at, d.next_attempt, d.cancelled,
                       d.destination, d.lease_until, a.at, a.http_status, a.error
                FROM x_deliveries d LEFT JOIN x_delivery_attempts a
                  ON a.post_id=d.post_id AND a.number=d.attempts
                {where} ORDER BY d.rowid DESC LIMIT ?
            """, [*params, PAGE_SIZE + 1]).fetchall()
        now = time.time()
        items = []
        for row in rows[:PAGE_SIZE]:
            blocked = _blocked(row, destination, now)
            scheduled = (row["status"] != "sent" and not row["cancelled"] and row["destination"] == destination
                         and row["lease_until"] <= now and row["next_attempt"] > 0)
            items.append({
                "id": row["post_id"], "handle": row["handle"], "status": row["status"], "attempts": row["attempts"],
                "createdAt": _stamp(row["created_at"]), "lastAttemptAt": _stamp(row["at"]),
                "nextAttemptAt": _stamp(row["next_attempt"]) if scheduled else None,
                "httpStatus": row["http_status"], "error": row["error"], "retryable": blocked is None,
                "retryBlockedReason": blocked if row["status"] == "failed" else None,
            })
        return {"items": items, "nextCursor": rows[PAGE_SIZE - 1]["cursor"] if len(rows) > PAGE_SIZE else None}

    def history(self, post_id: str) -> dict:
        now = time.time()
        with self.database.connection() as db:
            rows = db.execute("""
                SELECT a.number, a.at, a.status, a.http_status, a.error, d.lease_until
                FROM x_delivery_attempts a JOIN x_deliveries d ON a.post_id=d.post_id
                WHERE a.post_id=? ORDER BY a.number DESC
            """, (post_id,)).fetchall()
        return {"items": [{"number": n, "at": _stamp(at), "status": "unknown" if state == "sending" and lease <= now else state,
                           "httpStatus": code, "error": error} for n, at, state, code, error, lease in rows]}

    def claim(self, destination: str, post_id: str | None, expected: int | None) -> tuple[Attempt | None, str | None]:
        now = time.time()
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            if post_id is None:
                row = db.execute("""
                    SELECT * FROM x_deliveries WHERE destination=? AND status!='sent' AND cancelled=0
                      AND next_attempt<=? AND lease_until<=? ORDER BY next_attempt, rowid LIMIT 1
                """, (destination, now, now)).fetchone()
                if row is None:
                    return None, None
            else:
                row = db.execute("SELECT * FROM x_deliveries WHERE post_id=?", (post_id,)).fetchone()
                if row is None:
                    return None, "找不到这条投递记录"
                reason = _blocked(row, destination, now)
                if reason:
                    return None, reason
                if expected is not None and row["attempts"] != expected:
                    return None, "投递状态已更新，请刷新记录"
            claim = Attempt(row["post_id"], row["attempts"] + 1, row["payload"])
            db.execute("UPDATE x_deliveries SET attempts=?, lease_until=? WHERE post_id=?",
                       (claim.number, now + LEASE_SECONDS, claim.post_id))
            db.execute("UPDATE x_delivery_attempts SET status='unknown' WHERE post_id=? AND number=? AND status='sending'",
                       (claim.post_id, claim.number - 1))
            db.execute("INSERT INTO x_delivery_attempts(post_id,number,at,status) VALUES (?,?,?,'sending')",
                       (claim.post_id, claim.number, now))
            return claim, None

    def finish(self, claim: Attempt, success: bool, code: int | None, error: str | None) -> None:
        status = "sent" if success else "failed"
        retry_at = 0 if success else time.time() + min(3600, 60 * 2 ** min(claim.number - 1, 6))
        with self.database.connection() as db:
            db.execute("UPDATE x_delivery_attempts SET status=?, http_status=?, error=? WHERE post_id=? AND number=?",
                       (status, code, error, claim.post_id, claim.number))
            # A late response can describe its own attempt but must never overwrite a newer claim.
            db.execute("UPDATE x_deliveries SET status=?, next_attempt=?, lease_until=0 WHERE post_id=? AND attempts=?",
                       (status, retry_at, claim.post_id, claim.number))
