# Design Doc — SourceContext / SourceTool (PR #429 rework)

## 1. Overview

Replace PR #429 (`Sources` access layer on `feat/sources-access-layer`) with a
smaller feature that does the same two jobs: load an external resource into
agent context, and give an agent tools scoped to an external resource. The
public surface is two classes, `SourceContext` and `SourceTool`, each taking
one plain dictionary as its first positional argument (provider credentials
plus resource address, including the external provider's `api_key` passed
directly) with every other parameter keyword-only. `SourceContext(...).load()`
is async and returns `list[DocumentContextItem]`; `SourceTool(...).build()` is
sync and returns `list[BaseTool]`. Both lists attach directly to the existing
`Agent(..., context_items=..., tools=...)` constructor with no `Agent` change.
A working GitHub provider ships with the feature: PR content loads into
context, and repository-scoped file/search tools bind one repository in a
construction-time closure. The connection registry, credential broker,
multi-selection resolver, load modes, report framework, and returned permission
policy from PR #429 are removed, not wrapped.

## 2. Goals / Non-Goals

Goals:

- Provide `SourceContext` (fetch one resource into context items under a
  `max_tokens` budget) and `SourceTool` (build repo-scoped tools under a
  `max_output_bytes` per-response bound) as the only public entry points.
- Accept credentials as a direct `api_key` string inside the input dictionary;
  hold it in memory on a provider client, send it as an Authorization header,
  and never persist, register, or log it.
- Ship a real GitHub implementation proving both paths end to end against the
  existing `Agent`, using only the existing `HttpTransport`, `DocumentContextItem`,
  `BaseTool`/`ToolResult`, and error hierarchy.
- Enforce resource scope where the provider HTTP request is built, with tests
  that attempt cross-resource access through the tool (not just metadata).
- Keep every reusable edge-case fix found in PR #429 self-critique (response
  byte accounting with truncation, token-budget marker accounting, zero-arg
  `super()` avoidance under `slots=True`).

Non-goals (N/A — nothing further excluded beyond the list below):

- No concrete providers beyond GitHub; no `Sources.from_urls()` / manifest
  loading; no CLI `connections login` / `context add` wiring; no
  refresh-token flow (`REAUTH` surfaces as a failed result, caller retries).
- No multi-selection batching, partial-success policy, or aggregate report.
- No returned `permission_policy`; the agent's existing permission policy and
  tool-internal scope enforcement cover authorization.
- No changes to `Agent`, `BaseAgent`, `vidbyte/sources/` (llms.txt layer), or
  the `vidbyte/tools/` execution pipeline.

## 3. Background

PR #429 added `vidbyte/integrations/` with `Sources`, `SourcesResolver`,
`ResolvedSources`, `ConnectionRegistry`, `CredentialResolver`,
`ConnectionBroker`, `ResourceSelection`, `LoadMode` (`LOAD`/`TOOLS`/`HYBRID`),
an empty public adapter registry, `SourcesReport`, `ResourceScopePolicy`, and
supporting dataclass/enum/constant/error modules — all with no concrete
provider, so the abstraction never demonstrated the requested developer
experience. The "pr 429 rework" review (Codex thread `01a08d39`, 2026-09-10,
whose last response is the source of truth for this refactor) found that the
requested API — two objects each taking one dictionary plus keyword options —
needs none of that machinery: there is no `mode` (using both objects gives
both behaviors), no connection nickname or credential store (the external
provider key is passed directly to a provider client), and no multi-selection
report (one resource per object fails loudly or truncates explicitly). The
prior answer's mistake was proposing fake "default" connections and temporary
registries underneath the new API; this doc designs the machinery away.

Repo facts constraining placement: `lint/rules/a006_directed_dependency_graph.py`
classifies `vidbyte.sources` as lower-layer (may not import `vidbyte.tools` or
`vidbyte.context`), while `vidbyte/integrations/` does not exist on `main` and
is unclassified, so the new layer lives there and may depend on both. The
field guide requires strict validated dataclasses owning constructor rules
(`strict-config-dataclasses.md`), full `DIAGNOSTIC_FIELDS` packets on new error
classes (`blocking-lint-invariants.md`, A003 ratchet), and `PYTHONPATH=$(pwd)`
for the source CI stage in worktrees (`local-ci-verification.md`).

## 4. Requirements

1. `SourceContext(source: dict, *, max_tokens: int = 20000).load() -> list[DocumentContextItem]`
   fetches one resource and fits it to the budget.
2. `SourceTool(source: dict, *, max_output_bytes: int = 50000).build() -> list[BaseTool]`
   builds repo-scoped tools synchronously; fetching happens at tool-call time.
3. Input dictionary keys: `provider` (string, currently only `"github"`),
   `api_key` (nonempty string, the external provider's key), `resource`
   (provider-specific address: PR URL for context, repo URL or `owner/repo`
   for tools). Unknown keys are rejected; typos fail at construction.
4. `load()` raises `SourceAccessError` when the content cannot be fetched
   (auth, scope, rate limit, missing resource, transport); truncation is
   marked on items, never silent; auth failure never returns an empty list.
5. Tool execution failures return the SDK's normal failed `ToolResult`;
   per-response output is bounded by `max_output_bytes` (UTF-8 bytes of the
   provider payload, overruns clipped with a marker); provenance metadata
   (provider, resource, operation) rides every result.
6. Scope enforcement holds at HTTP request construction: tools accept only
   repo-relative paths/queries, reject absolute URLs and path escapes, and
   search cannot widen beyond the bound repository. Verified by adversarial
   tests calling the built tools with escape attempts.
7. A GitHub PR load defines its content explicitly: description, diff,
   reviews, and discussion, each as a `DocumentContextItem` carrying source
   URL, revision identifiers where available, and truncation flags.
8. Token budgeting reuses PR #429's character-ratio estimator only if the API
   documents the limit as approximate; the truncation marker counts toward
   the budget. A zero `max_tokens` admits nothing without raising.
9. No token, credential, or provider response body ever enters an exception
   message, diagnostic packet, log line, or report string.
10. `python lint/run.py` passes with no baseline change; source CI stage and
    package stage pass; semgrep typed-mapping policy reports 0 findings.

## 5. High-Level Design

Two thin public classes over one private validated config plus a small
provider factory:

- `SourceContext` validates the dict once into a private frozen
  `SourceConfig`, resolves a provider client from the built-in factory,
  calls `provider.load_context(resource)` for typed raw sections, converts
  them to `DocumentContextItem`s, and fits them through a private
  `ContextAdmission` helper honoring `max_tokens`.
- `SourceTool` validates the same way, resolves the same client, and returns
  three `BaseTool` subclasses (`github_list_files`, `github_read_file`,
  `github_search_code`) closing over the bound `(owner, repo)` and the
  client. Each tool validates its model-supplied arguments, builds the
  GitHub REST URL from the closed-over scope only, and bounds the response
  through `HttpTransport(max_response_bytes=...)` plus a UTF-8 clip pass.
- The GitHub client (`GitHubClient`) wraps the existing `HttpTransport`,
  sends `Authorization: Bearer <api_key>` plus `Accept: application/vnd.github+json`,
  paginates boundedly (`per_page=100`, max 10 pages per call), and maps HTTP
  401/403/404/429/5xx to typed `SourceAccessError` states.
- One resource per object: no resolver loop, no sibling cancellation concern,
  no report aggregation. `load()` raises; tools fail their `ToolResult`.

## 6. Detailed Design

### 6.1 Input validation (`vidbyte/lib/dataclasses/sources.py`, private `SourceConfig`)

- `@dataclass(frozen=True, slots=True)` with fields `provider: SourceProvider`
  (internal enum, currently `GITHUB`), `api_key: str`, `resource: str`,
  `kind: SourceKind` (`PULL_REQUEST` | `REPOSITORY`, derived from resource
  syntax at construction).
- `__post_init__` owns every rule: nonempty `api_key` (no whitespace-only),
  `resource` matching one of `https://github.com/<owner>/<repo>/pull/<n>`,
  `https://github.com/<owner>/<repo>`, or `<owner>/<repo>`; rejects control
  characters. Resource keeps original case; provider string lowercases before
  enum coercion. (Avoids zero-arg `super()` entirely — plain dataclass, no
  inheritance from a slotted base.)
- Public constructors accept the raw dict, check `set(source) <=
  {"provider","api_key","resource"}` raising `ConfigurationError` naming the
  unknown key, coerce, and store only the `SourceConfig`. No
  `ConfigurationError` raise remains in the public classes outside this
  coercion adapter, per the strict-dataclass pattern.

### 6.2 Provider factory (`vidbyte/integrations/providers.py`)

- `SourceProviderClient` protocol: `async load_context(resource) ->
  tuple[LoadedSection, ...]`; `async read_repo_file(owner, repo, path,
  *, max_bytes) -> str`; `async list_repo_files(owner, repo, path, *,
  max_entries) -> str`; `async search_repo_code(owner, repo, query, *,
  max_items) -> str`. `LoadedSection` is a small frozen dataclass
  `(title, source_url, body, revision)` in the same module (private by
  convention, not exported).
- `create_client(config) -> SourceProviderClient` switches on the internal
  enum; today only GitHub. No public registry: adding a provider is a new
  `elif` plus client module, until a second provider proves a registry earns
  its keep.

### 6.3 GitHub client (`vidbyte/integrations/github.py`, class `GitHubClient`)

- Constructed as `GitHubClient(api_key, *, transport=None,
  timeout_seconds=30.0)`; transport injectable for tests. Three public
  methods in 3–5 private helpers each (request building, pagination,
  response mapping, error mapping).
- `load_pull_request(owner, repo, number)`: `GET /repos/{o}/{r}/pulls/{n}`
  (description + head/base SHAs), `GET .../pulls/{n}/reviews` (bounded 3
  pages), `GET .../issues/{n}/comments` (bounded 3 pages), diff via
  `Accept: application/vnd.github.diff` on the pull URL (bounded
  `max_response_bytes=1_000_000`). Returns four `LoadedSection`s; any empty
  section is kept as an explicit empty-body section, not dropped.
- `read_repo_file`: `GET /repos/{o}/{r}/contents/{path}?ref={ref}` with
  base64 decode; `list_repo_files`: same endpoint for a directory (bounded
  200 entries, names only); `search_repo_code`: `GET /search/code?q={q}+repo:{o}/{r}`
  (bounded 20 items, capped 2 pages). Every URL is built from the bound
  scope; the model-supplied `path`/`query` never contributes host, owner, or
  repo segments.
- Error mapping: 401 → `AUTH_REQUIRED`, 403 with `rate limit` body →
  `RATE_LIMITED` else `INSUFFICIENT_SCOPE`, 404 → `RESOURCE_UNAVAILABLE`,
  429 → `RATE_LIMITED`, 5xx/timeout → `TRANSPORT_FAILED`. Messages carry
  provider, resource, and state only.

### 6.4 `SourceContext` (`vidbyte/integrations/source_context.py`)

- `__init__(source: dict, *, max_tokens: int = 20000)` coerces and stores.
  `async load(self)` fetches sections, converts each to
  `DocumentContextItem(source=section.source_url, title=..., content=...,
  document_id=f"github-pr-{n}" or None, metadata={provider, resource,
  revision, truncated})`, then admits through `ContextAdmission(max_tokens)`.
- `ContextAdmission` (in `vidbyte/integrations/budget.py`, adapted from
  PR #429's `ContextAdmissionBudget` including its zero-budget and marker
  accounting): per-item `estimate_tokens = max(1, len(chars) //
  INTEGRATIONS_CHARS_PER_TOKEN)`; admits whole while affordable, truncates
  exactly one boundary item with marker `…[truncated N chars]` counted in
  the budget, skips the rest. Returns `(items, outcome)`; `load()` stamps
  `truncated=True` metadata on the clipped item.

### 6.5 `SourceTool` (`vidbyte/integrations/source_tool.py`)

- `__init__(source: dict, *, max_output_bytes: int = 50000)` requires
  `kind == REPOSITORY` (a PR resource raises `ConfigurationError` naming the
  mismatch). `build(self)` returns the three tools in deterministic order.
- Each tool subclasses `BaseTool`, holds `(client, owner, repo,
  max_output_bytes)` in construction closure, and exposes a `ToolSpec`
  whose parameters are only the model-fillable fields (`path` with default
  `""` for list, required `path` for read, required `query` for search;
  optional `ref` branch omitted from the request URL entirely, in which case
  the GitHub API serves the repository default branch; model-supplied `ref`
  values are limited to `[A-Za-z0-9._/-]{1,64}`). No eager default-branch
  resolution happens at build time, keeping `build()` synchronous and
  side-effect free.
- `execute(call)`: validate path (`posix` normalize, reject absolute,
  `..` escapes above root, empty for read, URLs), validate query (nonempty,
  ≤256 chars, reject `repo:` qualifier which would widen scope), call the
  client (bounded transport), UTF-8 clip to `max_output_bytes` with marker,
  return `ToolResult.success(name, text, metadata={provider, resource,
  operation, truncated})`. Any exception becomes `ToolResult.failure` with
  `error_type` metadata — never raised.
- No `ResourceScopePolicy` is returned. Tool descriptions are 4–5 sentences,
  example-free, per the model-facing tool contract guide.

### 6.6 Errors (reuse `SourceError` / `SourceFetchError`)

No new exception class is added, per the repo's shallow-hierarchy
discipline (reuse an existing type with a clear message). Access failures
raise the existing `SourceFetchError(SourceError)` with structured
`details={"provider", "resource", "state"}` carrying only SDK-authored
metadata — no key material, token, or response body. Constructor shape
problems raise the existing `ConfigurationError`; unclassifiable transport
problems stay `ProviderRequestError`.

### 6.7 Constants and enums

- `vidbyte/lib/constants/sources.py`: `SOURCES_DEFAULT_MAX_TOKENS = 20000`,
  `SOURCES_DEFAULT_MAX_OUTPUT_BYTES = 50000`, `SOURCES_CHARS_PER_TOKEN = 4`,
  `SOURCES_MAX_PATH_CHARS = 512`, `SOURCES_MAX_QUERY_CHARS = 256`,
  `SOURCES_MAX_PAGES = 10`, `SOURCES_TRUNCATION_MARKER = "…[truncated]"`,
  `SOURCES_KNOWN_FIELDS = frozenset({"provider","api_key","resource"})`.
- `vidbyte/lib/enums/sources.py`: `SourceProvider(str, Enum)` with
  `GITHUB`; no `LoadMode`, no `AccessState` republication (states are plain
  strings on the error, matching the codex direction that one-resource
  failures need no framework).

## 7. Data Model Changes

N/A — no persisted state, no migrations, no session/eval schema change. New
in-memory only: private `SourceConfig`, `LoadedSection`, `ContextAdmission`
result tuple, and the two error classes. All are constructed per call and
never stored.

## 8. API Changes

New public API (all additive; `main` has no `vidbyte.integrations`):

```python
from vidbyte import Agent, SourceContext, SourceTool
context_items = await SourceContext({"provider": "github", "api_key": token, "resource": "https://github.com/acme/api/pull/41"}, max_tokens=20000).load()
tools = SourceTool({"provider": "github", "api_key": token, "resource": "https://github.com/acme/api"}, max_output_bytes=50000).build()
agent = Agent(name="reviewer", system_prompt="...", context_items=context_items, tools=tools)
```

`vidbyte/__init__.py` exports `SourceContext`, `SourceTool`. Removed
relative to PR #429 (never on `main`, so no deprecation): `Sources`,
`SourcesResolver`, `ResolvedSources`, `ResourceSelection`, `LoadMode`,
`ConnectionRegistry`, `CredentialResolver`, `ConnectionBroker`,
`SourcesReport`, `ResourceScopePolicy`, adapter registry. PR #429 will be
closed unmerged in favor of the replacement PR.

## 9. File Change Manifest

Create (12):

- `vidbyte/integrations/__init__.py` — export `SourceContext`, `SourceTool`.
- `vidbyte/integrations/README.md` — layer readme with usage and bounds.
- `vidbyte/integrations/source_context.py` — `SourceContext` + load pipeline.
- `vidbyte/integrations/source_tool.py` — `SourceTool` + 3 `BaseTool`s.
- `vidbyte/integrations/providers.py` — client protocol + factory +
  `LoadedSection`.
- `vidbyte/integrations/github.py` — `GitHubClient`.
- `vidbyte/integrations/budget.py` — `ContextAdmission`, byte-clip helper.
- `vidbyte/lib/dataclasses/sources.py` — private `SourceConfig`.
- `vidbyte/lib/enums/sources.py` — `SourceProvider`.
- `vidbyte/lib/constants/sources.py` — bounds and defaults.
- `tests/test_source_context_tools.py` — Section 10 suite.
- `scripts/test-source-context-tools.py` — verification script.

Modify (6):

- `vidbyte/__init__.py` — export the two classes.
- `README.md` — one Layer Guide table row for `vidbyte.integrations`.
- `vidbyte/lib/constants/__init__.py`, `vidbyte/lib/enums/__init__.py`,
  `vidbyte/lib/dataclasses/__init__.py` — re-export the new substrate names.
- `lint/baseline.json` — tighten the S051 ratchet after ruff-canonical import
  ordering (improvement only, no allowance raised).

Delete (0): `vidbyte/integrations/` does not exist on `main`; PR #429 branch
files are abandoned by closing the PR, not deleted.

Totals: 12 create, 6 modify, 0 delete.

## 10. Testing Plan

Every case runs in `scripts/test-source-context-tools.py` against injected
fake transports (no network) plus one Agent-attachment integration test with a
stub runner. Labels: [Edge Case], [Hidden Failure], [Silent Failure],
[Hidden Assumption].

1. [Edge Case] `empty_pr_sections_admit_cleanly` — all four PR sections empty
   bodies: `load()` returns 4 items, no truncation flags, no raise.
2. [Edge Case] `zero_max_tokens_admits_nothing` — `max_tokens=0` returns `[]`
   without raising.
3. [Edge Case] `single_char_over_budget_truncates_boundary_item` — item one
   char over remaining budget is clipped with marker and the marker bytes
   count within budget.
4. [Edge Case] `empty_path_lists_repo_root` — `list_files(path="")` lists
   root; `read_file(path="")` fails validation rather than fetching root.
5. [Edge Case] `unicode_payload_clipped_by_utf8_bytes_not_chars` — multibyte
   body over `max_output_bytes` clips on byte boundary without splitting a
   code point and appends the marker.
6. [Hidden Failure] `expired_token_raises_source_access_error` — 401 maps to
   state `AUTH_REQUIRED` naming provider+resource, message contains no token
   substring.
7. [Hidden Failure] `rate_limit_mid_pagination_reports_transport_state` — page
   2 of reviews returns 429: `load()` raises `SourceAccessError` with
   `RATE_LIMITED`, not a partial list.
8. [Hidden Failure] `transport_timeout_during_tool_call_fails_result` —
   `read_file` with hanging transport returns failed `ToolResult` (no raise),
   metadata carries `error_type`.
9. [Hidden Failure] `unknown_dict_key_rejected_at_construction` —
   `{"resouce": ...}` raises `ConfigurationError` before any network use.
10. [Hidden Failure] `pr_resource_rejected_by_source_tool` — PR URL given to
    `SourceTool` raises `ConfigurationError` naming the kind mismatch.
11. [Silent Failure] `path_escape_attempt_cannot_leave_repo` —
    `read_file(path="../../etc/passwd")` and absolute `/etc/passwd` fail
    validation; assert the fake transport saw zero requests.
12. [Silent Failure] `search_repo_qualifier_rejected` —
    `search_code(query="x repo:other/repo")` fails validation; transport sees
    zero requests and the built URL for a legal query contains exactly the
    bound `repo:owner/repo`.
13. [Silent Failure] `tool_url_ignores_model_supplied_host` — model arguments
    contain no host/owner/repo fields at all (spec parameter names asserted);
    request URL equals the bound-scope URL byte for byte.
14. [Silent Failure] `truncation_marker_counted_in_budget` — admitted token
    total including marker never exceeds `max_tokens` under the estimator.
15. [Silent Failure] `empty_list_not_returned_for_auth_failure` — 401 on the
    first PR request raises; assert result is never `[]`.
16. [Hidden Assumption] `resource_case_preserved` — mixed-case owner/repo
    round-trips byte-identical into request URLs (no lowercasing).
17. [Hidden Assumption] `provider_string_coerced_case_insensitively` —
    `"GitHub"` accepted; `"gitlab"` raises `ConfigurationError`.
18. [Hidden Assumption] `agent_attachment_accepts_both_lists` — items and
    tools attach to a real `Agent` (stub runner, one tool round-trip) and the
    tool executes through the agent's executor path.
19. [Hidden Assumption] `whitespace_api_key_rejected` — `"   "` raises
    `ConfigurationError` without any HTTP attempt.
20. [Hidden Assumption] `second_provider_requires_no_registry_change` —
    factory raises `ConfigurationError("unknown provider")` for unregistered
    names (documents the extension seam without building it).

## 11. Dependencies

Runtime: existing `httpx` (via `HttpTransport`), `pydantic` (tool arg
models via `FunctionTool` path — not needed since tools subclass `BaseTool`
directly; no new dependency). No new third-party packages. Test-only:
`pytest`, `pytest-asyncio` (already in `[dev]`). GitHub REST API v3 shape
assumed for PR/review/comment/diff/contents/search endpoints.

## 12. Rollout

1. Land design doc commit, implement in worktree, verification script green,
   lint + source + package gates green.
2. Close PR #429 unmerged with a pointer comment to the replacement PR.
3. Open replacement PR (base `main`, draft) with this doc as the body.
4. Post-merge: `llms.txt` regenerates on its own cadence (not hand-edited);
   follow-ups (second provider, `from_urls`, CLI wiring, refresh flow) are
   separate PRs against the factory seam.

## 13. Open Questions

1. Should `max_tokens` stay a char-ratio approximation (documented) or adopt
   a tokenizer now? Recommendation: approximate + documented; tokenizer is a
   follow-up once model-specific counting is decided.
2. Should `SourceTool.build()` resolve the repo default branch eagerly (one
   network call at build) or lazily per tool call? Recommendation: lazy with
   per-process cache on the tool; keeps `build()` sync and side-effect free
   as specified.
3. Should `LoadedSection` become a public dataclass later for custom
   providers? Recommendation: keep private until the second provider lands.

## 14. Alternatives Considered

1. **Keep PR #429 and wrap it** (previous answer's approach: default
   connections, credential registries under the new API). Rejected: preserves
   every abstraction the request removed; the "simplification" would be
   naming-only while tests still cover registries, modes, and reports.
2. **Place the feature in `vidbyte/sources/`** (thematically closest).
   Rejected: blocking A006 regression — lower-layer `vidbyte.sources` may
   not import `vidbyte.tools`/`vidbyte.context`, which this feature must.
3. **Return a `permission_policy` from `SourceTool.build()`** (PR #429's
   `ResourceScopePolicy`). Rejected per the rework review: metadata checks
   cannot prove the adapter scoped its HTTP request; scope is instead
   enforced and adversarially tested at request construction, while the
   agent's own policy still governs execution.
4. **Multi-selection batching with `on_failure` report policy**. Rejected:
   with one resource per object there is no sibling to cancel and nothing to
   aggregate; raise-vs-failed-`ToolResult` per path is the whole policy.
5. **Public provider registry developers must populate before using GitHub**.
   Rejected: GitHub must work out of the box; the factory gains extension
   points only when a second provider's real differences are known.
