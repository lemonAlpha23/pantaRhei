from fastapi import FastAPI

from ...core import Database, Plugin
from .migrations import market_migrations
from .provider import MarketDataProvider, build_provider
from .quotes import QuoteFeed
from .routes import register_routes
from .service import MarketService
from .storage import MarketStore


def create_market_plugin(provider: MarketDataProvider | None = None, *, feed: QuoteFeed | None = None) -> Plugin:
    source = provider if provider is not None else build_provider()

    def register(app: FastAPI, database: Database) -> None:
        store = MarketStore(database)
        register_routes(app, MarketService(source, store), store, feed or QuoteFeed(source))

    return Plugin(name="market", register=register, migrations=market_migrations(source.instruments))
