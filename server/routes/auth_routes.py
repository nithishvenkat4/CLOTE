"""
CLOTE - routes/auth_routes.py
User registration and login endpoints.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from database import get_db
from auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (body.username,)
        ).fetchone()

        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (body.username.strip(), hash_password(body.password))
        )
        conn.commit()
    finally:
        conn.close()

    return {"message": f"User '{body.username}' registered successfully"}


# ─────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (form.username,)
        ).fetchone()
    finally:
        conn.close()

    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    token = create_access_token(data={"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer"}