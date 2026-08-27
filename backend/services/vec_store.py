import asyncio
import struct
import sqlite3
import sqlite_vec
from pathlib import Path
from backend.config import settings


def _get_conn() -> sqlite3.Connection:
    # 长超时：避免与其他写事务争锁时立即报 "database is locked"
    conn = sqlite3.connect(str(settings.db_abs_path), timeout=30)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class VecStore:
    def add(self, chunk_id: int, document_id: int, embedding: list[float]):
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
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM chunk_embeddings WHERE document_id = ?", (document_id,))
            conn.commit()
        finally:
            conn.close()


vec_store = VecStore()


# ---- 异步包装：把同步 sqlite3 调用移出事件循环，避免阻塞/死锁 ----

async def delete_by_document_async(document_id: int):
    await asyncio.to_thread(vec_store.delete_by_document, document_id)


async def bulk_add_async(items: list[tuple[int, int, list[float]]]):
    await asyncio.to_thread(vec_store.bulk_add, items)


async def search_async(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    return await asyncio.to_thread(vec_store.search, query_embedding, top_k)
