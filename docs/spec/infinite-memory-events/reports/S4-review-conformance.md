LENS: conformance
VERDICT: SOUND — every FR-, NFR-, INV-, AC- and EC- ID and every §12.3 row conforms, both on reading and under test. The §8.5, §9.1 and §9.2 contract that the vidbyte-cli and the Vidbyte backend consume matches the spec in every name, field, enum value and cap. The one departure from a row's wording, the inline handoff line cut, was necessary, is recorded in §17, and gives the same output as the helper on all 3,007 inputs tested.

Reviewed: `git diff 7efceb5504b0d2ac64a3b5874ada635a47ac35cf...24297ccf` on `feat/infinite-memory-events`. HEAD is `50a75ddb`; the commits after `24297ccf` change only `docs/spec/infinite-memory-events/pipeline.md`, so the code under review is `24297ccf`.

WHAT THE IMPLEMENTATION GETS RIGHT

- **The consumer contract matches the spec exactly.**
  - The 14 `InfiniteEventKind` values, `InfiniteDropReason`, `InfiniteFileChange` and `InfiniteStopCause`.
  - The `InfiniteEvent` envelope, 13 details records, 2 item records, and `DETAILS_TYPES`.
  - The caps: summary 280, text 500, path 500, line 120, label 64, key 512, 5 items, and `INFINITE_EVENT_MAX_COUNT` = 2^63−1.
  - The summary templates.
  - The D-25 digest rule (`vidbyte/agents/infinite/events.py:377-381`): `~`, then 16 hex digits, then `/`, then the last 490 characters, which makes 508; `/gen` or `/ver` is then appended, giving 512.
  - Keys are ASCII, as D-24 requires, because task names must match `^[a-z0-9][a-z0-9-]{0,63}$` (`vidbyte/lib/constants/infinite.py:80`).
- **Every event is sent only after the change it reports is saved.**
  - `journal.finish` (`runtime.py:119`) runs before `run_finished` (`:126`).
  - `journal.pair_finished` (`launch.py:381`) runs before `subagent_finished` (`:382`).
  - The commit and the staging step in `memory.py` run before `memory_saved` and `memory_staged`.
  - AC-26 passes.
- **Sink failures are handled exactly as D-3, D-9, INV-7 and INV-36 require, and the §14 "Never" list holds.**
  - `_shielded` catches `Exception` and nothing broader (`events.py:332`). Its log line carries no text (`:333`).
  - A coroutine returned by a sink is closed and counted as a `TypeError` (`:347-348`).
  - `arun` handles `BaseException` by sending `run_stopped` and then re-raising (`runtime.py:120-121`).
  - No `BaseException` catch exists in `InfiniteEvents` or in `InfinitePair.run`.
  - Nothing writes events to disk, and nothing makes a model call.
- **The scope is clean.**
  - Every changed file is a §12.3 row, a new test file, or a file in the spec folder.
  - The tests have not changed since S2 apart from the approved row-22 edit.
  - Lint, semgrep and pyproject are unchanged, and there are no suppression comments.
  - Every module is within its §8.4 cap: `events.py` 400/400, `launch.py` 398/410, `lib/dataclasses/infinite.py` 604/620, `context/handoff/infinite.py` 100/400, and 9 modules in the agent package against a limit of 9.

FINDINGS (ranked, max 15)

R-C1 [Minor] [deviations] vidbyte/context/handoff/infinite.py:106-108 — Handoff list lines repeat `OutputText.truncate`'s cut instead of calling it (deviation 3), and the README still says they call it
  Evidence:
  - §12.3 row 12 (`spec.md:839`) says each list line is cut "with `OutputText.truncate(..., marker=INFINITE_TRUNCATION_MARKER)`".
  - `_lines` instead computes `room = INFINITE_HANDOFF_LINE_MAX_CHARS - len(INFINITE_TRUNCATION_MARKER)` and returns `f"{text[:room]}{INFINITE_TRUNCATION_MARKER}"`.
  - `vidbyte/agents/infinite/README.md:135` ("Shared helpers") still says `OutputText.truncate` "cuts event and handoff text with the infinite marker". The real reason for the inline cut is given only at `README.md:163` (Notes for agents).

  Prosecution: AGENTS.md style 5 says to "have every caller use that helper instead of re-implementing the job inline".

  Defense (it wins, so this is not a Blocker):
  1. Adding the top-level import breaks the package. An in-memory import hook that adds `from vidbyte.lib.outputs.text import OutputText` to this module makes `import vidbyte` fail with `ImportError: cannot import name 'FileSystemToolConfig' from partially initialized module 'vidbyte.lib.dataclasses'`.
  2. Lint A006's diagnostic lists "Adding a local import inside a function to hide the cycle" under `will_not_work`.
  3. The cause is an upward import that predates this PR: `vidbyte/lib/dataclasses/__init__.py:19` imports `vidbyte.context.primitives`. That already breaks AGENTS.md style 3, and AGENTS.md says not to rewrite untouched code in an unrelated PR.
  4. The output is the same. Across 3,007 inputs (lengths cap−1, cap, cap+1 and 2×cap; emoji, CJK and whitespace), `_lines([t])` equalled `OutputText.truncate(" ".join(t.split()), 1000, marker=" … [cut]")` every time.
  5. The deviation is recorded in §17 (deviation 3), and the README's Notes for agents explain it.

  Failure: Nothing breaks today. If `OutputText.truncate` ever changes its cut (a grapheme-safe cut, for example), handoff list lines will quietly keep the old rule, because no test ties the two together. Separately, `README.md:135` tells a reader there is one cut site when there are two.

  Smallest fix:
  - In this PR, reword `README.md:135` to: "`OutputText.truncate` … cuts event text and handoff sections with the infinite marker (handoff list lines repeat its cut inline; see Notes for agents)".
  - Follow-up [scope-adding]: in its own PR, remove the `vidbyte.lib.dataclasses → vidbyte.context.primitives` upward import. Then call `OutputText.truncate` in `_lines`, delete the copy, and add a test that ties the two cuts together.

  Spec IDs: §12.3 row 12, INV-37, AC-33, §17 deviation 3, AGENTS.md style 3/5.

No other finding reached Minor. The candidates I dropped are listed under V-12 to V-15, with the reason for each.

VERIFIED CLAIMS

- **V-1 — AC-1, §4 snippet.** `test_section_4_snippet_prints_the_two_run_events_and_the_nine_handoff_titles` (`tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py:131`) runs the §4 snippet word for word, with a `ScriptedTree` standing in for the model. It compares stdout byte for byte with the three lines in the spec, and it passes.
- **V-2 — §5 against the real call path.**
  - The flowchart and the sequence diagram match the real order: the clash check, then the journal, then `InfiniteEvents(on_event, run_id)` (`runtime.py:86`), then `run_started` or `run_resumed` (`:88-90`), then the loop inside `try`, then `journal.finish`, then `run_finished`; `run_stopped` is sent on `BaseException`.
  - In `launch.py`, the order is `batch_rejected` (`:138`), then `pair_started`, then `subagent_launched` or `subagent_replayed` (`:153`), then `generator_finished` (`:241`), then the commit or a RULE drop (`:364`), then UNCHECKED drops (`:373`), then `pair_finished` and `subagent_finished` (`:381-382`).
  - The only difference is deviation 3: the line cut sits in the context module, and the section cut is in `agent.py:169-172`.
- **V-3 — §8.5 and §9.1/§9.2 names, fields, caps and templates.**
  - Every public `InfiniteEvents` method signature matches §8.5.
  - Each details record's fields, their types, which fields may not be blank, and their caps match §9.1.
  - The template strings in `vidbyte/lib/constants/infinite.py` match the spec character for character.
  - `scripts/generate-sdk-public-api.py --check` reports the contract is current with 647 exports.
- **V-4 — D-25 key digest.**
  - `events.py:377` sets `room` to 512 − len("/gen") = 508.
  - `:380` builds the head from the mark, 16 hex digits and `/`, 18 characters in all.
  - `:381` keeps the last 508 − 18 = 490 characters, then appends the suffix.
  - A key of 508 characters or fewer is returned unchanged, and `root` never changes. This matches D-25 and EC-30 exactly.
- **V-5 — Deviation 1 (text-list items are refused under the list's own name).** Necessary.
  - The AC-30 check in `test_infinite_memory_events_records.py:369` requires the error to name exactly `f"{record}.{field}"`.
  - `require_text_items` with `max_chars` or `pattern` names `field[index]` instead.
  - So two calls, a `require_text_items(max_items=N)` check followed by a `require_text` on each item, is the smallest way to meet AC-30.
- **V-6 — Deviations 2 and 4 (packing to fit the line budgets).** Accepted. Both change layout only: `lib/dataclasses/infinite.py` is 604 of 620 lines and `events.py` is 400 of 400. No logic or validation was dropped; the records tests all pass and `lint/run.py` passes.
- **V-7 — Deviation 3 (inline cut).** Necessary and minimal; see R-C1. The import-hook reproduction and the 3,007-case comparison are independent of the implementer's own claim. INV-37 and AC-33 hold.
- **V-8 — Deviation 5 (the journal uses RecordFieldConverter).** Accepted. `journal.py` `_parse` checks `answer` with `require_instance(..., str, optional=True)` and `files` with `to_tuple(..., item_type=str)`. A record of the wrong type still becomes the existing bad-record `ConfigurationError` with its line number (EC-20). The pack tests pass.
- **V-9 — Deviation 6 (generator duration keyed by the agent key minus `/gen`).** Accepted.
  - The launch time is stored under `f"{launch.key}/{card.name}"`. The generator's memory key minus `/gen` (`events.py:229`) is the same string.
  - When no launch time is known, the duration is `INFINITE_MIN_COUNT`, which is `0` (`vidbyte/lib/constants/infinite.py:34`). That is the default AC-37 (f) expects.
- **V-10 — Budget and boundaries (§8.4, §12.3, §14 "Never").**
  - Line counts after the header: `events.py` 400, `launch.py` 398, lib records 604, `workspace.py` 353, constants 301, `memory.py` 277, `settings.py` 205, `journal.py` 186, `agent.py` 173, `runtime.py` 131, `context/handoff/infinite.py` 100, enums 100.
  - Changed files are limited to the §12.3 rows, the new tests and the spec folder.
  - `git diff --stat 1944edab..24297ccf -- tests/` is empty.
  - There is no `noqa`, `type: ignore`, `nosemgrep` or `pragma` in the vidbyte diff.
  - Lint passes. I001 is 0 on every touched file except `vidbyte/context/__init__.py`, which shows 1 both at HEAD and at the base, so that finding predates this PR.
- **V-11 — Request fidelity (request.md §A and §D).**
  - Every behavior the request asks for is present. No §C decision is reversed.
  - Logging a sink failure where §C says "swallowed" is D-3 and was already decided.
  - Nothing from NG-1..NG-13 was implemented.
- **V-12 — NFR-2 (no sink, no cost); not a finding.**
  - `runtime.py:90` builds the tuple of extra tool names at the call site before `run_started` returns early. That costs one tuple over the extra tools.
  - NFR-2's measurable checks pass: 0 `InfiniteEvent` objects and 0 log records with `on_event=None` (AC-20).
- **V-13 — The two commit-message ID slips (`8cd15dab` cites AC-15, `72f1f56d` cites FR-14); not a finding.** The code, the test docstrings and §17 carry the right IDs, and the squash merge replaces these messages.
- **V-14 — A `KeyboardInterrupt` raised by the sink during `run_started`; not a finding.** It escapes before the `try`, so no `run_stopped` follows. That matches D-9, which says `run_stopped` follows only "after the opening event". INV-7 and EC-2 are tested in `test_a_keyboard_interrupt_raised_by_the_sink_is_not_swallowed`.
- **V-15 — The full test suite.**
  - Apart from the known `harness_threads` surface file, the suite gives 6110 passed and 16 skipped.
  - One earlier `-x` run failed `tests/test_mcp_stdio_transport.py::...test_cancelled_waiter_does_not_break_transport` under load. That file is untouched by the diff, it passed 22/22 three times on its own, and it passed in the full rerun, so the failure was a flake.
  - The 3 `test_harness_threads_surface.py` failures do not come from this PR:
    - **Root `__all__`:** the test compares `vidbyte.__all__` with `git merge-base origin/main HEAD` = `c04e5ef5`. The stacked base `7efceb55` is not yet on origin/main and already adds 9 `Infinite*` root names.
    - **vidbyte/tools:** the reported `vidbyte/tools` changes are the stacked base's; this PR's diff on `vidbyte/tools` and `vidbyte/lib/configs` is empty.
    - **Failure codes:** origin/main's `FailureCode` now has 148 members against the test's pinned 120, and this PR does not touch `failure.py`.

COMMANDS RUN

All commands ran from the worktree with `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1`. Final lines are shown.

- `git diff --stat 1944edab..24297ccf -- tests/` → (empty)
- `git diff --name-only 7efceb55...24297ccf` against the §12.3 rows, plus a grep of the vidbyte diff for `noqa|type: ignore|nosemgrep|pragma` → every file is a row, a test or the spec folder; 0 suppressions
- `python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_record_field_validation.py tests/test_output_text_truncate_marker.py tests/test_handoff_agent.py tests/test_create_handoff_tool.py tests/features/harness_threads/test_harness_threads_records.py -q -p no:cacheprovider` → `309 passed in 7.09s` (an earlier, narrower selection gave `281 passed in 7.54s`)
- `python -m pytest tests -q -p no:cacheprovider --deselect tests/features/harness_threads/test_harness_threads_surface.py` → `6110 passed, 16 skipped, 9 deselected in 104.83s`
- The same command with `-x` → `1 failed, 5054 passed, 15 skipped, 9 deselected` (the MCP stdio flake)
- `python -m pytest tests/test_mcp_stdio_transport.py -q -p no:cacheprovider`, run 3 times → `22 passed in 2.23s` / `2.21s` / `2.32s`
- `python -m pytest tests/features/harness_threads/test_harness_threads_surface.py -q -p no:cacheprovider` → 3 FAILED (failure codes 148 == 120; tools diff from the stacked base; root `__all__` against origin/main `c04e5ef5`)
- `git merge-base origin/main HEAD` → `c04e5ef5`; `git merge-base --is-ancestor 7efceb55 origin/main` → not an ancestor
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS` (exit 0)
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 52249854… (vidbyte-sdk 0.3.0, 647 exports).`
- I001, file by file, at HEAD and at the base → 0 on every touched file except `vidbyte/context/__init__.py`, which is 1 at both
- An in-memory import hook (a `sys.meta_path` loader that adds `from vidbyte.lib.outputs.text import OutputText` to `vidbyte.context.handoff.infinite`), then `import vidbyte` → `ImportError: cannot import name 'FileSystemToolConfig' from partially initialized module 'vidbyte.lib.dataclasses'`
- `python <scratchpad>/s4_conf_cut_equiv.py` (a differential check of `_lines` against `OutputText.truncate`, written outside the repo) → `cases=3007 mismatches=0 cap=1000 marker=' … [cut]'`
- A line count after the A001 header for each §8.4 module → the counts in V-10
