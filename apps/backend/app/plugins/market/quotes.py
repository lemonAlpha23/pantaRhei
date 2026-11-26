import asyncio

from .provider import QUOTE_BATCH_SIZE, MarketDataError, MarketDataProvider
from .types import MonitorQuote


REFRESH_TIMEOUT = 12


class QuoteFeed:
    """Share in-flight batches between monitor windows and the price alert worker."""

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider
        self._requests: dict[str, asyncio.Task[dict[str, MonitorQuote]]] = {}
        self._slots = asyncio.Semaphore(3)

    async def fetch(self, symbols: list[str]) -> dict[str, MonitorQuote]:
        missing = [s for s in dict.fromkeys(symbols) if s not in self._requests]
        for start in range(0, len(missing), QUOTE_BATCH_SIZE):
            batch = missing[start:start + QUOTE_BATCH_SIZE]
            task = asyncio.create_task(self._load(batch))
            self._requests.update(dict.fromkeys(batch, task))
        tasks = {self._requests[s] for s in symbols}
        batches = await asyncio.gather(*(asyncio.shield(task) for task in tasks))
        requested = set(symbols)
        return {s: q for batch in batches for s, q in batch.items() if s in requested}

    async def _load(self, symbols: list[str]) -> dict[str, MonitorQuote]:
        try:
            async with asyncio.timeout(REFRESH_TIMEOUT):
                async with self._slots:
                    return await asyncio.to_thread(self.provider.quotes, symbols)
        except (MarketDataError, TimeoutError):
            return {}
        finally:
            for symbol in symbols:
                self._requests.pop(symbol, None)
