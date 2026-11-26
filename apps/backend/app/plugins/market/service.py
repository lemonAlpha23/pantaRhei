from decimal import Decimal, ROUND_HALF_UP
from threading import Lock

from .provider import DAILY_BARS, MarketDataProvider, UnknownInstrument
from .types import History
from .storage import MarketStore


class OlderHistory(Exception):
    pass


def closes(history: History) -> tuple[float, float | None, str]:
    bars = history["bars"]
    return bars[-1]["close"], bars[-2]["close"] if len(bars) >= 2 else None, history["asOf"]


def quote(last_close: float, previous_close: float | None, as_of: str) -> dict:
    close = Decimal(str(last_close))
    previous = Decimal(str(previous_close)) if previous_close is not None else None
    change = close - previous if previous is not None else None

    def rounded(value: Decimal) -> float:
        return float(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))

    return {
        "close": float(close),
        "change": rounded(change) if change is not None else None,
        "changePercent": rounded(change / previous * 100) if previous else None,
        "asOf": as_of,
    }


class MarketService:
    def __init__(self, provider: MarketDataProvider, store: MarketStore):
        self.provider = provider
        self.store = store
        self._snapshots = {symbol: provider.history(symbol) for symbol in provider.instruments}
        self._refresh_locks = {}

    def instrument(self, symbol: str) -> dict | None:
        return self.provider.instruments.get(symbol) or self.store.imported_instrument(symbol)

    def history(self, symbol: str) -> History:
        bundled = self._snapshots.get(symbol)
        cached = self.store.history(symbol)
        if cached and (bundled is None or cached["asOf"] >= bundled["asOf"]):
            return cached
        if bundled is not None:
            return bundled
        raise UnknownInstrument(symbol)

    def instruments(self, query: str) -> list[dict]:
        keyword = query.strip().casefold()
        catalog = self.provider.instruments.copy()
        for info in self.store.imported():
            catalog.setdefault(info["symbol"], info)
        cached = self.store.closes()
        result = []
        for symbol, info in catalog.items():
            if keyword not in symbol and keyword not in info["name"].casefold():
                continue
            prices = cached.get(symbol)
            snapshot = self._snapshots.get(symbol)
            if snapshot and (prices is None or snapshot["asOf"] > prices[2]):
                prices = closes(snapshot)
            if prices is not None:
                result.append({**info, **quote(*prices)})
        return result

    def refresh(self, symbol: str) -> History:
        with self._refresh_locks.setdefault(symbol, Lock()):
            fresh = self.provider.refresh(symbol)
            bundled = self._snapshots.get(symbol)
            if bundled and fresh["asOf"] < bundled["asOf"]:
                raise OlderHistory
            snapshot_count = len(bundled["bars"]) if bundled else 0
            if not self.store.save_history(symbol, fresh, snapshot_count=snapshot_count, window_size=DAILY_BARS):
                raise OlderHistory
            return fresh

    def import_instrument(self, symbol: str) -> dict:
        info = self.instrument(symbol)
        if info is None:
            info, history = self.provider.download(symbol)
            self.store.import_instrument(info, history)
        return {**info, **quote(*closes(self.history(symbol)))}
