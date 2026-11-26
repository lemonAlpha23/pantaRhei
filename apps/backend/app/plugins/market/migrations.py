import sqlite3
from collections.abc import Collection

from ...core import Migration


DEFAULT_WATCHLIST = ("600519", "300750", "601318", "600036", "000858", "002594")


def market_migrations(symbols: Collection[str]) -> tuple[Migration, ...]:
    def create_watchlist_and_history(db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE watchlist (
                position INTEGER PRIMARY KEY,
                symbol TEXT UNIQUE NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE history (
                symbol TEXT PRIMARY KEY,
                as_of TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        defaults = [(symbol,) for symbol in DEFAULT_WATCHLIST if symbol in symbols]
        db.executemany("INSERT INTO watchlist(symbol) VALUES (?)", defaults)

    return (
        Migration(create_watchlist_and_history, legacy_version=1),
        Migration(create_imported_instruments, legacy_version=2),
        Migration(add_closing_prices, legacy_version=3),
        Migration(create_monitor_quotes),
    )


def create_imported_instruments(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE imported (symbol TEXT PRIMARY KEY, metadata TEXT NOT NULL)")


def add_closing_prices(db: sqlite3.Connection) -> None:
    # Keep the catalog a small query even when years of imported bars are cached.
    db.execute("ALTER TABLE history ADD COLUMN close REAL")
    db.execute("ALTER TABLE history ADD COLUMN previous REAL")
    db.execute("""
        UPDATE history SET close = json_extract(payload, '$.bars[#-1].close'),
                           previous = json_extract(payload, '$.bars[#-2].close')
    """)


def create_monitor_quotes(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE monitor_quotes (
            symbol TEXT PRIMARY KEY, price REAL, previous_close REAL, quoted_at TEXT,
            checked_at TEXT NOT NULL, failed INTEGER NOT NULL
        )
    """)
