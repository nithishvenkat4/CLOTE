"""
CLOTE - routes/folder_routes.py
Folder CRUD + file upload into folders.
Now project-aware: folders can belong to a project or be personal.
"""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db
from routes.project_routes import get_member_role, require_editor_or_above

router = APIRouter(prefix="/folders", tags=["folders"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    project_id: Optional[int] = None

class FolderRename(BaseModel):
    name: str


# ─────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────

def _check_folder_access(conn, folder_row, user, require_write: bool = False):
    if folder_row["project_id"] is None:
        if folder_row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if require_write:
            require_editor_or_above(conn, folder_row["project_id"], user["id"])
        else:
            get_member_role(conn, folder_row["project_id"], user["id"])


# ─────────────────────────────────────────────
# Create folder
# ─────────────────────────────────────────────

@router.post("/", status_code=201)
def create_folder(body: FolderCreate, user=Depends(get_current_user)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")

    conn = get_db()
    try:
        # If project folder, must be editor or above
        if body.project_id is not None:
            require_editor_or_above(conn, body.project_id, user["id"])

        # Validate parent folder exists and belongs to same context
        if body.parent_id is not None:
            parent = conn.execute(
                "SELECT * FROM folders WHERE id = ?", (body.parent_id,)
            ).fetchone()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent folder not found")
            if parent["project_id"] != body.project_id:
                raise HTTPException(status_code=400,
                                    detail="Parent folder belongs to a different context")

        cur = conn.execute(
            """INSERT INTO folders (owner_id, parent_id, project_id, name)
               VALUES (?, ?, ?, ?)""",
            (user["id"], body.parent_id, body.project_id, body.name.strip())
        )
        folder_id = cur.lastrowid
        conn.commit()

        return {
            "id": folder_id,
            "name": body.name.strip(),
            "parent_id": body.parent_id,
            "project_id": body.project_id,
            "owner_id": user["id"]
        }
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409,
                                detail="A folder with this name already exists here")
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# List folders (personal root or project root)
# ─────────────────────────────────────────────

@router.get("/")
def list_folders(user=Depends(get_current_user)):
    """
    Returns all personal folders (project_id IS NULL) owned by the user.
    For project folders use GET /projects/{id} instead.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM folders
               WHERE owner_id = ? AND project_id IS NULL
               ORDER BY name""",
            (user["id"],)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Get folder contents (children + files)
# ─────────────────────────────────────────────

@router.get("/{folder_id}")
def get_folder(folder_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        folder = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_folder_access(conn, folder, user, require_write=False)

        children = conn.execute(
            "SELECT * FROM folders WHERE parent_id = ? ORDER BY name",
            (folder_id,)
        ).fetchall()

        files = conn.execute(
            "SELECT * FROM files WHERE folder_id = ? ORDER BY filename",
            (folder_id,)
        ).fetchall()

        return {
            **dict(folder),
            "children": [dict(c) for c in children],
            "files": [dict(f) for f in files],
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Upload file into folder
# ─────────────────────────────────────────────

@router.post("/{folder_id}/upload", status_code=201)
async def upload_to_folder(
    folder_id: int,
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    conn = get_db()
    try:
        folder = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_folder_access(conn, folder, user, require_write=True)

        stored_name = f"{uuid.uuid4().hex}_{file.filename}"
        dest = Path(FILES_DIR) / stored_name

        content = await file.read()
        dest.write_bytes(content)
        size = len(content)

        cur = conn.execute(
            """INSERT INTO files
               (owner_id, folder_id, project_id, filename, stored_name, size_bytes, mime_type, current_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (user["id"], folder_id, folder["project_id"],
             file.filename, stored_name, size, file.content_type)
        )
        file_id = cur.lastrowid

        conn.execute(
            """INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by)
               VALUES (?, 1, ?, ?, ?)""",
            (file_id, stored_name, size, user["id"])
        )
        conn.commit()

        return {
            "id": file_id,
            "filename": file.filename,
            "folder_id": folder_id,
            "project_id": folder["project_id"],
            "size_bytes": size,
            "current_version": 1
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Rename folder
# ─────────────────────────────────────────────

@router.patch("/{folder_id}/rename")
def rename_folder(folder_id: int, body: FolderRename, user=Depends(get_current_user)):
    conn = get_db()
    try:
        folder = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_folder_access(conn, folder, user, require_write=True)

        conn.execute(
            "UPDATE folders SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (body.name.strip(), folder_id)
        )
        conn.commit()
        return {"detail": "Renamed", "name": body.name.strip()}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Delete folder (cascades to children + files in DB)
# ─────────────────────────────────────────────

@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        folder = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_folder_access(conn, folder, user, require_write=True)

        # Collect all files inside this folder tree and delete from disk
        _delete_folder_files_from_disk(conn, folder_id)

        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
    finally:
        conn.close()


def _delete_folder_files_from_disk(conn, folder_id: int):
    """Recursively delete all files on disk for a folder tree."""
    files = conn.execute(
        "SELECT stored_name FROM files WHERE folder_id = ?", (folder_id,)
    ).fetchall()
    for f in files:
        p = Path(FILES_DIR) / f["stored_name"]
        if p.exists():
            p.unlink()
        # Also clean up version files
        versions = conn.execute(
            """SELECT v.stored_name FROM versions v
               JOIN files fi ON fi.id = v.file_id
               WHERE fi.folder_id = ?""",
            (folder_id,)
        ).fetchall()
        for v in versions:
            vp = Path(VERSIONS_DIR) / v["stored_name"]
            if vp.exists():
                vp.unlink()

    # Recurse into subfolders
    children = conn.execute(
        "SELECT id FROM folders WHERE parent_id = ?", (folder_id,)
    ).fetchall()
    for child in children:
        _delete_folder_files_from_disk(conn, child["id"])
