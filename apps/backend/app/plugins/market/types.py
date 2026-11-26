from typing_extensions import TypedDict


class Bar(TypedDict):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class History(TypedDict):
    bars: list[Bar]
    source: str
    adjustment: str
    asOf: str


class MonitorQuote(TypedDict):
    symbol: str
    price: float
    previousClose: float | None
    quotedAt: str


class MonitorPage(TypedDict):
    quotes: list[MonitorQuote]
    failed: list[str]
    checkedAt: str | None
