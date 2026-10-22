# Standalone Database Layer (`db_layer`)

A modular, domain-agnostic persistence package implemented with Python, SQLAlchemy 2.x, SQLite, and Alembic.

## 1. Environment Configuration

All settings are read via `DatabaseConfig.from_env()` with the `DB_` prefix:

| Variable | Default | Description |
|---|---|---|
| `DB_URL` | `sqlite:///./data/database.sqlite3` | SQLAlchemy connection string. |
| `DB_ECHO` | `false` | Log generated SQL statements (`true`/`false`). |
| `DB_ENABLE_WAL` | `true` | Enable SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL`). |
| `DB_CONNECT_TIMEOUT` | `5.0` | Connection and busy timeout in seconds. |
| `DB_ENFORCE_PERMISSIONS` | `true` | Apply `0700` dir / `0600` file permissions on POSIX systems. |

## 2. Initialization & Migration Instructions

> **Approval & Safety Notice:** Run these commands only in an approved environment. Never run migrations against an unbacked-up database file.

### Step 1: Create an isolated virtual environment and install dependencies
```bash
cd db_layer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-db.txt