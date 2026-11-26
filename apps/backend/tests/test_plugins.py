import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core import Database, Migration, Plugin, create_application


def register_labels(app, database):
    @app.get("/api/labels")
    def labels():
        with database.connection() as connection:
            return [row[0] for row in connection.execute("SELECT name FROM labels ORDER BY name")]


def labels_table(db):
    db.execute("CREATE TABLE labels(name TEXT PRIMARY KEY)")


def test_add_and_temporarily_disable_plugin(tmp_path):
    plugin = Plugin("labels", register_labels, (Migration(labels_table),))
    database = Database(tmp_path)

    def start():
        return create_application((plugin,), data_dir=tmp_path, token="local")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, _ = list(pool.map(lambda _: start(), range(2)))
    with database.connection() as db:
        db.execute("INSERT INTO labels VALUES ('观察')")
    with TestClient(first) as client:
        assert client.get("/api/labels").status_code == 401
        assert client.get("/api/labels", headers={"Authorization": "Bearer local"}).json() == ["观察"]
    with TestClient(create_application((), data_dir=tmp_path, token="")) as core:
        assert core.get("/api/health").json() == {"status": "ok"}
        assert core.get("/api/labels").status_code == 404
        assert core.get("/api/instruments").status_code == 404
    with TestClient(start()) as reenabled:
        assert reenabled.get("/api/labels", headers={"Authorization": "Bearer local"}).json() == ["观察"]


def test_migrations_roll_back_and_can_retry(tmp_path):
    original = Plugin("labels", register_labels, (Migration(labels_table),))
    create_application((original,), data_dir=tmp_path)
    def set_color(db):
        db.execute("ALTER TABLE labels ADD COLUMN color TEXT")

    def broken(db):
        set_color(db)
        raise ValueError("interrupted")

    failed = Plugin("labels", register_labels, (*original.migrations, Migration(broken)))
    with pytest.raises(ValueError, match="interrupted"):
        create_application((failed,), data_dir=tmp_path)
    with Database(tmp_path).connection() as db:
        assert db.execute("SELECT version FROM plugin_schema WHERE name='labels'").fetchone() == (1,)
        assert [row[1] for row in db.execute("PRAGMA table_info(labels)")] == ["name"]

    fixed = Plugin("labels", register_labels, (*original.migrations, Migration(set_color)))
    create_application((fixed,), data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="labels"):
        create_application((original,), data_dir=tmp_path)
    with pytest.raises(ValueError, match="名称重复"):
        create_application((fixed, fixed), data_dir=tmp_path)


def test_existing_legacy_schema_is_adopted_once(tmp_path):
    with sqlite3.connect(tmp_path / "workspace.sqlite3") as db:
        labels_table(db)
        db.execute("INSERT INTO labels VALUES ('旧标签')")
        db.execute("PRAGMA user_version = 1")

    plugin = Plugin("labels", register_labels, (Migration(labels_table, legacy_version=1),))
    for _ in range(2):
        with TestClient(create_application((plugin,), data_dir=tmp_path, token="")) as app:
            assert app.get("/api/labels").json() == ["旧标签"]
