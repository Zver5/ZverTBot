import tarfile
from pathlib import Path


def get_archive_names(deploy_archive):
    with tarfile.open(deploy_archive) as tar:
        return tar.getnames()


def test_archive_has_no_secrets(deploy_archive):
    names = get_archive_names(deploy_archive)

    forbidden_names = [
        ".env",
        ".env.local",
        ".env.production",
        ".env.backup",
        "authorized_keys",
        "id_rsa",
        "id_ed25519",
    ]

    forbidden_suffixes = [
        ".pem",
        ".key",
        ".token",
    ]

    found = []

    for name in names:
        path = Path(name)
        filename = path.name

        if filename in forbidden_names:
            found.append(name)

        for suffix in forbidden_suffixes:
            if filename.endswith(suffix):
                found.append(name)

    assert not found, f"Possible secrets found in archive: {found}"


def test_archive_contains_required_deploy_parts(deploy_archive):
    names = get_archive_names(deploy_archive)

    required = [
        "deploy/botinstaller/install.sh",
        "deploy/botinstaller/packages.txt",
        "deploy/botinstaller/system_tuning.sh",
        "deploy/botinstaller/systemd/",
    ]

    missing = []

    for item in required:
        if not any(item in name for name in names):
            missing.append(item)

    assert not missing, f"Missing required deploy content: {missing}"


def test_archive_is_free_from_development_files(deploy_archive):
    names = get_archive_names(deploy_archive)

    forbidden = [
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".git/",
        ".coverage",
    ]

    found = []

    for bad in forbidden:
        for name in names:
            if bad in name:
                found.append(name)

    assert not found, f"Development files found in archive: {found}"


def test_archive_contains_no_secret_values(deploy_archive):

    dangerous_patterns = [
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
    ]

    import re

    telegram_token = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")

    found = []

    with tarfile.open(deploy_archive) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue

            # Сам тест содержит шаблоны приватных ключей.
            # Это не реальные секреты.
            if member.name == "ZverTBot/tests/test_deploy_security.py":
                continue

            # читаем только текстовые файлы
            try:
                data = tar.extractfile(member)
                if not data:
                    continue

                text = data.read().decode("utf-8", errors="ignore")

            except Exception:
                continue

            for pattern in dangerous_patterns:
                if pattern in text:
                    found.append(f"{member.name}: {pattern}")

            if telegram_token.search(text):
                found.append(f"{member.name}: Telegram token pattern")

    assert not found, f"Possible secret values found: {found}"
