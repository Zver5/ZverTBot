# ZverTBot — развёртывание и перенос

Документ описывает сборку deploy-архива, установку ZverTBot на новый VPS, настройку дополнительных компонентов и перенос проекта между серверами.

## Назначение

Deploy-механизм предназначен для **повторяемого развёртывания программной части ZverTBot на чистом VPS**.

Основной принцип:

> **Переносится программная часть проекта, а runtime-состояние, секреты и инфраструктурные параметры конкретного VPS создаются заново на целевой системе.**

Поэтому deploy-архив не является копией работающего `/opt/ZverTBot`. Он содержит только компоненты, необходимые для установки проекта.

Это позволяет использовать один deploy-архив для разных совместимых VPS без переноса старого рабочего окружения.

---

# 1. Состав deploy-механизма

Основные компоненты находятся в каталоге `deploy/`:

```text
deploy/
├── build.sh
├── output/
└── botinstaller/
    ├── install.sh
    ├── checks.sh
    ├── system_tuning.sh
    ├── packages.txt
    ├── .env.example
    ├── examples/
    │   ├── awg0.conf.example
    │   └── xray.config.example.json
    └── systemd/
        ├── core/
        └── optional/
```

| Компонент                               | Назначение                            |
| --------------------------------------- | ------------------------------------- |
| `deploy/build.sh`                       | Сборка переносимого deploy-архива     |
| `deploy/output/`                        | Результаты сборки                     |
| `deploy/botinstaller/install.sh`        | Установка ZverTBot на целевой VPS     |
| `deploy/botinstaller/packages.txt`      | Список системных пакетов              |
| `deploy/botinstaller/checks.sh`         | Предварительные проверки системы      |
| `deploy/botinstaller/system_tuning.sh`  | Системные настройки ZverTBot          |
| `deploy/botinstaller/.env.example`      | Шаблон конфигурации                   |
| `deploy/botinstaller/examples/`         | Примеры конфигураций Xray и AmneziaWG |
| `deploy/botinstaller/systemd/core/`     | Основные systemd-компоненты           |
| `deploy/botinstaller/systemd/optional/` | Дополнительные компоненты             |

---

# 2. Архитектура развёртывания

```text
Рабочая копия ZverTBot
        │
        ▼
  deploy/build.sh
        │
        ▼
ZverTBot-deploy-VERSION.tar.gz
        │
        ▼
     install.sh
        │
        ├── системные пакеты
        ├── ZverTBot
        ├── Python .venv
        ├── systemd
        ├── GeoIP
        ├── Xray       (опционально)
        └── AmneziaWG  (опционально)
        │
        ▼
     Новый VPS
        │
        ├── /opt/ZverTBot
        ├── .env
        ├── runtime state
        └── systemd services/timers
```

Xray и AmneziaWG являются дополнительными компонентами. Они устанавливаются только при передаче соответствующих ключей installer.

---

# 3. Сборка deploy-архива

Сборка выполняется из корня проекта:

```bash
cd ~/ZverTBot
./deploy/build.sh
```

Сборщик:

* определяет проект и текущую версию;
* проверяет корректность версии;
* создаёт временный каталог сборки;
* копирует программную часть проекта;
* исключает Git-историю;
* исключает виртуальное окружение;
* исключает секреты;
* исключает Python-кэши;
* исключает тестовые артефакты;
* исключает runtime-состояние;
* исключает журналы и временные данные;
* добавляет `.env.example`;
* добавляет шаблоны Xray и AmneziaWG;
* формирует переносимый архив;
* подготавливает `install.sh`.

`deploy/output/` является каталогом результатов сборки и не включается внутрь самого deploy-архива.

Результат:

```text
deploy/output/
├── install.sh
└── ZverTBot-deploy-VERSION.tar.gz
```

---

# 4. Что входит в deploy-архив

Архив содержит программную часть ZverTBot и необходимые для установки шаблоны.

В него не должны попадать данные, относящиеся к конкретному рабочему VPS.

## Исключаемые данные

Из deploy-сборки исключаются:

* `.git/`;
* `.venv/`;
* `.env`;
* Python-кэши;
* результаты тестов;
* runtime JSON-файлы;
* журналы;
* резервные копии;
* временные файлы;
* локальные эксплуатационные данные;
* `data/geoip/`;
* временные patch-скрипты.

Deploy-архив поэтому не является backup каталога:

```text
/opt/ZverTBot
```

---

# 5. Статические данные и GeoIP

Необходимые статические файлы проекта включаются в deploy-архив, например:

```text
data/asn_types.json
data/ru_geo.conf
data/storage.py
data/traffic.py
```

Runtime-содержимое `data/` не переносится.

Каталог:

```text
data/geoip/
```

в deploy-архив не включается.

GeoIP-базы устанавливаются отдельно на целевом VPS.

Installer проверяет:

* доступность загрузки;
* корректность gzip-архива;
* валидность MMDB;
* возможность чтения базы через `maxminddb`.

Сначала проверяется текущий месячный релиз DB-IP Lite, затем при необходимости предыдущий месяц.

Уже существующая непустая база повторно не скачивается.

---

# 6. Установка на новый VPS

Установка выполняется от имени `root`.

Installer поддерживает Ubuntu и перед началом установки проверяет операционную систему. На неподдерживаемой системе установка завершается с ошибкой.

В одном каталоге должны находиться:

```text
install.sh
ZverTBot-deploy-VERSION.tar.gz
```

Перед запуском:

```bash
chmod +x install.sh
```

## Базовая установка

```bash
./install.sh
```

## Установка с Xray

```bash
./install.sh -xray
```

## Установка с AmneziaWG

```bash
./install.sh -awg
```

## Установка с обоими компонентами

```bash
./install.sh -xray -awg
```

Ключи `-xray` и `-awg` являются **опциональными**.

Без соответствующего ключа installer не должен устанавливать соответствующий VPN-компонент.

> Установка VPN-компонента не означает, что его серверная конфигурация уже готова к созданию клиентов.

---

# 7. Что выполняет installer

Основной порядок установки:

1. проверка прав `root`;
2. проверка поддерживаемой ОС;
3. проверка сети и DNS;
4. распаковка deploy-архива;
5. запуск предварительных проверок;
6. ожидание освобождения `dpkg/apt lock` при необходимости;
7. установка системных пакетов;
8. установка и проверка `rclone`;
9. настройка автоматических обновлений безопасности;
10. запуск `system_tuning.sh`;
11. установка Xray при `-xray`;
12. установка AmneziaWG при `-awg`;
13. создание `.env`;
14. включение IPv4 forwarding;
15. создание runtime-каталогов и начального состояния;
16. создание Python virtual environment;
17. установка Python-зависимостей;
18. создание systemd units;
19. запуск и включение core-компонентов;
20. выполнение финальной verification;
21. вывод результата установки и пути к installer log.

Если финальная verification обнаруживает `FAIL`, installer завершается с ненулевым кодом возврата.

---

# 8. Конфигурация `.env`

Основная конфигурация устанавливается в:

```text
/opt/ZverTBot/.env
```

Шаблон:

```text
deploy/botinstaller/.env.example
```

Если `.env` отсутствует или пустой, installer создаёт его из шаблона.

При этом параметры целевого VPS автоматически подставляются там, где это предусмотрено.

Если `.env` уже существует и содержит данные, installer **не перезаписывает его**. В этом случае устанавливаются только необходимые права доступа.

Ожидаемые права:

```text
600
```

Таким образом, повторный запуск installer не должен уничтожать существующую конфигурацию.

---

# 9. Основные переменные `.env`

## Обязательные

```text
BOT_TOKEN
ADMIN_CHAT
```

`SERVER_IP` также является обязательным параметром проекта, однако installer пытается определить его автоматически.

Вручную задавать `SERVER_IP` требуется только для переопределения автоматически определённого значения.

## Дополнительные

```text
SERVER_FLAG
```

## Инфраструктура

```text
HA_TUNNEL_IP
HASS_FLAG
XRAY_CONF
AWG_CONF
```

Не все эти параметры обязательны для каждого VPS.

## LLM

```text
LLM_PROVIDER
LLM_API_KEY
LLM_API_URL
LLM_MODEL
LLM_MODELS
```

Используются соответствующим функционалом LLM.

## Внешние сервисы

```text
ABUSEIPDB_API_KEY
```

## Backup

```text
BACKUP_REMOTE
BACKUP_ROOT_DIR
```

Например:

```text
BACKUP_REMOTE=yandex
BACKUP_ROOT_DIR=VPS
```

В этом случае конфигурационные архивы сохраняются в:

```text
yandex:VPS/configs/
```

а паспортные данные:

```text
yandex:VPS/passport/
```

Тип удалённого хранилища определяется настройкой `rclone remote`.

## Логирование

```text
ZVERTBOT_LOG_LEVEL
```

Позволяет изменить уровень журналирования ZverTBot.

---

# 10. Xray

Xray устанавливается только при:

```bash
./install.sh -xray
```

или:

```bash
./install.sh -xray -awg
```

## Определение конфигурации

Рабочая конфигурация Xray относится к инфраструктуре целевого VPS.

Installer не предполагает фиксированный путь к конфигурации.

После установки анализируется:

```text
xray.service
```

и его `ExecStart`.

На основании этого installer пытается определить фактический путь к конфигурационному файлу и сохранить его в:

```text
XRAY_CONF
```

Если путь определить невозможно, `XRAY_CONF` может остаться пустым и installer выводит предупреждение.

## systemd-настройка Xray

Installer создаёт drop-in:

```text
/etc/systemd/system/xray.service.d/99-zvertbot-nofile.conf
```

с:

```text
LimitNOFILE=65535
```

После изменения выполняется:

```bash
systemctl daemon-reload
```

Если Xray уже работает, сервис перезапускается.

Installer дополнительно проверяет фактическое значение `LimitNOFILE`.

---

# 11. Example-конфигурация Xray

В deploy-пакет входит:

```text
deploy/botinstaller/examples/xray.config.example.json
```

Это **шаблон**, а не готовая рабочая конфигурация.

Он может использоваться как пример структуры конфигурации, если стандартный конфигурационный файл отсутствует.

Шаблон содержит значения:

```text
REPLACE_WITH_XRAY_REALITY_PRIVATE_KEY
REPLACE_WITH_REALITY_SHORT_ID
```

а также примерные параметры:

```text
serverNames
```

Перед использованием шаблонные значения необходимо заменить на реальные параметры сервера.

---

# 12. Проверка готовности Xray

Наличие конфигурационного файла не означает, что Xray готов к созданию VLESS-клиентов.

Перед созданием клиента ZverTBot проверяет конфигурацию.

Проверяются, в частности:

* наличие VLESS inbound;
* наличие `settings`;
* наличие списка `clients`;
* наличие `streamSettings`;
* `network = tcp`;
* `security = reality`;
* наличие `realitySettings`;
* наличие реального `privateKey`;
* отсутствие `REPLACE_WITH_*` private key;
* наличие `serverNames`;
* наличие `shortIds`.

Пустой список `clients` допустим для нового сервера.

Если конфигурация не готова, создание клиента блокируется, а администратору возвращается список обнаруженных проблем.

---

# 13. AmneziaWG

AmneziaWG устанавливается только при:

```bash
./install.sh -awg
```

или:

```bash
./install.sh -xray -awg
```

## Определение конфигурации

Рабочая конфигурация AmneziaWG относится к инфраструктуре целевого VPS и не переносится со старого сервера.

Installer пытается определить конфигурацию через systemd units:

```text
awg-quick@*.service
```

и соответствующие конфигурационные файлы.

Обнаруженный путь сохраняется в:

```text
AWG_CONF
```

Если путь определить невозможно, `AWG_CONF` может остаться пустым и installer выводит предупреждение.

---

# 14. Example-конфигурация AmneziaWG

В deploy-пакет входит:

```text
deploy/botinstaller/examples/awg0.conf.example
```

Если стандартный конфигурационный файл отсутствует, installer может установить шаблон:

```text
/etc/amnezia/amneziawg/awg0.conf
```

Шаблон содержит значения:

```text
REPLACE_WITH_AWG_SERVER_PRIVATE_KEY
REPLACE_WITH_CLIENT_PUBLIC_KEY
```

Это **не готовая рабочая конфигурация**.

Перед использованием необходимо заменить шаблонные значения на реальные ключи и параметры сервера.

---

# 15. Проверка готовности AmneziaWG

Перед созданием AWG-клиента проверяется серверная конфигурация.

Проверяются:

* наличие `[Interface]`;
* наличие `PrivateKey`;
* отсутствие `REPLACE_WITH_*` private key;
* наличие `Address`;
* наличие `ListenPort`.

Список существующих Peer может быть пустым.

Если конфигурация не готова, создание клиента блокируется и администратору возвращается список обнаруженных проблем.

---

# 16. Установка VPN ≠ готовность VPN

Команда:

```bash
./install.sh -xray -awg
```

означает установку программных компонентов.

Она **не означает полную настройку VPN**.

Для Xray должна быть подготовлена рабочая конфигурация, включающая необходимые:

```text
Reality private key
shortIds
serverNames
VLESS inbound
```

Для AmneziaWG:

```text
server private key
Address
ListenPort
параметры VPN-инфраструктуры
```

Только после прохождения readiness-проверки компонент считается готовым к созданию клиентов.

---

# 17. System tuning

Installer запускает:

```text
deploy/botinstaller/system_tuning.sh
```

Настраиваются:

### IPv4 preference

```text
/etc/gai.conf
```

Добавляется приоритет:

```text
precedence ::ffff:0:0/96  100
```

для предпочтения IPv4 при разрешении адресов.

### Conntrack

```text
/etc/sysctl.d/99-zvertbot.conf
```

с:

```text
net.netfilter.nf_conntrack_max=262144
```

Если `nf_conntrack` недоступен в ядре, installer выводит предупреждение и продолжает установку.

### journald

```text
/etc/systemd/journald.conf
```

Используются:

```text
SystemMaxUse=100M
RuntimeMaxUse=50M
MaxRetentionSec=7day
Compress=yes
```

После изменения выполняется перезапуск `systemd-journald`.

Другие системные сетевые параметры installer не изменяет.

---

# 18. Systemd

Systemd-конфигурация разделена на:

```text
deploy/botinstaller/systemd/
├── core/
└── optional/
```

## Core

Основные компоненты:

```text
zvertbot.service
zvertbot-vps-monitor.service
stats-http.service
vps-stats.service
vps-stats.timer
geoip-collect.timer
```

## Optional

Дополнительные компоненты:

```text
xray-traffic.service
xray-traffic.timer
zvertbot-backup.service
zvertbot-backup.timer
```

Таймеры запускают соответствующие сервисы:

```text
xray-traffic.timer
    └── xray-traffic.service

zvertbot-backup.timer
    └── zvertbot-backup.service
```

Optional-компоненты используются при наличии соответствующей конфигурации и функциональности.

---

# 19. Резервное копирование

Backup использует:

```text
BACKUP_REMOTE
BACKUP_ROOT_DIR
```

Конфигурационные архивы:

```text
${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/
```

Паспортные данные:

```text
${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/passport/
```

Перед загрузкой проверяется наличие настроенного `rclone remote`.

Если remote отсутствует или недоступен, backup может быть создан локально, однако удалённая копия не считается успешно сохранённой.

## Отображение прогресса

При ручном запуске через Telegram используется единое сообщение с обновлением состояния.

Например:

```text
📦 Создание архива, ожидайте...
```

Во время загрузки отображается реальный прогресс `rclone`:

```text
🔄 Загрузка бэкапа

☁️ Загрузка на backup remote
[██████████████░░░░░░] 74%

📦 58.3 / 78.2 MB
⚡ 12.3 MB/s
⏳ Осталось: 1 сек
```

Процент, размер, скорость и ETA берутся из фактического вывода `rclone`.

После завершения исходное сообщение заменяется итоговым результатом.

---

# 20. Автоматические обновления безопасности

Installer устанавливает и настраивает:

```text
unattended-upgrades
```

Используются:

```text
/etc/apt/apt.conf.d/20auto-upgrades
/etc/apt/apt.conf.d/52-zvertbot-unattended-upgrades
```

Разрешены security updates Ubuntu и соответствующие ESM security updates.

Из автоматических обновлений исключаются:

```text
xray-core
wireguard
wireguard-tools
iptables
netfilter-persistent
```

Автоматическая перезагрузка VPS отключена.

После настройки выполняется:

```bash
unattended-upgrade --dry-run
```

Ошибка dry-run считается ошибкой установки.

---

# 21. Проверка установки

После установки installer выполняет финальную verification.

Проверяются следующие группы:

### CORE SERVICES

```text
zvertbot.service
zvertbot-vps-monitor.service
stats-http.service
```

### TIMERS

```text
vps-stats.timer
geoip-collect.timer
```

Проверяются активность и enabled-состояние.

### SECURITY UPDATES

Проверяется наличие и конфигурация `unattended-upgrades`.

### SYSTEM TUNING

Проверяются:

* IPv4 preference;
* `nf_conntrack_max`;
* параметры journald.

### OPTIONAL COMPONENTS

Xray и AmneziaWG проверяются, если они были запрошены.

Каждая проверка получает статус:

```text
PASS
FAIL
SKIP
INFO
```

Если обнаружен хотя бы один `FAIL`, verification считается неуспешной и installer завершается с кодом:

```text
1
```

---

# 22. Дополнительная ручная проверка

После установки:

```bash
systemctl status zvertbot.service
systemctl status zvertbot-vps-monitor.service
systemctl status stats-http.service
systemctl status vps-stats.timer
systemctl status geoip-collect.timer
```

Проверка Python-окружения:

```bash
cd /opt/ZverTBot
.venv/bin/python --version
```

Проверка systemd:

```bash
systemctl --failed
```

Если используются VPN-компоненты, дополнительно необходимо проверить:

* `XRAY_CONF` / `AWG_CONF`;
* состояние соответствующих systemd-сервисов;
* готовность рабочих конфигураций;
* отсутствие `REPLACE_WITH_*`;
* возможность создания VPN-клиента.

---

# 23. Журнал установки

Installer сохраняет полный вывод в:

```text
/var/log/zvertbot-installer.log
```

Вывод одновременно отображается в терминале и записывается в журнал.

Файл создаётся с правами:

```text
600
```

При каждом запуске записываются дата, время и аргументы запуска.

Для диагностики:

```bash
less /var/log/zvertbot-installer.log
```

Последние строки:

```bash
tail -100 /var/log/zvertbot-installer.log
```

Поиск ошибок:

```bash
grep -nEi 'error|fail|warning|warn|✗' /var/log/zvertbot-installer.log
```

Installer log не входит в deploy-архив.

---

# 24. Перенос существующего VPS

Перенос ZverTBot выполняется не копированием всего:

```text
/opt/ZverTBot
```

а через новый deploy-архив.

Стандартный процесс:

```text
Рабочая копия
     │
     ▼
deploy/build.sh
     │
     ▼
ZverTBot-deploy-VERSION.tar.gz
     │
     ▼
Новый VPS
     │
     ▼
install.sh
     │
     ├── ZverTBot
     ├── Xray       (опционально)
     └── AmneziaWG  (опционально)
     │
     ▼
/opt/ZverTBot
```

На новом сервере заново создаются:

```text
.venv
.env
systemd
runtime state
```

---

# 25. Что не переносится

При штатном deploy-переносе не копируются:

* Git-история;
* `.venv`;
* `.env`;
* секреты;
* старые журналы;
* runtime-кэш;
* временные файлы;
* старые GeoIP-базы;
* резервные копии;
* локальное runtime-состояние;
* рабочая конфигурация Xray;
* рабочая конфигурация AmneziaWG;
* сетевые параметры старого VPS.

Runtime-состояние нового сервера создаётся заново.

К нему относятся, в частности:

* registry AWG-клиентов;
* bindings Telegram-пользователей;
* tickets;
* IP-токены;
* runtime-снимки Home Assistant;
* другие эксплуатационные данные.

Если такие данные необходимо сохранить, их следует отдельно восстановить из backup.

---

# 26. Принцип переносимости

Deploy-архив должен содержать только компоненты, необходимые для установки программной части ZverTBot.

Инфраструктурные параметры определяются на целевом VPS.

К ним относятся:

* IP-адрес;
* сетевые интерфейсы;
* пути конфигурации Xray;
* пути конфигурации AmneziaWG;
* systemd-окружение;
* секреты;
* GeoIP-базы;
* параметры Home Assistant;
* параметры внешнего мониторинга;
* параметры `rclone`;
* другие параметры конкретной инфраструктуры.

Главное требование:

> **Один deploy-архив должен быть пригоден для повторной установки ZverTBot на другой совместимый VPS без копирования runtime-состояния исходного сервера.**

---

# 27. Тестирование installer

`install.sh` изменяет системное окружение VPS:

* устанавливает пакеты;
* создаёт Python-окружение;
* создаёт systemd units;
* изменяет системные настройки;
* может устанавливать Xray и AmneziaWG.

Поэтому installer **не следует использовать для экспериментального тестирования на production VPS**.

Проверка установочного сценария должна выполняться на отдельной тестовой машине или временном VPS.

На production-сервере безопаснее выполнять:

* чтение исходного кода;
* статические проверки;
* unit-тесты;
* mock/temp-тесты;
* проверку содержимого deploy-архива;
* проверки, не изменяющие систему.

---

# 28. Рекомендуемый процесс выпуска deploy-архива

Из корня проекта:

```bash
cd ~/ZverTBot
./deploy/build.sh
```

Проверить:

```text
deploy/output/
```

Основной артефакт:

```text
ZverTBot-deploy-VERSION.tar.gz
```

На целевой системе используются:

```text
install.sh
ZverTBot-deploy-VERSION.tar.gz
```

После установки проверить:

```bash
systemctl status zvertbot.service
systemctl status zvertbot-vps-monitor.service
systemctl status stats-http.service

systemctl status vps-stats.timer
systemctl status geoip-collect.timer
```

При использовании VPN:

```text
XRAY_CONF / AWG_CONF
        │
        ▼
рабочая конфигурация
        │
        ▼
readiness-проверка
        │
        ▼
создание VPN-клиентов
```

---

# 29. Результат успешного развёртывания

После успешной установки целевой VPS должен содержать:

* ZverTBot в `/opt/ZverTBot`;
* рабочее Python-окружение;
* установленные системные зависимости;
* `.env`;
* необходимые systemd-компоненты;
* подготовленное runtime-окружение;
* актуальные GeoIP-базы;
* Xray, если был указан `-xray`;
* AmneziaWG, если был указан `-awg`;
* определённые `XRAY_CONF` / `AWG_CONF`, если соответствующие конфигурации обнаружены;
* настроенные конфигурации целевой VPN-инфраструктуры;
* необходимые эксплуатационные сервисы и таймеры.

Важно:

> **Установка программного компонента и готовность его конфигурации — разные этапы.**

ZverTBot блокирует создание VPN-клиентов, если соответствующая конфигурация не проходит readiness-проверку.

---

# 30. Итог

Deploy-механизм ZverTBot обеспечивает:

* повторяемую установку;
* перенос проекта между VPS;
* отделение программного кода от runtime-состояния;
* автоматическую подготовку системного окружения;
* опциональную установку Xray и AmneziaWG;
* автоматическую проверку результата установки;
* отдельное создание инфраструктурной конфигурации на целевом VPS.

**Deploy-архив — это артефакт установки программной части ZverTBot, а не копия рабочего сервера.**
