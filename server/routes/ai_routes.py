"""
CLOTE - routes/ai_routes.py
AI-powered file summarization and project description.

Supports two backends, auto-detected from env vars:
  1. Ollama (local, preferred)  — set OLLAMA_HOST and OLLAMA_MODEL
  2. Anthropic API (cloud)      — set ANTHROPIC_API_KEY

Ollama takes priority if OLLAMA_HOST is set.

Quick start with Ollama:
  ollama pull llama3.2       # or mistral, phi3, gemma2, etc.
  set OLLAMA_HOST=http://localhost:11434
  set OLLAMA_MODEL=llama3.2
  uvicorn main:app --reload
"""

import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from config import FILES_DIR
from database import get_db
from routes.project_routes import get_member_role

router = APIRouter(prefix="/ai", tags=["AI"])

# ── Backend config ────────────────────────────────────────────────────
# Ollama (local)
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "").rstrip("/")   # e.g. http://localhost:11434
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# Anthropic (cloud fallback)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"

USE_OLLAMA    = bool(OLLAMA_HOST)
USE_ANTHROPIC = bool(ANTHROPIC_API_KEY) and not USE_OLLAMA
AI_READY      = USE_OLLAMA or USE_ANTHROPIC


def _call_ai(system: str, user_msg: str, max_tokens: int = 400) -> str:
    """
    Call either Ollama or Anthropic depending on env config.
    Raises HTTPException on any failure.
    """
    if not AI_READY:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI not configured. Set OLLAMA_HOST (e.g. http://localhost:11434) "
                "or ANTHROPIC_API_KEY in your environment."
            )
        )

    if USE_OLLAMA:
        return _call_ollama(system, user_msg, max_tokens)
    else:
        return _call_anthropic(system, user_msg, max_tokens)


def _call_ollama(system: str, user_msg: str, max_tokens: int) -> str:
    """
    Call local Ollama via its OpenAI-compatible /api/chat endpoint.
    Works with any model you've pulled: llama3.2, mistral, phi3, gemma2, etc.
    """
    url = f"{OLLAMA_HOST}/api/chat"
    try:
        resp = httpx.post(
            url,
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.3},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
            },
            timeout=60.0,   # local models can be slow on first call
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running? Run: ollama serve"
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama timed out. Try a smaller model.")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama error: {resp.text[:200]}")

    data = resp.json()
    return data["message"]["content"].strip()


def _call_anthropic(system: str, user_msg: str, max_tokens: int) -> str:
    """Call Anthropic Claude API (cloud fallback)."""
    try:
        resp = httpx.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",   # cheapest, fastest
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=30.0,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Anthropic API timed out.")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Anthropic error: {resp.text[:200]}")

    return resp.json()["content"][0]["text"].strip()


# ── Health check ──────────────────────────────────────────────────────

@router.get("/status")
def ai_status(user=Depends(get_current_user)):
    """Check which AI backend is active."""
    if USE_OLLAMA:
        # Ping Ollama to confirm it's alive
        try:
            r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            models = [m["name"] for m in r.json().get("models", [])]
            return {
                "backend": "ollama",
                "host": OLLAMA_HOST,
                "active_model": OLLAMA_MODEL,
                "available_models": models,
                "ready": True
            }
        except Exception:
            return {"backend": "ollama", "host": OLLAMA_HOST, "ready": False,
                    "error": "Ollama is not reachable. Run: ollama serve"}
    elif USE_ANTHROPIC:
        return {"backend": "anthropic", "model": "claude-haiku-4-5-20251001", "ready": True}
    else:
        return {"backend": "none", "ready": False,
                "hint": "Set OLLAMA_HOST=http://localhost:11434 or ANTHROPIC_API_KEY"}


# ── File summarizer ───────────────────────────────────────────────────

TEXT_MIMES = {
    "text/plain", "text/markdown", "text/csv", "text/html",
    "application/json", "text/xml", "application/xml",
}
CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c",
    ".go", ".rs", ".sh", ".bash", ".yaml", ".yml", ".toml", ".sql",
    ".json", ".md", ".txt", ".html", ".css", ".php", ".rb", ".swift",
}


@router.post("/files/{file_id}/summarize")
async def summarize_file(file_id: int, user=Depends(get_current_user)):
    """Generate an AI summary of a file's contents."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM files WHERE id=? AND deleted_at IS NULL", (file_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")

        if row["project_id"] is None:
            if row["owner_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            get_member_role(conn, row["project_id"], user["id"])

        mime = row["mime_type"] or ""
        ext  = Path(row["filename"]).suffix.lower()

        if mime not in TEXT_MIMES and ext not in CODE_EXTS and not mime.startswith("text/"):
            raise HTTPException(
                status_code=415,
                detail="Only text and code files can be summarized"
            )

        path = Path(FILES_DIR) / row["stored_name"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not on disk")

        raw = path.read_bytes()[:12000]   # ~12KB is enough context for any local model
        try:
            file_content = raw.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=415, detail="Cannot read file as text")

        summary = _call_ai(
            system=(
                "You are a concise technical assistant. Summarize the given file in 2-4 sentences. "
                "Describe what it does or contains, its structure, and any notable details. "
                "Be direct — no preamble, no 'This file is...' opener."
            ),
            user_msg=f"File: {row['filename']}\n\n```\n{file_content}\n```",
            max_tokens=300,
        )
        return {"summary": summary, "filename": row["filename"], "backend": "ollama" if USE_OLLAMA else "anthropic"}
    finally:
        conn.close()


# ── Project description generator ────────────────────────────────────

class ProjectDescBody(BaseModel):
    project_name: str
    existing_description: Optional[str] = None
    file_names: list[str] = []


@router.post("/projects/describe")
async def describe_project(body: ProjectDescBody, user=Depends(get_current_user)):
    """Generate an AI description for a project."""
    context = f"Project name: {body.project_name}\n"
    if body.existing_description and body.existing_description != "No description yet.":
        context += f"Current description: {body.existing_description}\n"
    if body.file_names:
        context += f"Files: {', '.join(body.file_names[:30])}\n"

    description = _call_ai(
        system=(
            "You write short, professional project descriptions for a self-hosted file manager. "
            "Write 1-2 sentences only. No bullet points. No markdown. "
            "Make it clear and purposeful."
        ),
        user_msg=f"{context}\nWrite a project description.",
        max_tokens=100,
    )
    return {"description": description, "backend": "ollama" if USE_OLLAMA else "anthropic"}
