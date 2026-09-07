# Design Doc: Claude Agent SDK Translation Skill

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-09-05  
**Last Updated:** 2026-09-05

---

## 1. Overview

Create a repository-level Vidbyte skill that serves as the complete planning and
translation inventory for adding the open-source Claude Agent SDK to `vidbyte-sdk`.
The skill records every current Claude Agent SDK capability, maps it to existing
Vidbyte contracts, identifies whether the mapping is native, translated, supervised,
observe-only, emulated, or unsupported, and establishes the provider-owned-loop
boundary. This change creates documentation only; it does not add a Claude adapter,
dependency, runtime behavior, or tests.

---

## 2. Goals & Non-Goals

### Goals

- Add a discoverable `claude-agent-sdk-translation` skill under the repository-level
  `vidbyte-sdk/skills/` surface.
- Capture the current Python Claude Agent SDK API surface: execution modes, options,
  tools, MCP, permissions, hooks, sessions, streaming, structured output, subagents,
  skills, plugins, file checkpointing, usage, tracing, and deployment constraints.
- Map each feature to concrete Vidbyte seams and clearly mark unsupported or
  provider-owned semantics.
- Preserve the distinction between a provider-backed agent façade and the outer
  Vidbyte Harness execution envelope.
- Create this architecture-first design record with a complete file manifest and
  explicit risks, rollout, rollback, and open questions.

### Non-Goals

- Do not implement Claude runtime integration, a `ClaudeAgent`, a runner, a harness,
  a dependency, or a new public Python API.
- Do not alter the importable `vidbyte/skills/` runtime package.
- Do not install or pin `claude-agent-sdk` in `pyproject.toml` yet.
- Do not add feature tests, integration tests, fixtures, CI changes, or a PR.
- Do not promise parity with every Claude Code CLI behavior that the Agent SDK does
  not expose through its public Python API.

---

## 3. Background & Context

- The earlier “codex translation” work established a general provider translation
  model: a Vidbyte-shaped façade, capability negotiation, typed dispositions, and a
  strict distinction between native, translated, supervised, observe-only, and
  unsupported behavior.
- The Claude Agent SDK now exposes the Claude Code agent loop, built-in tools,
  sessions, hooks, subagents, MCP, permissions, skills, plugins, streaming, and
  structured output through Python and TypeScript. It is a provider-owned loop, so
  it cannot inherit Vidbyte's exact iteration middleware, custom compaction, MCTS, or
  actor-model semantics merely by serializing constructor fields.
- `vidbyte-sdk` already has provider-neutral agents, loop/tool settings, middleware,
  context managers, checkpoint-DAG sessions, Harness capture, MCP bridges, security
  policies, usage, speed, and trace contracts. The requested artifact should align
  future implementation with those existing boundaries rather than create a second
  architecture.
- The repository is Python 3.11+, alpha-status, and uses `pyproject.toml` with
  optional development dependencies. Contributor guidance belongs in `skills/`;
  package-internal distributable skill machinery lives under `vidbyte/skills/`.

---

## 4. Requirements

### Functional Requirements

1. The new skill must have valid lowercase hyphenated skill metadata and a
   discriminating description.
2. The skill must state its scope, naming/branding constraints, authentication and
   commercial-term boundaries, and the no-implementation behavior for inventory-only
   requests.
3. The skill must list current Vidbyte architecture anchors and explain the required
   translation separation between shared abstractions and provider serialization.
4. The skill must define the six capability dispositions used by the inventory.
5. The feature matrix must cover provider lifecycle; prompt/model/budget/environment;
   tools/MCP/permissions; hooks; messages/streaming/output/errors; sessions and
   file state; subagents; context/usage/observability; and security/deployment.
6. Each matrix row must identify the Claude feature, disposition, Vidbyte target
   seam, and a concrete translation caveat or guarantee.
7. The skill must provide a future implementation order and non-negotiable rules that
   prevent silent loss of unsupported settings or accidental reimplementation of the
   provider loop.
8. The design document must use every section of the supplied design-doc template,
   describe this documentation-only scope, and enumerate every created file.

### Non-Functional Requirements

- Documentation must be scannable by future coding agents and progressively disclose
  the detailed matrix through a linked reference.
- No new runtime dependency, import path, generated artifact, network service, or
  persistent data is introduced.
- Security guidance must preserve API-key injection, redaction, consent, sandbox,
  path, plugin, and settings-source boundaries.
- Official Claude documentation links and the SDK snapshot date must be visible so a
  future implementation can re-check provider drift.
- The artifact must be valid under the repository's skill naming and frontmatter
  conventions and must not contain unfinished scaffold placeholders.

---

## 5. High-Level Design

Create one contributor-facing skill folder with a concise `SKILL.md` entrypoint and a
linked `references/feature-matrix.md` containing the exhaustive mapping. The
entrypoint handles routing, architectural boundaries, disposition definitions,
Vidbyte anchors, future implementation order, and verification expectations. The
reference holds the feature-by-feature inventory so ordinary uses do not need to
load all provider details.

The skill models a future adapter as a Vidbyte `BaseAgent`-compatible façade over
Claude's `query()` or `ClaudeSDKClient`, with typed translators and a capability
report between the two. A separate outer `Harness` may capture the run, but it does
not own Claude's internal loop, compaction, subagent scheduling, or transcript
protocol. This is documentation only; no such adapter is created by this change.

```text
[Future Vidbyte agent façade]
          |
          v
[typed capability + settings translators]
          |
          v
[Claude Agent SDK: query / ClaudeSDKClient]
          |
          v
[provider-owned loop, tools, sessions, subagents, compaction]
          |
          v
[normalized Vidbyte messages, usage, trace, session, Harness capture]
```

---

## 6. Detailed Design

### 6.1 Skill Entrypoint

**File(s):** `skills/claude-agent-sdk-translation/SKILL.md`  
**Type:** New file

#### What it does

Routes future Claude Agent SDK planning and implementation work. It states scope,
branding/auth constraints, provider-loop boundaries, Vidbyte architecture anchors,
capability dispositions, implementation order, non-negotiable rules, and verification
expectations.

#### Interface / API

The skill is loaded by its metadata name:

```yaml
name: claude-agent-sdk-translation
description: Plan, audit, or implement Vidbyte support for the open-source Claude Agent SDK...
```

It links to `references/feature-matrix.md` for detailed conditional guidance.

#### Logic / Algorithm

1. Identify whether the request is planning/inventory or implementation.
2. Read the current official Claude docs/source and the relevant Vidbyte anchors.
3. Classify each requested feature with the disposition legend.
4. Preserve provider-owned behavior and reject unsupported guarantees explicitly.
5. Require a design/capability contract before future runtime implementation.

#### Edge Cases & Error Handling

- If a Claude field is version-specific, require a pinned SDK/runtime version and
  record the field as a provider-only extension.
- If a Python feature is only documented for TypeScript, mark it unsupported or an
  approximation rather than presenting it as a Python guarantee.
- If the user requests only the skill or inventory, stop without changing runtime
  files, dependencies, tests, or CI.

### 6.2 Feature Matrix Reference

**File(s):** `skills/claude-agent-sdk-translation/references/feature-matrix.md`  
**Type:** New file

#### What it does

Provides the exhaustive, implementation-oriented mapping from current Claude Agent
SDK capabilities to Vidbyte seams and caveats, grouped by lifecycle, settings,
tools, hooks, messages, sessions, subagents, observability, and security.

#### Interface / API

Markdown reference linked from the skill entrypoint. Each row has:

```text
Claude feature | disposition | Vidbyte translation target | required notes
```

#### Logic / Algorithm

1. Start with official Python/SDK documentation and typed source.
2. Identify the nearest existing Vidbyte contract.
3. Choose the strongest honest disposition.
4. Write the semantic difference, identity boundary, and failure/security caveat.
5. Keep provider-only escape-hatch fields out of shared contracts unless a later
   design proves cross-provider semantics.

#### Edge Cases & Error Handling

- Provider-owned features such as compaction, subagent scheduling, sandboxing, and
  hook execution remain supervised unless Vidbyte can prove stronger control.
- Unsupported runner fields must be rejected or capability-negotiated; no silent
  dropping is allowed.
- Session transcript IDs, Vidbyte checkpoint IDs, file checkpoint IDs, and Harness
  run IDs remain distinct even when a future adapter correlates them.

### 6.3 Design Record

**File(s):** `docs/design/claude-agent-sdk-translation-skill.md`  
**Type:** New file

#### What it does

Records why the repository-level skill exists, exactly what it contains, what it does
not implement, and the complete change manifest.

#### Interface / API

No runtime API or endpoint is added.

#### Logic / Algorithm

The document follows the repository's required thirteen-section design template and
uses `N/A - ...` where a runtime/API/data migration section does not apply.

#### Edge Cases & Error Handling

The document explicitly records that no implementation worktree, dependency change,
CI change, or test addition is authorized by this request. A future implementation
must create its own design/branch workflow.

---

## 7. Data Model Changes

N/A - This change adds Markdown guidance only. It introduces no database, schema,
checkpoint, trace, or serialized runtime type.

---

## 8. API Changes

N/A - No Python import, CLI command, HTTP endpoint, or provider API wrapper is added.
The skill's metadata is a repository documentation interface only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `skills/claude-agent-sdk-translation/SKILL.md` | Add the reusable Claude Agent SDK translation workflow and architecture boundary. |
| CREATE | `skills/claude-agent-sdk-translation/references/feature-matrix.md` | Add the exhaustive Claude capability inventory and Vidbyte mapping. |
| CREATE | `docs/design/claude-agent-sdk-translation-skill.md` | Record the architecture-first design and documentation-only scope. |

Modify: 0  
Delete: 0

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Claude Agent SDK documentation | Official docs linked in the skill; snapshot checked 2026-09-05 | Source of current capability names and semantics. | Provider docs/API drift; re-check before implementation. |
| Claude Agent SDK Python package | Not added in this change | Future optional provider integration. | Commercial terms, bundled runtime drift, process/security behavior, and optional dependency size. |
| Vidbyte SDK existing contracts | Current repository `vidbyte/` modules | Translation targets and architectural boundaries. | Alpha APIs may change; future adapter must pin against a Vidbyte release. |

No external service is called and no dependency is installed by this documentation-only change.

---

## 11. Rollout & Deployment

- No feature flag or deployment step is required because no runtime/package artifact
  changes.
- The skill becomes available to repository contributors once the two new files are
  present under `skills/`.
- A future runtime integration should be opt-in, optional-dependency gated, and
  released only after capability, security, session, and provider-version review.
- Rollback is deleting the new skill folder and design document; no persisted runtime
  state or installed dependency must be migrated.

---

## 12. Open Questions

- [ ] Should the future public façade be named `ClaudeAgent`, `ClaudeAgentAdapter`,
  or a generic delegated-agent type with a Claude provider implementation?
- [ ] Which minimum `claude-agent-sdk` version and bundled Claude runtime version will
  Vidbyte support, and how will that pin be surfaced to callers?
- [ ] Should Claude-native built-in tools remain provider-owned, or should Vidbyte
  provide a first-class normalized tool-event view for them?
- [ ] Which Claude session persistence mode is acceptable for hosted/multi-tenant
  Vidbyte deployments, and what encryption/locking contract is required?
- [ ] What is the supported OS matrix for Claude sandboxing and process execution,
  especially for Windows users?
- [ ] Which provider usage/cost fields are stable enough to enter shared pricing and
  speed contracts versus remaining Claude-only metadata?
- [ ] Should provider-owned Claude subagents be exposed as a separate capability or
  composed behind `MultiAgent` only at the outer Vidbyte layer?

---

## 13. Alternatives Considered

### Alternative 1: Implement the Claude adapter now

- What: Add a `ClaudeAgent`/runner, dependency, and tests in the same change.
- Why rejected: The user explicitly requested a skill and feature inventory only;
  implementation would expand scope and could encode unreviewed provider semantics.

### Alternative 2: Put the guidance under `vidbyte/skills/`

- What: Ship the feature map as an importable runtime skill asset.
- Why rejected: Repository instructions distinguish contributor skills under `skills/`
  from package-internal runtime skill machinery under `vidbyte/skills/`. This request
  is for implementation guidance, not a model-facing runtime asset.

### Alternative 3: Treat Claude as another ordinary `BaseAgent` runner

- What: Serialize all Vidbyte loop settings into a generic model runner and let the
  existing linear runtime own the tool loop.
- Why rejected: The Agent SDK already owns planning, tools, context, permissions,
  compaction, and subagents. That approach would either discard Claude capabilities or
  falsely claim control over behavior Vidbyte cannot interpose.

### Alternative 4: Copy the Claude documentation wholesale

- What: Mirror the upstream reference in the repository skill.
- Why rejected: The skill needs a decision-oriented translation matrix tied to Vidbyte
  contracts, not a duplicated provider manual that will drift and consume context.

