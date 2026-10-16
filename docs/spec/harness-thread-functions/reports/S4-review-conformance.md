LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the PR delivers the nine `<verb>_<harness>_thread` functions, the caller-key isolation and the deletion the owner asked for, and every §12.3 row is present, but two spec guarantees fail on side paths: INV-5 (a `runtime.error` loses the caller's thread id and workspace) and INV-9 (a cancelled Muse call can leave its temp folder behind).

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The public surface is exactly the contract. `vidbyte.harnesses.native.__all__` holds the nine coroutines plus the D-22 names (17 entries). Each subpackage's `__all__` holds its three functions. The old names are gone. The restored areas (`vidbyte/tools`, `vidbyte/lib/configs`, root `vidbyte/__init__.py`, `lint/`, `pyproject.toml`) have an empty two-dot diff against origin/main, and origin/main equals the merge base 179d8adc.
- Key isolation follows INV-3/D-6 on every harness. Grok gets `GROK_HOME=~/.vidbyte/grok-homes/<sha256(normcase(resolved ws))[:16]>` (grok/threads.py:141-143). opencode gets an inline `provider.<prefix>.options.apiKey` (opencode/wire.py:44-49). Muse gets `META_API_KEY`, a per-call `XDG_CONFIG_HOME` and a never-created `MUSE_AUTH_PATH`, and serve runs with `env_remove=(META_API_KEY,)` (muse/threads.py:151-178). Do not "simplify" any of these.
- INV-15 holds. My own AST scan found zero literals and zero module-level constants in `vidbyte/harnesses/native/**`, and all 198 constants in `vidbyte/lib/constants/native_threads.py` have a reader. Every argv the harness modules start goes through `CliArgv.build` with enum flags (Grok and opencode JOINED; Muse exec, Muse serve, `wsl.exe -l -q` and the reap SEPARATE).
- The budget is met exactly. There are 24 added `.py` files, and the 45 added classes are 17 new + 16 kept + 12 new enums, as §8.4 lists. The test tree has only additions (18 files). There are no suppressions and no baseline edits. The spec §4 snippet, read from spec.md itself, runs green against stand-ins.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [every-ID: INV-5 / FR-10 / NFR-7] vidbyte/harnesses/native/hostkit/errors.py:120-130 — `runtime.error` drops the caller's thread id and the workspace, though both are known
  Evidence:
    errors.py:120 `def from_unexpected(self, exc: Exception) -> NativeThreadError:` builds only the summary and observation, then
    errors.py:130 `return self._error(FailureCode.RUNTIME_ERROR, sentences, error_type=error_type)` (so thread_id stays at its None default, and no `_context_sentences`).
    Call sites have the built request in scope: grok/threads.py:76-86, opencode/threads.py:68-78 and muse/threads.py:73-83 all reach `raise errors.from_unexpected(exc) from exc` after `request = NativeThreadRequest(...)`.
    Probe (scratchpad/s4-conformance/probes.py, E1): `continue_grok_thread("abc123", "hi", ..., workspace=<ws>)` with `CliRunner.run` raising KeyError →
    `E1 code: runtime.error | thread_id attr: None | workspace in message: False | thread in message: False`
    Message: "continue_grok_thread failed with runtime.error. The SDK failed while driving Grok Build. An unexpected KeyError was raised inside the SDK; ... Likely cause: ... Next step: ..."
    Secondary (E2): `continue_grok_thread("abc123", "", ...)` → `configuration.invalid_argument | thread_id attr: None | workspace in message: False`. The caller's valid id and workspace are dropped because the record never finished building.
    Why the tests miss it: test_harness_threads_errors.py:126-137 provokes runtime.error only with `call(harness)` (verb "run"), and `check_error` gets no `workspace=`. The `refuse` fixture (test_harness_threads_arguments.py:39-53) never checks thread_id or workspace.
  Failure: any SDK defect during a continue or fork → `error.thread_id is None`, and the message names neither the workspace nor the thread. INV-5 says thread_id "is the caller's thread_id (continue, fork)" when nothing newer was learned, and element 4 requires "the workspace path and the thread id, when known". Every other code path does this. Row 32's signature `from_unexpected(exc)` caused the gap.
  Smallest fix: give `from_unexpected` the request (`from_unexpected(exc, request)`). Add `*self._context_sentences(request, None if request is None else request.thread_id)` between the summary and the observation. Pass `thread_id=None if request is None else request.thread_id` to `_error`. Update the three call sites. Optionally do the same in `from_configuration_error` for the pre-record case, but only with a raw thread_id that already matches NATIVE_THREAD_ID_PATTERN. Extend the runtime.error test to continue/fork with `workspace=sandbox.workspace, thread_id=<id>`.
  Spec IDs: INV-5, FR-10, NFR-7, AC-10, EC-32; row 32

R-C2 [Major] [every-ID: INV-9 / AC-11 / EC-16] vidbyte/harnesses/native/muse/threads.py:106-107 — a cancel that lands while the Muse config folder is being prepared leaks the temp folder and the copied skills
  Evidence:
    muse/threads.py:106 `folder = await asyncio.to_thread(MuseThreadRun._prepare_config, request, errors)`
    muse/threads.py:107 `try:` ... 131-132 `finally: await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)`
    The await at 106 sits outside the try/finally. A CancelledError raised there skips the removal, while the worker thread goes on to finish `mkdtemp` and the `copytree` of every skill.
    Probe (probes.py, E3): `NativeSkillFolders.replace` is slowed by 1 s to stand in for a large skill copy or Windows AV scanning. `run_muse_thread(..., skills=[slow-skill])` is cancelled 0.3 s in →
    `E3 CancelledError propagated`
    `E3 temp folders left after the cancelled call: ['tmpc2i1mvig'] [['muse', 'muse/skills', 'muse/skills/slow-skill', 'muse/skills/slow-skill/SKILL.md']]`
  Failure: the caller cancels during the skill copy → CancelledError propagates (correct), but a folder holding copies of the caller's skills stays in the system temp folder for good. INV-9 says CancelledError propagates "after the Muse temp folder is removed", and AC-11 says "the Muse temp folder is gone". The AC-11 tests cancel only while the vendor process runs.
  Smallest fix: keep the removal until the worker stops writing. Start the preparation as a future (`preparing = asyncio.ensure_future(asyncio.to_thread(...))`) and `await asyncio.shield(preparing)`. On CancelledError, await `preparing` to completion (the file work is bounded), remove its folder with `shutil.rmtree(..., ignore_errors=True)` through `to_thread`, then re-raise. A plain "mkdtemp first, copy inside the try" is not enough: the finally's rmtree would race the still-running copy thread.
  Spec IDs: INV-9, AC-11, EC-16, INV-12 (the temp copy outlives the call)

R-C3 [Minor] [every-ID: FR-5] vidbyte/harnesses/native/grok/wire.py:49-53 — FR-5's "an unknown id raises <h>.thread_not_found" does not hold for Grok
  Evidence: FR-5 (spec line 299): "`continue_<h>_thread(thread_id, …)` … an unknown id raises `<h>.thread_not_found`". grok/wire.py:52 `problem = NativeThreadProblem.KEY_REJECTED if refused else NativeThreadProblem.RUN_FAILED`. Grok's error object for an unknown `--resume` id therefore becomes `grok.run_failed`, which is what EC-21 (spec line 262) prescribes. vendor-facts.md:39 records only "errors if the session does not exist", with no marker text, so the SDK cannot tell an unknown id apart.
  Failure: a caller that catches `FailureCode.GROK_THREAD_NOT_FOUND` to detect a stale id, as FR-5 promises for every harness, gets `grok.run_failed` instead. The spec contradicts itself here (FR-5 against EC-21/D-17), and the code follows EC-21.
  Smallest fix: no code change. Amend FR-5 to "(Grok: `grok.run_failed` carrying Grok's own text, EC-21; `grok.thread_not_found` only when Grok answers on another id)". Optionally add the same sentence to the `native/` bullet of vidbyte/harnesses/README.md.
  Spec IDs: FR-5, EC-21, D-17, A-2

R-C4 [Minor] [deviations] vidbyte/lib/constants/native_threads.py:300 and :389 — the R-20 remedy "set HOME/USERPROFILE" never reaches the caller
  Evidence: spec §16 R-20 disposition (line 996): "EC-14 and row 36 map `Path.home()` `RuntimeError` to `grok.launch_failed`, with the next step to set `HOME`/`USERPROFILE`". As built: grok/threads.py:144-145 raises `LAUNCH_FAILED` with `GROK_HOME_UNKNOWN_DETAIL = "The user home folder, where the private Grok home lives, could not be determined ({error_type})."`, and the shared next step (line 389) says "Check that grok runs from a terminal and that ~/.vidbyte/grok-homes is a writable folder, then retry; ...". No text names HOME or USERPROFILE.
  Failure: a service process with no HOME/USERPROFILE gets `grok.launch_failed` with a next step that cannot help, because there is no `~` to check. The detail the review accepted was not delivered, and §17 does not list this as a deviation.
  Smallest fix: append ", so set HOME (POSIX) or USERPROFILE (Windows) for this process" to `GROK_HOME_UNKNOWN_DETAIL`. That is one constant edit; INV-5 keeps one next step per code.
  Spec IDs: EC-14, §16 R-20, INV-5 element 5

R-C5 [Minor] [every-ID: INV-16] vidbyte/lib/process/runner.py:85 — one argv the feature starts does not come from `CliArgv.build`
  Evidence: runner.py:85 `await asyncio.create_subprocess_exec(*native_threads.NATIVE_TASKKILL_ARGUMENTS, str(pid), ...)`, with constants.py:64 `NATIVE_TASKKILL_ARGUMENTS = ("taskkill", "/T", "/F", "/PID")`. INV-16 says "Every argv the feature starts is built by `CliArgv.build` from `CliOption` records". On win32, every timeout or cancel of a thread call starts this taskkill. Row 30 of the spec itself asks for this constant, so the spec contradicts itself.
  Failure: no behavior difference. The weighted "Every" in INV-16, and comment 3's "enums for flags/hardcoded strings … for all providers", are not literally true for the Windows tree stop.
  Smallest fix: narrow INV-16 in the spec to "every vendor and wsl.exe argv". Routing taskkill through CliArgv would need a flag enum the §8.4 budget does not list.
  Spec IDs: INV-16, row 30, §12.5 comment 3

Notes that are not findings (checked, defensible, recorded):
- §5 diagram against the actual call path. (a) The OS launch-failure check sits between `CliRunner.run` and the codec in each flow, not in the codec (deviation 5). (b) The WSL distro-not-found and muse-missing errors are found after the run in `MuseLauncher.launch_failure`, not at resolution as the "D -. not found / batch / WSL" edge shows (deviation 6). (c) A ConfigurationError can also come from inside `execute`: `MusePathTranslator.to_wsl` refuses a UNC workspace after launcher resolution. So on win32 with `wsl_distro` set and no wsl.exe, a UNC workspace reports `muse.wsl_unavailable` before the argument error. INV-4 still holds, because nothing is started or written first.
- Deviation 1 (record annotations `Path | str`, `Sequence[str | Path]`) touches a §8.5 record, which §14 lists under "Ask first". It is recorded, the runtime contract is unchanged, and the alternative (converting in `_call`) would move validation out of the record and break D-26 and row 28. I accept it.
- Deviation 9 (scrub keeps the last 1000 characters) also applies to the workspace sentence, the `searched` details and the invalid-argument rule, not only vendor text. A workspace path longer than 1000 characters would show only its tail. This is improbable, so I am not raising it.
- Scope creep: none found. The extras are `register_secret(content)` for opencode, three Grok sign-in markers, and `NATIVE_LISTING_MAX_ITEMS`. Each is internal and serves a spec ID. No public name, control, dependency or config key was added beyond §8.5.
- request.md §A: naming (`run_grok_thread`, `run_opencode_thread`, `fork_grok_thread`) is exact. The API key goes per call, skills/prompt/config are present, composites are absent (KD-5), and usage, balance and readiness are gone (INV-19 grep: no such def anywhere). No §C decision was reversed. FR-17/AC-20 replies are S6 work.

VERIFIED CLAIMS:
- S3 "feature pack 395 passed, 2 skipped" — HELD (`395 passed, 2 skipped in 36.72s`).
- S3 "run_ci source: SDK-LINT PASS, 5568 passed, 16 skipped, CI passed; S009 350/350" — HELD (my run: `S009 ... 350 350 RATCHETED`, `SDK-LINT: PASS`, `5568 passed, 16 skipped in 84.04s`, `CI passed.`, exit 0).
- GitHub CI run 38754831930 — HELD: `completed success` on 622dabd9; jobs Source 3.12, Source 3.11 and Package all `success`. `git diff 622dabd9 01b20447 -- . ':!docs'` is empty, so HEAD's code is what CI tested.
- Budget "24 added .py files" — HELD (24). §8.4 class list — HELD (45 added `class` lines = 17 new + 16 kept + 12 new enums, no extras).
- "Tests: 18 added files, nothing else; no lint/baseline edits" — HELD (`--name-status ... -- tests` shows 18 A files; `git diff --stat origin/main...01b20447 -- lint pyproject.toml vidbyte/__init__.py vidbyte/tools vidbyte/lib/configs` is empty; no `noqa`/`type: ignore`/`nosec` in the vidbyte diff).
- INV-15 / AC-14 "no literals in harness modules" — HELD (independent AST scan: `INV-15 violations: none`). S3 "every constant has a reader" — HELD (`constants: 198 with no reader: none`).
- AC-1 — HELD. The snippet extracted from spec.md §4 ran with grok.exe/opencode.exe stand-ins on PATH, a redirected home and placeholder keys: returncode 0, three lines, fork id differs from the first id. The test's `SNIPPET` is identical to the spec text (`test SNIPPET == spec section 4: True`).
- AC-20 fixing commits — HELD. 2c39aa72 removes `backends/profiles.py` and `grok/host.py`. 3555279c adds constants, enums, `errors/base.py` and `process/argv.py`. 4c214907 adds `hostkit/errors.py` and `hostkit/launcher.py`. 8d6e643c removes `grok/cli.py` and adds `grok/threads.py`. 0c222707 and d5731e60 add the opencode and Muse threads. All six are ancestors of HEAD.
- "Files outside §12.3: none" — HELD (every changed path maps to a row: 19-31, 32-46, 47-49).
- "I001 on vidbyte/lib/errors/__init__.py is pre-existing" — HELD (ruff gives `Found 1 error` both on HEAD and on `git show origin/main:` piped through stdin).
- §6.2 Proof column and test-plan coverage map name real tests — HELD (49 spec names and 103 plan names; all exist; `test_invalid_` is the glob).
- INV-21 byte-identical restores — HELD (origin/main 179d8adc = merge base; two-dot diff of the restored paths is empty; old spec folder and `native/backends/` are absent).
- INV-2 / INV-19 greps — HELD (no `os.environ[`, `environ.update/pop`, `putenv`, logging or print in native or process; no usage/balance/ready/list/search/revert/diff/mcp/steer/interrupt/wait operation).
- INV-5 "every error carries the caller's thread id and the workspace when known" — DID NOT HOLD for runtime.error (R-C1).
- INV-9 / AC-11 "the Muse temp folder is gone after a cancel" — DID NOT HOLD when the cancel lands during preparation (R-C2).
- §16 R-20 "next step to set HOME/USERPROFILE" — DID NOT HOLD (R-C4).

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `395 passed, 2 skipped in 36.72s`
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `SDK-LINT: PASS` … `5568 passed, 16 skipped in 84.04s (0:01:24)` / `CI passed.` / exit=0 (the package stage was not run: it builds a dist into the worktree)
- `python -X utf8 scratchpad/s4-conformance/snippet_ac1.py <repo>` → `test SNIPPET == spec section 4: True`, `returncode: 0`, 3 lines, `fork id differs: True`, `workspace entries after run: []`
- `python -X utf8 scratchpad/s4-conformance/probes.py <repo>` → E1 `runtime.error | thread_id attr: None | workspace in message: False`; E2 `configuration.invalid_argument | thread_id attr: None`; E3 `temp folders left after the cancelled call: ['tmpc2i1mvig'] [[... 'muse/skills/slow-skill/SKILL.md']]`
- `python -X utf8 scratchpad/s4-conformance/static_checks.py <repo>` → `INV-15 violations: none`, `constants: 198 with no reader: none`
- `python -X utf8 scratchpad/s4-conformance/proof_names.py <repo>` → `spec 6.2 proof names: 49 missing: ['test_invalid_']` (the glob), `test-plan names: 103 missing: none`
- `git diff --diff-filter=A --name-only origin/main...01b20447 -- '*.py' | grep -v '^tests/' | wc -l` → `24`
- `git diff origin/main...01b20447 -- vidbyte | grep -cE "^\+class "` → `45`
- `git diff --stat origin/main 01b20447 -- vidbyte/tools vidbyte/lib/configs vidbyte/__init__.py lint` → (empty); `git rev-parse origin/main` = `git merge-base` = `179d8adc…`
- `gh api repos/cerredz/Vidbyte-SDK/actions/runs/38754831930 --jq ...` → `completed success 622dabd9…`; jobs `Source / Python 3.12 success`, `Source / Python 3.11 success`, `Package success`
- `git show --stat` on 2c39aa72, 3555279c, 4c214907, 8d6e643c, 0c222707, d5731e60 → each touches the files AC-20 names
- `python -m ruff check vidbyte/lib/errors/__init__.py --select I001` (HEAD and origin/main blob) → `Found 1 error.` on both
- greps for suppressions, env writes, logging and removed operations → no hits

Scratch scripts live in C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad/s4-conformance/ (snippet_ac1.py, probes.py, static_checks.py, proof_names.py). Each takes the worktree path as its only argument and needs `PYTHONPATH=<worktree>`.
