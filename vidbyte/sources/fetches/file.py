"""Context Protocol Header

Description:
    Defines a local-file source fetcher.
Purpose:
    Supports deterministic vendored artifact snapshots or local documentation fixtures without
    adding a network dependency.
Architecture:
    - FileFetcher: Reads file:// URLs or paths relative to an optional root.
Relations:
    Can be injected into Source when callers explicitly allow file-based artifacts.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from vidbyte.lib.dataclasses.sources import FetchResponse
from vidbyte.lib.errors import SourceFetchError


class FileFetcher:
    """Fetches source bytes from local files."""

    def __init__(self, root: str | Path | None = None, *, content_type: str = "text/markdown") -> None:
        # Records an optional root for relative paths.
        self._root = Path(root).resolve() if root is not None else None
        self._content_type = content_type

    def fetch(self, url: str) -> FetchResponse:
        # Reads bytes from a file URL or path and wraps filesystem errors as SourceFetchError.
        path = self._resolve_path(url)
        try:
            return FetchResponse(status_code=200, body_bytes=path.read_bytes(), content_type=self._content_type)
        except OSError as exc:
            raise SourceFetchError("Failed to fetch local source artifact.", details={"url": url, "path": str(path)}) from exc

    def _resolve_path(self, url: str) -> Path:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            raw_path = unquote(parsed.path)
            if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
                raw_path = raw_path[1:]
            return Path(raw_path).resolve()
        path = Path(url)
        if not path.is_absolute() and self._root is not None:
            path = self._root / path
        return path.resolve()


__all__ = [
    "FileFetcher",
]
