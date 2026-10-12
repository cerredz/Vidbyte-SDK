Stacked on #769

# Design Doc: CodingAgent environment context

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-11
**Last Updated:** 2026-10-11 (revised for review comment r4244137809 on #778)

---

## 1. Overview

When a `CodingAgent` is built, it now gathers facts about the machine and the project and places them in the model's context as the `ENVIRONMENT` section, right after `AGENTS.md` and before the user's message. The facts are the OS family (Windows, macOS, or Linux) and version, the CPU, today's date and time zone, the root folder, the manifests, lockfiles, and build files in it with the languages and package managers they imply, the dependency names its manifests declare, which dependency folders are already installed, whether the root is in a git repository and on which branch, which bash the `bash` tool runs, and which system package managers and common tools that bash finds on its `PATH`, with their versions. On Windows it says plainly that commands run in Git Bash with POSIX syntax, not PowerShell. All of it is plain code; no model is involved. A new `load_environment` switch, on by default, turns it off.

The section is an `EnvironmentContextItem`, the context primitive in `vidbyte/context/primitives/documents.py`. The loader runs the commands and checks the files, passes the raw results to the item, and the item writes every line the model reads.

The user's words:

> Environment info (environment_context). What it is: Tells the model which OS it's on, which shell it will get, the Python version, and the root folder path. It takes one short block of text. Why it's a good idea: On Windows, CodingAgent runs Git Bash. Without being told, models often write PowerShell commands or assume Linux tools like apt. For example, the model might run Get-ChildItem in bash, get an error, and waste a turn. One line of context prevents that.

> Again, should also be done deterministically trying to run commands, think about all environment information that we could feed the model, once we find out we append this information to the system prompt (for all things we append to context window, should prob be done through helper class [...]) contex window will become something like system prompt, agents.md, environment context, ...(more features), user prompt.

The review comment this revision answers (#778, `environment.py`):

> note, should link the context we actually derive into a "EnvironmentContextItem" as a context primitive in the vidbyte/context folder. Like, for examples, we run all of the commands that we need to get the information about the environment, then we pass the outputs to the context item, and then the context item can properly format the environment context. (should reduce LOC in this file), also try to thinkn about more useful environment information that can be derived through terminal commands (language, dependencies, windows or mac, etc)

---

## 2. Goals & Non-Goals

### Goals
- One `ENVIRONMENT` section, about 15 to 40 lines, built once at construction through the existing `CodingContextWindow`.
- The section is an `EnvironmentContextItem` that holds each fact as a typed field and formats them; the loader writes no text for the model.
- Python-side facts with no subprocess: OS family and version, CPU architecture and count, date and time zone, root path, project marker files with their languages and package managers, declared dependency names, installed dependency folders, git repository and branch.
- One `bash -c` probe, run with the same bash `BashTool` uses, that prints raw records: the bash version, `uname -srm`, the system package managers on its `PATH`, and the path and version of each common tool it finds.
- The Windows line: Git Bash (MSYS), POSIX syntax, not PowerShell or cmd, and paths shown as `/c/Users/...`.
- Failures never raise: no bash, a probe timeout, a non-zero exit, or a malformed manifest still give a section.
- `load_environment: bool = True` on `CodingAgent` and `CodingAgentSettings`.

### Non-Goals
- No environment-variable values, no username and no hostname. The probe never prints `env`, and `uname` is called without `-n`. Paths, such as the root folder or a tool's location, can contain the home folder's name; the model already sees those paths through its tools.
- No git status, commits or diffs; that is a different feature.
- No dependency resolution or installed versions: names come from the manifests as written, and nothing is installed or imported.
- No CLI, no new option beyond the switch, and no per-tool configuration.
- No change to `BashTool`'s behaviour. The one change to `bash.py` is shared with #777 (see Section 6.5).

---

## 3. Background & Context

PR #769 added `CodingContextWindow` and reserved `CodingContextSection.ENVIRONMENT` for this section. A section is one loader file in `vidbyte/agents/coding_context/` whose `load(settings)` returns a section record or `None`, plus one entry in the `sections` tuple in `CodingAgent.__init__`. `AgentsMdLoader` is the reference loader.

`EnvironmentContextItem` already existed in `vidbyte/context/primitives/documents.py` with three caller-supplied fields (`os_name`, `cwd`, `shell`) and the `context_create_environment` tool. This design extends that primitive rather than adding a second one.

On Windows, `BashTool.find_bash()` picks Git for Windows' `bin/bash.exe`, whose `PATH` differs from PowerShell's. Running the probe through that same executable shows the model what *its* bash will find.

Measured on the author's Windows machine, the probe takes about 2.6 s, mostly in `poetry --version` (0.5 s), `npm --version` (0.3 s), `pip --version` and `docker --version` (0.2 s each). The package-manager loop runs `command -v` only, with no version call. The feature pack runs the loader for about 60 distinct `tmp_path` roots.

---

## 4. Requirements

### Functional Requirements
1. `CodingAgent(load_environment=True)` is the default. `CodingAgentSettings._check_context_switches` rejects a `load_environment` that is not a real `bool` with a `ConfigurationError` naming the field.
2. With the switch off, the loader returns `None` and starts no process.
3. With the switch on, the loader returns a `CodingContextSectionItem(section=ENVIRONMENT, item=EnvironmentContextItem(...))`, and the window places that item itself as primitive `coding:environment`, titled `Environment`, after `coding:agents_md` and before the user message.
4. The item always holds the Python-side facts: the OS family from `sys.platform`, `platform.platform()` (plus the distribution name from `/etc/os-release` on Linux), `platform.machine()`, `os.cpu_count()`, the local time with its time-zone name and UTC offset, and the absolute root path.
5. It lists the marker files present directly in the root, from three fixed tables: language markers (`pyproject.toml` gives Python, `package.json` JavaScript, `tsconfig.json` TypeScript, `Cargo.toml` Rust, `go.mod` Go, and so on), lockfiles (`uv.lock` gives uv, `package-lock.json` npm, `pnpm-lock.yaml` pnpm, and so on), and build files (`Makefile`, `justfile`, `tox.ini`, `Dockerfile`, and so on). It derives the languages and package managers from the first two tables.
6. It lists up to 60 dependency names declared in `pyproject.toml` (PEP 621 dependencies, optional dependencies, dependency groups, and Poetry tables), `requirements.txt`, `package.json` (dependencies and devDependencies), and `Cargo.toml` (dependencies and dev-dependencies), each name once. A manifest over 256 KiB, undecodable, unparsable, or of the wrong shape gives no names and never raises.
7. It lists which of `.venv`, `venv`, `node_modules`, and `vendor` are folders in the root.
8. It says whether the root is inside a git repository and names the branch, or the detached commit, read from `.git` with no command. An unreadable `.git` or an empty `HEAD` says the branch could not be read.
9. It says which bash the `bash` tool runs. On Windows, the line says commands run in Git Bash (MSYS) with POSIX syntax, not PowerShell or cmd, and that Windows paths appear as `/c/Users/...` inside bash.
10. With bash found, it runs one `bash -c <script>` in the root, with stdin closed and a 15-second limit. The script prints tab-separated records: `bash` with the version and `uname -srm`; `package-manager` for each of brew, port, apt-get, dnf, yum, zypper, pacman, apk, winget, choco, and scoop it finds; and `tool` for each of git, python, python3, pip, uv, poetry, node, npm, pnpm, yarn, bun, deno, go, cargo, rustc, java, dotnet, ruby, php, docker, make, and gh it finds, with the first line of its version output and its `command -v` path. Only finished lines are parsed.
11. With no bash, the shell line says shell commands will fail, followed by `BashTool.not_found_message()`, which says how to fix it ("Install Git for Windows ..." on Windows, "Install bash ..." elsewhere). The other facts are still shown, and nothing raises.
12. On a probe timeout, a non-zero exit, or a failure to start, the section shows whatever the probe printed, followed by one line saying the tool probe failed and why. Nothing raises.
13. The probe's result is cached for the process, keyed by the bash path and the `PATH` value, so later agents reuse it.
14. `EnvironmentContextItem` checks every new field when it is built and raises a `ConfigurationError` naming the field. An item built with only `os_name`, `cwd`, and `shell`, as the create tool does, renders those three lines as before.

### Non-Functional Requirements
- **Performance:** at most one probe per process for a given bash and `PATH`. Probe output is read up to 8 KiB, and each manifest up to 256 KiB.
- **Security:** no environment-variable values, username or hostname in the section. The probe is a fixed script passed as one argv item, with no shell string (lint S055). Errors name only the exception class (S017).
- **Reliability:** the probe's output goes to a temporary file, not a pipe, so a killed launcher on Windows cannot leave the read waiting on a pipe that a child still holds.
- **Observability:** the section text shows what was found and what failed, and `get_by_id("coding:environment")` returns the item with each fact as a typed field.

---

## 5. High-Level Design

Gathering and wording are split. The loader and its two helpers gather raw facts; `EnvironmentContextItem` turns them into text.

```
CodingAgent.__init__
  -> CodingAgentSettings (load_environment checked)
  -> sections = (AgentsMdLoader.load(s), EnvironmentLoader.load(s), ProgressNotesLoader.load(s))
        EnvironmentLoader.load                        gathers only
          marker files, languages, package managers   file checks
          ProjectDependencies.read(root)              manifest parsing
          .git/HEAD                                   file reads
          BashTool.find_bash()                        no process
          EnvironmentProbe.run(bash, root)            bash -c SCRIPT -> temp file, once per (bash, PATH)
          EnvironmentContextItem(**facts)             the item writes every line
          -> CodingContextSectionItem(ENVIRONMENT, item)
  -> CodingContextWindow.build(sections, context_manager)
        item sections: dataclasses.replace(item, primitive_id="coding:environment")
        text sections: TextContextItem(...)
```

**Key decision: the probe prints raw records, not text.** Each line is a tab-separated record, so the probe's output is data that `EnvironmentProbe` parses into an `EnvironmentProbeResult`. The item owns every word. Only lines that end in a newline are parsed, so a timeout or the byte cap never yields half a record. The path is the record's last field, so a tab inside a version line stays in the version.

**Key decision: git is read from `.git/HEAD`, not from the probe.** Git is the only fact that would make the probe depend on the root. With git in the probe, every new root would pay about 2.6 s on Windows, about three minutes over the feature pack. Without it, one probe serves every agent in the process.

**Key decision: the window places a ready primitive.** `CodingContextSectionItem` pairs a `CodingContextSection` with a context primitive. The window gives the primitive the section's id and places it as it is, so `AgentsMdLoader` and `ProgressNotesLoader` keep returning `CodingContextSectionText` unchanged.

---

## 6. Detailed Design

### 6.1 EnvironmentLoader

**File(s):** `vidbyte/agents/coding_context/environment.py`
**Type:** New file

```python
class EnvironmentLoader:
    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionItem | None: ...
```

1. If `settings.load_environment` is false, return `None`.
2. `_project_files(root)` lists the marker files that are regular files in the root, in table order. `_labels(files, table)` maps them to languages or package managers, each once.
3. `ProjectDependencies.read(root)` returns the declared names.
4. `_git_head(root)` walks the root and its parents for `.git`. A folder is used directly; a file's `gitdir:` target is followed. It reads `HEAD`: `ref: refs/heads/<b>` gives `(BRANCH, b)`, any other non-empty text gives `(DETACHED, text)`, and an empty `HEAD` or a read error gives `(UNREADABLE, None)`. No `.git` gives `(NOT_A_REPOSITORY, None)`.
5. `bash = BashTool.find_bash()` and `probe = EnvironmentProbe.run(bash, root)`.
6. Build `EnvironmentContextItem` from all of it: `_os_family()`, `_linux_distribution()`, `_shell_kind(bash)` (`GIT_BASH` on Windows, `BASH` elsewhere, `None` without bash), and `shell_error=BashTool.not_found_message()` when there is no bash. Return it in a `CodingContextSectionItem`.

### 6.2 EnvironmentProbe

**File(s):** `vidbyte/agents/coding_context/environment_probe.py`
**Type:** New file

`run(bash, root) -> EnvironmentProbeResult` returns an empty result when `bash` is `None`. Otherwise it returns the cached result for `(bash, PATH)` or opens a temporary file, runs `_execute` (which returns the failure reason or `None`), reads the file with `_read_output` up to the cap, parses it with `_parse`, and caches the result, failure included.

### 6.3 ProjectDependencies

**File(s):** `vidbyte/agents/coding_context/project_dependencies.py`
**Type:** New file

`read(root)` reads each manifest with `_text` (a regular file, at most 256 KiB, decoded with replacement), parses TOML and JSON with `_toml` and `_json`, which return an empty table on a parse error, and takes names with one helper per manifest. Requirement strings are reduced to their name by one pattern that requires extras, a version, a marker, a URL, or the end after the name, so `git+https://...` gives no name. Lists and tables of the wrong shape are skipped. Names are kept in first-mention order, each once, capped at 60.

### 6.4 EnvironmentContextItem

**File(s):** `vidbyte/context/primitives/documents.py`
**Type:** Modified

New fields, all with defaults and after the existing ones, so positional and keyword callers and the create tool keep working: `os_family: OperatingSystemFamily | None`, `os_distribution`, `architecture`, `cpu_count`, `local_time` (an aware `datetime`), `project_files`, `languages`, `package_managers`, `dependencies`, `dependency_folders`, `git_state: GitHeadState | None`, `git_ref`, `shell_kind: ShellKind | None`, `shell_error`, `bash_version`, `uname`, `system_package_managers`, `tools: tuple[EnvironmentTool, ...]`, and `probe_error`.

`__post_init__` checks the new fields with `_wrong_texts`, `_wrong_lists`, and `_wrong_values`, and raises one `ConfigurationError` listing every bad field: blank text, a list that is not a tuple of non-blank strings, a wrong enum, a `bool` or non-positive `cpu_count`, a naive `local_time`, a branch or detached state with no `git_ref`, or a `shell_kind` with no `shell`. The original three fields stay unchecked, as before.

`to_context_text()` renders one line per known fact, in the groups host (`_host_lines`), project (`_project_lines`), git (`_git_lines`), shell (`_shell_lines`), and tools (`_tool_lines`), after the shared context introduction. Unknown facts are left out, and an item with none says `N/A`.

### 6.5 BashTool lookup, shared with #777

**File(s):** `vidbyte/tools/builtins/bash.py`
**Type:** Modified, byte-identical to sibling PR #777 (`feat/coding-agent-setup-commands`)

At the orchestrator's request, this branch takes #777's `bash.py` as it is. That version renames `_find_bash()` to the public `find_bash()` and adds `not_found_message()`, the install hint `execute` already returned. The tool's behaviour does not change.

### 6.6 Records, enums, constants, window, agent

- `vidbyte/lib/enums/context.py`: `OperatingSystemFamily` (`WINDOWS`, `MACOS`, `LINUX`, `OTHER`), `GitHeadState` (`NOT_A_REPOSITORY`, `BRANCH`, `DETACHED`, `UNREADABLE`), and `ShellKind` (`BASH`, `GIT_BASH`), exported from `vidbyte/lib/enums/__init__.py`.
- `vidbyte/lib/dataclasses/context.py`: `EnvironmentTool(name, version, path)`; name and path non-blank, version any string.
- `vidbyte/lib/dataclasses/coding.py`: `load_environment: bool = True` and its check; `CodingContextSectionItem(section, item)`, which checks the item by shape (a dataclass instance with a `primitive_id` field, a text title, and `to_context_text`), because `vidbyte/lib` cannot import the context layer; and `EnvironmentProbeResult(bash_version, uname, tools, package_managers, error)`.
- `vidbyte/lib/constants/coding.py`: the probe's timeout, byte cap, and script; `CODING_ENVIRONMENT_LANGUAGE_MARKERS`, `CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS` (tuples of pairs), `CODING_ENVIRONMENT_BUILD_FILES`, `CODING_ENVIRONMENT_DEPENDENCY_FOLDERS`, `CODING_ENVIRONMENT_MANIFEST_MAX_BYTES`, and `CODING_ENVIRONMENT_MAX_DEPENDENCIES`.
- `vidbyte/agents/coding_context/window.py`: accepts `CodingContextSectionItem` and places `dataclasses.replace(item, primitive_id=section.value)`.
- `vidbyte/agents/coding.py`: a `load_environment: bool = True` keyword, passed into the settings, and `EnvironmentLoader.load(settings)` in `sections`.

---

## 7. Data Model Changes

- `CodingAgentSettings`: new field `load_environment: bool = True`, which must be a real bool.
- `EnvironmentContextItem`: the new fields in Section 6.4, all defaulted.
- New records `EnvironmentTool`, `CodingContextSectionItem`, `EnvironmentProbeResult`, and the three enums.

No migration; all are in-memory records.

---

## 8. API Changes

- `CodingAgent(..., load_environment: bool = True, ...)`: `load_environment=1` or `"yes"` raises `ConfigurationError` naming `load_environment`.
- `EnvironmentContextItem(...)`: new optional keyword fields. A bad value raises `ConfigurationError`, where the item used to accept anything; existing callers set none of the new fields.
- `CodingContextWindow.build` accepts `CodingContextSectionItem` beside `CodingContextSectionText`.

There are no HTTP endpoints (N/A).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/coding_context/environment.py` | The loader, which gathers only |
| CREATE | `vidbyte/agents/coding_context/environment_probe.py` | The bash probe, its cache, and its parser |
| CREATE | `vidbyte/agents/coding_context/project_dependencies.py` | Manifest dependency names |
| MODIFY | `vidbyte/context/primitives/documents.py` | `EnvironmentContextItem` fields, checks, and wording |
| MODIFY | `vidbyte/agents/coding_context/window.py` | Place a `CodingContextSectionItem`'s primitive |
| MODIFY | `vidbyte/lib/enums/context.py`, `vidbyte/lib/enums/__init__.py` | Three enums |
| MODIFY | `vidbyte/lib/dataclasses/context.py`, `vidbyte/lib/dataclasses/__init__.py` | `EnvironmentTool` |
| MODIFY | `vidbyte/lib/dataclasses/coding.py` | `load_environment`, `CodingContextSectionItem`, `EnvironmentProbeResult` |
| MODIFY | `vidbyte/lib/constants/coding.py` | Probe script, limits, marker tables, caps |
| MODIFY | `vidbyte/agents/coding.py` | Keyword and `sections` entry |
| MODIFY | `vidbyte/tools/builtins/bash.py` | Public `find_bash()` and `not_found_message()`, taken verbatim from #777 |
| MODIFY | `vidbyte/agents/coding_context/README.md`, `vidbyte/agents/README.md` | Document the section |
| CREATE | `tests/features/coding_agent/test_coding_agent_environment.py` | Feature tests |
| MODIFY | `tests/features/coding_agent/test_coding_agent_contract.py` | `EXPECTED_SIGNATURE` gains `load_environment` |
| MODIFY | existing pack tests that assert an exact request or no section | Pass `load_environment=False` |
| MODIFY | `tests/features/coding_agent/FEATURE.md`, `README.md` | Pack index and contract |
| CREATE | `scripts/test-coding-agent-environment-context.py` | Thin runner for the pytest file |

---

## 10. Testing Plan

All tests are in `test_coding_agent_environment.py`. Most fake bash by pointing `BashTool.find_bash` at `sys.executable` and patching the probe script to a short Python program that prints raw records, so the real `subprocess.run`, temporary-file, parsing, and timeout path runs on every OS. Each test resets the probe cache.

### Unit Tests
- The section is an `EnvironmentContextItem`, rendered after `AGENTS.md` and before the user message, with the OS, the date, the root, the language, package manager, and dependency from the root's files, and the bash version, uname, package manager, and tools the fake bash reported. [Silent Failure]
- On simulated Windows, Linux, and macOS (`sys.platform` patched only while the loader runs), the OS family matches, and only Windows has the Git Bash / POSIX / `/c/Users` line. [Hidden Assumption]
- With no bash, on simulated Windows and on Linux, the item still holds the Python facts and the matching no-bash line, and nothing raises. [Hidden Failure]
- A probe timeout and a probe non-zero exit each keep what was printed first plus the failure line, and nothing raises. [Hidden Failure]
- A cut final line is dropped, a non-record line is ignored, and a tab inside a version stays in the version. [Edge Case]
- `load_environment=False` gives no section and starts no subprocess; `1` and `"yes"` raise `ConfigurationError` naming the field. [Silent Failure, Hidden Assumption]
- A planted `SECRET_TOKEN` value never appears in the section, with the real probe. [Hidden Failure]
- Marker files directly in the root are listed in table order with their languages and package managers; a folder or a nested file named like a marker is not, and an empty root lists nothing. [Edge Case]
- Dependencies come from every manifest, each once; the cap holds; unparsable, wrong-shaped, and undecodable manifests give none and never raise. [Edge Case, Hidden Failure]
- `.venv` and `node_modules` folders are listed, and a file named `vendor` is not. [Edge Case]
- The git state and line name the branch from a subfolder and through a worktree's `gitdir:` file, name a detached commit, and say "could not be read" for a broken `gitdir:` and an empty `HEAD`. [Edge Case]
- The probe runs once for two agents with different roots, and again when `PATH` changes. [Hidden Failure]
- An item built with only `os_name`, `cwd`, and `shell` renders those three lines, and an empty one says `N/A`; ten malformed field values each raise naming that field. [Silent Failure, Hidden Failure]
- The window places a `CodingContextSectionItem`'s primitive itself under the section's id without changing the loader's item; a non-primitive, a class, or a string section is rejected. [Silent Failure, Hidden Assumption]

### Integration Tests
- One real-bash test, skipped when `BashTool.find_bash()` finds none: the item has the bash version, `git` among the tools when git exists, and no failure line.
- Existing tests that assert an exact request or no context manager pass `load_environment=False` (and `progress_notes=False`), and each one is listed in the PR.

### Manual / QA Test Cases
1. On Windows with Git for Windows, build `CodingAgent(root_dir=".")` and print `agent.context_manager.get_by_id("coding:environment").to_context_text()`. Then the Git Bash line, the languages, the dependencies, the system package managers, and the tool list are shown. [Hidden Assumption]
2. Uninstall or hide Git, then build again. Then the "Install Git for Windows" line is shown, and nothing raises. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| bash (Git for Windows on Windows) | any; the script uses only bash 3.2 syntax | Tool probe | Missing: handled by the no-bash line |
| Python stdlib `platform`, `subprocess`, `tempfile`, `datetime`, `tomllib`, `json`, `re` | 3.11+ | Facts, probe, manifests | None |

---

## 12. Rollout & Deployment

- On by default, so every `CodingAgent` now has this section. `load_environment=False` restores the old request exactly.
- Building an agent now starts at most one bash process per process lifetime for a given bash and `PATH`, and reads up to four manifests of at most 256 KiB each.
- Rollback: revert the PR. No data or state is involved.

---

## 13. Open Questions

- [ ] Optional: run the tools' version commands in parallel inside the script to cut the first probe from about 2.6 s to about 0.6 s on Windows. Not built.
- [ ] Optional: report the Python interpreter that runs the SDK as well. The probe already reports the `python` and `python3` that bash finds, which is what the model will run. Not built.
- [ ] Optional: list `package.json` scripts and `Makefile` targets, which name the project's test and build commands. Not built; `AGENTS.md` usually names them.

---

## 14. Alternatives Considered

### Alternative 1: git in the probe, cache keyed by bash path and root
- What: The brief's suggestion.
- Why rejected: Every new root re-runs the probe, about 2.6 s on Windows, or about three minutes over the feature pack.

### Alternative 2: Reuse `BashTool.execute`
- What: Run the script through the tool itself.
- Why rejected: `execute` is async, so running it from a constructor that may already be inside an event loop needs a thread. Its 600-second limit is a module global, and a timeout loses the partial output.

### Alternative 3: Capture the output with a pipe
- What: `subprocess.run(..., capture_output=True, timeout=...)`.
- Why rejected: On Windows, after a timeout, `subprocess.run` waits on the pipe with no limit. If a child of Git's launcher still holds the pipe, construction hangs. A temporary file avoids that.

### Alternative 4: The loader formats text into `CodingContextSectionText`
- What: The first version of this PR. The probe printed finished lines, and the loader wrote the rest.
- Why rejected: Review asked for the facts to go into `EnvironmentContextItem` and for the item to format them. A typed item can also be read field by field, and the loader shrinks to gathering.

### Alternative 5: A new primitive class beside `EnvironmentContextItem`
- What: A coding-only primitive with the new fields.
- Why rejected: `EnvironmentContextItem` already names this concept, and the review named it. Defaulted fields keep its create tool and callers working.

### Alternative 6: The window accepts any context primitive and reads its section from `primitive_id`
- What: No `CodingContextSectionItem`; the loader sets `primitive_id="coding:environment"` itself.
- Why rejected: Ordering, duplicate checks, and placement would each need a branch to map an id back to a section. A record with a `section` field keeps them unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
