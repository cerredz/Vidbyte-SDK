# Code map: native-thread-compose (S0 scout)

- Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`, branch `feat/native-thread-compose`, HEAD `5c08c35edcb1827e190ca4e2b2b1370808ef24be`. That is the same commit as `origin/feat/native-grok-opencode-meta-hosts` (the head of PR #1036). `origin/main` is `72a4ade1`.
- CLI port sources come from `C:/Users/422mi/vidbyte-repos/vidbyte-cli` at `abd31b4` (read-only).
- Every `path:line` below was opened in this session at that HEAD. `[NEW]` marks a file that does not exist yet. "unverified: …" marks a claim nobody checked.
- Paths are relative to the worktree root unless they are absolute.
- Short forms used below:

| Short form | Full path |
|---|---|
| `grok/…`, `opencode/…`, `muse/…`, `hostkit/…` | `vidbyte/harnesses/native/<same>` |
| `spec.md`, `test-plan.md`, "vendor-facts" | `docs/spec/harness-thread-functions/spec.md`, `…/test-plan.md`, `…/context/vendor-facts.md` |
| bare `test_harness_threads_*.py`, `conftest.py`, `fake_harness.py`, `FEATURE.md` | `tests/features/harness_threads/<same>` |
| bare lint rule files (`s0xx_…py`, `a0xx_…py`, `c0xx_…py`) | `lint/rules/<same>` |
| `comment-format.md`, `blocking-lint-invariants.md`, `local-ci-verification.md` | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/<same>` |
| `agent-stage-prompts.md`, `runtime-execution.md` | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-cli/<same>` |
| `stages.py`, `stage_failures.py` | `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/lib/runtime_primitives/<same>` |
| `…/services/ensemble/<file>`, `library.py`, the ten prompt `.md` names | `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/services/ensemble/` and its `prompts/` folder |
| `…/types/runtime.py`, `types/ensemble.py` | `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/types/<same>` |

## 1. Rules, commands and conventions that bind this change

### 1.1 AGENTS.md rules (quoted under their headings)

`AGENTS.md` is 81 lines long. The worktree's `CLAUDE.md` contains only `@AGENTS.md`.

- **Repository Map (lines 7–13)**
  - "Read it [`REPO_MAP.md`] before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs."
  - "it is expected to drift, so regenerate a wrong entry from the tree instead of patching around it."
  - "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there". No `README.md` touched by this change has that section; see §2.
  - "lint rule A009 keeps every folder README at or under 40,000 characters".
  - "**Do not grep, glob, or read files under `docs/` as part of ordinary work** … treat the folder as opaque unless a human names a specific document".
  - "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Line 15:** "The Placement Rules below … [are] binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code to the location it names."
- **General Coding Style Guidelines › 1. Keep Call Chains One Level Deep (21–23)**
  - "a function may call another of its own functions, but that second function should not call a third."
  - "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator." This bears on closure-based binding helpers.
- **› 2. Narrate Main Functions in Plain English (25–27):** "place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments."
- **› 3. Build in Layers of Small, Single-Purpose Classes (29–31)**
  - "nothing in `vidbyte/lib/` may import from a layer above it."
  - "Keep files well below 1,000 lines".
  - "If describing the job of a function or a class needs the word "and", it is probably two functions or two classes."
- **› 4. Use Validated Dataclasses for Core Inputs and Outputs (33–35)**
  - "Functions that carry core business logic take a dataclass as input and return a dataclass as output".
  - "Prefer `@dataclass(frozen=True, slots=True)`", and type any field that takes a closed set of values as an enum.
- **› 5. Write Shared Logic Once, as a Canonical Helper in `lib/` (37–41)**
  - "Before you write logic like this, look in `vidbyte/lib/` for a helper that already does it … If none exists, create the helper in `vidbyte/lib/` rather than inside the feature that first needs it".
  - "a canonical helper never imports from a layer above it".
  - "Logic that only one feature will ever need can stay with that feature".
- **Placement Rules › Dataclasses go in `vidbyte/lib/dataclasses/` (45–57)**
  - "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`** … whether it is public or underscore-prefixed."
  - "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules next to the code that uses the dataclass."
  - "Validation of the record itself (`__post_init__`, field checks) lives with the dataclass."
  - Exceptions: only agent `*Settings` and JEV preflight questions.
- **› Enums go in `vidbyte/lib/enums/` (59–63)**
  - "**Every new enum (any `Enum` subclass …) is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
  - "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- **› New JEV code (65–77):** "**A new Jev-facing prompt** is a new family under `vidbyte/prompts/prompts/`, with its key in `vidbyte/lib/enums/prompts.py`." Compose prompts are not Jev-facing, so this rule is a precedent here, not a mandate.
- **› Existing code (79–81):** "Many modules on `main` still define dataclasses or enums outside these two folders; they predate these rules. Do not copy them as precedent." One example is `vidbyte/paradigms/context_minimal_fanout/types.py`.

### 1.2 Conventions enforced by code in this area (not written in AGENTS.md)

- **INV-15 static scan (test-enforced).** `tests/features/harness_threads/test_harness_threads_static_policy.py:29` parses every `*.py` under `vidbyte/harnesses/native/` (`PACKAGE.rglob`), so it also covers any new subpackage.
  - **Rule 1 (`module_level_problem`, line 68).** Module level may hold only a docstring, imports, classes, a literal `__all__`, and in `__init__` modules `public_name = Class.attr`.
  - **Rule 2 (lines 92–104).** The only allowed str/bytes/int/float constants are docstrings, `__all__` strings, `""`, `0` and `1`. The literal parts of an f-string count as constants.
  - **Line 107:** no `vidbyte.tools` imports.
- **Native package style** (`vidbyte/harnesses/native/grok/threads.py`)
  - Public functions are `@staticmethod`s on a class. The subpackage `__init__` binds plain names to them (`grok/__init__.py`, 22 lines).
  - Every module has an A001 docstring header with PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO IN THIS FILE, KNOWN EDGE CASES, RELATED DOCS and TESTS.
  - Load-bearing logic carries a `# @intent <name>` block, as in `grok/threads.py:136`.
  - Every public operation has one guarded `try` (`grok/threads.py:69–86`). Its clauses run in this order:
    1. `except asyncio.CancelledError: raise`
    2. `except NativeThreadError: raise`
    3. `except ConfigurationError` → `errors.from_configuration_error`
    4. `except Exception` → `errors.from_unexpected`
- **Comment format** (field guide `comment-format.md:3–8`): a multi-line comment is a block of at most 72 columns, placed directly above the line it explains, with `# @intent <name>` on its own first line. This is not a lint rule.
- **Lint baselines that bite here** (`lint/baseline.json`)
  - Rules at baseline 0, where any new finding fails the gate: S006 (RUF006, task ownership), S012 (a method named `request`), S042, S052 and S055 (no shell subprocess).
  - Other baselines: A001 642, A002 703, A003 36, A005 33, A006 34, A007 255, A008 3, C002 9, C008 45, C015 3, S015 13, S019 5, S020 1, S024 25 (max nesting `MAX_NESTING_DEPTH = 3`, `s024_maximum_control_flow_nesting.py:22`), S045 2 (Ruff ASYNC109), S051 259, S061 6, S062 889, S063 4, S064 4.
  - **S063** (`s063_gather_exceptions_classified.py:3`): every `gather(..., return_exceptions=True)` result must be tested against `BaseException` in the same module.
  - **S064** (`s064_retry_overall_deadline.py:3–5`): a loop that names retry vocabulary and sleeps must compare against a clock-derived deadline or sit inside a timeout block.
  - **S061** (`s061_bounded_safe_path.py:56–73`): flags `open(x)`, `.write_text(x)`, `.read_text(x)`, `shutil.copy*`/`move` and `extractall` whenever the first positional argument is not a literal.
  - **C008** (`c008_shared_validator_owner.py:24`): validator helpers belong only in `vidbyte/lib/dataclasses/validation.py`.
  - **C015:** `pyproject.toml` package-data must cover every tracked non-`.py` file under `vidbyte/`.
  - **S020:** a README that opts in with `## File Index` must list exactly the tracked direct children with suffixes `.json .md .py .toml .txt .yaml .yml`.
  - **A009:** `MAXIMUM_CHARACTERS = 40_000` (`a009_readme_size_limit.py:20`).
- **Out of scope for harness modules.** S016 and S017 do not scope `vidbyte/harnesses/`. S016 prefixes are at `s016_typed_boundary_errors.py:22`, S017 prefixes at `s017_no_raw_exception_disclosure.py:22`.
- **A006 layering.** `vidbyte.prompts` appears in no A006 prefix list. `vidbyte/lib/registries/prompts.py:3` already imports `vidbyte.prompts.catalog` from lib.

### 1.3 Commands (exact)

| Purpose | Command | Source |
|---|---|---|
| Install | `python -m pip install -e ".[dev]"` | `CONTRIBUTING.md:35`; `.github/workflows/ci.yml:36` |
| Lint, all rules | `python lint/run.py` | `lint/README.md:31–35` |
| Lint, one rule | `python lint/run.py --rule <ID>` (all findings: `--rule <ID> --all`; JSON: `--format json`) | `lint/README.md:31–35` |
| S051 over the whole tree | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | field guide `local-ci-verification.md:38–43` |
| Lint final line | `SDK-LINT: PASS` or `SDK-LINT: FAIL` | `lint/core/report.py:58` |
| Test, one file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>/<file>.py` | base `spec.md:630` |
| Test, area (new pack) | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>` | base `spec.md:630` |
| Test, area (base pack, must stay green) | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | `tests/features/harness_threads/FEATURE.md` |
| Test, prompt catalog (only if the catalog route is chosen) | `PYTHONPATH=$(pwd) python -m pytest -q tests/test_prompts_interface.py` | file exists, 70 lines |
| Test, all | `PYTHONPATH=$(pwd) python -m pytest -q` | base `spec.md:631` |
| Full gate (AGENTS.md wording) | `python scripts/run_ci.py` | `AGENTS.md:13` |
| Full gate (in this worktree) | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH` | `local-ci-verification.md:3–8`; `lint/README.md:38–44` |
| Check which `vidbyte` is imported | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | `local-ci-verification.md:7` |
| Semgrep (remote-only) | `python -m pip install semgrep==1.170.1`, then `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | `.github/workflows/static-policy.yml:24–30` |
| CI (dispatch-only) | `gh workflow run ci.yml --ref <branch>` | `.github/workflows/ci.yml:8–9` |

- **The source stage** (`scripts/run_ci.py:79–93`) runs, in order: tracked-bytecode check, `lint/run.py`, `compileall`, three check scripts, then `python -m pytest`, which is the whole suite (`testpaths=["tests"]`). It does not run semgrep.
- **The package stage** builds the wheel, checks `REQUIRED_PROMPT_ASSET = "vidbyte/prompts/prompts/error_correction_auditor.md"` (line 50), and runs a clean-venv smoke test.
- **CI** (`.github/workflows/ci.yml`) runs a source job on `ubuntu-latest` with Python 3.11 and 3.12 (lines 17, 20–23), plus a package job on 3.11 with `--dist-dir dist` (line 60).
- **Lint and semgrep read only tracked files** (`local-ci-verification.md:10–15, 31–36`). New files must be `git add`-ed before a clean result means anything.
- **Unverified:** whether running `pip install -e` from this worktree repoints the editable install that the main checkout and other worktrees share. The field guide says the editable install resolves to the canonical checkout (`local-ci-verification.md:6`).

### 1.4 PR and commit conventions

- AGENTS.md has no commit or PR convention.
- **PR template** (`.github/pull_request_template.md`):
  - Sections: Motivation, Changes, Compatibility (write "None" when nothing changes), Verification ("List the exact commands run"), Follow-ups.
  - Four checkboxes: repository checks pass; new or changed package assets are in the built wheel; docs and examples are updated; no credentials, bytecode or unrelated changes.
- **`CONTRIBUTING.md` › Making a Change (38–49)**
  - "Create a focused branch from the latest `main`."
  - "When adding non-Python runtime assets, confirm that the built wheel contains them and that the installed package can load them outside the source checkout."
- **› Verification (51–73):** "A change is not ready for review while any local gate or pull-request check is red. Do not skip, delete, or weaken checks to make a change pass."
- **› Pull Requests (75–85):** state the problem and intended outcome, compatibility implications, commands run with their output, documentation changes, and follow-ups that are out of scope.
- **This PR is stacked.** It targets `feat/native-grok-opencode-meta-hosts`, not `main` (request line 5), which conflicts with CONTRIBUTING's "from the latest `main`" (§4 C-15).

## 2. Files this change will touch

The entries come from the request's ledger items 1–13 and the code. "Touched when …" names the decision that pulls a file in; the decision itself belongs to the spec.

### 2.1 Existing files to modify

**F-1 `vidbyte/harnesses/native/__init__.py` (62 lines)**
- **Today:** re-exports the nine functions, `NativeThreadResult`, the three configs, `NativeThreadError`, `GrokPermissionMode`, `GrokReasoningEffort` and `MuseReasoningEffort` in a literal 17-name `__all__`. Its WHAT NOT TO DO says "Do not export the flow classes, codecs, launchers or hostkit helpers".
- **Touched when:** composites are exported from `vidbyte.harnesses.native`, which ledger 9 allows as an option.
- **Pattern:** `from vidbyte.harnesses.native.grok import (continue_grok_thread, fork_grok_thread, run_grok_thread,)` plus a literal `__all__`.
- **Constraint:** exports are pinned exactly (§4 C-2).

**F-2 `vidbyte/lib/enums/__init__.py` (289 lines)**
- **Today:** imports and exports every native enum. The import block is at line 111; `__all__` entries such as `"GrokPermissionMode"` are at line 210.
- **Change:** add every new public enum. AGENTS.md says "There are no exceptions."
- **Pattern:** an alphabetical `from vidbyte.lib.enums.<domain> import (...)` block plus `__all__` strings.

**F-3 `vidbyte/lib/enums/native_threads.py` (199 lines) or `[NEW] vidbyte/lib/enums/<domain>.py`**
- **Today:** holds every `StrEnum` of the base PR: `NativeHarness`, `NativeThreadVerb`, `NativeThreadOperation` (9 members), `NativeThreadProblem` (10), `GrokPermissionMode`, `GrokReasoningEffort`, `MuseReasoningEffort`, the flag enums, `NativeEnvironmentVariable`, `MuseMethod` and `OpencodeEventType`.
- **Change:** new closed vocabularies, such as a stage decision or a verdict, as new enum classes.
- **Constraint:** the 14 enums pinned in `EXPECTED_ENUMS` take no new members (§4 C-4). `ShellFlag` (line 144) is the only class in this module that is not pinned.
- **Pattern:** `class GrokPermissionMode(StrEnum)` with a docstring. The surface test requires `StrEnum` (`test_harness_threads_surface.py:166`).

**F-4 `vidbyte/lib/dataclasses/native_threads.py` (228 lines) or `[NEW] vidbyte/lib/dataclasses/<domain>.py`**
- **Today:** `NativeThreadRequest` (with `api_key` as `field(repr=False)`), the three configs, and `NativeThreadResult(harness, thread_id, text, text_truncated)` at lines 212–225. Validation goes through `RecordFieldValidator` and `RecordFieldConverter`.
- **Change:** new records, such as the stage spec, roster, verdict and per-composite results.
- **Pattern:** `@dataclass(frozen=True, slots=True)`, and in `__post_init__` the form `object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))` (line 86), with every bound taken from constants. Base NFR-2 caps files at 500 lines.
- **Precedent:** `vidbyte/lib/dataclasses/__init__.py` (497 lines) does not export native records, so new records need no export there.

**F-5 `vidbyte/lib/constants/native_threads.py` (452 lines) or `[NEW] vidbyte/lib/constants/<domain>.py`**
- **Today:** holds every literal the harness modules use: times (22–25), caps (27–40), patterns (53–63), Grok home parts (113–115), `NATIVE_THREAD_FAILURE_CODES` (349), likely causes (`NATIVE_THREAD_LIKELY_CAUSES`, 383) and next steps (for example 425, 429).
- **Change:** must hold every literal a compose module needs, because INV-15 allows none in native modules. That covers JSON member names, git argv words, caps, repair counts, prompt file names and format templates.
- **Constraints:**
  - `CONTRACT_CONSTANTS` values are pinned (`test_harness_threads_surface.py:53–60`).
  - Base NFR-2 says a constants module stays under 1,000 lines.
  - The constants package `__init__` does not re-export this module.

**F-6 `vidbyte/lib/enums/prompts.py`** (touched only when prompts go into the SDK catalog)
- **Today:** the `Prompt(str, Enum)` keys. The header reads "all 98 static prompt assets across 33 JSON/Markdown-backed families" and "additions must update them atomically" (descriptor, enum member, README entry, direct import, installed resource).
- **Change:** one member per new leaf, `family.leaf`, plus the header counts.

**F-7 `vidbyte/prompts/README.md`** (27,163 characters; catalog route only)
- **Today:** the "Available Prompts" section with a Quick reference table (line 52) and Descriptions (line 87). It has no Notes for agents and no File Index.
- **Change:** one row and one description per new family. A009 caps the file at 40,000 characters.

**F-8 `pyproject.toml`** (touched only when `.md` assets live outside `vidbyte/prompts/prompts/`)
- **Today:** line 69 `"vidbyte.prompts.prompts" = ["*.json", "*.md", "*/*.json", "*/*.md"]`, which covers one family folder deep. Lines 70–76 hold `"vidbyte.paradigms.context_minimal_fanout"`, the precedent for a feature-local `prompts/*.md`.
- **Change:** add a package-data entry for a local prompt folder (C015). Version is `0.3.0` (line 7). No new dependency is allowed (ledger 9, NG-10).

**F-9 `vidbyte/harnesses/README.md`** (10,771 characters)
- **Today:** line 178 is the `native/` bullet that the base PR added. It names the nine functions and EC-27, EC-39, EC-43, EC-44 and T-6. The file has no Notes for agents and no File Index.
- **Change:** describe the composites and their caveats there.

**F-10 `REPO_MAP.md`**
- **Today:** lines 159–161 are the `vidbyte/harnesses/native/` entry, which says "There are no host objects, model-facing tools or servers here". Line 215 is the `vidbyte/lib/process/` entry. Both came from the base PR (`git diff origin/main...HEAD -- REPO_MAP.md`).
- **Change:** mention the composite subpackage, and any new lib helper folder.

**F-11 `vidbyte/lib/README.md`** (2,884 characters; touched when a helper lands in `vidbyte/lib/`)
- **Today:** line 43 is the base PR's `process/` bullet.

**F-12 `tests/features/harness_threads/fake_harness.py`** (683 lines; touched when the fake gains modes)
- **Today:** a stdlib-only stand-in for grok, opencode, muse exec, muse serve and wsl, driven by one scenario JSON per command. It never imports vidbyte and never uses `shell=True`. Modes and gaps are listed in §3.2.
- **Change:** ledger 13 says "extended if needed". The acceptance tests need a mode that writes into the workspace, plus a launch counter for fail-then-succeed.
- **Pattern:** header line 7, "Add a scenario field, read it here with .get and a default".

**F-13 `tests/features/harness_threads/README.md`** (2,799 characters) **and `FEATURE.md`** (touched when files are added to this pack or its contract changes)
- **Today:** the README has `## File Index` (line 7), so S020 applies to it.

**F-14 `tests/features/harness_threads/test_harness_threads_surface.py`** (touched only when a pinned surface changes)
- **Today:** header line 7 says "A new public name is a spec change first (§8.5), then one entry in EXPECTED_EXPORTS."
- **Change:** needed if F-1, a pinned enum, or `vidbyte.lib.process.__all__` changes (§4 C-2, C-4).

**F-15 `vidbyte/lib/process/__init__.py`** (19 lines) and the `vidbyte/lib/process/` modules (touched only when diff capture becomes a canonical lib helper)
- **Today:** `__all__ = ["CliArgv", "CliRunner", "ProcessStopper"]`. That exact list is pinned (`test_harness_threads_surface.py:212`).

### 2.2 New files `[NEW]`

- **`[NEW] vidbyte/harnesses/native/compose/__init__.py`.** Ledger 9 says "`compose/` or the name the repo's conventions suggest".
  - Pattern: the harness `__init__` style. INV-15 rule 1 allows only imports, a literal `__all__` and `name = Class.method` bindings.
- **`[NEW] vidbyte/harnesses/native/compose/*.py`.** Static-method classes with an A001 header, under 500 lines each (base NFR-2).
  - The INV-15 scan covers them automatically through `rglob`.
  - A compose module that imports `vidbyte.harnesses.native.hostkit` goes against hostkit's documented boundary (`hostkit/__init__.py:4`, "Imported by vidbyte.harnesses.native.grok, .opencode and .muse only").
- **Prompt assets `[NEW]`.** Two routes, chosen by the spec. Request line 124 leaves the choice open.
  - **Catalog route:** `[NEW] vidbyte/prompts/prompts/<family>/<family>.json` plus `<leaf>.md`. Each leaf in the JSON needs `"path"` and `"source_url"` (`vidbyte/prompts/catalog.py:172–178`), and `Prompt(f"{family_key}.{prompt_name}")` must exist (106–110). The existing `vidbyte/prompts/prompts/handoff/handoff.md` is an 18-line "run digest → JSON `sections`" system prompt. It is not a thread-summary prompt.
  - **Local route:** `[NEW] vidbyte/harnesses/native/compose/prompts/*.md`, plus F-8. The precedent is `vidbyte/paradigms/context_minimal_fanout/prompts/__init__.py:20–55` (`_ROLE_ASSETS` holds literal file names and reads `resources.files(__package__)`). Those literals would break INV-15 inside `native/` (§4 C-3).
- **`[NEW] vidbyte/lib/{dataclasses,enums,constants}/<domain>.py`** (optional; see F-3 to F-5). Names to avoid: the surface test's `DELETED_FILES` (`test_harness_threads_surface.py:73–83`) must stay absent.
  - `vidbyte/lib/dataclasses/{grok,opencode,muse,native_hosts,harness_backends}.py`
  - `vidbyte/lib/enums/{native_hosts,harness_backends}.py`
  - `vidbyte/lib/constants/native_hosts.py`
  - `vidbyte/harnesses/native/hostkit/{peers,turns}.py`
  - the package `vidbyte/harnesses/native/backends/` (line 84)
- **`[NEW] tests/features/<pack>/`.** `FEATURE.md`, `README.md`, `conftest.py` and `test_<pack>_<topic>.py` files (ledger 13; base `spec.md` §13). Test basenames must be unique across the tree (§3.1).

### 2.3 Existing files the composites call or copy (read, not modified)

- **The nine functions.** Each takes `(prompt | thread_id, prompt, *, api_key, workspace, model, skills=(), config=None) -> NativeThreadResult`.
  - Grok (`grok/threads.py:54–66`) and Muse (`muse/threads.py:51–63`) take `model: str | None = None`.
  - **opencode requires `model: str`** (`opencode/threads.py:46–58`).
  - Continue and fork take `thread_id` positionally, first.
- **The process inside each function.**
  - **Grok:** `cwd=Path(request.workspace)` (line 112). Timeout is `config.timeout_seconds` (110). The home key is `sha256(os.path.normcase(str(workspace)))[:16]` (141). The home is `Path.home()/.vidbyte/grok-homes/<key>` (143, via `GROK_PRIVATE_HOMES_PARTS`). Skills go through `NativeSkillFolders.replace` (148).
  - **opencode:** the prompt goes on stdin (105).
  - **Muse:** the serve pre-check is bounded by `NATIVE_CONTROL_TIMEOUT_SECONDS` (`muse/threads.py:200`), and exec by `config.timeout_seconds` (223).
- **`vidbyte/harnesses/native/hostkit/errors.py`**
  - `NativeErrorFactory(harness, operation)` (line 36).
  - `failure()` looks up `NATIVE_THREAD_FAILURE_CODES[(harness, problem)]` (100).
  - `from_configuration_error` → `FailureCode.CONFIGURATION_INVALID_ARGUMENT` (142).
  - `from_unexpected` → `FailureCode.RUNTIME_ERROR` (159).
- **`vidbyte/harnesses/native/hostkit/skills.py:27–43`.** "a destination that already holds identical copies is left untouched" (34–35). Otherwise the folder is removed, recreated, and the skills are copied in.
- **`vidbyte/lib/errors/base.py`**
  - `NativeThreadError(AgentExecutionError)` (558).
  - `OutputSchemaViolationError(message, *, raw_output, validation_error=None, stop_reason=None)` (176–184) is an existing type for "answer did not validate". REPO_MAP line 197 says "A new failure mode should usually reuse an existing error type with a clear message rather than growing the hierarchy."
  - A new class in this file needs the A003 `DIAGNOSTIC_FIELDS` packet (field guide `blocking-lint-invariants.md:10–15`).
- **`vidbyte/lib/enums/failure.py`.** `FailureCode(str, Enum)` (22). `CONFIGURATION_INVALID_ARGUMENT = "configuration.invalid_argument"` (34). `RUNTIME_ERROR = "runtime.error"` (106). `RULE_EVALUATION_FAILED` (144) is followed by the 28 harness codes (lines 145 onward, starting `GROK_NOT_INSTALLED`).
- **`vidbyte/lib/process/`**
  - `CliRunner.run(invocation) -> CliOutcome` (`runner.py:186`); `find_program` (241); `json_objects` (306).
  - `CliArgv.build(launcher, *, command=(), options=(), style, operands=())` (`vidbyte/lib/process/argv.py:26`). A separate-style value starting with `-` is refused (50–51).
  - The records live in `vidbyte/lib/dataclasses/process.py`, not in `vidbyte/lib/process/` as request hint line 120 lists them: `CliOption` (36), `CliInvocation` (51), `CliOutcome` (73).
  - `CliInvocation` (`vidbyte/lib/dataclasses/process.py:51–60`): `argv`, `env_overlay` (repr=False), `timeout_seconds`, `max_output_bytes`, `cwd=None`, `stdin_text=None` (repr=False; `None` means DEVNULL), `env_remove=()`.
  - No git helper exists anywhere in `vidbyte/`. `git grep -n '"git"' -- vidbyte` finds only `vidbyte/lib/config/mcp_presets.py:1604` (an MCP preset name) and `vidbyte/tools/builtins/bash.py:67` (`shutil.which("git")`).
- **`vidbyte/lib/dataclasses/validation.py`** (C008's canonical module). `RecordFieldValidator.require_text(value, field_name, *, max_chars, pattern=None, allow_blank=False)` (41) and `accepts_text` (50), plus the other `require_*` helpers.
- **JSON-from-model-text parsing has no lib helper.** It is reimplemented inline at seven sites:
  - `vidbyte/agents/handoff.py:175`
  - `vidbyte/context/algorithms/error_correction.py:241`
  - `vidbyte/context/algorithms/problem_space_search.py:199`
  - `vidbyte/context/algorithms/trajectory_checkpoints.py:197`
  - `vidbyte/context/algorithms/independent_critic.py:264` (strips one code fence)
  - `vidbyte/evals/graders/llm_judge.py:122` and `vidbyte/evals/graders/rubric.py:132` (`json.JSONDecoder().raw_decode`)
  - `vidbyte/providers/output_schema.py:30,107–111` (`_FENCED_JSON`, `_unfenced`)
- **Worktree precedents.**
  - `vidbyte/agents/coding_context/environment.py:136–163` reads a worktree's `.git` file (`gitdir:`) without running git.
  - `vidbyte/agents/codex/README.md:753` says "Give each fork its own worktree … with a different `cwd`".
- **No `asyncio.TaskGroup` anywhere in `vidbyte/`.** Every fan-out uses `asyncio.gather`. Examples: `vidbyte/agents/aggregation.py:89` (`return_exceptions=True`) and `vidbyte/agents/jev/compute/clone.py:51`.

### 2.4 CLI port sources (read-only; never imported)

All paths are under `C:/Users/422mi/vidbyte-repos/vidbyte-cli/`.

**`src/vidbyte_cli/lib/runtime_primitives/stages.py` (367 lines), `StagesCodexSession`**
- **Sequential** (91–120): `prompt = spec.prompt.replace("{{previous}}", previous)`. `stop_on_error` keeps the completed prefix. A failed stage leaves the text `Stage {n} failed ({reason}).`
- **Parallel** (122–149): one `asyncio.gather` with no `return_exceptions`.
- **One stage** (151–191):
  - `for attempt in range(settings.max_retries_per_stage + 1)` builds a fresh agent per attempt.
  - Backoff is `2.0 * (4.0**retry_index) + random.uniform(0.0, 1.0)` (193–196).
  - `CancelledError`/`KeyboardInterrupt` are re-raised (177–179). Settings errors and `ValueError` fail fast (180–182).
  - Retry happens only when `failure.retryable` (183–189).
- **Per-turn timeout:** `asyncio.timeout(StagesLimit.TURN_TIMEOUT_SECONDS)` (223).
- **No effort ladder.** Effort is a fixed per-stage `StageEffort` (`_to_settings`, 303–367).

**`stage_failures.py` (103 lines)**
- `StageAttemptFailure(reason, retryable)` and `StageExhausted(reason, attempts, duration_ms)`.
- `_FINAL_REASONS` (27–36) holds provider codes that never retry.
- `classify` puts the provider's `codex_error_info` first (71–77). Otherwise it maps `TimeoutError`, `ConnectionError`, or a dotted `failure_code` with dots turned into underscores (97–99).

**`src/vidbyte_cli/types/runtime.py`**
- `StageSpec` (820–1024): name, prompt (≤20,000), system_prompt (≤20,000), model, effort, summary, sandbox, approval, personality, additional_context, image, skill, mention, output_schema.
- `StagesSettings` (1027–1080): stages, at most 25 per its description; parallel; `stop_on_error=True`; `max_retries_per_stage` 0..3, default 1.
- `StageStepResult` (1083–1095): index, name, status, thread_id, attempts, duration_ms, `reason` matching `^[a-z][a-z0-9_]{0,63}$`.
- `StagesResult` (1098–1107).

**`src/vidbyte_cli/services/ensemble/service.py` (263 lines)**
- `_orchestrate` (61–90) runs four steps:
  1. Plan on the root thread.
  2. `asyncio.gather(*proposals, return_exceptions=True)`, each proposal a fork of the root.
  3. Select on one selector thread forked from the root, over several rounds.
  4. Implement in a fork of the root.
- Only an empty slate aborts (71–72).
- **Each role is bounded by `asyncio.timeout(stages.inputs.role_timeout_seconds)`** (126), default 300 s (`types/ensemble.py:64`).
- Narrowing target is `max(ceil(alive / 5), 1)` (201–203). Candidate ids `f"{role_index}.{approach_index}"` are assigned by code (205–217) and checked on the way back (193–199).
- `_reason` re-raises `CancelledError` (255–258).

**`settings.py`, `sdk.py`, `types/ensemble.py`**
- **One writer by sandbox.** Only `implementer()` gets `write=True`. `_sandbox` names `READ_ONLY` or `WORKSPACE_WRITE` explicitly (`sdk.py:132–135`).
- **Structured output is enforced by the host.** `output_schema=CodexOutputSchema.strict_model(schema)` (`sdk.py:89–107`). Schema violations are a separate error (84–87).
- Bounds: `APPROACHES_PER_ROLE_MIN = 5`, `MAX = 10` (22–23); `ROLES_MIN = 3`, `MAX = 100` (26–27).

**`services/ensemble/prompts/`: ten `.md` files plus `library.py`**
- `library.py` `_render` uses `rendered.replace("{{" + key + "}}", value)`. `_render_role_context` and `_render_candidate` build `<role-context …>` and `<candidate …>` text in Python f-strings.
- Sizes are characters read by `Path.read_text` (newlines normalized):

| File | Characters | Placeholders |
|---|---|---|
| fork_turn | 720 | instructions, turn |
| implementer_system | **35,852** | none |
| implementer_turn | 847 | 19 |
| planner_system | **58,578** | roles |
| planner_turn | 166 | roles, task |
| role_system | 5,704 | 9 unique, 15 uses |
| role_turn | 558 | 6 |
| selector_final_turn | 726 | 5 |
| selector_round_turn | 606 | 9 |
| selector_system | 6,534 | none |

- No file contains a `{` or `}` outside a `{{name}}` placeholder (checked by script).
- **Harness-specific wording:**
  - `role_system.md:37`: "You are running in a read-only sandbox."
  - `implementer_system.md:58`: "You are running with workspace-write access".
  - `fork_turn.md:7`: "the workspace, the sandbox, and tool use still apply".
- `selector_system.md:60–68`: "Return one JSON object and nothing else … Missing keys, extra keys, prose, or code fences fail the run."

**`skills/harnesses/runtime-primitives/SKILL.md` (84 lines)**
- Seven parts (33–53).
- "**Exactly one agent may write.** … Enforce it with sandbox settings, not with prompt instructions — a prompt is a request, a sandbox is a guarantee." (62–64)
- "**Partial success is reported, not discarded.** … Only an empty result set should abort." (65–66)

**CLI field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-cli/`)
- `agent-stage-prompts.md:35–48`: structured output is enforced in three layers, schema plus revalidation plus a code check, and "the schema is the weakest one".
- `:117–128`: one schema and one thread per multi-turn stage.
- `:144–152`: non-Python assets must be package data, and "the gate will not catch it".
- `runtime-execution.md:36–41`: per-step retry, `2*4^n + up-to-1s` jitter, step records, and `stop_on_error`.

## 3. Tests that cover those files

### 3.1 Framework and configuration

- **Versions:** pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48–49`). Python `>=3.11` (line 10). The local interpreter is 3.11.0.
- **`[tool.pytest.ini_options]` (78–81):** `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`, `asyncio_default_fixture_loop_scope = "function"`.
  - There is no `asyncio_mode`, so pytest-asyncio runs in strict mode and every async test needs an explicit `@pytest.mark.asyncio` (pack style: `test_harness_threads_threads.py:121`).
  - There is no `markers` list, so under `--strict-markers` any custom marker fails.
- **Imports:** the default prepend import mode applies.
  - `tests/__init__.py` exists. No pack under `tests/features/` has an `__init__.py`, so test basenames must be unique.
  - Four packs already ship their own `conftest.py`: agent_output_connectors, coding_agent, harness_threads and jev_skills_preload. A new pack with its own `conftest.py` follows working precedent.
- **Pack layout** (base `spec.md` §13; `tests/features/harness_threads/`): `FEATURE.md` (sections at lines 3–66, including "Test Suite Map" and "Omitted Testing Strategies"), `README.md` with `## File Index`, `conftest.py`, a stdlib-only fake, and `test_<pack>_<topic>.py` files.

### 3.2 Fixtures and the fake harness

**`tests/features/harness_threads/conftest.py` (414 lines; pack-local)**
- Its `pack` fixture comment says test modules "cannot import conftest by name".
- **Constants (33–51):** `PACK = Path(__file__).resolve().parent`, `FAKE = PACK / "fake_harness.py"`, `API_KEY = "vbk-test-0123456789abcdef0123456789abcdef"`, `PROMPT`, `OPENCODE_MODEL = "deepseek/deepseek-v4-pro"`, `CALL_TIMEOUT_SECONDS = 60.0`, `FAST_KILL_WAIT_SECONDS = 0.5`, `SLACK_SECONDS = 5.0`.
- **`Sandbox` (91–204):** home, workspace, skill source, bin, tmp, and the fake's log/state/release flag.
  - `scenario()` writes one scenario JSON.
  - `command()` returns `(sys.executable, "-u", FAKE, scenario)` (117).
  - Also `stand_in`, `make_skill`, `release()`, `records()`, `starts()`, `answers()`.
- **The `sandbox` fixture (250–259) sets the environment:**
  - **`USERPROFILE` and `HOME` point at the sandbox home (255–256).**
  - **`PATH` holds only the sandbox `bin` (257).**
  - `tempfile.tempdir` is redirected (258).
  - So git is not on PATH inside the sandbox (§4 G-6).
- **Helpers:** `call` (262–279) passes `{<harness>_command, timeout_seconds=60, **config}`. Also `check_error` (295–328, the INV-5 check), `fast_stop` (331–336), `wait_until` (339–351), `alive` and `wsl_ready`.

**`fake_harness.py` (683 lines)**
- `HOLD_LIMIT_SECONDS = 30`; `DEFAULT_FAIL_EXIT = 93`. Each process writes one JSONL log.
- **Grok modes:** ok, hold, key_rejected, flood, garbage, fail, stderr_exit, echo_secrets, continue_other_id, continue_upper_id, fork_returns_source, long_text, missing_session.
  - Sessions live under `GROK_HOME/sessions/<sha256(normcase(abspath(--cwd)))[:16]>` (306).
  - An unknown `--resume` gives "Session {id} does not exist" (310).
- **opencode modes:** ok, session_then_hold, session_then_flood, hold, flood, garbage, echo_secrets, key_rejected, key_rejected_status, fail, stderr_exit, long_text, continue_other_id, fork_returns_source.
  - Sessions are global under the state folder, regardless of `--dir`.
- **Muse exec modes:** ok, hold, session_then_hold, key_rejected, flood, garbage, fail, echo_secrets, no_session, no_terminal, terminal_failed, long_text, continue_other_id.
- **Muse serve modes:** ok, other_error, fork_returns_source, hold, no_answer.
- **Default answers:** `"{harness} answer to: {prompt}"`.
- **Gaps for this feature:**
  1. No mode writes into the workspace.
  2. There is no per-launch counter: every launch of one command reads the same scenario, so fail-then-succeed cannot be scripted today.
  3. `hold()` (183–190) waits on one sandbox-wide release file, so `release()` frees every held process at once.
  4. The fake does not model permission modes. `--permission-mode` is only recorded in argv.

### 3.3 Tests that pin the files in §2

**`tests/features/harness_threads/` (397 tests in 14 files per the base `test-plan.md`)**

| Test file | What it pins |
|---|---|
| `test_harness_threads_surface.py` | `EXPECTED_EXPORTS` (31–34, asserted at 127); three names per harness subpackage (132–137); `EXPECTED_ENUMS` exact members for 14 enums (35–50, asserted 161–173); FailureCode tail exactly the 28 harness codes after `RULE_EVALUATION_FAILED`, total `120 + 28` (176–195); `CONTRACT_CONSTANTS` (53–60, 198–204); `lib.process.__all__` (212); `OLD_NAMES` absent (61–72); `DELETED_FILES` / `DELETED_PACKAGES` absent (73–84, 215–221) |
| `test_harness_threads_static_policy.py` | INV-15 rules over every `vidbyte/harnesses/native/**/*.py` (29, 68–104); no `vidbyte.tools` import (107–114) |
| `test_harness_threads_credentials.py` | key hygiene patterns to reuse: `spy_runner` (33–44); key fragments checked in str, repr, details, log and invocations (95–118); `test_request_record_repr_hides_the_key` (121–125); `os.environ` unchanged |
| `test_harness_threads_process_bounds.py` | cancellation pattern (157–177): `create_task`, `wait_until(records("grandchild"))`, `task.cancel()`, `pytest.raises(CancelledError)`, liveness read once, bound `4 * kill_wait + slack` |
| `test_harness_threads_threads.py` | a Grok thread is found only from the workspace that created it, `grok.run_failed` (121–132) |
| `test_harness_threads_skills.py` | Grok skills folder is rebuilt only on change (49–75); an empty list after a non-empty one leaves no skills (73–74) |
| `test_harness_threads_records.py`, `_arguments.py`, `_argv.py`, `_runner.py`, `_errors.py`, `_acceptance.py`, `_launcher.py`, `_wsl.py` | config validation (`BAD_CONFIG_FIELDS` 20–33), argument refusal, argv shapes, `CliInvocation` defaults (runner 60–65), error fields, end-to-end text `f"{harness} answer to: {pack.PROMPT}"`, launcher (`win32_only` / `posix_only` markers), WSL (module-level skip on non-Windows) |

**`tests/test_prompts_interface.py` (70 lines; catalog route)**
- `set(prompts.keys()) == set(Prompt)` (49).
- Every direct import name is in `vidbyte.prompts.__all__` and equals `Prompts().get(key)` (53–59).
- `Prompts._validate_enum_sync` raises at import when an enum member has no asset (`vidbyte/prompts/catalog.py:189–192`).

### 3.4 Commands

| Scope | Command |
|---|---|
| One file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>/test_<pack>_<topic>.py` |
| New area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>` |
| Base area (must stay green) | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` |
| Surface and static policy only | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_surface.py tests/features/harness_threads/test_harness_threads_static_policy.py` |
| Everything | `PYTHONPATH=$(pwd) python -m pytest -q`, then the gate in §1.3 |

## 4. Notes for the spec author

### 4.1 Contradictions (request assumes X; code shows Y)

- **C-1. Failure codes are not all harness codes.**
  - Request assumes every `NativeThreadError` has a code of the form `<harness>.<problem>` (request lines 117 and 122), and that a classifier can key on `NativeThreadProblem` (line 52).
  - Code: `configuration.invalid_argument` comes from `vidbyte/harnesses/native/hostkit/errors.py:142` and `runtime.error` from `:159` (`vidbyte/lib/enums/failure.py:34,106`).
  - `NativeThreadError` has no `problem` attribute (`vidbyte/lib/errors/base.py:558`). The problem can only be recovered by a reverse lookup through `NATIVE_THREAD_FAILURE_CODES` (`vidbyte/lib/constants/native_threads.py:349`).
- **C-2. Exports from `vidbyte.harnesses.native` are pinned.**
  - Request assumes composites may be exported from there (ledger 9, line 60) and that every INV still holds (ledger 1).
  - Code: INV-1 says "Exactly nine public functions exist under `vidbyte.harnesses.native` … The `__all__` of `vidbyte.harnesses.native` lists exactly those nine functions plus the records, error and enums named in D-22" (`docs/spec/harness-thread-functions/spec.md:143`).
  - The test asserts `sorted(native.__all__) == sorted(EXPECTED_EXPORTS)` (`tests/features/harness_threads/test_harness_threads_surface.py:127`). Even a separate `compose` subpackage adds public functions "under `vidbyte.harnesses.native`".
- **C-3. INV-15 binds the compose subpackage.**
  - Request assumes a module-level `ThreadStep = Callable[[str], Awaitable[NativeThreadResult]]` alias (line 111) and Python-held prompt rendering (the CLI's `library.py`).
  - Code: the static scan covers every `*.py` under `vidbyte/harnesses/native/` (`test_harness_threads_static_policy.py:29`). It allows no module-level assignment except `__init__` bindings (68). It allows no str or int constant other than `""`, `0` and `1`, f-string text included (92–104).
  - The CLI renders role context and candidates in f-strings, and the paradigm precedent keeps literal file names (`_ROLE_ASSETS`, `vidbyte/paradigms/context_minimal_fanout/prompts/__init__.py:23`). Neither can be copied into `native/`.
- **C-4. No new failure codes or enum members without changing pinned tests.**
  - Request assumes room for a composite-level failure vocabulary (ledger 2, ledger 6 parse failures, ledger 5 "a non-git workspace is a closed failure").
  - Code: the FailureCode tail must be exactly the 28 codes, and `len == 120 + 28` (`test_harness_threads_surface.py:183,195`). `NativeThreadOperation` (9 members) and `NativeThreadProblem` are pinned (lines 38–39). `NativeErrorFactory(harness, operation)` needs one of those nine operations (`hostkit/errors.py:36`).
- **C-5. Diff capture is excluded by the base spec.**
  - Request assumes `capture_diff` (ledger 5) and that every INV holds (ledger 1).
  - Code: NG-3 lists "diff" as out of scope (`spec.md:50`). INV-19 says "No … diff … operation exists anywhere in the PR" (`spec.md:204`).
- **C-6. Diff capture needs its own timeout.**
  - Request assumes "no composite invents a second timeout system" (ledger 8, line 59).
  - Code: every `CliRunner` run needs `CliInvocation.timeout_seconds` and `max_output_bytes` (`vidbyte/lib/dataclasses/process.py:56–57`). A007 requires the value to be a named constant.
  - The CLI ensemble also bounds each role with `asyncio.timeout(role_timeout_seconds)` (`…/services/ensemble/service.py:126`).
  - S064 fails a sleeping retry loop that has no cumulative deadline (`lint/rules/s064_retry_overall_deadline.py:3–5`), and the CLI backoff (`stages.py:166–168`) is exactly such a loop.
- **C-7. Grok PLAN mode is undocumented.**
  - Request assumes `GrokPermissionMode.PLAN` gives a read-only reviewer (ledger 4, Prompt 2 line 25).
  - Code: the enum member exists (`test_harness_threads_surface.py:40`), but vendor-facts documents only `default`, `acceptEdits`, `dontAsk` and `bypassPermissions` (`docs/spec/harness-thread-functions/context/vendor-facts.md:51–55`).
  - Headless `default` behaviour is "UNVERIFIED" (vendor-facts line 57; A-3 at `spec.md:926`). Under `dontAsk` "a call that no rule allows is denied" (vendor-facts line 56), and SDK Grok runs read no user rules (EC-44, `spec.md:285`).
- **C-8. opencode and Muse have no read-only mode.**
  - Request assumes a proposer may be "an opencode run on GLM" in a read-only role (line 53), and that the ensemble runs "N forks in PLAN mode" (line 31). The request itself lists this as open (line 150).
  - Code: `OpencodeThreadConfig` and `MuseThreadConfig` have no permission field, and NG-9 forbids adding one (`spec.md:56`).
  - opencode allows edits by default and auto-rejects asks (D-14, `spec.md:346`). An unknown `agent`, for example `plan`, silently falls back to the default agent (EC-26, `spec.md:267`).
  - Non-interactive `run` denies `plan_enter`/`plan_exit` on sessions it creates (vendor-facts line 127).
- **C-9. Forking the planner thread conflicts with both the roster and worktree isolation.**
  - Request assumes proposers are caller-supplied pre-bound steps that fork the planner thread (lines 31, 53), and that Grok fan-out may use one worktree per step (ledger 11).
  - Code: a fork needs the source `thread_id` positionally (`grok/threads.py:64`), and that id exists only after the planner returns. A Grok thread is reachable only from the workspace that created it (`vidbyte/lib/constants/native_threads.py:425`; EC-21 `spec.md:262`; `test_harness_threads_threads.py:121–132`).
  - So a Grok proposer in its own worktree cannot fork a planner thread created in another workspace.
  - A cross-harness fork does not exist at all: a fork stays on the source harness.
- **C-10. A repair turn needs a continue capability that `ThreadStep` lacks.**
  - Request assumes `ThreadStep` is prompt-only (line 111), yet `parse_json_answer` runs "`continue_*` repair turns" (ledger 6, line 57).
  - Code: continue needs `thread_id` plus the same `api_key`, `workspace`, `model` and `config` (`grok/threads.py:59`; opencode `model: str` is required, `opencode/threads.py:51`). Composites may not hold keys (ledger 3).
  - Muse continue first runs a serve pre-check bounded by 30 s (`muse/threads.py:200`; `NATIVE_CONTROL_TIMEOUT_SECONDS = 30.0`, `vidbyte/lib/constants/native_threads.py:24`).
- **C-11. Spliced prompts can exceed the receiving harness's cap.**
  - Request assumes Grok receives "the original prompt, opencode's text and the diff" (line 132), and that the CLI prompts port over.
  - Code: Grok and Muse prompts are capped at 24,000 characters (`vidbyte/lib/dataclasses/native_threads.py:91`; `NATIVE_ARGV_PROMPT_MAX_CHARS`, `vidbyte/lib/constants/native_threads.py:27`), plus 30,000 command-line units on Windows (`vidbyte/lib/dataclasses/native_threads.py:101–102`). opencode's cap is 200,000.
  - One previous answer alone can be 100,000 characters (`NATIVE_RESULT_TEXT_MAX_CHARS`, constants line 36). `planner_system.md` is 58,578 characters and `implementer_system.md` 35,852.
  - The nine functions have no system-prompt parameter. Grok's `--system-prompt-override` and `--rules` are not `GrokFlag` members (`test_harness_threads_surface.py:43`).
  - An opaque `ThreadStep` does not reveal its harness, and so its cap, until the result returns.
- **C-12. CLI prompts break under the SDK's `str.format`.**
  - Request assumes the CLI prompts port into the SDK prompt system as-is (ledger 10; hint line 124).
  - Code: SDK consumers render catalog prompts with `str.format` (`vidbyte/prompts/prompts/__init__.py:13–14`). The CLI files use `{{name}}` placeholders with a literal replace (`library.py` `_render`).
  - Under `str.format`, `{{task}}` renders as the literal text `{task}` and is never filled.
- **C-13. The CLI enforces JSON with a host schema the native functions lack.**
  - Request assumes the CLI's JSON contracts carry over (ledger 10).
  - Code: the CLI gets JSON through a host-enforced strict schema (`output_schema=CodexOutputSchema.strict_model(...)`, `…/services/ensemble/sdk.py:89–107`). The native functions have no output-schema parameter, so prompt text plus the parser is the only enforcement.
  - `NativeThreadResult.text` is cut at 100,000 characters with `text_truncated` set (EC-31, `spec.md:272`).
- **C-14. There are ten CLI ensemble prompt files, not eleven.**
  - Request (hint line 123) says "eleven `.md` files".
  - Code: `C:/Users/422mi/vidbyte-repos/vidbyte-cli/src/vidbyte_cli/services/ensemble/prompts/` holds 10 `.md` files, plus `library.py` and `__init__.py`. Ledger 10 lists the same ten names.
- **C-15. The PR is stacked, not branched from `main`.**
  - Request (line 5) targets `feat/native-grok-opencode-meta-hosts`.
  - Code: `CONTRIBUTING.md:40` says "Create a focused branch from the latest `main`."
- **C-16. The CLI has no effort ladder to port.**
  - Request assumes `StageSpec` carries an "effort ladder" and that the classifier can decide "raise effort" (lines 29, 52), as a "direct port of the CLI stages primitive". Per-harness meaning is an open question in the request (line 149).
  - Code: the CLI has a fixed `effort` per stage and no ladder (`…/types/runtime.py:871`; `stages.py:303–367`). Its classifier keys on Codex `codex_error_info` and dotted `failure_code` strings, not on a problem enum (`stage_failures.py:71–100`).
  - Native effort enums differ per harness: Grok tops out at `max`, Muse at `ultra`, and opencode has only a free-form `variant` (`test_harness_threads_surface.py:41–42`; vendor-facts line 121).
- **C-17. Concurrent Grok calls have a third safe pattern.**
  - Request assumes Grok fan-out must be serialized or run in worktrees (ledger 11, line 62).
  - Code: EC-27's own documented safe pattern is "run concurrent Grok calls in one workspace only with the skill set an earlier call already prepared, or use separate workspaces" (`spec.md:268`). `hostkit/skills.py:34–35` leaves a matching folder untouched. The base test plan did not test EC-27 (`docs/spec/harness-thread-functions/test-plan.md:86`).

### 4.2 Gaps and constraints that are not contradictions

- **G-1. A bound step can leak the key in its `repr`.** `functools.partial(f, api_key="SECRET-KEY-123", workspace="/w")` has the repr `functools.partial(<function f …>, api_key='SECRET-KEY-123', workspace='/w')`. This was checked here with Python 3.11.0 standard library only. INV-2 forbids the key in "the `repr` of any record"; the precedent fix is `field(repr=False)` (`test_harness_threads_credentials.py:121–125`).
- **G-2. Worktree-per-step costs for Grok.** Every new worktree path gets a new Grok home that is never removed, about 1 MB each (EC-43, `spec.md:284`; `vidbyte/harnesses/README.md:178`). A fresh home has no skills prepared yet, and its threads can be continued only from that worktree path, so repair turns must finish before the worktree is removed.
- **G-3. A Muse worktree must be on a drive path.** Muse WSL mode maps `C:\w\repo` to `/mnt/c/w/repo` and refuses UNC or drive-less paths with `ConfigurationError(MUSE_WSL_WORKSPACE_RULE)` (`vidbyte/harnesses/native/muse/launcher.py:44–53`).
- **G-4. The tests cannot show a verifier being stopped from writing.** The fake has no workspace-writing mode and models no permission mode (§3.2). Acceptance item "a verifier that tries to write" (request line 137) can therefore be shown only by detection, such as a before/after workspace comparison, plus the argv the composite passed. Vendor-side refusal cannot be shown.
- **G-5. Fail-then-succeed needs a fake change.** Retry exhaustion works today with `mode: "fail"`. A retry that then succeeds needs a per-launch counter, because every launch of one command reads one scenario.
- **G-6. git is unreachable in the sandbox.** `PATH` holds only the sandbox `bin` (`tests/features/harness_threads/conftest.py:257`), so `CliRunner` cannot find `git`. It returns a `NOT_FOUND` launch failure, which `test_harness_threads_runner.py` covers for a missing program.
- **G-7. Partial-success records see more than `NativeThreadError`.** Steps can also raise `ConfigurationError` from composite validation, an `OSError` from git or worktree work, and `CancelledError`. Ledger 7 names only `NativeThreadResult` or `NativeThreadError`.
- **G-8. Gather rules.** S063 requires a `BaseException` check on `gather(return_exceptions=True)` results in the same module. S019 requires cancellation to be re-raised. S006 (RUF006) requires every `create_task` result to be kept. No `TaskGroup` precedent exists in `vidbyte/`.
- **G-9. Prompt-route costs.**
  - **Catalog route:** each prompt becomes a public direct import in `vidbyte.prompts.__all__` (`vidbyte/prompts/__init__.py:22–32`, 33 lines in total). It needs `Prompt` members and the header counts (F-6), plus README rows (F-7). Package data is already covered (`pyproject.toml:69`).
  - **Local route:** needs F-8 and file names from constants. `import vidbyte` already loads the catalog (`vidbyte/__init__.py:539`), so the catalog route adds no import cost.
- **G-10. JSON parsing has no canonical helper.** Seven sites parse JSON from model text and none is in `vidbyte/lib/` (§2.3). AGENTS.md principle 5 (lines 37–41) applies to this choice, and request line 146 leaves it open.
- **G-11. opencode sessions belong to a project, and the fake ignores this.**
  - Real opencode ties sessions to a project: "Sessions belong to a project (the git worktree of `--dir`/cwd)". Whether `-s <id>` finds a session created from a different project directory is UNVERIFIED (vendor-facts line 146; A-10).
  - So an opencode reviewer in its own worktree may be unreachable for a continue from another directory.
  - The fake keeps every opencode session in one state folder regardless of `--dir` (`fake_harness.py`, opencode branch). It cannot show this difference.
  - A session reached with `-s` keeps its own permission rules (vendor-facts line 259).
- **G-12. A Grok writer needs ACCEPT_EDITS.** "Headless approval is needed under the vendor default (Grok `default` mode refuses edits; Muse `on-request` with the approval judge)". The result is "a thread that did not edit, `run_failed`, or `timed_out`" (EC-35, `spec.md:276`).
- **G-13. Spliced prompts must be NUL-free and non-blank.** `NATIVE_PROMPT_PATTERN = r"[^\x00]+"` (constants line 54) is checked with `require_text`, which also refuses blank text (`vidbyte/lib/dataclasses/validation.py:41–47`).

### 4.3 Unverified

- unverified: whether opencode ships a built-in read-only agent that `OpencodeThreadConfig(agent=…)` could select.
- unverified: what Grok `plan` and `default` modes do headless when an edit is attempted (vendor-facts line 57; A-3).
- unverified: whether Grok tolerates concurrent forks or continues of one session in one `GROK_HOME`. EC-28 calls concurrent continues "vendor behavior".
- unverified: whether git inside WSL can use a Windows git worktree, whose `.git` file holds a `gitdir:` with a Windows path.
- unverified: git behaviour under the sandbox's redirected `HOME`/`USERPROFILE`: commit identity, and whether system `core.autocrlf` adds CRLF noise to diffs. The base test plan records `core.autocrlf=true` in this checkout.
- unverified: whether S045 (Ruff ASYNC109) flags a parameter named `timeout_seconds` or only `timeout`.
- unverified: whether `pip install -e ".[dev]"` from this worktree repoints a shared environment (§1.3).

### Base PR spec constraints that bind the composites

All items are in `docs/spec/harness-thread-functions/spec.md`. Each line says what a composite could break.

- **INV-1** (143): exactly nine public functions under `vidbyte.harnesses.native`; `__all__` lists exactly the D-22 names; other classes stay internal.
- **INV-2** (144): the key never reaches argv, stdin, error text or attributes, any record's `repr`, or logs, and the SDK never writes `os.environ`. This covers bound steps and git argv.
- **INV-3** (145): runs authenticate only with the caller's key. A composite must go through the nine functions, never start vendors itself.
- **INV-4** (149): every argument is checked before any process starts or any file is written. Composite git and worktree work would run first unless validation precedes it.
- **INV-5** (150): error fields (`failure_code`, `harness`, `operation`, `next_step`, `likely_cause`, `thread_id`, `exit_code`, `vendor_message`). Composites must not rewrap or strip them.
- **INV-6** (163): failure classification is closed; the factory never builds a non-`FailureCode` code.
- **INV-7** (174): no caller value is ever read as a flag. Git argv built from caller paths must go through `CliArgv` style rules.
- **INV-8** (180): every vendor process runs at most `config.timeout_seconds`, and the tree is stopped on timeout.
- **INV-9** (181): `CancelledError` propagates unchanged, never turned into `NativeThreadError`. Gather must preserve it.
- **INV-10** (182): no child ever waits on stdin. A git child gets `stdin_text=None`, which means DEVNULL.
- **INV-11** (183): thread ids. A fork returning the source id is a `protocol_mismatch`, so composites must not reuse a fork result as the source.
- **INV-12** (188): skills reach the harness only through SDK-owned folders; the Grok `skills/` folder is rebuilt when the set differs (EC-27).
- **INV-13** (194): the Grok home is `<user home>/.vidbyte/grok-homes/<sha256 key>`, so every worktree path gets its own home.
- **INV-15** (196–200): AST rules for every module under `vidbyte.harnesses.native`: no module-level assignments except init bindings, and no literals except docstrings, `__all__`, `""`, `0` and `1`.
- **INV-16** (201): every argv the feature starts is built by `CliArgv.build` from `CliOption` records.
- **INV-18** (203): `cwd` and `--dir`/`--cwd`/`--workspace` are the workspace. A worktree used as workspace becomes the thread's identity.
- **INV-19** (204): no usage, cost, balance, readiness, version, model-list, session list/search/read/page, revert, **diff**, MCP, steer, interrupt or wait operation "anywhere in the PR".
- **INV-20** (205): `vidbyte.lib.*` imports nothing from harnesses or higher; `vidbyte.harnesses.native.*` imports nothing from `vidbyte.tools`.
- **INV-21** (208): five restored files stay byte-identical to `origin/main`: the MCP transport and its README, the toolsets init, the tools README and the configs init.
- **INV-22** (209): the 120 main `FailureCode` members keep name, value and order; new members follow `RULE_EVALUATION_FAILED`. The surface test pins exactly 28.
- **INV-23** (210): `import vidbyte` starts no process and does not import `vidbyte.harnesses.native`; the root `__all__` is unchanged (lint C016).
- **EC-3** (244): prompt caps (24,000 Grok/Muse, 200,000 opencode) and blank or NUL prompts, which spliced prompts can hit.
- **EC-15** (256): a run that passes `timeout_seconds` gives `<h>.timed_out` after the tree stops. A writer awaiting approval can end this way.
- **EC-16** (257): cancellation stops and reaps the tree, then `CancelledError` propagates.
- **EC-17** (258): the stdout cap gives `<h>.output_too_large`.
- **EC-21** (262): Grok continue with an id from another workspace gives `grok.run_failed`. Repairs and forks must use the creating workspace.
- **EC-22** (263): a Grok or opencode fork that returns the source id gives `protocol_mismatch`.
- **EC-23** (264): vendor failure gives `run_failed`, which a stage classifier must handle.
- **EC-25** (266): an unknown Grok model silently runs the default model (accepted).
- **EC-26** (267): an unknown opencode `agent` silently falls back to the default agent (accepted).
- **EC-27** (268): concurrent Grok calls in one workspace whose skill set is not yet prepared can fail with `grok.launch_failed` or lose a skill mid-run. Accepted: "run concurrent Grok calls in one workspace only with the skill set an earlier call already prepared, or use separate workspaces. No locking is added."
- **EC-28** (269): two concurrent continues on one thread follow vendor behavior, and there is no per-thread lock.
- **EC-31** (272): answer text over 100,000 characters is cut, with `text_truncated=True`.
- **EC-33** (274): a config record for another harness is refused naming `config`. Binding helpers must keep configs per harness.
- **EC-35** (276): under vendor defaults an edit is refused, the run fails, or it waits until timeout.
- **EC-36** (277): project instructions and skills are untrusted in headless mode, so they are not loaded.
- **EC-37** (278): personal skills in vendor home folders may load beside the caller's.
- **EC-40** (281): different spellings of one workspace map to one Grok home. Worktree paths are distinct workspaces.
- **EC-41** (282): a workspace `opencode.json` can set the provider `baseURL`. A worktree checks out the repository's config too.
- **EC-42** (283): workspace = user home puts the Grok home inside the workspace (accepted).
- **EC-43** (284): every new workspace path creates a Grok home that is never removed.
- **EC-44** (285): SDK Grok runs read nothing from `~/.grok`, so the user's own permission rules and hooks do not apply.
- **EC-45** (286): a Muse fork or exec that answers with the wrong id is a protocol mismatch.
- **NG-1** (48): "Composite cross-harness functions" were a non-goal of the base PR. §2 calls NG-1 and NG-4 "the later slices", so this PR is that slice.
- **NG-2** (49): no live turns, spawn-then-wait, interrupt, steer or streaming progress. Composites must not add progress streaming or mid-run steering.
- **NG-3** (50): no usage, cost, balance, readiness, version, model lists, session listing/search/read/page, revert, **diff** or MCP management.
- **NG-4** (51): no model-facing tools or toolsets (ledger 12).
- **NG-5** (52): no synchronous variants (ledger 12).
- **NG-6** (53): GLM and DeepSeek only through opencode.
- **NG-7** (54): never read a key from environment variables or stored logins. `bind_thread` must take the key as an argument.
- **NG-8** (55): local skill folders only.
- **NG-9** (56): no new permission controls: no approve-everything mode, opencode permission rules, Muse approval modes, or Grok allow/deny/max-turns. So opencode and Muse reviewers have no read-only switch.
- **NG-10** (57): no root `vidbyte` exports, no `vidbyte-sdk` CLI command, no new dependencies.
- **NG-11** (58): no fork without a prompt.
- **NG-12** (59): no workspace trust (Grok `--trust`, Muse `--trust-workspace`).
- **T-1** (597): careless key input, guarded by the record and INV-3. A bound step must keep it.
- **T-2** (598): hostile prompt or untrusted input. One step's model output spliced into the next prompt, and JSON verdicts from a model, are untrusted input.
- **T-3** (599): the key in `ps` argv or logs. Git argv, bound-step `repr` and error text must not carry it.
- **T-5** (601): a malicious skill folder; links are copied as links.
- **T-6** (602): malicious workspace content. A worktree of an untrusted repository brings its `opencode.json` and files; the Grok home stays outside the workspace.
