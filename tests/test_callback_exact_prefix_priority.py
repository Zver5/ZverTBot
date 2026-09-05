from core.callback_router import all_callbacks, all_prefixes, resolve


def test_exact_callbacks_have_priority_over_matching_prefixes():
    exact_routes = all_callbacks()
    prefixes = all_prefixes()

    overlaps = {
        callback: [prefix for prefix in prefixes if callback.startswith(prefix)]
        for callback in exact_routes
    }

    overlaps = {
        callback: matching_prefixes
        for callback, matching_prefixes in overlaps.items()
        if matching_prefixes
    }

    if not overlaps:
        return

    failures = []

    for callback, matching_prefixes in overlaps.items():
        expected_route = exact_routes[callback]
        result = resolve(callback)

        if result is not expected_route:
            failures.append(
                f"{callback!r} пересекается с {matching_prefixes!r}: "
                f"ожидался {expected_route.handler.__name__}, "
                f"получен "
                f"{getattr(getattr(result, 'handler', None), '__name__', None)}"
            )

    assert not failures, "\n".join(failures)
