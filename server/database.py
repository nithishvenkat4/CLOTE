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
    """
    Open and return a SQLite connection.
    - Row factory set so results behave like dicts.
    - Foreign keys enforced.
    Call this at the start of each route, close when done.
    """
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
    name          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(owner_id, parent_id, name)
);
"""

CREATE_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
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


# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables if they don't exist.
    Safe to call on every startup.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.executescript(
            CREATE_USERS_TABLE +
            CREATE_FOLDERS_TABLE +
            CREATE_FILES_TABLE +
            CREATE_VERSIONS_TABLE
        )
        conn.commit()
        print("[CLOTE] Database initialized.")
    finally:
        conn.close()
