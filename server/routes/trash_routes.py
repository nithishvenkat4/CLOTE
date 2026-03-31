"""
CLOTE - trash_routes.py
Soft delete, restore, list trash, and empty trash.
"""

from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/trash", tags=["Trash"])


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ── List all trashed items ──────────────────────────────────────────

@router.get("/")
async def list_trash(current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        uid = user["id"]

        files = db.execute(
            """SELECT id, filename, size_bytes, mime_type, deleted_at, folder_id, project_id
               FROM files
               WHERE owner_id=? AND deleted_at IS NOT NULL
               ORDER BY deleted_at DESC""",
            (uid,)
        ).fetchall()

        folders = db.execute(
            """SELECT id, name, deleted_at, parent_id, project_id
               FROM folders
               WHERE owner_id=? AND deleted_at IS NOT NULL
               ORDER BY deleted_at DESC""",
            (uid,)
        ).fetchall()

    return {
        "files": [dict(f) for f in files],
        "folders": [dict(f) for f in folders]
    }


# ── Soft delete a file ──────────────────────────────────────────────

@router.delete("/files/{file_id}")
async def trash_file(file_id: int, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        file = db.execute(
            "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL",
            (file_id, uid)
        ).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        db.execute(
            "UPDATE files SET deleted_at=?, deleted_by=? WHERE id=?",
            (_now(), uid, file_id)
        )
        db.commit()

    return {"message": "File moved to trash"}


# ── Soft delete a folder ────────────────────────────────────────────

@router.delete("/folders/{folder_id}")
async def trash_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        folder = db.execute(
            "SELECT * FROM folders WHERE id=? AND owner_id=? AND deleted_at IS NULL",
            (folder_id, uid)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        now = _now()
        # Trash the folder and all files inside it
        db.execute(
            "UPDATE folders SET deleted_at=?, deleted_by=? WHERE id=?",
            (now, uid, folder_id)
        )
        db.execute(
            "UPDATE files SET deleted_at=?, deleted_by=? WHERE folder_id=? AND deleted_at IS NULL",
            (now, uid, folder_id)
        )
        db.commit()

    return {"message": "Folder moved to trash"}


# ── Restore a file ──────────────────────────────────────────────────

@router.post("/files/{file_id}/restore")
async def restore_file(file_id: int, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        file = db.execute(
            "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL",
            (file_id, uid)
        ).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not in trash")

        db.execute(
            "UPDATE files SET deleted_at=NULL, deleted_by=NULL WHERE id=?",
            (file_id,)
        )
        db.commit()

    return {"message": "File restored"}


# ── Restore a folder ────────────────────────────────────────────────

@router.post("/folders/{folder_id}/restore")
async def restore_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        folder = db.execute(
            "SELECT * FROM folders WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL",
            (folder_id, uid)
        ).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not in trash")

        # Restore folder and all files that were trashed with it
        db.execute(
            "UPDATE folders SET deleted_at=NULL, deleted_by=NULL WHERE id=?",
            (folder_id,)
        )
        db.execute(
            "UPDATE files SET deleted_at=NULL, deleted_by=NULL WHERE folder_id=? AND deleted_by=?",
            (folder_id, uid)
        )
        db.commit()

    return {"message": "Folder restored"}


# ── Permanently delete a file ───────────────────────────────────────

@router.delete("/files/{file_id}/permanent")
async def permanent_delete_file(file_id: int, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        file = db.execute(
            "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL",
            (file_id, uid)
        ).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not in trash")

        db.execute("DELETE FROM files WHERE id=?", (file_id,))
        db.commit()

    return {"message": "File permanently deleted"}


# ── Empty trash (all items) ─────────────────────────────────────────

@router.delete("/empty")
async def empty_trash(current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        uid = user["id"]

        db.execute(
            "DELETE FROM files WHERE owner_id=? AND deleted_at IS NOT NULL", (uid,)
        )
        db.execute(
            "DELETE FROM folders WHERE owner_id=? AND deleted_at IS NOT NULL", (uid,)
        )
        db.commit()

    return {"message": "Trash emptied"}