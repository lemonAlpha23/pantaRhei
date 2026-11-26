import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ...a_shares import CHINA_STANDARD_TIME, exchange_suffix
from ...core import Database
from .signals import price_in_yuan


CalendarDate = Annotated[str, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]


def index_order_markers(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE INDEX x_orders_by_symbol_time ON x_posts(json_extract(signal, '$.symbol'), published_at)
        WHERE json_extract(signal, '$.kind') = 'order'
    """)


def _utc_midnight(day: date) -> str:
    stamp = datetime.combine(day, time.min, tzinfo=CHINA_STANDARD_TIME).astimezone(UTC)
    return stamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def register_order_marker_route(router: APIRouter, database: Database) -> None:
    @router.get("/order-markers")
    def order_markers(symbol: Annotated[str, Query(min_length=6, max_length=6)], start: CalendarDate, end: CalendarDate):
        exchange = exchange_suffix(symbol)
        if exchange is None:
            raise HTTPException(422, "请输入支持的沪深 A 股代码")
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if not 0 <= (last - first).days <= 3660:
                raise ValueError
            since = _utc_midnight(first)
            until = _utc_midnight(last + timedelta(days=1))
        except (ValueError, OverflowError):
            raise HTTPException(422, "请选择有效的起止日期，间隔最多 3660 天") from None

        with database.connection() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT p.id, p.handle, p.text, p.published_at AS publishedAt,
                       json_extract(p.signal, '$.action') AS action,
                       json_extract(p.signal, '$.orderType') AS orderType,
                       json_extract(p.signal, '$.price') AS price,
                       json_extract(p.signal, '$.quantity') AS quantity
                FROM x_posts p JOIN x_accounts a ON a.handle = p.handle
                WHERE a.enabled = 1 AND json_extract(p.signal, '$.kind') = 'order'
                  AND json_extract(p.signal, '$.symbol') IN (?, ?, ?)
                  AND p.published_at >= ? AND p.published_at < ?
                ORDER BY p.published_at, length(p.id), p.id
            """, (symbol, f"{symbol}.{exchange}", exchange + symbol, since, until))
            items = []
            for row in rows:
                marker = dict(row)
                marker["priceInYuan"] = price_in_yuan(marker.pop("text"), marker["price"])
                items.append(marker)
            return {"items": items}
