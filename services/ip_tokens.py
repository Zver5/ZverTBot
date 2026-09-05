"""
Токены для функции "Мой внешний IP".
"""

import json
import uuid

from config.paths import IP_TOKENS_FILE
from utils.logger import logger

TOKENS_FILE = IP_TOKENS_FILE


def _load():
    if not TOKENS_FILE.exists():
        return {}

    try:
        return json.loads(TOKENS_FILE.read_text())
    except Exception as e:
        logger.error("ip_tokens.load.failed | error=%s", e)
        raise


def _save(data):
    TOKENS_FILE.parent.mkdir(exist_ok=True)

    TOKENS_FILE.write_text(json.dumps(data, indent=2))


def create_ip_token(chat_id):
    """
    Создаёт новый токен для Telegram чата.
    """

    tokens = _load()

    token = uuid.uuid4().hex[:8]

    tokens[token] = str(chat_id)

    _save(tokens)

    return token


def get_chat_id_by_token(token):
    """
    Возвращает chat_id по токену.
    """

    tokens = _load()

    return tokens.get(token)
