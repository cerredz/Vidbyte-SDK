# JevAgent expert-depth done check

## What and why

`JevDoneCheck.EXPERT_DEPTH` is the second continuation done check, after `MULTI_PART`. Multi-part catches a run that *skipped* a deliverable. Expert depth catches a run that produced every deliverable, but only in its quick, shallow form. An example is a "retry" feature with no backoff, no attempt cap, a retry on a non-idempotent POST, and no rule for which errors retry.

The check does not ask what an ideal expert would add. It looks for the **weakest points**: the specific places in each requested deliverable where a quick version is thin. It checks each point against the finished run, and it sends the main agent back to go **deeper on the weakest ones first**. Depth, never breadth: a point is always a part of an output the request already asks for, never a new output.

## How it works

It follows `skills/jev-continuation/SKILL.md` step by step, with no runtime, agent, settings, or response changes.

1. **Run state (prior, before any work).** The `expert_depth` section lists the deliverables that a quick version could do thinly. Each one carries **3–5 `details`**, ordered from the point a quick version most likely gets wrong. Each detail has:
   - `id`: unique across the whole section;
   - `detail`: the specific part a deep version handles;
   - `shallow_version`: what the quick version of that part looks like, meaning the weak point;
   - `done_when`: the visible condition that shows the part handled in depth;
   - `risk`: what goes wrong if it stays shallow.

   A deliverable with no depth to miss is left out. An empty list passes with no Jev question.
2. **Handoff (every finish attempt).** It writes one `{id, evidence, missing}` entry per detail id. Its ids must match the run state exactly, or the handoff is discarded and the check fails open. `missing` is written as "what the deeper handling still needs" and goes only to the main agent.
3. **Jev (posterior).** The check adds one `noul` per detail, *"Does `evidence` show that `detail` was handled in depth, in the entry of `expert_details` with id `{item}`?"*, to the same single batched request. The state key is `expert_details: {id: {deliverable, detail, shallow_version, done_when, evidence}}`. `shallow_version` and `done_when` sit next to the evidence as a per-item minimal pair (T13). `risk` and `missing` stay out, because they are judgment, not run.
4. **Judge.** `score_noul` runs with `JEV_EXPERT_DEPTH_THRESHOLD = 0.7` as both the threshold and the veto. That is a starting point, set lower than multi-part's 0.8 because depth is graded and a false "shallow" costs a whole continuation. `incomplete` is **sorted weakest first**, by ascending P(yes), with ties in run-state order. The recorded result therefore carries the ranking.
5. **What the generative agent gets.** In `_explain`:
   - **Failed checks** lists every incomplete detail, weakest first, with its P(yes) and what the handoff says the deeper handling still needs.
   - **Focus** names only the `JEV_EXPERT_DEPTH_FOCUS_LIMIT = 3` weakest points. Each one reads: *go deeper on* `detail` (part of `deliverable`), *the quick version to move past* `shallow_version`, *why it matters* `risk`, *done when* `done_when`.

   Capping Focus stops the agent from spreading thin across every point, which would be shallow again. The next finish attempt re-ranks, so each continuation targets the points that are weakest *now*. The `gap` says this is deepening existing work, not new work, so it agrees with the prompt's "do not add work".

### Shared changes the second check forces

- **`DONE_STATE`** moves to `vidbyte/lib/jev/done/state.py` and is rewritten so that it holds true for every combination of enabled checks (skill step 11). `request` is always present; `deliverables` and `expert_details` are each "present only when …". Both briefs use it. This rewords the multi-part brief's state section, and that section's field descriptions are unchanged.
- **Run-state system prompt.** One existing sentence gains a general exception: "…except where a field's description asks you to name how a careful version of an output the request asks for would handle it". Without it, the prompt's "never add best practices" contradicts the section. The sentence count stays the same, and the change mentions no check.

## Files

- `vidbyte/lib/enums/jev.py`: `EXPERT_DEPTH`, `EXPERT_DEPTH_HANDLED`.
- `vidbyte/lib/dataclasses/jev.py`:
  - payloads `JevExpertDetailPayload`, `JevExpertDepthDeliverablePayload`, `JevExpertDepthPayload`, `JevExpertDetailEvidencePayload`, `JevExpertDepthEvidencePayload`;
  - records `JevExpertDetail`, `JevExpertDepthDeliverable`, `JevExpertDepth`, `JevExpertDetailEvidence`, `JevExpertDepthEvidence`;
  - an optional `expert_depth` field on `JevRunStateRecord` and `JevHandoffRecord`.
- `vidbyte/lib/constants/jev.py`: threshold, focus limit, min and max details, and the `JEV_DONE_EXPERT_DETAILS_FIELD`, `_DETAIL_`, `_SHALLOW_VERSION_`, and `_DONE_WHEN_FIELD` names.
- `vidbyte/lib/jev/done/expert_depth.py` (new): `ExpertDepthHandledQuestion`. `state.py` (new): `DONE_STATE`. Also `multi_part.py`, `done.py`, `__init__.py`, and `README.md`.
- `vidbyte/agents/jev/done/run_state.py` and `handoff.py`: `_SECTIONS`, `_record`, `_section`, `_judge`, and `_expert_depth`.
- `vidbyte/agents/jev/continuation/done.py`: the `_explain` case.
- `vidbyte/prompts/prompts/jev_run_state/system_prompt.md`: one sentence.
- Exports: `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`.
- `tests/test_jev_done.py`, `skills/jev-continuation/SKILL.md`, and `skills/jev-agent/SKILL.md` (if the steps change).

## Risks and open questions

- **Scope creep.** The writer might list "expert" extras the user never wanted. This is mitigated three ways: the section requires every detail to sit inside a requested deliverable, it must never conflict with `what_not_to_do`, and the gap forbids new outputs. `max_continuations` bounds the cost.
- **Padding.** Forcing 3–5 details on a trivial deliverable invents weak points. The section tells the writer to omit deliverables with no depth to miss.
- **Batch size.** Many deliverables times up to 5 details makes many questions in one request (T15). The focus rule names the id; no cap is added now.
- **Thresholds are untuned** (strategy 25).
- **Merge overlap with draft #473** (faithful scope). It touches the same `match` blocks, enums, and records. Whichever PR lands second rebases.

## Verification

- `python scripts/test-jev-multipart-done-criteria.py` runs all of `tests/test_jev_done.py`. The new tests cover:
  - schema sections;
  - 4–6 sentence descriptions;
  - the record rules: 3–5 details, unique ids across deliverables;
  - the question layout, the minimal pair, at least 2,000 tokens, and one literal per section;
  - `DONE_STATE` naming both fields;
  - pass, and fail with weakest-first `incomplete` and a Focus capped at 3;
  - handoff id mismatch fails open;
  - no deliverables passes with no Jev question;
  - both checks enabled produce one request with both keys and prefixes.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `--stage package`, with no lint baseline increase.
