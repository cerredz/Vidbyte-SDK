# Design Doc: Codex Harness Roadmap Skill

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

Add a repository skill that helps developers plan future CodexHarnessAgent translations and native features. It compares the unmerged PR #409 implementation with the installed Python SDK and current official Codex documentation, then provides a decomposed checklist, Vidbyte mapping guidance, dependencies, completion criteria, and a source index. This change writes documentation only.

---

## 2. Goals & Non-Goals

### Goals

- Provide a discoverable `skills/codex-harness-roadmap/SKILL.md`.
- Expand the previous high-level suggestions into separately actionable work.
- Distinguish native Python methods, app-server operations, experimental features, config controls, Vidbyte orchestration, and unavailable semantics.
- Preserve a dated, commit-specific implementation baseline and cite official documentation.
- Return the expanded checklist to the user.

### Non-Goals

- Implement any roadmap feature, modify provider code, install hooks, or run a paid model.
- Merge or close PR #409, change the CLI repository, or promise cross-provider parity.
- Treat desktop UI features or deprecated APIs as stable Python SDK methods.

---

## 3. Background & Context

Canonical repository: Vidbyte-SDK, Python >=3.11, setuptools, Pydantic, httpx, PyYAML. `skills/` contains repository guidance; it is separate from importable `vidbyte/skills/`. Main is clean at audit time and does not contain the Codex adapter. PR #409 is open at commit `c3842585822bb2eb950bc3a419ae1ae52ecaa21d`; its settings/translators, context rendering, five native inputs, sync/async calls, forks, typed results, and failures are the comparison baseline.

The installed `openai-codex` version is 0.147.0. Its public facade covers fewer operations than app-server. The PR does not support durable Vidbyte Session persistence and opens a provider connection for each transport operation. The field guide calls for explicit semantic translation boundaries and complete worktree CI. Existing design documents remain opaque per AGENTS.md; only this newly requested design is authored.

---

## 4. Requirements

### Functional Requirements

1. Create a skill with valid name/description frontmatter and focused invocation instructions.
2. Keep the entrypoint short; route detailed checklist, translation map, and sources into three references.
3. Separate already implemented PR behavior from pending work; use stable IDs and unchecked future items.
4. Cover lifecycle, concurrency, streaming, inputs/results, threads/forks, context, tools/MCP, approvals, configuration, hooks/skills/plugins, subagents, authentication, observability/budgets, failures, middleware, composition/evals, and advanced protocol features.
5. Identify the supporting provider surface and meaningful limits; flag experimental/deprecated operations.
6. Map actual Vidbyte abstractions to proposed collaborators and completion evidence; proposed names are explicitly not existing APIs.
7. Include at least 20 reviewed official documentation pages with descriptions, a verification date, and source refresh instructions.
8. Explain hard control limits: native loop ownership, permission precedence, thread versus filesystem state, incomplete portability, and observed versus enforceable behavior.
9. Provide an implementation order based on dependencies; no automatic authorization to implement the roadmap.

### Non-Functional Requirements

- Performance/scalability: N/A - static Markdown, with progressive loading to reduce agent context use.
- Security: no credentials or machine-specific paths; no new hook execution, permission changes, or implied authority.
- Observability: source IDs, snapshot commit, and per-domain completion checks make claims auditable.
- Reliability: separate dated evidence from future decisions; missing SDK methods remain version-gated.

---

## 5. High-Level Design

The skill entrypoint guides baseline inspection, topic selection, evidence refresh, and a scoped implementation proposal. A single checklist is the source of truth for task IDs. The translation map refers to those IDs rather than duplicating checkbox state. The source index supplies direct official links and notes which layer each describes.

The new skill is independent of PR #409 and targets main. Commit-pinned GitHub links identify absent adapter source without broken relative filesystem links. Existing Vidbyte source paths are repository-relative text. It adds no runtime dependencies and does not change the existing runtime-primitives skill in the unmerged PR.

---

## 6. Detailed Design

### 6.1 Skill entrypoint

**File(s):** `skills/codex-harness-roadmap/SKILL.md`
**Type:** New file

#### What it does

Routes roadmap planning and feature selection to the relevant reference, states baseline/version handling, and preserves the user's requested scope.

#### Interface / API

YAML frontmatter: `name: codex-harness-roadmap`; description selects CodexHarnessAgent roadmap, gaps, and translation planning.

#### Logic / Algorithm

1. Determine checkout/adapter version.
2. Load the checklist and only the mapping/source sections needed.
3. Classify native, configured, emulated, gated, or unavailable behavior.
4. Return selected tasks, dependencies, implementation seams, and completion evidence.

#### Edge Cases & Error Handling

If the adapter is absent, use the pinned PR baseline and label it unmerged. If documentation and SDK signatures differ, do not invent a wrapper method.

### 6.2 Future work checklist

**File(s):** `skills/codex-harness-roadmap/references/checklist.md`
**Type:** New file

#### What it does

Contains a dated baseline, surface legend, granular future tasks grouped by domain, per-domain completion criteria, and recommended delivery waves.

#### Interface / API

Each entry is `- [ ] ID [surface] Action and scope.` IDs remain stable when status changes.

#### Logic / Algorithm

Separate provider facts from proposed adapter behavior. Cite each domain's evidence. Retain uncertainty and deprecated paths explicitly.

#### Edge Cases & Error Handling

A feature already exposed by raw config is a typed-control improvement, not a newly discovered provider capability. A native fork does not isolate disk edits.

### 6.3 Translation map

**File(s):** `skills/codex-harness-roadmap/references/translation-map.md`
**Type:** New file

#### What it does

Maps existing Vidbyte types to proposed Codex seams, semantic fidelity, and required evidence. Describes differences between callbacks that can enforce a decision and events that can only observe it.

#### Interface / API

Table: abstraction/location, task IDs, proposed mapping, caveat/completion proof.

#### Logic / Algorithm

Inspect actual abstractions; name prospective collaborators as proposals. Identify cross-cutting dependencies rather than declaring automatic BaseAgent/Session compatibility.

#### Edge Cases & Error Handling

Reject unsupported internal-loop semantics. Distinguish context history rollback from file rollback, provider token totals from billed dollars, and role declarations from deterministic scheduling.

### 6.4 Evidence index

**File(s):** `skills/codex-harness-roadmap/references/sources.md`
**Type:** New file

#### What it does

Indexes reviewed official documentation and pinned implementation evidence, with focused descriptions and topic routing.

#### Interface / API

Stable source IDs and direct hyperlinks; verification date and SDK version.

#### Logic / Algorithm

Check each page's actual content. For API work inspect installed signatures/generated schema as well as documentation. Update dates and affected tasks together.

#### Edge Cases & Error Handling

Redirects to ChatGPT Learn are expected. Desktop-only and deprecated documentation is labeled; it cannot establish a stable Python API.

---

## 7. Data Model Changes

N/A - no Python dataclasses, persisted records, or database migrations. Roadmap IDs are documentation identifiers only.

---

## 8. API Changes

N/A - no runtime API or endpoint changes. Proposed collaborator names are explicitly future design suggestions.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-harness-roadmap-skill.md` | Design and verification contract |
| CREATE | `skills/codex-harness-roadmap/SKILL.md` | Discoverable planning skill |
| CREATE | `skills/codex-harness-roadmap/references/checklist.md` | Authoritative granular future-work checklist |
| CREATE | `skills/codex-harness-roadmap/references/translation-map.md` | Actual Vidbyte abstractions and proposed translation seams |
| CREATE | `skills/codex-harness-roadmap/references/sources.md` | Reviewed official sources and pinned implementation baseline |

Totals: 5 create, 0 modify, 0 delete.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing Python dev tools | Pinned in pyproject.toml | Canonical local CI | Pre-existing environment/tool drift |
| Codex Python SDK | Installed 0.147.0; inspected read-only | Method/shape verification | Docs may describe newer protocol |
| Official OpenAI documentation | developers.openai.com / learn.chatgpt.com | Provider evidence | Links, maturity, and behavior change |
| GitHub | cerredz/Vidbyte-SDK PR #409 | Unmerged baseline and draft PR | Availability/permissions |

No dependency additions.

---

## 11. Rollout & Deployment

Commit the design first in an isolated `feat/codex-harness-roadmap-skill` worktree. Author and validate the skill and local links, then reconcile the request, design, and each file. Run `python -m pip install -e ".[dev]"` and complete `python scripts/run_ci.py`; no new tests are needed. Validate the skill using the skill-creator quick validator.

Push and open a draft PR targeting main. Wait for Python 3.11/3.12 source, static policy, and package checks. Remove the clean, fully pushed worktree after all checks pass, retaining branch and PR. No deployment, flags, or user migration. Rollback is a revert of these documentation commits.

---

## 12. Open Questions

- None block the documentation change. Implementers must decide which advanced capabilities justify low-level app-server integration rather than waiting for public SDK wrappers.
- The PR #409 baseline may change or merge; refresh status and commit links before using this roadmap for implementation.
- Platform/account availability of remote, realtime, and desktop features requires separate verification; roadmap entries must not imply universal support.

---

## 13. Alternatives Considered

### Alternative 1: Expand only the existing runtime-primitives skill

- What: Add every Codex detail to the provider-neutral guidance in PR #409.
- Why rejected: The user asked for a dedicated future-work skill; the existing skill is unmerged and has a broader purpose.

### Alternative 2: One very large SKILL.md

- What: Load all source descriptions and translations on every invocation.
- Why rejected: Three focused references keep discovery cheap and allow topic-specific reading.

### Alternative 3: Implement future features now

- What: Add streaming, tools, and sessions together with the checklist.
- Why rejected: The authorized change is a roadmap skill; runtime implementation needs its own scoped design.

