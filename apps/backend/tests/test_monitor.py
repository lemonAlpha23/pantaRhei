import asyncio
import sqlite3
import threading
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient

from app.api import create_app
from app.plugins.market import provider, quotes
from app.plugins.market.migrations import DEFAULT_WATCHLIST


def feed_row(ticker, *, price="10.00", previous="9.80", timestamp="20250106103426", kind="GP-A", symbol=None):
    fields = [""] * 62
    fields[:5] = ["1" if ticker.startswith("sh") else "51", "股票", symbol or ticker[2:], price, previous]
    fields[30], fields[61] = timestamp, kind
    return f'v_{ticker}="{"~".join(fields)}";'.encode("gb18030")


def price(symbol, amount=10, stamp="2025-01-06T10:34:26+08:00"):
    return {"symbol": symbol, "price": amount, "previousClose": 9.8, "quotedAt": stamp}


def test_lightweight_quote_batch_parses_only_matching_timestamped_equities(monkeypatch):
    payload = b"\n".join((
        feed_row("sz000001", previous="0"), feed_row("sh600519"), feed_row("sh601398", kind="INDEX"),
        feed_row("sz300750", symbol="000001"), feed_row("sh600036", timestamp="20250230153400"),
        feed_row("sh600276", price="nan"), feed_row("sh600900", price="0"),
        feed_row("sz000333", timestamp="20990106103426"), feed_row("sh601318"),
        feed_row("sh600519", price="1", timestamp="20250106103425"),
    ))
    urls = []

    def read(url):
        urls.append(url)
        return payload

    monkeypatch.setattr(provider, "_read", read)
    symbols = ["000001", "600519", "601398", "300750", "600036", "600276", "600900", "000333"]
    result = provider.build_provider().quotes(symbols)
    assert len(urls) == 1 and set(urls[0].split("/q=")[1].split(",")) == {provider._ticker(s) for s in symbols}
    assert result == {"600519": price("600519"), "000001": {**price("000001"), "previousClose": None}}
    with pytest.raises(ValueError, match="batch"):
        provider.build_provider().quotes(["600519"] * (provider.QUOTE_BATCH_SIZE + 1))


def test_legacy_upgrade_failures_and_offline_restart(tmp_path, monkeypatch):
    source = provider.build_provider()
    first, second = "600519", "000001"
    quotes = {first: price(first), second: price(second)}
    with TestClient(create_app(provider=source, data_dir=tmp_path, token="")) as client:
        for symbol in DEFAULT_WATCHLIST:
            client.delete("/api/watchlist/" + symbol).raise_for_status()
        for symbol in [second, first]:
            client.put("/api/watchlist/" + symbol).raise_for_status()
        history = client.get("/api/history/" + first).json()
    # Restore the last pre-monitor schema, including the customized watchlist.
    with sqlite3.connect(tmp_path / "workspace.sqlite3") as db:
        db.execute("DROP TABLE monitor_quotes")
        db.execute("UPDATE plugin_schema SET version=3 WHERE name='market'")
    monkeypatch.setattr(source, "quotes", lambda symbols: (dict(quotes) if symbols == [second, first] else {}))
    with TestClient(create_app(provider=source, data_dir=tmp_path, token="")) as client:
        assert client.get("/api/monitor").json() == {"quotes": [], "failed": [], "checkedAt": None}
        first_page = client.post("/api/monitor/refresh").json()
        assert first_page["quotes"] == [price(second), price(first)]
        assert first_page["checkedAt"].endswith("+08:00") and first_page["failed"] == []
        quotes.clear()
        quotes[first] = price(first, 12, "2025-01-06T10:35:27+08:00")
        partial = client.post("/api/monitor/refresh").json()
        assert partial["quotes"] == [price(second), quotes[first]] and partial["failed"] == [second]
        quotes[first] = price(first, 8)  # An upstream mirror serves an older tick.
        stale = client.post("/api/monitor/refresh").json()
        assert stale["quotes"] == partial["quotes"] and stale["failed"] == [second, first]
        assert client.get("/api/history/" + first).json() == history
    monkeypatch.setattr(source, "quotes", lambda _: pytest.fail("cache read went online"))
    with TestClient(create_app(provider=source, data_dir=tmp_path, token="local")) as client:
        assert client.post("/api/monitor/refresh").status_code == 401
        assert client.get("/api/monitor").status_code == 401
        client.headers["Authorization"] = "Bearer local"
        assert client.get("/api/monitor").json() == stale
        for symbol in (first, second):
            client.delete("/api/watchlist/" + symbol).raise_for_status()
        assert client.post("/api/monitor/refresh").json() == {"quotes": [], "failed": [], "checkedAt": None}


def test_concurrent_requests_share_batches_and_partial_timeout_is_persisted(tmp_path, monkeypatch):
    source = provider.build_provider()
    app = create_app(provider=source, data_dir=tmp_path, token="")
    calls = Counter()
    release = threading.Event()
    both_started = threading.Barrier(2)
    monkeypatch.setattr(quotes, "REFRESH_TIMEOUT", 0.5)
    monkeypatch.setattr(quotes, "QUOTE_BATCH_SIZE", 3)

    def fetch(symbols):
        calls.update(symbols)
        assert len(symbols) == 3
        both_started.wait(timeout=3)
        if DEFAULT_WATCHLIST[0] in symbols:
            release.wait(timeout=3)
        return {symbol: price(symbol) for symbol in symbols}

    monkeypatch.setattr(source, "quotes", fetch)

    async def check():
        try:
            async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
                one, two = await asyncio.gather(client.post("/api/monitor/refresh"), client.post("/api/monitor/refresh"))
                result = one.json()
                assert result == two.json() == (await client.get("/api/monitor")).json()
                assert result["failed"] == list(DEFAULT_WATCHLIST[:3])
                assert result["quotes"] == [price(symbol) for symbol in DEFAULT_WATCHLIST[3:]]
        finally:
            release.set()

    asyncio.run(check())
    assert calls == Counter(DEFAULT_WATCHLIST)
