# Testing Guide

Guide for testing VibeBuild.

## Table of Contents

- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Writing Tests](#writing-tests)
- [Mocking](#mocking)
- [Coverage](#coverage)

---

## Running Tests

### Installing Dependencies

```bash
pip install -e ".[dev]"
```

### Running All Tests

```bash
pytest
```

### Running with Verbose Output

```bash
pytest -v
```

### Running Specific File

```bash
pytest tests/test_analyzer.py
```

### Running Specific Test

```bash
pytest tests/test_analyzer.py::test_get_build_requires
```

### Running Name Resolution Tests

```bash
# All name resolver tests (49 tests)
pytest tests/test_name_resolver.py -v

# All ML resolver tests (26 tests, requires scikit-learn)
pytest tests/test_ml_resolver.py -v

# Both together
pytest tests/test_name_resolver.py tests/test_ml_resolver.py -v
```

### Running by Marker

```bash
# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration
```

### Manual / E2E verification (optional)

With `koji` CLI and network access to Fedora Koji you can verify the full flow:

```bash
vibebuild --version
vibebuild --help
vibebuild --download-only python-requests
vibebuild --dry-run fedora-43 python-requests   # package name: download then show build plan
```

For a full public-demo script (one-command build by package name, analyze, dry-run, build), see [DEMO.md](../DEMO.md).

---

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── fixtures/                # Test data
│   ├── test-package.spec
│   └── test-package.src.rpm
├── test_analyzer.py         # Analyzer tests
├── test_resolver.py         # Resolver tests
├── test_fetcher.py          # Fetcher tests
├── test_builder.py          # Builder tests
├── test_cli.py              # CLI tests
├── test_name_resolver.py    # Name resolver tests (49 tests, 9 classes)
├── test_ml_resolver.py      # ML resolver tests (26 tests, 7 classes)
└── integration/             # Integration tests
    └── test_e2e.py
```

### test_name_resolver.py (49 tests)

Tests for rule-based `PackageNameResolver`:

| Test Class | Count | What's tested |
|---|---|---|
| `TestPackageNameResolverVirtualProvides` | 11 | All 9 provide patterns (python3dist, pkgconfig, perl, rubygem, npm, golang, tex, mvn, cmake) plus edge cases |
| `TestPackageNameResolverMacros` | 6 | Macro expansion: `%{python3_pkgversion}`, conditional `%{?...}`, unknown macros, multiple macros |
| `TestPackageNameResolverPlainNames` | 3 | Passthrough for plain names like `gcc`, empty strings |
| `TestPackageNameResolverSRPMNames` | 9 | SRPM name mapping: python3-X, python2-X, -devel, -libs, perl-, rubygem-, nodejs-, golang- |
| `TestPackageNameResolverCaching` | 3 | In-memory cache behavior |
| `TestPackageNameResolverMLFallback` | 7 | ML integration: called for unresolved provides, not called when rules match, exception handling, graceful degradation |
| `TestSystemMacros` | 5 | Validate SYSTEM_MACROS entries |
| `TestProvidePatterns` | 2 | Validate PROVIDE_PATTERNS structure |
| `TestResolveVirtualProvide` | 3 | Direct `resolve_virtual_provide()` method |

### test_ml_resolver.py (26 tests)

Tests for ML-based `MLPackageResolver`:

| Test Class | Count | What's tested |
|---|---|---|
| `TestMLPackageResolverInstantiation` | 2 | Constructor with/without model path |
| `TestMLPackageResolverTrain` | 3 | Training on sample data, empty data error, vocabulary check |
| `TestMLPackageResolverPredict` | 6 | Exact matches (python3dist, pkgconfig, perl), garbage input returns None, unavailable model |
| `TestMLPackageResolverSaveLoad` | 5 | Save/load roundtrip, directory creation, error handling |
| `TestMLPackageResolverIsAvailable` | 3 | Availability after training, without model, after load |
| `TestMLPackageResolverCache` | 5 | Prediction caching, disk persistence, corrupt file handling |
| `TestMLPackageResolverWithoutSklearn` | 2 | Mocked `HAS_SKLEARN=False`: train error, availability check |

---

## Writing Tests

### Style

Use AAA (Arrange-Act-Assert) pattern:

```python
def test_get_build_requires_extracts_packages():
    srpm_path = "tests/fixtures/test-package.src.rpm"

    result = get_build_requires(srpm_path)

    assert isinstance(result, list)
    assert "python3-devel" in result
```

### Naming Convention

```python
def test_<what>_<condition>_<expected>():
    # test_get_build_requires_with_valid_srpm_returns_list
    # test_analyze_spec_with_missing_name_raises_error
    pass
```

### Markers

```python
import pytest

@pytest.mark.unit
def test_unit_example():
    pass

@pytest.mark.integration
def test_integration_example():
    pass

@pytest.mark.slow
def test_slow_example():
    pass
```

---

## Fixtures

### conftest.py

```python
import pytest
from pathlib import Path

@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_spec(fixtures_dir):
    return fixtures_dir / "test-package.spec"

@pytest.fixture
def sample_srpm(fixtures_dir):
    return fixtures_dir / "test-package.src.rpm"

@pytest.fixture
def mock_koji_client(mocker):
    """Mock KojiClient for tests without real Koji."""
    client = mocker.Mock()
    client.list_packages.return_value = ["python3", "gcc", "make"]
    client.package_exists.return_value = True
    return client
```

### Using Fixtures

```python
def test_analyzer_with_fixture(sample_spec):
    analyzer = SpecAnalyzer()

    result = analyzer.analyze_spec(str(sample_spec))

    assert result.name == "test-package"
```

---

## Mocking

### Mock subprocess

```python
def test_koji_build_command(mocker):
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Created task: 12345"

    builder = KojiBuilder()
    task = builder.build_package("test.src.rpm")

    assert task.task_id == 12345
    mock_run.assert_called_once()
```

### Mock requests

```python
def test_download_srpm_from_koji(mocker):
    mocker.patch("subprocess.run").return_value.returncode = 0

    fetcher = SRPMFetcher(download_dir="/tmp/test")

    # ... test logic
```

### Mock ML resolver

```python
def test_resolve_with_ml_fallback(mocker):
    """Test that ML resolver is called for unresolved virtual provides."""
    mock_ml = mocker.Mock()
    mock_ml.predict.return_value = "custom-package"

    resolver = PackageNameResolver(ml_resolver=mock_ml)
    result = resolver.resolve("unknown_provider(something)")

    mock_ml.predict.assert_called_once_with("unknown_provider(something)")
    assert result == "custom-package"


def test_resolve_ml_not_called_when_rules_match(mocker):
    """Test that ML is skipped when rule-based resolution succeeds."""
    mock_ml = mocker.Mock()

    resolver = PackageNameResolver(ml_resolver=mock_ml)
    result = resolver.resolve("python3dist(requests)")

    mock_ml.predict.assert_not_called()
    assert result == "python3-requests"
```

### Mock filesystem

```python
def test_analyze_spec_file_not_found(tmp_path):
    analyzer = SpecAnalyzer()

    with pytest.raises(FileNotFoundError):
        analyzer.analyze_spec(str(tmp_path / "nonexistent.spec"))
```

---

## Test Examples

### test_analyzer.py

```python
import pytest
from vibebuild.analyzer import SpecAnalyzer, get_build_requires
from vibebuild.exceptions import InvalidSRPMError, SpecParseError


class TestSpecAnalyzer:
    def test_analyze_spec_extracts_name(self, sample_spec):
        analyzer = SpecAnalyzer()

        result = analyzer.analyze_spec(str(sample_spec))

        assert result.name == "test-package"

    def test_analyze_spec_extracts_version(self, sample_spec):
        analyzer = SpecAnalyzer()

        result = analyzer.analyze_spec(str(sample_spec))

        assert result.version == "1.0"

    def test_analyze_spec_extracts_build_requires(self, sample_spec):
        analyzer = SpecAnalyzer()

        result = analyzer.analyze_spec(str(sample_spec))

        assert len(result.build_requires) > 0

    def test_analyze_spec_raises_on_missing_file(self):
        analyzer = SpecAnalyzer()

        with pytest.raises(FileNotFoundError):
            analyzer.analyze_spec("/nonexistent/path.spec")

    def test_analyze_spec_raises_on_invalid_spec(self, tmp_path):
        invalid_spec = tmp_path / "invalid.spec"
        invalid_spec.write_text("invalid content")
        analyzer = SpecAnalyzer()

        with pytest.raises(SpecParseError):
            analyzer.analyze_spec(str(invalid_spec))


class TestGetBuildRequires:
    def test_returns_list(self, sample_srpm):
        result = get_build_requires(str(sample_srpm))

        assert isinstance(result, list)

    def test_raises_on_invalid_srpm(self, tmp_path):
        invalid = tmp_path / "not-an-srpm.txt"
        invalid.write_text("not an srpm")

        with pytest.raises(InvalidSRPMError):
            get_build_requires(str(invalid))
```

### test_resolver.py

```python
import pytest
from vibebuild.resolver import DependencyResolver, KojiClient
from vibebuild.exceptions import CircularDependencyError


class TestDependencyResolver:
    def test_find_missing_deps_returns_missing(self, mock_koji_client):
        mock_koji_client.package_exists.side_effect = lambda p, t: p != "missing-pkg"
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.find_missing_deps(["existing-pkg", "missing-pkg"])

        assert "missing-pkg" in result
        assert "existing-pkg" not in result

    def test_topological_sort_detects_cycle(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "a": Mock(dependencies=["b"], is_available=False),
            "b": Mock(dependencies=["a"], is_available=False),
        }

        with pytest.raises(CircularDependencyError):
            resolver.topological_sort()
```

---

## Coverage

### Running with Coverage

```bash
pytest --cov=vibebuild --cov-report=term-missing
```

### HTML Report

```bash
pytest --cov=vibebuild --cov-report=html
open htmlcov/index.html
```

### Minimum Coverage

```bash
pytest --cov=vibebuild --cov-fail-under=80
```

### Configuration in pyproject.toml

```toml
[tool.coverage.run]
source = ["vibebuild"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

---

## CI/CD

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pip install -e ".[dev]"

    - name: Run tests
      run: |
        pytest --cov=vibebuild --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

---

## Integration Tests

### Requirements

Integration tests require:
- Access to test Koji server
- Test SRPM files

### Example

```python
# tests/integration/test_e2e.py

import pytest

@pytest.mark.integration
@pytest.mark.slow
class TestEndToEnd:
    @pytest.fixture
    def koji_server(self):
        return "https://test-koji.example.com/kojihub"

    def test_full_build_workflow(self, koji_server, sample_srpm):
        from vibebuild.builder import KojiBuilder

        builder = KojiBuilder(
            koji_server=koji_server,
            scratch=True,  # Scratch build for tests
        )

        result = builder.build_with_deps(str(sample_srpm))

        assert result.success
```

### Running Integration Tests

```bash
# Only unit tests (default)
pytest -m "not integration"

# Including integration tests
pytest -m "integration"

# All tests
pytest
```
