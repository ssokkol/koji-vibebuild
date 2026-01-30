# VibeBuild Architecture

## System Overview

VibeBuild is an extension for Koji that automates dependency resolution when building RPM packages. The system consists of two main parts:

1. **VibeBuild CLI** — Python application for dependency analysis and build orchestration
2. **Koji Infrastructure** — RPM package build server

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User                                     │
└─────────────────────────────────┬───────────────────────────────┘
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

## VibeBuild Components

### 1. Analyzer (`analyzer.py`)

**Responsibility:** Parsing SRPM and spec files, extracting metadata.

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

**Responsibility:** Checking dependency availability in Koji, building dependency graph.

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

**DAG Construction Algorithm:**

```
1. Start with root package
2. For each package:
   a. If package exists in Koji tag → mark as available
   b. Otherwise:
      - Extract BuildRequires
      - Find missing dependencies
      - Recursively process each dependency
3. Build dependency graph
4. Perform topological sort
```

**Data Structure:**

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

**Responsibility:** Downloading SRPMs from external sources.

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

**SRPM Sources (in priority order):**

1. **Fedora Koji** (`koji.fedoraproject.org`)
   - Method: `koji download-build --type=src`
   - Advantage: ready-made SRPMs

2. **src.fedoraproject.org**
   - Method: download spec + sources, build SRPM locally
   - Used as fallback

### 4. Builder (`builder.py`)

**Responsibility:** Build orchestration in Koji.

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

**build_with_deps Algorithm:**

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

**Responsibility:** User command interface.

```
Commands:
  vibebuild TARGET SRPM          # Build with deps
  vibebuild --analyze-only SRPM  # Only analyze
  vibebuild --download-only PKG  # Only download
  vibebuild --dry-run TARGET SRPM # Show plan
```

## Koji Infrastructure

### Components

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

### Tags and Targets

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

## Error Handling

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

## Performance

### Caching

- **Available packages cache:** package list in Koji tag is cached
- **Downloaded SRPMs cache:** downloaded SRPMs are saved for reuse
- **Dependency graph cache:** dependency graph is built once

### Parallelism

- Packages at the same level of the dependency graph can be built in parallel
- SRPM downloading can be performed in parallel with analysis

## Security

### Authentication

- SSL client certificates for Koji
- CA verification for HTTPS connections

### Build Isolation

- All builds are executed in mock chroot
- Isolated network environment in builder
