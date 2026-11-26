import csv
import json
import math
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from pathlib import Path
from typing import NamedTuple, Protocol, TypedDict
from urllib.request import Request, urlopen

from ...a_shares import CHINA_STANDARD_TIME, exchange_suffix
from .types import Bar, History, MonitorQuote


class Instrument(TypedDict):
    symbol: str
    name: str
    exchange: str
    currency: str
    timezone: str
    sector: str


class MarketDataProvider(Protocol):
    instruments: dict[str, Instrument]

    def lookup(self, symbol: str) -> Instrument: ...

    def history(self, symbol: str) -> History: ...

    def refresh(self, symbol: str) -> History: ...

    def quotes(self, symbols: list[str]) -> dict[str, MonitorQuote]: ...

    def download(self, symbol: str) -> tuple[Instrument, History]: ...


class MarketDataError(RuntimeError):
    """The upstream provider could not supply a usable daily series."""


class UnknownInstrument(KeyError):
    """This symbol is outside the supported markets or does not identify an A share."""


SNAPSHOTS = Path(__file__).with_name("snapshots")
TENCENT_ENDPOINT = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
DAILY_BARS = 640
QUOTE_BATCH_SIZE = 50


def _ticker(symbol: str) -> str:
    exchange = exchange_suffix(symbol)
    if exchange is None:
        raise UnknownInstrument(symbol)
    return exchange.lower() + symbol


def _bar(day: str, opening: str, high: str, low: str, close: str, shares: int) -> Bar:
    trading_day = date.fromisoformat(day)
    prices = tuple(map(float, (opening, high, low, close)))
    opening_price, high_price, low_price, closing_price = prices
    if (
        trading_day.weekday() >= 5
        or not all(map(math.isfinite, prices))
        or low_price > min(opening_price, closing_price)
        or high_price < max(opening_price, closing_price)
        or shares < 0
    ):
        raise ValueError("Invalid daily bar")
    return Bar(
        time=trading_day.isoformat(),
        open=opening_price,
        high=high_price,
        low=low_price,
        close=closing_price,
        volume=shares,
    )


def _completed_daily_bars(rows: list, now: datetime, volume_multiplier: int) -> list[Bar]:
    today = now.date().isoformat()
    bars: list[Bar] = []
    for row in rows:
        day, opening, close, high, low, volume = row[:6]
        if day == today and now.time() < time(15):
            continue  # Tencent may include the current, unfinished session.
        if day > today or (bars and day <= bars[-1]["time"]):
            raise ValueError("Daily series dates are inconsistent")
        shares = Decimal(volume) * volume_multiplier
        if shares != shares.to_integral_value():
            raise ValueError("Invalid share volume")
        bars.append(_bar(day, opening, high, low, close, int(shares)))
    if not bars:
        raise ValueError("No completed trading sessions")
    return bars


def _equity_quote(quote: list, ticker: str) -> list:
    if len(quote) <= 1:
        # Tencent returns just the exchange identifier for an unknown code.
        raise UnknownInstrument(ticker[2:])
    if len(quote) <= 61 or quote[2] != ticker[2:] or not quote[1].strip():
        raise ValueError("Unexpected security metadata from Tencent")
    expected_exchange = "1" if ticker.startswith("sh") else "51"
    if quote[0] != expected_exchange or quote[61] not in {"GP-A", "GP-A-KCB", "GP-A-CYB"}:
        raise UnknownInstrument(ticker[2:])
    return quote


class _DailySeries(NamedTuple):
    quote: list
    rows: list
    volume_multiplier: int
    source: str
    adjustment: str


def _read(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "PantaRhei/1.0"})
    with urlopen(request, timeout=4) as response:
        return response.read(2_000_000)


def _tencent_quotes(symbols: list[str]) -> dict[str, MonitorQuote]:
    """Fetch one batch. A bad or absent row leaves only that symbol unavailable."""
    if len(symbols) > QUOTE_BATCH_SIZE:
        raise ValueError("Quote batch exceeds the request limit")
    tickers = set()
    for symbol in symbols:
        try:
            tickers.add(_ticker(symbol))
        except UnknownInstrument:
            continue
    if not tickers:
        return {}
    payload = _read("https://qt.gtimg.cn/q=" + ",".join(sorted(tickers)))
    future_limit = datetime.now(CHINA_STANDARD_TIME) + timedelta(minutes=2)
    result = {}
    for row in payload.splitlines():
        match = re.fullmatch(rb'v_((?:sh|sz)[0-9]{6})="([^"]*)";', row.strip())
        if not match:
            continue
        ticker = match[1].decode("ascii")
        if ticker not in tickers:
            continue
        try:
            fields = _equity_quote(match[2].decode("gb18030").split("~"), ticker)
            price = float(fields[3])
            if not math.isfinite(price) or price <= 0 or not re.fullmatch(r"[0-9]{14}", fields[30]):
                continue
            stamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CHINA_STANDARD_TIME)
            if stamp > future_limit:
                continue
            # A first-day listing or incomplete quote can have a price without a reference close.
            try:
                previous = float(fields[4])
            except ValueError:
                previous = None
            symbol = ticker[2:]
            quoted_at = stamp.isoformat()
            if symbol in result and result[symbol]["quotedAt"] > quoted_at:
                continue
            result[symbol] = MonitorQuote(
                symbol=symbol, price=price, quotedAt=quoted_at,
                previousClose=previous if previous is not None and math.isfinite(previous) and previous > 0 else None,
            )
        except (ValueError, UnknownInstrument):
            continue
    return result


def _tencent_daily(ticker: str) -> _DailySeries:
    url = f"{TENCENT_ENDPOINT}?param={ticker},day,,,{DAILY_BARS},qfq"
    payload = json.loads(_read(url))
    if payload["code"] != 0:
        raise ValueError("Unexpected status from Tencent")
    if not payload["data"]:
        raise UnknownInstrument(ticker[2:])
    series = payload["data"][ticker]
    quote = _equity_quote(series["qt"][ticker], ticker)
    field = "qfqday" if series.get("qfqday") else "day"
    # Tencent reports STAR Market volume in shares and other A shares in lots.
    multiplier = 1 if ticker.startswith("sh688") else 100
    adjustment = "前复权" if field == "qfqday" else "不复权"
    return _DailySeries(quote, series[field], multiplier, "腾讯自选股", adjustment)


def _sina_daily(ticker: str) -> _DailySeries:
    # Sina's daily endpoint has no security metadata. Verify the instrument
    # against Tencent's independent, lightweight quote endpoint first.
    text = _read(f"https://qt.gtimg.cn/q={ticker}").decode("gb18030").strip()
    if text.startswith('v_pv_none_match="'):
        raise UnknownInstrument(ticker[2:])
    prefix = f'v_{ticker}="'
    if not text.startswith(prefix) or not text.endswith('";'):
        raise ValueError("Unexpected quote response")
    quote = _equity_quote(text[len(prefix):-2].split("~"), ticker)
    url = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
           f"?symbol={ticker}&scale=240&ma=no&datalen={DAILY_BARS}")
    payload = json.loads(_read(url))
    rows = [[b["day"], b["open"], b["close"], b["high"], b["low"], b["volume"]] for b in payload]
    return _DailySeries(quote, rows, 1, "新浪财经", "不复权")


def _history(series: _DailySeries) -> History:
    now = datetime.now(CHINA_STANDARD_TIME)
    bars = _completed_daily_bars(series.rows, now, series.volume_multiplier)
    latest_quote = datetime.strptime(series.quote[30], "%Y%m%d%H%M%S").date()
    latest_bar = date.fromisoformat(bars[-1]["time"])
    if latest_bar > latest_quote or latest_quote > now.date():
        raise ValueError("Quote and history dates are inconsistent")
    session_complete = latest_quote < now.date() or now.time() >= time(15)
    if session_complete and Decimal(series.quote[6]) > 0 and latest_bar != latest_quote:
        raise ValueError("The most recent traded session is missing")
    return History(bars=bars, source=series.source, adjustment=series.adjustment, asOf=bars[-1]["time"])


class AShareMarketData:
    def __init__(self) -> None:
        catalog = json.loads((SNAPSHOTS / "catalog.json").read_text(encoding="utf-8"))
        self.instruments: dict[str, Instrument] = {row["symbol"]: row for row in catalog["instruments"]}
        self.snapshot_source: str = catalog["source"]
        self.snapshot_adjustment: str = catalog["adjustment"]

    def lookup(self, symbol: str) -> Instrument:
        if symbol in self.instruments:
            return self.instruments[symbol].copy()
        instrument, _ = self.download(symbol)
        return instrument

    def history(self, symbol: str) -> History:
        instrument = self.instruments[symbol]
        path = SNAPSHOTS / f"{instrument['symbol']}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            bars = [
                _bar(row["time"], row["open"], row["high"], row["low"], row["close"], int(row["volume"]))
                for row in csv.DictReader(stream)
            ]
        return History(
            bars=bars,
            source=self.snapshot_source,
            adjustment=self.snapshot_adjustment,
            asOf=bars[-1]["time"],
        )

    def refresh(self, symbol: str) -> History:
        _, history = self.download(symbol)
        return history

    def quotes(self, symbols: list[str]) -> dict[str, MonitorQuote]:
        try:
            return _tencent_quotes(symbols)
        except (OSError, HTTPException) as exc:
            raise MarketDataError("报价源暂时无法读取") from exc

    def download(self, symbol: str) -> tuple[Instrument, History]:
        ticker = _ticker(symbol)
        failure = None
        for fetch in (_tencent_daily, _sina_daily):
            try:
                series = fetch(ticker)
                history = _history(series)
            except UnknownInstrument:
                raise
            except (OSError, HTTPException, ValueError, KeyError, IndexError,
                    TypeError, AttributeError, OverflowError, InvalidOperation) as exc:
                failure = exc
                continue
            known = self.instruments.get(symbol)
            instrument = Instrument(
                symbol=symbol, name="".join(series.quote[1].split()),
                exchange="SSE" if ticker.startswith("sh") else "SZSE",
                timezone="Asia/Shanghai", currency="CNY", sector=known["sector"] if known else "未分类",
            )
            return instrument, history
        raise MarketDataError("行情源暂时无法提供这只股票的完整日线。") from failure


def build_provider() -> MarketDataProvider:
    return AShareMarketData()
