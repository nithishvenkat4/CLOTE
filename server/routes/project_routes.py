"""
CLOTE - routes/project_routes.py
Project CRUD + member management routes.

Endpoints:
  POST   /projects/                          — create project
  GET    /projects/                          — list my projects
  GET    /projects/{project_id}              — project detail + members + root contents
  PATCH  /projects/{project_id}/rename       — rename (owner only)
  DELETE /projects/{project_id}             — delete (owner only)

  POST   /projects/{project_id}/members              — invite by username (owner only)
  PATCH  /projects/{project_id}/members/{user_id}    — change role (owner only)
  DELETE /projects/{project_id}/members/{user_id}    — remove member (owner only)
  GET    /projects/{project_id}/members              — list members

  GET    /projects/invitations/pending               — list pending invitations for current user
  POST   /projects/invitations/{invitation_id}/accept  — accept invitation
  POST   /projects/invitations/{invitation_id}/decline — decline invitation
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectRename(BaseModel):
    name: str
    description: Optional[str] = None

class MemberInvite(BaseModel):
    username: str
    role: str = "viewer"   # viewer | editor | owner

class MemberRoleUpdate(BaseModel):
    role: str              # viewer | editor | owner


# ─────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────

VALID_ROLES = {"owner", "editor", "viewer"}

def get_member_role(conn, project_id: int, user_id: int) -> str:
    row = conn.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this project")
    return row["role"]

def require_owner(conn, project_id: int, user_id: int):
    role = get_member_role(conn, project_id, user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the project owner can do this")

def require_editor_or_above(conn, project_id: int, user_id: int):
    role = get_member_role(conn, project_id, user_id)
    if role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot modify project contents")


# ─────────────────────────────────────────────
# Project routes
# ─────────────────────────────────────────────

@router.post("/", status_code=201)
def create_project(body: ProjectCreate, user=Depends(get_current_user)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO projects (name, description, owner_id) VALUES (?, ?, ?)",
            (body.name.strip(), body.description, user["id"])
        )
        project_id = cur.lastrowid
        conn.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, 'owner')",
            (project_id, user["id"])
        )
        conn.commit()
        return {"id": project_id, "name": body.name.strip(), "description": body.description,
                "owner_id": user["id"], "role": "owner"}
    finally:
        conn.close()


@router.get("/")
def list_projects(user=Depends(get_current_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT p.id, p.name, p.description, p.owner_id,
                      pm.role, pm.role as my_role, p.created_at, p.updated_at
               FROM projects p
               JOIN project_members pm ON pm.project_id = p.id
               WHERE pm.user_id = ?
               ORDER BY p.created_at DESC""",
            (user["id"],)
        ).fetchall()
        return {"projects": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/invitations/pending")
def list_pending_invitations(user=Depends(get_current_user)):
    """List all pending invitations for the current user."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT pi.id, pi.project_id, pi.role, pi.created_at,
                      p.name as project_name,
                      u.username as inviter_username
               FROM project_invitations pi
               JOIN projects p ON p.id = pi.project_id
               JOIN users u ON u.id = pi.inviter_id
               WHERE pi.invitee_id = ? AND pi.status = 'pending'
               ORDER BY pi.created_at DESC""",
            (user["id"],)
        ).fetchall()
        return {"invitations": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(invitation_id: int, user=Depends(get_current_user)):
    """Accept a pending invitation."""
    conn = get_db()
    try:
        inv = conn.execute(
            "SELECT * FROM project_invitations WHERE id = ? AND invitee_id = ? AND status = 'pending'",
            (invitation_id, user["id"])
        ).fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Invitation not found or already handled")

        inv = dict(inv)

        # Check not already a member
        existing = conn.execute(
            "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
            (inv["project_id"], user["id"])
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, ?)",
                (inv["project_id"], user["id"], inv["role"])
            )

        conn.execute(
            "UPDATE project_invitations SET status = 'accepted', updated_at = datetime('now') WHERE id = ?",
            (invitation_id,)
        )
        conn.commit()
        return {"detail": "Invitation accepted", "project_id": inv["project_id"], "role": inv["role"]}
    finally:
        conn.close()


@router.post("/invitations/{invitation_id}/decline")
def decline_invitation(invitation_id: int, user=Depends(get_current_user)):
    """Decline a pending invitation."""
    conn = get_db()
    try:
        inv = conn.execute(
            "SELECT id FROM project_invitations WHERE id = ? AND invitee_id = ? AND status = 'pending'",
            (invitation_id, user["id"])
        ).fetchone()
        if not inv:
            raise HTTPException(status_code=404, detail="Invitation not found or already handled")

        conn.execute(
            "UPDATE project_invitations SET status = 'declined', updated_at = datetime('now') WHERE id = ?",
            (invitation_id,)
        )
        conn.commit()
        return {"detail": "Invitation declined"}
    finally:
        conn.close()


@router.get("/{project_id}")
def get_project(project_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        role = get_member_role(conn, project_id, user["id"])
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        members = conn.execute(
            """SELECT u.id, u.username, pm.role, pm.joined_at
               FROM project_members pm JOIN users u ON u.id = pm.user_id
               WHERE pm.project_id = ? ORDER BY pm.joined_at""",
            (project_id,)
        ).fetchall()
        folders = conn.execute(
            "SELECT * FROM folders WHERE project_id = ? AND parent_id IS NULL ORDER BY name",
            (project_id,)
        ).fetchall()
        files = conn.execute(
            "SELECT * FROM files WHERE project_id = ? AND folder_id IS NULL ORDER BY filename",
            (project_id,)
        ).fetchall()
        return {**dict(project), "your_role": role,
                "members": [dict(m) for m in members],
                "folders": [dict(f) for f in folders],
                "files": [dict(f) for f in files]}
    finally:
        conn.close()


@router.patch("/{project_id}/rename")
def rename_project(project_id: int, body: ProjectRename, user=Depends(get_current_user)):
    conn = get_db()
    try:
        require_owner(conn, project_id, user["id"])
        conn.execute(
            "UPDATE projects SET name = ?, description = ?, updated_at = datetime('now') WHERE id = ?",
            (body.name.strip(), body.description, project_id)
        )
        conn.commit()
        return {"detail": "Project updated"}
    finally:
        conn.close()


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        require_owner(conn, project_id, user["id"])
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Member routes
# ─────────────────────────────────────────────

@router.get("/{project_id}/members")
def list_members(project_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        get_member_role(conn, project_id, user["id"])
        rows = conn.execute(
            """SELECT u.id, u.username, pm.role, pm.joined_at
               FROM project_members pm JOIN users u ON u.id = pm.user_id
               WHERE pm.project_id = ? ORDER BY pm.joined_at""",
            (project_id,)
        ).fetchall()
        return {"members": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/{project_id}/members", status_code=201)
def invite_member(project_id: int, body: MemberInvite, user=Depends(get_current_user)):
    """
    Send an invitation to a user by username (owner only).
    Creates a pending invitation; user must accept via /invitations/{id}/accept.
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    conn = get_db()
    try:
        require_owner(conn, project_id, user["id"])

        target = conn.execute(
            "SELECT id, username FROM users WHERE username = ?",
            (body.username.strip(),)
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail=f"User '{body.username}' not found")

        target = dict(target)

        # Cannot invite yourself
        if target["id"] == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot invite yourself")

        # Already a member?
        existing = conn.execute(
            "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, target["id"])
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"'{body.username}' is already a member")

        # Already has a pending invite?
        pending = conn.execute(
            "SELECT id FROM project_invitations WHERE project_id = ? AND invitee_id = ? AND status = 'pending'",
            (project_id, target["id"])
        ).fetchone()
        if pending:
            raise HTTPException(status_code=409, detail=f"'{body.username}' already has a pending invitation")

        conn.execute(
            """INSERT INTO project_invitations (project_id, inviter_id, invitee_id, role, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (project_id, user["id"], target["id"], body.role)
        )
        conn.commit()
        return {"detail": f"Invitation sent to {body.username}", "username": target["username"], "role": body.role}
    finally:
        conn.close()


@router.patch("/{project_id}/members/{target_user_id}")
def change_member_role(project_id: int, target_user_id: int,
                       body: MemberRoleUpdate, user=Depends(get_current_user)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    conn = get_db()
    try:
        require_owner(conn, project_id, user["id"])
        if target_user_id == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        target = conn.execute(
            "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, target_user_id)
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        conn.execute(
            "UPDATE project_members SET role = ? WHERE project_id = ? AND user_id = ?",
            (body.role, project_id, target_user_id)
        )
        conn.commit()
        return {"detail": "Role updated", "role": body.role}
    finally:
        conn.close()


@router.delete("/{project_id}/members/{target_user_id}", status_code=204)
def remove_member(project_id: int, target_user_id: int, user=Depends(get_current_user)):
    conn = get_db()
    try:
        require_owner(conn, project_id, user["id"])
        if target_user_id == user["id"]:
            raise HTTPException(status_code=400,
                                detail="Owner cannot remove themselves. Delete the project instead.")
        result = conn.execute(
            "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, target_user_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Member not found")
        conn.commit()
    finally:
        conn.close()

