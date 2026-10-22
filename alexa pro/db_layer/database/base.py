"""Declarative base, deterministic constraint naming, and reusable column mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, MetaData
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import TypeDecorator

# Deterministic naming conventions required for reliable Alembic migrations
# especially when running batch-mode table alterations in SQLite.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Authoritative UTC timestamp generator."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC DateTime type across SQLite and client-server dialects.

    Authoritative Policy:
    - Python-side `utc_now()` is the single authoritative timestamp source.
    - Naive datetimes passed on bind are rejected to prevent local-time ambiguity.
    - Values read back from SQLite (which strips tzinfo) are normalized to `timezone.utc`.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: Optional[datetime], dialect: Dialect) -> Optional[datetime]:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected datetime instance, got {type(value).__name__}")
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Naive datetime values are forbidden; provide a timezone-aware UTC datetime.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class for all database models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PrimaryKeyMixin:
    """Reusable integer primary key mixin."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    """Reusable UTC creation and update timestamp mixin.

    Uses authoritative Python-side UTC defaults (`utc_now`) rather than
    conflicting dialect server defaults.
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class SoftDeleteMixin:
    """Opt-in mixin for logical deletion where historical retention is required.

    Should only be inherited by models that explicitly require logical deletion.
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime(),
        nullable=True,
        default=None,
    )

    @declared_attr
    def __table_args__(cls) -> tuple[Any, ...]:
        table_name = getattr(cls, "__tablename__", cls.__name__.lower())
        return (Index(f"ix_{table_name}_is_deleted", "is_deleted"),)