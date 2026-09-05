import os
import stat

from utils.atomic import atomic_write


def test_atomic_write_preserves_permissions(tmp_path):

    f = tmp_path / "test.conf"

    f.write_text("old")

    os.chmod(f, 0o600)

    atomic_write(f, "new content")

    assert f.read_text() == "new content"

    mode = stat.S_IMODE(f.stat().st_mode)

    assert mode == 0o600


def test_atomic_write_new_file(tmp_path):

    f = tmp_path / "new.conf"

    atomic_write(f, "hello")

    assert f.exists()
    assert f.read_text() == "hello"

    mode = stat.S_IMODE(f.stat().st_mode)

    assert mode == 0o600


def test_atomic_write_replace_failure_preserves_original(tmp_path, monkeypatch):
    f = tmp_path / "test.conf"
    f.write_text("old content", encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    import pytest

    with pytest.raises(OSError, match="replace failed"):
        atomic_write(f, "new content")

    assert f.read_text(encoding="utf-8") == "old content"
    assert list(tmp_path.glob(".test.conf.*")) == []
