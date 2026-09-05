from config import BOT_VERSION
from utils.formatters import get_help_text


def test_get_help_text():
    text = get_help_text()

    assert isinstance(text, str)

    # Заголовок
    assert "Управление сервером VPS" in text

    # Версия бота
    assert "ZverTBot" in text
    assert f"v{BOT_VERSION}" in text

    # Серверы
    assert "VPS:" in text
    assert "HASS:" in text

    # Кнопки/завершение меню
    assert "Выберите действие" in text
