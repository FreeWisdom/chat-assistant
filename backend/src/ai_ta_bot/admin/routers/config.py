from fastapi import APIRouter, Depends, Header, HTTPException

from ... import config_store

router = APIRouter(tags=["config"])


def require_sync_token(x_admin_token: str | None = Header(default=None)):
    from ... import config

    if config.ADMIN_SYNC_TOKEN and x_admin_token != config.ADMIN_SYNC_TOKEN:
        raise HTTPException(status_code=401, detail="同步 token 无效")
    return True


@router.get("/api/config")
def get_config():
    return {"config": config_store.read_config()}


@router.post("/api/validate")
def validate_config(payload: dict):
    try:
        normalized = config_store.normalize_config(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "errors": config_store.validate_config(normalized), "config": normalized}


@router.post("/api/config")
def save_config(payload: dict):
    try:
        saved = config_store.write_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "config": saved}


@router.get("/api/backups")
def list_backups():
    return {"backups": config_store.list_backups()}


@router.get("/api/sync/health")
def sync_health(_: bool = Depends(require_sync_token)):
    return {
        "ok": True,
        "service": "ai-ta-bot-local-sync",
        "configKeys": list(config_store.read_config().keys()),
    }


@router.post("/api/sync/apply")
def apply_platform_config(payload: dict, _: bool = Depends(require_sync_token)):
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
