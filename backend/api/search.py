import logging
import re
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_session
from backend.db.schemas import SearchResponse, SearchResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

# FTS5 特殊字符：双引号、括号、冒号、脱字符、波浪号、星号、加减号等
_FTS_SPECIAL = re.compile(r'["()*:^~+\-]')


def build_fts_query(q: str) -> tuple[str | None, list[str]]:
    """拆分用户查询词。

    FTS 索引使用 trigram 分词器（中文子串匹配）：
    - 长度 >= 3 的词走 MATCH（子串命中，可高亮）
    - 长度 1-2 的词 MATCH 不生效，走 LIKE 兜底
    """
    long_terms: list[str] = []
    short_terms: list[str] = []
    for raw in q.split():
        term = _FTS_SPECIAL.sub("", raw).strip()
        if not term:
            continue
        if len(term) >= 3:
            long_terms.append(term)
        else:
            short_terms.append(term)
    match_clause = " AND ".join(long_terms) if long_terms else None
    return match_clause, short_terms


def _make_snippet(text: str, terms: list[str], radius: int = 60) -> str:
    """LIKE 路径没有 FTS 位置信息，手工生成高亮摘要"""
    if not text:
        return ""
    pos = -1
    for term in terms:
        idx = text.find(term)
        if idx != -1:
            pos = idx
            break
    if pos == -1:
        return text[:120]
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    seg = text[start:end]
    if start > 0:
        seg = "..." + seg
    if end < len(text):
        seg = seg + "..."
    for term in terms:
        seg = seg.replace(term, f"<mark>{term}</mark>")
    return seg


@router.get("", response_model=SearchResponse)
async def fulltext_search(
    q: str,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
):
    if not q or not q.strip():
        return SearchResponse(total=0, results=[])

    match_clause, short_terms = build_fts_query(q)
    if not match_clause and not short_terms:
        return SearchResponse(total=0, results=[])

    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    # 组装 WHERE：MATCH(长词) AND LIKE(短词)，并过滤已删除文档
    conditions = ["d.is_deleted = 0"]
    params: dict = {}
    if match_clause:
        conditions.append("documents_fts MATCH :q")
        params["q"] = match_clause
    for i, term in enumerate(short_terms):
        p_title, p_content = f"t{i}_title", f"t{i}_content"
        conditions.append(
            f"(documents_fts.title LIKE :{p_title} OR documents_fts.content_md LIKE :{p_content})"
        )
        params[p_title] = f"%{term}%"
        params[p_content] = f"%{term}%"

    where_sql = " AND ".join(conditions)

    total_result = await session.execute(
        text(f"""
            SELECT count(*)
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE {where_sql}
        """),
        params,
    )
    total = total_result.scalar() or 0

    if match_clause:
        snippet_expr = "snippet(documents_fts, 1, '<mark>', '</mark>', '...', 12) as snippet"
        rank_expr = "documents_fts.rank"
        order_expr = "documents_fts.rank"
    else:
        snippet_expr = "documents_fts.content_md as snippet"
        rank_expr = "0 as rank"
        order_expr = "documents_fts.rowid"

    fts_result = await session.execute(
        text(f"""
            SELECT documents_fts.rowid, {rank_expr}, documents_fts.title, {snippet_expr}
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE {where_sql}
            ORDER BY {order_expr}
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset},
    )

    rows = fts_result.fetchall()
    results = []
    for row in rows:
        snippet = row[3] or ""
        if not match_clause:
            snippet = _make_snippet(snippet, short_terms)
        results.append(SearchResult(
            id=row[0], title=row[2] or "", snippet=snippet, rank=row[1] or 0,
        ))

    return SearchResponse(total=total, results=results)
