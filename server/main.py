"""
CLOTE - main.py
FastAPI app entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, APP_VERSION, init_storage
from database import init_db

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://100.119.135.59:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_storage()
    init_db()
    print(f"[CLOTE] Server ready — {APP_NAME} v{APP_VERSION}")


@app.get("/")
def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


from routes.auth_routes    import router as auth_router
from routes.file_routes    import router as file_router
from routes.folder_routes  import router as folder_router
from routes.project_routes import router as project_router
from routes.trash_routes   import router as trash_router
from routes.share_routes   import router as share_router
from routes.bulk_routes    import router as bulk_router
from routes.audit_routes   import router as audit_router

app.include_router(auth_router)
app.include_router(project_router)
app.include_router(file_router)
app.include_router(folder_router)
app.include_router(trash_router)
app.include_router(share_router)
app.include_router(bulk_router)
app.include_router(audit_router)
