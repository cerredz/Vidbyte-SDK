"""Context Protocol Header

Description:
    Defines URL security gates for artifact sources.
Purpose:
    Keeps source allowlist validation separate from fetcher implementations so all fetchers
    pass through the same trust boundary before I/O.
Architecture:
    - UrlAllowlist: Scheme and optional host allowlist enforced before each source fetch.
Relations:
    Used by Source._fetch_snapshot and re-exported from vidbyte.sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from vidbyte.lib.errors import SourceSecurityError


@dataclass(frozen=True, slots=True)
class UrlAllowlist:
    """Scheme + optional host allowlist enforced before every network call."""

    allowed_schemes: tuple[str, ...] = ("https",)
    allowed_hosts: frozenset[str] | None = None

    def check(self, url: str) -> None:
        # Raises SourceSecurityError when scheme/host are not permitted.
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if not scheme or scheme not in self.allowed_schemes:
            raise SourceSecurityError(
                "URL scheme is not permitted by the allowlist.",
                details={"url": url, "scheme": scheme, "allowed_schemes": list(self.allowed_schemes)},
            )
        host = (parsed.hostname or "").lower()
        if scheme == "file" and self.allowed_hosts is None:
            return
        if not host:
            raise SourceSecurityError("URL is missing a host.", details={"url": url})
        if self.allowed_hosts is not None and host not in self.allowed_hosts:
            raise SourceSecurityError(
                "URL host is not in the allowlist.",
                details={"url": url, "host": host, "allowed_hosts": sorted(self.allowed_hosts)},
            )


__all__ = [
    "UrlAllowlist",
]
