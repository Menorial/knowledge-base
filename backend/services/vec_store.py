import asyncio
import struct
import sqlite3
import threading
import sqlite_vec
from pathlib import Path
from backend.config import settings

# 进程级写锁：同一 SQLite 文件的所有 sqlite3 写操作串行化，
# 避免多个后台任务（向量化/链接/删除）并发写导致 "database is locked"
db_write_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    # WAL 已在启动时设置；长超时让写操作等待其他事务完成
    conn = sqlite3.connect(str(settings.db_abs_path), timeout=30)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


class VecStore:
    def add(self, chunk_id: int, document_id: int, embedding: list[float]):
        with db_write_lock:
            conn = _get_conn()
            try:
                vec_bytes = struct.pack(f"<{len(embedding)}f", *embedding)
                conn.execute(
                    "INSERT INTO chunk_embeddings(rowid, document_id, embedding) VALUES (?, ?, ?)",
                    (chunk_id, document_id, vec_bytes),
                )
                conn.commit()
            finally:
                conn.close()

    def bulk_add(self, items: list[tuple[int, int, list[float]]]):
        with db_write_lock:
            conn = _get_conn()
            try:
                rows = [(cid, did, struct.pack(f"<{len(emb)}f", *emb)) for cid, did, emb in items]
                conn.executemany(
                    "INSERT INTO chunk_embeddings(rowid, document_id, embedding) VALUES (?, ?, ?)",
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        conn = _get_conn()
        try:
            vec_bytes = struct.pack(f"<{len(query_embedding)}f", *query_embedding)
            cur = conn.execute(
                "SELECT rowid as chunk_id, document_id, distance "
                "FROM chunk_embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (vec_bytes, top_k),
            )
            return [
                {"chunk_id": r[0], "document_id": r[1], "distance": r[2]}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def delete_by_document(self, document_id: int):
        with db_write_lock:
            conn = _get_conn()
            try:
                conn.execute("DELETE FROM chunk_embeddings WHERE document_id = ?", (document_id,))
                conn.commit()
            finally:
                conn.close()


vec_store = VecStore()


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


async def delete_by_document_async(document_id: int):
    await _with_retry(vec_store.delete_by_document, document_id)


async def bulk_add_async(items: list[tuple[int, int, list[float]]]):
    await _with_retry(vec_store.bulk_add, items)


async def search_async(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    return await asyncio.to_thread(vec_store.search, query_embedding, top_k)
