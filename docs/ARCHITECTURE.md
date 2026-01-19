# VibeBuild Architecture

## Обзор системы

VibeBuild — это расширение для Koji, которое автоматизирует разрешение зависимостей при сборке RPM пакетов. Система состоит из двух основных частей:

1. **VibeBuild CLI** — Python-приложение для анализа зависимостей и оркестрации сборок
2. **Koji Infrastructure** — сервер сборки RPM пакетов

## Архитектура высокого уровня

```
┌─────────────────────────────────────────────────────────────────┐
│                         User                                     │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VibeBuild CLI                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Analyzer │  │ Resolver │  │ Fetcher  │  │ Builder  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    Koji Hub     │  │  Fedora Koji    │  │  src.fedoraproj │
│   (internal)    │  │   (external)    │  │    (SRPM src)   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Koji Builder   │
│    (mock)       │
└─────────────────┘
```

## Компоненты VibeBuild

### 1. Analyzer (`analyzer.py`)

**Ответственность:** Парсинг SRPM и spec файлов, извлечение метаданных.

```
┌─────────────────────────────────────────┐
│              Analyzer                    │
├─────────────────────────────────────────┤
│ + get_build_requires(srpm) -> list[str] │
│ + get_package_info_from_srpm() -> Info  │
├─────────────────────────────────────────┤
│              SpecAnalyzer               │
├─────────────────────────────────────────┤
│ + analyze_spec(path) -> PackageInfo     │
│ - _parse_spec_content(content)          │
│ - _parse_build_requires(line)           │
│ - _expand_macros(value)                 │
└─────────────────────────────────────────┘
```

**Data Flow:**
```
SRPM File ──► rpm2cpio ──► .spec file ──► SpecAnalyzer ──► PackageInfo
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ - name          │
                                                    │ - version       │
                                                    │ - release       │
                                                    │ - build_requires│
                                                    │ - source_urls   │
                                                    └─────────────────┘
```

### 2. Resolver (`resolver.py`)

**Ответственность:** Проверка доступности зависимостей в Koji, построение графа зависимостей.

```
┌─────────────────────────────────────────┐
│            DependencyResolver           │
├─────────────────────────────────────────┤
│ + find_missing_deps(deps, tag) -> list  │
│ + build_dependency_graph(pkg, srpm)     │
│ + topological_sort() -> list[str]       │
│ + get_build_chain() -> list[list[str]]  │
├─────────────────────────────────────────┤
│              KojiClient                 │
├─────────────────────────────────────────┤
│ + list_packages(tag) -> list[str]       │
│ + list_tagged_builds(tag) -> dict       │
│ + package_exists(pkg, tag) -> bool      │
└─────────────────────────────────────────┘
```

**Алгоритм построения DAG:**

```
1. Начать с корневого пакета
2. Для каждого пакета:
   a. Если пакет есть в Koji tag → пометить как available
   b. Иначе:
      - Извлечь BuildRequires
      - Найти недостающие зависимости
      - Рекурсивно обработать каждую зависимость
3. Построить граф зависимостей
4. Выполнить топологическую сортировку
```

**Структура данных:**

```
DependencyNode:
  - name: str
  - srpm_path: Optional[str]
  - dependencies: list[str]
  - is_available: bool
  - build_order: int

Graph Example:
                    ┌─────────┐
                    │ my-app  │
                    └────┬────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
      ┌─────────┐   ┌─────────┐   ┌─────────┐
      │ lib-foo │   │ lib-bar │   │ lib-baz │
      └────┬────┘   └─────────┘   └────┬────┘
           │         (available)       │
           ▼                           ▼
      ┌─────────┐                 ┌─────────┐
      │lib-base │                 │lib-core │
      └─────────┘                 └─────────┘
       (available)                (available)

Build Order: [lib-foo, lib-baz, my-app]
Build Chain: [[lib-foo, lib-baz], [my-app]]
```

### 3. Fetcher (`fetcher.py`)

**Ответственность:** Загрузка SRPM из внешних источников.

```
┌─────────────────────────────────────────┐
│              SRPMFetcher                │
├─────────────────────────────────────────┤
│ + download_srpm(name, version) -> path  │
│ + search_fedora_src(name) -> list       │
│ + get_package_versions(name) -> list    │
├─────────────────────────────────────────┤
│ - _download_from_koji(...)              │
│ - _download_from_src(...)               │
│ - _extract_sources(spec)                │
└─────────────────────────────────────────┘
```

**Источники SRPM (в порядке приоритета):**

1. **Fedora Koji** (`koji.fedoraproject.org`)
   - Метод: `koji download-build --type=src`
   - Преимущество: готовые SRPM

2. **src.fedoraproject.org**
   - Метод: скачать spec + sources, собрать SRPM локально
   - Используется как fallback

### 4. Builder (`builder.py`)

**Ответственность:** Оркестрация сборок в Koji.

```
┌─────────────────────────────────────────┐
│              KojiBuilder                │
├─────────────────────────────────────────┤
│ + build_package(srpm, wait) -> Task     │
│ + build_with_deps(srpm) -> BuildResult  │
│ + wait_for_repo(tag, timeout) -> bool   │
│ + build_chain(packages) -> BuildResult  │
├─────────────────────────────────────────┤
│ - _run_koji(*args) -> CompletedProcess  │
│ + get_build_status(task_id) -> Status   │
│ + cancel_build(task_id) -> bool         │
└─────────────────────────────────────────┘
```

**Алгоритм build_with_deps:**

```
┌──────────────────────┐
│ 1. Parse SRPM        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. Build dep graph   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. Get build chain   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ 4. For each level in chain:              │
│    a. Build all packages in level        │
│    b. Wait for builds to complete        │
│    c. Wait for repo regeneration         │
└──────────────────────┬───────────────────┘
           │
           ▼
┌──────────────────────┐
│ 5. Build target pkg  │
└──────────────────────┘
```

### 5. CLI (`cli.py`)

**Ответственность:** Командный интерфейс пользователя.

```
Commands:
  vibebuild TARGET SRPM          # Build with deps
  vibebuild --analyze-only SRPM  # Only analyze
  vibebuild --download-only PKG  # Only download
  vibebuild --dry-run TARGET SRPM # Show plan
```

## Инфраструктура Koji

### Компоненты

```
┌─────────────────────────────────────────────────────────────────┐
│                        VPS / Server                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Koji Hub   │    │ Koji Builder│    │  Koji Web   │         │
│  │  (Apache)   │    │   (kojid)   │    │  (Apache)   │         │
│  └──────┬──────┘    └──────┬──────┘    └─────────────┘         │
│         │                  │                                     │
│         ▼                  ▼                                     │
│  ┌─────────────┐    ┌─────────────┐                             │
│  │ PostgreSQL  │    │    Mock     │                             │
│  │     DB      │    │  (chroot)   │                             │
│  └─────────────┘    └─────────────┘                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────┐           │
│  │                    /mnt/koji                      │           │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐       │           │
│  │  │ packages │  │   repos  │  │   work   │       │           │
│  │  └──────────┘  └──────────┘  └──────────┘       │           │
│  └──────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### Tags и Targets

```
Tags:
  fedora-dest     ← Destination tag (ready packages)
       │
       │ (parent)
       ▼
  fedora-build    ← Build tag (buildroot)
       │
       │ (external repos)
       ▼
  [Fedora mirrors] ← RPM dependencies

Target:
  fedora-target
    build_tag: fedora-build
    dest_tag: fedora-dest
```

### Build Flow

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│   Upload   │────▶│   Build    │────▶│    Tag     │
│    SRPM    │     │   (mock)   │     │  Package   │
└────────────┘     └────────────┘     └────────────┘
                         │
                         ▼
                   ┌────────────┐
                   │  Regen     │
                   │   Repo     │
                   └────────────┘
```

## Обработка ошибок

### Retry Logic

```python
RETRY_CONFIG = {
    "koji_build": {
        "max_retries": 3,
        "backoff": "exponential",
        "initial_delay": 10,
    },
    "download_srpm": {
        "max_retries": 2,
        "backoff": "linear",
        "initial_delay": 5,
    },
}
```

### Error Hierarchy

```
VibeBuildError
├── InvalidSRPMError
├── SpecParseError
├── DependencyResolutionError
│   └── CircularDependencyError
├── SRPMNotFoundError
├── KojiBuildError
└── KojiConnectionError
```

## Производительность

### Кэширование

- **Available packages cache:** кэшируется список пакетов в Koji tag
- **Downloaded SRPMs cache:** скачанные SRPM сохраняются для повторного использования
- **Dependency graph cache:** граф зависимостей строится один раз

### Параллелизм

- Пакеты на одном уровне графа зависимостей могут собираться параллельно
- Загрузка SRPM может выполняться параллельно с анализом

## Безопасность

### Аутентификация

- SSL client certificates для Koji
- CA verification для HTTPS соединений

### Изоляция сборок

- Все сборки выполняются в mock chroot
- Изолированная сетевая среда в builder
