from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..services import process_manager

router = APIRouter(tags=["runtime"])


@router.get("/api/runtime/health")
def runtime_health():
    return process_manager.runtime_health()


@router.get("/api/runtime/logs")
def runtime_logs(limit: int = Query(default=200, ge=1, le=1000)):
    return process_manager.runtime_logs(limit)


@router.post("/api/runtime/start")
def start_runtime(payload: dict | None = None):
    result = process_manager.start_bot(
        force=bool((payload or {}).get("force", False)),
    )
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/api/runtime/stop")
def stop_runtime(payload: dict | None = None):
    payload = payload or {}
    result = process_manager.stop_bot(
        force=bool(payload.get("force", False)),
        timeout_seconds=int(payload.get("timeoutSeconds", 8) or 8),
    )
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/api/runtime/restart")
def restart_runtime(payload: dict | None = None):
    result = process_manager.restart_bot(
        force=bool((payload or {}).get("force", False)),
    )
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/api/script/restart")
def restart_script():
    result = process_manager.restart_bot(force=True)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return {
        **result,
        "killed": result.get("stoppedPids", []),
        "new_pid": result.get("pid"),
        "log_file": result.get("logFile", ""),
    }
