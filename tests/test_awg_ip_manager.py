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
        im.subprocess, "run", lambda *args, **kwargs: type("R", (), {"stdout": ""})()
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.8", "10.66.66.9"}


def test_get_used_awg_ips_from_running_config(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(im, "load_awg_registry", dict)

    output = """
peer ABC
    allowed ips: 10.66.66.20/32
peer DEF
    allowed ips: 10.66.66.30/32
"""

    monkeypatch.setattr(
        im.subprocess,
        "run",
        lambda *args, **kwargs: type("R", (), {"stdout": output})(),
    )

    result = im.get_used_awg_ips()

    assert "10.66.66.20" in result
    assert "10.66.66.30" in result


def test_get_used_awg_ips_combines_sources(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(im, "load_awg_registry", lambda: {"user": {"ip": "10.66.66.8"}})

    monkeypatch.setattr(
        im.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "R", (), {"stdout": "allowed ips: 10.66.66.9/32"}
        )(),
    )

    result = im.get_used_awg_ips()

    assert result == {"10.66.66.8", "10.66.66.9"}


def test_find_free_awg_ip(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(im, "get_used_awg_ips", lambda: {"10.66.66.8", "10.66.66.9"})

    result = im.find_free_awg_ip()

    assert result == "10.66.66.10"


def test_find_free_awg_ip_when_full(monkeypatch):
    from services.awg import ip_manager as im

    used = {f"10.66.66.{i}" for i in range(8, 100)}

    monkeypatch.setattr(im, "get_used_awg_ips", lambda: used)

    result = im.find_free_awg_ip()

    assert result is None


def test_get_used_awg_ips_exception(monkeypatch):
    from services.awg import ip_manager as im

    monkeypatch.setattr(
        im, "load_awg_registry", lambda: {"user1": {"ip": "10.66.66.8"}}
    )

    def raise_exception(*args, **kwargs):
        raise RuntimeError("awg command failed")

    monkeypatch.setattr(im.subprocess, "run", raise_exception)

    result = im.get_used_awg_ips()

    # Должны вернуться только IP из реестра, исключение обработано
    assert result == {"10.66.66.8"}
