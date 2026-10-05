"""Вспомогательные функции для проверки опциональных компонентов VPS."""


def is_xray_installed(binary, config_exists, unit_exists):
    """Определяет, установлен ли Xray как опциональный компонент."""
    return bool(binary or config_exists or unit_exists)


def is_awg_installed(binary, interfaces):
    """Определяет, установлен ли AmneziaWG как опциональный компонент."""
    return bool(binary or interfaces)
