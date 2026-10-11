Stacked on #769

# Design Doc: CodingAgent environment context

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11

---

## 1. Overview

When a `CodingAgent` is built, it now gathers a short block of facts about the machine and places it in the model's context as the `ENVIRONMENT` section, right after `AGENTS.md` and before the user's message. The block names the operating system, the CPU, today's date and time zone, the root folder, the project files that tell the model which package manager to use, whether the root is in a git repository and on which branch, which bash the `bash` tool runs, and which common tools that bash finds on its `PATH`, with their versions. On Windows it says plainly that commands run in Git Bash with POSIX syntax, not PowerShell. All of it is plain code; no model is involved. A new `load_environment` switch, on by default, turns it off.

The user's words:

> Environment info (environment_context). What it is: Tells the model which OS it's on, which shell it will get, the Python version, and the root folder path. It takes one short block of text. Why it's a good idea: On Windows, CodingAgent runs Git Bash. Without being told, models often write PowerShell commands or assume Linux tools like apt. For example, the model might run Get-ChildItem in bash, get an error, and waste a turn. One line of context prevents that.

> Again, should also be done deterministically trying to run commands, think about all environment information that we could feed the model, once we find out we append this information to the system prompt (for all things we append to context window, should prob be done through helper class [...]) contex window will become something like system prompt, agents.md, environment context, ...(more features), user prompt.

---

## 2. Goals & Non-Goals

### Goals
- One `ENVIRONMENT` section, about 10 to 30 lines, built once at construction through the existing `CodingContextWindow`.
- Python-side facts with no subprocess: OS and version, CPU architecture and count, date and time zone, root path, project marker files, git repository and branch.
- One `bash -c` probe, run with the same bash `BashTool` uses, that reports the bash version, `uname -srm`, and the path and version of each common tool it finds.
- The Windows line: Git Bash (MSYS), POSIX syntax, not PowerShell or cmd, and paths shown as `/c/Users/...`.
- Failures never raise: no bash, a probe timeout, or a non-zero exit still give a section.
- `load_environment: bool = True` on `CodingAgent` and `CodingAgentSettings`.

### Non-Goals
- No environment-variable values, no username and no hostname. The probe never prints `env`, and `uname` is called without `-n`. Paths, such as the root folder or a tool's location, can contain the home folder's name; the model already sees those paths through its tools.
- No git status, commits or diffs; that is a different feature.
- No CLI, no new option beyond the switch, and no per-tool configuration.
- No change to `BashTool`'s behaviour.

---

## 3. Background & Context

PR #769 added `CodingContextWindow` and reserved `CodingContextSection.ENVIRONMENT` for this section. A section is one loader file in `vidbyte/agents/coding_context/` whose `load(settings)` returns a `CodingContextSectionText` or `None`, plus one entry in the `sections` tuple in `CodingAgent.__init__`. `AgentsMdLoader` is the reference loader.

On Windows, `BashTool._find_bash()` picks Git for Windows' `bin/bash.exe`, whose `PATH` differs from PowerShell's. Running the probe through that same executable shows the model what *its* bash will find.

Measured on the author's Windows machine, the probe takes about 2.6 s, mostly in `poetry --version` (0.5 s), `npm --version` (0.3 s), `pip --version` and `docker --version` (0.2 s each). The feature pack ran in 5.3 s before this change and constructs a `CodingAgent` in about 100 tests, each with a new `tmp_path` root.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent(load_environment=True)` is the default. `CodingAgentSettings._check_context_switches` rejects a `load_environment` that is not a real `bool` with a `ConfigurationError` naming the field.
2. With the switch off, the loader returns `None` and starts no process.
3. With the switch on, the section renders as primitive `coding:environment`, titled `Environment`, after `coding:agents_md` and before the user message.
4. The section always contains the Python-side facts: `platform.platform()` (plus the distribution name from `/etc/os-release` on Linux), `platform.machine()`, `os.cpu_count()`, today's local date with the time-zone name and UTC offset, and the absolute root path.
5. It lists the project marker files present directly in the root (a fixed list including `pyproject.toml`, `uv.lock`, `poetry.lock`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.toml`, `go.mod` and `Makefile`).
6. It says whether the root is inside a git repository and names the branch, or the detached commit, read from `.git` with no command.
7. It says which bash the `bash` tool runs. On Windows, the line says commands run in Git Bash (MSYS) with POSIX syntax, not PowerShell or cmd, and that Windows paths appear as `/c/Users/...` inside bash.
8. With bash found, it runs one `bash -c <script>` in the root, with stdin closed and a 15-second limit, and shows the script's output: the bash version with `uname -srm`, then one line per tool found among git, python, python3, pip, uv, poetry, node, npm, pnpm, yarn, bun, go, cargo, java, dotnet, docker, make and gh, giving the first line of its version output and its `command -v` path.
9. With no bash, the shell line says the bash tool will fail and how to fix it ("install Git for Windows" on Windows, "install bash" elsewhere). The other facts are still shown, and nothing raises.
10. On a probe timeout, a non-zero exit, or a failure to start, the section shows whatever the probe printed, followed by one line saying the tool probe failed and why. Nothing raises.
11. The probe's result is cached for the process, keyed by the bash path and the `PATH` value, so later agents reuse it.

### Non-Functional Requirements
- **Performance:** at most one probe per process for a given bash and `PATH`. Output is read up to 8 KiB.
- **Security:** no environment-variable values, username or hostname in the section. The probe is a fixed script passed as one argv item, with no shell string (lint S055). Errors name only the exception class (S017).
- **Reliability:** the probe's output goes to a temporary file, not a pipe, so a killed launcher on Windows cannot leave the read waiting on a pipe that a child still holds.
- **Observability:** N/A - the section text itself shows what was found and what failed.

---

## 5. High-Level Design

One new loader, `EnvironmentLoader` in `vidbyte/agents/coding_context/environment.py`, follows `AgentsMdLoader`'s shape. Its narrated `load(settings)` returns `None` when the switch is off. Otherwise it collects lines from flat helpers: the host facts, the marker files, the git line, the shell line, and, when bash exists, the probe's lines. It returns one `CodingContextSectionText(section=ENVIRONMENT, title="Environment", ...)`. `CodingAgent.__init__` adds `EnvironmentLoader.load(settings)` to its `sections` tuple, and `CodingContextWindow` puts it in enum order.

```
CodingAgent.__init__
  -> CodingAgentSettings (load_environment checked)
  -> sections = (AgentsMdLoader.load(s), EnvironmentLoader.load(s))
        EnvironmentLoader.load
          host facts (platform, os, datetime)        no process
          marker files, .git/HEAD                    file checks only
          shell line (BashTool._find_bash())         no process
          probe: bash -c SCRIPT  -> temp file        once per (bash, PATH)
  -> CodingContextWindow.build(sections, context_manager)
```

**Key decision: git is read from `.git/HEAD`, not from the probe.** The brief suggested a cache keyed by bash path and root. Git is the only probe output that depends on the root. With git in the probe, every new root would pay about 2.6 s on Windows. Every test in the pack has a new root, which would add several minutes to the feature pack. Reading `.git/HEAD` (following a worktree's `gitdir:` file) is a few lines with no process. Without it, the probe depends only on bash and `PATH`, and one probe serves every agent in the process.

The probe script lives in `vidbyte/lib/constants/coding.py` with the timeout, the output cap, and the marker list. The script prints finished lines, so Python only caps, splits and appends them, and partial output survives a timeout.

---

## 6. Detailed Design

### 6.1 EnvironmentLoader

**File(s):** `vidbyte/agents/coding_context/environment.py`
**Type:** New file

#### Interface / API
```python
class EnvironmentLoader:
    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None: ...
```

#### Logic / Algorithm
1. If `settings.load_environment` is false, return `None`.
2. `_host_lines(root)` returns the OS, CPU, date and root lines.
3. `_marker_line(root)` lists `CODING_ENVIRONMENT_PROJECT_MARKERS` that are regular files in the root.
4. `_git_line(root)` walks the root and its parents for `.git`. A folder is used directly; a file's `gitdir:` target is followed. It reads `HEAD`: `ref: refs/heads/<b>` gives the branch, and anything else gives a detached commit.
5. `bash = BashTool._find_bash()` and `_shell_line(bash)`.
6. If bash exists, `_run_probe(bash, root)` returns `(text, failure)`, using the module cache. `_probe_lines(text, failure)` drops blank lines and carriage returns, and adds the failure line.
7. Return the section, prefixed by one line saying the facts were gathered when the agent was built.

#### Edge Cases & Error Handling
- No bash: no probe, and the no-bash line.
- `subprocess.TimeoutExpired`: `subprocess.run` kills bash. The text written so far is read from the temporary file. On Windows only Git's launcher is killed, as with `BashTool`.
- `OSError` at spawn: failure "could not start (<ExceptionClass>)".
- A non-zero exit: failure "exited with code N", with the output kept.
- An unreadable `.git` or `HEAD`: "inside a git repository; its branch could not be read."
- `os.cpu_count()` returning `None`, or a missing `/etc/os-release`: "unknown", or the distribution is left out.
- Results are cached even when the probe fails, so a hanging tool costs 15 s once per process, not once per agent.

### 6.2 Settings, constants, agent

- `vidbyte/lib/dataclasses/coding.py`: `load_environment: bool = True` and one `isinstance(..., bool)` check in `_check_context_switches`.
- `vidbyte/lib/constants/coding.py`: `CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS = 15.0`, `CODING_ENVIRONMENT_PROBE_MAX_BYTES = 8_192`, `CODING_ENVIRONMENT_PROJECT_MARKERS`, and `CODING_ENVIRONMENT_PROBE_SCRIPT`.
- `vidbyte/agents/coding.py`: a `load_environment: bool = True` keyword, passed into the settings, and `EnvironmentLoader.load(settings)` in `sections`.

---

## 7. Data Model Changes

### 7.1 CodingAgentSettings
**Change type:** Modified. New field `load_environment: bool = True`, which must be a real bool. No migration; it is an in-memory record.

---

## 8. API Changes

### 8.1 `CodingAgent(..., load_environment: bool = True, ...)`
**Change type:** New keyword. `load_environment=1` or `"yes"` raises `ConfigurationError` naming `load_environment`. There are no HTTP endpoints (N/A).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/coding_context/environment.py` | The loader |
| MODIFY | `vidbyte/lib/constants/coding.py` | Probe script, timeout, cap, markers |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `load_environment` field and check |
| MODIFY | `vidbyte/agents/coding.py` | Keyword and `sections` entry |
| MODIFY | `vidbyte/agents/coding_context/README.md`, `vidbyte/agents/README.md` | Document the section |
| CREATE | `tests/features/coding_agent/test_coding_agent_environment.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `load_environment` |
| MODIFY | existing pack tests that assert an exact request or no section | Pass `load_environment=False` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Pack index and contract |
| CREATE | `scripts/test-coding-agent-environment-context.py` | Thin runner for the pytest file |

---

## 10. Testing Plan

All tests are in `test_coding_agent_environment.py`. Most fake bash by pointing `BashTool._find_bash` at `sys.executable` and patching the probe script to a short Python program, so the real `subprocess.run`, temporary-file and timeout path runs on every OS. Each test resets the probe cache.

### Unit Tests
- The section renders after `AGENTS.md` and before the user message, with the OS, the date, the root and the tools the fake bash reported, in the request the model receives. [Silent Failure]
- On simulated Windows (`sys.platform` patched only while the loader runs), the Git Bash / POSIX / `/c/Users` line is present. [Hidden Assumption]
- With no bash, on simulated Windows and on Linux, the section still renders the Python facts and the matching no-bash line, and nothing raises. [Hidden Failure]
- A probe timeout and a probe non-zero exit each show the partial output plus the failure line, and nothing raises. [Hidden Failure]
- `load_environment=False` gives no section and starts no subprocess. [Silent Failure]
- `load_environment=1` and `"yes"` raise `ConfigurationError` naming the field. [Hidden Assumption]
- A planted `SECRET_TOKEN` value never appears in the section, with the real probe. [Hidden Failure]
- The lockfile markers that are present are listed, and absent ones and a folder named like a marker are not. [Edge Case]
- The git line names the branch of a repository and of a worktree's `gitdir:` file, and says when the root is not in a repository. [Edge Case]
- The probe runs once for two agents with different roots, and again when `PATH` changes. [Hidden Failure]

### Integration Tests
- One real-bash test, skipped when `BashTool._find_bash()` finds none: the section has the bash version, `git` among the tools when git exists, and no failure line.
- Existing tests that assert an exact request or no context manager pass `load_environment=False`, and each one is listed in the PR.

### Manual / QA Test Cases
1. On Windows with Git for Windows, build `CodingAgent(root_dir=".")` and print `agent.context_manager.get_by_id("coding:environment").content`. Then the Git Bash line and the tool list are shown. [Hidden Assumption]
2. Uninstall or hide Git, then build again. Then the "install Git for Windows" line is shown, and nothing raises. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| bash (Git for Windows on Windows) | any; the script uses only bash 3.2 syntax | Tool probe | Missing: handled by the no-bash line |
| Python stdlib `platform`, `subprocess`, `tempfile`, `datetime` | 3.11+ | Facts and probe | None |

---

## 12. Rollout & Deployment

- On by default, so every `CodingAgent` now has this section. `load_environment=False` restores the old request exactly.
- Building an agent now starts at most one bash process per process lifetime for a given bash and `PATH`.
- Rollback: revert the PR. No data or state is involved.

---

## 13. Open Questions

- [ ] Optional: run the tools' version commands in parallel inside the script to cut the first probe from about 2.6 s to about 0.6 s on Windows. Not built.
- [ ] Optional: report the Python interpreter that runs the SDK as well. The probe already reports the `python` and `python3` that bash finds, which is what the model will run. Not built.

---

## 14. Alternatives Considered

### Alternative 1: git in the probe, cache keyed by bash path and root
- What: The brief's suggestion.
- Why rejected: Every new root re-runs the probe, about 2.6 s on Windows, and that includes every test in the feature pack.

### Alternative 2: Reuse `BashTool.execute`
- What: Run the script through the tool itself.
- Why rejected: `execute` is async, so running it from a constructor that may already be inside an event loop needs a thread. Its 600-second limit is a module global, and a timeout loses the partial output.

### Alternative 3: Capture the output with a pipe
- What: `subprocess.run(..., capture_output=True, timeout=...)`.
- Why rejected: On Windows, after a timeout, `subprocess.run` waits on the pipe with no limit. If a child of Git's launcher still holds the pipe, construction hangs. A temporary file avoids that.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
