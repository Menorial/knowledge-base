"""回收站：查看软删除文档、恢复、彻底删除"""
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.database import get_session, async_session
from backend.db.models import Document
from backend.services.fts_sync import fts_delete_async, fts_upsert_async
from backend.services.vec_store import delete_by_document_async
from backend.services.links import rebuild_all_links

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trash", tags=["trash"])


def _schedule_links_rebuild():
    async def _run():
        try:
            async with async_session() as session:
                await rebuild_all_links(session)
        except Exception as e:
            logger.error(f"链接重建失败: {e}", exc_info=True)
    asyncio.create_task(_run())


@router.get("")
async def list_trash(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document)
        .where(Document.is_deleted == True)
        .order_by(Document.deleted_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "file_type": d.file_type,
            "file_size": d.file_size or 0,
            "word_count": d.word_count or 0,
            "deleted_at": d.deleted_at,
        }
        for d in docs
    ]


@router.post("/{doc_id}/restore")
async def restore_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == True)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc.is_deleted = False
    doc.deleted_at = None
    await session.commit()

    await fts_upsert_async(doc.id, doc.title, doc.content_md or "")
    _schedule_links_rebuild()
    return {"code": 0, "msg": "ok"}


@router.delete("/{doc_id}")
async def purge_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    """彻底删除：移除数据库记录、FTS、向量索引与原始文件"""
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == True)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或未删除")

    if doc.file_path:
        full_path = settings.file_storage_abs / Path(doc.file_path).name
        try:
            if full_path.exists():
                full_path.unlink()
                logger.info(f"已删除原始文件: {full_path.name}")
        except Exception as e:
            logger.error(f"删除原始文件失败 {full_path}: {e}")

    await fts_delete_async(doc_id)
    await delete_by_document_async(doc_id)

    # 显式清理关联数据（外键已开启，双保险）
    await session.execute(text("DELETE FROM document_versions WHERE document_id = :did"), {"did": doc_id})
    await session.execute(text("DELETE FROM document_tags WHERE document_id = :did"), {"did": doc_id})
    await session.execute(text("DELETE FROM chunks WHERE document_id = :did"), {"did": doc_id})
    await session.execute(text("DELETE FROM document_links WHERE from_doc_id = :did OR to_doc_id = :did"), {"did": doc_id})
    await session.delete(doc)
    await session.commit()
    return {"code": 0, "msg": "ok"}
