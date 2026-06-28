# Design Doc: Agentic Engineering — Python Semantics Principle

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

This change adds a fifth principle to the `agentic_engineering` prompt family: **Python Semantics for Agent-Authored Code**. The principle teaches a model to treat Python's full semantic surface — the static type system, the data model (dunders), descriptors, the runtime contract/assertion layer, and framework introspection — as the interface an AI coding agent perceives and is steered by, rather than as optional ceremony. It reframes each language capability by the agent-facing *channel* it fills, organizes them by *when they intervene* (STEER at authoring time, ENFORCE at runtime, WIRE through self-describing declarations frameworks act on), and teaches the agent to fill the strongest available channel — but only when it is semantically true. The deliverable is a new deep-dive prompt file plus the five wiring edits required to register it in the catalog, exactly as the meta-skill `vidbyte/prompts/skills/agentic-engineering.md` prescribes.

---

## 2. Goals & Non-Goals

### Goals
- Add a new principle file `vidbyte/prompts/prompts/agentic_engineering/python_semantics.md` that inherits the exact structure and tone of the existing principle files (`error_messages.md`, `file_headers.md`, `folder_readme.md`, `function_design.md`).
- Register the principle through every required integration point so the catalog loader discovers it and the direct import `agentic_engineering_python_semantics` resolves to non-empty text.
- Encode the two load-bearing premises: (1) these capabilities were skippable when humans wrote business logic but become load-bearing once agents author and re-read code on every cycle; (2) agent-authored code converges to one canonical, self-describing style, so the style should be specified deliberately.
- Organize the content along the STEER / ENFORCE / WIRE intervention-point spine, covering the type system (Ch.1), the data model / dunders + descriptors (Ch.4), the runtime contract/assertion layer (Ch.5), framework introspection (Ch.8), and the cross-cutting stdlib toolkit.
- Enforce the honesty discipline throughout: fill the strongest channel available, but only when the capability is semantically true; a meaningless dunder or a lying type is worse than its honest absence.
- Cross-reference the existing `error_messages` and `function_design` principles where the new principle's territory abuts theirs, instead of re-deriving their content.

### Non-Goals
- Not adding any executable SDK code, runtime behavior, tests, or schema. This is a prompt-asset-only change (the chosen workflow is design-doc-no-tests).
- Not modifying the catalog loader (`catalog.py`). The loader handles all families uniformly; a malformed principle surfaces as a load error, never a loader edit.
- Not rewriting the existing four principle files. The only edits to existing principles are the additive registration touchpoints (descriptor, enum, system prompt, README).
- Not making this principle language-agnostic. It is explicitly and deliberately scoped to Python; a one-line cross-language note is the only nod to other languages.
- Not splitting the content into multiple principles. The user asked for a single skill file; the chapters become named sub-sections within one principle, not separate catalog entries.
- Not duplicating the error-message field anatomy. Ch.5's "errors-as-data" overlaps the `error_messages` principle and will cross-reference it rather than restate it.

---

## 3. Background & Context

The `agentic_engineering` family is a set of prompt assets teaching a model to write source code that treats downstream AI agents as a primary audience. It currently ships four principles plus a system prompt that routes a model to the right principle for a task. A meta-skill (`vidbyte/prompts/skills/agentic-engineering.md`) documents the exact, mandatory procedure for adding a new principle.

This principle is being built now because the prior conversation converged on a specific, non-obvious thesis worth encoding: a large amount of Python's semantic machinery (`NewType`, precise type annotations, real `__repr__`/`__eq__`, tagged unions with `assert_never`, `Protocol`, structured exceptions, descriptors, `__init_subclass__`, decorators) was historically optional ceremony for application developers because a human held the model in their head and could read the implementation to recover any missing context. Agents flip that cost/benefit: an agent perceives code only through narrow channels (the signature, the type-checker verdict, the `repr` in a traceback, the fields on an exception, the decorator markers a framework reads), and that machinery is now machine-read on every edit/run cycle. The principle systematizes the exploitation of that flipped cost/benefit.

The relevant constraints come from the meta-skill's own criteria and conventions:
- A principle must reduce context-window cost for an agent, be concrete enough for a checklist, have enough depth for its own file, **not overlap** an existing principle, and be **language-agnostic or explicitly scoped**.
- Principle files use `# Header` sections with `*` bullets, no XML tags, no emoji, no YAML, no markdown callouts.
- The catalog loader validates that every `Prompt` enum member has backing asset text (`catalog.py` builds `missing_assets` and raises `ConfigurationError` if any enum value lacks an asset). Therefore the `.md` file, the JSON descriptor entry, and the enum member must all land together or the entire SDK fails to import.
- Direct import names are generated as `prompt_id.replace(".", "_")`, so the enum value `agentic_engineering.python_semantics` yields the import `agentic_engineering_python_semantics`.

Two observed drift points in the existing material, surfaced during the audit, are handled in Section 12:
- The meta-skill's identity text says the family "currently has two principles" — stale; there are four.
- The meta-skill procedure references adding a `*` item to a `# Checklist` section in `system_prompt.md`, but the current `system_prompt.md` has no `# Checklist` section. It enumerates principles as numbered entries under `# Principles`.

---

## 4. Requirements

### Functional Requirements
1. A new file `vidbyte/prompts/prompts/agentic_engineering/python_semantics.md` exists and opens with `# Description` (6–8 sentences), following the established principle-file structure.
2. The file contains, at minimum, these named sub-sections: the STEER/ENFORCE/WIRE intervention-point model; an authoring-time type-system section (Ch.1); a data-model/dunders+descriptors section (Ch.4) including the tiered "implement by meaning" discipline; a runtime contract/assertion section (Ch.5); a framework-introspection/decorators section (Ch.8); a cross-cutting stdlib toolkit section; a `# Things Not to Do` section; a `# Checklist` of 8–12 high-level process reminders; and a `# Code Examples` section with 3–4 weak→strict transformations.
3. `agentic_engineering.json` gains a `python_semantics` entry in its `prompts` object with `path: "python_semantics.md"` and the canonical GitHub `source_url`.
4. `vidbyte/lib/enums/prompts.py` gains `AGENTIC_ENGINEERING_PYTHON_SEMANTICS = "agentic_engineering.python_semantics"`, placed alphabetically among the `AGENTIC_ENGINEERING_*` members (after `FUNCTION_DESIGN`, before `SYSTEM_PROMPT`).
5. `system_prompt.md` gains a fifth numbered entry under `# Principles` with a summary paragraph, a `Use Cases:` line of 15–20 comma-separated triggering scenarios (5–10 words each), and a `GitHub:` link to the new file.
6. `vidbyte/prompts/README.md` is updated: the Agentic Engineering quick-reference row appends `python_semantics` to its Sub-prompts column, and the Agentic Engineering description paragraph is updated from "four core practices" to include the fifth.
7. The principle's content is explicitly Python-scoped and cross-references `error_messages` (for structured exceptions) and `function_design` (for callable shape) rather than duplicating them.
8. Integration verifies clean: `python -m compileall vidbyte` succeeds; the family-load check lists `python_semantics`; the direct import `agentic_engineering_python_semantics` resolves to non-empty text.

### Non-Functional Requirements
- **Performance:** N/A — prompt assets are loaded and cached once at catalog import; one additional Markdown file has negligible cost.
- **Consistency:** The new file must be indistinguishable in structure, heading style, and register from the existing four principle files. No XML tags, no emoji, no YAML, no markdown callouts.
- **Correctness of catalog state:** After the change, the `Prompt` enum, the JSON descriptor, and the on-disk `.md` files must be mutually consistent so the loader's `missing_assets` validation passes.
- **Observability:** N/A — no runtime telemetry. The verification commands in Section 6.6 stand in for observability.
- **Maintainability / staleness:** Content must be anchored to durable language semantics (the meaning of each capability), not to specific library version numbers, so the file does not rot as tooling versions move.

---

## 5. High-Level Design

The change follows the meta-skill's documented 8-step procedure verbatim, collapsed here into one new file plus four additive registration edits and a verification pass. There is no architectural novelty: the family is a flat catalog of Markdown principle files indexed by a JSON descriptor and a `str`-valued enum, discovered by a uniform loader. Adding a principle means adding one leaf and four index entries.

The intellectual core lives entirely inside `python_semantics.md`. Its spine is the three intervention points, ordered cheapest-feedback-first:

```
            AUTHORING TIME            RUNTIME (auto)              FRAMEWORK READS CODE
            ───────────────           ──────────────              ────────────────────
  STEER  →  type checker + IDE
            (pyright/mypy strict,
             annotations, NewType,
             Literal, sum types,
             Protocol, Final, ...)
                                  ENFORCE → dunders + descriptors
                                            (__repr__, __eq__, __hash__,
                                             __slots__, __init_subclass__,
                                             descriptor protocol, ...)
                                  ENFORCE → contracts + assertions
                                            (typed exception hierarchy,
                                             guard clauses, assert_never,
                                             raise-from, suppress, ...)
                                                                  WIRE → introspection + decorators
                                                                         (@decorator markers,
                                                                          singledispatch, get_type_hints,
                                                                          dataclasses.fields, DI/validation)
            ─────────────────────────────────────────────────────────────────────────
            CROSS-CUTTING TOOLKIT: dataclasses · functools · enum · contextlib · abc · typing
```

Each capability is presented as a *channel filler*: it states what agent-facing perception or enforcement channel the capability populates, and the rule is to prefer the earliest (cheapest) channel that applies. The data-model section carries the additional tiered discipline — `__repr__` always; value dunders for data; protocol/container/numeric dunders only when the type genuinely *is* that thing; machinery dunders deliberately — and the governing honesty rule that a meaningless channel-fill is worse than an honest absence because it is a guessable-wrong operation that actively misleads the agent.

Key design decisions:
- **One principle, chapters become sub-sections.** Keeps the family from bloating and matches the user's explicit "this skill file" framing. The breadth is handled by section depth, consistent with `error_messages.md` already being ~560 lines.
- **Explicitly Python-scoped.** This is the family's first single-language principle. The meta-skill criteria permit a scoped principle; the description and system-prompt entry will name the scope so a model does not misapply it to other languages.
- **Cross-reference, don't duplicate.** Where Ch.5 touches structured exceptions (the `error_messages` principle's territory) and where the type discussion touches callable shape (`function_design`'s territory), the file points at those principles instead of re-deriving them. This satisfies the "must not overlap" criterion.

---

## 6. Detailed Design

### 6.1 `python_semantics.md` (the principle deep-dive)

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/python_semantics.md`
**Type:** New file

#### What it does
Teaches a model the Python-semantics doctrine for agent-authored code. It is consumed by a model that has loaded the agentic-engineering system prompt and matched one of this principle's use cases.

#### Interface / API
This is a prompt asset, not code. Its "interface" is its section outline, which must match the family conventions:

```text
# Description            (6–8 sentences: the optional-ceremony→interface reframe; channels;
                          STEER/ENFORCE/WIRE; convergence; the honesty rule)
# Intent                 (why this matters: agents perceive through narrow channels; the cost/
                          benefit of these features flipped now that agents author and re-read)
# The Three Intervention Points   (STEER / ENFORCE / WIRE — the organizing spine, cheapest-first)
# Authoring-Time Steering: Type Checker and IDE   (Ch.1 — strict checker required or it degrades
                          to comments; annotations, NewType, Literal, sum types + match/assert_never,
                          Protocol, Final, overload, TypedDict, NamedTuple, Annotated, Self,
                          Generic/PEP 695, TypeAlias, ABC, if TYPE_CHECKING)
# Runtime Enforcement: The Data Model   (Ch.4 — the tier discipline: __repr__ always; value dunders
                          for data; protocol/container/numeric dunders only when the type IS that
                          thing; machinery deliberately; descriptors and __init_subclass__)
# Runtime Enforcement: Contracts and Assertions   (Ch.5 — typed exception hierarchy as errors-as-data
                          [cross-ref error_messages], guard clauses, assert for invariants,
                          assert_never, raise-from, spec-carrying stubs, deprecation, suppress)
# Framework Wiring: Introspection and Decorators   (Ch.8 — decorators as framework-read markers,
                          singledispatch, get_type_hints/__annotations__, dataclasses.fields,
                          DI/validation libs, ABC.register)
# Cross-Cutting Toolkit  (dataclasses, functools, enum, contextlib, abc, typing — the cheapest way
                          to fill several channels at once)
# Things Not to Do       (meaningless dunders; Any/bare dict; lying types; silent except: pass;
                          assert for input validation; magic strings; non-exhaustive matches; ...)
# Checklist              (8–12 high-level process reminders — when to apply, what to verify)
# Code Examples          (3–4 weak→strict transformations demonstrating channel-filling)
```

#### Logic / Algorithm
The prose is authored, not computed, but it follows a fixed internal logic per capability so the file reads uniformly:
1. Name the capability and the agent-facing channel it fills.
2. State the intervention point (STEER / ENFORCE / WIRE) and therefore its priority.
3. State the semantic precondition — when the capability is *true* and must be used, and when using it would be a lie.
4. Where the territory abuts `error_messages` or `function_design`, cross-reference rather than restate.

#### Edge Cases & Error Handling
- If the file is empty or missing, the catalog loader raises `ConfigurationError` at import (the `missing_assets` check). Mitigation: land the file, the enum, and the descriptor together.
- If the file contains XML tags, emoji, YAML, or markdown callouts, it violates family conventions. Mitigation: adversarial re-read against `function_design.md` formatting before commit.
- If a sub-section silently re-derives the error-message field anatomy, it violates the no-overlap criterion. Mitigation: the Ch.5 section must link to `error_messages` for the field anatomy and confine itself to the Python *mechanism* (exception classes carrying data, `raise ... from`, `assert_never`).

### 6.2 `agentic_engineering.json` (catalog descriptor)

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** Modified

#### What it does
Registers `python_semantics` as a sub-prompt so the loader emits the enum-backed asset and direct import.

#### Interface / API
```json
"python_semantics": {
  "path": "python_semantics.md",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/python_semantics.md"
}
```

#### Logic / Algorithm
1. Add the entry to the `prompts` object (after `function_design`).
2. Leave `name`, `key`, and structure untouched.
3. Optionally extend the `description` string to mention the fifth practice (see Section 12, Open Question 2).

#### Edge Cases & Error Handling
- A `path` that does not resolve raises `ConfigurationError` during `_resolve_prompt_text`. Mitigation: filename must exactly match the new `.md`.
- Trailing-comma / JSON-syntax errors break the whole catalog. Mitigation: validate JSON after edit.

### 6.3 `vidbyte/lib/enums/prompts.py` (enum registration)

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### Interface / API
```python
AGENTIC_ENGINEERING_FUNCTION_DESIGN = "agentic_engineering.function_design"
AGENTIC_ENGINEERING_PYTHON_SEMANTICS = "agentic_engineering.python_semantics"  # new, inserted here
AGENTIC_ENGINEERING_SYSTEM_PROMPT = "agentic_engineering.system_prompt"
```

#### Logic / Algorithm
1. Insert the member alphabetically among the `AGENTIC_ENGINEERING_*` block (between `FUNCTION_DESIGN` and `SYSTEM_PROMPT`).
2. Value must be exactly `agentic_engineering.python_semantics` so the direct import becomes `agentic_engineering_python_semantics`.

#### Edge Cases & Error Handling
- Enum member with no matching descriptor entry → loader `missing_assets` error. Mitigation: land alongside 6.1 and 6.2.

### 6.4 `system_prompt.md` (principle index entry)

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** Modified

#### What it does
Makes the principle visible to a model that loads only the system prompt, with use cases that let it decide when to load the deep-dive.

#### Interface / API
A fifth numbered block appended to `# Principles`:
```text
5. Python Semantics for Agent-Authored Code
   [Summary paragraph — 3–5 sentences: capabilities once optional become the agent's interface;
    STEER/ENFORCE/WIRE; fill the strongest channel, but only when semantically true. Scoped to Python.]

   Use Cases: writing a new Python module, choosing a precise type for a parameter, branding a domain id
   with NewType, modeling correlated flags as a tagged union, adding assert_never to a match, writing
   __repr__/__eq__ for a data class, choosing __slots__ for a dataclass, designing a Protocol for a port,
   parsing a boundary dict into a typed model, building a typed exception hierarchy, replacing except:
   pass with contextlib.suppress, registering a plugin via __init_subclass__, adding a framework decorator
   marker, introspecting annotations for DI, choosing dataclass over a hand-written class, exhaustively
   handling an enum, closing an extension point with Final, ... (15–20 items total)

   GitHub: https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/python_semantics.md
```

#### Logic / Algorithm
1. Append the numbered entry after principle 4 (function design).
2. Optionally update the `# Goal` section if the family scope statement should enumerate the new principle (it currently does not enumerate principles, so likely no change — see Section 12).
3. Do **not** invent a `# Checklist` section; the current file has none (see Section 12, Open Question 3).

#### Edge Cases & Error Handling
- `Use Cases:` count below ~15 weakens routing. Mitigation: author 15–20 concrete triggers.

### 6.5 `vidbyte/prompts/README.md` (human/machine index)

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### Interface / API
- Quick-reference table, Agentic Engineering row, Sub-prompts column: append `, python_semantics`.
- Descriptions section, "Agentic Engineering" paragraph: change "four core practices" to "five core practices" and add a clause describing the Python semantics practice.

#### Edge Cases & Error Handling
- The `/vidbyte-prompts` skill resolves names against this table; an inconsistent row degrades that skill. Mitigation: match the existing row format exactly.

### 6.6 Verification (no new files)

After all edits, run from `vidbyte-sdk/`:
```bash
python -m compileall vidbyte
python -c "from vidbyte.prompts import Prompts; p = Prompts(); print(sorted(p.family('agentic_engineering').keys()))"
python -c "from vidbyte.prompts import agentic_engineering_python_semantics as t; print(len(t))"
```
Expected: compile clean; the family key list includes `python_semantics`; the direct import length is large and non-zero.

---

## 7. Data Model Changes

N/A — no database, schema, or persisted data. The only "data" is the static `Prompt` enum and the JSON descriptor, both covered in Section 6.

---

## 8. API Changes

N/A — no HTTP/RPC API surface changes. The catalog gains one new prompt key (`Prompt.AGENTIC_ENGINEERING_PYTHON_SEMANTICS`) and one generated direct import (`agentic_engineering_python_semantics`), which are additive and covered in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/python_semantics.md` | The new principle deep-dive |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Register `python_semantics` sub-prompt (and optional description update) |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `AGENTIC_ENGINEERING_PYTHON_SEMANTICS` enum member |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add principle #5 entry with Use Cases and GitHub link |
| MODIFY | `vidbyte/prompts/README.md` | Update quick-ref row and Agentic Engineering description |
| CREATE | `docs/design/agentic-engineering-python-semantics.md` | This design doc (committed first on the branch) |

Net: 2 created, 4 modified, 0 deleted. `catalog.py` is explicitly untouched.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `typing` / language features referenced in prose | 3.10+ (PEP 604 unions, `match`); 3.11 (`assert_never`, `Self`); 3.12 (PEP 695, `@override`); 3.13 (PEP 702 `warnings.deprecated`) | The principle's content references these as the recommended vocabulary | Low — referenced descriptively in a prompt, not imported; `typing_extensions` noted as the backport path for older runtimes |
| Catalog loader `catalog.py` | in-repo | Discovers and validates the new principle | Low — uniform loader; correct enum+descriptor+file makes it pass |
| `gh` CLI | latest | Open the PR in Phase 6 | Low |

No new package dependencies are added to the SDK.

---

## 11. Rollout & Deployment

- **Feature flags:** None. Prompt assets are always available once shipped.
- **Breaking change:** No. The change is purely additive — a new enum member, descriptor entry, file, and two doc edits. Existing prompt keys and imports are unchanged.
- **Deployment order:** Single PR; the `.md`, JSON, and enum must be in the same commit/PR so the catalog never imports in a half-registered state.
- **Rollback:** Revert the PR. Because the change is additive and self-contained, revert fully removes the principle with no migration.

---

## 12. Open Questions

- [ ] **Key/name.** Default is `python_semantics` (enum `AGENTIC_ENGINEERING_PYTHON_SEMANTICS`, import `agentic_engineering_python_semantics`). Alternatives considered: `agent_native_python`, `python_channels`, `language_semantics`. Confirm `python_semantics`.
- [ ] **JSON descriptor `description` update.** The meta-skill says the descriptor's `name`/`description`/`key` are "stable," but the `description` enumerates the practices and the README description must change to five anyway. Recommendation: make a minimal additive edit to the JSON `description` so it stays in sync with the README. Confirm whether to edit it or leave it strictly per the "stable" rule.
- [ ] **`system_prompt.md` `# Checklist`.** The meta-skill procedure says to add a `*` item to a `# Checklist` section, but the current `system_prompt.md` has none (it uses numbered `# Principles` entries). Recommendation: add only the numbered principle entry and do not invent a new section. Confirm.
- [ ] **`# Goal` enumeration.** The current `# Goal` does not list principles by name, so adding a fifth likely needs no Goal edit. Confirm leaving `# Goal` unchanged.
- [ ] **Scope.** This is the family's first explicitly single-language (Python-only) principle. Confirm that explicit Python scoping (with a one-line cross-language note) is acceptable rather than generalizing.
- [ ] **Out-of-scope drift fix.** The meta-skill identity text says the family "currently has two principles" (now four/five). Should this PR also fix that stale sentence in `vidbyte/prompts/skills/agentic-engineering.md`, or leave it for a separate change? Recommendation: leave out of this PR to keep the diff focused; note as a follow-up.

---

## 13. Alternatives Considered

### Alternative 1: Split into multiple principles (e.g., `type_strictness` + `python_data_model` + `runtime_contracts`)
- What: Make each chapter its own catalog entry.
- Why rejected: The user explicitly asked for a single skill file, and the chapters are far more useful together (the STEER/ENFORCE/WIRE spine is the point). Splitting would bloat the family and fracture the unifying thesis.

### Alternative 2: Make the principle language-agnostic with Python examples
- What: Frame it as "type/semantic strictness" generally, with Python as one instantiation.
- Why rejected: The doctrine is built on Python-specific machinery (dunders, descriptors, `__init_subclass__`, `Protocol`, `assert_never`). Generalizing would dilute it into vague advice and lose the concrete, checklist-able specificity the criteria require. Explicit scoping is permitted and is the stronger choice.

### Alternative 3: Fold the type-system half into the existing `function_design` principle
- What: Extend `function_design.md` with strict-typing guidance instead of a new principle.
- Why rejected: `function_design` owns callable *shape and size*; this principle owns the *information content and enforceability of the semantic surface* (types, data model, contracts, wiring). They are distinct, and the new material is far too large to live as a sub-item. Cross-referencing keeps each principle focused.

### Alternative 4: Add the principle but skip the README/system-prompt updates
- What: Ship only the `.md`, JSON, and enum.
- Why rejected: A principle invisible in the system prompt is never routed to, and an unlisted README row breaks the `/vidbyte-prompts` skill's name resolution. The meta-skill marks every integration step mandatory.

---

END OF DESIGN DOC
