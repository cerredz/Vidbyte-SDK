# Jev run brief

## What and why

Mid-run dynamic compute will let Jev decide, between the main agent's iterations, whether a run gets extra compute (helper agents, fresh contexts, fan-out). Jev can only decide well if its state captures what the agent is working on right now. The raw run is too long to send at every checkpoint, and a raw tail loses the plan the agent stated twenty iterations ago.

The run brief is a small, structured, verified record of the agent's current work: its goal, its current step, the next steps it stated and has not done, the items it is working through, the approaches it tried and how they turned out, and the failures still open. A separate, cheap, tool-free agent keeps it up to date incrementally, and code computes exact run facts (call counts, repeats, error streaks, token growth) beside it.

This PR builds the brief as a standalone component with no effect on any run. A later PR attaches it to `JevAgent` behind a compute setting.

## How it works

`JevRunBriefKeeper` owns one brief per run.

1. `begin(request)` resets it for a new run.
2. `refresh_if_due(responses, calls, tokens_used=...)` is called between iterations. Code reads `JevRunFacts` from the run and decides whether a refresh is due:
   - never sooner than `min_gap` iterations after the last attempt;
   - the first brief at iteration `JEV_RUN_BRIEF_FIRST_ITERATION`, so the agent's opening plan is captured;
   - every `every_iterations` iterations;
   - early, on an error streak, a repeated identical tool call since the last attempt, or token growth past a fraction since the last attempt.
3. A refresh numbers the run with the existing `JevRunEventLog`, so the brief cites the same `E14` ids as REQUIRED_SEQUENCE, and gives the writer only the events after the last successful brief. Each event is clipped head and tail, and the window has a total budget: the newest events stay whole, older ones shrink to headers, and the oldest are counted as omitted.
4. `JevRunBriefWriter` is a separate `BaseAgent` with its own fixed system prompt, no tools, a cleared history on every call, and a structured `JevRunBriefPayload` output. It receives the request, the previous brief (or `none`), and the event window, and returns the whole updated brief. Its model, provider, and key are configurable (`JevRunBriefSettings`) so a cheap tier can be used, and fall back to the main agent's.
5. `JevRunBriefVerifier` checks every quote against the full text of the event it cites, after whitespace normalization. Unverifiable quotes are dropped, entries left with no evidence are dropped, and the update is rejected when more than `JEV_RUN_BRIEF_MAX_DROP_SHARE` of its quotes fail or the record is invalid (for example duplicate ids).
6. A verified brief replaces the previous one and advances the event pointer. A writer failure or a rejected update keeps the previous verified brief and leaves the pointer in place, so the next attempt re-reads the same events. Every attempt is reported as a `JevRunBriefUpdate` (status, event range, kept and dropped quotes, writer usage).

The brief records what happened, never what should happen: the writer is told to copy, not to judge, and every claim it makes must be a verbatim quote that code can find.

## Files

- `vidbyte/agents/jev/brief/`: new package. `events.py` (`JevRunBriefEvents`), `facts.py` (`JevRunFactsReader`), `writer.py` (`JevRunBriefWriter`), `verifier.py` (`JevRunBriefVerifier`), `keeper.py` (`JevRunBriefKeeper`), `__init__.py`.
- `vidbyte/agents/jev/settings.py`: `JevRunBriefSettings`.
- `vidbyte/lib/dataclasses/jev.py`: brief payloads (writer output schema) and records (`JevRunBrief`, its quote, item and approach entries, `JevRunBriefWindow`, `JevRunFacts`, `JevRepeatedCall`, `JevRunBriefVerification`, `JevRunBriefUpdate`), and a `JevCount` validation helper.
- `vidbyte/lib/enums/jev.py` and `vidbyte/lib/enums/__init__.py`: `JevRunBriefItemStatus`, `JevRunBriefOutcome`, `JevRunBriefUpdateStatus`.
- `vidbyte/lib/constants/jev.py`: cadence, trigger, size, and verification constants.
- `vidbyte/prompts/prompts/jev_run_brief/` plus `Prompt` keys and the prompts README: the writer's system prompt and update prompt.
- `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`, `AGENTS.md` (JEV file table): document the component.
- `tests/test_jev_run_brief.py`.

## Risks and open questions

- A stale brief: refreshes are periodic. The checkpoint will pair the brief with a raw tail of recent events, so the newest work is never only in the brief.
- Lost events: when a window exceeds its budget, the oldest events in it are counted but not shown. The budget is sized so that this happens only after long gaps, such as repeated writer failures.
- Writer quality: a cheap model may write a thin brief. Verification guarantees that what it does write is grounded; completeness is measured later against full-history decisions.
- Cost: one writer call per refresh, bounded by the window budget and the brief's own caps.

## Verification

`tests/test_jev_run_brief.py` covers settings validation, event windows and clipping, facts, every verifier rule, keeper cadence and triggers, and the success, failure, and rejection paths with a faked writer. Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH`.
