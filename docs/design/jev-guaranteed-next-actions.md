# Guaranteed Next Actions Done Check

## Problem

A run can reach a finish attempt after observing a blocker that makes the user's requested outcome impossible to complete as it stands. The agent may stop without resolving that blocker. This check catches only a concrete follow-on obligation that is necessarily required by the requested outcome and the observed trigger. It does not predict what work is likely to help.

## Design

Add the opt-in `JevDoneCheck.GUARANTEED_NEXT_ACTIONS`. At each finish attempt, the existing handoff may derive zero or more candidate obligations from the request and current run evidence. A candidate names the concrete requested outcome, a trigger directly shown in the run, and one remaining action. Its necessity basis is only a candidate-generation aid: it is not included as proof in Jev's state. The handoff must omit a candidate when it cannot tie all fields to the user's request and observed state.

Jev receives two questions per candidate in the existing batched request. The first independently asks whether the original request and observed trigger logically entail this action as necessary to achieve the requested outcome, with no plausible authorized alternative. The second asks whether the run evidence shows the action remains unfinished. Both recognition answers must pass the same candidate threshold before code may continue. The necessity question sees the request, outcome, trigger, and observed evidence directly; it never treats the handoff's necessity claim as proof. Jev does not generate actions or forecast useful work. Explicitly requested sequences and general phase progress are outside this check.

Failed items continue the same loop with only the outcome, trigger, action, and concrete evidence gap. No candidates passes without a Jev call. Missing run state, handoff, or either required answer fails open. A false necessity answer disqualifies that candidate and can never cause continuation. The existing continuation limit still bounds retries.

Candidates are dynamic because the trigger may not be observable until the main loop runs. The handoff is therefore the source of the item list, as it is for final-answer claims; the run-state schema is unchanged. The handoff proposes candidates and compiles evidence, while Jev independently recognizes necessity and incompletion.

## Files

- `vidbyte/lib/enums/jev.py`: add the check and two question keys.
- `vidbyte/lib/constants/jev.py`: add the threshold and state field names.
- `vidbyte/lib/dataclasses/jev.py`: add handoff payload and validated records for obligation and evidence.
- `vidbyte/lib/jev/done/guaranteed_next_actions.py`: define two recognition questions.
- `vidbyte/lib/jev/done/done.py` and `vidbyte/lib/jev/done/__init__.py`: register and export both questions.
- `vidbyte/agents/jev/done/handoff.py`: include and validate dynamic candidates in the handoff.
- `vidbyte/agents/jev/done/run_state.py`: project candidate state, batch both questions, and require necessity plus incompletion to pass.
- `vidbyte/agents/jev/continuation/done.py`: include only candidates that pass necessity and fail completion, with their concrete evidence gaps.
- `docs/design/jev-guaranteed-next-actions.md`: document the feature and its limits.
- `skills/jev-agent/SKILL.md` and `skills/jev-continuation/SKILL.md`: document the named capability and its two-question, fail-open continuation contract.

## Risks and limits

The handoff's candidate list and Jev's necessity answer are semantic judgments, not a machine proof. The check is conservative and opt-in, and fails open on unavailable or malformed evidence. It can still produce false positives or miss candidates. It does not guarantee that one particular tool call is the chronological next action; it only checks whether a necessary obligation remains before the requested outcome can be considered complete.

## Verification

Review the schema and questions for two separate recognition judgments, inspect enum/registry/schema wiring, and run `git diff --check`. Do not add or run tests in this task per the active instruction; hosted PR checks may run automatically.
