import pytest

from app.plugins.xmonitor.signals import extract_signal


@pytest.mark.parametrize("text,kind,order_type,action,symbol,price,qty", [
    ("I bought 10 shares of $AAPL at $180.50.", "trade", None, "buy", "AAPL", 180.50, 10),
    ("我已卖出 600519 100股，成交价 1500.00元。", "trade", None, "sell", "600519", 1500, 100),
    ("Sold $BRK.B", "trade", None, "sell", "BRK.B", None, None),
    ("I placed a limit buy order for 10 shares of $AAPL at $180.50.", "order", "limit", "buy", "AAPL", 180.50, 10),
    ("我已提交限价卖单：600519 100 股，委托价 1,500.50 元", "order", "limit", "sell", "600519", 1500.50, 100),
    ("Submitted a market sell order for 0.01 BTC", "order", "market", "sell", "BTC", None, .01),
    ("我已挂单限价买入 600519 200股，委托价 1200元", "order", "limit", "buy", "600519", 1200, 200),
])
def test_explicit_disclosures(text, kind, order_type, action, symbol, price, qty):
    assert extract_signal(text) == {"kind": kind, "orderType": order_type, "action": action,
                                    "symbol": symbol, "quantity": qty, "price": price}


@pytest.mark.parametrize("text", [
    "I might buy $AAPL at $100", "I never bought $AAPL", "He bought $AAPL", "I bought $AAPL?",
    "如果明天低开，我买入 600519", "I bought $AAPL in my paper trading account.",
    "I bought $AAPL and sold $TSLA", "I bought $AAPL puts", "I bought 0 shares of $AAPL at $0.",
    "I cancelled my limit buy order for 10 shares of $AAPL.", "I will place a limit buy order for $AAPL",
    "转述：我已提交限价买单 600519", "https://x.com/example/status/123", "I bought EVERYTHING.",
])
def test_other_posts_remain_text(text):
    assert extract_signal(text) is None
