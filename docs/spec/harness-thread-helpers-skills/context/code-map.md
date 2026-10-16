# Code map: harness thread helpers and skill functions (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills`, branch `feat/harness-thread-helpers-skills`, HEAD = merge base = `f216fdcf` (the merge of PR #1036). `origin/main` has since moved to `72a4ade1` (#1027; it touches `vidbyte/harnesses/serialization.py` and `vidbyte/lib/util/credential_keys.py`, nothing under `native/`, the tests, `failure.py` or the enums). Installed CLIs on this machine match PR #1036's tested versions: `grok 1.0.52`, `opencode 1.18.31`, `Muse Code 1.0.1` (in WSL distro `MuseUbuntu1`). Every path, symbol and line below was opened in this session; anything not opened is marked "unverified".

---

## 1. Rules, commands and conventions that bind this change

### 1.1 AGENTS.md rules (quoted briefly, by heading)

- **Repository Map:** read `REPO_MAP.md` "before you create a file, move code, or search for where something lives". Each folder's `README.md`: "read it to the end before you change anything inside the folder". Lint A009 keeps every folder README "at or under 40,000 characters".
- **Two rules from the map:** "Do not grep, glob, or read files under `docs/` as part of ordinary work". "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Placement Rules note:** "binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request".
- **1. Keep Call Chains One Level Deep:** "a function may call another of its own functions, but that second function should not call a third". Also: "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator." Calls into another class or a lower layer do not count. PR #1036 review R-3 was a Blocker for exactly this, in `NativeErrorFactory`.
- **2. Narrate Main Functions in Plain English:** "place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments".
- **3. Build in Layers of Small, Single-Purpose Classes:** "a lower layer never imports a higher one". `vidbyte/lib/` is the bottom layer, and lint A006 enforces this. "Keep files well below 1,000 lines". "If describing the job of a function or a class needs the word 'and', it is probably two".
- **4. Use Validated Dataclasses for Core Inputs and Outputs:** validation goes in `__post_init__`. "Prefer `@dataclass(frozen=True, slots=True)`". "type any field whose value comes from a small, closed set as an enum."
- **5. Write Shared Logic Once, as a Canonical Helper in `lib/`:** "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it". Parsing a provider's response is one of the named examples. PR #1036 review R-5 was a Blocker for three copies of a JSON-lines reader.
- **Placement Rules, dataclasses:** "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`". "Add to the existing domain module when there is one". "A feature package may re-export it from its own `__init__.py`".
- **Placement Rules, enums:** "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- **Existing code:** "Do not rewrite untouched code just to make it conform" (from the principles preamble).
- `CLAUDE.md` in the worktree is the single line `@AGENTS.md`. There is no nested rule file, and there is no README under `vidbyte/harnesses/native/`, its subfolders, or `vidbyte/lib/{process,constants,dataclasses,enums}/`.

### 1.2 Commands

| Purpose | Command | Source |
|---|---|---|
| Install | AGENTS.md gives none. `vidbyte-gates.md` gives `python -m pip install -e ".[dev]"` once. request.md §C says "never `pip install -e` into the global Python" and to use the venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills`, which exists. | gates file; request.md:65 |
| Lint, all rules | `python lint/run.py`. It must end with `AGENT-LINT: PASS`. | lint/README.md; gates file |
| Lint, one rule | `python lint/run.py --rule S010`. Add `--all` to list every finding. `--format json` gives JSON output. | lint/README.md |
| Lint baseline | Never raise `lint/baseline.json`, and never add a suppression. `--update-baseline` is only for an IMPROVED rule. | gates file; PR #1036 spec §14 |
| Test, one file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/<file>.py` | PR #1036 spec §13 (line 882) |
| Test, area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | same pattern |
| Test, all | `PYTHONPATH=$(pwd) python -m pytest -q` | PR #1036 spec §13 |
| Full gate | `python scripts/run_ci.py` (stages `all`, `source`, `package`; `scripts/run_ci.py:261-262`). In a worktree, lint/README.md says to set `$env:PYTHONPATH=(Get-Location).Path` first. PR #1036 AC-18 used `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`. | AGENTS.md; lint/README.md |

- What `run_source` runs (`scripts/run_ci.py:79-93`), in order:
  1. tracked-bytecode check
  2. `lint/run.py`
  3. `compileall`
  4. `check_context_write_paths`
  5. `check_context_primitive_introductions`
  6. `check_reasoning_trace_contracts`
  7. `python -m pytest` over all of `tests/`
- **Semgrep is not in `run_ci.py`.** It runs only in `.github/workflows/static-policy.yml:30`, as `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
  - Rule `no-untyped-mapping-fallback` is zero-tolerance. It forbids `def f(..., x: object|Any, ...): if not isinstance(x, Mapping|dict): return ...` anywhere under `vidbyte/`.
  - This matters for any new parser of `summary.json`, `opencode export`, `session list --format json` or MSP answers.
- **CI** (`.github/workflows/ci.yml:3-9`): "TEMPORARILY DISABLED: automatic triggers removed". Only `workflow_dispatch` and `workflow_call` remain. Dispatch both workflows:
  ```
  gh workflow run ci.yml --ref feat/harness-thread-helpers-skills
  gh workflow run static-policy.yml --ref feat/harness-thread-helpers-skills
  ```
  Read the results with `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` (request.md:63). CI is `ubuntu-latest` only, on Python 3.11 and 3.12 (`ci.yml:17-23`).
- **Lint scope:**
  - Python rules scan only tracked `vidbyte/**/*.py`, so a new file is invisible to lint until `git add`.
  - README rules read all tracked READMEs.
  - The baselines are global per-rule counts, so any new finding regresses the rule. Counts include A001 642, A007 255, S008 19, S024 25, S052 0, S061 6, A009 0.
- **Rules most likely to bite new code:**
  - **A001** (`lint/rules/a001_agent_readable_file_headers.py:24-32`): every module docstring needs `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:` within the first 80 lines. The house header also carries `FILE:`, `FUNCTION INVENTORY:` and `WHAT NOT TO DO IN THIS FILE:`.
  - **A007:** a numeric default on a parameter named like `limit`, `timeout`, `char`, `byte` or `depth` is a finding. So `limit=20` must be a named constant.
  - **S008:** C901, PLR0912 and PLR0915.
  - **S024:** nesting depth of at most 3.
  - **S052:** blocking calls inside `async def` (ASYNC100, 105, 110, 220, 221).
  - **S061:** `open(var)`, `x.read_text(var)`, and `shutil.copy`/`move`/`extractall` with a dynamic path.
  - **S015** (`lint/rules/s015_public_export_integrity.py`): every `__all__` name must be statically bound and not duplicated.
  - **C016:** the root `vidbyte/__init__.py` `__all__` must match `contracts/sdk-public-api.json`. Do not touch the root.
  - **C012:** a `model` or `provider` field on any `*Settings`, `*Config`, `*Configuration`, `*Spec`, `*Descriptor` or `*Options` record, or on a record such an owner embeds, must be proven against the SDK model catalog. This is why `dataclasses/native_threads.py` says "A config record never gets a model field".
  - **C006:** numeric guards in records must refuse True, NaN and ±inf.
  - **S009:** the mypy debt ratchet. PR #1036 deviation 1 had to type `workspace` as `Path | str` because of it.
  - **A006:** layering.
  - **S020:** a README `## File Index` must match its folder's tracked children.

### 1.3 PR and commit conventions

- AGENTS.md states none.
- request.md §C (lines 63–65):
  - Push with `git push -u origin feat/harness-thread-helpers-skills`. The upstream is unset on purpose.
  - Dispatch CI as in 1.2.
  - "Never merge; `gh pr merge --admin` needs the user's approval per PR."
- PR #1036 spec §14, the house practice:
  - Cite IDs in commit messages and end each one with the Co-Authored-By line.
  - Catch up with main by merge only; never rebase or force-push.
  - Never modify a test file at implementation time, because the test author owns `tests/`.
  - Never run a real vendor CLI with a real key. Live checks are the user's `! python probe.py` (request.md:60, 95).
- Commit trailer for this session: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## 2. Files this change will touch

Line counts are given as lines / characters. The ceilings are 1,000 lines per file (AGENTS.md) and 40,000 characters per README (A009).

### 2.1 Public surface and binding pattern

- **`vidbyte/harnesses/native/__init__.py`** (62 lines).
  - Today it re-exports the 9 functions, the records `GrokThreadConfig`, `MuseThreadConfig`, `NativeThreadResult` and `OpencodeThreadConfig`, the enums `GrokPermissionMode`, `GrokReasoningEffort` and `MuseReasoningEffort`, and `NativeThreadError`. Its literal `__all__` holds 17 names.
  - Its header says: "Nothing here is re-exported from vidbyte or vidbyte.harnesses" and "Do not export the flow classes, codecs, launchers or hostkit helpers."
  - Will change: new function names and new public records or enums (for example `NativeThreadSummary` and a scope enum) are added here and to `__all__`.
- **`vidbyte/harnesses/native/{grok,opencode,muse}/__init__.py`** (22 lines each).
  - Today each binds three names. Pattern to follow:
    ```python
    from vidbyte.harnesses.native.grok.threads import GrokThreads
    run_grok_thread = GrokThreads.run_grok_thread
    continue_grok_thread = GrokThreads.continue_grok_thread
    fork_grok_thread = GrokThreads.fork_grok_thread
    __all__ = ["continue_grok_thread", "fork_grok_thread", "run_grok_thread"]
    ```
  - Will change: one `name = Class.attr` line per new public function, plus the `__all__` entry.
  - Constraint: INV-15 rule 1 allows only these binding assignments at module level, and the static-policy test checks it.
- **`vidbyte/harnesses/__init__.py`** (95 lines) and **`vidbyte/__init__.py`**: do not re-export native. INV-23 and the surface test assert that `import vidbyte` leaves `vidbyte.harnesses.native` unloaded and that the root `__all__` equals main's. No change.

### 2.2 Per-harness flow modules (the pattern a new helper class copies)

- **`vidbyte/harnesses/native/grok/threads.py`** (188 / 12,872).
  - Today `GrokThreads` (line 50) holds the three public `@staticmethod async def`s. Each is one line, `return await GrokThreads._call(NativeThreadOperation.RUN_GROK_THREAD, NativeThreadVerb.RUN, None, prompt, api_key=…, …)`.
  - `_call` (line 66) is the single guarded try:
    ```python
    errors = NativeErrorFactory(NativeHarness.GROK, operation)
    request: NativeThreadRequest | None = None
    try:
        request = NativeThreadRequest(harness=NativeHarness.GROK, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
        settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
        return await GrokThreadRun.execute(request, settings, errors)
    except asyncio.CancelledError: raise
    except NativeThreadError: raise
    except ConfigurationError as exc: raise errors.from_configuration_error(exc, request) from exc
    except Exception as exc: raise errors.from_unexpected(exc, request) from exc
    ```
  - `GrokThreadRun.execute` (line 89 onward) is the narrated main function. In order:
    1. `NativeLauncher.resolve(config.grok_command, program=GROK_PROGRAM, fallback=_fallback(), errors=…, request=…)`
    2. `_prepare_home` through `asyncio.to_thread`
    3. `errors.register_secret(api_key)`
    4. build the `CliInvocation`
    5. `CliRunner().run`
    6. `outcome.launch_failure` → `errors.from_launch_failure`
    7. `GrokWire.read`
  - **Private home** at lines 141–143:
    ```python
    key = hashlib.sha256(os.path.normcase(str(request.workspace)).encode()).hexdigest()[: native_threads.GROK_HOME_KEY_HEX_CHARS]
    home = Path.home().joinpath(*native_threads.GROK_PRIVATE_HOMES_PARTS, key)
    ```
    - `request.workspace` is already `Path.resolve()`d by the record (D-26).
    - The constants are `GROK_PRIVATE_HOMES_PARTS = (".vidbyte", "grok-homes")` (`constants/native_threads.py:113`) and `GROK_HOME_KEY_HEX_CHARS = 16`.
  - `_environment` (lines 155–165) sets `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `GROK_HOME=str(home)` (line 163) and `GROK_DISABLE_AUTOUPDATER=1`.
  - `_argv` (line 168) uses JOINED style: `--output-format=json --cwd=<ws> --permission-mode=<m> [--model=] [--reasoning-effort=] [--resume=<id>] [--fork-session] --single=<prompt>`.
  - `_fallback` (line 125) is `~/.grok/bin/grok[.exe]`.
  - Will change: the new helper functions are added beside these, or in a sibling module in the same subpackage (open). An SDK-scope Grok helper must compute the same home, and today that code is private to `_prepare_home`, which also creates the folder and rebuilds `skills/`.
- **`vidbyte/harnesses/native/grok/wire.py`** (95 / 6,603).
  - `GrokWire.read(outcome, request, errors, *, timeout_seconds)` checks, in order:
    1. `timed_out` → TIMED_OUT
    2. `stdout_truncated` → OUTPUT_TOO_LARGE
    3. a `{"type":"error"}` object → KEY_REJECTED (by marker) or RUN_FAILED
    4. non-zero exit → RUN_FAILED
    5. no JSON → PROTOCOL_MISMATCH
    6. `sessionId` and `text` checks
    7. `errors.wrong_thread`
    8. return `NativeThreadResult`, with text cut at `NATIVE_RESULT_TEXT_MAX_CHARS`
  - Pattern for any new Grok output reader.
- **`vidbyte/harnesses/native/opencode/threads.py`** (149 / 10,515).
  - The same `OpencodeThreads` (line 42) and `OpencodeThreadRun` (line 81) shape.
  - `NativeLauncher.resolve(config.opencode_command, program=OPENCODE_PROGRAM, fallback=None, …)`.
  - Content comes from `OpencodeWire.config_content(request)`. The key and the content are both registered as secrets.
  - The `CliInvocation` gets `stdin_text=request.prompt`, `cwd=workspace` and `max_output_bytes=NATIVE_PROCESS_MAX_OUTPUT_BYTES`.
  - `_environment` (lines 118–125) sets only `OPENCODE_CONFIG_CONTENT` and `OPENCODE_DISABLE_AUTOUPDATE=1`.
  - `_argv` (line 128) is `run --format=json --dir=<ws> --model=<m> [--agent=] [--variant=] [--session=] [--fork]`.
- **`vidbyte/harnesses/native/opencode/wire.py`** (143 / 10,644).
  - `config_content` builds `{"provider":{<prefix>:{"options":{"apiKey":key}}},"skills":{"paths":[…]}}`.
  - `read` checks timeout, cap, a key-rejected `error` event, the `"Session not found"` stderr marker → THREAD_NOT_FOUND, other error or exit → RUN_FAILED, no `sessionID` → PROTOCOL_MISMATCH, then `wrong_thread`, then the text parts of the last message.
  - It parses with `CliRunner.json_objects`.
- **`vidbyte/harnesses/native/muse/threads.py`** (253 / 17,525).
  - `MuseThreads` (line 47) and `MuseThreadRun.execute` (line 90), in order:
    1. `MuseLauncher(config, errors).resolve(request)`
    2. `visible_path(workspace)`
    3. `register_secret`
    4. `_prepare_config`: `tempfile.mkdtemp()` (line 155) plus skill copies into `muse/skills`, run under a shielded task, with `_discard` at line 166
    5. `new_mark`, then `_overlay`
    6. for continue or fork: `_serve_invocation` (line 188), then `MuseWire.read_answer`
    7. `_exec_invocation` (line 207), then `_run` (line 229), then `MuseExecOutput.read`
    8. `finally` (line 142) runs `NativeSkillFolders.remove(folder)` (line 146)
  - `_overlay` (lines 177–185) sets `MUSE_NO_AUTO_UPDATE=1`, `XDG_CONFIG_HOME=<temp>` and `MUSE_AUTH_PATH=<temp>/<MUSE_AUTH_FILE_PARTS>`.
  - The serve invocation:
    - argv `(prefix…, "serve")`, SEPARATE style
    - `env_remove=(META_API_KEY,)`
    - `timeout=NATIVE_CONTROL_TIMEOUT_SECONDS` (30.0, `constants:24`)
    - stdin carries the batch frames
    - `cwd` is the workspace
  - The exec invocation: `exec --json --provider meta --workspace <ws> [--session-id] [--model] [--reasoning-effort] --user-input-auto-resolve -- <prompt>`, with `META_API_KEY` in the overlay.
  - Will change: the Muse list and compact helpers reuse the serve exchange (`_serve_invocation`, `MuseWire.batch_frames`, `_run` with its reap).
- **`vidbyte/harnesses/native/muse/wire.py`** (211 / 14,896).
  - `MuseWire.new_command_id()` (line 44) returns a UUIDv7.
  - `batch_frames(method: MuseMethod, params)` (line 60) emits initialize (id 1, `clientInfo{name, version=vidbyte.__version__}`), then initialized, then `method` (id 2). Each frame ends with a newline.
  - `session_read_params` (line 83) gives `{"sessionId", "excludeItems": True}`. `session_fork_params` (line 88) adds `commandId`.
  - `read_answer` (line 93) checks timeout, cap, no id-2 answer → PROTOCOL_MISMATCH, error code `-32020` → THREAD_NOT_FOUND, any other error → RUN_FAILED. A continue returns the source id. A fork returns `result.session.sessionId`, which must differ from the source.
  - `_answer` (line 131) picks the frame with `id == 2`.
  - `MuseExecOutput.read` (line 141) parses `stream.kind=="session"` records and `run.terminal.*`.
  - Will change: new params builders and answer readers for `session/list` and `session/compact`. `read_answer` returns a `str` id today (deviation 7), so a list answer needs its own reader.
- **`vidbyte/harnesses/native/muse/launcher.py`** (161 / 11,651).
  - `MusePathTranslator.to_wsl` (line 45) maps `C:\x` to `/mnt/c/x`. A UNC or drive-less path raises `ConfigurationError` naming `workspace`.
  - `MuseLauncher` provides:
    - `wsl_mode` (line 65): `muse_command is None and wsl_distro is not None`
    - `resolve(request)` (line 70)
    - `visible_path` (line 86)
    - `new_mark` (line 91)
    - `environment(overlay, mark)` (line 96), which adds the `WSLENV` forwarding
    - `launch_failure` (line 111)
    - `list_distros` (line 130)
    - `reap` (line 139)
  - `resolve` takes a `NativeThreadRequest`.

### 2.3 Shared plumbing (hostkit and lib)

- **`vidbyte/harnesses/native/hostkit/errors.py`** (224 / 14,943). `NativeErrorFactory(harness, operation)` provides:
  - `register_secret` (line 43) and `scrub` (line 51): registered secrets first, then `HarnessRedactor`, then the last 1,000 characters.
  - static `wrong_thread(request, answered)` (line 64) and `listing` (line 79).
  - `failure(problem, *, request, thread_id, outcome, vendor_text, seconds, cap_bytes, missing_member, searched)` (line 85).
  - `from_configuration_error(exc, request)` (line 129), `from_unexpected(exc, request)` (line 144) and `from_launch_failure(failure, program, *, request: NativeThreadRequest, thread_id=None)` (line 161). In the last one the request is **required**.
  - `_error` (line 202) builds the message: `"{operation} failed with {code}."`, then the summary, context, observation and vendor sentences, then the likely cause and next step.
  - The code is looked up in the closed table `NATIVE_THREAD_FAILURE_CODES[(harness, problem)]`.
  - It lives in hostkit, not lib, because it imports `vidbyte.harnesses.serialization.HarnessRedactor`.
- **`vidbyte/harnesses/native/hostkit/launcher.py`** (77 lines). `NativeLauncher.resolve(command, *, program, fallback, errors, request: NativeThreadRequest)` (line 30) tries, in order:
  1. the explicit argv prefix
  2. `CliRunner.find_program` (absolute PATH folders only, never the current folder; deviation 15)
  3. the fallback
  On win32 it refuses `.cmd` and `.bat` (INV-14).
- **`vidbyte/harnesses/native/hostkit/skills.py`** (78 lines). `NativeSkillFolders.replace` (line 27), `remove` (line 46) and `_matches` (line 61). Relevant only if a skill function passes skill folders.
- **`vidbyte/harnesses/native/hostkit/__init__.py`** (20 lines) exports `NativeErrorFactory`, `NativeLauncher` and `NativeSkillFolders`.
- **`vidbyte/lib/dataclasses/native_threads.py`** (228 lines). Will gain `NativeThreadSummary` (KD-7) and any new request or config records.
  - `NativeThreadRequest` (line 63) fields: `harness, verb, prompt, api_key=field(repr=False) (line 77), workspace, model=None, skills=(), thread_id=None`.
  - `prompt` is required and non-empty (line 92). Its cap is 24,000 on argv or 200,000 for opencode, plus the win32 units check.
  - `api_key` is required (line 106) and must match `^[!-z|~]+$`, at most 4,096 characters.
  - `workspace` must be absolute and existing, and is stored resolved.
  - opencode `model` must be `provider/model`.
  - `skills` holds at most 32 folders.
  - `thread_id` is None exactly when the verb is RUN (lines 132–135).
  - `__post_init__` pattern:
    ```python
    object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
    RecordFieldValidator.require_text(self.prompt, "prompt", max_chars=prompt_cap, pattern=NATIVE_PROMPT_PATTERN)
    ```
  - The config records:
    - `GrokThreadConfig` (line 158): `reasoning_effort=None, permission_mode=DEFAULT, timeout_seconds=1800.0, grok_command=None`
    - `OpencodeThreadConfig` (line 176): `agent, variant, timeout_seconds, opencode_command`
    - `MuseThreadConfig` (line 193): `reasoning_effort, timeout_seconds, muse_command, wsl_distro, muse_path="/usr/local/bin/muse"`
    - `NativeThreadResult` (line 213): `harness, thread_id, text, text_truncated`
  - `__all__` has 5 names. The header says "A config record never gets a model field".
- **`vidbyte/lib/dataclasses/validation.py`** (203 lines). The validators to use (no new ad-hoc checks):
  - `RecordFieldValidator`: `require_text`, `accepts_text`, `require_optional_text`, `require_command_line_units`, `require_number`, `require_int`, `require_bool`, `require_enum`, `require_argv`, `require_directory`
  - `RecordFieldConverter`: `to_tuple`, `to_mapping`, `to_enum`, `to_path`, `require_instance`
  - There is **no datetime or timestamp validator anywhere in `vidbyte/lib`**. `git grep` found no `fromisoformat` helper, so a `since` argument or `created_at`/`updated_at` field has no canonical parser.
- **`vidbyte/lib/enums/native_threads.py`** (199 lines, all `StrEnum`).
  - Members:
    - `NativeHarness` (line 19)
    - `NativeThreadVerb` (line 27): `run, continue, fork`
    - `NativeThreadOperation` (line 35): exactly the 9 function names
    - `NativeThreadProblem` (line 49): `not_installed, launcher_refused, launch_failed, key_rejected, thread_not_found, timed_out, output_too_large, protocol_mismatch, run_failed, wsl_unavailable`
    - `GrokPermissionMode`, `GrokReasoningEffort`, `MuseReasoningEffort`
    - `GrokFlag` (line 97), `OpencodeFlag` (line 110), `MuseFlag` (line 122), `WslFlag`, `ShellFlag`
    - `NativeEnvironmentVariable` (12 values)
    - `MuseMethod` (line 167): `initialize, initialized, session/read, session/fork`
    - `OpencodeEventType`
  - Header: "Do not add an approve-everything member". Also: "A new problem also needs its FailureCode members and its texts".
  - Will change: new operations, problems (for example `command_not_run`), flags (`-n`, `--limit`, `--format`, `--command`, `--session`, `--out`, `--max-count`, `--sanitize`, …), subcommand vocabularies, and MSP methods (`session/list`, `session/compact`, if they exist).
- **`vidbyte/lib/enums/__init__.py`** (289 lines). Every new enum needs an entry in both the import block and `__all__`.
- **`vidbyte/lib/enums/failure.py`** (325 lines). `FailureCode(str, Enum)`.
  - The 28 harness codes are at lines 145–172, after `RULE_EVALUATION_FAILED` (line 144).
  - The header says: "Add a category-prefixed code with docs, mapping coverage, and a focused test."
  - Values must contain "." (`tests/test_session_failures.py`).
- **`vidbyte/lib/constants/native_threads.py`** (452 lines / 31,588 characters). Every new literal goes here: subcommand words, JSON member names, default limits, markers and texts (INV-15).
  - Tables:
    - `NATIVE_THREAD_SUMMARIES` (line 290)
    - `NATIVE_THREAD_OBSERVATIONS` (line 304)
    - `NATIVE_THREAD_FAILURE_CODES` (line 349)
    - `NATIVE_THREAD_LIKELY_CAUSES` (line 383)
    - `NATIVE_THREAD_NEXT_STEPS` (line 419)
  - Tested versions: `GROK_TESTED_VERSION="1.0.52"`, `OPENCODE_TESTED_VERSION="1.18.31"`, `MUSE_TESTED_VERSION="1.0.1"` (lines 206–208).
  - Timing knobs are read through the module at call time.
  - The header says: "A new failure code adds its pair to NATIVE_THREAD_FAILURE_CODES and its own texts". Each per-code text must be unique within its harness.
  - Headroom is about 548 lines. PR #1036 D-11 flips to a per-harness split "if the constants module nears 1,000 lines".
- **`vidbyte/lib/errors/base.py`** (613 lines). `NativeThreadError(AgentExecutionError)` is at line 558.
  - Init: `(message, failure_code, harness, operation, next_step, likely_cause, thread_id=None, exit_code=None, vendor_message=None, error_type="")`.
  - **`self.expected = f"{operation.value} returning a NativeThreadResult"` (line 599)**.
  - `related_docs=("vidbyte/harnesses/README.md",)`, `relevant_tests=("tests/features/harness_threads",)`.
  - The literal 8-name `DIAGNOSTIC_FIELDS` is checked by A003.
  - The file was already over NFR-2's 500 lines (review R-20).
- **`vidbyte/lib/process/{argv.py (55), runner.py (372), __init__.py (20)}`, `vidbyte/lib/dataclasses/process.py` (95), `vidbyte/lib/enums/process.py` (34).** These are the canonical helpers to reuse:
  - `CliArgv.build(launcher, *, command=(), options=(), style, operands=())`. A separate-style value starting with "-" is refused. **Operands are not checked** (`argv.py:9`).
  - `CliRunner.run(CliInvocation) -> CliOutcome` (line 186). It never raises except for cancellation.
  - The child environment is `os.environ` minus `env_remove`, plus `env_overlay` (`runner.py:278-279`).
  - Other helpers: `CliRunner.find_program` (line 241), `CliRunner.json_objects(text)` (line 306), and `ProcessStopper`.
  - `CliInvocation(argv, env_overlay, timeout_seconds, max_output_bytes, cwd=None, stdin_text=None, env_remove=())`.
  - `CliOutcome(exit_code, stdout, stderr, stdout_truncated, stderr_truncated, timed_out, launch_failure)`.

### 2.4 Docs inside the package

- **`vidbyte/harnesses/README.md`** (181 lines / 10,972 characters; 29,028 characters of headroom). There is no `## File Index`, so S020 does not apply.
  - The `native/` bullet at line 178 lists the 9 functions and limitations. It says "SDK Grok runs read nothing from `~/.grok` … (EC-44)", which request.md §C reports as false.
  - Will change: the bullet must describe the helpers and skill functions.
- **`REPO_MAP.md`** (418 lines / 66,978 characters; A009 does not apply because it is not a folder README). The `vidbyte/harnesses/native/` entry is at lines 159–161 ("There are no host objects, model-facing tools or servers here"). The `vidbyte/lib/process/` entry is at line 215.
- **`vidbyte/lib/README.md`** (2,936 characters).

---

## 3. Tests that cover these files

- **Framework:**
  - pytest 8.3.5 with pytest-asyncio 1.3.0 (`pyproject.toml:48-49`).
  - `testpaths=["tests"]`, `addopts=["--strict-config","--strict-markers"]`, `asyncio_default_fixture_loop_scope="function"` (lines 79–81).
  - Async tests use `@pytest.mark.asyncio`.
  - CI is Linux, on 3.11 and 3.12. The local machine is win32.
- **Pack `tests/features/harness_threads/`:**
  - `FEATURE.md` (68 lines), and `README.md` (32 lines, with a `## File Index` that lists every file, so S020 requires each new test file to be indexed once tracked).
  - `conftest.py` (414 lines), `fake_harness.py` (683 lines / 33,740 characters).
  - The test files:

    | File | Lines | Asyncio marks |
    |---|---|---|
    | `test_harness_threads_acceptance.py` | 120 | 3 |
    | `_arguments` | 238 | 14 |
    | `_argv` | 178 | 3 |
    | `_credentials` | 209 | 6 |
    | `_errors` | 204 | 10 |
    | `_launcher` | 268 | 15 |
    | `_process_bounds` | 259 | 11 |
    | `_records` | 116 | 0 |
    | `_runner` | 269 | 12 |
    | `_skills` | 149 | 6 |
    | `_static_policy` | 114 | 0 |
    | `_surface` | 258 | 0 |
    | `_threads` | 207 | 12 |
    | `_wsl` | 184 | 9 |
- **`conftest.py` fixtures:**
  - `lib_api`: lazy imports of records, enums, constants, `FailureCode` and errors.
  - `api` (line 242): `functions[(harness, verb)] = getattr(native, f"{verb}_{harness}_thread")`.
  - `sandbox` (line 251):
    - sets `USERPROFILE` and `HOME` to the sandbox home, a sibling of the workspace
    - sets `PATH` to `sandbox.bin` only
    - sets `tempfile.tempdir`
  - `call` (line 263): runs one thread function against the stand-in through `config.<harness>_command = sandbox.command(...)`.
  - `check_error` (line 296):
    - asserts `error.operation == NativeThreadOperation(f"{verb}_{harness}_thread")` (line 305)
    - asserts `likely_cause` and `next_step` equal the constants maps
    - asserts the INV-5 order
  - Also: `fast_stop`, `wait_until`, `alive`, `wsl_ready`, `pack`.
  - `Sandbox` methods:
    - `command(program, **fields)` (line 116) returns `(sys.executable, "-u", fake_harness.py, scenario.json)`
    - `stand_in(...)` (line 119) builds an `.exe` on win32 with distlib's `t64.exe`
    - `records`, `starts`, `answers`, `snapshot`, `grok_home` (line 203)
  - `private_home(home, workspace)` (line 62) mirrors the SDK's home key.
- **How the fake works:**
  - `fake_harness.py` is a stdlib program run as a real child process and driven by a scenario JSON (`program`, `mode`, `serve_mode`, `log_dir`, `state_dir`, …). It logs per-process JSONL (argv, stdin, the presence and length of the key variables, never their values).
  - **Fake grok** stores sessions at `GROK_HOME/sessions/<sha256(normcase(abspath(cwd)))[:16]>/<id>.json` (lines 306–309). It handles only `--single` runs and has no `sessions`, `export` or `summary.json`.
  - **Fake opencode** accepts only `run` (line 359). Its sessions live at `state_dir/opencode/<id>` (line 365), and it has no `session list`, `export`, `session delete` or `db`.
  - **Fake muse** handles `exec` and `serve` (lines 606–608). Sessions live at `state_dir/muse/<id>` (lines 475, 577), not under `XDG_CONFIG_HOME`.
    - Before dispatching on the method, serve requires `excludeItems is True` and a string `sessionId` (lines 548–550), so a `session/list` frame gets `-32602`.
    - An unknown method gets `-32601` (line 564).
  - **Fake wsl** handles `-l -q`, `-d X -e path`, and the reap.
- **Tests that pin today's surface and must change in the same PR:**
  - `test_harness_threads_surface.py`:
    - `EXPECTED_EXPORTS` (line 31): the native `__all__`, compared exactly at line 127
    - each subpackage `__all__` is exactly 3 functions
    - `EXPECTED_ENUMS` (line 35): exact member lists of every native enum
    - `NEW_FAILURE_CODES` (line 52): the `FailureCode` tail after `RULE_EVALUATION_FAILED` must equal exactly the 28 codes (lines 176–195)
    - `CONTRACT_CONSTANTS` (line 53)
    - `test_thread_functions_are_coroutines_with_the_contract_signature` (line 140)
  - `test_harness_threads_errors.py::test_every_code_has_its_own_likely_cause_and_next_step` (line 193): the table keys must be exactly the 28 codes plus `CONFIGURATION_INVALID_ARGUMENT` and `RUNTIME_ERROR` (line 198).
  - `test_harness_threads_static_policy.py`: `PACKAGE.rglob("*.py")` (line 29), so **every new module under `vidbyte/harnesses/native/` is policed by INV-15 automatically**. `NAMED_MODULES` (line 20) must still exist.
  - `test_harness_threads_credentials.py` (AC-19 snapshot: writes go only where the spec allows) and `_arguments.py` (`refuse`: nothing is written when an argument is refused) are patterns for new "nothing written" checks.
- **Commands:**
  ```
  PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_surface.py
  PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads
  ```
  The area command is stated verbatim in `FEATURE.md:64`. `FEATURE.md` also has a `## Test Suite Map` (lines 47–62), which describes each test file, and an `## Invariants` section that cites PR #1036's INV-1 to INV-23. Both need entries for the new helpers. Its "Inputs and Preconditions" say: "Offline only … No real key, network, vendor CLI or WSL distro is used."

  Other tests that read `FailureCode`: `tests/test_session_failures.py` (every value contains "."), and `tests/test_codex_failure_recovery.py` (only `codex.*` codes).

---

## 4. Notes for the spec author

### 4.1 Open question: where do threads made by `run_/continue_/fork_` land? (request.md §C:94, KD-8)

- **Grok: a private store.**
  - `GROK_HOME=~/.vidbyte/grok-homes/<sha256(os.path.normcase(str(resolved workspace)))[:16]>` (`grok/threads.py:141-143`, `:163`).
  - Inside it, the sessions live under `sessions/<encoded-cwd>` (`vidbyte/harnesses/README.md:178`, EC-43). The `<id>/summary.json` layout comes from request.md §E and is unverified here.
  - A plain `grok` uses `~/.grok`, so SDK threads are invisible to it.
- **opencode: the user's normal store.** The SDK overrides only `OPENCODE_CONFIG_CONTENT` and `OPENCODE_DISABLE_AUTOUPDATE` (`opencode/threads.py:118-125`). Every other variable is inherited from `os.environ` (`lib/process/runner.py:278-279`). Sessions belong to the project chosen by `--dir=<workspace>` (INV-18, A-10).
- **Muse: the user's normal store, and not under the private config folder.**
  - The SDK overrides only `XDG_CONFIG_HOME` (a per-call `tempfile.mkdtemp()`), `MUSE_AUTH_PATH` (inside that folder) and `MUSE_NO_AUTO_UPDATE` (`muse/threads.py:177-185`, `:155`). It also adds `META_API_KEY` for exec, removes it for serve, and sets `WSLENV` forwarding in WSL mode (`muse/launcher.py:96`).
  - The folder is deleted in `finally` (`muse/threads.py:142-146`), yet continue and fork find earlier threads.
  - PR #1036 spec A-20 (verified by an S1 probe on Muse 1.0.1, echo provider): "Muse wrote nothing into any of the four config folders; sessions live under `XDG_DATA_HOME`, which the SDK does not change."
  - **On Windows the store is inside the WSL distro** (`MuseUbuntu1`). The host process cannot read it as files. Only `muse` run inside the distro can, through MSP or `export`.
  - The exact in-distro path is unverified.
- Consequence for KD-8: the code confirms that only Grok has a private store. request.md:242 states the same.

### 4.2 Contradictions ("request assumes X; code shows Y at path:line")

1. **Request assumes the keyless helpers fit PR #1036's seams.** KD-4: helpers "do not call a model", and the key is needed only where required.
   - `NativeThreadRequest` requires a non-empty `prompt` (`dataclasses/native_threads.py:92`) and an `api_key` (`:106`).
   - `NativeErrorFactory.from_launch_failure(..., request: NativeThreadRequest, ...)` (`hostkit/errors.py:161`), `NativeLauncher.resolve(..., request: NativeThreadRequest)` (`hostkit/launcher.py:30`) and `MuseLauncher.resolve(self, request)` (`muse/launcher.py:70`) all need that record.
   - A keyless, promptless helper cannot reach the launcher or the launch-failure path as written.
2. **Request assumes the helpers return `NativeThreadSummary` and other new shapes.** But `NativeThreadError.expected = f"{operation.value} returning a NativeThreadResult"` (`lib/errors/base.py:599`).
3. **Request assumes names such as `list_grok_threads`, `list_grok_threads_since`, `get_grok_thread_lineage` and `run_grok_goal`.**
   - `NativeThreadOperation` holds exactly the 9 names (`enums/native_threads.py:35`), and `error.operation` must be one of its members.
   - `NativeThreadVerb` is `run/continue/fork`, and the request record ties `thread_id` to it (`dataclasses/native_threads.py:132-135`).
   - The test helper derives the operation as `f"{verb}_{harness}_thread"` (`tests/.../conftest.py:305`, and the `api` fixture at `:246`), which does not fit `list_…_threads` or `run_<h>_<skill>`.
4. **Request §E (line 232) assumes Grok listing reads `sessions/<encoded-cwd>/*/summary.json` directly.** PR #1036 D-17 rejected a Grok sessions-folder check because "Grok's storage layout is a vendor detail the SDK should not read". Building this means flipping D-17.
5. **Request (§C:89) says the Grok private home does not isolate, which contradicts EC-44.** The code and docs still claim EC-44: `vidbyte/harnesses/README.md:178` ("SDK Grok runs read nothing from `~/.grok`") and the `grok/threads.py:5` header ("no stored grok login and no file a workspace ships can supply … a hook or a plugin").
6. **Request KD-6 assumes a `<harness>.command_not_run` FailureCode.**
   - The surface test pins the tail to exactly 28 codes (`test_harness_threads_surface.py:52`, `:176-195`).
   - The errors test pins the table keys exactly (`test_harness_threads_errors.py:193-198`).
   - Registering one new code touches every one of:
     1. `failure.py` (append after `MUSE_WSL_UNAVAILABLE`, line 172)
     2. `NativeThreadProblem`, if it is a new problem
     3. `NATIVE_THREAD_SUMMARIES` and `NATIVE_THREAD_OBSERVATIONS` (per problem)
     4. `NATIVE_THREAD_FAILURE_CODES` (per harness and problem)
     5. `NATIVE_THREAD_LIKELY_CAUSES` and `NATIVE_THREAD_NEXT_STEPS` (per code, unique per harness)
     6. the two tests above, plus `EXPECTED_ENUMS`
     7. per the `failure.py` header, "docs, mapping coverage, and a focused test"
7. **A pre-existing test fails on HEAD whenever `origin/main` is reachable.**
   - `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` asserts `len(main_members) == 120` against `git merge-base origin/main HEAD` (`test_harness_threads_surface.py:193`).
   - The merge base is `f216fdcf` (= HEAD), whose `FailureCode` already has **148** members. I verified this with the same AST filter, run on `git show`.
   - It passes in CI only because a shallow clone skips the check (`:5`). INV-22's "120 members on origin/main" is now stale.
8. **Request assumes `opencode session list --format json -n N` "run inside the workspace".** The probe shows no `--dir` option on `session list`. Yet INV-18 guarantees `--dir` so that "an inherited `PWD` never chooses the project", and that guarantee has no equivalent here. Unverified: whether opencode picks the project from the process cwd or from `PWD`.
9. **Request assumes `muse export --session <id> --out <file>`.** The probe shows that without `--out` it writes `trajectory-<timestamp>.json` into the current directory. AC-19 and INV-12 forbid the SDK writing inside the workspace (`muse/threads.py` uses `cwd=<workspace>`). On Windows, `--out` must be a path visible inside WSL (`MusePathTranslator.to_wsl`, `muse/launcher.py:45`).
10. **A Grok USER scope collides with INV-3.** INV-3 says "Grok always runs with `GROK_HOME` set to its private home". A USER-scope `grok sessions …` call would run without it. The probe shows every `grok sessions` subcommand takes `--leader-socket` (default `~/.grok/leader.sock`). Unverified: whether `sessions` talks to a leader process, and whether a private `GROK_HOME` moves that socket.
11. **Request §E assumes `search_grok_threads(workspace, query)` through `grok sessions search <QUERY>`.** QUERY is a positional operand, and `CliArgv` does not check operands (`lib/process/argv.py:9`). INV-7 requires that no caller value is read as a flag.
12. **`muse exec --api-key-stdin` exists (probe), but INV-2 says the key never travels on stdin.** The current code uses `META_API_KEY` in the environment. This is noted only so that nobody "simplifies" to stdin.
13. **The fakes do not match the needed surface.**
    - The fake grok layout (`<sha16>/<id>.json`) is not the real `summary.json` layout.
    - The fake opencode and muse lack the listing, export and delete paths, and the fake serve refuses frames without `sessionId`/`excludeItems` (§3).
    - `fake_harness.py` is 683 lines, so adding all of this risks passing 1,000. `conftest.py` is 414 lines.
14. **Size ceilings.**
    - `lib/errors/base.py` is 613 lines, already over PR #1036's NFR-2 limit of 500 (R-20).
    - `constants/native_threads.py` is 452 lines, and D-11 says to split per harness near 1,000.
    - Each new code adds about 4 texts per harness.
    - PR #1036's §8.4 budget ("24 Python files", "17 classes", "12 new enums") belonged to that PR. Whether this PR inherits a budget is unverified and is the spec's call.

### 4.3 PR #1036 items the new helpers must respect (cited by ID)

- **INV:**
  - **INV-1** says exactly nine functions, and the `__all__` lists are exact. Superseded in part: amend it, and the pinned tests with it.
  - **INV-2:** the key is never on argv, stdin, an error, a repr or a log, and the SDK never writes `os.environ`.
  - **INV-3:** Grok always gets the private `GROK_HOME`. Serve never gets `META_API_KEY`.
  - **INV-4:** every argument is checked before any process starts or any file is written. A refusal is `configuration.invalid_argument` naming the argument.
  - **INV-5:** the error attributes, and the 8-part message order.
  - **INV-6:** the closed classification and its check order. A new problem needs a place in that order.
  - **INV-7:** no caller value is ever read as a flag.
  - **INV-8:** a timeout and an output cap on every child.
  - **INV-9:** cancellation stops the tree, then propagates.
  - **INV-10:** no child waits on stdin.
  - **INV-11:** thread-id rules. Muse `exec --session-id <unknown>` silently creates a thread.
  - **INV-12:** never write into `~/.grok`, `~/.config/opencode`, Muse config folders, or the workspace.
  - **INV-13:** the home key.
  - **INV-14:** batch launchers are refused on win32.
  - **INV-15:** no literals in harness modules (`ast`-checked).
  - **INV-16:** all argv through `CliArgv` as plain `str`.
  - **INV-17:** autoupdate is off in every child.
  - **INV-18:** `--dir`, `--cwd` and `--workspace` are always the resolved workspace.
  - **INV-19** says no "session list/search/read/page … operation exists anywhere". Superseded by request KD-5 for the named helpers only, so it must be amended.
  - **INV-20:** lib never imports upward, and native never imports `vidbyte.tools`.
  - **INV-22:** "120" is stale (see 4.2 #7).
  - **INV-23:** `import vidbyte` does not load native.
- **NG:**
  - **NG-2:** no live turns. Grok `/goal` and `/deep-research` "return right away" onto background workflows (request §C:90), which a one-shot run cannot follow.
  - **NG-3:** superseded only for list, search, read and page. Usage, cost, balance, readiness, version, model lists, revert and diff stay out (KD-5).
  - **NG-4:** no model-facing tools.
  - **NG-5:** async only.
  - **NG-7:** never read a key from the environment.
  - **NG-9:** no new permission controls: no `--auto`, `--always-approve`, Muse `--yolo` or `--approval-mode`.
  - **NG-10:** no root exports and no SDK CLI command.
  - **NG-11:** no fork without a prompt.
  - **NG-12:** never trust the workspace. Muse `exec` and `serve` both offer `--trust-workspace`, and EC-36 says project skills are skipped without it.
- **EC:**
  - **EC-19:** a Muse unknown id → `muse.thread_not_found`, and `exec` never starts.
  - **EC-21:** a Grok thread from another workspace lives in another private home.
  - **EC-37:** the user's personal skills still load.
  - **EC-40:** different spellings of one workspace map to one home.
  - **EC-43:** a home's `sessions/<encoded-cwd>` folder names its workspace, and homes are never pruned.
  - **EC-44:** contradicted (4.2 #5).
  - **EC-45:** Muse exact-id checks.
- **D:**
  - **D-2:** "Flips if … the owner … asks for a verb (for example, delete)". It now flips.
  - **D-3:** the harness is named `muse`.
  - **D-10:** 9 problems × 3 + `muse.wsl_unavailable` = 28 codes.
  - **D-11:** placement, and the constants split near 1,000 lines.
  - **D-12:** Muse refuses `--name=value`, so SEPARATE style.
  - **D-13:** the runner inherits the environment, with the `env_remove` exception.
  - **D-16:** launcher order.
  - **D-17:** Grok's layout is not read (4.2 #4).
  - **D-22:** the import path is `vidbyte.harnesses.native`, with no root exports.
  - **D-23:** the static class, bound as module names, and `<H>ThreadRun.execute`.
  - **D-24:** home location.
  - **D-26:** the stored resolved path.
  - **D-27:** the Grok id is known only at exit. Its runner-up is `-s/--session-id <uuid>`, which the probe confirms exists.
- **Assumptions:**
  - **A-6:** HOME skill folders still load. The request's `grok inspect` finding widens it to hooks, MCP and `~/.claude/Claude.md`.
  - **A-10:** opencode `-s` lookup across projects is unverified.
  - **A-14:** batch serve answers every request before EOF. Verified only for `session/read` and `session/fork`.
  - **A-20:** Muse sessions live in `XDG_DATA_HOME`.
  - **A-21:** Muse credentials are read only from `MUSE_AUTH_PATH` or the XDG config.
- **Open review follow-ups on main (review.md):**
  - R-12: Grok error `type` and Muse terminal markers are string constants.
  - R-14: a stderr flood can leave a key prefix at the cap.
  - R-18: a Grok unknown id gives `run_failed`, not `thread_not_found`.
  - R-23: the Muse "No such file" marker is broad.
  - R-25: a configuration error before the record exists carries no thread id.
  - R-32: the WSL reap is not shielded from a second cancel.

### 4.4 Other harnesses on main with a thread concept

- `vidbyte/agents/codex/` (14 files: `agent.py`, `fork.py`, `transport.py`, …): "Owns the optional Codex app-server client, native threads, and turns" (`transport.py` header). It has `parent_thread_id` forks (`fork.py:44-86`). Out of scope (request KD-2, PR #1055).
- `vidbyte/harnesses/{client,config,contracts,execution,registry,serialization,dataset,errors}.py` and `stores/` are the execution envelope, Sessions-backed persistence and trajectory sinks (`client.py`, `stores/base.py` headers). They have no vendor thread.
- `vidbyte/sessions/` is the SDK's own durable Session checkpoints. It has `failure/recovery/{continue,fork,compact}_recovery.py`, so the words collide, but it is not a harness.
- `vidbyte/agents/coding.py` (`CodingAgent`, a `BaseAgent`) has no vendor thread. The `thread_id` in `vidbyte/lib/outputs/telegram.py:65-67` is a Telegram forum topic.
- No Claude Code harness is on main (request KD-2).
- **Conclusion:** the only thread-concept harnesses on main are grok, opencode and muse (`vidbyte/harnesses/native/`) and codex (`vidbyte/agents/codex/`).

### 4.5 CLI help probes (keyless, read-only; no prompt, no model call)

- **`grok --version`** → `grok 1.0.52 (0920c8169e27) [stable]`. Launcher: `~/.grok/bin/grok`.
- **`grok sessions --help`:**
  - "List, search, or restore sessions"
  - commands: `list` ("same as search with no query"), `search`, `delete` ("Permanently delete a session from history")
  - option `--leader-socket <PATH>` (default `~/.grok/leader.sock`)
- **`grok sessions list --help`:** only `-n, --limit <LIMIT>` "[default: 20]", plus debug and leader-socket. **There is no `--output-format`, no `--cwd` and no JSON output.**
- **`grok sessions search --help`:** `<QUERY>` "Search query (searches summaries and first prompts)", and `-n, --limit` [default: 20]. Text output only.
- **`grok sessions delete --help`:** `<ID>` "Session id to delete".
- **`grok export --help`:** "Export a session transcript as Markdown". `<SESSION_ID> [OUTPUT]`, where OUTPUT is "Output file path, which must not exist yet (default: stdout)". `-c, --clipboard`.
- **`grok --help`, relevant lines:**
  - `-p, --single <PROMPT>`: "Single-turn prompt. Prints the response to stdout and exits"
  - `--verbatim`: "Send the prompt exactly as given". Unverified whether a non-verbatim prompt gets slash expansion.
  - `-s, --session-id`: "Use a specific session UUID for a **new** conversation … With `--resume`/`--continue`, only valid together with `--fork-session`"
  - `-r, --resume [<SESSION_ID_OR_TITLE>]`
  - `--output-format` values: `plain|json|streaming-json|streaming-messages-json`
  - `--permission-mode` values: `default, acceptEdits, auto, dontAsk, bypassPermissions, plan`. `GrokPermissionMode` has 4 of them.
  - `--prompt-file`, `--agent <NAME>`, `--rules`
  - Commands include `export`, `inspect`, `sessions`, `trace`, `usage`, `memory`. **There is no `compact` subcommand.**
- **`opencode --version`** → `1.18.31`. Resolved through the scoop shim folder `C:/Users/422mi/scoop/shims/`, which holds `opencode.exe` plus `opencode.shim` and no `.cmd`, so INV-14 does not refuse it. The Grok launcher is `~/.grok/bin/grok.exe`.
- **`opencode session --help`:** commands `session list` and `session delete <sessionID>`. **There is no search.**
- **`opencode session list --help`:** `-n, --max-count` "limit to N most recent sessions", and `--format` choices `table|json` [default: table]. **There is no `--dir`.**
- **`opencode export --help`:** `opencode export [sessionID]` "export session data as JSON", with `--sanitize` "redact sensitive transcript and file data". There is no output-file option, so it presumably writes to stdout (unverified).
- **`opencode run --help`:**
  - `--command` "the command to run, use message for args"
  - `-s, --session`, `--fork` ("requires --continue or --session")
  - `--agent`, `--variant`, `--format default|json`, `--title`, `--dir`, `--attach`
  - `--auto` "auto-approve permissions … (dangerous!)", which NG-9 rules out
- **`opencode db --help`:** `opencode db [query]` "open an interactive sqlite3 shell or run a query", and `opencode db path` "print the database path". `--format json|tsv` [default: tsv].
- **`opencode --help`:** the commands include `import` and `stats`. **There is no compact or summarize command.**
- **`wsl.exe -l -q`** → `Ubuntu`, `MuseUbuntu1`.
- **`wsl.exe -e muse --help`** (default distro `Ubuntu`) **fails**: "WSL2 is unable to start since virtualization is not enabled … HCS_E_HYPERV_NOT_INSTALLED". Every Muse probe therefore used `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -e /usr/local/bin/muse …`, which matches `MuseThreadConfig.muse_path`'s default.
- **`muse --version`** → `Muse Code 1.0.1 (1.0.1-R2006.1)`.
- **`muse --help`:**
  - commands `resume, exec, config, export, trace, skills ("List, inspect, enable, or disable skills"), sandbox, schema ("Export the MSP wire schema"), serve, session-message, auth, login, logout, init`. **There is no session list and no delete command.**
  - `--provider` "echo or meta (default: meta)", `--preset native-basic, miniswe`
  - `--approval-mode untrusted|on-request|never`, `--yolo`, `--trust-workspace`
  - `--no-session-log` "Do not persist session event logs to disk"
- **`muse export --help`:**
  - `[--session <id|path>] [--last] [--out <file>] [--redacted]`
  - "Without --out, the document is written to trajectory-<timestamp>.json in the current directory … and stdout carries exactly one line: the absolute path written"
  - `--session`: "Session UUID (resolved in the local session store)"
  - The document includes "fork/subagent lineage"
  - "Offline: reads only local files; no network access."
- **`muse exec --help`:**
  - `--json`, `--prompt-file`, `--api-key-stdin` ("Read the provider API key from stdin")
  - `--context-compaction-strategy` and `--context-compaction-soft-threshold`/`-hard-threshold`. These are automatic compaction settings, not a compact command.
- **`muse resume --help`:** `--last` "Resume the most recent session in this workspace".
- **`muse serve --help`:** "serve an MSP session host over stdio". `--no-session-log` "Use memory-only sessions". `--trust-workspace` "Load each session workspace's skills and rules". Approval mode "is selected on the wire".
- **Not probed (unverified):**
  - MSP `session/list`, `session/compact` and their params. The request says "schema only", and I did not read the raw schema capture.
  - The real Grok `summary.json` format.
  - Whether `grok -p "/goal …"` expands.
  - The opencode `session` table and the `parent_id` column.
  - Muse's exact data path in the distro.

### 4.6 Unverified items (collected)

- Grok session layout `sessions/<encoded-cwd>/<id>/summary.json` and its fields (request §E itself says "needs one real thread").
- Whether `grok sessions list` and `search` scope to the process cwd or to `GROK_HOME`, and whether `search` contacts xAI servers (request.md:135).
- The `opencode session list` project selection: cwd vs `PWD`.
- The JSON shapes of `opencode session list --format json` and `opencode export`.
- MSP `session/list` and `session/compact` existence and params on 1.0.1. The fake answers `-32602` or `-32601` for them today.
- Whether Muse `session/compact` needs a credential. The serve child has `META_API_KEY` removed by design (INV-3).
- Field-guide `local-ci-verification.md` (outside the repo; not read).
