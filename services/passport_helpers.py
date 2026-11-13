"""Вспомогательные функции для проверки опциональных компонентов VPS."""


def is_xray_installed(binary, config_exists, unit_exists):
    """Определяет, установлен ли Xray как опциональный компонент."""
    return bool(binary or config_exists or unit_exists)


def is_awg_installed(binary, interfaces):
    """Определяет, установлен ли AmneziaWG как опциональный компонент."""
    return bool(binary or interfaces)


def traffic_timer_status(
    xray_installed,
    awg_installed,
    timer_enabled,
    timer_active,
):
    """Определяет статус сборщика трафика с учетом установленных протоколов."""
    if not (xray_installed or awg_installed):
        return "skip"

    if timer_enabled and timer_active:
        return "ok"

    return "warn"
