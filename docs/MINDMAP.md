# ZverTBot — MINDMAP навигации и архитектуры
**Актуализировано:** 03.09.2026 (полный аудит с исправлением всех расхождений)

## 🏠 ГЛАВНОЕ МЕНЮ АДМИНА
`main_menu_kb()` @ `ui/keyboards.py`
│
├── 👥 **Клиенты** (`nav:clients`)
│   └── `handle_navigation_callback()` → `navigation.go(cid, "clients_menu")` [ADMIN_CLIENTS]
│       └── `clients_menu_kb()`
│           ├── 👤 **Создать** (`nav:create`) → `create_menu_kb()`
│           │   ├── ⚡ VLESS (`add_vless`) → `handle_create_client_callback()` → `INPUT_REQUEST_MSGS` → `handle_add_input()` → `xray_add_user()`
│           │   └── 🛡 AWG (`add_awg`) → `handle_create_client_callback()` → `awg_add_user()`
│           │
│           ├── 👥 **Управление** (`nav:clients_manage`) → `clients_manage_menu_kb()`
│           │   ├── ⚡ VLESS (`nav:clients_vless`) → `render_vless_screen()` → `protocol_list_kb("vless")`
│           │   │   ├── `{username} [{ports}] 🗑` (`ask_del:vless:{username}`) → `handle_lists_delete_callback()` → `confirm_del:vless:{username}` → `delete_client()`
│           │   │   ├── 📤 QR (`qr:vless:{username}`) → `handle_qr_config_callback()` → выбор порта (`qr_select_{username}*{port}` или `qr_select_{username}_both`) → `qrencode`
│           │   │   ├── 📄 Конфиг (`conf:vless:{username}`) → `send_qr_or_conf(config_only=True)` + документ `RU_GEO_CONF`
│           │   │   ├── 📊 Статистика (`stats_vless_{username}`) → `handle_management_part4_callback()` → поток `_run_client_stats()`
│           │   │   └── 🔍 Поиск (`nav:clients_search_vless`) → `handle_search_callback()` → `process_search_input()`
│           │   │
│           │   └── 🛡 AWG (`nav:clients_awg`) → `render_awg_screen()` → `protocol_list_kb("awg")`
│           │       ├── `{username} 🗑` (`ask_del:awg:{username}`) → `confirm_del:awg:{username}` → `delete_client()`
│           │       ├── 📤 QR + config (`qr:awg:{username}`) → `send_qr_or_conf()`
│           │       ├── 📊 Статистика (`stats_awg_{username}`) → `_run_client_stats()`
│           │       └── 🔍 Поиск (`nav:clients_search_awg`) → `handle_search_callback()`
│           │
│           ├── ✏️ **Сменить имя** (`nav:clients_rename`) → `render_rename_screen()` → `process_rename_menu()` ("СтароеИмя НовоеИмя") → `rename_client()`
│           ├── 🔗 **Привязки** (`bindings_menu`) → `handle_bindings_part2_callback()` → `render_bindings_menu()`
│           │   ├── ✅ Активные (`bindings_active`) → `render_bindings_active()`
│           │   │   ├── 👤 `{clients}` (`bind_existing_{chat_id}`) → `handle_bind_existing_callback()` → `do_bind_{chat_id}_{username}`
│           │   │   └── ✖️ `{chat_id}` (`unbind_select_{chat_id}`) → `handle_bindings_part3_callback()` → `unbind_confirm_{chat_id}_{username}` → `remove_client_binding()`
│           │   └── ⏳ Ожидающие (`bindings_pending`) → `render_bindings_pending()`
│           │       ├── ✅ Привязать (`approve_bind_{chat_id}`) → `handle_bindings_part1_callback()` → `do_bind_{chat_id}_{username}`
│           │       └── ❌ Отклонить (`reject_bind_{chat_id}`) → `remove_pending_binding()`
│           │
│           └── 🎫 **Тикеты** (`nav:admin_tickets`) → `handle_admin_tickets()` (меню со счётчиками)
│               ├── 🆕 Новые (`nav:admin_tickets_new`) → `show_new_tickets()` (status="open")
│               ├── 🛠 В работе (`nav:admin_tickets_working`) → `show_working_tickets()` (status="answered", с историей)
│               └── 📚 Закрытые (`nav:admin_tickets_closed`) → `show_closed_tickets()` (пагинация `admin_closed_page:{page}`, детализация `admin_closed_ticket:{tid}`)
│
├── 🖥 **Статус** (`status`)
│   └── `handle_management_part4_callback()` → поток `_run_status()` → `get_status_text()` (автоудаление через 12с)
│
├── 🌐 **Сеть и безопасность** (`nav:manage`) → `manage_menu_kb()`
│   ├── 🔐 **SSH** (`ssh_menu`) → `handle_ssh_callback()` → `render_ssh_menu()`
│   │   ├── 🔑 Список (`ssh_list`) → `render_ssh_list()`
│   │   ├── 📜 История (`ssh_history`) → `render_ssh_history()`
│   │   ├── 🗑️ Удалить (`ssh_delete`) → `render_ssh_delete()` → `ssh_delete_confirm_{comment}` → `ssh_delete_final_{comment}` → `delete_ssh_key()`
│   │   └── 📥 Экспорт (`ssh_export`) → `send_document(authorized_keys)`
│   │
│   ├── 🔒 **Fail2ban** (`fail2ban_menu`) → `handle_fail2ban_callback()` → `render_fail2ban_menu()`
│   │   ├── 📜 Логи банов (`fail2ban_logs`) → `render_fail2ban_logs()`
│   │   └── 🔓 Разбан IP (`fail2ban_unban`) → `navigation.go(cid, FAIL2BAN_UNBAN_INPUT)` → `render_fail2ban_unban_input()` → ввод IP (с `validate_ip`) → `process_fail2ban_unban()` → `unban_ip()`
│   │
│   └── 🌐 **Сеть** (`nav:network`) → `network_menu_kb()`
│       ├── 🚀 Speedtest (`speedtest`) → `render_speedtest()` → поток `_run_speedtest()`
│       ├── 🔍 Мой внешний IP (`my_external_ip`) → `create_ip_token()` + `start_ip_server_once(8085)` → URL-кнопка (автоудаление 15с)
│       ├── 🔍 Сканирование портов (`port_scan`) → `handle_portscan_callback()` → `render_port_scan()` → `scan_open_ports()`
│       ├── 📡 MTR диагностика (`net_mtr`) → `render_net_mtr()` → `mtr_target_{target}` или ввод текста → `_run_mtr()` (asyncio)
│       └── 🌐 Репутация IP (`ip_reputation`) → `handle_ip_reputation_callback()` → `render_ip_reputation()` → `check_ip_reputation()`
│
├── 🔧 **Службы** (`nav:system`) → `system_menu_kb()`
│   ├── 🔁 Рестарт ZverTBot (`restart_bot`) → `restart_service_detached("zvertbot")` → `sys.exit(0)`
│   ├── 📜 Логи ZverTBot (`log_bot`) → `get_service_logs("bot")` + `log_close_kb()`
│   ├── 🔁 Рестарт AWG (`restart_awg`) → поток `_run_service_restart("awg-quick@awg0")`
│   ├── 📜 Логи AWG (`log_awg`) → `get_service_logs("awg")`
│   ├── 🔁 Рестарт Xray (`restart_xray`) → поток `_run_service_restart("xray")`
│   ├── 📜 Логи Xray (`log_xray`) → `get_service_logs("xray")`
│   ├── 📊 Процессы (`processes_menu`) → `handle_processes_callback()` → `render_processes_menu()`
│   │   ├── 📊 Топ процессов (`processes_top`) → `render_processes_top()` (CPU)
│   │   │   ├── 🔥 CPU (`processes_top_cpu`) → `navigation.replace()` → `render_processes_top_cpu()`
│   │   │   └── 💾 RAM (`processes_top_ram`) → `navigation.replace()` → `render_processes_top_ram()`
│   │   ├── 🔍 Поиск процесса (`process_search`) → `navigation.go(cid, PROCESS_SEARCH_INPUT)` → `render_processes_search_input()` → ввод имени → `process_search_handler()`
│   │   └── 🛑 Завершить процесс (`process_kill`) → `navigation.go(cid, PROCESS_KILL_INPUT)` → `render_processes_kill_input()` → ввод PID → `process_kill_handler()` → `kill_process_by_pid()`
│   ├── 🤖 **AI-диагностика** (`nav:ai_logs`) → `ai_diagnosis_menu_kb()`
│   │   ├── 🤖 ZverTBot (`ai_log_bot`), 🛡 AWG (`ai_log_awg`), ⚡ Xray (`ai_log_xray`) → `handle_ai_diagnosis_callback()` → `analyze_logs_with_llm()`
│   │   └── 🖥 Сервер (`ai_server_health`) → `collect_server_health()` → `analyze_logs_with_llm(report, "server")`
│   ├── 🧹 Очистка диска (`confirm_cleanup`) → `render_cleanup()` → `exec_cleanup` → поток `_run_cleanup()` → `run_disk_cleanup()`
│   └── 🏠 Главное меню (`nav:home`)
│
├── 📊 **Аналитика** (`nav:analytics`) → `analytics_menu_kb()`
│   ├── 📊 Отчёт по трафику (`weekly_report`) → поток `_run_weekly_report()` → `USAGE_JSON` → ТОП-7 клиентов
│   ├── 📈 Статистика бота (`bot_stats`) → поток `_run_bot_stats()` → `get_bot_stats_text()`
│   ├── 📜 История действий (`show_history`) → `render_action_history()` → поток `_run_show_history()` → `show_history_action()`
│   └── 🛡 Паспорт сервера (`passport_check`) → `handle_passport_check()` → `scripts/check_passport.py` (timeout=30) → сохранение в `/tmp/zvertbot_reports/` → `get_passport_file:{filename}`
│
└── 💾 **Бэкапы** (`nav:backups`) → `backups_menu_kb()`
    ├── 💾 Создать бэкап (`create_backup`) → `run_manual_backup()` (поток) → `bash BACKUP_SCRIPT` (timeout=300) → чтение `RCLONE_STATUS_JSON`
    └── 📜 История бэкапов (`nav:backup_history`) → `render_backup_history()` → `get_backup_history_text()` (локальные + `rclone size` с `BACKUP_REMOTE`:`BACKUP_ROOT_DIR`)

---

## 👤 КЛИЕНТСКОЕ МЕНЮ
Вход: `/start` → `cmd_start()` → если `is_client()` → `navigation.start(cid, CLIENT_HOME)` → `get_client_menu(cid)`
│
├── **1 аккаунт** → СРАЗУ экран аккаунта: `client_account_kb(username, proto)`
└── **Несколько аккаунтов** → `client_accounts_kb()` (row_width=2)
    ├── 🚀/🛡️ `{account}` (`client:account:{username}`) → `_open_account()` → `render_client_account()`
    ├── 🆘 Создать тикет (`create_ticket`)
    └── 📖 Инструкция (`nav:client_help`) → `render_client_help()`
    │
    └── **Экран аккаунта** (`client:account:{username}`) → `client_account_kb(username, proto)` (row_width=2)
        │
        ├── **[Оба протокола] Строка 1:**
        │   ├── 📊 Статистика (`client:stats:{username}`) → `handle_client_stats()` (поток) → `get_client_stats_text()`
        │   └── 📱 QR-код (`client:conf:{username}`) → `handle_client_conf()` → `send_qr_or_conf()`
        │
        ├── **[VLESS] Строка 2:**
        │   ├── 🆘 Создать тикет (`create_ticket`)
        │   └── 📦 Конфигурация + RU (`client:conf_ru:{username}`) → `handle_client_conf_ru()` → `send_qr_or_conf(config_only=True)` + документ `RU_GEO_CONF`
        │
        ├── **[VLESS] Строка 3:**
        │   └── 📖 Инструкция (`nav:client_help`) → `render_client_help()`
        │
        └── **[AWG] Строка 2:**
            ├── 🆘 Создать тикет (`create_ticket`)
            └── 📖 Инструкция (`nav:client_help`) → `render_client_help()`

---

## 🎫 ТИКЕТЫ
### Клиент (`handlers/client/tickets.py`)
- `create_ticket` → проверка привязки → лимит 1 активный → выбор темы → `_ticket_drafts` (TTL 1800) → `process_ticket_description()` → `ticket_service.create_ticket()` → уведомление ADMIN_CHATS
- `ticket_reply:{ticket_id}` → `handle_ticket_reply()` → `_ticket_reply_drafts` → `process_ticket_reply()` → `ticket_service.add_message()` → `set_status("open")` → уведомление админам
- `ticket_reply_cancel:{ticket_id}` → очистка черновика

### Админ (`handlers/admin/tickets.py`)
- `/tickets` → `cmd_admin_tickets()` (карточки открытых)
- `nav:admin_tickets` → `handle_admin_tickets()` (меню со счётчиками)
- `nav:admin_tickets_new` → `show_new_tickets()` (status="open")
- `nav:admin_tickets_working` → `show_working_tickets()` (status="answered", с историей)
- `nav:admin_tickets_closed` → `show_closed_tickets()` (status="closed", **пагинация** через `admin_closed_page:{page}`, **детальный просмотр** через `admin_closed_ticket:{tid}`)
- `admin_reply_ticket:{tid}` → `handle_admin_reply()` → `_admin_reply_drafts` → `process_admin_reply()` → `add_message("admin")` → `set_status("answered")`
- `admin_close_ticket:{tid}` → `handle_admin_close()` → `close_ticket()` → пересборка карточки

### Сервис (`services/ticket_service.py`)
- `ACTIVE_TICKET_STATUSES = ("open", "answered")`
- Мутации под `@client_operation_lock`
- `create_ticket()`: ID = `uuid4()[:8]`, отказ при активном тикете

---

## ⚙️ КОМАНДЫ БОТА (`handlers/commands.py`)
- `/start`, `/help` → `cmd_start()`: очистка степа, `is_admin` → `ADMIN_HOME`, `is_client` → `CLIENT_HOME`, иначе → кнопка `request_bind`
- `/my_id` → `cmd_my_id()`: если клиент → список аккаунтов, иначе → `add_pending_binding()` + уведомление ADMIN_CHATS с кнопками approve/reject
- `/rename` → `cmd_rename()`: валидация → `rename_client()`
- `/bind` → `cmd_bind()`: `add_client_binding()` (лимит 4)
- `/unbind` → `cmd_unbind()`: `remove_client_binding()`
- `/pending` → `cmd_pending()`: список ожидающих + кнопки approve
- `/status` → `cmd_status()`: `get_status_text()`
- `/history` → `cmd_history()`: `show_history_action()`

---

## 📦 СЕРВИСЫ И ХРАНИЛИЩА
### Xray (`services/xray/`)
- `client_manager.py`: `xray_add_user()` (генерация UUID, `add_client_to_all_inbounds`, `save_xray_config`, `reload_xray`)
- `config_manager.py`: `load_xray_config()`, `save_xray_config()` (atomic_write + `xray run -test` на candidate-файле), `get_vless_inbounds()`, `rename_client_in_config()`
- `link_generator.py`: `xray_get_link()`, `xray_get_ports()`, `_get_reality_public_key()` (через `xray x25519`)

### AmneziaWG (`services/awg/`)
- `client_manager.py`: `awg_add_user()` (genkey, `find_free_awg_ip`, `awg set`, `add_peer_to_config`), `awg_del_user()` (`awg set peer remove`, `remove_peer_from_config` с rollback при ошибке)
- `config_generator.py`: `awg_get_config()` (динамическое чтение параметров обфускации Jc, Jmin, S1-S4, H1-H4 и PrivateKey из `AWG_CONF`, генерация PublicKey через `awg pubkey`)
- `config_manager.py`: `add_peer_to_config()`, `remove_peer_from_config()` (поиск по PublicKey, удаление 4 строк), `rename_peer_in_config()` (с сохранением line endings)
- `ip_manager.py`: `get_used_awg_ips()` (реестр + `awg show awg0`), `find_free_awg_ip()` (диапазон 10.66.66.8-99)

### Прочие сервисы
- `client_service.py`: `rename_client()` (rollback-логика с флагом `awg_config_changed`), `delete_client()`, `send_qr_or_conf()`, `show_history_action()`
- `stats.py`: `get_status_text()` (uptime, cpu, ram, swap, disk, services), `get_bot_stats_text()`, `get_client_stats_text()`
- `backup.py`: `get_backup_history_text()` (локальные ls + `rclone size` с `BACKUP_REMOTE` + `RCLONE_STATUS_JSON`)
- `llm_diagnosis.py`: `analyze_logs_with_llm()` (sanitize_logs, `_has_problem_events`, retry по моделям, filter_unconfirmed_recommendations)

---

## ⚙️ РЕГИСТРАЦИЯ ЭКРАНОВ И РОУТИНГ
### Точка входа (`main.py`)
1. `load_handler_modules()`
2. `register_navigation_screens()`
3. `register_callback_router(bot)`
4. `check_callbacks()`
5. `bot.infinity_polling()`

### Навигация (`core/navigation.py`)
- `ScreenRegistry`: `register()`, `require()`, `ids()`
- `NavigationStack`: `start()`, `push()` (go), `replace()`, `back()`, `home()`
- `NavigationManager`: глобальный экземпляр `navigation`, `render()` вызывает зарегистрированный renderer
- **Fallback**: `back()` или `home()` возвращает `None` → `navigation.start(cid, ADMIN_HOME)` или `CLIENT_HOME`

### Callback-роутер (`core/callback_router.py`)
- `CallbackRoute(pattern, handler, access, prefix)`
- **Приоритет**: exact > prefix (сортировка по длине prefix от большего к меньшему)
- **Политика доступа**:
  - `PUBLIC`: `request_bind`, `create_ticket`, `ticket_topic_*`, `ticket_reply:*`, `ticket_reply_cancel:*`
  - `CLIENT`: `nav:client_*`, `client:account:*`, `client:stats:*`, `client:conf:*`, `client:conf_ru:*` (+ проверка `username in get_client_list(cid)`)
  - `CLIENT_OR_ADMIN`: `qr_select_*` (+ проверка принадлежности)
  - `ADMIN`: все остальные
- Отказ → `CallbackResponse("❌ Недостаточно прав.")`
- `finally`: `safe_answer_callback()`

### Проверка целостности (`core/callback_checker.py`)
- Сканирует `ui/`, `handlers/`, `services/`, `core/` на `callback_data=`
- Подставляет `{CLIENT_CONF_CALLBACK_PREFIX}` → `client:conf:`
- Динамические (`{` или `*`) → `has_prefix_handler()` (проверка `prefix.startswith(route.pattern)`)
- Реальные → `resolve()`
- Лог: `Callback checker: {total} всего (реальных: {real}, динамических: {dynamic})`

---

## 📝 ПРИМЕЧАНИЯ ПО АРХИТЕКТУРЕ
1. **Разделители в callback**:
   - **Двоеточие (`:`)** — основной стандарт для структурированных данных:
     - Клиентские аккаунты: `client:account:{username}`, `client:conf:{username}`, `client:conf_ru:{username}`
     - Админские действия с клиентами: `ask_del:{proto}:{username}`, `confirm_del:{proto}:{username}`, `conf:{proto}:{username}`
     - QR-коды: `qr:{proto}:{username}`
     - Тикеты: `admin_reply_ticket:{tid}`, `ticket_reply:{tid}`, `ticket_reply_cancel:{ticket_id}`, `admin_closed_page:{page}`, `admin_closed_ticket:{tid}`
   - **Звёздочка (`*`)** — используется только для выбора порта в QR: `qr_select_{username}*{port}`
   - **Подчёркивание (`_`)** — для статистики (`stats_{proto}_{username}`) и исторических callback привязок/SSH (`bind_existing_{chat_id}`, `do_bind_{chat_id}_{username}`, `ssh_delete_confirm_{comment}`).

2. **Навигационный стек для ввода данных**:
   - `fail2ban_unban`, `process_search`, `process_kill` теперь используют полноценные экраны (`FAIL2BAN_UNBAN_INPUT`, `PROCESS_SEARCH_INPUT`, `PROCESS_KILL_INPUT`) с `navigation.go()`, что устраняет анти-паттерн "inline без стека" и позволяет корректно удалять сообщения ввода.

3. **Состояния** (`core/state.py`):
   - `INPUT_REQUEST_MSGS`, `LAST_MAIN_MENU_MSGS`, `LAST_CLIENT_MENU_MSGS`, `LAST_STATUS_MSGS`, `LAST_MY_ID_MSGS`, `LAST_MY_ID_ADMIN_MSGS`.
   - Добавлена функция `replace_message_id()` для корректного обновления ID при fallback-отправке.

4. **Доступ** (`core/access.py`):
   - `is_admin()`: `str(chat_id) in ADMIN_CHATS`
   - `is_client()`: `bool(get_client_accounts(chat_id))`

5. **Блокировки**:
   - `@client_operation_lock` используется во всех мутациях клиентов (rename, delete, add, ticket creation) для предотвращения race conditions.

6. **Атомарность**:
   - `save_xray_config()` и `save_awg_config()` используют `utils.atomic.atomic_write()` (запись во временный файл + `os.replace`).
   - `save_xray_config()` дополнительно вызывает `xray run -test` на candidate-файле перед заменой рабочего.

7. **Улучшения конфигурации и надёжности**:
   - `AWG_CONF` теперь динамически разрешается через `resolve_awg_conf()` (по умолчанию `/etc/amnezia/amneziawg/awg0.conf`).
   - Параметры AmneziaWG (Jc, Jmin, S1-S4, H1-H4, PrivateKey) теперь динамически читаются из `AWG_CONF`, а не захардкожены.
   - `awg_del_user()` теперь выполняет rollback `awg set peer allowed-ips`, если удаление из конфига не удалось.
   - `rename_peer_in_config()` теперь корректно сохраняет исходные line endings (`\r\n` или `\n`).
   - `_has_problem_events()` в `llm_diagnosis.py` проверяет наличие реальных проблемных событий перед применением строгой фильтрации рекомендаций.

---

**MINDMAP.md полностью соответствует актуальному коду.**
