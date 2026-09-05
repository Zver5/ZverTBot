"""
Тесты универсального navigation core.

Эти тесты не зависят от существующих Telegram handlers.
"""

import pytest

from core.navigation import (
    NAV_BACK_CALLBACK,
    NAV_HOME_CALLBACK,
    NavigationManager,
    NavigationStack,
    ScreenRegistry,
)


class TestNavigationStack:
    """Проверка чистой истории экранов."""

    def test_start_creates_root(self):
        nav = NavigationStack()

        assert nav.start(100, "main") == "main"
        assert nav.current(100) == "main"
        assert nav.history(100) == ["main"]

    def test_push_creates_history(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "manage")
        nav.push(100, "network")

        assert nav.history(100) == ["main", "manage", "network"]
        assert nav.current(100) == "network"

    def test_push_same_screen_does_not_duplicate(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "manage")
        nav.push(100, "manage")

        assert nav.history(100) == ["main", "manage"]

    def test_back_returns_actual_previous_screen(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "manage")
        nav.push(100, "network")
        nav.push(100, "port_scan")

        assert nav.back(100) == "network"
        assert nav.back(100) == "manage"
        assert nav.back(100) == "main"
        assert nav.back(100) is None

    def test_back_keeps_root(self):
        nav = NavigationStack()

        nav.start(100, "main")

        assert nav.back(100) is None
        assert nav.current(100) == "main"
        assert nav.history(100) == ["main"]

    def test_replace_on_empty_stack_creates_screen(self):
        nav = NavigationStack()

        assert nav.replace(100, "main") == "main"
        assert nav.history(100) == ["main"]
        assert nav.current(100) == "main"

    def test_has_history(self):
        nav = NavigationStack()

        assert nav.has_history(100) is False

        nav.start(100, "main")

        assert nav.has_history(100) is True

        nav.clear(100)

        assert nav.has_history(100) is False

    def test_replace_does_not_add_history_level(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "manage")
        nav.replace(100, "network")

        assert nav.history(100) == ["main", "network"]
        assert nav.back(100) == "main"

    def test_home_keeps_only_root(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "manage")
        nav.push(100, "network")
        nav.push(100, "port_scan")

        assert nav.home(100) == "main"
        assert nav.history(100) == ["main"]

    def test_users_have_independent_histories(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "network")

        nav.start(200, "main")
        nav.push(200, "analytics")

        assert nav.history(100) == ["main", "network"]
        assert nav.history(200) == ["main", "analytics"]

    def test_home_on_empty_history_returns_none(self):
        nav = NavigationStack()

        assert nav.home(100) is None

    def test_history_for_unknown_user_is_empty(self):
        nav = NavigationStack()

        assert nav.history(100) == []

    def test_clear_removes_only_selected_user(self):
        nav = NavigationStack()

        nav.start(100, "main")
        nav.push(100, "network")

        nav.start(200, "main")
        nav.push(200, "analytics")

        nav.clear(100)

        assert nav.history(100) == []
        assert nav.history(200) == ["main", "analytics"]


class TestScreenRegistry:
    """Проверка отделения screen ID от renderer."""

    def test_register_and_get_screen(self):
        registry = ScreenRegistry()

        def render():
            return "network"

        screen = registry.register("network", render)

        assert screen.screen_id == "network"
        assert screen.renderer is render
        assert registry.get("network") is screen

    def test_unknown_screen_returns_none(self):
        registry = ScreenRegistry()

        assert registry.get("unknown") is None

    def test_require_unknown_screen_raises(self):
        registry = ScreenRegistry()

        with pytest.raises(KeyError, match="unknown"):
            registry.require("unknown")

    def test_clear_removes_registered_screens(self):
        registry = ScreenRegistry()

        registry.register("main")
        registry.register("network")

        registry.clear()

        assert registry.ids() == ()
        assert registry.get("main") is None

    def test_ids_returns_registered_screen_ids(self):
        registry = ScreenRegistry()

        registry.register("main")
        registry.register("network")

        assert registry.ids() == ("main", "network")

    def test_empty_screen_id_rejected(self):
        registry = ScreenRegistry()

        with pytest.raises(ValueError):
            registry.register("")


class TestNavigationManager:
    """Проверка публичного API новой навигации."""

    def test_go_requires_registered_screen(self):
        nav = NavigationManager()

        nav.register("main")
        nav.start(100, "main")

        with pytest.raises(KeyError):
            nav.go(100, "unknown")

    def test_manager_replace(self):
        nav = NavigationManager()

        nav.register("main")
        nav.register("network")
        nav.start(100, "main")

        assert nav.replace(100, "network") == "network"
        assert nav.history(100) == ["network"]

    def test_manager_home_current_history_and_clear(self):
        nav = NavigationManager()

        nav.register("main")
        nav.register("network")
        nav.start(100, "main")
        nav.go(100, "network")

        assert nav.current(100) == "network"
        assert nav.history(100) == ["main", "network"]
        assert nav.home(100) == "main"

        nav.clear(100)

        assert nav.current(100) is None
        assert nav.history(100) == []

    def test_render_requires_renderer(self):
        nav = NavigationManager()
        nav.register("main")

        with pytest.raises(
            ValueError,
            match="Для экрана не зарегистрирован renderer",
        ):
            nav.render("main")

    def test_render_calls_registered_renderer(self):
        nav = NavigationManager()

        def renderer(value):
            return f"rendered:{value}"

        nav.register("main", renderer)

        assert nav.render("main", "test") == "rendered:test"

    def test_navigation_does_not_depend_on_parent(self):
        """
        Экран не хранит информацию о родителе.

        Один и тот же screen_id можно открыть из разных мест,
        и Back возвращает именно фактический предыдущий экран.
        """
        nav = NavigationManager()

        for screen_id in (
            "main",
            "manage",
            "network",
            "system",
            "port_scan",
        ):
            nav.register(screen_id)

        nav.start(100, "main")
        nav.go(100, "manage")
        nav.go(100, "network")
        nav.go(100, "port_scan")

        assert nav.back(100) == "network"

        nav.clear(100)

        nav.start(100, "main")
        nav.go(100, "manage")
        nav.go(100, "system")
        nav.go(100, "port_scan")

        assert nav.back(100) == "system"

    def test_renderer_is_separate_from_navigation_history(self):
        nav = NavigationManager()

        def render_network():
            return "network-rendered"

        nav.register("network", render_network)
        nav.register("main")

        nav.start(100, "main")
        nav.go(100, "network")

        assert nav.current(100) == "network"
        assert nav.registry.require("network").renderer is render_network
        assert nav.render("network") == "network-rendered"

    def test_renderer_can_be_registered_for_feature_screen(self):
        nav = NavigationManager()

        calls = []

        def render_feature(bot, cid, message_id):
            calls.append((bot, cid, message_id))
            return True

        nav.register("main")
        nav.register("feature_menu", render_feature)

        nav.start(100, "main")
        nav.go(100, "feature_menu")

        assert nav.registry.require("feature_menu").renderer is render_feature
        assert nav.current(100) == "feature_menu"

        result = nav.render("feature_menu", "bot", 100, 555)

        assert result is True
        assert calls == [("bot", 100, 555)]

    def test_clear_removes_navigation_for_user(self):
        nav = NavigationManager()

        nav.register("main")
        nav.register("network")

        nav.start(100, "main")
        nav.go(100, "network")
        nav.clear(100)

        assert nav.current(100) is None
        assert nav.history(100) == []


class TestNavigationCallbacks:
    """Защита единого callback-контракта."""

    def test_back_callback_is_universal(self):
        assert NAV_BACK_CALLBACK == "nav:back"

    def test_home_callback_is_universal(self):
        assert NAV_HOME_CALLBACK == "nav:home"
