"""Сетевые hooks для жизненного цикла AmneziaWG."""

from __future__ import annotations

import ipaddress
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AwgNetworkHooks:
    """WAN-интерфейс и команды NAT для awg-quick."""

    wan_interface: str
    post_up: tuple[str, ...]
    post_down: tuple[str, ...]


def get_default_route_interface() -> str:
    """Возвращает интерфейс системного default route."""
    result = subprocess.run(
        ["ip", "route", "show", "default"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "не удалось определить default route"
        )

    for line in result.stdout.splitlines():
        fields = line.split()
        if "dev" in fields:
            index = fields.index("dev")
            if index + 1 < len(fields):
                return fields[index + 1]

    raise RuntimeError("не найден интерфейс default route")


def build_awg_network_hooks(
    *,
    address: str,
    wan_interface: str | None = None,
) -> AwgNetworkHooks:
    """Строит идемпотентные PostUp/PostDown для IPv4 NAT AWG."""
    wan = wan_interface or get_default_route_interface()
    network = ipaddress.ip_interface(address).network
    marker = "ZverTBot-AWG"

    post_up = (
        (
            "iptables -C FORWARD -i %i -o "
            f"{wan} -s {network} -m comment --comment {marker} "
            "-j ACCEPT || "
            "iptables -A FORWARD -i %i -o "
            f"{wan} -s {network} -m comment --comment {marker} "
            "-j ACCEPT"
        ),
        (
            "iptables -C FORWARD -i "
            f"{wan} -o %i -d {network} "
            "-m conntrack --ctstate RELATED,ESTABLISHED "
            f"-m comment --comment {marker} -j ACCEPT || "
            "iptables -A FORWARD -i "
            f"{wan} -o %i -d {network} "
            "-m conntrack --ctstate RELATED,ESTABLISHED "
            f"-m comment --comment {marker} -j ACCEPT"
        ),
        (
            "iptables -t nat -C POSTROUTING "
            f"-s {network} -o {wan} "
            f"-m comment --comment {marker} -j MASQUERADE || "
            "iptables -t nat -A POSTROUTING "
            f"-s {network} -o {wan} "
            f"-m comment --comment {marker} -j MASQUERADE"
        ),
    )

    post_down = (
        (
            "iptables -C FORWARD -i %i -o "
            f"{wan} -s {network} -m comment --comment {marker} "
            "-j ACCEPT && "
            "iptables -D FORWARD -i %i -o "
            f"{wan} -s {network} -m comment --comment {marker} "
            "-j ACCEPT"
        ),
        (
            "iptables -C FORWARD -i "
            f"{wan} -o %i -d {network} "
            "-m conntrack --ctstate RELATED,ESTABLISHED "
            f"-m comment --comment {marker} -j ACCEPT && "
            "iptables -D FORWARD -i "
            f"{wan} -o %i -d {network} "
            "-m conntrack --ctstate RELATED,ESTABLISHED "
            f"-m comment --comment {marker} -j ACCEPT"
        ),
        (
            "iptables -t nat -C POSTROUTING "
            f"-s {network} -o {wan} "
            f"-m comment --comment {marker} -j MASQUERADE && "
            "iptables -t nat -D POSTROUTING "
            f"-s {network} -o {wan} "
            f"-m comment --comment {marker} -j MASQUERADE"
        ),
    )


    return AwgNetworkHooks(
        wan_interface=wan,
        post_up=post_up,
        post_down=post_down,
    )
