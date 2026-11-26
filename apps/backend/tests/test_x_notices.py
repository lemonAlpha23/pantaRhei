import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core import Database, Migration, Plugin, create_application
from app.plugins.xmonitor import create_xmonitor_plugin, notices
from app.plugins.xmonitor.signals import extract_signal
from app.plugins.xmonitor.storage import XStore, create_tables


BASE = "/api/x-monitor"
INBOX = BASE + "/notices"
ORDER = "我已挂单限价买入 MSFT 8股，委托价 456.78元。"
TRADE = "I bought 10 shares of $AAPL at $180.50."


def stamp(second):
    return f"2026-11-26T03:00:{second:02d}.000Z"


def post(number, text=ORDER, second=30):
    return {"id": str(number), "text": text, "publishedAt": stamp(second)}


class Feed:
    configured = True

    def __init__(self):
        self.posts = []

    def resolve(self, handle):
        return "42"

    def timeline(self, *_):
        return self.posts, None


def client_for(path, feed, token=""):
    return TestClient(create_application((create_xmonitor_plugin(feed),), data_dir=path, token=token))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notices, "now_utc", lambda: stamp(5))


def test_v1_upgrade_requires_opt_in_and_retains_posts(tmp_path):
    database = Database(tmp_path)
    create_application((Plugin("xmonitor", lambda *_: None, (Migration(create_tables),)),), data_dir=tmp_path)
    with database.connection() as db:
        db.execute("INSERT INTO x_accounts(handle, initialized, since_id) VALUES ('trader', 1, '100')")
        db.execute("INSERT INTO x_posts(id, handle, text, published_at, signal) VALUES ('100','trader',?,?,?)",
                   (ORDER, stamp(2), json.dumps(extract_signal(ORDER))))
    feed = Feed()
    client = client_for(tmp_path, feed, "local")
    for path, method in [(INBOX, "GET"), (INBOX + "/read-all", "POST"), (INBOX + "/100/read", "POST")]:
        assert client.request(method, path).status_code == 401
    client.headers.update({"Authorization": "Bearer local"})
    snapshot = client.get(BASE).json()
    assert snapshot["accounts"][0]["noticeMode"] == "off" and snapshot["posts"][0]["id"] == "100"
    for mode in [True, "trades", 1, None]:
        assert client.patch(BASE + "/accounts/trader", json={"noticeMode": mode}).status_code == 422
    assert client.patch(BASE + "/accounts/absent", json={"noticeMode": "all"}).status_code == 404
    assert client.post(INBOX + "/bad-id/read").status_code == 422
    assert client.get(INBOX + "?limit=101").status_code == 422
    assert client.get(INBOX + "?limit=0").status_code == 422
    assert client.get(INBOX).json() == {"unread": 0, "items": []}
    client.patch(BASE + "/accounts/trader", json={"noticeMode": "all"}).raise_for_status()
    feed.posts = [post(100), post(101, second=2), post(102)]
    client.post(BASE + "/refresh").raise_for_status()
    assert [item["id"] for item in client.get(INBOX).json()["items"]] == ["102"]
    with database.connection() as db:
        assert db.execute("SELECT version FROM plugin_schema WHERE name='xmonitor'").fetchone() == (4,)


def test_signal_modes_inflight_page_baseline_and_restart(tmp_path, monkeypatch):
    feed = Feed()
    client = client_for(tmp_path, feed)
    account_url = BASE + "/accounts/trader"
    client.post(BASE + "/accounts", json={"handle": "@Trader"}).raise_for_status()
    client.patch(account_url, json={"noticeMode": "orders"}).raise_for_status()
    feed.posts = [post(100, second=9)]
    client.post(BASE + "/refresh").raise_for_status()
    assert client.get(INBOX).json() == {"unread": 0, "items": []}

    store = XStore(Database(tmp_path))
    account = store.active()[0]
    page = store.save_page(account, "42", [post(109, second=10), post(108, TRADE, 10)], "page2")
    monkeypatch.setattr(notices, "now_utc", lambda: stamp(20))
    client.patch(account_url, json={"noticeMode": "all"}).raise_for_status()
    # The in-flight page retains the orders start date but cannot replay trades from before the change.
    store.save_page(page, "42", [post(107, second=15), post(106, TRADE, 16), post(105, TRADE, 22)], None)
    result = client.get(INBOX).json()
    assert result["unread"] == 3 and [i["id"] for i in result["items"]] == ["105", "107", "109"]
    assert result["items"][0] == {**post(105, TRADE, 22), "handle": "trader", "read": False,
                                  "signal": extract_signal(TRADE)}
    summary = client.get(INBOX + "?limit=1").json()
    assert summary == {"unread": 3, "items": result["items"][:1]}
    read = client.post(INBOX + "/105/read").json()
    assert read["unread"] == 2 and read["items"][-1]["read"]
    assert client.post(INBOX + "/105/read").json() == read

    # Disabling while a request is pending takes effect at commit. Existing unread items stay unread.
    account = store.active()[0]
    client.patch(account_url, json={"noticeMode": "off"}).raise_for_status()
    store.save_page(account, "42", [post(111)], None)
    assert client.get(INBOX).json() == read
    client.patch(account_url, json={"noticeMode": "all"}).raise_for_status()
    client.patch(account_url, json={"enabled": False}).raise_for_status()
    assert store.active() == []
    client.patch(account_url, json={"enabled": True}).raise_for_status()
    feed.posts = [post(120)]
    client.post(BASE + "/refresh").raise_for_status()
    reopened = client_for(tmp_path, feed)
    assert reopened.get(INBOX).json() == read
    assert reopened.get(BASE).json()["accounts"][0]["noticeMode"] == "all"
    reopened.delete(account_url).raise_for_status()
    assert reopened.get(INBOX).json() == read


def test_concurrent_duplicates_limit_and_read_all_through_multiple_clients(tmp_path):
    feed = Feed()
    client = client_for(tmp_path, feed)
    peer = client_for(tmp_path, feed)
    store = XStore(Database(tmp_path))
    store.add("a")
    store.add("b")
    client.patch(BASE + "/accounts/a", json={"noticeMode": "all"}).raise_for_status()
    a, b = store.active()
    a = store.save_page(a, "42", [post(1)], None)
    b = store.save_page(b, "43", [post(2)], None)
    store.save_page(b, "43", [post(3)], None)  # Other handles default to off.
    posts = [post(i) for i in range(10, 115)] + [post(115, "Just watching.")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.save_page(a, "42", posts, None), range(2)))
    assert results.count(None) == 1
    first = peer.get(INBOX).json()
    assert first["unread"] == 105 and len(first["items"]) == 100
    assert first["items"][0]["id"] == "114" and first["items"][-1]["id"] == "15"
    cleared = client.post(INBOX + "/read-all").json()
    assert cleared["unread"] == 0 and all(item["read"] for item in cleared["items"])
    assert peer.post(INBOX + "/read-all").json() == cleared
    store.save_page(store.active()[0], "42", [post(114), post(116, TRADE)], None)
    assert peer.get(INBOX + "?limit=1").json()["items"][0]["id"] == "116"
    assert peer.get(INBOX).json()["unread"] == 1
