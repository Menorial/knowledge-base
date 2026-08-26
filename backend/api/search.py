import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.database import get_session
from backend.db.schemas import SearchResponse, SearchResult
from backend.db.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def fulltext_search(
    q: str,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
):
    if not q or not q.strip():
        return SearchResponse(total=0, results=[])

    query = q.strip().replace(" ", "* ") + "*"
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    total_result = await session.execute(
        text("SELECT count(*) FROM documents_fts WHERE documents_fts MATCH :q"),
        {"q": query},
    )
    total = total_result.scalar() or 0

    fts_result = await session.execute(
        text("""
            SELECT rowid, rank, title, snippet(documents_fts, 1, '<mark>', '</mark>', '...', 12) as snippet
            FROM documents_fts
            WHERE documents_fts MATCH :q
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """),
        {"q": query, "limit": page_size, "offset": offset},
    )

    rows = fts_result.fetchall()
    doc_ids = [row[0] for row in rows]

    results = []
    for row in rows:
        results.append(SearchResult(
            id=row[0],
            title=row[2] or "",
            snippet=row[3] or "",
            rank=row[1] or 0,
        ))

    return SearchResponse(total=total, results=results)
