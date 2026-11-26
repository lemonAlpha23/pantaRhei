from pydantic import BaseModel


class Instrument(BaseModel):
    symbol: str
    name: str
    exchange: str
    currency: str
    timezone: str
    sector: str
    close: float
    change: float | None
    changePercent: float | None
    asOf: str
