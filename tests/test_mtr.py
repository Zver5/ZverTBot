import asyncio

from services.network import mtr


class FakeProcess:
    def __init__(self, stdout=b"", stderr=b""):
        self.stdout = stdout
        self.stderr = stderr
        self.killed = False
        self.communicate_calls = 0

    async def communicate(self):
        self.communicate_calls += 1
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True


def test_run_mtr_success(monkeypatch):
    proc = FakeProcess(stdout=b"mtr output\n")

    async def fake_create(*args, **kwargs):
        assert args == (
            "mtr",
            "-n",
            "-r",
            "-c",
            str(mtr.PACKETS),
            "-m",
            str(mtr.MAX_HOPS),
            "8.8.8.8",
        )
        assert kwargs["stdout"] is asyncio.subprocess.PIPE
        assert kwargs["stderr"] is asyncio.subprocess.PIPE
        return proc

    async def fake_wait_for(awaitable, timeout):
        assert timeout == mtr.MTR_TIMEOUT
        return await awaitable

    monkeypatch.setattr(
        mtr.asyncio,
        "create_subprocess_exec",
        fake_create,
    )
    monkeypatch.setattr(
        mtr.asyncio,
        "wait_for",
        fake_wait_for,
    )

    result = asyncio.run(mtr.run_mtr("8.8.8.8"))

    assert result == "mtr output\n"
    assert proc.communicate_calls == 1
    assert proc.killed is False


def test_run_mtr_stderr(monkeypatch):
    proc = FakeProcess(stderr=b"permission denied\n")

    async def fake_create(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        return await awaitable

    monkeypatch.setattr(
        mtr.asyncio,
        "create_subprocess_exec",
        fake_create,
    )
    monkeypatch.setattr(
        mtr.asyncio,
        "wait_for",
        fake_wait_for,
    )

    result = asyncio.run(mtr.run_mtr("example.com"))

    assert result == "❌ mtr error: permission denied"


def test_run_mtr_timeout(monkeypatch):
    proc = FakeProcess()

    async def fake_create(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(
        mtr.asyncio,
        "create_subprocess_exec",
        fake_create,
    )
    monkeypatch.setattr(
        mtr.asyncio,
        "wait_for",
        fake_wait_for,
    )

    result = asyncio.run(mtr.run_mtr("8.8.8.8"))

    assert result == "❌ MTR timeout"
    assert proc.killed is True
    assert proc.communicate_calls == 1


def test_run_mtr_system_error(monkeypatch):
    async def fake_create(*args, **kwargs):
        raise OSError("mtr not found")

    monkeypatch.setattr(
        mtr.asyncio,
        "create_subprocess_exec",
        fake_create,
    )

    result = asyncio.run(mtr.run_mtr("8.8.8.8"))

    assert result == "❌ system error: mtr not found"


def test_parse_mtr_valid_output():
    output = """
HOST: example.com
Loss%  Snt  Last  Avg  Best  Wrst  StDev
  1.  10.0.0.1     0.0%   10   1.0   2.0   0.5   3.0   0.2
  2.  192.168.1.1  5.0%   10   8.0  12.5   7.0  20.0   3.1
"""

    result = mtr.parse_mtr(output)

    assert result == [
        {
            "hop": "1",
            "ip": "10.0.0.1",
            "loss": 0.0,
            "avg": 2.0,
        },
        {
            "hop": "2",
            "ip": "192.168.1.1",
            "loss": 5.0,
            "avg": 12.5,
        },
    ]


def test_parse_mtr_ignores_invalid_lines():
    output = """
HOST: example.com
Loss%  Snt  Last  Avg  Best  Wrst  StDev

invalid line
foo
2. no-ip-here 0.0% 10 1.0 2.0
3. 10.0.0.3 0.0% 10 4.0 5.0 3.0 6.0 1.0
"""

    result = mtr.parse_mtr(output)

    assert result == [
        {
            "hop": "3",
            "ip": "10.0.0.3",
            "loss": 0.0,
            "avg": 5.0,
        }
    ]


def test_parse_mtr_empty_output():
    assert mtr.parse_mtr("") == []


def test_parse_mtr_whitespace_only():
    assert mtr.parse_mtr("   \n\n   ") == []


def test_parse_mtr_missing_loss_defaults_to_zero():
    output = "3. 10.0.0.3 10 4.0 5.0 3.0 6.0 1.0"

    result = mtr.parse_mtr(output)

    assert result == [
        {
            "hop": "3",
            "ip": "10.0.0.3",
            "loss": 0.0,
            "avg": 5.0,
        }
    ]


def test_analyze_empty():
    assert mtr.analyze([]) == "❌ Нет данных"


def test_analyze_packet_loss():
    data = [
        {"hop": "1", "ip": "10.0.0.1", "loss": 25.0, "avg": 10.0},
    ]

    assert mtr.analyze(data) == "🚨 Потери на хопе 1 (10.0.0.1)"


def test_analyze_high_latency():
    data = [
        {"hop": "1", "ip": "10.0.0.1", "loss": 0.0, "avg": 151.0},
    ]

    assert mtr.analyze(data) == "⚠️ Высокая задержка"


def test_analyze_stable():
    data = [
        {"hop": "1", "ip": "10.0.0.1", "loss": 0.0, "avg": 20.0},
        {"hop": "2", "ip": "10.0.0.2", "loss": 1.0, "avg": 80.0},
    ]

    assert mtr.analyze(data) == "✅ Маршрут стабилен"


def test_format_mtr_empty():
    assert mtr.format_mtr([], "8.8.8.8") == "❌ Нет данных"


def test_format_mtr_contains_expected_data():
    data = [
        {"hop": "1", "ip": "10.0.0.1", "loss": 0.0, "avg": 12.5},
        {"hop": "2", "ip": "10.0.0.2", "loss": 3.0, "avg": 45.2},
        {"hop": "3", "ip": "10.0.0.3", "loss": 7.0, "avg": 200.0},
    ]

    result = mtr.format_mtr(data, "example.com")

    assert "<pre>" in result
    assert "</pre>" in result
    assert "📡 <b>MTR диагностика</b>" in result
    assert "🎯 <code>example.com</code>" in result
    assert "1 | 10.0.0.1 | 🟢 0.0% | 12.5" in result
    assert "2 | 10.0.0.2 | 🟡 3.0% | 45.2" in result
    assert "3 | 10.0.0.3 | 🔴 7.0% | 200.0" in result


def test_diagnose_mtr_error(monkeypatch):
    async def fake_run_mtr(target):
        assert target == "8.8.8.8"
        return "❌ MTR timeout"

    monkeypatch.setattr(mtr, "run_mtr", fake_run_mtr)

    result = asyncio.run(mtr.diagnose("8.8.8.8"))

    assert result == "❌ MTR timeout"


def test_diagnose_success(monkeypatch):
    raw = """
Loss%  Snt  Last  Avg  Best  Wrst  StDev
1. 10.0.0.1 0.0% 10 1.0 20.0 0.5 30.0 0.2
"""

    async def fake_run_mtr(target):
        assert target == "8.8.8.8"
        return raw

    monkeypatch.setattr(mtr, "run_mtr", fake_run_mtr)

    result = asyncio.run(mtr.diagnose("8.8.8.8"))

    assert "<pre>" in result
    assert "🎯 <code>8.8.8.8</code>" in result
    assert "1 | 10.0.0.1 | 🟢 0.0% | 20.0" in result


def test_main_module_can_be_executed(monkeypatch):
    logged = []

    async def fake_diagnose(target):
        assert target == "8.8.8.8"
        return "test result"

    monkeypatch.setattr(mtr, "diagnose", fake_diagnose)
    monkeypatch.setattr(
        mtr.logger,
        "debug",
        lambda value: logged.append(value),
    )

    async def invoke_main():
        await mtr.diagnose("8.8.8.8")

    asyncio.run(invoke_main())

    assert logged == []


def test_parse_mtr_ip_not_in_parts():
    """Покрытие строк 89-90: IP найден regex, но отсутствует в parts"""
    from services.network import mtr

    output = "1. (1.2.3.4) 50.0% 1.0 2.0 3.0"
    result = mtr.parse_mtr(output)

    assert result == []


def test_parse_mtr_loss_index_stop_iteration(monkeypatch):
    """Покрытие строк 102-103: loss_match есть, но loss_index не найден"""
    from services.network import mtr

    class MockLossRe:
        def search(self, line):
            class MockMatch:
                def group(self, idx):
                    return "50.0"

            return MockMatch()

    monkeypatch.setattr(mtr, "LOSS_RE", MockLossRe())

    output = "1. 1.2.3.4 1.0 2.0 3.0 4.0"
    result = mtr.parse_mtr(output)

    assert len(result) == 1
    assert result[0]["avg"] == 0.0


def test_parse_mtr_avg_index_error_with_loss():
    """Покрытие строк 102-103: IndexError при parts[loss_index + 3]"""
    from services.network import mtr

    output = "1. 1.2.3.4 50.0% 1.0"
    result = mtr.parse_mtr(output)

    assert len(result) == 1
    assert result[0]["avg"] == 0.0


def test_parse_mtr_avg_index_error_without_loss():
    """Покрытие строк 107-108: IndexError при parts[ip_index + 3]"""
    from services.network import mtr

    output = "1. 1.2.3.4"
    result = mtr.parse_mtr(output)

    assert len(result) == 1
    assert result[0]["avg"] == 0.0
