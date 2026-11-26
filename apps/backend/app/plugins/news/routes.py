from fastapi import APIRouter, FastAPI, HTTPException

from ...core import Database
from .service import NewsService
from .types import NewsPage


def register_news(app: FastAPI, database: Database) -> None:
    service = NewsService(database)
    router = APIRouter(prefix="/api/news")

    @router.get("", response_model=NewsPage)
    def cached_news():
        return service.page()

    @router.post("/refresh", response_model=NewsPage)
    async def refresh_news():
        return await service.refresh()

    @router.get("/{item_id}/link")
    def article_link(item_id: str) -> dict[str, str]:
        url = service.article_url(item_id)
        if url is None:
            raise HTTPException(404, "未找到可打开的新闻原文")
        return {"url": url}

    app.include_router(router)
