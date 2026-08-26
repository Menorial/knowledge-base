"""数据库与原始文件的自动备份。

- 使用 SQLite 在线备份 API 生成一致性快照（WAL 模式下也安全）
- 同时拷贝 data/files 原始文件目录
- 按 BACKUP_KEEP_DAYS 自动清理过期备份
"""
import logging
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)


def run_backup() -> Path | None:
    """执行一次完整备份，返回备份目录；失败返回 None"""
    try:
        backup_root = settings.backup_abs_path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_root / ts
        target.mkdir(parents=True, exist_ok=True)

        # SQLite 在线备份，保证数据一致性
        src = sqlite3.connect(str(settings.db_abs_path))
        try:
            dst = sqlite3.connect(str(target / "knowledge.db"))
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()

        # 拷贝原始文件
        if settings.file_storage_abs.exists():
            shutil.copytree(settings.file_storage_abs, target / "files", dirs_exist_ok=True)

        (target / "backup.info").write_text(
            f"created_at={datetime.now().isoformat()}\n"
            f"size_bytes={_dir_size(target)}\n",
            encoding="utf-8",
        )

        _cleanup_old()
        logger.info(f"备份完成: {target}")
        return target
    except Exception as e:
        logger.error(f"备份失败: {e}", exc_info=True)
        return None


def list_backups() -> list[dict]:
    backup_root = settings.backup_abs_path
    items = []
    if backup_root.exists():
        for p in sorted(backup_root.iterdir(), reverse=True):
            if not p.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
            except OSError:
                continue
            items.append({
                "name": p.name,
                "created_at": mtime.isoformat(),
                "size_bytes": _dir_size(p),
            })
    return items


def delete_backup(name: str) -> bool:
    backup_root = settings.backup_abs_path
    target = backup_root / name
    try:
        if not str(target.resolve()).startswith(str(backup_root.resolve())):
            return False
    except Exception:
        return False
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
        return True
    return False


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _cleanup_old():
    keep_days = max(1, settings.BACKUP_KEEP_DAYS)
    cutoff = datetime.now() - timedelta(days=keep_days)
    backup_root = settings.backup_abs_path
    if not backup_root.exists():
        return
    for p in backup_root.iterdir():
        if not p.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(p, ignore_errors=True)
                logger.info(f"清理过期备份: {p.name}")
        except Exception:
            continue
