"""Standalone, domain-agnostic database layer package."""

from database.base import Base, PrimaryKeyMixin, SoftDeleteMixin, TimestampMixin, UTCDateTime
from database.config import DatabaseConfig
from database.connection import DatabaseManager, DatabaseOperationError
from database.init_db import apply_sqlite_file_permissions, initialize_database
from database.models import APPROVED_MODELS, DemoCatalogAttribute, DemoCatalogNode
from database.repository import (
    MAX_PAGE_LIMIT,
    BaseRepository,
    RecordNotFoundError,
    RepositoryUsageError,
)

__all__ = [
    "APPROVED_MODELS",
    "Base",
    "BaseRepository",
    "DatabaseConfig",
    "DatabaseManager",
    "DatabaseOperationError",
    "DemoCatalogAttribute",
    "DemoCatalogNode",
    "MAX_PAGE_LIMIT",
    "PrimaryKeyMixin",
    "RecordNotFoundError",
    "RepositoryUsageError",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UTCDateTime",
    "apply_sqlite_file_permissions",
    "initialize_database",
]