"""Environment-driven configuration and credential redaction utilities."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

# Matches credentials in RFC-1738 style database URLs: scheme://user:pass@host/db
_URL_CREDENTIAL_PATTERN = re.compile(r"(?P<prefix>[a-zA-Z0-9_+.-]+://[^:/@\s]+:)(?P<secret>[^@\s]+)(?P<suffix>@)")


def redact_database_url(raw_url: str) -> str:
    """Redact password components from a database URL string safely."""
    if not raw_url:
        return "<empty_url>"
    try:
        parsed = urlsplit(raw_url)
        if parsed.password is not None:
            username = parsed.username or ""
            hostname = parsed.hostname or ""
            port_part = f":{parsed.port}" if parsed.port else ""
            netloc = f"{username}:***@{hostname}{port_part}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        pass
    return _URL_CREDENTIAL_PATTERN.sub(r"\g<prefix>***\g<suffix>", raw_url)


def redact_text_secrets(text: str, raw_url: Optional[str] = None) -> str:
    """Remove any embedded database credentials from diagnostic error messages."""
    if not text:
        return text
    sanitized = _URL_CREDENTIAL_PATTERN.sub(r"\g<prefix>***\g<suffix>", text)
    if raw_url:
        try:
            parsed = urlsplit(raw_url)
            if parsed.password:
                sanitized = sanitized.replace(parsed.password, "***")
        except Exception:
            pass
    return sanitized


def _parse_bool(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    normalized = val.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuration container for the database layer.

    Note on WAL & File Permissions:
    `enable_wal` and `enforce_file_permissions` are operational and local filesystem
    hygiene settings for SQLite. They are platform-dependent and are NOT substitutes
    for encryption at rest or database-level authentication/access control.
    """

    db_url: str = field(default="sqlite:///./data/database.sqlite3", repr=False)
    echo_sql: bool = False
    enable_wal: bool = True
    connect_timeout: float = 5.0
    enforce_file_permissions: bool = True

    def __post_init__(self) -> None:
        if not self.db_url or not isinstance(self.db_url, str):
            raise ValueError("db_url must be a non-empty string.")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be greater than 0.")

    @classmethod
    def from_env(cls, prefix: str = "DB_") -> DatabaseConfig:
        """Load configuration from environment variables with safe defaults."""
        url = os.environ.get(f"{prefix}URL", "sqlite:///./data/database.sqlite3")
        echo = _parse_bool(os.environ.get(f"{prefix}ECHO"), default=False)
        wal = _parse_bool(os.environ.get(f"{prefix}ENABLE_WAL"), default=True)
        enforce_perms = _parse_bool(os.environ.get(f"{prefix}ENFORCE_PERMISSIONS"), default=True)

        raw_timeout = os.environ.get(f"{prefix}CONNECT_TIMEOUT", "5.0")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError(f"Invalid float value for {prefix}CONNECT_TIMEOUT: {raw_timeout!r}") from exc

        return cls(
            db_url=url,
            echo_sql=echo,
            enable_wal=wal,
            connect_timeout=timeout,
            enforce_file_permissions=enforce_perms,
        )

    @property
    def is_sqlite(self) -> bool:
        """Return True if the configured backend uses the SQLite dialect."""
        return self.db_url.startswith("sqlite:")

    @property
    def is_in_memory(self) -> bool:
        """Return True if the SQLite database is transient in-memory."""
        return self.is_sqlite and (":memory:" in self.db_url or "mode=memory" in self.db_url)

    @property
    def sqlite_file_path(self) -> Optional[Path]:
        """Resolve local filesystem path if backed by a file-based SQLite URL."""
        if not self.is_sqlite or self.is_in_memory:
            return None
        prefix = "sqlite:///"
        if self.db_url.startswith(prefix):
            raw_path = self.db_url[len(prefix) :].split("?", 1)[0]
            if raw_path:
                return Path(raw_path).resolve()
        return None

    @property
    def safe_url(self) -> str:
        """Return the database URL with any password redacted."""
        return redact_database_url(self.db_url)

    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(db_url={self.safe_url!r}, echo_sql={self.echo_sql}, "
            f"enable_wal={self.enable_wal}, connect_timeout={self.connect_timeout}, "
            f"enforce_file_permissions={self.enforce_file_permissions})"
        )

    def __str__(self) -> str:
        return self.__repr__()