from unittest.mock import Mock, patch

from services.port_scanner import scan_open_ports


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_expected_only(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1))\n'
                'LISTEN 0 128 0.0.0.0:443 0.0.0.0:* users:(("xray",pid=2))\n'
            )
        ),
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
    ]

    text = scan_open_ports()

    assert "22/tcp" in text
    assert "443/tcp" in text
    assert "Подозрительных портов не обнаружено" in text
    assert "Ожидаемых: 2" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_with_suspicious(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'LISTEN 0 128 0.0.0.0:9999 0.0.0.0:* users:(("python",pid=5))\n'
            )
        ),
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
    ]

    text = scan_open_ports()

    assert "9999/tcp" in text
    assert "python" in text
    assert "Подозрительные порты" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_udp(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'UNCONN 0 0 0.0.0.0:58352 0.0.0.0:* users:(("awg",pid=7))\n'
            )
        ),
    ]

    text = scan_open_ports()

    assert "58352/udp" in text
    assert "AmneziaWG" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_remove_duplicates(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1))\n'
                'LISTEN 0 128 [::]:22 [::]:* users:(("sshd",pid=1))\n'
            )
        ),
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
    ]

    text = scan_open_ports()

    assert "Всего открытых: 1" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_skip_non_listen(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'ESTAB 0 0 1.1.1.1:22 2.2.2.2:3333 users:(("sshd",pid=1))\n'
            )
        ),
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
    ]

    text = scan_open_ports()

    assert "Всего открытых: 0" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_unknown_process(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                "LISTEN 0 128 0.0.0.0:9999 0.0.0.0:*\n"
            )
        ),
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
    ]

    text = scan_open_ports()

    assert "unknown" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_udp_skips_wildcard(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'UNCONN 0 0 *:5353 0.0.0.0:* users:(("dns",pid=8))\n'
            )
        ),
    ]

    text = scan_open_ports()

    assert "Всего открытых: 0" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_udp_skips_non_wildcard_address(mock_run):
    mock_run.side_effect = [
        Mock(
            stdout="State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        ),
        Mock(
            stdout=(
                "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
                'UNCONN 0 0 127.0.0.1:5353 0.0.0.0:* users:(("dns",pid=10))\n'
            )
        ),
    ]

    text = scan_open_ports()

    assert "Всего открытых: 0" in text


@patch("services.port_scanner.subprocess.run")
def test_scan_ports_exception(mock_run):
    mock_run.side_effect = Exception("boom")

    text = scan_open_ports()

    assert "Ошибка сканирования" in text
    assert "boom" in text
