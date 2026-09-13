from services.awg.runtime import AwgPeerRuntime


def _peer(ip: str) -> AwgPeerRuntime:
    return AwgPeerRuntime(
        public_key=f"key-{ip}",
        endpoint="",
        allowed_ip=ip,
        rx_bytes=0,
        tx_bytes=0,
        latest_handshake="never",
    )


def test_get_used_awg_ips_from_registry(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(
        im,
        "load_awg_registry",
        lambda: {
            "user1": {"ip": "10.66.66.8"},
            "user2": {"ip": "10.66.66.9"},
        },
    )
    monkeypatch.setattr(
        "services.awg.runtime.get_runtime_peers",
        lambda: {},
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.8", "10.66.66.9"}


def test_get_used_awg_ips_from_running_config(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(im, "load_awg_registry", dict)
    monkeypatch.setattr(
        "services.awg.runtime.get_runtime_peers",
        lambda: {
            "key-20": _peer("10.66.66.20"),
            "key-30": _peer("10.66.66.30"),
        },
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.20", "10.66.66.30"}


def test_get_used_awg_ips_combines_sources(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(
        im,
        "load_awg_registry",
        lambda: {"user": {"ip": "10.66.66.8"}},
    )
    monkeypatch.setattr(
        "services.awg.runtime.get_runtime_peers",
        lambda: {"key": _peer("10.66.66.9")},
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.8", "10.66.66.9"}


def test_find_free_awg_ip(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(
        im,
        "get_used_awg_ips",
        lambda: {"10.66.66.8", "10.66.66.9"},
    )

    result = im.find_free_awg_ip()

    assert result == "10.66.66.10"


def test_find_free_awg_ip_when_full(monkeypatch):
    from services.awg import ip_manager as im

    used = {f"10.66.66.{i}" for i in range(8, 100)}

    monkeypatch.setattr(im, "get_used_awg_ips", lambda: used)

    result = im.find_free_awg_ip()

    assert result is None


def test_get_used_awg_ips_runtime_failure(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(
        im,
        "load_awg_registry",
        lambda: {"user1": {"ip": "10.66.66.8"}},
    )

    def raise_exception():
        raise RuntimeError("awg command failed")

    monkeypatch.setattr(
        "services.awg.runtime.get_runtime_peers",
        raise_exception,
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.8"}
