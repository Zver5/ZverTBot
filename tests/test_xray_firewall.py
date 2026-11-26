import subprocess

import pytest

from services.xray import firewall


def make_rules():
    return (
        "*filter\n"
        ":INPUT DROP [0:0]\n"
        "-A INPUT -i lo -j ACCEPT\n"
        "-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT\n"
        "-A INPUT -p tcp -m tcp --dport 22 -j ACCEPT\n"
        "-A INPUT -p tcp -m tcp --dport 2096 -j ACCEPT\n"
        "-A INPUT -p udp -m udp --dport 58352 -j ACCEPT\n"
        "COMMIT\n"
    )


def mock_firewall(monkeypatch, active):
    def run(*args):
        if args[1] == "-I":
            active.add(int(args[args.index("--dport") + 1]))
        elif args[1] == "-D":
            active.remove(int(args[args.index("--dport") + 1]))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(firewall, "_active_rule_exists", lambda port: port in active)
    monkeypatch.setattr(firewall, "_ssh_ports", lambda: {22})
    monkeypatch.setattr(firewall, "_run", run)


def test_port_change_commit(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)

    assert active == {22, 2096, 2097}
    assert "--dport 2096" in path.read_text()
    assert "--dport 2097" in path.read_text()

    transaction.commit()

    assert active == {22, 2097}
    assert "--dport 2096" not in path.read_text()
    assert "--dport 2097" in path.read_text()


def test_port_change_rollback(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    transaction.rollback()

    assert active == {22, 2096}
    assert path.read_text() == original


def test_missing_ssh_rule_refuses_change(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {2096}
    mock_firewall(monkeypatch, active)

    with pytest.raises(RuntimeError, match="SSH"):
        firewall.prepare_xray_port_change(2096, 2097, path)

    assert active == {2096}
    assert path.read_text() == original


def test_missing_old_rule_refuses_change(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22}
    mock_firewall(monkeypatch, active)

    with pytest.raises(RuntimeError, match="2096"):
        firewall.prepare_xray_port_change(2096, 2097, path)

    assert active == {22}
    assert path.read_text() == original


def test_arbitrary_vless_ports(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules().replace("2096", "45678")
    path.write_text(original)
    active = {22, 45678}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(45678, 54321, path)

    assert active == {22, 45678, 54321}
    assert "--dport 54321" in path.read_text()
    assert "--dport 45678" in path.read_text()

    transaction.commit()

    assert active == {22, 54321}
    assert "--dport 45678" not in path.read_text()
    assert "--dport 54321" in path.read_text()


def test_same_port_keeps_existing_rule(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2096, path)
    transaction.commit()

    assert active == {22, 2096}
    assert path.read_text() == original


def test_port_change_preserves_nat_table(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    nat = (
        "*nat\n"
        ":PREROUTING ACCEPT [0:0]\n"
        ":INPUT ACCEPT [0:0]\n"
        ":OUTPUT ACCEPT [0:0]\n"
        ":POSTROUTING ACCEPT [0:0]\n"
        "-A POSTROUTING -s 10.66.66.0/24 -o ens3 -j MASQUERADE\n"
        "COMMIT\n"
    )
    original = make_rules() + nat
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    transaction.commit()

    content = path.read_text()
    assert content.split("*nat", 1)[1].rstrip("\n") == nat.split("*nat", 1)[1].rstrip(
        "\n"
    )
    assert "-A INPUT -p tcp -m tcp --dport 2097 -j ACCEPT" in content
    assert "-A INPUT -p tcp -m tcp --dport 2096 -j ACCEPT" not in content


def test_commit_failure_can_be_rolled_back(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    real_write = firewall.atomic_write
    calls = 0

    def fail_once(target, content):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated persistent write failure")
        real_write(target, content)

    monkeypatch.setattr(firewall, "atomic_write", fail_once)

    with pytest.raises(OSError, match="simulated"):
        transaction.commit()

    transaction.rollback()

    assert active == {22, 2096}
    assert path.read_text() == original
    assert transaction.finished is True


def test_rollback_keeps_preexisting_new_port_rule(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    original = make_rules() + "-A INPUT -p tcp -m tcp --dport 2097 -j ACCEPT\n"
    path.write_text(original)
    active = {22, 2096, 2097}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    transaction.rollback()

    assert active == {22, 2096, 2097}
    assert path.read_text() == original


@pytest.mark.parametrize(("old_port", "new_port"), [(22, 2097), (2096, 22)])
def test_ssh_port_conflict_refuses_change(tmp_path, monkeypatch, old_port, new_port):
    path = tmp_path / "rules.v4"
    original = make_rules()
    path.write_text(original)
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    with pytest.raises(ValueError, match="conflicts with an SSH port"):
        firewall.prepare_xray_port_change(old_port, new_port, path)

    assert active == {22, 2096}
    assert path.read_text() == original


def test_rollback_refuses_to_overwrite_external_rules_change(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    path.write_text(make_rules())
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    external_content = path.read_text() + "# external firewall change\\n"
    path.write_text(external_content)

    with pytest.raises(RuntimeError, match="changed externally"):
        transaction.rollback()

    assert active == {22, 2096}
    assert path.read_text() == external_content
    assert transaction.finished is False


def test_commit_refuses_to_overwrite_external_rules_change(tmp_path, monkeypatch):
    path = tmp_path / "rules.v4"
    path.write_text(make_rules())
    active = {22, 2096}
    mock_firewall(monkeypatch, active)

    transaction = firewall.prepare_xray_port_change(2096, 2097, path)
    external_content = path.read_text() + "# external firewall change\\n"
    path.write_text(external_content)

    with pytest.raises(RuntimeError, match="changed during"):
        transaction.commit()

    assert active == {22, 2096, 2097}
    assert path.read_text() == external_content
    assert transaction.finished is False
