"""
CLOTE - routes/auth_routes.py
Registration, login, current-user, OTP, forgot/reset password, storage.
"""

import os
import random
import smtplib
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional

from auth import get_current_user, hash_password, verify_password, create_access_token
from routes.audit_routes import log_action
from database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────
# SMTP config — update these with your details
# Use a Gmail account with an App Password
# ─────────────────────────────────────────────

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("CLOTE_SMTP_USER", "")   # set via env var or update here
SMTP_PASS = os.getenv("CLOTE_SMTP_PASS", "")   # Gmail App Password
OTP_EXPIRE_MINUTES = 10

SMTP_CONFIGURED = bool(SMTP_USER and SMTP_PASS and "@" in SMTP_USER)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, to, msg.as_string())


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _expires():
    return (datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class RegisterBody(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    otp: Optional[str] = None      # required when email is provided
    dry_run: Optional[bool] = False  # just validate, don't create


class ForgotPasswordBody(BaseModel):
    email: str


class VerifyOTPBody(BaseModel):
    email: str
    otp: str
    purpose: str   # "register" or "reset"


class ResetPasswordBody(BaseModel):
    email: str
    otp: str
    new_password: str


# ─────────────────────────────────────────────
# Send OTP for registration
# ─────────────────────────────────────────────

class RegisterOTPBody(BaseModel):
    email: str

@router.post("/register-otp", status_code=200)
def send_register_otp(body: RegisterOTPBody):
    """Send OTP to email before account creation."""
    if not SMTP_CONFIGURED:
        raise HTTPException(status_code=503, detail="Email service not configured on this server.")
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (body.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        otp = _generate_otp()
        conn.execute(
            "INSERT INTO otps (email, otp_hash, purpose, expires_at) VALUES (?,?,?,?)",
            (body.email, _hash_otp(otp), "register", _expires())
        )
        conn.commit()
        try:
            _send_email(
                body.email,
                "CLOTE — Email Verification OTP",
                f"Your registration OTP is: {otp}\n\nExpires in {OTP_EXPIRE_MINUTES} minutes."
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP config.")
        return {"detail": "OTP sent to your email"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(body: RegisterBody):
    if not body.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    # Password complexity rules
    pwd = body.password
    if len(pwd) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not any(c.isupper() for c in pwd):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(c.islower() for c in pwd):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in pwd):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in pwd):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character (!@#$%^&* etc.)")

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username=?", (body.username.strip(),)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        # Email is optional — saved as-is for password reset later, no OTP required at registration

        if body.dry_run:
            return {"detail": "OK"}

        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            (body.username.strip(), body.email or None, hash_password(body.password))
        )
        log_action(conn, cur.lastrowid, body.username.strip(), "register", detail="account created")
        conn.commit()
        return {"detail": "Account created"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (form.username,)
        ).fetchone()
        if not user or not verify_password(form.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = create_access_token({"sub": user["username"]})
        log_action(conn, user["id"], user["username"], "login", detail="login")
        conn.commit()
        return {"access_token": token, "token_type": "bearer"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Me
# ─────────────────────────────────────────────

@router.get("/me")
def get_me(user=Depends(get_current_user)):
    u = dict(user)
    return {
        "id":         u["id"],
        "username":   u["username"],
        "email":      u.get("email"),
        "created_at": u["created_at"]
    }


# ─────────────────────────────────────────────
# Storage stats
# ─────────────────────────────────────────────

@router.get("/me/storage")
def get_storage(user=Depends(get_current_user)):
    conn = get_db()
    try:
        personal = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(size_bytes),0) as used
               FROM files WHERE owner_id=? AND project_id IS NULL AND deleted_at IS NULL""",
            (user["id"],)
        ).fetchone()

        projects = conn.execute(
            """SELECT p.id, p.name,
                      COUNT(f.id) as file_count,
                      COALESCE(SUM(f.size_bytes),0) as used
               FROM projects p
               JOIN project_members pm ON pm.project_id=p.id AND pm.user_id=?
               LEFT JOIN files f ON f.project_id=p.id AND f.deleted_at IS NULL
               GROUP BY p.id""",
            (user["id"],)
        ).fetchall()

        trash = conn.execute(
            """SELECT COUNT(*) as count, COALESCE(SUM(size_bytes),0) as used
               FROM files WHERE owner_id=? AND deleted_at IS NOT NULL""",
            (user["id"],)
        ).fetchone()

        return {
            "personal": {"file_count": personal["count"], "used_bytes": personal["used"]},
            "trash":    {"file_count": trash["count"],    "used_bytes": trash["used"]},
            "projects": [dict(p) for p in projects]
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Forgot password — send OTP to email
# ─────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordBody):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email=?", (body.email,)
        ).fetchone()
        if not user:
            # Don't reveal whether email exists
            return {"detail": "If that email is registered, an OTP has been sent"}

        otp = _generate_otp()
        conn.execute(
            """INSERT INTO otps (email, otp_hash, purpose, expires_at)
               VALUES (?,?,?,?)""",
            (body.email, _hash_otp(otp), "reset", _expires())
        )
        conn.commit()

        try:
            if not SMTP_CONFIGURED:
                raise HTTPException(
                    status_code=503,
                    detail="Email service not configured. Contact the server admin."
                )
            _send_email(
                body.email,
                "CLOTE — Password Reset OTP",
                f"Your OTP is: {otp}\n\nExpires in {OTP_EXPIRE_MINUTES} minutes.\nIgnore if you didn't request this."
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP config.")

        return {"detail": "If that email is registered, an OTP has been sent"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Verify OTP
# ─────────────────────────────────────────────

@router.post("/verify-otp")
def verify_otp(body: VerifyOTPBody):
    conn = get_db()
    try:
        record = conn.execute(
            """SELECT * FROM otps
               WHERE email=? AND purpose=? AND used=0
               ORDER BY created_at DESC LIMIT 1""",
            (body.email, body.purpose)
        ).fetchone()

        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")

        if datetime.utcnow() > datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S"):
            raise HTTPException(status_code=400, detail="OTP expired")

        if record["otp_hash"] != _hash_otp(body.otp):
            raise HTTPException(status_code=400, detail="Incorrect OTP")

        return {"detail": "OTP verified"}
    finally:
        conn.close()


# ─────────────────────────────────────────────
# Reset password
# ─────────────────────────────────────────────

@router.post("/reset-password")
def reset_password(body: ResetPasswordBody):
    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    conn = get_db()
    try:
        record = conn.execute(
            """SELECT * FROM otps
               WHERE email=? AND purpose='reset' AND used=0
               ORDER BY created_at DESC LIMIT 1""",
            (body.email,)
        ).fetchone()

        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")

        if datetime.utcnow() > datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S"):
            raise HTTPException(status_code=400, detail="OTP expired")

        if record["otp_hash"] != _hash_otp(body.otp):
            raise HTTPException(status_code=400, detail="Incorrect OTP")

        conn.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (hash_password(body.new_password), body.email)
        )
        conn.execute(
            "UPDATE otps SET used=1 WHERE id=?", (record["id"],)
        )
        conn.commit()
        return {"detail": "Password reset successful"}
    finally:
        conn.close()
