"""
Атомарная запись файлов.

Используется для критичных конфигов:
- Xray config.json
- AmneziaWG awg0.conf
- другие файлы, где нельзя допустить частичную запись
"""

import os
import tempfile
from pathlib import Path


def atomic_write(path: str | Path, content: str) -> None:

    path = Path(path)

    old_uid = os.getuid()
    old_gid = os.getgid()
    old_mode = 0o600

    if path.exists():
        st = path.stat()
        old_uid = st.st_uid
        old_gid = st.st_gid
        old_mode = st.st_mode & 0o7777

    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.chown(tmp_path, old_uid, old_gid)
        os.chmod(tmp_path, old_mode)

        os.replace(tmp_path, path)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
