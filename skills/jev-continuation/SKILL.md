---
name: jev-continuation
description: Step-by-step guide to adding a continuation done check (a preset continuation setting enabled through JevContinualSettings.checks) to JevAgent. Covers the run-state and handoff section subclasses, the Jev question and its structure, batching every check into one Jev request, what the main agent receives when a check fails, the important files, and the invariants the tests enforce. Use it before adding or changing any JevDoneCheck, done question, run-state or handoff section, or JevContinuation.
---

# Adding a JevAgent continuation done check

Use this skill before you add a new continuation setting to `JevAgent`, or change how an existing one works. In code, a continuation setting is a **done check**. It is a `JevDoneCheck` member that a user enables through `JevRuntimeSettings(continual=JevContinualSettings(checks=(...)))`. The check runs every time the main agent tries to finish. When it fails, the main agent goes back to work in the same loop. `JevDoneCheck.MULTI_PART` is the first done check (PR #470, finished in #471). Every file and method named below exists on `main` and is the model to copy.

Load these first:

- `AGENTS.md`: read its **Placement Rules** and **JEV File Locations** sections. They are binding, and a workflow moves misplaced code on every PR.
- `skills/asking-jev-questions/SKILL.md`: load it before you write or review any Jev question. Its "Writing a full question" section is the layout every done question follows.
- `skills/jev-agent/SKILL.md`: the product contract for `JevAgent` as a whole.

This skill assumes that you want a new **kind of done check** under the existing `JevDoneContinuation`. If the reason to continue a run is not "a Jev question about the finished work said no", read [When to write a new JevContinuation instead](#when-to-write-a-new-jevcontinuation-instead) first.

---

## 1. The overall flow

```
JevAgent.__init__
  ├─ JevRunState(settings, runtime_settings, response)      # only when continual.checks is non-empty
  │    └─ JevHandoff(settings, continual)
  └─ JevDoneContinuation(run_state, continual, response)

JevRuntime.arun(message)
  ├─ JevPreflightGate.pass_(message)                        # preflight; unrelated to done checks
  ├─ run_state.begin(message)                               # (A) write the run state ONCE, before the main loop
  └─ inherited linear loop …
       └─ at every finish attempt → JevRuntime._continue_finish_attempt
            ├─ continuation.should_continue(final_answer, responses, calls)
            │    └─ run_state.check(...)                      # (B) every finish attempt
            │         ├─ JevHandoff.window(...)               #     main agent's context window as ContextManager
            │         ├─ handoff_writer.compile(...)          #     (C) evidence for every enabled check
            │         ├─ _ask → combine(handoff)              #     (D) ONE Jev request, every check's questions
            │         └─ _judge(check, …) per check           #     (E) JevDoneResult per check → response.done()
            └─ if True: continuation.continue_(messages)      # (F) append one user message to the SAME loop
```

The five stages, and who does the work in each:

| Stage | Who | Kind of work | Output |
|---|---|---|---|
| (A) Run state | `JevRunState`, a generative `BaseAgent` with no tools | Generation. For checks whose items are knowable before work, it reads the user's request and lists what the check will verify. | `JevRunStateRecord`, plus `rendered` JSON |
| (C) Handoff | `JevHandoff`, a generative `BaseAgent` with no tools | Generation. It reads the main agent's run, compiles evidence for request-derived items, and extracts final-answer claims when items only exist after work. | `JevHandoffRecord`, plus `rendered` JSON |
| (D) Jev | `DecisionModelRunner` (TypeSafe) | Recognition only. It answers one yes/no question per item. | `DecisionModelResponse` |
| (E) Judge | `JevRunState._judge` (code) | Scoring. `score_noul` applies a threshold and a veto, then lists the incomplete items. | `JevDoneResult` |
| (F) Continue | `JevDoneContinuation` (code and a prompt asset) | Formatting. It builds one message for the main agent. | a `{"role": "user"}` message |

The core split, which comes from `asking-jev-questions` strategy 16: **generative agents write the state and the evidence, and Jev only recognizes whether the evidence shows each item.** Never ask Jev to list, count, or produce anything.

Every stage fails open. With no run state there is no check. When the handoff or Jev is unavailable, the check is marked `available=False` and the answer stands. A done check is advisory. It must never block or crash the main agent's answer.

---

## 2. Important files

| File | What it holds | What a new check does there |
|---|---|---|
| `vidbyte/lib/enums/jev.py` | `JevDoneCheck`, `JevDoneQuestionKey` | Add one member to each. |
| `vidbyte/lib/dataclasses/jev.py` | Section payloads (`JevSectionPayload` subclasses), records, `JevRunStateRecord`, `JevHandoffRecord`, `JevDoneQuestion`, `JevDoneResult` | Add payloads and frozen records where items come from; a post-run-derived check adds its section and optional field to `JevHandoffRecord`, not `JevRunStateRecord`. |
| `vidbyte/lib/constants/jev.py` | `JEV_<CHECK>_THRESHOLD`, shared-state field names (`JEV_DONE_*_FIELD`), limits | Add the threshold and any new state field names. |
| `vidbyte/lib/jev/done/<check>.py` | One `JevDoneQuestion` subclass per question | **New file**, one per check (`multi_part.py` is the model). |
| `vidbyte/lib/jev/done/done.py` | `JevDoneRegistry` (`_questions`, `_thresholds`, `validate`) | Register the question and the threshold. |
| `vidbyte/lib/jev/done/__init__.py`, `README.md` | Exports and a folder guide | Export the question and list it in the README. |
| `vidbyte/agents/jev/done/run_state.py` | `JevRunState`: `_SECTIONS`, `schema`, `begin`, `check`, `combine`, `_section`, `_judge`, `_record` | Request-derived checks add a run-state `_SECTIONS` entry and `_record` conversion; every check adds `_section` and `_judge` cases, and post-run items come from the handoff. |
| `vidbyte/agents/jev/done/handoff.py` | `JevHandoff`: `_SECTIONS`, `schema`, `window`, `compile`, `_record` | Add the handoff section and conversion; require exact run-state id matching only when the check's items were written before work. |
| `vidbyte/agents/jev/continuation/done.py` | `JevDoneContinuation`: `should_continue`, `continue_`, `message`, `_explain` | One `case` in `_explain`. |
| `vidbyte/agents/jev/continuation/base.py` | `JevContinuation` ABC | Nothing, unless you are writing a new continuation kind. |
| `vidbyte/agents/jev/settings.py` | `JevContinualSettings` (`checks`, `max_continuations`, limits) | Usually nothing, because `checks` already accepts every registered member. |
| `vidbyte/agents/jev/runtime.py`, `agent.py` | Wiring | **Nothing.** A check never touches the runtime. |
| `vidbyte/agents/jev/response.py` | `JevResponse` (`run_state`, `handoff`, `done`, `continued`) | Nothing. `done` is keyed by check. |
| `vidbyte/prompts/prompts/jev_run_state/`, `jev_handoff/` | General system prompts | **Nothing.** They must stay check-agnostic, and a test enforces this. |
| `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md` | The continuation message template | Usually nothing. `_explain` fills `{failed}` and `{focus}`. |
| `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/jev/__init__.py` | Public exports | Export new records a user reads on `JevAgent.response`, as `JevDeliverable` is exported. |
| `tests/test_jev_done.py`, `scripts/test-jev-multipart-done-criteria.py` | Tests and the focused runner | Extend the test classes, and keep the script's loader exhaustive. |

### When to create a new file and when to extend one

Create a **new file** only for:

- **The check's question module**, `vidbyte/lib/jev/done/<check>.py`. One module per check holds that check's `JevDoneQuestion` subclasses, and any brief text it shares is a module-level constant, like `DONE_STATE`.
- **A new continuation kind**, `vidbyte/agents/jev/continuation/<kind>.py`. Create this only when the trigger is not a done check (see the last section).
- **A new prompt family**, `vidbyte/prompts/prompts/<family>/` with its key in `vidbyte/lib/enums/prompts.py`. Create this only for a new generative agent or a new continuation message, never for a new done check.

**Extend** existing modules for everything else:

- Enums go in `vidbyte/lib/enums/jev.py`, records and payloads in `vidbyte/lib/dataclasses/jev.py`, and constants in `vidbyte/lib/constants/jev.py`.
- The logic goes into `JevRunState`, `JevHandoff`, and `JevDoneContinuation` as `match` cases and map entries.

**Never** create any of these:

- a `JevRunState` or `JevHandoff` subclass for your check;
- a `types.py`, `enums.py`, `constants.py`, `records.py`, `models.py`, or `schemas.py` under `vidbyte/agents/jev/` or `vidbyte/lib/jev/`;
- a branch in `JevRuntime`.

The reviews on #470 rejected "one class per shape". The design is one general agent whose output schema grows by one section per enabled check.

---

## 3. The checklist

Work through the steps in order. Each is explained in detail below.

- [ ] 1. Design the check in product terms: its items, its evidence, its question, and the action for every outcome.
- [ ] 2. Add the `JevDoneCheck` member and its `JevDoneQuestionKey`.
- [ ] 3. Write a run-state section payload when the check's items are knowable from the request before work; post-run-derived items such as CLAIMS omit it.
- [ ] 4. Write the handoff evidence section payload (a `JevSectionPayload` subclass).
- [ ] 5. Add frozen records and optional fields only to the top-level records that carry the check's payloads.
- [ ] 6. Add the constants: the threshold, and the state field names.
- [ ] 7. Write the Jev question in `vidbyte/lib/jev/done/<check>.py`, following the asking-jev-questions layout.
- [ ] 8. Register the question and threshold in `JevDoneRegistry`, and export it.
- [ ] 9. Add sections and conversions to the schemas and records that carry the check's items; the maps need not be identical for dynamic items.
- [ ] 10. Add the check's `case` to `JevRunState._section`: its part of the shared state and its batched questions.
- [ ] 11. Keep the shared state description (`DONE_STATE`) true for every combination of enabled checks.
- [ ] 12. Add the check's `case` to `JevRunState._judge`, with a `_<check>` scorer that fails open.
- [ ] 13. Add the check's `case` to `JevDoneContinuation._explain`: what the main agent reads when the check fails.
- [ ] 14. Leave the runtime, the agent, the settings, and the system prompts alone, and confirm that you did.
- [ ] 15. Export public records, extend the tests, and update the docs and skills.
- [ ] 16. Run the verification commands.

### Step 1: Design the check before writing code

Write down five things. If you cannot write one of them, the check is not ready.

1. **The failure it catches**, in product terms. For multi-part, the failure is that the agent finished one visible part of a request and forgot another part it was asked for in passing.
2. **The items.** A done check judges a list of items, each with a stable id, with **one question per item** (strategy 11). Multi-part's items are deliverables. The run-state writer produces the items from the request before any work starts, because producing candidates is generation.
3. **The evidence per item.** Decide what the handoff must quote from the run so that a checker who sees only that text can judge the item. The handoff also writes a separate, human-readable `missing` for each item.
4. **The question.** One positive yes/no question per item, in the form "Does `evidence` show …, in the entry of `<items>` with id `{item}`?". It must pass the two-second test in `asking-jev-questions`.
5. **The action for every outcome** (strategy 25):
   - Pass means no continuation.
   - Fail means continue with a focus on the incomplete items.
   - Unavailable means fail open.
   - Nothing to check means the check passes with no Jev question. Multi-part does this when a request asks for no deliverables.

   Also decide the threshold. The veto is the same value, so one clear no is never averaged away.

A check that judges the run as a whole still fits this model: it has one item with a fixed id. `str.format(item=...)` ignores a placeholder the question does not use. Prefer real items when they exist.

### Dynamic items: CLAIMS

The `CLAIMS` check is the exception to the usual pre-run item list. Its items are the concrete, checkable factual assertions in the main agent's final answer, so they cannot be truthfully written from the user's request before work begins. Do not add a claims list to `JevRunStateRecord` or ask the run-state writer to predict what the main agent will say. Instead, `JevHandoff` extracts each assertion at a finish attempt, splits separate facts into separate entries, and pairs every entry with relevant `ToolCallContextItem` evidence or an explicit statement that no supporting call exists.

`JevHandoff._record` validates that generated claim ids are well-formed and unique within this answer; it cannot compare them with a pre-run id list. `JevRunState._section(CLAIMS)` places each claim and its evidence in the shared Jev state, omits the handoff's `missing` judgment, and asks one question per claim in the same batched request as other enabled checks. An empty claim list passes without a Jev call. When Jev marks claims incomplete, `JevDoneContinuation._explain` focuses only those claims and their evidence gaps, so the main agent can complete requested work with evidence or correct its final answer.

### Step 2: The enum member and question key (`vidbyte/lib/enums/jev.py`)

```python
class JevDoneCheck(str, Enum):
    MULTI_PART = "multi_part"
    <CHECK> = "<check>"            # the value is the section field name in both schemas

class JevDoneQuestionKey(str, Enum):
    MULTI_PART_DELIVERED = "multi_part.delivered"
    <CHECK>_<PROPERTY> = "<check>.<property>"   # prefixed by the check; the Jev answer name is "<key>.<item_id>"
```

- The member's **value** becomes the field name of the section in the schema that carries the check's items (`check.value` in `schema()`). Request-derived checks use both schemas; CLAIMS uses the handoff schema because its items are created from the final answer.
- `JevDoneCheck` is already exported from `vidbyte/lib/enums/__init__.py` and `vidbyte`, so users can enable the check the moment it is registered.
- Schema tests assert that each check is registered in the schema that carries its items. The run-state and handoff maps intentionally differ for CLAIMS.

### Step 3: The run-state section subclass (`vidbyte/lib/dataclasses/jev.py`)

The run state is **one** general schema: the central `JevRunStatePayload` (`goal`, `objective`, `mission`, `what_not_to_do`) plus one field for each enabled check whose items are known from the request before work. `JevRunState.schema()` builds it with `pydantic.create_model`. Such a check contributes a **`JevSectionPayload` subclass**; a check whose candidates are created from the final answer, like CLAIMS, does not add a predicted section:

```python
class <Check>ItemPayload(BaseModel):
    """One <item> the request asks for, as JevRunState writes it in the <check> section."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="<4–6 sentences>")
    ...: str = Field(min_length=1, description="<4–6 sentences>")

class <Check>Payload(JevSectionPayload):
    """The <check> section of the run state: …"""
    model_config = ConfigDict(extra="forbid")
    SECTION: ClassVar[str] = "<4–6 sentences: why the section exists, what it records, that it is filled from the request alone before work starts>"
    items: list[<Check>ItemPayload] = Field(description="<4–6 sentences, including when to return an empty list>")
```

What goes here:

- **Only schema and field descriptions.** The field descriptions *are* the run-state writer's instructions for your check. The system prompt is general and tells the model to follow each field's description. Write them as instructions to a generative model: what to write, in whose words, what not to add, and what to do when the request is silent.
- **The defining material Jev will need.** Multi-part writes a `description` and a `completion_signal` for each deliverable, because Jev can only judge against a reference it is given (T13). If the question needs a "done when" condition, the run state writes it now, before any work, so the main agent's own run cannot shape it.
- **Ids** that match `JEV_DELIVERABLE_ID_PATTERN` (lowercase, starting with a letter, at most 64 characters). They must be unique, name the subject rather than a number, and are never changed afterwards. Reuse the pattern and `JevDeliverableId`, and do not invent a second id scheme.

What does **not** go here:

- Parsing, conversion, `from_payload`, or `to_payload` code. A test forbids these on the records, and conversion lives in `JevRunState._record`.
- Anything the main agent's work could change. The run state is written once, from the request only.
- Any change to `JevRunStatePayload` itself. The central fields belong to every check.

Rules enforced by tests and lint:

- Every field description is **4–6 sentences**, and so is `SECTION` (`test_every_structured_output_field_has_a_four_to_six_sentence_description`; add your models to that test's tuple). Lint S025 also checks model-facing description depth.
- `extra="forbid"` on every payload (lint S058).

### Step 4: The handoff evidence section subclass (`vidbyte/lib/dataclasses/jev.py`)

The handoff is also **one** general schema, `JevHandoffPayload` plus one field per enabled check. A request-derived check contributes a second `JevSectionPayload` subclass that mirrors its run-state section item for item; a post-run-derived check defines its items here instead:

```python
class <Check>ItemEvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=JEV_DELIVERABLE_ID_PATTERN, description="<echo the run-state id exactly; one entry per item; same order>")
    evidence: str = Field(min_length=1, description="<quote the run; name sources; include failures; never a verdict>")
    missing: str = Field(min_length=1, description="<what the run does not show, written for the main agent>")

class <Check>EvidencePayload(JevSectionPayload):
    model_config = ConfigDict(extra="forbid")
    SECTION: ClassVar[str] = "<4–6 sentences: a separate checker sees only this; report observations, never a verdict; filled after the finish attempt>"
    items: list[<Check>ItemEvidencePayload] = Field(description="<one entry per run-state item, same ids and order, never omit one>")
```

What goes here:

- **`evidence`**: observations the checker judges. The handoff writer quotes or closely reproduces the relevant responses, tool calls with their arguments and outputs, command and test results, and passages of the final answer. It names where each came from, reports failed attempts, and never states that the item is complete.
- **`missing`**: the handoff writer's own summary of what is not shown, written for the main agent. This is **judgment, not evidence**, so it goes to the main agent in the continuation message and **never into the Jev state** (see step 10).

Split evidence from judgment this way even when the check seems simple. Without `missing`, the continuation cannot tell the main agent exactly what to do. And if `missing` leaked into the state, Jev would be judging the handoff writer's opinion instead of the run.

### Step 5: The records (`vidbyte/lib/dataclasses/jev.py`)

Payloads are pydantic models for the model's structured output. Records are **frozen, slotted dataclasses** that the rest of the code reads:

```python
@dataclass(frozen=True, slots=True)
class <Check>Item: ...          # like JevDeliverable: __post_init__ validates id (JevDeliverableId.require) and text (JevText.require)

@dataclass(frozen=True, slots=True)
class <Check>: ...              # like JevMultiPart: tuple of items, require_unique ids, ids() helper

@dataclass(frozen=True, slots=True)
class <Check>ItemEvidence: ...  # like JevDeliverableEvidence

@dataclass(frozen=True, slots=True)
class <Check>Evidence: ...      # like JevMultiPartEvidence
```

Then add one optional field to each top-level record, and validate its type in `__post_init__`:

```python
class JevRunStateRecord:
    ...
    multi_part: JevMultiPart | None = None
    <check>: <Check> | None = None           # set only when the check is enabled

class JevHandoffRecord:
    multi_part: JevMultiPartEvidence | None = None
    <check>: <Check>Evidence | None = None
```

- Validation of the record itself (ids, non-blank text, tuple types) lives in `__post_init__`. Behavior that acts on the record does not live here.
- Use tuples, never lists, so a recorded result cannot be edited.
- Every record and enum lives in `vidbyte/lib/`. `test_records_and_enums_live_in_lib` checks this, and the AGENTS.md placement workflow moves anything misplaced.

### Step 6: The constants (`vidbyte/lib/constants/jev.py`)

- `JEV_<CHECK>_THRESHOLD: float`, with a comment explaining that the value is used as both the mean threshold and the veto, and that it is a starting point, not a tuned value (strategy 25).
- One `JEV_DONE_<NAME>_FIELD: str` for every **new** key your check puts into the shared Jev state. Reuse `JEV_DONE_REQUEST_FIELD` and `JEV_DONE_EVIDENCE_FIELD` where the meaning is identical. Add each name to `__all__`.
- A per-check calibration value stays a constant. Promote it to a `JevContinualSettings` field only when users need to tune it, and then validate it in `__post_init__` as the existing limits are.

### Step 7: Write the Jev question (`vidbyte/lib/jev/done/<check>.py`, new file)

**Load `skills/asking-jev-questions/SKILL.md` first.** Every done question is a `JevDoneQuestion` subclass that is constructible with no arguments, with a default for every field:

```python
@dataclass(frozen=True)
class <Check><Property>Question(JevDoneQuestion):
    """<the yes/no question in one line>"""

    key: JevDoneQuestionKey = JevDoneQuestionKey.<CHECK>_<PROPERTY>
    instructions: JevBrief = field(default_factory=lambda: JevBrief(
        introduction="<2–3 sentences: what this answers, what it leaves to other checks>",
        state=DONE_STATE,                       # the ONE shared description of the batched state (step 11)
        definitions=("<every term a rule uses, in dependency order, no examples>",),
        rules=("<special cases; zero/one/many; empty input side (T8); focus on the named id only; meaning not writing (T7); guard against state arguing for itself (T14)>",),
        question="Does `evidence` show <property>, in the entry of `<items field>` with id `{item}`?",
    ))
    when_true: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose true when …",  not_for="… belongs to false.",
        easy=("With `…` of …, `evidence` is: …",), boundary=("…",),
    ))
    when_false: JevCriterion = field(default_factory=lambda: JevCriterion(
        what="Choose false when …", not_for="… belongs to true.",
        easy=("…",), boundary=("…",),   # boundary is a minimal pair with when_true.boundary
    ))
    gap: str = "<self-contained sentence the MAIN AGENT reads when this question fails>"
```

The structure, and why each part exists:

- **`JevBrief`** has five sections in a fixed order: introduction, state, definitions, rules, question. `render()` turns the brief into Jev's instructions.
  - Every rule lives in `rules`, once.
  - The focus rule must say to judge **only the entry whose id the question names**, and never to use another entry's evidence. Batching many items into one state is exactly where T15 warns that accuracy drops, and this rule is the mitigation.
- **The question text holds `{item}`.** `JevDoneQuestion.to_question(item)` formats it, and names the question `f"{key.value}.{item}"` through `name(item)`. That is how one request holds a question per item, and how each answer comes back keyed to its item.
- **`JevCriterion`** gives each side the same template: `what` opens with the verdict, `not_for` mirrors the other side, and `easy` and `boundary` are labeled examples. The two `boundary` examples form a minimal pair that differs only in the tested property. Criteria add no rules and no "because" sentences. Use **one verb** everywhere; multi-part uses "shows".
- **`gap`** is not sent to Jev. It is the opening line the **main agent** reads for this check in the continuation message (step 13). It must stand on its own, because the main agent never sees the brief, and it must not claim more than a "no" supports.
- **At least 2,000 tokens** across the rendered instructions, both sides, and the gap (`test_question_carries_at_least_two_thousand_tokens`). The floor is for completeness, not padding.
- **Each section is one string literal.** Never split text into adjacent literals (lint S062 and `test_question_text_is_one_string_literal_each`).
- **Yes means satisfied.** `score_noul` averages P(yes) with no inversion, so phrase the question positively.

Run the "Checklist before you ship a question" in `asking-jev-questions` before moving on.

### Step 8: Register it (`vidbyte/lib/jev/done/done.py`, `__init__.py`, `README.md`)

```python
_questions = MappingProxyType({JevDoneCheck.MULTI_PART: MultiPartDeliveredQuestion(), JevDoneCheck.<CHECK>: <Check><Property>Question()})
_thresholds = MappingProxyType({JevDoneCheck.MULTI_PART: JEV_MULTI_PART_THRESHOLD, JevDoneCheck.<CHECK>: JEV_<CHECK>_THRESHOLD})
```

`JevDoneRegistry.validate` runs when `JevContinualSettings` is constructed. It rejects an unknown check, a repeated check, a bare string, and a check with no registered question or threshold. That is the only "settings" work a new check needs. Export the question class from `vidbyte/lib/jev/done/__init__.py`, and add a bullet for your module to `vidbyte/lib/jev/done/README.md`.

### Step 9: The `_SECTIONS` maps and `_record` conversions

`vidbyte/agents/jev/done/run_state.py`:

```python
_SECTIONS = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartPayload, JevDoneCheck.<CHECK>: <Check>Payload})
```

`vidbyte/agents/jev/done/handoff.py`:

```python
_SECTIONS = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload, JevDoneCheck.<CHECK>: <Check>EvidencePayload})
```

The run-state map contains only checks whose items are known before work; the handoff map contains every check. Each schema adds `check.value: (payload, Field(description=payload.SECTION))` for every enabled check it carries, so users never pay for disabled sections. For CLAIMS, add no run-state section.

Then extend each `_record`, the only place a validated pydantic reply becomes a frozen record:

- **`JevRunState._record`**: convert only a request-derived section into `JevRunStateRecord`. CLAIMS has no section or record here.
- **`JevHandoff._record`**: build the typed evidence record. For request-derived items, require ids to match the run state's ids exactly; a mismatch makes the handoff unavailable. For CLAIMS, validate ids and uniqueness within the generated final-answer list because no pre-run id list exists.

### Step 10: Your part of the batched request (`JevRunState._section`)

Every enabled check's questions go to Jev in **one** `JevDecisionRequest` per finish attempt (review of #470; strategies 11 and 24). `combine()` does the batching, and you only add a `case`:

```python
def _section(self, check, handoff):
    match check:
        case JevDoneCheck.MULTI_PART:
            ...
        case JevDoneCheck.<CHECK>:
            # <comment: what the entries hold and why; what is deliberately left out>
            state = None if self.record is None else self.record.<check>
            if state is None or handoff.<check> is None:
                return {}, ()                                        # nothing to ask → _judge handles it
            question = JevDoneRegistry.question(JevDoneCheck.<CHECK>)
            evidence = {item.id: item.evidence for item in handoff.<check>.items}   # evidence only, never `missing`
            entries = {item.id: {JEV_DONE_<A>_FIELD: item.<a>, JEV_DONE_EVIDENCE_FIELD: evidence[item.id]} for item in state.items}
            return {JEV_DONE_<ITEMS>_FIELD: entries}, tuple(question.to_question(identifier) for identifier in state.ids())
```

What `combine()` does with your return value:

```python
state = {JEV_DONE_REQUEST_FIELD: self.request}      # shared by every check
for check in self.checks:
    section, asked = self._section(check, handoff)
    state.update(section)                           # your top-level keys join the ONE shared state
    questions.extend(asked)                         # your per-item questions join the ONE request
return JevDecisionRequest(state=state, questions=tuple(questions))   # or None if no check asked anything
```

Rules for your `case`:

- **Return a mapping of top-level state keys and a tuple of `JevQuestion`s.** Never call Jev here, and never build your own `JevDecisionRequest`.
- **Key entries by item id**, so that a question naming `{item}` finds its entry.
- **Put the defining material next to the evidence** (T13): for request-derived items, the run state's "what" and "done when" fields; for CLAIMS, the exact final-answer `claim`; in both cases include the handoff's `evidence`. **Leave out `missing`**, which is the handoff writer's opinion.
- **Your top-level keys must not collide** with `request`, `deliverables`, or another check's keys, because `state.update` would silently overwrite them. Use a distinct `JEV_DONE_*_FIELD` name.
- **Return `({}, ())`** when you have nothing to ask, for example when there is no record, no evidence, or no items.
- Every other enabled check's questions ride in the same request. You get batching for free and never need a second Jev call.

### Step 11: Keep the shared state description true

`DONE_STATE` in `vidbyte/lib/jev/done/multi_part.py` is the shared `state` section of every done-question brief. It describes `request` and the optional `deliverables` and `claims` fields, each present only when its check is enabled. Keep this one description true for every combination of enabled checks, including a dynamic claims list emitted by the handoff.

Before you ship:

- Keep **one** shared description of the batched state that every done question's brief uses, so any two questions can be compared line by line ("Feedback on one question applies to every question" in `asking-jev-questions`). If you move it to a shared module, it stays in `vidbyte/lib/jev/done/`.
- Describe each field together with the condition under which it is present. For example: "`<items>` is present only when the <check> check is enabled…". Also state that each question judges only the fields and the entry it names. The description must be true for **every combination** of enabled checks.
- Add a test that enables both checks, asserts the batched state holds both checks' keys, and asserts that every question's name has its check's prefix.

### Step 12: Score it (`JevRunState._judge` and a `_<check>` method)

```python
def _judge(self, check, handoff, decision):
    match check:
        case JevDoneCheck.MULTI_PART:
            return self._multi_part(handoff, decision)
        case JevDoneCheck.<CHECK>:
            # <comment: the rule this check enforces and how answers are combined>
            return self._<check>(handoff, decision)
```

`_<check>` must return a `JevDoneResult` on **every** path. Copy the order of `_multi_part`, and comment each step:

1. There is no required run-state section, no handoff, or no handoff section: return `JevDoneResult(check=…, score=None, available=False)`. Dynamic checks such as CLAIMS require the handoff section but no run-state section. The check fails open, and `passed` stays True.
2. There are no items: return `JevDoneResult(check=…, score=None)`. Nothing was asked, so the check passes.
3. `decision is None`, because Jev failed or no credentials were set: `available=False`, fail open.
4. Pick out this check's answers from the **combined** reply: `{id: decision.answers[question.name(id)] for id in state.ids() if question.name(id) in decision.answers}`. The reply holds every check's answers, and the name prefix is what separates them.
5. Call `DecisionModelRunner.score_noul(answers, state.ids(), threshold, threshold)`, where the threshold is also the veto. `None` means an answer was missing: `available=False`.
6. `incomplete` is the ids whose P(yes) (`probabilities[JEV_NOUL_TRUE]`) is below the threshold. These are exactly what the continuation will name.
7. `usage = JevUsage.from_usage_payload(decision.usage or {})`. This is the usage of the one batched request, so every check reports the same usage. Never sum it across checks.
8. Return `JevDoneResult(check=…, score=verdict.score, passed=verdict.passed, answers=verdict.answers, incomplete=incomplete, usage=usage)`.

For CLAIMS, use `handoff.claims.ids()` as the item list in steps 2, 4, 5, and 6. The check passes when that list is empty, asks no question in that case, and returns unavailable if the handoff section or combined Jev answer is missing.

`check()` then records each result through `self.response.done(result)` and returns only the failed ones. You do not touch `check()`.

### Step 13: What the main agent receives (`JevDoneContinuation._explain`)

This is what happens **after** `should_continue` returns True.

`should_continue` returns True only when all three of these hold:

- at least one enabled check failed;
- `run_state.handoff is not None`, since there is no evidence to hand back without it;
- `response.state.continuations < max_continuations`.

`JevRuntime` then calls `continue_(messages)`, which does two things:

1. `self.response.continued()` increments `JevAgent.response.continuations`.
2. It appends **one** `{"role": "user", "content": self.message()}` to the **same** loop's `messages`. The main agent keeps its history, tools, and budgets and resumes work. It is never re-run from scratch.

`message()` fills the `jev_continuation/continue_prompt.md` asset (`Prompt.JEV_CONTINUATION_CONTINUE_PROMPT`). The asset carries fixed instructions: finish only what is missing, focus on the Focus list, make each part visible in the work, do not redo work, do not add work. After those instructions come five sections:

| Section | Filled from | Your check's contribution |
|---|---|---|
| `# Original request` | `run_state.request` | none |
| `# Run state` | `run_state.rendered`, the JSON of the whole run state including your section | automatic, via your payload |
| `# Handoff` | `run_state.handoff_writer.rendered`, the JSON of the whole handoff including your section and its `missing` text | automatic, via your payload |
| `# Failed checks` | `"\n\n".join(failed …)` over the `_explain` results | the **first** string you return |
| `# Focus` | `"\n".join(focus …)` over the `_explain` results | the **second** string you return |

Your `case` returns `(failed, focus)`, following the multi-part case:

```python
case JevDoneCheck.<CHECK>:
    # <comment: what the main agent reads for this check and why>
    question = JevDoneRegistry.question(JevDoneCheck.<CHECK>)
    state = None if self.run_state.record is None else self.run_state.record.<check>
    handoff = None if self.run_state.handoff is None else self.run_state.handoff.<check>
    items = {} if state is None else {item.id: item for item in state.items}
    missing = {} if handoff is None else {item.id: item.missing for item in handoff.items}
    failed = [question.gap]                                   # the self-contained gap sentence first
    focus = []
    for identifier in result.incomplete:
        yes = result.answers[identifier].probabilities[JEV_NOUL_TRUE]
        failed.append(f"- {question.instructions.question.format(item=identifier)} Jev's answer: no (P(yes) = {yes:.2f}). Still missing: {missing[identifier]}")
        focus.append(f"- {items[identifier].<what>} Done when: {items[identifier].<done_when>}")   # in the USER's terms
    return "\n".join(failed), "\n".join(focus)
```

- **Failed checks** tells the agent what was asked, what Jev answered, and what the handoff says is missing, for **incomplete items only**.
- **Focus** lists only incomplete items. Request-derived items use the pre-run state; CLAIMS uses the exact final-answer claims from the handoff and includes their evidence gaps. Items that passed never appear here. `test_incomplete_deliverable_sends_the_main_agent_back_in_the_same_loop` asserts this for multi-part.
- Only change `continue_prompt.md` when the instructions for **every** check need to change. Its placeholders are fixed: `{request}`, `{run_state}`, `{handoff}`, `{failed}`, `{focus}`.

On the next finish attempt the whole cycle repeats:

- `JevHandoff` clears its history and recompiles evidence from the now longer window.
- Every enabled check is asked again, and `JevAgent.response.done` holds the latest results.
- After `max_continuations`, the latest verdict stays on the response and the main agent's answer stands. With `max_continuations=0` the checks still run and report, but they never send the agent back.

### Step 14: What you leave alone

Confirm your diff does **not** touch any of these:

- **`JevRuntime`** (`runtime.py`). It only asks `should_continue` and then calls `continue_`. The `@intent continuation-logic-lives-in-the-continuation` comment exists because a reviewer asked for exactly that split.
- **`JevAgent.__init__`**. It already builds `JevRunState` and `JevDoneContinuation` whenever `continual.checks` is non-empty.
- **`JevContinualSettings`** and **`JevRuntimeSettings`**. `checks` already validates through the registry.
- **`JevResponse`**. `done` is keyed by `JevDoneCheck`.
- **The run-state and handoff system prompts**. `test_prompts_are_general_not_multi_part_specific` forbids check-specific words in them. Your check's instructions live in `SECTION` and the field descriptions.

### Step 15: Exports, tests, docs

- **Exports.** Export records that a user reads from `JevAgent.response` (your item and evidence records) through the same chain as `JevDeliverable`: `vidbyte/agents/jev/__init__.py` → `vidbyte/agents/__init__.py` → `vidbyte/__init__.py`, with each module's `__all__` updated (lint S015).
- **Tests** in `tests/test_jev_done.py`:
  - `JevDoneRecordTests`: your records live in lib, reject bad and duplicate ids, and hold no parsing code; your payloads go into the 4–6-sentence description test.
  - `JevDoneSchemaTests`: enabling your check adds its described section to both schemas.
  - A question test class like `JevDoneQuestionTests`: the brief layout, verdict-first mirrored criteria, minimal-pair boundaries, at least 2,000 tokens, and one literal per section.
  - `JevDoneRuntimeTests`, through `JevAgent` with `ScriptedGenerativeRunner` and `ScriptedDecisionRunner` and no network:
    - a pass;
    - a fail that continues in the same loop, with the five sections and only the incomplete item under Focus;
    - the continuation cap;
    - the threshold boundary and the veto;
    - run-state, handoff, and Jev failures that fail open;
    - a handoff whose ids do not match, which makes the handoff unavailable;
    - no items, which passes with no Jev question;
    - **both checks enabled**: one request that carries both checks' state keys and questions.
  - Keep `scripts/test-jev-multipart-done-criteria.py` loading every done-check test module, or add a `scripts/test-jev-<check>-done-criteria.py` beside it.
- **Docs.**
  - Add a design doc at `docs/design/jev-<check>-done-criteria.md` for the check.
  - Update the module headers you touched (`COMMON MODIFICATION PATTERNS`, `RELATED DOCS`), which lint A001 checks.
  - Update the "Adding a done check" section in `skills/jev-agent/SKILL.md` if the steps changed.
  - **Update this skill** if any seam named here moved.

### Step 16: Verify

```text
python scripts/test-jev-multipart-done-criteria.py
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
```

Your change must not raise any lint baseline count.

---

## 4. Important things to remember

- **A check is data plus `match` cases, not a class.** It adds sections to the agents that can know its items, records, one question module, and one `case` each in `_section`, `_judge`, and `_explain`. CLAIMS items come from the post-run handoff, not the pre-run state.
- **Generative agents write, and Jev recognizes.** Listing items, writing "done when" conditions, and compiling evidence are generation, done by `JevRunState` and `JevHandoff`. Jev only answers yes or no per item. Counting, "all of them", and thresholds belong in code.
- **One Jev request per finish attempt.** Every enabled check's questions share one state and one request. Question names `"<key>.<item_id>"` keep the answers apart. Never add a second `DecisionModelRunner` call.
- **One item per question, and the focus rule names the id.** This keeps each answer tied to one item, so Focus names the exact missing part. The brief must say to judge only the named entry.
- **The shared state must describe itself truthfully** for every combination of enabled checks (step 11).
- **`evidence` goes to Jev, and `missing` goes to the main agent.** Never the reverse.
- **The run state is written once, from the request only, before any work.** It is the fixed reference for checks with request-derived items; never predict final-answer claims there.
- **The handoff is recompiled at every finish attempt**, with history cleared. Request-derived item ids must match the run state; dynamic claim ids must be valid and unique within that handoff.
- **Everything fails open.** Every failure path in `_judge` returns `available=False`, and an unavailable check never continues the run.
- **Continuations are bounded** by `JevContinualSettings.max_continuations` (default `JEV_DONE_MAX_CONTINUATIONS` = 3), and `0` means report only.
- **The continuation appends to the same loop.** It never re-runs the main agent, which would lose its history.
- **Outcomes reach the caller through `JevAgent.response`** (`run_state`, `handoff`, `done[check]`, `continuations`), never through result metadata.
- **Placement is enforced.** Enums go in `lib/enums/jev.py`, records and payloads in `lib/dataclasses/jev.py`, constants in `lib/constants/jev.py`, and questions in `lib/jev/done/`. Logic goes in `agents/jev/done/` and `agents/jev/continuation/`.
- **Each `match` case gets a comment** that says what the case does and why, as the existing cases do. Load-bearing choices get an `# @intent <slug>` comment (lint A002).
- **Prompts are assets.** Never inline message text for the main agent in Python. Only the run's own text is formatted in.

---

## 5. When to write a new JevContinuation instead

`JevContinuation` (`vidbyte/agents/jev/continuation/base.py`) is the contract the runtime calls:

- `async should_continue(final_answer, responses, calls) -> bool`
- `continue_(messages) -> None`, called only after `should_continue` returned True on the same finish attempt. The subclass may keep what it decided between the two calls.

Write a new subclass in its own module under `continuation/` **only** when the reason to continue is not "a done question about the finished work said no". An example would be a continuation driven by a compute budget or by a different signal. For a new subclass:

- Build it in `JevAgent.__init__` and pass it to the runtime through `_runtime_extension_kwargs()`. If more than one continuation must run, compose them in a continuation. Never branch in `JevRuntime`.
- Put its message text in a new prompt family under `vidbyte/prompts/prompts/`, with a key in `vidbyte/lib/enums/prompts.py`.
- Record its outcomes through a new `JevResponse` method.
- Give it its own settings field. That field lives in `vidbyte/agents/jev/settings.py`, because agent settings are the one exception to the dataclass placement rule.

A new kind of done check never needs a new continuation class, because `JevDoneContinuation` already runs every enabled check.
