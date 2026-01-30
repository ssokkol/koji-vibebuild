"""Tests for vibebuild.cli module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from io import StringIO

from vibebuild.cli import (
    create_parser,
    setup_logging,
    print_build_result,
    cmd_analyze,
    cmd_download,
    cmd_build,
    main,
)
from vibebuild.builder import BuildResult, BuildTask, BuildStatus
from vibebuild.analyzer import PackageInfo, BuildRequirement


class TestCreateParser:
    def test_parser_created(self):
        parser = create_parser()

        assert parser is not None
        assert parser.prog == "vibebuild"

    def test_parser_target_and_srpm_positional(self):
        parser = create_parser()

        args = parser.parse_args(["my-target", "my-package.src.rpm"])

        assert args.target == "my-target"
        assert args.srpm == "my-package.src.rpm"

    def test_parser_scratch_flag(self):
        parser = create_parser()

        args = parser.parse_args(["--scratch", "target", "pkg.src.rpm"])

        assert args.scratch is True

    def test_parser_nowait_flag(self):
        parser = create_parser()

        args = parser.parse_args(["--nowait", "target", "pkg.src.rpm"])

        assert args.nowait is True

    def test_parser_no_deps_flag(self):
        parser = create_parser()

        args = parser.parse_args(["--no-deps", "target", "pkg.src.rpm"])

        assert args.no_deps is True

    def test_parser_verbose_flag(self):
        parser = create_parser()

        args = parser.parse_args(["-v", "target", "pkg.src.rpm"])

        assert args.verbose is True

    def test_parser_quiet_flag(self):
        parser = create_parser()

        args = parser.parse_args(["-q", "target", "pkg.src.rpm"])

        assert args.quiet is True

    def test_parser_server_option(self):
        parser = create_parser()

        args = parser.parse_args(["--server", "https://custom.koji/kojihub", "target", "pkg.src.rpm"])

        assert args.server == "https://custom.koji/kojihub"

    def test_parser_server_default(self):
        parser = create_parser()

        args = parser.parse_args(["target", "pkg.src.rpm"])

        assert args.server == "https://koji.fedoraproject.org/kojihub"

    def test_parser_web_url_option(self):
        parser = create_parser()

        args = parser.parse_args(["--web-url", "https://custom.koji/koji", "target", "pkg.src.rpm"])

        assert args.web_url == "https://custom.koji/koji"

    def test_parser_cert_option(self):
        parser = create_parser()

        args = parser.parse_args(["--cert", "/path/to/cert.pem", "target", "pkg.src.rpm"])

        assert args.cert == "/path/to/cert.pem"

    def test_parser_serverca_option(self):
        parser = create_parser()

        args = parser.parse_args(["--serverca", "/path/to/ca.crt", "target", "pkg.src.rpm"])

        assert args.serverca == "/path/to/ca.crt"

    def test_parser_build_tag_option(self):
        parser = create_parser()

        args = parser.parse_args(["--build-tag", "custom-build", "target", "pkg.src.rpm"])

        assert args.build_tag == "custom-build"

    def test_parser_build_tag_default(self):
        parser = create_parser()

        args = parser.parse_args(["target", "pkg.src.rpm"])

        assert args.build_tag == "fedora-build"

    def test_parser_download_dir_option(self):
        parser = create_parser()

        args = parser.parse_args(["--download-dir", "/tmp/downloads", "target", "pkg.src.rpm"])

        assert args.download_dir == "/tmp/downloads"

    def test_parser_analyze_only_mode(self):
        parser = create_parser()

        args = parser.parse_args(["--analyze-only", "pkg.src.rpm"])

        assert args.analyze_only is True

    def test_parser_download_only_mode(self):
        parser = create_parser()

        args = parser.parse_args(["--download-only", "python-requests"])

        assert args.download_only is True

    def test_parser_dry_run_mode(self):
        parser = create_parser()

        args = parser.parse_args(["--dry-run", "target", "pkg.src.rpm"])

        assert args.dry_run is True


class TestSetupLogging:
    def test_default_level_info(self):
        import logging
        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.setLevel(logging.NOTSET)
        setup_logging()

        assert root_logger.level == logging.INFO

    def test_verbose_level_debug(self):
        import logging
        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.setLevel(logging.NOTSET)
        setup_logging(verbose=True)

        assert root_logger.level == logging.DEBUG

    def test_quiet_level_warning(self):
        import logging
        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.setLevel(logging.NOTSET)
        setup_logging(quiet=True)

        assert root_logger.level == logging.WARNING


class TestPrintBuildResult:
    def test_prints_success(self, capsys):
        result = BuildResult(
            success=True,
            built_packages=["pkg1", "pkg2"],
            failed_packages=[],
            total_time=60.0
        )

        print_build_result(result)

        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out
        assert "60.0" in captured.out

    def test_prints_failure(self, capsys):
        result = BuildResult(
            success=False,
            built_packages=["pkg1"],
            failed_packages=["pkg2"],
            total_time=45.0
        )

        print_build_result(result)

        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "pkg2" in captured.out

    def test_prints_task_info(self, capsys):
        task = BuildTask(
            package_name="test-pkg",
            srpm_path="/path/to/test.src.rpm",
            target="target",
            task_id=12345,
            status=BuildStatus.COMPLETE
        )
        result = BuildResult(
            success=True,
            tasks=[task],
            built_packages=["test-pkg"],
            total_time=30.0
        )

        print_build_result(result)

        captured = capsys.readouterr()
        assert "12345" in captured.out
        assert "test-pkg" in captured.out

    def test_prints_error_message(self, capsys):
        task = BuildTask(
            package_name="failed-pkg",
            srpm_path="/path/to/failed.src.rpm",
            target="target",
            status=BuildStatus.FAILED,
            error_message="Dependency resolution failed"
        )
        result = BuildResult(
            success=False,
            tasks=[task],
            failed_packages=["failed-pkg"],
            total_time=10.0
        )

        print_build_result(result)

        captured = capsys.readouterr()
        assert "Dependency resolution failed" in captured.out


class TestCmdAnalyze:
    def test_analyze_success(self, tmp_path, mock_subprocess_run, capsys):
        spec_file = tmp_path / "test.spec"
        spec_file.write_text("""
Name: test
Version: 1.0
Release: 1
BuildRequires: gcc
""")
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "test-1.0-1.fc40"

        with patch("vibebuild.cli.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test",
                version="1.0",
                release="1",
                build_requires=[BuildRequirement(name="gcc")],
                source_urls=[]
            )
            with patch("vibebuild.cli.KojiClient") as mock_client:
                mock_client.return_value.package_exists.return_value = True
                with patch("vibebuild.cli.DependencyResolver") as mock_resolver:
                    mock_resolver.return_value.find_missing_deps.return_value = []
                    result = cmd_analyze(
                        str(srpm),
                        "https://koji.fedoraproject.org/kojihub",
                        "fedora-build",
                        None,
                        None
                    )

        assert result == 0
        captured = capsys.readouterr()
        assert "test" in captured.out

    def test_analyze_with_missing_deps(self, tmp_path, capsys):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.get_package_info_from_srpm") as mock_info:
            mock_info.return_value = PackageInfo(
                name="test",
                version="1.0",
                release="1",
                build_requires=[BuildRequirement(name="missing-dep")],
                source_urls=[]
            )
            with patch("vibebuild.cli.KojiClient"):
                with patch("vibebuild.cli.DependencyResolver") as mock_resolver:
                    mock_resolver.return_value.find_missing_deps.return_value = ["missing-dep"]
                    result = cmd_analyze(str(srpm), "server", "tag", None, None)

        assert result == 0
        captured = capsys.readouterr()
        assert "missing-dep" in captured.out

    def test_analyze_failure(self, tmp_path, capsys):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.get_package_info_from_srpm") as mock_info:
            mock_info.side_effect = Exception("Parse error")
            result = cmd_analyze(str(srpm), "server", "tag", None, None)

        assert result == 1


class TestCmdDownload:
    def test_download_success(self, tmp_path, capsys):
        with patch("vibebuild.cli.SRPMFetcher") as mock_fetcher:
            mock_fetcher.return_value.download_srpm.return_value = "/path/to/pkg.src.rpm"
            result = cmd_download("python-requests", str(tmp_path))

        assert result == 0
        captured = capsys.readouterr()
        assert "Downloaded" in captured.out

    def test_download_failure(self, capsys):
        with patch("vibebuild.cli.SRPMFetcher") as mock_fetcher:
            mock_fetcher.return_value.download_srpm.side_effect = Exception("Not found")
            result = cmd_download("nonexistent-pkg", None)

        assert result == 1


class TestCmdBuild:
    def test_build_file_not_found(self):
        result = cmd_build(
            target="target",
            srpm_path="/nonexistent/path.src.rpm",
            server="server",
            web_url="web",
            cert=None,
            serverca=None,
            build_tag="tag",
            scratch=False,
            nowait=False,
            no_deps=False,
            download_dir=None,
            dry_run=False
        )

        assert result == 1

    def test_build_dry_run(self, tmp_path, capsys):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.KojiBuilder") as mock_builder:
            with patch("vibebuild.cli.get_package_info_from_srpm") as mock_info:
                mock_info.return_value = PackageInfo(
                    name="test", version="1.0", release="1",
                    build_requires=[], source_urls=[]
                )
                mock_builder.return_value.resolver.build_dependency_graph.return_value = None
                mock_builder.return_value.resolver.get_build_chain.return_value = []
                result = cmd_build(
                    target="target",
                    srpm_path=str(srpm),
                    server="server",
                    web_url="web",
                    cert=None,
                    serverca=None,
                    build_tag="tag",
                    scratch=False,
                    nowait=False,
                    no_deps=False,
                    download_dir=None,
                    dry_run=True
                )

        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    def test_build_no_deps(self, tmp_path, capsys):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.KojiBuilder") as mock_builder:
            mock_task = BuildTask(
                package_name="test",
                srpm_path=str(srpm),
                target="target",
                status=BuildStatus.COMPLETE
            )
            mock_builder.return_value.build_package.return_value = mock_task
            result = cmd_build(
                target="target",
                srpm_path=str(srpm),
                server="server",
                web_url="web",
                cert=None,
                serverca=None,
                build_tag="tag",
                scratch=False,
                nowait=False,
                no_deps=True,
                download_dir=None,
                dry_run=False
            )

        assert result == 0

    def test_build_with_deps(self, tmp_path, capsys):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.KojiBuilder") as mock_builder:
            mock_builder.return_value.build_with_deps.return_value = BuildResult(
                success=True,
                built_packages=["test"],
                total_time=30.0
            )
            result = cmd_build(
                target="target",
                srpm_path=str(srpm),
                server="server",
                web_url="web",
                cert=None,
                serverca=None,
                build_tag="tag",
                scratch=False,
                nowait=False,
                no_deps=False,
                download_dir=None,
                dry_run=False
            )

        assert result == 0
        mock_builder.return_value.build_with_deps.assert_called_once()


class TestMain:
    def test_main_analyze_only_requires_srpm(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--analyze-only"])

        assert exc_info.value.code == 2

    def test_main_download_only_requires_package(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--download-only"])

        assert exc_info.value.code == 2

    def test_main_build_requires_target_and_srpm(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["only-target"])

        assert exc_info.value.code == 2

    def test_main_analyze_only(self, tmp_path):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.cmd_analyze") as mock_cmd:
            mock_cmd.return_value = 0
            result = main(["--analyze-only", str(srpm)])

        assert result == 0
        mock_cmd.assert_called_once()

    def test_main_download_only(self):
        with patch("vibebuild.cli.cmd_download") as mock_cmd:
            mock_cmd.return_value = 0
            result = main(["--download-only", "python-requests"])

        assert result == 0
        mock_cmd.assert_called_once()

    def test_main_build(self, tmp_path):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.cmd_build") as mock_cmd:
            mock_cmd.return_value = 0
            result = main(["target", str(srpm)])

        assert result == 0
        mock_cmd.assert_called_once()

    def test_main_verbose_sets_logging(self, tmp_path):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.cmd_build") as mock_cmd:
            mock_cmd.return_value = 0
            with patch("vibebuild.cli.setup_logging") as mock_logging:
                result = main(["-v", "target", str(srpm)])

        mock_logging.assert_called_with(True, False)

    def test_main_quiet_sets_logging(self, tmp_path):
        srpm = tmp_path / "test.src.rpm"
        srpm.write_text("fake srpm")

        with patch("vibebuild.cli.cmd_build") as mock_cmd:
            mock_cmd.return_value = 0
            with patch("vibebuild.cli.setup_logging") as mock_logging:
                result = main(["-q", "target", str(srpm)])

        mock_logging.assert_called_with(False, True)
