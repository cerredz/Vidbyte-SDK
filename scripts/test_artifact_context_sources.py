"""Context Protocol Header

Description:
    Standalone verification script for the vidbyte/sources artifact-context-source layer.
Purpose:
    Exercises the manual/QA cases from the design doc end to end, fully offline, and exits
    non-zero on any failure so it can gate CI or a local check.
Architecture:
    - check(): Assertion helper printing PASS/FAIL.
    - main(): Runs index-only, expansion+determinism, https-only, and pin-integrity scenarios.
Relations:
    Imports the public vidbyte.sources surface.
"""

from __future__ import annotations

import sys

from vidbyte.lib.errors import SourcePinMismatchError, SourceSecurityError
from vidbyte.sources import (
    ArtifactRef,
    DocumentSource,
    InMemoryFetcher,
    LlmsTxtSource,
    Selection,
    UrlAllowlist,
    sha256_hex,
)

_INDEX = b"""# Demo

> Demo summary.

## Docs

- [Quickstart](https://ex.com/quick.md): Start here
- [Guide](https://ex.com/guide.md)

## Optional

- [Changelog](https://ex.com/changelog.md)
"""

_FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    # Records and prints the outcome of one verification case.
    status = "PASS" if condition else "FAIL"
    if not condition:
        _FAILURES.append(name)
    print(f"[{status}] {name}")


def _fetcher() -> InMemoryFetcher:
    return InMemoryFetcher(
        {
            "https://ex.com/llms.txt": _INDEX,
            "https://ex.com/quick.md": b"# Quickstart\nstart",
            "https://ex.com/guide.md": b"# Guide\nguide",
            "https://ex.com/changelog.md": b"# Changelog\nv1",
        }
    )


def _source(**kwargs) -> LlmsTxtSource:
    kwargs.setdefault("fetcher", _fetcher())
    kwargs.setdefault("allowlist", UrlAllowlist(allowed_hosts=frozenset({"ex.com"})))
    return LlmsTxtSource(**kwargs)


def main() -> int:
    # Case 1: a docs index must NOT dump bodies into context by default.
    index_only = _source().load(ArtifactRef(url="https://ex.com/llms.txt"))
    check("index-only by default (1 item)", len(index_only.items) == 1)
    check("index lists links", "https://ex.com/quick.md" in index_only.items[0].content)
    check("index is labeled untrusted", index_only.items[0].metadata.get("trust") == "untrusted-external")

    # Case 2: expansion is deterministic and namespaced.
    first = _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))
    second = _source().load(ArtifactRef(url="https://ex.com/llms.txt"), selection=Selection(expand=True))
    check("expand emits index + non-optional links", len(first.items) == 3)
    check(
        "expansion is deterministic",
        [item.document_id for item in first.items] == [item.document_id for item in second.items],
    )
    check("optional excluded by default", all("changelog" not in item.document_id for item in first.items))

    # Case 3: http:// is rejected (trust boundary).
    try:
        DocumentSource(fetcher=InMemoryFetcher({"http://ex.com/x.md": b"# x"})).load(ArtifactRef(url="http://ex.com/x.md"))
        check("http rejected", False)
    except SourceSecurityError:
        check("http rejected", True)

    # Case 4: a tampered pinned artifact fails closed.
    data = b"# Doc\nbody"
    try:
        DocumentSource(fetcher=InMemoryFetcher({"https://ex.com/x.md": data})).load(
            ArtifactRef(url="https://ex.com/x.md", expected_hash=sha256_hex(data + b"tamper"))
        )
        check("pin mismatch fails closed", False)
    except SourcePinMismatchError:
        check("pin mismatch fails closed", True)

    if _FAILURES:
        print(f"\n{len(_FAILURES)} failure(s): {', '.join(_FAILURES)}")
        return 1
    print("\nAll verification cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
