import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .embedding import embedding_service
from .vec_store import search_async
from ..db.models import Document, Chunk

logger = logging.getLogger(__name__)


RAG_SYSTEM_PROMPT = """你是一个专业的知识库问答助手。请严格基于下方提供的文档内容回答用户问题。

## 回答要求
1. 优先使用知识库中的内容回答，确保准确性
2. 如果检索到多个相关片段，请综合整理后给出完整回答
3. 如果知识库中完全没有相关内容，请直接回答"⚠️ 知识库中未找到相关信息"，不要编造答案
4. 回答末尾附上引用来源，格式：`📎 [文档标题 - 章节名]`

## 风格要求
- 回答清晰、有条理，适当使用 Markdown 格式
- 保持专业但友好的语气"""

DIRECT_SYSTEM_PROMPT = """你是一个专业、友好的 AI 助手。可以回答各类问题，包括知识查询、代码编写、文本分析、创意写作等。请用清晰、有条理的方式回答，适当使用 Markdown 格式让内容更易读。"""


def build_rag_messages(context_docs: list[dict], question: str, history: list[dict] | None = None) -> list[dict]:
    context_parts = []
    for item in context_docs:
        doc_title = item.get("title", "未知文档")
        section = item.get("section_path", "")
        content = item.get("content", "")
        header = f"📄 {doc_title}"
        if section:
            header += f" > {section}"
        context_parts.append(f"{header}\n{content}")

    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "（知识库中未检索到相关内容）"

    messages: list[dict] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]

    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"【检索到的知识库片段】\n\n{context_text}\n\n---\n\n【用户问题】\n{question}",
    })
    return messages


def build_direct_messages(question: str, history: list[dict] | None = None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": DIRECT_SYSTEM_PROMPT}]

    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})
    return messages


SINGLE_DOC_FULL_LIMIT = 12000     # 不超过该长度的文档直接全文塞进 prompt
SINGLE_DOC_SNIPPET_K = 6          # 长文档在文档内部检索的片段数
RAG_CANDIDATE_FACTOR = 4          # 向量召回放大倍数（软删除文档的向量仍在库里，需要跳过）


async def retrieve_for_rag(session: AsyncSession, question: str, top_k: int = 5) -> list[dict]:
    """跨库检索：一次 JOIN 取回片段与文档，跳过已删除文档后截断到 top_k。"""
    try:
        query_embedding = await embedding_service.get_embedding(question)
    except Exception as e:
        logger.error(f"Embedding 失败: {e}")
        return []

    candidates = await search_async(
        query_embedding, top_k=max(top_k * RAG_CANDIDATE_FACTOR, 20)
    )
    if not candidates:
        return []

    chunk_ids = [c["chunk_id"] for c in candidates]
    rows = (
        await session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(chunk_ids), Document.is_deleted == False)
        )
    ).all()
    pairs = {chunk.id: (chunk, doc) for chunk, doc in rows}

    context_docs: list[dict] = []
    for item in candidates:
        pair = pairs.get(item["chunk_id"])
        if not pair:
            continue
        chunk, doc = pair
        context_docs.append({
            "chunk_id": chunk.id,
            "document_id": doc.id,
            "title": doc.title,
            "section_path": chunk.section_path,
            "content": chunk.content,
            "distance": item["distance"],
        })
        if len(context_docs) >= top_k:
            break

    context_docs.sort(key=lambda x: x["distance"])
    return context_docs[:top_k]


def _question_terms(question: str) -> list[str]:
    """把问题拆成用于关键词兜底的词（长度 >= 2）"""
    return [
        t
        for t in re.split(r"[\s,，.。？?！!、;；:：()（）\[\]【】\"'“”]+", question or "")
        if len(t) >= 2
    ]


async def _retrieve_doc_chunks(
    session: AsyncSession,
    document_id: int,
    question: str,
    limit: int = SINGLE_DOC_SNIPPET_K,
) -> list[Chunk]:
    """在单篇文档内部检索相关片段：优先向量，失败时退化为关键词命中。"""
    try:
        query_embedding = await embedding_service.get_embedding(question)
        candidates = await search_async(query_embedding, top_k=max(limit * 8, 40))
        ids = [c["chunk_id"] for c in candidates if c["document_id"] == document_id][:limit]
        if ids:
            rows = (
                await session.execute(select(Chunk).where(Chunk.id.in_(ids)))
            ).scalars().all()
            by_id = {c.id: c for c in rows}
            ordered = [by_id[i] for i in ids if i in by_id]
            if ordered:
                return ordered
    except Exception as e:
        logger.warning(f"单文档向量检索失败，改用关键词匹配: {e}")

    rows = (
        await session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
    ).scalars().all()
    if not rows:
        return []

    terms = _question_terms(question)
    if terms:
        def _score(chunk: Chunk) -> int:
            text = chunk.content or ""
            return sum(text.count(t) for t in terms)

        scored = sorted(rows, key=_score, reverse=True)
        hit = [c for c in scored[:limit] if _score(c) > 0]
        if hit:
            return hit

    return rows[:limit]


async def build_single_doc_messages(
    session: AsyncSession,
    document_id: int,
    question: str,
    history: list[dict] | None = None,
) -> list[dict]:
    """指定文档问答：短文档给全文，长文档在文档内部检索相关片段。"""
    doc_result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"文档不存在: {document_id}")

    content = doc.content_md or ""
    system_prompt = (
        f"你是一个文档助手，请严格基于文档《{doc.title}》的内容回答问题。"
        "如果提供的文档内容中没有相关信息，请明确说明“文档中未找到相关内容”，不要编造。"
    )

    if len(content) <= SINGLE_DOC_FULL_LIMIT:
        user_content = f"文档《{doc.title}》全文：\n\n{content}\n\n问题：{question}"
    else:
        chunks = await _retrieve_doc_chunks(session, document_id, question)
        if chunks:
            parts = []
            for c in chunks:
                header = f"📄 {doc.title}"
                if c.section_path:
                    header += f" > {c.section_path}"
                parts.append(f"{header}\n{c.content}")
            excerpts = "\n\n---\n\n".join(parts)
            user_content = (
                f"《{doc.title}》全文约 {len(content)} 字，较长，以下是检索到的 "
                f"{len(chunks)} 个最相关片段（按相关度排序），请基于这些片段回答：\n\n"
                f"{excerpts}\n\n---\n\n【用户问题】\n{question}"
            )
        else:
            # 没有切片（尚未索引）时退化为开头部分，并在提示里注明，避免 AI 误以为读到了全文
            user_content = (
                f"文档《{doc.title}》较长（约 {len(content)} 字），当前仅提供开头 "
                f"{SINGLE_DOC_FULL_LIMIT} 字：\n\n{content[:SINGLE_DOC_FULL_LIMIT]}\n\n"
                f"【用户问题】\n{question}"
            )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_content})
    return messages
