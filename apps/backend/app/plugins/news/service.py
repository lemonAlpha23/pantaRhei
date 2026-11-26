import asyncio
import sqlite3
from datetime import UTC, datetime

from ...core import Database
from . import feeds
from .types import NewsItem, NewsPage


ITEMS_PER_SOURCE = 100
REFRESH_TIMEOUT = 8


class NewsService:
    def __init__(self, database: Database):
        self.database = database
        self.sources = {feed.id: feed for feed in feeds.FEEDS}
        self._pending: asyncio.Task[NewsPage] | None = None

    def page(self) -> NewsPage:
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            # Read the two parts of a page from the same SQLite snapshot.
            db.execute("BEGIN")
            items = [
                dict(row) for row in db.execute("""
                    SELECT id, source_id AS sourceId, title, url, published_at AS publishedAt
                    FROM news_items ORDER BY published_at DESC, id
                """) if row["sourceId"] in self.sources
            ]
            states = {
                key: (updated, error) for key, updated, error in
                db.execute("SELECT source_id, last_updated_at, error FROM news_sources")
            }

        sources = []
        for feed in self.sources.values():
            updated, error = states.get(feed.id, (None, None))
            sources.append({"id": feed.id, "name": feed.name, "lastUpdatedAt": updated, "error": error})
        return {"items": items, "sources": sources}

    def article_url(self, item_id: str) -> str | None:
        with self.database.connection() as db:
            row = db.execute("SELECT source_id, url FROM news_items WHERE id = ?", (item_id,)).fetchone()
        if row and (feed := self.sources.get(row[0])) and feeds.is_article_url(feed, row[1]):
            return row[1]
        return None

    async def refresh(self) -> NewsPage:
        # Concurrent requests share one fetch. A closed client does not cancel another client's refresh.
        if self._pending is None or self._pending.done():
            self._pending = asyncio.create_task(self._update())
        return await asyncio.shield(self._pending)

    async def _update(self) -> NewsPage:
        results = await asyncio.gather(*(self._fetch(feed) for feed in self.sources.values()))
        await asyncio.to_thread(self._save, results)
        return await asyncio.to_thread(self.page)

    @staticmethod
    async def _fetch(feed: feeds.Feed) -> tuple[str, list[NewsItem], str | None]:
        try:
            items = await asyncio.wait_for(asyncio.to_thread(feeds.fetch_feed, feed), timeout=REFRESH_TIMEOUT)
            return feed.id, items, None
        except TimeoutError:
            return feed.id, [], "连接超时，请稍后重试"
        except feeds.NewsFeedError:
            return feed.id, [], "暂时无法读取该来源，请稍后重试"

    def _save(self, results: list[tuple[str, list[NewsItem], str | None]]) -> None:
        updated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for source_id, items, error in results:
                db.execute("""
                    INSERT INTO news_sources(source_id, last_updated_at, error) VALUES (?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        last_updated_at = COALESCE(excluded.last_updated_at, news_sources.last_updated_at),
                        error = excluded.error
                """, (source_id, updated if error is None else None, error))
                if error is not None:
                    continue
                db.executemany("""
                    INSERT INTO news_items(id, source_id, title, url, published_at)
                    VALUES (:id, :sourceId, :title, :url, :publishedAt)
                    ON CONFLICT(id) DO UPDATE SET title = excluded.title, published_at = excluded.published_at
                """, items)
                db.execute("""
                    DELETE FROM news_items WHERE id IN (
                        SELECT id FROM news_items WHERE source_id = ?
                        ORDER BY published_at DESC, id LIMIT -1 OFFSET ?
                    )
                """, (source_id, ITEMS_PER_SOURCE))
