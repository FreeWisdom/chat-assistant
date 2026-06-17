"""Local admin page for bot profiles, styles, knowledge bases, and group bindings."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import config_store


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
REACT_DIST_DIR = BASE_DIR.parent / "admin-ui" / "dist"
REACT_ASSETS_DIR = REACT_DIST_DIR / "assets"

app = FastAPI(title="AI 社群助教管理页")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ADMIN_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if REACT_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_ASSETS_DIR)), name="react-assets")


def require_sync_token(x_admin_token: str | None = Header(default=None)):
    if config.ADMIN_SYNC_TOKEN and x_admin_token != config.ADMIN_SYNC_TOKEN:
        raise HTTPException(status_code=401, detail="同步 token 无效")
    return True


@app.get("/")
def index():
    react_index = REACT_DIST_DIR / "index.html"
    if react_index.exists():
        return FileResponse(react_index)
    return FileResponse(TEMPLATE_DIR / "admin.html")


@app.get("/api/config")
def get_config():
    return {"config": config_store.read_config()}


@app.post("/api/validate")
def validate_config(payload: dict):
    try:
        normalized = config_store.normalize_config(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "errors": config_store.validate_config(normalized), "config": normalized}


@app.post("/api/config")
def save_config(payload: dict):
    try:
        saved = config_store.write_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "config": saved}


@app.get("/api/knowledge/files")
def list_knowledge_files(kb_id: str | None = None):
    return {"files": config_store.list_knowledge_files(kb_id)}


@app.get("/api/backups")
def list_backups():
    return {"backups": config_store.list_backups()}


@app.post("/api/knowledge/upload")
async def upload_knowledge_file(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        content = await file.read()
        saved = config_store.save_knowledge_file(kb_id, file.filename or "upload.txt", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "file": saved}


@app.get("/api/sync/health")
def sync_health(_: bool = Depends(require_sync_token)):
    return {
        "ok": True,
        "service": "ai-ta-bot-local-sync",
        "configKeys": list(config_store.read_config().keys()),
    }


@app.post("/api/sync/apply")
def apply_platform_config(payload: dict, _: bool = Depends(require_sync_token)):
    """平台保存后调用：把平台配置同步到本地 courses.yaml。"""
    config_payload = payload.get("config", payload)
    try:
        saved = config_store.write_config(config_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "平台配置已同步到本地，重启机器人后生效",
        "config": saved,
    }


@app.post("/api/sync/knowledge/upload")
async def sync_knowledge_file(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    _: bool = Depends(require_sync_token),
):
    """平台上传知识库文件到本地项目。"""
    try:
        content = await file.read()
        saved = config_store.save_knowledge_file(kb_id, file.filename or "upload.txt", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "file": saved}


def _stop_bot_processes() -> list[int]:
    """Kill 正在跑的 main.py 进程（排除 admin_app 自己），返回被 kill 的 PID 列表。"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline,processid", "/format:csv"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return []
    killed: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "main.py" not in line or "admin_app" in line:
            continue
        parts = line.split(",")
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            killed.append(pid)
        except Exception:
            pass
    return killed


@app.post("/api/script/restart")
def restart_script():
    """停掉旧 main.py 并启动新进程（detached），日志写入 wxauto_logs/restart_TIMESTAMP.log"""
    main_py = BASE_DIR / "main.py"
    if not main_py.exists():
        raise HTTPException(status_code=404, detail="main.py not found in project root")

    killed = _stop_bot_processes()

    log_dir = BASE_DIR / "wxauto_logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"restart_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_handle = open(log_file, "w", encoding="utf-8")

    creation_flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [sys.executable, str(main_py)],
        cwd=str(BASE_DIR),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags,
        close_fds=True,
        env=env,
    )

    return {
        "ok": True,
        "killed": killed,
        "new_pid": proc.pid,
        "log_file": str(log_file.relative_to(BASE_DIR)).replace("\\", "/"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("admin_app:app", host="127.0.0.1", port=8000, reload=False)
