from pathlib import Path

from config import paths


def test_awg_conf_from_env_has_priority(monkeypatch, tmp_path):
    explicit = tmp_path / "custom-awg.conf"
    explicit.write_text("[Interface]\n")

    monkeypatch.setenv("AWG_CONF", str(explicit))

    result = paths.resolve_awg_conf()

    assert result == explicit


def test_awg_conf_from_env_kept_even_when_file_missing(monkeypatch, tmp_path):
    explicit = tmp_path / "missing-awg.conf"

    monkeypatch.setenv("AWG_CONF", str(explicit))

    result = paths.resolve_awg_conf()

    assert result == explicit


def test_awg_conf_uses_native_path_without_env(monkeypatch):
    monkeypatch.delenv("AWG_CONF", raising=False)

    result = paths.resolve_awg_conf()

    assert result == Path("/etc/amnezia/amneziawg/awg0.conf")
