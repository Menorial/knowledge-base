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
from backend.db.models import Document, Chunk, DocumentVersion, DocumentLink
from backend.db.schemas import DocumentResponse, DocumentListResponse, DocumentPreviewResponse, DocumentUpdate, ClipRequest
from backend.utils.security import validate_file, safe_save_filename, safe_store_path
from backend.services.parser import parse_document, ParseError, html_to_markdown
from backend.services.clipper import extract_main_html, localize_images
from backend.services.chunker import chunk_markdown
from backend.services.embedding import embedding_service, embedding_available
from backend.services.vec_store import delete_by_document_async, bulk_add_async
from backend.services.fts_sync import fts_upsert_async, fts_delete_async
from backend.services.links import rebuild_all_links

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _schedule_links_rebuild():
    """后台重建双向链接（不影响主流程，失败仅记日志）"""
    async def _run():
        try:
            async with async_session() as session:
                await rebuild_all_links(session)
        except Exception as e:
            logger.error(f"链接重建失败: {e}", exc_info=True)
    asyncio.create_task(_run())


def _doc_to_response(doc: Document, tags: list[str] | None = None) -> DocumentResponse:
    if tags is None:
        # 仅在 tags 已加载（selectinload）时读取，避免在异步上下文外触发懒加载 IO
        if "tags" in doc.__dict__ and doc.tags:
            tags = [t.name for t in doc.tags]
        else:
            tags = []
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
        source_url=doc.source_url,
        tags=tags,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _bg_vectorize(doc_id: int, content_md: str):
    """后台向量化：自己管理 session，上传接口可立即返回"""
    try:
        chunks = chunk_markdown(content_md)
        await delete_by_document_async(doc_id)

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
            await bulk_add_async(list(zip(chunk_ids, [doc_id] * len(chunks), embeddings)))

            # 更新文档状态
            doc = await session.get(Document, doc_id)
            if doc:
                doc.parse_status = "success"
                await session.commit()

        logger.info(f"文档 {doc_id} 向量化完成, {len(chunks)} 个片段")
    except Exception as e:
        logger.error(f"向量化失败 {doc_id}: {e}", exc_info=True)

    # 摘要生成独立于向量化，失败不影响主流程
    await _bg_summarize(doc_id, content_md)


async def _bg_summarize(doc_id: int, content_md: str):
    """后台 AI 自动摘要（可选功能，未配置 API Key 时静默跳过）"""
    try:
        if not settings.AI_API_KEY:
            return
        from backend.services.llm import llm_service
        preview = (content_md or "")[:4000]
        if len(preview.strip()) < 50:
            return
        text = await llm_service.chat([
            {"role": "system", "content": "你是文档摘要助手。请用不超过 80 字概括文档核心内容，直接输出摘要正文，不要任何前缀或解释。"},
            {"role": "user", "content": preview},
        ])
        text = (text or "").strip().strip('"“”')
        if text:
            async with async_session() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.summary = text[:500]
                    await session.commit()
                    logger.info(f"文档 {doc_id} 自动摘要完成")
    except Exception as e:
        logger.warning(f"自动摘要失败 doc={doc_id}: {e}")

    # 摘要后顺带自动打标签（同样走后台，失败不影响主流程）
    try:
        from backend.services.autotag import autotag_document
        await autotag_document(doc_id, content_md)
    except Exception as e:
        logger.warning(f"自动打标签失败 doc={doc_id}: {e}")


async def _do_chunk_and_vectorize(session: AsyncSession, doc_id: int, content_md: str):
    """给 reparse/reindex 用的同步版本"""
    chunks = chunk_markdown(content_md)

    await delete_by_document_async(doc_id)
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
    await bulk_add_async(list(zip(chunk_ids, [doc_id] * len(chunks), embeddings)))

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

    await fts_upsert_async(doc_id, title, md_content)

    if md_content and parse_status == "success" and embedding_available():
        asyncio.create_task(_bg_vectorize(doc_id, md_content))

    _schedule_links_rebuild()

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
        source_url=doc.source_url,
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

    # 必须在赋值前记录内容是否变化，否则赋值后比较恒为 False，向量索引永远不会更新
    content_changed = body.content_md is not None and body.content_md != doc.content_md

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

    await fts_upsert_async(doc.id, doc.title, doc.content_md)

    if content_changed and embedding_available():
        try:
            await _do_chunk_and_vectorize(session, doc.id, body.content_md)
        except Exception as e:
            logger.error(f"更新后向量化失败 {doc.id}: {e}", exc_info=True)
        asyncio.create_task(_bg_summarize(doc.id, body.content_md))

    if content_changed or body.title is not None:
        _schedule_links_rebuild()

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

    await fts_delete_async(doc_id)
    await delete_by_document_async(doc_id)
    _schedule_links_rebuild()

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

    await fts_upsert_async(doc.id, doc.title, doc.content_md or "")

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

    await fts_upsert_async(doc.id, doc.title, doc.content_md or "")
    _schedule_links_rebuild()

    return {"code": 0, "msg": "ok"}


@router.post("/{doc_id}/reindex")
async def reindex_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    if not embedding_available():
        raise HTTPException(status_code=400, detail="未配置 Embedding（本地 BGE 或 API Key）")

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
        await fts_upsert_async(doc.id, doc.title, doc.content_md)
    except Exception as e:
        logger.error(f"reindex 失败 doc={doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"code": 0, "msg": "ok", "chunks": cn}


@router.post("/reindex-all")
async def reindex_all_documents(session: AsyncSession = Depends(get_session)):
    if not embedding_available():
        raise HTTPException(status_code=400, detail="未配置 Embedding（本地 BGE 或 API Key）")

    result = await session.execute(
        select(Document).where(Document.is_deleted == False, Document.content_md != None)
    )
    docs = result.scalars().all()

    total_chunks = 0
    for doc in docs:
        try:
            cn = await _do_chunk_and_vectorize(session, doc.id, doc.content_md or "")
            total_chunks += cn
            await fts_upsert_async(doc.id, doc.title, doc.content_md or "")
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

    await fts_upsert_async(doc_id, title, content)

    if content and embedding_available():
        asyncio.create_task(_bg_vectorize(doc_id, content))

    _schedule_links_rebuild()

    return _doc_to_response(doc)


# ============ 双向链接 ============

@router.get("/{doc_id}/links")
async def get_document_links(doc_id: int, session: AsyncSession = Depends(get_session)):
    """返回文档的双向链接：outgoing=本文指向谁，incoming=谁指向本文"""
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="文档不存在")

    out_result = await session.execute(
        select(DocumentLink, Document.title)
        .join(Document, Document.id == DocumentLink.to_doc_id)
        .where(
            DocumentLink.from_doc_id == doc_id,
            Document.is_deleted == False,
        )
        .order_by(DocumentLink.id)
    )
    outgoing = [
        {"id": link.to_doc_id, "title": title, "source": link.source}
        for link, title in out_result.all()
    ]

    in_result = await session.execute(
        select(DocumentLink, Document.title)
        .join(Document, Document.id == DocumentLink.from_doc_id)
        .where(
            DocumentLink.to_doc_id == doc_id,
            Document.is_deleted == False,
        )
        .order_by(DocumentLink.id)
    )
    incoming = [
        {"id": link.from_doc_id, "title": title, "source": link.source}
        for link, title in in_result.all()
    ]

    return {"outgoing": outgoing, "incoming": incoming}


# ============ 版本历史 ============

@router.get("/{doc_id}/versions")
async def list_versions(doc_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="文档不存在")

    v_result = await session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.id.desc())
    )
    versions = v_result.scalars().all()
    return [
        {
            "id": v.id,
            "version_note": v.version_note,
            "created_at": v.created_at,
            "word_count": len(v.content_md or ""),
            "content_preview": (v.content_md or "")[:200],
        }
        for v in versions
    ]


@router.get("/{doc_id}/versions/{version_id}")
async def get_version(doc_id: int, version_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == doc_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {
        "id": version.id,
        "version_note": version.version_note,
        "created_at": version.created_at,
        "content_md": version.content_md or "",
    }


@router.post("/{doc_id}/versions/{version_id}/restore")
async def restore_version(doc_id: int, version_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    v_result = await session.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == doc_id,
        )
    )
    version = v_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    doc.content_md = version.content_md or ""
    doc.word_count = len(doc.content_md)
    doc.updated_at = datetime.utcnow()
    session.add(DocumentVersion(
        document_id=doc.id,
        content_md=doc.content_md,
        version_note=f"回滚到版本 #{version.id}",
    ))
    await session.commit()

    await fts_upsert_async(doc.id, doc.title, doc.content_md)

    if embedding_available():
        try:
            await _do_chunk_and_vectorize(session, doc.id, doc.content_md)
        except Exception as e:
            logger.error(f"回滚后向量化失败 {doc.id}: {e}", exc_info=True)
        asyncio.create_task(_bg_summarize(doc.id, doc.content_md))

    _schedule_links_rebuild()

    return {"code": 0, "msg": "ok"}


# ============ 网页剪藏 ============

_MAX_CLIP_BYTES = 5 * 1024 * 1024
_CLIP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


async def _fetch_webpage(url: str) -> tuple[str, str]:
    """抓取网页，返回 (html_text, page_title)。限协议、限大小、带超时"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="仅支持 http/https 链接")

    import httpx
    import re

    # 常见反爬/风控状态码 → 友好提示（CSDN 等站点会拦截服务器抓取）
    _ANTI_BOT_HINTS = {
        403: "网站拒绝访问（403，通常是反爬拦截）",
        405: "网站拒绝该请求方式（405）",
        418: "网站识别到非浏览器访问（418）",
        429: "访问过于频繁被限流（429）",
        503: "网站服务暂不可用（503）",
        521: "网站源站无法连接（521，CSDN 等 Cloudflare 站点常用来拦截服务器抓取）",
        522: "网站连接超时（522）",
        523: "网站源站不可达（523）",
        524: "网站响应超时（524）",
    }

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": _CLIP_UA},
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code in _ANTI_BOT_HINTS:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"抓取被拦截：{_ANTI_BOT_HINTS[resp.status_code]}。"
                            "请改用浏览器书签小工具剪藏（书签把页面 HTML 直接发给知识库，绕开网站风控），"
                            "在剪藏弹窗里点「复制书签代码」安装。"
                        ),
                    )
                resp.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_CLIP_BYTES:
                        raise HTTPException(status_code=400, detail="网页过大（>5MB），拒绝剪藏")
                    chunks.append(chunk)
                raw = b"".join(chunks)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = _ANTI_BOT_HINTS.get(code)
        if hint:
            raise HTTPException(
                status_code=400,
                detail=f"抓取被拦截：{hint}。请改用浏览器书签小工具剪藏（弹窗内可一键复制代码）。",
            )
        raise HTTPException(status_code=400, detail=f"网页抓取失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"网页抓取失败: {e}")

    # 编码探测：优先 <meta charset>，其次 UTF-8
    head = raw[:2048].decode("utf-8", errors="ignore")
    charset_m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    charset = charset_m.group(1) if charset_m else None
    if charset:
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")

    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    page_title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:200] if title_m else ""
    return text, page_title


@router.post("/clip")
async def clip_webpage(
    body: ClipRequest,
    session: AsyncSession = Depends(get_session),
):
    """网页剪藏：服务端抓取 URL，或直接接收页面 HTML，提取正文 + 图片本地化后入库"""
    if not body.url and not body.html:
        raise HTTPException(status_code=400, detail="需要提供 url 或 html")

    html_content = body.html
    source_url = (body.url or "").strip()
    title = (body.title or "").strip()

    if not html_content:
        html_content, page_title = await _fetch_webpage(source_url)
        if not title:
            title = page_title

    if not html_content or not html_content.strip():
        raise HTTPException(status_code=400, detail="网页内容为空，抓取失败")

    if not title:
        title = source_url[:100] if source_url else "未命名剪藏"

    # 1. 正文提取（去掉导航/广告/页脚等噪声），失败回退整页
    main_html = extract_main_html(html_content, source_url)

    # 2. 先建文档拿到 doc_id（图片目录按 doc_id 组织，便于彻底删除时清理）
    doc = Document(
        title=title[:500],
        file_path=None,
        file_type="clip",
        file_size=len(html_content),
        content_md="",
        parse_status="pending",
        word_count=0,
        source_url=source_url or None,
    )
    async with session.begin():
        session.add(doc)
        await session.flush()
        doc_id = doc.id
        session.add(DocumentVersion(
            document_id=doc_id,
            content_md="",
            version_note="网页剪藏",
        ))

    # 3. 图片本地化（下载到 files/clip/{doc_id}/，src 替换为本地路径）
    img_dir = settings.file_storage_abs / "clip" / str(doc_id)
    try:
        main_html = await localize_images(main_html, source_url, img_dir)
    except Exception as e:
        logger.warning(f"剪藏图片本地化失败 doc={doc_id}: {e}")

    # 4. 转 Markdown 并回填
    try:
        md_content = html_to_markdown(main_html)
    except ParseError as e:
        md_content = ""
        logger.warning(f"剪藏 Markdown 转换失败 doc={doc_id}: {e}")

    async with session.begin():
        doc = await session.get(Document, doc_id)
        doc.content_md = md_content
        doc.word_count = len(md_content)
        doc.parse_status = "success" if md_content else "partial"

    # 5. 附加标签（在事务内显式加载 tags，避免懒加载）
    if body.tags:
        from backend.db.models import Tag
        async with session.begin():
            doc_result = await session.execute(
                select(Document).where(Document.id == doc_id).options(selectinload(Document.tags))
            )
            doc = doc_result.scalar_one()
            for tag_name in body.tags:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                tag_result = await session.execute(select(Tag).where(Tag.name == tag_name))
                tag = tag_result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)
                if tag not in doc.tags:
                    doc.tags.append(tag)
                    tag.usage_count = (tag.usage_count or 0) + 1

    await fts_upsert_async(doc_id, doc.title, md_content)

    if md_content and embedding_available():
        asyncio.create_task(_bg_vectorize(doc_id, md_content))

    _schedule_links_rebuild()

    result = await session.execute(
        select(Document).where(Document.id == doc_id).options(selectinload(Document.tags))
    )
    doc = result.scalar_one()
    return _doc_to_response(doc)
