"""
Тесты services.llm_diagnosis.
"""

from unittest.mock import Mock, patch

import requests

from services import llm_diagnosis


class TestSanitizeLogs:
    def test_masks_api_key(self):
        text = "API_KEY=super-secret-key"

        result = llm_diagnosis.sanitize_logs(text)

        assert "super-secret-key" not in result
        assert "***" in result

    def test_masks_bot_token(self):
        text = "BOT_TOKEN: 123456:ABCDEF_SECRET"

        result = llm_diagnosis.sanitize_logs(text)

        assert "123456:ABCDEF_SECRET" not in result
        assert "***" in result

    def test_masks_password(self):
        text = "password=hunter2"

        result = llm_diagnosis.sanitize_logs(text)

        assert "hunter2" not in result
        assert "***" in result

    def test_masks_bearer_token(self):
        text = "Authorization: Bearer very-secret-token"

        result = llm_diagnosis.sanitize_logs(text)

        assert "very-secret-token" not in result
        assert "***" in result

    def test_keeps_regular_log_data(self):
        text = "ERROR service failed from 10.0.0.1"

        assert llm_diagnosis.sanitize_logs(text) == text


class TestPrepareLogsForAnalysis:
    def test_keeps_last_max_chars(self):
        logs = "A" * 100 + "LATEST_ERROR"

        with patch.object(llm_diagnosis, "MAX_LOG_CHARS", 12):
            result = llm_diagnosis.prepare_logs_for_analysis(logs)

        assert result == "LATEST_ERROR"

    def test_sanitizes_before_returning(self):
        logs = "old\nAPI_KEY=secret\nlatest error"

        result = llm_diagnosis.prepare_logs_for_analysis(logs)

        assert "secret" not in result
        assert "***" in result

    def test_extracts_problem_lines_from_debug_noise(self):
        logs = (
            "DEBUG navigation to main\n"
            "DEBUG callback nav:system\n"
            "ERROR connection failed\n"
            "DEBUG render complete"
        )

        result = llm_diagnosis.prepare_logs_for_analysis(logs)

        assert "ERROR connection failed" in result
        assert "DEBUG navigation to main" not in result
        assert "DEBUG render complete" not in result

    def test_keeps_logs_without_problem_keywords(self):
        logs = "DEBUG navigation ok\nDEBUG render complete"

        result = llm_diagnosis.prepare_logs_for_analysis(logs)

        assert "DEBUG navigation ok" in result
        assert "DEBUG render complete" in result


class TestSanitizeLLMResponse:
    def test_removes_markdown_and_html(self):
        text = "**Факт**\n\n`xray.service` работает\n\n<b>Ошибка</b>"

        result = llm_diagnosis.sanitize_llm_response(text)

        assert "**" not in result
        assert "`" not in result
        assert "<b>" not in result
        assert "Факт" in result
        assert "xray.service" in result
        assert "Ошибка" in result

    def test_removes_code_blocks(self):
        text = "```bash\nsystemctl status xray\n```"

        result = llm_diagnosis.sanitize_llm_response(text)

        assert "```" not in result
        assert "systemctl status xray" in result


class TestNormalizeLLMMarkdown:
    def test_normalizes_lists(self):
        text = "- first item\n* second item\n1. third item"

        result = llm_diagnosis.normalize_llm_markdown(text)

        assert "• first item" in result
        assert "• second item" in result
        assert "• third item" in result
        assert "- first item" not in result
        assert "* second item" not in result


class TestFilterUnconfirmedRecommendations:
    def test_removes_risk_and_recommendation_without_log_evidence(self):
        analysis = (
            "Факт\n"
            "Сервис работает успешно\n\n"
            "Риск\n"
            "Возможна проблема с сетью\n\n"
            "Рекомендация\n"
            "Перезапустить сервер"
        )

        result = llm_diagnosis.filter_unconfirmed_recommendations(
            analysis,
            "DEBUG service started successfully",
        )

        assert "Факт" in result
        assert "Сервис работает успешно" in result
        assert "Риск" not in result
        assert "Рекомендация" not in result
        assert "Перезапустить сервер" not in result

    def test_does_not_allow_generic_recommendations_for_ssh_preauth_errors(self):
        analysis = (
            "Факт 📋\n"
            "Зафиксированы ошибки kex_exchange_identification на этапе preauth.\n\n"
            "Риск ⚠️\n"
            "Возможны автоматические сканирования SSH.\n\n"
            "Рекомендация ✅\n"
            "Включить fail2ban.\n"
            "Обновить OpenSSH.\n"
            "Изменить PermitRootLogin.\n"
        )

        logs = (
            "Aug 27 18:50:00 sshd[123]: "
            "error: kex_exchange_identification: read: Connection reset by peer\n"
            "Aug 27 18:50:01 sshd[124]: "
            "error: Protocol major versions differ: 2 vs. 1\n"
        )

        result = llm_diagnosis.filter_unconfirmed_recommendations(
            analysis,
            logs,
        )

        assert "Факт" in result
        assert "kex_exchange_identification" in result
        assert "Изменить PermitRootLogin" not in result
        assert "Обновить OpenSSH" not in result
        assert "Включить fail2ban" not in result

    def test_keeps_recommendation_when_error_exists_in_logs(self):
        analysis = (
            "Факт\n"
            "ERROR database failed\n\n"
            "Риск\n"
            "Сервис недоступен\n\n"
            "Рекомендация\n"
            "Проверить подключение к базе"
        )

        result = llm_diagnosis.filter_unconfirmed_recommendations(
            analysis,
            "ERROR database failed",
        )

        assert "Факт" in result
        assert "Риск" in result
        assert "Рекомендация" in result
        assert "Проверить подключение к базе" in result


class TestGetAnalysisFromResponse:
    def test_valid_response(self):
        result = {
            "choices": [
                {
                    "message": {
                        "content": "Найдена ошибка",
                    },
                },
            ],
        }

        assert llm_diagnosis._get_analysis_from_response(result) == "Найдена ошибка"

    def test_missing_choices(self):
        assert llm_diagnosis._get_analysis_from_response({}) is None

    def test_empty_content(self):
        result = {
            "choices": [
                {
                    "message": {
                        "content": "   ",
                    },
                },
            ],
        }

        assert llm_diagnosis._get_analysis_from_response(result) is None


def test_prepare_logs_for_analysis_truncates_single_oversized_line(monkeypatch):
    from services import llm_diagnosis

    monkeypatch.setattr(llm_diagnosis, "MAX_LOG_CHARS", 20)

    logs = "abcdefghijklmnopqrstuvwxyz"

    result = llm_diagnosis.prepare_logs_for_analysis(logs)

    assert len(result) == 20
    assert result == "ghijklmnopqrstuvwxyz"


def test_prepare_logs_for_analysis_truncates_oversized_line_with_head_and_tail(
    monkeypatch,
):
    monkeypatch.setattr(llm_diagnosis, "MAX_LOG_CHARS", 30)

    logs = "A" * 100

    result = llm_diagnosis.prepare_logs_for_analysis(logs)

    assert len(result) == 30
    assert result.startswith("A" * 10)
    assert "..." in result
    assert result.endswith("A" * 17)


def test_filter_unconfirmed_recommendations_without_problem_resets_at_fact():
    analysis = (
        "📋 Факт: сервис работает\n"
        "Риск: всё плохо\n"
        "Рекомендация: включить fail2ban\n"
        "📋 Факт: ошибок нет"
    )

    result = llm_diagnosis.filter_unconfirmed_recommendations(
        analysis,
        "обычный лог без ошибок",
    )

    assert result == "📋 Факт: сервис работает\n📋 Факт: ошибок нет"


def test_analyze_logs_with_llm_returns_error_when_models_are_not_configured():
    with (
        patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
        patch.object(llm_diagnosis, "LLM_MODEL", ""),
        patch.object(llm_diagnosis, "LLM_MODELS", ()),
    ):
        result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

    assert result == "❌ Не настроены модели LLM"


def test_analyze_logs_with_llm_handles_request_exception():
    with (
        patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
        patch.object(
            llm_diagnosis.requests,
            "post",
            side_effect=requests.exceptions.RequestException("network error"),
        ),
    ):
        result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

    assert result.startswith("❌ Ошибка связи с AI.")
    assert "network error" in result


class TestAnalyzeLogsWithLLM:
    def test_missing_api_key(self):
        with patch.object(llm_diagnosis, "LLM_API_KEY", ""):
            result = llm_diagnosis.analyze_logs_with_llm(
                "some logs",
                "bot",
            )

        assert "⚠️ AI-провайдер не настроен." in result
        assert "Провайдер: groq" in result
        assert "Модель: openai/gpt-oss-120b" in result
        assert "Проверьте LLM_API_KEY в .env" in result

    def test_empty_logs(self):
        with patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"):
            result = llm_diagnosis.analyze_logs_with_llm("", "bot")

        assert result == "📭 Логи пусты, нечего анализировать."

    def test_success(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Обнаружена проблема.",
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ) as post,
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR test",
                "bot",
            )

        assert result == "🤖 AI-анализ логов bot:\n\nОбнаружена проблема."
        response.raise_for_status.assert_called_once()
        assert post.call_args.kwargs["timeout"] == llm_diagnosis.LLM_REQUEST_TIMEOUT
        assert post.call_args.kwargs["json"]["model"] == llm_diagnosis.LLM_MODEL

    def test_falls_back_to_next_model_when_model_not_found(self):
        unavailable_response = Mock()
        unavailable_response.status_code = 404
        unavailable_response.json.return_value = {
            "error": {
                "code": "model_not_found",
                "message": "The model does not exist",
            },
        }

        unavailable_error = requests.exceptions.HTTPError(
            response=unavailable_response,
        )

        success_response = Mock()
        success_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Ответ второй модели.",
                    },
                },
            ],
        }

        def post_side_effect(*args, **kwargs):
            if kwargs["json"]["model"] == "model-1":
                raise unavailable_error
            return success_response

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis,
                "LLM_MODEL",
                "model-1",
            ),
            patch.object(
                llm_diagnosis,
                "LLM_MODELS",
                ("model-1", "model-2"),
            ),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=post_side_effect,
            ) as post,
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR test",
                "bot",
            )

        assert result == "🤖 AI-анализ логов bot:\n\nОтвет второй модели."
        assert [call.kwargs["json"]["model"] for call in post.call_args_list] == [
            "model-1",
            "model-2",
        ]

    def test_does_not_fallback_on_other_404(self):
        response = Mock()
        response.status_code = 404
        response.json.return_value = {
            "error": {
                "code": "some_other_error",
                "message": "Not found",
            },
        }

        error = requests.exceptions.HTTPError(response=response)

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis,
                "LLM_MODEL",
                "model-1",
            ),
            patch.object(
                llm_diagnosis,
                "LLM_MODELS",
                ("model-1", "model-2"),
            ),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=error,
            ) as post,
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR test",
                "bot",
            )

        assert result.startswith("❌ Ошибка связи с AI.")
        assert "Провайдер: groq" in result
        assert "Модель: model-1" in result
        assert post.call_count == 1

    def test_sent_logs_are_limited_by_max_chars(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OK",
                    },
                },
            ],
        }

        huge_logs = "ERROR " + ("A" * 20000)

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ) as post,
            patch.object(
                llm_diagnosis,
                "MAX_LOG_CHARS",
                100,
            ),
        ):
            llm_diagnosis.analyze_logs_with_llm(
                huge_logs,
                "bot",
            )

        sent_logs = post.call_args.kwargs["json"]["messages"][1]["content"]

        assert len(sent_logs) < 500
        assert "ERROR" in sent_logs

    def test_debug_noise_is_not_sent_when_errors_exist(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OK",
                    },
                },
            ],
        }

        logs = (
            "DEBUG navigation main\n"
            "DEBUG callback ok\n"
            "ERROR database failed\n"
            "DEBUG render done"
        )

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ) as post,
        ):
            llm_diagnosis.analyze_logs_with_llm(
                logs,
                "bot",
            )

        sent_logs = post.call_args.kwargs["json"]["messages"][1]["content"]

        assert "ERROR database failed" in sent_logs
        assert "DEBUG navigation main" not in sent_logs
        assert "DEBUG render done" not in sent_logs

    def test_llm_response_is_normalized_before_return(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": ("**Факт**\\n`xray.service` работает\\n<b>OK</b>"),
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR test",
                "xray",
            )

        assert "**" not in result
        assert "`" not in result
        assert "<b>" not in result
        assert "Факт" in result
        assert "xray.service" in result
        assert "OK" in result

    def test_secret_is_not_sent_to_api(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OK",
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ) as post,
        ):
            llm_diagnosis.analyze_logs_with_llm(
                "API_KEY=real-secret\nlatest error",
                "bot",
            )

        messages = post.call_args.kwargs["json"]["messages"]
        sent_logs = messages[1]["content"]

        assert "real-secret" not in sent_logs
        assert "***" in sent_logs

    def test_uses_latest_logs(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OK",
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(llm_diagnosis, "MAX_LOG_CHARS", 12),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ) as post,
        ):
            llm_diagnosis.analyze_logs_with_llm(
                "A" * 100 + "LATEST_ERROR",
                "bot",
            )

        messages = post.call_args.kwargs["json"]["messages"]
        assert messages[1]["content"].endswith("LATEST_ERROR")

    def test_limits_analysis_length(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "X" * 100,
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(llm_diagnosis, "MAX_ANALYSIS_CHARS", 10),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR",
                "bot",
            )

        assert result.endswith("X" * 10)

    def test_timeout(self):
        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=requests.exceptions.Timeout,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR",
                "bot",
            )

        assert result == "⏱️ Превышено время ожидания ответа от LLM"

    def test_request_error(self):
        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=requests.exceptions.ConnectionError("offline"),
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR",
                "bot",
            )

        assert result.startswith("❌ Ошибка связи с AI.")
        assert "Провайдер: groq" in result
        assert "Модель: openai/gpt-oss-120b" in result

    def test_unexpected_response(self):
        response = Mock()
        response.json.return_value = {"unexpected": "response"}

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm(
                "ERROR",
                "bot",
            )

        assert result == "❌ Не удалось получить ответ от LLM"


class TestAnalyzeLogsWithLLMEdgeCases:
    def test_non_string_content(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": 12345,
                    },
                },
            ],
        }

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                return_value=response,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

        assert result == "❌ Не удалось получить ответ от LLM"

    def test_invalid_json_in_404_error(self):
        unavailable_response = Mock()
        unavailable_response.status_code = 404
        unavailable_response.json.side_effect = ValueError("Invalid JSON")

        error = requests.exceptions.HTTPError(response=unavailable_response)

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(llm_diagnosis, "LLM_MODEL", "model-1"),
            patch.object(llm_diagnosis, "LLM_MODELS", ("model-1",)),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=error,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

        assert result.startswith("❌ Ошибка связи с AI.")
        assert "Провайдер: groq" in result
        assert "Модель: model-1" in result

    def test_all_models_unavailable(self):
        unavailable_response = Mock()
        unavailable_response.status_code = 404
        unavailable_response.json.return_value = {
            "error": {"code": "model_not_found"},
        }

        error = requests.exceptions.HTTPError(response=unavailable_response)

        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(llm_diagnosis, "LLM_MODEL", "model-1"),
            patch.object(llm_diagnosis, "LLM_MODELS", ("model-1", "model-2")),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=error,
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

        assert result.startswith("❌ Ошибка связи с AI.")
        assert "Провайдер: groq" in result
        assert "Модель: model-1" in result

    def test_unexpected_exception(self):
        with (
            patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
            patch.object(
                llm_diagnosis.requests,
                "post",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            result = llm_diagnosis.analyze_logs_with_llm("ERROR", "bot")

        assert result.startswith("❌ Неожиданная ошибка:")


def test_has_problem_events_ignores_empty_system_errors_section():
    logs = (
        "=== SYSTEM ===\nUptime: up 2 hours\n=== SYSTEM ERRORS ===\nNo system errors\n"
    )

    assert llm_diagnosis._has_problem_events(logs) is False


def test_has_problem_events_ignores_no_ssh_events():
    logs = (
        "=== SECURITY EVENTS ===\n"
        "No SSH events\n"
        "=== SYSTEM ERRORS ===\n"
        "No system errors\n"
    )

    assert llm_diagnosis._has_problem_events(logs) is False


def test_has_problem_events_detects_real_error():
    logs = (
        "=== SYSTEM ERRORS ===\nAug 31 23:50:00 kernel: ERROR disk failure detected\n"
    )

    assert llm_diagnosis._has_problem_events(logs) is True


def test_filter_unconfirmed_recommendations_ignores_no_error_report():
    analysis = (
        "Факт\n"
        "Все сервисы работают\n\n"
        "Риск\n"
        "Возможна проблема с сетью\n\n"
        "Рекомендация\n"
        "Перезапустить сервер"
    )

    logs = (
        "=== SYSTEM ===\n"
        "Load: 0.01 0.02 0.03\n"
        "=== SECURITY EVENTS ===\n"
        "No SSH events\n"
        "=== SYSTEM ERRORS ===\n"
        "No system errors\n"
    )

    result = llm_diagnosis.filter_unconfirmed_recommendations(
        analysis,
        logs,
    )

    assert "Факт" in result
    assert "Все сервисы работают" in result
    assert "Риск" not in result
    assert "Рекомендация" not in result
    assert "Перезапустить сервер" not in result


def test_prepare_logs_for_analysis_oversized_line_with_head_and_tail():
    monkeypatch = patch.object(llm_diagnosis, "MAX_LOG_CHARS", 30)
    monkeypatch.start()
    try:
        logs = "ERROR " + ("A" * 100) + "\n" + "LATEST"
        result = llm_diagnosis.prepare_logs_for_analysis(logs)

        assert len(result) == 30
        assert result.startswith("ERROR ")
        assert "..." in result
    finally:
        monkeypatch.stop()


def test_prepare_logs_for_analysis_stops_after_fitting_latest_lines():
    with patch.object(llm_diagnosis, "MAX_LOG_CHARS", 15):
        logs = "old line\nLATEST\nSECOND"
        result = llm_diagnosis.prepare_logs_for_analysis(logs)

    assert result
    assert "SECOND" in result
    assert "LATEST" not in result or len(result) <= 15


def test_has_problem_events_skips_blank_lines():
    assert llm_diagnosis._has_problem_events("\n   \n\t\n") is False


def test_analyze_logs_server_uses_server_specific_prompt():
    response = Mock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "OK",
                },
            },
        ],
    }

    with (
        patch.object(llm_diagnosis, "LLM_API_KEY", "test-key"),
        patch.object(
            llm_diagnosis.requests,
            "post",
            return_value=response,
        ) as post,
    ):
        result = llm_diagnosis.analyze_logs_with_llm(
            "ERROR sshd authentication failed",
            "server",
        )

    assert result == "🤖 AI-анализ логов server:\n\nOK"

    system_prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "PermitRootLogin" in system_prompt
