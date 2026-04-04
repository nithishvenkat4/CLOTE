"""
CLOTE - trash_routes.py
Soft delete, restore, list trash, and empty trash.
Audit logging wired in for restore/permanent delete/empty.
"""

from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from auth import get_current_user
from datetime import datetime
from routes.audit_routes import log_action

router = APIRouter(prefix="/trash", tags=["Trash"])


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


@router.get("/")
async def list_trash(current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        uid = user["id"]
        files = db.execute(
            "SELECT id, filename, size_bytes, mime_type, deleted_at, folder_id, project_id FROM files WHERE owner_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (uid,)
        ).fetchall()
        folders = db.execute(
            "SELECT id, name, deleted_at, parent_id, project_id FROM folders WHERE owner_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (uid,)
        ).fetchall()
    return {"files": [dict(f) for f in files], "folders": [dict(f) for f in folders]}


@router.delete("/files/{file_id}")
async def trash_file(file_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        file = db.execute("SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL", (file_id, uid)).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        db.execute("UPDATE files SET deleted_at=?, deleted_by=? WHERE id=?", (_now(), uid, file_id))
        log_action(db, uid, current_user["username"], "trash", target_type="file", target_id=file_id, target_name=file["filename"])
        db.commit()
    return {"message": "File moved to trash"}


@router.delete("/folders/{folder_id}")
async def trash_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        folder = db.execute("SELECT * FROM folders WHERE id=? AND owner_id=? AND deleted_at IS NULL", (folder_id, uid)).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        now = _now()
        db.execute("UPDATE folders SET deleted_at=?, deleted_by=? WHERE id=?", (now, uid, folder_id))
        db.execute("UPDATE files SET deleted_at=?, deleted_by=? WHERE folder_id=? AND deleted_at IS NULL", (now, uid, folder_id))
        log_action(db, uid, current_user["username"], "trash", target_type="folder", target_id=folder_id, target_name=folder["name"])
        db.commit()
    return {"message": "Folder moved to trash"}


@router.post("/files/{file_id}/restore")
async def restore_file(file_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        file = db.execute("SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL", (file_id, uid)).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not in trash")
        db.execute("UPDATE files SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (file_id,))
        log_action(db, uid, current_user["username"], "restore", target_type="file", target_id=file_id, target_name=file["filename"])
        db.commit()
    return {"message": "File restored"}


@router.post("/folders/{folder_id}/restore")
async def restore_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        folder = db.execute("SELECT * FROM folders WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL", (folder_id, uid)).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not in trash")
        db.execute("UPDATE folders SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (folder_id,))
        db.execute("UPDATE files SET deleted_at=NULL, deleted_by=NULL WHERE folder_id=? AND deleted_by=?", (folder_id, uid))
        log_action(db, uid, current_user["username"], "restore", target_type="folder", target_id=folder_id, target_name=folder["name"])
        db.commit()
    return {"message": "Folder restored"}


@router.delete("/files/{file_id}/permanent")
async def permanent_delete_file(file_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        file = db.execute("SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL", (file_id, uid)).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not in trash")
        db.execute("DELETE FROM files WHERE id=?", (file_id,))
        log_action(db, uid, current_user["username"], "permanent_delete", target_type="file", target_id=file_id, target_name=file["filename"])
        db.commit()
    return {"message": "File permanently deleted"}


@router.delete("/folders/{folder_id}/permanent")
async def permanent_delete_folder(folder_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        folder = conn.execute("SELECT * FROM folders WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL", (folder_id, uid)).fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not in trash")
        _permanent_delete_folder_tree(conn, folder_id)
        log_action(conn, uid, current_user["username"], "permanent_delete", target_type="folder", target_id=folder_id, target_name=folder["name"])
        conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Folder permanently deleted"}


def _permanent_delete_folder_tree(conn, folder_id: int):
    from pathlib import Path
    from config import FILES_DIR, VERSIONS_DIR
    files = conn.execute("SELECT id, stored_name FROM files WHERE folder_id=?", (folder_id,)).fetchall()
    for f in files:
        versions = conn.execute("SELECT stored_name FROM versions WHERE file_id=?", (f["id"],)).fetchall()
        for v in versions:
            p = Path(VERSIONS_DIR) / v["stored_name"]
            if p.exists(): p.unlink()
        p = Path(FILES_DIR) / f["stored_name"]
        if p.exists(): p.unlink()
    children = conn.execute("SELECT id FROM folders WHERE parent_id=?", (folder_id,)).fetchall()
    for child in children:
        _permanent_delete_folder_tree(conn, child["id"])


@router.delete("/empty")
async def empty_trash(current_user: dict = Depends(get_current_user)):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE username=?", (current_user["username"],)).fetchone()
        uid = user["id"]
        db.execute("DELETE FROM files WHERE owner_id=? AND deleted_at IS NOT NULL", (uid,))
        db.execute("DELETE FROM folders WHERE owner_id=? AND deleted_at IS NOT NULL", (uid,))
        log_action(db, uid, current_user["username"], "empty_trash", detail="All trash emptied")
        db.commit()
    return {"message": "Trash emptied"}
