# S4 findings verifier — harness-thread-functions

Status: DONE · HEAD `ead28887` (code unchanged since `d5581a24`) · no commits · Python 3.11.0 win32
Output: `docs/spec/harness-thread-functions/review.md` · Scratch: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad/s4-verifier/`

Result: **MERGEABLE AFTER FIXES**. Confirmed: 5 Blockers, 6 Majors. Minors: 15 (4 of them downgraded or split from a Major). Refuted: 0.

## 1. Merge map (original IDs → merged IDs)

| Original | Lens | Proposed | Merged | Disposition |
|---|---|---|---|---|
| R-V3 | conventions | Blocker | R-1 | CONFIRMED Blocker (test part route S2) |
| R-V1 | conventions | Blocker | R-2 | CONFIRMED Blocker (needs spec deviation note) |
| R-V4 | conventions | Blocker | R-3 | CONFIRMED Blocker |
| R-E1 | engineering | Blocker | R-4 | CONFIRMED Blocker (needs spec deviation note; test route S2) |
| R-V2 | conventions | Blocker | R-5 | CONFIRMED Blocker (part (d), the `_call` try, excluded: row 36 prescribes it) |
| R-E5 | engineering | Major | R-6 | CONFIRMED Major |
| R-C1 + R-V5 (first half) | conformance + conventions | Major + Major | R-7 | CONFIRMED Major (needs spec deviation note: row 32 signature) |
| R-E6 | engineering | Major | R-8 | CONFIRMED Major |
| R-E7 | engineering | Major | R-9 | CONFIRMED Major |
| R-C2 + R-E4 | conformance + engineering | Major + Major | R-10 | CONFIRMED Major |
| R-E2 | engineering | Major | R-11 | CONFIRMED Major |
| R-V6 (vendor markers) | conventions | Major | R-12 | DOWNGRADED → Minor follow-up |
| R-V6 (taskkill) + R-C5 | conventions + conformance | Major + Minor | R-13 | DOWNGRADED → Minor follow-up (spec text) |
| R-E3 | engineering | Major | R-14 | DOWNGRADED → Minor follow-up |
| R-V5 (second half) | conventions | part of a Major | R-15 | split → Minor trivial |
| R-C4 | conformance | Minor | R-16 | Minor trivial |
| R-V7 | conventions | Minor | R-17 | Minor trivial |
| R-C3 | conformance | Minor | R-18 | Minor follow-up (spec text) |
| R-V8 | conventions | Minor | R-19 | Minor follow-up |
| R-V9 | conventions | Minor | R-20 | Minor follow-up |
| R-V10 | conventions | Minor | R-21 | Minor follow-up |
| R-V11 | conventions | Minor | R-22 | Minor follow-up (lint text out of repair scope) |
| R-E8 | engineering | Minor | R-23 | Minor follow-up |
| R-E9 | engineering | Minor | R-24 | Minor follow-up, route S2 |
| R-C1 secondary (probe E2) | conformance | (optional) | R-25 | Minor follow-up |
| — | verifier | — | R-26 | Minor follow-up `[verifier]` |

Duplicates the orchestrator flagged:
- **R-C2 = R-E4.** Confirmed: same line (`muse/threads.py:106-107`), same failure.
- **R-C1 = R-V5's first half.** Confirmed: same method (`errors.py:120`), same failure. R-V5's second half (the vendor sentence that is not ended) is a different defect and became R-15.
- **R-V6 vs R-C5.** They overlap only on the taskkill tuple; merged as R-13. R-V6's vendor-marker part stays separate as R-12.

## 2. Verifications (my own evidence)

Every probe I ran used stand-ins (a `t64.exe` launcher wrapping a Python body, or `sys.executable` scripts) with a dummy key (`vbk-dummy-…` or `xai-SECRETSECRET-…`). HOME, USERPROFILE, PATH and TEMP were sandboxed under the scratchpad (engineering `common.py`), or under a `s4c-probe-*` folder in the system temp (conformance `probes.py`). I read each script before running it. No real vendor CLI ran, and no credential file was opened.

### R-1 (R-V3) — CONFIRMED Blocker
- Command: for each changed `vidbyte/*.py` file, `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'`. Output: `grok/wire.py:80: 74`, `grok/wire.py:88: 74`, `lib/constants/native_threads.py:111: 73`, `lib/dataclasses/native_threads.py:100: 75`. The remaining hits are in `lib/enums/failure.py` (6) and `lib/errors/base.py` (9). The same count over `git show origin/main:` gives 6 and 9, so those were already on main.
- Tests: `total test wide comment lines: 124`, spread over 16 files; the widest is `149`.
- Rule: field guide `comment-format.md`: "Wrap every comment line at 72 columns … The owner rejected 100–120-column comment blocks … Check: `awk … | grep -E '^\s*#'` prints nothing for the files you touched." Contradicting a field-guide lesson is Blocker-class, and the test pack has the exact 100–149-column shape the owner rejected.

### R-2 (R-V1) — CONFIRMED Blocker
- `git grep -n MUSE_REAP_STDIN_SWITCH ead28887` → `muse/launcher.py:150` (operand) and `lib/constants/native_threads.py:83` (`= "-s"`). There are no other uses.
- `git show 5d0e95a1:vidbyte/harnesses/native/muse/launcher.py` line 39: `_REAP_SHELL = ("sh", "-s")`. Spec row 23 lists `MUSE_REAP_SHELL`, so the spec silently kept `-s` inside a constant.
- Requirements: INV-15's text says "So every flag comes from `GrokFlag`, `OpencodeFlag`, `MuseFlag` or `WslFlag`". The §12.5 row for comment 3 scopes "All argv the feature builds: … `wsl.exe` (SEPARATE)", and its S6 reply says "every flag is now a member of GrokFlag/OpencodeFlag/MuseFlag/WslFlag". With `-s` a string, that reply is false. This is a remaining instance of comment 3's rule ("define enums for flags/hardcoded strings … for all providers"), inside the scope the spec itself gave that comment, so it is not a stretch.
- Test interplay: `test_harness_threads_surface.py:35-47` pins `WslFlag` to `["-d", "-e", "-l", "-q"]`, so `-s` cannot go into `WslFlag` without S2, and it is `sh`'s flag anyway. The surface test iterates only over `EXPECTED_ENUMS`, so a new `ShellFlag` is test-neutral. `test_harness_threads_wsl.py:110` pins `reap["argv"] == ["-s", mark]`, and a StrEnum operand keeps that.

### R-3 (R-V4) — CONFIRMED Blocker
- Command: `python -X utf8 s4-conventions/depth.py <changed vidbyte .py>` (I read the script first: an `ast` walk of same-class calls). Output:
  ```
  vidbyte/harnesses/native/hostkit/errors.py: NativeErrorFactory.failure -> _context_sentences -> scrub
  vidbyte/harnesses/native/hostkit/errors.py: NativeErrorFactory.failure -> _observed_sentences -> scrub
  vidbyte/harnesses/native/hostkit/errors.py: NativeErrorFactory.from_configuration_error -> _context_sentences -> scrub
  vidbyte/harnesses/native/hostkit/errors.py: NativeErrorFactory.from_launch_failure -> _context_sentences -> scrub
  vidbyte/harnesses/native/hostkit/errors.py: NativeErrorFactory.from_launch_failure -> _observed_sentences -> scrub
  vidbyte/lib/enums/failure.py: FailureCode.from_exception -> _from_exception_name -> _from_exception_fallback
  ```
  The script reads blob `01b20447`. `git diff 01b20447 ead28887 -- vidbyte` is docs-only, and I also read `errors.py` at HEAD: lines 101-102, 115 and 142-143 call the helpers, and the helpers call `self.scrub` at 151, 153 and 163. The `FailureCode` chain was already on main.
- Rule: AGENTS.md principle 1 ("that second function should not call a third") and the house-style "At most one hop of same-class delegation". Calls to another class do not count, but `scrub` belongs to the same class.

### R-4 (R-E1) — CONFIRMED Blocker
- Python 3.11.0 `shutil.which` source (from `inspect.getsource`): `if sys.platform == "win32": # The current directory takes precedence on Windows. … if curdir not in path: path.insert(0, curdir)`. This runs after `path` is set from the argument, so `path=` does not help.
- `exp8b_cwd_grok.py` (re-run; PATH = an empty sandbox `bin`, process cwd = the workspace holding a planted stand-in `grok.exe`):
  ```
  shutil.which('grok') -> .\grok.EXE
  run_grok_thread -> grok.run_failed exit 3
  {"argv0": "...\\boxes\\exp8b\\ws\\grok.EXE", "has_inline_config": false, "has_xai_key": true, "grok_home_set": true, ...}
  ```
- `exp8_cwd_lookup.py` (re-run): `shutil.which('opencode') -> .\opencode.EXE | shutil.which('wsl.exe') -> .\wsl.exe`. The planted `opencode.EXE` recorded `"has_inline_config": true` (that config holds the key), and the planted `wsl.exe` recorded `"has_meta_key": true` with `WSLENV` naming `META_API_KEY/u`.
- Requirements: D-16 ("explicit command wins, then PATH, then the Grok fallback"), INV-2 ("reaches the vendor process only through that child's environment"), and T-6's attacker ("a cloned … repository"). This is not scope-adding: it makes an existing spec'd control work, and no Q-n covers it. Row 33's wording ("resolved through `shutil.which` (PATH + PATHEXT)") assumed `which` searches only PATH, so the fix needs a deviation note.
- Test interplay: no test monkeypatches `shutil.which` (`grep -rn "shutil.which" tests/features/harness_threads` hits only header comments). The batch-refusal tests compare paths case-insensitively, so a PATH walk that returns lower-case suffixes still passes. The engineering reviewer's exp9 (a planted `taskkill.exe` in the cwd during a real timeout) recorded `never`. I read exp9 and its setup is sound, so I did not widen R-4 to the bare `taskkill` launch.

### R-5 (R-V2) — CONFIRMED Blocker
- `git grep -n NATIVE_THREAD_ID_PATTERN ead28887 -- vidbyte` gives four inline uses: `grok/wire.py:65`, `muse/wire.py:123`, `muse/wire.py:216`, `opencode/wire.py:121`. There are two validator uses: `lib/dataclasses/native_threads.py:122`, `:209`.
- `git grep -n "json.loads(line)"` → `muse/wire.py:134`, `muse/wire.py:201`, `opencode/wire.py:107`. Read side by side, `OpencodeWire._events` (100-112) and `MuseExecOutput._records` (194-206) are identical apart from the variable name.
- `git grep -n 'requested = request.thread_id or ""'` → `grok/wire.py:73`, `opencode/wire.py:86`. Both are followed by the same casefold continue and fork checks and the same two raises.
- `grep -rn "def .*jsonl\|def .*json_lines\|…" vidbyte` finds no existing helper, so principle 5's "look first" turns up nothing to reuse.
- Rule: AGENTS.md principle 5 ("whenever a canonical helper in `vidbyte/lib/` would save writing the same logic a second time, build it that way"; it names "parsing a provider's response") and the field guide `strict-config-dataclasses.md` ("Any primitive value validated inline in more than one call site belongs in its own frozen dataclass … Two independent inline copies of the same rule drift silently"). Contradicting both is Blocker-class. I excluded R-V2(d), the repeated `_call` try, because row 36 prescribes that shape.

### R-6 (R-E5) — CONFIRMED Major
- Code: the 8 TIMED_OUT and OUTPUT_TOO_LARGE calls pass no `vendor_text`, and `errors.py:94` builds vendor text only from that argument.
- `exp10_timeout_stderr.py` (re-run): `code grok.timed_out | vendor_message None | 'device login' in str(error): False`.
- Requirement: INV-5 element 6 ("the vendor's own text … when the vendor printed any"). The rows that list timeouts without text are the plan; the INV is the requirement.
- Test interplay: `grep -n vendor_message tests/...` finds only `conftest.py:311` (checks presence when `vendor=` is given) and `test_harness_threads_errors.py:157` (an invalid-argument error, where None is right). No test pins None on a timeout.

### R-7 (R-C1 + R-V5 first half) — CONFIRMED Major
- `probes.py` (re-run; I read it first; it monkeypatches `CliRunner.run` to raise `KeyError`):
  ```
  E1 code: runtime.error | thread_id attr: None | workspace in message: False | thread in message: False
  ```
- Code: `errors.py:120` `def from_unexpected(self, exc: Exception)` and `:130` `return self._error(FailureCode.RUNTIME_ERROR, sentences, error_type=error_type)`. At all three call sites the request has been built, except when the defect is inside the record itself.
- Requirement: INV-5 ("Otherwise it is the caller's `thread_id` (continue, fork)"; element 4 "the workspace path and the thread id, when known"). Row 32's `from_unexpected(exc)` signature conflicts with that, so the fix needs a deviation note. The method is internal (§8.5 says the §12.3 names are a plan, not a contract).

### R-8 (R-E6) — CONFIRMED Major
- My own check: `subprocess.run([sys.executable, '-c', 'pass', 'x'*40000])` → `FileNotFoundError errno 2 winerror 206`, so a command line that is too long arrives as ENOENT.
- `runner.py:210-211`: `except FileNotFoundError: return None, ProcessLaunchFailure.NOT_FOUND`, and `errors.py:135` maps NOT_FOUND to `NOT_INSTALLED`.
- `exp3_cmdline.py` (re-run): `cap 24000`, `quotes prompt chars 20000 list2cmdline chars 40009`, `20000 double quotes -> grok.not_installed | … Grok Build could not be found …`, `emoji prompt chars 20000 utf-16 units 40000`, `20000 emoji -> grok.not_installed`, `15000 backslash/quote mix -> ran`.
- Requirement: EC-3 (the record refuses the prompt naming `prompt` and the cap, "Without the guard the Windows `CreateProcess` 32,767-character limit would fail the launch") and INV-6 (`not_installed` means "no launcher found"). A-18's assumption is false for quote-heavy or non-BMP prompts.

### R-9 (R-E7) — CONFIRMED Major
- `exp5_readonly.py` (re-run): `call 1 skills=[ro-skill] -> ok abc123`, `call 2 skills=[] -> grok.launch_failed | … could not be started …`, `call 3 skills=[] -> grok.launch_failed`. The script restores the write bits afterwards.
- Code: `skills.py:38-42` (`shutil.rmtree(destination)` with no handler; `copytree` copies the modes through `copy2` and `copystat`).
- Requirement: INV-12 (the folder is rebuilt to hold exactly the passed skills), with the EC-14 next step unable to help. Fix constraint: `rmtree(onerror=)` is deprecated on 3.12 (CI runs 3.11 and 3.12) and 3.11 has no `onexc`, so clear the bits with `os.walk` and `os.chmod`.

### R-10 (R-C2 + R-E4) — CONFIRMED Major
- `exp2_muse_cancel.py` (re-run): `CancelledError reached the caller` / `temp folder entries after the cancelled call: ['tmpsusmo1q7']` / `tmpsusmo1q7 holds 4004 entries`.
- `probes.py` E3 (re-run): `E3 CancelledError propagated` / `E3 temp folders left after the cancelled call: ['tmphjvvjd78'] [['muse', 'muse/skills', 'muse/skills/slow-skill', 'muse/skills/slow-skill/SKILL.md']]`.
- Code: `muse/threads.py:106` `folder = await asyncio.to_thread(...)` sits before `try:` at 107, so the `finally` at 131-132 never covers it.
- Requirement: INV-9 and AC-11. EC-34 excuses only a removal that fails.

### R-11 (R-E2) — CONFIRMED Major
- `exp1b.py` (re-run; the stand-in `grandchild_grok2.py` prints a valid answer, starts a 25 s child on the same stdout and stderr, and exits 0; timeout 3): `ERROR grok.timed_out 3.1 s; exit_code None` / `grandchild 6276 after the call: python.exe 6276 Console`. The script then kills its own grandchild by pid.
- Code: `runner.py:159-162`. Inside the bound, `await asyncio.wait(readers)` waits for EOF on both pipes before `process.wait()`.
- Fix constraint I verified: 3.11 `BaseSubprocessTransport._process_exited` wakes the `_exit_waiters` itself. In 3.13 (`C:/Users/422mi/AppData/Local/Programs/Python/Python313/python.exe`, `inspect.getsource`), `_process_exited` only calls `_try_finish()`, and the waiters are woken in `_call_connection_lost`, which runs after every pipe has disconnected. So swapping the order of the awaits is not enough on 3.12+.
- Requirement: AC-2 (the run returns its answer) and INV-8. The Windows orphan (taskkill /T cannot reach a grandchild once the leader is gone) is already a documented limit in the runner header, so the confirmed claim centers on the completed run that is reported as a timeout.

## 3. Downgrades and splits (evidence)

- **R-V6 vendor markers → R-12 (Minor).** `grok/wire.py:49`, `muse/wire.py:178` and `:214` each compare one vendor value once. D-11 says "Every other fixed value goes to `vidbyte.lib.constants.native_threads`: … vendor markers", and row 23 names `MUSE_COMPLETED_TERMINAL` and `MUSE_SESSION_STREAM_KIND` explicitly. On the merits: these are markers, not vocabularies the SDK enumerates. Owner comments 1, 2 and 4 accept the constants module as the location, and comment 3 is about flags. No behavior changes.
- **R-V6 taskkill + R-C5 → R-13 (Minor, spec text).** `runner.py:85` is the generic lib runner. §12.5 puts "the runner's `taskkill` argv" under comment 2 (location, now satisfied) and leaves it out of comment 3's argv list. Row 30 prescribes the constant. What remains is a conflict between INV-16's text and row 30; per the briefing that is a Minor follow-up.
- **R-E3 → R-14 (Minor).** I reproduced it with `exp6_straddle.py`: `code grok.run_failed`, `vendor_message tail: '…ddddkey=xai-SECR'`, `final error present: False`, `key prefix 'xai-SECR' in str(error): True`. The stand-in is built so that the key straddles the 4,194,304-byte stderr cap exactly. In real use it needs more than 4 MiB of stderr (64 MiB for opencode and Muse), and for the leak also a key echo that lands across the boundary, about 40 bytes in 4 MiB, given an echo that is itself unusual. I judge it real but not a production-surfacing gap. The `errors.py:9` claim refers to the factory's 1,000-character cap, and it holds for that cap.
- **R-V5 second half → R-15 (Minor, trivial).** My `v1_render.py` (it calls the factory directly; no process): `V1: The vendor printed: Not signed in Likely cause: xAI rejected the API k`. It is a readability defect in one template. Every INV-5 element is present.

Minor checks I ran along the way: `v1_render.py` `V2: HOME named: False | USERPROFILE named: False` (R-16). `wc -l` base.py 613 at HEAD and 552 on main (R-20). `grep -c '"field"'` gives validation.py 15, dataclasses/native_threads.py 4, argv.py 1 (R-19). `lint/rules/c008_shared_validator_owner.py:9` still says "does not exist yet" (R-22). `test_harness_threads_process_bounds.py:123` polls after `await task` (R-24).

## 4. Adjudications between reviewers

1. **R-C2 vs R-E4: must the fix wait for the `to_thread` copy?** Yes. The conformance reviewer said a plain "mkdtemp first, copy inside the try" races the copy that is still running. The engineering reviewer's alternative already says "waiting for the copy before removing". So they agree. The worker thread cannot be cancelled, and the folder path is known only when the worker returns, so the shield-and-wait shape is the one that is correct. Note also that `await asyncio.to_thread(tempfile.mkdtemp)` on its own has the same cancel gap.
2. **R-V1 (Blocker) vs R-V6 taskkill (Major) vs R-C5 (Minor).** All three are "a flag kept as a string constant", yet I split them. `-s` sits in a harness module's `wsl.exe` argv, which §12.5 scopes to comment 3, and the planned S6 reply claims it. Taskkill sits in the lib runner, scoped by §12.5 to comment 2 only, and row 30 prescribes it.
3. **R-C1 vs R-V5: severity.** Both reviewers said Major; kept. R-V5 also cited owner comment 1 ("much more detail"). The detail elements are present except for this path, so Major and not Blocker.
4. **R-V2 severity (Blocker).** I weighed Major, because the duplication causes no wrong result today. I kept Blocker because the calibration rule names "contradicts AGENTS.md or a field-guide lesson", and principle 5 plus `strict-config-dataclasses.md` both apply directly. The copies have already drifted in style: opencode `:121` skips `isinstance`, which the line above performs instead.
5. **R-E1 scope.** The briefing says it is not scope-adding, and I agree. It restores D-16's stated order. The fix contradicts row 33's wording only, hence the deviation note.

## 5. Interactions for the repair agent
- R-3, R-7, R-15, R-16 and R-6 all touch `hostkit/errors.py`, the constants templates or the wire call sites. Do R-3's shape first (scrub in the entry methods), then R-7's `from_unexpected` in that shape. R-6 adds vendor text to timeouts, so R-15's fixed template then appears on more errors.
- R-5 and R-6 edit the same wire lines. Batch them to avoid churn. R-5's validator predicate also makes R-17's `validation.py:4` header true.
- R-4, R-8's part (2) and R-11 all edit `lib/process/runner.py`. R-4's lookup helper fits there as a static method.
- R-9 and R-10 both change the Muse temp-folder removal. R-10's cancel path must use R-9's read-only-safe removal.
- R-1 is last: every comment the other fixes add must also fit in 72 columns.
- Spec deviation notes are needed for R-2 (§8.4 enum count; row 23), R-4 (row 33), R-7 (row 32), and R-5 or R-11 if a new class is added (§8.4).

## 6. Commands run (final lines)
- `PYTHONPATH=$(pwd) timeout 600 python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `395 passed, 2 skipped in 33.86s` / `exit=0`
- `timeout 900 python lint/run.py < /dev/null` → `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` / `exit=0`
- `awk` 72-column check (above) → 4 new `vidbyte/` lines; 124 test lines; max 149
- `python -X utf8 s4-conventions/depth.py <changed files>` → 5 `NativeErrorFactory` chains + 1 pre-existing
- `s4-engineering/exp8b_cwd_grok.py`, `exp8_cwd_lookup.py`, `exp1b.py`, `exp2_muse_cancel.py`, `exp3_cmdline.py`, `exp5_readonly.py`, `exp6_straddle.py`, `exp10_timeout_stderr.py` (each `timeout 120 python -X utf8 <exp> < /dev/null`) → outputs quoted in §2 and §3
- `PYTHONPATH=$(pwd) python -X utf8 s4-conformance/probes.py $(pwd)` → E1, E2, E3 quoted in §2 (E2: `configuration.invalid_argument | thread_id attr: None | workspace in message: False`)
- `python -X utf8 s4-verifier/v1_render.py $(pwd)` → V1 and V2 quoted in §3
- `python -c "subprocess.run([... 'x'*40000])"` → `FileNotFoundError errno 2 winerror 206`
- `inspect.getsource` on `shutil.which` (3.11.0) and on `asyncio.base_subprocess.BaseSubprocessTransport` (3.11.0 and 3.13) → quoted in §2
- `git grep` traces: `MUSE_REAP_STDIN_SWITCH`, `NATIVE_TASKKILL_ARGUMENTS`, `GROK_ERROR_TYPE`, `MUSE_COMPLETED_TERMINAL`, `MUSE_SESSION_STREAM_KIND`, `NATIVE_THREAD_ID_PATTERN`, `json.loads(line)`, `requested = request.thread_id or ""`, `RecordFieldValidator|RecordFieldConverter` in `vidbyte/harnesses`; `git show 5d0e95a1:…/muse/launcher.py`; `git show origin/main:vidbyte/lib/errors/base.py | wc -l` → 552

Not run: `scripts/run_ci.py` (the conformance reviewer ran `--stage source` green; GitHub CI is green on `622dabd9`, which has the same code). The `R-E8` scratch pytest was not re-run; it stays a Minor and passes through unchanged.
