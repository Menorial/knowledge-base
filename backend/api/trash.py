"""回收站：查看软删除文档、恢复、彻底删除"""
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
from backend.services.links import schedule_rebuild
from backend.services.tags_usage import recompute_tag_usage
from backend.api.documents import ensure_document_vectors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trash", tags=["trash"])


def _schedule_links_rebuild():
    schedule_rebuild(full=True)


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
    await ensure_document_vectors(doc.id, doc.content_md or "")
    await recompute_tag_usage(session)
    _schedule_links_rebuild()
    return {"code": 0, "msg": "ok"}


async def _purge_doc_files(doc: Document):
    """删除原始文件与剪藏图片目录（无数据库操作）"""
    if doc.file_path:
        full_path = settings.file_storage_abs / Path(doc.file_path).name
        try:
            if full_path.exists():
                full_path.unlink()
                logger.info(f"已删除原始文件: {full_path.name}")
        except Exception as e:
            logger.error(f"删除原始文件失败 {full_path}: {e}")

    clip_dir = settings.file_storage_abs / "clip" / str(doc.id)
    try:
        if clip_dir.exists():
            import shutil
            shutil.rmtree(clip_dir, ignore_errors=True)
            logger.info(f"已清理剪藏图片目录: {clip_dir.name}")
    except Exception as e:
        logger.error(f"清理剪藏图片目录失败: {e}")


async def _purge_doc_db(session: AsyncSession, doc: Document):
    """在 session 事务内清理关联数据并删除记录（不 commit）"""
    await session.execute(text("DELETE FROM document_versions WHERE document_id = :did"), {"did": doc.id})
    await session.execute(text("DELETE FROM document_tags WHERE document_id = :did"), {"did": doc.id})
    await session.execute(text("DELETE FROM chunks WHERE document_id = :did"), {"did": doc.id})
    await session.execute(text("DELETE FROM document_links WHERE from_doc_id = :did OR to_doc_id = :did"), {"did": doc.id})
    await session.delete(doc)


async def _purge_doc_index(doc_id: int):
    """删除 FTS 与向量索引（先提交 session 事务后调用，避免锁竞争）"""
    await fts_delete_async(doc_id)
    await delete_by_document_async(doc_id)


@router.delete("/{doc_id}")
async def purge_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    """彻底删除：移除数据库记录、FTS、向量索引与原始文件"""
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == True)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或未删除")

    await _purge_doc_files(doc)
    await _purge_doc_db(session, doc)
    await session.commit()
    await _purge_doc_index(doc_id)
    await recompute_tag_usage(session)
    return {"code": 0, "msg": "ok"}


@router.post("/batch-restore")
async def batch_restore_documents(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """批量恢复已删除文档"""
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要恢复的文档")
    ids = [int(i) for i in ids if str(i).strip().isdigit()]
    if not ids:
        raise HTTPException(status_code=400, detail="无效的文档 ID")

    result = await session.execute(
        select(Document).where(Document.id.in_(ids), Document.is_deleted == True)
    )
    docs = result.scalars().all()
    if not docs:
        raise HTTPException(status_code=404, detail="所选文档不存在")

    restored_ids: list[int] = []
    for doc in docs:
        doc.is_deleted = False
        doc.deleted_at = None
        restored_ids.append(doc.id)
    await session.commit()

    for doc_id in restored_ids:
        doc = await session.get(Document, doc_id)
        if doc:
            await fts_upsert_async(doc_id, doc.title, doc.content_md or "")
            await ensure_document_vectors(doc_id, doc.content_md or "")

    await recompute_tag_usage(session)
    _schedule_links_rebuild()
    return {"code": 0, "msg": "ok", "restored": len(restored_ids)}


@router.post("/batch-purge")
async def batch_purge_documents(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """批量彻底删除（不可恢复）"""
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的文档")
    ids = [int(i) for i in ids if str(i).strip().isdigit()]
    if not ids:
        raise HTTPException(status_code=400, detail="无效的文档 ID")

    result = await session.execute(
        select(Document).where(Document.id.in_(ids), Document.is_deleted == True)
    )
    docs = result.scalars().all()
    if not docs:
        raise HTTPException(status_code=404, detail="所选文档不存在")

    # 先处理文件与数据库记录，统一提交后再删索引（避免 sqlite3 与 aiosqlite 写锁竞争）
    for doc in docs:
        await _purge_doc_files(doc)
        await _purge_doc_db(session, doc)
    await session.commit()

    for doc in docs:
        await _purge_doc_index(doc.id)

    await recompute_tag_usage(session)
    return {"code": 0, "msg": "ok", "purged": len(docs)}
