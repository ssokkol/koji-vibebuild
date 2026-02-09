"""
Rule-based package name resolver with optional ML fallback.

Resolves virtual RPM dependency names (like python3dist(requests), pkgconfig(glib-2.0),
perl(File::Path)) to real RPM package names, and maps RPM names to possible SRPM names.
"""

import logging
import re
from typing import Optional

from vibebuild.exceptions import NameResolutionError

logger = logging.getLogger(__name__)

# Try to import ML resolver; it may not be installed
try:
    from vibebuild.ml_resolver import MLPackageResolver

    HAS_ML = True
except ImportError:
    HAS_ML = False

# Known RPM system macros for expanding %{...} in dependency names
SYSTEM_MACROS: dict[str, str] = {
    "python3_pkgversion": "3",
    "python3_version": "3.12",
    "python3_version_nodots": "312",
    "__python3": "/usr/bin/python3",
    "python3_sitelib": "/usr/lib/python3.12/site-packages",
    "python3_sitearch": "/usr/lib64/python3.12/site-packages",
    "lua_version": "5.4",
    "ruby_version": "3.2",
    "_prefix": "/usr",
    "_bindir": "/usr/bin",
    "_libdir": "/usr/lib64",
    "_includedir": "/usr/include",
    "_datadir": "/usr/share",
    "_sysconfdir": "/etc",
    "_mandir": "/usr/share/man",
    "_infodir": "/usr/share/info",
    "_localstatedir": "/var",
    "_sharedstatedir": "/var/lib",
}

# Regex patterns for resolving virtual RPM provides to real package names.
# Each entry is (compiled_regex, replacement_function).
PROVIDE_PATTERNS: list[tuple[re.Pattern, callable]] = [
    (
        re.compile(r"^python(\d*)dist\((.+)\)$"),
        lambda m: f"python{m.group(1) or '3'}-{m.group(2)}",
    ),
    (
        re.compile(r"^pkgconfig\((.+)\)$"),
        lambda m: f"{m.group(1)}-devel",
    ),
    (
        re.compile(r"^perl\((.+)\)$"),
        lambda m: f"perl-{m.group(1).replace('::', '-')}",
    ),
    (
        re.compile(r"^rubygem\((.+)\)$"),
        lambda m: f"rubygem-{m.group(1)}",
    ),
    (
        re.compile(r"^npm\((.+)\)$"),
        lambda m: f"nodejs-{m.group(1)}",
    ),
    (
        re.compile(r"^cmake\((.+)\)$"),
        lambda m: f"cmake-{m.group(1).lower()}",
    ),
    (
        re.compile(r"^tex\((.+)\)$"),
        lambda m: f"texlive-{m.group(1)}",
    ),
    (
        re.compile(r"^golang\((.+)\)$"),
        lambda m: f"golang-{m.group(1).replace('/', '-')}",
    ),
    (
        re.compile(r"^mvn\(([^:]+):([^:]+)\)$"),
        lambda m: m.group(2),
    ),
]

# Macro pattern for matching %{macro_name} or %{?macro_name}
_MACRO_PATTERN = re.compile(r"%\{([^}]+)\}")


class PackageNameResolver:
    """
    Resolves RPM dependency names to real package names using rule-based
    pattern matching with optional ML fallback.

    Pipeline: cache -> expand macros -> apply virtual provide patterns -> ML fallback -> original
    """

    def __init__(self, ml_resolver=None):
        """
        Initialize the resolver.

        Args:
            ml_resolver: Optional ML-based resolver instance. If provided and available,
                         it will be used as a fallback when rule-based resolution fails.
        """
        self._cache: dict[str, str] = {}
        self.ml_resolver = ml_resolver

    def resolve(self, dep_name: str) -> str:
        """
        Resolve a dependency name to a real RPM package name.

        Pipeline order:
        1. Check cache
        2. Expand RPM macros
        3. Try virtual provide pattern matching
        4. ML fallback (if available)
        5. Return expanded name as-is

        Args:
            dep_name: The dependency name from a spec file (e.g. "python3dist(requests)")

        Returns:
            Resolved RPM package name (e.g. "python3-requests")
        """
        if not dep_name:
            return dep_name

        # Check cache first
        if dep_name in self._cache:
            return self._cache[dep_name]

        # Step 1: Expand macros
        expanded = self.expand_macros(dep_name)

        # Step 2: Try virtual provide patterns
        resolved = self.resolve_virtual_provide(expanded)
        if resolved is not None:
            self._cache[dep_name] = resolved
            return resolved

        # Step 3: ML fallback if available and name contains parentheses
        # (indicating an unresolved virtual provide)
        if self.ml_resolver and "(" in expanded:
            try:
                ml_result = self.ml_resolver.predict(expanded)
                if ml_result and ml_result != expanded:
                    logger.debug(f"ML resolved '{expanded}' -> '{ml_result}'")
                    self._cache[dep_name] = ml_result
                    return ml_result
            except Exception as e:
                logger.debug(f"ML resolver failed for '{expanded}': {e}")

        # Step 4: Return expanded name as-is
        self._cache[dep_name] = expanded
        return expanded

    def expand_macros(self, name: str) -> str:
        """
        Expand RPM macros in a dependency name using SYSTEM_MACROS.

        Handles %{macro}, %{?macro} (conditional), and bare %macro patterns.

        Args:
            name: Name potentially containing RPM macros

        Returns:
            Name with known macros expanded
        """
        if "%" not in name:
            return name

        def replace_macro(match: re.Match) -> str:
            macro_expr = match.group(1)
            # Handle conditional macros like %{?python3_pkgversion}
            if macro_expr.startswith("?"):
                macro_name = macro_expr[1:]
                # Conditional: if defined, expand; otherwise empty string
                return SYSTEM_MACROS.get(macro_name, "")
            # Handle macros with default values like %{?macro:default}
            if ":" in macro_expr and macro_expr.startswith("?"):
                parts = macro_expr[1:].split(":", 1)
                macro_name = parts[0]
                default = parts[1] if len(parts) > 1 else ""
                return SYSTEM_MACROS.get(macro_name, default)
            return SYSTEM_MACROS.get(macro_expr, match.group(0))

        return _MACRO_PATTERN.sub(replace_macro, name)

    def resolve_virtual_provide(self, name: str) -> Optional[str]:
        """
        Try to resolve a virtual provide name using PROVIDE_PATTERNS.

        Args:
            name: Dependency name that may be a virtual provide
                  (e.g. "python3dist(requests)", "pkgconfig(glib-2.0)")

        Returns:
            Resolved package name, or None if no pattern matched
        """
        for pattern, resolver_fn in PROVIDE_PATTERNS:
            match = pattern.match(name)
            if match:
                return resolver_fn(match)
        return None

    def resolve_srpm_name(self, rpm_name: str) -> list[str]:
        """
        Map an RPM binary package name to possible SRPM (source package) names.

        Many RPM binary packages have different SRPM names. For example:
        - python3-requests (RPM) -> python-requests (SRPM)
        - glib2-devel (RPM) -> glib2 (SRPM)

        Args:
            rpm_name: RPM binary package name

        Returns:
            List of possible SRPM names, ordered by likelihood
        """
        candidates = []

        # Rule: python3-X -> try python-X first, then python3-X
        if rpm_name.startswith("python3-"):
            base = rpm_name[len("python3-"):]
            candidates.append(f"python-{base}")
            candidates.append(rpm_name)

        # Rule: python2-X -> try python-X first
        elif rpm_name.startswith("python2-"):
            base = rpm_name[len("python2-"):]
            candidates.append(f"python-{base}")
            candidates.append(rpm_name)

        # Rule: *-devel -> try without -devel suffix
        elif rpm_name.endswith("-devel"):
            base = rpm_name[: -len("-devel")]
            candidates.append(base)
            candidates.append(rpm_name)

        # Rule: *-libs -> try without -libs suffix
        elif rpm_name.endswith("-libs"):
            base = rpm_name[: -len("-libs")]
            candidates.append(base)
            candidates.append(rpm_name)

        # Rule: perl-X -> same name (SRPM usually matches)
        elif rpm_name.startswith("perl-"):
            candidates.append(rpm_name)

        # Rule: rubygem-X -> rubygem-X (SRPM usually matches)
        elif rpm_name.startswith("rubygem-"):
            candidates.append(rpm_name)

        # Rule: nodejs-X -> nodejs-X
        elif rpm_name.startswith("nodejs-"):
            candidates.append(rpm_name)

        # Rule: golang-X -> golang-X
        elif rpm_name.startswith("golang-"):
            candidates.append(rpm_name)

        # Default: use the name as-is
        else:
            candidates.append(rpm_name)

        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for name in candidates:
            if name not in seen:
                seen.add(name)
                result.append(name)

        return result
