from data.storage import load_client_bindings
from services.client_service import get_client_protocol, get_users_list
from ui.keyboards import client_account_kb, client_accounts_kb

CLIENT_ACCOUNT_PREFIX = "client:account:"
CLIENT_STATS_PREFIX = "client:stats:"


def get_client_list(chat_id):
    bindings = load_client_bindings()
    client_list = bindings.get(str(chat_id), [])

    if not isinstance(client_list, list):
        client_list = [client_list] if client_list else []

    return client_list


def get_client_menu(chat_id):
    """
    Единый renderer главного экрана клиента.
    """
    client_list = get_client_list(chat_id)

    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")

    if len(client_list) == 1:
        username = client_list[0]
        proto = get_client_protocol(username)

        if proto is not None:
            return (
                client_account_kb(username, proto),
                f"👋 Привет, *{username}*!\nВыберите действие:",
                True,
            )

    return (
        client_accounts_kb(
            client_list,
            users_vless,
            users_awg,
        ),
        "👋 Привет! Выберите аккаунт:",
        False,
    )


def get_client_account_screen(username):
    proto = get_client_protocol(username)

    if proto is None:
        return None

    return (
        client_account_kb(username, proto),
        f"👤 Аккаунт: *{username}*\n\nВыберите действие:",
        True,
    )
