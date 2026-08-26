"""知识图谱数据：节点 = 未删除文档，边 = 双向链接"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.database import get_session
from backend.db.models import Document, DocumentLink

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def graph_data(session: AsyncSession = Depends(get_session)):
    doc_result = await session.execute(
        select(Document)
        .where(Document.is_deleted == False)
        .options(selectinload(Document.tags))
        .order_by(Document.id)
    )
    docs = doc_result.scalars().all()
    doc_ids = {d.id for d in docs}

    nodes = [
        {
            "id": d.id,
            "title": d.title,
            "file_type": d.file_type,
            "tags": [t.name for t in d.tags],
        }
        for d in docs
    ]

    link_result = await session.execute(
        select(DocumentLink.from_doc_id, DocumentLink.to_doc_id, DocumentLink.source)
    )
    edges = [
        {"source": f, "target": t, "sourceType": src}
        for f, t, src in link_result.all()
        if f in doc_ids and t in doc_ids
    ]

    return {"nodes": nodes, "edges": edges}
