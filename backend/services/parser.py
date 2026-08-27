from abc import ABC, abstractmethod
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> str:
        ...


class MarkdownParser(BaseParser):
    def parse(self, file_path: str) -> str:
        return Path(file_path).read_text(encoding="utf-8")


class TxtParser(BaseParser):
    def parse(self, file_path: str) -> str:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        md_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                md_lines.append(stripped)
            else:
                md_lines.append("")
        return "\n".join(md_lines)


class PDFParser(BaseParser):
    def parse(self, file_path: str) -> str:
        try:
            import fitz
        except ImportError:
            raise ParseError("PyMuPDF 未安装，请运行 pip install PyMuPDF")

        doc = fitz.open(file_path)
        parts = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                parts.append(text.strip())
        doc.close()

        if not parts:
            raise ParseError("PDF 中未提取到文本，可能是扫描件")

        md_lines = []
        for part in parts:
            for line in part.splitlines():
                stripped = line.strip()
                if stripped:
                    md_lines.append(stripped)
                else:
                    md_lines.append("")
        return "\n".join(md_lines)


class DocxParser(BaseParser):
    def parse(self, file_path: str) -> str:
        try:
            from docx import Document as DocxDocument
        except ImportError:
            raise ParseError("python-docx 未安装，请运行 pip install python-docx")

        doc = DocxDocument(file_path)
        parts = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                if para.style and para.style.name.startswith("Heading"):
                    level = para.style.name.replace("Heading", "").strip()
                    try:
                        level = max(1, min(6, int(level)))
                    except ValueError:
                        level = 1
                    parts.append(f"{'#' * level} {text}")
                else:
                    parts.append(text)
            else:
                parts.append("")

        for table in doc.tables:
            parts.append("")
            header = [cell.text.strip() for cell in table.rows[0].cells]
            parts.append("| " + " | ".join(header) + " |")
            parts.append("| " + " | ".join(["---"] * len(header)) + " |")
            for row in table.rows[1:]:
                cells = [cell.text.strip() for cell in row.cells]
                parts.append("| " + " | ".join(cells) + " |")
            parts.append("")

        return "\n".join(parts)


def html_to_markdown(html_content: str) -> str:
    """HTML → Markdown（网页剪藏与 HTMLParser 共用）"""
    try:
        import html2text
    except ImportError:
        raise ParseError("html2text 未安装，请运行 pip install html2text")

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0
    return h.handle(html_content).strip()


class HTMLParser(BaseParser):
    def parse(self, file_path: str) -> str:
        html_content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return html_to_markdown(html_content)


PARSERS: dict[str, BaseParser] = {
    ".md": MarkdownParser(),
    ".txt": TxtParser(),
    ".pdf": PDFParser(),
    ".docx": DocxParser(),
    ".html": HTMLParser(),
}


def parse_document(file_path: str, ext: str) -> tuple[str, str]:
    parser = PARSERS.get(ext.lower())
    if not parser:
        raise ParseError(f"不支持的文件格式: {ext}")
    try:
        content = parser.parse(file_path)
        if len(content.strip()) < 20:
            logger.warning(f"解析结果内容过少: {file_path}")
            return content.strip(), "partial"
        return content.strip(), "success"
    except ParseError:
        raise
    except Exception as e:
        logger.error(f"解析失败 {file_path}: {e}")
        raise ParseError(f"解析失败: {e}")
