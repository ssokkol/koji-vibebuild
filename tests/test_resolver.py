"""Tests for vibebuild.resolver module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from vibebuild.resolver import (
    DependencyNode,
    KojiClient,
    DependencyResolver,
)
from vibebuild.analyzer import BuildRequirement
from vibebuild.exceptions import (
    CircularDependencyError,
    KojiConnectionError,
)


class TestDependencyNode:
    def test_default_values(self):
        node = DependencyNode(name="test-pkg")

        assert node.name == "test-pkg"
        assert node.srpm_path is None
        assert node.package_info is None
        assert node.dependencies == []
        assert node.is_available is False
        assert node.build_order == -1

    def test_with_all_values(self):
        node = DependencyNode(
            name="test-pkg",
            srpm_path="/path/to/test.src.rpm",
            dependencies=["dep1", "dep2"],
            is_available=True,
            build_order=5
        )

        assert node.name == "test-pkg"
        assert node.srpm_path == "/path/to/test.src.rpm"
        assert node.dependencies == ["dep1", "dep2"]
        assert node.is_available is True
        assert node.build_order == 5


class TestKojiClient:
    def test_default_server(self):
        client = KojiClient()

        assert client.server == "https://koji.fedoraproject.org/kojihub"
        assert client.web_url == "https://koji.fedoraproject.org/koji"

    def test_custom_server(self):
        client = KojiClient(
            server="https://custom.koji.example.com/kojihub",
            web_url="https://custom.koji.example.com/koji",
            cert="/path/to/cert.pem",
            serverca="/path/to/ca.crt"
        )

        assert client.server == "https://custom.koji.example.com/kojihub"
        assert client.cert == "/path/to/cert.pem"
        assert client.serverca == "/path/to/ca.crt"

    def test_list_packages_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "python3\ngcc\nmake\n"
        mock_subprocess_run.return_value.stderr = ""
        client = KojiClient()

        result = client.list_packages("fedora-build")

        assert "python3" in result
        assert "gcc" in result
        assert "make" in result

    def test_list_packages_failure_raises(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stdout = ""
        mock_subprocess_run.return_value.stderr = "Connection refused"
        client = KojiClient()

        with pytest.raises(KojiConnectionError, match="Failed to list packages"):
            client.list_packages("fedora-build")

    def test_list_tagged_builds_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = """python3-3.11.0-1.fc40  fedora-build  admin
gcc-13.0-1.fc40  fedora-build  admin
"""
        mock_subprocess_run.return_value.stderr = ""
        client = KojiClient()

        result = client.list_tagged_builds("fedora-build")

        assert "python3" in result
        assert result["python3"] == "python3-3.11.0-1.fc40"
        assert "gcc" in result
        assert result["gcc"] == "gcc-13.0-1.fc40"

    def test_list_tagged_builds_failure_raises(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = "Connection error"
        client = KojiClient()

        with pytest.raises(KojiConnectionError, match="Failed to list builds"):
            client.list_tagged_builds("fedora-build")

    def test_package_exists_returns_true(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "python3-3.11.0-1.fc40\n"
        client = KojiClient()

        result = client.package_exists("python3", "fedora-build")

        assert result is True

    def test_package_exists_returns_false(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = ""
        client = KojiClient()

        result = client.package_exists("nonexistent", "fedora-build")

        assert result is False

    def test_search_package_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "python3\npython3-devel\npython3-libs\n"
        client = KojiClient()

        result = client.search_package("python3*")

        assert "python3" in result
        assert "python3-devel" in result

    def test_search_package_no_results(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stdout = ""
        client = KojiClient()

        result = client.search_package("nonexistent*")

        assert result == []

    def test_command_timeout_raises(self, mock_subprocess_run):
        import subprocess
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="koji", timeout=60)
        client = KojiClient()

        with pytest.raises(KojiConnectionError, match="timed out"):
            client.list_packages("fedora-build")


class TestDependencyResolver:
    def test_default_initialization(self):
        resolver = DependencyResolver()

        assert resolver.koji is not None
        assert resolver.koji_tag == "fedora-build"
        assert resolver._available_packages is None
        assert resolver._dependency_graph == {}

    def test_custom_initialization(self, mock_koji_client):
        resolver = DependencyResolver(
            koji_client=mock_koji_client,
            koji_tag="custom-tag"
        )

        assert resolver.koji == mock_koji_client
        assert resolver.koji_tag == "custom-tag"

    def test_available_packages_lazy_load(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["python3", "gcc", "make"]
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.available_packages

        assert "python3" in result
        assert "gcc" in result
        mock_koji_client.list_packages.assert_called_once()

    def test_available_packages_cached(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["python3", "gcc"]
        resolver = DependencyResolver(koji_client=mock_koji_client)
        _ = resolver.available_packages
        _ = resolver.available_packages

        mock_koji_client.list_packages.assert_called_once()

    def test_refresh_available_packages(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["python3"]
        resolver = DependencyResolver(koji_client=mock_koji_client)
        _ = resolver.available_packages
        resolver.refresh_available_packages()
        mock_koji_client.list_packages.return_value = ["python3", "gcc"]
        result = resolver.available_packages

        assert mock_koji_client.list_packages.call_count == 2
        assert "gcc" in result

    def test_find_missing_deps_all_available(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["python3", "gcc", "make"]
        mock_koji_client.package_exists.return_value = True
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.find_missing_deps(["python3", "gcc"])

        assert result == []

    def test_find_missing_deps_some_missing(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["python3", "gcc"]
        mock_koji_client.package_exists.side_effect = lambda p, t: p != "missing-pkg"
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.find_missing_deps(["python3", "missing-pkg"])

        assert "missing-pkg" in result
        assert "python3" not in result

    def test_find_missing_deps_with_build_requirement_objects(self, mock_koji_client):
        mock_koji_client.list_packages.return_value = ["gcc"]
        mock_koji_client.package_exists.side_effect = lambda p, t: p == "gcc"
        resolver = DependencyResolver(koji_client=mock_koji_client)
        deps = [
            BuildRequirement(name="gcc"),
            BuildRequirement(name="missing-dep", version="1.0", operator=">=")
        ]

        result = resolver.find_missing_deps(deps)

        assert "missing-dep" in result
        assert "gcc" not in result

    def test_build_dependency_graph_available_package(self, mock_koji_client):
        mock_koji_client.package_exists.return_value = True
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.build_dependency_graph("available-pkg", "/path/to/srpm")

        assert "available-pkg" in result
        assert result["available-pkg"].is_available is True

    def test_build_dependency_graph_missing_package(self, mock_koji_client):
        mock_koji_client.package_exists.return_value = False
        resolver = DependencyResolver(koji_client=mock_koji_client)

        with patch("vibebuild.resolver.get_build_requires") as mock_get_requires:
            mock_get_requires.return_value = []
            result = resolver.build_dependency_graph("missing-pkg", "/path/to/srpm")

        assert "missing-pkg" in result
        assert result["missing-pkg"].is_available is False
        assert result["missing-pkg"].srpm_path == "/path/to/srpm"

    def test_build_dependency_graph_with_deps(self, mock_koji_client):
        def package_exists_side_effect(pkg, tag):
            return pkg in ["dep1", "dep2"]
        mock_koji_client.package_exists.side_effect = package_exists_side_effect
        resolver = DependencyResolver(koji_client=mock_koji_client)

        with patch("vibebuild.resolver.get_build_requires") as mock_get_requires:
            mock_get_requires.return_value = ["dep1", "dep2", "dep3"]
            result = resolver.build_dependency_graph(
                "main-pkg",
                "/path/to/main.src.rpm",
                srpm_resolver=lambda pkg: f"/path/to/{pkg}.src.rpm" if pkg == "dep3" else None
            )

        assert "main-pkg" in result
        assert "dep3" in result
        assert result["dep3"].srpm_path == "/path/to/dep3.src.rpm"

    def test_topological_sort_empty_graph(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.topological_sort()

        assert result == []

    def test_topological_sort_single_package(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "pkg-a": DependencyNode(name="pkg-a", is_available=False)
        }

        result = resolver.topological_sort()

        assert result == ["pkg-a"]

    def test_topological_sort_linear_deps(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "pkg-a": DependencyNode(name="pkg-a", dependencies=["pkg-b"], is_available=False),
            "pkg-b": DependencyNode(name="pkg-b", dependencies=["pkg-c"], is_available=False),
            "pkg-c": DependencyNode(name="pkg-c", dependencies=[], is_available=False),
        }

        result = resolver.topological_sort()

        assert result.index("pkg-c") < result.index("pkg-b")
        assert result.index("pkg-b") < result.index("pkg-a")

    def test_topological_sort_skips_available(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "pkg-a": DependencyNode(name="pkg-a", dependencies=["pkg-b"], is_available=False),
            "pkg-b": DependencyNode(name="pkg-b", is_available=True),
        }

        result = resolver.topological_sort()

        assert "pkg-a" in result
        assert "pkg-b" not in result

    def test_topological_sort_circular_dependency_raises(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "pkg-a": DependencyNode(name="pkg-a", dependencies=["pkg-b"], is_available=False),
            "pkg-b": DependencyNode(name="pkg-b", dependencies=["pkg-a"], is_available=False),
        }

        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            resolver.topological_sort()

    def test_get_build_chain_empty(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)

        result = resolver.get_build_chain()

        assert result == []

    def test_get_build_chain_groups_by_level(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "main": DependencyNode(name="main", dependencies=["dep1", "dep2"], is_available=False),
            "dep1": DependencyNode(name="dep1", dependencies=["base"], is_available=False),
            "dep2": DependencyNode(name="dep2", dependencies=["base"], is_available=False),
            "base": DependencyNode(name="base", dependencies=[], is_available=False),
        }

        result = resolver.get_build_chain()

        assert len(result) >= 2
        base_level = next(i for i, level in enumerate(result) if "base" in level)
        dep_level = next(i for i, level in enumerate(result) if "dep1" in level or "dep2" in level)
        main_level = next(i for i, level in enumerate(result) if "main" in level)
        assert base_level < dep_level < main_level

    def test_get_missing_packages(self, mock_koji_client):
        resolver = DependencyResolver(koji_client=mock_koji_client)
        resolver._dependency_graph = {
            "with-srpm": DependencyNode(name="with-srpm", srpm_path="/path/to.src.rpm", is_available=False),
            "no-srpm": DependencyNode(name="no-srpm", srpm_path=None, is_available=False),
            "available": DependencyNode(name="available", is_available=True),
        }

        result = resolver.get_missing_packages()

        assert "no-srpm" in result
        assert "with-srpm" not in result
        assert "available" not in result
