# Jev mid-run compute situations

## What and why

The compute checkpoint keeps a verified run brief between the main agent's iterations. This change has Jev read that brief and recognize which compute situation the run is in, so a later change can act on it:

- **REPEATING**: the agent is retrying an approach that already failed on a problem it has not solved.
- **EACH_OF_SEVERAL**: the agent plans the same work on each of several items.
- **SELF_CONTAINED_STEP**: the agent's next step is a self-contained piece of work a fresh helper could do.

It is observe-only: decisions are recorded on `JevAgent.response.compute_decisions` and nothing acts on them yet. That lets the thresholds be checked against real runs before any compute is spent on them.

## How it works

Jev never answers "would extra compute help?", which is a forecast it answers poorly. Each situation is a set of narrow signs Jev can recognize in the run as it is now, and code does every fact, lookup, and combination around them.

1. **When.** Recognition runs only right after a checkpoint that produced a newly verified brief (`JevRunBriefUpdateStatus.UPDATED`), so Jev follows the brief's cadence and judges the brief that was just verified. A writer outage or a rejected refresh asks Jev nothing.
2. **Preconditions in code** (`JevComputeStates`). Each situation is eligible only when the brief records a subject for it, and code picks that subject so no question searches for it:
   - EACH_OF_SEVERAL: the group with the most pending items, if it has at least `JEV_COMPUTE_EACH_OF_SEVERAL_MIN_PENDING`;
   - REPEATING: the first problem a failed approach targeted that no approach has solved;
   - SELF_CONTAINED_STEP: the soonest stated next step.

   An ineligible situation is recorded with `eligible=False`, and no Jev request is made for it.
3. **One focused request per eligible situation.** Each request carries that situation's small state (the request, its subject fields, and the newest run events from `JevRunBriefEvents.tail`) and its four sign questions. The requests run concurrently.
4. **Sign questions** (`vidbyte/lib/jev/compute/`). Twelve fixed noul questions, four per situation, each written to `skills/asking-jev-questions/SKILL.md` and recognizing one sign:

   | Situation | Signs (gate first) |
   |---|---|
   | REPEATING | same approach as a failed one; same failure again; no new cause offered; the request needs the problem solved |
   | EACH_OF_SEVERAL | the plan applies the same work to each item; each item stands on its own; the work needs its own reading or changing of each item; the request asks for it |
   | SELF_CONTAINED_STEP | the step takes its own tool calls; its words with the request state everything a helper needs; its result can be handed back; the request asks for it |

   Every `true` side is the sign being present.
5. **Scoring** (`JevComputeSituations`, `JevComputeRecognizer`). A situation passes when the mean P(yes) reaches its threshold (0.8), no sign is below its veto (0.3), and its gate sign reaches the threshold on its own. A missing answer or an unavailable Jev never passes. `JevComputeDecision.situation` is the first passing situation in priority order: REPEATING, then EACH_OF_SEVERAL, then SELF_CONTAINED_STEP.
6. **Settings.** `JevComputeSettings.situations` enables situations (all by default), validated and normalized into priority order by `JevComputeRegistry.validate`. An empty tuple keeps the brief and asks Jev nothing.

## Files

- `vidbyte/lib/jev/compute/`: `state.py` (shared sentences), `repeating.py`, `each_of_several.py`, `self_contained_step.py` (questions), `situations.py` (`JevComputeSituations`), `compute.py` (`JevComputeRegistry`), `README.md`.
- `vidbyte/agents/jev/compute/`: `states.py` (`JevComputeStates`), `recognizer.py` (`JevComputeRecognizer`), and the controller's recognition step.
- `vidbyte/agents/jev/brief/events.py`: `tail`, the newest events for a question's state.
- `vidbyte/agents/jev/settings.py`, `agent.py`, `response.py`: `situations`, the decision config passed to the controller, and `compute_decision`.
- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/constants/jev.py`: `JevComputeSituation`, `JevComputeQuestionKey`, the question base and records, thresholds, preconditions, and state field names.
- Docs: Jev README, jev-agent skill, AGENTS.md JEV table.
- `tests/test_jev_compute_situations.py`; `tests/test_jev_compute.py` pins its brief-only tests to no situations.

## Risks and open questions

- Thresholds are uncalibrated starting points. They are per-situation constants so they can be fitted separately once logged decisions are labeled (T17, T23 in the question skill).
- A plan stated between brief refreshes is seen only at the next refresh; the brief's cadence and early triggers bound the delay.
- Each eligible situation costs one Jev request of four questions of roughly 1,000 to 1,300 tokens, at most three requests per refresh.

## Verification

`tests/test_jev_compute_situations.py`:
- the question set and its shape: registry completeness, gates, noul options, verdict-first criteria, fields described in the state, at least 500 tokens each, and one literal per section;
- settings normalization;
- every state precondition;
- scoring: pass, veto, gate at and below the threshold, outage, missing answer, and priority choice;
- the record invariants;
- the checkpoint asking only after a verified refresh and only when situations are enabled.

Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH` and every file tracked.
