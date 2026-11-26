import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

from ..market.quotes import QuoteFeed
from .storage import AlertStore, ArmedRule
from .types import CheckSummary


POLL_INTERVAL = 30
logger = logging.getLogger(__name__)


class AlertChecker:
    def __init__(self, store: AlertStore, feed: QuoteFeed):
        self.store = store
        self.feed = feed
        self._checks: dict[tuple[ArmedRule, ...], asyncio.Task[int]] = {}

    async def check(self) -> CheckSummary:
        rules = tuple(await asyncio.to_thread(self.store.armed))
        if not rules:
            return CheckSummary(rules=0, evaluated=0)
        if rules not in self._checks:
            self._checks[rules] = asyncio.create_task(self._run_once(rules))
        evaluated = await asyncio.shield(self._checks[rules])
        return CheckSummary(rules=len(rules), evaluated=evaluated)

    async def _run_once(self, rules: tuple[ArmedRule, ...]) -> int:
        try:
            symbols = list(dict.fromkeys(rule.symbol for rule in rules))
            quotes = await self.feed.fetch(symbols)
            return await asyncio.to_thread(self.store.evaluate, rules, quotes) if quotes else 0
        finally:
            self._checks.pop(rules, None)

    async def _poll(self) -> None:
        while True:
            try:
                await self.check()
            except sqlite3.OperationalError:
                logger.exception("价格提醒暂时无法访问本地存储")
            await asyncio.sleep(POLL_INTERVAL)

    @asynccontextmanager
    async def lifespan(self, _app):
        poller = asyncio.create_task(self._poll())
        try:
            yield
        finally:
            poller.cancel()
            with suppress(asyncio.CancelledError):
                await poller
            await asyncio.gather(*self._checks.values(), return_exceptions=True)
