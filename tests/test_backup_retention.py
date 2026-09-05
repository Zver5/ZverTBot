from pathlib import Path

SCRIPT = Path("scripts/backup-to-yandex.sh").read_text()


def test_local_retention_sorts_newest_first():
    assert (
        """        -printf '%T@ %p\\n' \\
        2>/dev/null | sort -nr
"""
        in SCRIPT
    )


def test_remote_retention_sorts_newest_first():
    assert (
        """    awk '/vps-backup-.*\\.tar.gz/ {print}' "${REMOTE_BACKUPS_FILE}" | sort -r
"""
        in SCRIPT
    )
