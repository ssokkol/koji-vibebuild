# VibeBuild Roadmap

Development plan for the VibeBuild project.

## Current Version: 0.1.0

---

## Phase 1: Infrastructure ✅

**Status:** Completed

### Tasks

- [x] Ansible playbook for deploying Koji on Fedora VPS
  - [x] PostgreSQL setup
  - [x] Koji Hub configuration
  - [x] Koji Builder configuration
  - [x] Koji Web UI
  - [x] SSL certificates
  - [x] Tag and target initialization
  - [x] External repositories

### Result

Fully automated Koji server deployment with a single command:
```bash
ansible-playbook -i inventory/hosts.ini playbook.yml
```

---

## Phase 2: Core Modules ✅

**Status:** Completed

### Tasks

- [x] `analyzer.py` — SRPM and spec file parsing
  - [x] BuildRequires extraction
  - [x] Package metadata parsing
  - [x] RPM macro support

- [x] `resolver.py` — dependency resolution
  - [x] Koji API integration
  - [x] Dependency graph construction (DAG)
  - [x] Topological sorting
  - [x] Circular dependency detection

- [x] `fetcher.py` — SRPM downloading
  - [x] Downloading from Fedora Koji
  - [x] Downloading from src.fedoraproject.org
  - [x] Downloaded file caching

- [x] `builder.py` — build orchestration
  - [x] Submitting builds to Koji
  - [x] Waiting for repository regeneration
  - [x] Build chains

---

## Phase 3: CLI and Integration ✅

**Status:** Completed

### Tasks

- [x] CLI interface (`cli.py`)
  - [x] Main command `vibebuild TARGET SRPM`
  - [x] Analysis mode `--analyze-only`
  - [x] Download mode `--download-only`
  - [x] Dry run `--dry-run`
  - [x] Koji server options

- [x] Package setup
  - [x] `setup.py` and `pyproject.toml`
  - [x] Entry point for CLI
  - [x] Dependencies

---

## Phase 4: Documentation ✅

**Status:** Completed

### Tasks

- [x] README.md with Quick Start
- [x] CONTRIBUTING.md for developers
- [x] docs/ARCHITECTURE.md
- [x] docs/API.md
- [x] docs/ROADMAP.md
- [x] docs/DEPLOYMENT.md
- [x] docs/TESTING.md

---

## Phase 5: Testing 🔄

**Status:** Planned

### Tasks

- [ ] Unit tests for all modules
  - [ ] test_analyzer.py
  - [ ] test_resolver.py
  - [ ] test_fetcher.py
  - [ ] test_builder.py

- [ ] Integration tests
  - [ ] Mock Koji server
  - [ ] End-to-end tests

- [ ] CI/CD
  - [ ] GitHub Actions workflow
  - [ ] Automatic tests on PR
  - [ ] Coverage reporting

### Metrics

- Target coverage: >80%
- All public functions covered by tests

---

## Phase 6: Improvements 📋

**Status:** Planned

### 6.1 Parallel Building

- [ ] Parallel building of packages at the same DAG level
- [ ] max_parallel_builds configuration
- [ ] Progress bar for multiple builds

### 6.2 Extended Caching

- [ ] Persistent dependency cache
- [ ] Spec file analysis result cache
- [ ] Time-based cache invalidation

### 6.3 Improved Error Handling

- [ ] Retry with exponential backoff
- [ ] Continue after error (--continue-on-error)
- [ ] Detailed error reports

### 6.4 Additional SRPM Sources

- [ ] CentOS Stream
- [ ] EPEL
- [ ] Custom Git repositories
- [ ] Local SRPM directories

---

## Phase 7: Web UI 📋

**Status:** Planned (v0.3.0)

### Tasks

- [ ] REST API for VibeBuild
- [ ] Web dashboard
  - [ ] Current build status
  - [ ] Build history
  - [ ] Dependency graph visualization
- [ ] Integration with Koji Web

---

## Future Plans 🔮

### v1.0.0

- [ ] Stable API
- [ ] Full test coverage
- [ ] Production-ready documentation
- [ ] PyPI publication

### After v1.0.0

- [ ] Plugin system
- [ ] Support for other build systems (OBS, Copr)
- [ ] Integration with CI/CD systems (GitLab CI, Jenkins)
- [ ] Kubernetes operator for builder scaling

---

## Changelog

### v0.1.0 (current)

**Added:**
- Basic VibeBuild functionality
- Ansible playbook for Koji
- CLI interface
- Documentation

---

## How to Contribute

See [CONTRIBUTING.md](../CONTRIBUTING.md) for information on how to help the project.

Priority areas for contributors:
1. Unit tests
2. Usage example documentation
3. Testing on various distributions
