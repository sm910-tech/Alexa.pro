"""Tests for relational constraints, foreign-key cascades, UTC policy, and opt-in soft delete."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from database.base import SoftDeleteMixin
from database.connection import DatabaseManager, DatabaseOperationError
from database.models import DemoCatalogAttribute, DemoCatalogNode


def test_opt_in_soft_delete_separation() -> None:
    assert issubclass(DemoCatalogNode, SoftDeleteMixin)
    assert not issubclass(DemoCatalogAttribute, SoftDeleteMixin)
    assert hasattr(DemoCatalogNode, "is_deleted")
    assert not hasattr(DemoCatalogAttribute, "is_deleted")


def test_utc_timestamp_policy_and_naive_rejection(db_manager: DatabaseManager) -> None:
    with db_manager.session_scope() as session:
        node = DemoCatalogNode(code="UTC_01", label="UTC Check", status="DRAFT", priority=0)
        session.add(node)
        session.flush()
        node_id = node.id

    with db_manager.session_scope() as session:
        fetched = session.get(DemoCatalogNode, node_id)
        assert fetched is not None
        assert fetched.created_at.tzinfo == timezone.utc
        assert fetched.updated_at.tzinfo == timezone.utc

    # Naive datetime must be rejected by UTCDateTime
    with pytest.raises(DatabaseOperationError) as exc_info:
        with db_manager.session_scope() as session:
            bad_node = DemoCatalogNode(
                code="NAIVE_01",
                label="Naive Timestamp",
                status="DRAFT",
                priority=0,
                created_at=datetime(2026, 1, 1, 12, 0, 0),  # Naive datetime
            )
            session.add(bad_node)
    assert "Naive datetime" in str(exc_info.value)


def test_check_constraints_enforced(db_manager: DatabaseManager) -> None:
    # Negative priority violates priority_non_negative check constraint
    with pytest.raises(DatabaseOperationError):
        with db_manager.session_scope() as session:
            session.add(DemoCatalogNode(code="BAD_PRIO", label="Valid", status="ACTIVE", priority=-1))

    # Invalid status violates status_valid_values check constraint
    with pytest.raises(DatabaseOperationError):
        with db_manager.session_scope() as session:
            session.add(DemoCatalogNode(code="BAD_STAT", label="Valid", status="UNKNOWN", priority=1))

    # Blank code violates code_not_blank check constraint
    with pytest.raises(DatabaseOperationError):
        with db_manager.session_scope() as session:
            session.add(DemoCatalogNode(code="   ", label="Valid", status="ACTIVE", priority=1))


def test_foreign_key_enforcement_and_cascade_delete(db_manager: DatabaseManager) -> None:
    # Inserting attribute for non-existent parent node_id=9999 must fail
    with pytest.raises(DatabaseOperationError):
        with db_manager.session_scope() as session:
            session.add(
                DemoCatalogAttribute(
                    node_id=9999,
                    attr_key="color",
                    attr_value="blue",
                    metric_value=1.0,
                )
            )

    # Create parent and child, then delete parent and verify cascade
    with db_manager.session_scope() as session:
        parent = DemoCatalogNode(code="PARENT_1", label="Parent", status="ACTIVE", priority=1)
        session.add(parent)
        session.flush()
        parent_id = parent.id

        child = DemoCatalogAttribute(
            node_id=parent_id,
            attr_key="weight",
            attr_value="10kg",
            metric_value=10.0,
        )
        session.add(child)

    with db_manager.session_scope() as session:
        parent_obj = session.get(DemoCatalogNode, parent_id)
        session.delete(parent_obj)

    with db_manager.session_scope() as session:
        remaining_children = (
            session.query(DemoCatalogAttribute).filter_by(node_id=parent_id).count()
        )
        assert remaining_children == 0