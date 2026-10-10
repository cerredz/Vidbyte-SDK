# JevAgent self-review done check

## What and why

`JevDoneCheck.SELF_REVIEW` is a new continuation done check. Every time the main agent tries to finish, and before any other check runs, a strict reviewer runs one tool-free turn over the main agent's own run and answers: *list what a strict reviewer would reject in this work, most serious first.* Jev then decides which of those objections are real, unresolved, and in scope. Those objections become the Focus of the continuation, and the main agent goes back to fix them in the same loop.

Agents often know their shortcuts: the test they did not run, the edge case they waved away, the requirement they quietly narrowed. Asking "are you done?" invites self-grading, and the agent says yes. Asking for criticism outright, from the stance of a reviewer who has to approve the work and is looking for reasons to reject it, brings those known gaps out cheaply, especially around the crux of the task. The owner asked for this check to take the stance of a **stricter agent**: a critic of the original work whose objections drive the agent to improve its weak points. That stance appears in three places: the reviewer's prompt, the Jev questions, and the message the main agent receives.

## How it works

At each finish attempt, `JevRunState.check()` now runs these stages:

1. **Review (new, generation).** `JevReviewer` is a tool-free `BaseAgent` on the JevAgent's own model, with the fixed prompt `jev_review/system_prompt.md`. It reads the request (its message) and the run state plus the main agent's window (the same `ContextManager` the handoff reads). It returns `JevReviewPayload`: at most `JEV_REVIEW_MAX_OBJECTIONS` objections, ordered most serious first. Each objection has an `id`, the `objection` (what a strict reviewer would reject, and where), and `resolved_when` (the visible condition under which the reviewer would accept the work). The prompt casts it as the strictest reviewer who must sign off on the work. It starts from the crux and looks hardest at shortcuts. It is strict about the quality of what was asked, but it never asks for more than was asked.
2. **Handoff (existing, extended).** The review is added to the handoff's window, and a new `self_review` evidence section (`JevSelfReviewEvidencePayload`) asks for one entry per objection id. Each entry holds neutral `evidence` about what the run shows, plus `missing`. The objection is treated as an accusation to report on, not as a finding. The ids must match the review's ids exactly, or the handoff is unavailable (same rule as multi-part).
3. **Jev (recognition).** Two noul questions are asked per objection, batched into the one existing request:
   - `self_review.resolved`: "Does `evidence` show that the work meets `resolved_when`…?" Yes means the reviewer misread the work (the objection is not real) or a later step fixed it (it is resolved). So *real ∧ unresolved* is one observation of the latest state. Silence or claims count as no: the burden of proof sits on the work.
   - `self_review.in_scope`: "Does `request` ask for the work that `resolved_when` describes…?" A demand that requested work be correct, or meet a standard the request states or clearly implies, is in scope. New outputs the request never asked for (extra tests, docs, features, refactors) are not.
4. **Judge (code).** An objection is set aside only when Jev is confident about it: `max(P(resolved), 1 − P(in_scope)) ≥ JEV_SELF_REVIEW_THRESHOLD`. Doubt keeps the objection standing, which is the strict stance. The check passes when every objection is set aside. `score` is the mean clearance, and `incomplete` lists the standing objections in the reviewer's order. A review with no objections passes, and no question is asked for it.
5. **Continuation.** `_explain` opens with the two questions' `gap` sentences, written in the critic's voice ("A strict reviewer would reject your work as it stands…; fix each weakness at its root…"). It then lists each standing objection with Jev's two probabilities and the handoff's `missing` text. Focus lists `- A strict reviewer would reject: <objection> Accept when: <resolved_when>`, most serious first. The opening of `continue_prompt.md` is generalized by one clause so that it also covers "not yet done to a standard a strict reviewer would accept".

The shared Jev state gains `objections: {id: {objection, resolved_when, evidence}}` next to `request` (and next to `deliverables` when multi-part is also enabled). `DONE_STATE` moves to `vidbyte/lib/jev/done/state.py` and describes every field together with the condition under which it is present, so it stays true for every combination of checks (skill step 11).

Everything fails open. If the review fails, the self-review check is unavailable, and multi-part is unaffected because the handoff drops only the `self_review` section. Failures of the handoff or Jev are handled as they are today. Continuations stay capped by `max_continuations`.

### Deviations from the jev-continuation skill, and why

- **No run-state section.** Objections exist only after the work, so `JevRunState.schema()` skips checks that have no `_SECTIONS` entry. The tests that required `_SECTIONS == set(JevDoneCheck)` become "every check except self-review".
- **`check()` gains a stage.** The review has to run before the handoff. The runtime, the agent wiring, and `JevDoneContinuation.should_continue` stay untouched.
- **Two questions per item.** `JevDoneRegistry._questions` maps each check to a tuple, and `question(check)` becomes `questions(check)`. The call sites for multi-part unpack `(question,)`. `JevDoneResult.answers` is keyed by question name for self-review, which has two answers per id.
- **A new agent means new prompt, record, and settings surface.** This adds the prompt family `jev_review`, `JevResponse.review()` and `JevAgentResponse.review`, and `JevContinualSettings.review_max_iterations` / `review_max_tokens`, following the handoff's pattern.

The skill (`skills/jev-continuation/SKILL.md`) is updated where these seams moved.

## Files

- `vidbyte/lib/enums/jev.py`: `JevDoneCheck.SELF_REVIEW`, and `JevDoneQuestionKey.SELF_REVIEW_RESOLVED` / `SELF_REVIEW_IN_SCOPE`. `vidbyte/lib/enums/prompts.py`: `JEV_REVIEW_SYSTEM_PROMPT`.
- `vidbyte/lib/constants/jev.py`: the threshold, the maximum number of objections, the review limits, and the `objections` / `objection` / `resolved_when` state field names.
- `vidbyte/lib/dataclasses/jev.py`: the review payloads and record (`JevObjection`, `JevReviewRecord`), the evidence payloads and records, `JevHandoffRecord.self_review`, `JevAgentResponse.review`, and docstrings.
- `vidbyte/lib/jev/done/state.py` (new, `DONE_STATE`), `self_review.py` (new, both questions), plus `done.py`, `multi_part.py`, `__init__.py`, and `README.md`.
- `vidbyte/agents/jev/done/reviewer.py` (new, `JevReviewer`), plus `run_state.py`, `handoff.py`, and `__init__.py`.
- `vidbyte/agents/jev/continuation/done.py`, `response.py`, and `settings.py`.
- `vidbyte/prompts/prompts/jev_review/` (new family), `jev_handoff/system_prompt.md`, and `jev_continuation/continue_prompt.md`.
- Public exports: `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, and `vidbyte/__init__.py`.
- `tests/test_jev_done.py`, `skills/jev-continuation/SKILL.md`, and `skills/jev-agent/SKILL.md`.

## Risks and open questions

- **A strict reviewer always finds something.** Without limits, every run would use all of its continuations. The limits are: the in-scope question, "list only what you would *reject*, not polish" in the prompt, the maximum of `JEV_REVIEW_MAX_OBJECTIONS`, and `max_continuations`. The threshold (0.8) is a starting point and has not been tuned. It needs a labeled probe set (strategy 25).
- **One threshold serves both questions.** T17 warns against carrying a threshold across questions. It is kept as one constant until labels exist.
- **The reviewer is not literally the main agent's own loop turn.** A real extra turn in the main loop would need runtime changes, which the skill forbids. The reviewer uses the same model and reads the main agent's full window, which carries the knowledge of the shortcuts.
- **Sibling done checks.** #473 and other in-flight checks touch the same seams (`DONE_STATE`, `_section`, `_judge`, `_explain`). Whichever merges later rebases.

## Verification

- `tests/test_jev_done.py` will cover the following:
  - Records, payload description depth, and schemas.
  - That the reviewer is built only when the check is enabled, has no tools, and takes its limits from settings.
  - The prompt sections and the strict-reviewer wording.
  - For both questions: layout, criteria, minimal pairs, a floor of 2,000 tokens, and one string literal per section.
  - End to end:
    - A standing objection continues the run, and Focus holds only that objection, in the reviewer's order, in the critic's voice.
    - Objections that are resolved or out of scope are set aside.
    - A review with no objections passes with no Jev call.
    - A failed review fails open while multi-part still runs.
    - Mismatched objection ids make the handoff unavailable.
    - With both checks enabled, one request carries both checks' state keys and question prefixes.
    - Objections beyond the maximum are truncated.
- Commands:
  - `python scripts/test-jev-multipart-done-criteria.py`
  - `python lint/run.py`
  - `python scripts/run_ci.py --stage source`
  - `python scripts/run_ci.py --stage package`
