"""
services/llm_diagnosis.py
Модуль AI-диагностики логов через LLM API.

Перед отправкой во внешний LLM API чувствительные данные в логах
маскируются. Для анализа используются последние записи логов.
"""

import logging
import re

import requests

from config.config import (
    LLM_API_KEY,
    LLM_API_URL,
    LLM_MODEL,
    LLM_MODELS,
    LLM_PROVIDER,
)

logger = logging.getLogger(__name__)

MAX_LOG_CHARS = 6000

IMPORTANT_LOG_KEYWORDS = (
    "error",
    "warning",
    "warn",
    "exception",
    "traceback",
    "failed",
    "failure",
    "timeout",
    "restart",
    "critical",
    "***",
)
MAX_ANALYSIS_CHARS = 3500
LLM_REQUEST_TIMEOUT = 60


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b("
        r"bot[_-]?token|token|api[_-]?key|apikey|secret|password|passwd"
        r")\b(\s*[:=]\s*)([^\s,'\"`]+)"
    ),
    re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)([^\s,'\"`]+)"),
    re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9._~+/=-]+)"),
)


def sanitize_logs(logs: str) -> str:
    """Маскирует типовые секреты перед отправкой логов во внешний API."""
    sanitized = logs

    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(
            lambda match: "".join(match.groups()[:-1]) + "***",
            sanitized,
        )

    return sanitized


def extract_relevant_log_lines(logs: str) -> str:
    """
    Оставляет строки, которые потенциально содержат проблемы.

    DEBUG-события навигации и обычной работы не считаются ошибками.
    Если важных строк нет — возвращается исходный фрагмент.
    """
    lines = logs.splitlines()

    important = [
        line
        for line in lines
        if any(keyword in line.lower() for keyword in IMPORTANT_LOG_KEYWORDS)
    ]

    if important:
        return "\n".join(important)

    return logs


def prepare_logs_for_analysis(logs: str) -> str:
    """Маскирует данные и подготавливает безопасный фрагмент логов."""
    sanitized = sanitize_logs(logs)
    filtered = extract_relevant_log_lines(sanitized)

    if len(filtered) <= MAX_LOG_CHARS:
        return filtered

    lines = filtered.splitlines()
    result = []
    total = 0

    for line in reversed(lines):
        line_size = len(line) + 1

        if total + line_size <= MAX_LOG_CHARS:
            result.insert(0, line)
            total += line_size
        else:
            if not result:
                if MAX_LOG_CHARS <= 20:
                    return line[-MAX_LOG_CHARS:]

                head = min(20, MAX_LOG_CHARS // 3)
                tail = MAX_LOG_CHARS - head - 3

                return line[:head] + "..." + line[-tail:]
            break

    return "\n".join(result)


def _get_analysis_from_response(result: dict) -> str | None:
    """Безопасно извлекает текст анализа из OpenAI-совместимого ответа."""
    try:
        analysis = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None

    if not isinstance(analysis, str):
        return None

    analysis = analysis.strip()
    return analysis or None


def sanitize_llm_response(text: str) -> str:
    """Удаляет нежелательную Markdown и HTML-разметку из ответа LLM."""
    import re

    cleaned = text

    cleaned = re.sub(r"```(?:\w+)?\s*", "", cleaned)
    cleaned = cleaned.replace("```", "")

    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)

    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")

    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return normalize_llm_markdown(cleaned.strip())


def normalize_llm_markdown(text: str) -> str:
    """Приводит Markdown-списки LLM к удобному виду для Telegram."""
    import re

    normalized = text

    normalized = re.sub(
        r"(?m)^\s*[-*]\s+",
        "• ",
        normalized,
    )

    normalized = re.sub(
        r"(?m)^\s*\d+\.\s+",
        "• ",
        normalized,
    )

    normalized = re.sub(
        r"(?m)^\s*•\s*•\s*",
        "• ",
        normalized,
    )

    return normalized.strip()


def _has_problem_events(logs: str) -> bool:
    """Определяет наличие реальных проблемных событий в подготовленных логах."""
    for line in logs.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        # Служебные заголовки и отрицательные сообщения
        # не являются доказательством проблемы.
        if lower.startswith(("===", "no system errors", "no ssh events")):
            continue

        if any(keyword in lower for keyword in IMPORTANT_LOG_KEYWORDS):
            return True

    return False


def filter_unconfirmed_recommendations(
    analysis: str,
    logs: str,
) -> str:
    """
    Убирает неподтверждённые риски и рекомендации.

    Наличие ошибки в логах не подтверждает автоматически
    конкретные меры исправления. Факты и риск сохраняются,
    а рекомендации, требующие отдельного подтверждения,
    удаляются.
    """
    problem_detected = _has_problem_events(logs)

    lines = analysis.splitlines()

    if not problem_detected:
        result = []
        skip = False

        for line in lines:
            lower = line.lower().strip()

            if lower.startswith(("риск", "⚠️ риск", "рекомендация", "рекомендации")):
                skip = True
                continue

            if skip and lower.startswith(("факт", "📋 факт")):
                skip = False

            if not skip:
                result.append(line)

        return "\n".join(result).strip()

    unconfirmed_patterns = (
        "fail2ban",
        "обновить openssh",
        "permitrootlogin",
        "allowusers",
        "maxauthtries",
        "hosts.deny",
        "iptables",
        "nftables",
        "ufw",
        "loglevel verbose",
    )

    result = []

    for line in lines:
        lower = line.lower()

        if any(pattern in lower for pattern in unconfirmed_patterns):
            continue

        result.append(line)

    return "\n".join(result).strip()


def analyze_logs_with_llm(logs: str, service_name: str) -> str:
    """
    Отправляет логи в LLM и возвращает анализ.

    Args:
        logs: текст логов для анализа
        service_name: название сервиса

    Returns:
        Строка с анализом или сообщением об ошибке.
    """
    if not LLM_API_KEY:
        return (
            "⚠️ AI-провайдер не настроен."
            f"\nПровайдер: {LLM_PROVIDER or 'не указан'}"
            f"\nМодель: {LLM_MODEL or 'не указана'}"
            "\nПроверьте LLM_API_KEY в .env"
        )

    if not logs or not logs.strip():
        return "📭 Логи пусты, нечего анализировать."

    logs_prepared = prepare_logs_for_analysis(logs)

    system_prompt = (
        "Ты эксперт по диагностике Linux-сервисов и системных логов. "
        "Анализируй только факты, которые прямо подтверждены предоставленными логами. "
        "Не выдумывай причины, которых нет в логах. "
        "Не объявляй проблему без конкретного подтверждения. "
        "Если данных недостаточно — явно укажи, что подтверждённых данных нет. "
        "Разделяй вывод на: факт, риск и рекомендацию. "
        "В разделе факт используй только события из логов. "
        "В разделе риск указывай только последствия, которые логически "
        "следуют из фактов. "
        "В разделе рекомендация предлагай действия только для подтверждённых проблем. "
        "Не предлагай универсальные меры безопасности без связи с найденной проблемой. "
        "Обычные DEBUG-сообщения успешной работы не считать ошибками. "
        "Ответ давай на русском языке, структурированно, с эмодзи для наглядности. "
        "Не используй Markdown-разметку со звёздочками, обратными кавычками "
        "или HTML-тегами."
    )

    if service_name == "server":
        system_prompt += (
            " Для анализа сервера дополнительно соблюдай правила: "
            "не предлагай перезапускать сервисы без подтверждённой причины. "
            "Для SSH не предлагай изменения конфигурации без подтверждения "
            "текущих настроек. "
            "Не предлагай PermitRootLogin, AllowUsers, MaxAuthTries и подобные "
            "изменения, "
            "если текущая конфигурация sshd не предоставлена. "
            "Не утверждай факт взлома только по неудачным попыткам входа. "
            "Используй формулировку попытки перебора или подозрительная активность. "
            "Не рекомендуй hosts.deny, если нет подтверждения использования "
            "TCP wrappers. "
            "Отличай автоматические сканирования от успешного доступа. "
            "Команды systemctl предлагай только если точно известно имя systemd unit. "
            "Для Debian/Ubuntu SSH-сервис обычно называется ssh, а не sshd. "
        )

    user_prompt = f"Проанализируй логи сервиса '{service_name}':\n\n{logs_prepared}"

    models = list(dict.fromkeys(model for model in (LLM_MODEL, *LLM_MODELS) if model))
    last_error = None

    try:
        for model in models:
            try:
                response = requests.post(
                    LLM_API_URL,
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    },
                    timeout=LLM_REQUEST_TIMEOUT,
                )

                response.raise_for_status()
                result = response.json()
                analysis = _get_analysis_from_response(result)

                if analysis is None:
                    logger.error(
                        "llm.analysis.invalid_response | model=%s | response=%r",
                        model,
                        result,
                    )
                    return "❌ Не удалось получить ответ от LLM"

                analysis = sanitize_llm_response(analysis)
                analysis = filter_unconfirmed_recommendations(
                    analysis,
                    logs_prepared,
                )
                analysis = analysis[:MAX_ANALYSIS_CHARS]

                return f"🤖 AI-анализ логов {service_name}:\n\n{analysis}"

            except requests.exceptions.HTTPError as e:
                last_error = e

                is_model_unavailable = False

                if e.response is not None and e.response.status_code == 404:
                    try:
                        error_data = e.response.json().get("error", {})
                    except (ValueError, TypeError):
                        error_data = {}

                    is_model_unavailable = error_data.get("code") == "model_not_found"

                if is_model_unavailable:
                    logger.warning(
                        "llm.model.unavailable | model=%s",
                        model,
                    )
                    continue

                raise

        if last_error is not None:
            logger.error("llm.models.unavailable")
            return (
                "❌ Ошибка связи с AI."
                f"\nПровайдер: {LLM_PROVIDER or 'не указан'}"
                f"\nМодель: {LLM_MODEL or 'не указана'}"
                f"\nОшибка: {str(last_error)[:100]}"
            )

        return "❌ Не настроены модели LLM"

    except requests.exceptions.Timeout:
        logger.error("llm.request.timeout")
        return "⏱️ Превышено время ожидания ответа от LLM"

    except requests.exceptions.RequestException as e:
        logger.error("llm.request.failed | error=%s", e)
        return (
            "❌ Ошибка связи с AI."
            f"\nПровайдер: {LLM_PROVIDER or 'не указан'}"
            f"\nМодель: {LLM_MODEL or 'не указана'}"
            f"\nОшибка: {str(e)[:100]}"
        )

    except Exception as e:
        logger.exception("llm.analysis.failed | error=%s", e)
        return f"❌ Неожиданная ошибка: {str(e)[:100]}"
