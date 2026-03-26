"""
CLOTE - folder_routes.py
Folder management routes.

Schema reference:
  folders : id, owner_id, parent_id, name, created_at, updated_at
  files   : id, owner_id, folder_id, filename, stored_name, size_bytes,
            mime_type, current_version, created_at, updated_at
"""

import os
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db

router = APIRouter(prefix="/folders", tags=["folders"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _assert_owns_folder(folder_row, user_id: int):
    if folder_row is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder_row["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _new_stored_name() -> str:
    return str(uuid.uuid4())


def _touch_folder(db, folder_id: int):
    """Update folder updated_at whenever its contents change."""
    db.execute(
        "UPDATE folders SET updated_at = datetime('now') WHERE id = ?",
        (folder_id,),
    )


# ── Folder CRUD ───────────────────────────────────────────────────────────────

class CreateFolderPayload(BaseModel):
    name: str
    parent_id: Optional[int] = None


@router.post("/")
def create_folder(
    payload: CreateFolderPayload,
    current_user=Depends(get_current_user),
):
    """Create an empty folder (optionally inside a parent folder)."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Folder name must not be empty")

    db = get_db()
    try:
        # Validate parent folder ownership if provided
        if payload.parent_id is not None:
            parent = db.execute(
                "SELECT * FROM folders WHERE id = ?", (payload.parent_id,)
            ).fetchone()
            _assert_owns_folder(parent, current_user["id"])

        # Check for duplicate name in same location
        existing = db.execute(
            """
            SELECT id FROM folders
            WHERE owner_id = ? AND name = ? AND parent_id IS ?
            """,
            (current_user["id"], name, payload.parent_id),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A folder named '{name}' already exists here",
            )

        cursor = db.execute(
            """
            INSERT INTO folders (owner_id, parent_id, name)
            VALUES (?, ?, ?)
            """,
            (current_user["id"], payload.parent_id, name),
        )
        folder_id = cursor.lastrowid
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "folder_id": folder_id,
        "name": name,
        "parent_id": payload.parent_id,
    }


@router.get("/")
def list_root_folders(current_user=Depends(get_current_user)):
    """List all root-level folders (no parent) owned by the current user."""
    db = get_db()
    try:
        folders = db.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM folders
            WHERE owner_id = ? AND parent_id IS NULL
            ORDER BY name
            """,
            (current_user["id"],),
        ).fetchall()
        return [dict(f) for f in folders]
    finally:
        db.close()


@router.get("/{folder_id}")
def get_folder_contents(folder_id: int, current_user=Depends(get_current_user)):
    """Get contents of a folder — its subfolders and files."""
    db = get_db()
    try:
        folder = db.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        _assert_owns_folder(folder, current_user["id"])

        subfolders = db.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM folders
            WHERE owner_id = ? AND parent_id = ?
            ORDER BY name
            """,
            (current_user["id"], folder_id),
        ).fetchall()

        files = db.execute(
            """
            SELECT id, filename, size_bytes, mime_type, current_version, created_at, updated_at
            FROM files
            WHERE owner_id = ? AND folder_id = ?
            ORDER BY filename
            """,
            (current_user["id"], folder_id),
        ).fetchall()

        return {
            "folder_id": folder_id,
            "name": folder["name"],
            "parent_id": folder["parent_id"],
            "subfolders": [dict(f) for f in subfolders],
            "files": [dict(f) for f in files],
        }
    finally:
        db.close()


@router.post("/{folder_id}/upload")
async def upload_files_to_folder(
    folder_id: int,
    files: List[UploadFile] = File(...),
    current_user=Depends(get_current_user),
):
    """
    Upload one or more files into a folder (entire folder upload).
    Each file is stored as version 1.
    """
    db = get_db()
    saved_paths = []
    try:
        folder = db.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        _assert_owns_folder(folder, current_user["id"])

        results = []
        for file in files:
            content = await file.read()
            size_bytes = len(content)
            stored_name = _new_stored_name()
            dest_path = os.path.join(FILES_DIR, stored_name)

            with open(dest_path, "wb") as f:
                f.write(content)
            saved_paths.append(dest_path)

            cursor = db.execute(
                """
                INSERT INTO files (owner_id, folder_id, filename, stored_name, size_bytes, mime_type, current_version)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (current_user["id"], folder_id, file.filename, stored_name, size_bytes, file.content_type),
            )
            file_id = cursor.lastrowid

            db.execute(
                """
                INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by)
                VALUES (?, 1, ?, ?, ?)
                """,
                (file_id, stored_name, size_bytes, current_user["id"]),
            )

            results.append({
                "file_id": file_id,
                "filename": file.filename,
                "size_bytes": size_bytes,
                "version": 1,
            })

        _touch_folder(db, folder_id)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        for path in saved_paths:
            if os.path.exists(path):
                os.remove(path)
        raise
    finally:
        db.close()

    return {
        "folder_id": folder_id,
        "uploaded": len(results),
        "files": results,
    }


class RenameFolderPayload(BaseModel):
    name: str


@router.patch("/{folder_id}/rename")
def rename_folder(
    folder_id: int,
    payload: RenameFolderPayload,
    current_user=Depends(get_current_user),
):
    """Rename a folder."""
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="Folder name must not be empty")

    db = get_db()
    try:
        folder = db.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        _assert_owns_folder(folder, current_user["id"])

        # Check for duplicate name in same parent
        existing = db.execute(
            """
            SELECT id FROM folders
            WHERE owner_id = ? AND name = ? AND parent_id IS ? AND id != ?
            """,
            (current_user["id"], new_name, folder["parent_id"], folder_id),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"A folder named '{new_name}' already exists here",
            )

        db.execute(
            "UPDATE folders SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (new_name, folder_id),
        )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"folder_id": folder_id, "name": new_name}


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, current_user=Depends(get_current_user)):
    """
    Delete a folder and everything inside it recursively
    (subfolders, files, all versions) from DB and disk.
    """
    db = get_db()
    try:
        folder = db.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        _assert_owns_folder(folder, current_user["id"])

        # Collect all folder IDs in the subtree (BFS)
        all_folder_ids = [folder_id]
        queue = [folder_id]
        while queue:
            current = queue.pop(0)
            children = db.execute(
                "SELECT id FROM folders WHERE parent_id = ?", (current,)
            ).fetchall()
            for child in children:
                all_folder_ids.append(child["id"])
                queue.append(child["id"])

        # Collect all files in all folders of the subtree
        placeholders = ",".join("?" * len(all_folder_ids))
        file_rows = db.execute(
            f"""
            SELECT f.stored_name, f.current_version,
                   v.stored_name AS ver_stored_name, v.version_num
            FROM files f
            JOIN versions v ON v.file_id = f.id
            WHERE f.folder_id IN ({placeholders})
            """,
            all_folder_ids,
        ).fetchall()

        # Remove all version files from disk
        for row in file_rows:
            if row["version_num"] == row["current_version"]:
                path = os.path.join(FILES_DIR, row["ver_stored_name"])
            else:
                path = os.path.join(VERSIONS_DIR, row["ver_stored_name"])
                if not os.path.exists(path):
                    path = os.path.join(FILES_DIR, row["ver_stored_name"])
            if os.path.exists(path):
                os.remove(path)

        # ON DELETE CASCADE handles files + versions rows when folders are deleted
        db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"detail": f"Folder {folder_id} and all its contents deleted successfully."}
