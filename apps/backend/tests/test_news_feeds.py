import io
import re
from dataclasses import replace
from xml.etree import ElementTree

import pytest

from app.plugins.news import feeds


CHINANEWS, EEO = feeds.FEEDS
EEO_URL = "https://www.eeo.com.cn/2026/1126/1103246.shtml"
CHINANEWS_URL = "https://www.chinanews.com.cn/cj/2026/11-26/10737911.shtml"


def rss(rows):
    root = ElementTree.Element("rss")
    channel = ElementTree.SubElement(root, "channel")
    for title, link, published in rows:
        item = ElementTree.SubElement(channel, "item")
        for tag, value in (("title", title), ("link", link), ("pubDate", published),
                           ("description", "此处正文不会进入持久化记录")):
            ElementTree.SubElement(item, tag).text = value
    return ElementTree.tostring(root, encoding="utf-8")


def test_normalizes_titles_https_and_utc_and_deduplicates(monkeypatch):
    published = "Thu, 26 Nov 2026 09:34:57 +0800"
    payload = rss([
        (" 前日  快讯 ", EEO_URL.replace("1103246", "1103000"), "Wed, 25 Nov 2026 21:00:00 GMT"),
        ("   消费  &amp;quot;观察&amp;quot;  ", EEO_URL.replace("https:", "http:"), published),
        ("重复稿", EEO_URL, published),
        ("缺少时区", EEO_URL.replace("1103246", "1111111"), "Thu, 26 Nov 2026 09:00:00"),
        ("第三方链接", "https://example.com/2026/1126/1103246.shtml", published),
    ])
    monkeypatch.setattr(feeds, "_download", lambda feed: payload)
    stories = feeds.fetch_feed(EEO)
    assert len(stories) == 2
    latest = stories[0]
    assert latest == {
        "id": latest["id"], "sourceId": "eeo", "title": '消费 "观察"',
        "url": EEO_URL, "publishedAt": "2026-11-26T01:34:57Z",
    }
    assert re.fullmatch("[0-9a-f]{64}", latest["id"])
    monkeypatch.setattr(feeds, "_download", lambda feed: rss([("标题修订", EEO_URL, published)]))
    assert feeds.fetch_feed(EEO)[0]["id"] == latest["id"]


def test_article_link_is_canonical_and_owned_by_this_source():
    assert feeds.is_article_url(CHINANEWS, CHINANEWS_URL)
    assert feeds.is_article_url(EEO, EEO_URL)
    for url in (
        CHINANEWS_URL, EEO_URL + "?url=external", EEO_URL + "#fragment",
        EEO_URL.replace("www.", "alternate."), EEO_URL.replace(".cn/", ".cn:8443/"),
        EEO_URL.replace("www.eeo", "other.example@www.eeo"),
        "https://www.eeo.com.cn/redirect", EEO_URL.replace("https:", "http:"),
    ):
        assert not feeds.is_article_url(EEO, url)


def test_limits_the_number_of_headlines(monkeypatch):
    rows = [
        (f"标题 {i}", CHINANEWS_URL.replace("10737911", str(1000000 + i)), "Thu, 26 Nov 2026 08:00:00 +0800")
        for i in range(feeds.MAX_ITEMS + 10)
    ]
    monkeypatch.setattr(feeds, "_download", lambda feed: rss(rows))
    assert len(feeds.fetch_feed(CHINANEWS)) == feeds.MAX_ITEMS


@pytest.mark.parametrize("payload", [b"<html/>", b"<rss>", b"<rss><channel/></rss>",
                                     b'<!DOCTYPE rss [<!ENTITY x "hello">]><rss/>'])
def test_invalid_or_empty_feed_is_an_update_failure(monkeypatch, payload):
    monkeypatch.setattr(feeds, "_download", lambda feed: payload)
    with pytest.raises(feeds.NewsFeedError):
        feeds.fetch_feed(EEO)


def test_unregistered_feed_never_reaches_the_network(monkeypatch):
    monkeypatch.setattr(feeds, "_download", lambda _: pytest.fail("Unexpected network access"))
    with pytest.raises(feeds.NewsFeedError):
        feeds.fetch_feed(replace(EEO, url="https://example.com/rss"))


def test_download_is_bounded_and_does_not_follow_redirects(monkeypatch):
    class TooLarge:
        def open(self, request, timeout):
            assert request.full_url == EEO.url
            assert timeout == feeds.SOCKET_TIMEOUT
            return io.BytesIO(b"x" * (feeds.MAX_BYTES + 1))

    def opener(handler):
        assert handler.redirect_request(None, None, 302, "", {}, "https://example.com/") is None
        return TooLarge()

    monkeypatch.setattr(feeds, "build_opener", opener)
    with pytest.raises(feeds.NewsFeedError, match="大小"):
        feeds.fetch_feed(EEO)
