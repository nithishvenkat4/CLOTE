"""
CLOTE - database.py
SQLite connection, schema creation, and DB access helper.
"""

import sqlite3
from config import DATABASE_PATH


# ─────────────────────────────────────────────
# Connection Helper
# ─────────────────────────────────────────────

class _DBConn:
    """
    Thin wrapper around sqlite3.Connection that supports both patterns:
      conn = get_db(); conn.execute(...); conn.close()
      with get_db() as db: db.execute(...)
    sqlite3.Connection doesn't allow setting __enter__/__exit__ directly,
    so we wrap it instead.
    """
    def __init__(self, conn: sqlite3.Connection):
        object.__setattr__(self, '_conn', conn)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        object.__getattribute__(self, '_conn').close()

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_conn'), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_conn'), name, value)


def get_db() -> _DBConn:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _DBConn(conn)


# ─────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    DEFAULT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_FOLDERS_TABLE = """
CREATE TABLE IF NOT EXISTS folders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id     INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    project_id    INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    deleted_at    TEXT    DEFAULT NULL,
    deleted_by    INTEGER REFERENCES users(id),
    UNIQUE(owner_id, parent_id, name, project_id)
);
"""

CREATE_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    filename        TEXT    NOT NULL,
    stored_name     TEXT    NOT NULL UNIQUE,
    size_bytes      INTEGER NOT NULL,
    mime_type       TEXT,
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    deleted_at      TEXT    DEFAULT NULL,
    deleted_by      INTEGER REFERENCES users(id)
);
"""

CREATE_VERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id       INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    version_num   INTEGER NOT NULL,
    stored_name   TEXT    NOT NULL UNIQUE,
    size_bytes    INTEGER NOT NULL,
    uploaded_by   INTEGER NOT NULL REFERENCES users(id),
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_id, version_num)
);
"""

CREATE_PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_PROJECT_MEMBERS_TABLE = """
CREATE TABLE IF NOT EXISTS project_members (
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL DEFAULT 'viewer'
                        CHECK(role IN ('owner', 'editor', 'viewer')),
    joined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, user_id)
);
"""

CREATE_AUDIT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    action      TEXT    NOT NULL,
    target_type TEXT,
    target_id   INTEGER,
    target_name TEXT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    detail      TEXT,
    ip_address  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_SHARED_LINKS_TABLE = """
CREATE TABLE IF NOT EXISTS shared_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT    NOT NULL UNIQUE,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TEXT    DEFAULT NULL,
    max_uses    INTEGER DEFAULT NULL,
    use_count   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_OTPS_TABLE = """
CREATE TABLE IF NOT EXISTS otps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT    NOT NULL,
    otp_hash    TEXT    NOT NULL,
    purpose     TEXT    NOT NULL CHECK(purpose IN ('register', 'reset')),
    expires_at  TEXT    NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables if they don't exist.
    Also runs safe migrations for existing DBs.
    Safe to call on every startup.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Projects must exist before folders/files reference it
        cursor.executescript(
            CREATE_USERS_TABLE +
            CREATE_PROJECTS_TABLE +
            CREATE_PROJECT_MEMBERS_TABLE +
            CREATE_FOLDERS_TABLE +
            CREATE_FILES_TABLE +
            CREATE_VERSIONS_TABLE +
            CREATE_AUDIT_LOG_TABLE +
            CREATE_SHARED_LINKS_TABLE +
            CREATE_OTPS_TABLE
        )

        # ── Safe migrations for existing databases ──

        # project_id on folders + files
        _add_column_if_missing(cursor, "folders", "project_id",
                               "INTEGER REFERENCES projects(id) ON DELETE CASCADE")
        _add_column_if_missing(cursor, "files", "project_id",
                               "INTEGER REFERENCES projects(id) ON DELETE CASCADE")

        # Trash columns
        _add_column_if_missing(cursor, "files",   "deleted_at", "TEXT DEFAULT NULL")
        _add_column_if_missing(cursor, "files",   "deleted_by", "INTEGER REFERENCES users(id)")
        _add_column_if_missing(cursor, "folders", "deleted_at", "TEXT DEFAULT NULL")
        _add_column_if_missing(cursor, "folders", "deleted_by", "INTEGER REFERENCES users(id)")

        # Email on users (needed for OTP)
        _add_column_if_missing(cursor, "users", "email", "TEXT DEFAULT NULL")
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        except Exception:
            pass

        conn.commit()
        print("[CLOTE] Database initialized.")
    finally:
        conn.close()


def _add_column_if_missing(cursor, table: str, column: str, col_def: str) -> None:
    """Add a column to an existing table only if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = [row["name"] for row in cursor.fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        print(f"[CLOTE] Migration: added '{column}' to '{table}'")
