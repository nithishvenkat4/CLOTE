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
# CORS — allow Person B (React client) to connect
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this once you know Person B's IP
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
    init_db()
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

app.include_router(auth_router)
app.include_router(file_router)
app.include_router(folder_router)
