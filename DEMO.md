# Демонстрация VibeBuild

## Что такое VibeBuild

**VibeBuild** — расширение системы сборки [Koji](https://koji.fedoraproject.org/).
Одна команда `vibebuild <пакет>` запускает полный цикл: скачивание SRPM, анализ и разрешение зависимостей, сборку RPM.

В отличие от стандартного `koji build`, который собирает один пакет и падает при отсутствии зависимостей, VibeBuild:

- **Автоматически разрешает зависимости** — находит недостающие `BuildRequires`, строит DAG зависимостей и собирает пакеты в правильном порядке
- **Резолвит имена пакетов** — виртуальные provides (`python3dist(requests)` → `python3-requests`), pkgconfig (`pkgconfig(libxml-2.0)` → `libxml2-devel`), макросы (`%{python3_pkgversion}`)
- **Использует ML** — для сложных случаев резолва имён применяется обученная модель (RandomForest на данных из Fedora)

---

## Подготовка окружения

### 1. Запуск Koji-сервера в Docker

На машине развёрнут локальный Koji-сервер (hub + builder + PostgreSQL) через Docker Compose:

```bash
cd dev/koji-server
make setup
```

Это поднимает три контейнера:

| Сервис | Назначение |
|--------|------------|
| `db` | PostgreSQL 16 — база данных Koji |
| `koji-hub` | Koji Hub + Web UI (Apache + mod_wsgi, Fedora 42) |
| `koji-builder` | kojid + mock — сборщик RPM (Fedora 42, privileged) |

Проверка что сервер работает:

```bash
# Статус контейнеров
docker compose -f dev/koji-server/docker-compose.yml ps

# Проверка подключения к Koji
koji --authtype=ssl moshimoshi
# Ожидаемый вывод: "olá, kojiadmin!"

# Список тегов
koji --authtype=ssl list-tags
# Ожидаемый вывод:
# f42
# f42-build
```

### 2. Конфигурация клиента

Файл `~/.koji/config` уже настроен скриптом `make setup`:

```ini
[koji]
server = https://localhost:8443/kojihub
weburl = https://localhost:8443/koji
topurl = https://localhost:8443/kojifiles
cert = <путь>/dev/koji-server/ssl/kojiadmin.pem
serverca = <путь>/dev/koji-server/ssl/koji_ca_cert.crt
authtype = ssl
target = f42
build_tag = f42-build
```

VibeBuild читает этот конфиг автоматически — не нужно указывать `--server`, `--build-tag` и т.д.

---

## Демонстрация (пошагово)

### Шаг 1: Тесты (342 теста, покрытие 99%)

```bash
python3 -m pytest tests/ -v --cov=vibebuild --cov-report=term-missing
```

Результат:
```
342 passed in ~2s
TOTAL    1261    1    456    1    99%
```

---

### Шаг 2: Скачивание SRPM

Скачать SRPM пакета по имени из Fedora Koji:

```bash
vibebuild --download-only python-six
```

Вывод:
```
Downloading SRPM for: python-six
✓ Downloaded: /tmp/vibebuild/python-six/python-six-1.17.0-2.fc42.src.rpm
```

---

### Шаг 3: Анализ зависимостей (`--analyze-only`)

Извлекает spec-файл из SRPM, парсит `BuildRequires`, проверяет их наличие в Koji:

```bash
vibebuild --analyze-only /tmp/vibebuild/python-six/python-six-1.17.0-2.fc42.src.rpm
```

Вывод:
```
Package: python-six-1.17.0-1
Analyzing dependencies...

BuildRequires (8):
  - pyproject-rpm-macros
  - python3-devel
  - python3-pytest
  - python3-tkinter
  - python3-packaging
  - python3-pip
  - python3-setuptools
  - python3-six

Missing dependencies (7):
  ✗ pyproject-rpm-macros
  ✗ python3-devel
  ...
```

> **Примечание:** Зависимости «missing» потому что в локальном Koji они ещё не собраны. Но они доступны через external repos (Fedora 42), и mock скачает их автоматически при сборке.

---

### Шаг 4: Dry-run — граф сборки (`--dry-run`)

Строит полный DAG зависимостей без реальной сборки:

```bash
vibebuild --dry-run /tmp/vibebuild/python-six/python-six-1.17.0-2.fc42.src.rpm
```

Вывод:
```
Starting vibebuild for: python-six-1.17.0-2.fc42.src.rpm
Analyzing dependencies...
Found 8 packages to build in 2 levels

Build plan:
  Level 1: pyproject-rpm-macros, python3-devel, python3-pytest, ...
  Level 2: python-six

DRY RUN — no builds submitted.
```

Показывает **порядок сборки**: пакеты уровня 1 собираются первыми (параллельно), затем уровень 2.

---

### Шаг 5: Реальная сборка

Полный цикл: анализ → разрешение зависимостей → сборка RPM через Koji/mock:

```bash
vibebuild /tmp/vibebuild/python-six/python-six-1.17.0-2.fc42.src.rpm
```

Вывод:
```
Starting vibebuild for: python-six-1.17.0-2.fc42.src.rpm
Analyzing dependencies...
Found 8 packages to build in 2 levels
Building level 1/2: [...]
  Skipping pyproject-rpm-macros: no SRPM available (available via external repo)
  ...
Waiting for repo regeneration: f42-build
Repo regenerated successfully
Building level 2/2: [python-six]
Building target package: python-six-1.17.0-1
Build submitted: task_id=17

============================================================
BUILD SUMMARY
============================================================
Status: SUCCESS ✓
Total time: 109.7 seconds
Packages built: 1

Successfully built:
  ✓ python-six
      Task ID: 17
============================================================
```

Проверка результата в Koji:

```bash
# Пакет затегирован в f42
koji --authtype=ssl list-tagged f42
# python-six-1.17.0-2.fc42    f42    kojiadmin

# Детали билда
koji --authtype=ssl buildinfo python-six-1.17.0-2.fc42
# State: COMPLETE
# RPMs:
#   python-six-1.17.0-2.fc42.src.rpm
#   python3-six-1.17.0-2.fc42.noarch.rpm
```

---

### Шаг 6: Резолв имён пакетов (модуль)

Демонстрация работы резолвера имён:

```bash
python3 -c "
from vibebuild.name_resolver import PackageNameResolver
r = PackageNameResolver()
print(r.resolve('python3dist(requests)'))   # → python3-requests
print(r.resolve('python3dist(setuptools)')) # → python3-setuptools
print(r.resolve('pkgconfig(libxml-2.0)'))   # → libxml2-devel
print(r.resolve('perl(Getopt::Long)'))      # → perl-Getopt-Long
"
```

---

## Шпаргалка команд

| Режим | Команда | Описание |
|-------|---------|----------|
| Скачать SRPM | `vibebuild --download-only python-six` | Скачивает SRPM из Fedora Koji |
| Анализ | `vibebuild --analyze-only <srpm>` | Показывает BuildRequires и их наличие в Koji |
| Dry-run | `vibebuild --dry-run <srpm>` | Строит граф сборки без реальной сборки |
| Сборка | `vibebuild <srpm>` | Полная сборка с разрешением зависимостей |
| Scratch | `vibebuild --scratch <srpm>` | Тестовая сборка без тегирования |
| По имени | `vibebuild python-six` | Скачать SRPM по имени и собрать |

---

## Архитектура

```
vibebuild/
├── cli.py            — Точка входа, парсинг аргументов, загрузка конфига
├── analyzer.py       — Извлечение spec из SRPM, парсинг BuildRequires
├── fetcher.py        — Скачивание SRPM из Fedora Koji
├── resolver.py       — Проверка зависимостей в Koji, построение DAG
├── builder.py        — Запуск сборки через koji CLI, отслеживание задач
├── name_resolver.py  — Резолв имён: макросы, provides, паттерны
├── ml_resolver.py    — ML-модель (RandomForest) для сложных случаев
├── exceptions.py     — Иерархия исключений
└── data/
    ├── alias_training.json   — Обучающие данные для ML-модели
    └── ml_model.joblib       — Сериализованная модель

dev/koji-server/          — Локальный Koji-сервер в Docker Compose
├── docker-compose.yml
├── Makefile              — make setup / stop / clean / logs
├── hub/                  — Koji Hub + Web (Apache, Fedora 42)
├── builder/              — kojid + mock (privileged)
└── scripts/
    ├── generate-certs.sh — Генерация SSL-сертификатов
    ├── koji-init.sh      — Инициализация тегов, таргетов, групп
    └── setup-client.sh   — Настройка ~/.koji/config
```

---

## Управление сервером

```bash
cd dev/koji-server

make setup    # Первый запуск (certs + containers + init + client config)
make stop     # Остановить (данные сохраняются)
make start    # Запустить снова
make clean    # Полная очистка (контейнеры + volumes + сертификаты)
make logs     # Логи всех сервисов
```
