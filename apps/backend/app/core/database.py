import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


class Database:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "workspace.sqlite3"

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=8)) as connection, connection:
            yield connection
