"""
CLOTE - routes/audit_routes.py
Audit log recording helper + GET endpoints.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/audit", tags=["Audit"])


def log_action(conn, user_id: int, username: str, action: str,
               target_type: str = None, target_id: int = None,
               target_name: str = None, project_id: int = None,
               detail: str = None, ip_address: str = None):
    """Call this from any route to record an audit event."""
    conn.execute(
        """INSERT INTO audit_log
           (user_id, username, action, target_type, target_id, target_name,
            project_id, detail, ip_address)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, username, action, target_type, target_id, target_name,
         project_id, detail, ip_address)
    )


@router.get("/")
def get_audit_log(
    limit: int = Query(50, le=200),
    offset: int = 0,
    action: Optional[str] = None,
    project_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    conn = get_db()
    try:
        uid = user["id"]
        filters = ["(user_id=? OR project_id IN (SELECT project_id FROM project_members WHERE user_id=?))"]
        params: list = [uid, uid]

        if action:
            filters.append("action=?")
            params.append(action)
        if project_id is not None:
            filters.append("project_id=?")
            params.append(project_id)

        where = " AND ".join(filters)
        rows = conn.execute(
            f"SELECT * FROM audit_log WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset)
        ).fetchall()
        return {"logs": [dict(r) for r in rows]}
    finally:
        conn.close()
