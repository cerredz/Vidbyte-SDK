# Jev motivating-case continuation gate

## Purpose

The motivating-case gate catches a run that handles the ordinary flow but skips the unusual condition the user named as the reason for the work, such as empty input, a retry, conflicting state, or a failure path. It asks whether the run shows that exact condition handled, rather than a nearby, easier case.

The public API uses the current continuation settings:

```python
JevRuntimeSettings(
    continual=JevContinualSettings(checks=(JevDoneCheck.MOTIVATING_CASE,))
)
```

This is one named `JevDoneCheck`. It does not add `done_criteria` to `JevAgent`, a new runtime hook, or a separate continuation class.

## Flow

1. `JevRunState` writes request-derived scenario definitions once before the main loop. Each entry has a stable id, source quote, target, exact condition, near miss, expected behavior when stated, user-supplied literal inputs, and permitted exercise mode. Only user-named scenarios can block; inferred scenarios remain informational.
2. If there is no blocking scenario, a fixed recall question checks the raw request once before the main agent starts. When P(yes) reaches `JEV_MOTIVATING_CASE_RECALL_THRESHOLD`, the state writer gets one targeted retry. The response record exposes the guard probability and whether the first state disagreed; an unavailable guard does not stop the run, and a second empty state is not retried again.
3. At every finish attempt, `JevHandoff` writes one evidence entry for each scenario from the main agent's current run window. It includes the relevant setup or code inspection, execution and result, later edits that could make a run stale, and an actionable `missing` note. The handoff is regenerated from the longer loop after each continuation.
4. `JevRunState` combines one question per blocking scenario with every other enabled done check in one Jev request. The question judges the request-derived definition against evidence, not the handoff's `missing` opinion or the agent's claim that it is done.
5. A missing or below-threshold answer becomes the incomplete scenario id. `JevDoneContinuation` names that scenario and the evidence gap, appends the continuation message to the same loop, and respects `JevContinualSettings.max_continuations`. The latest result remains on `JevAgent.response.done` after the cap.

Every stage uses the existing fail-open path. An unavailable run state, recall question, handoff, or finish-attempt Jev answer leaves the main agent's answer standing. An empty second state or a list containing only implied scenarios has no blocking finish question.

## Evidence rule

For `run`, evidence must show a setup that supplies the exact condition to the target, a successful relevant execution, and a check of the expected behavior when the user stated one. A failed, skipped, deselected, or stale run does not count. For `run_or_inspect`, either an execution meeting those requirements or inspection of the target's exact handling branch can count. For `inspect_only`, the evidence must show the target code path for that condition and its defined result. A nearby case, test name, comment, plan, or final-answer claim does not show the case handled.

The state writer's source quote and any literal input are checked against the request with whitespace normalization. State ids must be unique and within the configured scenario cap. The handoff must return exactly one evidence entry per state id; mismatched or missing entries make the handoff unavailable instead of silently skipping a case.

## Records and integration

- `JevRunStateRecord.motivating_case` carries the immutable request-derived scenario definitions, recall probability, and initial-builder disagreement flag.
- `JevHandoffRecord.motivating_case` carries the current evidence and missing notes.
- `JevDoneResult` for `MOTIVATING_CASE` uses scenario ids for its answers and incomplete items.
- The records are exposed through `JevAgent.response`; they are not placed in `AgentResult.metadata`.
- The fixed question lives in `vidbyte/lib/jev/done/motivating_case.py`; schemas and continuation feedback extend the shared `JevRunState`, `JevHandoff`, and `JevDoneContinuation`.

The finish threshold `0.8` and recall threshold `0.6` are initial opt-in values and have not been tuned against labeled evaluations.
