"""
CLOTE - routes/auth_routes.py
Registration, login, and current-user endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from auth import get_current_user, hash_password, verify_password, create_access_token
from database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class RegisterBody(BaseModel):
    username: str
    password: str


# ─────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(body: RegisterBody):
    if not body.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (body.username.strip(),)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (body.username.strip(), hash_password(body.password))
        )
        conn.commit()
        return {"detail": "Account created"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Login  (OAuth2PasswordRequestForm — form data)
# ─────────────────────────────────────────────

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (form.username,)
        ).fetchone()
        if not user or not verify_password(form.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = create_access_token({"sub": user["username"]})
        return {"access_token": token, "token_type": "bearer"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Me  — returns current user info (used by client to get user id)
# ─────────────────────────────────────────────

@router.get("/me")
def get_me(user=Depends(get_current_user)):
    """Return the currently authenticated user's id and username."""
    return {
        "id":       user["id"],
        "username": user["username"],
        "created_at": user["created_at"]
    }
