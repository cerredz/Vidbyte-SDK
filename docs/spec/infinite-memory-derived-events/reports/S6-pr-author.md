# S6 PR author report: infinite-memory-derived-events

- **Stage:** S6, the last stage. No source changed.
- **Branch:** `feat/infinite-memory-derived-events`. HEAD went from `cdf75a62` to `edb0f3bc` (`docs(spec): finalize infinite-memory-derived-events for PR`), which is pushed.
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1191. It is still a draft, its base is `main`, and it has a new title and body.
- **Produced:** `pr-body.md` (title line plus body) and `spec.md`, whose frontmatter now reads `status: pr-open` and whose §17 gains the S6 row. This report is left uncommitted for the orchestrator, as earlier stage reports were.

## 1. What the code does (written from the diff, before the spec was opened)

The scratch note `s6-code-first.md`, in the session scratchpad, was written before the spec was opened. This is its content.

`InfiniteEventKind` grows from 14 to 22 values. The new ones, in order, are `memory_committed`, `verifier_started`, `verifier_finished`, `subagent_aborted`, `batch_finished`, `handoff_written`, `workspace_usage`, and `agent_progress`, all appended after `tool_refused`. There are three new enums: `InfiniteRefusalRule` (23 members), `InfiniteRefusalSource` (`tool`, `middleware`), and `InfinitePairPhase` (`generator`, `verifier`, `commit`). There are 8 new details records, and 8 existing ones gain fields:
- run finished: +11
- run stopped: +`events_failed`
- refusal: +`rule`, `source`
- launched: +7
- finished: +4
- memory saved, staged, and file written: +4 quota fields each

Where each event comes from:
- **`InfiniteMemoryRuntime`**
  - It keeps the root launch tool in `_launch` and a high-water mark `_announced`.
  - The hook renders the map once. It then announces the denied launch calls among `state.call_contexts[_announced:]` (through `InfiniteLaunchTool.denials`: tool name `launch_subagent`, state DENIED, and a result whose metadata names `limit`). After that it calls `workspace_usage(workspace, map_text)` and `agent_progress(settings, state)`.
  - After `super().arun` returns, a catch-up reads `result.metadata["tool_calls"]`, because the loop's last turn skips the hook.
  - `run_finished` now takes the workspace, so it can count the notes created in the run (`descriptions(run_id)`).
- **`InfiniteLaunchTool.execute`**
  - The batch offset is `len(journal.started)`, read before the batch.
  - `subagent_launched` gets the offset, the index among the batch's new pairs, and the number of new pairs.
  - `batch_finished` follows a pipeline that returned, with `replayed = len(cards) - len(pairs)`.
  - `_check` raises with `details={"rule": …}`, and `batch_rejected` now receives the exception.
- **`InfinitePair.run`**
  - A local `phase` moves from GENERATOR to VERIFIER to COMMIT, and the inner error branch sets COMMIT first.
  - Denials in the generator's reply are announced before `generator_finished`.
  - `verifier_started` comes before the verifier runs, and `verifier_finished` after its verdict.
  - `_commit(checker)` announces each commit and each rule drop under the verifier.
  - `_finish(last, …)` announces each unchecked drop under the last agent that ran.
  - An outer `except BaseException` announces `subagent_aborted(pair, exc, phase)` and re-raises the same object.
- **Memory tools and workspace**
  - The memory tools pass the exception itself to `tool_refused`.
  - The rule comes from `error.details["rule"]`. Without one, the error's type decides: `ConfigurationError` gives `invalid_arguments`, `UnicodeError` gives `text_encoding`, `OSError` gives `disk`, and anything else gives `other`.
  - The workspace raises carry the rule, and their messages are unchanged.
  - A new static `map_omitted` reads the map's closing "… and N more files" line.
- **Journal:** a read-only `started` property.
- **`run_handoff`:** a fresh `InfiniteEvents` announces `handoff_written` after the atomic write.

`InfiniteEvents` keeps this state:
- `_launched`: start times by key, for both pairs and verifiers.
- `_in_flight`: changed just outside the shield. An abort decrements it only when the journal has no finish for the pair.
- `_failures`: counted in `_shielded` and reported as `events_failed`.
- `_opened`: when the writer was built, for the session's duration.
- `_level`: the last `(level, map is cut)` pair offered, stored before delivery.

With no sink, every public method returns on its first line.

Nothing changes in `vidbyte/agents/runtime.py`, `base.py`, `vidbyte/middleware/`, `vidbyte/pipelines/`, `vidbyte/__init__.py`, `contracts/`, or `lint/`. I checked this with `git diff --name-only`, and the S4 review confirms it.

## 2. Spec vs code: deviations found

I compared the code against spec §4, §5, §8 (D-1 to D-23, §8.5), §9, and §12.3.
- **Real deviations.** All four are the S3 ones already in §17 r5, and the PR body lists them:
  1. `_in_flight` changes sit just before `with self._shielded(...)`, at `events.py:333`, `:421`, and `:464`. D-9 (spec.md:364) and §12.3 row 5 say "first statement inside the shield". A007 counts literals inside a shield body as operational, and it is exactly at its baseline of 255. The behavior is the same.
  2. The counters start at `INFINITE_MIN_COUNT`, not a bare `0`.
  3. `tool_refused` passes `str(error)` inline.
  4. Two commits the spec did not list: `542124fa` (I001 import sort) and `939381ec` (PURPOSE header lines).
- **§4:** the snippet runs as written. No change was needed.
- **§5:** it matches the code, so it is unchanged. Its "InfiniteEvents (one per run)" is loose, because the object is per session and `run_handoff` builds its own. EC-16 says so, and that is not a drift in the code. The PR's diagram says "one per session".
- **§8.5 and §9.1:** every signature, field, type, and order matches. The workspace has 18 raises plus the existing `_entry_lines` details, which is 19 sites; memory has 6.
- **Spec text left stale by deviation 1:** D-9 (spec.md:364) and §12.3 row 5 still describe the inside-the-shield placement. §17 r5 records the deviation, and I did not edit D-9 (S6 may edit only the frontmatter, §5, and §17).

## 3. The snippet's real output

Command: `PYTHONPATH=$(pwd) python <scratchpad>/run_snippet.py <worktree>`.
- The script reads the §4 code block out of `spec.md` and runs it with `exec`, so the code it runs is the spec's text byte for byte.
- It runs in a fresh temp folder under the pack's `ScriptedTree`, and the script is `_snippet_tree` from the AC-1 test. Only `BaseAgent._runner_for_model` is scripted, and no network is used.

```
---- snippet stdout ----
root: tool refused (duplicate_task)
#1 committed by root/p/ver: Acme charges 49 USD per seat
1 1 0
---- stream (kind, agent_key, summary) ----
run_started          root           Run started: Compare the list prices of our five competitors.
batch_rejected       root           launch_subagent refused for root: Two tasks are named t; give every task in one call its own name.
subagent_launched    root           root launched p: Find the list prices for p.
memory_staged        root/p/gen     p/gen proposed s1 (fact): Acme charges 49 USD per seat
file_written         root/p/gen     p/gen created notes/acme.md: Acme pricing notes
generator_finished   root/p/gen     p/gen: done: P-SUMMARY: Acme is 49 USD per seat.
verifier_started     root/p/ver     p/ver is checking 1 staged entries and 1 notes
verifier_finished    root/p/ver     p/ver: verdict passed
memory_committed     root/p/ver     p/ver committed s1 as memory #1 (fact): Acme charges 49 USD per seat
subagent_finished    root           p: passed, 1 memories saved, 0 dropped, 1 files
batch_finished       root           root: batch 0 finished: 1 passed, 0 fixed, 0 failed, 0 unchecked, 0 replayed
run_finished         root           Run finished (final_response): ROOT-FINAL: Acme is cheapest at 49 USD per seat.
handoff_written      root           Handoff saved to .runs/20261020T185637Z-e0450125.handoff.md
---- handoff file exists: True
---- model calls scripted: 7
```

## 4. Gates I ran myself (at `cdf75a62`)

The commit `edb0f3bc` after it adds only `pr-body.md` and two spec lines.

| Gate | Final lines |
|---|---|
| import path | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py` |
| pack | `418 passed in 8.49s` |
| lint | `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| public API | `contracts/sdk-public-api.json is current at 1332a34e6205ab4c9a86615b0b37462cdd527002 (vidbyte-sdk 0.4.0, 678 exports).` |
| CI source | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 171 == 120`) / `1 failed, 7037 passed, 17 skipped in 217.57s (0:03:37)`. This failure is inherited: `git diff --stat 181f1992..HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads` is empty. |
| CI package (`env -u PYTHONPATH`) | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| AC proof names | Every `file::test[ids]` in spec §6.2 is among the 418 collected items, checked by a script against `pytest --collect-only`. AC-13 also has a third id, `first-commit-fails-from-a-key-error` (R-12). |
| Mermaid | The PR diagram parses with `mermaid@11.4.1` under jsdom (`PARSE OK flowchart-v2`). A deliberately broken line fails, as a negative control. |
| **Merged with main** (extra) | `origin/main` is at `98a5d37b`, 3 commits past the merge base: #1147, #1190, and #1192. The tree from `git merge-tree --write-tree origin/main HEAD` (`1cbda189`) was extracted into the scratchpad, outside the worktree, with no ref changed. There: pack `418 passed in 8.96s`; lint `SDK-LINT: PASS` (in a throwaway `git init` copy, because the lint needs `git ls-files`); API `current at 731f094c… (733 exports)`. GitHub reports `mergeable: MERGEABLE`, `mergeStateStatus: BEHIND`. |

## 5. PR state after the update

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1191 --json title,isDraft,baseRefName,url
{"baseRefName":"main","headRefOid":"edb0f3bcf99580af35b56234a96031039dff6a40","isDraft":true,"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE","title":"feat(infinite): InfiniteMemoryAgent derives 8 more run events from the run and names the rule behind every refusal","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1191"}
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1191
no checks reported on the 'feat/infinite-memory-derived-events' branch
```

- The title has no `[WIP]`, and the PR is still a draft.
- Every workflow has its automatic triggers disabled repo-wide, and nothing was dispatched. To run CI by hand: `gh workflow run ci.yml --ref feat/infinite-memory-derived-events`.
- The body on GitHub equals `tail -n +2 pr-body.md` (checked with `diff`; the only difference is the trailing newline `gh` adds).
- The body was written to the scratchpad, not to `$B.body` in the worktree, so no stray file could be left behind.

## 6. Candidate field-guide lessons (report only; not written to the field guide)

Each candidate follows the guide's shape: When, Do, Because, Check, and Evidence. Each is drawn from a confirmed review finding or from a repo-specific rule that the review relied on. None has been through human review yet.

1. **A007 counts every numeric literal inside an `InfiniteEvents` shield body**
   - **When:** adding a counter change (`+= 1`, `- 1`) to an `InfiniteEvents` method, or any literal inside `with self._shielded(...)`.
   - **Do:** put the change just before the `with` line, after the `on_event is None` return. Start counters at `INFINITE_MIN_COUNT`, never a bare `0`.
   - **Because:** the shield body calls `_deliver(..., depth, ...)`. A007 sees the name `depth` near the literal and counts it as operational, and A007 sits exactly at its baseline (255).
   - **Check:** `python lint/run.py --rule A007` stays at its baseline.
   - **Evidence:** PR #1191, spec §17 r5 deviations 1 and 2; S4 conventions lens ("do not move them back inside `_shielded`").
2. **A002 maps the token `attempt` to retries**
   - **When:** an event or record field is named `attempt`.
   - **Do:** pass it as a keyword argument (`attempt=journal.started.count(key)`). Never bind a local named `attempt` or read `self.attempt`. Validate it in a string-name loop (`for name in (..., "attempt", ...)`), and put a `# @intent` within 20 lines of the `def`.
   - **Because:** A002 scans every `ast.Name` and `ast.Attribute` for retry words and demands an `@intent` block nearby.
   - **Check:** `python lint/run.py --rule A002` stays at its baseline.
   - **Evidence:** PR #1191, spec R-18; `events.py:335` (`@intent an-attempt-counts-journal-starts`).
3. **Prefix citations of a second spec in module headers**
   - **When:** a module header already cites one spec's `EC-`/`FR-` ids, and a new change cites another spec's.
   - **Do:** write `(derived-events EC-10)` and keep the bare ids for the first spec. Keep the header field on one line.
   - **Because:** the two specs reuse ids for different cases. `events.py` cited "(EC-10)" for two unrelated rows, and `launch.py` cited old EC-37, which says the opposite of the new sentence.
   - **Check:** `grep -o '(EC-[0-9]*)' <header line>`, and compare each id with the spec that RELATED DOCS lists first.
   - **Evidence:** PR #1191 review R-9 (R-V2), fixed at `41f420c5`.
4. **A header's TESTS line names the test files that prove this change**
   - **When:** a change adds behavior to a module (a raise site's `details`, a property, a static helper) and new test files prove it.
   - **Do:** add those files to the module's one-line `TESTS:` field in the same PR.
   - **Because:** A001 requires the field, and agents run the TESTS command before editing. A stale line points them at tests that cannot fail on the new behavior.
   - **Check:** `grep -n '^TESTS:' <touched modules>` names a file that exercises each new symbol.
   - **Evidence:** PR #1191 review R-10 (R-V3), fixed at `369e901e`.
5. **The lint's pass banner is `SDK-LINT: PASS`**
   - **When:** a spec, test plan, or gate check quotes the lint's last line.
   - **Do:** quote `SDK-LINT: PASS` (from `lint/core/report.py:58`).
   - **Because:** a spec that says `AGENT-LINT: PASS` can never be met verbatim, and a stage that greps for it reports a false failure.
   - **Check:** `python lint/run.py | tail -1`.
   - **Evidence:** PR #1191 review R-11 (R-V4), fixed at `e7dd0ef8`.
6. **A child agent's error always reaches its caller as a `VidbyteSdkError`**
   - **When:** code that runs a child `BaseAgent` (a pair, a swarm, a sub-agent tool) labels or catches the child's failure.
   - **Do:** catch `VidbyteSdkError`, and name the original with `type(err.__cause__ or err).__name__`.
   - **Because:** `BaseAgent._generate_reply` (base.py:965-979) wraps every other `Exception` as `AgentExecutionError ... from exc`, and passes `UsageAccountingError`, `FailureRaisedError`, and `AllModelsFailedError` through unwrapped. So "always `AgentExecutionError`" is false, while "always a `VidbyteSdkError`" is true. Only the caller's own code can raise past that catch.
   - **Check:** a test whose child runner raises `ToolExecutionError` sees `error_type == "ToolExecutionError"`, not `AgentExecutionError`.
   - **Evidence:** PR #1191 review R-7 and D-22; spec R-1 and R-2 (r1).
7. **When an event kind gains a new cause, update its details record's docstring**
   - **When:** an existing event kind starts firing from a new call site or for a new reason (here, `memory_dropped` for `rule` and `unchecked`).
   - **Do:** in the same PR, rewrite the record's one-line docstring in `vidbyte/lib/dataclasses/<domain>.py` to name every cause. The record is what a consumer's `help()` shows.
   - **Because:** AGENTS.md principle 2 says comments must never describe behavior that is gone. The spec's stale-comment list missed this docstring, so the implementer followed the spec into it.
   - **Check:** grep the record's docstring against the enum of reasons it carries.
   - **Evidence:** PR #1191 review R-8 (R-V1), fixed at `86741ac0`.
8. **A field drawn from a fixed set of constants is validated against that set, not a range** (scope-adding; this needs the user's decision)
   - **When:** a lib record's int field can only hold values from a constant tuple (such as the usage levels 0/50/75/90/100).
   - **Do:** check that the value is in the tuple, or the floor, rather than within `minimum..maximum`.
   - **Because:** AGENTS.md principle 4 asks each record to check "allowed values". A range check accepts 37.
   - **Check:** a record test that builds the record with an in-range but not allowed value expects `ConfigurationError`.
   - **Evidence:** PR #1191 review R-13 (R-V5), left open as a follow-up.

## 7. Things that looked wrong or worth a note while reading (none blocks the PR)

- **Stale comment (test-owned).** `tests/features/infinite_memory_agent/infinite_events_fixtures.py:4` says the module "builds on infinite_memory_fixtures.py and leaves that file unchanged". This PR changed that file: it added `ToolsStep` and `tool_calls`, a +16 −2 diff. The fix is one line, and the S2 test author should make it.
- **Spec text drift.** D-9 (spec.md:364) and §12.3 row 5 still say the `_in_flight` change is "the first statement inside the method's shield". The code and §17 r5 say "just before it". This is text only.
- **`_launched` never drops some start times.** `InfiniteEvents._launched` (`events.py:156`, `:341`, `:393`) keeps the start time of a pair that aborts before `generator_finished`, and of a verifier that aborts before `verifier_finished`. Nothing pops those entries. They are bounded by the pairs per session and live only as long as the per-run writer, so this is harmless. It is not a bug.
- **`_after_tool_iteration` renders the map before its guard.** It now calls `self._map()` before the `context_manager is not None` check (`runtime.py:145`). `arun` always sets a context manager before the loop (`runtime.py:118`), so this is no behavior change.
- **`_announce_denials` runs without a sink.** It filters the call records even when there is no sink (`runtime.py:162`). No event or record is built, so INV-1 holds; the cost is one tuple filter per root iteration.
- **Line budgets are nearly used up.** `events.py` is at 658 of 660 lines after its header, and `launch.py` at 456 of 470. The next event kind needs the Q-1 split (records into their own lib module) or another cap change.
- **No vacuous test found.** The S4 verifier's mutation runs (M1, M7, M10, M11, and the `len(shown)` mutant) are each now killed by one test. I did not re-run them.
