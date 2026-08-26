import uuid
from pathlib import Path
from typing import Tuple
from backend.config import settings


class ValidationError(Exception):
    pass


def validate_file(filename: str, size: int) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions_set:
        raise ValidationError(
            f"不支持的文件格式 {ext}，允许的格式：{settings.ALLOWED_EXTENSIONS}"
        )
    if size > settings.MAX_FILE_SIZE:
        max_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
        raise ValidationError(f"文件大小超过限制（{max_mb}MB）")


def safe_save_filename(original_filename: str) -> Tuple[str, str]:
    ext = Path(original_filename).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return safe_name, ext


def safe_store_path(filename: str) -> Path:
    target = settings.file_storage_abs / filename
    if not str(target.resolve()).startswith(str(settings.file_storage_abs.resolve())):
        raise ValidationError("非法文件路径")
    return target
