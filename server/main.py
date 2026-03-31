"""
CLOTE - main.py
FastAPI app entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, APP_VERSION, init_storage
from database import init_db

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(title=APP_NAME, version=APP_VERSION)

# ─────────────────────────────────────────────
# CORS
# During development: allow all origins.
# For Tailscale (Phase 5): replace "*" with your Tailscale IPs.
# Example:
#   allow_origins=["http://100.x.x.x:3000", "http://100.x.x.y:3000"]
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_storage()
    init_db()   # also runs safe column migrations automatically
    print(f"[CLOTE] Server ready — {APP_NAME} v{APP_VERSION}")

# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ─────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────

from routes.auth_routes import router as auth_router
from routes.file_routes import router as file_router
from routes.folder_routes import router as folder_router
from routes.project_routes import router as project_router

app.include_router(auth_router)
app.include_router(project_router)   # /projects — must be before file/folder so helpers are importable
app.include_router(file_router)
app.include_router(folder_router)
