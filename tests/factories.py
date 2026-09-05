from unittest.mock import Mock


def fake_process(
    user="root",
    pid="123",
    cpu=10.5,
    mem=5.0,
    rss=150,
    command="python bot.py",
):
    return {
        "user": user,
        "pid": pid,
        "cpu": cpu,
        "mem": mem,
        "rss": rss,
        "command": command,
    }


def fake_completed_process(returncode=0, stdout="", stderr=""):
    return Mock(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def fake_usage_client(
    uplink=100,
    downlink=200,
    total=300,
):
    return {
        "uplink": uplink,
        "downlink": downlink,
        "total": total,
    }
