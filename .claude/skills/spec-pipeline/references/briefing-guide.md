# How the orchestrator briefs a subagent

Every subagent starts with an empty context. It has never seen this conversation, the previous subagents' work, or the user. The only things it knows are what the orchestrator writes into its prompt and what it can read from disk. The quality of the pipeline is therefore bounded by the quality of the briefings. This file defines what a briefing is, what it must contain, and what a bad one looks like.

## The shape of every subagent prompt

```
<stage template from ${CLAUDE_SKILL_DIR}/prompts/s<n>-<agent>.md, with every [BRACKET] filled>

=== ORCHESTRATOR BRIEFING (written fresh for this run) ===
1. Where we are
2. What exists right now
3. What you must produce
4. Niche facts for this repo and this feature
5. Decisions already made (do not relitigate)
6. What you must not do in this stage
7. Files you may read under docs/ (and nothing else there)
=== END BRIEFING ===
```

The template carries the stage's procedure and rules; it is the same every run. The briefing carries everything specific to *this* run. Never send a template with an empty briefing, and never send a briefing that only restates the template.

## The seven briefing sections

**1. Where we are.** The stage number and name, what the previous stages produced (one line each, with absolute paths), and what comes after this stage so the agent knows who consumes its output. Example: "S2 of 6. S1 produced the spec at C:/…/docs/spec/api-key-rotation/spec.md (r2, reviewed SOUND WITH FIXES, 3 findings applied). Your output feeds S3, a fresh implementer who will build against the names your tests bind to."

**2. What exists right now.** Worktree absolute path, branch, HEAD SHA, whether the working tree is clean, state of the new tests (none / red / green), the last gate matrix if any, draft PR URL if any. Facts from `pipeline.md`, not from memory.

**3. What you must produce.** The exact files (absolute paths), the exact format (name the section of `report-formats.md`), the commit message pattern, and the final-message contract (`STATUS` block, ≤ 60 lines). Say what "done" looks like in one sentence.

**4. Niche facts for this repo and this feature.** This is the section that makes or breaks the stage. Distill from `context/code-map.md`, the previous reports' "NICHE FACTS FOR THE NEXT AGENT", and `pipeline.md`'s accumulated list. Each fact is one line, concrete, and would cause a fresh agent to make a mistake if omitted. Examples of the right altitude:
- "Enums go in `vidbyte/lib/enums/<domain>.py` and must be exported from `vidbyte/lib/enums/__init__.py`; lint rule S010 fails the gate otherwise (code-map.md §1)."
- "Backend tests for payments have their own pytest config at `backend/tests/payments/pytest.ini`; run them with `python -m pytest backend/tests/payments`, not from the repo root (code-map.md §3)."
- "`python scripts/run_ci.py` in this worktree needs `pip install -e '.[dev]'` first and takes ~6 minutes (code-map.md §1; installed at S2, see test-plan.md "Red run")."
- "The names `KeyRotator.rotate()` and `RotationResult` are a contract from spec §8.5; the tests in `tests/api_keys/test_rotation.py` import them. Do not rename."
- "The field-guide entry `review-scope.md` says reviewers push back on anything that touches `vidbyte/lib/errors/base.py`; the spec deliberately avoids it (spec §8.3)."
Wrong altitude: "follow the repo conventions", "write good tests", "be careful with MongoDB".

**5. Decisions already made.** The user's decisions from `request.md` §C and §0.2 user replies, the spec's `D-` decisions, and the orchestrator's own triage decisions from `pipeline.md`. State each as settled: "The user decided X (request.md §C). Do not reopen it; if you believe it is wrong, say so in OPEN ITEMS and proceed as decided."

**6. What you must not do in this stage.** The stage-specific hard lines, restated for this run with the real paths: e.g. "You may not modify anything under `tests/` — those files were written by the test author and are the contract. If a test contradicts the spec, report BLOCKED with the test name and the spec ID."

**7. Files you may read under `docs/`.** Because `vidbyte` and `vidbyte-sdk` declare `docs/` opaque, list the exact `docs/spec/<slug>/...` files this agent may read, and say "no other file under docs/".

## Rules for writing briefings

- **Absolute paths, always.** Never "the spec", always `C:/Users/…/docs/spec/<slug>/spec.md`.
- **Exact commands, copied.** Never "run the tests", always the command string from `code-map.md` §1 or AGENTS.md.
- **No conversation references.** Never "as discussed", "as you know", "the thing we talked about". The agent was not there.
- **No invented names.** If the conversation coined a nickname for something, define it or use the real identifier.
- **Quote, don't paraphrase, the user.** When the user's words matter (a constraint, a reply sent during the run), paste them verbatim inside a fence.
- **Length is fine; vagueness is not.** A briefing of 60–120 lines is normal. A 10-line briefing is a defect.
- **Carry niche facts forward.** When a subagent's `STATUS` block returns "NICHE FACTS FOR THE NEXT AGENT", append them to `pipeline.md` and include them in every later briefing where they apply.
- **Say who consumes the output.** An agent that knows a fresh reviewer will read its code writes differently from one that thinks it is the last step.

## A bad briefing and a good one (same stage, same feature)

Bad:
```
You are the implementer. Implement the spec in the worktree. Follow repo conventions and make the tests pass. Don't modify tests.
```

Good:
```
1. Where we are — S3 of 6 (implementation). S0 created the worktree at 7f3a2c1; the scout read AGENTS.md and the six files this change touches (code-map.md). S1 wrote the spec (r2, reviewed, 3 findings applied). S2 wrote 14 tests in C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-api-key-rotation/tests/api_keys/ and confirmed they are red (test-plan.md "Red run"). After you, S4 launches three fresh adversarial reviewers who will read your diff against the spec, the field guide, and AGENTS.md, and a repair agent will fix what they confirm.
2. What exists — worktree C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-api-key-rotation on feat/api-key-rotation at 9b1e4d0, clean. Commits so far: spec, request, context, tests. New tests: 14 red, 0 green. No PR yet.
3. Produce — all §12.3 rows of spec.md, committed per work item as "<type>(<scope>): <what> [W-n; FR-n, AC-n]"; tests green via `python -m pytest tests/api_keys -q`; `python scripts/run_ci.py --stage source` green; branch pushed; draft PR opened with the placeholder body; report at reports/S3-implementer.md; STATUS block ≤ 60 lines.
4. Niche facts —
   - Every new enum in vidbyte/lib/enums/api_keys.py and exported from vidbyte/lib/enums/__init__.py (AGENTS.md "Placement Rules"; lint S010 fails otherwise).
   - RotationResult is a frozen validated dataclass in vidbyte/lib/dataclasses/api_keys.py; tests import it by that path (test-plan.md "Notes for the implementer").
   - The nearest sibling is vidbyte/agents/sessions/rotate_session.py — copy its narrated main function shape (code-map.md §2).
   - run_ci.py needs `python -m pip install -e ".[dev]"` once in this worktree; already done by S2 (test-plan.md "Red run").
   - Field guide `strict-config-dataclasses.md`: constructors validate in __post_init__ and raise naming the field; reviewers reject loose Mapping inputs.
5. Decided — The user chose rotation-in-place over a new collection (request.md §C "Key decisions"); spec D-1 records it with flip condition. Do not reopen.
6. Must not — modify anything under tests/; add a dependency; exceed the §8.4 budget (2 new files); touch files outside §12.3 beyond an import or export line (list any in the report).
7. docs/ you may read — docs/spec/api-key-rotation/{request.md, spec.md, test-plan.md, context/code-map.md}. Nothing else under docs/.
```
