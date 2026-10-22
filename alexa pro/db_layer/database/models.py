"""Neutral demonstration entities illustrating relational patterns and constraints.

IMPORTANT:
The tables defined in this module (`demo_catalog_nodes` and `demo_catalog_attributes`)
are strictly neutral demonstration entities used to verify primary/foreign keys,
check constraints, unique constraints, indexes, UTC timestamps, and opt-in soft deletion.
They do not represent domain-specific application features.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, PrimaryKeyMixin, SoftDeleteMixin, TimestampMixin


class DemoCatalogNode(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Neutral demonstration parent entity (includes opt-in SoftDeleteMixin)."""

    __tablename__ = "demo_catalog_nodes"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    attributes: Mapped[list[DemoCatalogAttribute]] = relationship(
        "DemoCatalogAttribute",
        back_populates="node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_demo_catalog_nodes_code"),
        CheckConstraint("length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="label_not_blank"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')",
            name="status_valid_values",
        ),
        CheckConstraint("priority >= 0", name="priority_non_negative"),
        CheckConstraint(
            "(is_deleted = 0 AND deleted_at IS NULL) OR (is_deleted = 1 AND deleted_at IS NOT NULL)",
            name="soft_delete_consistency",
        ),
        Index("ix_demo_catalog_nodes_status_priority", "status", "priority"),
        Index("ix_demo_catalog_nodes_is_deleted", "is_deleted"),
    )


class DemoCatalogAttribute(PrimaryKeyMixin, TimestampMixin, Base):
    """Neutral demonstration child entity (does NOT use SoftDeleteMixin).

    Demonstrates foreign-key enforcement with ON DELETE CASCADE and composite uniqueness.
    """

    __tablename__ = "demo_catalog_attributes"

    node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("demo_catalog_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    attr_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attr_value: Mapped[str] = mapped_column(String(256), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    node: Mapped[DemoCatalogNode] = relationship(
        "DemoCatalogNode",
        back_populates="attributes",
    )

    __table_args__ = (
        UniqueConstraint("node_id", "attr_key", name="uq_demo_catalog_attributes_node_key"),
        CheckConstraint("length(trim(attr_key)) > 0", name="attr_key_not_blank"),
        CheckConstraint("metric_value >= 0.0", name="metric_value_non_negative"),
        Index("ix_demo_catalog_attributes_node_id", "node_id"),
    )


# Explicit registry of approved SQLAlchemy model classes allowed in BaseRepository
APPROVED_MODELS: frozenset[type[Base]] = frozenset(
    {
        DemoCatalogNode,
        DemoCatalogAttribute,
    }
)