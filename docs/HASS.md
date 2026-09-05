# ZverTBot — интеграция с Home Assistant

Документ описывает интеграцию ZverTBot с Home Assistant: источники данных, JSON-файлы, сбор статистики, HTTP-доступ, sensors и dashboards.

Пример готового дашборда мониторинга VPS:

![Home Assistant Dashboard](images/dashboard.png)

## 1. Архитектура

Основная схема работы:

    ZverTBot
        |
        +-- VPS statistics
        |       |
        |       +-- hass/stats/stats.json
        |
        +-- Traffic
        |       |
        |       +-- hass/traffic/usage.json
        |       +-- hass/traffic/archive.json
        |
        +-- GeoIP
        |       |
        |       +-- hass/geo/geoip.json
        |
        +-- Backup
                |
                +-- hass/backup/rclone_backup_status.json

Далее данные используются Home Assistant:

    JSON
      |
      v
    HTTP / другой транспорт
      |
      v
    Home Assistant
      |
      +-- Sensors
      +-- Template sensors
      +-- Binary sensors
      +-- Dashboards

ZverTBot отвечает за сбор и подготовку данных.

Home Assistant отвечает за отображение, автоматизацию и dashboards.

## 2. Источники данных

Основные JSON-файлы находятся в каталоге `hass/`.

| Источник | Файл | Назначение |
|---|---|---|
| VPS statistics | `hass/stats/stats.json` | состояние VPS, сервисов и VPN |
| Traffic | `hass/traffic/usage.json` | статистика клиентов и трафика |
| Traffic archive | `hass/traffic/archive.json` | архив статистики трафика |
| GeoIP | `hass/geo/geoip.json` | IP, страна, город, ISP и координаты |
| Backup | `hass/backup/rclone_backup_status.json` | состояние резервного копирования |

## 3. Сбор данных

### VPS statistics

Сбор выполняет:

    hass/stats/vps_stats.py

Результат записывается в:

    hass/stats/stats.json

В текущей структуре верхнего уровня присутствуют:

    cpu
    mem
    disk
    vpn_total_gb
    server_ip
    peers
    xray_clients
    connections
    fail2ban
    rclone
    services
    check_timestamp
    vps_stats_last_check

### Traffic

Сбор Xray-трафика выполняет:

    hass/traffic/xray-traffic-collect.py

Основной файл текущего состояния:

    hass/traffic/usage.json

Верхний уровень:

    updated
    clients

`clients` содержит данные отдельных клиентов.

Архив:

    hass/traffic/archive.json

### GeoIP

Сбор GeoIP выполняет:

    hass/geo/geoip-collect.py

Результат:

    hass/geo/geoip.json

Верхний уровень представляет собой объект, где ключом является имя клиента.

Для клиента используются поля:

    ip
    pubkey
    protocol
    country
    city
    isp
    type
    emoji
    asn
    lat
    lon
    last_update
    mobile
    accuracy
    location_source

Поле `pubkey` присутствует только у соответствующих клиентов.

### Backup

Статус резервного копирования хранится в:

    hass/backup/rclone_backup_status.json

Текущая структура:

    last_backup
    status
    size_mb
    next_run
    file_name

## 4. stats.json

`stats.json` является основным агрегированным источником информации о VPS.

При обращении к `stats-http` результат дополняется данными из `usage.json`,
`geoip.json` и AWG registry. Поэтому JSON, который получает Home Assistant
через HTTP, может содержать поля, формируемые самим `stats-http.py`.

### CPU

Поле:

    cpu

содержит текущую загрузку CPU.

### Memory

Поле:

    mem

содержит процент использования оперативной памяти.

### Disk

Поле `disk` содержит:

    used_gb
    total_gb
    free_gb
    percent

Эти значения подходят для отображения:

- занятого пространства;
- свободного пространства;
- общего объёма;
- процента использования диска.

### VPN

Поле:

    vpn_total_gb

содержит общий объём VPN-трафика.

### Server IP

Поле:

    server_ip

содержит IP-адрес сервера.

### Peers

Поле:

    peers

содержит список VPN peers.

Структура элемента `peers` документирована в подразделе «Структура AWG peers».

### Xray clients

Поле:

    xray_clients

содержит список клиентов Xray.

При формировании HTTP-ответа `stats-http.py` создаёт этот список на основе
`usage.json` для клиентов с `proto == "vless"` и рассчитывает `online`
по условию `_delta > 100`.

### Connections

Поле:

    connections

содержит текущие соединения.

Фактическая структура элементов документируется отдельно.

### Fail2ban

Поле `fail2ban` содержит:

    total_banned
    currently_banned

Это позволяет отображать состояние блокировок Fail2ban в Home Assistant.

### Services

Поле `services` содержит состояния сервисов.

В текущем `stats.json` присутствуют:

    xray
    stats-http
    zvertbot
    fail2ban
    awg-quick@awg0

Эти данные можно использовать для отображения состояния сервисов и создания binary sensors.

### Timestamps

В `stats.json` присутствуют два времени:

    check_timestamp
    vps_stats_last_check

Оба поля содержат время, связанное с последним сбором статистики.
Точный формат и момент формирования каждого поля определяются кодом
`vps_stats.py`.

### Структура AWG peers

Каждый элемент массива `peers` содержит:

    name
    ip
    endpoint
    last_ip
    rx
    tx
    hs
    total_bytes
    online
    last_seen
    geoip

Назначение полей:

| Поле | Тип | Назначение |
|---|---|---|
| `name` | string | имя клиента |
| `ip` | string | адрес клиента в VPN |
| `endpoint` | string | endpoint клиента |
| `last_ip` | string | последний внешний IP |
| `rx` | string | полученный трафик |
| `tx` | string | отправленный трафик |
| `hs` | string | информация о handshake |
| `total_bytes` | number | общий объём трафика в байтах |
| `online` | boolean | текущий online/offline статус |
| `last_seen` | string | время последней активности |
| `geoip` | object | GeoIP-информация клиента |

Поле `total_bytes` является числовым значением и может использоваться для расчётов в Home Assistant.

Поля `rx` и `tx` уже содержат форматированное представление трафика и подходят прежде всего для отображения.

В `stats-http.py` для AWG используется `usage.json`, если там есть
ненулевые `uplink`/`downlink`. Если оба значения равны нулю, а
`total_bytes` больше нуля, HTTP-слой использует приблизительный fallback:
70% `downlink` и 30% `uplink`. Это не является точным разделением
реального AWG-трафика.

`online` является основным полем для определения текущего состояния AWG-клиента.

`geoip` содержит дополнительную информацию о местоположении клиента.

### Структура Xray clients

Каждый элемент массива `xray_clients` содержит:

    name
    ip
    last_ip
    endpoint
    rx
    tx
    total
    online
    hs
    last_seen
    geoip

Назначение полей:

| Поле | Тип | Назначение |
|---|---|---|
| `name` | string | имя клиента |
| `ip` | string | адрес клиента |
| `last_ip` | string | последний внешний IP |
| `endpoint` | string | endpoint клиента |
| `rx` | string | полученный трафик |
| `tx` | string | отправленный трафик |
| `total` | string | общий объём трафика |
| `online` | boolean | текущий online/offline статус |
| `hs` | string | информация о handshake |
| `last_seen` | string | время последней активности |
| `geoip` | object | GeoIP-информация клиента |

В отличие от AWG peers, поле общего трафика здесь называется `total`.

### Структура usage.json → clients

Каждый клиент в `usage.json` содержит:

    uplink
    downlink
    total
    last_ip
    _snap_up
    _snap_down
    _delta
    proto
    last_seen

Назначение полей:

| Поле | Тип | Назначение |
|---|---|---|
| `uplink` | integer | накопленный исходящий трафик |
| `downlink` | integer | накопленный входящий трафик |
| `total` | integer | общий накопленный трафик |
| `last_ip` | string | последний IP клиента |
| `_snap_up` | integer | внутренний snapshot исходящего трафика |
| `_snap_down` | integer | внутренний snapshot входящего трафика |
| `_delta` | integer | рассчитанная дельта трафика |
| `proto` | string | протокол клиента |
| `last_seen` | string | время последней активности |

Поля с префиксом `_` являются служебными и не предназначены как основной пользовательский интерфейс.

Для Home Assistant основными полями этого источника являются:

    uplink
    downlink
    total
    last_ip
    proto
    last_seen

`usage.json` используется для накопительной статистики клиентов и
для расчёта текущей активности Xray-клиентов через поле `_delta`.

### Связь источников

Информация о клиентах распределена между несколькими JSON-источниками.

`stats.json` содержит агрегированное текущее состояние:

    peers
    xray_clients

`usage.json` содержит накопительную статистику трафика:

    clients

`geoip.json` содержит расширенную GeoIP-информацию.

Поэтому Home Assistant не должен считать эти JSON-файлы полностью взаимозаменяемыми.

Для конкретного клиента может потребоваться объединение данных из нескольких источников:

    имя клиента
        |
        +-- stats.json
        |     +-- online
        |     +-- rx
        |     +-- tx
        |     +-- last_seen
        |
        +-- usage.json
        |     +-- uplink
        |     +-- downlink
        |     +-- total
        |
        +-- geoip.json
              +-- country
              +-- city
              +-- isp
              +-- asn
              +-- lat
              +-- lon

Конкретный способ объединения будет определён после анализа HTTP-интерфейса и существующей логики `stats-http.py`.

## 5. Backup status

Файл:

    hass/backup/rclone_backup_status.json

содержит:

    last_backup
    status
    size_mb
    next_run
    file_name

Пример назначения:

- `status` — состояние последнего backup;
- `last_backup` — время последнего backup;
- `size_mb` — размер архива;
- `next_run` — время следующего backup;
- `file_name` — имя созданного архива.

## 6. HTTP-интерфейс

Для предоставления статистики используется:

    hass/stats/stats-http.py

Сервис:

    stats-http.service

Локальная проверка выполняется через:

    http://127.0.0.1:8080/stats.json

Доступен единственный endpoint:

    /stats.json

Другие HTTP-пути возвращают `404`.

HTTP-сервер слушает:

    127.0.0.1:8080

Ответ `/stats.json` формируется из базового `stats.json` и может дополняться
данными из `usage.json`, `geoip.json` и AWG registry.

Форматирование трафика выполняется функцией `fmt_traffic()`:
- от 1 GiB — `GB` с двумя знаками после запятой;
- от 1 MiB до 1 GiB — `MB` без знаков после запятой;
- ниже 1 MiB — `KB` без знаков после запятой.

## 7. Systemd

Основные HASS-related units:

    geoip-collect.service
    geoip-collect.timer
    healthcheck.service
    stats-http.service
    vps-stats.service
    vps-stats.timer

Дополнительные:

    xray-traffic.service
    xray-traffic.timer
    zvertbot-backup.service
    zvertbot-backup.timer
    kuma-webhook.service

Фактические интервалы timers:

| Timer | Интервал |
|---|---:|
| `vps-stats.timer` | каждые 3 минуты |
| `geoip-collect.timer` | каждые 5 минут |
| `xray-traffic.timer` | каждые 5 минут |
| `zvertbot-backup.timer` | каждые 8 часов |

Все перечисленные timers используют `Persistent=true`.
Для backup дополнительно задан `AccuracySec=1min`.

`healthcheck.service` является сервисом проверки состояния и не имеет
отдельного timer в каталоге systemd проекта.

## 8. Принцип создания Home Assistant entities

При создании entities необходимо разделять:

### Состояние

Например:

    online
    service status
    backup status

### Числовые показатели

Например:

    cpu
    mem
    disk.percent
    vpn_total_gb
    total_bytes
    uplink
    downlink

### Текстовые атрибуты

Например:

    server_ip
    last_ip
    country
    city
    isp
    protocol

Такое разделение позволяет использовать числовые значения в графиках и gauges, boolean-состояния в binary sensors, а текстовые значения — в attributes и информационных карточках.


## 9. SSH-туннель HASS → VPS

Home Assistant получает статистику VPS через SSH-туннель.

На VPS сервис `stats-http` слушает только локальный адрес:

    127.0.0.1:8080

Он отдаёт:

    http://127.0.0.1:8080/stats.json

Порт `8080` VPS не требуется открывать во внешний интернет. Home Assistant
создаёт SSH Local Forward:

    HASS 127.0.0.1:8080
          │
          │ SSH -L
          ▼
    VPS 127.0.0.1:8080
          │
          └── stats-http → stats.json

После создания туннеля Home Assistant обращается к:

    http://127.0.0.1:8080/stats.json

### 9.1. Что необходимо на стороне HASS

Для работы туннеля необходимы:

- SSH-клиент;
- приватный SSH-ключ;
- доступ к VPS по этому ключу;
- `/config/secrets.yaml`;
- `/config/tunnel-vps-host.sh`;
- `/config/tunnel-vpstats.sh`;
- автозапуск watchdog-туннеля.

Приватный ключ используется из:

    /root/.ssh/vps_key

Сам ключ не хранится в `secrets.yaml` и не должен попадать в Git.

### 9.2. Доступ к VPS по SSH-ключу

На HASS используется:

    /root/.ssh/vps_key

На VPS соответствующий публичный ключ должен находиться в:

    /root/.ssh/authorized_keys

Сначала необходимо убедиться, что обычное SSH-подключение работает:

    ssh -i /root/.ssh/vps_key root@IP_VPS

Только после успешной проверки обычного SSH имеет смысл запускать
автоматический туннель.

В туннеле используется:

    -o BatchMode=yes

Поэтому интерактивный ввод пароля не предусмотрен.

### 9.3. IP VPS в secrets.yaml

IP-адрес VPS хранится на стороне Home Assistant в:

    /config/secrets.yaml

Используется ключ:

    tunnel_vps_host

Пример:

    tunnel_vps_host: "IP_VPS"

Реальный IP VPS в документацию и Git не добавляется.

### 9.4. tunnel-vps-host.sh

Файл:

    /config/tunnel-vps-host.sh

Скрипт читает `tunnel_vps_host` из `secrets.yaml` и выводит найденный
адрес в stdout.

Рабочая версия:

    #!/bin/bash

    SECRETS="/config/secrets.yaml"

    TUNNEL_VPS_HOST="$(
        sed -n 's/^tunnel_vps_host:[[:space:]]*//p' "$SECRETS" |
        head -n 1 |
        sed 's/^["'\'']\(.*\)["'\'']$/\1/'
    )"

    if [ -z "$TUNNEL_VPS_HOST" ]; then
        echo "ERROR: tunnel_vps_host не найден в $SECRETS" >&2
        exit 1
    fi

    printf '%s\n' "$TUNNEL_VPS_HOST"

Проверка:

    /config/tunnel-vps-host.sh

Ожидаемый результат:

    IP_VPS

Если параметр отсутствует, скрипт завершается с ошибкой.

### 9.5. tunnel-vpstats.sh

Основной watchdog находится в:

    /config/tunnel-vpstats.sh

Он постоянно проверяет доступность:

    http://127.0.0.1:8080/stats.json

Если статистика доступна, новый туннель не создаётся.

Если endpoint недоступен, скрипт:

1. записывает событие в лог;
2. завершает старый stats-туннель;
3. создаёт новый SSH Local Forward;
4. проверяет доступность `stats.json`;
5. записывает результат;
6. через 30 секунд повторяет проверку.

Рабочая версия:

    #!/bin/bash

    LOG="/config/logs/tunnel-vpstats.log"
    VPS_HOST="$(/config/tunnel-vps-host.sh)" || exit 1

    mkdir -p /config/logs

    while true; do
        if curl -fsS --max-time 5 \
            http://127.0.0.1:8080/stats.json \
            >/dev/null 2>&1
        then
            sleep 30
            continue
        fi

        echo "$(date '+%Y-%m-%d %H:%M:%S') | Туннель stats недоступен. Запуск туннеля..." >> "$LOG"

        pkill -f \
            "ssh.*-L 127\.0\.0\.1:8080:127\.0\.0\.1:8080.*root@$VPS_HOST" \
            2>/dev/null || true

        sleep 1

        if ssh \
            -i /root/.ssh/vps_key \
            -fN \
            -L 127.0.0.1:8080:127.0.0.1:8080 \
            -o BatchMode=yes \
            -o ConnectTimeout=5 \
            -o ExitOnForwardFailure=yes \
            -o ServerAliveInterval=30 \
            -o ServerAliveCountMax=3 \
            -o StrictHostKeyChecking=accept-new \
            "root@$VPS_HOST" \
            2>> "$LOG"
        then
            sleep 2

            if curl -fsS --max-time 5 \
                http://127.0.0.1:8080/stats.json \
                >/dev/null 2>&1
            then
                echo "$(date '+%Y-%m-%d %H:%M:%S') | ✅ Stats-туннель поднят, stats доступны." >> "$LOG"
            else
                echo "$(date '+%Y-%m-%d %H:%M:%S') | ❌ Туннель запущен, но stats недоступны." >> "$LOG"
            fi
        else
            echo "$(date '+%Y-%m-%d %H:%M:%S') | ❌ Ошибка запуска stats-туннеля." >> "$LOG"
        fi

        sleep 30
    done

### 9.6. SSH Local Forward

Ключевая часть команды:

    -L 127.0.0.1:8080:127.0.0.1:8080

создаёт соединение:

    HASS:8080 → SSH → VPS:8080

На VPS `stats-http` продолжает слушать только `127.0.0.1:8080`.

То есть внешний доступ к `stats-http` не требуется.

Используется:

    -fN

`-N` не запускает удалённую команду.

`-f` переводит SSH в фон после успешного подключения.

### 9.7. Параметры устойчивости туннеля

Используются следующие SSH options:

    -o BatchMode=yes

Запрещает интерактивные запросы.

    -o ConnectTimeout=5

Ограничивает время подключения.

    -o ExitOnForwardFailure=yes

SSH завершается, если Local Forward создать не удалось.

    -o ServerAliveInterval=30

Отправляет keepalive каждые 30 секунд.

    -o ServerAliveCountMax=3

После трёх неудачных keepalive SSH считает соединение потерянным.

    -o StrictHostKeyChecking=accept-new

Автоматически принимает новый host key, но не принимает молча
изменившийся ключ уже известного хоста.

### 9.8. Почему watchdog проверяет stats.json

Наличие SSH-процесса само по себе не означает, что статистика доступна.

Поэтому watchdog проверяет именно:

    curl -fsS --max-time 5 \
        http://127.0.0.1:8080/stats.json

Это позволяет обнаружить ситуацию, когда SSH-процесс существует,
но Local Forward или `stats-http` фактически не работает.

### 9.9. Автозапуск

В текущей рабочей конфигурации туннель запускается через
**Advanced SSH & Web Terminal**.

В конфигурации приложения используется:

    nohup /config/tunnel-vpstats.sh >/dev/null 2>&1 &

`nohup` позволяет watchdog продолжать работу после завершения
терминальной сессии.

`&` запускает его в фоне.

Рабочий лог записывается в:

    /config/logs/tunnel-vpstats.log

### 9.10. Проверка туннеля

Проверить получение IP VPS:

    /config/tunnel-vps-host.sh

Проверить SSH-доступ:

    ssh -i /root/.ssh/vps_key root@IP_VPS

Проверить локальный endpoint:

    curl -fsS http://127.0.0.1:8080/stats.json

Проверить Local Forward:

    ss -ltn | grep '127.0.0.1:8080'

Проверить SSH-процесс:

    pgrep -af 'ssh.*127.0.0.1:8080:127.0.0.1:8080'

Проверить лог:

    tail -f /config/logs/tunnel-vpstats.log

### 9.11. Проверка на VPS

На VPS отдельно проверяется `stats-http`:

    systemctl status stats-http

И локальный endpoint:

    curl http://127.0.0.1:8080/stats.json

Если `stats-http` на VPS не работает, исправление SSH-туннеля само
по себе статистику не восстановит.

### 9.12. Связь с Home Assistant REST

После поднятия туннеля Home Assistant использует:

    http://127.0.0.1:8080/stats.json

Поэтому `rest:` sensor не должен знать реальный IP VPS.

Полная цепочка:

    Home Assistant REST sensor
            ↓
    HASS 127.0.0.1:8080
            ↓
    SSH Local Forward
            ↓
    VPS 127.0.0.1:8080
            ↓
    stats-http
            ↓
    stats.json

Это позволяет держать `stats-http` доступным только локально на VPS.

### 9.13. Диагностика

Если `sensor.vps_all_stats` недоступен, проверка выполняется снизу вверх:

    1. /config/tunnel-vps-host.sh
    2. SSH по ключу
    3. VPS stats-http
    4. Local Forward
    5. curl http://127.0.0.1:8080/stats.json
    6. лог /config/logs/tunnel-vpstats.log
    7. REST sensor в Home Assistant

Так проще определить, на каком именно уровне находится проблема.

## 10. Рабочая конфигурация Home Assistant

Ниже приведена фактически используемая конфигурация Home Assistant для
получения статистики VPS из ZverTBot.

Конфигурация рассчитана на локальный HTTP endpoint:

    http://127.0.0.1:8080/stats.json

Home Assistant опрашивает endpoint один раз в минуту (`scan_interval: 60`).

Конфигурация разделена на четыре части:

1. `rest` — получение данных VPS и создание основных sensors;
2. `template` — производные sensors и binary sensors;
3. `command_line` — проверка SSH-туннеля и локального `stats-http`;
4. атрибуты sensors — передача массивов клиентов и дополнительной информации
   из `stats.json`.

### 9.1. REST sensors

Основной REST sensor:

    VPS All Stats

Он получает количество peer из:

    value_json.peers | length

и сохраняет в attributes следующие структуры:

    peers
    awg_clients
    xray_clients
    connections
    fail2ban
    server_ip
    check_timestamp
    vps_stats_last_check

Это основной sensor для отображения подробной информации о VPS.

Отдельные REST sensors используются для:

| Sensor | Источник |
|---|---|
| `VPS CPU Load` | `cpu` |
| `VPS RAM Used` | `mem` |
| `VPS Disk Used` | `disk.used_gb` |
| `VPS Disk Total` | `disk.total_gb` |
| `VPS Disk Free` | `disk.free_gb` |
| `VPS Disk Percent` | `disk.percent` |
| `VPS VPN Traffic` | `vpn_total_gb` |
| `VPS Backup Status` | `rclone.status` |
| `VPS Backup Last` | `rclone.last_backup` |
| `VPS Backup Size` | `rclone.size_mb` |
| `VPS Backup Next` | `rclone.next_run` |
| `VPS Stats Last Check` | `vps_stats_last_check` |

### 9.2. VPN Traffic

`VPS VPN Traffic` переводит значение `vpn_total_gb` из гигабайт в
терабайты:

    {{ (value_json.vpn_total_gb | float(0) / 1024) | round(3) }}

Sensor использует:

    state_class: total_increasing

Поэтому он предназначен для накопительного отображения трафика.

### 9.3. Состояние systemd services

Для сервисов используется числовой state:

    1 = работает
    0 = установлен, но остановлен
    -1 = не установлен

В текущей конфигурации Home Assistant отображаются:

    xray
    awg-quick@awg0
    stats-http
    zvertbot
    fail2ban

Например:

    value_json.services.xray.status

Uptime сервиса сохраняется как attribute `uptime`.

Отдельные template sensors затем выводят uptime:

    VPS Xray Uptime
    VPS AmneziaWG Uptime
    VPS Stats-HTTP Uptime
    VPS ZverTBot Uptime
    VPS Fail2ban Uptime

### 9.4. Контроль свежести статистики

Основной timestamp:

    sensor.vps_stats_last_check

На его основе создаются:

    VPS Stats Minutes Since Check
    VPS Stats Check Age
    VPS Stats Last Check Time
    VPS Stats Last Check Full Time
    VPS Stats Status
    VPS Stats Fresh

Логика свежести:

    <= 5 минут — OK
    > 5 минут — Устарела

`VPS Stats Fresh` является binary sensor и использует тот же порог
в 300 секунд.

Это позволяет отдельно контролировать:

- наличие timestamp;
- возраст последнего обновления;
- состояние свежести;
- время последней проверки.

### 9.5. Binary sensors

Для systemd services создаются binary sensors:

    VPS Service Xray
    VPS Service AmneziaWG
    VPS Service Stats-HTTP
    VPS Service ZverTBot
    VPS Service Fail2ban

Они переходят в `on`, если соответствующий REST sensor имеет state `1`.

Дополнительно создаются:

    SSH Tunnel to VPS
    VPS Stats Fresh

`SSH Tunnel to VPS` проверяет состояние sensor:

    sensor.ssh_tunnel_status

`VPS Stats Fresh` непосредственно вычисляет возраст
`sensor.vps_stats_last_check`.

### 9.6. SSH tunnel

Для проверки локального SSH SOCKS-туннеля используется:

    command_line

Проверка выполняется командой:

    pgrep -f "ssh.*-D 1080"

Sensor:

    SSH Tunnel Status

обновляется каждые 60 секунд.

Для локального HTTP endpoint `stats-http` используется отдельная проверка:

    ss -ltn 2>/dev/null | grep -q "127\\.0\\.0\\.1:8080 "

Sensor:

    VPS Stats Tunnel Status

обновляется каждые 30 секунд.

Таким образом, Home Assistant может отдельно определить:

1. работает ли SSH-туннель;
2. слушается ли локальный порт `8080`;
3. актуальна ли сама статистика VPS.

### 9.7. Backup sensors

Backup-информация берётся непосредственно из:

    value_json.rclone

Используются:

    VPS Backup Status
    VPS Backup Last
    VPS Backup Size
    VPS Backup Next

Основные поля:

    status
    last_backup
    size_mb
    next_run
    file_name

`VPS Backup Last` использует `device_class: timestamp`.

Размер последнего backup отображается в MB.

### 9.8. Полный рабочий пример

Следующий пример соответствует текущей рабочей конфигурации Home Assistant
и структуре JSON, которую формирует ZverTBot.

    # =============================================================
    # VPS СТАТИСТИКА
    # =============================================================

    rest:
      - resource: "http://127.0.0.1:8080/stats.json"
        scan_interval: 60

        sensor:
          # SYSTEM
          - name: "VPS CPU Load"
            value_template: "{{ value_json.cpu | float(0) }}"
            unit_of_measurement: "%"
            state_class: measurement

          - name: "VPS RAM Used"
            value_template: "{{ value_json.mem | float(0) }}"
            unit_of_measurement: "%"
            state_class: measurement

          - name: "VPS Disk Used"
            value_template: "{{ value_json.disk.used_gb | float(0) }}"
            unit_of_measurement: "GB"
            state_class: measurement

          - name: "VPS Disk Total"
            value_template: "{{ value_json.disk.total_gb | float(0) }}"
            unit_of_measurement: "GB"
            state_class: measurement

          - name: "VPS Disk Free"
            value_template: "{{ value_json.disk.free_gb | float(0) }}"
            unit_of_measurement: "GB"
            state_class: measurement
            icon: mdi:harddisk

          - name: "VPS Disk Percent"
            value_template: "{{ value_json.disk.percent | float(0) }}"
            unit_of_measurement: "%"
            state_class: measurement
            icon: mdi:harddisk

          # VPN TRAFFIC
          - name: "VPS VPN Traffic"
            value_template: >
              {{ (value_json.vpn_total_gb | float(0) / 1024) | round(3) }}
            unit_of_measurement: "TB"
            state_class: total_increasing
            icon: mdi:ip-network

          # ALL STATS
          - name: "VPS All Stats"
            value_template: "{{ value_json.peers | length }}"
            json_attributes:
              - peers
              - awg_clients
              - xray_clients
              - connections
              - fail2ban
              - server_ip
              - check_timestamp
              - vps_stats_last_check

          # BACKUP
          - name: "VPS Backup Status"
            value_template: "{{ value_json.rclone.status }}"

          - name: "VPS Backup Last"
            value_template: "{{ value_json.rclone.last_backup }}"
            device_class: timestamp

          - name: "VPS Backup Size"
            value_template: "{{ value_json.rclone.size_mb | float(0) }}"
            unit_of_measurement: "MB"
            state_class: measurement

          - name: "VPS Backup Next"
            value_template: "{{ value_json.rclone.next_run }}"

          # SERVICES
          - name: "VPS Service Xray"
            value_template: "{{ value_json.services.xray.status | int(0) }}"
            json_attributes:
              - uptime

          - name: "VPS Service AmneziaWG"
            value_template: "{{ value_json.services['awg-quick@awg0'].status | int(0) }}"
            json_attributes:
              - uptime

          - name: "VPS Service Stats-HTTP"
            value_template: "{{ value_json.services['stats-http'].status | int(0) }}"
            json_attributes:
              - uptime

          - name: "VPS Service ZverTBot"
            value_template: "{{ value_json.services.zvertbot.status | int(0) }}"
            json_attributes:
              - uptime

          - name: "VPS Service Fail2ban"
            value_template: "{{ value_json.services.fail2ban.status | int(0) }}"
            json_attributes:
              - uptime

          # LAST CHECK
          - name: "VPS Stats Last Check"
            unique_id: vps_stats_last_check
            value_template: "{{ value_json.vps_stats_last_check | default('') }}"
            device_class: timestamp

    # TEMPLATE SENSORS
    template:
      - sensor:
          # SERVICE UPTIMES
          - name: "VPS Xray Uptime"
            unique_id: vps_xray_uptime
            state: "{{ state_attr('sensor.vps_service_xray', 'uptime') | default('Нет данных', true) }}"
            icon: mdi:clock-outline

          - name: "VPS AmneziaWG Uptime"
            unique_id: vps_amneziawg_uptime
            state: "{{ state_attr('sensor.vps_service_amneziawg', 'uptime') | default('Нет данных', true) }}"
            icon: mdi:clock-outline

          - name: "VPS Stats-HTTP Uptime"
            unique_id: vps_stats_http_uptime
            state: "{{ state_attr('sensor.vps_service_stats_http', 'uptime') | default('Нет данных', true) }}"
            icon: mdi:clock-outline

          - name: "VPS ZverTBot Uptime"
            unique_id: vps_zvertbot_uptime
            state: "{{ state_attr('sensor.vps_service_zvertbot', 'uptime') | default('Нет данных', true) }}"
            icon: mdi:clock-outline

          - name: "VPS Fail2ban Uptime"
            unique_id: vps_fail2ban_uptime
            state: "{{ state_attr('sensor.vps_service_fail2ban', 'uptime') | default('Нет данных', true) }}"
            icon: mdi:clock-outline

          # MINUTES SINCE CHECK
          - name: "VPS Stats Minutes Since Check"
            unique_id: vps_stats_minutes_since_check
            unit_of_measurement: "мин"
            state_class: measurement
            icon: mdi:clock-outline
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}

              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                unavailable
              {% else %}
                {% set age = (as_timestamp(now()) - as_timestamp(t)) / 60 %}
                {{ [age | round(0), 0] | max }}
              {% endif %}

          # HUMAN AGE
          - name: "VPS Stats Check Age"
            unique_id: vps_stats_check_age
            icon: mdi:clock-check-outline
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}

              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                Нет данных
              {% else %}
                {% set seconds = as_timestamp(now()) - as_timestamp(t) %}
                {% if seconds < 60 %}
                  только что
                {% elif seconds < 3600 %}
                  {{ (seconds / 60) | round(0) }} мин
                {% elif seconds < 86400 %}
                  {% set hours = (seconds / 3600) | int %}
                  {% set minutes = ((seconds % 3600) / 60) | round(0) | int %}
                  {% if minutes > 0 %}
                    {{ hours }} ч {{ minutes }} мин
                  {% else %}
                    {{ hours }} ч
                  {% endif %}
                {% else %}
                  {% set days = (seconds / 86400) | int %}
                  {{ days }} д
                {% endif %}
              {% endif %}

          # LAST CHECK HH:MM
          - name: "VPS Stats Last Check Time"
            unique_id: vps_stats_last_check_time
            icon: mdi:clock-outline
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}
              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                Нет данных
              {% else %}
                {{ as_timestamp(t) | timestamp_custom('%H:%M', true) }}
              {% endif %}

          # LAST CHECK HH:MM:SS
          - name: "VPS Stats Last Check Full Time"
            unique_id: vps_stats_last_check_full_time
            icon: mdi:clock-digital
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}
              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                Нет данных
              {% else %}
                {{ as_timestamp(t) | timestamp_custom('%H:%M:%S', true) }}
              {% endif %}

          # FRESHNESS STATUS
          - name: "VPS Stats Status"
            unique_id: vps_stats_status
            icon: mdi:database-clock-outline
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}
              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                Нет данных
              {% else %}
                {% set age = (as_timestamp(now()) - as_timestamp(t)) / 60 %}
                {% if age <= 5 %}
                  OK
                {% else %}
                  Устарела
                {% endif %}
              {% endif %}

      # BINARY SENSORS
      - binary_sensor:
          - name: "VPS Service Xray"
            unique_id: vps_service_xray
            state: "{{ states('sensor.vps_service_xray') == '1' }}"
            device_class: running

          - name: "VPS Service AmneziaWG"
            unique_id: vps_service_amneziawg
            state: "{{ states('sensor.vps_service_amneziawg') == '1' }}"
            device_class: running

          - name: "VPS Service Stats-HTTP"
            unique_id: vps_service_stats_http
            state: "{{ states('sensor.vps_service_stats_http') == '1' }}"
            device_class: running

          - name: "VPS Service ZverTBot"
            unique_id: vps_service_zvertbot
            state: "{{ states('sensor.vps_service_zvertbot') == '1' }}"
            device_class: running

          - name: "VPS Service Fail2ban"
            unique_id: vps_service_fail2ban
            state: "{{ states('sensor.vps_service_fail2ban') == '1' }}"
            device_class: running

          - name: "SSH Tunnel to VPS"
            unique_id: ssh_tunnel_to_vps
            state: "{{ is_state('sensor.ssh_tunnel_status', 'on') }}"
            device_class: connectivity

          - name: "VPS Stats Fresh"
            unique_id: vps_stats_fresh
            state: >
              {% set t = states('sensor.vps_stats_last_check') %}
              {% if t in ['unknown', 'unavailable', 'none', ''] %}
                false
              {% else %}
                {{ (as_timestamp(now()) - as_timestamp(t)) <= 300 }}
              {% endif %}
            device_class: connectivity

    # SSH TUNNEL
    command_line:
      - sensor:
          name: "SSH Tunnel Status"
          unique_id: ssh_tunnel_status
          command: 'pgrep -f "ssh.*-D 1080" > /dev/null && echo "on" || echo "off"'
          scan_interval: 60

      - sensor:
          name: "VPS Stats Tunnel Status"
          unique_id: vps_stats_tunnel_status
          command: 'ss -ltn 2>/dev/null | grep -q "127\\.0\\.0\\.1:8080 " && echo "on" || echo "off"'
          scan_interval: 30

### 9.9. Результат

В результате Home Assistant получает:

- системные показатели VPS;
- дисковое пространство;
- суммарный VPN-трафик;
- AWG clients;
- Xray clients;
- подключения;
- Fail2ban;
- состояние systemd services;
- uptime сервисов;
- состояние backup;
- время последней проверки;
- возраст статистики;
- состояние свежести;
- состояние SSH-туннеля;
- доступность локального `stats-http`.

Конфигурация выше является документацией рабочего варианта интеграции.
При изменении структуры `stats.json` соответствующие YAML-шаблоны должны
проверяться и обновляться одновременно с кодом ZverTBot.


## 11. VPS Dashboard

Для VPS используется отдельный dashboard с path:

    /vps

Заголовок:

    VPS

Иконка:

    mdi:vpn

Dashboard построен на `sections` с максимальным количеством четырёх колонок.

### 10.1. Общая структура

Dashboard содержит три основные информационные области:

1. состояние самого VPS;
2. состояние AWG-клиентов;
3. состояние VLESS/Xray-клиентов.

Дополнительно в первой области отображаются:

- backup;
- CPU;
- RAM;
- свободное место на диске;
- Fail2Ban;
- активные туннели;
- systemd services;
- SSH-туннель;
- время последнего опроса;
- VPN-трафик.

### 10.2. Заголовок VPS

Название VPS формируется динамически из attribute:

    sensor.vps_all_stats
    server_ip

Если IP отсутствует, dashboard показывает:

    IP неизвестен

Таким образом, заголовок не требует отдельного sensor только для IP-адреса.

### 10.3. Блок backup

Информация о backup берётся из:

    sensor.vps_backup_status
    sensor.vps_backup_last
    sensor.vps_backup_size
    sensor.vps_backup_next

В markdown-карточке отображаются:

- статус;
- время последнего backup;
- размер архива;
- время следующего backup.

Статус преобразуется в человекочитаемый вид:

    success → ✅ Успешно
    fail    → ❌ Ошибка
    другое  → ❓ Неизвестно

Временные значения форматируются как:

    DD.MM HH:MM

Если timestamp отсутствует, отображается:

    Никогда

или:

    Не задан

### 10.4. CPU, RAM и диск

Для основных ресурсов используются gauge cards.

CPU:

    sensor.vps_cpu_load

Диапазон:

    0–5

Пороговые значения:

    0     → green
    2     → yellow
    3     → red

RAM:

    sensor.vps_ram_used

Диапазон:

    0–100 %

Пороговые значения:

    0     → green
    70    → yellow
    90    → red

Для RAM включён `needle`.

Свободное место:

    sensor.vps_disk_free

Диапазон:

    0–10 GB

Пороговые значения:

    5     → green
    2     → yellow
    0     → red

Для свободного места также используется `needle`.

Эти gauges предназначены прежде всего для быстрого визуального контроля
ресурсов VPS.

### 10.5. Fail2Ban

Количество заблокированных адресов берётся из attribute:

    sensor.vps_all_stats
    fail2ban

Используются поля:

    currently_banned
    total_banned

Dashboard отображает:

    🚫 Заблокировано сейчас
    🚫 Всего заблокировано

Если attribute отсутствует, используется пустой объект и значение `0`.

### 10.6. Активные туннели

Подключения берутся из:

    sensor.vps_all_stats
    connections

Из массива выбираются только подключения с именами:

    HA-Tunnel
    Xray

Для каждого подключения отображаются:

| Поле | Источник |
|---|---|
| Тип | `name` |
| IP | `ip` |
| Порт | `port` |
| Rx | `rx` |
| Tx | `tx` |
| Статус | `hs` |

Названия отображаются следующим образом:

    HA-Tunnel → 🌐 HA Tunnel
    Xray     → 🚀 Xray

Если `port` отсутствует, используется `-`.

### 10.7. Состояние systemd services

В отдельной entities-карточке отображаются binary sensors:

    binary_sensor.vps_service_xray
    binary_sensor.vps_service_zvertbot
    binary_sensor.vps_service_amneziawg
    binary_sensor.vps_service_stats_http
    binary_sensor.vps_service_fail2ban

Для каждого сервиса показывается время последнего изменения
(`secondary_info: last-changed`).

В dashboard используются следующие названия:

    Xray
    ZverTBot
    AmneziaWG
    Stats HTTP
    Fail2ban

### 10.8. Подключение к VPS

Отдельный блок отображает состояние SSH-подключения.

Основной binary sensor:

    binary_sensor.ssh_tunnel_to_vps

Дополнительный sensor:

    sensor.ssh_tunnel_status

Первый показывает логическое состояние подключения, второй — фактическое
состояние command-line проверки.

Это позволяет отличать entity, используемую для dashboard, от исходного
проверочного sensor.

### 10.9. Последний опрос и VPN-трафик

В верхней entities-карточке отображаются:

    sensor.vps_stats_last_check
    sensor.vps_vpn_traffic

Для последнего опроса используется:

    secondary_info: last-changed

VPN-трафик выводится отдельным sensor и соответствует накопительному
значению, описанному в разделе REST sensors.

### 10.10. AWG clients

AWG-клиенты берутся из attributes:

    sensor.vps_all_stats
    peers

Дополнительная информация о сформированных AWG clients берётся из:

    sensor.vps_all_stats
    awg_clients

Количество online-клиентов рассчитывается непосредственно в markdown:

    peers | selectattr('online') | list | length

Для каждого peer dashboard показывает:

- имя клиента;
- внутренний IP;
- суммарный трафик;
- GeoIP;
- ISP;
- примерность GeoIP для мобильных адресов;
- online/offline;
- последний IP;
- время последней активности.

Для отображения трафика используется сформированный AWG client,
если он найден по IP. Если его нет, используется значение `peer.total`.

### 10.11. GeoIP для AWG clients

GeoIP берётся непосредственно из:

    peer.geoip

Используются:

    city
    isp
    emoji
    mobile
    ip

Для мобильного адреса перед городом отображается символ:

    ≈

и дополнительно:

    ⚠️ Примерное местоположение

IP для отображения выбирается в следующем порядке:

    peer.last_ip
    geoip.ip

То есть dashboard предпочитает фактически наблюдавшийся последний IP.

### 10.12. Статус AWG clients

Для каждого AWG peer отображается:

    🟢 Online

или:

    ⚫ Offline

Для offline-клиента дополнительно выводится `last_seen`.

Если `last_seen` отсутствует:

    🕐 Никогда

Таким образом, dashboard показывает не только текущее состояние клиента,
но и последнюю известную активность.

### 10.13. Xray / VLESS clients

VLESS-клиенты берутся из:

    sensor.vps_all_stats
    xray_clients

Количество online рассчитывается с учётом двух признаков:

    online == true

или:

    hs == active

Это позволяет учитывать активную Xray-сессию даже в случаях, когда
основной `online` ещё не установлен.

Для каждого клиента отображаются:

- имя;
- суммарный трафик;
- GeoIP;
- ISP;
- примерное мобильное местоположение;
- текущий/последний IP;
- online/offline;
- время последней активности.

### 10.14. GeoIP для Xray clients

Используется attribute:

    xray_clients[].geoip

Поля:

    city
    isp
    emoji
    mobile
    ip

Как и для AWG, при `mobile == true` dashboard показывает:

    ≈

и предупреждение:

    ⚠️ Примерное местоположение

IP выбирается из:

    last_ip

а при его отсутствии:

    geoip.ip

### 10.15. Три уровня состояния клиента

В dashboard фактически используются три источника информации о клиенте:

1. текущий `online`;
2. состояние handshake `hs`;
3. `last_seen`.

Для Xray `hs == active` также учитывается при определении Online.

Для offline-клиента `last_seen` позволяет определить, когда он последний
раз был замечен.

Это важно не смешивать с `VPS Stats Last Check`: первое относится к
конкретному VPN-клиенту, второе — ко всему набору статистики VPS.

### 10.16. Принцип dashboard

Dashboard не получает статистику напрямую от Xray или AWG.

Цепочка выглядит так:

    Xray / AWG
        ↓
    ZverTBot collectors
        ↓
    stats.json
        ↓
    stats-http
        ↓
    Home Assistant REST sensor
        ↓
    sensor.vps_all_stats
        ↓
    Markdown / Entities / Gauge cards

Поэтому dashboard является представлением уже подготовленной ZverTBot
статистики, а не самостоятельным сборщиком данных.

### 10.17. Что покрывает VPS Dashboard

Текущий рабочий dashboard покрывает:

| Область | Данные |
|---|---|
| VPS | IP, CPU, RAM, Disk |
| Traffic | VPN traffic |
| Backup | status, last, size, next |
| Security | Fail2Ban |
| Connections | HA Tunnel, Xray |
| Services | Xray, ZverTBot, AWG, Stats HTTP, Fail2ban |
| SSH | tunnel status |
| AWG | clients, traffic, GeoIP, status |
| Xray | VLESS clients, traffic, GeoIP, status |
| Freshness | last statistics check |

Следующие dashboard-разделы можно документировать отдельно, не смешивая
их с VPS overview:

- VPN / Traffic;
- Services / Health;
- Backup;
- GeoIP;
- диагностика.
