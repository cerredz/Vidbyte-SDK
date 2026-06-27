# Design Doc: Agentic Engineering — Folder README and Function Design Principles

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-27
**Last Updated:** 2026-06-27

---

## 1. Overview

Extend the `agentic_engineering` prompt family (designed in `docs/design/agentic-engineering.md`, not yet implemented) with two new principle prompts: `folder_readme` and `function_design`. The `folder_readme` prompt teaches models to write folder-level README files that function as comprehension caches — covering purpose, file index, and change logs — so an agent can route at folder granularity without opening source. The `function_design` prompt teaches models to write short, single-purpose functions where each function is the agent's atomic unit of comprehension, naming, change, test, and reuse, and capping size keeps all five units aligned to one thing. Together with the original three principles (system_prompt, error_messages, file_headers), the family becomes a complete five-principle agentic engineering curriculum.

---

## 2. Goals & Non-Goals

### Goals

- Add `folder_readme.md` and `function_design.md` as new principle prompts under `vidbyte/prompts/prompts/agentic_engineering/`
- Add two new keys (`folder_readme`, `function_design`) to the `agentic_engineering.json` descriptor (creating the descriptor since it does not yet exist)
- Add two new enum members: `AGENTIC_ENGINEERING_FOLDER_README` and `AGENTIC_ENGINEERING_FUNCTION_DESIGN` to `vidbyte/lib/enums/prompts.py`
- Implement the full `agentic_engineering` prompt family in a single PR, including the three principles already designed in `docs/design/agentic-engineering.md` (system_prompt, error_messages, file_headers) and the two new ones here
- Update `vidbyte/prompts/README.md` to reflect all five sub-prompts in the family row and descriptions section
- Format both new principle prompts using the same `# Identity / # Goal / sections / # Checklist` convention as the other agentic engineering prompts

### Non-Goals

- No changes to the system_prompt, error_messages, or file_headers content (covered by the original design doc)
- No runtime tool or function-calling integration
- No changes to the catalog loader (`vidbyte/prompts/catalog.py`) — the existing loader handles multi-file families automatically
- No test file modifications (design-doc-no-tests workflow; catalog validation provides implicit coverage)

---

## 3. Background & Context

`docs/design/agentic-engineering.md` designed a three-sub-prompt family teaching models to write code optimized for AI agent consumption: error messages as context-window primitives, and file headers as navigational landmarks. The family directory and all implementation files have not been created on `main` yet.

Two additional principles were requested as follow-on additions before the family is implemented:

**Folder-level README / file index / logs.** Source code can tell an agent what code does but cannot tell it why the folder exists, when to reach for it, or what has already been tried and failed here. These are exactly the three gaps a folder README closes. Without it, agents traverse N files to locate what they need, reconstruct purpose from mechanism (often wrongly), and re-discover the same footguns every session because code records the current state but erases the history of wrong turns. The README is a comprehension cache pinned to the node the agent always lands on first.

**Clean interface + capped function length (one function, one thing).** The human rationale for short single-purpose functions is cleanliness. The agent-native rationale is sharper: the function is the agent's atomic unit of comprehension, naming, change, test, and reuse. A 200-line function blows past all five at once. Capping function size and enforcing SRP in the linter converts what is aesthetic guidance for humans into a measurable feedback signal in the agent's loop.

---

## 4. Requirements

### Functional Requirements

1. `folder_readme.md` must open with an Identity section establishing the model as a folder-documentation specialist who closes the three agent failure modes: wrong purpose inference, traversal cost, and inter-session amnesia
2. `folder_readme.md` must include a Goal section establishing that the README lets an agent read one file and correctly route at folder granularity
3. `folder_readme.md` must cover the three sections and their distinct failure modes: Folder Description/Intent, File Index, and Logs, with the agent-native rationale for each
4. `folder_readme.md` must document the disciplines that separate a live README from stale markdown: generated-vs-authored split, thin log schema, prune-and-graduate lifecycle
5. `folder_readme.md` must cover the four README extrapolations: non-goals ("does not belong here"), blast radius, canonical example pointer, and why each prevents a class of agent errors
6. `folder_readme.md` must close with a Checklist of 8-10 actionable behaviors
7. `function_design.md` must open with an Identity section establishing the model as a specialist in agent-native function boundaries
8. `function_design.md` must include a Goal section that frames each function as the agent's atomic unit of comprehension, naming, change, test, and reuse, and explains why capping size aligns all five
9. `function_design.md` must enumerate the agent-native failure modes that long functions trigger: context overflow on edit, dishonest names at call sites, unpredictable blast radius, degraded test feedback, forced copy-paste reuse, hidden mid-body invariants
10. `function_design.md` must make "one thing" operational with four tests the agent can apply: honest-name test, single level of abstraction, single reason to change, one-sentence summary without "and"
11. `function_design.md` must cover the five function-design practices: extract-till-you-drop, orchestrator/leaf split, command/query separation, kill flag arguments, pure core / imperative shell
12. `function_design.md` must cover enforcement: put line count, nesting depth, cyclomatic complexity, and arg count in the linter so the constraint is a feedback signal, not prose
13. `function_design.md` must close with a Checklist of 8-10 actionable behaviors
14. The `agentic_engineering.json` descriptor must list all five sub-prompts: `system_prompt`, `error_messages`, `file_headers`, `folder_readme`, `function_design`
15. `AGENTIC_ENGINEERING_FOLDER_README` and `AGENTIC_ENGINEERING_FUNCTION_DESIGN` must be importable via `Prompts().get(Prompt.AGENTIC_ENGINEERING_*)` and `from vidbyte.prompts import agentic_engineering_folder_readme`
16. The README family row must show all five sub-prompt names; the descriptions section must include paragraphs for both new principles

### Non-Functional Requirements

- Follow the established prompt style: `# Identity`, `# Goal`, named section headers, `*`-prefixed bullets, authoritative second-person tone, no emoji, no callouts
- Both prompts are long-form reference documents (40-70 lines); they are exempt from sentence-count constraints per the catalog validator exemption list
- No secrets, credentials, or provider-specific payloads in any prompt text

---

## 5. High-Level Design

Two new `.md` files are added to the `agentic_engineering/` prompt family directory alongside the three already designed. The `agentic_engineering.json` descriptor is created (it does not exist yet) and lists all five sub-prompts. Two enum members are added to `vidbyte/lib/enums/prompts.py`. The README is updated. No loader changes are needed — the catalog's `_json_assets()` method discovers `.json` files in subdirectories automatically.

```
vidbyte/prompts/prompts/agentic_engineering/
├── agentic_engineering.json     ← NEW: family descriptor (5 sub-prompts)
├── system_prompt.md             ← NEW: from original design doc
├── error_messages.md            ← NEW: from original design doc
├── file_headers.md              ← NEW: from original design doc
├── folder_readme.md             ← NEW: this design doc
└── function_design.md           ← NEW: this design doc
```

The `system_prompt.md` should reference all five principles by name (not just the original two) so it remains the canonical entry point for the full discipline.

---

## 6. Detailed Design

### 6.1 `agentic_engineering.json` — New Descriptor

**File:** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** New file

#### What it does

Defines the Agentic Engineering prompt family with five leaf prompts. Each leaf references an external `.md` file in the same directory.

#### Interface

```json
{
  "name": "Agentic Engineering",
  "description": "Prompt assets for agentic engineering — the discipline of writing source code that treats AI agents as a primary audience. Covers five principles: error messages as context-window primitives, file headers as navigational landmarks, folder-level READMEs as comprehension caches, and single-purpose functions as the agent's atomic unit of comprehension, naming, change, test, and reuse.",
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
    },
    "folder_readme": {
      "path": "folder_readme.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/folder_readme.md"
    },
    "function_design": {
      "path": "function_design.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md"
    }
  }
}
```

---

### 6.2 `folder_readme.md` — Principle: Folder-Level README / File Index / Logs

**File:** `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md`
**Type:** New file

#### What it does

Teaches models to write folder-level README files that function as comprehension caches, giving agents the three pieces of information raw source cannot provide: why the folder exists, when to reach for it, and what has already been tried and failed here.

#### Content structure

```
# Identity
# Goal
# The Three Sections
  ## Folder Description / Intent
  ## File Index
  ## Logs
# The Disciplines (What Keeps It Alive)
# Extending the Cache
# Checklist
```

#### Detailed content requirements

**Identity (4-6 sentences):**
- Frame the model as a folder-documentation specialist
- Establish the core limitation: source code tells an agent what code does but never why the folder exists, when to reach for it, or what has already been tried and failed
- Frame the README as a comprehension cache + externalized memory, pinned to the node the agent always lands on first
- Explain the three-section structure and that each section closes one specific agent failure mode

**Goal (4-6 sentences):**
- State that the README lets an agent read one small file and correctly route at folder granularity — open the right file, skip the rest — without a single source file traversal
- Establish that the README survives across sessions, which the agent's own context window does not
- Define "read-one-skip-many at folder granularity" as the core reliability gain

**The Three Sections:**

*Folder Description / Intent:*
- Fixes: "can't infer purpose from mechanism." Agent reading raw source reconstructs a plausible purpose that is often subtly wrong, and writes code aligned to that wrong purpose.
- What to write: the folder's job, design intent, target use cases, and overall goal — 2-4 paragraphs
- Key insight: intent is not recoverable from code at any context cost; it lives only in someone's head until cached here
- These paragraphs answer: "should my new code even go in this folder, and what is this folder for?"

*File Index:*
- Fixes: traversal cost. Without it the agent opens N files or greps blindly just to learn what's where.
- What to write: 3-4 sentences per file — enough signal to decide whether to open the file without opening it
- The blurb's job is routing, not summarizing contents: "read-one-skip-many" means each blurb is a skip enabler
- Generate the index mechanically; CI should fail when a folder has source files but no README, or when the index lists a file that no longer exists

*Logs:*
- Fixes: "no memory between sessions," specifically for negative knowledge
- This is the highest-value, lowest-density signal in the whole repo: "tried X, broke Y, the fix was Z"
- Source code records the current state but erases every wrong turn; without the log, every session re-discovers the same footgun from scratch
- Schema: `<commit/date> — what changed — why it matters / what not to repeat` — one line per entry, no prose paragraphs
- The "why it matters" clause is the part future agents actually need

**The Disciplines (What Keeps It Alive):**
- Generated vs. authored split: the file index is mechanical — generate it and CI-enforce its freshness; the description and logs are hand-authored because they carry intent the code cannot express; generating the rote half is what stops the cache from rotting
- Thin log schema: the one-line format with the "why it matters" clause is load-bearing; a polluted log with prose paragraphs costs more context than it saves and defeats its own purpose
- Prune and graduate: logs are append-only but not infinite — rotate stale entries out; best move: when a logged bug recurs, promote it from the log into a code-level guard (assert, branded type, lint rule) and then delete the log line; log → recurs → harden into code → delete

**Extending the Cache (four extrapolations):**
- Non-goals / "does not belong here": explicitly state what this folder is not for and where misplaced code belongs instead; agents misfile code constantly; one "auth lives in services/auth, not here" line prevents a whole class of wrong placements
- Blast radius: a one-liner "this folder is imported by X, depends on Y" tells an agent what it might break before editing, not after
- Canonical example pointer: name the one file in the folder worth copying from, so the agent doesn't survey five near-duplicates guessing which pattern is current
- Cross-session skip budget: how many files are safe to skip after reading the README? State it explicitly so the agent calibrates exploration depth

**Checklist (8-10 items):**
- Include a folder README for every directory that contains source files
- Write the Folder Description/Intent first, before the code, when you create a new directory; update it when the directory's purpose changes
- Limit description prose to 2-4 paragraphs covering: job, intent, use cases, goal — no implementation detail that rotates out with refactors
- Generate the File Index from the directory listing; re-generate it on every structural change; CI-fail when the index is missing or stale
- Write each file index blurb as a routing decision, not a summary: the question is "should I open this file?" not "what is in this file?"
- Keep log entries to one line with the schema: `<commit/date> — what changed — why it matters / what not to repeat`; no prose paragraphs in the log
- When a logged footgun recurs, escalate: add an assert, a lint rule, or a branded type that makes the mistake impossible, then delete the log entry
- Add a Non-goals section that names at least one class of code that does NOT belong here and where it belongs instead
- Add a one-line blast radius statement before the File Index: what imports this folder and what does this folder depend on
- Name the one canonical example file an agent should copy from; do not leave an agent guessing among near-duplicates

---

### 6.3 `function_design.md` — Principle: Clean Interface + Capped Function Length

**File:** `vidbyte/prompts/prompts/agentic_engineering/function_design.md`
**Type:** New file

#### What it does

Teaches models to write short, single-purpose functions where the function is the agent's atomic unit of comprehension, naming, change, test, and reuse. Covers the agent-native failure modes of long functions, four operational tests for "one thing," five function-design practices, and linter enforcement.

#### Content structure

```
# Identity
# Goal
# Why Short Single-Purpose Functions Are Agent-Native
# Making "ONE THING" Operational
# What To Do
# Enforcement
# Checklist
```

#### Detailed content requirements

**Identity (4-6 sentences):**
- Frame the model as a specialist in agent-native function boundaries
- Establish the agent-native rationale: the function is the agent's atomic unit of comprehension, naming, change, test, and reuse; capping size keeps all five units aligned to one thing
- Contrast with the human rationale (cleanliness) — the agent rationale is structural reliability, not aesthetics
- Frame capped function size as a concrete reliability gain, not a style preference

**Goal (4-6 sentences):**
- State the invariant: every function you write must fit in one read, carry an honest name, have a bounded blast radius, provide a clean test, and be a reuse basis rather than a copy source
- State that 20-30 lines is the target ceiling — long enough for real logic, short enough to load, understand, and verify in a single pass
- Establish that the long-function failure is exactly the agent's worst one: edits part of a 200-line body without holding the whole, "fixes line 40, breaks line 160"

**Why Short Single-Purpose Functions Are Agent-Native (6 failure modes):**
- *Fits in one read:* 20-30 lines load, get understood, and get verified in a single pass; a long function requires the agent to hold more context than it can without losing precision
- *Enables an honest name:* one thing = one name with no "and"; that name becomes a comprehension cache at the call site — the agent reads the call graph as documentation and never opens the body; a function doing five things cannot be named honestly, so its call site lies to the next agent
- *Bounds the blast radius:* small single-purpose functions localize edits; the agent can predict what a change affects; tangled functions make every edit entangled and unpredictable
- *Gives a clean test = clean feedback:* one thing = one testable contract = one sharp signal in the loop; a multi-purpose function has no clean test, so the agent's perception of "did my change work" degrades
- *Is a reuse basis, not a copy source:* small orthogonal functions are primitives the agent recombines; big functions force copy-paste-mutate, which is how agents silently duplicate logic across the codebase
- *Erases hidden mid-body invariants:* a long body accrues implicit local state ("by line 80, x is sorted and non-null") the agent must track to edit safely and routinely doesn't; short functions have nowhere for those invariants to hide

**Making "ONE THING" Operational (four tests):**
- *The honest-name test:* if you can't name the function without "and" / "or" / "then," it's two functions; the conjunction in the name is the tell
- *Single level of abstraction:* every statement in the body sits at the same conceptual altitude; mixing high-level orchestration with low-level byte-twiddling in one body means more than one thing
- *Single reason to change (SRP):* if two different kinds of requirement change would both force an edit here, it's doing two jobs
- *One-sentence summary, no "and":* if the honest description of the function needs a conjunction, split the function

**What To Do (five practices):**
- *Extract-till-you-drop, and turn the comment into the name:* the comment you were about to write above a block of code becomes the extracted function's name — converting skimmable prose into a checked, call-site-visible contract; this is the highest-leverage agent-native refactor
- *Orchestrator / leaf split:* public functions orchestrate and read like a table of contents (`validate(); charge(); notify()`); private leaf functions do the work; the agent reads the orchestrator to understand the flow and drills into exactly one leaf — progressive disclosure at the function level; the orchestrator is a readme for the behavior
- *Command / query separation:* a function either does something (command) or returns something (query), never both; outcomes are predictable and the agent is never surprised by a hidden side effect in something that looks like a getter
- *Kill flag arguments:* a boolean that switches behavior is two functions in a trenchcoat; split them so the call site names which one it wants (`render_draft()` / `render_final()`, not `render(draft=True)`); the agent picks the right one by name instead of guessing the flag
- *Pure core, imperative shell:* push side effects to the edges; keep the middle pure; pure functions are the maximally agent-safe unit — same input, same output, no hidden state to track, trivially testable, locally verifiable without reading anything else

**Enforcement:**
- Put line count, nesting depth, cyclomatic complexity, and arg count caps in the linter
- Line count is only a proxy — the real enemy is branching state the agent must hold, which complexity and nesting depth measure directly
- In the lint loop, this becomes feedback the agent meets automatically rather than prose it skims and ignores
- Cap positional args at 3; beyond that, group into a typed parameter object — wide arg lists are where agents transpose and guess

**Checklist (8-10 items):**
- Cap function bodies at 20-30 lines; if you exceed this, extract until you don't
- Apply the honest-name test before committing: if the name needs "and," "or," or "then," split the function
- Keep every statement in the function body at the same level of abstraction; mixing orchestration with low-level mechanics is a split waiting to happen
- Turn every explanatory comment above a code block into an extracted function name — the comment you write is the function you should create
- Split every public function into an orchestrating public interface that reads like a table of contents and private leaf functions that do one thing each
- Separate commands from queries: a function that returns a value must have no side effects; a function that changes state must return nothing (or at most a success signal)
- Replace every boolean flag argument that switches behavior with two explicitly named functions
- Limit positional arguments to 3; beyond that, group into a named typed object (dataclass, TypedDict, Pydantic model) so call sites are self-documenting
- Keep all side effects at the edges of each unit; make the core logic pure so any agent can verify it locally without reading anything else
- Configure the linter with cyclomatic complexity, nesting depth, line count, and arg count limits; let the linter enforce these constraints so they become loop signals, not style guidelines

---

### 6.4 `vidbyte/lib/enums/prompts.py` — Modified

**File:** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### Changes

Add the following entries after the existing `ACTOR_RUNTIME_*` block. Also add the three entries from `docs/design/agentic-engineering.md` (system_prompt, error_messages, file_headers) that are not yet in the enum. Insert all five in alphabetical order by value string — `"agentic_engineering.*"` sorts before `"agentic_loop.*"`, so these go at the very top of the enum.

```python
AGENTIC_ENGINEERING_SYSTEM_PROMPT = "agentic_engineering.system_prompt"
AGENTIC_ENGINEERING_ERROR_MESSAGES = "agentic_engineering.error_messages"
AGENTIC_ENGINEERING_FILE_HEADERS = "agentic_engineering.file_headers"
AGENTIC_ENGINEERING_FOLDER_README = "agentic_engineering.folder_readme"
AGENTIC_ENGINEERING_FUNCTION_DESIGN = "agentic_engineering.function_design"
```

---

### 6.5 `vidbyte/prompts/README.md` — Modified

**File:** `vidbyte/prompts/README.md`
**Type:** Modified

#### Changes

1. **Quick reference table:** Insert a row after `Agentic Loop`:

```markdown
| Agentic Engineering | `agentic_engineering` | system_prompt, error_messages, file_headers, folder_readme, function_design | [agentic_engineering/](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering) |
```

2. **Descriptions section:** Insert after the `Agentic Loop` description:

```markdown
#### Agentic Engineering — `agentic_engineering`

Prompt assets for agentic engineering — the discipline of writing source code that treats AI agents as a primary audience alongside human developers. The `system_prompt` establishes the two-audience design constraint and introduces five core practices. `error_messages` teaches designing server-side errors as rich context-window primitives that carry file location, state snapshots, violated invariants, blast-radius references, and remediation hints. `file_headers` teaches writing structured file header comments that serve as navigational landmarks covering purpose, role, dependencies, function inventory, state model, and modification patterns. `folder_readme` teaches writing folder-level README files that function as comprehension caches: a description section that caches why the folder exists, a file index that enables read-one-skip-many routing at folder granularity, and a change log that preserves negative knowledge across sessions. `function_design` teaches writing short single-purpose functions where the function is the agent's atomic unit of comprehension, naming, change, test, and reuse — covering the orchestrator/leaf split, command/query separation, pure core / imperative shell, and linter enforcement.

Link: <https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering>
```

---

## 7. Data Model Changes

N/A — No schema, database, or dataclass changes. All additions are prompt text assets and enum values within the existing `Prompt` enum.

---

## 8. API Changes

N/A — No HTTP API changes. The five prompts are accessible through the existing `Prompts` catalog interface and exported as direct import names by the `__init__.py` dynamic globals loop.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Family descriptor (5 sub-prompts) |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Main principle intro — from original design doc |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` | Principle: errors as context-window primitives — from original design doc |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` | Principle: file headers as navigational landmarks — from original design doc |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md` | Principle: folder README as comprehension cache — this design doc |
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/function_design.md` | Principle: one function, one thing — this design doc |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add 5 enum members for the full family |
| MODIFY | `vidbyte/prompts/README.md` | Add family row and descriptions for all 5 principles |

**Summary:** 6 files created, 2 files modified, 0 files deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | N/A | No new dependencies | N/A |

---

## 11. Rollout & Deployment

- No feature flags — prompt assets are inert text loaded at import time
- Purely additive: no existing tests or behavior changes
- Rollback: remove the five new enum members, delete the `agentic_engineering/` directory, and remove the README entries

---

## 12. Open Questions

- [ ] **system_prompt.md scope update.** The original design doc describes a system_prompt covering two principles. Should it be updated to enumerate all five, or kept as a lightweight entry point that references the five principle prompts by key name?
- [ ] **CI enforcement for folder READMEs.** The `folder_readme` principle recommends CI-fail when a source directory has no README or when the file index is stale. Should a lint script be added to the SDK as a practical example, or is this left as a prompt-only recommendation?
- [ ] **Linter config reference.** The `function_design` principle recommends specific linter caps (line count, cyclomatic complexity, nesting depth, arg count). Should the prompt name concrete defaults (e.g., "30 lines, depth 3, complexity 10, 3 args") or leave thresholds to the reader?

---

## 13. Alternatives Considered

### Alternative 1: Two separate prompt families

- What: Create `folder_engineering` and `function_engineering` as independent families
- Why rejected: Both principles are extensions of the same discipline established in `agentic_engineering`. Splitting them loses the shared identity/goal framing and breaks the "one discipline, many principles" architecture that makes the `system_prompt` useful as an entry point.

### Alternative 2: Append to system_prompt.md rather than new files

- What: Add the two new principles as additional checklist items in `system_prompt.md`
- Why rejected: The existing system_prompt is already a concise entry point. Both new principles require deep-dive content (40-70 lines each) covering rationale, operational tests, practices, and enforcement — exactly the pattern `error_messages.md` and `file_headers.md` establish. Embedding that depth in the main prompt would make it unmaintainable.

### Alternative 3: Defer until original three are implemented and merged

- What: Implement system_prompt, error_messages, file_headers first; add folder_readme and function_design in a follow-up PR
- Why rejected: All five principle prompts need the same JSON descriptor, enum block, and README row. Implementing in two PRs requires touching the descriptor and enum twice, with interim state where the descriptor only lists three sub-prompts. A single PR is cleaner — the family either exists in full or doesn't exist at all.

---

## Appendix A: Prompt Content Sketches

### A.1 — `folder_readme.md` (sketch)

```markdown
# Identity
You are a specialist in folder-level documentation and codebase navigability for AI agents. Your expertise is creating and maintaining README files at folder granularity that function as comprehension caches — a pinned knowledge artifact at the node an agent always lands on first. You understand a fundamental limitation of source code: it can tell an agent what the code does, but it cannot tell the agent why the folder exists, when to reach for it, or what has already been tried and failed. Those three gaps are exactly the three sections every folder README must contain, and each section closes one specific agent failure mode that raw source cannot address at any context cost.

# Goal
Your goal is to produce folder-level README files that let an agent read one small file and correctly decide whether to skip the entire folder or dive in with full context — without opening a single source file first. A folder README is a comprehension cache and externalized memory in one: it caches purpose the code cannot express, provides per-file routing signal that eliminates blind traversal, and logs negative knowledge across sessions so each new agent does not re-discover the same footguns from scratch. The README survives across sessions, which the agent's own context window does not. The target behavior is read-one-skip-many at folder granularity: the agent reads the README, routes correctly, and opens exactly the files it needs — no more.

# The Three Sections

## Folder Description / Intent

* This section fixes the failure mode "can't infer purpose from mechanism." An agent reading raw source reconstructs a plausible purpose for the folder, which is often subtly wrong, and then writes code aligned to the wrong purpose. Intent is not recoverable from code at any context cost — it lives only in someone's head until you write it here.
* Write 2-4 paragraphs covering: what this folder's job is, why it was designed this way, what use cases it serves, and what goal it optimizes for. These paragraphs answer the agent's question "should my new code even go in this folder?" — a question source cannot answer.
* Keep the description anchored to stable intent, not implementation details. The "why" of the folder changes far less often than the "how." Write the description to stay true through three refactors.

## File Index

* This section fixes traversal cost. Without it, the agent opens N files or greps blindly just to learn what's where. The per-file blurb is the skip enabler: enough signal to decide whether to open a file without opening it.
* Write 3-4 sentences per file. The blurb's job is routing, not summarizing contents. The question it answers is "should I open this file right now?" — not "what is in this file?"
* Generate the file index mechanically from the directory listing. CI should fail when a folder has source files but no README, or when the index names a file that no longer exists. The generated half is what stops the cache from rotting; automation is the maintenance mechanism.

## Logs

* This section fixes "no memory between sessions," specifically for negative knowledge. This is the highest-value, lowest-density signal in the repo: "tried X, broke Y, the fix was Z." Source code records the current state but erases every wrong turn — without a log, every new session re-discovers the same footgun from scratch.
* Use the schema: `<commit/date> — what changed — why it matters / what not to repeat`. One line per entry. No prose paragraphs. The "why it matters" clause is the part future agents actually need — without it, the entry is just a changelog.
* Logs are append-only but not infinite. Rotate stale entries out. Best move: when a logged bug recurs, promote it out of the log into a code-level guard — an assert, a branded type, a lint rule — and then delete the log line. The log feeds the type/guard layer and then graduates itself out of existence.

# The Disciplines

* Generated vs. authored split: the file index is mechanical — generate it and CI-enforce its freshness. The description and logs are hand-authored because they carry intent the code cannot express. Generating the rote half is what stops the cache from rotting; the rule "find nearest README, create if none, append on every structural change" is the invalidation mechanism for the authored half.
* Keep the log schema thin and skimmable. A polluted log with prose paragraphs costs more context than it saves and defeats its own purpose. The one-line format with "why it matters" is load-bearing.
* Prune aggressively. Stale log entries are noise. The correct lifecycle is: footgun appears → log it → footgun recurs → harden into code → delete the log line. The ledger exists to feed the type/guard layer, not to accumulate indefinitely.

# Extending the Cache

* Non-goals / "does not belong here": state explicitly what this folder is not for and where misplaced code belongs instead. Agents misfile code constantly. One sentence — "auth lives in services/auth, not here" — prevents a whole class of wrong placements that cost multiple sessions to discover and undo.
* Blast radius: a one-liner "this folder is imported by X, depends on Y" tells an agent what it might break before it edits, not after. Without it, the agent discovers the blast radius by breaking the build.
* Canonical example pointer: name the one file in the folder an agent should copy from when adding a new file of the same kind. Without it, the agent surveys five near-duplicates and guesses which pattern is current. One pointer eliminates that survey.

# Checklist

* Include a folder README for every directory that contains source files.
* Write the Folder Description/Intent section before the code, when you create a new directory, and update it whenever the directory's purpose or design intent changes.
* Keep the description to 2-4 paragraphs anchored to stable intent: job, design rationale, use cases, goal — no implementation details that rotate out with refactors.
* Generate the File Index from the directory listing and re-generate it on every structural change; configure CI to fail when the index is missing or lists files that no longer exist.
* Write each file index entry as a routing decision, not a content summary: the question is "should I open this file?" not "what is in this file?"
* Write log entries in the one-line schema: `<commit/date> — what changed — why it matters / what not to repeat`; no prose, no paragraphs.
* When a footgun logged here recurs, escalate: add an assert, a lint rule, or a branded type that makes the mistake impossible, then delete the log line.
* Add a Non-goals section naming at least one class of code that does NOT belong here and where it belongs instead.
* Add a one-line blast radius statement before the File Index: what imports this folder and what does this folder depend on.
* Name one canonical example file an agent should copy from when adding a new file; do not leave the agent guessing among near-duplicates.
```

---

### A.2 — `function_design.md` (sketch)

```markdown
# Identity
You are a specialist in agent-native function boundaries. Your expertise is designing functions where the function is the agent's atomic unit of comprehension, naming, change, test, and reuse — and capping function size ensures all five units stay aligned to one thing. A 200-line function blows past all five at once: it cannot be held in one read, cannot be named honestly, localizes nothing, provides no clean test, and forces copy-paste reuse instead of recombination. The rule is not aesthetic. Each property below is a concrete reliability gain for an agent operating under limited context. You write functions sized and scoped so that every unit the agent needs to operate — understand, name, change, test, reuse — maps cleanly to one function.

# Goal
Your goal is to produce functions where 20-30 lines is the ceiling, a name without "and" is always possible, the blast radius of any edit is predictable and bounded, the test contract is a single sharp assertion, and every function is a primitive to recombine rather than a template to copy-paste-mutate. The long-function failure mode is the agent's worst one: it edits part of a 200-line body without holding the whole — fixes line 40, breaks line 160. Short single-purpose functions eliminate the class of edit failures that require the agent to hold state it cannot hold.

# Why Short Single-Purpose Functions Are Agent-Native

* Fits in one read: 20-30 lines load, get understood, and get verified in a single pass. The long-function failure is exactly the agent's worst: edits part of a 200-line body without holding the whole, "fixes line 40, breaks line 160."
* Enables an honest name: one thing = one name with no "and." That name becomes a comprehension cache at the call site — the agent reads the call graph as documentation and never opens the body. A function doing five things cannot be named honestly, so its call site lies to the next agent.
* Bounds the blast radius: small single-purpose functions localize edits; the agent can predict what a change affects. Tangled functions make every edit entangled and unpredictable.
* Gives a clean test = clean feedback: one thing = one testable contract = one sharp signal in the loop. A multi-purpose function has no clean test, so the agent's perception of "did my change work" degrades.
* Is a reuse basis, not a copy source: small orthogonal functions are primitives the agent recombines; big functions force copy-paste-mutate, which is how agents silently duplicate logic across the codebase.
* Erases hidden mid-body invariants: a long body accrues implicit local state ("by line 80, x is sorted and non-null") the agent must track to edit safely and routinely does not. Short functions have nowhere for those invariants to hide.

# Making "ONE THING" Operational

These are the four tests you apply before accepting that a function does one thing. If any test fails, split.

* The honest-name test: if you cannot name the function without "and," "or," or "then," it is two functions. The conjunction in the name is the tell.
* Single level of abstraction: every statement in the body sits at the same conceptual altitude. Mixing high-level orchestration with low-level byte-twiddling in one body means more than one thing.
* Single reason to change (SRP): if two different kinds of requirement change would both force an edit here, it is doing two jobs.
* One-sentence summary, no "and": if the honest one-sentence description of the function needs a conjunction, split the function at the conjunction.

# What To Do

* Extract-till-you-drop, and turn the comment into the name: the comment you were about to write above a block becomes the extracted function's name — converting skimmable prose into a checked, call-site-visible contract. This is the single highest-leverage agent-native refactor available in any codebase.
* Orchestrator / leaf split: public functions orchestrate and read like a table of contents (`validate(); charge(); notify()`); private leaf functions do the work. The agent reads the orchestrator to understand the flow and drills into exactly one leaf — progressive disclosure at the function level. The orchestrator is a readme for the behavior.
* Command / query separation: a function either does something (command) or returns something (query), never both. Outcomes are predictable and the agent is never surprised by a hidden side effect in something that looks like a getter.
* Kill flag arguments: a boolean that switches behavior is two functions in a trenchcoat; split them so the call site names which one it wants (`render_draft()` / `render_final()`, not `render(draft=True)`). The agent picks the right one by name instead of guessing the flag.
* Cap args, group into a typed param object: wide argument lists are where agents transpose and guess; limit positional args to 3; beyond that, group into a typed object (dataclass, TypedDict, Pydantic model). The call site becomes self-documenting.
* Pure core, imperative shell: push side effects to the edges; keep the middle pure. Pure functions are the maximally agent-safe unit — same input, same output, no hidden state to track, trivially testable, locally verifiable without reading anything else.

# Enforcement

* Put line count, nesting depth, cyclomatic complexity, and arg count caps in the linter. Line count is only a proxy — the real enemy is branching state the agent must hold, which complexity and nesting depth measure directly.
* In the lint loop, these caps become feedback the agent meets automatically rather than prose it skims and ignores. A linter violation is a signal; a style guide paragraph is noise.
* Suggested baselines: 30 lines per function, nesting depth 3, cyclomatic complexity 10, 3 positional args before requiring a typed object. Adjust per codebase but always enforce via tooling, not convention.

# Checklist

* Cap function bodies at 20-30 lines; if you exceed this, extract until you don't, converting extracted blocks into functions named by what they do.
* Apply the honest-name test before committing: if the function name needs "and," "or," or "then," split the function at the conjunction.
* Keep every statement in the function at the same level of abstraction; mixing orchestration with low-level mechanics is the most common sign that extraction is overdue.
* Turn every explanatory comment above a block of code into an extracted function whose name is the comment — converting prose into a checked, visible contract.
* Split every non-trivial public function into an orchestrating public method that reads like a table of contents and private leaf methods that each do one thing.
* Separate commands from queries: a function that returns a value must have no side effects; a function that changes state must return nothing or at most a success/error signal.
* Replace every boolean flag argument that switches between two behaviors with two explicitly named functions.
* Limit positional arguments to 3; beyond that, group into a named typed object so call sites are self-documenting and argument transposition is a type error.
* Push all side effects to the outermost layer; keep the core logic pure so any agent can verify it locally without reading anything else.
* Configure your linter with explicit caps for cyclomatic complexity, nesting depth, function line count, and argument count; treat violations as loop feedback signals, not discretionary style notes.
```
