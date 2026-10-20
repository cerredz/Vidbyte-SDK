# Code map: jev-cli-root-exports (PR R1)

Scouted on worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports`, branch `feat/jev-cli-root-exports`, HEAD `b7350ed6423642c9c178361eef87f3d9cda5589b` (= origin/main). Every path, line and symbol below was opened in this session unless it is marked "unverified". Line numbers refer to b7350ed6.

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### 1.1 AGENTS.md rules (quoted, with their headings)

- **Repository Map:** "Do not grep, glob, or read files under `docs/` as part of ordinary work ... treat the folder as opaque unless a human names a specific document." The only `docs/` file this run may read is `docs/spec/jev-cli-root-exports/request.md`.
- **Repository Map:** "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Repository Map:** "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder." `vidbyte/` (the root package folder) has no README. `contracts/README.md` exists (37 lines, read in full). `tests/` and `tests/features/` have no README. Each feature test pack has its own README.
- **Repository Map:** lint rule A009 keeps each folder README at or under 40,000 characters.
- **General Coding Style 3:** "Keep files well below 1,000 lines; when a file heads toward four digits, split it." `vidbyte/__init__.py` is already 1,467 lines (see §4).
- **General Coding Style 3:** "nothing in `vidbyte/lib/` may import from a layer above it." This does not bind the root `vidbyte/__init__.py`, which sits above every layer. Lint A006 skips it explicitly: `lint/rules/a006_directed_dependency_graph.py:67` excludes `vidbyte/__init__.py` and every `__init__.py`.
- **Placement Rules / Dataclasses:** "A feature package may re-export it from its own `__init__.py` as part of its public API ... but the definition stays in `vidbyte/lib/dataclasses/`." Re-exporting is allowed. The definitions must not move.
- **Placement Rules / Enums:** "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`." `TextModelMode` (line 347) and `JevDynamicComputeOption` (line 284) are already in that list.
- **Placement Rules / Existing code:** "Moving it to `vidbyte/lib/` is a change of its own and belongs in its own pull request." Some files in scope predate the rules: `PermissionDecision` is an enum defined in `vidbyte/lib/dataclasses/security.py:25`, and `ToolPermission` is an enum defined in `vidbyte/lib/dataclasses/tools.py:47`. They are not precedent, and this PR does not move them.
- AGENTS.md says nothing about commit or PR conventions. `CONTRIBUTING.md:38-45, 75-85` and `.github/pull_request_template.md` cover them (see 1.4).

### 1.2 Commands, exactly as the sources state them

| Purpose | Command | Source |
|---|---|---|
| Install (AGENTS.md states none) | `python -m pip install -e ".[dev]"` | `CONTRIBUTING.md:35`, `.github/workflows/ci.yml:36` |
| Full local gate | `python scripts/run_ci.py` | AGENTS.md "Repository Map"; `CONTRIBUTING.md:56` |
| One stage | `python scripts/run_ci.py --stage source` / `--stage package` | `CONTRIBUTING.md:62-63`; `scripts/run_ci.py:265-269` (choices `all`, `source`, `package`) |
| Lint, all rules | `python lint/run.py` (the last line must read `SDK-LINT: PASS`, `lint/core/report.py:58`) | `lint/README.md:32` |
| Lint, one rule | `python lint/run.py --rule C016` (also `--all`, `--format json`, `--update-baseline`) | `lint/README.md:33-57` |
| Contract freshness | `python scripts/generate-sdk-public-api.py --check` | `scripts/generate-sdk-public-api.py:15`, `contracts/README.md:27` |
| Contract regeneration | `python scripts/generate-sdk-public-api.py` (only after committing the `vidbyte/__init__.py` change) | `scripts/generate-sdk-public-api.py:14`, `contracts/README.md:28` |
| Import sort (S051/I001) over the whole tree | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | field guide `local-ci-verification.md` "Check S051 ..." |
| Static policy (semgrep) | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (version `semgrep==1.170.1`; `git add -A` first, because the scan reads only tracked files) | `.github/workflows/static-policy.yml:24-30`; field guide |
| Tests: one file / one pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>/<file>.py` / `... tests/features/<pack>` | the `TESTS:` header field of every feature-pack test file (for example `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py:11`) |
| Tests: all | `python -m pytest` (`testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`) | `scripts/run_ci.py:93`; `pyproject.toml:78-81` |

`scripts/run_ci.py --stage source` runs, in this order: the tracked-bytecode check, `lint/run.py` (this includes C016, so the contract is checked here), `compileall`, `check_context_write_paths.py`, `check_context_primitive_introductions.py`, `check_reasoning_trace_contracts.py`, and `pytest` (`scripts/run_ci.py:79-93`). `--stage package` builds the package, runs `twine check`, inspects the wheel, installs it into a clean venv with no `PYTHONPATH`, and runs the smoke test (`:95-239`).

### 1.3 Field-guide and workspace facts that bind this change

- **The interpreter and the install path:** on this machine, use `py -3.11`, not `python`. The editable install resolves `vidbyte` to the canonical checkout: run from a neutral directory, `import vidbyte` loads `C:\Users\422mi\vidbyte-repos\vidbyte-sdk\vidbyte\__init__.py` (verified). For that reason the source stage and the tests must run with `PYTHONPATH=$(pwd)`. The package stage must run without it. Never `export PYTHONPATH`. Use it inline for one command only. This comes from field guide `local-ci-verification.md` "Run the source stage with `PYTHONPATH=<worktree>` ...".
- **Field guide, "Two `harness_threads` surface tests fail locally on any branch that touches ... root exports":** `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` checks `report["all"] == literal_all(git show <merge-base>:vidbyte/__init__.py)` (`tests/features/harness_threads/test_harness_threads_surface.py:259-261`). It is red on this branch by design. CI skips it, because CI's shallow clone has no `origin/main`. The guide says to classify it as pre-existing, prove it with a control edit on main, and leave both the PR and the test unchanged. Its sibling, `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (`:227-235`), turns red only when a file under `vidbyte/tools/**` or `vidbyte/lib/configs/**` changes (see §4).
- **Field guide, "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself"** (`assert 167 == 120`, `:196`). It is inherited, so name it in the PR body.
- **Field guide, "Main can break a long-lived feature branch ... re-test after every merge":** run `scripts/generate-sdk-public-api.py --check` after each merge from main.
- **Field guide, "Dispatched checks never unblock the merge":** re-dispatch CI and Static policy on the exact head, then run `gh pr merge <n> --squash --admin --match-head-commit <sha>`.
- **Field guide, review-scope.md:** keep the PR to its minimal surface (settings, gate, runtime, tests, docs).

### 1.4 Commit and PR conventions (outside AGENTS.md)

- `CONTRIBUTING.md:40-45`: "Create a focused branch from the latest `main`. Keep public API changes explicit and document compatibility implications. Update nearby documentation when behavior, imports, package assets, or examples change."
- `.github/pull_request_template.md` has the sections Motivation, Changes, Compatibility, Verification (four checkboxes), and Follow-ups.
- The style of recent subject lines, from `git log`: `feat(<scope>): <sentence> (#NNNN)`. Examples are 64e2bd67 `feat(skills): ... (SDK 0.4.0) (#1099)` and 82b46c85 `feat(harnesses): export the native thread functions from vidbyte ... (#1179)`. The bodies end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **The contract needs two commits, enforced by its generator.** Commit A changes `vidbyte/__init__.py` (and any tests or docs). Then run `python scripts/generate-sdk-public-api.py`. Commit B adds the regenerated `contracts/sdk-public-api.json`. The generator refuses to write while any of its input files (`pyproject.toml` and `vidbyte/__init__.py`) differs from HEAD (`scripts/generate-sdk-public-api.py:69-72, 118-130`). It records HEAD as `source.commit`. Between commit A and commit B, C016 reports `exports-stale`, so lint is red, and so is any pytest that reads the contract JSON.

## 2. Files this change will touch

### 2.1 Edited

**`vidbyte/__init__.py`** (1,467 lines; it is the root public surface)
- **What it does today.** It imports 664 public names eagerly, plus 9 lazy native thread functions through `_LAZY_NATIVE_THREAD_EXPORTS` (`:1435-1445`) and a module `__getattr__`/`__dir__` hidden from type checkers (`:1449-1467`). `__all__` is one literal list (`:762-1427`) of 664 unique names, and it is not sorted. `__version__ = "0.4.0"` is at `:41`. The header is the old "Context Protocol Header" style (`:1-37`), which lacks most A001 fields, so the file is already in A001's baseline of 642.
- **What changes.** Bind `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption`, list each one exactly once in `__all__`, and probably update the header's Architecture bullets (precedent: 64e2bd67 added "plus the general ConfigurationError ..." to the Error exports bullet).
- **Patterns to follow, all at existing lines:**
  - `AgentLoopSettings`: the sibling `ToolSettings` comes into the root through `from vidbyte.agents import (... ToolSettings, ...)` (`:45-280`, `ToolSettings` at `:275`). `vidbyte/agents/__init__.py` already imports `AgentLoopSettings` (`:260`) and lists it in its `__all__` (`:323`). In ruff isort order, the new entry would sit between `AgentInput` (`:52`) and `AgentMessage` (`:53`).
  - `TextModelMode` and `JevDynamicComputeOption`: the existing block `from vidbyte.lib.enums import (BudgetPreset, GrokPermissionMode, GrokReasoningEffort, InfiniteMemoryPreset, MuseReasoningEffort, PermissionPreset, Prompt, StructuredOutputSupport, SystemPromptPreset,)` (`:481-491`). Both names are already in `vidbyte.lib.enums.__all__`.
  - `PermissionPolicy` has two precedents. (a) Import a lib dataclass directly, as in `from vidbyte.lib.dataclasses.skills import SkillResolution` (`:480`, added by 64e2bd67); the defining module is `vidbyte.lib.dataclasses.security`. (b) Import from a tools sub-package, as in `from vidbyte.tools.mcp import (...)` (`:663-667`) and `from vidbyte.tools.toolsets import ...` (`:668`); `vidbyte.tools.security` re-exports it, and that is the path `JevAgentSettings` uses (`vidbyte/agents/jev/settings.py:68`). The sibling enum `ToolPermission` comes in through `from vidbyte.tools import (... ToolPermission, ...)` (`:620`). `vidbyte.tools.__all__` (`vidbyte/tools/__init__.py:48-74`) does not include `PermissionPolicy`.
  - In `__all__`, precedent appends new names in a thematic cluster, not in alphabetical order. For example, 64e2bd67 put `"SkillLoader", "SkillResolution", "ConfigurationError"` at `:917-919`, after `"SkillUnavailableReason"`. Nearby clusters are `"ToolSettings"` (`:1054`), `"PermissionPreset"` (`:1257`), `"SystemPromptPreset"` (`:1271`), `"ToolPermission"` (`:1373`), and the Jev settings names (`:793-795`, `:824`).
  - The header lines that would carry the names are `:12` (Agent exports), `:14` (Tool exports, which already names `ToolPermission`), and `:18` (`- Preset exports: BudgetPreset, PermissionPreset, SystemPromptPreset.`). **`:25`, `- Error exports: ...`, must keep the word `ConfigurationError`.** `tests/features/public_skill_loader/test_public_skill_loader_docs.py:91` pins it, and that test's `part()` reads a bullet up to the next line that starts with `- `, `Word:`, or `#`.
- **Verified runtime facts.** All four defining modules are already in `sys.modules` after a plain `import vidbyte`, and `vidbyte.harnesses.native` is not. So eager root imports add no import-time work and do not affect INV-23. The objects are identical across their paths: `vidbyte.agents.AgentLoopSettings is vidbyte.agents.settings.loop.AgentLoopSettings`, `vidbyte.tools.security.PermissionPolicy is vidbyte.lib.dataclasses.security.PermissionPolicy is vidbyte.lib.dataclasses.PermissionPolicy`, `vidbyte.lib.enums.TextModelMode is vidbyte.lib.enums.text_model.TextModelMode is vidbyte.lib.config.TextModelMode`, and `vidbyte.lib.enums.JevDynamicComputeOption is vidbyte.lib.enums.jev.JevDynamicComputeOption` (all True). On b7350ed6, `hasattr(vidbyte, n)` is False for all four, and none is in `vidbyte.__all__`.

**`contracts/sdk-public-api.json`** (672 lines; GENERATED, never edited by hand)
- **What it is today.** The format is `schema_version 1`. `source.commit` is `ebd18517defa61dc3b80c1542080fc5177296325`. That is a `feat/public-skill-loader` branch commit, not an ancestor of main (verified with `git merge-base --is-ancestor`), and this is the normal result of squash merges. `version` is `"0.4.0"`, and `exports` lists the 664 names sorted with Python's `sorted()`, one per line. Today it equals `sorted(set(vidbyte.__all__))` (verified True).
- **What changes.** Running the generator rewrites it to 668 exports and a new `source.commit`. The four new lines sort as follows (computed): `"AgentLoopSettings"` between `"AgentInput"` (`:16`) and `"AgentMessage"` (`:17`); `"JevDynamicComputeOption"` between `"JevDoneResult"` (`:299`) and `"JevExerciseMode"` (`:300`); `"PermissionPolicy"` between `"ParentPolicy"` and `"PermissionPreset"` (`:462`); `"TextModelMode"` between `"TextContextItem"` (`:587`) and `"TokenRateLimitMiddleware"`. `version` stays `0.4.0`. `contracts/.gitattributes` pins `*.json text eol=lf`.
- **What writes it.** `scripts/generate-sdk-public-api.py` (152 lines, read in full) uses `lint/core/public_api_contract.py` (433 lines, read in full). That module reads `__all__` statically from the AST, never imports `vidbyte`, and fails closed on a conditional or computed `__all__`. The canonical render is LF-only with a trailing newline (`:101-112`).

### 2.2 Definition files: read, and not to be edited (no behavior change, request §C)

- **`vidbyte/agents/settings/loop.py`** (235 lines). `class AgentLoopSettings:` at `:46` is a plain class with a keyword-only `__init__` (`:49-67`): `max_iterations`, `max_tokens`, `max_tool_calls`, `max_queued_prompts=25`, `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`, `tool_error_policy`, `tool_settings`, `output_contracts=()`, and `max_contract_rejections=3`. It validates on construction and raises `ConfigurationError` (`:93-193`). Its header says "Exported from vidbyte.agents.settings" (`:14`).
- **`vidbyte/agents/settings/__init__.py`** (22 lines) exports `AgentFallbackSettings`, `AgentLoopSettings`, `ToolErrorPolicy`, `ToolSettings` and `UnrecoverableAction`. Its header says "Re-exported from vidbyte.agents.__init__".
- **`vidbyte/lib/dataclasses/security.py`** (61 lines). `@dataclass(frozen=True, slots=True)` is at `:32` and `class PermissionPolicy:` at `:33`, with `allowed: frozenset[ToolPermission] = frozenset({SAFE, READ})` (`:36-38`). `__post_init__` turns string values into `ToolPermission` and rejects a single string (`:40-46`). `check()` also honors `PermissionCeiling` (`:48-56`). `allow_all()` returns all four levels (`:58-61`). There is no `denied` field. The header says "Re-exported by vidbyte.tools.security.permissions" (`:12`).
- **`vidbyte/lib/enums/text_model.py`** (25 lines). `class TextModelMode(str, Enum)` at `:17` has `AUTO="auto"`, `VIDBYTE_MANAGED="vidbyte_managed"` and `DIRECT="direct"`. Its module `__all__` is `["TextModelMode"]`.
- **`vidbyte/lib/enums/jev.py`** (362 lines). `class JevDynamicComputeOption(str, Enum)` at `:278` has `FRESH_AGENT="fresh_agent"`, `FORK_AGENT="fork_agent"`, `SUBAGENT="subagent"`, `CLONE="clone"` and `SWARM="swarm"`, in tie-break order.

### 2.3 Neighbours read: the re-export paths and the consumer

- **`vidbyte/lib/enums/__init__.py`** (353 lines) already imports and lists `JevDynamicComputeOption` (`:122`, `:284`) and `TextModelMode` (`:204`, `:347`). No change is needed. Its header points to `tests/features/codex_host/test_codex_host_packaging.py`, which pins the `Codex*` order in this `__all__`.
- **`vidbyte/agents/__init__.py`** (574 lines) already re-exports `AgentLoopSettings` (`:258-264`, `:323`). No change is needed.
- **`vidbyte/agents/jev/__init__.py`** (281 lines) re-exports none of the four. It does list `JevUsageReport` (`:119`, `:280`), which `vidbyte.agents` and the root do not re-export (see §4).
- **`vidbyte/tools/security/__init__.py`** (29 lines) and **`vidbyte/tools/security/permissions.py`** (24 lines) re-export `PermissionPolicy`, `PermissionDecision` and `PermissionCeiling`, and the package also exports `ToolPermission`. **Do not edit either file** (see §3.3, `test_branch_leaves_the_tools...`).
- **`vidbyte/tools/__init__.py`** (82 lines) re-exports `ToolPermission` through `vidbyte.tools.types`. This is the sibling pattern.
- **`vidbyte/lib/dataclasses/__init__.py`** (`:201`, `:413`) and **`vidbyte/lib/config/__init__.py`** (`:16`, `:34`) are further existing export paths for `PermissionPolicy` and `TextModelMode`.
- **`vidbyte/agents/jev/settings.py`** (417 lines) is the consumer. `JevAgentSettings.permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)` (`:143`), `.loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)` (`:144`), and `.model_mode: TextModelMode = TextModelMode.AUTO` (`:150`). It rejects a model mode that is not an enum (`:169-170`), a policy that is not a `PermissionPolicy` (`:179-180`), and a loop that is not an `AgentLoopSettings` (`:181-182`). `JevComputeSettings.dynamic_compute: tuple[JevDynamicComputeOption | str, ...]` defaults to `(FRESH_AGENT, FORK_AGENT, SUBAGENT)` (`:352-356`) and accepts strings through `JevComputeRegistry.validate`. `JevRuntimeSettings.compute` defaults to `None` (`:378`).

### 2.4 Gate machinery that pins the public surface (read in full; not to be edited)

- **`lint/rules/c016_public_api_contract_current.py`** (216 lines). C016 is a blocking rule with baseline 0 (`lint/baseline.json:25`). Its finding kinds are `exports-stale`, `version-stale`, `not-canonical`, `contract-missing`, `contract-malformed`, `source-unresolvable` and `generator-missing`. It does not compare against git history. Verify with `python lint/run.py --rule C016 && python scripts/generate-sdk-public-api.py --check` (`:165`).
- **`lint/rules/s015_public_export_integrity.py`** (123 lines). S015 is blocking with baseline 13 (`lint/baseline.json:45`). For the root only, every public name it imports must appear in `__all__` (`:43-45`, "root public import is missing from __all__"). Every `__all__` entry must be bound, imported, or a key in a mapping whose name contains both "lazy" and "export" (`:41-42`, `:77-87`). Duplicates are findings (`:38-39`).
- **`lint/rules/a001_agent_readable_file_headers.py`** (81 lines). A001 is blocking with baseline 642. Every tracked `.py` file, tests included, needs non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:` (`:24-32`). A new test file without them regresses A001.
- **`lint/rules/s020_readme_file_index_parity.py`** (89 lines). S020 is blocking with baseline 1. A README with a `## File Index` must list every tracked direct child that has an indexed suffix (`.py`, `.md`, `.json`, and others), and `README.md` itself is excluded. This applies if a new `tests/features/<pack>/README.md` is added.
- **S051** (ruff I001 and UP rules) has baseline 259. On b7350ed6, `vidbyte/__init__.py` has no I001 finding (verified with the ruff command in §1.2), so any I001 finding on it after the edit is a regression. There is no file-length lint rule (searched `lint/rules`, `lint/core`).

### 2.5 The model for a new test pack (if the spec adds one)

- **`tests/features/root_native_thread_exports/`** (FEATURE.md 60 lines, README.md 15, test file 142, all read) is the 0.3.1 root-export pack. Its patterns: membership (`name in vidbyte.__all__`), identity (`getattr(vidbyte, n) is getattr(source, n)` and through `from vidbyte import ...`), a fresh-interpreter probe with `PYTHONPATH=REPO_ROOT` (`:50-54`), star import, misspelled-name errors, and a contract-JSON check plus `contract["version"] == pyproject == vidbyte.__version__` (`:133-142`). Its README has `## File Index` and `## Logs`.
- **`tests/features/public_skill_loader/`** (FEATURE.md 97 lines, read; `test_public_skill_loader_contract.py` 102, `_release.py` 115 and `_docs.py` 108, all read; conftest, acceptance, boundary, both_doors and security were not read because they concern SkillLoader behavior) is the 0.4.0 root-export pack from the same spec pipeline. Its patterns:
  - The `FEATURE_MISSING` try/except-ImportError guard, with an autouse fixture that re-raises it (`contract.py:23-52`), so tests written before the code still collect and fail at setup.
  - `root.__all__.count(name) == 1`, identity against the defining module (`:55-60`), and "exported nowhere else new" against `OTHER_EXPORTERS` (`:66-77`).
  - It deliberately does **not** read the contract JSON: "a pytest copy would be red by design between the source commit and the contract commit" (`FEATURE.md:95`).
  - The release test pins 8 version literals to `pyproject.toml`'s version (`_release.py:99-115`).
  - The docs test pins phrases in headers and READMEs (`_docs.py:85-91`).
- **Layout facts.** `tests/__init__.py` exists, but `tests/features/` and the packs have no `__init__.py`. Feature packs use `conftest.py` only where needed. There are no duplicate test basenames today (verified), and packs use `test_<pack>_<aspect>.py` names.

### 2.6 Version literals: recorded only so the spec can confirm that none changes

The version is `0.4.0` everywhere: `pyproject.toml:7`, `vidbyte/__init__.py:41`, `vidbyte/cli/__init__.py:58`, `vidbyte/mcp_server/server/core.py:79`, `vidbyte/tools/mcp/client.py:46`, `README.md:86`, `llms.txt:17`, `.github/ISSUE_TEMPLATE/bug_report.yml:19`, and the contract's `"version"` (`contracts/sdk-public-api.json:5`). `tests/features/public_skill_loader/test_public_skill_loader_release.py` pins the first eight to pyproject's version.

There is no CHANGELOG or release-notes file outside `docs/` (`git ls-files` search for changelog, release, history and news). `contracts/README.md:35-37` has a "Change Log" with one creation entry. A release note `docs/design/release-0-4-0.md` exists (it appears in `git show --stat 64e2bd67`, whose message says it "describes the release; do not tag it until #1184 ... is on main"). Its content is unverified, because `docs/` is opaque.

### 2.7 Docs that mention the four names but list no root exports (no mandated change)

- `README.md` shows submodule imports: `from vidbyte.lib.config import ... TextModelMode` (`:259`), `from vidbyte.tools.security import PermissionPolicy` (`:474`, `:1266`), and `from vidbyte.agents import AgentLoopSettings, ...` (`:1174`, `:1194`).
- `llms.txt` shows `from vidbyte.tools.security import PermissionPolicy` (`:577`) and `from vidbyte.agents import AgentLoopSettings` (`:676`, `:857`).
- `REPO_MAP.md` and `artifacts/file_index.md` do not list root exports. REPO_MAP has no `contracts/` or `lint/` entry.
- `skills/jev-agent/SKILL.md:118` imports JevAgent settings from `vidbyte`.
- No test or lint rule checks README, llms.txt, REPO_MAP or skills against `__all__`.

## 3. Tests that cover those files

### 3.1 Framework and commands

The framework is pytest 8.3.5 (installed), plus `unittest.TestCase` classes in older files, and it runs from `pyproject.toml [tool.pytest.ini_options]`. The fixtures in the packs above are module-level helpers, `importlib`, `subprocess` probes in a fresh interpreter, and `monkeypatch`. No network is used.

- One file: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q <path>`
- One area: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/<pack>`
- All tests: `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`, then `py -3.11 scripts/run_ci.py --stage package` with no PYTHONPATH, then `py -3.11 scripts/run_ci.py` (AGENTS.md's gate).

### 3.2 Tests that touch the root surface and still hold after adding four names (none pins an exact count or order of root `__all__`)

- `tests/features/public_skill_loader/test_public_skill_loader_contract.py`: the three 0.4.0 names stay listed once.
- `tests/features/public_skill_loader/test_public_skill_loader_docs.py:91`: the header's "- Error exports:" line holds `ConfigurationError`.
- `tests/features/public_skill_loader/test_public_skill_loader_release.py`: version literals.
- `tests/features/agent_output_connectors/test_output_connectors_contract.py:71-79`: 24 names are root, and `NOT_ROOT_NAMES` stay out (none of the four is in that list).
- `tests/features/agent_output_connectors/test_output_connectors_followup_contract.py:182-187`: the root docstring must not count "eleven connectors".
- `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:165-168`: subset of `__all__` and of the contract.
- `tests/features/jev_skills_preload/test_skill_sources_contract.py:52-67`: `SkillFetchStep` must not be root.
- `tests/features/coding_agent/test_coding_agent_contract.py:108`, `tests/features/system_prompt_presets/test_system_prompt_presets_units.py:56`.
- `tests/test_agent_modality_routing.py:196-198`: `TextModelRunner`, `ImageModelRunner` and `VideoModelRunner` stay out of the root.
- No test asserts that any of the four names is absent from the root (grep over `tests` and `scripts`).

### 3.3 Tests expected to be red locally on this branch, with the reason

1. **`tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py`: 3 tests fail on pristine b7350ed6. I ran the pack: `3 failed, 4 passed`.** The failing tests are `test_every_native_export_is_listed_in_the_root_all`, `test_each_root_name_is_the_native_object_itself` and `test_the_public_api_contract_lists_every_root_native_name_at_the_package_version`. The cause is that #1183 (b7350ed6) added 11 names to `vidbyte.harnesses.native.__all__` but not to the root: `BrowserThreadResult`, `BrowserToolCall`, and `{run,continue,fork}_{grok,opencode,muse}_with_browser`. This failure is not in the field guide or the workspace memory (see §4).
2. `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`) is inherited from main, per the field guide.
3. `...::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` is red on any branch that changes root `__all__`, because of its last clause (`:259-261`). CI skips it.
4. `...::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` turns red only if the PR changes any file under `vidbyte/tools/**`, including `vidbyte/tools/security/*.py` headers, or under `vidbyte/lib/configs/**` (`:227-235`).
5. `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is a CI-only flake on Python 3.11, per the field guide.
6. Between commit A and commit B (§1.4), C016 is red, and so is any new pytest that reads `contracts/sdk-public-api.json`.

### 3.4 Existing tests of the four classes' behavior (unchanged by this PR)

`tests/features/sdk_loop_settings/test_contract.py` (AgentLoopSettings), `tests/features/sdk_provider_keys/*` (TextModelMode modes), `tests/test_jev_compute_clone.py:70` and `tests/test_jev_compute_swarm.py:140` (JevDynamicComputeOption defaults), and `tests/features/coding_agent/test_coding_agent_environment.py:96` (`PermissionPolicy.allow_all()`). The existing tests import these names from these paths: `vidbyte.lib.config` (TextModelMode, 59+), `vidbyte.tools.security` (PermissionPolicy, 40+), `vidbyte.agents` and `vidbyte.agents.settings` (AgentLoopSettings), and `vidbyte.lib.enums` (JevDynamicComputeOption).

## 4. Notes for the spec author

- **Request assumes:** "satisfy every obligation the repo attaches to a new root export (whatever lint rule, contract test, README/llms listing, or REPO_MAP entry pins the public surface)". **Code shows:** the obligations are C016 (the regenerated contract), S015 (bound and listed once), S051 (sorted imports), the docs test on header `:25`, and A001/S020 for any new test files. No README, llms.txt, REPO_MAP or artifacts entry lists root exports (§2.7).
- **Request assumes main is green apart from the known failures. Code shows** `tests/features/root_native_thread_exports` is red on b7350ed6 (3 failures, verified). The cause is 11 native browser names (from #1183) missing from the root and the contract. This is out of scope: request §C allows "exactly these four names". The PR body must name the failure as inherited and show proof on pristine main. Whether a separate PR should root-export the browser surface (lazily, through `_LAZY_NATIVE_THREAD_EXPORTS`, per header `:22` and the test hint at `:47`) is a decision for the orchestrator.
- **Request assumes "do not change the version number". Prompt 3 Q2 says** "...auto merge that applies this change and updates the version". Decision D-P2 settles this as no version change, so cite D-P2. All 9 version places already read 0.4.0 (§2.6).
- **Request assumes** a changelog may list new exports. **Code shows** no such file outside `docs/`. `docs/design/release-0-4-0.md` exists, but its content is unverified (opaque). Updating it would need the orchestrator to name it for reading.
- **Request assumes** `PermissionPolicy` is at `security.py:33`. **Code shows** the class at `:33` and its decorator at `:32`. The other three line numbers match exactly.
- **AGENTS.md style 3 says** files stay "well below 1,000 lines". **Code shows** `vidbyte/__init__.py` at 1,467 lines today. Precedents #1179 and #1099 grew it without splitting, and no lint rule enforces the limit.
- **`PermissionPolicy` has two valid source paths** for the root import (§2.1), and both give the identical object. If the spec wants to note the root re-export in the `vidbyte/tools/security/` headers, that edit trips `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`. The headers that sit outside `vidbyte/tools` are `vidbyte/lib/dataclasses/security.py:12`, `vidbyte/agents/settings/loop.py:14` and `vidbyte/lib/enums/text_model.py`.
- **Contract test strategy has two conflicting precedents.** `infinite_memory_agent` and `root_native_thread_exports` read the contract JSON in pytest. `public_skill_loader` deliberately does not (`FEATURE.md:95`), because the JSON goes stale between the two required commits.
- **The larger outcome (the CLI builds every JevAgent setting from root names).** After R1, every type that `JevAgentSettings` and `JevRuntimeSettings` require is a root name or accepts a string. Root names: `JevAgentSettings`, `JevRuntimeSettings`, `JevContinualSettings`, `JevComputeSettings`, `JevRunBriefSettings`, `JevBulkSettings`, `JevAlignmentSettings`, `JevSpecialist` (it holds `agent: BaseAgent`, which is root), `JevPreflightPreset`, `JevDoneCheck`, `JevContinuationGate`, the skill entries, `ToolSettings`, `ToolPermission`, `CodingAgentTools`, `ParadigmMinimalToolset`, `SystemPromptPreset`, `ConfigurationError`, plus the four new names. String-accepting fields: `provider`, `api_keys`, `preflight`, `checks`, `gate` and `dynamic_compute`. These are still not root: `ModelProvider`, `ProviderKeys`, `ToolErrorPolicy`, `OutputContract`/`Min*` (AgentLoopSettings fields that the agreed flag map does not use), `DecisionModelConfig` (never exposed), and `JevUsageReport`. JevUsageReport matters only if CLI C4 needs it as a type (unverified).
- **Doc inaccuracy (unrelated, but the CLI author may copy it):** `skills/usage/create_agent_with_tools.md:164` shows `PermissionPolicy(allowed=..., denied=...)`, but `PermissionPolicy` has no `denied` field (`security.py:36`).
- Unverified: whether semgrep runs on this machine now (1.170.1 is installed; PR #1179 reported an mcp 2.x import break). Also unverified: the exact text of `docs/design/release-0-4-0.md`.
