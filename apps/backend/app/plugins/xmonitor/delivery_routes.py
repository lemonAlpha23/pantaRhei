from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from .delivery import DeliveryWorker


PostId = Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")]


class RetryVersion(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    attempts: int = Field(ge=0, le=2**53 - 1)


def register_delivery_routes(router: APIRouter, worker: DeliveryWorker) -> None:
    @router.get("/deliveries")
    def deliveries(status: Literal["all", "sent", "failed", "pending"] = "all",
                   before: Annotated[int | None, Query(ge=1, le=2**53 - 1)] = None):
        return worker.page(status, before)

    @router.get("/deliveries/{post_id}/attempts")
    def history(post_id: PostId):
        return worker.log.history(post_id)

    @router.post("/deliveries/{post_id}/retry")
    def retry(post_id: PostId, version: RetryVersion | None = None):
        return worker.retry(post_id, version.attempts if version else None)
