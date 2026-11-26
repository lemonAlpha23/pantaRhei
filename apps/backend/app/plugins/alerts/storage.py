import sqlite3
from datetime import datetime, timedelta
from typing import NamedTuple

from ...core import Database
from ..market.provider import CHINA_STANDARD_TIME
from ..market.types import MonitorQuote
from .types import AlertsPage, Direction, NewRule


MAX_QUOTE_AGE = timedelta(minutes=5)
HISTORY_LIMIT = 100


def create_tables(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, direction TEXT NOT NULL,
            target REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 1,
            armed_at TEXT NOT NULL, last_quote_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id INTEGER, symbol TEXT NOT NULL,
            direction TEXT NOT NULL, target REAL NOT NULL, price REAL NOT NULL, quoted_at TEXT NOT NULL
        )
    """)


def now() -> datetime:
    return datetime.now(CHINA_STANDARD_TIME).replace(microsecond=0)


class ArmedRule(NamedTuple):
    id: int
    symbol: str
    direction: Direction
    target: float
    generation: int


class AlertStore:
    def __init__(self, database: Database):
        self.database = database

    def page(self) -> AlertsPage:
        with self.database.connection() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            rules = db.execute("SELECT id, symbol, direction, target, enabled FROM alert_rules ORDER BY id DESC")
            items = [{**row, "enabled": bool(row["enabled"])} for row in rules]
            events = db.execute("""
                SELECT id, rule_id AS ruleId, symbol, direction, target, price, quoted_at AS quotedAt
                FROM alert_events ORDER BY id DESC LIMIT ?
            """, (HISTORY_LIMIT,))
            return AlertsPage(rules=items, events=[dict(row) for row in events])

    def add(self, rule: NewRule) -> None:
        with self.database.connection() as db:
            db.execute("""
                INSERT INTO alert_rules(symbol, direction, target, armed_at) VALUES (?, ?, ?, ?)
            """, (rule.symbol, rule.direction, rule.target, now().isoformat()))

    def set_enabled(self, rule_id: int, enabled: bool) -> bool:
        with self.database.connection() as db:
            cursor = db.execute("""
                UPDATE alert_rules SET generation = generation + (enabled != :enabled),
                    armed_at = CASE WHEN enabled = 0 AND :enabled = 1 THEN :stamp ELSE armed_at END,
                    enabled = :enabled WHERE id = :id
            """, {"enabled": enabled, "stamp": now().isoformat(), "id": rule_id})
            return cursor.rowcount == 1

    def delete(self, rule_id: int) -> bool:
        with self.database.connection() as db:
            removed = db.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            db.execute("UPDATE alert_events SET rule_id = NULL WHERE rule_id = ?", (rule_id,))
            return removed.rowcount == 1

    def armed(self) -> list[ArmedRule]:
        with self.database.connection() as db:
            return [ArmedRule(*row) for row in db.execute("""
                SELECT id, symbol, direction, target, generation FROM alert_rules WHERE enabled = 1 ORDER BY id
            """)]

    def evaluate(self, rules: tuple[ArmedRule, ...], quotes: dict[str, MonitorQuote]) -> int:
        checked = now()
        earliest = (checked - MAX_QUOTE_AGE).isoformat()
        latest = checked.isoformat()
        evaluated = 0
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for rule in rules:
                quote = quotes.get(rule.symbol)
                if not quote or not earliest <= quote["quotedAt"] <= latest:
                    continue
                stamp, price = quote["quotedAt"], quote["price"]
                reached = price >= rule.target if rule.direction == "above" else price <= rule.target
                # A rule may be paused, removed or rearmed while its network request is in flight.
                changed = db.execute("""
                    UPDATE alert_rules SET enabled = ?, last_quote_at = ?
                    WHERE id = ? AND generation = ? AND enabled = 1 AND armed_at <= ?
                        AND (last_quote_at IS NULL OR last_quote_at < ?)
                """, (not reached, stamp, rule.id, rule.generation, stamp, stamp))
                evaluated += changed.rowcount
                if reached and changed.rowcount:
                    db.execute("""
                        INSERT INTO alert_events(rule_id, symbol, direction, target, price, quoted_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (rule.id, rule.symbol, rule.direction, rule.target, price, stamp))
        return evaluated
