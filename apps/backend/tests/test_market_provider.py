import json
import unittest
from unittest.mock import patch

from app.plugins.market.provider import MarketDataError, UnknownInstrument, build_provider


def quote(ticker, name, kind):
    fields = [""] * 62
    fields[0] = "1" if ticker.startswith("sh") else "51"
    fields[1:3] = [name, ticker[2:]]
    fields[6] = "1000"
    fields[30] = "20250106153000"
    fields[61] = kind
    return fields


def daily(ticker, fields, field="qfqday", day="2025-01-06"):
    rows = [[day, "10", "11", "12", "9", "1234"]]
    series = {field: rows, "qt": {ticker: fields}}
    return json.dumps({"code": 0, "data": {ticker: series}}).encode()


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.provider = build_provider()

    def test_new_listing_can_have_a_single_completed_bar(self):
        ticker = "sh601398"
        data = daily(ticker, quote(ticker, "工商银行", "GP-A"))
        with patch("app.plugins.market.provider._read", return_value=data):
            instrument, history = self.provider.download("601398")
        self.assertEqual(instrument["name"], "工商银行")
        self.assertEqual(history["asOf"], "2025-01-06")
        self.assertEqual(history["bars"][0]["volume"], 123400)
        self.assertEqual(history["adjustment"], "前复权")
        self.assertNotIn("601398", self.provider.instruments)

    def test_star_market_unadjusted_day_is_in_shares(self):
        ticker = "sh688981"
        data = daily(ticker, quote(ticker, "中芯国际", "GP-A-KCB"), field="day")
        with patch("app.plugins.market.provider._read", return_value=data):
            history = self.provider.refresh("688981")
        self.assertEqual((history["adjustment"], history["bars"][0]["volume"]), ("不复权", 1234))

    def test_source_failure_can_fall_back_to_unadjusted_sina_data(self):
        ticker = "sh601398"
        fields = quote(ticker, "工商银行", "GP-A")
        quote_text = "~".join(fields)
        metadata = f'v_{ticker}="{quote_text}";'.encode("gb18030")
        bars = [{"day": "2025-01-06", "open": "10", "high": "12", "low": "9", "close": "11", "volume": "1001"}]
        with patch("app.plugins.market.provider._read", side_effect=[OSError(), metadata, json.dumps(bars).encode()]):
            history = self.provider.refresh("601398")
        self.assertEqual((history["source"], history["adjustment"]), ("新浪财经", "不复权"))
        self.assertEqual(history["bars"][0]["volume"], 1001)

    def test_non_equities_and_missing_codes_are_rejected(self):
        with patch("app.plugins.market.provider._read") as read:
            for symbol in ("510300", "399001", "900901", "001001", "309800", "../en"):
                with self.subTest(symbol=symbol), self.assertRaises(UnknownInstrument):
                    self.provider.lookup(symbol)
            read.assert_not_called()
        ticker = "sh688999"
        for fields in (["1"], quote(ticker, "其他证券", "ETF")):
            with patch("app.plugins.market.provider._read", return_value=daily(ticker, fields)):
                with self.assertRaises(UnknownInstrument):
                    self.provider.refresh("688999")

    def test_missing_latest_traded_session_is_not_cached_as_a_success(self):
        ticker = "sh601398"
        stale = daily(ticker, quote(ticker, "工商银行", "GP-A"), day="2025-01-03")
        with patch("app.plugins.market.provider._read", side_effect=[stale, OSError()]):
            with self.assertRaises(MarketDataError):
                self.provider.download("601398")

    def test_bundled_catalog_is_available_offline(self):
        with patch("app.plugins.market.provider._read") as read:
            for symbol in self.provider.instruments:
                bars = self.provider.history(symbol)["bars"]
                dates = [bar["time"] for bar in bars]
                self.assertGreaterEqual(len(dates), 260)
                self.assertEqual(dates, sorted(set(dates)))
            read.assert_not_called()
