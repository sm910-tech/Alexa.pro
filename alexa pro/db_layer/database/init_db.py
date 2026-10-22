"""Controlled database initialization and platform-aware file permission utilities."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from database.base import Base
from database.config import DatabaseConfig
from database.connection import DatabaseManager
import database.models  # noqa: F401 - Ensure models are registered on Base.metadata

logger = logging.getLogger(__name__)


def apply_sqlite_file_permissions(db_path: Path) -> bool:
    """Apply restrictive POSIX permissions (0700 dir, 0600 files) if supported by the OS.

    Limitation:
    POSIX mode bits (`chmod 0600`) only restrict local multi-user access on POSIX
    operating systems (Linux, macOS). On Windows (`os.name != 'posix'`), this function
    logs a warning and returns False. File permissions do NOT provide encryption at rest.
    """
    if os.name != "posix":
        logger.warning(
            "POSIX file permission hardening is not supported on OS %r; "
            "configure filesystem ACLs externally.",
            os.name,
        )
        return False

    parent_dir = db_path.parent
    if parent_dir.exists():
        os.chmod(parent_dir, 0o700)

    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            os.chmod(candidate, 0o600)

    return True


def initialize_database(
    config: Optional[DatabaseConfig] = None,
    *,
    allow_existing: bool = False,
) -> DatabaseManager:
    """Initialize database schema safely without overwriting pre-existing database files.

    Raises FileExistsError if `allow_existing=False` and the target SQLite file
    already exists and is non-empty.
    """
    cfg = config or DatabaseConfig.from_env()
    sqlite_path = cfg.sqlite_file_path

    if sqlite_path is not None:
        if sqlite_path.exists() and sqlite_path.stat().st_size > 0 and not allow_existing:
            raise FileExistsError(
                f"Refusing to initialize over existing non-empty database file at {sqlite_path}. "
                "Pass allow_existing=True or run Alembic migrations explicitly."
            )
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        if cfg.enforce_file_permissions and os.name == "posix":
            os.chmod(sqlite_path.parent, 0o700)

    manager = DatabaseManager(cfg)
    Base.metadata.create_all(bind=manager.engine)

    # Touch connection to ensure WAL/file creation before applying permissions
    with manager.session_scope(operation="init_db_verify"):
        pass

    if sqlite_path is not None and cfg.enforce_file_permissions:
        apply_sqlite_file_permissions(sqlite_path)

    return manager