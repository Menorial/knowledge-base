"""网页剪藏管线：正文提取 + 图片本地化 + Markdown 转换。

- 正文提取：readability-lxml（按文本密度找文章主体，去导航/广告/页脚）；
  未安装或提取失败时回退整页转换。
- 图片本地化：把正文里的远程图片下载到 files/clip/{doc_id}/，
  markdown 引用改为本地静态路径 /files/clip/{doc_id}/{fname}。
"""
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_IMG_RE = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', re.I)

MAX_IMG_BYTES = 5 * 1024 * 1024
ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}

_CLIP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _strip_noise(html: str) -> str:
    """删除明显非正文的标签：导航/页脚/侧边栏/广告/脚本/样式/iframe/评论等"""
    try:
        from lxml import html as lh

        root = lh.fromstring(html)
        # 标签名匹配
        for tag in root.xpath(
            "//nav | //footer | //aside | //script | //style | //iframe "
            "| //noscript | //form | //canvas"
        ):
            parent = tag.getparent()
            if parent is not None:
                parent.remove(tag)
        # class / id 特征匹配
        for el in root.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' ad ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' ads ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' banner ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' sidebar ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' recommend ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' related ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' comment ') "
            "or contains(concat(' ', normalize-space(@class), ' '), ' copyright ') "
            "or contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'advert') "
            "or contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'advert')]"
        ):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
        return lh.tostring(root, encoding="unicode")
    except Exception as e:
        logger.warning(f"噪声标签清洗失败，跳过: {e}")
        return html


def extract_main_html(html: str, url: str = "") -> str:
    """提取网页正文 HTML（先删噪声标签，再按文本密度找主体）；失败回退整页"""
    cleaned = _strip_noise(html)
    try:
        from readability import Document

        doc = Document(cleaned, url=url)
        summary = doc.summary()
        if summary and len(summary) > 200:
            return summary
        logger.warning("readability 提取内容过短，回退整页")
    except Exception as e:
        logger.warning(f"readability 提取失败，回退整页: {e}")
    return cleaned


def _img_ext_from_url(src: str) -> str | None:
    path = src.split("?", 1)[0].split("#", 1)[0]
    ext = Path(path).suffix.lower()
    return ext if ext in ALLOWED_IMG_EXTS else None


async def localize_images(html: str, page_url: str, save_dir: Path) -> str:
    """下载正文中的远程图片到 save_dir，并把 src 替换为本地静态路径"""
    srcs = _IMG_RE.findall(html)
    if not srcs:
        return html

    import httpx

    save_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": _CLIP_UA}
    if page_url:
        headers["Referer"] = page_url  # 防防盗链

    replaced: dict[str, str] = {}
    client = httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers)
    try:
        for src in dict.fromkeys(srcs):  # 去重
            if src.startswith("data:"):
                continue  # base64 内嵌图保持原样
            abs_url = urljoin(page_url, src) if page_url else src
            if not abs_url.startswith(("http://", "https://")):
                continue
            try:
                async with client.stream("GET", abs_url) as resp:
                    if resp.status_code != 200:
                        continue
                    ctype = resp.headers.get("content-type", "")
                    if not ctype.lower().startswith("image/"):
                        continue
                    data = bytearray()
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_IMG_BYTES:
                            data = bytearray()
                            break
                        data.extend(chunk)
                    if not data:
                        continue
                    ext = _img_ext_from_url(abs_url) or ".png"
                    fname = f"{uuid.uuid4().hex[:12]}{ext}"
                    (save_dir / fname).write_bytes(bytes(data))
                    # 静态路径：/files/clip/{doc_id}/{fname}
                    replaced[src] = f"/files/clip/{save_dir.name}/{fname}"
                    logger.info(f"剪藏图片已保存: {fname} ({size} bytes)")
            except Exception as e:
                logger.warning(f"图片下载失败 {abs_url[:80]}: {e}")
    finally:
        await client.aclose()

    for src, local in replaced.items():
        html = (
            html.replace(f'src="{src}"', f'src="{local}"')
            .replace(f"src='{src}'", f"src='{local}'")
        )
    return html
