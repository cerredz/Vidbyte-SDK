<!--
Context Protocol Header

Description:
    Development rules for the Vidbyte SDK artifact sources layer.
Purpose:
    Keeps future source fetchers, caches, parsers, regex helpers, dataclasses, and
    source-to-context-item loaders aligned with the reviewed package structure.
Architecture:
    - Documents file placement, public exports, parser structure, trust boundaries, and tests.
Relations:
    Complements skills/sdk/SKILL.md and vidbyte/sources/.
-->

# Artifact Sources Skill

Use this skill when adding or changing `vidbyte/sources/`.

## Package Placement

- Put the abstract lifecycle in `vidbyte/sources/base.py`.
- Put URL trust gates in `vidbyte/sources/security.py`.
- Put fetchers in `vidbyte/sources/fetches/`, one fetcher per file.
- Put caches in `vidbyte/sources/cache/`, one cache per file.
- Put regex patterns and regex-backed helpers in `vidbyte/sources/regex/regex.py`.
- Put concrete source-to-context-item loaders in `vidbyte/sources/loaders/`.
- Put source dataclasses in `vidbyte/lib/dataclasses/sources.py`.
- Put source enums in `vidbyte/lib/enums/sources.py`.
- Put source constants in `vidbyte/lib/config/sources.py`.
- Keep package-local `types.py`, old loader modules, and old helper modules as re-export
  shims when a stable import path exists.

## Source Lifecycle

Every concrete source should subclass `Source[T]` and implement only:

- `_parse(snapshot) -> T`
- `_emit(ir, snapshot, ref, selection) -> tuple[DocumentContextItem, ...]`

Do not duplicate fetch, cache, pin, size-guard, or trust-labeling logic inside concrete
loaders. Use `Source._wrap_untrusted_content()` and `Source._untrusted_metadata()` for
emitted external content.

## Fetchers And Caches

- Fetchers implement `Fetcher.fetch(url) -> FetchResponse`.
- Caches implement `SnapshotCache.get(content_hash)` and `put(content_hash, data)`.
- Each fetcher or cache implementation gets its own file and an explicit `__all__`.
- Keep default behavior network-safe: `Source` defaults to `HttpFetcher`, no cache, and an
  HTTPS-only `UrlAllowlist`.
- Add tests for new fetchers/caches even when they are small protocol adapters.

## Regex And Parsers

- Do not define regex patterns inside parser or loader modules.
- Add shared patterns to `vidbyte/sources/regex/regex.py`.
- Wrap pattern usage in semantic classes such as `DocumentRegex` or `LlmsTxtRegex`.
- Parser classes should expose a clean public method, usually `parse()`, and decompose large
  parsing flows into small named private methods.
- Keep compatibility free functions, such as `parse_llms_txt()`, when callers already use
  them.

## Dataclasses, Enums, Constants

- Dataclass definitions belong in `vidbyte/lib/dataclasses/sources.py`.
- Enum definitions belong in `vidbyte/lib/enums/sources.py`.
- Constants belong in `vidbyte/lib/config/sources.py`.
- Package-local type modules should only re-export central dataclasses.
- Update `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/enums/__init__.py`, or
  `vidbyte/lib/config/__init__.py` when adding public contracts.

## Trust Boundary

Treat every fetched artifact as attacker-controlled:

- Validate URLs before fetch.
- Keep HTTPS-only as the default.
- Enforce size limits before parsing.
- Fail closed on pin mismatch, malformed bytes, disallowed schemes/hosts, and malformed
  artifact structure.
- Label emitted `DocumentContextItem` metadata with `trust="untrusted-external"`.
- Keep the visible untrusted-content boundary enabled by default.

## Verification

Run these checks after source changes:

```bash
python -m unittest tests.test_sources_base tests.test_sources_document tests.test_sources_llms_txt
python scripts/test_artifact_context_sources.py
python -m compileall vidbyte/sources vidbyte/lib/dataclasses/sources.py vidbyte/lib/enums/sources.py vidbyte/lib/config/sources.py
```
