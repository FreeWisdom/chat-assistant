from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..services.process_manager import stop_bot, start_bot, PROJECT_ROOT

router = APIRouter(tags=["runtime"])


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
