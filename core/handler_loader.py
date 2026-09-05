"""Централизованная загрузка модулей, регистрирующих Telegram handlers."""

from importlib import import_module

HANDLER_MODULES = [
    "handlers.commands",
    "handlers.admin.tickets",
]


def load_handler_modules():
    """Принудительно загрузить модули, регистрирующие Telegram handlers."""

    for module_name in HANDLER_MODULES:
        import_module(module_name)
