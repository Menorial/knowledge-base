from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from backend.config import settings


def _on_pool_connect(dbapi_connection, connection_record):
    try:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
    try:
        dbapi_connection.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(dbapi_connection)
    except Exception:
        pass


engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_abs_path}",
    echo=False,
    future=True,
)


event.listen(engine.sync_engine.pool, "connect", _on_pool_connect)


async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        from . import models
        await conn.run_sync(Base.metadata.create_all)

    await _init_fts_table()
    await _init_vec_table()
    await _verify_vec_dim()
    await _migrate_add_mode_column()
    await _migrate_add_source_url()


async def _migrate_add_source_url():
    """旧库补 documents.source_url 列（网页剪藏）"""
    async with engine.begin() as conn:
        from sqlalchemy import text
        try:
            await conn.execute(text("SELECT source_url FROM documents LIMIT 1"))
        except Exception:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN source_url VARCHAR(1000)"))


async def _verify_vec_dim():
    """校验向量表维度与配置一致；不一致时重建（需重新索引）"""
    import logging
    import sqlite3
    import sqlite_vec

    logger = logging.getLogger("db")

    conn = sqlite3.connect(str(settings.db_abs_path))
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        try:
            row = conn.execute(
                "SELECT vec_length(embedding) FROM chunk_embeddings LIMIT 1"
            ).fetchone()
        except Exception:
            return

        if row is None:
            return
        actual = row[0]
        if actual == settings.VECTOR_DIM:
            return

        logger.warning(
            f"向量表维度({actual}) 与配置 VECTOR_DIM({settings.VECTOR_DIM}) 不一致，"
            f"正在重建向量表，请在文档管理页执行「重建索引」"
        )
        conn.execute("DROP TABLE IF EXISTS chunk_embeddings")
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
                rowid INTEGER PRIMARY KEY,
                document_id INTEGER,
                embedding float[{settings.VECTOR_DIM}]
            )
        """)
        conn.commit()
    finally:
        conn.close()


async def _migrate_add_mode_column():
    async with engine.begin() as conn:
        from sqlalchemy import text
        try:
            await conn.execute(text("SELECT mode FROM conversations LIMIT 1"))
        except Exception:
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN mode VARCHAR(20) DEFAULT 'rag'"))


async def _init_fts_table():
    """FTS5 全文索引。

    使用 trigram 分词器：中文按 3 字滑动窗口索引，天然支持子串匹配
    （unicode61 会把整段中文当作一个 token，导致词位于段落中间时搜不到）。
    检测到旧版 unicode61 索引时自动重建并回填。
    """
    import sqlite3
    conn = sqlite3.connect(str(settings.db_abs_path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone()
        sql = row[0] if row else ""
        if "trigram" in sql:
            return
        conn.execute("DROP TABLE IF EXISTS documents_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                title,
                content_md,
                tokenize='trigram'
            )
        """)
        # 全量回填（与 fts_sync.fts_rebuild_all 逻辑一致）
        conn.execute("""
            INSERT INTO documents_fts(rowid, title, content_md)
            SELECT id, title, content_md FROM documents
            WHERE is_deleted = 0 AND content_md IS NOT NULL
        """)
        conn.commit()
    finally:
        conn.close()


async def _init_vec_table():
    """vec0 虚拟表必须用原生 sqlite3 连接创建：
    aiosqlite 代理连接上 enable_load_extension 不可用，会导致 'no such module: vec0'。
    （向量检索走 services/vec_store.py 的原生连接，不受影响）"""
    import sqlite3
    import sqlite_vec
    conn = sqlite3.connect(str(settings.db_abs_path))
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
                rowid INTEGER PRIMARY KEY,
                document_id INTEGER,
                embedding float[{settings.VECTOR_DIM}]
            )
        """)
        conn.commit()
    finally:
        conn.close()
