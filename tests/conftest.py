"""
Pytest configuration and fixtures for VibeBuild tests.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_spec_content():
    """Sample spec file content for testing."""
    return """
Name:           test-package
Version:        1.0
Release:        1%{?dist}
Summary:        Test package for VibeBuild

License:        MIT
URL:            https://example.com/test-package
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  gcc
BuildRequires:  make >= 4.0

%description
A test package for VibeBuild unit tests.

%prep
%autosetup

%build
%make_build

%install
%make_install

%files
%license LICENSE
%doc README.md
"""


@pytest.fixture
def sample_spec(tmp_path, sample_spec_content):
    """Create a temporary spec file."""
    spec_path = tmp_path / "test-package.spec"
    spec_path.write_text(sample_spec_content)
    return spec_path


@pytest.fixture
def mock_koji_client():
    """Mock KojiClient for testing without real Koji."""
    client = Mock()
    client.server = "https://test.koji.example.com/kojihub"
    client.list_packages.return_value = ["python3", "gcc", "make", "glibc"]
    client.package_exists.return_value = True
    client.list_tagged_builds.return_value = {
        "python3": "python3-3.11.0-1.fc40",
        "gcc": "gcc-13.0-1.fc40",
    }
    return client


@pytest.fixture
def mock_subprocess_run(mocker):
    """Mock subprocess.run for testing."""
    mock = mocker.patch("subprocess.run")
    mock.return_value.returncode = 0
    mock.return_value.stdout = ""
    mock.return_value.stderr = ""
    return mock
