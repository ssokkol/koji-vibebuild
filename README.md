# VibeBuild

**Koji extension for automatic dependency resolution and building**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

VibeBuild extends Koji functionality by adding automatic dependency resolution. When you build a package, VibeBuild automatically finds missing BuildRequires, downloads their SRPMs from Fedora, and builds the entire dependency chain in the correct order.

## Features

- **Automatic dependency analysis** — parsing SRPM/spec files to extract BuildRequires
- **SRPM downloading** — automatic download of missing packages from Fedora Koji
- **DAG construction** — determining build order based on dependencies
- **Build orchestration** — sequential building with repository regeneration waiting
- **CLI interface** — convenient command line tool

## Quick Start

### Installation

```bash
pip install vibebuild
```

Or from source:

```bash
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild
pip install -e .
```

### Usage

```bash
# Build package with automatic dependency resolution
vibebuild fedora-target my-package-1.0-1.fc40.src.rpm

# Scratch build (not tagged)
vibebuild --scratch fedora-target my-package.src.rpm

# Analyze dependencies without building
vibebuild --analyze-only my-package.src.rpm

# Download SRPM from Fedora
vibebuild --download-only python-requests

# Dry run — show what would be built
vibebuild --dry-run fedora-target my-package.src.rpm
```

### Using with your own Koji server

```bash
vibebuild \
  --server https://koji.example.com/kojihub \
  --web-url https://koji.example.com/koji \
  --cert ~/.koji/client.pem \
  --serverca ~/.koji/serverca.crt \
  --build-tag my-build \
  my-target my-package.src.rpm
```

## Koji Deployment

The repository includes an Ansible playbook for automatic Koji deployment on Fedora:

```bash
cd ansible

# Configure inventory
vim inventory/hosts.ini

# Configure variables
vim group_vars/all.yml

# Run playbook
ansible-playbook -i inventory/hosts.ini playbook.yml
```

## How It Works

```
┌─────────────────┐
│  vibebuild CLI  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Analyzer     │────▶│  Parse SRPM     │
│                 │     │  Extract deps   │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Resolver     │────▶│  Check Koji     │
│                 │     │  Build DAG      │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Fetcher      │────▶│  Download SRPM  │
│                 │     │  from Fedora    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Builder      │────▶│  koji build     │
│                 │     │  wait-repo      │
└─────────────────┘     └─────────────────┘
```

1. **Analyzer** — extracts BuildRequires from SRPM/spec file
2. **Resolver** — checks which dependencies are missing in Koji and builds dependency graph
3. **Fetcher** — downloads SRPMs for missing packages from Fedora
4. **Builder** — builds packages in correct order, waiting for repository regeneration between builds

## Requirements

- Python 3.9+
- `koji` CLI (installed on system)
- `rpm-build`, `rpm2cpio` (for working with SRPMs)
- Access to Koji server

## Documentation

- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — full project description with diagrams
- [VPS_SETUP.md](docs/VPS_SETUP.md) — VPS server creation and setup guide
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [API.md](docs/API.md) — API documentation
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — deployment guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute

## License

MIT License. See [LICENSE](LICENSE) for details.
