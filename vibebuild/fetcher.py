"""
SRPM fetcher - downloads source RPMs from Fedora and other sources.
"""

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from vibebuild.exceptions import SRPMNotFoundError, VibeBuildError


@dataclass
class SRPMSource:
    """Configuration for an SRPM source."""
    name: str
    base_url: str
    koji_server: Optional[str] = None
    priority: int = 100


class SRPMFetcher:
    """
    Fetches SRPMs from various sources.
    
    Primary source is Fedora's Koji, but can also use
    src.fedoraproject.org and other mirrors.
    """
    
    DEFAULT_SOURCES = [
        SRPMSource(
            name="fedora-koji",
            base_url="https://kojipkgs.fedoraproject.org/packages",
            koji_server="https://koji.fedoraproject.org/kojihub",
            priority=10
        ),
        SRPMSource(
            name="fedora-src",
            base_url="https://src.fedoraproject.org/rpms",
            priority=20
        ),
    ]
    
    def __init__(
        self,
        download_dir: Optional[str] = None,
        sources: Optional[list[SRPMSource]] = None,
        fedora_release: str = "rawhide"
    ):
        self.download_dir = Path(download_dir) if download_dir else Path(tempfile.gettempdir()) / "vibebuild"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.sources = sorted(sources or self.DEFAULT_SOURCES, key=lambda s: s.priority)
        self.fedora_release = fedora_release
        self._cache: dict[str, str] = {}
    
    def download_srpm(self, package_name: str, version: Optional[str] = None) -> str:
        """
        Download SRPM for a package.
        
        Tries each configured source until SRPM is found.
        
        Args:
            package_name: Name of the package
            version: Optional specific version to download
            
        Returns:
            Path to downloaded SRPM file
            
        Raises:
            SRPMNotFoundError: If SRPM cannot be found in any source
        """
        cache_key = f"{package_name}-{version or 'latest'}"
        if cache_key in self._cache:
            cached_path = self._cache[cache_key]
            if Path(cached_path).exists():
                return cached_path
        
        errors = []
        
        for source in self.sources:
            try:
                if source.koji_server:
                    srpm_path = self._download_from_koji(package_name, version, source)
                else:
                    srpm_path = self._download_from_src(package_name, version, source)
                
                self._cache[cache_key] = srpm_path
                return srpm_path
                
            except Exception as e:
                errors.append(f"{source.name}: {str(e)}")
                continue
        
        raise SRPMNotFoundError(
            f"Could not find SRPM for {package_name}: {'; '.join(errors)}"
        )
    
    def _download_from_koji(
        self,
        package_name: str,
        version: Optional[str],
        source: SRPMSource
    ) -> str:
        """Download SRPM using koji CLI."""
        cmd = ["koji", f"--server={source.koji_server}"]
        
        if version:
            cmd.extend(["download-build", "--type=src", f"{package_name}-{version}"])
        else:
            result = subprocess.run(
                ["koji", f"--server={source.koji_server}",
                 "latest-build", "--type=src", f"f{self.fedora_release.replace('rawhide', '42')}", package_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                result = subprocess.run(
                    ["koji", f"--server={source.koji_server}",
                     "latest-build", "--type=src", "rawhide", package_name],
                    capture_output=True,
                    text=True
                )
            
            if result.returncode != 0 or not result.stdout.strip():
                raise SRPMNotFoundError(f"Package {package_name} not found in Koji")
            
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if package_name in line:
                    nvr = line.split()[0]
                    cmd.extend(["download-build", "--type=src", nvr])
                    break
            else:
                raise SRPMNotFoundError(f"Could not parse Koji output for {package_name}")
        
        download_path = self.download_dir / package_name
        download_path.mkdir(parents=True, exist_ok=True)
        
        result = subprocess.run(
            cmd,
            cwd=str(download_path),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise SRPMNotFoundError(f"Failed to download: {result.stderr}")
        
        srpms = list(download_path.glob("*.src.rpm"))
        if not srpms:
            raise SRPMNotFoundError(f"No SRPM found after download for {package_name}")
        
        return str(srpms[0])
    
    def _download_from_src(
        self,
        package_name: str,
        version: Optional[str],
        source: SRPMSource
    ) -> str:
        """Download spec and sources from src.fedoraproject.org."""
        if not HAS_REQUESTS:
            raise VibeBuildError("requests library required for src.fedoraproject.org")
        
        spec_url = f"{source.base_url}/{package_name}/raw/{self.fedora_release}/f/{package_name}.spec"
        
        response = requests.get(spec_url, timeout=30)
        if response.status_code != 200:
            raise SRPMNotFoundError(f"Spec not found at {spec_url}")
        
        spec_content = response.text
        
        work_dir = self.download_dir / package_name / "build"
        work_dir.mkdir(parents=True, exist_ok=True)
        
        spec_path = work_dir / f"{package_name}.spec"
        spec_path.write_text(spec_content)
        
        sources = self._extract_sources(spec_content)
        sources_dir = work_dir / "SOURCES"
        sources_dir.mkdir(exist_ok=True)
        
        for source_file in sources:
            if source_file.startswith(('http://', 'https://', 'ftp://')):
                self._download_file(source_file, sources_dir / Path(source_file).name)
            else:
                lookaside_url = f"https://src.fedoraproject.org/lookaside/pkgs/{package_name}/{source_file}"
                try:
                    self._download_file(lookaside_url, sources_dir / source_file)
                except Exception:
                    pass
        
        result = subprocess.run(
            ["rpmbuild", "-bs",
             "--define", f"_topdir {work_dir}",
             "--define", f"_sourcedir {sources_dir}",
             "--define", f"_srcrpmdir {work_dir}",
             str(spec_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise VibeBuildError(f"Failed to build SRPM: {result.stderr}")
        
        srpms = list(work_dir.glob("*.src.rpm"))
        if not srpms:
            raise SRPMNotFoundError(f"No SRPM created for {package_name}")
        
        return str(srpms[0])
    
    def _extract_sources(self, spec_content: str) -> list[str]:
        """Extract source URLs from spec content."""
        sources = []
        pattern = re.compile(r'^Source\d*:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
        
        for match in pattern.finditer(spec_content):
            source = match.group(1).strip()
            sources.append(source)
        
        return sources
    
    def _download_file(self, url: str, dest: Path) -> None:
        """Download a file from URL."""
        if not HAS_REQUESTS:
            subprocess.run(
                ["curl", "-L", "-o", str(dest), url],
                check=True,
                timeout=300
            )
            return
        
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    
    def search_fedora_src(self, name: str) -> list[str]:
        """
        Search for packages in Fedora src.
        
        Args:
            name: Package name or pattern
            
        Returns:
            List of matching package names
        """
        if not HAS_REQUESTS:
            result = subprocess.run(
                ["koji", "--server=https://koji.fedoraproject.org/kojihub",
                 "search", "package", f"*{name}*"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.strip().split('\n') if line]
            return []
        
        url = f"https://src.fedoraproject.org/api/0/projects?pattern=*{name}*&namespace=rpms"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return [p['name'] for p in data.get('projects', [])]
        except Exception:
            pass
        
        return []
    
    def get_package_versions(self, package_name: str) -> list[str]:
        """Get available versions for a package."""
        result = subprocess.run(
            ["koji", "--server=https://koji.fedoraproject.org/kojihub",
             "list-builds", "--package", package_name, "--quiet"],
            capture_output=True,
            text=True
        )
        
        versions = []
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line:
                    nvr = line.split()[0]
                    parts = nvr.rsplit('-', 2)
                    if len(parts) >= 2:
                        versions.append(parts[-2])
        
        return list(set(versions))
    
    def clear_cache(self) -> None:
        """Clear downloaded SRPM cache."""
        self._cache.clear()
    
    def cleanup(self) -> None:
        """Remove all downloaded files."""
        import shutil
        if self.download_dir.exists():
            shutil.rmtree(self.download_dir)
        self._cache.clear()
