"""Tests for vibebuild.fetcher module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

from vibebuild.fetcher import SRPMFetcher, SRPMSource
from vibebuild.exceptions import SRPMNotFoundError, VibeBuildError


class TestSRPMSource:
    def test_default_values(self):
        source = SRPMSource(name="test", base_url="https://example.com")

        assert source.name == "test"
        assert source.base_url == "https://example.com"
        assert source.koji_server is None
        assert source.priority == 100

    def test_with_all_values(self):
        source = SRPMSource(
            name="fedora",
            base_url="https://koji.fedoraproject.org",
            koji_server="https://koji.fedoraproject.org/kojihub",
            priority=10
        )

        assert source.koji_server == "https://koji.fedoraproject.org/kojihub"
        assert source.priority == 10


class TestSRPMFetcher:
    def test_default_initialization(self, tmp_path):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        assert fetcher.download_dir == tmp_path
        assert len(fetcher.sources) == 2
        assert fetcher.fedora_release == "rawhide"
        assert fetcher._cache == {}

    def test_custom_sources(self, tmp_path):
        custom_sources = [
            SRPMSource(name="custom", base_url="https://custom.example.com", priority=5)
        ]
        fetcher = SRPMFetcher(download_dir=str(tmp_path), sources=custom_sources)

        assert len(fetcher.sources) == 1
        assert fetcher.sources[0].name == "custom"

    def test_sources_sorted_by_priority(self, tmp_path):
        sources = [
            SRPMSource(name="low-priority", base_url="https://low.com", priority=100),
            SRPMSource(name="high-priority", base_url="https://high.com", priority=10),
        ]
        fetcher = SRPMFetcher(download_dir=str(tmp_path), sources=sources)

        assert fetcher.sources[0].name == "high-priority"
        assert fetcher.sources[1].name == "low-priority"

    def test_download_dir_created(self, tmp_path):
        download_dir = tmp_path / "new_dir"
        assert not download_dir.exists()

        fetcher = SRPMFetcher(download_dir=str(download_dir))

        assert download_dir.exists()

    def test_download_srpm_returns_cached(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        cached_path = tmp_path / "cached.src.rpm"
        cached_path.write_text("cached srpm")
        fetcher._cache["test-pkg-latest"] = str(cached_path)

        result = fetcher.download_srpm("test-pkg")

        assert result == str(cached_path)
        mock_subprocess_run.assert_not_called()

    def test_download_srpm_cache_miss_if_file_deleted(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        fetcher._cache["test-pkg-latest"] = "/nonexistent/path.src.rpm"
        mock_subprocess_run.side_effect = [
            Mock(returncode=0, stdout="test-pkg-1.0-1.fc40\n", stderr=""),
            Mock(returncode=0, stdout="Downloading...\n", stderr=""),
        ]
        pkg_dir = tmp_path / "test-pkg"
        pkg_dir.mkdir()
        srpm_file = pkg_dir / "test-pkg-1.0-1.fc40.src.rpm"
        srpm_file.write_text("fake srpm")

        result = fetcher.download_srpm("test-pkg")

        assert result == str(srpm_file)

    def test_download_srpm_from_koji_with_version(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Downloaded\n"
        pkg_dir = tmp_path / "test-pkg"
        pkg_dir.mkdir()
        srpm_file = pkg_dir / "test-pkg-1.0-1.fc40.src.rpm"
        srpm_file.write_text("fake srpm")

        result = fetcher.download_srpm("test-pkg", version="1.0-1.fc40")

        assert "test-pkg" in result
        assert result.endswith(".src.rpm")

    def test_download_srpm_from_koji_latest(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        mock_subprocess_run.side_effect = [
            Mock(returncode=0, stdout="test-pkg-2.0-1.fc42  fedora-build\n", stderr=""),
            Mock(returncode=0, stdout="Downloaded\n", stderr=""),
        ]
        pkg_dir = tmp_path / "test-pkg"
        pkg_dir.mkdir()
        srpm_file = pkg_dir / "test-pkg-2.0-1.fc42.src.rpm"
        srpm_file.write_text("fake srpm")

        result = fetcher.download_srpm("test-pkg")

        assert result == str(srpm_file)

    def test_download_srpm_fallback_to_rawhide(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        mock_subprocess_run.side_effect = [
            Mock(returncode=1, stdout="", stderr="Not found"),
            Mock(returncode=0, stdout="test-pkg-3.0-1.fc42  rawhide\n", stderr=""),
            Mock(returncode=0, stdout="Downloaded\n", stderr=""),
        ]
        pkg_dir = tmp_path / "test-pkg"
        pkg_dir.mkdir()
        srpm_file = pkg_dir / "test-pkg-3.0-1.fc42.src.rpm"
        srpm_file.write_text("fake srpm")

        result = fetcher.download_srpm("test-pkg")

        assert result == str(srpm_file)

    def test_download_srpm_raises_not_found(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stdout = ""
        mock_subprocess_run.return_value.stderr = "Not found"

        with pytest.raises(SRPMNotFoundError, match="Could not find SRPM"):
            fetcher.download_srpm("nonexistent-pkg")

    def test_download_srpm_no_srpm_after_download(self, tmp_path, mock_subprocess_run):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        mock_subprocess_run.side_effect = [
            Mock(returncode=0, stdout="test-pkg-1.0-1.fc40\n", stderr=""),
            Mock(returncode=0, stdout="Downloaded\n", stderr=""),
        ]
        pkg_dir = tmp_path / "test-pkg"
        pkg_dir.mkdir()

        with pytest.raises(SRPMNotFoundError, match="Could not find SRPM for test-pkg"):
            fetcher.download_srpm("test-pkg")

    def test_search_fedora_src_success(self, tmp_path, mocker):
        mock_requests = mocker.patch("vibebuild.fetcher.requests")
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "projects": [
                {"name": "python3"},
                {"name": "python3-devel"},
                {"name": "python3-libs"}
            ]
        }
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        result = fetcher.search_fedora_src("python3")

        assert "python3" in result
        assert "python3-devel" in result

    def test_search_fedora_src_no_results(self, tmp_path, mocker):
        mock_requests = mocker.patch("vibebuild.fetcher.requests")
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {"projects": []}
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        result = fetcher.search_fedora_src("nonexistent")

        assert result == []

    def test_get_package_versions_success(self, tmp_path, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = """python3-3.11.0-1.fc40
python3-3.10.0-1.fc39
python3-3.9.0-1.fc38
"""
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        result = fetcher.get_package_versions("python3")

        assert "3.11.0" in result
        assert "3.10.0" in result
        assert "3.9.0" in result

    def test_get_package_versions_no_results(self, tmp_path, mock_subprocess_run):
        mock_subprocess_run.return_value.returncode = 1
        mock_subprocess_run.return_value.stdout = ""
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        result = fetcher.get_package_versions("nonexistent")

        assert result == []

    def test_clear_cache(self, tmp_path):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        fetcher._cache["pkg1"] = "/path/to/pkg1.src.rpm"
        fetcher._cache["pkg2"] = "/path/to/pkg2.src.rpm"

        fetcher.clear_cache()

        assert fetcher._cache == {}

    def test_cleanup_removes_directory(self, tmp_path):
        download_dir = tmp_path / "to_cleanup"
        download_dir.mkdir()
        (download_dir / "some_file.txt").write_text("test")
        fetcher = SRPMFetcher(download_dir=str(download_dir))
        fetcher._cache["test"] = "value"

        fetcher.cleanup()

        assert not download_dir.exists()
        assert fetcher._cache == {}


class TestSRPMFetcherWithRequests:
    @pytest.fixture
    def mock_requests(self, mocker):
        mock = mocker.patch("vibebuild.fetcher.requests")
        mock.get.return_value.status_code = 200
        return mock

    def test_download_from_src_success(self, tmp_path, mock_subprocess_run, mock_requests):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        fetcher.sources = [
            SRPMSource(name="fedora-src", base_url="https://src.fedoraproject.org/rpms", priority=1)
        ]
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.text = """
Name: test-pkg
Version: 1.0
Release: 1
Source0: test-pkg-1.0.tar.gz
"""
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = ""
        work_dir = tmp_path / "test-pkg" / "build"
        work_dir.mkdir(parents=True)
        srpm_file = work_dir / "test-pkg-1.0-1.src.rpm"
        srpm_file.write_text("fake srpm")

        with patch.object(fetcher, '_download_file'):
            with patch("vibebuild.fetcher.Path.glob") as mock_glob:
                mock_glob.return_value = [srpm_file]
                result = fetcher.download_srpm("test-pkg")

        assert "test-pkg" in result

    def test_download_from_src_spec_not_found(self, tmp_path, mock_requests):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        fetcher.sources = [
            SRPMSource(name="fedora-src", base_url="https://src.fedoraproject.org/rpms", priority=1)
        ]
        mock_requests.get.return_value.status_code = 404

        with pytest.raises(SRPMNotFoundError):
            fetcher.download_srpm("nonexistent-pkg")

    def test_search_fedora_src_with_requests(self, tmp_path, mock_requests):
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {
            "projects": [
                {"name": "python3"},
                {"name": "python3-devel"}
            ]
        }
        fetcher = SRPMFetcher(download_dir=str(tmp_path))

        result = fetcher.search_fedora_src("python3")

        assert "python3" in result
        assert "python3-devel" in result


class TestSRPMFetcherExtractSources:
    def test_extract_sources_from_spec(self, tmp_path):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        spec_content = """
Name: test
Version: 1.0
Source0: https://example.com/test-1.0.tar.gz
Source1: test-config.conf
Source2: https://cdn.example.com/patches/patch1.diff
"""

        result = fetcher._extract_sources(spec_content)

        assert "https://example.com/test-1.0.tar.gz" in result
        assert "test-config.conf" in result
        assert "https://cdn.example.com/patches/patch1.diff" in result

    def test_extract_sources_empty(self, tmp_path):
        fetcher = SRPMFetcher(download_dir=str(tmp_path))
        spec_content = """
Name: test
Version: 1.0
"""

        result = fetcher._extract_sources(spec_content)

        assert result == []
