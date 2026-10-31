import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_session
from backend.db.models import Document, Conversation, Message, Tag, Chunk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)):
    doc_count = (await session.execute(select(func.count()).select_from(Document).where(Document.is_deleted == False))).scalar() or 0
    conv_count = (await session.execute(select(func.count()).select_from(Conversation))).scalar() or 0
    msg_count = (await session.execute(select(func.count()).select_from(Message))).scalar() or 0
    tag_count = (await session.execute(select(func.count()).select_from(Tag))).scalar() or 0
    chunk_count = (await session.execute(
        select(func.count())
        .select_from(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.is_deleted == False)
    )).scalar() or 0

    # 最近 7 天文档上传趋势
    trend = []
    for i in range(6, -1, -1):
        date_expr = text(f"date('now', '-{i} day')")
        cnt = (await session.execute(
            select(func.count()).select_from(Document).where(
                Document.is_deleted == False,
                func.date(Document.created_at) == func.date(date_expr)
            )
        )).scalar() or 0
        trend.append(int(cnt))

    # 解析状态分布
    status_result = await session.execute(
        select(Document.parse_status, func.count()).where(Document.is_deleted == False).group_by(Document.parse_status)
    )
    parse_status = {row[0] or "unknown": row[1] for row in status_result.all()}

    # Top 标签
    tag_result = await session.execute(
        select(Tag.name, Tag.usage_count).order_by(Tag.usage_count.desc()).limit(5)
    )
    top_tags = [{"name": row[0], "count": row[1]} for row in tag_result.all()]

    return {
        "documents": doc_count,
        "conversations": conv_count,
        "messages": msg_count,
        "tags": tag_count,
        "chunks": chunk_count,
        "upload_trend_7d": trend,
        "parse_status": parse_status,
        "top_tags": top_tags,
    }


@router.post("/test-llm")
async def test_llm():
    """测试 AI 接口是否通畅"""
    from backend.services.llm import llm_service
    try:
        messages = [{"role": "user", "content": "ping"}]
        result = ""
        stream = llm_service.chat_stream(messages)
        try:
            async for chunk in stream:
                result += chunk
                if len(result) > 10:
                    break
        finally:
            # 中途 break 不会自动关闭底层连接，必须显式 aclose
            await stream.aclose()
        return {"ok": True, "response_preview": result[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
