# Design Doc: Agentic Engineering Prompt Family

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-27
**Last Updated:** 2026-06-27

---

## 1. Overview

Add a new `agentic_engineering` prompt family to the Vidbyte SDK containing three prompt assets: a main system prompt that introduces the discipline of agentic engineering (writing source code optimized for AI agent consumption), and two principle-level deep-dives covering server-side error messages as context-window primitives and file header comments as navigational landmarks. The main prompt explains the paradigm, establishes the two-audience design constraint (humans AND agents), and links to each principle. Each principle prompt provides structured, example-rich guidance on how to implement that practice in code. Together, these prompts form a complete instructional package that teaches a model how to write code an agent can efficiently navigate, debug, and extend.

---

## 2. Goals & Non-Goals

### Goals

- Add a new `agentic_engineering.json` descriptor under `vidbyte/prompts/prompts/agentic_engineering/` with three leaf prompts: `system_prompt`, `error_messages`, `file_headers`
- Create three `.md` prompt files under the same directory, referenced by the descriptor
- Add three corresponding enum members in `vidbyte/lib/enums/prompts.py`
- Auto-export three direct import names from `vidbyte.prompts` via the existing dynamic globals loop
- Add the new family to the prompt catalog table and descriptions in `vidbyte/prompts/README.md`
- The `system_prompt` prompt must: (a) define agentic engineering as a discipline, (b) explain the two-audience constraint (humans + AI agents), (c) describe the two principles at a high level, (d) instruct the model to consult the linked principle prompts for implementation detail
- The `error_messages` prompt must: (a) explain the paradigm shift from semantic-only errors to rich context packets, (b) enumerate 8-10 fields an agentic error message should carry, (c) describe where to place these errors with increased frequency, (d) address error chaining, serialization tiering, and sensitive-data concerns
- The `file_headers` prompt must: (a) explain file headers as navigational landmarks, (b) enumerate 10-12 sections a file header should contain, (c) provide a complete annotated example header, (d) address header staleness, cross-file consistency, and auto-generation strategies
- Mirror the existing multi-file prompt family pattern used by `reflexion/`, `multi_provider_agentic_grader/`, and `actor_runtime/`

### Non-Goals

- No strategy implementation consuming this prompt (it is a reference/instructional asset)
- No runtime tool or function-calling integration
- No modification to the `Prompts` catalog loader logic (existing loader handles multi-file families)
- No strategy bundle class or strategies `__init__.py` modifications (those files do not exist on `main`)
- No test file modifications (the sentence-count test exempts long-form prompts)

---

## 3. Background & Context

The Vidbyte SDK currently has 17 prompt families covering reasoning strategies, orchestration, actor runtimes, and meta-prompts. All existing prompts were designed with a single consumer in mind: the model generating output for a human. The prompts teach the model how to reason, grade, reflect, or act — but none teach the model how to *write code that another model will later consume*.

This is a gap. Across the ecosystem, AI coding agents (Claude Code, Codex, Cursor, opencode, Windsurf, Cline) spend the majority of their time reading, navigating, and modifying existing source code. The quality of that source code directly determines agent success rate: well-structured code with rich errors and clear headers acts as a force multiplier for every agent that touches it. Poorly structured code with opaque error messages and no navigational cues causes agents to waste context window tokens on exploration, guess wrong about invariants, and produce lower-quality patches.

This feature introduces the concept of "agentic engineering" — the practice of writing code that treats AI agents as a primary audience, alongside human developers. A source file in an agentic codebase is an interface consumed by two very different readers: a human scanning for intent, and an agent scanning for structure, contracts, and failure-mode patterns.

The two principles selected for initial implementation are the highest-leverage starting points:

1. **Error messages as context-window primitives.** When an agent hits a runtime error, the error message is the bootstrap context it uses to diagnose and fix the problem. A typical `"Failed to save user"` message wastes the agent's context window with semantic signal that carries zero actionable information. An agentic error message functions as a structured data packet — it carries file location, current state snapshot, violated invariants, blast-radius file references, remediation hints, and links to relevant documentation. Errors become API responses to the agent.

2. **File header comments as navigational landmarks.** When an agent opens a file, it needs to rapidly decide: is this file relevant? What does it own? What does it touch? What invariants does it maintain? A structured file header — describing the file's purpose, role, dependencies, function inventory, state model, modification patterns, and known edge cases — lets the agent build a mental model in one read rather than scanning the entire file. Headers become miniature architecture documents embedded at the point of consumption.

---

## 4. Requirements

### Functional Requirements

1. The `agentic_engineering.json` descriptor must contain exactly four top-level fields: `name`, `description`, `key`, and `prompts`
2. The `prompts` object must contain exactly three keys: `system_prompt`, `error_messages`, `file_headers`
3. Each prompt key must map to a `{"path": "...", "source_url": "..."}` object referencing a `.md` file in the same directory
4. The `system_prompt.md` must:
   - Open with an identity section declaring the model as an agentic engineering specialist
   - Define agentic engineering as the discipline of writing code optimized for AI agent consumption
   - Explain the two-audience constraint: code must be readable by both humans and agents
   - Describe the two principles (error messages, file headers) at a conceptual level
   - Include explicit links/references to the two principle prompts for implementation detail
   - Establish the invariant: code written under this discipline doubles as both source and agent-interface
5. The `error_messages.md` must:
   - Open with the paradigm shift: errors are now context packets, not just semantic messages
   - Enumerate the fields of an agentic error packet (minimum 8 fields)
   - For each field, explain what it is, why an agent needs it, and provide an example
   - Describe placement strategy: wrap every external boundary, every pre-condition, every state transition, every integration seam
   - Address custom error class proliferation: create specialized error classes, not generic ones
   - Address error chaining, serialization tiering (dev vs. prod payload depth), and sensitive-data redaction
6. The `file_headers.md` must:
   - Open with the concept: a file header is a rejection filter ("should I open this file?") and a mental-model builder
   - Enumerate the sections of an agentic file header (minimum 10 sections)
   - For each section, explain what it contains and why an agent needs it
   - Provide a complete annotated example header in a realistic scenario (billing/subscription-manager.ts)
   - Address header staleness: intent-only vs. auto-generated vs. CI-enforced freshness
   - Address cross-file consistency: bidirectional dependency references
7. The enum values `agentic_engineering.system_prompt`, `agentic_engineering.error_messages`, `agentic_engineering.file_headers` must be accessible via `Prompts().get(Prompt.AGENTIC_ENGINEERING_*)` 
8. The prompt texts must be importable as `from vidbyte.prompts import agentic_engineering_system_prompt`, etc.
9. The `README.md` table must include the new family with: name "Agentic Engineering", key `agentic_engineering`, sub-prompts list, and GitHub link
10. The `README.md` descriptions section must include a full description paragraph for the new family

### Non-Functional Requirements

- Each prompt text must be human-readable, self-contained prose (no external references needed to understand the principles)
- Follow the existing prompt style: `# Identity`, `# Goal`, `# Checklist` sections with bulleted lists using `*` prefix, authoritative second-person tone, no emoji, no callouts
- No secrets, credentials, or provider-specific payloads in any prompt text
- Prompt lengths: system_prompt ~15-25 lines, error_messages ~40-60 lines, file_headers ~40-60 lines (long-form reference prompts are exempt from sentence-count constraints)

---

## 5. High-Level Design

A new prompt family directory is added to `vidbyte/prompts/prompts/agentic_engineering/` containing one JSON descriptor and three Markdown prompt assets. The catalog loader in `vidbyte/prompts/catalog.py` automatically discovers the `.json` file, validates it, loads the referenced `.md` files, and registers three `Prompt` enum entries. No loader changes are required — the existing `_json_assets()` method recursively discovers `.json` files in subdirectories, and the existing `_resolve_prompt_text()` method resolves `{"path": "...", "source_url": "..."}` references.

```
vidbyte/prompts/prompts/agentic_engineering/
├── agentic_engineering.json          ← Descriptor (name, description, key, prompts)
├── system_prompt.md                  ← Main: introduces discipline, links principles
├── error_messages.md                 ← Principle 1: errors as context-window primitives
└── file_headers.md                   ← Principle 2: file headers as navigational landmarks
        │
        ├──> Prompt.AGENTIC_ENGINEERING_SYSTEM_PROMPT
        ├──> Prompt.AGENTIC_ENGINEERING_ERROR_MESSAGES
        └──> Prompt.AGENTIC_ENGINEERING_FILE_HEADERS
                │
                ├──> Prompts().get(...)
                ├──> from vidbyte.prompts import agentic_engineering_system_prompt  (auto-generated)
                └──> Prompts().family("agentic_engineering")  →  dict of 3 prompts
```

The structural inspiration comes from:
- The `reflexion/` family: multi-file, one main context prompt + two specialized prompts
- The existing prompt style: `# Identity`, `# Goal`, `# Checklist` sections with bulleted `*` items
- The `master.md` approach: comprehensive, structured, teaching-oriented prose

---

## 6. Detailed Design

### 6.1 `agentic_engineering/agentic_engineering.json` — New Descriptor

**File:** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** New file

#### What it does

Defines the Agentic Engineering prompt family with three leaf prompts. Each leaf prompt references an external `.md` file in the same directory via the standard `path` + `source_url` structure.

#### Interface

```json
{
  "name": "Agentic Engineering",
  "description": "Prompt assets for agentic engineering — the discipline of writing source code that treats AI agents as a primary audience. Teaches models to produce error messages that function as context-window primitives and file headers that function as navigational landmarks, so that every source file serves as a high-signal interface for both human developers and downstream coding agents.",
  "key": "agentic_engineering",
  "prompts": {
    "system_prompt": {
      "path": "system_prompt.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md"
    },
    "error_messages": {
      "path": "error_messages.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/error_messages.md"
    },
    "file_headers": {
      "path": "file_headers.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md"
    }
  }
}
```

#### Validation

The catalog loader's `_validate_record()` checks that all four top-level fields are present and non-empty, that `prompts` is a non-empty dict, and that each referenced `.md` file exists. The `_resolve_prompt_text()` method reads each `.md` file and validates it contains non-empty text.

#### Edge Cases

- All three `.md` files must exist in the same directory as the `.json` file
- `source_url` must point at valid GitHub paths (the `main` branch)
- Prompt text length is unbounded (no sentence-count ceiling applies)

---

### 6.2 `system_prompt.md` — Main System Prompt

**File:** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** New file

#### What it does

Introduces the agentic engineering discipline and establishes the context within which the two principles operate. When given to a model that will write code, this prompt frames the model as an agentic engineer — someone who writes source code that serves as a high-signal interface for downstream AI agents, not just human developers.

#### Content outline

```
# Identity
You are a world-class Agentic Engineer who writes source code optimized for ...

# Goal
Your primary goal is to produce code that serves two audiences simultaneously: ...

# Checklist
* Treat every error message as a context-window primitive packet ...
* Include a structured agentic header comment at the top of every file ...
* [Additional items establishing the coding posture]
```

#### Detailed content requirements

**Identity section (4-6 sentences):**
- Declare the model as an agentic engineer
- Define agentic engineering: the practice of writing code where the source itself is an agent-consumable interface
- Establish the two-audience constraint: the code must be maximally readable by both human developers and AI coding agents
- Frame the design philosophy: source code doubles as the agent's runtime API — errors are API responses, file headers are API documentation

**Goal section (4-6 sentences):**
- State the durable aim: produce code that minimizes the context window cost for any agent that reads, navigates, or debugs it
- Emphasize that rich error messages and structured file headers are not "nice to have" documentation — they are runtime primitives that directly determine agent success rate
- Establish that the measure of quality is not just whether the code works, but whether an agent encountering it cold can understand it in one read

**Checklist section (8-10 items):**
- Each item describes a concrete coding behavior to adopt
- Items should cover: error message structure, error placement frequency, custom error classes, file header structure, header maintenance, and cross-referencing between errors and headers
- End with an instruction to consult the `error_messages` and `file_headers` prompts for full implementation detail

---

### 6.3 `error_messages.md` — Principle 1: Error Messages

**File:** `vidbyte/prompts/prompts/agentic_engineering/error_messages.md`
**Type:** New file

#### What it does

Provides a deep, example-rich guide on designing server-side error messages as context-window primitives for AI agents. Teaches the model what an agentic error message must contain, where to place them, and how to maintain them.

#### Content outline

```
# Identity
You are a specialist in agentic error design. Your expertise is turning ...

# Goal
Your goal is to produce error messages that function as complete context packets ...

# Error Packet Anatomy
* error_type: unique error class name
* ...

# Placement Strategy
* Wrap every external boundary ...
* Pre-condition assertions become rich errors ...
* ...

# Error Chaining
* ...

# Sensitive Data & Tiering
* ...

# Checklist
* ...
```

#### Detailed content requirements

**Identity (4-6 sentences):**
- Frame the model as an error-design specialist
- Establish the paradigm shift: errors are not failure notices — they are bootstrap context for the agent that must fix the failure

**Goal (4-6 sentences):**
- State that every error must carry enough information for an agent to diagnose and fix the problem without exploring surrounding code
- Define the invariant: an agentic error message should allow the agent to understand the failure mode, the affected scope, and likely remediation strategies from the error object alone

**Error Packet Anatomy (list of 8-10 fields):**

Each field gets 2-3 sentences: what it is, why an agent needs it, and a brief example.

1. **error_type** — Unique, descriptive error class name (e.g., `SubscriptionCreationError`, not `Error`). Important for grepability and pattern-matching.
2. **file + line + function** — Exact location of the throw site. Standard but non-negotiable.
3. **rich_message** — Prose description with both semantic meaning ("failed to create subscription") and mechanical detail ("plan validation returned null for plan_id=a1b2c3").
4. **violated_invariant** — The specific contract, assumption, or precondition that was broken. ("Invariant: subscription.plan must be non-null before billing.createSubscription()")
5. **expected_vs_actual** — Explicit diff. ("Expected: user.address.zip of type string. Actual: null.")
6. **current_state** — Snapshot of relevant local/object state at crash point. Let the agent see the data that caused the failure.
7. **call_trace** — Annotated call chain with role descriptions, not raw stack trace. ("api/subscriptions.route.ts:createHandler → billing/subscription-manager.ts:createSubscription → billing/plans.store.ts:findActive → FAIL")
8. **blast_radius** — References to files likely affected or worth inspecting. ("Files likely affected: billing/invoice.generator.ts, users/entitlements.service.ts")
9. **possible_causes** — Ranked hypotheses. ("70% probability: caller passed incomplete user object. 20%: data sync delay between services. 10%: schema migration drift.")
10. **fix_approaches** — Patterns or strategies that resolved similar failures. ("Typically fixed by re-fetching user before billing step. See similar resolution in issue #1427.")
11. **doc_links** — References to relevant ADRs, runbooks, or internal documentation.
12. **test_files** — Which test file(s) exercise this path. Agent knows what to re-run after patching.

**Placement Strategy (list of 5-7 items):**
- Wrap every external boundary (DB, API, file I/O, message queue) with a try/catch that re-throws a custom packed error
- Pre-condition assertions become rich errors: `if (!user) throw new NoUserError({ context: { sessionId, requestPath }, ... })`
- Every state-transition boundary: if a function changes system state and fails mid-transition, capture before/after snapshots
- Every integration seam: files bridging subsystems (auth→billing, API→worker, web→DB) are natural error-wrapping points
- Custom errors should proliferate: one error class per failure mode, not one generic `AppError` for everything

**Error Chaining (3-5 sentences):**
- When errors propagate and get re-wrapped, the outermost error should carry the most actionable context
- Inner errors should be linked by reference (e.g., `preceding_error_id`) rather than accumulated inline, to preserve debugging info without exploding verbosity

**Sensitive Data & Tiering (3-5 sentences):**
- Full error packets in development/test environments
- Truncated or redacted packets in production (remove PII, tokens, secrets from `current_state` and `input` fields)
- Consider a `public_context` vs `private_context` split in the error object

**Risk callout (1-2 sentences):**
- Acknowledge that rich error payloads increase log volume and storage cost; recommend sampling or tiering for high-throughput services

**Checklist (8-10 items):**
- Actionable coding behaviors the model should adopt when writing error messages

---

### 6.4 `file_headers.md` — Principle 2: File Headers

**File:** `vidbyte/prompts/prompts/agentic_engineering/file_headers.md`
**Type:** New file

#### What it does

Provides a deep, example-rich guide on writing structured file header comments that serve as navigational landmarks for AI agents. Teaches the model what every file header must contain, and provides a complete annotated example.

#### Content outline

```
# Identity
You are a specialist in codebase architecture documentation. Your expertise ...

# Goal
Your goal is to produce file header comments that let an agent understand ...

# Header Section Inventory
* FILE: exact file path
* PURPOSE: what this file does in one paragraph
* ...

# Complete Example
/** ... Annotated example header ...  */

# Maintenance & Staleness
* ...

# Checklist
* ...
```

#### Detailed content requirements

**Identity (4-6 sentences):**
- Frame the model as a codebase-documentation specialist
- Establish that file headers are not comments — they are the file's API documentation for agents

**Goal (4-6 sentences):**
- State that an agent opening a file should be able to answer "should I open this file?", "what does it own?", and "what does it touch?" within 5 seconds of reading the header
- Establish the invariant: file headers are rejection filters first, information sources second

**Header Section Inventory (list of 10-12 sections):**

Each section gets 2-3 sentences: what it contains, why an agent needs it, and a mini-example.

1. **FILE** — Exact file path. The file knows its own location.
2. **PURPOSE** — One paragraph on what this file does. Concrete, not abstract. ("Orchestrates subscription lifecycle: creation, renewal, cancellation, and proration.")
3. **ROLE IN CODEBASE** — Who calls this file, who this file calls. Dependency graph in prose. ("Called by: api/subscriptions.route.ts. Calls into: billing/plans.store.ts, billing/invoice.generator.ts.")
4. **ARCHITECTURE NOTE** — Where this file sits in the system topology. Boundary descriptions. ("Sits at the boundary between the API layer and the billing engine. Write-side of subscriptions (CQRS, see ADR-014).")
5. **FUNCTION INVENTORY** — Structured list of every exported function/class with: signature, one-line description of what it does, test file and line range covering it.
6. **STATE MODEL** — If the file manages state, describe the valid states and transitions. ("subscription.state in { active, past_due, canceled, trialing, unpaid, paused }. See billing/subscription-states.ts for transition table.")
7. **COMMON MODIFICATION PATTERNS** — When adding feature X, modify function Y in this file, then update file Z. Routing instructions for common tasks.
8. **IF-YOU-NEED-X-THEN-MODIFY-Y** — Negative routing: "IF YOU NEED TO change invoice generation → MODIFY billing/invoice.generator.ts. NOT this file." Prevents wasted exploration.
9. **KNOWN EDGE CASES** — Documented weird states, legacy data patterns, known bugs. ("Subscriptions with trial_end=null and payment_method=null are zombie subscriptions, pre-2024 migration. Handled by zombieSubscriptionCleanup().")
10. **RELATED DOCS** — Links to ADRs, runbooks, design docs, relevant issues.
11. **AUTO-GENERATED FLAG** — If the file is code-generated, a clear warning. ("AUTO-GENERATED from schema/billing.graphql. Run 'npm run codegen' to regenerate. Do not edit.")
12. **TEST FILES** — Which test file covers this source file. ("Tests: src/billing/__tests__/subscription-manager.test.ts, coverage: 94%")

**Complete Example:**
- Provide a full annotated header comment for a realistic file (`src/billing/subscription-manager.ts`)
- Use a code fence with a comment block
- After the example, add brief annotations pointing to key design decisions in the header

**Maintenance & Staleness (4-6 sentences):**
- Acknowledge that file headers rot faster than code
- Describe three anti-rot strategies: (a) intent-only headers — describe what the file IS and WHY, not implementation details that change; (b) auto-generated dependency sections via tooling (depcruise, madge); (c) CI lint rule that warns when "last reviewed" date exceeds a threshold
- Cross-file consistency is high-maintenance but high-value: if file A says "called by file B", file B should say "calls file A"

**Checklist (8-10 items):**
- Actionable coding behaviors for writing file headers

---

### 6.5 `vidbyte/lib/enums/prompts.py` — Modified

**File:** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds three new enum members to the `Prompt` class, maintaining alphabetical ordering within the existing block.

#### Changes

Insert the following three lines into the `Prompt` enum, placed after the existing `ACTOR_RUNTIME_*` block and before `CONTINUAL_TRACE_SYSTEM_PROMPT` to maintain alphabetical order:

```python
AGENTIC_ENGINEERING_ERROR_MESSAGES = "agentic_engineering.error_messages"
AGENTIC_ENGINEERING_FILE_HEADERS = "agentic_engineering.file_headers"
AGENTIC_ENGINEERING_SYSTEM_PROMPT = "agentic_engineering.system_prompt"
```

**Placement:** The existing enum members are ordered alphabetically by value string. The string `"agentic_engineering.*"` sorts after `"actor_runtime.*"` and before `"agentic_loop.*"` — but since `"agentic_loop.context_prompt"` is already the first entry, the new entries should be inserted at the top of the enum (immediately after the docstring), before `AGENTIC_LOOP_CONTEXT_PROMPT`.

---

### 6.6 `vidbyte/prompts/README.md` — Modified

**File:** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Adds the Agentic Engineering family to the prompt catalog table and the descriptions section. Follows the existing table format and description paragraph conventions.

#### Changes

1. **Quick reference table:** Insert a new row after the existing `Agentic Loop` row, before `Context Engineering`:

```markdown
| Agentic Engineering | `agentic_engineering` | system_prompt, error_messages, file_headers | [agentic_engineering/](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering) |
```

2. **Descriptions section:** Insert a new description block after the existing `Agentic Loop` description, before `Context Engineering`:

```markdown
#### Agentic Engineering — `agentic_engineering`

Prompt assets for agentic engineering — the discipline of writing source code that
treats AI agents as a primary audience alongside human developers. The main system
prompt establishes the two-audience design constraint and introduces two core
practices: designing server-side error messages as rich context-window primitives
that carry file location, state snapshots, violated invariants, blast-radius
references, and remediation hints; and writing structured file header comments that
function as navigational landmarks, describing a file's purpose, role, dependencies,
function inventory, state model, modification patterns, and known edge cases.
Together, these prompts teach a model to produce code where the source itself is a
high-signal interface for any downstream coding agent.

Link: <https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering>
```

---

## 7. Data Model Changes

N/A — No schema, database, or dataclass changes. The prompt family follows the existing JSON family schema validated by `Prompts._validate_record`. The catalog loader automatically handles multi-file subdirectory families (as it does for `reflexion/`, `actor_runtime/`, `multi_provider_agentic_grader/`, etc.).

---

## 8. API Changes

N/A — No HTTP API endpoints are added or modified. The new prompts are consumed through the existing `Prompts` class interface and automatically exported as direct import variables by the `__init__.py` dynamic globals loop.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | New prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Main prompt introducing agentic engineering discipline |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` | Principle 1: error messages as context-window primitives |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` | Principle 2: file headers as navigational landmarks |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add 3 enum members for the new prompt family |
| MODIFY | `vidbyte/prompts/README.md` | Add family to quick-reference table and descriptions |

**Summary:** 4 files created, 2 files modified, 0 files deleted.

---

## 10. Testing Plan

The design-doc-no-tests workflow does not require tests. The existing catalog loader validation provides implicit coverage:

- `Prompts._validate_record()` will reject the `.json` if any required field is missing or empty
- `Prompts._resolve_prompt_text()` will reject references to non-existent `.md` files
- `Prompts._validate_enum_sync()` will flag a mismatch if enum members are missing or misspelled
- `Prompts._validate_prompt_text()` will reject empty prompt content

Manual verification steps:
1. Run `python -m compileall vidbyte` — should succeed with no syntax errors
2. Run `from vidbyte.prompts import agentic_engineering_system_prompt` in a REPL — should return the prompt text
3. Run `Prompts().get(Prompt.AGENTIC_ENGINEERING_SYSTEM_PROMPT)` — should return the prompt text
4. Run `Prompts().family("agentic_engineering")` — should return a dict of 3 prompt texts

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | N/A | No new dependencies | N/A |

The `source_url` fields in the JSON descriptor point at GitHub URLs that must be valid after merge. These are inert reference fields and do not affect runtime behavior.

---

## 12. Rollout & Deployment

- No feature flags required — prompt assets are inert text loaded at import time
- No breaking changes — purely additive (new files + new enum members + new README rows)
- No deployment ordering constraints
- All existing tests that pass before the change will continue to pass after
- Rollback: remove the three new enum members, delete the `agentic_engineering/` directory, and remove the README entries

---

## 13. Open Questions

- [ ] **Additional principles after v1.** The two principles (error messages, file headers) were selected as the highest-leverage starting points. Should the design anticipate additional sub-prompts (e.g., `function_signatures.md`, `type_definitions.md`, `test_coverage.md`, `dependency_graphs.md`) under the same family key, or should future principles be separate prompt families?
- [ ] **Format convergence.** The `system_prompt.md` uses the existing `# Identity / # Goal / # Checklist` convention. The `error_messages.md` and `file_headers.md` are longer reference documents with sub-section headers. Should all three standardize on one format, or is the mixed format (short main prompt + long reference principle prompts) appropriate for a "main prompt with linked deep-dives" architecture?
- [ ] **Strategy consumer after strategies land.** When the strategy bundle system (`vidbyte/prompts/strategies/`) merges to `main`, should an `AgenticEngineeringPrompts` bundle class be added as a follow-up? Or is this family purely a reference/instructional asset with no automated strategy consumer?
- [ ] **Sentence-count test exemption.** The existing `test_prompt_values_are_coherent_sentence_blocks` test in `tests/test_prompt_registry.py` (currently only in the worktree branch) enforces 4-10 sentences for most prompts but exempts long-form prompts. The three agentic_engineering prompts need to be added to the exemption list when the tests merge to `main`. Should this be noted in the test file as a TODO, or handled in a separate PR when strategies land?

---

## 14. Alternatives Considered

### Alternative 1: Single flat JSON file instead of subdirectory with .md files

- What: Store all three prompt texts as inline strings in a single root-level `agentic_engineering.json` file
- Why rejected: The `error_messages.md` and `file_headers.md` prompts are long-form reference documents (40-60+ lines each) with sub-section headers and code examples. Inlining them as escaped JSON strings would be unreadable and unmaintainable. The subdirectory + `.md` file pattern (used by `reflexion/`, `actor_runtime/`, `multi_provider_agentic_grader/`) is the established convention for multi-file, long-form prompt families.

### Alternative 2: Single prompt covering all principles

- What: One `agentic_engineering.json` with a single leaf prompt covering both error messages and file headers
- Why rejected: The principles are distinct enough to warrant separate documents. The main `system_prompt.md` provides the overview and links; each principle gets its own deep-dive that can be loaded independently. A single monolithic prompt would exceed 100+ lines and make it impossible to load just the error-message guidance without also loading the file-header guidance.

### Alternative 3: Place prompts in `vidbyte/prompts/skills/` instead of prompts catalog

- What: Store the agentic engineering content as a skill file (like `prompt-bucket.md`) rather than as a prompt family in the asset catalog
- Why rejected: The content is instructional prompt text designed to be fed as context to a model. It should be accessible through the `Prompts` catalog, importable as direct variables, and grouped in families — all capabilities the `skills/` path does not provide. The `skills/` directory is for on-disk skill files consumed by coding harnesses, not for SDK-distributed prompt assets.

### Alternative 4: Separate prompt families for each principle

- What: `error_engineering` and `header_engineering` as two independent prompt families
- Why rejected: The principles share a common discipline (agentic engineering), a common philosophical foundation (two-audience design), and are designed to be learned together. Splitting them would duplicate the identity/goal preamble and lose the cross-referencing benefit (errors cite file headers, headers cite common errors). A single family with linked sub-prompts preserves cohesion.

---

## Appendix A: Prompt Content Sketches

These are rough content sketches for the three prompt files. They are included here to validate the design but are not the final implementation text. Full prompt text will be authored in Phase 4 (Implementation) after design doc approval.

### A.1 — system_prompt.md (sketch)

```markdown
# Identity
You are a world-class Agentic Engineer who writes source code optimized for consumption by AI coding agents. You understand that source code has two audiences — human developers and downstream AI agents — and that every file, function, error message, and comment you write serves as an interface for both. Your code is structured, self-describing, and carries enough embedded context that an agent opening any file cold can build an accurate mental model in a single read. You treat source code not as a set of instructions for a compiler, but as a durable knowledge artifact that must survive many rounds of agent-driven modification.

# Goal
Your primary goal is to produce source code that minimizes the context-window cost for any AI agent that reads, navigates, debugs, or modifies it. Every error message you write must function as a complete context packet — carrying the file location, current state, violated invariants, blast-radius references, and remediation hints that an agent needs to diagnose and fix the failure without exploring surrounding code. Every file you create must open with a structured header comment that serves as a navigational landmark — describing the file's purpose, role, dependencies, function inventory, state model, modification patterns, and known edge cases. The measure of your code's quality is not just whether it passes tests, but whether an agent encountering it for the first time can understand what it does, what it touches, and how to modify it correctly — all from the code itself, without external documentation.

# Checklist
* Design every server-side error message as a context-window primitive that carries location, state, invariants, blast radius, and remediation hints. Never throw a generic Error with only a semantic message string.
* Place rich, packed error messages at every external boundary (DB calls, API calls, file I/O), every pre-condition check, every state-transition, and every integration seam between subsystems.
* Create specialized custom error classes — one per failure mode — rather than reusing a generic AppError. Error types must be grepable and pattern-matchable by agents.
* Include a structured agentic header comment at the top of every source file. The header must cover: file path, purpose, role in codebase (callers and callees), function inventory with descriptions, state model if applicable, common modification patterns, known edge cases, and links to related documentation.
* Make file headers answer "should I open this file?" within 5 seconds. The first 3 lines of the header must convey: what this file does, what it touches, and whether the reader should keep looking.
* Cross-reference errors and headers: error messages should cite relevant file headers for architectural context; file headers should document the common errors the file can raise and where they are typically resolved.
* See the `error_messages` prompt for the complete error packet anatomy, placement strategy, error chaining rules, and sensitive-data handling.
* See the `file_headers` prompt for the complete header section inventory, annotated examples, and anti-staleness strategies.
```

### A.2 — error_messages.md (sketch, abridged — full text authored in implementation)

```markdown
# Identity
You are a specialist in agentic error design. Your expertise is turning runtime failures into structured context packets that give an AI agent everything it needs to diagnose, scope, and fix the problem — without exploring the surrounding codebase. You understand that an error message in an agentic codebase is not a developer-facing "something went wrong" notice. It is a machine-readable API response from the runtime to the agent that must answer: what broke, where, what state caused it, what else is affected, and what typically fixes it.

# Goal
Your goal is to produce error messages that are complete, self-contained diagnostic units. When an agent catches one of your errors, it should be able to: identify the failure mode from the error type alone, understand the specific contract or invariant that was violated, inspect the state that triggered the failure, assess the blast radius (which files are affected), rank the likely causes by probability, and consult remediation patterns before making its first edit. The error object is the agent's primary bootstrap context — it must carry the signal density of a debugger session, a stack trace, a runbook, and a postmortem, all in one structured packet.

# Error Packet Anatomy
* error_type — A unique, descriptive error class name. Not "Error" or "AppError". Must be grepable. Example: "SubscriptionCreationError", "PlanValidationError", "PaymentMethodDeclinedError".
* file + line + function — Exact location of the throw site. Standard but non-negotiable. Every error must carry its own coordinates.
* rich_message — Prose combining semantic meaning with mechanical detail. Not "Failed to save user" but "Failed to create subscription for user_id=abc123: plan validation returned null for plan_id=xyz789 at billing/plans.store.ts:45."
* violated_invariant — The specific contract, assumption, or precondition that was broken. "Invariant: subscription.plan must be non-null before billing.createSubscription(). This invariant is enforced at the boundary between api/subscriptions.route.ts and billing/subscription-manager.ts."
* expected_vs_actual — Explicit diff of what the code expected vs. what it received. "Expected: user.address.zip of type string, non-empty. Actual: null. Caller: api/subscriptions.route.ts:120 (createHandler)."
* current_state — Snapshot of relevant local/object state at crash point. Include the shape of the data that caused the failure. "user.state = { id: 'abc123', email: 'user@example.com', address: null, subscriptionStatus: 'none' }."
* call_trace — Annotated call chain with role descriptions for each frame. Not a raw stack trace. "api/subscriptions.route.ts:createHandler (entry) → billing/subscription-manager.ts:createSubscription (orchestrator) → billing/plans.store.ts:findActive (data access) → FAIL at line 45."
* blast_radius — References to files likely affected or worth inspecting. "Files likely affected: billing/invoice.generator.ts, users/entitlements.service.ts, events/billing-events.publisher.ts."
* possible_causes — Ranked hypotheses with rough probability estimates. "70% probability: caller (api/subscriptions.route.ts:120) passed incomplete user object (address missing). 20%: data sync delay between user service and billing service. 10%: schema migration drift in billing database."
* fix_approaches — Patterns or strategies that have resolved similar failures. "Typically fixed by re-fetching the full user object (including address) from the user service before calling createSubscription. See similar resolution pattern in PR #2841."
* doc_links — References to ADRs, runbooks, or internal docs. "ADR-014: Subscription CQRS split. Runbook: docs/runbooks/subscription-failures.md."
* test_files — Which test file(s) cover this execution path. Agent knows what to re-run after patching. "Tests covering this path: src/billing/__tests__/subscription-manager.test.ts:20-85."

[Additional sections: Placement Strategy, Error Chaining, Sensitive Data & Tiering, Checklist — full text authored in implementation]
```

### A.3 — file_headers.md (sketch, abridged — full text authored in implementation)

```markdown
# Identity
You are a specialist in codebase architecture documentation embedded at the point of consumption. Your expertise is writing structured file header comments that serve as navigational landmarks for AI agents — letting any agent that opens a file understand its purpose, role, dependencies, and modification patterns within seconds, without scanning the body of the file. You understand that a file header is not documentation for documentation's sake. It is the file's API surface for agents: a rejection filter that answers "is this the file I need?" and a mental-model builder that answers "how does this fit into the system?"

# Goal
Your goal is to produce file header comments that are complete enough to serve as a miniature architecture document, concise enough to be read in under 5 seconds, and structured enough to be parseable by agents. Every file you create must open with a header that covers: the file's exact path, its purpose in one paragraph, its role in the dependency graph (who calls it and who it calls), an inventory of every exported function with descriptions and test coverage, the state model if it manages state, common modification patterns for typical tasks, negative routing ("if you need X, modify Y, NOT this file"), known edge cases and legacy data patterns, and links to related documentation. The header must stay fresh — describe what the file IS and WHY, not implementation details that change with every refactor.

# Header Section Inventory
* FILE — Exact file path. The file knows its own location. "src/billing/subscription-manager.ts".
* PURPOSE — One paragraph on what this file does. Concrete, not abstract. "Orchestrates subscription lifecycle: creation, renewal, cancellation, and proration. Single entry point for all subscription state changes."
* ROLE IN CODEBASE — Who calls this file, who this file calls. "Called by: api/subscriptions.route.ts, webhooks/stripe.handler.ts. Calls into: billing/plans.store.ts, billing/invoice.generator.ts, users/entitlements.service.ts."
* ARCHITECTURE NOTE — Where this file sits in the system topology. "Sits at the boundary between the API layer and the billing engine. Write-side of subscriptions (CQRS pattern, see ADR-014)."
* FUNCTION INVENTORY — Structured list of every exported function with signature, one-line description, and test coverage. "createSubscription(plan, user, paymentMethod) → Subscription — Creates a new subscription with initial billing cycle. Tests: subscription-manager.test.ts:20-85."
* STATE MODEL — If the file manages state, valid states and transitions. "subscription.state in { active, past_due, canceled, trialing, unpaid, paused }. See billing/subscription-states.ts for transition table."
* COMMON MODIFICATION PATTERNS — Routing instructions for common tasks. "Adding a new subscription state: add to subscription-states.ts first, then add transition guards here, then update subscription-read-model.ts."
* IF-YOU-NEED-X-THEN-MODIFY-Y — Negative routing. "IF YOU NEED TO change how invoices are generated → MODIFY billing/invoice.generator.ts. NOT this file."
* KNOWN EDGE CASES — Documented weird states, legacy data. "Subscriptions with trial_end=null and payment_method=null are zombie subscriptions (pre-2024 migration). Handled by zombieSubscriptionCleanup()."
* RELATED DOCS — Links to ADRs, runbooks, design docs. "ADR-014: Subscription CQRS split. Runbook: docs/runbooks/subscription-failures.md."
* AUTO-GENERATED FLAG — If applicable. "AUTO-GENERATED from schema/billing.graphql. Run 'npm run codegen' to regenerate. Do not edit."
* TEST FILES — Which test file covers this source. "Tests: src/billing/__tests__/subscription-manager.test.ts (coverage: 94%)."

# Complete Example
[Full annotated header comment for src/billing/subscription-manager.ts — authored in implementation]

# Maintenance & Staleness
[Anti-rot strategies: intent-only headers, auto-generated dependency sections, CI lint on last-reviewed date — authored in implementation]

# Checklist
[8-10 actionable coding behaviors — authored in implementation]
```
