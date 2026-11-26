"""Transactional management of the Xray VLESS TCP firewall rule."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils.atomic import atomic_write

IPTABLES_RULES = Path("/etc/iptables/rules.v4")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command {' '.join(args)} failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def _valid_port(port: int) -> None:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError(f"Invalid TCP port: {port!r}")


def _ssh_ports() -> set[int]:
    result = subprocess.run(
        ["sshd", "-T"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot determine SSH ports: {result.stderr.strip()}")

    ports = {
        int(line.split()[1])
        for line in result.stdout.splitlines()
        if line.startswith("port ") and len(line.split()) == 2
    }
    if not ports or any(not 1 <= port <= 65535 for port in ports):
        raise RuntimeError("No valid SSH listening ports found in sshd configuration")
    return ports


def _active_rule_exists(port: int) -> bool:
    result = subprocess.run(
        [
            "iptables",
            "-C",
            "INPUT",
            "-p",
            "tcp",
            "-m",
            "tcp",
            "--dport",
            str(port),
            "-j",
            "ACCEPT",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"Cannot inspect iptables rule for TCP/{port}: {result.stderr.strip()}"
        )
    return result.returncode == 0


def _rule_line(port: int) -> str:
    return f"-A INPUT -p tcp -m tcp --dport {port} -j ACCEPT"


def _has_persistent_rule(content: str, port: int) -> bool:
    return any(line.strip() == _rule_line(port) for line in content.splitlines())


def _replace_persistent_rule(
    content: str,
    old_port: int | None,
    new_port: int,
    ssh_ports: set[int],
) -> str:
    lines = content.splitlines()
    if not any(line.strip() == "*filter" for line in lines):
        raise RuntimeError("Persistent iptables file has no filter table")

    for ssh_port in ssh_ports:
        if not _has_persistent_rule(content, ssh_port):
            raise RuntimeError(f"Persistent firewall has no SSH TCP/{ssh_port} rule")

    if old_port is not None and old_port != new_port:
        if not _has_persistent_rule(content, old_port):
            raise RuntimeError(f"Persistent firewall has no Xray TCP/{old_port} rule")

    if not _has_persistent_rule("\n".join(lines), new_port):
        ssh_indices = [
            i
            for i, line in enumerate(lines)
            if any(line.strip() == _rule_line(port) for port in ssh_ports)
        ]
        lines.insert(max(ssh_indices) + 1, _rule_line(new_port))

    return "\n".join(lines) + "\n"


@dataclass
class XrayFirewallTransaction:
    old_port: int | None
    new_port: int
    rules_path: Path
    original_content: str
    old_was_active: bool
    new_was_active: bool
    expected_content: str | None = None
    finished: bool = False

    def commit(self) -> None:
        if self.finished:
            return

        if self.old_port is not None and self.old_port != self.new_port:
            content = self.rules_path.read_text(encoding="utf-8")
            if content != self.expected_content:
                raise RuntimeError(
                    "Persistent firewall rules changed during Xray port transaction"
                )
            if self.old_was_active:
                _run(
                    "iptables",
                    "-D",
                    "INPUT",
                    "-p",
                    "tcp",
                    "-m",
                    "tcp",
                    "--dport",
                    str(self.old_port),
                    "-j",
                    "ACCEPT",
                )

            lines = [
                line
                for line in content.splitlines()
                if line.strip() != _rule_line(self.old_port)
            ]
            updated_content = "\n".join(lines) + "\n"
            atomic_write(self.rules_path, updated_content)
            self.expected_content = updated_content

        self.finished = True

    def rollback(self) -> None:
        if self.finished:
            return

        errors: list[str] = []

        try:
            if not self.new_was_active and _active_rule_exists(self.new_port):
                _run(
                    "iptables",
                    "-D",
                    "INPUT",
                    "-p",
                    "tcp",
                    "-m",
                    "tcp",
                    "--dport",
                    str(self.new_port),
                    "-j",
                    "ACCEPT",
                )
        except Exception as exc:
            errors.append(f"new rule rollback: {exc}")

        try:
            if self.old_port is not None and self.old_was_active:
                if not _active_rule_exists(self.old_port):
                    _run(
                        "iptables",
                        "-I",
                        "INPUT",
                        "1",
                        "-p",
                        "tcp",
                        "-m",
                        "tcp",
                        "--dport",
                        str(self.old_port),
                        "-j",
                        "ACCEPT",
                    )
        except Exception as exc:
            errors.append(f"old rule restoration: {exc}")

        try:
            current_content = self.rules_path.read_text(encoding="utf-8")
            if current_content != self.expected_content:
                raise RuntimeError(
                    "Persistent firewall rules changed externally; "
                    "refusing to overwrite them during rollback"
                )
            if current_content != self.original_content:
                atomic_write(self.rules_path, self.original_content)
        except Exception as exc:
            errors.append(f"persistent rules restoration: {exc}")

        if errors:
            raise RuntimeError("; ".join(errors))

        self.finished = True


def prepare_xray_port_change(
    old_port: int | None,
    new_port: int,
    rules_path: Path | None = None,
) -> XrayFirewallTransaction:
    _valid_port(new_port)
    if old_port is not None:
        _valid_port(old_port)

    path = rules_path or IPTABLES_RULES
    original_content = path.read_text(encoding="utf-8")

    ssh_ports = _ssh_ports()
    if new_port in ssh_ports:
        raise ValueError(f"VLESS TCP/{new_port} conflicts with an SSH port")
    if old_port in ssh_ports:
        raise ValueError(f"Existing VLESS TCP/{old_port} conflicts with an SSH port")
    for ssh_port in ssh_ports:
        if not _active_rule_exists(ssh_port):
            raise RuntimeError(f"Active firewall has no SSH TCP/{ssh_port} rule")
        if not _has_persistent_rule(original_content, ssh_port):
            raise RuntimeError(f"Persistent firewall has no SSH TCP/{ssh_port} rule")

    old_active = False
    if old_port is not None and old_port != new_port:
        old_active = _active_rule_exists(old_port)
        if not old_active:
            raise RuntimeError(f"Active firewall has no Xray TCP/{old_port} rule")
        if not _has_persistent_rule(original_content, old_port):
            raise RuntimeError(f"Persistent firewall has no Xray TCP/{old_port} rule")

    new_active = _active_rule_exists(new_port)
    transaction = XrayFirewallTransaction(
        old_port=old_port,
        new_port=new_port,
        rules_path=path,
        original_content=original_content,
        old_was_active=old_active,
        new_was_active=new_active,
        expected_content=original_content,
    )

    try:
        if not new_active:
            _run(
                "iptables",
                "-I",
                "INPUT",
                "1",
                "-p",
                "tcp",
                "-m",
                "tcp",
                "--dport",
                str(new_port),
                "-j",
                "ACCEPT",
            )

        updated = _replace_persistent_rule(
            original_content, old_port, new_port, ssh_ports
        )
        if updated != original_content:
            atomic_write(path, updated)
            transaction.expected_content = updated

        return transaction
    except Exception as exc:
        try:
            transaction.rollback()
        except Exception as rollback_exc:
            raise RuntimeError(
                f"{exc}; firewall rollback failed: {rollback_exc}"
            ) from exc
        raise
