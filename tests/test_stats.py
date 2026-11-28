from unittest.mock import patch

from services.stats import get_bot_stats_text


@patch("services.stats.load_stats")
def test_bot_stats_empty(mock_load):
    mock_load.return_value = {
        "commands": {},
        "total_commands": 0,
        "start_date": "2026-07-01 12:00:00",
    }

    text = get_bot_stats_text()

    assert "Статистика пуста" in text
    assert "Используйте бота" in text


@patch("services.stats.load_stats")
def test_bot_stats_success(mock_load):
    mock_load.return_value = {
        "commands": {
            "status": 10,
            "speedtest": 5,
        },
        "total_commands": 15,
        "start_date": "2026-07-01 12:00:00",
    }

    text = get_bot_stats_text()

    assert "Статистика использования бота" in text
    assert "15" in text
    assert "🖥️ Статус VPS" in text
    assert "🚀 Speedtest" in text
    assert "66.7%" in text
    assert "33.3%" in text


@patch("services.stats.load_stats")
def test_bot_stats_unknown_command(mock_load):
    mock_load.return_value = {
        "commands": {
            "my_super_command": 1,
        },
        "total_commands": 1,
        "start_date": "2026-07-01",
    }

    text = get_bot_stats_text()

    assert "My Super Command" in text


@patch("services.stats.load_stats")
def test_bot_stats_exception(mock_load):
    mock_load.side_effect = Exception("boom")

    text = get_bot_stats_text()

    assert "Ошибка чтения статистики" in text
    assert "boom" in text


@patch("services.stats.load_stats")
def test_bot_stats_localizes_legacy_and_navigation_actions(mock_load):
    mock_load.return_value = {
        "commands": {
            "Nav:Analytics": 1,
            "Nav:System": 1,
            "Nav:Clients": 1,
            "/Start": 1,
            "Test:": 1,
        },
        "total_commands": 5,
        "start_date": "2026-11-15",
    }

    text = get_bot_stats_text()

    assert "📊 Аналитика" in text
    assert "⚙️ Система" in text
    assert "👥 Клиенты" in text
    assert "🚀 Запуск бота" in text
    assert "🧪 Тестовое действие" in text
    assert "Nav:" not in text
    assert "Test:" not in text
    assert "/Start" not in text
