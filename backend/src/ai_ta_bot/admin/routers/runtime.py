import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ... import config
from ..services.process_manager import stop_bot, start_bot, PROJECT_ROOT

router = APIRouter(tags=["runtime"])


@router.get("/api/runtime/health")
def runtime_health():
    health_path = Path(config.BOT_HEALTH_PATH)
    if not health_path.is_absolute():
        health_path = PROJECT_ROOT / health_path

    if not health_path.exists():
        return {
            "ok": True,
            "running": False,
            "health": {"status": "not_started"},
        }

    try:
        health = json.loads(health_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"无法读取机器人健康状态: {exc}",
        ) from exc

    return {
        "ok": True,
        "running": health.get("status") == "running",
        "health": health,
    }


@router.post("/api/script/restart")
def restart_script():
    killed = stop_bot()

    try:
        proc = start_bot()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log_file = proc.args[0] if hasattr(proc, "args") else ""

    return {
        "ok": True,
        "killed": killed,
        "new_pid": proc.pid,
        "log_file": str(Path(log_file).relative_to(PROJECT_ROOT)).replace("\\", "/") if log_file else "",
    }
