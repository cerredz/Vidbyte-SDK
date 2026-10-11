# Design Doc: Codex Harness Agent README

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-18
**Last Updated:** 2026-09-18

---

## 1. Overview

`vidbyte/agents/codex/` has no README. The package's only developer documentation is a short section in the root `README.md`: one construction example, a tools example, and a context-placement table. This change adds `vidbyte/agents/codex/README.md`, a developer cookbook for `CodexHarnessAgent`. It lists common use cases, and each use case has a code snippet that runs against the current API. Topics include input shapes, Codex settings, structured output, custom tools, turn-boundary middleware, context translation, threads, forks, subagents, fallback chains, usage and cost, error handling, and composition. It also follows the repository's folder-README convention: Intent, Blast Radius, Non-Goals, File Index, and Logs.

---

## 2. Goals & Non-Goals

### Goals
- Create `vidbyte/agents/codex/README.md` at the same level as the package files.
- List the common ways developers use the agent, and give each one a copy-pasteable snippet written from a developer's point of view.
- Cover every use case the user named: Vidbyte translations (context, input, settings), custom tools, middleware, and structured outputs. Also cover further common situations: multi-turn and resumed threads, forks, subagents, fallback, usage and cost, error handling, pipelines, async apps, images and skills, sandbox presets, and custom providers.
- Record non-obvious limits found during the audit so that a developer does not configure something that silently does nothing. Examples: the fallback chain needs `fallback_on=(CodexAgentError,)`, and several built-in middleware are rejected at construction.
- Keep a File Index that passes lint rule S020 (it lists every tracked direct `.py` child).

### Non-Goals
- No change to runtime code, public exports, or behavior.
- No new test files (this is a no-tests workflow). The existing CI must still pass.
- No rewrite of the root `README.md` Codex section. The new README links back to it instead.
- No edits to `llms.txt` or `docs/`.

---

## 3. Background & Context

- **Why now:** The Codex adapter has grown over several PRs: #409 (base), the input bridge, middleware, failure recovery and fallback, usage tracking, and #432 (custom tools). No single developer-facing page shows how these features combine.
- **Problem solved:** A developer currently has to read 12 modules and 1,100 lines of dataclasses to learn which Vidbyte features translate to Codex and which do not. Several limits are silent unless you read the source:
  - With the default `AgentFallbackSettings.fallback_on`, the chain never advances. `DEFAULT_FALLBACK_ERRORS` contains only provider errors, and Codex raises `CodexAgentError`.
  - Most built-in middleware override inner-loop hooks, so `CodexMiddlewareValidator` rejects them at construction. `ModelRetryMiddleware` and `ExponentialBackoffRetryMiddleware` pass validation, but their `on_model_error` decision is discarded, so they never retry.
  - `CodexHarnessAgent` has no `generate_reply`, so it cannot be a `BasePipeline` stage directly.
  - `run()` raises inside an active event loop.
  - `reply.codex.usage` is cumulative for the thread. `last_usage` is the per-turn snapshot.
- **Current state:** Root `README.md` lines ~197–335 hold a short Codex section. `vidbyte/agents/codex/` has no README.
- **Constraints:** The repository's `AGENTS.md` says not to read `docs/` during ordinary work, so this design is based on source only. Writing a new design doc there is part of this workflow. The folder README convention (see `vidbyte/agents/multi/README.md`) and lint rule S020 govern the File Index.

---

## 4. Requirements

### Functional Requirements
1. `vidbyte/agents/codex/README.md` exists, next to `agent.py`.
2. It has a use-case index (a list) that links to each recipe.
3. Each recipe has at least one Python snippet that uses only public, verified import paths.
4. Recipes cover:
   - quick start (sync and async)
   - input shapes (`str`, `AgentInput`, `CodexRunInput` with image, local image, skill, and mention items)
   - Codex settings (client, thread, and turn layers, and precedence)
   - sandbox and approval presets
   - structured output (Pydantic model and mapping schema, plus violation handling)
   - custom tools (`@tool`, async tool, `BaseTool`, permission policy, description customization, naming rules)
   - middleware (a guard that aborts, an audit or metadata step, an error observer, and the supported and unsupported hooks)
   - Vidbyte context translations (additional context, `ContextManager` placements, per-turn context items, request-scoped managers, native anchors, manager metadata)
   - multi-turn and resumed threads
   - forks
   - subagents
   - fallback chains
   - usage and cost
   - error handling and failure codes
   - composition (pipelines, parallel fan-out, async web apps)
   - custom model providers and binaries
   - reading results
5. It documents the limits listed in §3 next to the recipes they affect.
6. It has Intent, Blast Radius, Non-Goals, File Index, and Logs sections, following the folder-README convention.
7. The File Index lists all 12 tracked `.py` files in the folder, and S020 passes.

### Non-Functional Requirements
- **Accuracy:** Snippets are checked offline in a scratch script. The script patches `CodexTransport.run` and `CodexTransport.fork_thread` with fakes and executes each block, so construction, input and context translation, middleware, and structured-output validation run for real. The script is not committed.
- **Performance / Scalability / Observability:** N/A (documentation only).
- **Security:** Snippets never hard-code credentials. Sandbox guidance defaults to the narrowest mode.
- **Reliability:** The full `python scripts/run_ci.py` gate must pass.

---

## 5. High-Level Design

This change adds one Markdown file and changes no code. The README is ordered by developer intent. It starts with what the agent is and a quick start, then gives a use-case index. Each recipe follows the same pattern: when to use it, a snippet, and the pitfalls. Reference material (supported feature matrix, failure codes, file index) comes at the end, so a first-time reader reaches running code quickly.

```
README.md (root) ── short Codex overview ──► links to ──► vidbyte/agents/codex/README.md
                                                          ├─ Intent + quick start
                                                          ├─ Use-case index → 18 recipes
                                                          ├─ What translates / what doesn't (matrix)
                                                          ├─ Failure-code reference
                                                          └─ Blast Radius / Non-Goals / File Index / Logs
```

Key decision: document what the code does today, including its sharp edges, rather than an idealized API. Where something is not supported (for example a pipeline stage or inner-loop middleware), the README shows the supported workaround using public API only, such as a `BasePipeline` subclass or `fallback` in place of retry middleware.

---

## 6. Detailed Design

### 6.1 Codex package README

**File(s):** `vidbyte/agents/codex/README.md`
**Type:** New file

#### What it does
It is the developer cookbook and folder map for the Codex harness adapter.

#### Interface / API
Documentation only. It references these public symbols:
- From `vidbyte`: `CodexHarnessAgent`, `CodexHarnessAgentSettings`, `CodexAgentSettings`, `CodexClientSettings`, `CodexThreadSettings`, `CodexTurnSettings`, `CodexSubagentSettings`, `CodexForkSettings`, `CodexRunInput`, the input item types, `CodexContextPlacement`, the enums, `AgentInput`, `ContextManager`, the context primitives, `ContextWindowPlacement`, `tool`, `BaseTool`, `ToolPermission`, `AgentMiddleware`, `MiddlewareDecision`, `MiddlewareContext`, `CodexAgentError`, and `OutputSchemaViolationError`.
- From submodules: `vidbyte.tools.security.PermissionPolicy`, `vidbyte.agents.AgentFallbackSettings`, `vidbyte.agents.FallbackModel`, `vidbyte.pipelines.base.BasePipeline`, and `vidbyte.tools.types`.

#### Logic / Algorithm
1. Title, then a one-paragraph intent.
2. Install and quick start.
3. Use-case index.
4. Recipes 1–18.
5. The feature matrix: what translates and what is rejected.
6. Failure-code table.
7. Blast Radius, Non-Goals, File Index (12 entries), and Logs.

#### Edge Cases & Error Handling
- **S020:** The `## File Index` section may contain backticked `.py` names only for direct children. Snippets and prose that mention other `.py` files must go in other sections.
- **Drift:** If a snippet references a symbol that later changes, the README goes stale. The Logs entry records the audit date and the SDK pin (`openai-codex>=0.147,<0.148`).

---

## 7. Data Model Changes

N/A. This change is documentation only and changes no schema or dataclass.

---

## 8. API Changes

N/A. There are no endpoint or public Python API changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-harness-agent-readme.md` | This design doc |
| CREATE | `vidbyte/agents/codex/README.md` | Developer cookbook and folder map for `CodexHarnessAgent` |
| MODIFY | `README.md` | One line under the Codex section linking to the new package README |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` (optional extra `vidbyte-sdk[codex]`) | `>=0.147.0,<0.148.0` | Referenced by the install instructions only | Enum values documented in the README track this pin |

---

## 11. Rollout & Deployment

- No feature flags.
- Not a breaking change.
- Rollback: revert the commit.

---

## 12. Open Questions

- [ ] Should `CodexHarnessAgent` gain `generate_reply` so it can be a native pipeline stage? This is out of scope here. The README documents the wrapper workaround.
- [ ] Should the Codex fallback default `fallback_on` to `(CodexAgentError,)` so that a chain works without extra configuration? This is out of scope. The README documents the explicit setting.

---

## 13. Alternatives Considered

### Alternative 1: Expand the root README's Codex section
- **What:** Add all the recipes to `README.md`.
- **Why rejected:** The root README is already long and covers every layer. The user asked for a README at the package level, and the repository convention places folder READMEs beside the code.

### Alternative 2: Add a runnable examples module or notebook
- **What:** Put the recipes in `examples/codex/*.py`.
- **Why rejected:** The repository has no examples package. Cookbook notebooks live in a separate repository. A README matches the request.

---

## CI

The canonical gate is `python scripts/run_ci.py`. From a worktree, run the source stage with `PYTHONPATH=<worktree>`, and run the package stage without it (see the field guide, "Local CI Verification"). Run `python lint/run.py --rule S020` to check the File Index quickly.
