# Design Doc: CodingAgent setup commands (the SETUP_RESULTS section)

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

`CodingAgent` gains one keyword, `setup_commands: Sequence[str] = ()`. When it is not empty, the agent runs the commands once, in order, while it is being built (for example `uv sync`, then `npm ci`), and puts a short pass/fail note in the model's context as the reserved `SETUP_RESULTS` section. The environment is then ready before turn one, and when a command fails the model sees the failure and the end of its output in its first request instead of finding a missing dependency partway through the task.

The user's words, verbatim:

> Setup commands (setup_commands). What it is: A list of commands that run once before the agent starts, such as uv sync or npm ci. A short pass/fail note goes into the agent's context. Why it's a good idea: Many failures come from a missing dependency the agent only finds partway through. For example, without setup the agent's first test run fails with ModuleNotFoundError, and it spends several turns installing things. With setup, the environment is ready before turn one.

---

## 2. Goals & Non-Goals

### Goals
- `setup_commands` is a validated tuple on `CodingAgentSettings`. A bare string (`setup_commands="uv sync"`), a non-string item, or a blank item fails with a `ConfigurationError` naming `setup_commands`.
- The commands run once, at construction, in order, each as `bash -c <command>` in `root_dir`, with stdin closed and stderr merged into stdout, using the bash executable and the per-command limit (`BASH_TIMEOUT_SECONDS`) that `BashTool` uses.
- The first failure (non-zero exit, timeout, or failure to start) stops the run; later commands are marked "not run". Nothing raises.
- One line per command. Only the failed command shows output, and only a capped tail of it.
- With no bash, nothing runs and the section says bash was not found, with `BashTool`'s install hint.
- Empty `setup_commands` (the default) runs nothing and adds no section, so every existing request is unchanged.

### Non-Goals
- Secrets handling, environment changes, re-running per run, parallel commands (the brief excludes them; see §13).
- A CLI flag. The feature is used through the Python API only.
- Configurable limits or caps.

---

## 3. Background & Context

- **Why now.** PR #769 added `CodingContextWindow` and reserved `CodingContextSection.SETUP_RESULTS` for this section. A section is one loader with `load(settings) -> CodingContextSectionText | None` plus one entry in `CodingAgent.__init__`'s `sections` tuple.
- **Current state.** Every section is built once, in `CodingAgent.__init__`, which is "before the agent starts". `BashTool` already owns the bash lookup (`_find_bash`, which picks Git for Windows' `bin/bash.exe` on Windows), the install hint, and the limits, so the loader reuses them.
- **Constraint.** `__init__` is synchronous and may be called inside a running event loop, so `asyncio.run` (and `BashTool.execute`) cannot be used. The loader uses the synchronous `subprocess` module.
- **Bug class to avoid.** A bare string is itself a sequence, so `tuple("uv sync")` would run seven one-letter commands. The repo has fixed this four times (#743, #756, #757, #758); the check carries the same `@intent name-lists-reject-bare-strings` marker.

---

## 4. Requirements

### Functional Requirements
1. FR-1. `CodingAgent(setup_commands=...)` accepts any sequence of strings, such as a list or tuple, and stores it as a tuple on `CodingAgentSettings`.
2. FR-2. A `str`, a non-sequence (for example `None`), a non-string item, or a blank item raises `ConfigurationError` naming `setup_commands`, before any command runs.
3. FR-3. Empty `setup_commands` starts no process and adds no section.
4. FR-4. Commands run in order, each as `[bash, "-c", command]` with `cwd=root_dir`, stdin set to the null device, stderr merged into stdout, and on POSIX in a new session.
5. FR-5. Each command is limited to `BASH_TIMEOUT_SECONDS`, read from `vidbyte.tools.builtins.bash` at call time. On timeout the command is killed (POSIX: its whole process group), the wait after the kill is limited to `BASH_KILL_GRACE_SECONDS`, and the command is marked timed out.
6. FR-6. The first command that exits non-zero, times out, or cannot start stops the run. Every later command is listed as "not run, because an earlier command failed" and is never started.
7. FR-7. When `BashTool.find_bash()` returns `None`, no command runs, and the section says bash was not found, with `BashTool.not_found_message()`'s install hint.
8. FR-8. The section (`coding:setup_results`, title `Setup command results`) reads:
   ```
   These commands ran in <root> before this conversation started:
   1. `uv sync`: passed (exit 0, 4.2 s)
   2. `npm ci`: FAILED (exit 1, 12.0 s). Last lines of its output:
      <at most 30 lines, from at most the last 8,192 bytes>
   3. `make build`: not run, because an earlier command failed
   ```
9. FR-9. Loading never raises for a command's outcome.

### Non-Functional Requirements
- **Performance.** Construction blocks while the commands run, up to `BASH_TIMEOUT_SECONDS` (600 s) per command. This is the documented cost of "before the agent starts".
- **Memory.** Output goes to an unnamed temporary file, so a huge output costs disk, not memory, and only the last 8,192 bytes are read back.
- **Reliability.** A background process that keeps the output open cannot hang construction, because the loader waits for bash to exit, not for the output to close.
- **Security.** Commands come from the developer, not the model. Like `BashTool`, they are unsandboxed and inherit the environment. The command is one argv item, so lint S055 holds (no shell string).
- **Observability.** The section text is the record of what happened.

---

## 5. High-Level Design

```
CodingAgent.__init__
  -> CodingAgentSettings(setup_commands=...)   # FR-1, FR-2: checks, stores a tuple
  -> sections = (AgentsMdLoader.load(settings),
                 SetupCommandsLoader.load(settings))   # runs the commands now
  -> CodingContextWindow.build(sections, context_manager)  # places coding:setup_results
  -> BaseAgent.__init__(...)
```

One new loader file, `vidbyte/agents/coding_context/setup_commands.py`, holds `SetupCommandsLoader`. Its narrated `load` finds bash and runs each command, stopping at the first failure. It then returns one `CodingContextSectionText` with section `SETUP_RESULTS`. The window, the enum, and the record do not change.

`BashTool` gets two small public static methods that the loader shares instead of copying them. `find_bash()` is the existing `_find_bash` renamed. `not_found_message()` is the "bash was not found" text with the install hint, moved out of `execute`. `BashTool` behaves exactly as before.

**Key decision: `Popen` and a temporary file instead of `subprocess.run` with a pipe.** The brief asked for plain synchronous `subprocess.run`, and also for the process-group kill on POSIX "if that costs only a few lines". `subprocess.run` cannot kill the group, because it does not hand back the pid. Its Windows timeout path also reads the pipe to the end, and a command left running behind Git's launcher can hold that pipe open forever. `subprocess.Popen`, `wait(timeout=...)`, and an unnamed temporary file as stdout fix both in a few lines. They also bound memory for a huge output. The call is still plain synchronous `subprocess`.

---

## 6. Detailed Design

### 6.1 SetupCommandsLoader

**File(s):** `vidbyte/agents/coding_context/setup_commands.py`
**Type:** New file

#### Interface / API
```python
class SetupCommandsLoader:
    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None: ...
    @staticmethod
    def _run(executable: str, command: str, root: Path, output: BinaryIO) -> tuple[bool, str]: ...
    @staticmethod
    def _output_tail(output: BinaryIO) -> str: ...
    @staticmethod
    def _section(content: str) -> CodingContextSectionText: ...
```

#### Logic / Algorithm
1. `load`: return `None` when `settings.setup_commands` is empty.
2. Get `BashTool.find_bash()`. When it is `None`, return a section that says none of the commands ran, followed by `BashTool.not_found_message()` and each command marked "not run".
3. For each command, in order: if an earlier one failed, add a "not run" line and start nothing. Otherwise open a `tempfile.TemporaryFile()`, call `_run`, and on a failure read `_output_tail`, then add the command's line.
4. `_run` starts `Popen([bash, "-c", command], cwd=root, stdin=DEVNULL, stdout=output, stderr=STDOUT, start_new_session=True)` and returns `(False, "could not start: <ExceptionClass>")` on `OSError` or `ValueError`. It then calls `wait(timeout=BASH_TIMEOUT_SECONDS)`. On `TimeoutExpired`, it kills the group (POSIX `os.killpg(pid, SIGKILL)`, or Windows `process.kill()`), ignoring `ProcessLookupError` and `PermissionError`. It then waits at most `BASH_KILL_GRACE_SECONDS` and returns `(False, "timed out after 600 s")`. Otherwise it returns `(exit_code == 0, "exit N, S.s s")`.
5. `_output_tail` seeks to `max(0, size - 8192)`, decodes UTF-8 with replacement, keeps the last 30 non-trailing-blank lines, and indents each by three spaces.

#### Edge Cases & Error Handling
- **No output from a failed command.** The line reads `FAILED (...), with no output.`
- **A command that cannot start**, such as a removed root folder or a NUL byte: `FAILED (could not start: ValueError)`. The message names only the exception class, as `BashTool` does (S017).
- **A timeout on Windows.** Only Git's launcher is killed, so the command may keep running after construction returns. This is the same limit `BashTool` documents.
- **A setsid descendant on POSIX** survives the group kill. This is the same limit as `BashTool`.
- **A background process the command started** (`server &`). The loader returns when bash exits and does not wait for the output to close.
- **The byte cap can cut a line or a UTF-8 character**, so the first tail line may be partial or start with U+FFFD.
- **A `BaseAgent` keyword error**, such as a missing `name`, is raised after the commands ran, because sections load before `BaseAgent.__init__`. `CodingAgentSettings` errors are raised before anything runs.

### 6.2 CodingAgentSettings.setup_commands

**File(s):** `vidbyte/lib/dataclasses/coding.py`
**Type:** Modified

The new field is `setup_commands: Sequence[str] = ()`. A new helper, `_checked_setup_commands() -> tuple[str, ...]`, is called from `__post_init__`, which stores the result with `object.__setattr__`. The helper raises unless the value is a non-`str` `Sequence` whose items are all non-blank strings. The field is typed `Sequence[str]` for the same reason `root_dir` keeps its raw type: the record must see the raw value to refuse a bare string. After `__post_init__` the value is always a tuple. `CodingAgent.__init__` passes the value through unchanged, so `__init__` raises nothing itself, as the Strict Config Dataclasses guide requires.

### 6.3 CodingAgent

**File(s):** `vidbyte/agents/coding.py`
**Type:** Modified

Adds the `setup_commands: Sequence[str] = ()` keyword, passes it to `CodingAgentSettings`, and adds `SetupCommandsLoader.load(settings)` to the `sections` tuple. It also updates the narration and the header.

### 6.4 BashTool

**File(s):** `vidbyte/tools/builtins/bash.py`
**Type:** Modified

`_find_bash` is renamed to `find_bash`. `not_found_message()` returns the existing `bash was not found. <hint>` text, and `execute` calls it. The tool's behaviour does not change.

### 6.5 Constants

**File(s):** `vidbyte/lib/constants/coding.py`
**Type:** Modified

Adds `CODING_SETUP_OUTPUT_TAIL_LINES = 30` and `CODING_SETUP_OUTPUT_TAIL_BYTES = 8_192`.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings

**Change type:** Modified. One field, `setup_commands: Sequence[str] = ()`, stored as `tuple[str, ...]`. No persistence, so no migration.

---

## 8. API Changes

N/A - no HTTP endpoints. The Python API gains `CodingAgent(setup_commands=...)` and `BashTool.find_bash()` / `BashTool.not_found_message()`. The root `vidbyte` exports are unchanged.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/coding_context/setup_commands.py` | The loader |
| MODIFY | `vidbyte/agents/coding.py` | Keyword and `sections` entry |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | Validated field |
| MODIFY | `vidbyte/lib/constants/coding.py` | Tail caps |
| MODIFY | `vidbyte/tools/builtins/bash.py` | Share the bash lookup and the not-found message |
| MODIFY | `vidbyte/agents/coding_context/README.md` | Section 5 is now filled |
| MODIFY | `vidbyte/agents/README.md` | Coding Agent section: the keyword |
| CREATE | `tests/features/coding_agent/test_coding_agent_setup_commands.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `setup_commands` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Pack contract and index |
| CREATE | `scripts/test-coding-agent-setup-commands.py` | Thin runner (skill Phase 5) |
| CREATE | `docs/design/coding-agent-setup-commands.md` | This doc |

---

## 10. Testing Plan

All tests are in `tests/features/coding_agent/test_coding_agent_setup_commands.py`. They run offline with the scripted model and assert on the system string the model receives. Real-bash cases are skipped when `BashTool.find_bash()` finds none.

### Unit and integration tests
- `test_two_passing_commands_show_two_passed_lines_between_the_earlier_sections_and_the_user_message`: two "passed" lines, after the AGENTS.md section and before the user message, and both commands' effects exist. [Edge Case]
- `test_first_failure_shows_its_exit_code_and_tail_and_never_runs_the_next_command`: exit 3 and the output tail are shown, the second command is "not run", and its marker file does not exist. [Silent Failure]
- `test_a_command_that_times_out_is_marked_timed_out_and_nothing_raises`: the limit is patched to 0.5 s, and `sleep 30` is marked timed out and returns quickly. [Hidden Failure]
- `test_commands_run_in_root_dir_even_when_the_process_cwd_is_elsewhere`: chdir elsewhere with a relative root; `pwd` output and the marker file are under the root. [Hidden Assumption]
- `test_without_bash_the_section_says_so_and_nothing_runs`: `find_bash` is patched to return `None`; the not-found text appears and `subprocess.Popen` is never called. [Hidden Assumption]
- `test_empty_setup_commands_add_no_section_and_start_no_process`: the request has no primitives zone and `subprocess.Popen` is never called. [Edge Case]
- `test_invalid_setup_commands_fail_naming_the_field`, parametrized over a bare string, `None`, a non-str item, and a blank item: `ConfigurationError` naming `setup_commands`, and no process starts. [Hidden Assumption]
- `test_a_huge_failing_output_shows_only_a_capped_tail`: 5,000 numbered lines, then exit 1; only the last 30 lines are shown. One 100,000-character line stays under the byte cap. [Silent Failure]

### Manual / QA Test Cases
1. Given a repo whose `setup_commands=["uv sync"]` fails, when the agent is built, then the first request shows `FAILED (exit 1, ...)` with uv's last lines. [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| bash | Git for Windows `bin/bash.exe`, or `bash` on PATH | Runs the commands | Missing bash gives the not-found section, not an error |

---

## 12. Rollout & Deployment

- Off by default (empty), so existing agents and requests are unchanged. The change is not breaking.
- Rollback: revert the PR.

---

## 13. Open Questions

These are optional and not built:
- [ ] Q-1. Should setup commands get their own time limit instead of the bash tool's 600 s?
- [ ] Q-2. Should secrets or extra environment variables be passable to setup commands only?
- [ ] Q-3. Should commands re-run per `run()` (for example after a long-lived agent idles), or run in parallel?
- [ ] Q-4. Should a passing command's output (for example warnings) ever be shown?

---

## 14. Alternatives Considered

### Alternative 1: `subprocess.run(..., capture_output=True, timeout=...)`
- What: The brief's suggested call.
- Why rejected: It cannot kill the POSIX process group. On Windows its timeout path can wait forever on a pipe held by the command still running behind Git's launcher. It also holds the whole output in memory. See §5.

### Alternative 2: Reuse `BashTool.execute` through `asyncio.run`
- What: Run each command through the bash tool.
- Why rejected: `CodingAgent.__init__` may run inside an event loop, where `asyncio.run` raises.

### Alternative 3: Raise on a failed command
- What: Fail construction.
- Why rejected: The point is that the model sees the failure and fixes it.
