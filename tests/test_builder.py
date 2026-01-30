"""Tests for vibebuild.builder module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess
import time

from vibebuild.builder import (
    BuildStatus,
    BuildTask,
    BuildResult,
    KojiBuilder,
)
from vibebuild.exceptions import KojiBuildError, KojiConnectionError
from vibebuild.analyzer import PackageInfo


class TestBuildStatus:
    def test_status_values(self):
        assert BuildStatus.PENDING.value == "pending"
        assert BuildStatus.BUILDING.value == "building"
        assert BuildStatus.COMPLETE.value == "complete"
        assert BuildStatus.FAILED.value == "failed"
        assert BuildStatus.CANCELED.value == "canceled"


class TestBuildTask:
    def test_default_values(self):
        task = BuildTask(
            package_name="test-pkg",
            srpm_path="/path/to/test.src.rpm",
            target="fedora-target"
        )

        assert task.package_name == "test-pkg"
        assert task.srpm_path == "/path/to/test.src.rpm"
        assert task.target == "fedora-target"
        assert task.task_id is None
        assert task.status == BuildStatus.PENDING
        assert task.error_message is None
        assert task.nvr is None

    def test_with_all_values(self):
        task = BuildTask(
            package_name="test-pkg",
            srpm_path="/path/to/test.src.rpm",
            target="fedora-target",
            task_id=12345,
            status=BuildStatus.COMPLETE,
            nvr="test-pkg-1.0-1.fc40"
        )

        assert task.task_id == 12345
        assert task.status == BuildStatus.COMPLETE
        assert task.nvr == "test-pkg-1.0-1.fc40"


class TestBuildResult:
    def test_default_values(self):
        result = BuildResult(success=True)

        assert result.success is True
        assert result.tasks == []
        assert result.failed_packages == []
        assert result.built_packages == []
        assert result.total_time == 0.0

    def test_with_tasks(self):
        task1 = BuildTask(package_name="pkg1", srpm_path="/path/1", target="target")
        task2 = BuildTask(package_name="pkg2", srpm_path="/path/2", target="target")
        result = BuildResult(
            success=True,
            tasks=[task1, task2],
            built_packages=["pkg1", "pkg2"],
            total_time=120.5
        )

        assert len(result.tasks) == 2
        assert "pkg1" in result.built_packages
        assert result.total_time == 120.5


class TestKojiBuilder:
    def test_default_initialization(self):
        builder = KojiBuilder()

        assert builder.koji_server == "https://koji.fedoraproject.org/kojihub"
        assert builder.target == "fedora-target"
        assert builder.build_tag == "fedora-build"
        assert builder.scratch is False
        assert builder.nowait is False

    def test_custom_initialization(self):
        builder = KojiBuilder(
            koji_server="https://custom.koji.example.com/kojihub",
            koji_web_url="https://custom.koji.example.com/koji",
            cert="/path/to/cert.pem",
            serverca="/path/to/ca.crt",
            target="custom-target",
            build_tag="custom-build",
            scratch=True,
            nowait=True,
            download_dir="/tmp/downloads"
        )

        assert builder.koji_server == "https://custom.koji.example.com/kojihub"
        assert builder.cert == "/path/to/cert.pem"
        assert builder.target == "custom-target"
        assert builder.scratch is True
        assert builder.nowait is True

    def test_run_koji_command(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "output"
        builder = KojiBuilder()

        result = builder._run_koji("list-tags")

        assert result.returncode == 0
        call_args = mock_subprocess_run.call_args[0][0]
        assert "koji" in call_args
        assert "--server=https://koji.fedoraproject.org/kojihub" in call_args
        assert "list-tags" in call_args

    def test_run_koji_with_cert(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        builder = KojiBuilder(cert="/path/to/cert.pem", serverca="/path/to/ca.crt")

        builder._run_koji("list-tags")

        call_args = mock_subprocess_run.call_args[0][0]
        assert "--cert=/path/to/cert.pem" in call_args
        assert "--serverca=/path/to/ca.crt" in call_args

    def test_run_koji_timeout(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="koji", timeout=60)
        builder = KojiBuilder()

        with pytest.raises(KojiConnectionError, match="timed out"):
            builder._run_koji("list-tags")

    def test_build_package_success(self, tmp_path, mock_subprocess_run, sample_spec_content):
        srpm = tmp_path / "test-package-1.0-1.src.rpm"
        srpm.write_text("fake srpm")
        spec_file = tmp_path / "test-package.spec"
        spec_file.write_text(sample_spec_content)
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345\nTask info: id=12345"
        mock_subprocess_run.return_value.stderr = ""
        builder = KojiBuilder()

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test-package",
                version="1.0",
                release="1",
                build_requires=[],
                source_urls=[]
            )
            task = builder.build_package(str(srpm), wait=False)

        assert task.package_name == "test-package"
        assert task.task_id == 12345
        assert task.status == BuildStatus.BUILDING

    def test_build_package_with_wait(self, tmp_path, mock_subprocess_run, sample_spec_content):
        srpm = tmp_path / "test-package-1.0-1.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345\nBuild complete"
        mock_subprocess_run.return_value.stderr = ""
        builder = KojiBuilder()

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test-package",
                version="1.0",
                release="1",
                build_requires=[],
                source_urls=[]
            )
            task = builder.build_package(str(srpm), wait=True)

        assert task.status == BuildStatus.COMPLETE

    def test_build_package_scratch(self, tmp_path, mock_subprocess_run, sample_spec_content):
        srpm = tmp_path / "test-package-1.0-1.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345"
        builder = KojiBuilder(scratch=True)

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test-package",
                version="1.0",
                release="1",
                build_requires=[],
                source_urls=[]
            )
            builder.build_package(str(srpm), wait=False)

        call_args = mock_subprocess_run.call_args[0][0]
        assert "--scratch" in call_args

    def test_build_package_file_not_found(self):
        builder = KojiBuilder()

        with pytest.raises(FileNotFoundError):
            builder.build_package("/nonexistent/path.src.rpm")

    def test_build_package_failure(self, tmp_path, mock_subprocess_run):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = "Build failed: dependency error"
        builder = KojiBuilder()

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test", version="1.0", release="1",
                build_requires=[], source_urls=[]
            )
            with pytest.raises(KojiBuildError, match="Build failed"):
                builder.build_package(str(srpm))

    def test_wait_for_repo_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Repo ready"
        builder = KojiBuilder()

        result = builder.wait_for_repo()

        assert result is True
        call_args = mock_subprocess_run.call_args[0][0]
        assert "wait-repo" in call_args
        assert "fedora-build" in call_args

    def test_wait_for_repo_custom_tag(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        builder = KojiBuilder()

        builder.wait_for_repo(tag="custom-tag")

        call_args = mock_subprocess_run.call_args[0][0]
        assert "custom-tag" in call_args

    def test_wait_for_repo_failure(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stderr = "Timeout waiting for repo"
        builder = KojiBuilder()

        result = builder.wait_for_repo()

        assert result is False

    def test_get_build_status_complete(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Task: 12345\nState: closed"
        builder = KojiBuilder()

        result = builder.get_build_status(12345)

        assert result == BuildStatus.COMPLETE

    def test_get_build_status_failed(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Task: 12345\nState: failed"
        builder = KojiBuilder()

        result = builder.get_build_status(12345)

        assert result == BuildStatus.FAILED

    def test_get_build_status_building(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Task: 12345\nState: open"
        builder = KojiBuilder()

        result = builder.get_build_status(12345)

        assert result == BuildStatus.BUILDING

    def test_get_build_status_canceled(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Task: 12345\nState: canceled"
        builder = KojiBuilder()

        result = builder.get_build_status(12345)

        assert result == BuildStatus.CANCELED

    def test_get_build_status_error(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        builder = KojiBuilder()

        result = builder.get_build_status(12345)

        assert result == BuildStatus.FAILED

    def test_cancel_build_success(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        builder = KojiBuilder()

        result = builder.cancel_build(12345)

        assert result is True
        call_args = mock_subprocess_run.call_args[0][0]
        assert "cancel" in call_args
        assert "12345" in call_args

    def test_cancel_build_failure(self, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        builder = KojiBuilder()

        result = builder.cancel_build(12345)

        assert result is False


class TestKojiBuilderBuildWithDeps:
    def test_build_with_deps_no_missing_deps(self, tmp_path, mock_subprocess_run, sample_spec_content):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345"
        builder = KojiBuilder()

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test", version="1.0", release="1",
                build_requires=[], source_urls=[]
            )
            with patch.object(builder.resolver, "build_dependency_graph"):
                with patch.object(builder.resolver, "get_build_chain", return_value=[]):
                    result = builder.build_with_deps(str(srpm))

        assert result.success is True
        assert "test" in result.built_packages

    def test_build_with_deps_builds_dependencies_first(self, tmp_path, mock_subprocess_run):
        srpm = tmp_path / "main.src.rpm"
        srpm.write_text("fake srpm")
        dep_srpm = tmp_path / "dep.src.rpm"
        dep_srpm.write_text("fake dep srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345"
        builder = KojiBuilder()
        from vibebuild.resolver import DependencyNode
        builder.resolver._dependency_graph = {
            "main": DependencyNode(name="main", srpm_path=str(srpm)),
            "dep": DependencyNode(name="dep", srpm_path=str(dep_srpm)),
        }

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="main", version="1.0", release="1",
                build_requires=[], source_urls=[]
            )
            with patch.object(builder.resolver, "build_dependency_graph"):
                with patch.object(builder.resolver, "get_build_chain", return_value=[["dep"], ["main"]]):
                    result = builder.build_with_deps(str(srpm))

        assert "dep" in result.built_packages
        assert "main" in result.built_packages

    def test_build_with_deps_file_not_found(self):
        builder = KojiBuilder()

        with pytest.raises(FileNotFoundError):
            builder.build_with_deps("/nonexistent/path.src.rpm")

    def test_build_with_deps_returns_time(self, tmp_path, mock_subprocess_run):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345"
        builder = KojiBuilder()

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test", version="1.0", release="1",
                build_requires=[], source_urls=[]
            )
            with patch.object(builder.resolver, "build_dependency_graph"):
                with patch.object(builder.resolver, "get_build_chain", return_value=[]):
                    result = builder.build_with_deps(str(srpm))

        assert result.total_time >= 0


class TestKojiBuilderBuildChain:
    def test_build_chain_success(self, tmp_path, mock_subprocess_run):
        pkg1 = tmp_path / "pkg1.src.rpm"
        pkg1.write_text("fake")
        pkg2 = tmp_path / "pkg2.src.rpm"
        pkg2.write_text("fake")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Created task: 12345"
        builder = KojiBuilder()
        packages = [("pkg1", str(pkg1)), ("pkg2", str(pkg2))]

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.side_effect = [
                PackageInfo(name="pkg1", version="1.0", release="1", build_requires=[], source_urls=[]),
                PackageInfo(name="pkg2", version="1.0", release="1", build_requires=[], source_urls=[]),
            ]
            result = builder.build_chain(packages)

        assert result.success is True
        assert "pkg1" in result.built_packages
        assert "pkg2" in result.built_packages

    def test_build_chain_stops_on_failure(self, tmp_path, mock_subprocess_run):
        pkg1 = tmp_path / "pkg1.src.rpm"
        pkg1.write_text("fake")
        pkg2 = tmp_path / "pkg2.src.rpm"
        pkg2.write_text("fake")
        mock_subprocess_run.side_effect = [
            Mock(returncode=1, stderr="Build failed"),
        ]
        builder = KojiBuilder()
        packages = [("pkg1", str(pkg1)), ("pkg2", str(pkg2))]

        with patch("vibebuild.builder.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="pkg1", version="1.0", release="1",
                build_requires=[], source_urls=[]
            )
            result = builder.build_chain(packages)

        assert result.success is False
        assert "pkg1" in result.failed_packages
        assert "pkg2" not in result.built_packages
        assert "pkg2" not in result.failed_packages
