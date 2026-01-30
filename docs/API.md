# VibeBuild API Reference

## Modules

- [analyzer](#analyzer) — SRPM and spec file parsing
- [resolver](#resolver) — dependency resolution
- [fetcher](#fetcher) — SRPM downloading
- [builder](#builder) — build orchestration
- [exceptions](#exceptions) — exceptions

---

## analyzer

Module for analyzing SRPM and spec files.

### Classes

#### `BuildRequirement`

Represents a single build dependency.

```python
@dataclass
class BuildRequirement:
    name: str
    version: Optional[str] = None
    operator: Optional[str] = None
```

**Attributes:**
- `name` — package name
- `version` — version (if specified)
- `operator` — comparison operator (`>=`, `<=`, `>`, `<`, `=`)

**Example:**
```python
req = BuildRequirement(name="python3-devel", version="3.9", operator=">=")
print(str(req))  # "python3-devel >= 3.9"
```

---

#### `PackageInfo`

Package information extracted from spec file.

```python
@dataclass
class PackageInfo:
    name: str
    version: str
    release: str
    build_requires: list[BuildRequirement]
    source_urls: list[str]
```

**Attributes:**
- `name` — package name
- `version` — version
- `release` — release
- `build_requires` — list of build dependencies
- `source_urls` — source URLs

**Properties:**
- `nvr` — Name-Version-Release string

---

#### `SpecAnalyzer`

Spec file analyzer.

```python
class SpecAnalyzer:
    def analyze_spec(self, spec_path: str) -> PackageInfo: ...
```

**Methods:**

##### `analyze_spec(spec_path: str) -> PackageInfo`

Parses spec file and extracts package information.

**Parameters:**
- `spec_path` — path to .spec file

**Returns:**
- `PackageInfo` with package data

**Exceptions:**
- `FileNotFoundError` — file not found
- `SpecParseError` — spec parsing error

**Example:**
```python
analyzer = SpecAnalyzer()
info = analyzer.analyze_spec("/path/to/package.spec")
print(f"Package: {info.name}-{info.version}")
for req in info.build_requires:
    print(f"  Requires: {req}")
```

---

### Functions

#### `get_build_requires(srpm_path: str) -> list[str]`

Extracts BuildRequires list from SRPM file.

**Parameters:**
- `srpm_path` — path to .src.rpm file

**Returns:**
- List of package names (without versions)

**Exceptions:**
- `FileNotFoundError` — SRPM not found
- `InvalidSRPMError` — invalid SRPM

**Example:**
```python
requires = get_build_requires("my-package-1.0-1.fc40.src.rpm")
print(requires)  # ["python3-devel", "gcc", "make"]
```

---

#### `get_package_info_from_srpm(srpm_path: str) -> PackageInfo`

Extracts complete package information from SRPM.

**Parameters:**
- `srpm_path` — path to .src.rpm file

**Returns:**
- `PackageInfo` with package data

**Example:**
```python
info = get_package_info_from_srpm("my-package-1.0-1.fc40.src.rpm")
print(f"NVR: {info.nvr}")
```

---

## resolver

Module for dependency resolution and build graph construction.

### Classes

#### `DependencyNode`

Node in the dependency graph.

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

Client for interacting with Koji.

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

**Methods:**

##### `list_packages(tag: str) -> list[str]`

List of all packages in tag.

##### `list_tagged_builds(tag: str) -> dict[str, str]`

List of all builds in tag. Returns `{package_name: nvr}`.

##### `package_exists(package: str, tag: str) -> bool`

Checks if package exists in tag.

##### `search_package(pattern: str) -> list[str]`

Search packages by pattern.

---

#### `DependencyResolver`

Resolves dependencies and builds build graph.

```python
class DependencyResolver:
    def __init__(
        self,
        koji_client: Optional[KojiClient] = None,
        koji_tag: str = "fedora-build"
    ): ...
```

**Methods:**

##### `find_missing_deps(deps: list[str | BuildRequirement], check_provides: bool = True) -> list[str]`

Finds dependencies missing in Koji.

**Parameters:**
- `deps` — list of dependencies
- `check_provides` — whether to check provides

**Returns:**
- List of missing packages

**Example:**
```python
resolver = DependencyResolver(koji_tag="fedora-build")
missing = resolver.find_missing_deps(["python3-devel", "my-custom-lib"])
print(f"Missing: {missing}")
```

---

##### `build_dependency_graph(root_package: str, srpm_path: str, srpm_resolver: Optional[callable] = None) -> dict[str, DependencyNode]`

Builds complete dependency graph.

**Parameters:**
- `root_package` — root package name
- `srpm_path` — path to root package SRPM
- `srpm_resolver` — function to get SRPM by package name

**Returns:**
- Dictionary `{package_name: DependencyNode}`

---

##### `topological_sort() -> list[str]`

Returns packages in build order (dependencies first).

**Exceptions:**
- `CircularDependencyError` — circular dependency detected

---

##### `get_build_chain() -> list[list[str]]`

Groups packages by levels (for parallel building).

**Returns:**
- List of lists. Packages in the same list can be built in parallel.

**Example:**
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

Module for downloading SRPMs from external sources.

### Classes

#### `SRPMSource`

SRPM source configuration.

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

SRPM downloader.

```python
class SRPMFetcher:
    def __init__(
        self,
        download_dir: Optional[str] = None,
        sources: Optional[list[SRPMSource]] = None,
        fedora_release: str = "rawhide"
    ): ...
```

**Methods:**

##### `download_srpm(package_name: str, version: Optional[str] = None) -> str`

Downloads SRPM for package.

**Parameters:**
- `package_name` — package name
- `version` — version (optional)

**Returns:**
- Path to downloaded SRPM

**Exceptions:**
- `SRPMNotFoundError` — SRPM not found in any source

**Example:**
```python
fetcher = SRPMFetcher(download_dir="/tmp/srpms")
srpm_path = fetcher.download_srpm("python-requests")
print(f"Downloaded: {srpm_path}")
```

---

##### `search_fedora_src(name: str) -> list[str]`

Search packages in Fedora.

**Parameters:**
- `name` — name or pattern

**Returns:**
- List of package names

---

##### `get_package_versions(package_name: str) -> list[str]`

Gets available package versions.

---

##### `clear_cache() -> None`

Clears downloaded SRPM cache.

##### `cleanup() -> None`

Removes all downloaded files.

---

## builder

Module for build orchestration in Koji.

### Enumerations

#### `BuildStatus`

```python
class BuildStatus(Enum):
    PENDING = "pending"
    BUILDING = "building"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"
```

### Classes

#### `BuildTask`

Build task information.

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

Build operation result.

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

Build orchestrator.

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

**Methods:**

##### `build_package(srpm_path: str, wait: bool = True) -> BuildTask`

Submits package for building.

**Parameters:**
- `srpm_path` — path to SRPM
- `wait` — wait for completion

**Returns:**
- `BuildTask` with build information

**Exceptions:**
- `FileNotFoundError` — SRPM not found
- `KojiBuildError` — build error

---

##### `build_with_deps(srpm_path: str) -> BuildResult`

**Main VibeBuild function.** Builds package with automatic dependency resolution.

**Parameters:**
- `srpm_path` — path to SRPM

**Returns:**
- `BuildResult` with complete information

**Example:**
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

Waits for repository regeneration.

**Parameters:**
- `tag` — tag (defaults to build_tag)
- `timeout` — timeout in seconds

**Returns:**
- `True` if repository is updated

---

##### `build_chain(packages: list[tuple[str, str]]) -> BuildResult`

Builds multiple packages in order.

**Parameters:**
- `packages` — list of `(package_name, srpm_path)`

---

##### `get_build_status(task_id: int) -> BuildStatus`

Gets build task status.

##### `cancel_build(task_id: int) -> bool`

Cancels build.

---

## exceptions

### Exception Hierarchy

```python
VibeBuildError                    # Base exception
├── InvalidSRPMError              # Invalid SRPM
├── SpecParseError                # Spec parsing error
├── DependencyResolutionError     # Dependency resolution error
│   └── CircularDependencyError   # Circular dependency
├── SRPMNotFoundError             # SRPM not found
├── KojiBuildError                # Build error
└── KojiConnectionError           # Koji connection error
```

### Usage

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
