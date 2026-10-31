"""测试环境隔离：不写项目里的 data/，也不加载任何模型。"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="kb-tests-"))
os.environ.setdefault("DB_PATH", str(_TMP / "knowledge.db"))
os.environ.setdefault("FILE_STORAGE_DIR", str(_TMP / "files"))
os.environ.setdefault("BACKUP_DIR", str(_TMP / "backup"))
os.environ.setdefault("AI_API_KEY", "")
