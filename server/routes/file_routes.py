"""
CLOTE - file_routes.py
Phase 1 + Phase 2 file management routes.

Schema reference:
  files    : id, owner_id, filename, stored_name, size_bytes, mime_type,
             current_version, created_at, updated_at
  versions : id, file_id, version_num, stored_name, size_bytes,
             uploaded_by, note, created_at
"""

import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db

router = APIRouter(prefix="/files", tags=["files"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _assert_owns(file_row, user_id: int):
    if file_row is None:
        raise HTTPException(status_code=404, detail="File not found")
    if file_row["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _new_stored_name() -> str:
    return str(uuid.uuid4())


def _resolve_version_path(stored_name: str, version_num: int, current_version: int) -> str:
    """Return the disk path for a given version."""
    if version_num == current_version:
        return os.path.join(FILES_DIR, stored_name)
    path = os.path.join(VERSIONS_DIR, stored_name)
    if not os.path.exists(path):
        path = os.path.join(FILES_DIR, stored_name)
    return path


# ── Phase 1 ───────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """Upload a brand-new file (version 1)."""
    content = await file.read()
    size_bytes = len(content)
    stored_name = _new_stored_name()
    dest_path = os.path.join(FILES_DIR, stored_name)

    with open(dest_path, "wb") as f:
        f.write(content)

    db = get_db()
    try:
        cursor = db.execute(
            """
            INSERT INTO files (owner_id, filename, stored_name, size_bytes, mime_type, current_version)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (current_user["id"], file.filename, stored_name, size_bytes, file.content_type),
        )
        file_id = cursor.lastrowid

        db.execute(
            """
            INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by)
            VALUES (?, 1, ?, ?, ?)
            """,
            (file_id, stored_name, size_bytes, current_user["id"]),
        )
        db.commit()
    except Exception:
        db.rollback()
        os.remove(dest_path)
        raise
    finally:
        db.close()

    return {
        "file_id": file_id,
        "filename": file.filename,
        "stored_name": stored_name,
        "size_bytes": size_bytes,
        "version": 1,
    }


@router.get("/")
def list_files(current_user=Depends(get_current_user)):
    """List all files owned by the current user."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT id, filename, size_bytes, mime_type, current_version, created_at, updated_at
            FROM files
            WHERE owner_id = ?
            ORDER BY updated_at DESC
            """,
            (current_user["id"],),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/{file_id}/download")
def download_file(file_id: int, current_user=Depends(get_current_user)):
    """Download the latest version of a file."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(row, current_user["id"])

        path = os.path.join(FILES_DIR, row["stored_name"])
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File data missing on disk")

        return FileResponse(path, filename=row["filename"], media_type=row["mime_type"])
    finally:
        db.close()


# ── Phase 2 ───────────────────────────────────────────────────────────────────

@router.post("/{file_id}/upload")
async def upload_new_version(
    file_id: int,
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
):
    """Upload a new version of an existing file."""
    db = get_db()
    new_path = None
    try:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(row, current_user["id"])

        new_version = row["current_version"] + 1
        content = await file.read()
        size_bytes = len(content)
        new_stored_name = _new_stored_name()
        new_path = os.path.join(FILES_DIR, new_stored_name)

        # Archive current live file into VERSIONS_DIR
        old_stored_name = row["stored_name"]
        old_live_path = os.path.join(FILES_DIR, old_stored_name)
        archive_path = os.path.join(VERSIONS_DIR, old_stored_name)

        if os.path.exists(old_live_path):
            shutil.copy2(old_live_path, archive_path)

        # Write new file to FILES_DIR
        with open(new_path, "wb") as f:
            f.write(content)

        db.execute(
            """
            INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, new_version, new_stored_name, size_bytes, current_user["id"], note),
        )
        db.execute(
            """
            UPDATE files
            SET filename = ?, stored_name = ?, size_bytes = ?, mime_type = ?,
                current_version = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (file.filename, new_stored_name, size_bytes, file.content_type, new_version, file_id),
        )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        if new_path and os.path.exists(new_path):
            os.remove(new_path)
        raise
    finally:
        db.close()

    return {
        "file_id": file_id,
        "filename": file.filename,
        "version": new_version,
        "size_bytes": size_bytes,
    }


@router.get("/{file_id}/versions")
def list_versions(file_id: int, current_user=Depends(get_current_user)):
    """List all versions of a file."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(row, current_user["id"])

        versions = db.execute(
            """
            SELECT version_num, stored_name, size_bytes, uploaded_by, note, created_at
            FROM versions
            WHERE file_id = ?
            ORDER BY version_num
            """,
            (file_id,),
        ).fetchall()

        return {
            "file_id": file_id,
            "filename": row["filename"],
            "current_version": row["current_version"],
            "versions": [dict(v) for v in versions],
        }
    finally:
        db.close()


@router.get("/{file_id}/versions/{version_num}/download")
def download_version(
    file_id: int,
    version_num: int,
    current_user=Depends(get_current_user),
):
    """Download a specific version of a file."""
    db = get_db()
    try:
        file_row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(file_row, current_user["id"])

        ver = db.execute(
            "SELECT * FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num),
        ).fetchone()
        if ver is None:
            raise HTTPException(status_code=404, detail=f"Version {version_num} not found")

        path = _resolve_version_path(ver["stored_name"], version_num, file_row["current_version"])
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Version data missing on disk")

        name, ext = os.path.splitext(file_row["filename"])
        download_name = f"{name}_v{version_num}{ext}"
        return FileResponse(path, filename=download_name)
    finally:
        db.close()


@router.delete("/{file_id}/versions/{version_num}")
def delete_version(
    file_id: int,
    version_num: int,
    current_user=Depends(get_current_user),
):
    """
    Delete a specific version of a file.
    - Cannot delete the current (latest) version.
    - Cannot delete if only one version exists.
    """
    db = get_db()
    try:
        file_row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(file_row, current_user["id"])

        # Block deletion of the current version
        if version_num == file_row["current_version"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the current version. Upload a new version first, or delete the entire file.",
            )

        # Block deletion if only one version exists
        total_versions = db.execute(
            "SELECT COUNT(*) FROM versions WHERE file_id = ?", (file_id,)
        ).fetchone()[0]
        if total_versions <= 1:
            raise HTTPException(
                status_code=400,
                detail="Only one version exists. Use DELETE /files/{file_id} to delete the entire file.",
            )

        ver = db.execute(
            "SELECT * FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num),
        ).fetchone()
        if ver is None:
            raise HTTPException(status_code=404, detail=f"Version {version_num} not found")

        # Remove from disk (old versions live in VERSIONS_DIR)
        path = _resolve_version_path(ver["stored_name"], version_num, file_row["current_version"])
        if os.path.exists(path):
            os.remove(path)

        db.execute(
            "DELETE FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num),
        )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "detail": f"Version {version_num} of file {file_id} deleted successfully."
    }


@router.delete("/{file_id}")
def delete_file(file_id: int, current_user=Depends(get_current_user)):
    """Delete a file and ALL its versions from DB and disk."""
    db = get_db()
    try:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(row, current_user["id"])

        ver_rows = db.execute(
            "SELECT stored_name, version_num FROM versions WHERE file_id = ?",
            (file_id,),
        ).fetchall()

        for v in ver_rows:
            path = _resolve_version_path(v["stored_name"], v["version_num"], row["current_version"])
            if os.path.exists(path):
                os.remove(path)

        # ON DELETE CASCADE removes versions rows automatically
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"detail": f"File {file_id} and all its versions deleted successfully."}


class RenamePayload(BaseModel):
    filename: str


@router.patch("/{file_id}/rename")
def rename_file(
    file_id: int,
    payload: RenamePayload,
    current_user=Depends(get_current_user),
):
    """Rename a file (metadata only — no disk changes)."""
    new_name = payload.filename.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="filename must not be empty")

    db = get_db()
    try:
        row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        _assert_owns(row, current_user["id"])

        db.execute(
            "UPDATE files SET filename = ?, updated_at = datetime('now') WHERE id = ?",
            (new_name, file_id),
        )
        db.commit()
    finally:
        db.close()

    return {"file_id": file_id, "filename": new_name}
