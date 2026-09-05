from dataclasses import dataclass


@dataclass(frozen=True)
class CallbackResponse:
    """Результат обработки callback."""

    text: str | None = None
    show_alert: bool = False
