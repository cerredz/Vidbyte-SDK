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
    """Scheme + optional host allowlist enforced before every fetch and on the final URL after redirects."""

    allowed_schemes: tuple[str, ...] = ("https",)
    allowed_hosts: frozenset[str] | None = None

    def __post_init__(self) -> None:
        # @intent name-lists-reject-bare-strings
        # @intent url-allowlist-never-substring-matches
        # A bare string would turn check()'s `in` into a substring test ("http" in "https"),
        # so the allowlist would fail open; refuse it here instead.
        for field_name, value, example in (
            ("allowed_schemes", self.allowed_schemes, 'scheme names (e.g. ("https",))'),
            ("allowed_hosts", self.allowed_hosts, 'host names (e.g. frozenset({"docs.example.com"}))'),
        ):
            if isinstance(value, (str, bytes)):
                raise SourceSecurityError(
                    f"UrlAllowlist.{field_name} must be a collection of {example}, not a single string.",
                    details={"field": field_name, "value": value},
                )
        # @intent url-allowlist-config-is-case-insensitive
        # Schemes and hosts are case-insensitive (RFC 3986) and check() lowercases the URL side, so store the
        # configured names lowercased too; otherwise a policy spelled "Docs.Acme.dev" or "HTTPS" refuses every URL.
        object.__setattr__(self, "allowed_schemes", tuple(scheme.lower() for scheme in self.allowed_schemes))
        if self.allowed_hosts is not None:
            object.__setattr__(self, "allowed_hosts", frozenset(host.lower() for host in self.allowed_hosts))

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
