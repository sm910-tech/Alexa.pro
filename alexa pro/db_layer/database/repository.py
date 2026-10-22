"""Constrained, type-safe generic repository for approved SQLAlchemy models."""

from __future__ import annotations

from typing import Any, Collection, Generic, Optional, Sequence, TypeVar

from sqlalchemy import Select, inspect, select
from sqlalchemy.orm import Session

from database.base import Base, SoftDeleteMixin, utc_now
from database.models import APPROVED_MODELS

ModelT = TypeVar("ModelT", bound=Base)

MAX_PAGE_LIMIT: int = 500
DEFAULT_PAGE_LIMIT: int = 50


class RepositoryUsageError(ValueError):
    """Raised when a caller supplies an unapproved model, invalid pagination, or invalid column."""


class RecordNotFoundError(LookupError):
    """Raised when a requested entity record does not exist."""


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository constrained to approved SQLAlchemy Declarative models.

    Security & Integrity Controls:
    - Rejects unmapped classes or models outside `allowed_models`.
    - Enforces strict bounds on `limit` (1..500) and `offset` (>= 0).
    - Validates filter and update field names against mapped model columns.
    - Restricts `soft_delete` to models that explicitly inherit `SoftDeleteMixin`.
    """

    def __init__(
        self,
        model_cls: type[ModelT],
        *,
        allowed_models: Collection[type[Base]] = APPROVED_MODELS,
    ) -> None:
        if not isinstance(model_cls, type) or not issubclass(model_cls, Base) or model_cls is Base:
            raise RepositoryUsageError(
                f"model_cls must be a concrete subclass of Base; got {model_cls!r}."
            )
        if model_cls not in allowed_models:
            raise RepositoryUsageError(
                f"Model {model_cls.__name__!r} is not in the approved repository model allowlist."
            )

        mapper = inspect(model_cls, raiseerr=False)
        if mapper is None:
            raise RepositoryUsageError(f"Model {model_cls.__name__!r} is not a mapped SQLAlchemy class.")

        self.model_cls: type[ModelT] = model_cls
        self._column_names: frozenset[str] = frozenset(col.key for col in mapper.column_attrs)
        self._supports_soft_delete: bool = issubclass(model_cls, SoftDeleteMixin)

    @property
    def supports_soft_delete(self) -> bool:
        """Return True if the bound model opted into SoftDeleteMixin."""
        return self._supports_soft_delete

    def _validate_column_names(self, fields: dict[str, Any], *, forbid_pk: bool = False) -> None:
        for key in fields:
            if not isinstance(key, str) or key not in self._column_names:
                raise RepositoryUsageError(
                    f"Invalid or unmapped column attribute {key!r} for model {self.model_cls.__name__}."
                )
            if forbid_pk and key in {"id", "created_at"}:
                raise RepositoryUsageError(
                    f"Column {key!r} is immutable and cannot be modified via update()."
                )

    def create(self, session: Session, **kwargs: Any) -> ModelT:
        """Instantiate, persist, and flush a new model record."""
        self._validate_column_names(kwargs, forbid_pk=False)
        instance = self.model_cls(**kwargs)
        session.add(instance)
        session.flush()
        return instance

    def get_by_id(
        self,
        session: Session,
        record_id: int,
        *,
        include_deleted: bool = False,
    ) -> Optional[ModelT]:
        """Retrieve a single record by primary key."""
        if not isinstance(record_id, int) or isinstance(record_id, bool):
            raise RepositoryUsageError("record_id must be an integer.")

        stmt: Select[tuple[ModelT]] = select(self.model_cls).where(
            getattr(self.model_cls, "id") == record_id
        )
        if self._supports_soft_delete and not include_deleted:
            stmt = stmt.where(getattr(self.model_cls, "is_deleted").is_(False))

        return session.scalars(stmt).first()

    def list_records(
        self,
        session: Session,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        include_deleted: bool = False,
        filters: Optional[dict[str, Any]] = None,
        order_by_column: str = "id",
        descending: bool = False,
    ) -> Sequence[ModelT]:
        """List records with mandatory pagination validation and safe equality filters."""
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > MAX_PAGE_LIMIT:
            raise RepositoryUsageError(
                f"limit must be an integer between 1 and {MAX_PAGE_LIMIT}; got {limit!r}."
            )
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise RepositoryUsageError(
                f"offset must be a non-negative integer; got {offset!r}."
            )
        if order_by_column not in self._column_names:
            raise RepositoryUsageError(
                f"Invalid order_by_column {order_by_column!r} for model {self.model_cls.__name__}."
            )

        stmt: Select[tuple[ModelT]] = select(self.model_cls)

        if self._supports_soft_delete and not include_deleted:
            stmt = stmt.where(getattr(self.model_cls, "is_deleted").is_(False))

        if filters:
            self._validate_column_names(filters, forbid_pk=False)
            for col_name, col_val in filters.items():
                col_attr = getattr(self.model_cls, col_name)
                if col_val is None:
                    stmt = stmt.where(col_attr.is_(None))
                else:
                    stmt = stmt.where(col_attr == col_val)

        order_attr = getattr(self.model_cls, order_by_column)
        stmt = stmt.order_by(order_attr.desc() if descending else order_attr.asc())
        stmt = stmt.limit(limit).offset(offset)

        return session.scalars(stmt).all()

    def update(
        self,
        session: Session,
        record_id: int,
        **updates: Any,
    ) -> ModelT:
        """Update allowed columns on an existing active record."""
        if not updates:
            raise RepositoryUsageError("At least one column update must be provided.")
        self._validate_column_names(updates, forbid_pk=True)

        instance = self.get_by_id(session, record_id, include_deleted=False)
        if instance is None:
            raise RecordNotFoundError(
                f"{self.model_cls.__name__} with id={record_id} was not found."
            )

        for key, value in updates.items():
            setattr(instance, key, value)

        if hasattr(instance, "updated_at"):
            setattr(instance, "updated_at", utc_now())

        session.flush()
        return instance

    def soft_delete(self, session: Session, record_id: int) -> ModelT:
        """Logically delete a record if the model explicitly inherits SoftDeleteMixin."""
        if not self._supports_soft_delete:
            raise RepositoryUsageError(
                f"Model {self.model_cls.__name__} does not opt into SoftDeleteMixin; use hard_delete()."
            )

        instance = self.get_by_id(session, record_id, include_deleted=False)
        if instance is None:
            raise RecordNotFoundError(
                f"Active {self.model_cls.__name__} with id={record_id} was not found."
            )

        now = utc_now()
        setattr(instance, "is_deleted", True)
        setattr(instance, "deleted_at", now)
        if hasattr(instance, "updated_at"):
            setattr(instance, "updated_at", now)

        session.flush()
        return instance

    def hard_delete(self, session: Session, record_id: int) -> None:
        """Permanently delete a record from the database."""
        instance = self.get_by_id(session, record_id, include_deleted=True)
        if instance is None:
            raise RecordNotFoundError(
                f"{self.model_cls.__name__} with id={record_id} was not found."
            )
        session.delete(instance)
        session.flush()