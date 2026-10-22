"""Tests for constrained repository CRUD, pagination validation, rollback, and Alembic migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect

from database.base import Base, PrimaryKeyMixin
from database.config import DatabaseConfig
from database.connection import DatabaseManager
from database.models import DemoCatalogAttribute, DemoCatalogNode
from database.repository import (
    MAX_PAGE_LIMIT,
    BaseRepository,
    RecordNotFoundError,
    RepositoryUsageError,
)


class UnapprovedModel(PrimaryKeyMixin, Base):
    """Model intentionally omitted from APPROVED_MODELS to test allowlist enforcement."""

    __tablename__ = "unapproved_test_table"


def test_repository_rejects_unapproved_models() -> None:
    with pytest.raises(RepositoryUsageError, match="not in the approved repository model allowlist"):
        BaseRepository(UnapprovedModel)


def test_repository_pagination_and_column_validation(db_manager: DatabaseManager) -> None:
    repo = BaseRepository(DemoCatalogNode)

    with db_manager.session_scope() as session:
        with pytest.raises(RepositoryUsageError, match="limit must be an integer"):
            repo.list_records(session, limit=0)

        with pytest.raises(RepositoryUsageError, match="limit must be an integer"):
            repo.list_records(session, limit=MAX_PAGE_LIMIT + 1)

        with pytest.raises(RepositoryUsageError, match="offset must be a non-negative integer"):
            repo.list_records(session, offset=-1)

        with pytest.raises(RepositoryUsageError, match="Invalid or unmapped column"):
            repo.list_records(session, filters={"non_existent_column": "val"})


def test_repository_crud_and_opt_in_soft_delete(db_manager: DatabaseManager) -> None:
    node_repo = BaseRepository(DemoCatalogNode)
    attr_repo = BaseRepository(DemoCatalogAttribute)

    with db_manager.session_scope() as session:
        node = node_repo.create(
            session,
            code="REPO_NODE_1",
            label="Initial Label",
            status="DRAFT",
            priority=2,
        )
        node_id = node.id
        attr = attr_repo.create(
            session,
            node_id=node_id,
            attr_key="tier",
            attr_value="standard",
            metric_value=5.5,
        )
        attr_id = attr.id

    # Update node
    with db_manager.session_scope() as session:
        updated = node_repo.update(session, node_id, label="Updated Label", status="ACTIVE")
        assert updated.label == "Updated Label"
        assert updated.status == "ACTIVE"

    # Soft delete on DemoCatalogAttribute (which did not opt in) must fail
    with db_manager.session_scope() as session:
        with pytest.raises(RepositoryUsageError, match="does not opt into SoftDeleteMixin"):
            attr_repo.soft_delete(session, attr_id)

    # Soft delete on DemoCatalogNode succeeds and hides record from default queries
    with db_manager.session_scope() as session:
        deleted_node = node_repo.soft_delete(session, node_id)
        assert deleted_node.is_deleted is True
        assert deleted_node.deleted_at is not None

    with db_manager.session_scope() as session:
        assert node_repo.get_by_id(session, node_id, include_deleted=False) is None
        assert node_repo.get_by_id(session, node_id, include_deleted=True) is not None
        assert len(node_repo.list_records(session, include_deleted=False)) == 0
        assert len(node_repo.list_records(session, include_deleted=True)) == 1

    # Hard delete removes record permanently
    with db_manager.session_scope() as session:
        node_repo.hard_delete(session, node_id)

    with db_manager.session_scope() as session:
        assert node_repo.get_by_id(session, node_id, include_deleted=True) is None


def test_atomic_transaction_rollback_on_failure(db_manager: DatabaseManager) -> None:
    node_repo = BaseRepository(DemoCatalogNode)

    with pytest.raises(RuntimeError, match="Simulated mid-transaction failure"):
        with db_manager.session_scope() as session:
            node_repo.create(
                session,
                code="ROLLBACK_NODE",
                label="Should Not Persist",
                status="ACTIVE",
                priority=1,
            )
            raise RuntimeError("Simulated mid-transaction failure")

    with db_manager.session_scope() as session:
        records = node_repo.list_records(session, filters={"code": "ROLLBACK_NODE"})
        assert len(records) == 0


def test_alembic_migrations_upgrade_and_downgrade(tmp_path: Path) -> None:
    migration_db = tmp_path / "alembic_test.sqlite3"
    db_url = f"sqlite:///{migration_db}"

    alembic_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(alembic_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(alembic_root / "database" / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    mgr = DatabaseManager(DatabaseConfig(db_url=db_url))
    try:
        inspector = inspect(mgr.engine)
        tables = set(inspector.get_table_names())
        assert "demo_catalog_nodes" in tables
        assert "demo_catalog_attributes" in tables

        # Downgrade to base
        command.downgrade(alembic_cfg, "base")
        inspector_after = inspect(mgr.engine)
        tables_after = set(inspector_after.get_table_names())
        assert "demo_catalog_nodes" not in tables_after
        assert "demo_catalog_attributes" not in tables_after
    finally:
        mgr.dispose()