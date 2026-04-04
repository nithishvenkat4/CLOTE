"""
CLOTE - routes/file_routes.py
File upload, download, preview, versioning, rename, move, delete.
Audit logging wired in for all mutating operations.
"""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR, VERSIONS_DIR
from database import get_db
from routes.project_routes import get_member_role, require_editor_or_above
from routes.audit_routes import log_action

router = APIRouter(prefix="/files", tags=["files"])


class RenameBody(BaseModel):
    filename: str

class MoveBody(BaseModel):
    folder_id: Optional[int] = None


def _check_file_access(conn, file_row, user, require_write: bool = False):
    if file_row["project_id"] is None:
        if file_row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if require_write:
            require_editor_or_above(conn, file_row["project_id"], user["id"])
        else:
            get_member_role(conn, file_row["project_id"], user["id"])

def _ip(request: Request):
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


@router.get("/search")
async def search_files(q: str, project_id: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    if not q or len(q.strip()) < 1:
        return {"files": [], "folders": []}
    user_id = current_user["id"]
    pattern = f"%{q.strip()}%"
    conn = get_db()
    try:
        if project_id is not None:
            member = conn.execute("SELECT role FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id)).fetchone()
            if not member:
                raise HTTPException(status_code=403, detail="Not a project member")
            files = conn.execute("SELECT id, filename, size_bytes, mime_type, owner_id, created_at, current_version FROM files WHERE project_id=? AND deleted_at IS NULL AND filename LIKE ?", (project_id, pattern)).fetchall()
            folders = conn.execute("SELECT id, name, created_at FROM folders WHERE project_id=? AND deleted_at IS NULL AND name LIKE ?", (project_id, pattern)).fetchall()
        else:
            files = conn.execute("SELECT id, filename, size_bytes, mime_type, owner_id, created_at, current_version FROM files WHERE owner_id=? AND project_id IS NULL AND deleted_at IS NULL AND filename LIKE ?", (user_id, pattern)).fetchall()
            folders = conn.execute("SELECT id, name, created_at FROM folders WHERE owner_id=? AND project_id IS NULL AND deleted_at IS NULL AND name LIKE ?", (user_id, pattern)).fetchall()
        return {"files": [dict(f) for f in files], "folders": [dict(f) for f in folders]}
    finally:
        conn.close()


@router.post("/upload", status_code=201)
async def upload_file(request: Request, file: UploadFile = File(...), project_id: Optional[int] = Form(None), user=Depends(get_current_user)):
    conn = get_db()
    try:
        if project_id is not None:
            require_editor_or_above(conn, project_id, user["id"])
        stored_name = f"{uuid.uuid4().hex}_{file.filename}"
        dest = Path(FILES_DIR) / stored_name
        content = await file.read()
        dest.write_bytes(content)
        size = len(content)
        cur = conn.execute(
            "INSERT INTO files (owner_id, folder_id, project_id, filename, stored_name, size_bytes, mime_type, current_version) VALUES (?, NULL, ?, ?, ?, ?, ?, 1)",
            (user["id"], project_id, file.filename, stored_name, size, file.content_type)
        )
        file_id = cur.lastrowid
        conn.execute("INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by) VALUES (?, 1, ?, ?, ?)", (file_id, stored_name, size, user["id"]))
        log_action(conn, user["id"], user["username"], "upload", target_type="file", target_id=file_id, target_name=file.filename, project_id=project_id, ip_address=_ip(request))
        conn.commit()
        return {"id": file_id, "filename": file.filename, "size_bytes": size, "current_version": 1, "project_id": project_id}
    finally:
        conn.close()


@router.get("/")
def list_files(project_id: Optional[int] = Query(None), user=Depends(get_current_user)):
    conn = get_db()
    try:
        if project_id is not None:
            get_member_role(conn, project_id, user["id"])
            rows = conn.execute("SELECT * FROM files WHERE project_id = ? AND deleted_at IS NULL ORDER BY filename", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM files WHERE owner_id = ? AND project_id IS NULL AND deleted_at IS NULL ORDER BY filename", (user["id"],)).fetchall()
        return {"files": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/{file_id}/download")
def download_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)
        path = (Path(FILES_DIR).resolve() / row["stored_name"]).resolve()
        if not path.exists():
            candidates = list(Path(FILES_DIR).resolve().glob(row["stored_name"].split("_")[0] + "_*"))
            path = candidates[0] if candidates else None
            if not path:
                raise HTTPException(status_code=404, detail="File missing from storage")
        log_action(conn, user["id"], user["username"], "download", target_type="file", target_id=file_id, target_name=row["filename"], project_id=row["project_id"])
        conn.commit()
        return FileResponse(path=str(path), filename=row["filename"], media_type=row["mime_type"] or "application/octet-stream")
    finally:
        conn.close()


PREVIEWABLE = {"image/jpeg","image/png","image/gif","image/webp","image/svg+xml","application/pdf","text/plain","text/markdown","text/csv","text/html","application/json"}

@router.get("/{file_id}/preview")
def preview_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)
        mime = row["mime_type"] or "application/octet-stream"
        if mime not in PREVIEWABLE:
            raise HTTPException(status_code=415, detail="This file type cannot be previewed inline")
        path = (Path(FILES_DIR).resolve() / row["stored_name"]).resolve()
        if not path.exists():
            candidates = list(Path(FILES_DIR).resolve().glob(row["stored_name"].split("_")[0] + "_*"))
            if candidates:
                path = candidates[0]
            else:
                raise HTTPException(status_code=404, detail=f"File missing from storage: {row['stored_name']}")
        return FileResponse(path=str(path), media_type=mime, headers={"Content-Disposition": f"inline; filename=\"{row['filename']}\""})
    finally:
        conn.close()


@router.post("/{file_id}/upload", status_code=201)
async def upload_new_version(file_id: int, request: Request, file: UploadFile = File(...), note: Optional[str] = Form(None), user=Depends(get_current_user)):
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
        (Path(VERSIONS_DIR) / stored_name).write_bytes(content)
        (Path(FILES_DIR).resolve() / row["stored_name"]).write_bytes(content)
        conn.execute("INSERT INTO versions (file_id, version_num, stored_name, size_bytes, uploaded_by, note) VALUES (?, ?, ?, ?, ?, ?)", (file_id, new_version, stored_name, size, user["id"], note))
        conn.execute("UPDATE files SET current_version = ?, size_bytes = ?, filename = ?, updated_at = datetime('now') WHERE id = ?", (new_version, size, file.filename, file_id))
        log_action(conn, user["id"], user["username"], "new_version", target_type="file", target_id=file_id, target_name=row["filename"], project_id=row["project_id"], detail=f"v{new_version}" + (f" — {note}" if note else ""), ip_address=_ip(request))
        conn.commit()
        return {"file_id": file_id, "version": new_version, "size_bytes": size, "note": note}
    finally:
        conn.close()


@router.get("/{file_id}/versions")
def list_versions(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)
        current_version = row["current_version"]
        versions = conn.execute("SELECT * FROM versions WHERE file_id = ? ORDER BY version_num DESC", (file_id,)).fetchall()
        result = []
        for v in versions:
            d = dict(v)
            d["is_current"] = (v["version_num"] == current_version)
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/{file_id}/versions/{version_num}/download")
def download_version(file_id: int, version_num: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=False)
        ver = conn.execute("SELECT * FROM versions WHERE file_id = ? AND version_num = ?", (file_id, version_num)).fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="Version not found")
        if version_num == row["current_version"]:
            path = Path(FILES_DIR).resolve() / row["stored_name"]
        else:
            path = Path(VERSIONS_DIR) / ver["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="Version file missing from storage")
        return FileResponse(path=str(path), filename=f"v{version_num}_{row['filename']}", media_type=row["mime_type"] or "application/octet-stream")
    finally:
        conn.close()


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
        ver = conn.execute("SELECT * FROM versions WHERE file_id = ? AND version_num = ?", (file_id, version_num)).fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="Version not found")
        path = Path(VERSIONS_DIR) / ver["stored_name"]
        if path.exists():
            path.unlink()
        conn.execute("DELETE FROM versions WHERE file_id = ? AND version_num = ?", (file_id, version_num))
        log_action(conn, user["id"], user["username"], "delete_version", target_type="file", target_id=file_id, target_name=row["filename"], detail=f"v{version_num} deleted")
        conn.commit()
    finally:
        conn.close()


@router.patch("/{file_id}/rename")
def rename_file(file_id: int, body: RenameBody, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)
        conn.execute("UPDATE files SET filename = ?, updated_at = datetime('now') WHERE id = ?", (body.filename.strip(), file_id))
        log_action(conn, user["id"], user["username"], "rename", target_type="file", target_id=file_id, target_name=body.filename.strip(), detail=f"{row['filename']} → {body.filename.strip()}")
        conn.commit()
        return {"detail": "Renamed", "filename": body.filename.strip()}
    finally:
        conn.close()


@router.patch("/{file_id}/move")
def move_file(file_id: int, body: MoveBody, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)
        if body.folder_id is not None:
            folder = conn.execute("SELECT * FROM folders WHERE id = ?", (body.folder_id,)).fetchone()
            if not folder:
                raise HTTPException(status_code=404, detail="Target folder not found")
            if folder["project_id"] != row["project_id"]:
                raise HTTPException(status_code=400, detail="Cannot move file across projects")
        conn.execute("UPDATE files SET folder_id = ?, updated_at = datetime('now') WHERE id = ?", (body.folder_id, file_id))
        log_action(conn, user["id"], user["username"], "move", target_type="file", target_id=file_id, target_name=row["filename"], detail=f"moved to folder {body.folder_id}")
        conn.commit()
        return {"detail": "Moved", "folder_id": body.folder_id}
    finally:
        conn.close()


@router.delete("/{file_id}", status_code=200)
def delete_file(file_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM files WHERE id=? AND deleted_at IS NULL", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        _check_file_access(conn, row, user, require_write=True)
        uid = conn.execute("SELECT id FROM users WHERE username=?", (user["username"],)).fetchone()["id"]
        conn.execute("UPDATE files SET deleted_at=datetime('now'), deleted_by=? WHERE id=?", (uid, file_id))
        log_action(conn, user["id"], user["username"], "trash", target_type="file", target_id=file_id, target_name=row["filename"], project_id=row["project_id"])
        conn.commit()
    finally:
        conn.close()
    return {"message": "File moved to trash"}
