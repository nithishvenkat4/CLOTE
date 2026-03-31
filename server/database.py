"""
CLOTE - database.py
SQLite connection, schema creation, and DB access helper.
"""

import sqlite3
from config import DATABASE_PATH


# ─────────────────────────────────────────────
# Connection Helper
# ─────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
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
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
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
            CREATE_VERSIONS_TABLE
        )

        # ── Safe migrations for existing databases ──
        # Add project_id to folders if missing
        _add_column_if_missing(cursor, "folders", "project_id",
                               "INTEGER REFERENCES projects(id) ON DELETE CASCADE")

        # Add project_id to files if missing
        _add_column_if_missing(cursor, "files", "project_id",
                               "INTEGER REFERENCES projects(id) ON DELETE CASCADE")

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
