"""
CLOTE - routes/share_routes.py
Token-based public share links for files.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR
from database import get_db

router = APIRouter(prefix="/share", tags=["Share"])


class CreateShareBody(BaseModel):
    file_id: int
    expires_hours: Optional[int] = None   # None = never expires
    max_uses: Optional[int] = None        # None = unlimited


@router.post("/")
def create_share_link(body: CreateShareBody, user=Depends(get_current_user)):
    conn = get_db()
    try:
        file = conn.execute(
            "SELECT * FROM files WHERE id=? AND deleted_at IS NULL", (body.file_id,)
        ).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        if file["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Only the file owner can share")

        token = secrets.token_urlsafe(32)
        expires_at = None
        if body.expires_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=body.expires_hours)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            """INSERT INTO shared_links (token, file_id, created_by, expires_at, max_uses)
               VALUES (?,?,?,?,?)""",
            (token, body.file_id, user["id"], expires_at, body.max_uses)
        )
        conn.commit()
        return {"token": token, "expires_at": expires_at, "max_uses": body.max_uses}
    finally:
        conn.close()


@router.get("/links")
def list_my_share_links(user=Depends(get_current_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT sl.*, f.filename FROM shared_links sl
               JOIN files f ON f.id = sl.file_id
               WHERE sl.created_by=? ORDER BY sl.created_at DESC""",
            (user["id"],)
        ).fetchall()
        return {"links": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.delete("/{token}")
def revoke_share_link(token: str, user=Depends(get_current_user)):
    conn = get_db()
    try:
        link = conn.execute(
            "SELECT * FROM shared_links WHERE token=? AND created_by=?",
            (token, user["id"])
        ).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
        conn.execute("DELETE FROM shared_links WHERE token=?", (token,))
        conn.commit()
        return {"message": "Link revoked"}
    finally:
        conn.close()


@router.get("/{token}/download")
def download_shared_file(token: str):
    """Public endpoint — no auth required."""
    conn = get_db()
    try:
        link = conn.execute(
            "SELECT * FROM shared_links WHERE token=?", (token,)
        ).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="Invalid link")

        if link["expires_at"]:
            if datetime.utcnow() > datetime.strptime(link["expires_at"], "%Y-%m-%d %H:%M:%S"):
                raise HTTPException(status_code=410, detail="Link expired")

        if link["max_uses"] and link["use_count"] >= link["max_uses"]:
            raise HTTPException(status_code=410, detail="Link use limit reached")

        file = conn.execute(
            "SELECT * FROM files WHERE id=? AND deleted_at IS NULL", (link["file_id"],)
        ).fetchone()
        if not file:
            raise HTTPException(status_code=404, detail="File no longer available")

        conn.execute(
            "UPDATE shared_links SET use_count=use_count+1 WHERE token=?", (token,)
        )
        conn.commit()

        path = Path(FILES_DIR) / file["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="File missing from storage")

        return FileResponse(
            path=str(path),
            filename=file["filename"],
            media_type=file["mime_type"] or "application/octet-stream"
        )
    finally:
        conn.close()
