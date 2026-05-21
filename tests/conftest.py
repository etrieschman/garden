from pathlib import Path

import pytest

from garden.storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path: Path) -> SQLiteStorage:
    s = SQLiteStorage(db_path=tmp_path / "garden.sqlite")
    s.init_schema()
    return s
