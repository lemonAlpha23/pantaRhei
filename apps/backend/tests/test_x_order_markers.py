from dataclasses import replace

from fastapi.testclient import TestClient

from app.core import Database, create_application
from app.plugins.xmonitor import create_xmonitor_plugin
from app.plugins.xmonitor.provider import XProvider
from app.plugins.xmonitor.signals import extract_signal, price_in_yuan
from app.plugins.xmonitor.storage import XStore


ENDPOINT = "/api/x-monitor/order-markers"
DAY = {"symbol": "600519", "start": "2026-11-26", "end": "2026-11-26"}
FIRST = "2026-11-25T16:00:00.000Z"
LAST = "2026-11-26T15:59:59.999Z"


def post(number, text, published=FIRST):
    return {"id": str(number), "text": text, "publishedAt": published}


def test_markers_from_existing_history_follow_subscription_and_shanghai_date(tmp_path, monkeypatch):
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_URL", raising=False)
    plugin = create_xmonitor_plugin(XProvider(lambda: None))
    create_application((replace(plugin, migrations=plugin.migrations[:3]),), data_dir=tmp_path)
    store = XStore(Database(tmp_path))
    for handle in ("alpha", "beta"):
        store.add(handle)
    alpha, beta = store.active()
    bare = post(9, "我已提交限价买单：600519 100 股，委托价 1500 元。")
    other_exchange = post(20, "我已提交限价买单：600519.SZ")
    store.save_page(alpha, "42", [
        bare, bare, other_exchange, post(21, "我已挂出卖单：SZ600519"), post(22, "我已挂出卖单：600519.BJ"),
        post(23, "我买入了 600519 50 股。"), post(24, "我已挂出买单：600036"),
        post(25, "明天关注 600519。"), post(26, "我已挂出买单：600519", "2026-11-25T15:59:59.999Z"),
        post(27, "我已挂出买单：600519", "2026-11-26T16:00:00.000Z"),
        post(28, "我已挂出市价卖单：SH600519", LAST), post(29, "我已挂出卖单：000001.SZ"),
        post(30, "我已挂出卖单：SZ000001"), post(31, "我已挂出买单：000001.SH"),
        *[post(n, "普通动态", LAST) for n in range(1000, 1201)],
    ], None)
    store.save_page(beta, "43", [post(10, "我已挂出卖单：600519.SH")], None)

    client = TestClient(create_application((plugin,), data_dir=tmp_path, token="local"))
    assert client.get(ENDPOINT, params=DAY).status_code == 401
    client.headers["Authorization"] = "Bearer local"
    assert all(item["id"] != "9" for item in client.get("/api/x-monitor").json()["posts"])
    assert client.get(ENDPOINT, params=DAY).json() == {"items": [
        {"id": "9", "handle": "alpha", "publishedAt": FIRST, "action": "buy", "price": 1500,
         "quantity": 100, "orderType": "limit", "priceInYuan": True},
        {"id": "10", "handle": "beta", "publishedAt": FIRST, "action": "sell", "price": None,
         "quantity": None, "orderType": None, "priceInYuan": False},
        {"id": "28", "handle": "alpha", "publishedAt": LAST, "action": "sell", "price": None,
         "quantity": None, "orderType": "market", "priceInYuan": False},
    ]}
    assert [r["id"] for r in client.get(ENDPOINT, params={**DAY, "symbol": "000001"}).json()["items"]] == ["29", "30"]
    client.patch("/api/x-monitor/accounts/alpha", json={"enabled": False}).raise_for_status()
    assert [r["id"] for r in client.get(ENDPOINT, params=DAY).json()["items"]] == ["10"]
    client.delete("/api/x-monitor/accounts/beta").raise_for_status()
    assert client.get(ENDPOINT, params=DAY).json() == {"items": []}
    client.patch("/api/x-monitor/accounts/alpha", json={"enabled": True}).raise_for_status()
    assert [r["id"] for r in client.get(ENDPOINT, params=DAY).json()["items"]] == ["9", "28"]


def test_markers_validate_exchange_and_calendar_range(tmp_path):
    plugin = create_xmonitor_plugin(XProvider(lambda: None))
    client = TestClient(create_application((plugin,), data_dir=tmp_path))
    for symbol in ("AAPL", "６００５１９", "600519.SH", "920001", "001050", "309999"):
        assert client.get(ENDPOINT, params={**DAY, "symbol": symbol}).status_code == 422
    for start, end in [("2026-11-27", "2026-11-26"), ("2026-02-30", "2026-11-26"),
                       ("20261125", "2026-11-26"), ("2000-01-01", "2026-11-26"),
                       ("9999-12-31", "9999-12-31"), ("0001-01-01", "0001-01-01")]:
        assert client.get(ENDPOINT, params={**DAY, "start": start, "end": end}).status_code == 422


def test_marker_currency_is_taken_only_from_the_disclosed_price():
    cases = [
        ("我已挂出买单：$600519，限价 ￥1,300.50 元。", True),
        ("我已挂出买单：600519，限价 1300.50元。汇率另计，费用 5 美元。", True),
        ("我已挂出买单：600519，限价 1300.50美元。手续费 5 元。", False),
        ("我已挂出买单：600519，限价 1300.50。手续费 5 元。", False),
        ("我已挂出买单：600519，限价 ￥1300.50。", False),
        ("我已挂出买单：600519，限价 $1300.50 元。", False),
        ("I submitted a buy order for $600519 at $1300.50.", False),
    ]
    for text, expected in cases:
        signal = extract_signal(text)
        assert signal["price"] == 1300.50
        assert price_in_yuan(text, signal["price"]) is expected
        assert price_in_yuan(text, 5) is False
