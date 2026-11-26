import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

from .delivery import DeliveryWorker
from .provider import XProvider, XSourceError
from .storage import Account, XStore


POLL_INTERVAL = 300
PAGE_BUDGET = 4
MANUAL_WAIT = 18
logger = logging.getLogger(__name__)


class XMonitor:
    def __init__(self, store: XStore, provider: XProvider, delivery: DeliveryWorker):
        self.store = store
        self.provider = provider
        self.delivery = delivery
        self._running: asyncio.Task | None = None
        self._slots = asyncio.Semaphore(3)

    def snapshot(self) -> dict:
        return {**self.store.snapshot(), "configured": self.provider.configured,
                "deliveryConfigured": self.store.settings.webhook_target() is not None,
                "syncing": self._running is not None and not self._running.done()}

    async def _account(self, account: Account) -> None:
        async with self._slots:
            try:
                if await asyncio.to_thread(self.store.cooling_down):
                    return
                user_id = account.user_id or await asyncio.to_thread(self.provider.resolve, account.handle)
                for _ in range(PAGE_BUDGET):
                    if await asyncio.to_thread(self.store.cooling_down):
                        return
                    posts, token = await asyncio.to_thread(self.provider.timeline, user_id, account.since_id, account.page_token)
                    if token is not None and token == account.page_token:
                        await asyncio.to_thread(self.store.failed, account, "X 重复返回分页位置，请稍后同步", None, True)
                        return
                    account = await asyncio.to_thread(self.store.save_page, account, user_id, posts, token)
                    if not account or not account.page_token:
                        return
            except XSourceError as error:
                await asyncio.to_thread(self.store.failed, account, str(error), error.retry_after, error.invalid_cursor)

    async def _sync(self) -> None:
        if self.provider.configured and not await asyncio.to_thread(self.store.cooling_down):
            accounts = await asyncio.to_thread(self.store.active)
            await asyncio.gather(*(self._account(account) for account in accounts))
        await self.delivery.flush()

    def start(self) -> asyncio.Task:
        if not self._running or self._running.done():
            self._running = asyncio.create_task(self._sync())
        return self._running

    async def refresh(self) -> dict:
        # Multiple windows join one sync. Slow accounts can finish after the HTTP response.
        job = self.start()
        done, _ = await asyncio.wait({job}, timeout=MANUAL_WAIT)
        if done:
            job.result()
        return await asyncio.to_thread(self.snapshot)

    async def _poll(self) -> None:
        while True:
            try:
                await self.start()
            except sqlite3.OperationalError:
                logger.exception("X 监控暂时无法访问本地存储")
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
            if self._running and not self._running.done():
                self._running.cancel()
                with suppress(asyncio.CancelledError):
                    await self._running
