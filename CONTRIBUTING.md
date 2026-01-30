# Contributing to VibeBuild

Thank you for your interest in VibeBuild! This document describes the process of contributing to the project.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Working with Git](#working-with-git)
- [Pull Request](#pull-request)
- [Testing](#testing)
- [Documentation](#documentation)

## Development Environment Setup

### Requirements

- Python 3.9+
- Git
- `koji` CLI (for integration tests)
- `rpm-build`, `rpm2cpio` (for working with SRPMs)

### Installation

1. Fork the repository and clone it:

```bash
git clone https://github.com/YOUR_USERNAME/vibebuild.git
cd vibebuild
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

3. Install development dependencies:

```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:

```bash
pre-commit install
```

### Verify Installation

```bash
# Run tests
pytest

# Check code style
black --check vibebuild
isort --check vibebuild
flake8 vibebuild
mypy vibebuild
```

## Project Structure

```
vibebuild/
├── vibebuild/              # Main package
│   ├── __init__.py         # Exports and version
│   ├── analyzer.py         # SRPM/spec file parsing
│   ├── resolver.py         # Dependency resolution, DAG
│   ├── fetcher.py          # SRPM downloading from Fedora
│   ├── builder.py          # Koji build orchestration
│   ├── cli.py              # CLI interface
│   └── exceptions.py       # Custom exceptions
├── ansible/                # Ansible playbook for Koji
│   ├── playbook.yml
│   ├── inventory/
│   ├── group_vars/
│   └── roles/
├── tests/                  # Tests
│   ├── test_analyzer.py
│   ├── test_resolver.py
│   └── ...
├── docs/                   # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── ...
├── setup.py
├── pyproject.toml
└── requirements*.txt
```

## Code Style

### Python

We use:
- **Black** for code formatting (line-length: 100)
- **isort** for import sorting (profile: black)
- **flake8** for linting
- **mypy** for type checking

Configuration is in `pyproject.toml`.

```bash
# Auto-format
black vibebuild tests
isort vibebuild tests

# Check
black --check vibebuild tests
isort --check vibebuild tests
flake8 vibebuild tests
mypy vibebuild
```

### Type Hints

Use type hints for all public functions:

```python
def get_build_requires(srpm_path: str) -> list[str]:
    """Docstring..."""
    ...
```

### Docstrings

Use Google style docstrings:

```python
def build_package(srpm_path: str, wait: bool = True) -> BuildTask:
    """
    Submit a single package build to Koji.

    Args:
        srpm_path: Path to SRPM file
        wait: Whether to wait for build to complete

    Returns:
        BuildTask with result information

    Raises:
        FileNotFoundError: If SRPM doesn't exist
        KojiBuildError: If build fails
    """
```

## Working with Git

### Branch Structure

- `main` — stable version
- `develop` — current development
- `feature/*` — new features
- `bugfix/*` — bug fixes
- `release/*` — release preparation

### Creating a Branch

```bash
# New feature
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# Bug fix
git checkout -b bugfix/issue-123
```

### Commit Messages

Format: `<type>(<scope>): <description>`

Types:
- `feat` — new functionality
- `fix` — bug fix
- `docs` — documentation changes
- `style` — formatting, no logic changes
- `refactor` — refactoring without functionality changes
- `test` — adding/modifying tests
- `chore` — dependency updates, configs

Examples:

```
feat(resolver): add circular dependency detection
fix(fetcher): handle network timeout errors
docs(readme): add installation instructions
test(analyzer): add tests for spec parsing
```

## Pull Request

### Checklist

Before creating a PR, make sure:

- [ ] Code follows code style (black, isort, flake8)
- [ ] Tests are added/updated
- [ ] All tests pass (`pytest`)
- [ ] Documentation is updated (if needed)
- [ ] Commit messages follow the format
- [ ] PR has a clear description

### Process

1. Push branch to your fork
2. Create Pull Request to `develop`
3. Fill out PR template
4. Wait for code review
5. Address requested changes
6. After approval — squash & merge

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## How was it tested?
Description of testing

## Checklist
- [ ] Tests pass
- [ ] Code style OK
- [ ] Documentation updated
```

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=vibebuild --cov-report=html

# Specific file
pytest tests/test_analyzer.py

# Specific test
pytest tests/test_analyzer.py::test_parse_spec
```

### Test Structure

Use AAA pattern (Arrange-Act-Assert):

```python
def test_get_build_requires_returns_list():
    srpm_path = "fixtures/test-package.src.rpm"

    result = get_build_requires(srpm_path)

    assert isinstance(result, list)
    assert "python3-devel" in result
```

### Fixtures

Test data in `tests/fixtures/`:

```
tests/
├── fixtures/
│   ├── test-package.spec
│   └── test-package.src.rpm
├── conftest.py
└── test_*.py
```

## Documentation

### Updating Documentation

When changing public API, update:

1. Docstrings in code
2. `docs/API.md`
3. `README.md` (if it affects usage)

### Building Documentation

```bash
# Check docstrings
pydocstyle vibebuild
```

## Questions?

- Create an Issue with your question
- Write in discussions

Thank you for your contribution!
