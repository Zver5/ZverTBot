"""
Универсальная навигация по экранам.

Принцип:
- callback/action и screen ID — разные понятия;
- экран не знает своего родителя;
- история хранится отдельно для каждого chat_id;
- переход вперёд добавляет экран в стек;
- nav_back возвращает фактический предыдущий экран;
- renderer регистрируется отдельно от истории навигации.

Модуль является фундаментом новой навигации.
Существующие обработчики пока могут работать независимо от него.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from utils.logger import logger

NAV_BACK_CALLBACK = "nav:back"
NAV_HOME_CALLBACK = "nav:home"
NAV_MANAGE_CALLBACK = "nav:manage"
NAV_SYSTEM_CALLBACK = "nav:system"
NAV_NETWORK_CALLBACK = "nav:network"
NAV_ANALYTICS_CALLBACK = "nav:analytics"
NAV_BACKUPS_CALLBACK = "nav:backups"
NAV_AI_LOGS_CALLBACK = "nav:ai_logs"
NAV_CREATE_CALLBACK = "nav:create"
NAV_CLIENTS_CALLBACK = "nav:clients"
NAV_CLIENTS_MANAGE_CALLBACK = "nav:clients_manage"
NAV_CLIENTS_VLESS_CALLBACK = "nav:clients_vless"
NAV_CLIENTS_AWG_CALLBACK = "nav:clients_awg"
NAV_CLIENTS_RENAME_CALLBACK = "nav:clients_rename"
NAV_CLIENTS_SEARCH_VLESS_CALLBACK = "nav:clients_search_vless"
NAV_CLIENTS_SEARCH_AWG_CALLBACK = "nav:clients_search_awg"

NAV_CLIENT_HOME_CALLBACK = "nav:client_home"
NAV_CLIENT_BACK_CALLBACK = "nav:client_back"
NAV_CLIENT_HELP_CALLBACK = "nav:client_help"

NAV_ADMIN_TICKETS_CALLBACK = "nav:admin_tickets"
NAV_ADMIN_TICKETS_NEW_CALLBACK = "nav:admin_tickets_new"
NAV_ADMIN_TICKETS_WORKING_CALLBACK = "nav:admin_tickets_working"
NAV_ADMIN_TICKETS_CLOSED_CALLBACK = "nav:admin_tickets_closed"
NAV_BACKUP_HISTORY_CALLBACK = "nav:backup_history"

FAIL2BAN_MENU_CALLBACK = "fail2ban_menu"
FAIL2BAN_LOGS_CALLBACK = "fail2ban_logs"
FAIL2BAN_UNBAN_CALLBACK = "fail2ban_unban"

PROCESS_MENU_CALLBACK = "processes_menu"
PROCESS_TOP_CALLBACK = "processes_top"
PROCESS_TOP_CPU_CALLBACK = "processes_top_cpu"
PROCESS_TOP_RAM_CALLBACK = "processes_top_ram"
PROCESS_SEARCH_CALLBACK = "process_search"
PROCESS_KILL_CALLBACK = "process_kill"

CLIENT_BACK_CALLBACK = "client:back"
CLIENT_CONF_CALLBACK_PREFIX = "client:conf:"
CLIENT_CONF_RU_CALLBACK_PREFIX = "client:conf_ru:"


@dataclass(frozen=True)
class Screen:
    """Описание экрана."""

    screen_id: str
    renderer: Callable[..., Any] | None = None


class ScreenRegistry:
    """Центральный реестр экранов и их renderer-функций."""

    def __init__(self):
        self._screens: dict[str, Screen] = {}

    def register(
        self,
        screen_id: str,
        renderer: Callable[..., Any] | None = None,
    ) -> Screen:
        """Зарегистрировать экран."""
        if not screen_id:
            raise ValueError("screen_id не может быть пустым")

        screen = Screen(screen_id=screen_id, renderer=renderer)
        self._screens[screen_id] = screen
        return screen

    def get(self, screen_id: str) -> Screen | None:
        """Получить описание экрана."""
        return self._screens.get(screen_id)

    def require(self, screen_id: str) -> Screen:
        """Получить экран или выбросить понятную ошибку."""
        screen = self.get(screen_id)

        if screen is None:
            raise KeyError(f"Экран не зарегистрирован: {screen_id}")

        return screen

    def clear(self) -> None:
        """Очистить реестр."""
        self._screens.clear()

    def ids(self) -> tuple[str, ...]:
        """Вернуть зарегистрированные screen ID."""
        return tuple(self._screens)


class NavigationStack:
    """История экранов одного пользователя."""

    def __init__(self):
        self._stacks: dict[int, list[str]] = defaultdict(list)

    def start(self, chat_id: int, screen_id: str) -> str:
        """
        Начать новую навигационную историю.

        Используется для входа в корневой экран или полного сброса
        текущего маршрута.
        """
        old_history = list(self._stacks.get(chat_id, []))
        self._stacks[chat_id] = [screen_id]

        logger.debug(
            "navigation.start | chat_id=%s | screen=%s | old=%s | new=%s",
            chat_id,
            screen_id,
            old_history,
            self._stacks[chat_id],
        )

        return screen_id

    def push(self, chat_id: int, screen_id: str) -> str:
        """
        Перейти на новый экран.

        Повторный push текущего экрана не создаёт дубликат.
        """
        stack = self._stacks[chat_id]
        old_history = list(stack)

        if not stack or stack[-1] != screen_id:
            stack.append(screen_id)

        logger.debug(
            "navigation.push | chat_id=%s | screen=%s | old=%s | new=%s",
            chat_id,
            screen_id,
            old_history,
            stack,
        )

        return screen_id

    def replace(self, chat_id: int, screen_id: str) -> str:
        """
        Заменить текущий экран без добавления нового уровня истории.
        """
        stack = self._stacks[chat_id]
        old_history = list(stack)

        if stack:
            stack[-1] = screen_id
        else:
            stack.append(screen_id)

        logger.debug(
            "navigation.replace | chat_id=%s | screen=%s | old=%s | new=%s",
            chat_id,
            screen_id,
            old_history,
            stack,
        )

        return screen_id

    def back(self, chat_id: int) -> str | None:
        """
        Вернуться на фактический предыдущий экран.

        Текущий экран удаляется из истории.
        Корневой экран остаётся в стеке.
        """
        stack = self._stacks.get(chat_id)
        old_history = list(stack or [])

        if not stack or len(stack) <= 1:
            logger.debug(
                "navigation.back | chat_id=%s | old=%s | result=None",
                chat_id,
                old_history,
            )
            return None

        stack.pop()
        result = stack[-1]

        logger.debug(
            "navigation.back | chat_id=%s | old=%s | result=%s | new=%s",
            chat_id,
            old_history,
            result,
            stack,
        )

        return result

    def home(self, chat_id: int) -> str | None:
        """Вернуть корневой экран и удалить промежуточную историю."""
        stack = self._stacks.get(chat_id)
        old_history = list(stack or [])

        if not stack:
            logger.debug(
                "navigation.home | chat_id=%s | old=%s | result=None",
                chat_id,
                old_history,
            )
            return None

        root = stack[0]
        self._stacks[chat_id] = [root]

        logger.debug(
            "navigation.home | chat_id=%s | old=%s | result=%s | new=%s",
            chat_id,
            old_history,
            root,
            self._stacks[chat_id],
        )

        return root

    def current(self, chat_id: int) -> str | None:
        """Вернуть текущий экран."""
        stack = self._stacks.get(chat_id)

        if not stack:
            return None

        return stack[-1]

    def history(self, chat_id: int) -> list[str]:
        """Вернуть копию истории."""
        return list(self._stacks.get(chat_id, []))

    def clear(self, chat_id: int) -> None:
        """Полностью удалить историю пользователя."""
        self._stacks.pop(chat_id, None)

    def has_history(self, chat_id: int) -> bool:
        """Проверить наличие истории."""
        return bool(self._stacks.get(chat_id))


class NavigationManager:
    """
    Универсальный менеджер навигации.

    Отвечает только за:
    - историю;
    - регистрацию экранов;
    - переходы;
    - получение renderer.

    Он не знает ничего о конкретных меню ZverTBot.
    """

    def __init__(
        self,
        stack: NavigationStack | None = None,
        registry: ScreenRegistry | None = None,
    ):
        self.stack = stack or NavigationStack()
        self.registry = registry or ScreenRegistry()

    def register(
        self,
        screen_id: str,
        renderer: Callable[..., Any] | None = None,
    ) -> Screen:
        """Зарегистрировать экран."""
        return self.registry.register(screen_id, renderer)

    def start(self, chat_id: int, screen_id: str) -> str:
        """Начать новую навигацию."""
        self.registry.require(screen_id)
        return self.stack.start(chat_id, screen_id)

    def go(self, chat_id: int, screen_id: str) -> str:
        """Перейти на экран с сохранением текущего экрана в истории."""
        self.registry.require(screen_id)
        return self.stack.push(chat_id, screen_id)

    def replace(self, chat_id: int, screen_id: str) -> str:
        """Заменить текущий экран без добавления уровня истории."""
        self.registry.require(screen_id)
        return self.stack.replace(chat_id, screen_id)

    def back(self, chat_id: int) -> str | None:
        """Вернуться на фактический предыдущий экран."""
        return self.stack.back(chat_id)

    def home(self, chat_id: int) -> str | None:
        """Вернуться в корень текущей истории."""
        return self.stack.home(chat_id)

    def current(self, chat_id: int) -> str | None:
        """Получить текущий экран."""
        return self.stack.current(chat_id)

    def history(self, chat_id: int) -> list[str]:
        """Получить историю экранов."""
        return self.stack.history(chat_id)

    def render(self, screen_id: str, *args: Any, **kwargs: Any) -> Any:
        """Отрисовать зарегистрированный экран через его renderer."""
        renderer = self.registry.require(screen_id).renderer

        if renderer is None:
            raise ValueError(f"Для экрана не зарегистрирован renderer: {screen_id}")

        return renderer(*args, **kwargs)

    def clear(self, chat_id: int) -> None:
        """Очистить историю."""
        self.stack.clear(chat_id)


navigation = NavigationManager()
