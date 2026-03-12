"""
CLOTE - routes/file_routes.py
File upload, list, and download endpoints.
All routes require authentication.
"""

import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse

from auth import get_current_user
from config import FILES_DIR, MAX_UPLOAD_SIZE_BYTES
from database import get_db

router = APIRouter(prefix="/files", tags=["Files"])


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _get_file_or_404(conn, file_id: int, user_id: int):
    """Fetch a file row — must exist and belong to this user."""
    row = conn.execute(
        "SELECT * FROM files WHERE id = ? AND owner_id = ?",
        (file_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return row


# ─────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    # Read content
    content = await file.read()

    # Size check
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB"
        )

    # Generate a unique name for storage (avoid collisions)
    ext = Path(file.filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = FILES_DIR / stored_name

    # Write to disk
    dest.write_bytes(content)

    # Detect mime type
    mime_type, _ = mimetypes.guess_type(file.filename)

    # Save to DB
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO files (owner_id, filename, stored_name, size_bytes, mime_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], file.filename, stored_name, len(content), mime_type)
        )
        file_id = cursor.lastrowid

        # Record version 1
        conn.execute(
            """
            INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by, note)
            VALUES (?, 1, ?, ?, ?, 'Initial upload')
            """,
            (file_id, stored_name, len(content), user["id"])
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "message": "File uploaded successfully",
        "file_id": file_id,
        "filename": file.filename,
        "size_bytes": len(content),
        "version": 1
    }


# ─────────────────────────────────────────────
# List Files
# ─────────────────────────────────────────────

@router.get("/")
def list_files(user=Depends(get_current_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, size_bytes, mime_type, current_version, created_at, updated_at
            FROM files
            WHERE owner_id = ?
            ORDER BY updated_at DESC
            """,
            (user["id"],)
        ).fetchall()
    finally:
        conn.close()

    return {
        "files": [dict(row) for row in rows],
        "total": len(rows)
    }


# ─────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────

@router.get("/{file_id}/download")
def download_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = _get_file_or_404(conn, file_id, user["id"])
    finally:
        conn.close()

    file_path = FILES_DIR / row["stored_name"]

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=row["filename"],
        media_type=row["mime_type"] or "application/octet-stream"
    )