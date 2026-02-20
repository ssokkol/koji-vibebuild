# VibeBuild

**Koji extension for automatic dependency resolution and building**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

VibeBuild extends Koji functionality by adding automatic dependency resolution. When you build a package, VibeBuild automatically finds missing BuildRequires, downloads their SRPMs from Fedora, and builds the entire dependency chain in the correct order.

## Features

- **Automatic dependency analysis** — parsing SRPM/spec files to extract BuildRequires
- **Smart package name resolution** — automatic conversion of virtual provides (`python3dist(requests)`, `pkgconfig(glib-2.0)`, `perl(File::Path)`) and RPM macros (`%{python3_pkgversion}`) to real package names
- **ML-based name resolution** — optional scikit-learn model (TF-IDF + KNN) as fallback when rule-based patterns don't match
- **SRPM downloading** — automatic download of missing packages from Fedora Koji, with smart SRPM name mapping (e.g. `python3-requests` -> `python-requests`)
- **DAG construction** — determining build order based on dependencies
- **Build orchestration** — sequential building with repository regeneration waiting
- **CLI interface** — convenient command line tool with flexible options

## Quick Start

### Installation

From PyPI (when published):

```bash
pip install vibebuild
pip install vibebuild[ml]   # optional: ML-based name resolution
```

From source (recommended for development and verification):

```bash
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild
pip install -e .
pip install -e ".[ml]"     # optional: ML dependencies
pip install -e ".[dev]"    # for tests: pytest, black, etc.
pip install -e ".[dev,ml]" # both dev and ML
```

### Usage

Basic form: `vibebuild [OPTIONS] TARGET SRPM`. SRPM can be a path to a `.src.rpm` file or a **package name** (e.g. `python3`); if it is a name, the SRPM is downloaded from Koji and then built.

```bash
# One command: download SRPM by name and build (with dependency resolution)
vibebuild fedora-43 python3
vibebuild fedora-43 python-requests

# Build from local SRPM file
vibebuild fedora-target my-package-1.0-1.fc40.src.rpm

# Scratch build (not tagged)
vibebuild --scratch fedora-target my-package.src.rpm

# Build without resolving dependencies (single package only)
vibebuild --no-deps fedora-target my-package.src.rpm

# Analyze dependencies without building (one argument: path to SRPM)
vibebuild --analyze-only my-package.src.rpm

# Download SRPM from Fedora by package name (requires koji CLI)
vibebuild --download-only python-requests

# Dry run — show build order and what would be built
vibebuild --dry-run fedora-target my-package.src.rpm

# Name resolution options
vibebuild --no-ml fedora-target my-package.src.rpm              # rules only
vibebuild --no-name-resolution fedora-target my-package.src.rpm # raw names
vibebuild --ml-model /path/to/model.joblib fedora-target my-package.src.rpm
```

For a step-by-step public demo (download, analyze, dry-run, build), see [DEMO.md](DEMO.md).

### Verification

After installation you can confirm everything works:

```bash
vibebuild --version
vibebuild --help          # short list of common options
vibebuild --help-all      # full list of all options
```

If you installed with `[dev]`, run tests from the project root:

```bash
pytest
```

To verify dependency resolution on a real package (requires `koji` CLI and network access to Fedora Koji):

```bash
vibebuild --download-only python-requests
vibebuild --analyze-only python-requests-*.src.rpm   # use the downloaded file
vibebuild --dry-run fedora-43 python-requests         # package name: download then show plan
vibebuild --dry-run fedora-43 python-requests-*.src.rpm
```

Without `koji`, use any existing `.src.rpm` you have for `--analyze-only` and `--dry-run`. See [TESTING.md](docs/TESTING.md) for running the test suite.

### Using with your own Koji server

If you use Koji already, `vibebuild` reads `~/.koji/config` (and `/etc/koji.conf`) for `server`, `weburl`, `cert`, and `serverca`, so you often only need to pass `--server` if overriding. For all options run `vibebuild --help-all`.

```bash
vibebuild --server https://koji.example.com/kojihub my-target my-package.src.rpm
# or with explicit certs:
vibebuild --server https://koji.example.com/kojihub --cert ~/.koji/client.pem \
  --serverca ~/.koji/serverca.crt --build-tag my-build my-target my-package.src.rpm
```

## Koji Deployment

The repository includes an Ansible playbook for automatic Koji deployment on Fedora:

```bash
cd ansible

# Configure inventory (set YOUR_VPS_IP and ansible_user)
vim inventory/hosts.ini

# Configure variables (FQDN, passwords, etc.)
vim group_vars/all.yml

# Run playbook
ansible-playbook -i inventory/hosts.ini playbook.yml
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.

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
│ Name Resolver   │────▶│  Expand macros  │
│ (rules + ML)    │     │  Resolve names  │
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

1. **Analyzer** — extracts BuildRequires from SRPM/spec file, expands RPM macros
2. **Name Resolver** — converts virtual provides and macro-based names to real RPM package names (rule-based + optional ML fallback)
3. **Resolver** — checks which dependencies are missing in Koji and builds dependency graph
4. **Fetcher** — downloads SRPMs for missing packages from Fedora, with smart SRPM name mapping
5. **Builder** — builds packages in correct order, waiting for repository regeneration between builds

## ML Model Training (optional)

VibeBuild includes scripts to train a custom ML model for package name resolution:

```bash
# 1. Collect training data from Fedora repositories
python scripts/collect_training_data.py --output data/training_data.json

# 2. Train the model (alias data from vibebuild/data/alias_training.json is merged automatically)
python scripts/train_model.py --input data/training_data.json --output vibebuild/data/model.joblib
```

The model uses TF-IDF character n-grams with K-Nearest Neighbors to predict real package names from virtual dependency strings. Training automatically merges aliases from `vibebuild/data/alias_training.json` (e.g. `python3` → `python3.12`), so that commands like `vibebuild --download-only python3` work when the model is installed. Use `--ml-model` to point to a custom model. See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.

## Requirements

- **Python** 3.9+
- **koji** CLI — required for `--download-only` (downloading SRPMs from Fedora Koji) and for building. Without it, those features are unavailable. Install: `sudo dnf install koji` (Fedora) or equivalent on your distribution.
- **rpm-build**, **rpm2cpio** (for unpacking and building SRPMs; on Fedora: `dnf install rpm-build`)
- Access to a Koji server (e.g. Fedora Koji for download; your own for building)

**Optional (ML-based name resolution):** `scikit-learn >= 1.3`, `joblib >= 1.3` — install with `pip install vibebuild[ml]`.

## Documentation

- [DEMO.md](DEMO.md) — step-by-step public demo (one-command build, download, analyze, dry-run)
- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — full project description with diagrams
- [VPS_SETUP.md](docs/VPS_SETUP.md) — VPS server creation and setup guide
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [API.md](docs/API.md) — API documentation
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — deployment guide
- [TESTING.md](docs/TESTING.md) — testing guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute

## License

MIT License. See [LICENSE](LICENSE) for details.
