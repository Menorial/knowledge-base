import asyncio
import logging
import os
import threading
import concurrent.futures
import numpy as np

# 默认使用国内镜像（用户也可通过环境变量覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from backend.config import settings

logger = logging.getLogger(__name__)

_EMBED_TIMEOUT_SEC = 10


def embedding_available() -> bool:
    """本地 BGE 模型不需要 API Key；API 型 embedding 需要 Key"""
    return settings.AI_EMBEDDING_MODEL.strip().lower() == "local" or bool(settings.AI_API_KEY)


class EmbeddingService:
    def __init__(self):
        self._model = None
        self._load_error = None
        self._loading = False
        self._load_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _lazy_load(self):
        if self._model is not None:
            return
        if self._load_error:
            raise RuntimeError(f"Embedding 模型加载失败: {self._load_error}")
        if self._loading:
            raise RuntimeError("Embedding 模型正在加载中，请稍后再试")

        with self._load_lock:
            if self._model is not None:
                return
            if self._load_error:
                raise RuntimeError(f"Embedding 模型加载失败: {self._load_error}")
            if self._loading:
                raise RuntimeError("Embedding 模型正在加载中，请稍后再试")
            self._loading = True

            from sentence_transformers import SentenceTransformer

            # 优先用魔搭（modelscope）的本地缓存（国内网络友好）
            modelscope_cache = os.path.expanduser(
                r"~/.cache/modelscope/models/BAAI--bge-small-zh-v1.5/snapshots/master"
            )
            if os.path.isdir(modelscope_cache):
                logger.info(f"使用 modelscope 本地缓存: {modelscope_cache}")
                self._model = SentenceTransformer(modelscope_cache)
                self._loading = False
                return

            # 再试 huggingface 本地缓存
            hf_local_only = os.environ.get("BGE_OFFLINE", "0") == "1"
            try:
                self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5", local_files_only=True)
                logger.info("Loaded from local HF cache")
                self._loading = False
                return
            except Exception:
                pass

            # 都没有 → 在线下载（有 10 秒硬超时）
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "10")
            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")

            future = self._executor.submit(self._do_load, "BAAI/bge-small-zh-v1.5")
            try:
                future.result(timeout=_EMBED_TIMEOUT_SEC)
            except concurrent.futures.TimeoutError:
                self._load_error = "模型加载超时（网络不通？）"
                future.cancel()
                self._loading = False
                raise RuntimeError(
                    f"Embedding 模型加载超时（{_EMBED_TIMEOUT_SEC}秒）。"
                    f"这台机器可能无法访问 huggingface。"
                )
            except Exception as e:
                self._load_error = str(e)
                self._loading = False
                raise RuntimeError(f"Embedding 模型加载失败: {e}")
            self._loading = False

    def _do_load(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        logger.info(f"Loaded {model_name}")

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        self._lazy_load()
        clean = [t[:2048] for t in texts]
        vecs = self._model.encode(clean, normalize_embeddings=True, show_progress_bar=False)
        return vecs.astype(np.float32).tolist()

    async def get_embedding(self, text: str) -> list[float]:
        return (await self.batch_embed([text]))[0]

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        result = await asyncio.to_thread(self._encode_sync, texts)
        if result:
            logger.info(f"embed {len(texts)} texts, dim={len(result[0])}")
        return result

    def reset(self):
        self._model = None
        self._load_error = None

    async def close(self):
        self._model = None
        self._executor.shutdown(wait=False)


embedding_service = EmbeddingService()
