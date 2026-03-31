"""
CLOTE - routes/file_routes.py
File upload, download, preview, versioning, rename, move, delete.
Now project-aware: files can belong to a project (project_id) or be personal (project_id IS NULL).
"""

import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db
from routes.project_routes import get_member_role, require_editor_or_above

router = APIRouter(prefix="/files", tags=["files"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class RenameBody(BaseModel):
    filename: str

class MoveBody(BaseModel):
    folder_id: Optional[int] = None


# ─────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────

def _check_file_access(conn, file_row, user, require_write: bool = False):
    """
    Check the current user can access a file.
    - Personal files: only the owner.
    - Project files: any member can read; editors/owners can write.
    """
    if file_row["project_id"] is None:
        # Personal file — owner only
        if file_row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        # Project file — check membership
        if require_write:
            require_editor_or_above(conn, file_row["project_id"], user["id"])
        else:
            get_member_role(conn, file_row["project_id"], user["id"])


# ─────────────────────────────────────────────
# Upload new file
# ─────────────────────────────────────────────

@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    user=Depends(get_current_user)
):
    """
    Upload a brand-new file to My Files (project_id=None) or a project root.
    For folder uploads use POST /folders/{folder_id}/upload.
    """
    conn = get_db()
    try:
        # If uploading to a project, must be editor or above
        if project_id is not None:
            require_editor_or_above(conn, project_id, user["id"])

        stored_name = f"{uuid.uuid4().hex}_{file.filename}"
        dest = Path(FILES_DIR) / stored_name

        content = await file.read()
        dest.write_bytes(content)
        size = len(content)

        cur = conn.execute(
            """INSERT INTO files
               (owner_id, folder_id, project_id, filename, stored_name, size_bytes, mime_type, current_version)
               VALUES (?, NULL, ?, ?, ?, ?, ?, 1)""",
            (user["id"], project_id, file.filename, stored_name, size, file.content_type)
        )
        file_id = cur.lastrowid

        # Create version 1 record
        conn.execute(
            """INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by)
               VALUES (?, 1, ?, ?, ?)""",
            (file_id, stored_name, size, user["id"])
        )
        conn.commit()

        return {
            "id": file_id,
            "filename": file.filename,
            "size_bytes": size,
            "current_version": 1,
            "project_id": project_id
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# List files
# ─────────────────────────────────────────────

@router.get("/")
def list_files(project_id: Optional[int] = Query(None), user=Depends(get_current_user)):
    """
    List files.
    - project_id=None  → personal files only
    - project_id=X     → project files (must be member)
    """
    conn = get_db()
    try:
        if project_id is not None:
            get_member_role(conn, project_id, user["id"])
            rows = conn.execute(
                "SELECT * FROM files WHERE project_id = ? ORDER BY filename",
                (project_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files WHERE owner_id = ? AND project_id IS NULL ORDER BY filename",
                (user["id"],)
            ).fetchall()

        return {"files": [dict(r) for r in rows]}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Download file (current version)
# ─────────────────────────────────────────────

@router.get("/{file_id}/download")
def download_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)

        path = Path(FILES_DIR) / row["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="File missing from storage")

        return FileResponse(
            path=str(path),
            filename=row["filename"],
            media_type=row["mime_type"] or "application/octet-stream"
        )
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Preview file (inline, no download header)
# ─────────────────────────────────────────────

PREVIEWABLE = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf", "text/plain", "text/markdown", "text/csv",
    "text/html", "application/json"
}

@router.get("/{file_id}/preview")
def preview_file(file_id: int, user=Depends(get_current_user)):
    """
    Serve the file inline for browser preview.
    Only allowed for safe MIME types.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)

        mime = row["mime_type"] or "application/octet-stream"
        if mime not in PREVIEWABLE:
            raise HTTPException(status_code=415,
                                detail="This file type cannot be previewed inline")

        path = Path(FILES_DIR) / row["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="File missing from storage")

        return FileResponse(
            path=str(path),
            media_type=mime,
            headers={"Content-Disposition": f"inline; filename=\"{row['filename']}\""}
        )
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Upload new version
# ─────────────────────────────────────────────

@router.post("/{file_id}/upload", status_code=201)
async def upload_new_version(
    file_id: int,
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    user=Depends(get_current_user)
):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)

        new_version = row["current_version"] + 1
        stored_name = f"{uuid.uuid4().hex}_{file.filename}"

        content = await file.read()
        size = len(content)

        # Save to versions/ directory
        dest = Path(VERSIONS_DIR) / stored_name
        dest.write_bytes(content)

        # Also overwrite the current file in files/ so download always gets latest
        current_path = Path(FILES_DIR) / row["stored_name"]
        current_path.write_bytes(content)

        # Insert version record
        conn.execute(
            """INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (file_id, new_version, stored_name, size, user["id"], note)
        )

        # Update file record
        conn.execute(
            """UPDATE files SET current_version = ?, size_bytes = ?,
               filename = ?, updated_at = datetime('now') WHERE id = ?""",
            (new_version, size, file.filename, file_id)
        )
        conn.commit()

        return {
            "file_id": file_id,
            "version": new_version,
            "size_bytes": size,
            "note": note
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# List versions
# ─────────────────────────────────────────────

@router.get("/{file_id}/versions")
def list_versions(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)

        current_version = row["current_version"]
        versions = conn.execute(
            "SELECT * FROM versions WHERE file_id = ? ORDER BY version_num DESC",
            (file_id,)
        ).fetchall()

        result = []
        for v in versions:
            d = dict(v)
            d["is_current"] = (v["version_num"] == current_version)
            result.append(d)

        return result
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Download specific version
# ─────────────────────────────────────────────

@router.get("/{file_id}/versions/{version_num}/download")
def download_version(file_id: int, version_num: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)

        ver = conn.execute(
            "SELECT * FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num)
        ).fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="Version not found")

        # Current version lives in FILES_DIR, older ones in VERSIONS_DIR
        if version_num == row["current_version"]:
            path = Path(FILES_DIR) / row["stored_name"]
        else:
            path = Path(VERSIONS_DIR) / ver["stored_name"]

        if not path.exists():
            raise HTTPException(status_code=404, detail="Version file missing from storage")

        return FileResponse(
            path=str(path),
            filename=f"v{version_num}_{row['filename']}",
            media_type=row["mime_type"] or "application/octet-stream"
        )
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Delete specific version
# ─────────────────────────────────────────────

@router.delete("/{file_id}/versions/{version_num}", status_code=204)
def delete_version(file_id: int, version_num: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)

        if version_num == row["current_version"]:
            raise HTTPException(status_code=400, detail="Cannot delete the current version")

        ver = conn.execute(
            "SELECT * FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num)
        ).fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="Version not found")

        # Remove from disk
        path = Path(VERSIONS_DIR) / ver["stored_name"]
        if path.exists():
            path.unlink()

        conn.execute(
            "DELETE FROM versions WHERE file_id = ? AND version_num = ?",
            (file_id, version_num)
        )
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Rename file
# ─────────────────────────────────────────────

@router.patch("/{file_id}/rename")
def rename_file(file_id: int, body: RenameBody, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)

        conn.execute(
            "UPDATE files SET filename = ?, updated_at = datetime('now') WHERE id = ?",
            (body.filename.strip(), file_id)
        )
        conn.commit()
        return {"detail": "Renamed", "filename": body.filename.strip()}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Move file to a different folder
# ─────────────────────────────────────────────

@router.patch("/{file_id}/move")
def move_file(file_id: int, body: MoveBody, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)

        # Validate target folder belongs to same owner / project
        if body.folder_id is not None:
            folder = conn.execute(
                "SELECT * FROM folders WHERE id = ?", (body.folder_id,)
            ).fetchone()
            if not folder:
                raise HTTPException(status_code=404, detail="Target folder not found")
            if folder["project_id"] != row["project_id"]:
                raise HTTPException(status_code=400,
                                    detail="Cannot move file across projects")

        conn.execute(
            "UPDATE files SET folder_id = ?, updated_at = datetime('now') WHERE id = ?",
            (body.folder_id, file_id)
        )
        conn.commit()
        return {"detail": "Moved", "folder_id": body.folder_id}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Delete file
# ─────────────────────────────────────────────

@router.delete("/{file_id}", status_code=204)
def delete_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)

        # Delete all version files from disk
        versions = conn.execute(
            "SELECT stored_name FROM versions WHERE file_id = ?", (file_id,)
        ).fetchall()
        for v in versions:
            p = Path(VERSIONS_DIR) / v["stored_name"]
            if p.exists():
                p.unlink()

        # Delete current file from disk
        p = Path(FILES_DIR) / row["stored_name"]
        if p.exists():
            p.unlink()

        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
    finally:
        conn.close()
