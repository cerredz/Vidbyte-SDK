# Code map: jev-skill-sources

Base: `ba3e4ca5` on `feat/jev-skill-sources`. All paths are relative to the
worktree root unless absolute. Line numbers are from the files as read at
this base.

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### AGENTS.md (81 lines; `CLAUDE.md` is just `@AGENTS.md`)

- **REPO_MAP first** (AGENTS.md:9). Read `REPO_MAP.md` before you create a
  file, move code, or search. Put new code where the map says that kind of
  code belongs. The map is lossy. If an entry is wrong, regenerate it from
  the tree rather than patching around it.
- **Folder READMEs** (AGENTS.md:11). Read each folder's `README.md` to the
  end, including `## Notes for agents` where it exists. Lint A009 caps every
  folder README at 40,000 characters.
- **docs/ is opaque** (AGENTS.md:13). Do not grep, glob, or read under
  `docs/` unless a human names a document.
- **Full gate before "complete"** (AGENTS.md:13): `python scripts/run_ci.py`.
  No narrower script substitutes for it.
- **Principle 1: one level of calls** (AGENTS.md:21-23). The main function
  calls a flat list of helpers, and helpers do not call further own-helpers.
  No nested functions unless an API requires a callback or decorator.
- **Principle 2: narration** (AGENTS.md:25-27). Main functions carry
  plain-English step comments. Update them in the same edit as the steps.
- **Principle 3: layers** (AGENTS.md:29-31).
  - `vidbyte/lib/` is the bottom layer and never imports upward. There are no
    cycles.
  - Use small single-purpose classes, and keep files "well below 1,000
    lines".
  - If describing a class needs "and", it is probably two classes.
- **Principle 4: validated records** (AGENTS.md:33-35).
  - Core-logic functions take and return dataclasses.
  - Records are `@dataclass(frozen=True, slots=True)`, validated in
    `__post_init__` with an error naming the field and the value.
  - Closed sets are enums.
- **Principle 5: canonical helpers in lib** (AGENTS.md:37-41).
  - HTTP goes through `HttpTransport` in `vidbyte/lib/http/transport.py`.
  - If a lib helper is close but lacks an option, add the option to it
    rather than copying it.
  - A new shared helper goes in `vidbyte/lib/<domain>/`.
- **Placement: dataclasses** (AGENTS.md:45-57).
  - Every new dataclass, public or underscore-private, goes in
    `vidbyte/lib/dataclasses/<domain>.py`.
  - Add to the existing domain module when one exists.
  - Never create `types.py`, `records.py`, `models.py`, or `schemas.py`.
  - A feature package may re-export a dataclass, but the definition stays in
    lib.
  - Behavior that acts on a record lives in the owning layer.
  - Exceptions: `*Settings` classes (in `vidbyte/agents/settings/` or the
    agent's own `settings.py`) and `JevPreflightQuestion` subclasses.
- **Placement: enums** (AGENTS.md:59-63).
  - Every new enum goes in `vidbyte/lib/enums/<domain>.py`. Every public
    enum is added to `vidbyte/lib/enums/__init__.py`. No exceptions.
  - Closed-set fields and parameters are typed with an enum, not `str`.
- **New JEV code** (AGENTS.md:65-77).
  - JEV records go in `vidbyte/lib/dataclasses/jev.py`, enums or members in
    `vidbyte/lib/enums/jev.py`, and constants in
    `vidbyte/lib/constants/jev.py`.
  - Never create `types.py`, `enums.py`, or `constants.py` under
    `vidbyte/agents/jev/` or `vidbyte/lib/jev/`.
  - AGENTS.md:76: "A new JevAgent capability is a named, validated field on
    `JevAgentSettings`. Its questions and actions stay inside
    `vidbyte/agents/jev/` and `vidbyte/lib/jev/`." See §4 N1.
- **Existing code** (AGENTS.md:79-81). Modules on main that break these rules
  are not precedent. Editing one in place is fine.
- AGENTS.md has no install command and no commit or PR conventions.

### Commands (all opened in this session)

**Full gate**

- `python scripts/run_ci.py`. Stages are `--stage source` and
  `--stage package` (scripts/run_ci.py).
- The source stage runs, in order:
  1. a check that no bytecode is tracked
  2. `lint/run.py`
  3. `compileall vidbyte`
  4. `scripts/check_context_write_paths.py`
  5. `scripts/check_context_primitive_introductions.py`
  6. `scripts/check_reasoning_trace_contracts.py`
  7. `python -m pytest`
- The package stage builds, runs `twine check`, inspects the wheel, installs
  into a clean venv, and smoke-tests with `PYTHONPATH` popped.
- run_ci.py does **not** run semgrep.

**Worktree gate** (field guide `local-ci-verification.md`)

- Run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.
- Then run `python scripts/run_ci.py --stage package` with no `PYTHONPATH`.
- Check that the import resolves to the worktree:
  `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"`
  must print the worktree path.
- `lint/README.md` gives the PowerShell form:
  `$env:PYTHONPATH=(Get-Location).Path; python scripts/run_ci.py --stage source`.

**Lint**

- `python lint/run.py`. Options: `--rule <ID>`, `--all`, `--format json`.
  Use `--update-baseline` only after a genuine improvement, and never raise a
  baseline count.
- Discovery is `git ls-files -z` (lint/core/discovery.py). New files are
  invisible to lint until they are `git add`-ed.

**Ruff import sort (S051)**

- Run `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`
  over the whole tree, then filter to your paths (field guide).

**Semgrep** (not in run_ci; `.github/workflows/static-policy.yml`, dispatch-only)

- Install with `pip install semgrep==1.170.1`. Per user memory it needs its
  own venv or pipx, because the SDK pulls mcp 2.x.
- Rule test:
  `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
- Scan:
  `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
- Run `git add -A` first. Semgrep scans tracked files only.
- The rule `no-untyped-mapping-fallback` covers `vidbyte/**/*.py`, excluding
  `lib/http`, `providers`, `mcp_server`, and `tools/mcp`. It flags
  `def f(..., v: object|Any): if not isinstance(v, Mapping|dict): return ...`.

**Public API contract**

- Commit the `vidbyte/__init__.py` change first, then run
  `python scripts/generate-sdk-public-api.py`. The generator refuses to run
  while `vidbyte/__init__.py` or `pyproject.toml` is dirty.
- Check with `python scripts/generate-sdk-public-api.py --check`.
- Lint C016 baseline is 0.
- contracts/README.md: "When an export is removed or renamed, tell the
  vidbyte-cli owners so they refresh their copy."

**CI**

- `.github/workflows/ci.yml` triggers only on `workflow_dispatch` and
  `workflow_call` ("TEMPORARILY DISABLED").
- It runs `pip install -e ".[dev]"` and `--stage source` on 3.11 and 3.12,
  then the package stage.
- `static-policy.yml` and `agents-md-placement.yml` are also dispatch-only.

**Unverified:** that the mypy S009 count differs on Windows. Not run.
Baseline S009=350.

### Lint rules that bite this change (lint/rules, lint/baseline.json)

| Rule | What it enforces here | Baseline |
|---|---|---|
| A001 | Header fields on every tracked `.py` file, including tests and scripts: PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS | 643 |
| A002 | `# @intent <name>` within lineno-4..+20 of a function whose name or body hits a policy token (retry, backoff, attempt, permission, authorize, secret, fallback, transport, request, fetch, send, provider, subprocess, persist, ...) | 703 |
| A003 | A new `*Error` in `vidbyte/lib/errors/` needs the full `DIAGNOSTIC_FIELDS` packet | 36 |
| A005 | Params named transport, client, fetcher, runner, store, or tracer must not be annotated `object` or `Any` | 33 |
| A006 | Lower prefixes (`vidbyte.lib`, providers, sessions, sources) must not import orchestration (`vidbyte.agents`, context, middleware, tools, pipelines, workflows, harnesses, trace, evals, paradigms) or application (client, config, cli, mcp_server). Cycles also count. Function-local imports count; only `TYPE_CHECKING` edges are skipped; `__init__.py` files are excluded from the graph | 34 |
| A007 | Operational literals (timeout, retry, attempt, backoff, byte, char, limit, status, ...) must be named UPPERCASE constants. A `read(CAP + 1)` probe is flagged; the os.fstat pattern is in `vidbyte/agents/coding_context/root_file.py` `_read_capped` | 255 |
| A009 | Folder README at most 40,000 characters | 0 |
| C002 | No duplicated bool guard by field name; derive status flags | 9 |
| C008 | Primitive validators (timeout, limit, positive int, finite, bool, temperature) only in the canonical module | 45 |
| C013 | Jev only via `DecisionModelHelper` | 9 |
| C015 | Package data: READMEs must not ship | 3 |
| C016 | `contracts/sdk-public-api.json` equals the generator output | 0 |
| S011 | No raw httpx or `urllib.request` outside transport.py | 0 |
| S012 | Every `.request(` call passes `timeout_seconds=` or `timeout=`. A non-HTTP method named `request` is flagged too | 0 |
| S013 | `max_response_bytes` required. Scoped to `tools/` paths only | 4 |
| S015 | `__all__` integrity. Every root public import must be in `vidbyte.__all__` | 13 |
| S020 | README File Index parity, only when a README has a `## File Index` heading | 1 |
| S039 | `typing.TypedDict` banned (lint/ruff.toml TID251) | 5 |
| S045 | ASYNC109: an async function with a timeout-like parameter | 2 |
| S047 | ASYNC230: `open()` inside an async function | 0 |
| S049 | YAML unsafe load | 2 |
| S060 | No new `dict[str, Any]` signature in `vidbyte/lib/dataclasses/` | 32 |
| S061 | Non-literal positional path in `open`, `read_text`, `read_bytes`, or `extractall`. Allowlist: `lib/tools/filesystem/backends/local.py` | 6 |
| S062 | Adjacent string-literal splitting | 889 |
| S063 | `gather` results classified against `BaseException` | 4 |
| S064 | Retry loops need a deadline | 4 |
| S010 | Transport async/sync parity. Scoped to lib/runners, providers, and tools/builtins only | 5 |

### Field-guide entries that apply

All are in `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`.

- **`jev-capability-layout.md`**: the most directly relevant entry.
  - Capability logic lives in one subclass under `vidbyte/agents/jev/`, with
    question data in `vidbyte/lib/jev/`.
  - Records go in lib/dataclasses/jev.py and vocabularies in lib/enums/jev.py.
  - A Jev capability module holds no module-level constants or type aliases,
    including underscore-private ones. They go in `lib/constants/jev.py`
    with `__all__`.
  - Usage is read and summed only through `JevUsage.from_decision` and
    `JevUsage.total`.
  - JevAgent takes two settings objects: generation fields on
    `JevAgentSettings`, Jev policy on `JevRuntimeSettings`.
  - Build steps in `JevAgent.__init__` and pass them through
    `_runtime_extension_kwargs`.
  - Report outcomes via a `JevResponse` method, never via metadata.
  - "Independent skill candidates use one typed Jev request each and load
    concurrently" (`gather(return_exceptions=True)`, fail closed).
- **`blocking-lint-invariants.md`**: covers several traps.
  - A006: lib function-local imports count.
  - A003 packet for new error classes.
  - S060/S039: no `dict[str, Any]` encoder on lib records, and TypedDict is
    banned.
  - S012: never name a non-HTTP helper `request`.
  - A lib record holding a higher-layer object validates by shape.
  - C002: derive bools.
  - A007: size a capped read with `os.fstat`.
- **`local-ci-verification.md`**: covers the gate procedure.
  - Use `PYTHONPATH` for the source stage and not for the package stage.
  - Semgrep needs `git add` first.
  - Check S051 over the whole tree.
  - Stage merge resolutions before linting.
- **`comment-format.md`**: multi-line `#` comments are 72-column PEP 8
  blocks directly above the line they explain, with `# @intent <name>` on
  its own first line. This is not a lint rule.
- **`strict-config-dataclasses.md`**: covers record and settings design.
  - Settings constructors are thin adapters over one validated record.
  - Key fields are `repr=False`.
  - Avoid union fields unless structurally required.
  - A primitive validated in two places gets its own record.
  - Reusable bounds go in `vidbyte/lib/constants/`.
  - Local size caps are generous and derived from vendor constants.
- **`provider-api-contracts.md`**: covers outbound provider calls.
  - Mirror the vendor's API reference exactly.
  - Use one guarded try per provider call, with a documented status map
    (401/422/429/5xx/none) and messages that name the fix.
  - Never catch `BaseException`.
- **`class-bound-helpers.md`**: prefer a `@staticmethod` helper class over a
  bag of module-level free functions (relevant to a shared SKILL.md parser).
- **`prebuilt-agents.md`**: never add a `vidbyte-sdk` CLI command.
  `vidbyte/cli/` holds only the `skills` group.
- **`cli-backed-source-integrations.md`**: the CLI-runner pattern.
  - The request rejects running `npx` (request.md:191), so the runner part
    does not apply.
  - Its "authentication and command failures should remain failures rather
    than silently switching transports" applies to the source-failure
    classification.
- **Checked and not applicable** (one-line descriptions do not match):
  - `declarative-config-resolution.md`, except its fact that two
    `YamlLoader` classes exist (see §4 N7)
  - `diagnostic-context.md`, which applies only if a lint rule is added
  - `fallback-coordination.md`, which covers model fallback
  - `context-primitives.md`, which covers CodingAgent sections
  - `review-scope.md`

## 2. Files this change will touch

Entries marked *new* do not exist at base. "Will change" restates the
request (request.md section and line). It is not a design.

### Core preload and settings

**`vidbyte/agents/jev/alignment/skills.py`** (158 lines)

- **Today:** `JevSkillsPreload(JevPreload)`.
  - `__init__(*, skills: tuple[SkillDocument, ...], decision, threshold, response)` (:60).
  - `run(message, context)` (:68):
    1. Seeds every skill as an `UNAVAILABLE` `JevSkillResult(name, description, source, status)` (:72-75).
    2. Calls `_build_batches` (:78, :103-118). A skill whose `_build_batch((index,))` returns None joins no batch (:108-111). This is the TOO_LARGE point.
    3. Runs `asyncio.gather(... DecisionModelHelper(self.decision).arun(batch.request) ..., return_exceptions=True)` (:80).
    4. On `VidbyteSdkError` it continues, and re-raises any other `BaseException` (:85-88).
    5. Reads usage with `JevUsage.from_decision`; a `VidbyteSdkError` there also means continue (:90-93).
    6. Scores each skill with `_score_skill` (:96, :136-146).
    7. Calls `self.response.skills(JevSkillsOutcome(results=..., usage=JevUsage.total(usages)))` (:98).
    8. `_append_selected` (:149-155) appends `JEV_SKILLS_PROMPT_SECTION + "\n\n---\n\n".join(texts)`.
  - Per-candidate state records are `{"name","description","source","text"}` (:126).
  - Byte bounds use `json.dumps` with default `ensure_ascii=True` (:130-132), so non-ASCII counts as `\uXXXX`.
  - The header (:13) says "Keep source resolution outside this core contract. Future source adapters may provide resolved SkillDocument values". WHAT NOT TO DO is at :15-18.
- **Will change:**
  - Per request §C (request.md:153-154), the preload calls the internal loader before it builds batches.
  - Unresolved skills become `UNAVAILABLE` with `reason` and `detail` (request.md:156-157).
  - A skill that fits no batch gets `TOO_LARGE` (request.md:162).
  - Failed Jev batches presumably get `DECISION_FAILED` (request.md:157 lists the value; where it is set is not stated).
- **Pattern:** keep the `@intent` markers, the narrated `run`, the one-level helpers, and the gather classification against `BaseException` (S063).

**`vidbyte/agents/jev/agent.py`** (128 lines)

- **Today:**
  - Builds `self._response = JevResponse()` (:47).
  - Builds the preload at :80-89: `JevSkillsPreload(skills=settings.alignment.skills, decision=runtime_settings.decision, threshold=runtime_settings.skills_threshold, response=self._response) if settings.alignment.skills else None`.
  - `_runtime_extension_kwargs` passes `"skill_preload"` (:123-125).
  - The `response` property returns `self._response.state` (:104-107).
- **Will change:** request.md:154 says the cache lives as long as the `JevAgent`. The preload object is built once per agent here.
  - `BaseAgent._runtime()` (vidbyte/agents/base.py:1285-1289) builds the runtime class from `RuntimeRegistry` with `_runtime_extension_kwargs()`.
  - Unverified: that `_runtime()` runs once per run.

**`vidbyte/agents/jev/runtime.py`** (260 lines)

- **Today:**
  - Constructor param `skill_preload: JevPreload | None` (:53), with an isinstance check (:60-74).
  - `arun` wraps the run in `async with JevManagedRun(self.runtime_settings.decision)` and `self.usage.scope()` (:100-102).
  - `_arun_metered` calls `self.response.start(message)` (:118).
  - The gate stop comes at :120-121 and the specialist delegation at :123-124, both before `_preload_skills` (:125). Then `self.usage.require_accounted()` (:126).
  - `_preload_skills` (:190-204) honors an explicit `options["system"]` and calls `self.skill_preload.run(message, context)` (:200).
  - There is no `finally` in this file (grep).
- **Will change:** probably nothing. Resolution placed inside the preload runs here, inside the managed-run scope.
  - `JevManagedRun` (vidbyte/lib/jev/managed.py, 67 lines) only sets a TypeSafe context var.
  - `vidbyte/lib/http/` has no ContextVar.
- **Pattern:** "JevRuntime.arun names no preset" (field guide).

**`vidbyte/agents/jev/preload.py`** (35 lines)

- **Today:** `class JevPreload(ABC)` with abstract `async run(message, context) -> BaseAgentContext`.
- **Will change:** nothing stated.

**`vidbyte/agents/jev/response.py`** (153 lines)

- **Today:**
  - `start()` resets state to `JevAgentResponse(input=message)` (:51-53).
  - `skills(outcome)` sets `state.skills` (:101-105), under `@intent response-never-retains-skill-content`.
- **Will change:** nothing stated. Results carry the new `reason` and `detail`, never text.

**`vidbyte/agents/jev/settings.py`** (387 lines)

- **Today:** `JevAlignmentSettings` (:77-118) is frozen and slotted, with `skills: tuple[SkillDocument | str, ...] = ()` (:81). `_normalized_skills` (:87-117) works as follows:
  - It rejects a bare str or bytes (:93) and non-iterables (:97).
  - A string becomes `SkillDocument(name=f"inline_skill_{index}", description="Caller-supplied inline skill text.", text=..., source="inline")` (:101-106), with the index starting at 1.
  - A value that is not a `SkillDocument` raises "must contain only SkillDocument or string values." (:107-108).
  - Duplicate names raise `ConfigurationError(..., details={"names": sorted(duplicates)})` (:111-117).
  - Other relevant lines: `JevAgentSettings.api_key = field(default=None, repr=False)` (:129) is the repr=False pattern; `JevRuntimeSettings.decision` is `repr=False` (:344); `skills_threshold` (:349) and its validator (:377-385); `__all__` (:387).
- **Will change:**
  - Per request.md:149-151 and :158, `skills` takes a flat tuple of per-source entry classes plus plain strings.
  - Duplicate-name checking stays here at construction.
  - Secrets are `field(repr=False)` (request.md:164).
- **Pattern:** settings-exception placement (AGENTS.md:56).

### Records, enums, constants (placement-bound)

**`vidbyte/lib/dataclasses/skills.py`** (47 lines)

- **Today:** `SkillDocument(name, description, text, source=None)`, frozen and slotted. `__post_init__` requires non-blank name, description, and text, and a source that is None or non-blank. Text is never trimmed.
- **Will change:**
  - Becomes the internal resolved record (request.md:163).
  - This is the existing `skills` domain module for new non-JEV records; AGENTS.md:49 says add to an existing domain module.

**`vidbyte/lib/dataclasses/jev.py`** (4,673 lines; read in slices)

- **Today:**
  - `JevSkillResult(name, description, source, status, probability=None)` (:3727-3751) validates a non-blank name and description (:3742-3745) and that status is a `JevSkillStatus`. Probability goes through `JevProbability.require`.
  - `JevSkillsOutcome(results=(), usage=None)` (:3754-3767).
  - `JevSkillBatch(indices, request)` (:3770-3786).
  - `JevAgentResponse` is `@dataclass(slots=True)`, not frozen (:3837-3877). `skills` is at :3877.
  - Validation helpers: `JevValidation.error` (:129-151), `JevJson` (:153-210), `JevProbability.require` (:212-220), `JevText.require` / `require_all` (:489-504).
  - The header (:5) says it must not import model_configs (cycle). `ProviderUsage` is imported under `TYPE_CHECKING` (:97-99).
- **Will change:** `reason` and `detail` fields, and `description: str | None` (request.md:157).

**`vidbyte/lib/enums/jev.py`** (353 lines)

- **Today:** `JevSkillStatus(str, Enum)` SELECTED / SKIPPED / UNAVAILABLE (:211-216). `__all__` is at :353.
- **Will change:** the new reason enum, proposed `JevSkillUnavailableReason` with 8 members (request.md:157).
- Export it through `vidbyte/lib/enums/__init__.py`. The jev block is at :74-97 (226 lines total).

**`vidbyte/lib/enums/skills.py`** (62 lines)

- **Today:**
  - `ContextMinimalFanoutSkill(str, Enum)`.
  - `Skill: TypeAlias = ContextMinimalFanoutSkill` (:34).
  - `Skills: Final[dict]` (:36), `iter_skill_values`, `skill_from_value`.
  - It uses the old "Context Protocol Header" style.
- **Will change:** it is the existing `skills` enum domain module, a candidate home for a source-type enum (request.md:150 says read-only `type` enum field). Name collisions are covered in §4 N4.

**`vidbyte/lib/constants/jev.py`** (758 lines)

- **Today:**
  - Line 43: `JEV_DEFAULT_TIMEOUT_SECONDS=60.0`.
  - Line 44: `JEV_DEFAULT_RETRY_COUNT=2`.
  - Line 47: `JEV_RETRY_BACKOFF_SECONDS=0.5`.
  - Line 48: `JEV_MAX_RESPONSE_BYTES=16_000_000`.
  - Lines 89-105: status constants (401, 408, 429, 5xx range, 403 `VIDBYTE_STATUS_FORBIDDEN`).
  - Line 112: `JEV_NOUL_YES_THRESHOLD=0.5`.
  - Lines 455-461, skill preload constants: `JEV_SKILLS_PROMPT_SECTION`, `JEV_SKILL_INDEX_BASE=1`, `JEV_SKILLS_MAX_REQUEST_JSON_BYTES=60_000`, `JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES=30_000`.
  - `__all__` is at :740-743.
  - `vidbyte/lib/constants/__init__.py` (167 lines) does not re-export jev constants.
  - The `lib/constants/` modules are: codex, coding, cot_events, failure, jev, reasoning_strategies, runners, speed, trace. There is no `skills.py`.
- **Will change:** resolution timeouts, retries, and size caps (open question, request.md:252).

### New package (user directive)

**`vidbyte/agents/skills/`** *(new)*

- **Today:** absent.
- **Will change** (request.md:152, :159, :222-223):
  - An internal `SkillLoader` coordinator.
  - One resolver subclass per source: inline, local, skills.sh, GitHub, Anthropic, OpenAI.
  - Entries are grouped by type, resolved concurrently, and cached per entry.
  - The module layout is an open question (request.md:250).
- **Pattern:** the nearest shape is `vidbyte/agents/coding_context/`.
  - One loader class per file, each with an A001 header and a narrated main function.
  - A base class with thin subclasses: `root_file.py` `RootFileLoader` with `agents_md.py` and `map_md.py`.
  - `__init__.py` exports nothing on purpose.
  - A 42-line README with `## Notes for agents`.
- **Pattern for credentialed per-vendor HTTP clients** with an injectable `transport: HttpTransport | None = None`:
  - `vidbyte/tools/builtins/operations/clients/_base.py`: `WebOperationClient.request_json` (:71-92) has the `@intent` block, `_require_ok` (:99-102) raises `ProviderRequestError` on non-2xx, and `_decode_object` (:104-112).
  - `brave.py` is the subclass per vendor. Its `_headers()` keeps the key in the header mapping only.
  - `RetryPolicy` there (:38-45) is a dataclass defined in a tools module and predates the rules.
- Injectable transport also appears in lib/runners/decision.py (:29-36).

**`vidbyte/agents/__init__.py`** (546 lines)

- **Today:** imports every subpackage (codex, jev, ...). Line 204 imports `SkillDocument` from `vidbyte.agents.jev`. It is in `__all__` at :386.
- **Will change:** export changes (request.md:163).
- Importing `vidbyte.agents.skills` runs this `__init__` first.

### Public surface

- **`vidbyte/agents/jev/__init__.py`** (262 lines). Line 121 imports `SkillDocument` from `vidbyte.lib.dataclasses.skills`. It is in `__all__` at :254, alongside `JevSkillResult`, `JevSkillsOutcome` (:112-113) and `JevSkillStatus` (:137). The header says importing must not resolve credentials.
- **`vidbyte/__init__.py`** (1297 lines). It imports Jev names from `vidbyte.agents`: `SkillDocument` (:245), `JevSkillResult` / `JevSkillsOutcome` / `JevSkillStatus` (:214-216), and `JevAlignmentSettings` (:106). `SkillDocument` is also listed in `__all__`. S015 requires every root import to be in `__all__`.
- **`vidbyte/lib/__init__.py`** (:55, :117) and **`vidbyte/lib/dataclasses/__init__.py`** (:211, :433) both export `SkillDocument`. The latter also imports `vidbyte.context.primitives`.
- **`contracts/sdk-public-api.json`** lists `JevAlignmentSettings` (:243), `JevSkillResult` / `JevSkillStatus` / `JevSkillsOutcome` (:351-353), and `SkillDocument` (:502). `source.commit` is `f7a02bae`. Regenerate it as described in §1.

### Helpers used, not necessarily changed

**`vidbyte/lib/http/transport.py`** (211 lines; no structured header docstring)

- `HttpResponse(status_code, body, headers, raw_bytes=None, attempts=1)` (:28-34).
- `HttpTransport.request` signature (:40):

  ```
  request(*, method, url, headers, json_body=None, timeout_seconds=60.0, retry_count=0, backoff_seconds=0.5, backoff_multiplier=2.0, retry_status_codes=(408,409,425,429,500,502,503,504), max_response_bytes=None, idempotency_key=None, follow_redirects=False)
  ```

- Non-2xx is returned, not raised. After retries the final response carries `attempts`.
- `httpx.RequestError`, which includes timeouts, becomes `ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc))` with `status_code=None` (:55-56, :72-73).
- Over the size cap raises `ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=...)` (:84-89). A stream failure raises `ProviderRequestError` (:92).
- `raw_bytes` is set only on the bounded path, when `max_response_bytes` is given (:95). The unbounded path returns `body=response.text` with `raw_bytes=None` (:71).
- Headers are `dict(response.headers)`. GET is idempotent (:19). 403 is not in the default retry codes.
- `_send_once(self, client, *, method, url, headers, json_body, timeout_seconds, max_response_bytes=None)` (:59) is the test seam.
- `SyncHttpTransport` has `request`, `request_bytes` (which raises on non-2xx), `upload_multipart`, and `stream_request`.
- The package exports `HttpResponse`, `HttpResponseParser` (`parse_json_response`, `bearer_headers`), `HttpTransport`, and `SyncHttpTransport`.
- AGENTS.md:39 says to add an option here rather than copy the helper.

**`vidbyte/lib/errors/base.py`** (503 lines)

- `VidbyteSdkError(message, *, details)`, `ConfigurationError` (:235), `ProviderRequestError(message, *, provider, status_code=None, response_excerpt=None)` (:247-259), and `ProviderResponseError` (:271).
- A new class needs a distinct remediation category plus the A003 packet.

**`vidbyte/lib/registries/models.py`**: the env-key pattern.

- `API_KEY_ENV_VARS` maps OPENAI to `OPENAI_API_KEY` (:84) and ANTHROPIC to `ANTHROPIC_API_KEY` (:85).
- `DEFAULT_ENDPOINTS` has openai `https://api.openai.com/v1` and anthropic `https://api.anthropic.com/v1`.
- `resolve_api_key(provider, explicit_key)` (:162-171) tries the stripped explicit key, then the stripped env var, then raises `ConfigurationError("Missing API key for provider {p}. Pass api_key or set {env_var}.")`.
- `find_vidbyte_api_key` (:174-190) treats a `vb_live_`-prefixed value in those env vars as a Vidbyte managed key.
- Other env reads use the `x or os.environ.get(...)` form: `vidbyte/providers/tracing/langfuse.py:40-42` and `langsmith.py:38`.
- `GITHUB_TOKEN` appears nowhere in `vidbyte/`.

**YAML**

- `pyproject.toml` declares `PyYAML>=6,<7`.
- `yaml.safe_load` is used at `vidbyte/harnesses/config.py:146`.
- Two private duplicate-key loaders exist:
  - `vidbyte/config/loader.py:65` `_DuplicateKeySafeLoader`, used at :234.
  - `vidbyte/lib/config/loader.py:49-70`, used at :116. This file imports `vidbyte.agents.settings.loop` (:28-29).

**Frontmatter**

- `vidbyte/skills/catalog.py` has `_validate_frontmatter` (:223-236) and `_parse_frontmatter_fields` (:239-247). They are non-YAML on purpose ("without adding a YAML dependency").
- Safe paths: `_validate_file_list` rejects `..` and absolute paths. `_safe_materialize_target` uses `resolve()` plus `is_relative_to` (:281-287).

**Zip**

- `vidbyte/sessions/portable.py`: line 19 imports `zipfile`, and lines 105-109 use `zipfile.ZipFile(io.BytesIO(bundle))` with `zipfile.BadZipFile`.
- `vidbyte/lib/tools/filesystem/backends/local.py:76, :92`. This file is the S061 allowlist.

**`vidbyte/lib/jev/decision.py`** (64 lines)

- `DecisionModelHelper(config)`, with `async arun(request) -> DecisionModelResponse` (:31-34).
- `score_noul(answers, names, threshold, veto=None) -> JevNoulScore | None` (:36-51) and `noul_passes` (:53-62).
- Unchanged.

**`vidbyte/lib/jev/preflight/skills.py`** (142 lines)

- `JevSkillRelevanceQuestion` (:99).
- Its `_STATE` prose (:29) describes each candidate record as `name`, `description`, `source`, and `text`, with `description` "the caller's short summary".
- Unchanged unless the record shape sent to Jev changes.

### Docs and maps inside the repo

- **`REPO_MAP.md`** (398 lines).
  - The `vidbyte/agents/` subsections (:71-101) list algorithms, contracts, jev, multi, pricing, runtimes, and settings. They do not list codex, coding_context, or speed.
  - `vidbyte/skills/` (:287-289) is described as "the machinery that loads and applies a skill". The three-locations warning is at :57 and :263-265.
  - The JEV table (:359-398) has no row for `alignment/skills.py` or `preload.py`.
  - `lib/http` (:187-189) says nothing else should reach for an HTTP client.
  - No REPO_MAP generator script exists. `REPO_MAP` is referenced only in `.github/prompts/agents-md-placement.md` and `.github/workflows/claude.yml`.
- **`vidbyte/agents/jev/README.md`** (49 lines): no mention of skills or alignment, no `## File Index`, and no Notes for agents.
- **`vidbyte/agents/README.md`** (264 lines): the Key Modules list (:247-258) omits jev and coding_context.
- **`vidbyte/skills/README.md`** (83 lines): the packaged-catalog README, which documents the `vidbyte-sdk skills` CLI group.
- **`tests/features/jev_skills_preload/FEATURE.md`** (103 lines) says "network/source loaders and native provider skill references are deferred". The commands are at :96.
- **`skills/jev-agent/SKILL.md`** (185 lines): grep finds no "preload" or "SkillDocument". Line 101 says "Update this skill and the design documentation when the public philosophy or package boundary changes."
- **`pyproject.toml`**: package-data covers only prompts and the context_minimal_fanout paradigm (C015).

## 3. Tests that cover those files

### Framework

- Dev dependencies: `pytest==8.3.5` (pyproject.toml:48) and `pytest-asyncio==1.3.0` (:49).
- `[tool.pytest.ini_options]` (:78+) sets `testpaths=["tests"]`, `addopts --strict-config --strict-markers`, and `asyncio_default_fixture_loop_scope="function"`.
- `asyncio_mode` is not `auto`, so async tests need `@pytest.mark.asyncio` or `unittest.IsolatedAsyncioTestCase`.
- Test files need an A001 header too (`all_python_files()`).

### `tests/test_jev_skill_preload.py` (479 lines)

This is the only test file that references `SkillDocument`, `JevAlignmentSettings`, or `JevSkillResult` (grep over `tests/`). It uses unittest classes and runs under pytest.

**Imports**

- `from vidbyte import JevAgent, JevAgentSettings, JevRuntimeSettings` (:23).
- `from vidbyte import SkillDocument as RootSkillDocument` (:25), with `assert RootSkillDocument is SkillDocument` (:164).

**Fakes**

- `_HELPER_PATH = "vidbyte.agents.jev.alignment.skills.DecisionModelHelper"` (:56). Use it with `patch(_HELPER_PATH, new=_helper_class(scripted))`. `_helper_class` returns a class whose `__new__` returns the scripted runner and keeps `score_noul = staticmethod(DecisionModelHelper.score_noul)`.
- `ScriptedDecisionRunner(probabilities, per_call, missing, fail_calls, unreported_usage_calls)` (:59). It records requests and raises `ProviderRequestError("scripted TypeSafe failure", provider="typesafe")`.
- `CapturingGenerativeRunner` (:92) records `kwargs.get("system")`.
- `bind_test_runner(agent, runner)` from `tests/agent_test_support.py` sets `agent._runner_cache[RUNNER_TYPE_TEXT]`.
- `_preloader(skills)` builds `JevSkillsPreload(..., decision=DecisionModelConfig(api_key="test-key"), threshold=0.5, response=JevResponse())`.
- `_agent(skills, continual)` uses `JevRuntimeSettings(preflight=(), continual=...)`.

**Classes**

- `SkillDocumentSettingsTests` (:157). Tests at :160 (exact text plus public exports), :167 (`inline_skill_<n>` names), :176 (duplicates and invalid documents), and :188 (threshold).
- `SkillQuestionTests` (:197). Tests at :200 and :211; tiktoken is optional.
- `SkillsBatchTests(IsolatedAsyncioTestCase)` (:221). Tests at :224, :252, :262, :292 (oversized `"x" * 35_000` at :296), :316, :338, :344, :359, and :371.
- `SkillsRuntimeTests` (:384). Tests at :387, :406, :432 (gate stop and specialist bypass), :451, and :464.

### HTTP fake patterns (no network)

- `tests/features/coding_agent/conftest.py:76-88`: the `fake_provider_http` fixture monkeypatches `HttpTransport._send_once` with `async def fake_send(self, client, **kwargs) -> HttpResponse`. The fake receives `max_response_bytes` and must set `raw_bytes` itself when the code reads it.
- `tests/test_web_operation_client_retry.py:27-40`: patches `HttpTransport._send_once` plus `transport_module.asyncio.sleep` (no_sleep), with `@pytest.mark.asyncio`.
- `tests/test_jev_managed_gateway.py:43-59`: a `ScriptedTransport` with `async def request(self, **kwargs)` injected directly.
- `tests/test_sources_base.py:269`: `mock.patch.object(SyncHttpTransport, "request_bytes")`.
- `tests/features/coding_agent/test_coding_agent_web_fetch.py:58-74`: env vars via `monkeypatch.setenv`, with socket and subprocess blocked.

### Commands

- `python -m pytest tests/test_jev_skill_preload.py`
- `python scripts/test-jev-skills-preload.py` (54 lines): runs `tests.test_jev_skill_preload` through unittest and prints PASS/FAIL lines.
- FEATURE.md:96 lists:
  - `python scripts/test-jev-agent-scaffold.py`
  - `python scripts/test-jev-multipart-done-criteria.py`
  - `python lint/run.py`
  - `python scripts/run_ci.py --stage source`
  - `python scripts/run_ci.py`
- In a worktree, prefix the pytest and run_ci source commands with `PYTHONPATH=$(pwd)` (§1).
- `tests/features/jev_skills_preload/` holds only `FEATURE.md`; it contains no test modules.

## 4. Notes for the spec author

### Contradictions

**N1. Package location.**

- Request assumes the core logic lives in `vidbyte/agents/skills/` (request.md:152, user directive).
- AGENTS.md:76 says a new JevAgent capability's "questions and actions stay inside `vidbyte/agents/jev/` and `vidbyte/lib/jev/`".
- The field guide `jev-capability-layout.md` puts capability logic "under `vidbyte/agents/jev/`".

**N2. Where source resolution lives.**

- Request assumes `JevSkillsPreload` calls the loader before batching (request.md:153).
- The code header says "Keep source resolution outside this core contract. Future source adapters may provide resolved SkillDocument values" (`vidbyte/agents/jev/alignment/skills.py:13`).

**N3. SkillDocument leaves the public exports.**

- Request assumes `SkillDocument` leaves the public exports (request.md:163).
- The code exports it in five places plus the contract:
  - `vidbyte/__init__.py:245`
  - `vidbyte/agents/__init__.py:204`, and its `__all__` at :386
  - `vidbyte/agents/jev/__init__.py:121`, and its `__all__` at :254
  - `vidbyte/lib/__init__.py:55`, and its `__all__` at :117
  - `vidbyte/lib/dataclasses/__init__.py:211`, and its `__all__` at :433
  - `contracts/sdk-public-api.json:502`
- `tests/test_jev_skill_preload.py:25,164` asserts the root export.
- contracts/README.md requires telling the vidbyte-cli owners when an export is removed.

**N4. Name collisions** (request.md:250 leaves the base-class name open). The code already exports:

- `Skill` (TypeAlias) and `SkillEnums` from `vidbyte.lib.enums` (`vidbyte/lib/enums/__init__.py:128-129`, `__all__` :216-217)
- `Skill`, `SkillRecord`, and `Skills` from `vidbyte.skills` (`vidbyte/skills/__init__.py`)
- `Skills: Final[dict]` in `vidbyte/lib/enums/skills.py:36`

The field name `source` also clashes. `SkillsShSkill.source` is `owner/repo` (request.md:141), while `SkillDocument.source` and `JevSkillResult.source` are the display label (request.md:171).

**N5. Nullable description.**

- Request assumes `JevSkillResult.description` becomes `str | None` (request.md:157).
- The code requires a non-blank description (`vidbyte/lib/dataclasses/jev.py:3742-3745`).
- The seed result copies `skill.description` (`alignment/skills.py:73`), and `JevSkillsPreload.__init__` takes `tuple[SkillDocument, ...]` (:60), which agent.py fills from `settings.alignment.skills` (`agent.py:80-89`).

**N6. Existing frontmatter parser.**

- Request assumes a YAML frontmatter parser (request.md:161).
- `vidbyte/skills/catalog.py:223-247` deliberately parses SKILL.md frontmatter without YAML. A second parser would exist.

**N7. Which YAML loader.**

- Request cites `vidbyte/lib/config/loader.py` for the duplicate-key YAML loader (request.md:239).
- The field guide says the exported `YamlLoader` is `vidbyte/config/loader.py`, which has its own private `_DuplicateKeySafeLoader` (:65).
- `vidbyte/lib/config/loader.py` imports `vidbyte.agents.settings.loop` (:28-29). That is an upward edge from lib.

**N8. Agent skill doc.**

- Request names `skills/jev-agent/SKILL.md` as the agent skill doc (request.md:240).
- That file never mentions the preload. `vidbyte/agents/jev/README.md` doesn't either, and the REPO_MAP JEV table has no row for `alignment/` or `preload.py`.

**N9. Byte access and HTTP errors.**

- Request assumes `HttpResponse.raw_bytes` is available (request.md:237).
- It is set only when `max_response_bytes` is passed (`vidbyte/lib/http/transport.py:95` vs :71).
- Other error behavior:
  - Non-2xx is returned, not raised.
  - A connection error or timeout raises `ProviderRequestError(status_code=None)`.
  - An oversize response raises `ProviderRequestError` with the status code.
  - 403 is not retried by default.

**N10. Field guide vs code on batching.**

- The field guide says "one `JevDecisionRequest` per candidate" (`jev-capability-layout.md`, "Independent skill candidates").
- The code packs several skills per request greedily (`alignment/skills.py:103-118`).

**N11. Per-run restore.**

- Request assumes "JevRuntime restores its per-run fields in a `finally` block" (request.md:208).
- `vidbyte/agents/jev/runtime.py` contains no `finally`, and it assigns `self.user_tools` and `self.tools` at :156-158 and :177.
- Unverified: whether the runtime is rebuilt per run via `BaseAgent._runtime()` (base.py:1285).

**N12. Env-key fallbacks.**

- Request assumes the `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` env fallbacks (request.md:183, :185).
- `ProviderModelRegistry.find_vidbyte_api_key` (`vidbyte/lib/registries/models.py:174-190`) treats a `vb_live_` value in those same variables as a Vidbyte managed key.
- `vidbyte/agents/README.md` says CodingAgent keys "are never read from the environment".

### Gaps (facts, no proposals)

**G1. File size.** `vidbyte/lib/dataclasses/jev.py` is 4,673 lines, but AGENTS.md:31 says keep files "well below 1,000 lines" and AGENTS.md:69 sends new JEV records there.

**G2. No skills constants module.** There is no `vidbyte/lib/constants/skills.py`. AGENTS.md has a constants placement rule only for JEV (:69). The field-guide rule "no module-level constants" is stated for `vidbyte/agents/jev/` modules.

**G3. New files are invisible to the gates until staged.** Lint discovery (`lint/core/discovery.py`) and semgrep read only git-tracked files. A001 applies to all tracked `.py` files, including tests.

**G4. Rules scoped away from `vidbyte/agents/`.** S013 (`max_response_bytes`) covers only `tools/` paths. S010 covers only lib/runners, providers, and tools/builtins. S011 and S012 apply everywhere.

**G5. No GitHub token helper.** No helper reads `GITHUB_TOKEN`.

**G6. README requirements.**

- No rule I read requires a README per package.
- S020 parity applies only when a `## File Index` heading exists.
- C015 forbids shipping READMEs.
- A009 caps README size.
- REPO_MAP omits several existing `agents/` subpackages.

**G7. Import order.** `vidbyte/agents/__init__.py` imports every subpackage, so importing `vidbyte.agents.skills` from `vidbyte/agents/jev/` runs it first. A006 counts cycles. `vidbyte/lib/dataclasses/__init__.py` imports `vidbyte.context.primitives`.

**G8. Example the request relies on.** `tests/features/jev_skills_preload/FEATURE.md` says source loaders are deferred. The pasted docs page says "Loading skills from other sources comes later" (request.md:82). That page lives in the separate `vidbyte` repo.

**G9. ASYNC rules.** S047 (ASYNC230) flags `open()` in async functions. S045 (ASYNC109) flags async functions with a timeout-like parameter.

### Unverified

- Unverified: whether `dict(response.headers)` keys are lowercased (the request reads `x-ratelimit-remaining`).
- Unverified: whether ruff ASYNC230 or another selected rule flags `Path.read_text` in async code (lint/ruff.toml selects only TID251 directly; S047 selects ASYNC230 via the adapter).
- Unverified: every vendor behavior in request.md:174-185 (GitHub, Anthropic `latest`, OpenAI content format, skills.sh lock layout) and the measured skill sizes (request.md:206). No network was used.
- Unverified: the mypy S009 count on Windows (not run).
- Unverified: that `BaseAgent._runtime()` runs once per run.
- Unverified: that the worktree's Python resolves `vidbyte` to this worktree without `PYTHONPATH` (not run).
