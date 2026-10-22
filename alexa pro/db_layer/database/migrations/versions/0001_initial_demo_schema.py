"""Initial neutral demonstration schema.

Revision ID: 0001_initial_demo_schema
Revises: None
Create Date: 2026-10-22 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from database.base import UTCDateTime

revision: str = "0001_initial_demo_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "demo_catalog_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.CheckConstraint("length(trim(code)) > 0", name=op.f("ck_demo_catalog_nodes_code_not_blank")),
        sa.CheckConstraint("length(trim(label)) > 0", name=op.f("ck_demo_catalog_nodes_label_not_blank")),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')",
            name=op.f("ck_demo_catalog_nodes_status_valid_values"),
        ),
        sa.CheckConstraint("priority >= 0", name=op.f("ck_demo_catalog_nodes_priority_non_negative")),
        sa.CheckConstraint(
            "(is_deleted = 0 AND deleted_at IS NULL) OR (is_deleted = 1 AND deleted_at IS NOT NULL)",
            name=op.f("ck_demo_catalog_nodes_soft_delete_consistency"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_catalog_nodes")),
        sa.UniqueConstraint("code", name="uq_demo_catalog_nodes_code"),
    )
    op.create_index(
        "ix_demo_catalog_nodes_is_deleted",
        "demo_catalog_nodes",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        "ix_demo_catalog_nodes_status_priority",
        "demo_catalog_nodes",
        ["status", "priority"],
        unique=False,
    )

    op.create_table(
        "demo_catalog_attributes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("attr_key", sa.String(length=64), nullable=False),
        sa.Column("attr_value", sa.String(length=256), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(attr_key)) > 0",
            name=op.f("ck_demo_catalog_attributes_attr_key_not_blank"),
        ),
        sa.CheckConstraint(
            "metric_value >= 0.0",
            name=op.f("ck_demo_catalog_attributes_metric_value_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["demo_catalog_nodes.id"],
            name=op.f("fk_demo_catalog_attributes_node_id_demo_catalog_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_catalog_attributes")),
        sa.UniqueConstraint("node_id", "attr_key", name="uq_demo_catalog_attributes_node_key"),
    )
    op.create_index(
        "ix_demo_catalog_attributes_node_id",
        "demo_catalog_attributes",
        ["node_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_demo_catalog_attributes_node_id", table_name="demo_catalog_attributes")
    op.drop_table("demo_catalog_attributes")
    op.drop_index("ix_demo_catalog_nodes_status_priority", table_name="demo_catalog_nodes")
    op.drop_index("ix_demo_catalog_nodes_is_deleted", table_name="demo_catalog_nodes")
    op.drop_table("demo_catalog_nodes")