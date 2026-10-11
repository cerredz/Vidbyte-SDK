# JevAgent done checks: multi-part done criteria

## Problem

An agent often finishes one visible part of a request and forgets another part that was asked for in passing: it changes the code but never documents it, or answers two of three questions. JevAgent should notice this before it returns, and send the main agent back to finish the missing part inside the same run.

## User-facing capability

A developer enables a done check by name on `JevRuntimeSettings`, the object that holds Jev's own decision policy:

```python
agent = JevAgent(settings, JevRuntimeSettings(done=(JevDoneCheck.MULTI_PART,)))
```

`JevDoneCheck` is the only option list. Today it has one member, `MULTI_PART`. After a run, `agent.response.run_state`, `agent.response.handoff`, `agent.response.done[JevDoneCheck.MULTI_PART]`, and `agent.response.continuations` report what happened. Nothing is written to result metadata.

## Design

Two generative agents own the feature, both in `vidbyte/agents/jev/done/`. Jev question text, records, vocabularies, and thresholds stay in `vidbyte/lib`.

### `JevRunState`

`JevAgent.__init__` builds one `JevRunState` when `done` is set, the same way it builds the preflight gate.

- **Schema.** The output schema is the central `JevRunStatePayload` (`goal`, `objective`, `mission`, `what_not_to_do`) plus one field per enabled `JevDoneCheck`. Each field is typed as that check's section payload (`JevMultiPartPayload`) and described by the section's `SECTION` text. Enabling a check adds a field to the one class; no check gets its own class. Every field of every payload carries a 4–6 sentence description, and that description is the instruction the model reads for the field.
- **Begin.** Before the main loop, `JevRuntime` calls `begin(request)`. The generative model writes the run state once, from the request alone. The reply is converted into the frozen `JevRunStateRecord`, and `JevMultiPart` holds the `JevDeliverable` entries.
- **Check.** Each time the main agent tries to finish, `JevRuntime._continue_finish_attempt` calls `check(...)`. This hook on `AgentRuntime` returns `False` by default. `check` asks `JevHandoff` for evidence, runs every enabled check, and records the results through `JevResponse`. When a check fails, it returns feedback, which joins the same loop's messages. The main agent therefore keeps its history, tools, and budgets. At most `JEV_DONE_MAX_CONTINUATIONS` (3) continuations are sent; after that the latest verdict is recorded and the answer stands.

### `JevHandoff`

The handoff is general. It is not written for the multi-part check.

- Its message is the user's original request.
- Its context is a `vidbyte.context.ContextManager`: the rendered run state, then the main agent's context window as SDK primitives (`ResponseContextItem` per response, `ToolCallContextItem` per tool call), then the final answer.
- Its output schema is `JevHandoffPayload` plus one evidence section per enabled check, typed and described exactly as in `JevRunState`. For the multi-part check, the section is `JevMultiPartEvidencePayload`: one `{id, evidence, missing}` entry per deliverable.
- The handoff reports what the run shows and never gives a verdict. Evidence whose ids differ from the run state's ids makes the handoff unavailable.

### The Jev question

`MultiPartDeliveredQuestion` (`vidbyte/lib/jev/done/multi_part.py`) is written to `skills/asking-jev-questions/SKILL.md`. It has a brief with one-string definitions and rules, mirrored criteria with minimal-pair boundary examples, and more than 2,000 tokens in total.

Jev is asked once per deliverable. Each request's state holds the original `request`, that one `deliverable`, its `completion_signal`, and only that deliverable's `evidence`:

- The request lets Jev read the deliverable's words in context.
- The deliverable and its completion signal define the right answer (T13).
- The evidence is the only view of the run Jev needs.

The handoff's `missing` text stays out of the state, because it is the handoff writer's judgment rather than an observation. It is used only for the feedback the main agent reads.

`DecisionModelRunner.score_noul` joins the answers. `JEV_MULTI_PART_THRESHOLD` (0.8, untuned) serves as both the mean threshold and the veto, so every deliverable must reach it.

### Failure policy

Done checks are advisory, like preflight, so every failure fails open:

| Failure | Result |
|---|---|
| No run state | No check runs. |
| Handoff failure or id mismatch | The check is marked unavailable. |
| Jev outage or missing credential | The check is marked unavailable. |

A request with no deliverables passes without asking Jev. A chosen specialist runs through its own agent, so no done check applies to it.

## Alternatives rejected

- **Records with `from_payload` and `output_schema` methods in `vidbyte/agents/jev/run_state.py`.** The review moved records and enums to `vidbyte/lib`. Payload-to-record conversion now belongs to the agent that asked for the reply.
- **One builder class per shape (`MultiPartStateBuilderAgent`, `MultiPartHandoffBuilderAgent`).** The review asked for one class whose schema grows with the enabled enum options.
- **A multi-part-specific handoff with source-excerpt validation.** The review asked for a general handoff that reads the main agent's context window through the context manager, with an evidence shape tailored to each check.
- **An inline Jev question built in the runtime.** The review asked for real Jev questions written with the skill, kept in `vidbyte/lib/jev/done/`.
- **A `done_criteria` argument on the `JevAgent` constructor.** Since #469, Jev policy lives on `JevRuntimeSettings`, and `JevAgent.__init__` takes only the two settings objects.
