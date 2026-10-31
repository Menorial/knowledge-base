from contextlib import asynccontextmanager
import logging
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.db.database import init_db
from backend.api import documents, search, chat, tags
from backend.api import stats
from backend.api import system, trash, graph


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

    # 启动时后台初始化双向链接（旧库升级后自动补建）
    try:
        import asyncio as _asyncio
        from backend.db.database import async_session
        from backend.services.links import rebuild_all_links

        async def _init_links():
            try:
                async with async_session() as session:
                    await rebuild_all_links(session)
            except Exception as e:
                logger.warning(f"启动链接初始化失败: {e}")

            # 校正历史数据里可能失真的标签计数（冗余字段，靠增量维护容易漂移）
            try:
                from backend.services.tags_usage import recompute_tag_usage

                async with async_session() as session:
                    await recompute_tag_usage(session)
            except Exception as e:
                logger.warning(f"标签计数校正失败: {e}")

        _asyncio.create_task(_init_links())
    except Exception as e:
        logger.warning(f"链接初始化任务启动失败: {e}")

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


# ---- CORS：按路径放行 ----
# 除了本地前端，其余跨域来源默认不放行；唯一例外是网页剪藏接口 ——
# 书签小工具会从任意网站直接 POST 过来，收窄来源会让这个功能直接失效。
LOCAL_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
CROSS_ORIGIN_PATHS = {"/api/documents/clip"}


class ScopedCORSMiddleware:
    """按路径放行的 CORS 中间件。

    - /api/documents/clip：允许任意来源（书签小工具）
    - 其余接口：只允许本地前端来源
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        origin = headers.get("origin", "")
        allowed = origin in LOCAL_ORIGINS or scope["path"] in CROSS_ORIGIN_PATHS

        # 预检请求
        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            if not allowed:
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-length", b"0")],
                })
                await send({"type": "http.response.body", "body": b""})
                return
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS"),
                    (
                        b"access-control-allow-headers",
                        headers.get("access-control-request-headers", "*").encode("latin-1"),
                    ),
                    (b"access-control-max-age", b"600"),
                    (b"vary", b"Origin"),
                    (b"content-length", b"0"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        if not allowed or not origin:
            await self.app(scope, receive, send)
            return

        async def _send_with_cors(message):
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": list(message.get("headers", [])) + [
                        (b"access-control-allow-origin", origin.encode("latin-1")),
                        (b"vary", b"Origin"),
                    ],
                }
            await send(message)

        await self.app(scope, receive, _send_with_cors)


app = FastAPI(title="个人知识库", version="1.0.0", lifespan=lifespan)

# 剪藏图片等静态资源（文件名为 uuid 随机名，直接暴露安全）
app.mount("/files", StaticFiles(directory=str(settings.file_storage_abs)), name="files")

app.add_middleware(ScopedCORSMiddleware)

app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(tags.router)
app.include_router(stats.router)
app.include_router(system.router)
app.include_router(trash.router)
app.include_router(graph.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
