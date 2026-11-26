import asyncio
from collections.abc import Callable

from fastapi import APIRouter, FastAPI, HTTPException, Path

from ...core import Database, Migration, Plugin
from ..market.quotes import QuoteFeed
from .service import AlertChecker
from .storage import AlertStore, create_tables
from .types import AlertsPage, CheckedPage, NewRule, RuleState


def create_alerts_plugin(feed: QuoteFeed, known_symbol: Callable[[Database, str], bool]) -> Plugin:
    def register(app: FastAPI, database: Database) -> None:
        store = AlertStore(database)
        checker = AlertChecker(store, feed)
        router = APIRouter(prefix="/api/alerts", lifespan=checker.lifespan)

        @router.get("", response_model=AlertsPage)
        def list_alerts():
            return store.page()

        @router.post("", response_model=AlertsPage)
        def add_alert(rule: NewRule):
            if not known_symbol(database, rule.symbol):
                raise HTTPException(404, "找不到该股票")
            store.add(rule)
            return store.page()

        @router.post("/check", response_model=CheckedPage)
        async def check_alerts():
            summary = await checker.check()
            return {**await asyncio.to_thread(store.page), "check": summary}

        @router.patch("/{rule_id}", response_model=AlertsPage)
        def update_alert(state: RuleState, rule_id: int = Path(gt=0, le=2**63 - 1)):
            if not store.set_enabled(rule_id, state.enabled):
                raise HTTPException(404, "找不到该提醒规则")
            return store.page()

        @router.delete("/{rule_id}", response_model=AlertsPage)
        def delete_alert(rule_id: int = Path(gt=0, le=2**63 - 1)):
            if not store.delete(rule_id):
                raise HTTPException(404, "找不到该提醒规则")
            return store.page()

        app.include_router(router)

    return Plugin(name="alerts", register=register, migrations=(Migration(create_tables),))
