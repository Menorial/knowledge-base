"""核心纯函数测试：不需要数据库、模型或网络。"""
from backend.api.search import _escape_like, build_fts_query
from backend.services.chunker import chunk_markdown
from backend.services.links import extract_links
from backend.services.rag import _question_terms


def test_chunk_split_by_heading():
    md = "# 一级标题\n\n段落一\n\n## 二级标题\n\n段落二"
    chunks = chunk_markdown(md)
    assert chunks
    paths = [c.section_path for c in chunks]
    assert "一级标题" in paths
    assert any("二级标题" in p for p in paths)


def test_chunk_long_section_splits():
    long_text = "句子。" * 500
    chunks = chunk_markdown("# 标题\n\n" + long_text, max_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.content) <= 260 for c in chunks)


def test_explicit_link_syntax():
    links = extract_links("参见 [[目标文档]] 的说明", "来源文档", ["来源文档", "目标文档"])
    assert ("目标文档", "syntax") in links


def test_auto_title_link_skips_code_block():
    content = "正文提到了目标文档。\n\n```\n目标文档\n```"
    links = extract_links(content, "来源文档", ["来源文档", "目标文档"])
    assert ("目标文档", "auto") in links


def test_no_self_link():
    links = extract_links("来源文档 来源文档 来源文档", "来源文档", ["来源文档"])
    assert links == []


def test_fts_query_splits_special_chars():
    # 连字符必须当分隔符：否则会拼成 "验证文档临时" 这个不存在的 trigram
    match, short = build_fts_query("验证文档-临时")
    assert match == "验证文档"
    assert short == ["临时"]


def test_fts_query_splits_two_long_terms():
    match, short = build_fts_query("prompt-engineering")
    assert match == "prompt AND engineering"
    assert short == []


def test_fts_query_short_terms_fallback():
    match, short = build_fts_query("AI 库")
    assert match is None
    assert short == ["AI", "库"]


def test_like_wildcard_escaping():
    assert _escape_like("50%") == "50\\%"
    assert _escape_like("a_b") == "a\\_b"


def test_question_terms():
    terms = _question_terms("什么是 Prompt Engineering？")
    assert "Prompt" in terms
    assert "Engineering" in terms
    assert all(len(t) >= 2 for t in terms)
