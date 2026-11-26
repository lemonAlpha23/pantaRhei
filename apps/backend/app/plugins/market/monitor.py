import asyncio
from datetime import datetime

from .provider import CHINA_STANDARD_TIME
from .quotes import QuoteFeed
from .storage import MarketStore
from .types import MonitorPage, MonitorQuote


class QuoteMonitor:
    def __init__(self, feed: QuoteFeed, store: MarketStore):
        self.feed = feed
        self.store = store

    def page(self) -> MonitorPage:
        with self.store.database.connection() as db:
            rows = db.execute("""
                SELECT q.symbol, q.price, q.previous_close, q.quoted_at, q.checked_at, q.failed
                FROM monitor_quotes q JOIN watchlist w ON w.symbol = q.symbol ORDER BY w.position
            """).fetchall()
        return MonitorPage(
            quotes=[MonitorQuote(symbol=symbol, price=price, previousClose=previous, quotedAt=stamp)
                    for symbol, price, previous, stamp, _, _ in rows if price is not None],
            failed=[symbol for symbol, _, _, _, _, failed in rows if failed],
            checkedAt=max((row[4] for row in rows), default=None),
        )

    async def refresh(self) -> MonitorPage:
        symbols = await asyncio.to_thread(self.store.watchlist)
        if symbols:
            quotes = await self.feed.fetch(symbols)
            await asyncio.to_thread(self._save, symbols, quotes)
        return await asyncio.to_thread(self.page)

    def _save(self, symbols: list[str], quotes: dict[str, MonitorQuote]) -> None:
        checked = datetime.now(CHINA_STANDARD_TIME).isoformat(timespec="seconds")
        with self.store.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for symbol in symbols:
                db.execute("""
                    INSERT INTO monitor_quotes(symbol, checked_at, failed) VALUES (?, ?, 1)
                    ON CONFLICT(symbol) DO UPDATE SET checked_at = excluded.checked_at, failed = 1
                """, (symbol, checked))
                if quote := quotes.get(symbol):
                    db.execute("""
                        UPDATE monitor_quotes SET price = :price, previous_close = :previousClose,
                                                  quoted_at = :quotedAt, failed = 0
                        WHERE symbol = :symbol AND (quoted_at IS NULL OR quoted_at <= :quotedAt)
                    """, quote)
