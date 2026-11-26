from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.api import create_app
from app.plugins.market.provider import MarketDataError, UnknownInstrument, build_provider


def test_catalog_matches_bundled_history(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, token="")) as client:
        catalog = client.get("/api/instruments").json()
        assert len(catalog) >= 10
        selected = client.get("/api/instruments", params={"q": "茅台"}).json()
        assert len(selected) == 1
        assert selected == client.get("/api/instruments?q=600519").json()
        for instrument in catalog:
            history = client.get(f"/api/history/{instrument['symbol']}").json()
            bars = history["bars"]
            assert len(bars) >= 260
            dates = [bar["time"] for bar in bars]
            assert dates == sorted(set(dates))
            assert history["asOf"] == instrument["asOf"] == dates[-1]
            assert instrument["close"] == bars[-1]["close"]
            assert instrument["change"] == round(bars[-1]["close"] - bars[-2]["close"], 2)
            assert history["source"] and history["adjustment"]
        assert client.get("/api/history/999999").status_code == 404
        assert client.put("/api/watchlist/999999").status_code == 404


def test_watchlist_membership_survives_restart_and_empty_state(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, token="")) as client:
        defaults = client.get("/api/watchlist").json()
        assert defaults[0] == "600519"
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda _: client.put("/api/watchlist/000001"), range(8)))
        assert all(response.json() == [*defaults, "000001"] for response in results)
        for symbol in [*defaults, "000001"]:
            client.delete(f"/api/watchlist/{symbol}").raise_for_status()

    with TestClient(create_app(data_dir=tmp_path, token="")) as reopened:
        assert reopened.get("/api/watchlist").json() == []
        assert reopened.put("/api/watchlist/600519").json() == ["600519"]
        assert reopened.delete("/api/watchlist/000001").json() == ["600519"]


def test_refresh_persists_and_handles_failure_and_stale_upstream(tmp_path, monkeypatch):
    provider = build_provider()
    original = provider.history("600519")
    new_bar = {**original["bars"][-1], "time": "2090-01-02"}
    fresh = {**original, "bars": [*original["bars"], new_bar], "asOf": new_bar["time"]}
    monkeypatch.setattr(provider, "refresh", lambda _: fresh)
    route = "/api/history/600519/refresh"
    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as client:
        assert client.post(route).json() == fresh

    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as reopened:
        def unavailable(_):
            raise MarketDataError("offline")

        monkeypatch.setattr(provider, "refresh", unavailable)
        assert reopened.post(route).status_code == 503
        monkeypatch.setattr(provider, "refresh", lambda _: original)
        assert reopened.post(route).status_code == 409
        assert reopened.get("/api/history/600519").json() == fresh
        assert reopened.get("/api/instruments?q=600519").json()[0]["asOf"] == new_bar["time"]


def test_local_session_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTARHEI_TOKEN", "session-secret")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get("/api/health").status_code == 401
        assert client.put("/api/watchlist/600519", headers={"Authorization": "Bearer other"}).status_code == 401
        assert client.get("/api/health", headers={"Authorization": "Bearer session-secret"}).json() == {"status": "ok"}


def test_refresh_keeps_complete_history_but_accepts_rolling_windows(tmp_path, monkeypatch):
    provider = build_provider()
    symbol = "600519"
    original = provider.history(symbol)
    bars = original["bars"]
    route = f"/api/history/{symbol}"
    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as client:
        def refresh(history):
            monkeypatch.setattr(provider, "refresh", lambda _: history)
            return client.post(f"{route}/refresh")

        truncated = {**original, "bars": bars[-1:]}
        assert refresh(truncated).status_code == 409
        assert client.get(route).json() == original

        intraday = {**original, "source": "备用源", "adjustment": "不复权", "bars": bars[1:]}
        assert refresh(intraday).json() == intraday
        assert client.get(route).json() == intraday

        next_bar = {**bars[-1], "time": "2090-01-02"}
        rolled = {**intraday, "bars": [*intraday["bars"], next_bar], "asOf": next_bar["time"]}
        assert refresh(rolled).json() == rolled
        result = refresh({**rolled, "bars": [next_bar]})
        assert result.status_code == 409
        assert "历史记录不完整" in result.json()["detail"]

    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as reopened:
        assert reopened.get(route).json() == rolled


def test_import_is_atomic_idempotent_and_available_offline(tmp_path, monkeypatch):
    provider = build_provider()
    symbol = "600000"
    info = {**provider.instruments["600036"], "symbol": symbol, "name": "测试证券"}
    seed = provider.history("600036")
    history = {**seed, "bars": [seed["bars"][-1]]}
    base_url = f"/api/instruments/{symbol}/import"

    def offline(_):
        raise MarketDataError("offline")

    def unknown(_):
        raise UnknownInstrument(symbol)

    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as client:
        assert client.post("/api/instruments/1e0000/import").status_code == 422
        monkeypatch.setattr(provider, "download", unknown)
        assert client.post(base_url).status_code == 404
        monkeypatch.setattr(provider, "download", offline)
        assert client.post(base_url).status_code == 503
        assert client.get(f"/api/instruments?q={symbol}").json() == []

        monkeypatch.setattr(provider, "download", lambda _: (info, history))
        result = client.post(base_url)
        result.raise_for_status()
        imported = result.json()
        assert imported["change"] is None and imported["changePercent"] is None
        assert client.put(f"/api/watchlist/{symbol}").json()[-1] == symbol

    monkeypatch.setattr(provider, "download", offline)
    with TestClient(create_app(provider=provider, data_dir=tmp_path, token="")) as reopened:
        assert reopened.post(base_url).json() == imported
        assert reopened.get("/api/instruments", params={"q": "测试"}).json() == [imported]
        assert reopened.get(f"/api/history/{symbol}").json() == history
        assert reopened.get("/api/watchlist").json()[-1] == symbol
        next_bar = {**history["bars"][0], "time": "2090-01-02"}
        growing = {**history, "bars": [*history["bars"], next_bar], "asOf": next_bar["time"]}
        monkeypatch.setattr(provider, "refresh", lambda _: growing)
        refresh_route = f"/api/history/{symbol}/refresh"
        assert reopened.post(refresh_route).json() == growing
        monkeypatch.setattr(provider, "refresh", lambda _: {**growing, "bars": [next_bar]})
        assert reopened.post(refresh_route).status_code == 409
        assert reopened.get(f"/api/history/{symbol}").json() == growing
