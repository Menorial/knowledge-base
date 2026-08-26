from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from backend.config import settings


def _on_pool_connect(dbapi_connection, connection_record):
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
    await _migrate_add_mode_column()


async def _migrate_add_mode_column():
    async with engine.begin() as conn:
        from sqlalchemy import text
        try:
            await conn.execute(text("SELECT mode FROM conversations LIMIT 1"))
        except Exception:
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN mode VARCHAR(20) DEFAULT 'rag'"))


async def _init_fts_table():
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title,
                content_md,
                tokenize='unicode61'
            )
        """))


async def _init_vec_table():
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
                rowid INTEGER PRIMARY KEY,
                document_id INTEGER,
                embedding float[{settings.VECTOR_DIM}]
            )
        """))
