# VibeBuild API Reference

## Modules

- [analyzer](#analyzer) — SRPM and spec file parsing
- [name_resolver](#name_resolver) — package name resolution (rules + ML)
- [ml_resolver](#ml_resolver) — ML-based package name prediction
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

## name_resolver

Module for rule-based package name resolution with optional ML fallback.

### Constants

#### `SYSTEM_MACROS`

Dictionary of known RPM system macros for expanding `%{...}` in dependency names.

```python
SYSTEM_MACROS: dict[str, str] = {
    "python3_pkgversion": "3",
    "python3_version": "3.12",
    "python3_version_nodots": "312",
    "__python3": "/usr/bin/python3",
    "_prefix": "/usr",
    "_bindir": "/usr/bin",
    "_libdir": "/usr/lib64",
    # ... 18 macros total
}
```

---

#### `PROVIDE_PATTERNS`

List of compiled regex patterns for resolving virtual RPM provides.

```python
PROVIDE_PATTERNS: list[tuple[re.Pattern, callable]]
# 9 patterns: python3dist, pkgconfig, perl, rubygem, npm, cmake, tex, golang, mvn
```

**Examples:**

| Input | Pattern | Output |
|---|---|---|
| `python3dist(requests)` | `python(\d*)dist\((.+)\)` | `python3-requests` |
| `pkgconfig(glib-2.0)` | `pkgconfig\((.+)\)` | `glib-2.0-devel` |
| `perl(File::Path)` | `perl\((.+)\)` | `perl-File-Path` |
| `rubygem(bundler)` | `rubygem\((.+)\)` | `rubygem-bundler` |
| `npm(typescript)` | `npm\((.+)\)` | `nodejs-typescript` |
| `cmake(Qt5Core)` | `cmake\((.+)\)` | `cmake-qt5core` |
| `tex(latex)` | `tex\((.+)\)` | `texlive-latex` |
| `golang(github.com/foo/bar)` | `golang\((.+)\)` | `golang-github.com-foo-bar` |
| `mvn(org.apache:commons-lang)` | `mvn\(([^:]+):([^:]+)\)` | `commons-lang` |

---

### Classes

#### `PackageNameResolver`

Rule-based resolver with optional ML fallback.

```python
class PackageNameResolver:
    def __init__(self, ml_resolver=None): ...
```

**Parameters:**
- `ml_resolver` — optional `MLPackageResolver` instance for ML fallback

**Methods:**

##### `resolve(dep_name: str) -> str`

Resolve a dependency name to a real RPM package name.

**Pipeline:** cache -> expand macros -> virtual provide patterns -> ML fallback -> return expanded name as-is.

**Parameters:**
- `dep_name` — dependency name from spec file (e.g. `"python3dist(requests)"`)

**Returns:**
- Resolved RPM package name (e.g. `"python3-requests"`)

**Example:**
```python
resolver = PackageNameResolver()
resolver.resolve("python3dist(requests)")   # "python3-requests"
resolver.resolve("pkgconfig(glib-2.0)")     # "glib-2.0-devel"
resolver.resolve("%{python3_pkgversion}-devel")  # "3-devel"
resolver.resolve("gcc")                     # "gcc" (unchanged)
```

---

##### `expand_macros(name: str) -> str`

Expand RPM macros in a name using `SYSTEM_MACROS`.

Handles `%{macro}`, `%{?macro}` (conditional), and nested macros.

**Parameters:**
- `name` — name containing RPM macros

**Returns:**
- Name with known macros expanded

---

##### `resolve_virtual_provide(name: str) -> Optional[str]`

Try to resolve a virtual provide name using `PROVIDE_PATTERNS`.

**Parameters:**
- `name` — dependency name that may be a virtual provide

**Returns:**
- Resolved package name, or `None` if no pattern matched

---

##### `resolve_srpm_name(rpm_name: str) -> list[str]`

Map an RPM binary package name to possible SRPM names.

**Parameters:**
- `rpm_name` — RPM binary package name

**Returns:**
- List of possible SRPM names, ordered by likelihood

**Example:**
```python
resolver = PackageNameResolver()
resolver.resolve_srpm_name("python3-requests")  # ["python-requests", "python3-requests"]
resolver.resolve_srpm_name("glib2-devel")        # ["glib2", "glib2-devel"]
resolver.resolve_srpm_name("perl-File-Path")     # ["perl-File-Path"]
resolver.resolve_srpm_name("gcc")                # ["gcc"]
```

---

## ml_resolver

ML-based package name resolver using TF-IDF and K-Nearest Neighbors. **Optional** -- requires `scikit-learn` (`pip install vibebuild[ml]`).

### Classes

#### `MLPackageResolver`

ML resolver that predicts RPM package names from dependency strings.

```python
class MLPackageResolver:
    def __init__(self, model_path: Optional[str] = None): ...
```

**Parameters:**
- `model_path` — path to saved model file (joblib). Defaults to `vibebuild/data/model.joblib`

If the model file exists at the given path, it is loaded automatically on construction.

**Attributes:**
- `confidence_threshold` — minimum cosine similarity for a prediction (default: `0.3`)

**Methods:**

##### `is_available() -> bool`

Check if the resolver is ready to make predictions.

**Returns:**
- `True` if scikit-learn is installed AND a model has been loaded

---

##### `train(data: list[dict]) -> None`

Train the model on provide-to-package mapping data.

**Parameters:**
- `data` — list of dicts with keys `"provide"`, `"rpm_name"`, `"srpm_name"`

**Raises:**
- `RuntimeError` — if scikit-learn is not installed
- `ValueError` — if data is empty

**Example:**
```python
resolver = MLPackageResolver()
resolver.train([
    {"provide": "python3dist(requests)", "rpm_name": "python3-requests", "srpm_name": "python-requests"},
    {"provide": "pkgconfig(glib-2.0)", "rpm_name": "glib2-devel", "srpm_name": "glib2"},
])
```

---

##### `predict(dep_name: str) -> Optional[dict]`

Predict the RPM package name for a dependency string.

**Parameters:**
- `dep_name` — dependency name (e.g. `"python3dist(requests)"`)

**Returns:**
- Dict `{"rpm_name": ..., "srpm_name": ...}` or `None` if confidence is too low

---

##### `save(path: str) -> None`

Save the trained model to disk (joblib format).

##### `load(path: str) -> None`

Load a trained model from disk.

**Raises:**
- `FileNotFoundError` — if model file does not exist

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
        koji_tag: str = "fedora-build",
        name_resolver: Optional[PackageNameResolver] = None,
    ): ...
```

**Parameters:**
- `koji_client` — Koji client instance (default: creates new)
- `koji_tag` — Koji build tag to check packages against
- `name_resolver` — optional `PackageNameResolver` for normalizing dependency names before Koji lookup

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
        fedora_release: str = "rawhide",
        no_ssl_verify: bool = False,
        name_resolver: Optional[PackageNameResolver] = None,
    ): ...
```

**Parameters:**
- `download_dir` — directory for downloaded SRPMs
- `sources` — list of SRPM sources
- `fedora_release` — Fedora release version
- `no_ssl_verify` — disable SSL verification
- `name_resolver` — optional `PackageNameResolver` for SRPM name mapping (e.g. `python3-requests` -> `python-requests`)

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
        no_ssl_verify: bool = False,
        no_name_resolution: bool = False,
        no_ml: bool = False,
        ml_model_path: Optional[str] = None,
    ): ...
```

**Parameters:**
- `no_name_resolution` — disable all package name normalization (macros, virtual provides, ML)
- `no_ml` — disable only ML-based resolution (keep rule-based)
- `ml_model_path` — custom path to ML model file (default: built-in `vibebuild/data/model.joblib`)

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
├── KojiConnectionError           # Koji connection error
└── NameResolutionError           # Package name resolution error
```

### Usage

```python
from vibebuild.exceptions import (
    VibeBuildError,
    InvalidSRPMError,
    CircularDependencyError,
    NameResolutionError,
)

try:
    result = builder.build_with_deps("package.src.rpm")
except CircularDependencyError as e:
    print(f"Circular dependency: {e}")
except NameResolutionError as e:
    print(f"Name resolution failed: {e}")
except VibeBuildError as e:
    print(f"Build error: {e}")
```
