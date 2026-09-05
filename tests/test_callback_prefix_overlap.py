"""
Проверка специфичности callback prefix-маршрутов.

Архитектурное правило:
- exact проверяется раньше prefix;
- среди prefix выбирается самый длинный маршрут.
"""

from core import callback_router as router


def test_prefixes_are_sorted_by_specificity():
    prefixes = list(router.PREFIX_ROUTES)

    lengths = [len(route.pattern) for route in prefixes]

    assert lengths == sorted(lengths, reverse=True)


def test_qr_select_prefix_wins_over_qr_prefix():
    assert router.resolve("qr_select_alice_both").pattern == "qr_select_"
    assert router.resolve("qr_select_alice*443").pattern == "qr_select_"


def test_longest_prefix_wins_when_prefixes_overlap():
    short = router.CallbackRoute(
        pattern="test_",
        handler=lambda *args: "short",
        access=router.CallbackAccess.ADMIN,
        prefix=True,
    )

    long = router.CallbackRoute(
        pattern="test_special_",
        handler=lambda *args: "long",
        access=router.CallbackAccess.ADMIN,
        prefix=True,
    )

    original = router.PREFIX_ROUTES

    try:
        router.PREFIX_ROUTES = tuple(
            sorted(
                (long, short),
                key=lambda route: len(route.pattern),
                reverse=True,
            )
        )

        assert router.resolve("test_special_value") is long
        assert router.resolve("test_other_value") is short
    finally:
        router.PREFIX_ROUTES = original
