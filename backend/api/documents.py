import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.db.database import get_session, async_session
from backend.db.models import Document, Chunk, DocumentVersion
from backend.db.schemas import DocumentResponse, DocumentListResponse, DocumentPreviewResponse, DocumentUpdate
from backend.utils.security import validate_file, safe_save_filename, safe_store_path
from backend.services.parser import parse_document, ParseError
from backend.services.chunker import chunk_markdown
from backend.services.embedding import embedding_service
from backend.services.vec_store import vec_store
from backend.services.fts_sync import fts_upsert, fts_delete

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _doc_to_response(doc: Document, tags: list[str] | None = None) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        file_path=doc.file_path,
        content_md=None,
        file_type=doc.file_type,
        file_size=doc.file_size or 0,
        parse_status=doc.parse_status,
        summary=doc.summary,
        word_count=doc.word_count or 0,
        tags=tags if tags is not None else [],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _bg_vectorize(doc_id: int, content_md: str):
    """后台向量化：自己管理 session，上传接口可立即返回"""
    try:
        chunks = chunk_markdown(content_md)
        vec_store.delete_by_document(doc_id)

        async with async_session() as session:
            await session.execute(text("DELETE FROM chunks WHERE document_id = :did"), {"did": doc_id})
            await session.commit()

            if not chunks:
                return

            chunk_ids = []
            async with session.begin():
                for c in chunks:
                    ck = Chunk(
                        document_id=doc_id,
                        chunk_index=c.index,
                        content=c.content,
                        section_path=c.section_path,
                        token_count=c.token_count,
                    )
                    session.add(ck)
                    await session.flush()
                    chunk_ids.append(ck.id)

            embeddings = await embedding_service.batch_embed([c.content for c in chunks])
            vec_store.bulk_add(list(zip(chunk_ids, [doc_id] * len(chunks), embeddings)))

            # 更新文档状态
            doc = await session.get(Document, doc_id)
            if doc:
                doc.parse_status = "success"
                await session.commit()

        logger.info(f"文档 {doc_id} 向量化完成, {len(chunks)} 个片段")
    except Exception as e:
        logger.error(f"向量化失败 {doc_id}: {e}", exc_info=True)


async def _do_chunk_and_vectorize(session: AsyncSession, doc_id: int, content_md: str):
    """给 reparse/reindex 用的同步版本"""
    chunks = chunk_markdown(content_md)

    vec_store.delete_by_document(doc_id)
    await session.execute(text("DELETE FROM chunks WHERE document_id = :did"), {"did": doc_id})
    await session.commit()

    if not chunks:
        return 0

    chunk_ids = []
    async with session.begin():
        for c in chunks:
            ck = Chunk(
                document_id=doc_id,
                chunk_index=c.index,
                content=c.content,
                section_path=c.section_path,
                token_count=c.token_count,
            )
            session.add(ck)
            await session.flush()
            chunk_ids.append(ck.id)

    embeddings = await embedding_service.batch_embed([c.content for c in chunks])
    vec_store.bulk_add(list(zip(chunk_ids, [doc_id] * len(chunks), embeddings)))

    return len(chunks)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    file_bytes = await file.read()
    try:
        validate_file(file.filename, len(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    safe_name, ext = safe_save_filename(file.filename)
    store_path = safe_store_path(safe_name)
    store_path.write_bytes(file_bytes)

    title = Path(file.filename).stem
    doc = Document(
        title=title,
        file_path=f"files/{safe_name}",
        file_type=ext.lstrip("."),
        file_size=len(file_bytes),
        parse_status="processing",
    )

    md_content = ""
    parse_status = "success"
    try:
        md_content, parse_status = parse_document(str(store_path), ext)
    except ParseError as e:
        parse_status = "failed"
        logger.error(f"解析失败: {e}")
    except Exception as e:
        parse_status = "failed"
        logger.error(f"上传处理失败: {e}", exc_info=True)

    doc.content_md = md_content
    doc.parse_status = parse_status
    doc.word_count = len(md_content)

    async with session.begin():
        session.add(doc)
        await session.flush()
        doc_id = doc.id

    async with session.begin():
        session.add(DocumentVersion(
            document_id=doc_id,
            content_md=md_content,
            version_note="初始版本",
        ))

    fts_upsert(doc_id, title, md_content)

    if md_content and parse_status == "success" and settings.AI_API_KEY:
        asyncio.create_task(_bg_vectorize(doc_id, md_content))

    return _doc_to_response(doc)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    count_stmt = select(func.count()).select_from(Document).where(Document.is_deleted == False)
    list_stmt = select(Document).where(Document.is_deleted == False)

    if search:
        count_stmt = count_stmt.where(Document.title.ilike(f"%{search}%"))
        list_stmt = list_stmt.where(Document.title.ilike(f"%{search}%"))

    list_stmt = (
        list_stmt.options(selectinload(Document.tags))
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    docs_result = await session.execute(list_stmt)
    docs = docs_result.scalars().all()

    return DocumentListResponse(total=total, items=[_doc_to_response(d) for d in docs])


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False).options(selectinload(Document.tags))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _doc_to_response(doc)


@router.get("/{doc_id}/preview", response_model=DocumentPreviewResponse)
async def preview_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocumentPreviewResponse(
        id=doc.id,
        title=doc.title,
        content_md=doc.content_md,
        parse_status=doc.parse_status,
        file_type=doc.file_type,
    )


@router.get("/{doc_id}/raw")
async def download_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    from fastapi.responses import FileResponse

    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="原始文件不存在")

    full_path = settings.file_storage_abs / Path(doc.file_path).name
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="文件丢失")

    return FileResponse(str(full_path), filename=f"{doc.title}.{doc.file_type}")


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    body: DocumentUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if body.title is not None:
        doc.title = body.title

    if body.content_md is not None and body.content_md != doc.content_md:
        doc.content_md = body.content_md
        doc.word_count = len(body.content_md)
        doc.updated_at = datetime.utcnow()
        session.add(DocumentVersion(
            document_id=doc.id,
            content_md=body.content_md,
            version_note="自动保存",
        ))

    await session.commit()
    await session.refresh(doc)

    fts_upsert(doc.id, doc.title, doc.content_md)

    if body.content_md is not None and body.content_md != doc.content_md and settings.AI_API_KEY:
        try:
            await _do_chunk_and_vectorize(session, doc.id, body.content_md)
        except Exception as e:
            logger.error(f"更新后向量化失败 {doc.id}: {e}", exc_info=True)

    result = await session.execute(
        select(Document).where(Document.id == doc_id).options(selectinload(Document.tags))
    )
    doc = result.scalar_one()
    return _doc_to_response(doc)


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc.is_deleted = True
    doc.deleted_at = datetime.utcnow()
    await session.commit()

    fts_delete(doc_id)
    vec_store.delete_by_document(doc_id)

    return {"code": 0, "msg": "ok"}


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

    fts_upsert(doc.id, doc.title, doc.content_md or "")

    return {"code": 0, "msg": "ok"}


@router.post("/{doc_id}/reparse")
async def reparse_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="文档或原始文件不存在")

    full_path = settings.file_storage_abs / Path(doc.file_path).name
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="原始文件丢失")

    doc.parse_status = "processing"
    await session.commit()

    try:
        ext = f".{doc.file_type}" if doc.file_type else ".md"
        md_content, status = parse_document(str(full_path), ext)
        doc.content_md = md_content
        doc.parse_status = status
        doc.word_count = len(md_content)

        if settings.AI_API_KEY and md_content:
            await _do_chunk_and_vectorize(session, doc.id, md_content)

        session.add(DocumentVersion(
            document_id=doc.id,
            content_md=md_content,
            version_note="重新解析",
        ))
    except ParseError as e:
        doc.parse_status = "failed"
        raise HTTPException(status_code=500, detail=str(e))

    await session.commit()

    fts_upsert(doc.id, doc.title, doc.content_md or "")

    return {"code": 0, "msg": "ok"}


@router.post("/{doc_id}/reindex")
async def reindex_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    if not settings.AI_API_KEY:
        raise HTTPException(status_code=400, detail="AI_API_KEY 未配置")

    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc.content_md:
        raise HTTPException(status_code=400, detail="文档无可索引内容")

    try:
        cn = await _do_chunk_and_vectorize(session, doc.id, doc.content_md)
        fts_upsert(doc.id, doc.title, doc.content_md)
    except Exception as e:
        logger.error(f"reindex 失败 doc={doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"code": 0, "msg": "ok", "chunks": cn}


@router.post("/reindex-all")
async def reindex_all_documents(session: AsyncSession = Depends(get_session)):
    if not settings.AI_API_KEY:
        raise HTTPException(status_code=400, detail="AI_API_KEY 未配置")

    result = await session.execute(
        select(Document).where(Document.is_deleted == False, Document.content_md != None)
    )
    docs = result.scalars().all()

    total_chunks = 0
    for doc in docs:
        try:
            cn = await _do_chunk_and_vectorize(session, doc.id, doc.content_md or "")
            total_chunks += cn
            fts_upsert(doc.id, doc.title, doc.content_md or "")
            logger.info(f"文档 {doc.id} ({doc.title}) 索引完成, {cn} 个片段")
        except Exception as e:
            logger.error(f"文档 {doc.id} 索引失败: {e}")

    return {"code": 0, "msg": "ok", "documents": len(docs), "chunks": total_chunks}


@router.post("/create-text")
async def create_text_document(
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """从纯文本创建文档（在线新建 Markdown 用）"""
    import asyncio
    from datetime import datetime as dt

    title = body.get("title", "未命名文档").strip()
    content = body.get("content", "")

    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")

    doc = Document(
        title=title,
        file_path=None,
        file_type="md",
        file_size=0,
        content_md=content,
        parse_status="success" if content else "partial",
        word_count=len(content),
    )

    async with session.begin():
        session.add(doc)
        await session.flush()
        doc_id = doc.id

    async with session.begin():
        session.add(DocumentVersion(
            document_id=doc_id,
            content_md=content,
            version_note="在线创建",
        ))

    fts_upsert(doc_id, title, content)

    if content and settings.AI_API_KEY:
        asyncio.create_task(_bg_vectorize(doc_id, content))

    return _doc_to_response(doc)
