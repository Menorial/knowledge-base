import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.database import get_session, engine
from backend.db.models import Conversation, Message, Document
from backend.db.schemas import (
    ConversationCreate, ConversationResponse,
    ChatRequest, ChatRAGRequest, ChatDirectRequest,
)
from backend.services.llm import llm_service
from backend.services.rag import (
    build_rag_messages, build_direct_messages,
    retrieve_for_rag, build_single_doc_messages,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

AsyncSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _conv_to_response(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "mode": getattr(conv, "mode", "rag"),
        "document_id": conv.document_id,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": json.loads(m.sources) if m.sources else None,
                "created_at": m.created_at,
            }
            for m in conv.messages
        ],
    }


@router.get("/conversations")
async def list_conversations(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "mode": getattr(c, "mode", "rag"),
            "document_id": c.document_id,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in convs
    ]


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_session),
):
    mode = body.mode or ("doc" if body.document_id else "rag")
    conv = Conversation(title=body.title, mode=mode, document_id=body.document_id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return {"id": conv.id, "title": conv.title, "mode": mode, "document_id": conv.document_id}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session.refresh(conv, ["messages"])
    return _conv_to_response(conv)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session.delete(conv)
    await session.commit()
    return {"code": 0, "msg": "ok"}


@router.put("/conversations/{conv_id}")
async def update_conversation(
    conv_id: int,
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if "title" in body:
        conv.title = body["title"]
    if "mode" in body:
        conv.mode = body["mode"]
    await session.commit()
    await session.refresh(conv)
    return {"id": conv.id, "title": conv.title, "mode": getattr(conv, "mode", "rag")}


async def _get_history(session: AsyncSession, conv_id: int) -> list[dict]:
    if not conv_id:
        return []
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        return []
    await session.refresh(conv, ["messages"])
    return [
        {"role": m.role, "content": m.content}
        for m in conv.messages
    ]


async def _save_msg(conv_id: int, role: str, content: str, sources_json: str | None = None):
    async with AsyncSessionFactory() as s:
        s.add(Message(
            conversation_id=conv_id,
            role=role,
            content=content,
            sources=sources_json,
        ))
        await s.commit()


async def _stream_llm(messages, conv_id, sources_json=None, sources_list=None):
    """统一的流式输出 + 保存消息"""
    full_response = ""

    async def generate():
        nonlocal full_response
        try:
            async for chunk in llm_service.chat_stream(messages):
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            done_payload = {"done": True}
            if sources_list:
                done_payload["sources"] = sources_list
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            err_chunk = f"\n\n❌ AI 响应出错：{e}"
            full_response += err_chunk
            yield f"data: {json.dumps({'content': err_chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        finally:
            if conv_id and full_response:
                try:
                    await _save_msg(conv_id, "assistant", full_response, sources_json)
                except Exception as e:
                    logger.error(f"Save assistant msg error: {e}")

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============ 1. 纯 AI 对话（不依赖知识库）============
@router.post("/chat/direct")
async def chat_direct(
    body: ChatDirectRequest,
    session: AsyncSession = Depends(get_session),
):
    history = await _get_history(session, body.conversation_id)
    messages = build_direct_messages(body.message, history)

    if body.conversation_id:
        await _save_msg(body.conversation_id, "user", body.message)

    return await _stream_llm(messages, body.conversation_id)


# ============ 2. RAG 知识库问答 ============
@router.post("/chat/rag")
async def chat_rag(
    body: ChatRAGRequest,
    session: AsyncSession = Depends(get_session),
):
    context_docs = await retrieve_for_rag(session, body.message, top_k=body.top_k)
    messages = build_rag_messages(
        context_docs, body.message,
        await _get_history(session, body.conversation_id),
    )

    sources_json = json.dumps([
        {"title": d["title"], "section_path": d.get("section_path", ""), "snippet": d["content"][:200]}
        for d in context_docs
    ], ensure_ascii=False) if context_docs else None

    sources_list = [
        {"title": d["title"], "section_path": d.get("section_path", ""), "snippet": d["content"][:200]}
        for d in context_docs
    ] if context_docs else None

    if body.conversation_id:
        await _save_msg(body.conversation_id, "user", body.message)

    return await _stream_llm(messages, body.conversation_id, sources_json, sources_list)


# ============ 3. 指定文档问答 ============
@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
):
    if not body.document_id:
        raise HTTPException(status_code=400, detail="需要指定 document_id")

    messages = await build_single_doc_messages(
        session, body.document_id, body.message,
        await _get_history(session, body.conversation_id),
    )

    if body.conversation_id:
        await _save_msg(body.conversation_id, "user", body.message)

    return await _stream_llm(messages, body.conversation_id)


# ============ 4. 导出对话为 Markdown ============
@router.get("/conversations/{conv_id}/export")
async def export_conversation(conv_id: int, session: AsyncSession = Depends(get_session)):
    from fastapi.responses import PlainTextResponse
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session.refresh(conv, ["messages"])

    mode_map = {"rag": "知识库问答", "direct": "纯AI对话", "doc": "指定文档问答"}
    lines = [
        f"# {conv.title or '未命名对话'}",
        "",
        f"- **模式**: {mode_map.get(getattr(conv, 'mode', 'rag'), '知识库问答')}",
        f"- **创建时间**: {conv.created_at}",
        f"- **消息数**: {len(conv.messages)}",
        "",
        "---",
        "",
    ]

    for msg in conv.messages:
        role_label = "👤 **用户**" if msg.role == "user" else "🤖 **AI**"
        lines.append(f"### {role_label}")
        lines.append("")
        lines.append(msg.content)
        lines.append("")
        if msg.sources:
            try:
                srcs = json.loads(msg.sources)
                if srcs:
                    lines.append("**📎 引用来源:**")
                    for s in srcs:
                        lines.append(f"- {s.get('title', '')}{' > ' + s.get('section_path', '') if s.get('section_path') else ''}")
                    lines.append("")
            except Exception:
                pass
        lines.append("---")
        lines.append("")

    md_content = "\n".join(lines)
    filename = (conv.title or "conversation").replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
    import urllib.parse
    safe_name = urllib.parse.quote(filename)
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}.md"; filename*=UTF-8\'\'{safe_name}.md'}
    return PlainTextResponse(md_content, media_type="text/markdown", headers=headers)


# ============ 5. 重新生成某条 AI 消息 ============
@router.post("/conversations/{conv_id}/regenerate/{msg_id}")
async def regenerate_message(conv_id: int, msg_id: int, session: AsyncSession = Depends(get_session)):
    from backend.db.models import Message

    conv_result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session.refresh(conv, ["messages"])

    # 找到要重新生成的消息及其之前的最后一条 user 消息
    target_idx = None
    for i, m in enumerate(conv.messages):
        if m.id == msg_id:
            target_idx = i
            break
    if target_idx is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if conv.messages[target_idx].role != "assistant":
        raise HTTPException(status_code=400, detail="只能重新生成 AI 消息")

    # 找到 target_idx 之前的最后一条 user 消息
    last_user_idx = None
    for i in range(target_idx - 1, -1, -1):
        if conv.messages[i].role == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        raise HTTPException(status_code=400, detail="找不到对应的用户消息")

    last_user_msg = conv.messages[last_user_idx]
    # 删除 target_idx 之后的所有消息 + target 本身
    msgs_to_delete = conv.messages[target_idx:]
    for m in msgs_to_delete:
        await session.delete(m)
    await session.commit()

    # 用该用户消息重新走一遍对话逻辑
    mode = getattr(conv, "mode", "rag")
    doc_id = conv.document_id

    # 重建 history（target 之前的）
    history = [{"role": m.role, "content": m.content} for m in conv.messages[:last_user_idx]]

    sources_json = None
    sources_list = None

    if mode == "direct":
        messages = build_direct_messages(last_user_msg.content, history)
    elif mode == "doc" and doc_id:
        messages = await build_single_doc_messages(session, doc_id, last_user_msg.content, history)
    else:
        context_docs = await retrieve_for_rag(session, last_user_msg.content, top_k=5)
        messages = build_rag_messages(context_docs, last_user_msg.content, history)
        sources_json = json.dumps([
            {"title": d["title"], "section_path": d.get("section_path", ""), "snippet": d["content"][:200]}
            for d in context_docs
        ], ensure_ascii=False) if context_docs else None
        sources_list = [
            {"title": d["title"], "section_path": d.get("section_path", ""), "snippet": d["content"][:200]}
            for d in context_docs
        ] if context_docs else None

    # 保存 user 消息（还没保存到新 session）
    await _save_msg(conv_id, "user", last_user_msg.content)

    return await _stream_llm(messages, conv_id, sources_json, sources_list)
