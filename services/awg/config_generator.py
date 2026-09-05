"""Модуль генерации клиентских конфигов AmneziaWG.
Содержит параметры сервера и функции генерации конфигов.
"""

import subprocess

from config import AWG_CONF, SERVER_IP
from data.storage import load_awg_registry
from utils.logger import logger
from utils.perf import profile


def get_awg_server_params() -> tuple[str, dict]:
    """
    Возвращает параметры сервера AmneziaWG из реального AWG-конфига.

    Returns:
        (srv_pub, params): PublicKey сервера и параметры обфускации.
    """
    params = {}
    private_key = None

    try:
        with open(AWG_CONF, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key == "PrivateKey":
                    private_key = value
                elif key in {
                    "Jc",
                    "Jmin",
                    "Jmax",
                    "S1",
                    "S2",
                    "S3",
                    "S4",
                    "H1",
                    "H2",
                    "H3",
                    "H4",
                }:
                    params[key] = value

        required = {
            "Jc",
            "Jmin",
            "Jmax",
            "S1",
            "S2",
            "S3",
            "S4",
            "H1",
            "H2",
            "H3",
            "H4",
        }

        missing = required - params.keys()

        if missing:
            raise ValueError(
                f"AWG parameters not found in {AWG_CONF}: {', '.join(sorted(missing))}"
            )

        if not private_key:
            raise ValueError(f"PrivateKey not found in {AWG_CONF}")

        result = subprocess.run(
            ["awg", "pubkey"],
            input=f"{private_key}\n",
            text=True,
            capture_output=True,
            check=True,
        )

        srv_pub = result.stdout.strip()

        if not srv_pub:
            raise ValueError("Failed to derive AWG server public key")

        return srv_pub, params

    except OSError as e:
        raise ValueError(f"Cannot read AWG server config {AWG_CONF}: {e}") from e


def get_awg_port() -> str:
    """Возвращает ListenPort из серверного AWG-конфига."""
    try:
        with open(AWG_CONF, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ListenPort"):
                    _, value = line.split("=", 1)
                    return value.strip()
    except OSError:
        pass

    return "N/A"


@profile()
def awg_get_config(username: str) -> str | None:
    """
    Генерирует клиентский конфиг AmneziaWG.

    Args:
        username: Имя клиента

    Returns:
        str | None: Конфиг клиента или None если клиент не найден
    """
    try:
        reg = load_awg_registry()

        if username not in reg:
            logger.warning(
                "awg.config.generate_not_found | username=%s",
                username,
            )
            return None

        u = reg[username]
        srv_pub, params = get_awg_server_params()

        # ListenPort берём непосредственно из серверного AWG-конфига.
        # Это единственный источник истины для порта AWG.
        listen_port = get_awg_port()

        if listen_port == "N/A":
            raise ValueError(f"ListenPort не найден в {AWG_CONF}")

        config = f"""[Interface]
PrivateKey = {u["privkey"]}
Address = {u["ip"]}/24
DNS = 1.1.1.1
MTU = 1300
Jc = {params["Jc"]}
Jmin = {params["Jmin"]}
Jmax = {params["Jmax"]}
S1 = {params["S1"]}
S2 = {params["S2"]}
S3 = {params["S3"]}
S4 = {params["S4"]}
H1 = {params["H1"]}
H2 = {params["H2"]}
H3 = {params["H3"]}
H4 = {params["H4"]}
[Peer]
PublicKey = {srv_pub}
Endpoint = {SERVER_IP}:{listen_port}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25"""

        return config

    except Exception as e:
        logger.error(
            "awg.config.generate_failed | username=%s | error=%s",
            username,
            e,
        )
        return None
