import hashlib
import html
import re
import time
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from .types import NewsItem


class NewsFeedError(RuntimeError):
    """The publisher's feed could not provide usable headlines."""


@dataclass(frozen=True)
class Feed:
    id: str
    name: str
    url: str
    article_url: re.Pattern[str]


FEEDS = (
    Feed("chinanews", "中新网财经", "https://www.chinanews.com.cn/rss/finance.xml",
         re.compile(r"https://www\.chinanews\.com\.cn/cj/[0-9]{4}/[0-9]{2}-[0-9]{2}/[0-9]+\.shtml")),
    Feed("eeo", "经济观察网", "https://www.eeo.com.cn/rss.xml",
         re.compile(r"https://www\.eeo\.com\.cn/[0-9]{4}/[0-9]{4}/[0-9]+\.shtml")),
)

MAX_BYTES = 256 * 1024
MAX_ITEMS = 40
SOCKET_TIMEOUT = 4


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_article_url(feed: Feed, url: str) -> bool:
    """Only canonical HTTPS articles on the publisher's own origin may be opened."""
    return feed.article_url.fullmatch(url) is not None


def _download(feed: Feed) -> bytes:
    request = Request(feed.url, headers={"Accept": "application/rss+xml, application/xml",
                                        "User-Agent": "PantaRhei/1.0"})
    deadline = time.monotonic() + 8
    body = bytearray()
    with build_opener(_NoRedirect()).open(request, timeout=SOCKET_TIMEOUT) as response:
        while time.monotonic() < deadline:
            block = response.read1(min(65536, MAX_BYTES + 1 - len(body)))
            if not block:
                return bytes(body)
            body.extend(block)
            if len(body) > MAX_BYTES:
                raise NewsFeedError("订阅内容超过大小限制")
    raise NewsFeedError("订阅读取超时")


def _parse_item(feed: Feed, item: ElementTree.Element) -> NewsItem | None:
    raw_title = item.findtext("title") or ""
    # EEO sometimes HTML-escapes quotation marks twice inside its RSS titles.
    title = " ".join(html.unescape(html.unescape(raw_title)).split())
    url = (item.findtext("link") or "").strip()
    # EEO's feed still spells its canonical, HTTPS-capable article URLs as HTTP.
    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")
    if not title or len(title) > 300 or not is_article_url(feed, url):
        return None
    try:
        stamp = parsedate_to_datetime(item.findtext("pubDate") or "")
        if stamp.tzinfo is None:
            return None
        published_at = stamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (OverflowError, TypeError, ValueError):
        return None
    return NewsItem(id=hashlib.sha256(url.encode("ascii")).hexdigest(), sourceId=feed.id,
                    title=title, url=url, publishedAt=published_at)


def fetch_feed(feed: Feed) -> list[NewsItem]:
    if feed not in FEEDS:
        raise NewsFeedError("未知新闻来源")
    try:
        document = _download(feed).decode("utf-8-sig")
        if "<!DOCTYPE" in document.upper() or "\x00" in document:
            raise NewsFeedError("订阅文档格式不受支持")
        channel = ElementTree.fromstring(document).find("channel")
        if channel is None:
            raise NewsFeedError("订阅缺少新闻频道")
        articles: dict[str, NewsItem] = {}
        for entry in channel.iterfind("item"):
            item = _parse_item(feed, entry)
            if item is not None:
                articles.setdefault(item["id"], item)
            if len(articles) == MAX_ITEMS:
                break
        if not articles:
            raise NewsFeedError("订阅中没有可用的财经标题")
        return sorted(articles.values(), key=lambda row: row["publishedAt"], reverse=True)
    except (OSError, HTTPException, TimeoutError, UnicodeError, ElementTree.ParseError) as exc:
        raise NewsFeedError("财经订阅暂时无法读取") from exc
