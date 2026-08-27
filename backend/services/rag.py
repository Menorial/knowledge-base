import logging
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


async def retrieve_for_rag(session: AsyncSession, question: str, top_k: int = 5) -> list[dict]:
    try:
        query_embedding = await embedding_service.get_embedding(question)
    except Exception as e:
        logger.error(f"Embedding 失败: {e}")
        return []

    search_results = await search_async(query_embedding, top_k=top_k)
    if not search_results:
        return []

    context_docs = []
    for item in search_results:
        chunk_result = await session.execute(
            select(Chunk).where(Chunk.id == item["chunk_id"])
        )
        chunk = chunk_result.scalar_one_or_none()
        if not chunk:
            continue

        doc_result = await session.execute(
            select(Document).where(Document.id == item["document_id"])
        )
        doc = doc_result.scalar_one_or_none()
        if not doc or doc.is_deleted:
            continue

        context_docs.append({
            "chunk_id": chunk.id,
            "document_id": doc.id,
            "title": doc.title,
            "section_path": chunk.section_path,
            "content": chunk.content,
            "distance": item["distance"],
        })

    context_docs.sort(key=lambda x: x["distance"])
    return context_docs[:top_k]


async def build_single_doc_messages(
    session: AsyncSession,
    document_id: int,
    question: str,
    history: list[dict] | None = None,
) -> list[dict]:
    doc_result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"文档不存在: {document_id}")

    content = doc.content_md or ""

    messages: list[dict] = [
        {"role": "system", "content": f"你是一个文档助手，请严格基于文档《{doc.title}》的内容回答问题。如果文档中没有相关内容，请明确说明。"}
    ]

    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"文档内容：\n\n{content[:12000]}\n\n问题：{question}",
    })
    return messages
