# Design Doc: SDK Documentation Refresh From Recent PRs

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-06
**Last Updated:** 2026-07-06

---

## 1. Overview

Refresh the Vidbyte SDK repository's central docs after auditing the most recent mainline PRs. The change will update the root `README.md`, `llms.txt`, and the relevant skill files so they accurately describe recently added or changed capabilities: durable-session follow-ups, agent-native session entry points, portable session bundles, usage rollups, session batch forking, tag/name lookup, the richer agent fork tool, provider-aware tool-error policy, semantic trace profiles, repository artifacts, and recent skill-reference cleanup.

---

## 2. Goals & Non-Goals

### Goals

- Audit the recent merged PRs on `main` and summarize the repo-visible additions they introduced.
- Update `README.md` so the central human-facing repo overview reflects current SDK capabilities.
- Update `llms.txt` so LLM-oriented retrieval has the same current feature surface and guidance.
- Update the skill files that future agents will consult when using or modifying the affected SDK areas.
- Keep this as a documentation-only change; do not change Python behavior, tests, package metadata, or generated artifacts.
- Preserve the public SDK boundary: document reusable SDK abstractions without implying private Vidbyte platform internals are included.

### Non-Goals

- N/A - no source-code feature changes.
- N/A - no new tests or verification scripts because the requested change is documentation-only and the selected workflow is `design-doc-no-tests`.
- N/A - no rewrites of unrelated docs, design docs, or historical PR records.
- N/A - no broad reformatting of existing Markdown beyond the sections needed for accuracy.
- N/A - no changes to nested local worktrees or currently untracked user files.

---

## 3. Background & Context

The working checkout is on `feat/context-minimal-fanout-trace` and contains existing untracked files. `origin/main` is newer than the local branch and includes merges through `0f14864` (`fix: resolve SDK review comments from PR #238`). This design treats `origin/main` and the GitHub PR metadata as the source of truth for the docs refresh, and the implementation phase must start from a fresh worktree branched from updated `main`.

Recent mainline PRs audited:

| PR | Title | Main documentation impact |
|----|-------|---------------------------|
| #240 | `fix: resolve SDK review comments from PR #238` | Tool-error policy is retry/abort only; terminal tool errors render full detail through `ToolsFormatter`; `ToolErrorPolicy` lives in agent loop settings. |
| #236 | `fix: resolve review comments from PR #229` | `ForkConversationTool` is a Vidbyte-native agent fork primitive with SDK-native parts: model/provider, runtime, context window, handoff, output schema, MCP carry, run-state carry, tools, and depth controls. |
| #232 | `docs: add artifacts/file_index.md` | New `artifacts/` repo artifact folder and `artifacts/file_index.md` compressed structural map. |
| #231 | `feat: Agent Session Entry Points` | `agent.persist(...)`, `agent.session`, public `bind_session`, and agent-direct `run`/`arun` persistence for bound sessions. |
| #230 | `feat: Remove MCP Install Doc and Skill` | Removed the standalone MCP install doc/skill references; central docs should avoid pointing to deleted install artifacts. |
| #228 | `fix: resolve SDK review comments from PR #226` | Portable session export/import through `Session.export()`, `sdk.harnesses.sessions.export(...)`, and `import_(...)`. |
| #227 | `fix: resolve SDK review comments from PR #225` | Session usage rollups via `Session.usage(...)`, typed usage dataclasses, and validation errors. |
| #224 | `feat: Session Batch Fork` | `Session.batch_fork(...)`, `ForkOutcome`, and `BatchForkTool` with bounded `count`. |
| #223 | `feat: Session Tagging and Name Resolution` | Session tags/names, `Session.tag(...)`, store `resolve(...)`, filtered `list_sessions(...)`, and tool descriptions updated for named sessions. |
| #222 | `fix: isolate agent fork state` | Agent fork state isolation and safer carry semantics for handoff, MCP, runtime state, and tool-bound context. |
| #221 | `fix: resolve SDK review comments from PR #135` | Durable sessions baseline: `vidbyte/sessions`, stores, DB provider adapters, prebuilt session tools, `skills/sessions.md`, `skills/forking.md`. |
| #220 | `docs: expand handoff skill reference` | Handoff skill is already expanded; it should not be duplicated unless cross-links need adjustment. |
| #208 | `fix: resolve SDK review comments from PR #198` | Semantic trace profiles, `vidbyte/trace/components/`, LangSmith defaults/session tracing, trace skill maintenance rules. |
| #205 | `fix: rewrite paradigm SKILL.md` | Paradigm skill is already rewritten as conceptual repo guidance; central references should align with it. |
| #203 | `fix: resolve SDK review comments from PR #190` | Agentic Engineering prompt-family conclusion sections; current docs may only need high-level prompt/skill consistency. |

Audit findings:

- `README.md` and `llms.txt` already include durable sessions and semantic trace profiles, but they do not fully cover all follow-up session capabilities: batch fork, tags/name resolution, portable export/import, and usage rollups.
- `skills/sessions.md` includes agent `persist` and baseline session tools, but does not yet document batch fork, tags/name resolution, export/import bundles, or usage rollups.
- `skills/forking.md` covers durable session fork/rewind/resume modes, but not `BatchForkTool` or the separate `ForkConversationTool` agent-bound runtime fork primitive.
- `skills/usage/available_tools.md` does not list session tools or `ForkConversationTool`, despite both being built-in model-callable tools.
- `skills/usage/available_features.md` does not yet summarize durable sessions, artifact sources/repo artifacts, tool-error policy, or the newest fork/session additions.
- `skills/vidbyte-sdk/SKILL.md` is stale relative to `skills/sdk/SKILL.md`; it still references old `strategies` layout and lacks sessions, semantic trace components, sources, session stores, and expanded built-in tool categories.
- `skills/vidbyte-sdk/middleware.md` lists 13 baseline middleware plus compaction, but does not document `ToolErrorPolicyMiddleware` and the full-detail tool-error rendering rule from PR #240.
- `skills/sdk/update-skill-files.md` lacks explicit maintenance rows for session changes, tool-error policy changes, agent-bound fork tool changes, and repo artifacts.

---

## 4. Requirements

### Functional Requirements

1. `README.md` must summarize the current recent-PR feature surface, including durable session follow-ups, agent-native persistence, native fork tooling, tool-error retry policy, semantic trace profiles, and `artifacts/file_index.md`.
2. `llms.txt` must include equivalent LLM-ingestion guidance for those same features and preserve the removed-MCP-install-doc cleanup from PR #230.
3. `skills/sessions.md` must document `Session.batch_fork`, `BatchForkTool`, `Session.tag`, store `resolve`, `list_sessions`, `Session.usage`, portable export/import, and agent `persist`.
4. `skills/forking.md` must distinguish durable-session DAG fork/resume from `ForkConversationTool`, including when to use each and how fork isolation/non-escalation works.
5. `skills/usage/available_tools.md` must add built-in session tools and agent forking tools with import paths and concise descriptions.
6. `skills/usage/available_features.md` must add or update sections for durable sessions, artifact sources/repo artifacts, tool-error policy, and agent forking.
7. `skills/usage/create_agent.md` must document agent-native persistence (`persist`, `session`, bound `run`/`arun`) and, if present in the file's style, constructor/setting notes for `AgentLoopSettings.tool_error_policy`.
8. `skills/usage/create_agent_with_tools.md` must show how to attach `ForkConversationTool`, session tools, and explain permission/non-escalation constraints.
9. `skills/sdk/SKILL.md` must have an up-to-date framework map and rules for sessions, sources, artifacts, semantic trace components, tool-error policy, and built-in tool categories.
10. `skills/vidbyte-sdk/SKILL.md` must be brought in line with current package layout and rules, removing stale `strategies` guidance and adding sessions/sources/trace components/tool categories.
11. `skills/vidbyte-sdk/middleware.md` must document `ToolErrorPolicyMiddleware`, `ToolErrorPolicy`, idempotent retry gates, total-error circuit breaking, unrecoverable behavior, and the rule that terminal tool errors render full detail.
12. `skills/sdk/update-skill-files.md` must add update-matrix entries for session changes, agent-bound fork tool changes, tool-error policy changes, repo artifacts, and central `llms.txt`/README refreshes.
13. `skills/vidbyte-sdk-doc/SKILL.md` must be updated where it acts as an exhaustive repo reference so it does not contradict the central README or skill index.
14. The updates must be grounded in `origin/main` source files and the audited PR list, not the stale local branch state.
15. The implementation must avoid modifying untracked local files unrelated to this design.

### Non-Functional Requirements

- Accuracy: every documented import path, class, method, and file path must exist on `origin/main`.
- Consistency: README, `llms.txt`, and skill files must use the same terminology for sessions, forking, middleware, and tracing.
- Scannability: additions should be compact and sectioned; do not bury new features in long prose blocks only.
- Maintainability: skill files should point future contributors to the correct canonical reference instead of duplicating every detail everywhere.
- Security: docs must mention that credentials/API keys are not model-controlled in `ForkConversationTool`, session serialization scrubs credential-like keys, and DB session stores import drivers lazily.
- Reliability: docs must mention fail-open session persistence and fail-open/full-detail behavior where relevant.
- Observability: docs must mention semantic trace components and session trace capture at the conceptual level.

---

## 5. High-Level Design

This is a coordinated Markdown documentation refresh. The implementation will keep `README.md` as the human-facing central overview, `llms.txt` as the LLM-ingestion bundle, and the skills tree as the operational source of truth for future agents and contributors. The central docs will carry concise public-facing summaries; the skill files will hold the exact usage and maintenance rules.

The main design decision is to avoid creating a new standalone "recent PRs" document as the final user-facing artifact. The user asked to update the central readme, `llms.txt`, and skills with what was added to the repo; therefore, the new information belongs in those existing surfaces. The design doc itself will remain the implementation record.

```text
Recent PR audit
    |
    +-- README.md              human repo overview
    +-- llms.txt               LLM retrieval bundle
    `-- skills/
        +-- sdk/               contributor map and update matrix
        +-- sessions.md        durable session usage source of truth
        +-- forking.md         fork/resume and agent-fork guidance
        +-- usage/             task recipes and catalogs
        `-- vidbyte-sdk/       package layout and middleware reference
```

No Python APIs, package metadata, or tests change in this PR.

---

## 6. Detailed Design

### 6.1 Design document

**File(s):** `docs/design/sdk-doc-refresh-recent-prs.md`
**Type:** New file

#### What it does

Records this documentation-only plan, the audited PR set, requirements, risks, and file manifest.

#### Interface / API

```text
docs/design/sdk-doc-refresh-recent-prs.md
```

#### Logic / Algorithm

1. Record the recent PR audit and source-of-truth decision.
2. Define every central doc and skill file that will change.
3. Stop for approval before writing implementation docs.

#### Edge Cases & Error Handling

- If the user wants a narrower update set, remove files from the manifest before implementation.
- If `main` cannot be updated or a worktree cannot be created during Phase 3, stop before implementation.

### 6.2 Root README

**File(s):** `README.md`
**Type:** Modified

#### What it does

Serves as the central human-facing overview of the SDK repository.

#### Interface / API

```markdown
## Layer Guide
## Tracing
## Tools
## Middleware
## Durable Sessions
## Repository Artifacts
## Package Structure
```

#### Logic / Algorithm

1. Add `vidbyte.sessions` and `vidbyte.sources` to the layer/package overview if missing or incomplete.
2. Expand the Durable Sessions section with agent `persist`, `session`, batch fork, tags/name resolution, export/import, and usage rollups.
3. Add concise guidance for `ForkConversationTool` under tools or agent forking.
4. Add concise guidance for `ToolErrorPolicy` / `ToolErrorPolicyMiddleware` under middleware.
5. Mention `artifacts/file_index.md` as the repo structural map companion to `llms.txt`.
6. Keep code examples short and importable.

#### Edge Cases & Error Handling

- Avoid duplicating the full sessions skill content in README; link or point to skill files for depth.
- Preserve the alpha/public-boundary wording.

### 6.3 LLM documentation bundle

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Provides the agent-oriented documentation bundle used for LLM retrieval and MCP/doc indexing.

#### Interface / API

```text
# Vidbyte SDK Documentation for LLMs
## Feature Summary
## Core Features
## Durable Sessions
## Tools
## Middleware
## Package Map
## Docs-to-MCP Submission Notes
```

#### Logic / Algorithm

1. Mirror the README additions in more retrieval-friendly prose.
2. Include exact class/method names for session follow-ups and fork/tool-error features.
3. Keep deleted MCP install doc references out of primary reference lists.
4. Add `artifacts/file_index.md` to recommended indexing notes as a compressed map.

#### Edge Cases & Error Handling

- Preserve the file's role as an LLM bundle, not a changelog.
- If the UTF-8 BOM remains in the file, preserve it rather than re-encoding unnecessarily.

### 6.4 SDK meta skill

**File(s):** `skills/sdk/SKILL.md`
**Type:** Modified

#### What it does

Acts as the current contributor map and package-boundary rule file for the SDK.

#### Interface / API

```markdown
## Framework Boundaries
## Core Use Cases
## Usage Skill Files
## SDK Developer Reference
## Package Structure
## Rules
## Semantic Trace Components
```

#### Logic / Algorithm

1. Add/verify framework rows for Sessions, Sources, Trace, Middleware, Tools, and Artifacts as needed.
2. Add recent-session capabilities to Core Use Cases and Rules.
3. Add rules for `ToolErrorPolicyMiddleware` and full-detail tool-error rendering.
4. Add `ForkConversationTool` / `fork` built-in category rules.
5. Add skill references for sessions and forking if not already present.

#### Edge Cases & Error Handling

- Do not reintroduce removed `strategies` guidance.
- Keep this as a map and rule file, not a usage tutorial.

### 6.5 Legacy SDK structure skill alignment

**File(s):** `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Provides the broad SDK structure reference used by older or alternate skill routing.

#### Interface / API

```markdown
# Vidbyte SDK Structure
## Current Layout
## Rules
## Semantic Trace Components
```

#### Logic / Algorithm

1. Bring the current layout tree in line with `origin/main`, including `sessions`, `sources`, `paradigms`, `trace/components`, and expanded tool categories.
2. Remove stale `vidbyte/strategies/` and `sdk.strategies` instructions.
3. Add rules that point to `skills/sessions.md`, `skills/forking.md`, `skills/sources/SKILL.md`, and `skills/vidbyte-sdk/middleware.md`.
4. Keep the file compatible with existing skill naming and context-header style.

#### Edge Cases & Error Handling

- If content substantially overlaps `skills/sdk/SKILL.md`, keep references consistent rather than inventing a different architecture.

### 6.6 Session skill

**File(s):** `skills/sessions.md`
**Type:** Modified

#### What it does

Canonical usage guide for durable sessions.

#### Interface / API

```markdown
# Durable Sessions
## Attach in one line
## Stores
## The verbs
## Tags and lookup
## Usage rollups
## Portable bundles
## Prebuilt agent-facing tools
## Rules of thumb
```

#### Logic / Algorithm

1. Add examples for `session.tag(...)`, `store.resolve(...)`, and `store.list_sessions(...)`.
2. Add `session.batch_fork(...)` and `BatchForkTool`.
3. Add `session.usage(prices=...)` and the rollup fields.
4. Add `session.export()`, `sdk.harnesses.sessions.export(...)`, and `sdk.harnesses.sessions.import_(...)`.
5. Keep `agent.persist(...)` guidance and clarify it delegates to `Session`.

#### Edge Cases & Error Handling

- Clarify `BatchForkTool` creates branches only; it does not run child sessions.
- Clarify same-id import requires an absent session unless `new_id=` is provided.

### 6.7 Forking skill

**File(s):** `skills/forking.md`
**Type:** Modified

#### What it does

Explains branch, rewind, resume, batch fork, and runtime fork patterns.

#### Interface / API

```markdown
# Forking and Resuming Agent Threads
## Durable session fork
## Batch fork
## Agent-native conversation fork
## Cross-thread resume
## Cross-agent access
## Patterns
```

#### Logic / Algorithm

1. Add a section for `Session.batch_fork(...)` and `BatchForkTool`.
2. Add a section for `ForkConversationTool`, describing it as agent-bound, non-escalating, and separate from durable session DAG operations.
3. Document supported fork parts: history mode, tools, extra toolsets, provider/model, modality, runtime/actor runtime, context-window algorithm, loop settings, handoff, output schema, runner options, metadata, run-state carry, and MCP carry.
4. Explain isolation from PR #222 and review follow-up PR #236.

#### Edge Cases & Error Handling

- Do not imply model-controlled credentials or permission escalation.
- Do not confuse `ForkTool`/`BatchForkTool` durable session branches with `ForkConversationTool` child agent execution.

### 6.8 Usage tool catalog

**File(s):** `skills/usage/available_tools.md`
**Type:** Modified

#### What it does

Catalogs built-in tools available out of the box.

#### Interface / API

```markdown
## Agent Forking
## Session Tools
```

#### Logic / Algorithm

1. Add `ForkConversationTool` import and summary.
2. Add durable session tools: `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`, and `SessionTool`.
3. Mention session tools bind to a `Session` and are gated by `SessionScope`.
4. Keep permissions accurate: these tools are `SAFE` in the SDK but operate over permitted session scope.

#### Edge Cases & Error Handling

- Avoid listing non-tool classes such as `ToolErrorPolicy` in the tools catalog.

### 6.9 Usage feature catalog

**File(s):** `skills/usage/available_features.md`
**Type:** Modified

#### What it does

Summarizes major SDK features and where to go for deeper docs.

#### Interface / API

```markdown
## Durable Sessions
## Agent Forking
## Tool Error Policy
## Repository Artifacts
## Artifact Sources
```

#### Logic / Algorithm

1. Add durable sessions as a first-class feature with current verbs and stores.
2. Add `agent.persist(...)` and `sdk.harnesses.sessions`.
3. Add agent forking and `ForkConversationTool`.
4. Add tool-error policy under middleware/reliability.
5. Add `artifacts/file_index.md` as repo artifact and keep `vidbyte.sources` as artifact-to-context loaders.

#### Edge Cases & Error Handling

- Keep "available features" broad; link to detailed skills instead of expanding every method.

### 6.10 Create agent usage skill

**File(s):** `skills/usage/create_agent.md`
**Type:** Modified

#### What it does

Shows how to construct and run agents.

#### Interface / API

```markdown
## Durable agent sessions
## Loop settings and tool-error policy
```

#### Logic / Algorithm

1. Add a compact example for `agent.persist(store=...)`, `agent.session`, and direct persistent `agent.arun(...)`.
2. Add `AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))` if the file already documents loop settings.
3. Cross-link to `skills/sessions.md` and `skills/vidbyte-sdk/middleware.md`.

#### Edge Cases & Error Handling

- Avoid overloading the basic create-agent tutorial with every session verb.

### 6.11 Create agent with tools usage skill

**File(s):** `skills/usage/create_agent_with_tools.md`
**Type:** Modified

#### What it does

Shows how to attach custom and built-in tools to agents.

#### Interface / API

```markdown
## Built-in tools
## Agent forking tool
## Session tools
```

#### Logic / Algorithm

1. Add `ForkConversationTool` as an agent-bound built-in.
2. Add durable session tool attachment example.
3. Mention `Session` auto-binds session tools found on the wrapped agent.
4. Explain permission/non-escalation constraints for fork tooling.

#### Edge Cases & Error Handling

- Clarify `ForkConversationTool` runs a child branch and returns the child reply as a tool result.
- Clarify `BatchForkTool` does not execute child runs.

### 6.12 Middleware skill

**File(s):** `skills/vidbyte-sdk/middleware.md`
**Type:** Modified

#### What it does

Detailed reference for middleware hooks, decisions, built-ins, and implementation rules.

#### Interface / API

```markdown
## Built-in Middleware Catalog
## Tool Error Policy
```

#### Logic / Algorithm

1. Update the built-in count to include `ToolErrorPolicyMiddleware`.
2. Add a reliability subsection for `ToolErrorPolicyMiddleware`.
3. Document `ToolErrorPolicy` fields: `max_retries_per_tool_call`, `retry_on`, backoff settings, `retry_only_idempotent`, `on_unrecoverable`, and `max_total_tool_errors`.
4. State that rendering detail is not a policy knob; terminal tool errors always render full detail through the formatter.

#### Edge Cases & Error Handling

- Do not reintroduce removed `ErrorVerbosity` or `ToolErrorRenderOptions`.

### 6.13 Skill update matrix

**File(s):** `skills/sdk/update-skill-files.md`
**Type:** Modified

#### What it does

Defines which skill files must change when repo features change.

#### Interface / API

```markdown
## Change Type -> Skill File Matrix
### Add or Change Durable Sessions
### Add or Change Agent Forking
### Add or Change Tool Error Policy
### Add Repository Artifacts
```

#### Logic / Algorithm

1. Add session-change matrix rows for `skills/sessions.md`, `skills/forking.md`, `README.md`, `llms.txt`, `skills/usage/available_features.md`, and `skills/usage/available_tools.md`.
2. Add fork-tool matrix rows.
3. Add tool-error policy matrix rows.
4. Add repository artifact matrix rows for `artifacts/`, `README.md`, `llms.txt`, and `artifacts/file_index.md`.

#### Edge Cases & Error Handling

- Keep this file prescriptive, not historical.

### 6.14 Comprehensive SDK doc skill

**File(s):** `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** Modified

#### What it does

Acts as the exhaustive repo reference for agents and contributors.

#### Interface / API

```markdown
Package map, subsystem references, public API notes, and contribution guardrails.
```

#### Logic / Algorithm

1. Update package maps and subsystem summaries for sessions, sources, artifact file index, semantic trace components, tool-error policy, and agent fork tooling.
2. Ensure examples and reference text do not contradict README/`llms.txt`.

#### Edge Cases & Error Handling

- If this file is very large, keep edits targeted to stale sections.

---

## 7. Data Model Changes

N/A - This is a documentation-only change. No dataclasses, schemas, persisted data, or migrations will be modified.

---

## 8. API Changes

N/A - This is a documentation-only change. Existing Python APIs will only be described.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/sdk-doc-refresh-recent-prs.md` | Design doc for the recent-PR documentation refresh |
| MODIFY | `README.md` | Update central human-facing repo overview with recent features |
| MODIFY | `llms.txt` | Update LLM-oriented bundle with recent features and current indexing guidance |
| MODIFY | `skills/sdk/SKILL.md` | Update contributor map and rules for recent package/documentation changes |
| MODIFY | `skills/sdk/update-skill-files.md` | Add maintenance rules for sessions, fork tooling, tool-error policy, and artifacts |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Align legacy/broad SDK structure skill with current package layout |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Keep exhaustive SDK reference aligned with central docs |
| MODIFY | `skills/sessions.md` | Document session follow-up capabilities added after the baseline sessions PR |
| MODIFY | `skills/forking.md` | Document batch fork and agent-native fork tool semantics |
| MODIFY | `skills/usage/available_features.md` | Add durable sessions, forking, artifacts, and tool-error policy to the feature catalog |
| MODIFY | `skills/usage/available_tools.md` | Add built-in agent fork and session tool categories |
| MODIFY | `skills/usage/create_agent.md` | Add agent-native persistence and tool-error policy usage notes |
| MODIFY | `skills/usage/create_agent_with_tools.md` | Add fork/session tool attachment guidance |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Add tool-error policy middleware and full-detail rendering guidance |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| GitHub PR metadata via `gh` | `cerredz/Vidbyte-SDK` | Audit recent merged PR list and touched files | Low - already fetched/read during design; implementation can rely on `origin/main` source if GitHub is unavailable |
| Local git remote | `origin/main` | Source of truth for current files and API names | Medium - implementation must update local `main` and create a fresh worktree before editing |

No new runtime dependencies or services.

---

## 11. Rollout & Deployment

- No feature flags.
- No package release or runtime deployment required.
- Rollout is merge of a documentation-only PR.
- Rollback is reverting the documentation commits.
- Implementation must begin from a fresh worktree after updating `main`.
- Verification should include Markdown/readability review and link/path/import sanity checks. No test suite is required by this workflow.

---

## 12. Open Questions

- [ ] Should `README.md` include a short "Recent Additions" section, or should all additions be woven into existing subsystem sections? Plan: weave into existing sections to avoid a stale changelog.
- [ ] Should `skills/vidbyte-sdk/SKILL.md` be made a near-match of `skills/sdk/SKILL.md`, or kept as a shorter legacy compatibility guide? Plan: keep it as a structure guide but align all layout/rules.
- [ ] Should `skills/vidbyte-sdk/sessions.md` remain a redirect to root `skills/sessions.md`, or should it duplicate the expanded content? Plan: keep the redirect to avoid two session sources of truth.

---

## 13. Alternatives Considered

### Alternative 1: Only update README and llms.txt

- What: Leave skill files untouched.
- Why rejected: The user explicitly asked for "any skill files", and several skill files are currently stale relative to recent PRs. Future agents rely on those files for repo work, so leaving them stale would preserve the actual problem.

### Alternative 2: Add a separate changelog of recent PRs

- What: Create a new doc summarizing the last 15 PRs without changing central docs.
- Why rejected: The request is to update central docs with what was added, not create a historical PR digest. A changelog would not fix stale usage guidance.

### Alternative 3: Regenerate llms.txt from README automatically

- What: Build a generator that derives `llms.txt` from README and skill files.
- Why rejected: No generator exists in the repo, and adding one is outside this docs-only request. Manual targeted edits are lower risk for this update.

### Alternative 4: Update every skill file

- What: Sweep the entire `skills/` tree and rewrite all stale-looking content.
- Why rejected: The blast radius would be high and unrelated to the recent PRs. The manifest targets files that either centralize SDK knowledge or directly cover the changed features.
