import asyncio
import sqlite3
import sqlite_vec
from backend.config import settings


def _conn() -> sqlite3.Connection:
    # 长超时：避免与其他写事务争锁时立即报 "database is locked"
    c = sqlite3.connect(str(settings.db_abs_path), timeout=30)
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    return c


def fts_upsert(doc_id: int, title: str, content_md: str):
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
    conn = _conn()
    try:
        conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def fts_rebuild_all():
    """从 documents 表全量重建 FTS 索引"""
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

async def fts_upsert_async(doc_id: int, title: str, content_md: str):
    await asyncio.to_thread(fts_upsert, doc_id, title, content_md)


async def fts_delete_async(doc_id: int):
    await asyncio.to_thread(fts_delete, doc_id)
