# Design Doc: Vidbyte SDK Doc Skill

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Create a new repository-local Codex skill named `vidbyte-sdk-doc` that acts as the main comprehensive reference for the Vidbyte SDK repository. The skill will live under `skills/vidbyte-sdk-doc/SKILL.md` and document the SDK's public surface, package layout, design-doc history, development rules, tests, and subsystem responsibilities in enough detail for future agents to understand what the repo offers before changing it.

---

## 2. Goals & Non-Goals

### Goals

- Add a new `vidbyte-sdk-doc` skill package with a complete `SKILL.md` file.
- Cover the current SDK surface: root client, agents, modality routing, strategies, multi-agent orchestration, tools, MCP, filesystem tools, providers, runners, prompts, contexts, dataclasses, enums, errors, harnesses, tests, and repository conventions.
- Summarize all existing design docs and call out when design docs are historical, superseded, or locally untracked.
- Provide future Codex agents with practical instructions for reading, modifying, and verifying the SDK.
- Keep the change documentation-only and avoid altering runtime behavior.

### Non-Goals

- No changes to Python package code under `vidbyte/`.
- No new tests unless a repository convention requires tests for skill markdown files.
- No changes to existing `skills/vidbyte-sdk/SKILL.md` or `skills/vidbyte-sdk/adding-prompts.md`.
- No attempt to implement pending design docs such as pipelines or minimal agent runtime.
- No generated API reference from introspection tooling; the skill will be hand-curated from the audited source and design docs.

---

## 3. Background & Context

The SDK has grown from a minimal namespace scaffold into a broad Python package with agents, strategies, tools, provider adapters, prompt assets, runners, contexts, and many design docs. The existing `skills/vidbyte-sdk/SKILL.md` is a concise structure guide; it does not explain the full SDK offering or how the design docs relate to the current implementation. The requested `vidbyte-sdk-doc` skill should become the deeper local reference for agents working in this repository.

Current repository characteristics from audit:

- Python package built with `setuptools` via `pyproject.toml`.
- Runtime dependency is currently `pydantic>=2,<3`; most other implementation uses the Python standard library.
- Python version requirement is `>=3.11`.
- Public package namespace is `vidbyte`.
- Tests use `unittest` and are discovered with `python -m unittest discover -s tests`.
- Existing verification commands in README are `python -m compileall vidbyte`, `python -m unittest discover -s tests`, and a root import smoke test.
- There is no repo-local CI/config file found beyond `pyproject.toml`.
- `main` is currently clean for tracked files, with local untracked docs at `docs/design/minimal-agent-runtime.md` and `docs/design/pipelines.md`.

Relevant source material:

- README and existing skill docs.
- All files under `vidbyte/`.
- Existing tests under `tests/`.
- Design docs under `docs/design/`, including tracked docs and the two local untracked design docs visible in the workspace.

---

## 4. Requirements

### Functional Requirements

1. The repository must contain a new skill package at `skills/vidbyte-sdk-doc/`.
2. The skill package must contain `skills/vidbyte-sdk-doc/SKILL.md`.
3. `SKILL.md` must include valid skill frontmatter with `name: vidbyte-sdk-doc`.
4. `SKILL.md` must describe the skill's purpose as a comprehensive Vidbyte SDK repository reference.
5. `SKILL.md` must document the repository identity, package metadata, package manager/build backend, Python version, dependency posture, and verification commands.
6. `SKILL.md` must document the top-level SDK package layout and the responsibility of each major package.
7. `SKILL.md` must document the root public surface exposed from `vidbyte.__init__` and `VidbyteSDK`.
8. `SKILL.md` must document agents, including `BaseAgent`, `Agent` alias behavior if present, `AgentInput`, `AgentMessage`, `AgentCard`, `AgentRegistry`, modality routing, runner creation, tool loop behavior, and MCP attachment lifecycle.
9. `SKILL.md` must document strategies, including base strategy contracts, reasoning strategies, sampling strategies, agent-loop strategies, routing strategies, ReAct/CodeAct/Reflexion, and multi-agent strategies.
10. `SKILL.md` must document tools, including `Tools`, `@tool`, `@vidbyte_tool`, `FunctionTool`, `BaseTool`, `ToolRegistry`, `ToolExecutor`, tool dataclasses, provider schema formatting, security, permissions, built-ins, code search, editing, context compaction, document retrieval, code execution, calculator, filesystem tools, and MCP bridging.
11. `SKILL.md` must document providers, configs, HTTP transport/parser, model runners, model-provider enum, model-modality enum, and supported text/image/video provider capabilities as represented by the current code.
12. `SKILL.md` must document prompts, prompt JSON assets, the `Prompt` enum, `Prompts` accessor, direct import names, strategy prompt bundle classes, and the prompt addition workflow.
13. `SKILL.md` must document context/dataclass models, including budget and permission presets, context rendering, multi-agent dataclasses, filesystem config, security, sandbox, MCP, and runner response types.
14. `SKILL.md` must document existing design docs with short descriptions and note supersession relationships where the docs already state them.
15. `SKILL.md` must document test coverage areas and standard commands to run after changes.
16. `SKILL.md` must include contribution guardrails: keep dataclasses centralized, preserve public compatibility shims, avoid private service logic, avoid global mutable tool state, require explicit permission policies for mutating/executable tools, and prefer code over stale docs when there is a conflict.
17. `SKILL.md` must not claim unimplemented code exists. Pending or untracked design docs must be labeled as design-only unless implementation is present.

### Non-Functional Requirements

- Performance targets: N/A - markdown-only documentation has no runtime performance impact.
- Scalability considerations: the skill should be organized into scannable sections so it remains maintainable as the SDK grows.
- Security requirements: the skill must not include secrets, credentials, private customer data, or instructions to bypass permission checks.
- Observability: N/A - no runtime logging, metrics, or tracing changes.
- Reliability / error tolerance: the skill must distinguish source-code facts from design intent and avoid stale claims where local code disagrees with historical design docs.

---

## 5. High-Level Design

The change will add a single new local skill package under `skills/vidbyte-sdk-doc/`. The new `SKILL.md` will use the Codex skill format already present in the broader workspace and in `skills/vidbyte-sdk/SKILL.md`: YAML frontmatter followed by Markdown instructions.

The skill will be a human-authored repository reference, not generated code. It will organize the SDK into major subsystems and provide future agents with the specific files, contracts, and verification commands that matter when changing each subsystem.

Source authority will be explicit: current source code and tests are authoritative for implemented behavior; design docs provide context and intent, but any unimplemented or superseded design content must be labeled. This matters because the workspace contains design docs for future/pending work such as pipelines and minimal runtime, and the existing docs include supersession notes around the public tool API.

```text
[docs/design/*]      [README.md]      [vidbyte/*]      [tests/*]
        \                |              |              /
         \               |              |             /
          +--------> skills/vidbyte-sdk-doc/SKILL.md
                         |
                 Future Codex agents use it
                 before SDK edits/reviews
```

---

## 6. Detailed Design

### 6.1 Design Doc

**File(s):** `docs/design/vidbyte-sdk-doc.md`
**Type:** New file

#### What it does

Records the approved scope, source audit, file manifest, testing approach, and rollout plan for adding the `vidbyte-sdk-doc` skill.

#### Interface / API

```markdown
# Design Doc: Vidbyte SDK Doc Skill
```

#### Logic / Algorithm

1. Capture the local repository audit.
2. Define the `vidbyte-sdk-doc` skill structure and expected content.
3. List all files expected to be created.
4. Define verification for a documentation-only change.

#### Edge Cases & Error Handling

- If the implementation later discovers that `skills/vidbyte-sdk-doc/` already exists in the approved worktree, update the existing skill only after confirming it is the same intended artifact.
- If `main` cannot be updated or the worktree cannot be created because of local changes, stop before implementation.

---

### 6.2 Vidbyte SDK Doc Skill

**File(s):** `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** New file

#### What it does

Provides the main in-repository Codex skill reference for the SDK. The skill will tell future agents what the SDK contains, how the major pieces fit together, what files own each subsystem, what compatibility surfaces must be preserved, and how to verify changes.

#### Interface / API

```markdown
---
name: vidbyte-sdk-doc
description: Comprehensive reference for the Vidbyte SDK repository, including public APIs, package layout, design docs, subsystem responsibilities, and verification commands.
---

# Vidbyte SDK Doc
```

The body will include these sections:

```text
1. When To Use This Skill
2. Source Of Truth And Staleness Rules
3. Repository Snapshot
4. Package Map
5. Public Import Surface
6. Root SDK Client
7. Agents And Modality Routing
8. Strategies
9. Multi-Agent Orchestration
10. Tools
11. Filesystem Tools
12. MCP Integration
13. Providers, Configs, Runners, And HTTP
14. Prompts
15. Context And Dataclasses
16. Enums And Errors
17. Harnesses And Shared Namespace
18. Design Doc Index
19. Test Suite Map
20. Development Guardrails
21. Verification Commands
22. Common Change Playbooks
```

#### Logic / Algorithm

1. Start with frontmatter and a concise skill trigger statement.
2. Add source-of-truth rules: inspect code first, then README, then design docs; treat tests as behavioral examples; label unimplemented design-only content.
3. Add repository snapshot: Python `>=3.11`, `setuptools`, `pydantic`, `unittest`, root package `vidbyte`, no private service logic.
4. Add subsystem sections grounded in the audited code:
   - Root client: `VidbyteSDK` creates `agents`, `harnesses`, `tools`, `providers`, and `strategies` namespace clients.
   - Agents: `BaseAgent`, typed inputs, modality detection, runner resolution, direct runner calls, strategy delegation, agent-local tools, permission policy, tool-call loop, and MCP attachment.
   - Strategies: `BaseStrategy`, `StrategyResult`, sync/async contract, reasoning/sampling/agent-loop/routing strategies, and direct import paths.
   - Multi-agent: `BaseMultiAgentStrategy`, consensus, AutoGen-style conversation, VMAO, economic gate, evolving orchestration, DAG and evaluation dataclasses.
   - Tools: `Tools` catalog as preferred public mental model, decorator-first custom tools, registry/executor compatibility layer, formatter helpers, built-ins, permissions, sandbox protocols.
   - Filesystem: safe local backend/config/permission abstractions and public filesystem tool classes.
   - Providers/runners: model config dataclasses, provider factories, HTTP transport/parser, text/image/video runner behavior, supported providers by modality.
   - Prompts: JSON asset shape, `Prompt` enum, `Prompts` accessor, direct imports, prompt family helpers, `adding-prompts.md` workflow.
   - Context/dataclasses/enums/errors: centralized `vidbyte.lib.dataclasses`, compatibility re-export modules, budget/permission presets, public error families.
5. Add design doc index covering:
   - `advanced-tool-ecosystem.md`
   - `agent-abstractions.md`
   - `agent-modality-routing.md`
   - `agent-tool-api-consolidation.md`
   - `custom-function-tools.md`
   - `mcp-server-attachment.md`
   - `minimal-agent-runtime.md` as currently local/untracked design context
   - `multi-agent-orchestration-strategies.md`
   - `pipelines.md` as currently local/untracked design context
   - `prompt-api-strategies-sdk.md`
   - `prompt-description-enhancement.md`
   - `prompt-interface-simplification.md`
   - `sdk-consolidated.md`
6. Add test suite map matching existing `tests/test_*.py` coverage areas.
7. Add verification commands from README.
8. Add common playbooks for adding tools, prompts, providers, strategies, agents, and context dataclasses.

#### Edge Cases & Error Handling

- If docs mention a feature not present in `vidbyte/`, the skill will mark it as design-only.
- If a historical design doc conflicts with current code, the skill will tell agents to trust current code/tests and use the doc only for background.
- If a future implementation adds more files before this PR is created, the skill should be updated from the final worktree state before commit.

---

## 7. Data Model Changes

N/A - this change creates Markdown documentation only and does not modify schemas, dataclasses, enums, or persisted data.

---

## 8. API Changes

N/A - this change does not add, modify, deprecate, or delete any Python SDK API.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/vidbyte-sdk-doc.md` | Design doc for the new SDK documentation skill |
| CREATE | `skills/vidbyte-sdk-doc/SKILL.md` | Main comprehensive SDK skill reference |

---

## 10. Testing Plan

### Unit Tests

N/A - the implementation is documentation-only and introduces no executable Python code.

### Integration Tests

- Run `python -m compileall vidbyte` to confirm no accidental Python changes broke importability.
- Run `python -m unittest discover -s tests` to confirm no runtime regressions if the branch includes only documentation changes.

### Manual / QA Test Cases

1. Open `skills/vidbyte-sdk-doc/SKILL.md` and confirm the frontmatter contains `name: vidbyte-sdk-doc` and a meaningful `description`.
2. Confirm the skill includes all major SDK subsystems listed in Functional Requirements.
3. Confirm the design doc index includes all design docs currently visible under `docs/design/`.
4. Confirm pending or untracked design docs are not described as implemented runtime behavior.
5. Confirm `git diff --stat` shows only the approved docs/skill files.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | No new dependencies or external services | N/A |

---

## 12. Rollout & Deployment

- No feature flags are required.
- This is not a breaking change.
- The rollout is a documentation PR targeting `main`.
- Rollback is deleting `skills/vidbyte-sdk-doc/SKILL.md` and this design doc from the branch.
- The PR should be opened as draft after implementation, per the `design-doc` skill workflow.

---

## 13. Open Questions

- [ ] Should `vidbyte-sdk-doc` replace or coexist with the shorter `skills/vidbyte-sdk` skill? The proposed implementation keeps both, with `vidbyte-sdk` as the concise structure guide and `vidbyte-sdk-doc` as the comprehensive reference.
- [ ] Should the skill include exact public `__all__` export lists, or keep export lists summarized by subsystem to reduce maintenance burden? The proposed implementation uses subsystem summaries plus important class/function names.
- [ ] Should locally untracked design docs (`minimal-agent-runtime.md`, `pipelines.md`) be included in the skill's design-doc index if they are still untracked when the implementation worktree is created? The proposed implementation includes them only if present in the worktree and labels them as design context rather than implemented behavior.

---

## 14. Alternatives Considered

### Alternative 1: Expand `skills/vidbyte-sdk/SKILL.md`

- What: Replace the existing concise SDK structure skill with the exhaustive repository reference.
- Why rejected: The current skill is useful as a compact rules file. Expanding it heavily would make quick package-structure guidance harder to scan and could create unnecessary churn in an existing artifact.

### Alternative 2: Put the reference under `docs/` instead of `skills/`

- What: Create `docs/vidbyte-sdk-doc.md` or similar.
- Why rejected: The user specifically requested a skill file named `vidbyte-sdk-doc`, and a Codex skill under `skills/` is directly reusable by future agents.

### Alternative 3: Generate API docs from source

- What: Use an automated documentation generator or introspection script to emit an API reference.
- Why rejected: The repo has no documentation generation tooling today, and the requested artifact is a skill with development guidance, design-doc interpretation, and repository conventions, not a raw API dump.

### Alternative 4: Include every source file verbatim or near-verbatim

- What: Copy every module's code or docstrings into the skill.
- Why rejected: That would be noisy, hard to maintain, and likely stale quickly. The skill should be comprehensive in coverage but concise enough to guide future work.
