import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.database import get_session
from backend.db.models import Tag, Document, DocumentTag
from backend.db.schemas import TagResponse, TagCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
async def list_tags(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).order_by(Tag.usage_count.desc()))
    return result.scalars().all()


@router.post("", response_model=TagResponse)
async def create_tag(body: TagCreate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).where(Tag.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="标签已存在")
    tag = Tag(name=body.name, color=body.color)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: int, body: TagCreate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    tag.name = body.name
    tag.color = body.color
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    await session.delete(tag)
    await session.commit()
    return {"code": 0, "msg": "ok"}


@router.post("/document/{doc_id}")
async def add_tag_to_document(
    doc_id: int,
    tag_names: list[str],
    session: AsyncSession = Depends(get_session),
):
    doc_result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False).options(selectinload(Document.tags))
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    for tag_name in tag_names:
        tag_result = await session.execute(select(Tag).where(Tag.name == tag_name))
        tag = tag_result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            session.add(tag)
        if tag not in doc.tags:
            doc.tags.append(tag)
            tag.usage_count = (tag.usage_count or 0) + 1

    await session.commit()
    return {"code": 0, "msg": "ok"}


@router.delete("/document/{doc_id}/{tag_id}")
async def remove_tag_from_document(
    doc_id: int,
    tag_id: int,
    session: AsyncSession = Depends(get_session),
):
    doc_result = await session.execute(
        select(Document).where(Document.id == doc_id).options(selectinload(Document.tags))
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    tag_result = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_result.scalar_one_or_none()
    if tag and tag in doc.tags:
        doc.tags.remove(tag)
        tag.usage_count = max(0, (tag.usage_count or 0) - 1)

    await session.commit()
    return {"code": 0, "msg": "ok"}
