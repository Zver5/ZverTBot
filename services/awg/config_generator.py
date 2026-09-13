"""Модуль генерации клиентских конфигов AmneziaWG.
Содержит параметры сервера и функции генерации конфигов.
"""

import subprocess

from config import SERVER_IP
from data.storage import load_awg_registry
from services.awg.config_manager import get_awg_interface_params, get_awg_listen_port
from utils.logger import logger
from utils.perf import profile


def get_awg_server_params() -> tuple[str, dict]:
    """Возвращает параметры сервера AWG из [Interface]."""
    try:
        fields = get_awg_interface_params()
        private_key = fields.get("privatekey")
        params = {
            key: fields[key]
            for key in {
                "jc",
                "jmin",
                "jmax",
                "s1",
                "s2",
                "s3",
                "s4",
                "h1",
                "h2",
                "h3",
                "h4",
            }
            if key in fields
        }
        required = {
            "jc", "jmin", "jmax", "s1", "s2", "s3", "s4",
            "h1", "h2", "h3", "h4",
        }
        missing = required - params.keys()
        if missing:
            raise ValueError(
                "AWG parameters not found: " + ", ".join(sorted(missing))
            )
        if not private_key:
            raise ValueError("PrivateKey not found")

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

        output_keys = {
            "jc": "Jc",
            "jmin": "Jmin",
            "jmax": "Jmax",
            "s1": "S1",
            "s2": "S2",
            "s3": "S3",
            "s4": "S4",
            "h1": "H1",
            "h2": "H2",
            "h3": "H3",
            "h4": "H4",
        }
        return srv_pub, {
            output_keys[key]: value for key, value in params.items()
        }
    except OSError as e:
        raise ValueError(f"Cannot read AWG server config: {e}") from e


def get_awg_port() -> str:
    """Возвращает ListenPort из серверного AWG-конфига."""
    try:
        return get_awg_listen_port() or "N/A"
    except OSError:
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
            raise ValueError("ListenPort не найден в AWG-конфиге")

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
