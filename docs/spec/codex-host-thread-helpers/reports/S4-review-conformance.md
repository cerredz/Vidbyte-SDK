LENS: conformance
VERDICT: SOUND — every FR, NFR, INV, AC and §12.3 row traces to code that does what the spec and request.md §C ask, the catalog names are exactly the owner's, and the five findings below are all Minor: spec or text consistency, plus one scope-adding follow-up.

Review range: `git diff c181be65...c81ba632` (18 files under `vidbyte/`, S2's test files, and the spec folder). The pre-existing CodexHost code was read only where the new code calls it: `_guard`, `interrupt_codex_turn`, `continue_codex_thread`'s resume, `CodexConnection.call` and `raw`, `CodexPreflight.require_thread` and `require_idle`, `CodexErrorMapper`, and `CodexResultSerializer._item`.

## WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- **Names, order and the delete rule are exactly as asked.**
  - `CodexHost` gains exactly the 12 methods of §8.5, in §8.5 order, right after `start_codex_review`, with the §8.5 signatures. They are checked with `inspect.signature`.
  - `CodexHostTools(...).names()` has 26 entries, `"delete_codex_thread" in names()` is `False`, and the 11 new tools match the §9.2 tool table on permission, properties, `required` and `additionalProperties: false`.
  - The only mentions of `delete_codex_thread` under `vidbyte/` are the host method, the enum member and three docstrings.
- **"Check that the command actually ran" holds on every exit path.**
  - In `skill_functions.py:106-122` and `:148-166`, the statement after `spawn_codex_thread` returns is the `try:`. Every path out of the read-back sends one `_interrupt(handle)` before it raises: a mismatch, `None` from the deadline or from running out of rounds (`:215-217` → `:161-165`), a `CodexAgentError` (re-raised with the `*_UNCHECKED_MESSAGE` suffix), or any other `BaseException`, cancellation included.
  - The deadline is taken once before the first read and checked before each wait. There is no `asyncio.timeout`, so EC-50 holds. S064 still lists only its 4 baseline findings, none of them in this file.
- **No READ path loads a thread, and no helper runs a spend check (INV-10, INV-33).**
  - The only new `thread/resume` is `CodexThreadHelpers._resume` (`thread_helpers.py:271-276`). Its only caller is `compact` (`:164-166`), and only after `_refuse_unfinished`.
  - The added code calls nothing that reads `account/*`, rate limits, sandbox readiness or `model/list`. `require_idle` is a local registry read.
- **Settled deviations are built exactly as the spec says.**
  - D-9: an empty window returns `tuple({}.values()) == ()` (`thread_helpers.py:115`).
  - D-14: delete runs `require_idle`, the `ACTIVE` refusal and no resume (`:179-192`), so an idle loaded thread is deleted.
  - R-17: `_reject_skill_arguments` refuses `spawn.thread.ephemeral` with `EPHEMERAL_SKILL_MESSAGE` before `list_codex_skills` (`skill_functions.py:179-180`).
  - D-5: argument errors stay `ConfigurationError`.
  - The `CODEX_HOST_INPUT_CHECK_ATTEMPTS` name is the spec's own: §9.3 line 885, INV-34, NFR-5, §12.3 rows 4 and 10. §12.4 forbids renaming it.

## FINDINGS (ranked, most severe first, max 15)

R-C1 [Minor] [weighted words] vidbyte/harnesses/native/codex/thread_helpers.py:189-190 — "`thread/delete` is sent exactly once per call" (INV-19) does not hold on the overload path; the spec contradicts itself and the code follows D-14/EC-24
  Evidence:
  - Spec line 300 (INV-19): "`thread/delete` is sent exactly once per call, through the raw path."
  - Spec EC-24 (line 452): "The SDK retries up to 3 times (raw path, not a spending method)."
  - Code: `delete = connection.raw(CODEX_THREAD_DELETE_METHOD, ...)`. `connection.py:89` has `SPENDING_RAW_METHODS = frozenset({CODEX_REVIEW_START_METHOD, CODEX_GOAL_SET_METHOD})`, so `connection.py:210` returns `send` with openai-codex's default `max_attempts=3` (`openai_codex/client.py:731-746`; `is_retryable_error`, `errors.py:112-121`).
  Failure:
  - Codex answers one `thread/delete` with an overload error, and the SDK sends the delete up to 3 times. Under the lens rule, "exactly once" fails on that path.
  - If A-14 is wrong and the overload came after the delete took, the retry gets -32600 "no rollout found". `_rpc_code("thread/delete", refused=True)` then maps it to `codex.api_error`, so a delete that succeeded is reported as failed.
  Smallest fix: no code change. Reword INV-19 to say one delete per call, which the SDK may resend after an overload refusal (EC-24, A-14). The alternative is A-14's own flip, a single-attempt `thread/delete`, and that is the owner's call.
  Spec IDs: INV-19, EC-24, D-14, A-14

R-C2 [Minor] [deviations] vidbyte/tools/toolsets/codex.py:54 — the `CodexHostTools` class docstring still says "one agent tool per CodexHost function", which is now false, and the reason given for keeping it (S3 deviation 5) does not hold
  Evidence:
  - `codex.py:54`: `"""Catalog of one agent tool per CodexHost function over one host.`. The host now has 27 public functions and the catalog 26 tools (script output: `27` public methods, `26 26 False`).
  - `grep -rn "one agent tool per CodexHost function\|One tool per CodexHost function" tests vidbyte contracts` finds a test pin only for `vidbyte/tools/toolsets/__init__.py:11` (`test_codex_host_packaging.py:249`). Nothing pins the class docstring, and `contracts/sdk-public-api.json` has no `CodexHost` entry.
  - The settled Q-18 covers only the `__init__.py:11` line.
  Failure: `help(CodexHostTools)` tells a developer that every host function, `delete_codex_thread` included, has a tool. That is the opposite of INV-2, and the file's own header (line 3) and comment (line 70) now say otherwise.
  Smallest fix: change the class docstring's first line to "Catalog of one agent tool per CodexHost function, except delete_codex_thread, over one host." Leave the pinned `__init__.py:11` line alone.
  Spec IDs: INV-2, §12.5 (texts must stay true), NG-14 (pins only `__init__.py:11`), §17 deviation 5

R-C3 [Minor] [deviations] vidbyte/harnesses/native/codex/skill_functions.py:66 — an item-type vocabulary value is defined in a feature module, outside §9.3, and is not reported as a deviation
  Evidence:
  - `USER_MESSAGE_ITEM_TYPE = "userMessage"`, used at `:220` (`... if item.type == USER_MESSAGE_ITEM_TYPE`).
  - The same literal already sits inside `CODEX_SUPPORTED_ITEM_TYPES` (`vidbyte/lib/constants/codex.py:85`).
  - §12.4: "Every bound, method name and fixed value is a named constant in `vidbyte/lib/constants/codex.py` ... except message text constants."
  - request.md §C Constraints: "Constants and flags go in `vidbyte/lib/constants/codex.py` ... Never in feature files."
  - Spec §17 deviations 1 to 7 do not mention it.
  - The other new feature-module constants (`FOLDER_PLACE`, `APP_SERVER_PLACE`, `NAME_SEPARATOR`, `MORE_NAMES_TEXT`, `NO_NAMES_TEXT`) are message text that §9.2 itself defines, so they are acceptable.
  Failure: behavior does not change. Two copies of the wire name can drift, and the rule §12.4 and §C state is broken without a record.
  Smallest fix: record it as S3 deviation 8 in spec §17. Moving it into `constants/codex.py` would need a §9.3 row, and it would break S2's pin `test_codex_host_helper_surface.py:288`, which compares the last names of `constants.__all__` with the §9.3 set exactly. That move is a follow-up, not a repair.
  Spec IDs: §12.4, §9.3, request.md §C Constraints

R-C4 [Minor] [§12 rows] vidbyte/lib/constants/codex.py:9 — §12.5's "TESTS lines name the S2 test files" was skipped for three modified files, although the S3 report counts §12.5 as done
  Evidence:
  - `constants/codex.py:9`: `TESTS: python scripts/run_ci.py.`
  - `vidbyte/lib/enums/codex.py:9`: `TESTS: python scripts/run_ci.py.`
  - `vidbyte/agents/codex/result.py:10`: `TESTS: Offline typed-result checks and python scripts/run_ci.py.`
  - Spec §12.5: "`TESTS:` lines of the new and modified files name the test files S2 created in `tests/features/codex_host/`."
  - The other 13 codex files were updated. Commit `7980ebbb` added RELATED DOCS to `result.py` and `enums/codex.py`, but not TESTS.
  Failure: an agent that edits these constants, enums or `CodexResultSerializer.items` is not pointed to `test_codex_host_helper_surface.py` or `test_codex_host_records.py`, which pin them.
  Smallest fix: append the matching S2 files to those three TESTS lines: `test_codex_host_helper_surface.py` and `test_codex_host_records.py`, plus `test_codex_host_thread_helpers.py` for `result.py`.
  Spec IDs: §12.5, NFR-8 (A001 headers)

R-C5 [Minor] [scope-adding] [user's words] vidbyte/harnesses/native/codex/wire.py:561-573 — skill-loading errors that Codex reports are dropped, so a skill run on a broken skill reports "not found" with advice that cannot help
  Evidence:
  - `skills()` reads only `entry.skills`. `SkillsListEntry` also carries `errors: list[SkillErrorInfo]` with `message` and `path` (`openai_codex/generated/v2_all.py:4859-4865, 9815-9821`).
  - `_skill_path` (`skill_functions.py:197-201`) then raises `codex.skill_not_found`, whose next step is "Pick a skill that list_codex_skills reports ...".
  Failure: a user skill whose `SKILL.md` Codex failed to parse appears only under `errors`. `run_codex_skill("that-skill", ...)` then says Codex lists no skill by that name, and the real cause, which Codex did report, is lost. That is weak against the owner's "extensively handle errors for every single function".
  Smallest fix: none in this PR. D-24 fixes the listing's fields, and INV-29 bans paths from error text. The fix would add an error count or a code, so it is `[scope-adding]` and goes to the user as a follow-up (for example, an "N skills failed to load for {place}" sentence in `SKILL_NOT_FOUND_MESSAGE`).
  Spec IDs: n/a (D-24, INV-29 constrain it; request.md §D weighted word)

## VERIFIED CLAIMS

1. **Catalog names (request §C, owner's naming rule): held.** `list_recent_codex_threads`, `list_codex_threads_since`, `search_codex_threads`, `get_codex_thread_lineage`, `list_codex_turns`, `compact_codex_thread`, `delete_codex_thread`, `get_codex_goal`, `run_codex_goal`, `list_codex_skills`, `run_codex_skill` and `run_codex_openai_docs` exist with the §8.5 signatures and in the §8.5 order, and all follow the `<verb>_codex_...` pattern. `CodexHostOperation` values equal the method names.
2. **26 tools, no delete tool: held.** `names()` has 26 entries, `False` for delete, and the 11 new names follow `start_codex_review` in §9.2 order. Permissions: 7 read, then compact, run goal, run skill and run docs as write. This matches the table.
3. **Budget (§8.4): held.** 4 new files (`--diff-filter=A`). 20 new classes: 2 collaborators, the Protocol, 5 records, 1 enum and 11 tools. 0 dependencies: `pyproject.toml` is not in the diff. `host.py` has 891 lines; the new modules have 279, 251, 238 and 211.
4. **Boundaries (§12.3, §14): held.**
   - Exactly the 18 §12.3 files changed under `vidbyte/`.
   - These are untouched: `preflight.py`, `errors.py`, `turns.py`, `oneshot.py`, `native/codex/__init__.py`, `native/__init__.py`, `toolsets/__init__.py`, `REPO_MAP.md`, `harnesses/README.md`, `contracts/`, `pyproject.toml` and `lib/dataclasses/codex.py` (`git diff --stat` output is empty).
   - `git diff c181be65...c81ba632 -- lint/baseline.json` is empty, and so is `git diff 33787d9a..c81ba632 -- tests/`.
   - The added lines hold no `noqa`, `type: ignore`, `nosem`, `skip` or `xfail`.
   - S2's pin edits are exactly the authorized §13 pins: the counts 15 to 26, `RECORD_EXPORTS`, `ENUMS_CODEX_ORDER`, `CALL_LIST` `thread_compact` and `_valid_arguments`. `test_codex_host_threads.py`, `test_codex_host_review_goals.py`, `tests/features/harness_threads` and `tests/test_codex_output_contracts.py` have no diff at all.
5. **The S3 claim that the spec names `CODEX_HOST_INPUT_CHECK_ATTEMPTS`: held.** Spec r3 names it (§9.3 line 885, INV-34 line 358, NFR-5, §12.3 rows 4 and 10). §12.4 forbids renaming it. The read-back is bounded by both the attempts and `CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS` (`skill_functions.py:212-218`). `lint/run.py --rule S064 --all` lists only `runtime.py:722`, `runtime.py:1716`, `transport.py:67` and `transport.py:129`.
6. **INV-33 (only compact resumes): held.** The added code's `resume` and `turn/start` hits are comments, plus `_resume` and its one call site in `compact`.
7. **§9.3 constants, §9.2 codes and next steps: held.** All 21 new constants have the spec's values and are appended to `__all__` in definition order. The 4 `FailureCode`s sit between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY`. The classification rows and the `CODEX_NEXT_STEPS` texts are character-for-character §9.2.
8. **NFR-7 (tool descriptions): held.** Each of the 22 new description constants has 4 sentences. The content rules hold: the listings mention tool-started threads, the query description says title only, the since description says Unix seconds, compact says paid work, open-host only and the unfinished-goal refusal, the turn limit says turns not size and to page with the cursor, and the run descriptions say paid work. No name contains `TOKEN`.
9. **INV-31 (import boundary): held.** Importing `CodexHost` and `CodexHostTools` leaves no `openai_codex*` key in `sys.modules`.
10. **INV-32 (`from_sdk` unchanged): held.** The `result.py` diff adds only `items()`, `Sequence` and the header link.
11. **NFR-8 (comment width): held.** No added `#` line is wider than 72 columns.
12. **S3 deviations 1 to 4, 6 and 7: held, necessary and minimal, and recorded in §17.** Deviation 5 does not hold as a necessity (R-C2). One deviation was not reported (R-C3).
13. **AC-1: held.** The test file's `main()` (`test_codex_host_helper_lifecycle.py:79-95`) is the §4 snippet, character for character. Its only changes are that the test loop replaces `asyncio.run`, plus one added `docs_threads.append`. The calls run in snippet order, and the 7 printed lines are compared exactly (`:100-111`): 3 summary lines newest first (`None` for an unnamed thread), `active 200000`, `completed <answer>`, `1 completed 2` and `26 False`. The deleted docs thread is then gone from the fake. The test passes.
14. **Area suite: held.** `1 failed, 673 passed, 2 skipped`. The one failure is the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` with `assert 148 == 120`, the message §11 records at `c181be65`.
15. **Lint: held** (`SDK-LINT: PASS`; S061 and S063 IMPROVED, left alone). **Public API: held.**
16. **Not re-verified here:** the full `run_ci.py --stage source` and `--stage package` runs, semgrep, and remote CI runs 38893453043 and 38893455393. The orchestrator re-verified them.

**ID walk (prosecution against defense, by ID).**

| IDs | Result | Evidence |
|---|---|---|
| FR-1 to FR-17 | held | FR-16 by the §9.2 catalog table; FR-17 because `list_codex_threads`, `read_codex_thread` and `start_codex_review` are unchanged in the `host.py` diff. |
| NFR-1 to NFR-9 | held | NFR-9: each of the 11 delegating methods is operation, `_guard` and one return. `list_codex_skills` is inline, as the spec allows. |
| INV-1 to INV-18, INV-20 to INV-35 | held | See below. |
| INV-19 | held in code | Its "exactly once" wording is R-C1. |
| AC-1 to AC-43 | held | Every proof test name in §6.2 exists (scripted grep, 0 missing), and the area suite is green apart from the inherited test. |
| EC-1 to EC-50 | handled as specified | EC-24 is R-C1. EC-19 to EC-21, EC-33, EC-41, EC-43, EC-44 and EC-49 are accepted limitations, untested by design. |

How the INV rows hold:
- **Listing walk.** It asks for `limit - len(summaries)` on each page, with `sent` cursors deduped (INV-11 to INV-14).
- **Summary mapping** follows `wire.py` `summary` (INV-15).
- **Lineage** catches only `session_not_found` from ancestors (INV-16).
- **Turns** send `itemsView` full, ascending, with cursor and limit only when set (INV-17).
- **Compact** checks the goal only for `NOT_LOADED`, sends a typed `thread_compact` with no retry, reserves the thread and releases it in `finally` (INV-8, INV-9, INV-18).
- **Run functions**: `replace(spawn, goal=...)` or `replace(spawn, prompt=...)` only (INV-27).

**Request §A, §C and §D.**
- **Nothing asked is missing.**
  - "View recent" maps to `list_recent_codex_threads`.
  - "Sessions in last N time period" maps to `list_codex_threads_since(cwd, since)`. That is the shape of the §E catalog the user accepted; the caller computes `now - N`.
  - The goal "simply" runs through `thread/goal/set`, never through a `/goal` prefix. `turns_page` and the input never add text.
  - Built-in skills are covered by `run_codex_skill` and `run_codex_openai_docs`, and review by the existing `start_codex_review`.
- **No §C decision is reversed.**
- **No scope creep.** Everything added is in §12.3. The run wrappers' spend checks come only from the reused `spawn_codex_thread` (NG-6, settled).
- **Not in this diff:** Prompt 6's "explain the changes" belongs to the pipeline's PR-body stage. The PR body is still the old 15-function text, per the S3 report's "title and body untouched".

**§5 diagram against the real call path.** Each divergence is documentation only, and in each case the code follows the normative INV:
- (a) The flowchart draws "this host busy" as an outcome of `require_thread`. The code runs `require_idle` and then `registry.reserve` before any request (`thread_helpers.py:157-158, 179-180`), as INV-8(a) requires.
- (b) The lineage loop and its quiet stop on a refused ancestor (`_ancestor` returns None) are not drawn. The only drawn outcome of `require_thread` is `session_not_found`.
- (c) Compact and delete's registry hold (INV-9) is not drawn.
- (d) The run branch does not show the own-input, ephemeral and skill-name checks before `host.list_codex_skills` (`skill_functions.py:140-141`).
- (e) The path where the check itself fails (one interrupt, then the original error with the `*_UNCHECKED_MESSAGE` suffix) is in the prose but not in either diagram.
- (f) The sequence diagram's spawn line leaves out openai-codex's own `thread/read` and `thread/goal/clear`, which the §9.2 `run_codex_goal` row lists. That is the pre-existing spawn path.

## COMMANDS RUN

- `git diff --stat c181be65...c81ba632 -- vidbyte` → `18 files changed, 1590 insertions(+), 36 deletions(-)`
- `git diff c181be65...c81ba632 -- lint/baseline.json | wc -l` → `0`. `git diff 33787d9a..c81ba632 --stat -- tests/` prints nothing.
- `git diff --diff-filter=A --name-only c181be65...c81ba632 -- vidbyte` → the 4 new modules. The `+class` count is `20`.
- `git diff --stat c181be65...c81ba632 -- pyproject.toml contracts/ REPO_MAP.md ... lib/dataclasses/codex.py` prints nothing.
- `PYTHONPATH=$(pwd) VPY -m pytest -q -p no:cacheprovider tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` → `FAILED ...test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 673 passed, 2 skipped in 51.81s`
- `VPY -m pytest -q ... test_the_section_4_snippet_prints_its_seven_lines tests/.../test_codex_host_goal_skills.py -k "snippet or deadline or never_recorded or read_back or cancelled"` → `7 passed, 16 deselected in 1.46s`
- `PYTHONPATH=$(pwd) VPY lint/run.py` → `S064 RATCHETED: 4 known finding(s)` ... `SDK-LINT: PASS`
- `VPY lint/run.py --rule S064 --all` → findings at `runtime.py:722`, `runtime.py:1716`, `transport.py:67` and `transport.py:129` only. `SDK-LINT: PASS`.
- `VPY scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 998dc0da... (vidbyte-sdk 0.3.0, 639 exports).`
- A scripted check of `CodexHostTools(object(), max_live_turns=1)`, the public methods of `CodexHost` and `inspect.signature` → `26 26 False`, `27`, `True` (order). It also printed the 12 signatures equal to §8.5 and `openai_codex loaded: False`.
- A scripted print of `specs()[15:]` → 11 rows of permission, properties and required, all equal to §9.2. A scripted sentence count of the 22 new description constants → 4 each.
- `grep` of the `+` lines for `resume|turn_start|turn/start|preflight` and for suppressions or skips. An `awk` check of the `+` lines for `#` lines longer than 72 columns printed nothing. A scripted grep found every §6.2 proof test name, with 0 missing.
- `git status --short` after every run prints nothing. Pytest ran with `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, and `__pycache__` is git-ignored.
