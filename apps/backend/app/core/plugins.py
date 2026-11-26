import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fastapi import FastAPI

from .database import Database


@dataclass(frozen=True)
class Migration:
    apply: Callable[[sqlite3.Connection], None]
    # Releases through 0.2.0 shared a single SQLite user_version across all features.
    legacy_version: int | None = None


@dataclass(frozen=True)
class Plugin:
    name: str
    register: Callable[[FastAPI, Database], None]
    migrations: tuple[Migration, ...] = ()


def install_plugins(app: FastAPI, database: Database, plugins: Sequence[Plugin]) -> None:
    names = [plugin.name for plugin in plugins]
    if len(set(names)) != len(names):
        raise ValueError("插件名称重复")

    with database.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS plugin_schema (name TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        installed = dict(db.execute("SELECT name, version FROM plugin_schema"))
        legacy = db.execute("PRAGMA user_version").fetchone()[0]
        old_steps = set()
        for plugin in plugins:
            version = installed.get(plugin.name, 0)
            if version > len(plugin.migrations):
                raise RuntimeError(f"{plugin.name} 的数据库版本高于当前插件版本")
            for migration in plugin.migrations[version:]:
                if migration.legacy_version is None or migration.legacy_version > legacy:
                    migration.apply(db)
            if installed.get(plugin.name) != len(plugin.migrations):
                db.execute("""
                    INSERT INTO plugin_schema(name, version) VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET version = excluded.version
                """, (plugin.name, len(plugin.migrations)))
            old_steps.update(m.legacy_version for m in plugin.migrations if m.legacy_version is not None)

        # Keep databases containing the full original schema readable by older releases.
        compatible = legacy
        while compatible + 1 in old_steps:
            compatible += 1
        if compatible > legacy:
            db.execute(f"PRAGMA user_version = {compatible}")

    for plugin in plugins:
        plugin.register(app, database)
