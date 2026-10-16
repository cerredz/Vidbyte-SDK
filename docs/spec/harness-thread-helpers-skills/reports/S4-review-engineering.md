LENS: engineering

VERDICT: MERGEABLE AFTER FIXES — The helper layer is careful about keys, bounds, cancellation and SQL, but the Muse anchoredSnapshot evidence path accepts the SDK's own prompt as proof (one Blocker). Three Majors with small, local fixes must also land: Grok agent evidence errors lose the minted id, the test pack fails whenever DEEPSEEK_API_KEY is set, and a quoted flag gets past D-30.

Reviewed: `git diff origin/main...462e6d45` (64 files, +10958/−345; merge base 239c408a). The worktree HEAD is 6eafd6c8, which differs from 462e6d45 only in `docs/spec/harness-thread-helpers-skills/pipeline.md`, so the code under review is identical.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Every helper and evidence child is keyless by construction.**
  - One constant, `NATIVE_HELPER_REMOVED_VARIABLES` (`vidbyte/lib/constants/native_threads.py:453-458`), is passed as `env_remove` by every child role: Grok `delete` and `export` (`grok/helpers.py:229`, `:262`), opencode `_child` (`opencode/helpers.py:239`), and Muse serve, export and init (`muse/helpers.py:247`, `:311`, `:338`). Muse children also get a fresh private config folder.
  - The test pack checks all nine roles (AC-10): dropping `env_remove` from any one role fails a test.
- **Injection surfaces are closed at the boundary.**
  - `NATIVE_THREAD_ID_PATTERN` is applied with fullmatch semantics, so an id ending in a newline is refused (probe below).
  - The opencode `db` query takes only an id that passed that pattern. The parent id is checked too, by `NativeThreadSummary` before `_query(parent)`, so T-9 has no shorter path.
- **One-id reads are separate from strict scans (D-27).**
  - `GrokStore.thread` (`grok/store.py:152-167`) opens only `<group>/<id>/summary.json`, so a corrupt sibling cannot fail a get or an agent check (AC-30 covers this).
  - A missing private home reads as `()` and is never created (EC-1, INV-4).
- **Bounds and cancellation are real, not nominal.**
  - Sizes come from `os.fstat` before any read (`grok/store.py:216-221`, `muse/helpers.py:357-359`).
  - The opencode scan cap raises at exactly 10,000 rows (EC-75, tested with 10,000 seeded rows).
  - Muse private folders are removed in `finally`, and `open_config` is shielded. The cancel tests reap the children.
  - On timeout and on the output cap, the error carries the minted Grok id (`grok/wire.py:115`, `:117`).

## FINDINGS

### R-E1 [Blocker] [failure-modes] vidbyte/harnesses/native/muse/commands.py:149-152 — After compaction, the Muse evidence check is satisfied by the SDK's own prompt

- **Evidence.**
  - In anchoredSnapshot mode, `execute` runs `require_text(transcript, fragment=tool)` and then `require_text(transcript, fragment=<skill id>)` over the whole `muse export` text.
  - That text always contains the user message the SDK itself sent:
    - `MUSE_GOAL_PROMPT_TEMPLATE = "Use the create_goal tool to set this goal, ..."` (`constants/native_threads.py:450`)
    - `MUSE_SKILL_PROMPT_TEMPLATE = "Use the \`{skill}\` skill. ..."` (`:449`)
  - So for `run_muse_goal` the check is a tautology. For every skill function, the skill-id check is a tautology, and the only thing tested is that the word `read_skill` appears somewhere.
  - Repro `repro_muse_goal_anchored.py`, which uses only the repo's stand-in:
    - `[goal, anchoredSnapshot, exec never calls create_goal] RETURNED SUCCESS`, against the inline control `raised muse.command_not_run`.
    - `[plan, anchoredSnapshot, exec reads ANOTHER skill (bundled:import)] RETURNED SUCCESS`, against the inline control `command_not_run`.
- **Failure.**
  - Any Muse run long enough to compact returns success without proof that the goal was set or the skill was read. This is the exact case INV-8 and KD-6 exist to stop, and the caller has paid for the run.
  - A user prompt that mentions "read_skill" also passes with no tool call at all.
  - The pack cannot catch this. AC-34's only negative case (`test_harness_threads_muse_commands.py:116`) drops `read_skill` for `run_muse_plan`. There is no goal case and no other-skill case.
- **Smallest fix.**
  - In anchoredSnapshot mode, apply the inline rule to the export's tool-call items: an item whose tool equals the evidence tool and whose args contain the skill id. If the export's shape cannot be read, fail closed.
  - At minimum, drop the user-message items before the two `require_text` calls.
  - Add negative tests for `run_muse_goal` without `create_goal`, and for `run_muse_plan` reading another skill.
  - S5 should amend the D-33 wording ("the transcript must contain…"). Its literal rule is what makes the check vacuous.
- **Spec IDs:** INV-8, KD-6, D-33, AC-34, EC-79, and the §9.2 rows `run_muse_skill` and `run_muse_goal`.

### R-E2 [Major] [error-handling] vidbyte/harnesses/native/grok/commands.py:243 — Plan and explore evidence errors after a paid run carry `thread_id=None`

- **Evidence.**
  - `GrokStore.thread(..., thread_id=thread_id)` uses the id only as a folder name. It calls `_directories`, `_in_scope` and `_read` (`grok/store.py:156`, `:163`), and these raise `errors.failure(...)` with no `thread_id` (`store.py:121`, `:180`, `:205`, `:221`, `:227`; `GrokHelperWire.thread_file` at `grok/wire.py:197`, `:199`, `:224`).
  - `NativeErrorFactory.failure` falls back to `request.thread_id`, which is None for a RUN request.
  - Repro `repro_grok_plan_evidence_id.py`:
    - `[plan; own summary.json has agent_name of the wrong type] raised grok.protocol_mismatch error.thread_id=None argv --session-id=['143ca336-7e63-4b59-81d5-627419af57fe']`
    - The same happens with a garbled `created_at`.
- **Failure.** The run completed and a thread exists, but the caller gets no id with which to read, continue or delete it. That is the contract INV-29 promises for "every error raised after the child started".
- **Smallest fix.**
  - Pass `thread_id` through `GrokStore.thread` → `_directories`, `_in_scope`, `_read` → `GrokHelperWire.thread_file` and into each `errors.failure`. As an optional keyword, this leaves the helper callers unchanged.
  - Add an AC-30-style case: a malformed own `summary.json` with `error.thread_id == the minted id`.
- **Spec IDs:** INV-29, D-29, INV-8, EC-51.

### R-E3 [Major] [test-quality] tests/features/harness_threads/conftest.py:262-270 — The new tests fail on any machine where DEEPSEEK_API_KEY or ZAI_API_KEY is set

- **Evidence.**
  - The stand-in records digests for `CREDENTIAL_NAMES` (`fake_harness.py:36`, `:179`), which includes DEEPSEEK_API_KEY and ZAI_API_KEY.
  - Ten new assertions require every value to be None, for example `test_harness_threads_grok_commands.py:179`, `grok_helpers.py:142`, `muse_commands.py:54`, `muse_helpers.py:144` and `opencode_helpers.py:59`.
  - The `sandbox` fixture sets USERPROFILE, HOME, PATH and tempdir, but never removes those variables.
  - With DEEPSEEK_API_KEY set: `16 failed, 982 passed, 3 skipped`. With it unset: `998 passed, 3 skipped`.
- **Failure.**
  - `python scripts/run_ci.py` goes red on a developer box or a runner that carries a provider key. Grok and Muse children never use these keys, so the failures are false.
  - The implementation matches INV-2, which names only the four SDK variables. The tests over-assert.
- **Smallest fix.** In `sandbox`, run `monkeypatch.delenv(name, raising=False)` for every name in `CREDENTIAL_NAMES`. Alternatively, assert only over `NATIVE_HELPER_REMOVED_VARIABLES`.
- **Spec IDs:** INV-2, INV-23, AC-10, NFR on a hermetic suite.

### R-E4 [Major] [security] vidbyte/lib/dataclasses/native_threads.py:430-433 — A quoted flag gets past the D-30 refusal

- **Evidence.** `words = self.text.split()` matches the flag exactly or as `flag=`. Probe results:
  - `'ship "--budget" 99999999'` is ACCEPTED.
  - `"ship '--budget=99999999'"` is ACCEPTED.
  - `'ship it --budget 9'` is refused.
- **Failure.**
  - D-30's own rationale cites Grok's hint `--instructions "..."`, a quoted value read as one argument, so Grok's slash tokenizer honors quotes.
  - Under that tokenizer, T-8's hostile forwarded text (an issue title used as a goal) sets `--budget` above `GROK_GOAL_MAX_BUDGET_TOKENS` with two extra characters.
  - This is not verifiable without a real Grok run, which this review may not make. If Grok splits only on whitespace, this finding drops to Minor.
- **Smallest fix.** Strip `"` and `'` from each word before comparing, or also compare `shlex.split(text, posix=True)` tokens. Add the two strings above to the EC-70 cases.
- **Spec IDs:** T-8, D-30, EC-70.

### R-E5 [Minor] [failure-modes] vidbyte/harnesses/native/grok/commands.py:247-248 — Code-review evidence can be met by text that is not the expanded skill

- **Evidence.** `require_text(document.text, GROK_CODE_REVIEW_FRAGMENT)` matches anywhere in the export. Repro: raw `run_grok_command(GrokCommand.CODE_REVIEW, "deep code quality audit of the current branch's changes")`, with the skill NOT expanded, RETURNED SUCCESS.
- **Failure.** Two cases pass without the skill running:
  - a caller line or forwarded text holding the fragment;
  - a tool result that prints a file holding it, such as a review of a branch that touches `constants/native_threads.py`.
- **Smallest fix.** Match only in the transcript's skill or system expansion item, not in user or tool text. If that is not possible, document it as a known edge in the module docstring.
- **Spec IDs:** KD-6, D-28, INV-8.

### R-E6 [Minor] [data] vidbyte/lib/dataclasses/validation.py:196 — An extreme timestamp gives runtime.error, not protocol_mismatch

- **Evidence.**
  - The new `to_utc_datetime` calls `parsed.astimezone(UTC)` uncaught. Probe: `9999-12-31T23:00:00-05:00` and `0001-01-01T00:30:00+05:00` both raise a raw `OverflowError`.
  - `grok/wire.py:211-224` and `muse/wire.py:354-355` catch only `ConfigurationError`, so the `except Exception` guard (`grok/helpers.py:123`) turns it into `runtime.error`.
- **Failure.** A crafted or garbled `summary.json` or Muse session time gives `runtime.error` with no member or path named. Because lists are strict scans, one such sibling breaks every `list_*`, `search_*` and `*_since` for the workspace.
- **Smallest fix.** Catch `OverflowError` alongside `ValueError` and raise the field's `ConfigurationError`.
- **Spec IDs:** INV-6, EC-14, T-2.

### R-E7 [Minor] [error-handling] vidbyte/lib/constants/native_threads.py:817 — The scan-cap next step suggests a remedy that cannot work

- **Evidence.**
  - The message says "narrow the list with list_opencode_threads_since".
  - `OpencodeHelperWire.sessions` raises at `len(rows) >= NATIVE_OPENCODE_SCAN_MAX` (`opencode/wire.py:181`), before any since window or directory filter is applied. The count covers every root session in the project, across every directory.
- **Failure.** A project with 10,000 or more roots can never list from any subfolder by any window. A user who follows the advice gets the same error again.
- **Smallest fix.** Drop the since clause from the next step, leaving "archive or delete old sessions". If the cap should apply after the window, say so in EC-75.
- **Spec IDs:** EC-75, D-19, INV-5 (next step).

### R-E8 [Minor] [error-handling] vidbyte/harnesses/native/muse/helpers.py:361 — Export-file read errors other than "missing" become runtime.error

- **Evidence.** `_export_file` catches only `FileNotFoundError`. Grok's equivalent (`grok/store.py:225-227`) maps every other `OSError` to `store_unreadable` naming the path.
- **Failure.** A `PermissionError`, or a file still locked on Windows or under a WSL path, surfaces as an unnamed `runtime.error`.
- **Smallest fix.** Add `except OSError` and raise `protocol_mismatch` (or `store_unreadable`) naming the path.
- **Spec IDs:** INV-5, EC-38, EC-13 analogue.

### R-E9 [Minor] [test-quality] test-plan.md (no INV-18 row) — The "no blocking I/O on the event loop" rule has no test

- **Evidence.** `grep -n "INV-18\|event loop\|to_thread" test-plan.md` finds nothing. The INV-18 mentions under `tests/` refer to #1036's different INV-18.
- **Failure.** Dropping an `asyncio.to_thread` around a scan, read or removal, for example `grok/commands.py:243` or the Muse export read, passes the whole pack.
- **Smallest fix.** Add one test that runs a helper with `loop.slow_callback_duration` and debug mode on, against a slow stand-in folder, or that patches `Path.iterdir` to assert it is not running on the loop thread.
- **Spec IDs:** INV-18.

### R-E10 [Minor] [security] [scope-adding] vidbyte/lib/constants/native_threads.py:453-458 — opencode helper children still inherit provider keys

- **Evidence.**
  - The removal list covers the four SDK variables only. The opencode `session list`, `export`, `delete` and `db` children inherit DEEPSEEK_API_KEY, ZAI_API_KEY and any other provider key in the parent environment.
  - #1036's run path does the same, so this is not a regression.
- **Failure.** It conflicts with least privilege (T-3, "reaches a helper child that does not need it"), because these children call no model.
- **Smallest fix.** A follow-up that removes opencode's provider key variables from helper children.
- **Spec IDs:** T-3, INV-2, D-18.

## VERIFIED CLAIMS

1. **HELD.** `NativeEnvironmentVariable.PWD.value == "PWD"`, from the `_generate_next_value_` name rule (`enums/native_threads.py`). Checked with the venv Python.
2. **HELD, with a condition.** The test pack passes: 998 passed and 3 skipped with DEEPSEEK_API_KEY unset; 16 failed with it set (R-E3).
3. **HELD.** Every helper and evidence child removes all four SDK key variables (grep of `env_remove=` at the seven call sites above, plus AC-10 across nine roles).
4. **HELD, by code.** Read helpers never create the Grok private home (EC-1). `iterdir` with `FileNotFoundError` gives `()`. No `mkdir` is on a read path.
5. **REFUTED.** INV-29, "every post-launch error carries the minted id": it fails for errors from `summary.json` evidence (R-E2, repro).
6. **REFUTED.** AC-34 / test-plan, "with the call absent → command_not_run": the rule is true for plan with `read_skill` dropped, but run_muse_goal and other-skill reads pass without evidence (R-E1, repro).
7. **HELD.** The opencode run argv only adds `--command`. `stdin_text=request.prompt or None` is unchanged from #1036.
8. **HELD.** The opencode `db` SQL takes only pattern-checked ids, the parent id included (T-9 has no shorter path).
9. **PARTLY REFUTED.** "The D-30 refusals cover the text option flags": quoted flags pass (R-E4).
10. **HELD.** T-1: an id with a trailing newline is refused (fullmatch, not `$`-match).

Three plausible bugs tested against the pack:
- (a) A missing or vacuous anchored evidence branch for goal: NOT caught (R-E1).
- (b) A missing `thread_id` on a plan evidence error: NOT caught (R-E2).
- (c) An off-by-one in the opencode cap or the lineage depth: caught (AC-32 seeds exactly 10,000 rows; AC-6 seeds 64 and 65 links).

Also caught: a dropped `env_remove` on any role (AC-10), and missing backslash folding (the stand-in prints backslash paths).

## COMMANDS RUN

- `git diff --stat origin/main...462e6d45` → 64 files changed, 10958 insertions(+), 345 deletions(-).
- `git diff --stat 462e6d45 HEAD` → only `docs/spec/harness-thread-helpers-skills/pipeline.md`.
- `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python -c "from vidbyte.lib.enums.native_threads import NativeEnvironmentVariable as V; print(V.PWD.value)"` → `PWD`.
- `.../Scripts/python -m pytest tests/features/harness_threads -q -p no:cacheprovider -rf`, with DEEPSEEK_API_KEY set → `16 failed, 982 passed, 3 skipped in 86.89s`.
- `env -u DEEPSEEK_API_KEY .../Scripts/python -m pytest tests/features/harness_threads -q -p no:cacheprovider -rf` → `998 passed, 3 skipped in 86.69s`.
- `env -u DEEPSEEK_API_KEY .../Scripts/python <scratch>/s4eng/repro_muse_goal_anchored.py <worktree> <scratch>/s4eng`. The stand-in served as muse; the key was fake.
  - `[goal, anchoredSnapshot, exec never calls create_goal] RETURNED SUCCESS`
  - `[goal, inline history, exec never calls create_goal (control)] raised muse.command_not_run`
  - `[plan, anchoredSnapshot, exec reads ANOTHER skill (bundled:import)] RETURNED SUCCESS`
  - `[plan, inline history, exec reads ANOTHER skill (control)] raised muse.command_not_run`
- `.../Scripts/python <scratch>/s4eng/repro_grok_plan_evidence_id.py <worktree> <scratch>/s4eng`. The stand-in served as grok; the key was fake.
  - `[plan; own summary.json has agent_name of the wrong type] raised grok.protocol_mismatch error.thread_id=None argv --session-id=['143ca336-7e63-4b59-81d5-627419af57fe']`
  - `[plan; own summary.json has a garbled created_at] raised grok.protocol_mismatch error.thread_id=None argv --session-id=['37da0e5b-…']`
  - `[raw code-review; skill NOT expanded; caller arguments hold the fragment] RETURNED SUCCESS`
- Edge-case probe (venv Python, `GrokCommandArguments` and `RecordFieldConverter.to_utc_datetime`):
  - `refused 'ship it --budget 9'`
  - `ACCEPTED 'ship "--budget" 99999999'`
  - `ACCEPTED "ship '--budget=99999999'"`
  - `refused 'ship it\n--budget 9'`
  - `RAW OverflowError 9999-12-31T23:00:00-05:00`
  - `RAW OverflowError 0001-01-01T00:30:00+05:00`
  - `id with newline refused`
- Read-only greps and `sed -n` over the diff files, the spec, the test-plan and the tests to anchor each line cited above.

`<scratch>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad`. No vendor CLI was run, nothing was installed, and no git state was changed.
