#!/usr/bin/env python3
"""
VibeBuild CLI - Koji extension for automatic dependency resolution.

Usage:
    vibebuild [OPTIONS] TARGET SRPM
    
Examples:
    vibebuild fedora-target my-package.src.rpm
    vibebuild --scratch fedora-target my-package.src.rpm
    vibebuild --server https://my-koji/kojihub fedora-target pkg.src.rpm
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from vibebuild import __version__
from vibebuild.analyzer import get_build_requires, get_package_info_from_srpm
from vibebuild.builder import KojiBuilder, BuildResult, BuildStatus
from vibebuild.exceptions import VibeBuildError
from vibebuild.fetcher import SRPMFetcher
from vibebuild.resolver import DependencyResolver, KojiClient


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging based on verbosity."""
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog='vibebuild',
        description='Koji build with automatic dependency resolution',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Build package with automatic dependency resolution
  vibebuild fedora-target my-package-1.0-1.fc40.src.rpm

  # Scratch build (not tagged)
  vibebuild --scratch fedora-target my-package.src.rpm

  # Use custom Koji server
  vibebuild --server https://koji.example.com/kojihub fedora-target pkg.src.rpm

  # Analyze dependencies without building
  vibebuild --analyze-only my-package.src.rpm

  # Download SRPM from Fedora
  vibebuild --download-only python-requests
'''
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress non-error output'
    )
    
    koji_group = parser.add_argument_group('Koji options')
    
    koji_group.add_argument(
        '--server',
        metavar='URL',
        default='https://koji.fedoraproject.org/kojihub',
        help='Koji hub URL (default: Fedora Koji)'
    )
    
    koji_group.add_argument(
        '--web-url',
        metavar='URL',
        default='https://koji.fedoraproject.org/koji',
        help='Koji web URL'
    )
    
    koji_group.add_argument(
        '--cert',
        metavar='FILE',
        help='Client certificate for authentication'
    )
    
    koji_group.add_argument(
        '--serverca',
        metavar='FILE',
        help='CA certificate for server verification'
    )
    
    koji_group.add_argument(
        '--build-tag',
        metavar='TAG',
        default='fedora-build',
        help='Build tag for dependency checking'
    )
    
    build_group = parser.add_argument_group('Build options')
    
    build_group.add_argument(
        '--scratch',
        action='store_true',
        help='Perform scratch build (not tagged)'
    )
    
    build_group.add_argument(
        '--nowait',
        action='store_true',
        help='Do not wait for builds to complete'
    )
    
    build_group.add_argument(
        '--no-deps',
        action='store_true',
        help='Skip dependency resolution, just build the package'
    )
    
    build_group.add_argument(
        '--download-dir',
        metavar='DIR',
        help='Directory for downloaded SRPMs'
    )
    
    mode_group = parser.add_argument_group('Mode options')
    
    mode_group.add_argument(
        '--analyze-only',
        action='store_true',
        help='Only analyze dependencies, do not build'
    )
    
    mode_group.add_argument(
        '--download-only',
        action='store_true',
        help='Only download SRPM, do not build'
    )
    
    mode_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be built without actually building'
    )
    
    parser.add_argument(
        'target',
        nargs='?',
        help='Build target (e.g., fedora-target)'
    )
    
    parser.add_argument(
        'srpm',
        nargs='?',
        help='Path to SRPM file or package name (with --download-only)'
    )
    
    return parser


def print_build_result(result: BuildResult) -> None:
    """Print build result summary."""
    print("\n" + "=" * 60)
    print("BUILD SUMMARY")
    print("=" * 60)
    
    if result.success:
        print("Status: SUCCESS ✓")
    else:
        print("Status: FAILED ✗")
    
    print(f"Total time: {result.total_time:.1f} seconds")
    print(f"Packages built: {len(result.built_packages)}")
    print(f"Packages failed: {len(result.failed_packages)}")
    
    if result.built_packages:
        print("\nSuccessfully built:")
        for pkg in result.built_packages:
            print(f"  ✓ {pkg}")
    
    if result.failed_packages:
        print("\nFailed packages:")
        for pkg in result.failed_packages:
            print(f"  ✗ {pkg}")
    
    if result.tasks:
        print("\nBuild tasks:")
        for task in result.tasks:
            status_icon = {
                BuildStatus.COMPLETE: "✓",
                BuildStatus.FAILED: "✗",
                BuildStatus.BUILDING: "⏳",
                BuildStatus.PENDING: "○",
                BuildStatus.CANCELED: "⊘",
            }.get(task.status, "?")
            
            print(f"  {status_icon} {task.package_name}: {task.status.value}")
            if task.task_id:
                print(f"      Task ID: {task.task_id}")
            if task.error_message:
                print(f"      Error: {task.error_message[:100]}")
    
    print("=" * 60)


def cmd_analyze(srpm_path: str, server: str, build_tag: str, cert: Optional[str], serverca: Optional[str]) -> int:
    """Analyze SRPM dependencies."""
    print(f"Analyzing: {srpm_path}")
    
    try:
        package_info = get_package_info_from_srpm(srpm_path)
        print(f"\nPackage: {package_info.name}")
        print(f"Version: {package_info.version}")
        print(f"Release: {package_info.release}")
        print(f"NVR: {package_info.nvr}")
        
        print(f"\nBuildRequires ({len(package_info.build_requires)}):")
        for req in package_info.build_requires:
            print(f"  - {req}")
        
        print("\nChecking availability in Koji...")
        
        koji_client = KojiClient(server=server, cert=cert, serverca=serverca)
        resolver = DependencyResolver(koji_client=koji_client, koji_tag=build_tag)
        
        missing = resolver.find_missing_deps([r.name for r in package_info.build_requires])
        
        if missing:
            print(f"\nMissing dependencies ({len(missing)}):")
            for dep in missing:
                print(f"  ✗ {dep}")
        else:
            print("\n✓ All dependencies available")
        
        return 0
        
    except Exception as e:
        logging.error(f"Analysis failed: {e}")
        return 1


def cmd_download(package_name: str, download_dir: Optional[str]) -> int:
    """Download SRPM from Fedora."""
    print(f"Downloading SRPM for: {package_name}")
    
    try:
        fetcher = SRPMFetcher(download_dir=download_dir)
        srpm_path = fetcher.download_srpm(package_name)
        
        print(f"✓ Downloaded: {srpm_path}")
        return 0
        
    except Exception as e:
        logging.error(f"Download failed: {e}")
        return 1


def cmd_build(
    target: str,
    srpm_path: str,
    server: str,
    web_url: str,
    cert: Optional[str],
    serverca: Optional[str],
    build_tag: str,
    scratch: bool,
    nowait: bool,
    no_deps: bool,
    download_dir: Optional[str],
    dry_run: bool,
) -> int:
    """Build package with dependency resolution."""
    srpm = Path(srpm_path)
    if not srpm.exists():
        logging.error(f"SRPM not found: {srpm_path}")
        return 1
    
    builder = KojiBuilder(
        koji_server=server,
        koji_web_url=web_url,
        cert=cert,
        serverca=serverca,
        target=target,
        build_tag=build_tag,
        scratch=scratch,
        nowait=nowait,
        download_dir=download_dir,
    )
    
    if dry_run:
        print("DRY RUN - showing what would be built:\n")
        
        package_info = get_package_info_from_srpm(str(srpm))
        print(f"Target package: {package_info.nvr}")
        
        if not no_deps:
            def srpm_resolver(pkg: str) -> Optional[str]:
                try:
                    return builder.fetcher.download_srpm(pkg)
                except:
                    return None
            
            builder.resolver.build_dependency_graph(
                package_info.name,
                str(srpm),
                srpm_resolver=srpm_resolver
            )
            
            build_chain = builder.resolver.get_build_chain()
            
            if build_chain:
                print(f"\nBuild order ({sum(len(l) for l in build_chain)} packages):")
                for level_idx, level in enumerate(build_chain):
                    print(f"  Level {level_idx + 1}: {', '.join(level)}")
            else:
                print("\nNo additional dependencies to build")
        
        return 0
    
    try:
        if no_deps:
            task = builder.build_package(str(srpm), wait=not nowait)
            result = BuildResult(
                success=task.status == BuildStatus.COMPLETE,
                tasks=[task],
                built_packages=[task.package_name] if task.status == BuildStatus.COMPLETE else [],
                failed_packages=[task.package_name] if task.status != BuildStatus.COMPLETE else [],
            )
        else:
            result = builder.build_with_deps(str(srpm))
        
        print_build_result(result)
        
        return 0 if result.success else 1
        
    except VibeBuildError as e:
        logging.error(f"Build failed: {e}")
        return 1
    except Exception as e:
        logging.exception(f"Unexpected error: {e}")
        return 1


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    opts = parser.parse_args(args)
    
    setup_logging(opts.verbose, opts.quiet)
    
    if opts.analyze_only:
        if not opts.srpm:
            parser.error("--analyze-only requires SRPM path")
        return cmd_analyze(
            opts.srpm,
            opts.server,
            opts.build_tag,
            opts.cert,
            opts.serverca
        )
    
    if opts.download_only:
        if not opts.srpm:
            parser.error("--download-only requires package name")
        return cmd_download(opts.srpm, opts.download_dir)
    
    if not opts.target or not opts.srpm:
        parser.error("TARGET and SRPM are required for building")
    
    return cmd_build(
        target=opts.target,
        srpm_path=opts.srpm,
        server=opts.server,
        web_url=opts.web_url,
        cert=opts.cert,
        serverca=opts.serverca,
        build_tag=opts.build_tag,
        scratch=opts.scratch,
        nowait=opts.nowait,
        no_deps=opts.no_deps,
        download_dir=opts.download_dir,
        dry_run=opts.dry_run,
    )


if __name__ == '__main__':
    sys.exit(main())
