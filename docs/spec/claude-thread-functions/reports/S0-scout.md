# S0 scout report — claude-thread-functions

Output: `docs/spec/claude-thread-functions/context/code-map.md`. HEAD `d8ef24f5` (no commits made). Nothing installed, no gate or test run, no `claude` invoked, no state-changing git. Under `docs/` only `docs/spec/claude-thread-functions/request.md` was read; `docs/spec/claude-host/` (24 files) and `docs/spec/harness-thread-functions/` (26 files) were only counted with `git ls-files`; `context/vendor-facts.md` was not opened.

## Planned list (from the request's hints and KD-6/KD-7)

- Build on: `vidbyte/harnesses/native/{__init__, grok/*, opencode/*, muse/*, hostkit/*}`, `vidbyte/lib/process/*`, `vidbyte/lib/dataclasses/{native_threads, process, validation}.py`, `vidbyte/lib/enums/{native_threads, process, failure}.py`, `vidbyte/lib/constants/native_threads.py`, `vidbyte/lib/errors/base.py`.
- Delete: `vidbyte/harnesses/native/claude/*`, `vidbyte/lib/{constants,enums,dataclasses}/claude.py`, `vidbyte/lib/dataclasses/claude_host.py`, `vidbyte/tools/builtins/claude/*`, `vidbyte/tools/toolsets/claude.py`, the `claude` extra, `tests/features/claude_host/`, `docs/spec/claude-host/`.
- Tests: `tests/features/harness_threads/*`.
- Docs to edit: `vidbyte/harnesses/README.md`, `REPO_MAP.md`.

## Files read in full this session

- Rules: `AGENTS.md`, `REPO_MAP.md`, `vidbyte/harnesses/README.md`, `vidbyte/lib/README.md`, `contracts/README.md`, `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`, `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/` (`init.md`, `cli-backed-source-integrations.md`, `local-ci-verification.md`, `blocking-lint-invariants.md`, `strict-config-dataclasses.md`, `comment-format.md`, `class-bound-helpers.md`, `review-scope.md`, `provider-api-contracts.md`, `prebuilt-agents.md`, `diagnostic-context.md`).
- #1036 code: `vidbyte/harnesses/native/__init__.py`; `grok/{__init__,threads,wire}.py`; `opencode/{__init__,threads,wire}.py`; `muse/{__init__,threads,launcher,wire}.py`; `hostkit/{__init__,errors,launcher,skills}.py`; `vidbyte/lib/process/{__init__,argv,runner}.py`; `vidbyte/lib/dataclasses/{process,native_threads,validation}.py`; `vidbyte/lib/enums/{process,native_threads,failure,__init__}.py`; `vidbyte/lib/constants/native_threads.py`.
- #1044 code: `vidbyte/harnesses/native/claude/{__init__,probe,options,failures,sdk,tool_server,history,host,session}.py`; `vidbyte/lib/constants/claude.py`; `vidbyte/lib/enums/claude.py`; `vidbyte/lib/dataclasses/{claude,claude_host}.py`; `vidbyte/tools/builtins/claude/{__init__,_base,descriptions,history,readiness,sessions,turns}.py`; `vidbyte/tools/toolsets/claude.py`; the #1044 diffs of `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/toolsets/__init__.py`, `pyproject.toml`, `vidbyte/lib/errors/{base,__init__}.py`.
- Tests: all of `tests/features/harness_threads/` (FEATURE.md, README.md, conftest.py, fake_harness.py and all 13 test files); `tests/features/claude_host/README.md`.
- Partial reads: `vidbyte/lib/errors/base.py` (header 1–67, `NativeThreadError` 590–645, the `ClaudeOperationError` diff), `vidbyte/lib/enums/failure.py` (header, member lines, tail), `scripts/run_ci.py` (stages and CLI), `lint/run.py` (flags), `pyproject.toml` (extras, pytest config), `.github/workflows/{ci,static-policy}.yml` (triggers, commands), `tests/features/claude_host/test_claude_host_contract.py` (docstring and the REPO_MAP/README pins only). The other 12 files of `tests/features/claude_host/` (FEATURE.md, the fixtures and 10 test files; 5,509 lines) were sized and grepped, not read; they are deleted whole and nothing outside the folder references them.
- Checks: `git grep` importers of every delete-list module (only the two `__init__` files in `lib/enums`, `lib/errors` and the two tools `__init__` files); `git grep` of `contracts/`, `llms.txt`, `artifacts/`, `lint/`, `scripts/`, `.semgrep/` (no ClaudeHost or native-thread names); a read-only `ast` count with the static-policy test's own helpers (13 / 266 / 3 offenders, all in #1044's `claude/` files).

## What the hint got wrong

1. **#1036 is not open any more.** `request.md:124` says #1036 is still open at `5c08c35e`, and KD-8 retargets #1044's base to `feat/native-grok-opencode-meta-hosts`. `origin/main` holds #1036 as squash commit `f216fdcf` (tree identical to `5c08c35e`) plus #1027 (`72a4ade1`) on top. HEAD's merge base with main is still `77fef0e5`.
2. **The Windows rule in #1044 was ".exe or .com", not "claude.exe only"** (`request.md:121`); `vidbyte/lib/constants/claude.py:96`.
3. **"tests check no module holds constants or hardcoded strings"** (`request.md:141`) understates the rule: every literal except `""`, `0`, `1`, docstrings and `__all__` strings fails, including f-string parts, and module-level code may hold only imports, classes, `__all__` and `__init__` bindings.
4. **Not in the hint, but it will bite:** the surface test pins main's `FailureCode` at exactly 120 members and the harness tail at exactly 28 codes; `vidbyte/tools` must equal main byte for byte; the errors test pins the exact code set of the likely-cause and next-step tables; `NativeThreadResult` must refuse `harness="claude_code"`.
5. The request's hint list is otherwise accurate: the named modules exist at the named paths with the described roles, and `CLAUDE_MIN_CLI_VERSION = "2.1.296"` is at `vidbyte/lib/constants/claude.py:24`.
