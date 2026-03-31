"""
CLOTE - routes/bulk_routes.py
Bulk actions: delete, restore, move for multiple files at once.
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db

router = APIRouter(prefix="/bulk", tags=["Bulk"])


class BulkTrashBody(BaseModel):
    file_ids: List[int]

class BulkRestoreBody(BaseModel):
    file_ids: List[int]

class BulkDeleteBody(BaseModel):
    file_ids: List[int]

class BulkMoveBody(BaseModel):
    file_ids: List[int]
    folder_id: Optional[int] = None


@router.post("/trash")
def bulk_trash(body: BulkTrashBody, user=Depends(get_current_user)):
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    conn = get_db()
    try:
        moved = 0
        for fid in body.file_ids:
            row = conn.execute(
                "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (fid, user["id"])
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE files SET deleted_at=datetime('now'), deleted_by=? WHERE id=?",
                    (user["id"], fid)
                )
                moved += 1
        conn.commit()
        return {"moved_to_trash": moved}
    finally:
        conn.close()


@router.post("/restore")
def bulk_restore(body: BulkRestoreBody, user=Depends(get_current_user)):
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    conn = get_db()
    try:
        restored = 0
        for fid in body.file_ids:
            row = conn.execute(
                "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL",
                (fid, user["id"])
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE files SET deleted_at=NULL, deleted_by=NULL WHERE id=?",
                    (fid,)
                )
                restored += 1
        conn.commit()
        return {"restored": restored}
    finally:
        conn.close()


@router.post("/delete")
def bulk_permanent_delete(body: BulkDeleteBody, user=Depends(get_current_user)):
    """Permanently delete files that are already in trash."""
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    conn = get_db()
    try:
        deleted = 0
        for fid in body.file_ids:
            row = conn.execute(
                "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NOT NULL",
                (fid, user["id"])
            ).fetchone()
            if row:
                # Delete versions from disk
                versions = conn.execute(
                    "SELECT stored_name FROM versions WHERE file_id=?", (fid,)
                ).fetchall()
                for v in versions:
                    p = Path(VERSIONS_DIR) / v["stored_name"]
                    if p.exists():
                        p.unlink()
                # Delete current file from disk
                p = Path(FILES_DIR) / row["stored_name"]
                if p.exists():
                    p.unlink()
                conn.execute("DELETE FROM files WHERE id=?", (fid,))
                deleted += 1
        conn.commit()
        return {"permanently_deleted": deleted}
    finally:
        conn.close()


@router.post("/move")
def bulk_move(body: BulkMoveBody, user=Depends(get_current_user)):
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    conn = get_db()
    try:
        if body.folder_id is not None:
            folder = conn.execute(
                "SELECT * FROM folders WHERE id=?", (body.folder_id,)
            ).fetchone()
            if not folder:
                raise HTTPException(status_code=404, detail="Target folder not found")

        moved = 0
        for fid in body.file_ids:
            row = conn.execute(
                "SELECT * FROM files WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (fid, user["id"])
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE files SET folder_id=?, updated_at=datetime('now') WHERE id=?",
                    (body.folder_id, fid)
                )
                moved += 1
        conn.commit()
        return {"moved": moved, "folder_id": body.folder_id}
    finally:
        conn.close()
