from pathlib import Path

from fastapi import FastAPI

from .core import Database, create_application
from .plugins.alerts import create_alerts_plugin
from .plugins.market import create_market_plugin
from .plugins.market.provider import MarketDataProvider, build_provider
from .plugins.market.quotes import QuoteFeed
from .plugins.market.storage import MarketStore
from .plugins.news import news_plugin
from .plugins.xmonitor import create_xmonitor_plugin


def create_app(*, provider: MarketDataProvider | None = None, data_dir: Path | None = None, token: str | None = None) -> FastAPI:
    source = provider if provider is not None else build_provider()
    feed = QuoteFeed(source)

    def known_symbol(database: Database, symbol: str) -> bool:
        return symbol in source.instruments or MarketStore(database).imported_instrument(symbol) is not None

    plugins = (create_market_plugin(source, feed=feed), news_plugin, create_alerts_plugin(feed, known_symbol),
               create_xmonitor_plugin())
    return create_application(plugins, data_dir=data_dir, token=token)
