"""Tests for connection pragmas, secret redaction, exception chaining, permissions, and persistence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.config import DatabaseConfig, redact_database_url
from database.connection import DatabaseManager, DatabaseOperationError
from database.init_db import initialize_database
from database.models import DemoCatalogNode


def test_url_secret_redaction() -> None:
    raw = "postgresql+psycopg://db_admin:SuperSecretP@ss123@db.internal.example:5432/prod"
    cfg = DatabaseConfig(db_url=raw)
    assert "SuperSecretP@ss123" not in repr(cfg)
    assert "SuperSecretP@ss123" not in str(cfg)
    assert cfg.safe_url == "postgresql+psycopg://db_admin:***@db.internal.example:5432/prod"
    assert redact_database_url(raw) == cfg.safe_url


def test_sqlite_pragmas_enforced_and_configurable(tmp_path: Path) -> None:
    wal_db = tmp_path / "wal_enabled.sqlite3"
    cfg_wal = DatabaseConfig(
        db_url=f"sqlite:///{wal_db}",
        enable_wal=True,
        connect_timeout=3.5,
    )
    mgr_wal = initialize_database(cfg_wal)
    try:
        with mgr_wal.session_scope() as session:
            fk_status = session.execute(text("PRAGMA foreign_keys")).scalar_one()
            journal_mode = session.execute(text("PRAGMA journal_mode")).scalar_one()
            busy_timeout = session.execute(text("PRAGMA busy_timeout")).scalar_one()

            assert fk_status == 1
            assert str(journal_mode).lower() == "wal"
            assert busy_timeout == 3500
    finally:
        mgr_wal.dispose()

    no_wal_db = tmp_path / "wal_disabled.sqlite3"
    cfg_no_wal = DatabaseConfig(
        db_url=f"sqlite:///{no_wal_db}",
        enable_wal=False,
        connect_timeout=1.5,
    )
    mgr_no_wal = initialize_database(cfg_no_wal)
    try:
        with mgr_no_wal.session_scope() as session:
            fk_status = session.execute(text("PRAGMA foreign_keys")).scalar_one()
            journal_mode = session.execute(text("PRAGMA journal_mode")).scalar_one()
            busy_timeout = session.execute(text("PRAGMA busy_timeout")).scalar_one()

            assert fk_status == 1
            assert str(journal_mode).lower() != "wal"
            assert busy_timeout == 1500
    finally:
        mgr_no_wal.dispose()


def test_exception_chaining_and_diagnostics_preserved(db_manager: DatabaseManager) -> None:
    with db_manager.session_scope() as session:
        session.add(DemoCatalogNode(code="NODE_DUP", label="First Node", status="ACTIVE", priority=1))

    with pytest.raises(DatabaseOperationError) as exc_info:
        with db_manager.session_scope(operation="duplicate_node_insert") as session:
            session.add(DemoCatalogNode(code="NODE_DUP", label="Second Node", status="ACTIVE", priority=2))

    err = exc_info.value
    assert err.operation == "duplicate_node_insert"
    assert err.original_exception_type is not None
    assert "IntegrityError" in err.original_exception_type
    assert isinstance(err.__cause__, IntegrityError)


def test_refuses_to_overwrite_existing_database(temp_db_path: Path, db_manager: DatabaseManager) -> None:
    assert temp_db_path.exists()
    cfg = DatabaseConfig(db_url=f"sqlite:///{temp_db_path}")
    with pytest.raises(FileExistsError):
        initialize_database(cfg, allow_existing=False)


def test_posix_file_permissions_when_supported(temp_db_path: Path, db_manager: DatabaseManager) -> None:
    if os.name != "posix":
        pytest.skip("POSIX file permission bits are only enforced on POSIX systems.")
    file_mode = temp_db_path.stat().st_mode & 0o777
    dir_mode = temp_db_path.parent.stat().st_mode & 0o777
    assert file_mode == 0o600
    assert dir_mode == 0o700


def test_persistence_across_engine_close_and_reopen(temp_db_path: Path) -> None:
    cfg = DatabaseConfig(db_url=f"sqlite:///{temp_db_path}")
    first_manager = initialize_database(cfg, allow_existing=False)
    with first_manager.session_scope() as session:
        node = DemoCatalogNode(code="PERSIST_01", label="Persistent Item", status="ACTIVE", priority=5)
        session.add(node)
    first_manager.dispose()

    second_manager = DatabaseManager(cfg)
    try:
        with second_manager.session_scope() as session:
            loaded = session.query(DemoCatalogNode).filter_by(code="PERSIST_01").one()
            assert loaded.label == "Persistent Item"
            assert loaded.priority == 5
    finally:
        second_manager.dispose()