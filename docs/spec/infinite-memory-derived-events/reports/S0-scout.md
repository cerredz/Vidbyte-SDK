# S0 scout report: infinite-memory-derived-events

**Status:** DONE. HEAD is `181f1992`, and I made no commits. I created two files: `context/code-map.md` and this report. I modified nothing else, and I ran no installs, gates, lint, or pytest.

## 1. Planned touch list (from AGENTS.md, REPO_MAP.md, the request, and the module headers)

Expected to be edited:
- `vidbyte/lib/enums/infinite.py`: new kinds, plus enums for the refusal rule and other closed sets.
- `vidbyte/lib/enums/__init__.py`: export the new enums.
- `vidbyte/lib/dataclasses/infinite.py`: new details records, union and DETAILS_TYPES entries, and fields for A3–A8 and D1.
- `vidbyte/lib/constants/infinite.py`: summary templates, plus named constants for the C3 thresholds and E1 throttle.
- `vidbyte/agents/infinite/events.py`: new methods, enrichment, the in-flight counter, and the failure counter.
- `vidbyte/agents/infinite/launch.py`: call sites for A1, A2, A5, A8, B1–B4, and D1 for generators.
- `vidbyte/agents/infinite/runtime.py`: E1, C3, and D1 for the root, plus the A6/A7 inputs.
- `vidbyte/agents/infinite/memory.py`: A4 and A3.
- `vidbyte/agents/infinite/workspace.py`: A3 refusal rules, and the C3 omitted count.
- `vidbyte/agents/infinite/journal.py`: A5 attempt reader.
- `vidbyte/agents/infinite/agent.py`: B5.
- `vidbyte/agents/infinite/README.md`.

Tests and test docs (owned by the S2 test author):
- `tests/features/infinite_memory_agent/test_infinite_memory_events_{records,stream,pairs,lifecycle}.py`
- `test_infinite_memory_contract.py` (budget)
- `infinite_events_fixtures.py` (`AC2_KINDS`)
- the pack `README.md` and `FEATURE.md`

Read only, for derivation:
- `vidbyte/agents/runtime.py`
- `vidbyte/agents/base.py`
- `vidbyte/middleware/pipeline.py`
- `vidbyte/middleware/builtins/delegation_limits.py`
- `vidbyte/pipelines/parallel.py`
- `vidbyte/lib/errors/base.py`
- `vidbyte/lib/tools/arguments.py`
- `vidbyte/lib/tools/filesystem/usage.py`
- `vidbyte/lib/dataclasses/middleware.py`
- `vidbyte/lib/dataclasses/tools.py`

## 2. Files actually read

**Read in full**
- Guidance: AGENTS.md, CLAUDE.md, request.md
- Package: `vidbyte/agents/infinite/` `events.py`, `launch.py`, `runtime.py`, `memory.py`, `workspace.py`, `journal.py`, `agent.py`, `settings.py`, `__init__.py`, `README.md`
- Lib: `vidbyte/lib/enums/infinite.py`, `vidbyte/lib/constants/infinite.py`, `vidbyte/lib/dataclasses/infinite.py`
- Base runtime and middleware: `vidbyte/agents/runtime.py` (in chunks), `vidbyte/middleware/pipeline.py`, `vidbyte/middleware/builtins/delegation_limits.py`, `vidbyte/pipelines/parallel.py`, `vidbyte/lib/tools/filesystem/usage.py`, `vidbyte/lib/README.md`
- Tests: `infinite_memory_fixtures.py`, `infinite_events_fixtures.py`, `test_infinite_memory_events_{stream,records,pairs,lifecycle}.py`, `test_infinite_memory_contract.py`, tests `README.md`, `FEATURE.md`
- Lint: `lint/README.md`, `lint/rules/README.md`, `lint/ruff.toml`, and the S019, S008, S024, A001, A007, A009, and S020 rule modules
- Contracts: `contracts/README.md`
- Field guide (`vidbyte-sdk/`): `init.md`, `local-ci-verification.md`, `runtime-boundaries.md`, `blocking-lint-invariants.md`, `comment-format.md`, `review-scope.md`

**Read in part**
- `vidbyte/agents/base.py`: :872-905, :986-1006, :1265-1331, :1408-1484
- `vidbyte/lib/errors/base.py`: the `VidbyteSdkError`, `ToolExecutionError`, and `ConfigurationError` constructors
- `vidbyte/lib/tools/arguments.py`: :31-53
- `vidbyte/lib/dataclasses/middleware.py`: decision and event records
- `vidbyte/lib/dataclasses/tools.py`: `ToolCall` :267-272
- `vidbyte/agents/settings/loop.py`: :52
- `vidbyte/lib/enums/__init__.py`: header and infinite block
- `vidbyte/__init__.py`: infinite exports
- `contracts/sdk-public-api.json`: infinite names
- `REPO_MAP.md`: :60-115, :175-200, and the JEV table rows
- `lint/core/ruff.py`: SELECTORS
- `lint/baseline.json`: the relevant IDs
- `scripts/generate-sdk-public-api.py`: header
- Field guide `strict-config-dataclasses.md`: headings only
- `test_infinite_memory_handoff.py`: the event and details assertions
- Delegation, verification, resume, workspace, acceptance, and context test modules: test names, and their assertions only where they relate to events

**Line counts only:** `vidbyte/tools/toolsets/infinite.py`, `vidbyte/context/handoff/infinite.py`, `vidbyte/lib/errors/__init__.py`

**Not read:** `scripts/run_ci.py`; the A002, A006, S015, S043, and S044 rule modules; `vidbyte/middleware/README.md`; `vidbyte/agents/README.md`

## 3. Corrections to the areas hint and the gates reference

1. **Budgets.** The request says "events.py at its 400-line budget". That holds only as the test measures it:
   - events.py: 412 by `wc`, 400 after the 12-line header, so 0 lines of room.
   - Dataclasses: 616/604 against 620, so 16 lines of room, not "near".
   - launch.py: 410 by `wc` but 398 after the header against 410, so 12 lines of room, not 0.
   - The request omits a binding rule: `vidbyte/agents/infinite/` may hold at most 9 `.py` files (contract test :484). It holds 9 now, so a split module there fails.
2. **Hint a (E1/C3 in `_after_tool_iteration`).** The hook exists and sees the loop state. But:
   - `events` is a local in `arun` (runtime.py:86), not reachable from the hook.
   - The hook is skipped on the final iteration, after a continued finish attempt or contract rejection (runtime.py:680-688), and on an `after_iteration` abort (:690-697).
3. **Hint b (D1).** The pipeline does record denials (pipeline.py:160-161). But:
   - The list is cumulative and mixed with other middleware's events.
   - `batch_rejected` needs a launch object, which the root hook and the generator path do not hold.
   - A generator that raised has no reply metadata.
4. **Hint c (reply metadata).** The constants are as quoted. Reply metadata has no `model_call_count` and no duration. `tool_call_count` includes internal and denied calls.
5. **Hint d (refusal reasons).** `details=` is supported, but most workspace raises do not pass it, and `OSError`/`ValueError` refusals carry none.
6. **Hint e (attempt).** The journal has no public per-key start count. `_started` is private.
7. **Hint f.** `settings.loop.max_iterations` defaults to 500 in the infinite settings and to None in `AgentLoopSettings`. The map's omitted count is not returned (workspace.py:239).
8. **Re-located line numbers.**

   | Request said | Now at |
   |---|---|
   | launch ~:364 (rule drop) | :364 |
   | launch ~:373 (unchecked drop) | :373 |
   | launch ~:362-366 (commit) | `commit_entry` at :362 |
   | launch ~:267 (error catch) | :267 |
   | launch ~:253 (verifier) | :252-256 |
   | launch ~:158 (pipeline) | :157-158 |
   | agent.py ~:166 (handoff write) | :165-166 |
   | runtime ~:129 (hook) | :129-135 |
   | events ~:251, :261 | `subagent_finished` at :239 |

9. **Gates reference.** It gives `pip install -e ".[dev]"`, then `run_ci.py --stage source`, then `run_ci.py`. Field-guide `local-ci-verification.md` says that from a worktree:
   - the source stage needs `PYTHONPATH=$(pwd)`, or it tests the canonical checkout through the editable install;
   - the package stage must run *without* `PYTHONPATH`.

   Two more facts the reference does not give:
   - No lint rule enforces line length: SELECTORS has no E501, and no `line-length` is set anywhere.
   - "Function length" is only S008 (C901/PLR0912/PLR0915 at Ruff defaults; the default values are unverified).
10. **AC pins.** The request lists four pinned tests: AC-24, AC-2, AC-36, and AC-25. More tests pin exact kind lists or the method set:
    - AC-3 (stream :250) breaks if the root's hook emits on iteration 1.
    - NFR-2 (stream :435-436) requires the public `InfiniteEvents` functions to equal the kind values.
    - Stream :388 compares a sink count against `AC2_KINDS`.
    - Pairs :106, :178, :291, :328, :458, :479, and :560 pin exact lists.
    - Lifecycle :88, :102, :155, :182, :193, and :209 pin exact lists.
