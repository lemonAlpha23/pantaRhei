import json
import sqlite3

from ...core import Database
from .types import History


class IncompleteHistory(Exception):
    pass


class MarketStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _watchlist(db: sqlite3.Connection) -> list[str]:
        return [row[0] for row in db.execute("SELECT symbol FROM watchlist ORDER BY position")]

    def watchlist(self) -> list[str]:
        with self.database.connection() as db:
            return self._watchlist(db)

    def set_membership(self, symbol: str, added: bool) -> list[str]:
        with self.database.connection() as db:
            if added:
                db.execute("INSERT OR IGNORE INTO watchlist(symbol) VALUES (?)", (symbol,))
            else:
                db.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
            return self._watchlist(db)

    def history(self, symbol: str) -> History | None:
        with self.database.connection() as db:
            row = db.execute("SELECT payload FROM history WHERE symbol = ?", (symbol,)).fetchone()
            return json.loads(row[0]) if row else None

    def closes(self) -> dict[str, tuple[float, float | None, str]]:
        with self.database.connection() as db:
            rows = db.execute("SELECT symbol, close, previous, as_of FROM history")
            return {symbol: (close, previous, day) for symbol, close, previous, day in rows}

    def imported(self) -> list[dict]:
        with self.database.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT metadata FROM imported ORDER BY symbol")]

    def imported_instrument(self, symbol: str) -> dict | None:
        with self.database.connection() as db:
            row = db.execute("SELECT metadata FROM imported WHERE symbol = ?", (symbol,)).fetchone()
            return json.loads(row[0]) if row else None

    def import_instrument(self, instrument: dict, history: History) -> None:
        symbol = instrument["symbol"]
        with self.database.connection() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO imported(symbol, metadata) VALUES (?, ?)",
                (symbol, json.dumps(instrument, ensure_ascii=False)),
            )
            if inserted.rowcount:
                self._write_history(db, symbol, history)

    def save_history(self, symbol: str, history: History, *, snapshot_count: int, window_size: int) -> bool:
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT json_array_length(payload, '$.bars') FROM history WHERE symbol = ?", (symbol,)
            ).fetchone()
            known_count = max(snapshot_count, row[0] if row else 0)
            # A full provider window may include today's unfinished bar, which we discard.
            if len(history["bars"]) < min(known_count, window_size - 1):
                raise IncompleteHistory
            return self._write_history(db, symbol, history)

    @staticmethod
    def _write_history(db: sqlite3.Connection, symbol: str, history: History) -> bool:
        bars = history["bars"]
        previous = bars[-2]["close"] if len(bars) > 1 else None
        payload = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
        cursor = db.execute(
            """
            INSERT INTO history(symbol, as_of, payload, close, previous) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET as_of = excluded.as_of, payload = excluded.payload,
                                              close = excluded.close, previous = excluded.previous
            WHERE excluded.as_of >= history.as_of
            """,
            (symbol, history["asOf"], payload, bars[-1]["close"], previous),
        )
        return cursor.rowcount == 1
