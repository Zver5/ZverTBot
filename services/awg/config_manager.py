"""Модуль работы с конфигом AmneziaWG (awg0.conf).
Централизует операции чтения/записи файла.
Формат Peer-блока:
    # Name: username
    [Peer]
    PublicKey = ...
    AllowedIPs = 10.66.66.X/32
"""

from config.paths import AWG_CONF
from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger
from utils.perf import profile


def load_awg_config() -> str:
    """
    Загружает содержимое awg0.conf.

    Returns:
        str: Содержимое файла

    Raises:
        FileNotFoundError: Если файл не существует
    """
    with open(AWG_CONF, encoding="utf-8") as f:
        return f.read()


@client_operation_lock
def save_awg_config(content: str) -> None:
    """
    Сохраняет содержимое awg0.conf.

    Args:
        content: Новое содержимое файла
    """
    atomic_write(AWG_CONF, content)


@client_operation_lock
def add_peer_to_config(username: str, pub: str, ip: str) -> None:
    """
    Добавляет Peer-блок в awg0.conf.

    Args:
        username: Имя клиента (для комментария)
        pub: PublicKey клиента
        ip: IP-адрес клиента (например: 10.66.66.12)
    """
    peer_block = (
        f"\n# Name: {username}\n[Peer]\nPublicKey = {pub}\nAllowedIPs = {ip}/32\n"
    )

    content = load_awg_config()
    content += peer_block

    atomic_write(AWG_CONF, content)

    logger.info(
        "awg.config.peer_added | username=%s | ip=%s",
        username,
        ip,
    )


@client_operation_lock
def remove_peer_from_config(pub: str) -> bool:
    """
    Удаляет Peer-блок из awg0.conf по PublicKey.
    Удаляет ВСЕ 4 строки: комментарий, [Peer], PublicKey, AllowedIPs.

    Args:
        pub: PublicKey клиента для удаления

    Returns:
        bool: True если блок найден и удалён, False иначе
    """
    try:
        with open(AWG_CONF, encoding="utf-8") as f:
            lines = f.readlines()

        # Ищем строку с PublicKey
        pubkey_line_idx = -1
        for i, line in enumerate(lines):
            if f"PublicKey = {pub}" in line:
                pubkey_line_idx = i
                break

        if pubkey_line_idx == -1:
            logger.warning(
                "awg.config.peer_not_found | pubkey_prefix=%s",
                pub[:20],
            )
            return False

        # Находим начало блока (идём назад от PublicKey)
        start_idx = pubkey_line_idx

        # Ищем [Peer] (должен быть на 1 строку выше PublicKey)
        if start_idx > 0 and lines[start_idx - 1].strip() == "[Peer]":
            start_idx -= 1

        # Ищем комментарий # Name: или # xxx (должен быть на 1 строку выше [Peer])
        if start_idx > 0 and (
            lines[start_idx - 1].strip().startswith("# Name:")
            or lines[start_idx - 1].strip().startswith("# ")
        ):
            start_idx -= 1

        # Находим конец блока (AllowedIPs — следующая строка после PublicKey)
        end_idx = pubkey_line_idx + 1

        # Проверяем что следующая строка — AllowedIPs и включаем её в удаление
        if end_idx < len(lines) and lines[end_idx].strip().startswith("AllowedIPs"):
            end_idx += 1  # Теперь end_idx указывает на строку ПОСЛЕ AllowedIPs

        # Удаляем блок (4 строки: комментарий, [Peer], PublicKey, AllowedIPs)
        removed_lines = lines[start_idx:end_idx]
        del lines[start_idx:end_idx]

        # Сохраняем изменения атомарно
        atomic_write(AWG_CONF, "".join(lines))

        logger.info(
            "awg.config.peer_removed | lines=%s",

            len(removed_lines),

        )
        return True

    except Exception as e:
        logger.error(
            "awg.config.peer_remove_failed | error=%s",
            e,
        )
        return False


@profile()
@client_operation_lock
def rename_peer_in_config(old_name: str, new_name: str) -> bool:
    """
    Переименовывает клиента в awg0.conf (замена комментария # Name:).

    Args:
        old_name: Старое имя клиента
        new_name: Новое имя клиента

    Returns:
        bool: True если клиент найден и переименован, False иначе
    """
    try:
        content = load_awg_config()
        old_comment = f"# Name: {old_name}"
        new_comment = f"# Name: {new_name}"

        lines = content.splitlines(keepends=True)
        changed = False

        for index, line in enumerate(lines):
            line_body = line.rstrip("\r\n")
            if line_body == old_comment:
                lines[index] = new_comment + line[len(line_body) :]
                changed = True

        if not changed:
            logger.warning(
                "awg.config.rename_not_found | username=%s",
                old_name,
            )
            return False

        save_awg_config("".join(lines))

        logger.info(
            "awg.config.peer_renamed | old_username=%s | new_username=%s",

            old_name,

            new_name,

        )
        return True

    except Exception as e:
        logger.error(
            "awg.config.rename_failed | old_username=%s | new_username=%s | error=%s",
            old_name,
            new_name,
            e,
        )
        return False
