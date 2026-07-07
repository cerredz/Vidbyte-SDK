# Design Doc: Agentic Engineering Principles for Agents, Middleware, and Top-Level Tools

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Apply the Vidbyte agentic engineering principles to `vidbyte/agents` recursively, `vidbyte/middleware` recursively, and only the top-level files in `vidbyte/tools`. This is a source-orientation and maintainability pass: strengthen file headers, folder READMEs, function-level comments, intent comments, and existing error context so a future agent can understand and safely modify these files with less repository traversal.

---

## 2. Goals & Non-Goals

### Goals

- Add or upgrade structured file headers for every targeted Python source file so each file states its path, purpose, dependency role, exported API inventory, modification patterns, forbidden responsibilities, edge cases, related docs, and test/verification references.
- Expand targeted folder READMEs into comprehension caches with folder intent, non-goals, file indexes, and compact logs.
- Add missing folder READMEs for targeted subfolders that contain source files and do not currently have README coverage.
- Apply the function-design principle within the target scope by making edited function and method signatures one-line where practical, adding an immediate one- or two-line explanatory comment below every function or method signature, and splitting only the highest-risk long functions when the split is local and behavior-preserving.
- Apply intent-based comments beside non-obvious business or domain rules, especially runtime compatibility rules, permission decisions, loop termination decisions, trace redaction, context compaction invariants, and tool execution policy.
- Improve existing error messages and safe `details` payloads at target-scope raise sites when doing so fits the current `vidbyte.lib.errors` exception hierarchy.
- Keep `vidbyte/tools` scope limited to files directly inside `vidbyte/tools`; do not modify `vidbyte/tools/security`, `vidbyte/tools/mcp`, `vidbyte/tools/filesystem`, or `vidbyte/tools/builtins`.

### Non-Goals

- No test files or feature test packs in this pass. The user selected `design-doc-no-tests`, so the feature-test-packs principle is documented as intentionally omitted.
- No behavioral redesign of agent execution, middleware semantics, compaction algorithms, or tool execution.
- No new public APIs, package dependencies, runtime services, migrations, database work, or provider integrations.
- No changes to generated cache files such as `__pycache__`.
- No recursive changes under `vidbyte/tools` subfolders.
- No wholesale replacement of the existing `vidbyte.lib.errors` exception hierarchy with a new per-failure error class taxonomy.

---

## 3. Background & Context

The referenced GitHub prompt, `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`, frames source code as a durable knowledge artifact for both humans and downstream coding agents. Its routing guidance says source changes trigger file headers, folder changes trigger folder READMEs, function changes trigger function design, domain logic triggers intent comments, server-side failures trigger richer error context, and durable behavior changes trigger feature test packs.

Repository audit findings:

- The SDK is a Python package (`pyproject.toml`) requiring Python `>=3.11` and depending on `pydantic>=2,<3` and `httpx>=0.27`.
- The package is published by a GitHub Actions workflow that builds on Python 3.11 and publishes tagged releases to PyPI.
- `README.md` identifies the public SDK layers and already links `vidbyte.agents`, `vidbyte.middleware`, and `vidbyte.tools`.
- Targeted source files often start with lightweight `Context Protocol Header` docstrings, but those headers are much shorter than the agentic file-header deep dive requires.
- Existing target READMEs explain broad role, philosophy, usage, key modules, and related layers, but they do not yet include full non-goals, per-file indexes for all targeted files, or logs.
- Existing code already favors classes in most non-trivial areas, but there are long orchestration methods, multi-line signatures, and helper functions whose agent readability can be improved without changing behavior.
- Error handling currently uses centralized safe SDK exceptions from `vidbyte.lib.errors.base`, with optional `details` mappings. The target pass should enrich those existing details where appropriate rather than creating a second error framework inside `agents`, `middleware`, or `tools`.
- The local checkout is dirty on branch `feat/context-minimal-fanout-trace` with unrelated untracked design docs and worktree folders. Implementation must happen only after approval, in a fresh worktree, without touching unrelated files.
- The repository does not contain `docs/design/references/design-doc-template.md`; this design uses the template bundled with the selected local skill at `C:/Users/422mi/.codex/skills/design-doc-no-tests/references/design-doc-template.md`.

Reference sources loaded through web search:

- https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md
- https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md
- https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/folder_readme.md
- https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md
- https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md
- https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/error_messages.md

---

## 4. Requirements

### Functional Requirements

1. Every targeted Python source file must open with a structured, file-specific header docstring.
2. Every structured header must identify the literal file path and explain the file's purpose, role in the dependency graph, exported API inventory, common modification patterns, what not to do in the file, known edge cases, common errors raised or returned by the file, related docs, test or verification references, and concurrency model when relevant.
3. Existing `Context Protocol Header` blocks in targeted files must be replaced or expanded, not duplicated.
4. `vidbyte/agents/README.md`, `vidbyte/middleware/README.md`, and `vidbyte/tools/README.md` must be expanded into folder-level comprehension caches while preserving useful existing usage examples.
5. New folder-level READMEs must be created for targeted source subfolders that currently lack one: `vidbyte/agents/algorithms`, `vidbyte/agents/runtimes`, `vidbyte/agents/runtimes/actor`, `vidbyte/agents/settings`, `vidbyte/middleware/builtins`, and `vidbyte/middleware/compaction`.
6. Folder READMEs must include folder description/intent, explicit non-goals, a per-file index, and a concise log section for known footguns or invariants discovered during the audit.
7. Python functions and methods touched by this pass must have a one-line signature where practical and an immediate explanatory comment or docstring line below the signature.
8. Existing comments that narrate obvious implementation mechanics should be converted to intent comments only where the code protects a non-obvious domain or runtime invariant.
9. Existing error raises in target files should gain better safe context through existing exception message/detail patterns when the error is at an external boundary, precondition check, state transition, or integration boundary.
10. Public imports and `__all__` exports must remain compatible unless a file header documents an existing export, in which case the header must match the code exactly.
11. The implementation must not modify any file under `vidbyte/tools` subdirectories.
12. The implementation must not modify `__pycache__` or generated artifacts.

### Non-Functional Requirements

- Performance: No runtime overhead beyond any enriched exception construction on paths that already raise or return errors.
- Scalability: Documentation should reduce future context-window traversal cost without adding generated bulk that becomes stale immediately.
- Security: Error detail enrichment must not expose API keys, tokens, credentials, authorization headers, or sensitive prompt payloads.
- Observability: Headers and READMEs must point agents to existing trace, middleware, and test/script verification surfaces.
- Reliability: Behavior must remain unchanged except for clearer errors in existing failure paths.
- Maintainability: Header content must describe durable architectural intent, not fragile line-by-line implementation mechanics.

---

## 5. High-Level Design

The implementation will be a documentation-first pass across the requested source boundaries. It will add agentic file headers to target Python files, update or add folder READMEs, then perform narrow inline cleanup for function comments, intent comments, and error context where the current code already exposes obvious agent-navigation gaps.

The work will preserve the current SDK architecture. `vidbyte.agents` remains the executable actor layer, `vidbyte.middleware` remains deterministic runtime policy, and `vidbyte.tools` top-level files remain the public tool catalog/execution/decorator surface. No new package, dependency, database, API endpoint, or runtime feature will be introduced.

The main design decision is to apply the agentic principles without turning this into an untested behavioral refactor. The linked prompt's feature-test-packs principle normally applies to durable behavior changes, but this request explicitly uses the no-tests workflow. Therefore, behavior-preserving documentation and comment improvements are in scope, while deep refactors and new feature test packs are out of scope.

```text
Agentic Engineering Prompt
        |
        v
Principle routing
        |
        +--> File headers for targeted .py files
        +--> Folder READMEs for targeted folders/subfolders
        +--> Function comments/signature cleanup where files are touched
        +--> Intent comments for runtime/domain invariants
        +--> Existing error context enrichment
        |
        v
No public API change, no migrations, no new dependencies
```

---

## 6. Detailed Design

### 6.1 Agentic Principle Routing

**File(s):** all files listed in Section 9
**Type:** Modified and New file

#### What it does

Route the referenced agentic engineering principles into concrete edits that fit this SDK and the selected no-tests workflow.

#### Interface / API

```python
# No new runtime API.
```

#### Logic / Algorithm

1. Read each target source file and identify exports, imports, common callers, callees, errors, and non-obvious invariants.
2. Read sibling and parent READMEs to avoid contradictory folder responsibility statements.
3. Update or create READMEs before finalizing file headers so file-level "what not to do" sections can point to accurate folder boundaries.
4. Update each file header after any body edits so header and code agree.
5. Re-read the target scope and check that no `vidbyte/tools` subfolder files changed.

#### Edge Cases & Error Handling

- If a file has no exported public API, its header inventory will state that it is an internal module and list internal helpers only when needed for navigation.
- If a file has no meaningful concurrency model, the header will omit that section rather than using a placeholder.
- If an error path would require a new exception taxonomy, the implementation will leave behavior intact and document the gap in the handoff report.

### 6.2 Structured File Headers

**File(s):** target Python source files in Section 9
**Type:** Modified

#### What it does

Replace existing short module docstrings or missing headers with structured, file-specific agentic headers.

#### Interface / API

```python
"""
FILE: vidbyte/agents/base.py

PURPOSE:
...
"""
```

#### Logic / Algorithm

1. Put the structured header at the first line of each Python file, before `from __future__ import annotations`.
2. Use literal repository-relative paths.
3. Include durable architecture and ownership facts rather than volatile implementation steps.
4. Include a function/class inventory for exported symbols and important internal classes.
5. Cross-reference related folders, docs, scripts, and errors with fetchable local paths or GitHub URLs where useful.
6. Reconcile the final header against the file body after edits.

#### Edge Cases & Error Handling

- Files that currently have no header, such as `vidbyte/tools/function_tool.py` and `vidbyte/middleware/compaction/strategies.py`, will receive a new header.
- `__init__.py` files will document re-export responsibilities and must not claim ownership of implementation logic.
- Very large modules such as `vidbyte/agents/runtime.py`, `vidbyte/agents/base.py`, and `vidbyte/middleware/compaction/strategies.py` need concise but complete inventories to avoid making the header itself harder to scan.

### 6.3 Folder-Level READMEs

**File(s):** `vidbyte/agents/README.md`, `vidbyte/agents/algorithms/README.md`, `vidbyte/agents/runtimes/README.md`, `vidbyte/agents/runtimes/actor/README.md`, `vidbyte/agents/settings/README.md`, `vidbyte/middleware/README.md`, `vidbyte/middleware/builtins/README.md`, `vidbyte/middleware/compaction/README.md`, `vidbyte/tools/README.md`
**Type:** New file and Modified

#### What it does

Make each targeted directory navigable as a comprehension cache before opening individual files.

#### Interface / API

```markdown
# Agents

## Folder Intent
...

## Non-Goals
...

## File Index
...

## Logs
...
```

#### Logic / Algorithm

1. Preserve existing usage examples in the three existing top-level READMEs where they still match current APIs.
2. Add explicit non-goals so future agents do not misfile code.
3. Write a file index entry for each targeted file in the folder.
4. Add short log entries for audit-time invariants and known footguns.
5. Keep `vidbyte/tools/README.md` scoped to top-level files and point to subfolder READMEs without editing those subfolders.

#### Edge Cases & Error Handling

- If a subfolder has no README but contains only `__init__.py` plus one small file, it still gets a compact README because the folder README principle applies to source folders.
- Logs must not invent production incidents. They should record only observed audit facts and structural invariants from this pass.

### 6.4 Function Design and Inline Documentation

**File(s):** target Python source files in Section 9
**Type:** Modified

#### What it does

Improve agent readability inside function bodies without changing runtime behavior.

#### Interface / API

```python
def _safe_trace_value(value: Any) -> Any:
    # Redacts nested trace metadata before it reaches provider or trace backends.
    ...
```

#### Logic / Algorithm

1. Convert multi-line signatures to one-line signatures only where the resulting line remains readable and does not violate formatter expectations.
2. Add an immediate one- or two-line comment below signatures that currently have neither a docstring nor an explanatory first comment.
3. Split a long function only if the split is local, semantically obvious, and behavior-preserving.
4. Avoid broad decomposition of core orchestration loops without tests.

#### Edge Cases & Error Handling

- Some signatures are long because of typed public SDK options. If forcing them to one line makes the file materially less readable, the implementation should document the deviation in the handoff rather than perform a risky style-only churn.
- Dataclasses, protocols, and abstract methods may use short docstrings instead of comments when that matches surrounding style.

### 6.5 Intent-Based Comments

**File(s):** target Python source files in Section 9
**Type:** Modified

#### What it does

Add intent comments only beside non-obvious domain or runtime invariants.

#### Interface / API

```python
# @intent fail-closed-policy
# Middleware defaults to aborting when policy code crashes so unsafe tool calls do not continue after a guard fails.
```

#### Logic / Algorithm

1. Identify runtime/domain rules whose "why" is not obvious from code alone.
2. Add comments near the enforcing branch, not only in the module header.
3. Prefer compact `@intent` comments over long narration.
4. Do not tag simple CRUD, one-to-one mappers, imports, or obvious validation branches.

#### Edge Cases & Error Handling

- Avoid comments that restate code mechanics, such as "increments count".
- Use comments to preserve product or safety meaning, such as why non-linear runtimes reject middleware or why trace metadata redacts secret-like keys.

### 6.6 Existing Error Context Enrichment

**File(s):** target Python source files in Section 9, especially `vidbyte/agents/base.py`, `vidbyte/agents/runtime.py`, `vidbyte/agents/aggregation.py`, `vidbyte/agents/settings/loop.py`, `vidbyte/agents/runtimes/configs.py`, `vidbyte/middleware/pipeline.py`, `vidbyte/middleware/builtins/*.py`, `vidbyte/middleware/compaction/*.py`, `vidbyte/tools/catalog.py`, `vidbyte/tools/executor.py`, `vidbyte/tools/function_tool.py`
**Type:** Modified

#### What it does

Make existing failure paths more self-diagnosing while preserving the current SDK exception hierarchy and public behavior.

#### Interface / API

```python
raise ConfigurationError(
    "ActorRuntime max_loop must be at least 1.",
    details={"field": "max_loop", "actual": max_loop, "expected": "integer >= 1"},
)
```

#### Logic / Algorithm

1. Audit target-scope `raise` sites and `ToolResult.error/failure` paths.
2. Add safe `details` to existing `VidbyteSdkError` subclasses when the exception type supports it.
3. Improve returned `ToolResult` metadata where a tool execution path already returns error metadata.
4. Do not include secrets, full prompt text, auth headers, provider API keys, or unbounded outputs.
5. Do not introduce new custom error classes unless an existing local pattern already supports it cleanly.

#### Edge Cases & Error Handling

- Some current errors are plain `ValueError`; changing their type may be a breaking API change, so the implementation should improve messages only unless there is a strong local precedent.
- Some error paths return `ToolResult` instead of raising; those should remain return-based.

---

## 7. Data Model Changes

N/A - This change does not alter schemas, persisted data, dataclasses, Pydantic models, migrations, or package metadata.

---

## 8. API Changes

N/A - This change does not add, modify, or deprecate runtime APIs or HTTP endpoints. Public imports and exports must remain compatible.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agentic-engineering-principles-agents-middleware-tools.md` | Design doc for this feature. |
| CREATE | `vidbyte/agents/algorithms/README.md` | Folder comprehension cache for agent runtime algorithms. |
| CREATE | `vidbyte/agents/runtimes/README.md` | Folder comprehension cache for runtime implementations. |
| CREATE | `vidbyte/agents/runtimes/actor/README.md` | Folder comprehension cache for actor-model runtime internals. |
| CREATE | `vidbyte/agents/settings/README.md` | Folder comprehension cache for agent settings. |
| CREATE | `vidbyte/middleware/builtins/README.md` | Folder comprehension cache for built-in middleware. |
| CREATE | `vidbyte/middleware/compaction/README.md` | Folder comprehension cache for compaction middleware internals. |
| MODIFY | `vidbyte/agents/README.md` | Expand folder README into agentic comprehension cache. |
| MODIFY | `vidbyte/agents/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/agents/aggregation.py` | Add agentic header, intent comments, and safe error context where appropriate. |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | Add agentic header, intent comments, and function documentation cleanup. |
| MODIFY | `vidbyte/agents/algorithms/reflexion.py` | Add agentic header, intent comments, and function documentation cleanup. |
| MODIFY | `vidbyte/agents/base.py` | Add agentic header, intent comments, function documentation cleanup, and safe error context where appropriate. |
| MODIFY | `vidbyte/agents/client.py` | Add or upgrade structured file header and public client inventory. |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Add agentic header and document context-window routing responsibilities. |
| MODIFY | `vidbyte/agents/continual_trace.py` | Add agentic header and intent comments for continual trace behavior. |
| MODIFY | `vidbyte/agents/handoff.py` | Add agentic header, intent comments, and safe parse/error context where appropriate. |
| MODIFY | `vidbyte/agents/mixins.py` | Add agentic header and document MCP attachment responsibilities. |
| MODIFY | `vidbyte/agents/runtime.py` | Add agentic header, intent comments, function documentation cleanup, and safe error context where appropriate. |
| MODIFY | `vidbyte/agents/runtimes/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/agents/runtimes/actor/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/agents/runtimes/actor/actor.py` | Add agentic header and intent comments for actor behavior. |
| MODIFY | `vidbyte/agents/runtimes/actor/broker.py` | Add agentic header, intent comments for concurrency/termination, and safe error context where appropriate. |
| MODIFY | `vidbyte/agents/runtimes/actor/inbox.py` | Add agentic header and document queue semantics. |
| MODIFY | `vidbyte/agents/runtimes/actor/message.py` | Add agentic header and message contract inventory. |
| MODIFY | `vidbyte/agents/runtimes/configs.py` | Add agentic header and safe configuration error context. |
| MODIFY | `vidbyte/agents/runtimes/linear.py` | Add agentic header and runtime compatibility notes. |
| MODIFY | `vidbyte/agents/runtimes/search.py` | Add agentic header and intent comments for search runtime constraints. |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/agents/settings/loop.py` | Add agentic header and safe configuration error context. |
| MODIFY | `vidbyte/agents/types.py` | Add or upgrade structured file header for compatibility re-exports. |
| MODIFY | `vidbyte/middleware/README.md` | Expand folder README into agentic comprehension cache. |
| MODIFY | `vidbyte/middleware/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/middleware/base.py` | Add agentic header and hook contract inventory. |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/middleware/builtins/audit.py` | Add agentic header and intent comments for audit metadata. |
| MODIFY | `vidbyte/middleware/builtins/canary_tripwire.py` | Add agentic header and intent comments for canary leak detection. |
| MODIFY | `vidbyte/middleware/builtins/circuit_breaker.py` | Add agentic header and safe validation error context where appropriate. |
| MODIFY | `vidbyte/middleware/builtins/confused_deputy.py` | Add agentic header and intent comments for deputy-attack guardrails. |
| MODIFY | `vidbyte/middleware/builtins/context_compaction.py` | Add agentic header for compatibility re-exports. |
| MODIFY | `vidbyte/middleware/builtins/cost_budget.py` | Add agentic header and safe validation error context where appropriate. |
| MODIFY | `vidbyte/middleware/builtins/exponential_backoff_retry.py` | Add agentic header and intent comments for retry policy. |
| MODIFY | `vidbyte/middleware/builtins/honeypot_tool.py` | Add agentic header and intent comments for trap tools. |
| MODIFY | `vidbyte/middleware/builtins/loop_detection.py` | Add agentic header and intent comments for soft/hard loop handling. |
| MODIFY | `vidbyte/middleware/builtins/rate_limit.py` | Add agentic header and safe validation error context where appropriate. |
| MODIFY | `vidbyte/middleware/builtins/retry.py` | Add agentic header and intent comments for model retry behavior. |
| MODIFY | `vidbyte/middleware/builtins/runtime_limits.py` | Add agentic header and safe validation error context where appropriate. |
| MODIFY | `vidbyte/middleware/builtins/token_budget.py` | Add agentic header and intent comments for final-response-over-budget behavior. |
| MODIFY | `vidbyte/middleware/builtins/tool_policy.py` | Add agentic header and intent comments for tool allow/deny decisions. |
| MODIFY | `vidbyte/middleware/compaction/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/middleware/compaction/base.py` | Add agentic header and compaction contract inventory. |
| MODIFY | `vidbyte/middleware/compaction/context_compaction.py` | Add agentic header, intent comments, and function documentation cleanup. |
| MODIFY | `vidbyte/middleware/compaction/engine.py` | Add agentic header and compaction mode routing notes. |
| MODIFY | `vidbyte/middleware/compaction/strategies.py` | Add agentic header, intent comments, and local function documentation cleanup. |
| MODIFY | `vidbyte/middleware/compaction/trace_render.py` | Add agentic header and intent comments for trace rendering limits. |
| MODIFY | `vidbyte/middleware/continual_trace.py` | Add agentic header and intent comments for fail-open tracing. |
| MODIFY | `vidbyte/middleware/pipeline.py` | Add agentic header, intent comments for fail-closed/fail-open behavior, and safe error context where appropriate. |
| MODIFY | `vidbyte/tools/README.md` | Expand top-level tools README only, without subfolder edits. |
| MODIFY | `vidbyte/tools/__init__.py` | Add or upgrade structured file header and export inventory. |
| MODIFY | `vidbyte/tools/_internal.py` | Add agentic header for internal agent tool helpers. |
| MODIFY | `vidbyte/tools/adapters.py` | Add agentic header and tool normalization inventory. |
| MODIFY | `vidbyte/tools/agent_tool.py` | Add agentic header and intent comments for agent-as-tool delegation. |
| MODIFY | `vidbyte/tools/base.py` | Add agentic header and tool protocol inventory. |
| MODIFY | `vidbyte/tools/catalog.py` | Add agentic header and safe registration error context where appropriate. |
| MODIFY | `vidbyte/tools/client.py` | Add agentic header and namespace client inventory. |
| MODIFY | `vidbyte/tools/continual_trace.py` | Add agentic header and trace tool responsibilities. |
| MODIFY | `vidbyte/tools/decorators.py` | Add agentic header and decorator contract inventory. |
| MODIFY | `vidbyte/tools/dynamic_actor.py` | Add agentic header and actor-spawning tool intent comments. |
| MODIFY | `vidbyte/tools/executor.py` | Add agentic header, intent comments for permission and validation order, and safe error metadata improvements. |
| MODIFY | `vidbyte/tools/function_tool.py` | Add agentic header, function documentation cleanup, and safe validation/execution error metadata improvements. |
| MODIFY | `vidbyte/tools/mixins.py` | Add agentic header and mixin responsibility inventory. |
| MODIFY | `vidbyte/tools/types.py` | Add agentic header and public dataclass/enum contract inventory. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Existing SDK runtime. | No new risk; unchanged. |
| Pydantic | `>=2,<3` from `pyproject.toml` | Existing tool argument models and dataclasses. | No new risk; unchanged. |
| GitHub prompt URLs | GitHub and raw.githubusercontent.com links in Section 3 | Source of agentic engineering principles used to shape this design. | If upstream prompt files change later, this design reflects the versions loaded on 2026-07-07. |

---

## 11. Rollout & Deployment

- No feature flags are involved.
- No breaking runtime change is intended.
- Rollout is a standard SDK source/docs PR.
- Implementation must occur in a new worktree after explicit approval.
- Verification should include at minimum `python -m compileall vidbyte` to catch syntax damage from signature or comment edits. Test execution is not required by this no-tests workflow, but existing scripts may be referenced in headers.
- Rollback is reverting the PR. Since no schema or public API changes are intended, rollback is source-control only.

---

## 12. Open Questions

- [ ] Should implementation strictly enforce one-line signatures for every touched function even when the resulting line becomes very long, or should readability override that rule with deviations documented in the handoff?
- [ ] Should existing plain `ValueError` validation errors remain plain `ValueError` with clearer messages, or should selected target files migrate those validations to `ConfigurationError` where public behavior allows it?
- [ ] Should the implementation add `details` support to any existing exception class in `vidbyte.lib.errors.base` if a target-scope error needs richer context, or is changing the shared error class out of scope for this pass?

---

## 13. Alternatives Considered

### Alternative 1: Full Agentic Refactor Including Feature Test Packs

- What: Apply every principle literally, including feature test packs and broad function decomposition.
- Why rejected: The user selected `design-doc-no-tests`, and broad behavior refactoring without tests would make this pass riskier than the requested documentation-oriented agentic engineering cleanup.

### Alternative 2: Headers And READMEs Only

- What: Update only file headers and folder READMEs with no inline comments or error context improvements.
- Why rejected: The referenced system prompt explicitly routes function edits to function design, domain logic to intent comments, and server-side failures to rich error context. A headers-only pass would leave major agentic engineering benefits unaddressed.

### Alternative 3: Introduce A New Per-Failure Error Class Taxonomy

- What: Create one custom exception class per failure mode across agents, middleware, and tools.
- Why rejected: The current SDK centralizes public exceptions in `vidbyte.lib.errors.base`, and a new taxonomy spread through target folders would be a public API and maintenance change. This pass should enrich existing error messages/details unless a later approved design focuses specifically on tool/error taxonomy.
