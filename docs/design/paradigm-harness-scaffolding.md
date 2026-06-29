# Design Doc: Paradigm Harness Scaffolding

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-29
**Last Updated:** 2026-06-29

---

## 1. Overview

This change introduces the first boilerplate paths for "paradigm harnesses" in the
Vidbyte SDK without implementing any concrete paradigm yet. A paradigm harness is
a thin, runnable harness pattern that composes lower-level SDK primitives such as
agents, tools, prompts, context managers, middleware, tracing, pipelines, and
evals into an opinionated execution loop. The user-facing intent is that future
callers can configure a paradigm harness with their own tools, system prompts,
models, and limits, then call `run()` or `arun()` much like an agent.

The implementation scope is deliberately small: add a `vidbyte.paradigms`
namespace, expose a namespace client from `VidbyteSDK().paradigms`, document the
package role in the README, and add a comprehensive maintainer skill at
`skills/paradigm/SKILL.md`. The skill file will define what paradigms mean in
this codebase, how they differ from primitives, pipelines, middleware, tools,
and external harness integrations, and how future contributors should decide
whether a new paradigm belongs in the SDK. No concrete paradigms, API routes, or
hosted-service behaviors are implemented in this PR.

---

## 2. Goals & Non-Goals

### Goals

- Add a top-level `vidbyte.paradigms` package as the future home for thin
  runnable paradigm harnesses.
- Add a minimal `ParadigmHarness` abstract base so future paradigm harnesses have
  a clear `run()` / `arun()` execution contract.
- Add a minimal `ParadigmClient` namespace client and expose it as
  `VidbyteSDK().paradigms`.
- Re-export the new public scaffolding from `vidbyte.paradigms` and root
  `vidbyte` when appropriate.
- Update README layer guidance and package structure so users and future agents
  know paradigms are a first-class layer.
- Add `skills/paradigm/SKILL.md` as a comprehensive skill guide explaining
  paradigms in relation to this codebase.
- Write the paradigm skill in the style of the existing agentic engineering
  skill files: identity, intent, structure, criteria, procedure, conventions,
  and rules.
- Explicitly state that paradigms are full thin harnesses built from SDK
  primitives, not low-level primitives themselves.
- Preserve the current `vidbyte.harnesses` boundary for external harness
  integrations.

### Non-Goals

- Do not implement any concrete paradigm harness such as critique-repair,
  minimal-context debugging, fresh-window decomposition, PRD-to-subagent, noisy
  prompt expansion, or dynamic reasoning effort.
- Do not add hosted API routes, service clients, database persistence, dashboards,
  proprietary scoring, or Vidbyte private service behavior.
- Do not add tests or verification scripts in this change; this is a scaffolding
  and documentation PR under the no-tests workflow.
- Do not move or repurpose `vidbyte.harnesses`; it remains the namespace for
  external harness integrations.
- Do not change agent runtime behavior, middleware behavior, prompt catalog
  loading, MCP server behavior, or existing public APIs beyond additive exports.
- Do not add prompt catalog assets for paradigms yet.

---

## 3. Background & Context

The current SDK presents reusable agent engineering layers: `agents`, `context`,
`middleware`, `tools`, `prompts`, `evals`, `pipelines`, `trace`, `providers`,
`mcp_server`, and `harnesses`. The root README describes `vidbyte.harnesses` as
a boundary for custom harness integrations, and the current `HarnessClient` is
intentionally minimal. That makes `vidbyte.harnesses` a poor fit for paradigm
implementations that are themselves reusable SDK-level runnable objects.

The user clarified that paradigms should be treated as high-level harness
patterns rather than low-level primitives. A paradigm like "run a worker, critique
the output against the original prompt, produce fixes, repeat until no defects
remain" should not force the developer to manually wire a worker agent, critic
agent, prompts, trace state, retry loop, stopping rules, and context policy. The
future abstraction should be a thin harness object with a familiar run surface.
The lower-level SDK primitives still matter, but they are internal building
blocks of the paradigm harness rather than the product abstraction.

The agentic engineering files already establish the desired documentation style.
`vidbyte/prompts/skills/agentic-engineering.md` uses explicit sections such as
`<identity>`, `<structure>`, `<criteria>`, `<procedure>`, `<conventions>`, and
`<rules>`. The underlying prompt files use dense `# Description`, `# Intent`,
criteria, checklists, and "Things Not to Do" sections. The new paradigm skill
should follow that diction and structure, but focus on SDK architecture and
future contributor guidance rather than source-code style principles.

The design-doc skill requested `references/design-doc-template.md`, but that
file does not exist in this checkout. Existing design docs under `docs/design/`
share a stable 14-section structure, so this document follows that local
structure and records the missing template as an open question.

---

## 4. Requirements

### Functional Requirements

1. Create `vidbyte/paradigms/` as an importable Python package.
2. Add `vidbyte/paradigms/base.py` containing a minimal abstract
   `ParadigmHarness` contract.
3. `ParadigmHarness` must define `async arun(prompt: str, **options: Any) -> Any`
   as the async execution method future paradigm harnesses implement.
4. `ParadigmHarness` must define `run(prompt: str, **options: Any) -> Any` as a
   sync bridge that mirrors existing `BasePipeline.run_sync()` style behavior.
5. Calling `run()` from an active event loop must raise `PipelineExecutionError`
   or an existing SDK error rather than nesting an event loop.
6. Add `vidbyte/paradigms/client.py` containing a minimal `ParadigmClient`
   namespace class.
7. Add `vidbyte/paradigms/README.md` explaining the role of the package, the
   difference between paradigm harnesses and primitives, and the non-goals.
8. Add `vidbyte/paradigms/__init__.py` re-exporting the public scaffolding.
9. Update `vidbyte/client.py` so `VidbyteSDK().__init__` creates
   `self.paradigms = ParadigmClient()`.
10. Update root `vidbyte/__init__.py` to expose `ParadigmClient` and
    `ParadigmHarness`.
11. Update the root README Layer Guide to include `vidbyte.paradigms`.
12. Update the root README package structure block to include `paradigms/`.
13. Add `skills/paradigm/SKILL.md`.
14. The paradigm skill must be comprehensive and in depth.
15. The paradigm skill must explicitly define paradigms as thin runnable harnesses
    built from SDK primitives, not as the primitives themselves.
16. The paradigm skill must explain how paradigms relate to `agents`, `context`,
    `middleware`, `tools`, `prompts`, `evals`, `pipelines`, `trace`,
    `harnesses`, and hosted API implementations.
17. The paradigm skill must include criteria for when a new idea qualifies as a
    paradigm harness.
18. The paradigm skill must include placement rules for SDK primitives,
    paradigm harnesses, skill adapters, hosted API routes, and external harness
    integrations.
19. The paradigm skill must include a procedure for adding future paradigm
    harnesses, but must not require this PR to add one.
20. The paradigm skill must include concrete non-goals and anti-patterns, such as
    "do not turn every helper into a paradigm" and "do not duplicate primitive
    logic inside a paradigm harness."

### Non-Functional Requirements

- Keep the implementation additive and backward compatible.
- Keep the scaffolding dependency-free.
- Keep public classes minimal so future concrete paradigms can evolve without
  being forced into premature API commitments.
- Keep examples documentation-only; do not add runnable examples for paradigms
  that do not exist yet.
- Preserve ASCII-only documentation content for new files.
- Avoid tests and verification scripts, per the selected no-tests workflow.
- Run lightweight verification after implementation: `python -m compileall
  vidbyte` and an import smoke command, but do not add test files.

---

## 5. High-Level Design

Add a new SDK layer:

```text
vidbyte.paradigms
  Thin runnable harness patterns that compose SDK primitives into opinionated
  execution loops. Future examples include critique-repair, minimal-context
  debugging, fresh-window decomposition, and PRD-to-subagent implementation.
```

This layer sits above lower-level building blocks:

```text
ParadigmHarness
  owns orchestration and run loop shape
  composes:
    Agent / BaseAgent
    ContextManager / context primitives
    Middleware
    Tools
    Prompt templates
    Trace artifacts
    Eval graders
    Pipeline stages when useful
```

It does not replace any existing layer. Instead, it gives a future stable home
for reusable, out-of-the-box harness patterns. `vidbyte.harnesses` remains for
adapting Vidbyte abstractions into external harnesses. `vidbyte.paradigms`
contains Vidbyte-owned harness patterns.

The first PR adds only the path and the contract:

```text
vidbyte/paradigms/
|-- __init__.py
|-- base.py
|-- client.py
`-- README.md

skills/paradigm/
`-- SKILL.md
```

No concrete paradigm modules are created yet. Future PRs can add subpackages such
as:

```text
vidbyte/paradigms/critique_repair/
vidbyte/paradigms/context_minimal/
vidbyte/paradigms/fresh_window/
```

---

## 6. Detailed Design

### 6.1 `vidbyte/paradigms/base.py`

**File:** `vidbyte/paradigms/base.py`
**Type:** New file

#### What it does

Defines the minimal abstract base for future paradigm harnesses.

#### Interface / API

```python
class ParadigmHarness(ABC):
    @abstractmethod
    async def arun(self, prompt: str, **options: Any) -> Any: ...
    def run(self, prompt: str, **options: Any) -> Any: ...
```

#### Logic / Algorithm

1. `arun(...)` is abstract and must be implemented by concrete paradigm
   harnesses.
2. `run(...)` calls `asyncio.get_running_loop()`.
3. If no loop is running, `run(...)` uses `asyncio.run(self.arun(prompt,
   **options))`.
4. If a loop is already running, `run(...)` raises `PipelineExecutionError` with
   a message instructing callers to use `await arun(...)`.

This mirrors the existing sync bridge pattern in `vidbyte/pipelines/base.py` and
avoids creating a new error type for scaffolding.

#### Edge Cases & Error Handling

- Active event loop: fail fast with an existing SDK error.
- Concrete class does not implement `arun`: standard ABC behavior prevents
  instantiation.
- Return type is `Any` for now because no concrete paradigm result contract has
  been designed yet.

---

### 6.2 `vidbyte/paradigms/client.py`

**File:** `vidbyte/paradigms/client.py`
**Type:** New file

#### What it does

Defines a namespace client for future paradigm factories.

#### Interface / API

```python
class ParadigmClient:
    """Namespace client for paradigm harness factories."""
```

#### Logic / Algorithm

No factory methods are added yet. The empty client establishes the namespace
without implying that any paradigm implementation exists.

#### Edge Cases & Error Handling

N/A - namespace marker only.

---

### 6.3 `vidbyte/paradigms/__init__.py`

**File:** `vidbyte/paradigms/__init__.py`
**Type:** New file

#### What it does

Re-exports `ParadigmHarness` and `ParadigmClient` from the package namespace.

#### Interface / API

```python
from vidbyte.paradigms import ParadigmClient, ParadigmHarness
```

#### Logic / Algorithm

Keep `__all__` explicit and sorted consistently with the repo style.

#### Edge Cases & Error Handling

N/A - export-only file.

---

### 6.4 `vidbyte/paradigms/README.md`

**File:** `vidbyte/paradigms/README.md`
**Type:** New file

#### What it does

Documents the new package in the same style as other package READMEs.

#### Required Sections

- `# Paradigms`
- `## Role In The SDK`
- `## Design Philosophy`
- `## Usage`
- `## Key Modules`
- `## Related Layers`
- `## Non-Goals`

#### Content Requirements

The README must state that paradigm harnesses are thin runnable patterns, not
raw primitives. It should also say that the package is currently scaffolding only
and contains no concrete paradigm harnesses yet.

---

### 6.5 `vidbyte/client.py`

**File:** `vidbyte/client.py`
**Type:** Modified

#### What it does

Adds the paradigm namespace client to the root SDK object.

#### Interface / API

```python
sdk = VidbyteSDK()
sdk.paradigms
```

#### Logic / Algorithm

1. Import `ParadigmClient`.
2. Add `self.paradigms = ParadigmClient()` in `VidbyteSDK.__init__`.
3. Update the context protocol header relations/architecture text to mention
   paradigms.

#### Edge Cases & Error Handling

N/A - additive root namespace field.

---

### 6.6 Root `vidbyte/__init__.py`

**File:** `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds root convenience exports for the new paradigm scaffolding.

#### Interface / API

```python
from vidbyte import ParadigmClient, ParadigmHarness
```

#### Logic / Algorithm

1. Import `ParadigmClient` and `ParadigmHarness` from `vidbyte.paradigms`.
2. Add both names to `__all__`.
3. Update the context protocol header description if needed.

#### Edge Cases & Error Handling

N/A - additive import/export only.

---

### 6.7 Root README

**File:** `README.md`
**Type:** Modified

#### What it does

Adds `vidbyte.paradigms` to public SDK docs without documenting concrete
paradigms that do not exist.

#### Changes

1. Add a Layer Guide row:
   `vidbyte.paradigms` - thin runnable paradigm harness scaffolding built from
   agents, tools, context, prompts, middleware, trace, and evals.
2. Add `sdk.paradigms` to the basic usage snippet.
3. Add `paradigms/` to the package structure block.
4. Keep examples conceptual and explicitly state that no concrete paradigm
   harnesses ship in this scaffolding PR.

---

### 6.8 `skills/paradigm/SKILL.md`

**File:** `skills/paradigm/SKILL.md`
**Type:** New file

#### What it does

Provides the comprehensive maintainer skill for future paradigm work.

#### Required Structure

The skill will follow the agentic-engineering skill style:

```markdown
---
name: paradigm
description: ...
---

# Paradigm Harnesses

<identity>
...
</identity>

<intent>
...
</intent>

<structure>
...
</structure>

<criteria>
...
</criteria>

<placement>
...
</placement>

<procedure>
...
</procedure>

<conventions>
...
</conventions>

<rules>
...
</rules>
```

#### Content Requirements

The skill must explain:

- A paradigm is a high-level harness strategy with its own control flow.
- A paradigm harness is the runnable SDK implementation of that strategy.
- SDK primitives are lower-level building blocks that paradigm harnesses compose.
- Skills are adapters and guidance layers, not the canonical implementation.
- Hosted API routes, when they exist, are managed product implementations of the
  same paradigm contract, not replacements for SDK primitives.
- `vidbyte.harnesses` remains for external harness integration; `vidbyte.paradigms`
  is for Vidbyte-owned thin harness patterns.
- A candidate paradigm must have a repeatable workflow, clear orchestration
  ownership, meaningful user-facing configuration, measurable outcomes, and
  enough depth to justify a dedicated runnable harness.
- Not every prompt trick, tool, middleware policy, or helper function qualifies
  as a paradigm.
- Future paradigm additions should start with a design doc, identify primitive
  gaps, add stable primitives first, then add a thin harness.

---

## 7. Data Model Changes

No persisted data model, database schema, or external API schema changes.

The only new in-process contract is `ParadigmHarness`, an abstract Python class
with `arun(...)` and `run(...)`. It intentionally does not define a result
dataclass yet because no concrete paradigm output schema has been designed.

---

## 8. API Changes

### New Python Imports

```python
from vidbyte.paradigms import ParadigmClient, ParadigmHarness
from vidbyte import ParadigmClient, ParadigmHarness
```

### New Root Client Namespace

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.paradigms
```

### Behavior

No concrete paradigm factories are added. `ParadigmClient` is a namespace marker.
Concrete paradigms will be added in future design-reviewed PRs.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/paradigm-harness-scaffolding.md` | Design doc for this change |
| CREATE | `vidbyte/paradigms/__init__.py` | Public package exports for paradigm scaffolding |
| CREATE | `vidbyte/paradigms/base.py` | Minimal abstract base for future thin paradigm harnesses |
| CREATE | `vidbyte/paradigms/client.py` | Namespace client for future paradigm factories |
| CREATE | `vidbyte/paradigms/README.md` | Package-level documentation for paradigms |
| CREATE | `skills/paradigm/SKILL.md` | Comprehensive skill guide for paradigm harness work |
| MODIFY | `vidbyte/client.py` | Add `VidbyteSDK().paradigms` namespace client |
| MODIFY | `vidbyte/__init__.py` | Root re-export of paradigm scaffolding |
| MODIFY | `README.md` | Add paradigms to layer guide, usage snippet, and package map |

Summary: **6 files created**, **3 files modified**, **0 files deleted**.

---

## 10. Testing Plan

N/A - no test files or verification scripts will be added under the selected
`design-doc-no-tests` workflow.

Implementation verification will be limited to:

```powershell
python -m compileall vidbyte
python -c "from vidbyte import ParadigmClient, ParadigmHarness, VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.paradigms).__name__, ParadigmHarness.__name__)"
```

These commands verify syntax and import/export wiring without adding tests.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `abc`, `asyncio`, `typing` | Python >=3.11 | Abstract harness contract and sync run bridge | Low |
| Existing `vidbyte.lib.errors.PipelineExecutionError` | In-repo | Reuse existing active-event-loop error pattern | Low |

No new third-party dependencies, network calls, external services, environment
variables, or package-data entries are required.

---

## 12. Rollout & Deployment

- This is additive SDK scaffolding.
- No feature flag is required.
- No migration is required.
- The package remains alpha, and public APIs may change before concrete
  paradigms ship.
- Rollout sequence after approval:
  1. Create an isolated worktree from `main`.
  2. Commit this design doc first.
  3. Add `vidbyte.paradigms` package files.
  4. Wire root client and root exports.
  5. Add README documentation.
  6. Add `skills/paradigm/SKILL.md`.
  7. Run compile/import verification.
  8. Open a draft PR.

Rollback:

- Revert the feature PR. Since no persisted data, migrations, or service
  integrations exist, rollback is a normal code revert.

---

## 13. Open Questions

- [ ] The requested `references/design-doc-template.md` file does not exist in
  this checkout. This doc follows the existing `docs/design/*.md` structure
  instead. Should the missing template be restored in a separate docs hygiene PR?
- [ ] Should `ParadigmHarness.run(...)` raise `PipelineExecutionError` for active
  event loops, matching `BasePipeline`, or should future work add a dedicated
  `ParadigmExecutionError`?
- [ ] Should `ParadigmClient` remain completely empty in this scaffolding PR, or
  should it expose a discovery method such as `available()` returning an empty
  tuple? Recommended: keep it empty until concrete paradigms exist.
- [ ] Should future concrete paradigm harnesses return plain `AgentMessage`,
  strings, or dedicated result dataclasses? This PR intentionally leaves the
  result shape undefined.
- [ ] Should the new skill live at `skills/paradigm/SKILL.md` exactly as requested
  or should it be pluralized to `skills/paradigms/SKILL.md` for consistency with
  package naming? Recommended: use the requested singular path now.

---

## 14. Alternatives Considered

### Alternative 1: Put paradigm harnesses under `vidbyte.harnesses`

- What: Extend the existing harness namespace with future paradigm harnesses.
- Why rejected: The current `harnesses` README defines that namespace as the
  boundary for adapting SDK abstractions into external execution harnesses.
  Paradigm harnesses are Vidbyte-owned runnable patterns, not adapters to
  external hosts. Reusing `harnesses` would blur a useful boundary.

### Alternative 2: Add only `skills/paradigm/SKILL.md`

- What: Create the skill guide but no Python package scaffolding.
- Why rejected: The user asked for boilerplate folder/code paths in the SDK repo.
  A skill-only change would document the concept but leave no canonical import
  path for future paradigm harnesses.

### Alternative 3: Add concrete first paradigm now

- What: Implement a first `CritiqueRepairHarness` or minimal-context debugging
  harness in the same PR.
- Why rejected: The user explicitly asked not to implement paradigms yet. Adding
  one would force unresolved decisions about result schemas, stopping criteria,
  tracing, evals, and hosted API boundaries into a scaffolding PR.

### Alternative 4: Add `vidbyte.paradigms` package with no base class

- What: Create only `__init__.py`, `client.py`, and README.
- Why rejected: The user described future paradigms as thin harnesses that expose
  `run()` like an agent. A minimal abstract base captures that intent without
  implementing a concrete paradigm or overcommitting to result types.

---

END OF DESIGN DOC
