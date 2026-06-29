"""Local admin page entry point.

python -m ai_ta_bot.admin_app  # start admin server on port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .admin.routers import config as config_router
from .admin.routers import knowledge as knowledge_router
from .admin.routers import runtime as runtime_router
from .admin.routers import settings as settings_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REACT_DIST_DIR = PROJECT_ROOT / "admin-ui" / "dist"
REACT_ASSETS_DIR = REACT_DIST_DIR / "assets"

app = FastAPI(title="AI 社群助教管理页")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ADMIN_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
if REACT_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_ASSETS_DIR)), name="react-assets")

app.include_router(config_router.router)
app.include_router(knowledge_router.router)
app.include_router(runtime_router.router)
app.include_router(settings_router.router)


@app.get("/")
def index():
    react_index = REACT_DIST_DIR / "index.html"
    if not react_index.exists():
        raise HTTPException(status_code=404, detail="admin-ui 未构建，请先运行: cd admin-ui && npm run build")
    return FileResponse(react_index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_ta_bot.admin_app:app", host="127.0.0.1", port=8000, reload=False)
