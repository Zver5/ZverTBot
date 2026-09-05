"""
Проверка единого registry callback-маршрутов.

CALLBACK_ROUTES является единственным источником истины.
EXACT_ROUTES и PREFIX_ROUTES — производные индексы.
"""

from core import callback_router as router


def test_every_route_is_valid():
    assert router.CALLBACK_ROUTES

    for route in router.CALLBACK_ROUTES:
        assert route.pattern
        assert callable(route.handler)
        assert isinstance(route.access, router.CallbackAccess)

        if route.prefix:
            assert route.pattern not in router.EXACT_ROUTES
        else:
            assert route.pattern in router.EXACT_ROUTES


def test_exact_routes_are_built_from_registry():
    expected = {
        route.pattern: route for route in router.CALLBACK_ROUTES if not route.prefix
    }

    assert expected == router.EXACT_ROUTES


def test_prefix_routes_are_built_from_registry():
    expected = tuple(
        sorted(
            (route for route in router.CALLBACK_ROUTES if route.prefix),
            key=lambda route: len(route.pattern),
            reverse=True,
        )
    )

    assert expected == router.PREFIX_ROUTES


def test_registered_exact_routes_are_resolvable():
    for route in router.CALLBACK_ROUTES:
        if route.prefix:
            continue

        assert router.resolve(route.pattern) is route
        assert router.get(route.pattern) is route.handler


def test_registered_prefix_routes_are_resolvable():
    for route in router.CALLBACK_ROUTES:
        if not route.prefix:
            continue

        callback = route.pattern + "test"

        resolved = router.resolve(callback)

        assert resolved is not None
        assert resolved.handler is route.handler


def test_exact_route_wins_over_matching_prefix():
    overlaps = [
        route
        for route in router.CALLBACK_ROUTES
        if not route.prefix
        and any(
            route.pattern.startswith(prefix.pattern)
            for prefix in router.CALLBACK_ROUTES
            if prefix.prefix
        )
    ]

    assert not overlaps
