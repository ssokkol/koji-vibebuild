# Демонстрация VibeBuild

## Введение

**VibeBuild** — расширение системы сборки [Koji](https://koji.fedoraproject.org/) командой `vibebuild`.
Одна команда `vibebuild <пакет>` запускает полный цикл: скачивание SRPM, разрешение зависимостей и сборку.
В отличие от стандартной команды `koji build`, которая собирает один пакет и падает при отсутствии зависимостей, VibeBuild:

- **Автоматически разрешает зависимости** — находит недостающие `BuildRequires`, скачивает их SRPM из Koji и строит DAG (граф зависимостей) для правильного порядка сборки
- **Резолвит имена пакетов** — виртуальные provides (`python3dist(requests)` → `python3-requests`), макросы (`%{python3_pkgversion}`) и короткие алиасы
- **Использует ML** — для сложных случаев резолва имён, когда правила не срабатывают, применяется обученная модель (RandomForest на алиасах из Fedora)

---

## Почему AlmaLinux не ломает демонстрацию

VibeBuild **полностью работает на AlmaLinux 9** (и любом RHEL-совместимом дистрибутиве). Вот почему:

1. **Работа с Fedora Koji удалённо.** VibeBuild взаимодействует с `koji.fedoraproject.org` через CLI (`koji` команда) и HTTP API. Это работает с любой машины с сетевым доступом.

2. **Пакет `koji` из EPEL идентичен.** На AlmaLinux 9 `koji` устанавливается из EPEL и функционально идентичен Fedora-версии — это тот же Python-клиент для Koji hub.

3. **Локальные операции не зависят от ОС.** Скачивание SRPM, извлечение spec-файла (`rpm2cpio`), анализ `BuildRequires`, построение графа зависимостей — всё это стандартные операции с RPM, доступные на любой RPM-based системе.

4. **Реальная сборка идёт на удалённых билдерах.** Команда `koji build` отправляет SRPM на серверы Koji, где сборка выполняется в чистых chroot-окружениях. Локальная ОС не влияет на результат.

5. **Единственное ограничение** — для отправки задач на сборку (`koji build`) нужна аутентификация в Fedora Koji (Fedora Account System). Все остальные режимы (download, analyze, dry-run) работают без аутентификации.

---

## Предусловия для AlmaLinux 9

```bash
# Подключить EPEL (если ещё не подключён)
sudo dnf install epel-release

# Установить необходимые пакеты
sudo dnf install koji rpm-build python3-pip

# Установить vibebuild
cd koji-vibebuild
pip install -e .
```

Проверка:
```bash
python3 --version   # Python 3.9.x
koji --version       # koji 1.x
vibebuild --version  # vibebuild 0.1.0
```

---

## Предусловия для Fedora (38+)

```bash
# Установить необходимые пакеты
sudo dnf install koji rpm-build python3-pip

# Установить vibebuild
cd koji-vibebuild
pip install -e .
```

Проверка — аналогично.

---

## Запуск тестов

Тесты — доказательство работоспособности всех модулей. 340 тестов, покрытие 99%.

```bash
python3 -m pytest tests/ -v --cov=vibebuild --cov-report=term-missing
```

Ожидаемый результат:
```
340 passed in ~2s

Name                         Stmts   Miss Branch BrPart  Cover
------------------------------------------------------------------------
vibebuild/__init__.py            8      0      0      0   100%
vibebuild/analyzer.py          164      0     70      0   100%
vibebuild/builder.py           226      0     64      0   100%
vibebuild/cli.py               226      0     74      0   100%
vibebuild/exceptions.py         18      0      0      0   100%
vibebuild/fetcher.py           173      1     66      1    99%
vibebuild/ml_resolver.py       114      0     24      0   100%
vibebuild/name_resolver.py     124      0     58      0   100%
vibebuild/resolver.py          196      0     92      0   100%
------------------------------------------------------------------------
TOTAL                         1249      1    448      1    99%
```

---

## Демо 1: Загрузка SRPM

Скачать SRPM пакета `python-requests` из Fedora Koji:

```bash
vibebuild --download-only python-requests
```

Ожидаемый вывод:
```
Downloading SRPM for: python-requests
✓ Downloaded: /tmp/vibebuild/python-requests/python-requests-2.32.3-4.fc42.src.rpm
```

Файл сохраняется в `/tmp/vibebuild/<имя-пакета>/`. Можно указать другой каталог через `--download-dir`.

---

## Демо 2: Анализ зависимостей

Проанализировать скачанный SRPM — извлечь spec-файл, показать метаданные и `BuildRequires`:

```bash
vibebuild --analyze-only --build-tag f42-build \
    /tmp/vibebuild/python-requests/python-requests-2.32.3-4.fc42.src.rpm
```

Ожидаемый вывод:
```
Analyzing: /tmp/vibebuild/python-requests/python-requests-2.32.3-4.fc42.src.rpm

Package: python-requests
Version: 2.32.3
Release: 4
NVR: python-requests-2.32.3-4

BuildRequires (5):
  - python3-devel
  - python3dist(pytest)
  - python3dist(pytest-httpbin)
  - python3dist(pytest-mock)
  - python3dist(trustme)

Checking availability in Koji...

Missing dependencies (5):
  ✗ python3-devel
  ✗ python3dist(pytest)
  ✗ python3dist(pytest-httpbin)
  ✗ python3dist(pytest-mock)
  ✗ python3dist(trustme)
```

> **Примечание:** Зависимости помечены как «missing» потому что `koji list-pkgs` ищет по имени source-пакета, а `python3-devel` — subpackage от `python3.14`. VibeBuild обрабатывает такие случаи при построении графа сборки (dry-run/build).

---

## Демо 3: Dry-run (граф сборки)

Показать порядок сборки без реальной сборки. Для быстрой демонстрации рекомендуется использовать пакет с небольшим числом зависимостей:

```bash
# Если target = f42 прописан в ~/.koji/config:
vibebuild --dry-run --build-tag f42-build \
    /tmp/vibebuild/python-chardet/python-chardet-5.2.0-16.fc42.src.rpm

# Явный target (прежняя форма):
vibebuild --dry-run --build-tag f42-build f42 \
    /tmp/vibebuild/python-chardet/python-chardet-5.2.0-16.fc42.src.rpm
```

VibeBuild в этом режиме:
1. Извлекает `BuildRequires` из SRPM
2. Проверяет, какие зависимости отсутствуют в Koji tag `f42-build`
3. Для каждой недостающей зависимости скачивает SRPM и рекурсивно анализирует её зависимости
4. Строит DAG и выводит уровни сборки (level 0 — пакеты без зависимостей, level 1 — зависят от level 0 и т.д.)

> **Примечание:** Для пакетов с глубоким деревом зависимостей (например `python-requests`) dry-run может занять несколько минут из-за скачивания SRPM всех транзитивных зависимостей.

---

## Демо 4 (опционально): Реальная сборка

При наличии аутентификации в Fedora Koji (FAS) можно выполнить scratch-сборку:

```bash
# Если target = f42 прописан в ~/.koji/config:
vibebuild --scratch --build-tag f42-build \
    /tmp/vibebuild/python-requests/python-requests-2.32.3-4.fc42.src.rpm

# Явный target (прежняя форма):
vibebuild --scratch --build-tag f42-build f42 \
    /tmp/vibebuild/python-requests/python-requests-2.32.3-4.fc42.src.rpm
```

Scratch-сборка — тестовая сборка без тегирования результата. Для аутентификации нужен Kerberos-тикет или клиентский сертификат в `~/.koji/config`.

---

## Демо 5: Резолв имён пакетов (модуль)

Продемонстрировать работу резолвера имён напрямую:

```bash
python3 -c "
from vibebuild.name_resolver import PackageNameResolver
r = PackageNameResolver()
print(r.resolve('python3dist(requests)'))   # → python3-requests
print(r.resolve('python3dist(setuptools)')) # → python3-setuptools
print(r.resolve('pkgconfig(libxml-2.0)'))   # → libxml2-devel
"
```

---

## Шпаргалка команд

| Режим | Команда | Что делает |
|-------|---------|------------|
| Загрузка SRPM | `vibebuild --download-only python-requests` | Скачивает SRPM из Fedora Koji |
| Анализ зависимостей | `vibebuild --analyze-only --build-tag f42-build <path.src.rpm>` | Парсит spec, выводит BuildRequires и проверяет наличие в Koji |
| Dry-run | `vibebuild --dry-run --build-tag f42-build f42 <path.src.rpm>` | Строит граф сборки без реальной сборки |
| Сборка | `vibebuild --build-tag f42-build f42 <path.src.rpm>` | Полная сборка с разрешением зависимостей |
| Scratch-сборка | `vibebuild --scratch --build-tag f42-build f42 <path.src.rpm>` | Тестовая сборка без тегирования |
| Без зависимостей | `vibebuild --no-deps f42 <path.src.rpm>` | Сборка без разрешения зависимостей |
| По имени пакета | `vibebuild python-requests` | Скачать SRPM по имени и собрать (target из ~/.koji/config) |
| С явным target | `vibebuild fedora-target python-requests` | Скачать SRPM по имени и собрать (явный target) |

---

## Архитектура

```
vibebuild/
├── cli.py            — Точка входа, парсинг аргументов, диспетчер команд
├── analyzer.py       — Извлечение spec из SRPM, парсинг BuildRequires
├── fetcher.py        — Скачивание SRPM из Fedora Koji (API + fallback на koji CLI)
├── resolver.py       — Проверка зависимостей в Koji tag, построение DAG
├── builder.py        — Запуск сборки через koji CLI, отслеживание статуса
├── name_resolver.py  — Резолв имён: макросы, виртуальные provides, паттерны
├── ml_resolver.py    — ML-модель (RandomForest) для сложных случаев резолва
├── exceptions.py     — Иерархия исключений
└── data/
    ├── alias_training.json   — Обучающие данные для ML-модели
    └── ml_model.joblib       — Обученная модель (если есть)
```

**Роль ML:** Когда стандартные правила `name_resolver.py` не могут определить имя source-пакета по имени BuildRequires (например, `rubygem-foo` → `rubygem-foo`), ML-модель предсказывает маппинг на основе обучения на реальных данных из Fedora.
