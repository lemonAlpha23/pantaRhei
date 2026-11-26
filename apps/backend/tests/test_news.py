import asyncio
import hashlib
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient

from app.core import create_application
from app.plugins.news import feeds, news_plugin, service


def item(source: str, index: int):
    base = {
        "chinanews": "https://www.chinanews.com.cn/cj/2026/11-26/",
        "eeo": "https://www.eeo.com.cn/2026/1126/",
    }[source]
    url = f"{base}{1000000 + index}.shtml"
    when = datetime(2026, 11, 26, tzinfo=UTC) + timedelta(minutes=index)
    return {"id": hashlib.sha256(url.encode()).hexdigest(), "sourceId": source, "title": f"文章 {index}",
            "url": url, "publishedAt": when.strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_existing_workspace_migrates_and_get_reads_only_local_data(tmp_path, monkeypatch):
    database = tmp_path / "workspace.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE watchlist(position INTEGER PRIMARY KEY, symbol TEXT UNIQUE NOT NULL)")
        db.execute("INSERT INTO watchlist(symbol) VALUES ('000001')")
        db.execute("PRAGMA user_version = 3")

    def unexpected_fetch(_):
        raise AssertionError("A local read or unauthorized refresh must not access feeds")

    monkeypatch.setattr(feeds, "fetch_feed", unexpected_fetch)
    with TestClient(create_application((news_plugin,), data_dir=tmp_path, token="local")) as client:
        for method, route in (("GET", "/api/news"), ("POST", "/api/news/refresh"), ("GET", "/api/news/id/link")):
            assert client.request(method, route).status_code == 401
        client.headers["Authorization"] = "Bearer local"
        assert client.get("/api/watchlist").status_code == 404
        assert client.get("/api/news").json() == {
            "items": [],
            "sources": [{"id": source.id, "name": source.name, "lastUpdatedAt": None, "error": None}
                        for source in feeds.FEEDS],
        }
        assert client.get("/api/news/missing/link").status_code == 404
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT symbol FROM watchlist").fetchall() == [("000001",)]


def test_version_four_cache_is_adopted_on_news_only_install(tmp_path):
    cached = item("eeo", 12)
    with sqlite3.connect(tmp_path / "workspace.sqlite3") as db:
        # Tables from the shipped 0.2.0 workspace, before per-plugin migrations.
        db.executescript("""
            CREATE TABLE news_items(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL,
                                    url TEXT NOT NULL, published_at TEXT NOT NULL);
            CREATE INDEX news_source_date ON news_items(source_id, published_at DESC, id);
            CREATE TABLE news_sources(source_id TEXT PRIMARY KEY, last_updated_at TEXT, error TEXT);
            PRAGMA user_version = 4;
        """)
        db.execute("INSERT INTO news_items VALUES (:id, :sourceId, :title, :url, :publishedAt)", cached)
        db.execute("INSERT INTO news_sources VALUES ('eeo', ?, NULL)", (cached["publishedAt"],))
    with TestClient(create_application((news_plugin,), data_dir=tmp_path, token="")) as client:
        page = client.get("/api/news").json()
        assert page["items"] == [cached]
        assert next(s for s in page["sources"] if s["id"] == "eeo")["lastUpdatedAt"] == cached["publishedAt"]
        assert client.get(f"/api/news/{cached['id']}/link").json() == {"url": cached["url"]}


def test_source_failures_keep_offline_cache_and_recover(tmp_path, monkeypatch):
    first, second, third = item("chinanews", 1), item("eeo", 2), item("eeo", 3)
    batches = {"chinanews": [first, first], "eeo": [second]}

    def fetch(feed):
        rows = batches[feed.id]
        if rows is None:
            raise feeds.NewsFeedError("来源暂不可用")
        return rows

    monkeypatch.setattr(feeds, "fetch_feed", fetch)
    with TestClient(create_application((news_plugin,), data_dir=tmp_path, token="")) as client:
        refresh = "/api/news/refresh"
        initial = client.post(refresh).json()
        assert initial["items"] == [second, first]
        assert client.post(refresh).json()["items"] == initial["items"]
        link = f"/api/news/{first['id']}/link"
        assert client.get(link).json() == {"url": first["url"]}

        before = client.get("/api/news").json()["sources"][0]["lastUpdatedAt"]
        batches.update(chinanews=None, eeo=[third])
        partial = client.post(refresh).json()
        assert partial["items"] == [third, second, first]
        assert partial["sources"][0]["error"] and partial["sources"][0]["lastUpdatedAt"] == before
        assert partial["sources"][1]["error"] is None
        batches["eeo"] = None
        failed = client.post(refresh)
        assert failed.status_code == 200
        offline = failed.json()
        assert offline["items"] == partial["items"]
        assert all(source["error"] for source in offline["sources"])

    with TestClient(create_application((news_plugin,), data_dir=tmp_path, token="")) as reopened:
        assert reopened.get("/api/news").json() == offline
        batches.update(chinanews=[first], eeo=[third])
        assert all(source["error"] is None for source in reopened.post(refresh).json()["sources"])
        with sqlite3.connect(tmp_path / "workspace.sqlite3") as db:
            db.execute("UPDATE news_items SET url = ? WHERE id = ?", ("https://example.com", first["id"]))
        assert reopened.get(link).status_code == 404


def test_cache_is_bounded_per_source(tmp_path, monkeypatch):
    limit = service.ITEMS_PER_SOURCE
    other = item("eeo", 0)
    batches = {"eeo": [other], "chinanews": [item("chinanews", n) for n in range(limit)]}
    monkeypatch.setattr(feeds, "fetch_feed", lambda feed: batches[feed.id])
    with TestClient(create_application((news_plugin,), data_dir=tmp_path, token="")) as client:
        client.post("/api/news/refresh").raise_for_status()
        batches["chinanews"] = [item("chinanews", n) for n in range(limit - 5, limit + 10)]
        rows = client.post("/api/news/refresh").json()["items"]
        assert len(rows) == limit + 1
        assert rows[0] == item("chinanews", limit + 9) and rows[-1] == other
        assert client.get(f"/api/news/{item('chinanews', 0)['id']}/link").status_code == 404


def test_parallel_refresh_is_coalesced_and_a_slow_source_is_bounded(tmp_path, monkeypatch):
    app = create_application((news_plugin,), data_dir=tmp_path, token="")
    simultaneous = threading.Barrier(2)
    release = threading.Event()
    calls = Counter()
    monkeypatch.setattr(service, "REFRESH_TIMEOUT", 0.25)

    def fetch(feed):
        calls[feed.id] += 1
        simultaneous.wait(3)
        if feed.id == "eeo":
            release.wait(3)
        return [item(feed.id, 1)]

    monkeypatch.setattr(feeds, "fetch_feed", fetch)

    async def refresh_together():
        try:
            async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
                first, second = await asyncio.gather(client.post("/api/news/refresh"), client.post("/api/news/refresh"))
                page = first.json()
                assert page == second.json() == (await client.get("/api/news")).json()
                assert page["items"] == [item("chinanews", 1)]
                assert page["sources"][1]["lastUpdatedAt"] is None
                assert "超时" in page["sources"][1]["error"]
        finally:
            release.set()

    asyncio.run(refresh_together())
    assert calls == {"chinanews": 1, "eeo": 1}
