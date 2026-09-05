from core.callback_router import get


def test_bindings_routes():
    from handlers.admin.bindings import (
        handle_bind_existing_callback,
        handle_bindings_part1_callback,
        handle_bindings_part2_callback,
        handle_bindings_part3_callback,
    )

    assert get("approve_bind_12345") == handle_bindings_part1_callback
    assert get("reject_bind_12345") == handle_bindings_part1_callback
    assert get("do_bind_12345") == handle_bindings_part1_callback
    assert get("bind_existing_12345") == handle_bind_existing_callback

    assert get("bindings_menu") == handle_bindings_part2_callback

    assert get("unbind_select_12345") == handle_bindings_part3_callback
