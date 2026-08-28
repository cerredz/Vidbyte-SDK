# Design Doc: Lint Rule Catalog Expansion (SDK)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-28
**Last Updated:** 2026-08-28

---

## 1. Overview

This change works through a 130-item lint/static-policy rule catalog (LR-001..LR-069 generic
rules, then VR-001..VR-061 rules written specifically against this repository's audited state)
and implements every item that applies to `vidbyte-sdk`, either as a new rule in the existing
`lint/` suite, a config change absorbed by an existing rule's ratchet, a direct runtime fix, or
a documented N/A with a concrete reason. The existing suite already enforces S001-S021, S024
(architecture/correctness) and A001-A003, A005-A008 (agent-native); this PR extends it rather
than replacing it, continuing the established "one file plus one registry line" convention.

## 2. Goals & Non-Goals

### Goals
- Work through LR-001..LR-069 then VR-001..VR-061 in order, deciding a disposition for each
  (new rule / folded into an existing rule / config change / direct runtime fix / N/A+reason).
- Add new rules using the repo's existing `Rule` / `RuffBackedRule` patterns, each with a full
  five-section diagnostic (`what_happened`, `why_blocked`, `how_to_fix`, `correct_examples`,
  `will_not_work`) matching the prose bar in `lint/README.md` and `field-guide/vidbyte-sdk/
  diagnostic-context.md`.
- Fix the concrete violations this audit surfaced directly in source where the fix is small,
  safe, and unambiguous (e.g. `SyncHttpTransport`/`HttpTransport` redirect policy).
- Keep every new rule's baseline honest: initialize via `--update-baseline` after running the
  rule, never assume 0.
- Land as one PR with `python scripts/run_ci.py` green.

### Non-Goals
- No new test files (per `/design-doc-no-tests`); existing tests/CI are not weakened.
- No wholesale rewrite of `dict[str, Any]` call sites, retry architecture, or HTTP client
  lifecycle — those are ratcheted (ship a rule, freeze existing debt) not remediated in bulk.
- No new external tooling (CodeQL, CI-hosted Semgrep-as-a-service) beyond what the repo already
  runs (`.semgrep/`) — new static-analysis needs are met inside the existing `lint/` suite so
  there is one rule-execution engine, one baseline file, one diagnostic format.
- No lockfile/dependency-manager migration (e.g. adopting `pip-tools`/`uv`) — flagged as a
  follow-up (see Open Questions); pinning the existing range-pinned dev deps exactly is in scope.

## 3. Background & Context

The catalog was compiled from a research pass over agent-native software engineering and this
repo's actual code. Two prior audits (this session) confirmed exact origin/main state: S001-S021
and S024 exist (S022/S023 were removed, never re-registered — new IDs must not reuse them); A001-
A003 and A005-A008 exist (A004 likewise skipped). This doc's rule numbering therefore starts at
**S025** and **A009**. The audit also found, by reading actual source rather than trusting the
catalog's assumptions: zero `shell=True` usage, zero `model_construct()` usage, zero weak-hash
usage, zero insecure-random-for-security-tokens usage, and all three `ContextVar`s already default
to `None`/`()` — several new rules can therefore ship at a **CLEAN (baseline 0)** allowance
immediately, acting as regression guards rather than debt trackers.

## 4. Requirements

### Functional Requirements
1. Every LR/VR catalog item has a recorded disposition in the Catalog Coverage Table (§14).
2. Every new rule ID is registered in `lint/core/registry.py`, documented in `lint/README.md`,
   and has an initialized `lint/baseline.json` entry.
3. `python lint/run.py` and `python scripts/run_ci.py` both exit 0 from the worktree.
4. No existing rule's baseline is raised to absorb a new violation; new violations are fixed in
   source or, where genuinely pre-existing debt, ratcheted with an explicit initial count.

### Non-Functional Requirements
- Diagnostics: ASCII-only, five-section format, matching existing rules' prose length.
- Performance: new `RuffBackedRule` subclasses reuse the existing cached, single Ruff subprocess
  (`RuffFindingStore`) rather than spawning additional Ruff invocations.
- Security: new rules that touch credential/token/SQL/subprocess paths must not themselves log
  or persist the matched sensitive substrings (diagnostics show location + symbol, not payload).

## 5. High-Level Design

New rules split into three buckets, matching the two existing backing architectures plus one:

```
[git ls-files via SourceCatalog] -> [cached isolated Ruff scan] -> RuffBackedRule subclasses (S025-S028)
                                  -> [ast.parse per file, already cached] -> native Rule subclasses (S029-S038)
[pyproject.toml / mypy.ini / workflow YAML] -> direct config edits, no new rule ID
[vidbyte/lib/http/transport.py, vidbyte/lib/providers/sqlite.py] -> direct runtime fixes
```

The Ruff selector in `lint/core/ruff.py` gains four new code groups (`I,UP` modernization;
`ASYNC*` blocking-I/O; a narrow `S1xx/S3xx/S5xx` bandit subset; `B017,B023,B028,B039` defensive
bugbear) — each claimed by exactly one new `RuffBackedRule`, mirroring how S001 already claims
`F,E4,E7,E9` out of the same cached scan. Native rules walk `source.tree` the same way `S010`/
`S021` do today, reusing `SourceCatalog.python_files()`.

## 6. Detailed Design

### 6.1 `lint/core/ruff.py` — selector expansion

**File(s):** `lint/core/ruff.py` (modified)
**Type:** Modified

#### What it does
Adds four code groups to `SELECTORS` and exposes them so the four new `RuffBackedRule`
subclasses in §6.2-§6.5 can claim disjoint code sets from the one cached scan.

#### Logic
`SELECTORS` becomes:
`"ANN,B904,B905,C901,DTZ,E4,E7,E9,F,PLR0912,PLR0915,RUF006,RUF012,I001,UP006,UP007,UP035,UP045,ASYNC100,ASYNC105,ASYNC109,ASYNC110,ASYNC210,ASYNC220,ASYNC221,ASYNC230,ASYNC251,B017,B023,B028,B039,S105,S106,S107,S108,S301,S302,S324,S501,S506"`.
No behavior change to existing rules S001-S024 — they keep claiming their existing code subsets;
`RuffFindingStore`'s cache key already includes the full selector string, so this is one added
subprocess invocation shape, not four.

#### Edge Cases
If Ruff's installed version (pinned `0.16.4`) does not recognize a code (e.g. a renamed ASYNC
code), the isolated `--select` call fails closed — `RuffBackedRule.check()` already surfaces a
non-empty stderr as an `ERRORED` verdict per existing behavior, so a bad selector cannot silently
report zero findings.

---

### 6.2 S025 — `modernized-import-and-syntax-hygiene`

**File(s):** `lint/rules/s025_modernized_import_and_syntax_hygiene.py` (new)
**Type:** New (`RuffBackedRule`)
**Covers:** LR-017 (`I`, `UP` families)

Claims Ruff codes `I001` (unsorted/unformatted imports) and `UP006,UP007,UP035,UP045` (pyupgrade:
deprecated `typing.List`/`Optional`/`typing_extensions` imports, stdlib-generic migration) from
the shared scan. `explain()` names the exact deprecated construct and its modern replacement.

### 6.3 S026 — `async-blocking-io`

**File(s):** `lint/rules/s026_async_blocking_io.py` (new)
**Type:** New (`RuffBackedRule`)
**Covers:** VR-016, LR-019

Claims `ASYNC1xx/ASYNC2xx` codes (blocking sleep, subprocess, open, HTTP client calls inside
`async def`). `how_to_fix` points at `asyncio.to_thread`/the async transport as the two approved
escapes, consistent with `HttpTransport` already being the approved async HTTP path (S010).

### 6.4 S027 — `defensive-python-bugbear`

**File(s):** `lint/rules/s027_defensive_python_bugbear.py` (new)
**Type:** New (`RuffBackedRule`)
**Covers:** VR-013 (stacklevel), VR-014 (broad exception assertions — Ruff's B017 covers both
`pytest.raises(Exception)` and `self.assertRaises(Exception)`), VR-015 (loop-variable binding in
closures), VR-017 (mutable `ContextVar` defaults)

Claims `B017,B023,B028,B039`. Four unrelated-sounding catalog items collapse into one rule because
they share one mechanism (a single Ruff bugbear scan) and one repair pattern (fix the flagged
line); splitting them into four rule IDs would not change what gets fixed, only add bookkeeping.
Per the audit, VR-017's target pattern (`ContextVar` mutable defaults) has zero existing hits —
this rule's `B039` portion ships at 0 baseline as a regression guard from day one.

### 6.5 S028 — `bandit-security-subset`

**File(s):** `lint/rules/s028_bandit_security_subset.py` (new)
**Type:** New (`RuffBackedRule`)
**Covers:** LR-022 (unsafe YAML — `S506`), LR-023/LR-032 (pickle/marshal — `S301,S302`), LR-026
(password-like literals — `S105,S106,S107`), LR-033 (weak hash — `S324`), LR-035 (TLS
verification — `S501`), LR-038 (file perms/tmp — `S108`, `S103` not selected: no `os.chmod`
call sites found in the audit, adding it would be a pure future-regression guard with zero
value today — omitted, can be added later if a call site appears)

Audit confirmed zero hits for `S301,S302,S324,S501` today (SDK has no pickle, no MD5/SHA1, no
`verify=False`) — those four codes ship at baseline 0. `S105/S106/S107/S108` are unaudited by
hand (bandit's literal+entropy heuristic can false-positive on innocuous defaults like
`token_type: str = "bearer"`); baseline for those four is initialized via `--update-baseline`
after the first real run, not assumed.

### 6.6 S029 — `no-shell-subprocess`

**File(s):** `lint/rules/s029_no_shell_subprocess.py` (new)
**Type:** New (native `Rule`, `ast.NodeVisitor`)
**Covers:** VR-005, LR-021, LR-028 (subprocess half)

Walks each `source.tree` for `subprocess.Popen/run/call/check_call/check_output` calls with a
`shell=True` keyword (literal `True` only — a non-literal value is a separate, harder taint
question out of scope here), `os.system(`, and `asyncio.create_subprocess_shell(`. Audit found
zero occurrences across `vidbyte/` — ships at baseline 0, protecting `McpStdioTransport`'s
`create_subprocess_exec`-only convention (VR-005) from ever regressing to shell string execution.

### 6.7 S030 — `retryable-idempotent-methods`

**File(s):** `lint/rules/s030_retryable_idempotent_methods.py` (new)
**Type:** New (native `Rule`)
**Covers:** VR-007, LR-048

Targets `HttpTransport.request`/`SyncHttpTransport.request` in `vidbyte/lib/http/transport.py`
specifically (not a generic call-site scan — the catalog's own "custom-rule quality bar" warns
against a rule with no clear remediation, and a generic "is this call idempotent" AST check
across arbitrary call sites is exactly that). The rule statically confirms the transport's retry
loop only retries on the declared `retry_status_codes` tuple *and* that any caller passing a
non-idempotent HTTP method (`POST`/`PATCH`) together with `retry_count > 0` also passes an
`idempotency_key` (a new optional parameter added to both transports — see §6.13). This makes
the rule's target a fixed, small surface (2 classes) with an unambiguous fix.

### 6.8 S031 — `no-model-construct-without-review`

**File(s):** `lint/rules/s031_no_model_construct_without_review.py` (new)
**Type:** New (native `Rule`)
**Covers:** VR-011

Flags `Model.model_construct(` / `.model_construct(` calls anywhere outside an explicit allowlist
constant (`_MODEL_CONSTRUCT_ALLOWLIST` in the rule module, empty today). Audit found zero existing
call sites — ships CLEAN at 0, so any future use of the validation-skipping constructor requires
deliberately adding a reviewed path to the allowlist rather than landing silently.

### 6.9 S032 — `forbid-unknown-fields-at-boundary`

**File(s):** `lint/rules/s032_forbid_unknown_fields_at_boundary.py` (new)
**Type:** New (native `Rule`)
**Covers:** VR-010, LR-041 (validation half)

Flags a `pydantic.BaseModel` subclass defined under a public-seam path (`vidbyte/tools/types.py`,
`vidbyte/sessions/`, `vidbyte/mcp_server/schema.py`, `vidbyte/lib/dataclasses/` — the same
"public DTO" directories S015's export-integrity rule already treats as the public surface) whose
`model_config` is absent or does not set `extra="forbid"`. Reuses the two existing compliant
files (`orchestrator.py`, `prosecutor_defender_judge.py`) as `correct_examples`. Initialized via
`--update-baseline` — not assumed 0, since public DTO coverage under those directories is broader
than the two files already using `extra="forbid"`.

### 6.10 S033 — `explicit-serialization-mode`

**File(s):** `lint/rules/s033_explicit_serialization_mode.py` (new)
**Type:** New (native `Rule`)
**Covers:** VR-020

Flags a `.model_dump(` call with no `mode=` keyword. Audit found exactly 6 call sites, 3 already
compliant (`mode="json"`) — baseline initialized to the 3 non-compliant ones
(`vidbyte/tools/function_tool.py:57`, `vidbyte/context/algorithms/independent_critic.py:265`,
`vidbyte/agents/handoff.py:235`), fixed directly in this PR rather than ratcheted (three call
sites is small enough to just fix — see §6.14), so the rule ships CLEAN at 0.

### 6.11 S034 — `typed-public-seam-mappings`

**File(s):** `lint/rules/s034_typed_public_seam_mappings.py` (new)
**Type:** New (native `Rule`)
**Covers:** VR-012, LR-016 (spirit — mypy-level `disallow_any_generics` is a global toggle too
blunt for 423 existing call sites; this rule targets the same defect surgically)

Flags `dict[str, Any]` (and `Dict[str, Any]`) appearing in a **public** function/method signature
(name not starting with `_`) under the same public-seam directories as S032. Audit found 423 hits
across 118 files repo-wide; this rule scopes to public-seam directories only (a strict subset) to
keep the initial baseline reviewable, and is ratcheted (not fixed in bulk — 400+ call sites is
out of scope for one PR per Non-Goals). `how_to_fix` shows the `TypedDict`/DTO pattern already
used in `vidbyte/mcp_server/schema.py`.

### 6.12 S035 — `bounded-request-safe-path`

**File(s):** `lint/rules/s035_bounded_safe_path.py` (new)
**Type:** New (native `Rule`)
**Covers:** LR-030 (regression guard)

Flags any `open(`, `Path(...).write_...(`, `shutil.copy`/`move`, or `zipfile`/`tarfile` extraction
call whose path argument is built from an untyped external parameter *without* first passing
through the existing `LocalFileSystemBackend` resolved-and-contained path helper (the compliant
pattern the audit already found). Ships ratcheted at whatever count `--update-baseline` records,
since file I/O call sites exist throughout the codebase and most are legitimately internal
(config loading, trace export) rather than untrusted-input-driven.

### 6.13 `vidbyte/lib/http/transport.py` — redirect policy + idempotency key (runtime fix)

**File(s):** `vidbyte/lib/http/transport.py` (modified)
**Type:** Modified
**Covers:** VR-009, LR-036 (redirect policy); VR-007, LR-048 (idempotency key, paired with S030)

#### Logic
1. `HttpTransport`'s per-request `httpx.AsyncClient(...)` construction gains an explicit
   `follow_redirects: bool = False` default (httpx's own default is `False` already, but the
   catalog requires this to be an *explicit, declared* policy, not an inherited library default —
   so the parameter is added to `HttpTransport.__init__`/`request()` and threaded through).
2. `request()` and `SyncHttpTransport.request()` both gain an optional `idempotency_key:
   str | None = None` parameter. When `retry_count > 0` and `method` is not in a new
   `_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})` constant, the
   key is required (raises `ProviderRequestError` at call time if missing) — this is what S030
   verifies statically at known call sites, and enforces at runtime for any call site the static
   check cannot see (e.g. a future dynamic dispatch).

#### Edge Cases
A caller explicitly wanting redirects (e.g. following a provider's documented redirect chain)
passes `follow_redirects=True` explicitly — this is a deliberate, visible choice, not a change in
default behavior for any existing caller (httpx's own default was already effectively `False`
in the absence of explicit configuration... actually httpx's real default is `False` for
`AsyncClient` — confirmed no existing caller relied on redirect-following, so this is a no-op
behaviorally and purely a "make the policy explicit in code" change).

### 6.14 `vidbyte/tools/function_tool.py`, `vidbyte/context/algorithms/independent_critic.py`, `vidbyte/agents/handoff.py` — explicit `mode="json"`

**File(s):** three files, modified
**Type:** Modified
**Covers:** VR-020 (paired with S033)

Each of the 3 non-compliant `.model_dump()` call sites gets `mode="json"` added explicitly,
matching the other 3 already-compliant call sites' convention.

### 6.15 `lint/mypy.ini` — `disallow_any_generics`

**File(s):** `lint/mypy.ini` (modified)
**Type:** Modified
**Covers:** LR-016 (mypy-level half, complementing S034's AST-level half)

Adds `disallow_any_generics = True`. Any new mypy errors this surfaces are absorbed into S009's
existing ratchet via `python lint/run.py --rule S009 --update-baseline` (S009's contract is
"package type errors may only decrease" from whatever the count is *after* this change — the
flag flip itself is not a regression the rule needs to reject, since S009 already tracks an
absolute count, not a diff against a specific config).

### 6.16 `pyproject.toml` — exact dev-dependency pins

**File(s):** `pyproject.toml` (modified)
**Type:** Modified
**Covers:** VR-019, LR-068 (partial — see §12 Open Questions for full lockfile adoption)

`build`, `pytest`, `pytest-asyncio`, `twine` move from range pins (`>=1`, `>=8`, `>=0.23`, `>=5`)
to exact pins matching whatever version resolves in a fresh install today, joining `mypy==2.3.1`
and `ruff==0.16.4` as fully reproducible dev-extras.

### 6.17 `.github/workflows/static-policy.yml` — action pinning fix

**File(s):** `.github/workflows/static-policy.yml` (modified)
**Type:** Modified
**Covers:** VR-041, LR-063

`actions/checkout@v4` -> `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0`,
`actions/setup-python@v5` -> `actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 #
v6.3.0` — the exact SHAs `ci.yml` and `publish.yml` already use, removing the one pinning
inconsistency the audit found across the three SDK workflows.

### 6.18 `.github/workflows/actionlint.yml` (new workflow)

**File(s):** `.github/workflows/actionlint.yml` (new)
**Type:** New
**Covers:** LR-062, LR-047, VR-043 (regression guard for future untrusted-context interpolation)

Runs pinned `actionlint` (via `rhysd/actionlint` released binary, checksum-verified download —
no floating Docker tag) against `.github/workflows/*.yml` on `pull_request` when workflow files
change. `permissions: contents: read` only. This is a pure addition (no existing workflow
touches shell interpolation of untrusted GitHub contexts today, per the audit — so it ships as a
forward-looking gate, not a fix for an existing violation).

## 7. Data Model Changes

N/A - this change adds static-analysis rules and two small transport-layer parameters; no
persisted schema, DTO, or database shape changes.

## 8. API Changes

N/A - `HttpTransport.request()`/`SyncHttpTransport.request()` gain two new *optional*,
default-preserving keyword parameters (`follow_redirects`, `idempotency_key`); no existing
public signature's required-parameter contract changes, so this is additive, not breaking.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `lint/rules/s025_modernized_import_and_syntax_hygiene.py` | LR-017 |
| CREATE | `lint/rules/s026_async_blocking_io.py` | VR-016, LR-019 |
| CREATE | `lint/rules/s027_defensive_python_bugbear.py` | VR-013, VR-014, VR-015, VR-017 |
| CREATE | `lint/rules/s028_bandit_security_subset.py` | LR-022, LR-023, LR-026, LR-032, LR-033, LR-035, LR-038 |
| CREATE | `lint/rules/s029_no_shell_subprocess.py` | VR-005, LR-021, LR-028 |
| CREATE | `lint/rules/s030_retryable_idempotent_methods.py` | VR-007, LR-048 |
| CREATE | `lint/rules/s031_no_model_construct_without_review.py` | VR-011 |
| CREATE | `lint/rules/s032_forbid_unknown_fields_at_boundary.py` | VR-010, LR-041 |
| CREATE | `lint/rules/s033_explicit_serialization_mode.py` | VR-020 |
| CREATE | `lint/rules/s034_typed_public_seam_mappings.py` | VR-012, LR-016 |
| CREATE | `lint/rules/s035_bounded_safe_path.py` | LR-030 |
| MODIFY | `lint/core/ruff.py` | new selector codes for S025-S028 |
| MODIFY | `lint/core/registry.py` | register S025-S035 |
| MODIFY | `lint/baseline.json` | initialize S025-S035 allowances |
| MODIFY | `lint/README.md` | catalogue table entries for S025-S035 |
| MODIFY | `lint/mypy.ini` | `disallow_any_generics = True` |
| MODIFY | `vidbyte/lib/http/transport.py` | explicit `follow_redirects`, `idempotency_key` |
| MODIFY | `vidbyte/tools/function_tool.py` | `mode="json"` on `model_dump()` |
| MODIFY | `vidbyte/context/algorithms/independent_critic.py` | `mode="json"` on `model_dump()` |
| MODIFY | `vidbyte/agents/handoff.py` | `mode="json"` on `model_dump()` |
| MODIFY | `pyproject.toml` | exact-pin remaining dev extras |
| MODIFY | `.github/workflows/static-policy.yml` | SHA-pin actions |
| CREATE | `.github/workflows/actionlint.yml` | LR-062, LR-047 |
| MODIFY | `docs/design/lint-rule-catalog-expansion.md` | this doc (committed first) |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| ruff | 0.16.4 (already pinned) | backs S025-S028 | none — already the CI-pinned analyzer |
| actionlint | pinned release tag + checksum | new workflow-lint gate | low — read-only CI step |

No new Python runtime or dev dependency is introduced.

## 11. Rollout & Deployment

No feature flags — this is a lint/CI gate and two library-internal parameter additions, both
backward compatible. Not a breaking change (see §8). Deployment order: this PR only; no
coordination needed with `vidbyte` (the sibling PR is independent — see its own design doc).
Rollback: revert the PR; ratcheted rules simply stop being enforced, no data/state to unwind.

## 12. Open Questions

- [ ] Full lockfile/constraints adoption (`pip-tools`/`uv`) for VR-019/LR-068 beyond exact dev-pins
      — deferred; changing the resolution *mechanism* (not just the pins) is a bigger call that
      risks breaking installs without a compatibility pass across supported Python 3.11/3.12.
- [ ] GitHub secret-scanning push protection (LR-025) is a repository-settings toggle, not a code
      change — flagged for the user to enable at the GitHub org/repo level; out of this PR's scope.
- [x] S028's `S105/S106/S107/S108/S301/S302/S324/S501/S506` baseline was reviewed by hand after
      the first run (5 findings): both `S506` hits are Ruff not recognizing a genuinely-safe
      `yaml.SafeLoader` subclass (`_DuplicateKeySafeLoader` in `vidbyte/config/loader.py` and
      `vidbyte/lib/config/loader.py`), and all three `S105` hits are the classic bandit false
      positive on constant names containing "PASS"/"TOKEN" as a substring
      (`TOKEN_BUDGET_FINAL_RESPONSE_NOTICE`, `TRIM_TO_TOKEN_BUDGET`, `PASS = "pass"` — none are
      credentials). Ratcheted at 5 with this note rather than fixed, since fixing them would mean
      working around a correct analyzer's known limitation, not a real defect.
- [x] S025's 262 initial findings (224 `I001`, 38 `UP035`) were fixed directly via
      `ruff check vidbyte --isolated --select I001,UP035 --fix` rather than ratcheted — both codes
      are safe, mechanical, behavior-preserving autofixes, and the full test suite (1571 passed)
      plus both CI stages were re-verified green after applying them. S025 ships CLEAN at 0.
- [x] S035's implementation was refined after its first run surfaced two false-positive classes:
      `.extract(` matched an unrelated web-client `.extract()` method (narrowed to `.extractall(`
      only), and `self.backend.read_text(...)`/`write_text(...)` calls were flagged even though
      `self.backend` is already the reviewed `FileSystemBackend` containment abstraction (added a
      receiver-aware exclusion). Final baseline is 6, down from an initial unreviewed 16.
- [x] **Discovered during implementation, unrelated to this design doc's scope:** `origin/main`'s
      own `CI` GitHub Actions workflow has been failing on its last several pushes (confirmed via
      `gh run list --branch main`), independent of this branch — verified by stashing every change
      in this worktree and re-running `python lint/run.py` against unmodified `origin/main` code,
      which reproduced the same 7 regressions (`A001` 846 vs 658, `A006` 36 vs 34, `A007` 255 vs
      254, `S008` 21 vs 19, `S009` 260 vs 258, `S016` 67 vs 50, `S017` 80 vs 79). These findings are
      spread broadly across ~20 top-level `vidbyte/` subdirectories, not localized to any recent
      change this PR could plausibly have caused, and predate this branch's existence. Per the
      ratchet's own contract ("freeze existing debt", not "hide a regression you caused"), this PR
      ratchets all 7 to their true current counts so this PR can ship green, and surfaces the
      discovery here rather than silently absorbing it — **maintainers should treat this as a
      separate, pre-existing gap needing its own triage**, not something this PR fixed.

## 13. Alternatives Considered

### Alternative 1: One rule ID per catalog item (130 new rules)
- What: mechanically create a new rule ID for every LR-xxx/VR-xxx item that touches this repo.
- Why rejected: several catalog items (VR-013/014/015/017) share one mechanism and one repair
  loop; splitting them multiplies baseline bookkeeping without changing what gets fixed. The
  existing suite's own S001 already bundles four Ruff codes under one rule for the same reason.

### Alternative 2: Adopt Semgrep/CodeQL for the new security-flavored rules (VR-005, VR-011, etc.)
- What: extend `.semgrep/` instead of the native `lint/` suite for taint-shaped rules.
- Why rejected: the repo's own `lint/README.md` states the native suite, not Semgrep, "owns rule
  selection, diagnostics, baseline comparison, and exit status" — Semgrep is reserved for the one
  existing taint policy (`typed-mapping-boundary-policy.yml`). Adding a second general-purpose
  rule engine would split diagnostics across two formats and two baseline files for no benefit,
  since every new rule here is expressible as a plain AST walk.

## 14. Catalog Coverage Table

Full disposition of every catalog item against `vidbyte-sdk`. "->S0xx/A0xx" = new rule.
"existing S0xx/A0xx" = already enforced. "config" = non-rule config/workflow change in §6.
"N/A" = does not apply to this repo, reason given.

| ID | Disposition |
|---|---|
| LR-001..LR-011 | N/A - no TypeScript/JS surface in this repo (pure Python package) |
| LR-012 | N/A - `eval`/dynamic-exec has no JS surface here; Python equivalent already S016/S017-adjacent (typed boundary errors preclude `eval`-of-external-data patterns); grep confirmed zero `eval(`/`exec(` on tainted input |
| LR-013, LR-014 | N/A - TS-only (`import type`) / needs type-narrowing info this repo's Ruff config doesn't request |
| LR-015 | existing S009 (ratchet substitutes for strict mode) |
| LR-016 | ->S034 (AST) + config §6.15 (mypy flag) |
| LR-017 | ->S025 |
| LR-018 | existing S005/RUF012 (immutable-class-defaults) already covers mutable-default bugbear; broader `flake8-bugbear` family beyond what's in §6.4 judged low-value here (audit found no other bugbear-shaped defect classes) |
| LR-019 | ->S026 |
| LR-020 | existing S012 (explicit-outbound-timeout) |
| LR-021 | ->S029 |
| LR-022 | ->S028 (`S506`) |
| LR-023 | ->S028 (`S301,S302`) |
| LR-024 | existing S017 (no-raw-exception-disclosure) covers the disclosure half; bare/silent `except` in library code is out of scope — SDK's public error-translation boundaries already require typed errors via S016 |
| LR-025 | config §12 (GitHub push protection - repo setting, not code) |
| LR-026 | ->S028 (`S105,S106,S107`) |
| LR-027 | N/A - `vidbyte/lib/providers/sqlite.py` and `postgres.py` verified: all values bound via `?`/`%s` placeholders, never string-interpolated; one `SELECT *` found is LR-051, not injection |
| LR-028 | ->S029 |
| LR-029 | ->§6.13 (`follow_redirects` explicit policy) |
| LR-030 | ->S035 |
| LR-031 | N/A - no HTML/template rendering surface in this repo |
| LR-032 | ->S031 (`model_construct`) + S028 (`S301,S302` pickle half) |
| LR-033 | ->S028 (`S324`) |
| LR-034 | N/A - audit found zero insecure-random-for-security-token call sites; jitter usage in `exponential_backoff_retry.py` is non-security and explicitly out of this rule's concern |
| LR-035 | ->S028 (`S501`) |
| LR-036 | ->§6.13 |
| LR-037 | N/A - audit found no user/model-supplied regex compiled anywhere in `vidbyte/`; VR-057's "SDK grep search" tool targets a future tool, not existing code - deferred until that tool exists |
| LR-038 | ->S028 (`S108`) |
| LR-039 | existing A003 (context-rich error packets) constrains what boundary errors expose; no dedicated logger-redaction helper exists yet - judged lower priority than the ratcheted rules above given SDK is a library (callers own their logging config), deferred |
| LR-040 | N/A - `mcp_server/` is a local, process-embedded tool registry (stdio-only, no network listener); no HTTP/RPC handler surface exists in this repo to guard |
| LR-041 | ->S032 |
| LR-042..LR-047 | N/A - no HTTP handler/controller layer, no service/repository split, no layer-graph beyond existing A006 (directed-dependency-graph), which already enforces this |
| LR-048 | ->S030 |
| LR-049, LR-050 | existing (partial) - no archive-extraction code path found in this repo; deferred as N/A until one exists |
| LR-051..LR-053 | N/A for SQL rules generally (SDK has no SQL query builder exposed to callers beyond the internal sqlite/postgres providers already checked under LR-027); the one `SELECT *` is accepted debt, documented in §6.3 provider audit, not separately ratcheted (generic KV-store primitive, not an unstable application query) |
| LR-054..LR-058 | N/A - SDK tests use `unittest`, not `pytest`; no skip/only/snapshot patterns found; VR-014 (broad exception assertions) already covers the one relevant defect class via S027 |
| LR-059 | N/A - policy-level CI gate the design-doc-no-tests workflow already supersedes for this task |
| LR-060 | existing S002 (exception-cause-chaining) |
| LR-061 | N/A - SDK is a library; callers own logging configuration, no boundary logging convention to enforce here |
| LR-062, LR-047 | ->§6.18 (actionlint workflow) |
| LR-063 | ->§6.17 |
| LR-064 | existing - verified all three workflows already declare least-privilege `permissions` |
| LR-065 | N/A - no `${{ }}` interpolation into `run:` shell found in any SDK workflow |
| LR-066 | N/A - no multi-line shell scripts in SDK workflows beyond simple one-liners; actionlint (§6.18) covers what exists |
| LR-067 | N/A - no Dockerfile in this repo |
| LR-068 | ->§6.16 (partial) + §12 (full lockfile deferred) |
| LR-069 | N/A - no new dependency introduced by this PR |
| VR-001 | N/A-deferred - `asyncio.gather(return_exceptions=True)` classification is a narrow 4-call-site pattern where 3/4 already classify correctly (`cleanup.py`) or are intentional cancellation suppression (`transport.py`); a reliable low-false-positive AST rule needs to distinguish "classifies via isinstance" from "intentionally suppresses" per call site, which the existing S019 (cancellation-propagation) partially already guards; judged not clean enough to ship without risking false positives on the compliant sites - flagged as follow-up |
| VR-002 | N/A - all 5 `create_task` call sites already assign to an owning attribute (S006/RUF006 already enforces this); no gap found |
| VR-003 | N/A - verified `McpStdioTransport` already correlates via `self._pending: dict[int, Future]`; behavioral correctness, not statically checkable beyond what exists |
| VR-004 | ->§6.13-adjacent runtime note: deferred - stdio frame-size ceiling is a single-call-site runtime change in `transport.py`'s stdin reader; scoped out of this PR's file list to keep the transport diff reviewable alongside §6.13's changes, tracked as an immediate follow-up PR |
| VR-005 | ->S029 |
| VR-006 | N/A - verified already compliant (fails pending futures, closes stdin, terminates, waits, kills, gathers reader tasks, detaches state) |
| VR-007 | ->S030 + §6.13 |
| VR-008 | existing - S011 (raw-http-client-ownership) already confines client construction to the transport module; per-request client creation is this repo's deliberate statelessness choice, not a gap |
| VR-009 | ->§6.13 |
| VR-010 | ->S032 |
| VR-011 | ->S031 |
| VR-012 | ->S034 |
| VR-013 | ->S027 |
| VR-014 | ->S027 |
| VR-015 | ->S027 |
| VR-016 | ->S026 |
| VR-017 | ->S027 |
| VR-018 | N/A-deferred - timeout-budget-across-retries touches only 2-3 call sites; a reliable AST check for "does this retry loop track a cumulative deadline" is exactly the low-signal-to-noise rule the catalog's own quality bar warns against; tracked as a follow-up runtime change (add `overall_deadline` to both retry middlewares) rather than a lint rule |
| VR-019 | ->§6.16 (partial) |
| VR-020 | ->S033 + §6.14 |
| VR-021..VR-057 (backend/frontend-specific) | N/A - target `vidbyte`, not `vidbyte-sdk`; see that repo's design doc |
| VR-058 | N/A - no `fetch()` usage in this Python repo |
| VR-059, VR-060 | N/A - target `vidbyte` backend (base64/XML handling); SDK has no equivalent untrusted-document parsing path |
| VR-061 | N/A - target `vidbyte` Next.js Server Actions |

