"""AI 自动打标签：根据文档内容用 LLM 生成 1-5 个标签并附加到文档。

触发时机：上传/新建/剪藏/编辑/回滚后随 _bg_summarize 后台执行。
规则：
- 未配置 AI_API_KEY 或内容过短时跳过
- 文档已有标签时跳过（尊重手动标签）
- 标签复用已存在的 Tag，并更新 usage_count
"""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.db.database import async_session
from backend.db.models import Document, Tag

logger = logging.getLogger(__name__)

_MAX_TAGS = 5
_MIN_CONTENT = 50

_TAG_PROMPT = (
    "你是知识库的标签助手。请根据下面的文档内容，生成 1 到 5 个简短标签（每个 2-6 个字，"
    "不要使用'教程''笔记''文档'等过于宽泛的词），用于分类检索。"
    "只输出标签，用英文逗号分隔，不要编号、不要多余解释。\n\n文档内容：\n{content}"
)


def _parse_tags(text: str) -> list[str]:
    """从 LLM 输出解析标签列表"""
    if not text:
        return []
    text = re.sub(r"^[#*\-\d\.、\s]+", "", text.strip())
    parts = re.split(r"[,，;；、\n]+", text)
    tags: list[str] = []
    for p in parts:
        t = p.strip().strip("#").strip()
        if not t or len(t) > 20:
            continue
        if t not in tags:
            tags.append(t)
    return tags[:_MAX_TAGS]


async def autotag_document(doc_id: int, content_md: str):
    """后台自动打标签（失败不影响主流程）"""
    try:
        if not settings.AI_API_KEY:
            return
        preview = (content_md or "").strip()
        if len(preview) < _MIN_CONTENT:
            return

        from backend.services.llm import llm_service

        text = await llm_service.chat([
            {"role": "system", "content": "你是知识库的标签助手，输出简洁准确的中文标签。"},
            {"role": "user", "content": _TAG_PROMPT.format(content=preview[:3000])},
        ])
        tags = _parse_tags(text or "")
        if not tags:
            return

        async with async_session() as session:
            result = await session.execute(
                select(Document)
                .where(Document.id == doc_id)
                .options(selectinload(Document.tags))
            )
            doc = result.scalar_one_or_none()
            if not doc or doc.is_deleted:
                return
            # 已有标签则跳过，尊重手动标签
            if doc.tags:
                return

            for tag_name in tags:
                tag_result = await session.execute(select(Tag).where(Tag.name == tag_name))
                tag = tag_result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)
                if tag not in doc.tags:
                    doc.tags.append(tag)
                    tag.usage_count = (tag.usage_count or 0) + 1

            await session.commit()
            logger.info(f"文档 {doc_id} 自动打标签: {', '.join(tags)}")
    except Exception as e:
        logger.warning(f"自动打标签失败 doc={doc_id}: {e}")
