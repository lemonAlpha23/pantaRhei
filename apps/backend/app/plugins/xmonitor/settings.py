import hashlib
import os
import sqlite3
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

from ...core import Database
from . import protected_values
from .delivery import WebhookTarget, valid_webhook_url, webhook_target_from_env


class SettingsConflict(Exception):
    pass


def add_settings(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE x_connection_settings (
            name TEXT PRIMARY KEY, protected_value BLOB NOT NULL, destination TEXT
        )
    """)
    db.execute("""
        CREATE TABLE x_connection_revision (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            revision INTEGER NOT NULL CHECK(revision BETWEEN 0 AND 9007199254740991),
            vault_id TEXT NOT NULL
        )
    """)
    db.execute("INSERT INTO x_connection_revision VALUES (1, 0, ?)", (uuid4().hex,))


def _scope(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


@dataclass(frozen=True)
class _Setting:
    value: str | None = field(repr=False)
    source: str

    def status(self) -> dict:
        return {"configured": bool(self.value), "source": self.source}


def _active(db: sqlite3.Connection, name: str, fallback: str | None, scope: str | None = None) -> _Setting:
    row = db.execute("SELECT protected_value, destination FROM x_connection_settings WHERE name=?", (name,)).fetchone()
    if row and row[1] == scope:
        try:
            return _Setting(protected_values.unprotect(db, row[0]), "saved")
        except (OSError, UnicodeError):
            # A copied database may belong to another OS user. Allow the value to be replaced or reset.
            return _Setting(None, "saved")
    if row and not fallback:
        # An environment URL may have changed. Keep the orphan visible for removal.
        return _Setting(None, "saved")
    return _Setting(fallback, "environment" if fallback else "none")


def _x_token(db: sqlite3.Connection) -> _Setting:
    return _active(db, "xToken", os.environ.get("PANTARHEI_X_BEARER_TOKEN", "").strip() or None)


def _webhook(db: sqlite3.Connection) -> tuple[_Setting, _Setting]:
    env = webhook_target_from_env()
    url = _active(db, "webhookUrl", env.url if env else None)
    if not url.value:
        return url, _active(db, "webhookToken", None)
    token = _active(db, "webhookToken", env.token if env and url.value == env.url else None, _scope(url.value))
    return url, token


def _status(db: sqlite3.Connection) -> dict:
    url, token = _webhook(db)
    return {
        "revision": db.execute("SELECT revision FROM x_connection_revision WHERE singleton=1").fetchone()[0],
        "storageAvailable": protected_values.available(db),
        "xToken": _x_token(db).status(),
        "webhookUrl": {**url.status(), "host": urlsplit(url.value).hostname if url.value else None},
        "webhookToken": token.status(),
    }


def _save(db: sqlite3.Connection, key: str, value: str | None, scope: str | None = None) -> None:
    if value is None:
        db.execute("DELETE FROM x_connection_settings WHERE name=?", (key,))
    else:
        db.execute("""
            INSERT INTO x_connection_settings(name, protected_value, destination) VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET protected_value=excluded.protected_value, destination=excluded.destination
        """, (key, protected_values.protect(db, value), scope))


def _validate(changes: object) -> tuple[dict[str, str | None], int | None]:
    if not isinstance(changes, dict):
        raise ValueError("请选择要修改的连接配置")
    revision = changes.get("expectedRevision")
    if "expectedRevision" in changes and (type(revision) is not int or not 0 <= revision <= 2**53 - 1):
        raise ValueError("配置版本无效")
    fields = changes.keys() - {"expectedRevision"}
    if not fields or fields - {"xToken", "webhookUrl", "webhookToken"}:
        raise ValueError("请选择要修改的连接配置")
    cleaned = {}
    for key in fields:
        raw = changes[key]
        if raw is None:
            cleaned[key] = None
            continue
        if not isinstance(raw, str) or not 0 < len(raw) <= 8192:
            raise ValueError("配置值应为非空文本，最多 8192 个字符")
        value = raw.strip()
        if key == "webhookUrl":
            if not valid_webhook_url(value):
                raise ValueError("Webhook 需要有效的 HTTPS 地址")
        elif not value or not value.isascii() or any(not 33 <= ord(char) <= 126 for char in value):
            raise ValueError("令牌格式无效")
        cleaned[key] = value
    return cleaned, revision


class XSettings:
    def __init__(self, database: Database):
        self.database = database

    def status(self) -> dict:
        with self.database.connection() as db:
            db.execute("BEGIN")
            return _status(db)

    def x_token(self) -> str | None:
        with self.database.connection() as db:
            return _x_token(db).value

    def webhook_target(self, db: sqlite3.Connection | None = None) -> WebhookTarget | None:
        if db is None:
            with self.database.connection() as connection:
                connection.execute("BEGIN")
                return self.webhook_target(connection)
        url, token = _webhook(db)
        return WebhookTarget(url.value, token.value) if url.value else None

    def patch(self, changes: object) -> dict:
        cleaned, expected_revision = _validate(changes)
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            advanced = db.execute("""
                UPDATE x_connection_revision SET revision=revision+1
                WHERE singleton=1 AND (:expected IS NULL OR revision=:expected) AND revision < 9007199254740991
            """, {"expected": expected_revision})
            if not advanced.rowcount:
                raise SettingsConflict("连接配置已发生变更，请重新读取后再保存")
            if "xToken" in cleaned:
                _save(db, "xToken", cleaned["xToken"])
            if "webhookUrl" in cleaned:
                previous, _ = _webhook(db)
                _save(db, "webhookUrl", cleaned["webhookUrl"])
                current, _ = _webhook(db)
                if current.value != previous.value or (previous.source == "saved" and previous.value is None):
                    _save(db, "webhookToken", None)
            if "webhookToken" in cleaned:
                url, _ = _webhook(db)
                if cleaned["webhookToken"] and not url.value:
                    raise ValueError("请先配置 Webhook 接收地址")
                _save(db, "webhookToken", cleaned["webhookToken"], _scope(url.value) if url.value else None)
            return _status(db)
