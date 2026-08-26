"""系统设置（读写 .env）与备份管理 API"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.config import settings, BASE_DIR
from backend.db.schemas import SettingsUpdate
from backend.services.backup import run_backup, list_backups, delete_backup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


@router.get("/settings")
async def get_settings():
    return {
        "ai_base_url": settings.AI_BASE_URL,
        "ai_model": settings.AI_MODEL,
        "ai_embedding_model": settings.AI_EMBEDDING_MODEL,
        "ai_api_key_set": bool(settings.AI_API_KEY),
        "ai_api_key_masked": _mask_key(settings.AI_API_KEY),
        "vector_dim": settings.VECTOR_DIM,
        "max_file_size": settings.MAX_FILE_SIZE,
        "allowed_extensions": settings.ALLOWED_EXTENSIONS,
        "backup_keep_days": settings.BACKUP_KEEP_DAYS,
    }


@router.put("/settings")
async def update_settings(body: SettingsUpdate):
    """将配置写入 .env 并热更新内存配置（无需重启后端）"""
    env_path = BASE_DIR / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    updates = {
        "AI_BASE_URL": body.ai_base_url,
        "AI_MODEL": body.ai_model,
        "AI_EMBEDDING_MODEL": body.ai_embedding_model,
        "AI_API_KEY": body.ai_api_key,
    }

    updated_keys: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates and updates[key] is not None:
            lines[i] = f"{key}={updates[key]}"
            updated_keys.add(key)

    for key, value in updates.items():
        if value is None or key in updated_keys:
            continue
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 热更新内存配置
    if body.ai_base_url is not None:
        settings.AI_BASE_URL = body.ai_base_url
    if body.ai_model is not None:
        settings.AI_MODEL = body.ai_model
    if body.ai_embedding_model is not None:
        settings.AI_EMBEDDING_MODEL = body.ai_embedding_model
    if body.ai_api_key is not None:
        settings.AI_API_KEY = body.ai_api_key

    # 重建 LLM 客户端；embedding 模型变化时重置本地模型缓存
    from backend.services.llm import llm_service
    llm_service.reload()
    if body.ai_embedding_model is not None:
        from backend.services.embedding import embedding_service
        embedding_service.reset()

    logger.info("设置已更新并热生效")
    return {"code": 0, "msg": "ok"}


@router.post("/backup")
async def backup_now():
    target = await asyncio.to_thread(run_backup)
    if not target:
        raise HTTPException(status_code=500, detail="备份失败，请查看后端日志")
    return {"code": 0, "msg": "ok", "path": target.name}


@router.get("/backups")
async def backups():
    items = await asyncio.to_thread(list_backups)
    return {"code": 0, "msg": "ok", "items": items}


@router.delete("/backups/{name}")
async def remove_backup(name: str):
    ok = await asyncio.to_thread(delete_backup, name)
    if not ok:
        raise HTTPException(status_code=400, detail="备份不存在或路径非法")
    return {"code": 0, "msg": "ok"}
