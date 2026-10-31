"""文档双向链接检测与重建。

链接来源分两种：
- `syntax`：文档中显式写 `[[目标标题]]`
- `auto`：正文中出现其他文档的标题（自动匹配，最长优先，跳过代码块与已占用的区间）

全量重建会串行化执行（asyncio.Lock），避免并发编辑时互相覆盖。
"""
import asyncio
import logging
import re
import threading

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session
from ..db.models import Document, DocumentLink
from ..utils.loop_lock import loop_lock

logger = logging.getLogger(__name__)


_SYNTAX_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# 太短的标题不做自动匹配，避免大量误连
MIN_AUTO_TITLE_LEN = 2


def _strip_code(content: str) -> str:
    """去掉代码块与行内代码，防止代码里的词汇被误判为链接"""
    content = _FENCE_RE.sub(" ", content)
    content = _INLINE_CODE_RE.sub(" ", content)
    return content


def _resolve_syntax_target(raw_target: str, title_set: set[str], sorted_titles: list[str]) -> str | None:
    """解析 [[目标]]：
    1. 精确匹配标题
    2. 子串兜底（目标包含于某标题，或某标题包含于目标），支持小幅重命名后旧引用继续生效
    """
    if raw_target in title_set:
        return raw_target
    for title in sorted_titles:  # 从长到短，避免命中过短的泛化标题
        if raw_target in title or title in raw_target:
            return title
    return None


def extract_links(content_md: str, own_title: str, all_titles: list[str]) -> list[tuple[str, str]]:
    """提取一篇文档指向其他文档的链接。

    返回 [(目标标题, 来源)]，来源 ∈ {"syntax", "auto"}；同一目标只保留最高优先级。
    """
    content = content_md or ""
    results: list[tuple[str, str]] = []
    if not content.strip():
        return results

    title_set = set(all_titles)
    sorted_titles = sorted(title_set, key=len, reverse=True)

    # 1. [[语法]] 链接（显式意图，精确 + 子串兜底）
    syntax_spans: list[tuple[int, int]] = []
    for m in _SYNTAX_RE.finditer(content):
        target = m.group(1).strip()
        if target and target != own_title:
            resolved = _resolve_syntax_target(target, title_set, sorted_titles)
            if resolved:
                results.append((resolved, "syntax"))
        syntax_spans.append((m.start(), m.end()))

    # 2. 自动标题匹配（最长优先，跳过代码块与语法链接占用的区间）
    #    自身标题也参与匹配（用于区间保护），但只记录不生成自链
    plain = _strip_code(content)
    candidates = sorted(
        (t for t in title_set if len(t) >= MIN_AUTO_TITLE_LEN),
        key=len,
        reverse=True,
    )
    matched_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
        return any(s <= start < e for s, e in spans)

    for title in candidates:
        for m in re.finditer(re.escape(title), plain):
            start, end = m.start(), m.end()
            if _overlaps(start, end, matched_spans) or _overlaps(start, end, syntax_spans):
                continue
            matched_spans.append((start, end))
            if title != own_title:
                results.append((title, "auto"))
            break  # 每个标题只记一条连接

    return results


async def rebuild_all_links(session: AsyncSession) -> int:
    """全量重建链接表（串行化）。返回新增链接数。"""
    async with loop_lock("links_rebuild"):
        result = await session.execute(
            select(Document.id, Document.title, Document.content_md).where(
                Document.is_deleted == False
            )
        )
        docs = result.all()
        titles = [d.title for d in docs]

        await session.execute(text("DELETE FROM document_links"))

        # 目标标题 → 目标 id
        title_to_id = {d.title: d.id for d in docs}

        # 按 (from, to) 去重，syntax 优先于 auto
        pairs: dict[tuple[int, int], str] = {}
        for doc_id, title, content in docs:
            for target_title, source in extract_links(content, title, titles):
                target_id = title_to_id.get(target_title)
                if target_id is None or target_id == doc_id:
                    continue
                key = (doc_id, target_id)
                if key not in pairs or source == "syntax":
                    pairs[key] = source

        for (from_id, to_id), source in pairs.items():
            session.add(DocumentLink(from_doc_id=from_id, to_doc_id=to_id, source=source))

        await session.commit()
        logger.info(f"链接重建完成，共 {len(pairs)} 条")
        return len(pairs)


async def rebuild_links_for_document(session: AsyncSession, doc_id: int) -> int:
    """只重建某一篇文档的出边。

    正文变化时其它文档的标题集合没变，没必要整表重扫 —— 这是编辑文档最常走的路径。
    """
    async with loop_lock("links_rebuild"):
        rows = (
            await session.execute(
                select(Document.id, Document.title, Document.content_md).where(
                    Document.is_deleted == False
                )
            )
        ).all()

        await session.execute(delete(DocumentLink).where(DocumentLink.from_doc_id == doc_id))

        doc = next((r for r in rows if r[0] == doc_id), None)
        if doc is None:
            await session.commit()
            return 0

        title_to_id = {row[1]: row[0] for row in rows}
        titles = list(title_to_id.keys())
        added = 0
        seen: set[int] = set()
        for target_title, source in extract_links(doc[2], doc[1], titles):
            target_id = title_to_id.get(target_title)
            if not target_id or target_id == doc_id or target_id in seen:
                continue
            seen.add(target_id)
            session.add(DocumentLink(from_doc_id=doc_id, to_doc_id=target_id, source=source))
            added += 1

        await session.commit()
        logger.info(f"文档 {doc_id} 链接重建完成，共 {added} 条")
        return added


# ---- 重建调度：把短时间内的多次请求合并成一次，避免 N 次上传触发 N 次全表扫描 ----

_sched_guard = threading.Lock()
_pending_full = False
_pending_docs: set[int] = set()
_worker: "asyncio.Task | None" = None


def schedule_rebuild(full: bool = False, doc_id: int | None = None) -> None:
    """把重建请求排进队列；真正执行时合并连续请求。"""
    global _pending_full, _worker
    with _sched_guard:
        if full:
            _pending_full = True
        elif doc_id is not None:
            _pending_docs.add(doc_id)
        else:
            return
        if _worker is None or _worker.done():
            _worker = asyncio.create_task(_drain_rebuilds())


async def _drain_rebuilds() -> None:
    global _pending_full
    while True:
        with _sched_guard:
            if _pending_full:
                full, docs = True, set()
                _pending_full = False
                _pending_docs.clear()
            elif _pending_docs:
                full, docs = False, set(_pending_docs)
                _pending_docs.clear()
            else:
                return
        try:
            async with async_session() as session:
                if full:
                    await rebuild_all_links(session)
                else:
                    for doc_id in docs:
                        await rebuild_links_for_document(session, doc_id)
        except Exception as e:
            logger.error(f"链接重建失败: {e}", exc_info=True)
