from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from ... import config_store

router = APIRouter(tags=["knowledge"])


@router.get("/api/knowledge/files")
def list_knowledge_files(kb_id: str | None = None):
    return {"files": config_store.list_knowledge_files(kb_id)}


@router.post("/api/knowledge/upload")
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


@router.post("/api/sync/knowledge/upload")
async def sync_knowledge_file(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None),
):
    from .config import require_sync_token

    require_sync_token(x_admin_token)
    try:
        content = await file.read()
        saved = config_store.save_knowledge_file(kb_id, file.filename or "upload.txt", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "file": saved}
