# Code map: public-skill-loader (S0 scout)

Base: worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader`, branch
`feat/public-skill-loader`, HEAD `179d8adc8872d9a616f190c93c75b0169ec719c4` (the squash of PR #904).
Paths are relative to the worktree root unless absolute. Line numbers are at HEAD. Nothing was
installed, linted, or tested; the one command run was `python -c "import vidbyte; print(vidbyte.__file__)"`.

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

AGENTS.md is 81 lines. CLAUDE.md is only `@AGENTS.md`.

### Rules, by AGENTS.md heading

- **Repository Map.**
  - "Read it [`REPO_MAP.md`] before you create a file, move code, or search for where something
    lives, and put new code where it says that kind of code belongs."
  - Each folder `README.md`: "read it to the end before you change anything inside the folder".
    Its closing `## Notes for agents` section records review lessons.
  - "lint rule A009 keeps every folder README at or under 40,000 characters". The root
    `README.md` is exempt.
  - "Do not grep, glob, or read files under `docs/` as part of ordinary work". The pipeline's own
    `docs/spec/public-skill-loader/` is the exception that request.md names.
  - "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`;
    none of the narrow verification scripts beside it substitutes for it."
  - Callout: the Placement Rules are "binding for all new code, and the `AGENTS.md placement`
    workflow enforces it on every pull request by moving misplaced code to the location it
    names". The workflow file is `.github/workflows/agents-md-placement.yml`.
- **General Coding Style Guidelines (intro).** "Do not rewrite untouched code just to make it
  conform; that belongs in its own pull request."
- **1. Keep Call Chains One Level Deep.**
  - "a function may call another of its own functions, but that second function should not call
    a third."
  - "Avoid defining functions inside other functions as well, unless an API requires a callback
    or a decorator."
- **2. Narrate Main Functions in Plain English.**
  - "place short plain-English comments throughout the body".
  - "When you change the steps of a main function, update its comments in the same edit".
- **3. Build in Layers of Small, Single-Purpose Classes.**
  - "`vidbyte/lib/` is the bottom layer ... nothing in `vidbyte/lib/` may import from a layer
    above it"; "no two modules depend on each other in a cycle".
  - "Keep files well below 1,000 lines".
  - "If describing the job of a function or a class needs the word 'and', it is probably two".
- **4. Use Validated Dataclasses for Core Inputs and Outputs.**
  - Core logic takes "a dataclass as input and return[s] a dataclass as output".
  - Validate in `__post_init__`. "Prefer `@dataclass(frozen=True, slots=True)`". Type any closed
    set as an enum.
- **5. Write Shared Logic Once, as a Canonical Helper in `lib/`.**
  - "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the
    option you need to it rather than copying it into a variant beside your feature."
  - The example is `HttpTransport` in `vidbyte/lib/http/transport.py`.
- **Placement Rules / Dataclasses go in `vidbyte/lib/dataclasses/`.**
  - "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`". The `skills`
    domain module already exists.
  - "Import it from its domain module ... A feature package may re-export it from its own
    `__init__.py` as part of its public API, as `vidbyte/agents/jev/__init__.py` does".
  - The only exceptions are `*Settings` classes (in `vidbyte/agents/settings/` or the agent's own
    `settings.py`) and the JEV preflight questions.
- **Placement Rules / Enums go in `vidbyte/lib/enums/`.** "Every new enum ... is defined in
  `vidbyte/lib/enums/<domain>.py`, and every public enum is added to the export list in
  `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- **New JEV code.** "A new JevAgent capability is a named, validated field on `JevAgentSettings`."
  This matters here only as a boundary: the public loader is not a Jev capability, and JevAgent
  must keep its behavior.
- **Existing code.** Do not copy old misplaced dataclasses or enums "as precedent". Moving them
  "belongs in its own pull request".

**PR and commit conventions.** AGENTS.md states none. The request settles these instead:
- the PR stays a draft;
- the source change is committed first, then the regenerated contract as its own commit;
- never amend after generating.

### Commands

Sources: AGENTS.md, `scripts/run_ci.py`, `pyproject.toml`, `lint/README.md`, `contracts/README.md`,
and the field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/local-ci-verification.md`.

| Purpose | Command |
|---|---|
| Install (dev) | `python -m pip install -e ".[dev]"` (from the workspace-facts file; not run; see §4 note 20) |
| Which checkout is imported | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` |
| Lint (ratcheted) | `python lint/run.py` (`--rule <ID>`, `--all`, `--format json`); the last line reads `AGENT-LINT: PASS` |
| Contract | `python scripts/generate-sdk-public-api.py`, then `python scripts/generate-sdk-public-api.py --check` |
| Contract lint | `python lint/run.py --rule C016 && python scripts/generate-sdk-public-api.py --check` |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1`. It scans tracked files only, so `git add` new files first. It runs in `.github/workflows/static-policy.yml:23-30`, not in `run_ci.py`. |
| Test one file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_contract.py` |
| Test the area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload tests/test_jev_skill_preload.py` |
| Test all | `PYTHONPATH=$(pwd) python -m pytest` |
| Area scripts | `python scripts/test-jev-skills-preload.py`; `python scripts/test-jev-agent-scaffold.py` |
| Source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` |
| Package stage | `python scripts/run_ci.py --stage package` (without PYTHONPATH) |
| Full gate | `python scripts/run_ci.py` |

What the gate runs (`scripts/run_ci.py`, 287 lines):
- **Source stage**, in order:
  - the tracked-bytecode check;
  - `lint/run.py`;
  - `compileall vidbyte`;
  - `scripts/check_context_write_paths.py`, `scripts/check_context_primitive_introductions.py`
    and `scripts/check_reasoning_trace_contracts.py`;
  - `python -m pytest`.
- **Package stage**: build, twine check, wheel inspection, a clean-venv install, and a smoke test
  asserting `vidbyte.__version__ == version('vidbyte-sdk')`.

pytest settings (`pyproject.toml` `[tool.pytest.ini_options]`):
- `testpaths=["tests"]`;
- `addopts=["--strict-config","--strict-markers"]`;
- `asyncio_default_fixture_loop_scope="function"`;
- no `pythonpath` option;
- dev pins `pytest==8.3.5` and `pytest-asyncio==1.3.0`.

Never raise a number in `lint/baseline.json`.

### Lint rules this change will meet

Baselines are from `lint/baseline.json`.

- **C016** (0): the contract equals the generator output for `vidbyte.__all__` plus the pyproject
  version (`lint/rules/c016_public_api_contract_current.py`).
- **S015** (13): every `__all__` entry is bound, with no duplicates. Every public name imported
  in `vidbyte/__init__.py` must be in `__all__` ("root public import is missing from
  `__all__`"). Lazy exports are recognized only through a module-level dict whose name contains
  "lazy" and "export" (`lint/rules/s015_public_export_integrity.py`).
- **A006** (34): `vidbyte.lib`, `vidbyte.providers`, `vidbyte.sessions` and `vidbyte.sources` must
  not import orchestration packages such as `vidbyte.agents`. Function-local imports count.
  Only TYPE_CHECKING edges and `__init__.py` files are skipped.
- **A001** (642): file headers need PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON
  MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS and TESTS.
- **A002** (703): `# @intent <name>` within 20 lines of a `def` that uses a policy token (retry,
  fetch, request, send, provider, ...). The field guide's `comment-format.md` says it goes on its
  own first line, and that multi-line `#` comments are at most 72 columns.
- **A009** (0): READMEs are capped at 40,000 characters. `vidbyte/agents/skills/README.md` is
  7,596 characters and `vidbyte/agents/README.md` is 22,470.
- **C011** (2): sync twins. A public class whose name or an ancestor's name ends in Agent,
  Runner, Harness, Session or Machine, and which defines async `arun()`, needs a sync `run()`
  with the same signature. The pattern is `TextModelRunner.run` (`vidbyte/lib/runners/text.py:93-100`).
  The rule does not fire on a method named `load()`.
- **S020** (1): README File Index parity. It is opt-in; the skills README has no File Index.
- **S063** (4): gather results must be classified against BaseException.
- **From the field guide's `blocking-lint-invariants.md`:**
  - S012: do not name a non-HTTP helper `request`.
  - S060: no `dict[str, Any]` in `vidbyte/lib/dataclasses/`. S039 bans TypedDict.
  - C002: derive status bools instead of storing them.
  - A007: use the `os.fstat` capped read.
  - A003: a new error class needs the full DIAGNOSTIC_FIELDS.
- **TID251** bans `asyncio.Lock` (per the `vidbyte/agents/skills/loader.py` header).
- **No file-length rule and no placement rule exist in `lint/`.** Placement is enforced by the
  workflow.

## 2. Files this change will touch

Format: path — what it does today — what will change — the pattern to follow. "Spec's call"
marks a change whose shape the spec must decide; the scout does not design it.

### A. The loader and its records

1. **`vidbyte/agents/skills/loader.py`** (92 lines)
   - Today:
     - `class SkillLoader` is at :31.
     - `__init__(self, entries: tuple[SkillEntry | SkillDocument, ...])` (:34) does no I/O. It
       pre-remembers `SkillDocument` entries and builds one resolver per `SkillSourceType`
       (:40-47).
     - `async def load(self) -> tuple[SkillResolution, ...]` (:49) groups pending entries, runs
       `asyncio.gather(..., return_exceptions=True)` (:61), and re-raises any BaseException
       (`raise answer`, :66). It remembers non-transient results and returns them in settings
       order.
     - `documents()` is at :77 and `_pending_groups()` at :82. `__all__ = ["SkillLoader"]` (:92).
     - There is no type check, no duplicate-name check, no byte-limit parameter and no
       credential parameter.
   - Will change: this is the existing loader the public door exposes or wraps (spec's call).
     Its header "ROLE IN CODEBASE" names JevSkillsPreload as the builder, so the header changes if
     a second caller exists.
   - Pattern: the header's WHAT NOT TO DO:
     1. no I/O in `__init__`;
     2. do not catch resolver exceptions;
     3. never replace a remembered resolution;
     4. no module-level memory.
2. **`vidbyte/agents/skills/__init__.py`** (16 lines)
   - Today: `__all__: list[str] = []` (:16). The header says "callers import each module directly"
     and, under WHAT NOT TO DO, "1. Do not add per-resolver imports or exports. 2. Do not add
     import-time side effects."
   - Will change: probably nothing. Any change must respect that header.
   - Pattern: callers import the module directly, as `vidbyte/agents/jev/alignment/skills.py:37`
     does with `from vidbyte.agents.skills.loader import SkillLoader`.
3. **A new public module, only if the spec picks a facade** (spec's call)
   - Today: nothing. REPO_MAP gives no location for a "public resolver function".
   - `REPO_MAP.md:107-109` calls `vidbyte/agents/skills/` "agent-agnostic machinery" that "never
     imports a specific agent, so any agent can reuse it".
   - Any new record goes in `vidbyte/lib/dataclasses/skills.py`, any new enum in
     `vidbyte/lib/enums/skills.py`, and any new bound in `vidbyte/lib/constants/skills.py`.
   - Pattern: the field guide's `class-bound-helpers.md` prefers a static helper class over free
     functions, with `__all__` exporting the class. Use the module header format of the existing
     resolver modules (A001).
4. **`vidbyte/lib/dataclasses/skills.py`** (268 lines)
   - Today:
     - Header line 5: "Data and validation only. No record reads a file, an environment variable,
       or the network".
     - `SkillDocument` (:42-61, class at :43) has `name`, `description`, `text` and
       `source: str | None = None`. Each must be non-blank text, and is kept exactly.
     - `SkillEntry` base is at :108, plus six subclasses. `GitHubSkill.token` and
       `AnthropicSkill`/`OpenAISkill.api_key` are `repr=False`.
     - `SkillResolution` (:234) holds `document`, `reason` and `detail`: exactly one of a
       document, or a reason plus a non-blank detail. Its `transient` property is at :252.
     - The module `__all__` includes `SkillResolution` and `SkillText`.
   - Will change: only if the public path needs a new or changed record, for example to export
     `SkillResolution` or to add a result or options record (spec's call).
   - Pattern: `@dataclass(frozen=True, slots=True)`, `__post_init__` validation through
     `SkillText.require*`, and `ConfigurationError` naming the field.
5. **`vidbyte/lib/constants/skills.py`** (143 lines)
   - Today:
     - `SKILL_MARKDOWN_MAX_BYTES = 1_048_576` (:30)
     - `SKILL_DOWNLOAD_MAX_BYTES = 33_554_432` (:35)
     - `SKILL_FETCH_TIMEOUT_SECONDS = 10.0`, `SKILL_FETCH_RETRY_COUNT = 1`,
       `SKILL_FETCH_BACKOFF_SECONDS = 0.5` (:39-41)
     - `SKILL_FETCH_DEADLINE_SECONDS = 25.0` (:45)
     - `SKILL_TRANSIENT_REASONS` (:49)
     - `GITHUB_CREDENTIAL_ENV_VAR = "GITHUB_TOKEN"` (:72)
     - Caps are inclusive. The module imports only `vidbyte.lib.enums.skills`.
   - Will change: only if the spec adds a caller byte limit or any other bound (spec's call).
   - Pattern: the field guide's `strict-config-dataclasses.md`: "Keep bounds in
     `vidbyte/lib/constants/`" and "Local size caps are generous and derived from the vendor
     constants".
6. **`vidbyte/lib/enums/skills.py`** (94 lines) and **`vidbyte/lib/enums/__init__.py`** (254 lines)
   - Today:
     - `SkillSourceType` (:51) and `SkillUnavailableReason` (:62, eight members including
       `DECISION_FAILED`).
     - `SkillFetchStep` (:75) is internal ("Do not export `SkillFetchStep` beyond
       `vidbyte.lib.enums`").
     - `__init__` exports them at :140-146 and :242-244.
   - Will change: nothing is expected, because the reasons already exist and are root-exported.
     They change only if the spec adds a member or an enum. The header calls a new reason "a
     public contract change".
   - Pattern: the file's header, COMMON MODIFICATION PATTERNS.

### B. The export chain and the version

7. **`vidbyte/__init__.py`** (1,366 lines)
   - Today:
     - `__version__ = "0.2.1"` (:40).
     - `from vidbyte.agents import (...)` runs from :42 to :274 and includes the nine #904 names.
     - Direct `vidbyte.lib.dataclasses.*` import blocks are at :436-466.
     - `__all__` (:726-1366) is not sorted. The skill names are at :867-876.
     - There is no lazy `__getattr__`.
   - Will change:
     - `__version__` becomes `"0.2.2"`.
     - The new public name(s) are imported and added to `__all__` (S015).
   - Pattern: the existing import blocks. Root imports from deeper modules already exist (:436-466).
8. **`vidbyte/agents/__init__.py`** (564), **`vidbyte/agents/jev/__init__.py`** (281),
   **`vidbyte/lib/__init__.py`** (142), **`vidbyte/lib/dataclasses/__init__.py`** (497)
   - Today:
     - The entry names and `SkillDocument` are re-exported at every level: agents :84-214 and
       :395-404; jev :121-130, :148 and :264-273; lib.dataclasses :212-221 and :444-451.
     - `SkillResolution` is exported at none of them.
   - Will change: spec's call. `vidbyte/agents/skills/README.md` "Adding a source" step 5 routes
     new entry classes through all five files. Whether a loader-facing name follows the same
     chain is open (§4 note 13).
   - Pattern: the existing skill lines in each file.
9. **`contracts/sdk-public-api.json`** (647 lines)
   - Today:
     - `"version": "0.2.1"` (:5) and `source.commit` `2bb5a8e9...`.
     - Exports are sorted. The skill lines are AnthropicSkill :47, GitHubSkill :218,
       InlineSkill :246, LocalSkill :382, OpenAISkill :429, SkillDocument :525,
       SkillEntry :526, SkillSourceType :527, SkillUnavailableReason :528 and
       SkillsShSkill :529.
   - Will change: it is regenerated, never hand-edited.
   - Pattern: `contracts/README.md`. Run `python scripts/generate-sdk-public-api.py` after the
     source commit, then `--check`. The generator is run, not edited.
10. **The version literals.** `git grep -n "0\.2\.1" -- ':!docs'` finds these, and no other hits:
    - `pyproject.toml:7`
    - `vidbyte/__init__.py:40`
    - `vidbyte/cli/__init__.py:58` (`return "0.2.1"`, the `VersionResolver.resolve` fallback)
    - `vidbyte/mcp_server/server/core.py:79` (`version: str = "0.2.1",`)
    - `vidbyte/tools/mcp/client.py:46` (`"clientInfo": {"name": "vidbyte-sdk", "version": "0.2.1"}`)
    - `README.md:86` (`pip install vidbyte-sdk==0.2.1`)
    - `llms.txt:17`
    - `.github/ISSUE_TEMPLATE/bug_report.yml:19` (`placeholder: 0.2.1`)
    - `contracts/sdk-public-api.json:5` (regenerated)

    No test pins `0.2.1`.
    - Will change: every one becomes 0.2.2.
    - Pattern: commit `29fbfd28` (the 0.2.0 to 0.2.1 bump, #695) changed the same literals, then
      regenerated the contract in a second commit.

### C. Documentation and maps that name the loader's only consumer

11. **`vidbyte/agents/skills/README.md`** (49 lines)
    - Today:
      - Line 3 describes entries in `JevAlignmentSettings`.
      - The contract bullets are "No I/O at construction", "Fail open, with reasons", "Memory"
        and "Bounds".
      - "Adding a source" steps 5-6.
      - `## Notes for agents`: :44 is the import-order rule and :46 is the env-credential warning.
    - Will change: consumer wording and any new public-entry contract (spec's call).
    - Pattern: keep `## Notes for agents` last. Stay under 40,000 characters.
12. **`vidbyte/agents/README.md:297`**
    - Today: "`skills/`: `SkillLoader` and one resolver per source, the agent-agnostic loader that
      turns declarative skill entries into `SkillDocument`s for `JevAgent`'s skill preload."
    - Will change: probably the consumer wording.
    - Pattern: one line per subpackage.
13. **`REPO_MAP.md:107-109`**
    - Today: "today JevAgent's skill preload is its only consumer".
    - Will change: probably that clause. AGENTS.md says to regenerate a wrong entry from the tree.
    - Pattern: the File Index entry style.
14. **`README.md`** and **`llms.txt`**
    - Today: only the version literals touch this change. Neither documents skill sources or
      `SkillLoader`.
    - Will change: the version. Documenting the new public API is the spec's call.
    - Pattern: README.md's Layer Guide table; the bump commit `29fbfd28`.

### D. Must keep behavior (JevAgent); touched only if the loader's interface moves

15. **`vidbyte/agents/jev/alignment/skills.py`** (219 lines)
    - Today:
      - `JevSkillsPreload.__init__` sets `self.loader = SkillLoader(skills)` (:76).
      - `run` awaits `self.loader.load()` (:84) and reads `self.loader.documents()` (:85, :132,
        :153, :174, :183).
      - It batches the skills, asks DecisionModelHelper, and appends the selected texts.
    - Will change: nothing, unless the loader's signature changes.
    - Pattern: it imports `vidbyte.agents.skills.loader` directly.
16. **`vidbyte/agents/jev/settings.py`**
    - Today: `JevAlignmentSettings.skills` (:83). `_normalized_skills` does the following:
      - rejects a bare str or bytes;
      - turns strings into `SkillDocument(name=f"inline_skill_{index}", ...)`;
      - rejects any other element type;
      - raises ConfigurationError on duplicate names (`details={"names": sorted(dups)}`).
    - Will change: nothing is expected. It is the only place the entry tuple is validated
      (§4 note 6).
    - Pattern: none to copy. It is a `*Settings` exception under the Placement Rules.
17. **`vidbyte/agents/jev/agent.py:80-89`**
    - Today: builds `JevSkillsPreload` only when `settings.alignment.skills` is non-empty.
    - Will change: nothing.

### E. Tests (detail in §3)

18. **`tests/features/jev_skills_preload/`** and **`tests/test_jev_skill_preload.py`**
    - Today: they pin the loader and JevAgent behavior.
    - Will change: new tests for the public path; possibly the export lists in
      `test_skill_sources_contract.py` (spec's call). Whether a new feature pack folder is created
      is the spec's call.
    - Pattern: the pack conventions in §3.

## 3. Tests that cover those files

**Framework.**
- pytest plus pytest-asyncio (`@pytest.mark.asyncio`, function-scoped loop).
- `tests/test_jev_skill_preload.py` is `unittest` (`unittest.TestCase` and
  `IsolatedAsyncioTestCase`), and pytest collects it.
- `tests/__init__.py` exists. `tests/conftest.py`, `tests/features/__init__.py` and
  `tests/features/jev_skills_preload/__init__.py` do not.

**Feature pack `tests/features/jev_skills_preload/`.** It has FEATURE.md (122 lines) and
`conftest.py` (347 lines). Its test modules, with line counts:

| Module | Lines | Module | Lines |
|---|---|---|---|
| `test_skill_sources_acceptance.py` | 169 | `test_skill_sources_contract.py` | 119 |
| `test_skill_sources_entries.py` | 242 | `test_skill_sources_fetch.py` | 195 |
| `test_skill_sources_github.py` | 331 | `test_skill_sources_jev_wiring.py` | 159 |
| `test_skill_sources_local.py` | 259 | `test_skill_sources_markdown.py` | 129 |
| `test_skill_sources_memory.py` | 255 | `test_skill_sources_security.py` | 335 |
| `test_skill_sources_skills_sh.py` | 239 | `test_skill_sources_vendor.py` | 499 |

Also `tests/test_jev_skill_preload.py` (479) and the runner `scripts/test-jev-skills-preload.py`.

**Fixtures (`conftest.py`).**
- **`fake_http`.** It monkeypatches `HttpTransport._send_once` with a URL-routed fake that records
  `SentRequest(url, headers, max_response_bytes, timeout_seconds, follow_redirects)`, and patches
  `transport_module.asyncio.sleep`.
  - Helpers: `.answer(url, *answers)`, `.reply(status, body, headers)`, `.oversized(n)`,
    `.connection_error()`, `.HANG`, `.count(url)`, `.urls()` and `.sent`.
  - An unrouted URL raises AssertionError.
- **Autouse `_isolated_skill_environment`.** It deletes `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` and
  `OPENAI_API_KEY`, then `chdir`s to `tmp_path`.
- **`jev`.** It installs a scripted helper by patching
  `"vidbyte.agents.jev.alignment.skills.DecisionModelHelper"`.
- **`make_agent`.** It builds a JevAgent with `JevRuntimeSettings(preflight=())` and a capturing
  runner through `tests.agent_test_support.bind_test_runner`. This needs the repo root on
  `sys.path`.
- **Others:** `bind_main_runner`, `skill_md`, `write_skill`, `record_io` (spies on `open`,
  `os.open`, `os.stat` and env `__getitem__`) and `spin_loop`.
- **Conftest rules:** "Do not import or stub vidbyte.agents.skills or the new entry classes" and
  "Do not patch SkillMarkdown, entry validation, SkillLoader memory, zipfile, or yaml".
- **Module convention.** Every module guards its feature imports into `FEATURE_MISSING` and adds
  an autouse `_feature_present` fixture, which fails each test at setup instead of skipping it.
  For example, `test_skill_sources_skills_sh.py:23-44`.

**What already pins behavior the public path must not break.**
- **memory.** Remembered entries; overlap; a crash becomes AgentExecutionError with `__cause__`
  through JevAgent; cancellation; per-agent memory; concurrency; grouping; `documents()`.
- **jev_wiring.** Byte-exact append; reasons; too_large recomputed each run; nothing loaded means
  no Jev call; batching order; the explicit system baseline.
- **acceptance.** Construction reads no file, sends no request and reads no key, and a key is
  first read during the first run.
- **contract.** `test_public_names_are_one_object_across_every_export_path` (around :52-59) uses
  the exporter lists ENTRY_EXPORTERS (`vidbyte`, `vidbyte.agents`, `vidbyte.agents.jev`,
  `vidbyte.lib`, `vidbyte.lib.dataclasses`) and ENUM_EXPORTERS.
  - `SkillFetchStep` must stay off the root (:66).
  - `SkillResolution` validity and `transient` are checked at :113-119.
  - No test asserts that `SkillLoader` or `SkillResolution` is absent from the root (grep over
    `tests/`).
- **fetch.** `test_fetch_bounds_are_the_documented_values` pins every constant.
- **security.**
  - Each secret appears only in its own header.
  - The Vidbyte-key guard and header-unsafe credentials give AUTH_FAILED before any request,
    and the answer is remembered.
  - No redirects, no processes and no disk writes; reprs hide secrets.
- **github.** Status rows; token precedence and stripping (`GITHUB_TOKEN` read at load); the
  inclusive cap.
- **local.** The NOT_FOUND detail names the absolute path and says to create a new agent.
  PermissionError gives FETCH_FAILED, and reads happen off the event loop.
- **skills_sh.**
  - The lock hash is in the label.
  - A missing install gives NOT_INSTALLED with `npx skills add {SOURCE} --skill {NAME}` and the
    absolute path, and it is remembered (:71-88).
  - The cap is inclusive; over it gives TOO_LARGE, remembered (:91-104).
  - A read error gives FETCH_FAILED and is read again.
  - A broken lock counts as absent; a lock naming another source gives INVALID_SKILL.
  - One JevAgent run (:223-239).
- **vendor.**
  - Headers per vendor: `x-api-key`, `anthropic-version: 2023-06-01` and
    `anthropic-beta: skills-2025-10-02`, or a bearer token.
  - The latest fallback rows (:188-211).
  - The status table `VENDOR_STATUS_ROWS` (:280-297). The 429 row pins "next run" in the detail.
  - A missing key gives AUTH_FAILED with `api_key=` and the variable name, with no request,
    remembered (:319-333).
  - Key precedence and stripping; the bare SKILL.md body; the inclusive cap (:367-381).
  - The zip cases and a seeded 120-archive fuzz (:487-499).
- **`tests/test_jev_skill_preload.py`.**
  - Settings normalization and duplicates (:157-194).
  - The relevance question (:197-218).
  - Batching bounds and fail-open (:221-381).
  - Runtime ordering and bypass (:384-476).
  - It patches `_HELPER_PATH = "vidbyte.agents.jev.alignment.skills.DecisionModelHelper"`.

**Commands.**
- One file: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_contract.py`.
  Every pack module's TESTS header line gives the same form.
- The area: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload tests/test_jev_skill_preload.py`
- The unittest file alone: `python scripts/test-jev-skills-preload.py` (its TESTS line).
- Use `python -m pytest`, not bare `pytest`, with PYTHONPATH set (§4 note 20).

## 4. Notes for the spec author

### Contradictions: what the request assumes and what the code shows

1. **Where `SkillResolution` lives.** The request assumes `SkillResolution` belongs to the
   loader ("`vidbyte/agents/skills/loader.py` (`SkillLoader`, `async def load`;
   `SkillResolution`)"). The code shows it is defined at `vidbyte/lib/dataclasses/skills.py:234`
   and imported by `loader.py`. It is in that module's `__all__` only. It is not exported from
   `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/__init__.py`,
   `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py` or `vidbyte/__init__.py`.
2. **What the 1 MiB cap measures.** Consumer item 4 assumes "The SDK allows a SKILL.md of up to
   1 MiB". The code shows:
   - `SKILL_MARKDOWN_MAX_BYTES = 1_048_576` (`vidbyte/lib/constants/skills.py:30`) is inclusive
     and applies to the whole file, frontmatter included.
   - `SkillDocument.text` is the body only (`test_skill_sources_skills_sh.py:100` asserts
     `len(text.encode()) == SKILL_MARKDOWN_MAX_BYTES - len(head)`).
   - A vendor download may be up to `SKILL_DOWNLOAD_MAX_BYTES = 33_554_432` (:35) before the
     SKILL.md member inside it is capped.
   - Neither `SkillLoader.__init__` (`loader.py:34`) nor any resolver accepts a caller byte
     limit.
   - TOO_LARGE is remembered for the loader's lifetime.

   A 20,000-byte CLI budget on the appended text therefore measures something different from the
   SDK cap.
3. **Sync or async.** Consumer item 2 assumes the CLI calls the loader "from command setup
   before an agent runs". The code shows:
   - `load()` is async only (`loader.py:49`), with no sync twin.
   - The repo's sync-twin pattern raises inside a running event loop:
     `TextModelRunner.run` (`vidbyte/lib/runners/text.py:93-100`) raises `AgentExecutionError`,
     and `BaseAgent.run` (`vidbyte/agents/base.py:1053-1060`) does the same.

   Whether the CLI's setup runs inside a loop is unverified (CLI code-map: "Codex agents run in
   `asyncio`").
4. **Who reads credentials.** Consumer item 3 assumes the CLI decides whether `GITHUB_TOKEN` is
   read. The code shows the loader itself reads the environment, at load time:
   - **GitHub:** `entry.token if entry.token is not None else os.environ.get(GITHUB_CREDENTIAL_ENV_VAR)`
     at `vidbyte/agents/skills/github.py:141`. The value is stripped, and blank means None.
   - **Anthropic and OpenAI:** `ProviderModelRegistry.resolve_api_key(self.PROVIDER, entry.api_key)`
     at `vidbyte/agents/skills/vendor.py:121`.

   Credentials can be passed only per entry (`token=`, `api_key=`); there is no loader-level
   credential parameter.
   - A missing vendor key gives AUTH_FAILED: "No API key for {host}: pass api_key= on the entry
     or set {env_var}." (`vendor.py:123`).
   - A key starting with `VIDBYTE_API_KEY_PREFIX`, or one that is not printable ASCII, gives
     AUTH_FAILED with no request.
   - `vidbyte/agents/skills/README.md:46` warns that apps building entries from untrusted input
     must pass explicit credentials or unset the variables.
5. **Unavailability versus crashes.** The request assumes unavailability is "never [reported
   as] an exception that aborts the other entries". The code shows:
   - Expected failures are data.
   - `load()` re-raises any BaseException from a resolver group (`loader.py:61-66`), so a
     programming error or a cancellation aborts the whole load, and nothing from that load is
     remembered. The README contract bullet "Fail open, with reasons" says this is intended.
   - Invalid entries raise `ConfigurationError` when the entry is constructed (validation in
     `__post_init__`), before any loader exists.
6. **Validation of the entry tuple.** The request treats `SkillLoader` as ready to expose. The
   code shows `SkillLoader.__init__` (`loader.py:34-47`) does not check element types, duplicate
   names, or that it got a tuple. That validation exists only in
   `JevAlignmentSettings._normalized_skills` (`vidbyte/agents/jev/settings.py`, around :83-122),
   which also turns bare strings into `inline_skill_{index}` documents. Memory is keyed by entry
   equality, so two equal entries share one result. Secrets take part in equality and hashing.
7. **The "only consumer" wording.** The request describes JevAgent as the only consumer, which
   matches, but these texts would go stale once a public door exists:
   - `REPO_MAP.md:107-109` ("today JevAgent's skill preload is its only consumer");
   - `vidbyte/agents/README.md:297`;
   - `vidbyte/agents/skills/README.md:3`;
   - the `loader.py` header ROLE IN CODEBASE ("Built once per agent by JevSkillsPreload");
   - the `vidbyte/lib/enums/skills.py:9` note that `DECISION_FAILED` and the batching
     `TOO_LARGE` are set only by the Jev preload.
8. **Agent-centric detail strings that tests pin.**
   - `vidbyte/agents/skills/local.py:59` ends "This agent remembers the miss, so create a new
     agent after fixing it."
   - "retried on the next run" appears in `fetch.py:86,89,97`, `github.py:78,80` and
     `vendor.py:170,172`. "it is read again on the next run" appears in `local.py:57` and
     `skills_sh.py:52`.
   - The tests pin "next run" (`test_skill_sources_vendor.py:287`) and the local NOT_FOUND
     wording (`test_skill_sources_local.py`).

   For a one-shot caller, "run" means the next `load()` on the same loader. Rewording breaks
   those tests.
9. **The import-order hazard.** The request hint ("reportedly forbids `from vidbyte.agents import
   …`") is confirmed at `vidbyte/agents/skills/README.md:44`. The import chain is:
   - `vidbyte/__init__.py:42`
   - → `vidbyte/agents/__init__.py:84`
   - → `vidbyte/agents/jev/__init__.py:12`
   - → `vidbyte/agents/jev/agent.py:19`
   - → `vidbyte/agents/jev/alignment/skills.py:37`
   - → `vidbyte.agents.skills.loader`.

   So the loader is fully imported while `vidbyte.agents` is still initializing. Inferred, not
   executed: a root import of `vidbyte.agents.skills.<module>` placed after :42 finds the module
   already in `sys.modules`. The hazard applies only to imports written inside
   `vidbyte/agents/skills/*`.
10. **What makes the generator refuse.** The request assumes the generator "refuses to write
    while `vidbyte/__init__.py` or `pyproject.toml` have uncommitted changes". The code shows:
    - It refuses on any dirty path in `derived.read_paths` (`scripts/generate-sdk-public-api.py:70,118-120`).
    - That set is `pyproject.toml` plus every module `AllResolver` read
      (`lint/core/public_api_contract.py:430`).
    - It is unverified whether that is exactly those two files. The root `__all__` is a literal
      list, so it probably is.
    - When the data is unchanged, it keeps `source.commit` and only restores formatting.
11. **The stamped commit.** The request implies the contract reflects `179d8adc`. The code shows
    `contracts/sdk-public-api.json` records `source.commit` `2bb5a8e9...`, a merge commit on the
    #904 branch. C016 does not compare the commit; regenerating stamps this PR's commit.
12. **Rule-ID collision.** Consumer item 6 cites "C028 and C011". Those are vidbyte-cli rules. In
    this repo C011 is the sync-twin rule (§1), which is unrelated.

### Gaps (no design)

13. **Export depth.** README "Adding a source" step 5 routes new entry classes through five
    `__init__` files. No rule says whether a loader-facing name must be exported below the root.
    - S015 requires only that root imports are in `__all__`.
    - The contract test's ENTRY_EXPORTERS lists the five paths for entries only.
    - `vidbyte/agents/skills/__init__.py` forbids exports there.
14. **The root file is already oversized.** `vidbyte/__init__.py` is 1,366 lines, over AGENTS.md's
    "well below 1,000". This is existing debt, and no lint rule measures it. `__all__` is
    unsorted, and there is no lazy export.
15. **Memory semantics.** Memory is per `SkillLoader` instance and never module-level
    (`loader.py` header WHAT NOT TO DO 4). Transient reasons (`SKILL_TRANSIENT_REASONS`, :49) are
    retried on the next `load()`. A fresh loader per CLI invocation re-reads everything. A blocked
    host costs up to `SKILL_FETCH_DEADLINE_SECONDS` (25.0) per step.
16. **No source-string parser exists.** A grep for `def parse|from_string|from_source` over
    `vidbyte/agents/skills/` and `vidbyte/lib/dataclasses/skills.py` finds only
    `SkillMarkdown.parse` (`markdown.py:27`), which parses SKILL.md bytes. The request's default
    is not built.
17. **Relevance selection is Jev-only.** It lives in `JevSkillsPreload` (DecisionModelHelper,
    `_build_batches`, the threshold). The loader has no decision step.
18. **The last bump also added a design doc.** Commit `29fbfd28` also changed
    `docs/design/release-0-2-1.md` (+9 lines), which was not read because of the `docs/` rule.
    Whether this PR adds a 0.2.2 counterpart is open; the request lists only the literal files.
19. **`SkillFetchStep` stays internal** (`test_skill_sources_contract.py:66`). It appears only
    inside detail strings.
20. **Which checkout is imported.**
    - From the worktree root, `python -c "import vidbyte; print(vidbyte.__file__)"` printed
      `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-public-skill-loader\vidbyte\__init__.py`,
      so the working directory beats the editable install.
    - The field guide still prescribes `PYTHONPATH=$(pwd)` because the editable install points
      at the canonical checkout.
    - Inferred, not run: `run_ci.py` calls `sys.executable -m pytest` with cwd at the repo root,
      so it also picks up the worktree.
    - Unverified: which checkout the editable install currently points to. Running
      `pip install -e` from this worktree would repoint the shared install away from the user's
      checkout.

### Where the CLI's assumptions differ from the SDK code

Sources: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/`
`reports/S1-spec-author.md` (read in full) and `context/code-map.md` (lines 140-199 and 355-429).

21. **Tagging.** The CLI S1 report §3 option 1 says the SDK PR should "Bump `version` to 0.2.2,
    regenerate `contracts/sdk-public-api.json`, and tag the release". This request puts tagging
    and publishing out of scope and keeps the PR a draft.
22. **How the token is read.** The CLI code-map (:410-411) says the SDK reads
    `os.environ["GITHUB_TOKEN"]`. The code uses `os.environ.get(...)` (`github.py:141`), so an
    unset variable means an anonymous request, not a KeyError.
23. **"Internal" per the SDK spec.** The CLI code-map (:370) cites "SDK spec §8.5 calls the
    package internal". This is unverified here: `docs/spec/jev-skill-sources/` may not be read.
24. **Which shape the CLI expects.** CLI S1 §2 assumes the shape is "root-export `SkillLoader`
    and `SkillResolution`, or one small facade". Code facts that matter for either:
    - `SkillLoader.load()` is async and returns `tuple[SkillResolution, ...]` in input order.
    - `documents()` returns `tuple[SkillDocument | None, ...]`.
    - Neither is in `vidbyte.__all__`.
25. **Sync use from inside an event loop.** The CLI code-map (:420-421) leaves as unverified
    whether an `asyncio` loader call fits each agent's event loop. See note 3.
26. **Where the 20,000-byte budget is enforced.** The CLI's budget
    (`InstructionsLimit.MAX_TOTAL_BYTES`) is CLI-side. The SDK has no matching bound, and no way
    to pass one (note 2).
27. **Contract provenance.** CLI S1 §6 notes the contract provenance `2bb5a8e9`, which matches
    note 11.
