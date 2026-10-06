# Design Doc: Context Write-Path Integrity

**Status:** Draft
**Author:** Grok
**Created:** 2026-07-18
**Last Updated:** 2026-07-18

## 1. Overview

Coding agents and feature PRs that implement context-window algorithms or agent
behavior frequently bypass the SDK’s managed context APIs. They mutate provider
message lists, rewrite system prompts ad hoc, or read/write private
`ContextManager` state instead of using the public write surface
(`upsert`, `place_after_*`, `remove_by_id`, `registry_items`,
`ContextWindowRunContext`).

This change does three things:

1. **Corrects a real production bug** where `ErrorCorrectionAlgorithm` lists
   *unmanaged* items (`manager.items()`) when it should list *managed registry*
   primitives (`manager.registry_items()`), so the auditor cannot see algorithm-
   owned primitives and cannot name stale ids correctly.
2. **Adds a repository-owned static checker** that enforces zone-scoped context
   write-path rules (private registry access, inner-loop message mutation, and
   context-primitive tools holding a `ContextManager`).
3. **Wires that checker into the existing source CI gate**
   (`python scripts/run_ci.py` / `.github/workflows/ci.yml`) so every PR fails
   closed on known bypass patterns.

The policy is intentionally **not** “nothing may touch messages except
`ContextManager`.” Provider transcripts, compaction middleware, providers, and
outer-loop trial orchestration remain legitimate non-manager surfaces, with
explicit allowlists.

## 2. Goals & Non-Goals

### Goals

- Fix `ErrorCorrectionAlgorithm._format_managed_primitives` so it enumerates
  managed registry entries via `ContextManager.registry_items()`.
- Add `scripts/check_context_write_paths.py` that hard-fails on high-signal
  write-path violations under scoped paths.
- Invoke the checker from `scripts/run_ci.py` `run_source()` so local and PR CI
  both enforce the invariant without a separate workflow job.
- Document the invariant in maintainer-facing skills so coding agents see it
  before CI fails them.
- Keep enforcement zone-scoped with an explicit allowlist for legitimate raw
  message mutators (`AgentRuntime`, providers, formatters, compaction).

### Non-Goals

- Do **not** ban `AgentRuntime` transcript `messages.append` for assistant/tool
  turns.
- Do **not** force compaction middleware or provider request packaging through
  `ContextManager`.
- Do **not** rewrite outer-loop algorithms (Reflexion, multi-provider grader,
  independent critic, prosecutor/defender/judge) to store all trial memory only
  as managed primitives in this PR.
- Do **not** adopt non-linear/actor runtimes onto the primitives zone in this PR.
- Do **not** add Ruff/mypy plugins, Semgrep, or a new GitHub Actions workflow
  file; extend the existing `run_ci.py` source gate only.
- Do **not** add a new `tests/` feature test pack for this change (per
  design-doc-no-tests). Existing pytest suite must remain green. The checker
  validates itself with inline fixture strings / temp fixtures when executed,
  not a new product test module.
- Do **not** make `ContextWindowRunContext.messages` raise on mutation beyond
  documenting that it is already typed as `Sequence` (read contract). Optional
  tuple normalization is out of scope unless needed for a green baseline.

## 3. Background & Context

### Repository audit baseline

Audit target is **`origin/main`** of `cerredz/Vidbyte-SDK` (fetched 2026-07-18),
not the dirty local feature branch `feat/context-minimal-fanout-trace`.

Relevant main facts:

| Area | State on `origin/main` |
|------|-------------------------|
| `ContextManager.registry_items()` | Already present; public read of managed registry |
| `ContextListTool` / `ContextStatsTool` | Already use `registry_items()` |
| Create/edit/move/recite tools + factory | Already bind `ContextManager` and write via public APIs |
| `ErrorCorrectionAlgorithm._format_managed_primitives` | **Bug:** iterates `ctx.context_manager.items()` (unmanaged only) |
| Inner-loop algorithms | `trajectory_checkpoints`, `problem_space_search`, `error_correction` already write via `place_*` / `upsert` / `ctx.remove` |
| Outer-loop algorithms | Use `replace(context, system_prompt=...)` and stage `{"system": ...}` call options by design |
| Canonical CI | `python scripts/run_ci.py` (`--stage source` = bytecode hygiene + `compileall` + `pytest`; `--stage package` = build/twine/install smoke) |
| Workflow | `.github/workflows/ci.yml` calls `run_ci.py` after `pip install -e ".[dev]"` |

### Context zones (load-bearing model)

```text
Zone 1–2: system prompt + tools     → BaseAgentContext fixed rendering
Zone 3:   managed primitives        → ContextManager registry + placement
Zone 4:   agent loop transcript     → AgentRuntime provider messages
Outer:    multi-trial orchestration → algorithm replace(context) / side calls
History:  compaction                → middleware / compaction tools
```

**Managed context engineering** (zone 3 and conversation placements) must go
through `ContextManager` / `ContextWindowRunContext`.

**Transcript mutation** (zone 4) remains runtime-owned.

### Why coding agents break this

Skills already say “write with `ctx.place_after_*`; prove visibility via
`ContextManager`, not direct message injection.” Agents still invent
`messages.append` / private `_registry` access because those look simpler and
there is no CI doorstop. Docs alone have proven insufficient.

### Material uncertainty

- Exact count of future outer-loop algorithms that will need soft rules is
  unknown; v1 hard rules stay limited to inner-loop + private registry + tools.
- Whether Error Correction’s existing tests assert auditor listing content is
  unclear from skim; the fix must preserve current behavior for empty registries
  and remain consistent with `removable_prefixes` filtering.

## 4. Requirements

### Functional Requirements

1. **Error Correction managed listing**
   - `_format_managed_primitives` MUST iterate managed registry entries from
     `ctx.context_manager.registry_items()`.
   - It MUST continue filtering to ids matching `removable_prefixes` (and skip
     empty listings as `"None."`).
   - It MUST NOT use `items()` for this purpose (that API is unmanaged only).

2. **Static checker (`check_context_write_paths.py`)**
   - MUST be a pure-stdlib Python AST script under `scripts/`.
   - MUST exit non-zero with file:line messages when any hard rule fails.
   - MUST exit zero on a clean `origin/main` tree after the Error Correction fix
     (and on any tree that only uses allowlisted patterns).
   - MUST scan repository `vidbyte/**/*.py` with path-scoped rules (below).
   - MUST include a `--self-check` mode (default-on when invoked from CI, or
     always run a short self-check at start) that validates good/bad snippet
     fixtures so the checker cannot silently no-op.

3. **Hard rules (v1)**

   | ID | Scope | Rule |
   |----|-------|------|
   | `CWP001` | `vidbyte/context/**` except `manager.py`; `vidbyte/tools/builtins/context_primitives/**`; `vidbyte/tools/builtins/context/**`; `vidbyte/agents/**` | Forbid attribute access to `_registry` or `_placements` (private ContextManager storage). |
   | `CWP002` | Inner-loop algorithm modules: `vidbyte/context/algorithms/error_correction.py`, `problem_space_search.py`, `trajectory_checkpoints.py` (and any new file that defines a class subclassing `InnerContextWindowAlgorithm` under `vidbyte/context/algorithms/`) | Forbid mutating provider message lists: `messages.append` / `insert` / `pop` / `clear` / `del messages[...]` / assignment to `ctx.messages`. Reading `ctx.messages` remains allowed. |
   | `CWP004` | `vidbyte/tools/builtins/context_primitives/**` tool classes that mutate or list managed context | Constructor must accept a parameter typed/named as context manager (`ContextManager` annotation or parameter name in `{context_manager, manager}`) and store it; no alternate in-memory registry dict for managed primitives. |

   Note: `CWP003` (heuristic “if you construct `*ContextItem` you must place it”)
   is **deferred** to a follow-up to avoid false positives in pure builders;
   skills already require placement tests for algorithms.

4. **Allowlist (explicit non-violations)**
   - `vidbyte/context/manager.py` may access `_registry` / `_placements`.
   - `vidbyte/agents/runtime.py` may mutate provider `messages` for the tool loop.
   - `vidbyte/providers/**`, `vidbyte/lib/tools/**`, `vidbyte/middleware/compaction/**`,
     and `vidbyte/tools/builtins/context/compaction.py` may mutate message history
     for wire format / compaction (outside CWP002 scope).
   - Outer-loop modules under `vidbyte/agents/algorithms/**` and config modules
     such as `reflexion.py`, `multi_provider_agentic_grader.py`,
     `independent_critic.py`, `prosecutor_defender_judge.py`, `tool_results.py`
     are **not** under CWP002 message-mutation ban (they do not own inner-loop
     placement; side-call system prompts remain legal).

5. **CI integration**
   - `CiPipeline.run_source()` MUST run the checker after `compileall` and before
     or after `pytest` (order: bytecode → compileall → **context write paths** →
     pytest) so syntax errors surface before architecture rules.
   - No change to package stage or workflow YAML structure is required beyond
     what `run_ci.py` already drives (workflow already calls `run_ci.py`).

6. **Documentation**
   - `skills/vidbyte-sdk/context-primitives.md` MUST add a short “Context write
     path integrity” section stating the invariant, the three hard rules, and
     the checker command.
   - `skills/vidbyte-sdk/adding-context-window-algorithms.md` MUST reference the
     checker and CWP002 for inner-loop algorithms (link/anchor-style cross-ref).

### Non-Functional Requirements

- Stdlib only for the checker (no new dependency).
- Checker runtime: sub-second on the current package tree.
- Backward compatible public APIs; only bugfix + enforcement + docs.
- Canonical full local CI (required for handoff after implementation):

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

- Diagnostic stages:

```bash
python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
```

- Required remote checks: GitHub Actions workflow `CI` jobs
  `Source / Python 3.11`, `Source / Python 3.12`, and `Package`.

## 5. High-Level Design

```text
┌─────────────────────────────────────────────────────────────┐
│ CI / local: python scripts/run_ci.py --stage source         │
│   1. no tracked bytecode                                    │
│   2. compileall vidbyte/                                    │
│   3. check_context_write_paths.py   ◄── NEW                 │
│   4. pytest                                                 │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ AST scan of scoped Python files                             │
│   CWP001 private registry attrs                             │
│   CWP002 inner-loop message mutation                        │
│   CWP004 context_primitives tools hold ContextManager       │
└─────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┴────────────────┐
          ▼                                ▼
 ErrorCorrection uses                 Future PRs that
 registry_items()                     bypass write APIs
 (bugfix)                            fail closed in CI
```

### Key design decisions

1. **Zone-scoped enforcement over global ban** — prevents false positives against
   the runtime transcript and compaction.
2. **Fix before lock** — Error Correction listing is corrected in the same change
   set as the checker so main is green when the door closes.
3. **Extend `run_ci.py`, not a new workflow** — one entry point for agents and GHA.
4. **AST over regex-only** — reduces false positives on comments/strings while
   remaining stdlib-only.
5. **Defer outer-loop Reflexion migration** — separate product design; do not
   block this integrity gate on it.

## 6. Detailed Design

### 6.1 Error Correction managed primitive listing

**Files:** `vidbyte/context/algorithms/error_correction.py`  
**Type:** Modified

#### Responsibility

Produce the auditor-facing inventory of **managed** primitives that are eligible
for removal (prefix allowlist), so stale id suggestions are grounded in the
registry that algorithms actually write.

#### Interface / API

No public signature change. Private helper behavior changes:

```python
def _format_managed_primitives(self, ctx: ContextWindowRunContext) -> str:
    ...
```

#### Logic / Algorithm

1. Call `ctx.context_manager.registry_items()` → `tuple[tuple[str, ContextItem], ...]`.
2. For each `(primitive_id, item)`, if `_is_removable(primitive_id)`, append
   `f"- {primitive_id} ({title})"`.
3. If no lines, return `"None."`.

#### Edge Cases & Error Handling

- Empty registry → `"None."` (unchanged outcome shape).
- Unmanaged-only `context_items` must **not** appear (corrects prior wrong behavior).
- Missing `title` → empty title string as today via `getattr(item, "title", "")`.
- Frozen / non-removable ids remain filtered by prefix rules (unchanged).

#### Adversarial note

Using `items()` looked plausible but only walks unmanaged standing inputs. Managed
algorithm notices use `upsert` into `_registry`, so the auditor was effectively
blind to the primitives it is allowed to delete. That is a silent correctness bug,
not a style preference.

---

### 6.2 Context write-path checker

**Files:** `scripts/check_context_write_paths.py`  
**Type:** New

#### Responsibility

Statically enforce CWP001 / CWP002 / CWP004 over the package tree; self-check
with synthetic snippets; print actionable diagnostics; exit status for CI.

#### Interface / API

```text
python scripts/check_context_write_paths.py
  [--root PATH]          # default: repository root containing vidbyte/
  [--skip-self-check]    # emergency only; not used by run_ci.py

Exit codes:
  0  all rules and self-check passed
  1  one or more violations or self-check failure
  2  usage / IO error
```

Diagnostic line format:

```text
CWP001 path/to/file.py:42: private ContextManager storage access '._registry' is forbidden outside manager.py
```

#### Logic / Algorithm

1. Resolve `root` and `package = root / "vidbyte"`.
2. Run self-check: parse embedded good/bad snippets with the same rule engine;
   expect bad snippets to produce specific rule ids and good snippets zero findings.
3. Collect all `*.py` under `vidbyte/` (skip `__pycache__`).
4. For each file, `ast.parse` and walk:

**CWP001**

- If file path is `vidbyte/context/manager.py` → skip.
- Else if file is under scoped roots
  (`vidbyte/context/`, `vidbyte/agents/`, `vidbyte/tools/builtins/context_primitives/`,
  `vidbyte/tools/builtins/context/`) and node is `ast.Attribute` with
  `attr in {"_registry", "_placements"}` → violation.
- Rationale for path scope: other packages legitimately use `_registry` names
  (evals client, MCP handlers) for unrelated registries.

**CWP002**

- Target set:
  - Explicit paths: `error_correction.py`, `problem_space_search.py`,
    `trajectory_checkpoints.py` under `vidbyte/context/algorithms/`.
  - Plus any module under `vidbyte/context/algorithms/` whose AST contains a
    class base named `InnerContextWindowAlgorithm` (catches new inner-loop files).
- Forbidden patterns on those modules:
  - `Call` of `Attribute` where attr is `append|insert|pop|clear` and value is
    `Name(id="messages")` or `Attribute(attr="messages")` (e.g. `ctx.messages.append`).
  - `Delete` targets that are subscripts of `messages`.
  - `Assign` / `AnnAssign` targets that are `ctx.messages` or bare `messages`
    rebinding when the right-hand side is not a pure read alias used only for
    local formatting — **v1 simplifies** to: forbid any `Assign` target that is
    `Attribute(value=Name(id='ctx'), attr='messages')`. Local
    `history = list(ctx.messages or [])` for read-only formatting remains allowed
    because the target is not `ctx.messages`.

**CWP004**

- For modules under `vidbyte/tools/builtins/context_primitives/` defining a class
  that subclasses `BaseTool` (or has `execute` + `spec` methods) and whose name
  contains `Context` or is in the known set
  (`ContextListTool`, `ContextRemoveTool`, `ContextUpsertTool`, `ContextEditTool`,
  `ContextMoveTool`, `ContextReciteTool`, `ContextStatsTool`,
  `CreateContextPrimitiveTool`, and factory consumers):
  - `__init__` must have a parameter whose annotation string contains
    `ContextManager` **or** whose name is `context_manager` or `manager`.
- Factory module is exempt from “must be BaseTool” but must still accept
  `ContextManager` / `manager` in `ContextWindowFactory.__init__`.
- Lightweight: if a file under this package defines `class X(BaseTool)` and
  defines `__init__`, apply the parameter check. This covers the tool family
  without over-fitting names.

5. Aggregate findings; print sorted by path then line; exit 1 if any.

#### Edge Cases & Error Handling

- Syntax error in scanned file → report as checker IO/parse failure exit 2 with path.
- Empty package → fail loudly (misconfigured root).
- Self-check failure → exit 1 with message that the rule engine is broken.
- Windows path separators normalized to posix in messages for stable CI logs.

#### Self-check fixtures (embedded)

| Snippet | Expected |
|---------|----------|
| Inner algorithm with `ctx.place_after_tools(item)` only | pass |
| Inner algorithm with `ctx.messages.append({})` | CWP002 |
| Tool reading `self._manager._registry` | CWP001 |
| Tool `__init__(self, context_manager: ContextManager)` | pass |
| Tool `__init__(self)` with internal `self._store = {}` used as registry **not** required to fail CWP004 if it still takes manager — CWP004 only requires manager parameter presence |

---

### 6.3 CI pipeline hook

**Files:** `scripts/run_ci.py`  
**Type:** Modified

#### Responsibility

Keep one canonical verification entry point; add architecture invariant to source
gate.

#### Interface / API

Unchanged CLI (`--stage all|source|package`, `--dist-dir`). Behavior of
`run_source()` gains one command.

#### Logic / Algorithm

```python
def run_source(self) -> None:
    self._assert_no_tracked_bytecode()
    self._run_command([sys.executable, "-m", "compileall", "-q", str(PACKAGE_ROOT)])
    self._run_command([sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_context_write_paths.py")])
    self._run_command([sys.executable, "-m", "pytest"])
```

#### Edge Cases & Error Handling

- Checker non-zero exit propagates via existing `_run_command` / `CiFailure` path
  (same as compileall/pytest failures). Do not swallow or xfail.

---

### 6.4 Maintainer documentation

**Files:**

- `skills/vidbyte-sdk/context-primitives.md` (Modified)
- `skills/vidbyte-sdk/adding-context-window-algorithms.md` (Modified)

**Type:** Modified

#### Responsibility

Teach the invariant before implementation; mirror CI rules in prose.

#### Content outline (context-primitives.md)

Add section **Context write path integrity**:

- Invariant one-liner.
- Table of legal write surfaces vs illegal bypasses.
- Commands:

```bash
python scripts/check_context_write_paths.py
python scripts/run_ci.py --stage source
```

- Point to Error Correction / list tools as examples of correct `registry_items()`
  usage.

#### Content outline (adding-context-window-algorithms.md)

In the inner-loop section already forbidding direct message mutation, add:

- CI enforces CWP002 on `InnerContextWindowAlgorithm` modules.
- Link to the checker script and context-primitives integrity section.

#### Edge Cases & Error Handling

N/A - documentation only.

---

### 6.5 Optional follow-ups (not in this PR)

Documented here so reviewers do not expand scope mid-implementation:

- CWP003 placement heuristic.
- Soft rule for outer-loop durable memory as primitives.
- Runtime assertion that `ctx.messages` is immutable (tuple copy at construction).
- Actor/non-linear runtime adoption of manager zone rendering.

## 7. Data Model Changes

N/A - no schema, persistence, or dataclass field changes. `registry_items()`
already exists on `ContextManager`. Error Correction only changes which public
read API it calls.

## 8. API Changes

| Surface | Change |
|---------|--------|
| `ContextManager` | None (uses existing `registry_items()`) |
| `ErrorCorrectionAlgorithm` | Behavior fix for auditor listing only; no signature change |
| `scripts/check_context_write_paths.py` | New developer/CI CLI |
| `scripts/run_ci.py` | Source stage gains one subprocess step |
| Public package exports | None |

Errors:

- Checker prints human diagnostics; no SDK exception type added.
- Error Correction continues to raise/record audit failures as today.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-write-path-integrity.md` | This design document (committed first after approval). |
| CREATE | `scripts/check_context_write_paths.py` | AST write-path integrity checker + self-check. |
| MODIFY | `vidbyte/context/algorithms/error_correction.py` | Use `registry_items()` for managed primitive listing. |
| MODIFY | `scripts/run_ci.py` | Invoke checker in `run_source()`. |
| MODIFY | `skills/vidbyte-sdk/context-primitives.md` | Document invariant, rules, commands. |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Reference CWP002 / checker for inner-loop algorithms. |

No workflow YAML changes required (ci.yml already runs `run_ci.py`).

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `ast` | 3.11+ | Static analysis | Low — stable |
| Existing CI (`pytest`, `build`, `twine`) | `.[dev]` extra | Unchanged gates | Low |
| GitHub Actions CI | existing workflow | Remote enforcement via `run_ci.py` | Low — no new secrets |

No new third-party packages.

## 11. Rollout & Deployment

1. Land design doc commit on `feat/context-write-path-integrity` from updated
   `main`.
2. Implement Error Correction fix + checker + `run_ci` hook + skill docs in
   logical commits.
3. Run full local gate: `python -m pip install -e ".[dev]"` then
   `python scripts/run_ci.py`.
4. Open **draft** PR to `main`; wait for CI jobs Source 3.11/3.12 + Package.
5. No feature flag; enforcement is repository-local and CI-only (no runtime
   behavior change except Error Correction auditor visibility).

### Rollback

- Revert the PR. That removes the CI step and restores prior Error Correction
  listing (regresses the bug). Prefer forward-fix of checker false positives
  by tightening path scopes rather than reverting the Error Correction fix.

### Compatibility

- Existing callers of Error Correction that depended on the auditor *not* seeing
  managed primitives would change behavior only if they relied on that bug. No
  supported API promised that broken listing.

## 12. Open Questions

- [x] Should outer-loop Reflexion memory move to primitives in this PR?  
      **Resolved: No** — non-goal; separate design.
- [x] New GitHub workflow vs extend `run_ci.py`?  
      **Resolved: extend `run_ci.py` only.**
- [x] New pytest module for checker?  
      **Resolved: No** — self-check inside the script; design-doc-no-tests.
- [ ] Should CWP001 also scan `tests/` for private registry access to teach
      agent authors in tests?  
      **Default for implementation: no** — tests may intentionally probe
      internals; document as open if reviewers want teaching-mode coverage.

## 13. Alternatives Considered

### Global ban on all `messages.append` under `vidbyte/`

- What: Single rule forbidding any message list mutation package-wide.
- Why rejected: Breaks `AgentRuntime` tool loop, providers, and compaction;
  high false-positive rate; fights the multi-zone architecture.

### Custom Ruff plugin / Semgrep ruleset

- What: External linter plugin for architecture rules.
- Why rejected: Adds tooling surface and onboarding cost; stdlib AST script
  matches existing `run_ci.py` style and ships with zero new deps.

### Runtime-only enforcement (immutable messages proxy)

- What: Make `ContextWindowRunContext.messages` raise on write at runtime.
- Why rejected as sole solution: Does not catch private `_registry` access or
  bad tool construction; better as a later complement, not the first doorstop.

### Migrate all outer-loop system_prompt rewrites to ContextManager now

- What: Force Reflexion/grader trial memory into primitives.
- Why rejected: Changes model-visible layout and prompt templates; product
  decision with behavior risk; out of scope for an integrity gate PR.

### Checker outside CI (docs/skill only)

- What: Document the invariant without automated enforcement.
- Why rejected: The original problem is coding agents ignoring docs; CI is the
  load-bearing control.

---

## Implementation notes for the post-approval worktree

- Work from a **clean** `main` worktree (`git pull origin main`), not the dirty
  `feat/context-minimal-fanout-trace` checkout.
- Branch name: `feat/context-write-path-integrity`.
- First commit: this design doc only.
- Then implementation commits; full `python scripts/run_ci.py` before push.
- Draft PR body can reuse this document.
)
