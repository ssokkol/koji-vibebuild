# Локальная установка Koji (Docker)

Руководство по поднятию локального Koji-сервера для разработки и тестирования VibeBuild.

## Содержание

- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Что происходит при setup](#что-происходит-при-setup)
- [Управление сервером](#управление-сервером)
- [Проверка работоспособности](#проверка-работоспособности)
- [Использование с VibeBuild](#использование-с-vibebuild)
- [Конфигурация](#конфигурация)
- [Архитектура](#архитектура)
- [Устранение неполадок](#устранение-неполадок)

---

## Требования

- **Docker** и **Docker Compose** (v2+)
- **koji CLI** — `sudo dnf install koji` (Fedora) или эквивалент
- **RAM:** минимум 4 ГБ (рекомендуется 8 ГБ)
- **Диск:** ~5 ГБ для контейнеров и данных
- **Сеть:** доступ к интернету (для скачивания образов и пакетов из Fedora-репозиториев)

---

## Быстрый старт

Одна команда для полной настройки:

```bash
cd dev/koji-server
make setup
```

После завершения:
- Веб-интерфейс Koji: https://localhost:8443/koji
- API: https://localhost:8443/kojihub
- Проверка: `koji --noauth list-tags`

---

## Что происходит при setup

Команда `make setup` выполняет следующие шаги:

### 1. Генерация SSL-сертификатов (`make certs`)

Скрипт `scripts/generate-certs.sh` создаёт в каталоге `ssl/`:
- **CA** — корневой сертификат (`koji_ca_cert.crt`)
- **Hub** — серверный сертификат для Apache (`kojihub.pem`)
- **Web** — сертификат для Koji Web (`kojiweb.pem`)
- **Admin** — клиентский сертификат администратора (`kojiadmin.pem`)
- **Builder** — сертификат для демона сборки (`kojibuilder.pem`)

Все сертификаты выпускаются на 10 лет с SAN для `localhost` и `koji-hub`.

### 2. Запуск БД и Hub

```bash
docker compose up -d --build db koji-hub
```

- **db** — PostgreSQL 16 (Alpine), хранит метаданные Koji
- **koji-hub** — Fedora 42 с Apache + mod_wsgi, Koji Hub и Koji Web

Hub-контейнер при первом запуске автоматически импортирует схему БД из `/usr/share/koji/schema.sql`.

### 3. Инициализация Koji (`make init`)

Скрипт `scripts/koji-init.sh`:
- Ждёт готовности Hub (до 60 секунд)
- Создаёт пользователя `kojiadmin` с правами администратора
- Добавляет хост-сборщик `kojibuilder` (архитектура x86_64)
- Создаёт теги: `f42`, `f42-build`
- Создаёт цель сборки: `f42` (build_tag=`f42-build`, dest_tag=`f42`)
- Настраивает группы сборки (`build`, `srpm-build`) с базовыми пакетами (gcc, make, rpm-build и др.)
- Подключает внешние репозитории Fedora 42 (releases + updates)
- Запускает регенерацию репозитория

### 4. Запуск Builder

```bash
docker compose up -d koji-builder
```

Контейнер `koji-builder` на Fedora 42 с mock, koji-builder и createrepo_c. Запускает демон `kojid`, который подключается к Hub и ждёт задач на сборку.

### 5. Настройка клиента (`make client`)

Скрипт `scripts/setup-client.sh` создаёт `~/.koji/config`:

```ini
[koji]
server = https://localhost:8443/kojihub
weburl = https://localhost:8443/koji
topurl = https://localhost:8443/kojifiles
cert = <путь>/ssl/kojiadmin.pem
serverca = <путь>/ssl/koji_ca_cert.crt
authtype = ssl
target = f42
build_tag = f42-build
```

Если `~/.koji/config` уже существует, создаётся резервная копия.

---

## Управление сервером

| Команда | Описание |
|---------|----------|
| `make setup` | Полная установка с нуля |
| `make stop` | Остановить все контейнеры |
| `make logs` | Показать логи всех контейнеров |
| `make clean` | Удалить контейнеры, тома и сертификаты |
| `make certs` | Перегенерировать SSL-сертификаты |
| `make init` | Повторная инициализация Koji |
| `make client` | Пересоздать конфигурацию клиента |

Все команды запускаются из каталога `dev/koji-server/`.

---

## Проверка работоспособности

### Проверка через CLI

```bash
# Список тегов (без аутентификации)
koji --noauth list-tags

# Список тегов (с аутентификацией)
koji list-tags

# Статус сборщика
koji list-hosts

# Информация о цели
koji list-targets
```

### Веб-интерфейс

Откройте в браузере: https://localhost:8443/koji

Браузер покажет предупреждение о самоподписанном сертификате — это нормально для локальной разработки.

### Тестовая сборка

```bash
# Скачать SRPM из Fedora и собрать
vibebuild python-requests
```

---

## Использование с VibeBuild

После `make setup` VibeBuild готов к работе без дополнительных флагов:

```bash
# Сборка пакета по имени (скачает SRPM из Fedora, разрешит зависимости, соберёт)
vibebuild python-requests

# Сборка локального SRPM
vibebuild my-package-1.0-1.fc42.src.rpm

# Анализ зависимостей (без сборки)
vibebuild --analyze-only my-package.src.rpm

# Показать план сборки (без реального запуска)
vibebuild --dry-run python-requests

# Скачать SRPM без сборки
vibebuild --download-only python-requests
```

Target (`f42`) и все параметры подключения берутся из `~/.koji/config`, созданного при `make client`.

---

## Конфигурация

### Переменные окружения (.env)

Файл `dev/koji-server/.env` содержит настройки:

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `POSTGRES_USER` | `koji` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `kojisecret` | Пароль PostgreSQL |
| `POSTGRES_DB` | `koji` | Имя базы данных |
| `KOJI_FQDN` | `localhost` | Доменное имя сервера |
| `KOJI_HTTPS_PORT` | `8443` | HTTPS-порт Hub |
| `KOJI_TAG` | `f42` | Основной тег |
| `KOJI_BUILD_TAG` | `f42-build` | Тег сборки |
| `KOJI_TARGET` | `f42` | Цель сборки |

### Изменение порта

Отредактируйте `KOJI_HTTPS_PORT` в `.env` и пересоздайте окружение:

```bash
# В .env:
KOJI_HTTPS_PORT=9443

# Пересоздать
make clean
make setup
```

---

## Архитектура

```
┌──────────────────────────────────────────────────┐
│                  Docker Network (koji-net)        │
│                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐ │
│  │    db     │  │   koji-hub   │  │koji-builder│ │
│  │PostgreSQL │  │ Apache+WSGI  │  │   kojid    │ │
│  │  :5432    │  │   :443       │  │   mock     │ │
│  └──────────┘  └──────┬───────┘  └────────────┘ │
│                        │                          │
└────────────────────────┼──────────────────────────┘
                         │
                    :8443 (HTTPS)
                         │
                    ┌────┴─────┐
                    │  Клиент  │
                    │ koji CLI │
                    │VibeBuild │
                    └──────────┘
```

### Контейнеры

| Контейнер | Образ | Описание |
|-----------|-------|----------|
| `db` | `postgres:16-alpine` | База данных Koji |
| `koji-hub` | Fedora 42 (собирается) | Koji Hub + Web + Apache |
| `koji-builder` | Fedora 42 (собирается) | Koji Builder (kojid + mock) |

### Тома

| Том | Назначение |
|-----|-----------|
| `koji-db-data` | Данные PostgreSQL |
| `koji-data` | Пакеты и репозитории (`/mnt/koji`) |

---

## Устранение неполадок

### Hub не запускается

```bash
# Проверить логи
make logs

# Проверить статус контейнеров
docker compose ps

# Проверить, свободен ли порт
ss -tlnp | grep 8443
```

### Builder в статусе offline

```bash
# Проверить логи builder
docker compose logs koji-builder

# Проверить, видит ли builder hub
docker compose exec koji-builder curl -sk https://koji-hub/kojihub

# Перезапустить builder
docker compose restart koji-builder
```

### Ошибка сертификатов (SSL)

```bash
# Перегенерировать сертификаты и пересоздать всё
make clean
make setup
```

### koji list-tags не работает

```bash
# Попробовать без аутентификации
koji --noauth --server=https://localhost:8443/kojihub list-tags

# Проверить конфигурацию клиента
cat ~/.koji/config

# Проверить доступность Hub
curl -sk https://localhost:8443/kojihub
```

### Сборка зависает или не запускается

```bash
# Проверить статус builder
koji list-hosts

# Проверить, есть ли репозиторий
koji list-tags --build

# Принудительная регенерация репозитория
koji regen-repo f42-build
```

### Полный сброс

```bash
cd dev/koji-server
make clean    # Удаляет всё: контейнеры, тома, сертификаты
make setup    # Поднимает заново с нуля
```
