import asyncio
import sqlite3
import sqlite_vec
from backend.config import settings
from .vec_store import db_write_lock


def _conn() -> sqlite3.Connection:
    # WAL 已在启动时设置；长超时让写操作等待其他事务完成
    c = sqlite3.connect(str(settings.db_abs_path), timeout=30)
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    return c


def fts_upsert(doc_id: int, title: str, content_md: str):
    with db_write_lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO documents_fts(rowid, title, content_md) VALUES (?, ?, ?)",
                (doc_id, title or "", content_md or ""),
            )
            conn.commit()
        finally:
            conn.close()


def fts_delete(doc_id: int):
    with db_write_lock:
        conn = _conn()
        try:
            conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            conn.commit()
        finally:
            conn.close()


def fts_rebuild_all():
    """从 documents 表全量重建 FTS 索引"""
    with db_write_lock:
        conn = _conn()
        try:
            conn.execute("DELETE FROM documents_fts")
            conn.execute(
                """
                INSERT INTO documents_fts(rowid, title, content_md)
                SELECT id, title, content_md FROM documents
                WHERE is_deleted = 0 AND content_md IS NOT NULL
                """
            )
            conn.commit()
        finally:
            conn.close()


# ---- 异步包装：把同步 sqlite3 调用移出事件循环，避免阻塞/死锁 ----

async def _with_retry(fn, *args, retries: int = 4):
    """执行写操作；遇 "database is locked" 短暂等待后重试"""
    import sqlite3 as _sqlite3
    for attempt in range(retries):
        try:
            await asyncio.to_thread(fn, *args)
            return
        except _sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise


async def fts_upsert_async(doc_id: int, title: str, content_md: str):
    await _with_retry(fts_upsert, doc_id, title, content_md)


async def fts_delete_async(doc_id: int):
    await _with_retry(fts_delete, doc_id)
