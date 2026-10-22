"""Engine management, SQLite pragma listeners, and atomic session scope."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from database.config import DatabaseConfig, redact_text_secrets


class DatabaseOperationError(RuntimeError):
    """Sanitized database exception that preserves diagnostic metadata and chaining.

    Secrets and raw parameter payloads are stripped from string output, while
    `original_exception_type`, `dialect_code`, and `__cause__` remain accessible
    for structured debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str = "database_operation",
        original_exception_type: Optional[str] = None,
        dialect_code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.original_exception_type = original_exception_type
        self.dialect_code = dialect_code

    @classmethod
    def from_sqlalchemy_error(
        cls,
        exc: SQLAlchemyError,
        *,
        operation: str,
        raw_url: Optional[str] = None,
    ) -> DatabaseOperationError:
        orig = getattr(exc, "orig", None)
        orig_type_name = type(exc).__name__
        dialect_code: Optional[str] = getattr(exc, "code", None)

        # Extract database driver error message without dumping full bound parameters
        if orig is not None:
            raw_detail = str(orig)
            orig_type_name = f"{type(exc).__name__}({type(orig).__name__})"
        else:
            raw_detail = str(exc).split("[SQL:", 1)[0].strip()

        safe_detail = redact_text_secrets(raw_detail, raw_url=raw_url)
        formatted_msg = (
            f"Database error during {operation} [{orig_type_name}]: {safe_detail}"
        )
        return cls(
            formatted_msg,
            operation=operation,
            original_exception_type=orig_type_name,
            dialect_code=dialect_code,
        )


class DatabaseManager:
    """Manages SQLAlchemy Engine and Session lifecycle for a given DatabaseConfig."""

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        self.config: DatabaseConfig = config or DatabaseConfig.from_env()
        self._engine: Engine = self._build_engine()
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )

    def _build_engine(self) -> Engine:
        connect_args: dict[str, Any] = {}
        if self.config.is_sqlite:
            connect_args["timeout"] = self.config.connect_timeout

        engine = create_engine(
            self.config.db_url,
            echo=self.config.echo_sql,
            connect_args=connect_args,
            future=True,
        )

        if self.config.is_sqlite:
            self._register_sqlite_pragmas(engine)

        return engine

    def _register_sqlite_pragmas(self, engine: Engine) -> None:
        """Attach connection listener to enforce foreign keys and configurable pragmas."""
        enable_wal = self.config.enable_wal and not self.config.is_in_memory
        busy_timeout_ms = int(self.config.connect_timeout * 1000)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                # Unconditionally enforce foreign-key constraints in SQLite
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
                if enable_wal:
                    cursor.execute("PRAGMA journal_mode = WAL")
                    cursor.execute("PRAGMA synchronous = NORMAL")
            finally:
                cursor.close()

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session_scope(self, operation: str = "transaction") -> Generator[Session, None, None]:
        """Provide an atomic transactional scope around a series of operations.

        Commits automatically if no exception occurs; rolls back immediately on
        any exception; sanitizes SQLAlchemyError messages while preserving
        exception chaining (`raise ... from exc`); always closes the session.
        """
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except DatabaseOperationError:
            session.rollback()
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabaseOperationError.from_sqlalchemy_error(
                exc,
                operation=operation,
                raw_url=self.config.db_url,
            ) from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Close all checked-in connections in the engine pool."""
        self._engine.dispose()