# Jev required sequence (done check #15)

## What and why

A request such as "research the topic, then write a draft from your research, have it reviewed, and only then publish it" defines stages that must happen in order. Today a JevAgent stops as soon as the model returns a final answer, even if it skipped the review or edited the draft after the review. Reaching the last stage does not show that the whole sequence happened.

This change adds one named setting, `JevAgentSettings(required_sequence=True)`. When it is on, the agent derives the ordered stages from the request before it starts, and it is only allowed to finish when the run shows every stage done, in order.

It also lays the foundation the "jev done criteria" design settled on, which later done checks (for example multi-part completion) reuse:

1. A generative **run-state builder** runs once, before the main loop, and turns the request into a structured `JevRunState`: `goal`, `objective`, `mission`, `what_not_to_do`, `constraints`, `proposed_plan`, plus one section per enabled setting.
2. At every finish attempt, a generative **handoff builder** reads the request, the run state, the proposed answer, and a numbered event log of the run, and fills a handoff whose sections mirror the run state's sections.
3. Code checks what code can check exactly. Jev answers narrow recognition questions about each stage, written with `skills/asking-jev-questions/SKILL.md`.
4. A new finish-attempt seam on `AgentRuntime` lets `JevRuntime` send the agent back to work with specific feedback.

## How it works

### Run state (once, before the run)

`JevRunStateAgent` is a tool-free `BaseAgent` subclass with a strict JSON output schema. It reuses the main agent's runner. Its schema is the base object plus the `required_sequence` section:

| Stage field | Set by | Used for |
| --- | --- | --- |
| `stage_id` | code (`stage_1`, `stage_2`, ...) | joins state, handoff, Jev questions, and feedback |
| `name` | model | readable feedback |
| `source_text` | model, verbatim from the request | code checks it appears in the request, which blocks invented stages |
| `completion_criterion` | model | the definition Jev compares observed work against |
| `produces` | model | what the stage outputs, matched against the next stage's inputs |
| `depends_on_previous` | model (forced false for stage 1) | whether the "uses previous output" question is asked |

The section is **inactive** for the run (nothing is gated) when the request has no required order, has fewer than 2 or more than 12 stages, has a blank field, or cites words that are not in the request. The reason is recorded in the result metadata.

When active, the stage list is appended to the main agent's system prompt so the agent knows the order from the start.

### Event log

No middleware is involved. At each finish attempt, code builds a numbered log from the loop state that `review_finish_attempt` already receives:
- `E1` is the request (`state.message`);
- then, for each iteration, the assistant's text from `state.iteration_outputs`, followed by that iteration's tool calls from `state.call_contexts` (matched on `iteration_count`), each with its arguments, status, and output;
- feedback from earlier rejected finish attempts appears as `[finish review]` events at the iteration where it was sent.

Every list only grows, so event IDs stay stable across finish attempts. `isDone` calls are skipped, because the proposed answer is passed separately. Very long single outputs are cut with an explicit marker. Only the final attempt of a retried tool call is visible, because that is what `call_contexts` keeps.

### Handoff (at each finish attempt)

`JevRunHandoffAgent` fills exactly one entry per stage ID. It reports what the log shows; it has no `complete` field.

| Entry field | Used for |
| --- | --- |
| `observed_work` (description plus event IDs) | Jev "work shown" question; code checks the IDs exist |
| `outputs_produced`, `inputs_used` | Jev "uses previous output" question |
| `first_event_id`, `last_work_event_id` | code order check |
| `failures` | told to Jev as not counting |
| `missing_or_uncertain` | Jev context and feedback text |

Code validates the handoff: exactly the state's stage IDs, cited event IDs exist, and `first <= last`. An invalid handoff is rebuilt once with the error; if it is still invalid, the finish is accepted and flagged `handoff_invalid`.

### Decision

For each stage in order, code finds the first failure:

1. No work located: stage has no observed work or no first event.
2. Out of order: `first_event_id(k) <= last_work_event_id(k-1)`. This also catches rework, such as editing the draft after the review started.
3. Jev says the observed work does not show the completion criterion.
4. Jev says the stage did not work from the previous stage's output (asked only when `depends_on_previous`).

Jev gets one request per review. Its state holds each stage's state and handoff fields, and each question points at one stage by field name. Code never asks Jev whether the sequence is complete or ordered; it computes `required_sequence_complete` itself.

If any stage fails, the review sends the agent back with feedback naming that stage. The agent is sent back at most 3 times; the next failing review stops the run with the new `AgentStopReason.FINISH_REVIEW_REJECTED`, because `max_iterations` defaults to unbounded.

If Jev is unavailable (no key, provider error), only the code checks run and the review is flagged `jev_unavailable`.

### Finish-attempt seam

`AgentRuntime.review_finish_attempt(candidate_output, state) -> FinishReview` is called on both finish paths (plain final response and `isDone`), after the output contract. The default accepts, so every other agent is unchanged. `FinishReview` can accept, continue with feedback, or stop.

### Pre-existing fix: schema conformance never saw the output

`AgentRuntime._contract_counters` never set the `final_output` key that `SchemaConformance` reads. As a result, every `BaseAgent` with an `output_schema` was rejected as "not valid JSON", even when the model returned valid JSON. `HandoffAgent` only worked because it falls back to parsing prose. Both builders need strict structured output, so the counters now include `final_output`.

## Files

- `vidbyte/lib/dataclasses/agents.py`: `FinishReviewAction`, `FinishReview`, `AgentStopReason.FINISH_REVIEW_REJECTED`.
- `vidbyte/agents/runtime.py`: the seam on both finish paths, and `final_output` in the contract counters.
- `vidbyte/agents/jev/settings.py`: `required_sequence: bool`.
- `vidbyte/agents/jev/run_state.py`: base run state, handoff, event records, section contract.
- `vidbyte/agents/jev/builders.py`: `JevStructuredBuilderAgent`, `JevRunStateAgent`, `JevRunHandoffAgent`.
- `vidbyte/agents/jev/event_log.py`: builds the numbered event log from the loop state.
- `vidbyte/agents/jev/required_sequence.py`: the section, its parsing, Jev questions, and verdict.
- `vidbyte/agents/jev/runtime.py`: orchestration and the review override.
- `vidbyte/agents/jev/README.md`, `__init__.py`: package docs and exports.
- `vidbyte/lib/constants/jev.py`: named caps and thresholds.
- `vidbyte/lib/enums/jev_run_state.py`, `vidbyte/lib/enums/__init__.py`: section key, section status, event kind, stage failure.
- `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/prompts/jev_run_state/`, `vidbyte/prompts/README.md`: builder and stage prompts as assets.
- `vidbyte/lib/dataclasses/__init__.py`: exports `FinishReview` and `FinishReviewAction`.
- `tests/test_jev_required_sequence.py`: offline tests.
- `skills/jev-agent/SKILL.md`: capability and architecture guidance.

## Risks and open questions

- The handoff builder can attribute an event to the wrong stage. Code only confirms cited events exist.
- The strict order rule forbids interleaving (for example more research while drafting). That matches "must happen in order" but is a policy choice.
- Builder calls are extra generative cost: one at the start, one or two per finish attempt. Their usage is reported in metadata, not folded into the main agent's token budget.
- Failing open on builder failure keeps a broken builder from blocking runs, at the cost of an ungated run (flagged in metadata).
- Overlaps with open PRs #443 and #445 on `JevRuntime.arun`; whichever merges second needs a small rebase.

## Verification

- `tests/test_jev_required_sequence.py`, fully offline with scripted runners and a scripted decision runner:
  - disabled path unchanged;
  - no-order request is inactive;
  - invented stage is inactive;
  - in-order run accepted;
  - skipped stage sends the agent back with that stage named;
  - out-of-order rework rejected;
  - Jev "not shown" rejected;
  - the finish-review cap stops the run;
  - Jev unavailable falls back to the code checks;
  - invalid handoff is rebuilt;
  - the seam works on both finish paths.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, `python scripts/run_ci.py`, then PR CI.
