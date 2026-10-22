"""Pytest fixtures providing isolated, temporary per-test SQLite databases."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest

from database.config import DatabaseConfig
from database.connection import DatabaseManager
from database.init_db import initialize_database


@pytest.fixture()
def temp_db_path(tmp_path: Path) -> Path:
    """Return a unique temporary SQLite file path inside pytest's isolated tmp_path."""
    return tmp_path / "isolated_test.sqlite3"


@pytest.fixture()
def db_config(temp_db_path: Path) -> DatabaseConfig:
    """Provide a DatabaseConfig pointing strictly to the temporary SQLite file."""
    return DatabaseConfig(
        db_url=f"sqlite:///{temp_db_path}",
        echo_sql=False,
        enable_wal=True,
        connect_timeout=2.5,
        enforce_file_permissions=True,
    )


@pytest.fixture()
def db_manager(db_config: DatabaseConfig) -> Generator[DatabaseManager, None, None]:
    """Initialize a fresh temporary database before each test and dispose afterwards."""
    manager = initialize_database(db_config, allow_existing=False)
    try:
        yield manager
    finally:
        manager.dispose()