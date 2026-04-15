# AmneziaWG Telegram Bot

Telegram-бот на Python для управления клиентами AmneziaWG прямо внутри существующего контейнера, без отдельного API-сервиса и без отдельного контейнера.

## Возможности

- `New conf` — создать новый клиентский конфиг и выдать `.conf` или `.vpn`
- `List confs` — показать клиентов из `clientsTable`
- `Revoke conf` — удалить клиента из `wg0.conf` и `clientsTable`, затем выполнить `wg syncconf`
- `Rename conf` — переименовать клиента только в `clientsTable`
- доступ только для Telegram ID из `SUPERUSER_TG_IDS`

## Структура проекта

```text
app/
  bot.py
  config.py
  handlers/
    __init__.py
    menu.py
  services/
    __init__.py
    auth.py
    clients_table.py
    config_builder.py
    wg_manager.py
  utils/
    __init__.py
    files.py
    process.py
    time.py
```

## Зависимости Python

Установить внутри контейнера:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Если в контейнере уже есть Python-окружение, достаточно:

```bash
pip install -r requirements.txt
```

## Системные зависимости

В контейнере должны быть доступны:

- `python3.11+`
- `wg`
- `wg-quick`
- `zlib` для Python стандартной библиотеки

Бот использует:

- `wg genkey`
- `wg pubkey`
- `wg syncconf wg0 <(wg-quick strip /opt/amnezia/awg/wg0.conf)`

Поэтому запускать его нужно в том же контейнере, где уже работает AmneziaWG и доступны файлы:

- `WG0_PATH`
- `CLIENTS_TABLE_PATH`
- `SERVER_PUBLIC_KEY_PATH`
- `SERVER_PSK_PATH`

## Настройка

1. Скопировать пример окружения:

```bash
cp .env.example .env
```

2. Заполнить `.env`.

Обязательные переменные:

```env
BOT_TOKEN=
SUPERUSER_TG_IDS=123,456
WG0_PATH=/opt/amnezia/awg/wg0.conf
CLIENTS_TABLE_PATH=/opt/amnezia/awg/clientsTable
SERVER_PUBLIC_KEY_PATH=/opt/amnezia/awg/wireguard_server_public_key.key
SERVER_PSK_PATH=/opt/amnezia/awg/wireguard_psk.key
PRIMARY_DNS=1.1.1.1
SECONDARY_DNS=1.0.0.1
SERVER_HOST=205.196.81.3
SERVER_PORT=49283
TRANSPORT_PROTO=udp
DEFAULT_MTU=1376
```

## Запуск

Из корня проекта:

```bash
source .venv/bin/activate
python -m app.bot
```

Если виртуальное окружение не используется:

```bash
python3 -m app.bot
```

## Как это работает

- `wg0.conf` и `clientsTable` читаются перед каждой операцией
- запись идет через временный файл и `atomic replace`
- используется файловый lock, чтобы параллельные действия не ломали состояние
- если `wg0.conf` или `clientsTable` повреждены, бот прекращает операцию и сообщает об ошибке

## Замечания по данным

- `clientId` хранится как публичный ключ клиента
- при `Rename conf` меняется только `clientsTable`
- при `Revoke conf` удаляется peer из `wg0.conf`, удаляется запись из `clientsTable`, затем вызывается `wg syncconf`
- логика выбора IP не заполняет дырки в середине списка и всегда берет следующий хвостовой адрес

