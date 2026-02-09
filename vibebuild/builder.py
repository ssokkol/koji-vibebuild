"""
Koji builder - orchestrates package builds with dependency resolution.
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from vibebuild.analyzer import get_package_info_from_srpm
from vibebuild.exceptions import KojiBuildError, KojiConnectionError
from vibebuild.fetcher import SRPMFetcher
from vibebuild.name_resolver import PackageNameResolver
from vibebuild.resolver import DependencyResolver, KojiClient

logger = logging.getLogger(__name__)


class BuildStatus(Enum):
    """Status of a build task."""

    PENDING = "pending"
    BUILDING = "building"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class BuildTask:
    """Represents a single build task."""

    package_name: str
    srpm_path: str
    target: str
    task_id: Optional[int] = None
    status: BuildStatus = BuildStatus.PENDING
    error_message: Optional[str] = None
    nvr: Optional[str] = None


@dataclass
class BuildResult:
    """Result of a vibebuild operation."""

    success: bool
    tasks: list[BuildTask] = field(default_factory=list)
    failed_packages: list[str] = field(default_factory=list)
    built_packages: list[str] = field(default_factory=list)
    total_time: float = 0.0


class KojiBuilder:
    """
    Orchestrates Koji builds with automatic dependency resolution.

    This is the main class that implements the vibebuild functionality:
    1. Analyzes SRPM to find BuildRequires
    2. Checks which dependencies are missing in Koji
    3. Downloads missing SRPMs from Fedora
    4. Builds dependencies in correct order
    5. Waits for repo regeneration between builds
    6. Finally builds the target package
    """

    def __init__(
        self,
        koji_server: str = "https://koji.fedoraproject.org/kojihub",
        koji_web_url: str = "https://koji.fedoraproject.org/koji",
        cert: Optional[str] = None,
        serverca: Optional[str] = None,
        target: str = "fedora-target",
        build_tag: str = "fedora-build",
        scratch: bool = False,
        nowait: bool = False,
        download_dir: Optional[str] = None,
        no_ssl_verify: bool = False,
        no_name_resolution: bool = False,
        no_ml: bool = False,
        ml_model_path: Optional[str] = None,
    ):
        self.koji_server = koji_server
        self.koji_web_url = koji_web_url
        self.cert = cert
        self.serverca = serverca
        self.target = target
        self.build_tag = build_tag
        self.scratch = scratch
        self.nowait = nowait
        self.no_ssl_verify = no_ssl_verify

        self.koji_client = KojiClient(
            server=koji_server,
            web_url=koji_web_url,
            cert=cert,
            serverca=serverca,
            no_ssl_verify=no_ssl_verify,
        )

        # Create name resolver
        self.name_resolver = None
        if not no_name_resolution:
            ml_resolver = None
            if not no_ml:
                try:
                    from vibebuild.ml_resolver import MLPackageResolver

                    ml_resolver = MLPackageResolver(model_path=ml_model_path)
                    if not ml_resolver.is_available():
                        ml_resolver = None
                except ImportError:
                    ml_resolver = None
            self.name_resolver = PackageNameResolver(ml_resolver=ml_resolver)

        self.resolver = DependencyResolver(
            koji_client=self.koji_client,
            koji_tag=build_tag,
            name_resolver=self.name_resolver,
        )

        self.fetcher = SRPMFetcher(
            download_dir=download_dir,
            no_ssl_verify=no_ssl_verify,
            name_resolver=self.name_resolver,
        )

        self._tasks: list[BuildTask] = []

    def _get_env(self) -> Optional[dict]:
        """Get environment variables for subprocess, with SSL verification disabled if needed."""
        if self.no_ssl_verify:
            env = os.environ.copy()
            env["PYTHONHTTPSVERIFY"] = "0"
            env["REQUESTS_CA_BUNDLE"] = ""
            env["CURL_CA_BUNDLE"] = ""
            return env
        return None

    def _run_koji(self, *args, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run koji command with configured options."""
        cmd = ["koji", f"--server={self.koji_server}"]

        if self.cert:
            cmd.append(f"--cert={self.cert}")
        if self.serverca:
            cmd.append(f"--serverca={self.serverca}")

        cmd.extend(args)

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, env=self._get_env()
            )
        except subprocess.TimeoutExpired:
            raise KojiConnectionError(f"Command timed out: {' '.join(args)}")

    def build_package(self, srpm_path: str, wait: bool = True) -> BuildTask:
        """
        Submit a single package build to Koji.

        Args:
            srpm_path: Path to SRPM file
            wait: Whether to wait for build to complete

        Returns:
            BuildTask with result information
        """
        srpm_path = Path(srpm_path)
        if not srpm_path.exists():
            raise FileNotFoundError(f"SRPM not found: {srpm_path}")

        package_info = get_package_info_from_srpm(str(srpm_path))

        task = BuildTask(
            package_name=package_info.name,
            srpm_path=str(srpm_path),
            target=self.target,
            nvr=package_info.nvr,
        )

        cmd_args = ["build"]

        if self.scratch:
            cmd_args.append("--scratch")
        if not wait or self.nowait:
            cmd_args.append("--nowait")

        cmd_args.extend([self.target, str(srpm_path)])

        logger.info(f"Starting build: {package_info.nvr}")

        result = self._run_koji(*cmd_args, timeout=3600 if wait else 60)

        if result.returncode != 0:
            task.status = BuildStatus.FAILED
            task.error_message = result.stderr
            raise KojiBuildError(f"Build failed: {result.stderr}")

        for line in result.stdout.split("\n"):
            if "Created task:" in line:
                try:
                    task.task_id = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
            elif "Task info:" in line:
                try:
                    task.task_id = int(line.split("=")[-1].strip())
                except ValueError:
                    pass

        if wait and not self.nowait:
            task.status = BuildStatus.COMPLETE
        else:
            task.status = BuildStatus.BUILDING

        logger.info(f"Build submitted: task_id={task.task_id}")

        return task

    def wait_for_repo(self, tag: Optional[str] = None, timeout: int = 1800) -> bool:
        """
        Wait for repository to be regenerated after build.

        Args:
            tag: Build tag to wait for (defaults to self.build_tag)
            timeout: Maximum time to wait in seconds

        Returns:
            True if repo was regenerated successfully
        """
        tag = tag or self.build_tag

        logger.info(f"Waiting for repo regeneration: {tag}")

        result = self._run_koji("wait-repo", tag, f"--timeout={timeout}", timeout=timeout + 60)

        if result.returncode != 0:
            logger.warning(f"wait-repo failed: {result.stderr}")
            return False

        logger.info("Repo regenerated successfully")
        return True

    def build_with_deps(self, srpm_path: str) -> BuildResult:
        """
        Build package with automatic dependency resolution.

        This is the main vibebuild function. It:
        1. Analyzes the SRPM for BuildRequires
        2. Finds which dependencies are missing
        3. Downloads SRPMs for missing deps from Fedora
        4. Recursively resolves all dependencies
        5. Builds everything in correct order

        Args:
            srpm_path: Path to SRPM file to build

        Returns:
            BuildResult with all build information
        """
        start_time = time.time()
        result = BuildResult(success=True)

        srpm_path = Path(srpm_path)
        if not srpm_path.exists():
            raise FileNotFoundError(f"SRPM not found: {srpm_path}")

        logger.info(f"Starting vibebuild for: {srpm_path}")

        package_info = get_package_info_from_srpm(str(srpm_path))
        logger.info(f"Package: {package_info.nvr}")

        logger.info("Analyzing dependencies...")

        def srpm_resolver(pkg_name: str) -> Optional[str]:
            try:
                return self.fetcher.download_srpm(pkg_name)
            except Exception as e:
                logger.warning(f"Could not download SRPM for {pkg_name}: {e}")
                return None

        self.resolver.build_dependency_graph(
            package_info.name, str(srpm_path), srpm_resolver=srpm_resolver
        )

        build_chain = self.resolver.get_build_chain()

        if not build_chain:
            logger.info("No dependencies to build, proceeding with target package")
        else:
            total_deps = sum(len(level) for level in build_chain)
            logger.info(f"Found {total_deps} packages to build in {len(build_chain)} levels")

            for level_idx, level in enumerate(build_chain):
                logger.info(f"Building level {level_idx + 1}/{len(build_chain)}: {level}")

                for pkg_name in level:
                    if pkg_name == package_info.name:
                        continue

                    node = self.resolver._dependency_graph.get(pkg_name)
                    if not node or not node.srpm_path:
                        logger.warning(f"Skipping {pkg_name}: no SRPM available")
                        continue

                    try:
                        task = self.build_package(node.srpm_path, wait=True)
                        result.tasks.append(task)

                        if task.status == BuildStatus.COMPLETE:
                            result.built_packages.append(pkg_name)
                        else:
                            result.failed_packages.append(pkg_name)
                            result.success = False

                    except Exception as e:
                        logger.error(f"Failed to build {pkg_name}: {e}")
                        result.failed_packages.append(pkg_name)

                if level_idx < len(build_chain) - 1:
                    self.wait_for_repo()

        if result.success or not result.failed_packages:
            logger.info(f"Building target package: {package_info.nvr}")

            try:
                task = self.build_package(str(srpm_path), wait=True)
                result.tasks.append(task)

                if task.status == BuildStatus.COMPLETE:
                    result.built_packages.append(package_info.name)
                else:
                    result.failed_packages.append(package_info.name)
                    result.success = False

            except Exception as e:
                logger.error(f"Failed to build target package: {e}")
                result.failed_packages.append(package_info.name)
                result.success = False

        result.total_time = time.time() - start_time

        logger.info(f"VibeBuild complete in {result.total_time:.1f}s")
        logger.info(f"Built: {len(result.built_packages)}, Failed: {len(result.failed_packages)}")

        return result

    def build_chain(self, packages: list[tuple[str, str]]) -> BuildResult:
        """
        Build multiple packages in order.

        Args:
            packages: List of (package_name, srpm_path) tuples

        Returns:
            BuildResult with all build information
        """
        start_time = time.time()
        result = BuildResult(success=True)

        for pkg_name, srpm_path in packages:
            try:
                task = self.build_package(srpm_path, wait=True)
                result.tasks.append(task)

                if task.status == BuildStatus.COMPLETE:
                    result.built_packages.append(pkg_name)
                    self.wait_for_repo()
                else:
                    result.failed_packages.append(pkg_name)
                    result.success = False
                    break

            except Exception as e:
                logger.error(f"Failed to build {pkg_name}: {e}")
                result.failed_packages.append(pkg_name)
                result.success = False
                break

        result.total_time = time.time() - start_time
        return result

    def get_build_status(self, task_id: int) -> BuildStatus:
        """Get current status of a build task."""
        result = self._run_koji("taskinfo", str(task_id))

        if result.returncode != 0:
            return BuildStatus.FAILED

        output = result.stdout.lower()

        if "closed" in output or "complete" in output:
            return BuildStatus.COMPLETE
        elif "failed" in output:
            return BuildStatus.FAILED
        elif "canceled" in output:
            return BuildStatus.CANCELED
        elif "open" in output or "free" in output or "assigned" in output:
            return BuildStatus.BUILDING

        return BuildStatus.PENDING

    def cancel_build(self, task_id: int) -> bool:
        """Cancel a running build task."""
        result = self._run_koji("cancel", str(task_id))
        return result.returncode == 0
