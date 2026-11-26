"""Financial news feeds and local headline storage."""

import sqlite3

from ...core import Migration, Plugin
from .routes import register_news


def _create_tables(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE news_items (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL,
            url TEXT NOT NULL, published_at TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX news_source_date ON news_items(source_id, published_at DESC, id)")
    db.execute("""
        CREATE TABLE news_sources (
            source_id TEXT PRIMARY KEY, last_updated_at TEXT, error TEXT
        )
    """)


news_plugin = Plugin(name="news", register=register_news, migrations=(Migration(_create_tables, legacy_version=4),))
