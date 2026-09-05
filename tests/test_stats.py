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
