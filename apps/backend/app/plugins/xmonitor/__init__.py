import sqlite3
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from ...core import Database, Migration, Plugin
from .delivery import DeliveryWorker, add_delivery_log
from .delivery_routes import register_delivery_routes
from .notices import NoticeInbox, NoticeMode, add_inbox
from .order_markers import index_order_markers, register_order_marker_route
from .provider import XProvider
from .service import XMonitor
from .settings import add_settings
from .settings_routes import register_settings_routes
from .storage import XStore, create_tables, normalize_handle


class Subscription(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    handle: str = Field(max_length=64)


class SubscriptionState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool


class NoticeSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    noticeMode: NoticeMode


def _handle(value: str) -> str:
    try:
        return normalize_handle(value)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def _add_connections(db: sqlite3.Connection) -> None:
    add_settings(db)
    add_delivery_log(db)


def create_xmonitor_plugin(provider: XProvider | None = None) -> Plugin:
    def register(app: FastAPI, database: Database) -> None:
        store = XStore(database)
        inbox = NoticeInbox(database)
        source = provider if provider is not None else XProvider(store.settings.x_token)
        delivery = DeliveryWorker(database, store.settings.webhook_target)
        service = XMonitor(store, source, delivery)
        router = APIRouter(prefix="/api/x-monitor", lifespan=service.lifespan)

        router.get("")(service.snapshot)
        router.post("/refresh")(service.refresh)
        register_settings_routes(router, store.settings, source)
        register_delivery_routes(router, delivery)
        register_order_marker_route(router, database)

        @router.get("/notices")
        def notices(limit: Annotated[int, Query(ge=1, le=100)] = 100):
            return inbox.page(limit)

        @router.post("/notices/read-all")
        def read_all():
            return inbox.mark_read()

        @router.post("/notices/{post_id}/read")
        def read_notice(post_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")]):
            return inbox.mark_read(post_id)

        @router.post("/accounts")
        def add(account: Subscription):
            store.add(_handle(account.handle))
            return service.snapshot()

        @router.patch("/accounts/{handle}")
        def update_subscription(handle: str, state: SubscriptionState | NoticeSettings):
            handle = _handle(handle)
            found = (store.change(handle, state.enabled) if isinstance(state, SubscriptionState)
                     else inbox.configure(handle, state.noticeMode))
            if not found:
                raise HTTPException(404, "找不到该博主订阅")
            return service.snapshot()

        @router.delete("/accounts/{handle}")
        def remove(handle: str):
            if not store.change(_handle(handle), None):
                raise HTTPException(404, "找不到该博主订阅")
            return service.snapshot()

        app.include_router(router)

    return Plugin(name="xmonitor", register=register, migrations=(
        Migration(create_tables), Migration(add_inbox), Migration(_add_connections), Migration(index_order_markers),
    ))
