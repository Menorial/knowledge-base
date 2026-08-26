from contextlib import asynccontextmanager
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.db.database import init_db
from backend.api import documents, search, chat, tags
from backend.api import stats
from backend.api import system, trash


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info(f"数据库初始化完成: {settings.db_abs_path}")
    logger.info(f"文件存储目录: {settings.file_storage_abs}")
    logger.info(f"AI 模型: {settings.AI_MODEL} | Embedding: {settings.AI_EMBEDDING_MODEL}")

    # 启动时后台执行一次自动备份（不阻塞启动）
    try:
        from backend.services.backup import run_backup
        threading.Thread(target=run_backup, daemon=True).start()
    except Exception as e:
        logger.warning(f"自动备份任务启动失败: {e}")

    # 后台预加载 embedding 模型（有 10 秒硬超时，不会卡启）
    if settings.AI_API_KEY or settings.AI_EMBEDDING_MODEL.strip().lower() == "local":
        import concurrent.futures
        from backend.services.embedding import embedding_service
        def _try_load():
            try:
                embedding_service._lazy_load()
            except Exception as e:
                logger.warning(f"Embedding 模型预加载失败: {e}")
                logger.warning(f"提示: 如需向量检索功能，请设置 HF_ENDPOINT=https://hf-mirror.com 或下载模型到本地")
        threading.Thread(target=_try_load, daemon=True).start()

    yield


app = FastAPI(title="个人知识库", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(tags.router)
app.include_router(stats.router)
app.include_router(system.router)
app.include_router(trash.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
