# Design Doc: Artifact Context Sources (`vidbyte/sources/`)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-28
**Last Updated:** 2026-07-04

## Overview

This feature adds a deterministic source layer that compiles public, machine-readable
documents into the SDK's existing `DocumentContextItem` primitive. The first supported
artifact is `llms.txt`; the reusable leaf loader is a generic markdown/text document
source.

The layer is opt-in, synchronous, stdlib-first, and fail-closed. Network or filesystem
I/O is injected through fetcher protocols, cached snapshots are content-addressed, and
all emitted text is labeled as untrusted external content by metadata and a visible
boundary by default.

## Goals

- Provide a `Source[T]` lifecycle: fetch, pin, parse, emit, cache.
- Keep public value contracts in `vidbyte/lib/dataclasses/sources.py`.
- Keep source policy enums in `vidbyte/lib/enums/sources.py`.
- Keep source constants in `vidbyte/lib/config/sources.py`.
- Keep fetchers under `vidbyte/sources/fetches/`, one implementation per file.
- Keep caches under `vidbyte/sources/cache/`, one implementation per file.
- Keep regex patterns and regex-backed parsing helpers under `vidbyte/sources/regex/`.
- Keep concrete source-to-context-item loaders under `vidbyte/sources/loaders/`.
- Keep package-local modules such as `vidbyte/sources/document.py` and
  `vidbyte/sources/llms_txt/types.py` as compatibility re-export shims.
- Add a repository skill under `skills/sources/SKILL.md` so future source work follows the
  reviewed layout.

## Non-Goals

- No orchestration, scheduling, agent attachment, or context-manager lifecycle.
- No new third-party dependencies.
- No full markdown or HTML AST parsing.
- No private Vidbyte service logic, database access, auth, or internal URLs.
- No root `vidbyte.__init__` export in this PR.

## Package Layout

```text
vidbyte/
|-- sources/
|   |-- __init__.py
|   |-- base.py                  Source[T] lifecycle only
|   |-- security.py              UrlAllowlist
|   |-- _fetch.py                compatibility re-export shim
|   |-- _markdown.py             compatibility helper shim
|   |-- document.py              compatibility loader shim
|   |-- cache/
|   |   |-- __init__.py
|   |   |-- base.py              SnapshotCache protocol
|   |   |-- file.py              FileSnapshotCache
|   |   |-- memory.py            InMemorySnapshotCache
|   |   `-- null.py              NullSnapshotCache
|   |-- fetches/
|   |   |-- __init__.py
|   |   |-- base.py              Fetcher protocol
|   |   |-- chained.py           ChainedFetcher
|   |   |-- file.py              FileFetcher
|   |   |-- hash.py              sha256_hex
|   |   |-- http.py              HttpFetcher
|   |   `-- memory.py            InMemoryFetcher
|   |-- loaders/
|   |   |-- __init__.py
|   |   |-- document.py          DocumentSource
|   |   `-- llms_txt.py          LlmsTxtSource
|   |-- llms_txt/
|   |   |-- __init__.py
|   |   |-- loader.py            compatibility re-export shim
|   |   |-- parser.py            LlmsTxtParser + parse_llms_txt
|   |   `-- types.py             compatibility dataclass shim
|   `-- regex/
|       |-- __init__.py
|       `-- regex.py             SourcesRegex, DocumentRegex, LlmsTxtRegex
`-- lib/
    |-- config/sources.py
    |-- dataclasses/sources.py
    `-- enums/sources.py
```

## Public API

The curated public API is exported from `vidbyte.sources`:

- Lifecycle and contracts: `Source`, `ArtifactRef`, `Selection`, `SourceSnapshot`,
  `SourceResult`, `PinPolicy`.
- Loaders and IR: `DocumentSource`, `MarkdownDocument`, `LlmsTxtSource`,
  `LlmsTxtParser`, `parse_llms_txt`, `LlmsTxtDocument`, `LlmsTxtSection`,
  `LlmsTxtLink`.
- Fetchers: `Fetcher`, `FetchResponse`, `HttpFetcher`, `InMemoryFetcher`,
  `FileFetcher`, `ChainedFetcher`, `sha256_hex`.
- Caches: `SnapshotCache`, `InMemorySnapshotCache`, `FileSnapshotCache`,
  `NullSnapshotCache`.
- Security/regex helpers: `UrlAllowlist`, `SourcesRegex`, `DocumentRegex`,
  `LlmsTxtRegex`.

## Lifecycle

`Source.load(ref, selection=None)` executes the same lifecycle for every concrete loader:

1. Validate the URL with `UrlAllowlist` before I/O.
2. Serve a pinned cache hit when `ref.expected_hash` is available and the cache has it.
3. Fetch bytes through the injected `Fetcher`.
4. Enforce `DEFAULT_SOURCE_MAX_BYTES`.
5. Compute and verify the SHA-256 content hash.
6. Parse raw bytes into a typed IR.
7. Emit deterministic `DocumentContextItem` values.
8. Store the snapshot in the configured cache.

`Source` owns only the lifecycle and shared trust helpers. Dataclasses, enums,
constants, fetchers, caches, regex helpers, and concrete loaders live in their own
modules.

## llms.txt Parsing

`LlmsTxtParser` is the authoritative parser. It decomposes parsing into semantic methods:

- `_decode`
- `_normalize_lines`
- `_skip_blank_lines`
- `_parse_title`
- `_parse_summary`
- `_parse_details`
- `_parse_sections`
- `_parse_section`
- `_parse_section_links`

Regex patterns live in `vidbyte/sources/regex/regex.py` on `LlmsTxtRegex`. The parser
imports those helpers rather than defining regexes locally. `parse_llms_txt()` remains as
a compatibility wrapper.

## Trust Boundary

All fetched bytes are attacker-controlled. Defaults are conservative:

- HTTPS-only `UrlAllowlist`.
- Host allowlisting when callers provide `allowed_hosts`.
- Size cap before parsing.
- UTF-8 parsing fails closed.
- Pin mismatch fails closed.
- `DocumentContextItem.metadata["trust"] == "untrusted-external"`.
- Visible `BEGIN/END UNTRUSTED EXTERNAL CONTENT` boundary unless `label_untrusted=False`.

`FileFetcher` is available for explicit vendored/local workflows only. It requires callers
to opt into `UrlAllowlist(allowed_schemes=("file",))`; the default allowlist still rejects
file URLs.

## Tests

The source test suite is fully offline:

```bash
python -m unittest tests.test_sources_base tests.test_sources_document tests.test_sources_llms_txt
python scripts/test_artifact_context_sources.py
```

Coverage includes pin mismatch, allowlist rejection, userinfo/port host checks, size
guards, warm-cache no-network behavior, live refetching, null/file/memory cache behavior,
chained/file/in-memory fetchers, deterministic IDs, llms parsing failures, optional
section handling, expansion filtering, and untrusted metadata/boundaries.
