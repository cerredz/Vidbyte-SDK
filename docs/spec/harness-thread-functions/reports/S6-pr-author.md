# S6 · PR author report: harness-thread-functions

Stage S6 of the spec pipeline for PR #1036 (`feat/native-grok-opencode-meta-hosts`). No source or test file changed in this stage. Commits: `6910d89b` (spec frontmatter and §17, deviation 20 wording, review.md R-31 status, `pr-body.md`) and the commit that adds this report.

## 1. What the code does (written from the diff, before reading the spec)

The PR adds nine async module functions under `vidbyte.harnesses.native`: `run_`, `continue_` and `fork_` × `grok`, `opencode`, `muse` `_thread`. Each subpackage `__init__` binds the functions to static methods of a `<Harness>Threads` class (`grok/threads.py`, `opencode/threads.py`, `muse/threads.py`). Every function has the same shape: `prompt` (after `thread_id` for continue and fork), then keyword `api_key`, `workspace`, `model`, `skills`, `config`. opencode's `model` is required and must be `<provider>/<model>`.

The path of one call:

1. `<Harness>Threads._call` builds a `NativeThreadRequest` (`vidbyte/lib/dataclasses/native_threads.py`), which checks every argument in `__post_init__` (key pattern, absolute existing workspace, prompt caps, the Windows quoted-units ceiling for argv prompts, model pattern, thread id tied to the verb, skill folders holding `SKILL.md` with unique names) and stores resolved paths. It checks that `config` is the harness's config record. One guarded `try`: `CancelledError` and `NativeThreadError` pass through, `ConfigurationError` becomes `configuration.invalid_argument` naming the argument, and anything else becomes `runtime.error` named by class only.
2. `<Harness>ThreadRun.execute` resolves the launcher. `NativeLauncher.resolve` (`hostkit/launcher.py`) tries the explicit `<harness>_command`, then `CliRunner.find_program` over the absolute PATH folders (never the current folder), then the installer fallback (`~/.grok/bin/grok[.exe]` for Grok), and refuses `.cmd`/`.bat` on win32. `MuseLauncher.resolve` (`muse/launcher.py`) uses `wsl.exe -d <distro> -e <muse_path>` when `wsl_distro` is set, refuses plain PATH lookup on win32, and maps paths to `/mnt/<drive>/…`.
3. It prepares where the key goes. Grok: `~/.vidbyte/grok-homes/<sha256(normcase(workspace))[:16]>` as `GROK_HOME`, with `skills/` rebuilt to exactly the passed skills (off the event loop), and the key in `XAI_API_KEY` and `GROK_CODE_XAI_API_KEY` of the child only. opencode: `OPENCODE_CONFIG_CONTENT` JSON binding `apiKey` to the provider before the slash in `model`, listing skill folders in place. Muse: a fresh `tempfile.mkdtemp()` folder as `XDG_CONFIG_HOME` with skill copies, `MUSE_AUTH_PATH` pointing at a file inside it that never exists, and `META_API_KEY` in the exec child only. The preparation runs as a shielded task, so a cancel mid-copy waits and removes the folder.
4. Muse continue and fork first run one `muse serve` batch (`initialize`, `initialized`, then `session/read` or `session/fork`) with `META_API_KEY` removed from the environment (`env_remove`). `-32020` is `muse.thread_not_found`; a fork answering its source id is `muse.protocol_mismatch`.
5. `CliArgv.build` (`vidbyte/lib/process/argv.py`) builds argv from `CliOption(flag_enum_member, value)` records: JOINED (`--flag=value`) for Grok and opencode, SEPARATE for Muse and WSL, with the Muse prompt after `--`. The Grok prompt travels in `--single=`; the opencode prompt on stdin.
6. `CliRunner.run` (`vidbyte/lib/process/runner.py`) starts the child through `loop.subprocess_exec` with `CliExitProtocol`, in a new session on POSIX, with stdin a pipe or DEVNULL and the caller's environment minus `env_remove` plus the overlay. It ends at the leader's exit, gives the readers one kill wait, and stops the tree if a reader is still open. On the deadline or a cancel, `ProcessStopper.stop_tree` stops the tree: SIGTERM, grace, SIGKILL and a wait until the group is gone on POSIX; `%SystemRoot%\System32\taskkill.exe /T /F /PID` on Windows, plus a leader kill. Output is capped per stream with a one-byte probe. Every failure is a `CliOutcome` field; only cancellation raises. In WSL mode, a timeout or cancel also runs the in-distro reap of the call's peer mark.
7. The harness reader (`GrokWire.read`, `OpencodeWire.read`, `MuseExecOutput.read`) checks, in order: timeout, output cap, the vendor's key-refusal signal, unknown or wrong thread, run failure, then the answer's shape. It returns `NativeThreadResult(harness, thread_id, text[:100000], text_truncated)`. A continue returns the caller's id; a fork must answer on a new id.
8. Every error goes through `NativeErrorFactory` (`hostkit/errors.py`). It looks the code up in a closed `(harness, problem) → FailureCode` table, registers the key (and the opencode config value) as secrets, replaces them before `HarnessRedactor` and before the 1,000-character tail cap, and joins: head (function, code), summary, workspace, thread id, observation, launcher detail, missing member, exit status, quoted vendor text, likely cause, next step. `NativeThreadError` stores each part as an attribute and in the `DIAGNOSTIC_FIELDS` packet.
9. The Muse temp folder is removed in a `finally` after the reap, however the call ends.

Every fixed value and text is in `vidbyte/lib/constants/native_threads.py`; every flag is a StrEnum member in `vidbyte/lib/enums/native_threads.py`. Nothing in `vidbyte/tools`, `vidbyte/lib/configs`, root `vidbyte/__init__.py`, `lint/`, `scripts/`, `.github/` or `pyproject.toml` differs from `origin/main` (checked with `git diff --stat origin/main...HEAD -- <paths>`, empty).

## 2. The §4 snippet, run against stand-ins

Command: `python <scratchpad>/s6/run_snippet.py <worktree>`. It extracts the python block from spec §4 verbatim, builds a `conftest.Sandbox`, puts `.exe` stand-ins named `grok` and `opencode` (running `fake_harness.py`) in the sandbox `bin`, sets `PATH` to that folder only, `USERPROFILE`/`HOME` to the sandbox home, `XAI_API_KEY`/`DEEPSEEK_API_KEY` to placeholders, and swaps the two literal paths for sandbox folders. Output (Python 3.11.0):

```text
returncode: 0
stdout:
b19b8f35-0d32-41ef-9cbe-1f97a6fe2da0 grok answer to: Add a --verbose flag to cli.py.
e5acf969-c018-4f16-8df0-d4b4e4488167 grok answer to: Now write a test for it.
ses_77fb10dd-8211-4c81-a22e-1599e3cbb62f opencode answer to: Review cli.py for bugs.
stderr tail: ''
lines: 3 | fork id differs from first: True
workspace entries after the run: []
private grok homes: ['db0d2f3ffca33fd2'] | skills in home: [[]]
```

It runs as written; there is no snippet deviation. The last line shows a behavior worth stating in the body: the fork call passed no skills, so the private home's `skills/` was rebuilt empty. Skills apply per call (AC-16 by design). The body says "pass them again on a continue or a fork".

Error sample (`<scratchpad>/s6/error_samples.py`, `PYTHONPATH=$(pwd)`): `grok.not_installed` with PATH empty, and `grok.key_rejected` from the stand-in's `key_rejected` mode on a continue. The second message, quoted in the body with the sandbox path shortened, carried `thread_id: b19b8f35`, `exit_code: 1`, and `key in message: False`.

## 3. Deviations

No deviation beyond spec §17's 24. I checked §8.5's interfaces and §5's flow against the code. The signatures, records, enums, the 28 failure codes and the contract constants match, apart from the recorded deviations (1, 13, 15, 16, 21). §5 has not drifted, so it is unchanged, and §17's S6 row says so. Deviation 20's wording was corrected per R-RRB1.

## 4. Gates

| Gate | Result (final lines) |
|---|---|
| Feature pack on `b3394268` (my run, 3.11.0, win32) | `436 passed, 2 skipped in 51.52s`; skips: `test_harness_threads_launcher.py:100` (POSIX only), `test_harness_threads_runner.py:245` (POSIX only) |
| `python lint/run.py` on `b3394268` (my run) | `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS` |
| run_ci source and package, Semgrep, whole suite, 3.13 pack | from verify-log Iteration 2 (at `53d9f45a`) and the orchestrator's run at `ac8c8cdb`; `git diff --stat 53d9f45a..b3394268 -- vidbyte tests lint REPO_MAP.md pyproject.toml scripts .github` is empty |

## 5. PR state

`gh pr view 1036 --repo cerredz/Vidbyte-SDK --json title,isDraft,baseRefName,url,headRefOid` after `gh pr edit` at `6910d89b`:

```json
{"baseRefName":"main","headRefOid":"6910d89beecaa94326d9015c699e3781c8553ab6","isDraft":false,"title":"feat(harnesses): run, continue and fork Grok, opencode and Muse threads with the caller's API key","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1036"}
```

The title has no `[WIP]`, and the PR is still non-draft. Earlier, `mergeable: MERGEABLE` with `mergeStateStatus: BLOCKED`, which is the repo's required-review state, not a conflict. I left it alone and did not merge. The body file was written to `<scratchpad>/s6/pr-body.body` (`tail -n +2` of `pr-body.md`). The commit that adds this report also updates the GitHub CI row in `pr-body.md` with the `6910d89b` runs below. After the push, the PR body is applied again from that file, so the PR body and `pr-body.md` stay identical.

### Check-runs

Dispatched on `6910d89b` with `gh workflow run ci.yml` and `gh workflow run static-policy.yml` (`--ref feat/native-grok-opencode-meta-hosts`). CI run 38791963789, static policy run 38791967127.

- Attempt 1: `Static policy success`, `Source / Python 3.11 success` (`5569 passed, 56 skipped in 95.88s (0:01:35)` / `CI passed.`), `Package skipped`, and `Source / Python 3.12 failure`. The failure was `1 failed, 5568 passed, 56 skipped, 19 warnings in 126.92s`: `FAILED tests/features/coding_agent/test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git` with "Tool probe failed: bash did not finish within 15 seconds". This is the known flake. The PR does not touch `vidbyte/agents` or `tests/features/coding_agent` (`git diff --stat origin/main...HEAD -- vidbyte/agents tests/features/coding_agent` is empty).
- `gh run rerun 38791963789 --failed` gave attempt 2, `conclusion: success`.
- `gh api repos/cerredz/Vidbyte-SDK/commits/6910d89beecaa94326d9015c699e3781c8553ab6/check-runs` (excluding the four skipped `claude` runs that the thread replies triggered as `pull_request_review` events):

```text
Package               completed  success  …/runs/38791963789/job/116622095112
Source / Python 3.11  completed  success  …/runs/38791963789/job/116620572770
Source / Python 3.12  completed  success  …/runs/38791963789/job/116620570783  (5569 passed, 56 skipped, 19 warnings in 98.31s / CI passed.)
Static policy         completed  success  …/runs/38791967127/job/116618534981
```

The commit that adds this report is the final head, and it changes only `docs/`. Its own CI is dispatched after the push, and the orchestrator's STATUS block reports the result.

## 6. Owner review threads

Replies were posted with `gh api -X POST repos/cerredz/Vidbyte-SDK/pulls/1036/comments/<id>/replies -F body=@reply-<n>.md`. The authenticated `gh` account is `cerredz`, so the replies show under that login. Threads were resolved with `resolveReviewThread`. The final GraphQL read shows `total=4`, each thread with 2 comments, `resolved=true` and `outdated=true`. No other thread or comment was touched.

| Comment | Thread | Reply | Resolved |
|---|---|---|---|
| 4280069037 (`backends/profiles.py:59`) | `PRRT_kwDOShl6qc6sqOnk` | https://github.com/cerredz/Vidbyte-SDK/pull/1036#discussion_r4287233236 | true |
| 4280082885 (`grok/cli.py:36`) | `PRRT_kwDOShl6qc6sqQux` | https://github.com/cerredz/Vidbyte-SDK/pull/1036#discussion_r4287233496 | true |
| 4280090901 (`grok/cli.py:127`) | `PRRT_kwDOShl6qc6sqR_U` | https://github.com/cerredz/Vidbyte-SDK/pull/1036#discussion_r4287233766 | true |
| 4280092326 (`grok/host.py:64`) | `PRRT_kwDOShl6qc6sqSOR` | https://github.com/cerredz/Vidbyte-SDK/pull/1036#discussion_r4287234110 | true |

Every SHA cited in a reply was checked with `git show --stat` first: `2c39aa72` deletes `backends/profiles.py`, `grok/host.py` and the other hosts. `3555279c` adds `constants/native_threads.py`, `enums/native_threads.py`, `process/argv.py` and the `NativeThreadError` change in `errors/base.py`. `4c214907` adds `hostkit/errors.py`, `launcher.py` and `skills.py`. `8d6e643c` deletes `grok/cli.py` and adds `grok/threads.py`. `0c222707` and `d5731e60` are the opencode and Muse threads. `74114bd1` adds `ShellFlag`. `bdc8cd7a` puts stderr on timeouts and caps, and `cdf4efde` puts the workspace and thread id on `runtime.error`.

## 7. Candidate field-guide lessons (not written to the field guide)

### Feature values and texts go in `vidbyte/lib/constants/<domain>.py`; flags are StrEnum members in `vidbyte/lib/enums/<domain>.py`
- **When:** A feature module needs a fixed value: a program or folder name, a vendor marker, a JSON member name, an error text, a next-step string, or a CLI flag.
- **Do:** Put the value under a feature prefix in `vidbyte/lib/constants/<domain>.py` and every flag in a per-program `StrEnum` in `vidbyte/lib/enums/<domain>.py`. Leave the feature module only a docstring, imports, classes, a literal `__all__` and `__init__` bindings. Guard it with an `ast` test that allows only docstrings, `__all__` entries and `""`/0/1 as literals.
- **Because:** The owner flagged module-level constants in three files, saying "wrong file location for all of these" and "wrong file location", and asked for "enums for flags/hardcoded strings" "for all providers". Use `StrEnum`, not `(str, Enum)`: Python 3.11 formats the latter as `Class.MEMBER` in f-strings and would corrupt argv.
- **Check:** `tests/features/harness_threads/test_harness_threads_static_policy.py` is the pattern. `git grep -nE '^[A-Z_]+ = ' vidbyte/<feature>/` prints nothing.
- **Evidence:** PR #1036 comments r4280069037, r4280082885, r4280090901 and r4280092326; commits `3555279c` and `74114bd1`.

### Every argv the SDK builds goes through `CliArgv.build`, including helper shells
- **When:** Code starts any external program: a vendor CLI, `wsl.exe`, an in-distro `sh`.
- **Do:** Build argv with `CliArgv.build(launcher, command=…, options=(CliOption(Flag.X, value), …), style=JOINED|SEPARATE, operands=…)`. Every flag is an enum member, even a one-off like `sh -s`, which is `ShellFlag.READ_STDIN`. Put a prompt inside `--flag=`, after `--`, or on stdin.
- **Because:** Owner comment 3: "this type of code can be cleaner for all providers". Review R-2 found the last flag kept as a string constant, which the `ast` test could not see because it lived in `lib/constants`.
- **Check:** `git grep -nE '"-{1,2}[a-z]' vidbyte/harnesses/native vidbyte/lib/constants/native_threads.py` finds no flag outside an enum.
- **Evidence:** PR #1036; R-2, commit `74114bd1`.

### A feature error names its code, context, vendor text, likely cause and next step
- **When:** A feature raises at a boundary (a vendor process, a validator, the launcher).
- **Do:** Raise one feature error class with a closed failure code from a `(feature, problem) → FailureCode` table. Write one likely cause and one next step per code, as constants. The message holds the function, code, workspace or target, ids, what the SDK observed, and the scrubbed and capped vendor text, including stderr on timeouts. A defect is named by its class only.
- **Because:** Owner comment 1: "error messages need to be in much more detail". Review R-6 and R-7 found timeouts without stderr and `runtime.error` without the workspace or thread id.
- **Check:** A test asserts every part in order through one `check_error` helper (`tests/features/harness_threads/conftest.py`).
- **Evidence:** PR #1036; commits `4c214907`, `bdc8cd7a` and `cdf4efde`.

### On Windows, never start a program by a bare name the OS looks up itself
- **When:** Code starts a child by a bare program name, or calls `shutil.which` on win32.
- **Do:** Look the name up with `CliRunner.find_program`, which uses absolute PATH folders and PATHEXT, never the current folder, and launch the path it returns. Start system tools such as taskkill by `%SystemRoot%\System32\<tool>.exe`.
- **Because:** CreateProcess, and `shutil.which` on 3.11, search the current folder first, so a `grok.exe`, `wsl.exe` or `taskkill.exe` shipped in a cloned repository ran with the caller's key (R-4, R-28).
- **Check:** `git grep -nE 'shutil\.which\(|create_subprocess_exec\("' -- vidbyte/harnesses/native vidbyte/lib/process` prints nothing.
- **Evidence:** PR #1036; commits `f64ba4b8` and `7ec71ec7`.

### A current-folder lookup test must clear `NoDefaultCurrentDirectoryInExePath`
- **When:** Writing a win32 test that plants a program in the current folder and asserts that it never runs.
- **Do:** Call `monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)` in the fixture.
- **Because:** The agent shell sets that variable, and from Python 3.12 on both `shutil.which` and CreateProcess honor it, so the test passes on the unfixed code (R-31: 3.13 with the variable gave `9 passed` on the pre-repair code).
- **Check:** The test fails on the commit before the fix in the agent shell.
- **Evidence:** PR #1036; R-31, commit `4b5eacad`.

### A process run ends at the leader's exit, not at `Process.wait()`
- **When:** Code waits for a child that may leave a grandchild holding its stdout or stderr.
- **Do:** Learn of the exit from the protocol's `process_exited` (`CliExitProtocol`), give the readers one bounded wait, and then stop the tree. Keep that wait and the stop inside the `try` that handles `CancelledError`.
- **Because:** On Python 3.12+, `Process.wait()` resolves only after every pipe closes, so a finished run was reported as timed out after 1,800 s (R-11). A cancel in the post-exit wait then skipped the tree stop (R-27).
- **Check:** A runner test with a leader that exits 0 while a grandchild holds the pipes returns the answer within the kill wait.
- **Evidence:** PR #1036; commits `1583ee8c`, `4a352946` and `53d9f45a`.

### A Windows argv prompt is capped in quoted UTF-16 units
- **When:** A prompt or other long value travels on a Windows command line.
- **Do:** Check `len(subprocess.list2cmdline([value]).encode("utf-16-le")) // 2` against a ceiling below 32,766, with room for the rest of the line. Map `FileNotFoundError` with `winerror == 206` to a launch failure, never "not installed".
- **Because:** Quotes and astral characters double once quoted, so a prompt within its character cap failed as "could not be found" (R-8). A ceiling equal to the character cap refused ordinary prose (R-29).
- **Check:** A 24,000-character prose prompt runs, and 20,000 `"` characters are refused naming the ceiling.
- **Evidence:** PR #1036; commits `2e8ae979` and `5ee16c7d`.

### Comment width applies to tests too
- **When:** Writing comments in new test files.
- **Do:** Apply the 72-column rule of `comment-format.md` to tests as well.
- **Because:** Review R-1 found 124 over-wide comment lines in the new test pack.
- **Check:** `awk 'length($0) > 72' <file> | grep -E '^\s*#'`.
- **Evidence:** PR #1036; commit `1f6fc22e`.

## 8. Things that looked wrong while reading (not fixed: no source changes in S6)

- `vidbyte/harnesses/native/muse/threads.py:9` (header, KNOWN EDGE CASES) says a second cancel "stops only that waiting, never the removal, which then ends in the background". R-RRB1 showed that the removal never runs if the event loop ends first. The spec's deviation 20 is corrected, but this header still carries the old claim, and changing it is a source edit for repair. It is listed under Follow-ups in the PR body.
- `vidbyte/lib/constants/native_threads.py:28-31`: the comment "measured worst case is 608 units" holds only with the default `muse_path`. A 4,096-character `muse_path` measured 4,685 units (re-review 2). Deviation 18 covers the residual, but the comment has no qualifier.
- `vidbyte/lib/process/runner.py:44`, `:66`, `:80`, `:94`, `:196`, `:252` and `:292` compare `sys.platform == "win32"` with a literal, while `NATIVE_WINDOWS_PLATFORM` exists and the harness modules use it. This is legal, because INV-15 covers only `vidbyte/harnesses/native/`, but it is inconsistent with owner comment 3's spirit.
- `vidbyte/lib/process/argv.py:51-52` refuses a dash-led value with an inline `"-"` literal and an f-string message holding the literal `"field"` key. This is the R-19 class (producers write `"field"` on about 20 lines).
- `vidbyte/lib/process/runner.py:160` reads asyncio's private `Process._transport` through `getattr`. It is documented, and it degrades to a pipe leak if a future Python drops the attribute.
- `vidbyte/lib/errors/base.py` is 613 lines against NFR-2's 500 (R-20, and already over on `main`).
- No vacuous test found beyond R-24, which is already a follow-up: the cancellation test polls after `CancelledError`, so it cannot tell "stopped before" from "stopped after".
