from core.navigation import navigation
from handlers.navigation_registry import register_navigation_screens
from ui import screens
from ui.screens import CLIENT_ACCOUNT, CLIENT_HELP, CLIENT_HOME


def test_all_declared_navigation_screens_are_registered_with_renderers():
    declared = {
        value
        for name, value in vars(screens).items()
        if name.isupper() and isinstance(value, str)
    }
    declared.update(
        {
            CLIENT_HOME,
            CLIENT_HELP,
            CLIENT_ACCOUNT,
        }
    )

    registered = set(navigation.registry.ids())

    assert registered == declared

    for screen_id in declared:
        screen = navigation.registry.require(screen_id)
        assert screen.renderer is not None


def test_navigation_registry_contains_expected_screen_count():
    assert len(navigation.registry.ids()) == 39


def test_navigation_registration_is_complete_and_deterministic():
    before = navigation.registry.ids()

    register_navigation_screens()

    after = navigation.registry.ids()

    assert after == before
