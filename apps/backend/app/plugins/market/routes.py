import re

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .monitor import QuoteMonitor
from .provider import MarketDataError, UnknownInstrument
from .quotes import QuoteFeed
from .schemas import Instrument
from .service import MarketService, OlderHistory
from .storage import IncompleteHistory, MarketStore
from .types import History, MonitorPage


def register_routes(app: FastAPI, market: MarketService, store: MarketStore, feed: QuoteFeed) -> None:
    monitor = QuoteMonitor(feed, store)

    @app.get("/api/monitor", response_model=MonitorPage)
    def monitor_page():
        return monitor.page()

    @app.post("/api/monitor/refresh", response_model=MonitorPage)
    async def refresh_monitor():
        return await monitor.refresh()

    def known_symbol(symbol: str) -> str:
        if market.instrument(symbol) is None:
            raise HTTPException(404, "找不到该股票")
        return symbol

    @app.exception_handler(MarketDataError)
    async def unavailable(_request: Request, _exc: MarketDataError):
        return JSONResponse(status_code=503, content={"detail": "行情源暂时不可用，请稍后重试。已保存的行情可离线查看。"})

    @app.exception_handler(UnknownInstrument)
    async def missing(_request: Request, _exc: UnknownInstrument):
        return JSONResponse(status_code=404, content={"detail": "未找到该沪深 A 股，请检查股票代码"})

    @app.get("/api/instruments", response_model=list[Instrument])
    def instruments(q: str = ""):
        return market.instruments(q)

    @app.post("/api/instruments/{symbol}/import", response_model=Instrument)
    def import_instrument(symbol: str):
        if not re.fullmatch(r"[0-9]{6}", symbol):
            raise HTTPException(422, "请输入六位数字股票代码")
        return market.import_instrument(symbol)

    @app.get("/api/history/{symbol}", response_model=History)
    def history(symbol: str = Depends(known_symbol)):
        return market.history(symbol)

    @app.post("/api/history/{symbol}/refresh", response_model=History)
    def refresh(symbol: str = Depends(known_symbol)):
        try:
            return market.refresh(symbol)
        except OlderHistory as exc:
            raise HTTPException(409, "行情源返回了较早的数据，已保留本地最新行情") from exc
        except IncompleteHistory as exc:
            raise HTTPException(409, "行情源返回的历史记录不完整，已保留本地行情") from exc

    @app.get("/api/watchlist")
    def watchlist() -> list[str]:
        return store.watchlist()

    @app.put("/api/watchlist/{symbol}")
    def add(symbol: str = Depends(known_symbol)) -> list[str]:
        return store.set_membership(symbol, added=True)

    @app.delete("/api/watchlist/{symbol}")
    def remove(symbol: str = Depends(known_symbol)) -> list[str]:
        return store.set_membership(symbol, added=False)
