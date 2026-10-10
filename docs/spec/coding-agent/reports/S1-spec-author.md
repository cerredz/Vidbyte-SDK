# S1 spec author report — coding-agent r1

Spec: `docs/spec/coding-agent/spec.md` (revision 1, committed `672157b8`). This report was written after that commit and is not committed.

## What I read

- **Pipeline inputs:** `request.md` (prompts 1–2, §C decisions and constraints, §D weighted words), `context/code-map.md` (scout recon), `spec-template.md`, `house-style.md`, and `vidbyte-gates.md`.
- **Repo rules:**
  - `AGENTS.md` and `REPO_MAP.md`.
  - The folder READMEs `vidbyte/agents/README.md` and `vidbyte/tools/README.md`.
  - The agentic-engineering `file_headers.md`.
  - Field-guide entries: init, model-facing-tool-contracts, cli-backed-source-integrations, local-ci-verification, blocking-lint-invariants, strict-config-dataclasses, runtime-boundaries, review-scope, agents-md-map, class-bound-helpers, priced-operation-execution, provider-api-contracts.
- **Source:**
  - Agents: `agents/base.py` (constructor, restore, catalog building), `agents/runtime.py` (`_run_tool_call`, `_check_permission`, `_execute_tool`, `_record_operation_usage`, `_billable_attempts`, `_truncate_for_tool_settings`), `agents/fork.py`, `agents/handoff.py`, `agents/continual_trace.py`, `agents/jev/agent.py`, `agents/settings/{tool,loop}.py`.
  - Tools: `tools/base.py` (`_ToolWrapper`, `_CustomizedTool`, `_unwrap_tool`), `tools/activity.py`, `tools/catalog.py`, the filesystem tools, code_search base/glob/grep, `operations/{base,fetch}.py` and all clients, `code_execution.py`, `mcp/{transport,bridge}.py`.
  - Lib and other modules: `lib/http/transport.py`, `lib/dataclasses/{filesystem,security,operations,tools}.py`, `sources/fetches/http.py`, `middleware/builtins/tool_error_policy.py`, `sessions/session.py`.
  - Exports: the three `__init__` files to be touched and `contracts/sdk-public-api.json`.
- **Lint rules:**
  - Read in source: a001, a002, a005, a007, s016, s017, s021, s025, s055, s061, s062.
  - Confirmed present by file listing: s006, s007, s008, s012, s015, s019, s039, s041, s045, s051, s052, c016, a006, a008, s009.
- **Tests (for §13 facts only):** `agent_test_support.py`, `test_agent_tool_loop.py`, `test_jev_agent.py`, `test_restore_permission_policy.py`, `test_web_operation_client_retry.py`, `test_mcp_stdio_transport.py`, and `pyproject.toml`.
- **Run or verified on this machine (2026-10-10):**
  - `python lint/run.py` on the clean branch finished with `SDK-LINT: PASS` in about 59 s. The counts are in spec §11.
  - Windows bash resolution:
    - `shutil.which("bash")` returns `C:\WINDOWS\system32\bash.EXE`, which exits 1 with "WSL2 is unable to start".
    - `shutil.which("git")` returns `C:\Program Files\Git\cmd\git.EXE`, and `C:\Program Files\Git\bin\bash.exe` beside it works.
  - Import order: `vidbyte.agents.base` already loads `vidbyte.tools.builtins`, `operations.fetch`, `vidbyte.tools.filesystem` and `code_search.glob`, so a new `vidbyte/agents/coding.py` cannot create a new import cycle.
  - `BaseAgent.__init__` has 31 keyword-only parameters, and `name` and `system_prompt` have no default.
  - mypy's typeshed declares `os.killpg` and `signal.SIGKILL` only under `sys.platform != "win32"`.
  - Pricing reads only `metadata["operation_usage"]` (`PricedOperationTool.units_used`, `mode_used`, `attempts_used`). This is why a view that replaces only `output` keeps billing identical.
  - Every line-number citation in the spec was re-checked against the tree before committing, and five were corrected.

## Approaches weighed

- **Smallest design: BaseAgent plus the seven tools, nothing else (rejected).** Three of the seven tools would be DENIED under the default policy. A keyed WebFetch would show the model only `N. url (len chars)`. On the user's Windows machine every bash call would hit the WSL launcher and fail. A factory function would also fail "create a new CodingAgent class". All of this is recorded in spec §8.3.
- **Constructor shape.** I chose a thin subclass with `**kwargs` pass-through (precedents: `HandoffAgent`, `ContinualTraceAgent`). The runner-up was to redeclare all 31 `BaseAgent` parameters, which I rejected because the copy would drift.
- **WebFetch selection.**
  - Chosen: four key parameters. More than one key, or a blank key, is a `ConfigurationError`.
  - Runner-up: a provider enum plus one key. That would add an enum the request never asked for.
  - Linkup is excluded because it has no client and its tool is always a stub.
- **Showing page text.**
  - Chosen: a private `_ToolWrapper` view in the CodingAgent module.
  - Runner-up: change `_render_fetched_pages` for everyone. Rejected because of the blast radius and the documented two-channel contract in `tools/README.md`.
- **Default permissions.** Chosen: `PermissionPolicy.allow_all()`, with a caller's policy used unchanged. request.md §C marks this as forced.
- **Bash bounds.**
  - Chosen: fixed constants of 600 s and 1,000,000 bytes in `vidbyte/lib/constants/bash.py`.
  - Runner-up: no tool-level timeout, relying only on `ToolSettings.tool_timeout_seconds`. `runtime-boundaries.md` leans that way, but that setting defaults to `None`, so a `sleep 9999` would hang the run forever.
  - A configurable knob was not requested, so it is Q-2 with default **no**.
- **Bash environment.**
  - Chosen: inherit the parent environment.
  - Runner-up: the allow-listed environment from `build_child_env`. Rejected because the request says minimal and an allow-list was not discussed. It is Q-3 with default **no**.
- **Exit semantics.** A finished command is a success whatever its exit code. Treating a non-zero exit as an error would trip `max_consecutive_failures` on ordinary failing tests.
- **Error codes.** Chosen: string codes in `metadata["error"]`, which is how every builtin does it. Runner-up: a new enum. It is flagged in D-15 so a reviewer can flip it.
- **Edit tool.** Chosen: `ReplaceTextTool`, which shares the file config and requires an exact single match. Runner-up: `PatchTool`. This is Q-1.

## Where I disagreed with the scout, the request, or other inputs

1. **Import cycle (scout raised it as a risk).** It does not happen. The modules `coding.py` needs are already in `sys.modules` once `vidbyte.agents.base` is imported (checked directly). The only rule is to import concrete submodules, never the `vidbyte.tools.builtins` package root (checklist item, A006).
2. **Windows bash (request §C left it open).** I resolved it from evidence: the bash on `PATH` is the failing WSL launcher, so on win32 the tool uses Git for Windows' `bin/bash.exe` located from `git` (D-13).
3. **`vidbyte-gates.md` says semgrep runs inside `run_ci.py`.** It does not. Semgrep runs only in `.github/workflows/static-policy.yml`, which is dispatch-only. Spec §11 gives the exact semgrep commands.
4. **Lint counts on main are below baseline (IMPROVED) for A002, S017, S025, S051 and others.** The scout reported baseline numbers. The spec forbids consuming this headroom.
5. **cli-backed-source-integrations.md says "do not expose command strings to model-facing inputs".** This conflicts with the user's explicit request for a Bash tool. The user wins, and the conflict is recorded in §11 and T-2.
6. **S012 and S013.** These do not apply to a subprocess. The timeout reasoning is carried by D-11 instead.
7. **REPO_MAP.md.** It needs no edit, because the map is folder-level and no folder is added.
8. **Keyed fetch content gap.** Neither the request nor the scout noticed that the model never sees keyed page text (`fetch.py:39-42`). I treated closing it as forced by the word "WebFetch" (FR-6, A-1). It is the one place where I added behaviour beyond the literal tool list, so the user should confirm it.

## Assumptions I am least sure of

- **A-1, that WebFetch should show page text.** If the user is happy with the summary-only output, `_FetchedPagesView` and FR-6 should be deleted. This is the biggest design addition.
- **A-3, that inheriting the full environment is acceptable.** Bash commands can read every secret in the developer's environment. The user said "minimal", but may not have considered this.
- **A-4, the 600 s and 1 MB bounds.** 1 MB of output can flood the model's context unless the caller sets `result_max_chars` (Q-4, EC-17).
- **A-7, that a non-zero exit counts as success.** This is the right default for test runs, but it is a semantic choice the user never discussed.
- **D-8, that `root_dir` is required.** It means a direct `CodingAgent.restore(state)` raises `TypeError`. A session cold resume is unaffected because it calls `BaseAgent.restore`.

## Self-check (Stage E)

- 18 `## §` sections, matching the template headings in order.
- Only the 9 rows in §12.3 start with `| <digit>`.
- Traceability:
  - Every FR maps to an INV or AC. FR-13 (docs) maps to §12.3 rows 8–9.
  - Every AC maps to a §12.3 row.
  - Every EC names a guard or states that it is an accepted limitation.
  - Every T names a control that is enforced in code.
- The contract names in §4, §8.5 and §12.3 are identical.
- The budget allows 3 new files, and §12.3 creates exactly 3.
- Every §12.3 row names its governing standard.
- Each weighted word maps to an INV, NFR or FR (NFR-1, NFR-7, INV-8, INV-9, FR-2).
- No test cases appear anywhere in the spec.
- Every command flag the spec names exists (`--rule`, `--stage source|package`, `--check`).
