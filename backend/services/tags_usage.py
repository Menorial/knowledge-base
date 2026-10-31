"""标签使用计数（tags.usage_count）的统一重算。

usage_count 是冗余字段：加/减标签时增量维护，但删除文档、彻底删除、
恢复等路径很容易漏减，时间一长统计和排序就会失真。
所有会改变「文档-标签」关联的写操作结束后调用一次，成本是一条 UPDATE。
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_RECOMPUTE_SQL = text(
    """
    UPDATE tags
    SET usage_count = (
        SELECT COUNT(*)
        FROM document_tags dt
        JOIN documents d ON d.id = dt.document_id
        WHERE dt.tag_id = tags.id AND d.is_deleted = 0
    )
    """
)


async def recompute_tag_usage(session: AsyncSession) -> None:
    """按「未删除文档的实际关联数」重算每个标签的 usage_count"""
    try:
        await session.execute(_RECOMPUTE_SQL)
        await session.commit()
    except Exception as e:
        logger.warning(f"标签计数重算失败: {e}")
