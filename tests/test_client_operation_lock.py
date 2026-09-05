import subprocess
import sys
import time

from utils.client_operation_lock import client_operation_lock


def test_lock_is_released_after_exception():
    calls = []

    @client_operation_lock
    def failing():
        calls.append("inside")
        raise RuntimeError("boom")

    @client_operation_lock
    def succeeding():
        calls.append("after")

    try:
        failing()
    except RuntimeError:
        pass

    succeeding()

    assert calls == ["inside", "after"]


def test_lock_is_reentrant_in_same_thread():
    calls = []

    @client_operation_lock
    def outer():
        calls.append("outer-start")
        inner()
        calls.append("outer-end")

    @client_operation_lock
    def inner():
        calls.append("inner")

    outer()

    assert calls == ["outer-start", "inner", "outer-end"]


def test_lock_blocks_other_process(tmp_path):
    marker = tmp_path / "entered"

    child_code = """
import time
from pathlib import Path
from utils.client_operation_lock import client_operation_lock

marker = Path(__import__("os").environ["LOCK_TEST_MARKER"])

@client_operation_lock
def worker():
    marker.write_text("entered")
    time.sleep(0.3)

worker()
"""

    import os

    env = os.environ.copy()
    env["LOCK_TEST_MARKER"] = str(marker)

    process = None

    @client_operation_lock
    def first():
        nonlocal process

        process = subprocess.Popen(
            [sys.executable, "-c", child_code],
            env=env,
        )

        time.sleep(0.15)

        # Независимый процесс должен ждать освобождения flock.
        assert not marker.exists()

    first()

    process.wait(timeout=3)

    assert process.returncode == 0
    assert marker.read_text() == "entered"
