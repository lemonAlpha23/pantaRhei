from typing_extensions import TypedDict


class NewsItem(TypedDict):
    id: str
    sourceId: str
    title: str
    url: str
    publishedAt: str


class NewsSource(TypedDict):
    id: str
    name: str
    lastUpdatedAt: str | None
    error: str | None


class NewsPage(TypedDict):
    items: list[NewsItem]
    sources: list[NewsSource]
