"""
CLOTE - config.py
Central configuration for the server.
All paths, secrets, and settings live here.
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────
# Base Paths
# ─────────────────────────────────────────────

# Root of the server project (where this file lives)
BASE_DIR = Path(__file__).resolve().parent

# Where uploaded files and their versions are stored
STORAGE_DIR = BASE_DIR / "storage"

# SQLite database file
DATABASE_PATH = BASE_DIR / "clote.db"

# ─────────────────────────────────────────────
# Storage Structure
# ─────────────────────────────────────────────
# storage/
#   files/        ← current (latest) version of each file
#   versions/     ← all historical versions

FILES_DIR    = STORAGE_DIR / "files"
VERSIONS_DIR = STORAGE_DIR / "versions"

# ─────────────────────────────────────────────
# JWT Auth Settings
# ─────────────────────────────────────────────

# IMPORTANT: Change this to a strong random secret before deploying.
# Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY = os.getenv("CLOTE_JWT_SECRET", "change-this-secret-before-production")
JWT_ALGORITHM  = "HS256"

# Token validity (in minutes)
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours

# ─────────────────────────────────────────────
# Upload Limits
# ─────────────────────────────────────────────

MAX_UPLOAD_SIZE_MB = 100  # Maximum file size allowed (in MB)
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ─────────────────────────────────────────────
# App Meta
# ─────────────────────────────────────────────

APP_NAME    = "CLOTE"
APP_VERSION = "0.1.0"

# ─────────────────────────────────────────────
# Startup: ensure storage folders exist
# ─────────────────────────────────────────────

def init_storage() -> None:
    """Create storage directories if they don't exist."""
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)