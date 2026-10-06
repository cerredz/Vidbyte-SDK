# JevAgent required actions continuation gate

## User outcome

When enabled with `JevDoneCheck.REQUIRED_ACTIONS`, JevAgent checks that explicitly requested procedures or actions have observable completion evidence before accepting a finish attempt. The check does not invent useful steps, conflate procedure with output count, or accept the final answer's bare statement that an action happened.

## Callers and flow

- Caller: `JevAgent` configured through `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.REQUIRED_ACTIONS,)))`.
- `JevRunState.begin()` extracts stable, explicit action ids and observable completion conditions before work starts.
- At each finish attempt, `JevHandoff` collects the per-action trace observations and may cite an exact substantive excerpt from a recorded response or final answer.
- One Jev yes/no question is sent per action in the same batched request as any other enabled checks. Deterministic code vetoes a positive answer when neither a successful completion call nor a source-validated output excerpt exists, and checks explicit ordering from successful call indices.
- On failure, `JevDoneContinuation` returns the run to the same model loop with the request, state, evidence, failed questions, and action-specific focus. Continuations obey the existing cap; unavailable model stages fail open.

## Invariants

- Only actions directly required by the user's request enter `required_actions`; conventional or inferred steps stay out.
- A call attempt, failed tool result, delegation without a returned result, or final-answer completion claim does not count as successful completion.
- An output excerpt is accepted as evidence only if its exact text occurs in the cited response or final answer. Jev still determines whether its content satisfies the completion signal.
- Explicit dependencies require successful completion trace indices in the stated order. Missing chronology cannot pass the dependent action.
- `missing` is for continuation feedback; Jev receives evidence only.
- Every enabled check shares one Jev request per finish attempt, and all failure paths are advisory and fail open.

## Failure inventory and test mapping

| Risk or behavior | Coverage |
|---|---|
| Bad or duplicate action ids, unknown predecessors, malformed trace indices | `JevDoneRecordTests` |
| Missing or reversed explicit order | `test_required_action_order_fails_without_successful_indices_or_when_indices_are_reversed` |
| A high Jev score cannot hide absent evidence; same-loop focus names the gap | `test_required_actions_asks_per_action_and_requires_observable_explicit_order` |
| Substantive output can prove a non-tool action | `test_required_action_accepts_a_validated_substantive_output_excerpt_without_a_tool_call` |
| One question per action, state projection, schema and threshold | `JevDoneSchemaTests`, `JevDoneQuestionTests` |
| Question boundaries and minimum size | `test_required_actions_criteria_have_a_passing_and_failing_tool_output_pair`, `test_required_actions_question_carries_two_thousand_tokens_and_one_literal_per_section` |

No live provider or browser test is needed: the gate has no external side effect, and scripted model and decision runners exercise the production schema, registration, scoring, handoff, and continuation wiring.
