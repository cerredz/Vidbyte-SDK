# Design Doc: Artifact Context Sources (`vidbyte/sources/`)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

This feature adds a new **`Source` / loader primitive layer** to the Vidbyte SDK that
compiles a public, machine-readable remote document into the SDK's existing typed
context primitive, `DocumentContextItem`. The base case is a generic remote
markdown/document URL; the first real loader targets the **`llms.txt`** standard
(Answer.AI) — it fetches an `llms.txt` index, optionally expands its linked markdown
sections, and emits `DocumentContextItem` instances. The whole layer is deterministic
and **pinned-by-content-hash by default**: the same artifact version always produces the
same primitives, with stable IDs and a stable output order. Network access is explicit
and injectable so loaders are fully testable offline, and all fetched content is treated
as attacker-controlled (validated, fail-closed, labeled untrusted, guarded by a URL
allowlist).

This is the **context-layer sibling** of the "public artifact → deterministic harness
piece" pattern (the tools-layer dual being the eve.dev OpenAPI→tools idea). Here the
artifact becomes *context*, not *tools*.

---

## 2. Goals & Non-Goals

### Goals
- Introduce a thin generic substrate `Source[T]` with a fixed lifecycle:
  `fetch(ref) → pin(content_hash) → parse→IR → filter(select/deny) → emit(Primitive[]) → cache`.
- Ship a generic single-document/markdown URL loader (`DocumentSource`) as the base case.
- Ship the first concrete loader, `LlmsTxtSource`, that parses the `llms.txt` standard,
  optionally expands its linked markdown sections, and **emits the existing
  `DocumentContextItem`** (no parallel context type).
- Guarantee determinism: fetch-once, hash-the-bytes, vendor a local snapshot, stable
  content-derived IDs, deterministic/sorted output order. `live` re-fetch is opt-in only.
- Support filtering (allow/deny sections & links by glob) and progressive disclosure
  (compact index by default; on-demand section expansion).
- Parse to a validated typed intermediate representation (IR) and **fail closed** on
  malformed input.
- Enforce a trust boundary: URL allowlist, size limits, untrusted-content labeling,
  injectable/explicit network access.

### Non-Goals
- **No orchestration.** Scheduling fetches, attaching emitted primitives to an agent,
  refreshing on a timer, or wiring into a `ContextManager` lifecycle is harness/cookbook
  territory and is explicitly out of scope. `Source.load()` is a pure-ish call that
  returns primitives; the caller decides what to do with them.
- **No new third-party dependencies.** Parsing uses the stdlib (`hashlib`, `fnmatch`,
  `urllib`, hand-written markdown parsing). No `markdown`, `beautifulsoup4`, or YAML libs.
- **No full markdown/HTML rendering.** We parse `llms.txt` structure (H1/blockquote/H2 +
  link lists) and treat document bodies as opaque text; we do not build an AST of
  arbitrary markdown or interpret front-matter semantics.
- **No async API in v1.** Loaders are synchronous (no subprocess/event-loop concerns like
  MCP has). An async variant is a possible future follow-up.
- **No network IP/DNS-level SSRF resolution.** The allowlist operates on scheme/host
  strings; defense-in-depth IP pinning is called out as a limitation, not implemented.
- **No new tool wrappers.** This is the context (static document) layer, not the tools
  layer. We do not add `BaseTool` subclasses here.

---

## 3. Background & Context

The SDK already exposes a rich set of immutable **context primitives** under
`vidbyte/context/primitives/` (e.g. `DocumentContextItem`, `FileContextItem`,
`TextContextItem`). It also already has an **external-surface attach pattern** for the
*tools* side: `vidbyte/tools/mcp/attach.py` takes an external surface (an MCP server),
discovers its capabilities, wraps/emits them as native `BaseTool` instances, and returns a
handle. There is, however, no equivalent path for turning a **public static document** into
context primitives. Today a developer who wants a docs site or an `llms.txt` index in
context must hand-roll fetching, parsing, and `DocumentContextItem` construction — with no
determinism, caching, filtering, or trust handling.

`llms.txt` (https://llmstxt.org, Answer.AI) is a small, well-specified markdown convention:
a single `# H1` title, an optional `> blockquote` summary, optional free prose, then `##`
sections each containing a bulleted list of markdown links (`- [name](url): notes`), plus a
conventional `## Optional` section whose links may be skipped under tight budgets. It is the
ideal first artifact because it is (a) public and machine-readable, (b) explicitly designed
for LLM context, and (c) naturally supports progressive disclosure (the index lists section
links; bodies are fetched only when needed).

This feature is the **`Source` dual of the MCP attach flow** — a static-document loader that
mirrors `external surface → discover → wrap/emit → handle`, but emits *context primitives*
instead of tools, and is deterministic rather than live by default.

**Constraints / dependencies:**
- SDK invariant: **primitives only**. Loaders + typed IR live here; orchestration does not.
- Dependency budget: stdlib + existing `httpx`/`SyncHttpTransport`; nothing new.
- House style: "Context Protocol Header" module docstrings; `from __future__ import
  annotations`; frozen slotted dataclasses for value types; `Protocol` for injectable
  seams; errors subclass `VidbyteSdkError` under `vidbyte/lib/errors`; one-line signatures
  with a mandatory 1–2 line comment beneath each; sparse inline comments.

---

## 4. Requirements

### Functional Requirements
1. Provide an abstract `Source[T]` base class whose public `load(ref, selection)` method
   executes the lifecycle `fetch → pin → parse → filter → emit → cache` in that order.
2. Provide `ArtifactRef` (the immutable description of what to load: URL, optional pinned
   content hash, pin policy, optional content-type hint).
3. Provide `PinPolicy` with two values: `PINNED` (default — reuse a cached snapshot when its
   hash matches and verify against any expected hash) and `LIVE` (opt-in — always re-fetch).
4. Provide `Selection` (allow globs, deny globs, `expand` flag) and apply it during emit so
   only matching sections/links are emitted.
5. Compute a SHA-256 content hash of the raw fetched bytes; if `ArtifactRef.expected_hash`
   is set and differs, raise `SourcePinMismatchError` (fail closed; emit nothing).
6. Parse fetched bytes into a validated typed IR before emitting; reject malformed input
   with `SourceParseError` rather than emitting partial results.
7. `DocumentSource` (base case) emits **exactly one** `DocumentContextItem` for a single
   remote markdown/text document, with a content-derived stable `document_id`.
8. `LlmsTxtSource` parses the `llms.txt` standard into an `LlmsTxtDocument` IR and always
   emits a compact **index** `DocumentContextItem` (title + summary + section/link listing).
9. `LlmsTxtSource` performs **progressive disclosure**: with `expand=False` (default) it
   emits only the index; with `expand=True` (or a non-trivial allow selection) it fetches
   each selected linked document via the shared fetch substrate and emits one
   `DocumentContextItem` per expanded link.
10. The `## Optional` llms.txt section is flagged `optional=True` in the IR and is excluded
    from expansion by default unless explicitly selected.
11. Every emitted primitive carries a content-derived, deterministic `document_id` and the
    emitted tuple is in a stable, deterministic order (identical bytes ⇒ identical IDs and
    order across runs and machines).
12. Every emitted `DocumentContextItem` is labeled untrusted: `metadata` includes
    `trust="untrusted-external"`, `origin` (URL), `content_sha256`, and `source_kind`; and
    (default-on) the rendered content is wrapped in a clearly delimited untrusted boundary.
13. A `UrlAllowlist` validates every URL before any network call (scheme + optional host
    allowlist); disallowed URLs raise `SourceSecurityError` (fail closed). HTTPS-only by
    default.
14. A configurable `max_bytes` limit rejects oversized responses with `SourceSecurityError`.
15. The fetch transport is an injected `Fetcher` protocol; an `InMemoryFetcher` enables
    fully offline tests; a default `HttpFetcher` wraps the existing `SyncHttpTransport`.
16. The snapshot cache is an injected `SnapshotCache` protocol; an `InMemorySnapshotCache`
    and a `FileSnapshotCache` (vendored local snapshot directory) are provided.
17. New error types subclass `VidbyteSdkError` and are re-exported from
    `vidbyte.lib.errors`.
18. The new package is importable as `vidbyte.sources` with a curated `__all__`.

### Non-Functional Requirements
- **Determinism / reproducibility:** primary quality bar. No timestamps, randomness, or
  dict-ordering dependence may leak into IDs or output order.
- **Security:** treat all fetched bytes as attacker-controlled — validate, bound size,
  fail closed, label untrusted, allowlist URLs. No `eval`, no HTML execution, no following
  of non-allowlisted redirects (redirects to disallowed hosts must fail closed).
- **Testability:** 100% offline-testable via injected fetcher + in-memory cache; no live
  network in unit tests.
- **Performance:** O(n) over document size; expansion fetches are sequential and bounded by
  `max_bytes` and the selection. Pinned loads with a warm cache perform zero network I/O.
- **Observability:** errors carry safe structured `details` (URL, status, hashes) via the
  existing `VidbyteSdkError(details=...)` mechanism. No logging side-channels in v1.
- **Compatibility:** reuse `DocumentContextItem` unchanged; do not modify existing
  primitives or their `to_context_text()` output contract.

---

## 5. High-Level Design

We add a new top-level package `vidbyte/sources/`. At its core is an abstract
`Source[T]` (a `Generic` ABC) implementing the lifecycle as a **template method**:
`load()` composes small, named steps and delegates two IR-specific steps (`_parse`,
`_emit`) to subclasses. The base owns fetch+cache+pin+allowlist+size-guard; subclasses own
"how do I parse these bytes into my IR" and "how do I turn my IR + selection into
`DocumentContextItem[]`". This mirrors how `McpToolBridge.bridge()` owns the generic
discover-and-wrap loop while delegating per-tool specifics.

Data flows end-to-end like this:

```
ArtifactRef ──▶ Source.load()
                  │
                  ├─ _guard_url(ref.url) ───────────▶ UrlAllowlist (scheme/host)   [fail closed]
                  ├─ _fetch_snapshot(ref) ──────────▶ SnapshotCache (hit?) / Fetcher (miss)
                  │                                     └─ size guard (max_bytes)   [fail closed]
                  ├─ _pin(snapshot, ref) ───────────▶ sha256(bytes); verify expected_hash [fail closed]
                  ├─ ir = _parse(snapshot) ─────────▶ typed IR, validated          [fail closed]
                  ├─ items = _emit(ir, ref, sel) ───▶ filter(select/deny) + label untrusted
                  │        (LlmsTxtSource expand ───▶ DocumentSource per selected link)
                  └─ _store(snapshot) ──────────────▶ SnapshotCache.put(hash, snapshot)
                         │
                         ▼
                  SourceResult[T] { ref, snapshot, ir, items: tuple[DocumentContextItem,...] }
```

**Key design decisions:**
- **Synchronous, not async.** Unlike MCP (subprocess + handshake), a document fetch is a
  single request; sync keeps the substrate simple, deterministic, and trivially testable.
- **Template-method ABC, not a free function.** The MCP attach surface is a single free
  function because it has one concrete path. Here we have a family of loaders sharing one
  lifecycle but differing in parse/emit, so an ABC with two abstract hooks is the right
  shape and matches the "class-first, compose named methods" house style.
- **Pinned-by-hash default.** `PinPolicy.PINNED` makes the snapshot the unit of truth: same
  bytes ⇒ same hash ⇒ same IR ⇒ same primitives. `LIVE` is the explicit escape hatch.
- **Index-first progressive disclosure.** `LlmsTxtSource` emits a compact index by default
  and only fans out to section bodies when asked, so a whole docs site never dumps into
  context implicitly.
- **`DocumentSource` is the reusable leaf.** `LlmsTxtSource` expansion calls a
  `DocumentSource` (sharing fetcher/cache/allowlist) to fetch+emit each linked document, so
  there is exactly one fetch/label/ID code path.

Components created (all new): the `vidbyte/sources/` package (`base.py`, `_fetch.py`,
`_markdown.py`, `document.py`, `llms_txt/{__init__,types,parser,loader}.py`,
`__init__.py`). Components modified: `vidbyte/lib/errors/base.py` and
`vidbyte/lib/errors/__init__.py` (add + re-export the `Source*` error family). No deletions.

---

## 6. Detailed Design

### 6.1 `Source[T]` base + shared types

**File(s):** `vidbyte/sources/base.py`
**Type:** New file

#### What it does
Defines the immutable request/result value types (`ArtifactRef`, `PinPolicy`, `Selection`,
`SourceSnapshot`, `SourceResult[T]`) and the abstract `Source[T]` that runs the lifecycle.

#### Interface / API
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Generic, TypeVar

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.sources._fetch import Fetcher, HttpFetcher, SnapshotCache, UrlAllowlist

T = TypeVar("T")

DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB


class PinPolicy(str, Enum):
    """Determines whether a load reuses a pinned snapshot or always re-fetches."""
    PINNED = "pinned"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Immutable description of a remote artifact to load."""
    url: str
    expected_hash: str | None = None
    pin: PinPolicy = PinPolicy.PINNED
    content_type_hint: str | None = None


@dataclass(frozen=True, slots=True)
class Selection:
    """Allow/deny globs plus the progressive-disclosure expand flag."""
    allow: tuple[str, ...] = ("*",)
    deny: tuple[str, ...] = ()
    expand: bool = False

    def matches(self, name: str) -> bool:
        # True when name matches any allow glob and no deny glob (case-insensitive).
        ...

    @property
    def is_trivial(self) -> bool:
        # True when allow is the default "*" with no deny entries (no narrowing requested).
        ...


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Immutable, hashable record of fetched bytes and their content hash."""
    url: str
    raw_bytes: bytes
    content_hash: str
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class SourceResult(Generic[T]):
    """The full deterministic output of one load: snapshot, IR, and emitted primitives."""
    ref: ArtifactRef
    snapshot: SourceSnapshot
    ir: T
    items: tuple[DocumentContextItem, ...]

    @property
    def content_hash(self) -> str:
        # Convenience accessor for the pinned content hash of the loaded artifact.
        ...


class Source(ABC, Generic[T]):
    """Abstract substrate that compiles a remote artifact into context primitives."""

    def __init__(self, *, fetcher: Fetcher | None = None, cache: SnapshotCache | None = None, allowlist: UrlAllowlist | None = None, max_bytes: int = DEFAULT_MAX_BYTES, label_untrusted: bool = True) -> None:
        # Stores injectable seams; defaults to HttpFetcher, no cache, https-only allowlist.
        ...

    def load(self, ref: ArtifactRef, *, selection: Selection | None = None) -> SourceResult[T]:
        # Runs fetch -> pin -> parse -> filter/emit -> cache and returns the result.
        ...

    def _fetch_snapshot(self, ref: ArtifactRef) -> SourceSnapshot:
        # Guards the URL, serves from cache when pinned+warm, else fetches under the size cap.
        ...

    def _pin(self, snapshot: SourceSnapshot, ref: ArtifactRef) -> SourceSnapshot:
        # Verifies the content hash against any expected_hash; fails closed on mismatch.
        ...

    def _store(self, snapshot: SourceSnapshot) -> None:
        # Persists the snapshot in the cache keyed by content hash when a cache is configured.
        ...

    @abstractmethod
    def _parse(self, snapshot: SourceSnapshot) -> T:
        # Parses raw bytes into a validated IR; must raise SourceParseError on malformed input.
        ...

    @abstractmethod
    def _emit(self, ir: T, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Turns the IR + selection into a deterministically ordered tuple of primitives.
        ...
```

#### Logic / Algorithm (`load`)
1. `selection = selection or Selection()`.
2. `snapshot = self._fetch_snapshot(ref)`.
3. `snapshot = self._pin(snapshot, ref)`.
4. `ir = self._parse(snapshot)`.
5. `items = self._emit(ir, ref, selection)`.
6. `self._store(snapshot)`.
7. Return `SourceResult(ref=ref, snapshot=snapshot, ir=ir, items=items)`.

`_fetch_snapshot`:
1. `self._allowlist.check(ref.url)` (raises `SourceSecurityError`).
2. If `ref.pin is PinPolicy.PINNED` and `ref.expected_hash` and the cache holds that hash →
   return the cached snapshot (no network).
3. Else `response = self._fetcher.fetch(ref.url)`; if `len(response.body_bytes) >
   self._max_bytes` → `SourceSecurityError`.
4. Build `SourceSnapshot(url, raw_bytes=response.body_bytes,
   content_hash=sha256_hex(response.body_bytes), content_type=response.content_type)`.

`_pin`:
1. `actual = sha256_hex(snapshot.raw_bytes)` (already on the snapshot; recompute-verify).
2. If `ref.expected_hash` and `actual != ref.expected_hash` → `SourcePinMismatchError`
   (details: url, expected, actual). Emit nothing.
3. Return the snapshot (hash recorded).

`Selection.matches`: lowercase `name`; `allowed = any(fnmatch(name_l, p.lower()) for p in
allow)`; `denied = any(fnmatch(name_l, p.lower()) for p in deny)`; return `allowed and not
denied`.

#### Edge Cases & Error Handling
- Empty body bytes: still hashable (sha256 of `b""`); `_parse` decides whether empty is
  valid (llms.txt parser rejects: no H1 ⇒ `SourceParseError`).
- `expected_hash` set but cache miss + `LIVE` policy: still fetch, then `_pin` verifies.
- Allowlist rejects the URL: raised before any fetch (no partial state, no cache write).
- Size overflow: raised before parse; nothing cached or emitted.
- Cache not configured: `_store` is a no-op; pinned re-loads simply re-fetch (still
  deterministic given identical bytes).

---

### 6.2 Fetch substrate, cache, allowlist, hashing

**File(s):** `vidbyte/sources/_fetch.py`
**Type:** New file

#### What it does
Holds the injectable I/O seams and pure helpers shared by all sources: the `Fetcher`
protocol + two implementations, the `SnapshotCache` protocol + two implementations, the
`UrlAllowlist`, and the `sha256_hex` content-hash helper.

#### Interface / API
```python
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from vidbyte.lib.errors import SourceFetchError, SourceSecurityError


def sha256_hex(data: bytes) -> str:
    # Returns the lowercase hex SHA-256 digest of the given bytes (the canonical pin hash).
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class FetchResponse:
    """Raw transport result: status, body bytes, and optional content type."""
    status_code: int
    body_bytes: bytes
    content_type: str | None = None


class Fetcher(Protocol):
    """Injectable byte-level fetch seam; the only network boundary of the sources layer."""
    def fetch(self, url: str) -> FetchResponse:
        """Fetch the URL and return its raw bytes, or raise SourceFetchError."""


class InMemoryFetcher:
    """Deterministic offline fetcher backed by an in-memory url->bytes mapping (tests)."""
    def __init__(self, responses: Mapping[str, bytes | FetchResponse]) -> None: ...
    def fetch(self, url: str) -> FetchResponse: ...


class HttpFetcher:
    """Default fetcher wrapping the existing SyncHttpTransport.request_bytes."""
    def __init__(self, *, timeout_seconds: float = 30.0, user_agent: str = "vidbyte-sdk-sources/0.1") -> None: ...
    def fetch(self, url: str) -> FetchResponse: ...


class SnapshotCache(Protocol):
    """Injectable content-addressed snapshot store keyed by SHA-256 hash."""
    def get(self, content_hash: str) -> bytes | None: ...
    def put(self, content_hash: str, data: bytes) -> None: ...


class InMemorySnapshotCache:
    """Dict-backed snapshot cache for tests and ephemeral runs."""
    def __init__(self) -> None: ...
    def get(self, content_hash: str) -> bytes | None: ...
    def put(self, content_hash: str, data: bytes) -> None: ...


class FileSnapshotCache:
    """Vendored on-disk snapshot cache: one file per content hash under a root directory."""
    def __init__(self, root: str | Path) -> None: ...
    def get(self, content_hash: str) -> bytes | None: ...
    def put(self, content_hash: str, data: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class UrlAllowlist:
    """Scheme + optional host allowlist enforced before every network call."""
    allowed_schemes: tuple[str, ...] = ("https",)
    allowed_hosts: frozenset[str] | None = None

    def check(self, url: str) -> None:
        # Raises SourceSecurityError when scheme/host are not permitted; returns None when ok.
        ...
```

#### Logic / Algorithm
- `HttpFetcher.fetch`: lazily import `SyncHttpTransport` (avoids importing `httpx` for
  in-memory test runs), call `request_bytes(method="GET", url=url, headers={"user-agent":
  ...})`, translate `ProviderRequestError` → `SourceFetchError` (preserve status + excerpt),
  return `FetchResponse(status_code, raw_bytes, content_type=headers.get("content-type"))`.
- `InMemoryFetcher.fetch`: look up the exact URL; miss ⇒ `SourceFetchError` (status 404-like
  details). A `bytes` value is wrapped as `FetchResponse(200, value, "text/markdown")`.
- `FileSnapshotCache`: filename = `f"{content_hash}.bin"` under `root`; `get` returns file
  bytes or `None`; `put` writes atomically (write temp then replace). `root` created on
  first `put`.
- `UrlAllowlist.check`: `parsed = urlparse(url)`; reject empty scheme/host; scheme not in
  `allowed_schemes` ⇒ raise; if `allowed_hosts is not None` and `parsed.hostname` (lowercased)
  not in it ⇒ raise. Both raise `SourceSecurityError` with safe `details`.

#### Edge Cases & Error Handling
- URL with credentials/userinfo or non-default ports: `urlparse` still yields `hostname`;
  host check uses `hostname` only (ignores port/userinfo) to prevent `user@evil` bypass.
- `http://` URL under default allowlist: rejected (https-only default).
- Cache hash collision: SHA-256 collisions are out of scope; content is addressed by its own
  hash so a "wrong" entry is cryptographically implausible.
- `FileSnapshotCache` partial write / crash: atomic temp-then-replace avoids torn files; a
  missing file ⇒ `get` returns `None` ⇒ clean re-fetch.

---

### 6.3 Shared markdown helpers

**File(s):** `vidbyte/sources/_markdown.py`
**Type:** New file

#### What it does
Tiny stdlib-only helpers shared by `DocumentSource` and the llms.txt parser: extract the
first H1 title, parse a markdown link, and slugify a name for stable IDs.

#### Interface / API
```python
from __future__ import annotations

import re

_LINK_RE = re.compile(r"^\s*-\s*\[(?P<text>[^\]]+)\]\((?P<url>[^)]+)\)\s*(?::\s*(?P<note>.*))?$")
_H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)


def first_h1_title(text: str) -> str | None:
    # Returns the first markdown H1 ("# Title") found, or None when absent.
    ...

def parse_link_bullet(line: str) -> tuple[str, str, str | None] | None:
    # Parses "- [text](url): note" into (text, url, note); returns None if the line is not a link bullet.
    ...

def slugify(name: str, *, max_len: int = 48) -> str:
    # Lowercases, replaces non-alphanumeric runs with hyphens, and trims to a stable slug.
    ...
```

#### Edge Cases & Error Handling
- Link with nested brackets/parens: the conservative regex returns `None` (treated as a
  non-link bullet); the llms.txt parser decides whether that is fatal (see 6.5).
- Title with trailing `#` or markdown: captured verbatim minus surrounding whitespace.
- `slugify` of an all-symbol name: collapses to empty ⇒ falls back to `"item"` so IDs never
  become empty or collide on `""`.

---

### 6.4 `DocumentSource` — generic single-document base case

**File(s):** `vidbyte/sources/document.py`
**Type:** New file

#### What it does
The base-case loader: fetches one remote markdown/text URL and emits exactly one
`DocumentContextItem`. Its IR is a minimal `MarkdownDocument`. `LlmsTxtSource` reuses it to
expand each linked document.

#### Interface / API
```python
from __future__ import annotations

from dataclasses import dataclass

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.sources.base import ArtifactRef, Selection, Source, SourceSnapshot
from vidbyte.sources._markdown import first_h1_title


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Minimal IR for a single fetched document: a title and its raw body text."""
    title: str
    body: str
    url: str


class DocumentSource(Source[MarkdownDocument]):
    """Compiles a single remote markdown/text document into one DocumentContextItem."""

    def _parse(self, snapshot: SourceSnapshot) -> MarkdownDocument:
        # Decodes UTF-8 (fail closed on undecodable bytes) and derives a title from the first H1 or URL.
        ...

    def _emit(self, ir: MarkdownDocument, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Builds exactly one labeled DocumentContextItem with a content-derived stable id.
        ...

    def _build_item(self, ir: MarkdownDocument, snapshot_hash: str) -> DocumentContextItem:
        # Constructs the labeled DocumentContextItem (used directly by LlmsTxtSource expansion).
        ...
```

#### Logic / Algorithm
- `_parse`: `text = snapshot.raw_bytes.decode("utf-8")` inside try/except →
  `SourceParseError` on `UnicodeDecodeError`. `title = first_h1_title(text) or
  snapshot.url`. Return `MarkdownDocument(title, body=text, url=snapshot.url)`.
- `_build_item`: `document_id = f"document:{snapshot_hash[:12]}"`; `content =
  _wrap_untrusted(ir.body, ir.url)` when `label_untrusted` else `ir.body`; `metadata =
  {"trust": "untrusted-external", "origin": ir.url, "content_sha256": snapshot_hash,
  "source_kind": "document"}`; return `DocumentContextItem(source=ir.url, content=content,
  title=ir.title, document_id=document_id, metadata=metadata)`.
- `_emit`: returns `(self._build_item(ir, ref-snapshot-hash),)`. `selection` is accepted for
  signature parity but a single document has nothing to filter (documented).

#### Edge Cases & Error Handling
- Non-UTF-8 body ⇒ `SourceParseError` (fail closed; no lossy decode for primitives).
- Empty body ⇒ valid single item with empty content (a document *can* be empty; the
  llms.txt parser is the one that enforces structure).
- Title fallback to URL guarantees a non-empty title (matches `DocumentContextItem`'s
  `title` default semantics).

---

### 6.5 llms.txt IR types

**File(s):** `vidbyte/sources/llms_txt/types.py`
**Type:** New file

#### Interface / API
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmsTxtLink:
    """A single markdown link inside an llms.txt section."""
    title: str
    url: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LlmsTxtSection:
    """A named H2 section of an llms.txt file containing zero or more links."""
    name: str
    links: tuple[LlmsTxtLink, ...]
    optional: bool = False


@dataclass(frozen=True, slots=True)
class LlmsTxtDocument:
    """Validated IR of a parsed llms.txt file."""
    title: str
    summary: str | None
    details: str | None
    sections: tuple[LlmsTxtSection, ...]
```

---

### 6.6 llms.txt parser

**File(s):** `vidbyte/sources/llms_txt/parser.py`
**Type:** New file

#### What it does
Parses raw `llms.txt` bytes into a validated `LlmsTxtDocument`, failing closed on structural
violations. Pure function over text; no I/O.

#### Interface / API
```python
from __future__ import annotations

from vidbyte.lib.errors import SourceParseError
from vidbyte.sources.llms_txt.types import LlmsTxtDocument, LlmsTxtLink, LlmsTxtSection
from vidbyte.sources._markdown import parse_link_bullet


def parse_llms_txt(raw: bytes, *, url: str) -> LlmsTxtDocument:
    # Decodes and parses llms.txt structure into a validated IR; raises SourceParseError on malformed input.
    ...
```

#### Logic / Algorithm
1. Decode UTF-8 (fail closed → `SourceParseError`).
2. Split into lines. The first non-blank line MUST be a single H1 (`# Title`); otherwise
   `SourceParseError("llms.txt must begin with a single H1 title")`.
3. Optional immediately-following `> summary` blockquote (one or more `>` lines joined) →
   `summary`.
4. Free prose lines up to the first `## ` header → `details` (stripped; `None` if empty).
5. For each `## Section` header: collect subsequent bullet lines until the next `## ` or EOF.
   - A bullet beginning with `- [` MUST parse via `parse_link_bullet`; if it does not,
     raise `SourceParseError` (fail closed — malformed link). Non-link, non-bullet lines
     within a section are ignored as inter-link prose.
   - `optional = name.strip().lower() == "optional"`.
6. Require at least one H1 (already enforced) — sections may be empty (an index with only a
   title+summary is valid).
7. Return the assembled `LlmsTxtDocument` with `sections` as a tuple in document order.

#### Edge Cases & Error Handling
- Two H1s: only the first is the title; a second `# ...` later is treated as prose/detail
  (not fatal) — but a document whose *first* non-blank line is not an H1 is fatal.
- A `- [text](url)` with an empty URL ⇒ `parse_link_bullet` returns a link with empty url;
  parser raises `SourceParseError` (empty link target is malformed).
- Windows `\r\n` line endings: normalized before line processing.
- BOM at start of file: stripped before H1 detection.
- Duplicate section names: preserved as separate sections (document order); IDs disambiguate
  by section index (see 6.7), so no collision.

---

### 6.7 `LlmsTxtSource` loader

**File(s):** `vidbyte/sources/llms_txt/loader.py`
**Type:** New file

#### What it does
The first concrete `Source`: parses `llms.txt` into `LlmsTxtDocument`, always emits a compact
index `DocumentContextItem`, and (on request) expands selected section links into per-link
`DocumentContextItem`s by delegating to a shared `DocumentSource`.

#### Interface / API
```python
from __future__ import annotations

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.sources.base import ArtifactRef, Selection, Source, SourceSnapshot
from vidbyte.sources.document import DocumentSource
from vidbyte.sources.llms_txt.parser import parse_llms_txt
from vidbyte.sources.llms_txt.types import LlmsTxtDocument


class LlmsTxtSource(Source[LlmsTxtDocument]):
    """Compiles an llms.txt index into a compact index primitive plus optional expanded sections."""

    def _parse(self, snapshot: SourceSnapshot) -> LlmsTxtDocument:
        # Delegates to parse_llms_txt; raises SourceParseError on malformed input.
        ...

    def _emit(self, ir: LlmsTxtDocument, ref: ArtifactRef, selection: Selection) -> tuple[DocumentContextItem, ...]:
        # Always emits the index item, then optionally the deterministically ordered expanded items.
        ...

    def _build_index_item(self, ir: LlmsTxtDocument, snapshot_hash: str, url: str) -> DocumentContextItem:
        # Renders title, summary, and a per-section listing of link titles+urls into one item.
        ...

    def _expand_sections(self, ir: LlmsTxtDocument, selection: Selection, parent_hash: str) -> tuple[DocumentContextItem, ...]:
        # Fetches each selected link via a shared DocumentSource and returns sorted expanded items.
        ...

    def _should_expand(self, selection: Selection) -> bool:
        # True when selection.expand is set or a non-trivial allow/deny narrows the link set.
        ...

    def _selected_links(self, ir: LlmsTxtDocument, selection: Selection) -> tuple[tuple[int, int, "LlmsTxtLink"], ...]:
        # Returns (section_index, link_index, link) triples passing the selection, in document order.
        ...
```

#### Logic / Algorithm (`_emit`)
1. `items = [self._build_index_item(ir, snapshot_hash, ref.url)]`.
2. If `self._should_expand(selection)`: `items.extend(self._expand_sections(ir, selection,
   snapshot_hash))`.
3. Return `tuple(items)` — index always first.

`_build_index_item`:
- `document_id = f"llms-txt:{snapshot_hash[:12]}:000-index"` (zero-padded so it sorts first).
- Content: `# {title}` + `> {summary}` + for each section: `## {name}` then `- [title](url)
  — note` lines. This is the **progressive-disclosure index**: link inventory only, no bodies.
- metadata: `{"trust": "untrusted-external", "origin": ref.url, "content_sha256":
  snapshot_hash, "source_kind": "llms_txt", "section_count": len(ir.sections)}`.

`_selected_links`: iterate sections in document order with `enumerate`; skip a section when
`section.optional and not selection-explicitly-allows it`; for each link, qualifying key =
`f"{section.name}/{link.title}"`; include when `selection.matches(section.name)` AND
`selection.matches(qualifying key)` (so both section-level and link-level globs work). Return
triples in `(section_index, link_index)` order.

`_expand_sections`:
- Build one `DocumentSource` sharing `self._fetcher`, `self._cache`, `self._allowlist`,
  `self._max_bytes`, `self._label_untrusted`.
- For each `(s_idx, l_idx, link)`: `child_ref = ArtifactRef(url=link.url, pin=ref.pin)`;
  `result = doc_source.load(child_ref)`; take its single item and **re-stamp** its
  `document_id = f"llms-txt:{parent_hash[:12]}:{s_idx:03d}-{slugify(section.name)}:{l_idx:03d}-{slugify(link.title)}"`
  (re-create the frozen dataclass with the new id + parent linkage metadata
  `metadata["parent"] = parent_hash`, `metadata["section"] = section.name`).
- Sort the resulting list by `document_id` (zero-padded indices ⇒ lexical sort == document
  order) and return as a tuple.

#### Edge Cases & Error Handling
- A section link that fails the allowlist or size guard during expansion: the underlying
  `DocumentSource.load` raises `SourceSecurityError`/`SourceFetchError`. **Default = fail
  closed** (one bad link fails the whole expansion). An opt-in `skip_failed_links: bool`
  constructor flag (default `False`) can downgrade per-link failures to omission for
  resilience; documented and off by default to honor the fail-closed invariant.
- `expand=False` + trivial selection ⇒ only the index item (true progressive disclosure).
- A link URL on a different host than the index: still subject to the same allowlist (so a
  host allowlist must include link hosts, or expansion fails closed — intended).
- Relative link URLs in llms.txt (e.g. `/docs/x.md`): not resolved against the index URL in
  v1 (open question 13.3); a relative URL fails the allowlist/`urlparse` scheme check and
  raises `SourceSecurityError`. Documented limitation.
- Duplicate `(section, link.title)` pairs: disambiguated by `(s_idx, l_idx)` in the ID.

---

### 6.8 Package exports

**File(s):** `vidbyte/sources/__init__.py`, `vidbyte/sources/llms_txt/__init__.py`
**Type:** New files

`vidbyte/sources/__init__.py` re-exports the public surface with a curated `__all__`:
`Source`, `ArtifactRef`, `PinPolicy`, `Selection`, `SourceSnapshot`, `SourceResult`,
`DocumentSource`, `MarkdownDocument`, `LlmsTxtSource`, `LlmsTxtDocument`, `LlmsTxtSection`,
`LlmsTxtLink`, `Fetcher`, `FetchResponse`, `InMemoryFetcher`, `HttpFetcher`, `SnapshotCache`,
`InMemorySnapshotCache`, `FileSnapshotCache`, `UrlAllowlist`, `sha256_hex`. Each module gets
the standard "Context Protocol Header" docstring (Description/Purpose/Architecture/Relations).

> **Top-level export decision:** to limit blast radius on the very large root
> `vidbyte/__init__.py`, v1 does **not** add these to the root namespace; consumers import
> from `vidbyte.sources`. Promoting to the root export is deferred (open question 13.1).

---

### 6.9 Error family

**File(s):** `vidbyte/lib/errors/base.py` (MODIFY), `vidbyte/lib/errors/__init__.py` (MODIFY)
**Type:** Modified

Add, mirroring the existing `McpError` family shape:
```python
class SourceError(VidbyteSdkError):
    """Base class for all artifact-source loader failures."""

class SourceFetchError(SourceError):
    """Raised when fetching a remote artifact fails or returns a non-2xx response."""

class SourcePinMismatchError(SourceError):
    """Raised when fetched content hash does not match the pinned expected hash."""

class SourceParseError(SourceError):
    """Raised when an artifact cannot be parsed into a valid typed IR (fail closed)."""

class SourceSecurityError(SourceError):
    """Raised when a URL is disallowed or a response violates a size/scheme guard."""
```
Then extend the `from vidbyte.lib.errors.base import (...)` block and `__all__` in
`vidbyte/lib/errors/__init__.py` with the five new names (kept alphabetical within the list).

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema. The only "schema" introduced is the in-memory
typed IR (`MarkdownDocument`, `LlmsTxtDocument`/`LlmsTxtSection`/`LlmsTxtLink`) and the value
types (`ArtifactRef`, `Selection`, `SourceSnapshot`, `SourceResult`), all defined in Section
6 as frozen slotted dataclasses. `FileSnapshotCache` writes opaque content-addressed
`{sha256}.bin` files, which are a cache, not a schema (safe to delete; rebuilt on next load).

---

## 8. API Changes

N/A — no HTTP endpoints. This is a library/SDK surface. The public Python API is the
exported classes/functions enumerated in Section 6.8. The only **outbound** network contract
is an HTTP `GET` of the artifact URL (and, on expansion, of each selected link URL) performed
through the injected `Fetcher`; no inbound API is added.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/sources/__init__.py` | Public package surface + `__all__` |
| CREATE | `vidbyte/sources/base.py` | `Source[T]` ABC + `ArtifactRef`/`PinPolicy`/`Selection`/`SourceSnapshot`/`SourceResult` |
| CREATE | `vidbyte/sources/_fetch.py` | `Fetcher`/`HttpFetcher`/`InMemoryFetcher`, `SnapshotCache`/impls, `UrlAllowlist`, `sha256_hex` |
| CREATE | `vidbyte/sources/_markdown.py` | Shared stdlib markdown helpers (H1 title, link bullet, slug) |
| CREATE | `vidbyte/sources/document.py` | `DocumentSource` generic single-document base case + `MarkdownDocument` IR |
| CREATE | `vidbyte/sources/llms_txt/__init__.py` | llms.txt subpackage exports |
| CREATE | `vidbyte/sources/llms_txt/types.py` | `LlmsTxtDocument`/`LlmsTxtSection`/`LlmsTxtLink` IR |
| CREATE | `vidbyte/sources/llms_txt/parser.py` | `parse_llms_txt` fail-closed parser |
| CREATE | `vidbyte/sources/llms_txt/loader.py` | `LlmsTxtSource` (index + progressive expansion) |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `SourceError` family |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Re-export `SourceError` family in import block + `__all__` |
| CREATE | `tests/test_sources_base.py` | Unit tests for substrate (pin, allowlist, size, cache, selection) |
| CREATE | `tests/test_sources_document.py` | Unit tests for `DocumentSource` |
| CREATE | `tests/test_sources_llms_txt.py` | Unit tests for parser + `LlmsTxtSource` (index/expand/filter) |
| CREATE | `scripts/test_artifact_context_sources.py` | Phase-5 verification script covering every Section 10 case |

No deletions.

---

## 10. Testing Plan

All tests use stdlib `unittest` (the repo's convention — see `tests/test_mcp_attachment.py`)
with an `InMemoryFetcher` and `InMemorySnapshotCache`; **zero live network**. The
`InMemoryFetcher` is the injection seam equivalent to the MCP tests' `MockMcpStdioTransport`.

### Unit Tests

**`tests/test_sources_base.py` — substrate**
- `test_pin_mismatch_fails_closed` — `expected_hash` differs from fetched bytes ⇒
  `SourcePinMismatchError`, no items emitted. — [Hidden Assumption] (assumes server returns
  the pinned version)
- `test_allowlist_rejects_http_by_default` — `http://` URL ⇒ `SourceSecurityError` before any
  fetch (assert fetcher never called). — [Hidden Assumption]
- `test_allowlist_rejects_unlisted_host` — host not in `allowed_hosts` ⇒ `SourceSecurityError`.
  — [Edge Case]
- `test_allowlist_ignores_userinfo_and_port` — `https://user@evil.com:8443/...` host-checks
  `evil.com` only (no `user@`/port bypass). — [Silent Failure]
- `test_size_guard_rejects_oversized_body` — body > `max_bytes` ⇒ `SourceSecurityError`,
  nothing cached/emitted. — [Edge Case]
- `test_pinned_warm_cache_does_no_network` — pinned ref with matching cached hash ⇒ fetcher
  `fetch` not invoked. — [Hidden Failure]
- `test_live_policy_always_refetches` — `PinPolicy.LIVE` ⇒ fetcher invoked even with a warm
  cache. — [Hidden Assumption]
- `test_selection_matches_allow_and_deny` — allow `"Docs*"` + deny `"Docs/secret*"` returns
  correct booleans (0/1/N globs). — [Edge Case]
- `test_selection_is_case_insensitive` — `"docs"` matches `"Docs"`. — [Silent Failure]
- `test_sha256_hex_of_empty_bytes` — `sha256_hex(b"")` equals the known constant (stable hash
  contract). — [Edge Case]
- `test_store_noop_without_cache` — no cache configured ⇒ `load` still succeeds, no error. —
  [Edge Case]
- `test_filesnapshotcache_roundtrip_and_atomicity` — `put` then `get` returns identical
  bytes; missing hash ⇒ `None`. — [Edge Case]

**`tests/test_sources_document.py` — DocumentSource**
- `test_emits_single_item_with_stable_id` — two loads of identical bytes ⇒ identical
  `document_id` and content. — [Silent Failure] (catches nondeterministic IDs)
- `test_title_falls_back_to_url_when_no_h1` — body without H1 ⇒ title == URL. — [Edge Case]
- `test_non_utf8_body_fails_closed` — invalid UTF-8 ⇒ `SourceParseError`. — [Hidden Assumption]
- `test_empty_body_emits_empty_content_item` — `b""` ⇒ one item, empty content, valid id. —
  [Edge Case]
- `test_item_is_labeled_untrusted` — metadata has `trust=untrusted-external`, `origin`,
  `content_sha256`, `source_kind=document`; content carries the untrusted boundary. —
  [Hidden Assumption]
- `test_label_untrusted_false_omits_boundary` — `label_untrusted=False` ⇒ raw body, metadata
  still labeled. — [Edge Case]

**`tests/test_sources_llms_txt.py` — parser + loader**
- `test_parse_minimal_index` — H1 + blockquote + one section/one link parses to correct IR. —
  [Edge Case]
- `test_parse_missing_h1_fails_closed` — first non-blank line not an H1 ⇒ `SourceParseError`.
  — [Hidden Assumption]
- `test_parse_malformed_link_fails_closed` — `- [text](` ⇒ `SourceParseError` (no half-load).
  — [Silent Failure]
- `test_parse_empty_link_target_fails_closed` — `- [text]()` ⇒ `SourceParseError`. —
  [Edge Case]
- `test_parse_optional_section_flagged` — `## Optional` ⇒ `section.optional is True`. —
  [Edge Case]
- `test_parse_crlf_and_bom` — `\r\n` endings + leading BOM still parse (title correct). —
  [Hidden Failure]
- `test_parse_duplicate_sections_preserved` — two `## Docs` sections both retained. —
  [Edge Case]
- `test_emit_index_only_by_default` — `expand=False` ⇒ exactly one item (the index); fetcher
  called once (index only). — [Silent Failure] (catches accidental fan-out)
- `test_emit_index_lists_all_links` — index content contains every link URL/title. —
  [Silent Failure] (catches truncated index)
- `test_expand_fetches_and_emits_per_link` — `expand=True` ⇒ index + one item per link, in
  deterministic sorted order; ids zero-padded. — [Edge Case]
- `test_expand_excludes_optional_by_default` — optional-section links not expanded unless
  explicitly allowed. — [Hidden Assumption]
- `test_expand_respects_allow_deny_globs` — allow `"API*"` expands only API-section links. —
  [Edge Case]
- `test_expand_failed_link_fails_closed_by_default` — a link whose host is disallowed ⇒
  whole expansion raises `SourceSecurityError`. — [Hidden Assumption]
- `test_expand_skip_failed_links_when_enabled` — `skip_failed_links=True` ⇒ bad link omitted,
  others emitted. — [Hidden Failure]
- `test_expanded_ids_namespaced_under_parent` — expanded item ids start with
  `llms-txt:{parenthash}:` and carry `metadata["parent"]`. — [Silent Failure]
- `test_deterministic_across_two_loads` — same bytes loaded twice ⇒ byte-identical
  `document_id` list and order. — [Silent Failure]

### Integration Tests
- **End-to-end pinned load with `FileSnapshotCache`** (temp dir): first `load` writes a
  snapshot file; a second `load` of the same pinned ref reads from disk and performs **no**
  fetch (assert via a counting fetcher). Verifies the determinism + caching invariant across
  the real file cache. Silent-failure path guarded: assert the second load's item ids equal
  the first's.
- **llms.txt → expansion → DocumentSource composition**: a single `InMemoryFetcher` holds the
  index URL plus each link URL; assert the emitted set is `index + selected links`, ids are
  namespaced, and order is stable. Hidden assumption surfaced: link hosts must pass the same
  allowlist as the index (test a link on an unlisted host fails closed).
- **Mock vs real:** the `Fetcher` and `SnapshotCache` are always mocked/in-memory; the
  `HttpFetcher`→`SyncHttpTransport` seam is verified only by a thin construction test (no live
  socket) asserting `ProviderRequestError` is translated to `SourceFetchError`.

### Manual / QA Test Cases
1. Given a real public `llms.txt` URL and `LlmsTxtSource(allowlist=UrlAllowlist(allowed_hosts=frozenset({host})))`,
   when `load(ArtifactRef(url))` with default selection, then exactly one index
   `DocumentContextItem` is returned and `to_context_text()` shows title/source/section list —
   [Edge Case: a docs site with many sections must NOT dump bodies into context].
2. Given the same URL with `Selection(expand=True)`, when loaded, then index + per-link items
   are returned in stable order; re-running yields identical `document_id`s — [Silent Failure:
   determinism].
3. Given an `http://` URL (not https), when loaded with defaults, then `SourceSecurityError`
   is raised and nothing is emitted — [Hidden Assumption: trust boundary].
4. Given a tampered artifact (bytes changed) with a pinned `expected_hash`, when loaded, then
   `SourcePinMismatchError` is raised — [Hidden Assumption: pin integrity].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `hashlib` (stdlib) | — | SHA-256 content hashing / pinning | None |
| `fnmatch` (stdlib) | — | Allow/deny glob matching for `Selection` | None |
| `urllib.parse` (stdlib) | — | URL scheme/host parsing for `UrlAllowlist` | None |
| `re` (stdlib) | — | Markdown H1/link parsing | Regex must stay conservative (ReDoS-safe, anchored) |
| `vidbyte.lib.http.transport.SyncHttpTransport` | existing | Default `HttpFetcher` backend (`request_bytes`) | Reuses existing `httpx`/urllib path; lazily imported |
| `vidbyte.context.primitives.documents.DocumentContextItem` | existing | Emission target | Must not be modified; reuse only |
| `vidbyte.lib.errors.VidbyteSdkError` | existing | Error base class | Additive only |
| Remote artifact URL(s) | user-supplied, https | The artifact + (on expand) its link targets | **Attacker-controlled** — mitigated by allowlist, size cap, fail-closed parse, untrusted labeling |

No new entries are added to `pyproject.toml` `dependencies`.

---

## 12. Rollout & Deployment

- **Feature flag:** none. This is additive, opt-in code — nothing runs unless a developer
  imports `vidbyte.sources` and calls `load()`.
- **Breaking change:** none. New package + additive error types. Existing imports and
  `DocumentContextItem` behavior are untouched. Root `vidbyte/__init__.py` is unchanged in
  v1 (see 6.8), so no risk to the large existing export surface.
- **Deployment order:** single package; ships in one PR.
- **Rollback:** delete the `vidbyte/sources/` package and revert the two `lib/errors`
  edits; no data migration, no persisted state beyond a disposable cache directory.

---

## 13. Open Questions

- [ ] **13.1 Root export.** Should `LlmsTxtSource`/`DocumentSource`/`ArtifactRef` be promoted
  into the root `vidbyte/__init__.py` namespace now, or left under `vidbyte.sources` until the
  API stabilizes? (Default: leave under `vidbyte.sources`.)
- [ ] **13.2 Default cache.** Should `Source` default to `InMemorySnapshotCache` (so pinned
  re-loads within a process avoid re-fetch out of the box) or to **no cache** (zero implicit
  side effects, must opt in)? (Default proposed: no cache — explicit is safer for a primitives
  layer.)
- [ ] **13.3 Relative link resolution.** llms.txt files sometimes use relative link URLs.
  v1 fails closed on these (no scheme ⇒ allowlist rejects). Do we want opt-in resolution
  against the index URL's base, or keep relative links unsupported? (Default: unsupported.)
- [ ] **13.4 Untrusted boundary format.** Is metadata labeling sufficient, or must the
  rendered `content` always carry a visible boundary marker (default-on `label_untrusted`)?
  Confirm the exact marker text/format the harness layer expects.
- [ ] **13.5 Content-type enforcement.** Should a non-text/markdown `content-type` hard-fail,
  warn-via-metadata, or be ignored? (Default proposed: record in metadata, do not hard-fail,
  since servers misreport types.)
- [ ] **13.6 `skip_failed_links`.** Is per-link resilience (opt-in, default off) acceptable
  given the fail-closed invariant, or should expansion always be all-or-nothing?

---

## 14. Alternatives Considered

### Alternative 1: A new parallel context type (e.g. `RemoteDocumentContextItem`)
- **What:** Define a bespoke primitive for sourced documents instead of reusing
  `DocumentContextItem`.
- **Why rejected:** The scope explicitly forbids a parallel context type, and
  `DocumentContextItem` already carries `source`/`content`/`title`/`document_id`/`metadata` —
  exactly the fields we need. Reuse keeps emitted primitives interoperable with every existing
  `ContextManager`/window consumer. Trust/provenance live in `metadata`.

### Alternative 2: Free-function loaders (mirror `attach_mcp_server`)
- **What:** Expose `load_llms_txt(ref) -> tuple[DocumentContextItem, ...]` free functions with
  no shared base.
- **Why rejected:** MCP attach has a single concrete path so a free function fits; here we have
  a *family* of loaders sharing one lifecycle (fetch/pin/parse/filter/emit/cache). A
  template-method ABC removes duplication, matches the "class-first, compose 3–5 named methods"
  house style, and makes adding the next loader (OpenAPI, sitemap, RSS) trivial.

### Alternative 3: Async loaders (mirror MCP transports)
- **What:** Make `load` a coroutine using `HttpTransport` (async httpx).
- **Why rejected:** A document fetch is a single request with no subprocess/handshake; sync is
  simpler, fully deterministic, and easier to test offline. Async can be layered later without
  changing the IR or emission contract. (Noted as a future follow-up, not a v1 need.)

### Alternative 4: Add a markdown parsing dependency (`markdown`, `mistune`)
- **What:** Use a real markdown library to build a full AST.
- **Why rejected:** Violates the no-new-deps budget and over-parses. llms.txt structure is a
  tiny, well-defined subset (H1/blockquote/H2 + link bullets) that a conservative, ReDoS-safe
  stdlib parser handles exactly, while keeping fail-closed validation under our control.

### Alternative 5: Live-by-default with optional pinning
- **What:** Fetch fresh every call; let callers opt into pinning.
- **Why rejected:** Inverts the determinism invariant. Pinned-by-hash must be the default so
  the same artifact version always yields the same primitives; `LIVE` is the explicit,
  documented escape hatch.

---

## Summary

- **Files:** 13 created (9 package modules + 3 test files + 1 verification script), 2 modified
  (`lib/errors/base.py`, `lib/errors/__init__.py`), 0 deleted. (The package-module count is 9;
  total CREATE rows including tests/script = 13.)
- **Key risks / open questions:** default cache behavior (13.2), relative-link handling (13.3),
  exact untrusted-boundary format the harness expects (13.4), and whether per-link expansion
  may be resilient vs strictly all-or-nothing (13.6). The trust boundary (allowlist + size cap
  + fail-closed parse + untrusted labeling) and the determinism/pinning model are the two
  highest-stakes areas and are specified in detail above.
- **Invariants honored:** primitives-only (no orchestration); pinned-by-hash determinism with
  opt-in `LIVE`; allow/deny filtering + index-first progressive disclosure; typed IR with
  fail-closed parsing; attacker-controlled-content trust boundary with injectable, offline-
  testable network access.

**Requesting explicit approval of this design before proceeding to implementation (Phase 3+).**
