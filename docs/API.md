# VibeBuild API Reference

## Модули

- [analyzer](#analyzer) — парсинг SRPM и spec файлов
- [resolver](#resolver) — разрешение зависимостей
- [fetcher](#fetcher) — загрузка SRPM
- [builder](#builder) — оркестрация сборок
- [exceptions](#exceptions) — исключения

---

## analyzer

Модуль для анализа SRPM и spec файлов.

### Классы

#### `BuildRequirement`

Представляет одну зависимость сборки.

```python
@dataclass
class BuildRequirement:
    name: str
    version: Optional[str] = None
    operator: Optional[str] = None
```

**Атрибуты:**
- `name` — имя пакета
- `version` — версия (если указана)
- `operator` — оператор сравнения (`>=`, `<=`, `>`, `<`, `=`)

**Пример:**
```python
req = BuildRequirement(name="python3-devel", version="3.9", operator=">=")
print(str(req))  # "python3-devel >= 3.9"
```

---

#### `PackageInfo`

Информация о пакете, извлечённая из spec файла.

```python
@dataclass
class PackageInfo:
    name: str
    version: str
    release: str
    build_requires: list[BuildRequirement]
    source_urls: list[str]
```

**Атрибуты:**
- `name` — имя пакета
- `version` — версия
- `release` — релиз
- `build_requires` — список зависимостей сборки
- `source_urls` — URL исходников

**Свойства:**
- `nvr` — Name-Version-Release строка

---

#### `SpecAnalyzer`

Анализатор spec файлов.

```python
class SpecAnalyzer:
    def analyze_spec(self, spec_path: str) -> PackageInfo: ...
```

**Методы:**

##### `analyze_spec(spec_path: str) -> PackageInfo`

Парсит spec файл и извлекает информацию о пакете.

**Параметры:**
- `spec_path` — путь к .spec файлу

**Возвращает:**
- `PackageInfo` с данными пакета

**Исключения:**
- `FileNotFoundError` — файл не найден
- `SpecParseError` — ошибка парсинга spec

**Пример:**
```python
analyzer = SpecAnalyzer()
info = analyzer.analyze_spec("/path/to/package.spec")
print(f"Package: {info.name}-{info.version}")
for req in info.build_requires:
    print(f"  Requires: {req}")
```

---

### Функции

#### `get_build_requires(srpm_path: str) -> list[str]`

Извлекает список BuildRequires из SRPM файла.

**Параметры:**
- `srpm_path` — путь к .src.rpm файлу

**Возвращает:**
- Список имён пакетов (без версий)

**Исключения:**
- `FileNotFoundError` — SRPM не найден
- `InvalidSRPMError` — невалидный SRPM

**Пример:**
```python
requires = get_build_requires("my-package-1.0-1.fc40.src.rpm")
print(requires)  # ["python3-devel", "gcc", "make"]
```

---

#### `get_package_info_from_srpm(srpm_path: str) -> PackageInfo`

Извлекает полную информацию о пакете из SRPM.

**Параметры:**
- `srpm_path` — путь к .src.rpm файлу

**Возвращает:**
- `PackageInfo` с данными пакета

**Пример:**
```python
info = get_package_info_from_srpm("my-package-1.0-1.fc40.src.rpm")
print(f"NVR: {info.nvr}")
```

---

## resolver

Модуль для разрешения зависимостей и построения графа сборки.

### Классы

#### `DependencyNode`

Узел в графе зависимостей.

```python
@dataclass
class DependencyNode:
    name: str
    srpm_path: Optional[str] = None
    package_info: Optional[PackageInfo] = None
    dependencies: list[str] = field(default_factory=list)
    is_available: bool = False
    build_order: int = -1
```

---

#### `KojiClient`

Клиент для взаимодействия с Koji.

```python
class KojiClient:
    def __init__(
        self,
        server: str = "https://koji.fedoraproject.org/kojihub",
        web_url: str = "https://koji.fedoraproject.org/koji",
        cert: Optional[str] = None,
        serverca: Optional[str] = None,
    ): ...
```

**Методы:**

##### `list_packages(tag: str) -> list[str]`

Список всех пакетов в теге.

##### `list_tagged_builds(tag: str) -> dict[str, str]`

Список всех сборок в теге. Возвращает `{package_name: nvr}`.

##### `package_exists(package: str, tag: str) -> bool`

Проверяет существование пакета в теге.

##### `search_package(pattern: str) -> list[str]`

Поиск пакетов по паттерну.

---

#### `DependencyResolver`

Разрешает зависимости и строит граф сборки.

```python
class DependencyResolver:
    def __init__(
        self,
        koji_client: Optional[KojiClient] = None,
        koji_tag: str = "fedora-build"
    ): ...
```

**Методы:**

##### `find_missing_deps(deps: list[str | BuildRequirement], check_provides: bool = True) -> list[str]`

Находит зависимости, отсутствующие в Koji.

**Параметры:**
- `deps` — список зависимостей
- `check_provides` — проверять ли provides

**Возвращает:**
- Список отсутствующих пакетов

**Пример:**
```python
resolver = DependencyResolver(koji_tag="fedora-build")
missing = resolver.find_missing_deps(["python3-devel", "my-custom-lib"])
print(f"Missing: {missing}")
```

---

##### `build_dependency_graph(root_package: str, srpm_path: str, srpm_resolver: Optional[callable] = None) -> dict[str, DependencyNode]`

Строит полный граф зависимостей.

**Параметры:**
- `root_package` — имя корневого пакета
- `srpm_path` — путь к SRPM корневого пакета
- `srpm_resolver` — функция для получения SRPM по имени пакета

**Возвращает:**
- Словарь `{package_name: DependencyNode}`

---

##### `topological_sort() -> list[str]`

Возвращает пакеты в порядке сборки (зависимости первыми).

**Исключения:**
- `CircularDependencyError` — обнаружена циклическая зависимость

---

##### `get_build_chain() -> list[list[str]]`

Группирует пакеты по уровням (для параллельной сборки).

**Возвращает:**
- Список списков. Пакеты в одном списке могут собираться параллельно.

**Пример:**
```python
chain = resolver.get_build_chain()
for level, packages in enumerate(chain):
    print(f"Level {level}: {packages}")
# Level 0: ['lib-base', 'lib-core']
# Level 1: ['lib-foo', 'lib-bar']
# Level 2: ['my-app']
```

---

## fetcher

Модуль для загрузки SRPM из внешних источников.

### Классы

#### `SRPMSource`

Конфигурация источника SRPM.

```python
@dataclass
class SRPMSource:
    name: str
    base_url: str
    koji_server: Optional[str] = None
    priority: int = 100
```

---

#### `SRPMFetcher`

Загрузчик SRPM.

```python
class SRPMFetcher:
    def __init__(
        self,
        download_dir: Optional[str] = None,
        sources: Optional[list[SRPMSource]] = None,
        fedora_release: str = "rawhide"
    ): ...
```

**Методы:**

##### `download_srpm(package_name: str, version: Optional[str] = None) -> str`

Загружает SRPM для пакета.

**Параметры:**
- `package_name` — имя пакета
- `version` — версия (опционально)

**Возвращает:**
- Путь к загруженному SRPM

**Исключения:**
- `SRPMNotFoundError` — SRPM не найден ни в одном источнике

**Пример:**
```python
fetcher = SRPMFetcher(download_dir="/tmp/srpms")
srpm_path = fetcher.download_srpm("python-requests")
print(f"Downloaded: {srpm_path}")
```

---

##### `search_fedora_src(name: str) -> list[str]`

Поиск пакетов в Fedora.

**Параметры:**
- `name` — имя или паттерн

**Возвращает:**
- Список имён пакетов

---

##### `get_package_versions(package_name: str) -> list[str]`

Получает доступные версии пакета.

---

##### `clear_cache() -> None`

Очищает кэш загруженных SRPM.

##### `cleanup() -> None`

Удаляет все загруженные файлы.

---

## builder

Модуль для оркестрации сборок в Koji.

### Перечисления

#### `BuildStatus`

```python
class BuildStatus(Enum):
    PENDING = "pending"
    BUILDING = "building"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"
```

### Классы

#### `BuildTask`

Информация о задаче сборки.

```python
@dataclass
class BuildTask:
    package_name: str
    srpm_path: str
    target: str
    task_id: Optional[int] = None
    status: BuildStatus = BuildStatus.PENDING
    error_message: Optional[str] = None
    nvr: Optional[str] = None
```

---

#### `BuildResult`

Результат операции сборки.

```python
@dataclass
class BuildResult:
    success: bool
    tasks: list[BuildTask] = field(default_factory=list)
    failed_packages: list[str] = field(default_factory=list)
    built_packages: list[str] = field(default_factory=list)
    total_time: float = 0.0
```

---

#### `KojiBuilder`

Оркестратор сборок.

```python
class KojiBuilder:
    def __init__(
        self,
        koji_server: str = "https://koji.fedoraproject.org/kojihub",
        koji_web_url: str = "https://koji.fedoraproject.org/koji",
        cert: Optional[str] = None,
        serverca: Optional[str] = None,
        target: str = "fedora-target",
        build_tag: str = "fedora-build",
        scratch: bool = False,
        nowait: bool = False,
        download_dir: Optional[str] = None,
    ): ...
```

**Методы:**

##### `build_package(srpm_path: str, wait: bool = True) -> BuildTask`

Отправляет пакет на сборку.

**Параметры:**
- `srpm_path` — путь к SRPM
- `wait` — ждать завершения

**Возвращает:**
- `BuildTask` с информацией о сборке

**Исключения:**
- `FileNotFoundError` — SRPM не найден
- `KojiBuildError` — ошибка сборки

---

##### `build_with_deps(srpm_path: str) -> BuildResult`

**Главная функция VibeBuild.** Собирает пакет с автоматическим разрешением зависимостей.

**Параметры:**
- `srpm_path` — путь к SRPM

**Возвращает:**
- `BuildResult` с полной информацией

**Пример:**
```python
builder = KojiBuilder(
    koji_server="https://koji.example.com/kojihub",
    cert="/path/to/cert.pem",
    target="my-target",
)
result = builder.build_with_deps("my-package-1.0-1.src.rpm")

if result.success:
    print(f"Built {len(result.built_packages)} packages")
else:
    print(f"Failed: {result.failed_packages}")
```

---

##### `wait_for_repo(tag: Optional[str] = None, timeout: int = 1800) -> bool`

Ожидает регенерации репозитория.

**Параметры:**
- `tag` — тег (по умолчанию build_tag)
- `timeout` — таймаут в секундах

**Возвращает:**
- `True` если репозиторий обновлён

---

##### `build_chain(packages: list[tuple[str, str]]) -> BuildResult`

Собирает несколько пакетов по порядку.

**Параметры:**
- `packages` — список `(package_name, srpm_path)`

---

##### `get_build_status(task_id: int) -> BuildStatus`

Получает статус задачи сборки.

##### `cancel_build(task_id: int) -> bool`

Отменяет сборку.

---

## exceptions

### Иерархия исключений

```python
VibeBuildError                    # Базовое исключение
├── InvalidSRPMError              # Невалидный SRPM
├── SpecParseError                # Ошибка парсинга spec
├── DependencyResolutionError     # Ошибка разрешения зависимостей
│   └── CircularDependencyError   # Циклическая зависимость
├── SRPMNotFoundError             # SRPM не найден
├── KojiBuildError                # Ошибка сборки
└── KojiConnectionError           # Ошибка подключения к Koji
```

### Использование

```python
from vibebuild.exceptions import (
    VibeBuildError,
    InvalidSRPMError,
    CircularDependencyError,
)

try:
    result = builder.build_with_deps("package.src.rpm")
except CircularDependencyError as e:
    print(f"Circular dependency: {e}")
except VibeBuildError as e:
    print(f"Build error: {e}")
```
