# S4 findings verifier — claude-thread-functions

Diff verified: `origin/main...0a2752dd` (merge base `b28c3027`; HEAD `dd5db847` differs only in `pipeline.md`). Output: `docs/spec/claude-thread-functions/review.md`. No source, test or spec file was edited, and no git state was changed. The real `claude` was never run, and no real key was used. Every probe set `HOME` and `USERPROFILE` to a temporary folder (except the relative-home probe, which sets them to `relhome` under a temporary parent folder). Every probe also removed all `ANTHROPIC_*`/`CLAUDE*` variables and called a Python stand-in through an explicit `*_command`. Afterwards, `~/.vidbyte/claude-configs` does not exist in the real home.

My own probe scripts are in `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\c726d777-284c-4c17-9776-72f9da8a13f9\scratchpad\s4verify\`:
- `standin_v.py` and `probe_v.py`. The second takes `wire | print_then_hang | surrogate <claude|opencode|grok> | relhome`.
- `fixcheck\wire_fixed.py`, the patched `ClaudeWire.read` for R-1 and R-3.
- `fixcheck\fixplug.py` and `fixcheck\surrplug.py`, pytest plugins that apply the R-1/R-3 and R-2 fixes in memory.
- `fixcheck\check_fixed.py` and `fixcheck\check_surrogate_fixed.py`.

I read the reviewers' `s4eng` scripts but did not run them as evidence; my drivers are separate.

## 1. Merge map

| Original ID(s) | Lens | Original severity | Merged ID | Final disposition |
|---|---|---|---|---|
| R-C1 | conformance | Major | R-1 | CONFIRMED Major |
| R-E1 | engineering | Major | R-2 | CONFIRMED Major (Claude-only fix verified) |
| R-E3 | engineering | Major | R-3 | CONFIRMED Major |
| R-V2 | conventions | Major | R-4 | CONFIRMED Major (part (b) needs S2 test change + AC-23 change) |
| R-V1 | conventions | Major | R-5 | DOWNGRADED to Minor (follow-up) |
| R-E2 | engineering | Major | R-6 | DOWNGRADED to Minor (follow-up for the user) |
| R-C2 | conformance | Minor | R-7 | Minor, trivial (spec text) |
| R-V6 | conventions | Minor | R-8 | Minor, trivial |
| R-V4 | conventions | Minor | R-9 | Minor, trivial |
| R-V3 | conventions | Minor | R-10 | Minor, follow-up |
| R-V5 | conventions | Minor | R-11 | Minor, follow-up |
| R-E4 | engineering | Minor | R-12 | Minor, follow-up |
| R-E5 | engineering | Minor | R-13 | Minor, follow-up |
| R-E6 | engineering | Minor `[scope-adding]` | R-14 | Minor, follow-up (user) |
| (conformance note to the conventions lens, unfiled) | — | — | R-15 `[verifier]` | Minor, trivial |

No two original findings shared a root cause:
- R-1 and R-3 touch the same lines of `ClaudeWire.read`, but they fail differently (dropped stderr against a dropped thread id). I kept them separate and gave one combined patch.
- R-8 and R-13 both concern `_missing_member`. R-8 is an honest-signature issue; R-13 is error wording.

Nothing was refuted outright.

## 2. Verification of every Blocker and Major

### R-1 (R-C1): `output_too_large` drops stderr — CONFIRMED Major

**The defect, at the wire.** `vidbyte/harnesses/native/claude/wire.py:44` is `raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, cap_bytes=...)`, with no `vendor_text`.

```
$ PYTHONPATH=$(pwd) python s4verify/probe_v.py wire
output_too_large with stderr -> claude.output_too_large thread_id= None vendor_message= None
   'output limit notice' in message: False
```

**The siblings attach it.** `git show b28c3027:vidbyte/harnesses/native/<h>/wire.py | grep OUTPUT_TOO_LARGE` gives:
- grok `:44` `... vendor_text=outcome.stderr, cap_bytes=native_threads.GROK_CLI_MAX_OUTPUT_BYTES)`
- opencode `:64` `... vendor_text=outcome.stderr, cap_bytes=...)`
- muse `:99` and `:154`, the same.

**Spec reading.** INV-6 lists "the scrubbed and capped vendor text" as a message element, and G-4 asks for "the same detail as #1036's harnesses". Row 20 step (2) only fails to list `vendor_text`; it does not forbid it. §17 deviation 3's "unlike Grok" is inaccurate, because Claude is unlike all three siblings. So the finding rests on a correct reading.

**No existing guard.** No test pins the absence:
- `conftest.py:374` checks vendor text only when `vendor is not None`.
- `fake_harness.flood` writes no stderr.
- `grep -rn "vendor_message is None" tests/features/harness_threads/` is empty.

**The fix works.** With `wire_fixed.py` swapped in, `check_fixed.py` prints `run output_too_large + stderr -> claude.output_too_large thread_id=None vendor='limit notice'`.

### R-2 (R-E1): a lone-surrogate prompt leaks a key-holding `claude` child — CONFIRMED Major

**Mechanism, read in code.**
- `NATIVE_PROMPT_PATTERN = r"[^\x00]+"` (`constants:57`) accepts `\ud800`.
- `NativeThreadRequest.__post_init__:96` validates with it.
- `CliRunner.run` starts the child (`runner.py:202`). Inside `async with asyncio.timeout` it awaits `_feed_stdin` (`:217`). That method runs `stdin_text.encode("utf-8")` (`:330`) inside `contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError)`.
- `UnicodeEncodeError` is a `ValueError`, so it escapes. `run()` catches only `TimeoutError` (`:225`) and `CancelledError` (`:231`), so neither `ProcessStopper.stop_tree` nor `_finish_readers` runs.
- `ClaudeThreads._call` maps the exception to `runtime.error` (`threads.py:83-84`).

**Executed on win32.**

```
$ PYTHONPATH=$(pwd) python -W ignore s4verify/probe_v.py surrogate claude      (timeout_seconds=5)
claude result: {"ok": false, "type": "NativeThreadError", "code": "runtime.error", "elapsed": 0.11}
  message: run_claude_thread failed with runtime.error. The SDK failed while driving Claude Code. ... An unexpected UnicodeEncodeError was raised inside the
  child started: True pid 10156
  child alive 6 s after the call returned (timeout was 5 s): True
  stdin bytes the child received: none (still waiting for EOF)
  verifier killed leftover pid 10156
```

**Pre-existing for opencode.** `git diff --stat b28c3027 0a2752dd -- vidbyte/harnesses/native/opencode vidbyte/lib/process` shows only a one-line header change in `runner.py`, so opencode's path is byte-identical to main.

```
$ ... probe_v.py surrogate opencode
opencode result: {"ok": false, "type": "NativeThreadError", "code": "runtime.error", "elapsed": 0.2}
  child started: True pid 14916
  child alive 6 s after the call returned (timeout was 5 s): True
  stdin bytes the child received: none (still waiting for EOF)
```

Grok, which takes the prompt on argv, gives `runtime.error, elapsed 0.0, child started: False`. It fails before launch, so there is no leak, but it is still misclassified. That case is pre-existing and is noted under follow-ups.

**Spec reading.** These all fail for this input:
- INV-5: "Every argument is checked before … any process starts".
- INV-9: "at most `config.timeout_seconds` … whole process tree is stopped".
- INV-11: "the prompt on stdin … then EOF".
- AGENTS.md principle 4: "Invalid data then fails at the boundary".
- The weighted words "dataclass should have strict input validation".

The finding asks for no behaviour the spec does not require.

**No existing guard.** I checked `RecordFieldValidator._text_problem` (`validation.py:120-126`, `re.fullmatch` of the pattern) and `CliRunner.launch`, whose `(OSError, ValueError)` catch covers only `subprocess_exec`, not the stdin write.

**Claude-only fix, verified without editing source.** `fixcheck/surrplug.py` recompiles `NativeThreadRequest.__post_init__` with one line changed: `pattern=CLAUDE_PROMPT_PATTERN if self.harness is NativeHarness.CLAUDE else NATIVE_PROMPT_PATTERN`, with `CLAUDE_PROMPT_PATTERN = r"[^\x00\ud800-\udfff]+"`.

The pattern on its own:

```
'list files' True | 'list \ud800 files' False | 'emoji \U0001f600 ok' True | 'a\x00b' False | 'caf\xe9' True | 'esc \udc80 x' False
```

The fix applied, then the full pack:

```
$ PYTHONPATH="$(pwd):<fixcheck>" python fixcheck/check_surrogate_fixed.py
'list \ud800 files' -> configuration.invalid_argument "... The argument prompt was refused: prompt must match [^\\x00\\ud800-\\udfff]+; got 'list \\ud800 files'. ..."
   a child was started: False
'emoji \U0001f600 and ' -> OK c85185f3-...
$ PYTHONPATH="$(pwd):<fixcheck>" python -m pytest -q -p no:cacheprovider -p surrplug tests/features/harness_threads/
630 passed, 2 skipped in 96.81s
```

The fix adds no `if` (C901 of `__post_init__` is unchanged), and the constants pin `CLAUDE_CONSTANTS` checks only the names it lists (`test_harness_threads_claude_surface.py:159-162`). It does add a constant §8.5 does not list. §14's ask-first list names flags, environment variables, config fields, enum members and failure codes, not constants. The orchestrator should still record it as a §17 deviation.

The reviewer's `NATIVE_STDIN_PROMPT_HARNESSES` variant changes opencode, from an orphaned child to a refusal. A runner-level stop on any `_feed_stdin` exception is a `lib/process` behaviour change (§14 ask-first). Both need the user's sign-off under INV-20.

### R-3 (R-E3): an answer printed before a hang is thrown away — CONFIRMED Major

**Mechanism.** `wire.py:41-42` raises `TIMED_OUT` before `_answer` runs (`:49`), with no `thread_id`. `CliRunner.run` keeps what was read on timeout (`runner.py:225-238`: "collect the output read so far"; `_outcome` decodes the buffers). It waits for the process's own exit, not pipe EOF (`:212-218`), so a `claude` that prints and does not exit times out with the answer in `outcome.stdout`.

**Executed.**

```
$ ... probe_v.py print_then_hang        (stand-in prints a success answer, flushes, sleeps 30 s; timeout 3 s)
printed session: 47c4c8e1-fafc-4dc2-8bdf-7b6953864617
result: {"ok": false, "code": "claude.timed_out", "thread_id": null, "vendor": "still finishing background work", "elapsed": 3.3}
printed session id appears in error message: False
```

**Spec reading.**
- INV-6: "`thread_id` is the newest id the SDK learned: for run and fork, the `session_id` of Claude's JSON answer when it is a valid id, even on a failed run".
- D-14: "A failed run's or fork's error carries the answer's `session_id` when valid."
- D-9 and Q-3 decline *minting* an id up front with `--session-id`, so a run that times out *before printing* reports none.
- EC-14's trigger says "Tree stopped; no JSON was printed".

So the spec accepts `None` only when nothing was printed. This case is not declined, and the fix mints nothing (Q-3 is untouched). `opencode/wire.py:54-62` already reads the session first, "so a timed-out or cut stream still reports the session opencode printed", which is #1036's INV-5, the same rule. The trigger, a vendor that hangs after answering, was not measured for 2.1.301. It is the house doctrine's named pre-mortem case ("the upstream call that hangs instead of erroring"), and the SDK cannot tell it from a run that never answered.

**No test pins the old behaviour.** `test_harness_threads_claude_process_bounds.py:40` (run, `hold`, `thread_id=None`) and `:57` (continue and fork, `thread_id=first.thread_id`) both use `hold`, which prints nothing. With the fix:
- a run still gets `None`;
- a continue keeps `request.thread_id` through `newest`;
- a fork gets `newest = None`, and `NativeErrorFactory.failure` falls back to `request.thread_id` (`hostkit/errors.py:104`).

**Fix verified together with R-1.** `fixcheck/wire_fixed.py` moves the read block above the checks and adds `thread_id=newest` to both raises, plus `vendor_text` on the cap raise.

```
$ python -m ruff check fixcheck/wire_fixed.py --isolated --select C901,PLR0912,PLR0915 --config "lint.mccabe.max-complexity=8"
All checks passed!
$ ... --select C901 --config "lint.mccabe.max-complexity=7"
C901 `read` is too complex (8 > 7)
$ PYTHONPATH=$(pwd) MYPYPATH=$(pwd) python -m mypy --config-file lint/mypy.ini --no-pretty fixcheck/wire_fixed.py   -> exit=0, 0 lines
  (sanity: planting thread_id=1 makes mypy report `Argument "thread_id" to "failure" ... has incompatible type "int"`, so the copy is really checked)
$ PYTHONPATH="$(pwd):<fixcheck>" python -m pytest -q -p no:cacheprovider -p fixplug tests/features/harness_threads/ -k claude
fixplug: ClaudeWire.read swapped for the R-C1+R-E3 copy
195 passed, 437 deselected in 15.60s
$ ... python fixcheck/check_fixed.py
run      timed_out after print        -> claude.timed_out   thread_id=a65d1958-…  vendor=None
run      timed_out, nothing printed   -> claude.timed_out   thread_id=None
run      output_too_large + stderr    -> claude.output_too_large thread_id=None vendor='limit notice'
continue timed_out after print        -> claude.timed_out   thread_id=11111111-… (caller's)
fork     timed_out after print        -> claude.timed_out   thread_id=a65d1958-… (new)
fork     timed_out, nothing printed   -> claude.timed_out   thread_id=11111111-… (source, as INV-6 says)
```

**Cost note.** The fix parses `stdout` before the output-cap check. The success path already parses up to 64 MiB on the event loop, and opencode parses first too, so it adds no new worst case.

### R-4 (R-V2): REPO_MAP entry holds code references — CONFIRMED Major; part (b) needs an S2 test change and an AC-23 change

**Merged precedent in this exact entry.** `git show b28c3027:REPO_MAP.md`, line 161, holds two backtick references, `` `hostkit` `` (a child folder) and `` `vidbyte/lib/process/` `` (a folder path). Both are of the "child-folder path" kind. The owner merged them with #1036, so for that kind the lesson was not enforced on this entry.

**What this PR adds.** `git diff b28c3027 0a2752dd -- REPO_MAP.md` adds kinds the precedent does not have:
- `` `CLAUDE.md` ``: a backtick-quoted file name with a `.md` extension. The field-guide Check names this kind verbatim: "No folder-heading description contains a backtick-quoted file name, a `.py`/`.md`/… extension, a child-folder path, or a literal command".
- `` `run_claude_thread` ``, `` `continue_claude_thread` ``, `` `fork_claude_thread` ``: code names in a map that calls itself "code-free" (`REPO_MAP.md:7`) and "nothing that isn't derivable from the tree itself" (`:3`).
- `` `--setting-sources user` ``: a CLI flag, the owner's "commands".
- `` `~/.vidbyte/claude-configs/` ``: a path.

So this is a new kind of violation, and I confirm it. The lesson applies here even though its "When" names "the root `AGENTS.md` File Index", because AGENTS.md's "Repository Map" section moved the File Index into `REPO_MAP.md`.

**Spec and test conflict.** AC-23 (`spec.md:216`) requires REPO_MAP to name the three functions, `~/.vidbyte/claude-configs/` and the `--setting-sources user` consequence. `test_harness_threads_claude_acceptance.py:153-155` checks `(*FUNCTIONS, "claude-configs", "--setting-sources user")` in the REPO_MAP native section. `CLAUDE.md` is required by neither.

**Severity: Major, not Blocker.** The calibration rule puts a field-guide contradiction at Blocker. I keep Major because the owner merged path references in this same entry, so the lesson is not enforced as a hard gate here. The tokens that remain also come from an approved AC with a pinned test, which makes this a spec defect routed through the orchestrator, not an implementer slip. Behaviour is unaffected.

**Fix.** Part (a), replacing `` `CLAUDE.md` ``, is repair-only. Part (b) **needs a test change by S2**: restrict the token loop at `:153-155` to `vidbyte/harnesses/README.md`. It also needs **an AC-23 change** by the orchestrator: "REPO_MAP describes the private per-workspace config folder and the settings isolation in plain words". Only then can the repair agent reword the Claude sentences. Removing the backticks alone is not a fix.

## 3. Downgrades

### R-5 (R-V1): four functions without `@intent` — Major → Minor

**Evidence, from my runs:**

```
$ PYTHONPATH=$(pwd) python lint/run.py --rule A002
A002   intent-comments    578    703 IMPROVED
SDK-LINT: PASS
$ python -c "...json.load(open('lint/baseline.json'))..."     -> {'A002': 703, 'S008': 19, 'S009': 350}
$ git diff --stat b28c3027 0a2752dd -- lint/                   -> (empty)
$ python lint/run.py --rule A002 --all --format json, filtered to native-thread paths:
  claude/threads.py 67 _call; 91 execute (external boundaries, fallback, redaction); claude/wire.py 38 read;
  grok/threads.py 66 _call; 90 execute; 154 _argv; grok/wire.py 38 read; opencode/threads.py 61 _call; opencode/wire.py 53 read;
  muse/threads.py 66 _call ...; muse/wire.py 141 read ...; lib/dataclasses/native_threads.py 174 __post_init__ (Grok); 229 __post_init__ (Claude)
$ python s4conv_a002_cmp.py b28c3027 0a2752dd                  -> b28c3027 TOTAL 19 / 0a2752dd TOTAL 23
```

**Rule text.** A002 is a ratchet, and it passes.
- `comment-format.md` mentions "the `# @intent` blocks lint A002 requires", and its Check is "A002 still passes".
- `class-bound-helpers.md`'s Check is "`A002 intent-comments` passes, since a new boundary function needs its own `@intent` block". That lesson is about adapter translation helpers, and A002 passes.
- AGENTS.md does not mention `@intent`.

So no repo rule requires these four blocks beyond the ratchet passing. The detector is lexical: `request` is in `POLICY_TOKENS` as "external boundaries" (`lint/rules/a002_intent_comments.py:42`), and every `_call`/`read` takes a parameter named `request`.

**Spec.** The spec contradicts itself. §12.4 (`spec.md:662`) says "… and any other function A002 flags", while §12.3 row 19 (`spec.md:636`) says "`@intent` blocks only on `_environment`, `_inherited_names` and `_argv`". S3 followed the more specific row. The same pattern is on owner-merged main for every sibling.

**Result.** This would neither change behaviour nor draw a human review comment the owner has not already waived on #1036, so it is Minor. Optional, cheap follow-up: add the four blocks. If they are added, the orchestrator reconciles §12.4 with row 19. The comment-placement sub-point at `native_threads.py:139-141` is trivial.

### R-6 (R-E2): a relative user home misplaces the private folder — Major → Minor

**Executed.**

```
$ ... probe_v.py relhome            (HOME=USERPROFILE=relhome, parent cwd parentcwd/)
Path.home() = relhome absolute: False
CLAUDE_CONFIG_DIR the child got: relhome\.vidbyte\claude-configs\601c4ec7af6ecf8c
child resolves it to: ...\ws\relhome\.vidbyte\claude-configs\601c4ec7af6ecf8c
  inside the workspace: True
  skills the child finds there: None
folder the SDK prepared: ...\parentcwd\relhome\.vidbyte\claude-configs\601c4ec7af6ecf8c skills: ['write-tests']
$ USERPROFILE= HOME= python -c "from pathlib import Path; print(repr(str(Path.home())), Path.home().is_absolute())"
'.' False
```

So an empty `USERPROFILE` also triggers it on Windows.

**Pre-existing on main.**
- `b28c3027:grok/threads.py:141-152` (`_prepare_home`) builds the folder with `Path.home().joinpath(...)`, the same expression, never made absolute.
- `:163` passes `GROK_HOME: str(home)`.
- `:112` sets `cwd=Path(request.workspace)`.
- `:125-132` (`_fallback`) has the same relative path.

This PR lifted that body verbatim into `hostkit/folders.py:36-47` (INV-20).

**Realism.** The trigger is the caller's own process environment (a relative or empty `USERPROFILE`/`HOME`). A hostile workspace cannot set it, and exploiting it also needs the attacker to know that misconfiguration and the workspace path. It is a pre-existing property of shared code, not a Claude regression.

**Fix.** The robust fix refuses a non-absolute home as `launch_failed` in `NativePrivateFolders.prepare` and in both `_fallback`s. It changes Grok, so it needs the user's sign-off. The Claude-only stopgap (`.absolute()` in `_environment` and `_fallback`) restores INV-14 for Claude and matches INV-13/EC-31 as written, but Claude would then differ from Grok. I recommend one cross-harness follow-up.

## 4. Answers to the orchestrator's adjudication questions

1. **R-V2 against AC-23.**
   - The precedent at `b28c3027` holds two folder-path references, so it overrides the lesson only for that kind.
   - The PR adds a file name with `.md`, function names, a flag and a home path.
   - That is a new kind, so I confirm it (R-4).
   - Part (b) of the fix needs an **S2 test change** (`test_harness_threads_claude_acceptance.py:153-155`, check the tokens in the README only) and **a spec AC-23 change**. Part (a), `CLAUDE.md`, needs neither.
2. **R-V1 against lint.**
   - A002 is ratcheted at 703, the tree is at 578, and the lint run passes.
   - The spec contradicts itself (§12.4 at `spec.md:662` against row 19 at `spec.md:636`).
   - No repo rule or field-guide text requires `@intent` there beyond A002 passing.
   - Downgraded to Minor (R-5).
3. **R-E1.**
   - It is real on Windows (probe above).
   - It is pre-existing for opencode at `b28c3027`: same code, same leak.
   - A Claude-only fix exists and is verified: a Claude prompt pattern chosen by a conditional expression in `NativeThreadRequest.__post_init__`, with the full pack at 630 passed, 2 skipped.
   - The stdin-harness-wide fix and the runner fix change opencode, so they need the user's sign-off.
4. **R-E2.**
   - It needs a misconfigured caller environment (a relative *or empty* `USERPROFILE`, or a relative `HOME`).
   - Grok's `_prepare_home` at `b28c3027` behaved identically, so it is pre-existing shared behaviour.
   - Downgraded (R-6). The Claude-only stopgap is `.absolute()`, but I recommend the cross-harness fix as a user follow-up.
5. **R-E3.**
   - The spec accepts `None` only when no JSON was printed (EC-14, D-9, Q-3). INV-6 and D-14 require the printed id otherwise.
   - No test pins `thread_id` on a printed-then-hung run.
   - The fix keeps C901 at 8, ruff passes at max 8, mypy is clean, and the 195 Claude tests pass.
   - Confirmed (R-3).
6. **R-C1.**
   - Confirmed (R-1). All three siblings attach stderr at `b28c3027`.
   - G-4 and INV-6 support it, and row 20 does not forbid it.
   - §17 deviation 3 is unnecessary and inaccurately worded.
7. **Blind spot.**
   - R-1 and R-3 edit the same four lines of `ClaudeWire.read`. The combined patch adds no `if` (S008 holds) and no narrowing change (S009 holds), so apply them together.
   - R-8 (dropping `_missing_member`'s `text`) touches `read`'s call at `:75`; it is a trivial merge.
   - R-4 (b) conflicts with AC-23's test until S2 changes it: the "convention fix breaks a conformance requirement" case.
   - R-2's fix adds a constant outside §8.5; record it in §17.
   - R-5, if done, adds comment lines only.
   - No new Blocker-class risk falls between the lenses. I filed one trivial verifier Minor, R-15, the stale `_checked_model` comment the conformance review pointed at.

## 5. Disagreements between reviewers, adjudicated

- **AC-23 and REPO_MAP.** Conformance reported "AC-23: HOLDS"; conventions filed R-V2 against the same text. Both are right on their own terms: the code meets the spec, and the spec breaks a field-guide lesson. Resolution: confirm R-4, and route part (b) through S2 and an AC-23 change.
- **`@intent` placement.** Conformance checked row 19 symbol by symbol ("Unreported deviations: none found … the `@intent` placement"), while conventions cited §12.4's broader clause. The spec contradicts itself; the rule text does not require the blocks; downgraded.
- **R-E1 fix scope.** The engineering reviewer proposed `NATIVE_STDIN_PROMPT_HARNESSES` and flagged that INV-20 makes it the user's call. I give a Claude-only alternative that I verified, keep theirs as the user follow-up, and keep the runner-level stop as defence in depth.
- **R-E3 smallest fix.** I adopted the engineering reviewer's fix unchanged, and checked it under S008 and S009 and against the test pack together with R-1.

## 6. Follow-ups for the user (not for the repair loop)

- **Shared stdin path.** opencode leaks a child on a lone-surrogate prompt (pre-existing). Either refuse such prompts for every stdin harness, or make `CliRunner.run` stop the tree when `_feed_stdin` raises. Grok and Muse report `runtime.error` for that prompt instead of `configuration.invalid_argument`. All of these change sibling behaviour (INV-20).
- **Home folder.** Refuse a non-absolute `Path.home()` in `NativePrivateFolders.prepare` and in the Grok and Claude `_fallback`s (R-6).
- **Grok wire.** Grok's `read` has R-3's shape (timeout checked before parsing), but Grok prints only at exit, per its header. If a printed-then-hung Grok run is plausible, apply the same reordering there.
- **Remaining Minors.** R-10 (one hostkit fallback helper), R-11 (`NativeEnvironmentVariable` member), R-12, R-13 and R-14 `[scope-adding]` are as listed in review.md.

## 7. Commands run (all from the worktree, stdin from `/dev/null`)

- **Git.**
  - `git rev-parse HEAD 0a2752dd; git merge-base origin/main 0a2752dd` gives `dd5db847…`, `0a2752dd…`, `b28c3027…`.
  - `git diff --stat origin/main...0a2752dd -- . ':!docs' ':!tests'` gives 21 files, `+628 −66`.
  - `git diff --stat b28c3027 0a2752dd -- vidbyte/harnesses/native/{opencode,muse,grok} vidbyte/lib/process vidbyte/harnesses/native/hostkit` shows only `grok/threads.py`, the hostkit files, and header lines in `lib/process`.
  - `git show b28c3027:vidbyte/harnesses/native/{grok,opencode,muse}/wire.py | grep TIMED_OUT|OUTPUT_TOO_LARGE`
  - `git show b28c3027:vidbyte/harnesses/native/grok/threads.py` (`_prepare_home`, `_fallback`, env, cwd)
  - `git diff b28c3027 0a2752dd -- REPO_MAP.md vidbyte/lib/dataclasses/native_threads.py vidbyte/harnesses/native/hostkit/errors.py vidbyte/lib/process/runner.py`
- **Probes.**
  - `PYTHONPATH=$(pwd) python s4verify/probe_v.py wire | print_then_hang | relhome`
  - `… probe_v.py surrogate claude | opencode | grok` (leftover children killed by the probe)
- **Fix checks.**
  - `python -m ruff check fixcheck/wire_fixed.py --isolated --select C901,PLR0912,PLR0915 --config "lint.mccabe.max-complexity=8"` passes; at max 7 it fails at `read` (8 > 7).
  - `PYTHONPATH=$(pwd) MYPYPATH=$(pwd) python -m mypy --config-file lint/mypy.ini fixcheck/wire_fixed.py` is clean, with the planted-error sanity check.
  - `PYTHONPATH="$(pwd):<fixcheck>" python -m pytest -q -p no:cacheprovider -p fixplug tests/features/harness_threads/ -k claude` gives `195 passed, 437 deselected`.
  - `PYTHONPATH="$(pwd):<fixcheck>" python -m pytest -q -p no:cacheprovider -p surrplug tests/features/harness_threads/` gives `630 passed, 2 skipped`.
  - `PYTHONPATH="$(pwd):<fixcheck>" python fixcheck/check_fixed.py` and `… fixcheck/check_surrogate_fixed.py`
- **Lint and tests.**
  - `PYTHONPATH=$(pwd) python lint/run.py --rule A002` gives `578 703 IMPROVED … SDK-LINT: PASS`; `--all --format json` was filtered to native paths.
  - `PYTHONPATH=$(pwd) python s4conv_a002_cmp.py b28c3027 0a2752dd` (read first; read-only `git show`) gives TOTAL 19 then 23.
  - `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude` (unpatched) gives `195 passed, 437 deselected`.
- **Not run.** `scripts/run_ci.py`, the full `lint/run.py`, `--update-baseline`, and the real `claude`.
