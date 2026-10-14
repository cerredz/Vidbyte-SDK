Scout code map for `prebuilt-agent-tools`. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-prebuilt-agent-tools`, branch `feat/prebuilt-agent-tools`, HEAD `8387d66680951766f02b0d740d78eb6450cb6419`. Every line number below refers to that HEAD. Anything marked "unverified" was not opened or not executed. S0 ran no gate, no install, and no lint; the commands below come from reading source.

## 1. Rules, commands, and conventions that bind this change

### 1.1 AGENTS.md (binding; `CLAUDE.md` contains only `@AGENTS.md`)

- **Read the map first.** Read `REPO_MAP.md` before creating a file or moving code, and put new code where the map says that kind of code belongs. The map is lossy and expected to drift. If an entry is wrong, regenerate it from the tree instead of patching around it.
- **Read folder READMEs.** Read each touched folder's `README.md` to the end, including `## Notes for agents` where it exists. `vidbyte/tools/README.md` (6,343 chars) has no such section, no `## File Index`, and a `## Key Modules` list at line 80. `vidbyte/tools/builtins/` and `vidbyte/tools/toolsets/` have no README.
- **README size (A009).** A folder README may hold at most 40,000 chars. The root `README.md` is exempt. Two legacy ceilings apply: `vidbyte/agents/codex/README.md` at 65,000 and `vidbyte/providers/README.md` at 55,000.
- **`docs/` is opaque.** Do not grep, glob, or read under `docs/` unless a human names a specific document.
- **Full gate.** Before a change counts as complete, run `python scripts/run_ci.py`. No narrow script beside it substitutes for it.
- **Style principles:**
  1. Call chains stay one level deep: a main function calls a flat list of helpers. Nested functions are allowed only when an API needs a callback or decorator.
  2. Main functions carry plain-English narration comments throughout the body.
  3. Build in layers of small single-purpose classes. `vidbyte/lib/` is the bottom layer and never imports `tools/`, `agents/`, or anything else above it. Keep files "well below 1,000 lines" and split along subsystem lines before they head toward four digits. If a description needs "and", the thing is probably two things.
  4. Core inputs and outputs are `@dataclass(frozen=True, slots=True)` records validated in `__post_init__`. Closed-set fields are enums.
  5. Shared logic lives once, as a canonical helper in `vidbyte/lib/`. Look there before writing a new one.
- **Placement rules** (prescriptive; enforced on every PR by the "AGENTS.md placement" workflow, whose workflow file is unverified):
  - Every new dataclass, public or private, goes in `vidbyte/lib/dataclasses/<domain>.py`. Never create `types.py`, `records.py`, `models.py`, or `schemas.py` beside code.
  - Every new enum goes in `vidbyte/lib/enums/<domain>.py`, and every public enum is added to `__all__` in `vidbyte/lib/enums/__init__.py`. No exceptions.
  - Any field, parameter, or registry key drawn from a small closed set is typed with an enum.
  - Existing misplaced code is not precedent. Two examples that predate the rule:
    - `ReasoningTraceDefinition`, a dataclass defined in `vidbyte/tools/builtins/reasoning/_base.py`.
    - `ToolStatus` and `ToolPermission`, enums defined inside `vidbyte/lib/dataclasses/tools.py`.
- **No PR or commit conventions.** AGENTS.md states none.

### 1.2 Lint rules that new tool modules and tests will hit (`python lint/run.py`)

Baselines are in `lint/baseline.json`. A new violation fails the gate. Do not raise a baseline and do not add a suppression. Source discovery uses `git ls-files`, so new files are linted only once they are tracked.

| Rule | What it requires | Scope | Baseline | Source |
|---|---|---|---|---|
| A001 | A module docstring with non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, `TESTS:` | Every tracked `.py`, tests included | 643 | `lint/rules/a001_agent_readable_file_headers.py:24-31` |
| A002 | `# @intent <name>` within 3 lines before or 20 lines after a def whose name tokens include retry, backoff, attempt, permission, authorize, pricing, price, billing, redact, secret, persist, persistence, checkpoint, fallback, transition, transport, request, fetch, send, urlopen, provider, subprocess, or mcp | `vidbyte/` | 703 | `lint/rules/a002_intent_comments.py` |
| A003 | A new `*Error` class carries all 8 `DIAGNOSTIC_FIELDS` | `vidbyte/lib/errors/` | 36 | `lint/rules/a003_context_rich_error_packets.py` |
| A006 | No import cycles. lib, providers, sessions, and sources must not import `vidbyte.tools` or other higher layers. `__init__.py` files and TYPE_CHECKING edges are excluded | `vidbyte/` | 34 | `lint/rules/a006_directed_dependency_graph.py` |
| A007 | Numeric literals must be UPPERCASE named constants when they sit near names containing timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth, or interval; when passed to sleep, urlopen, send, request, read, or read_bytes; or when used as operational defaults | `vidbyte/` | 255 | `lint/rules/a007_operational_constants.py` |
| A009 | README size (see 1.1) | READMEs | 0 | `lint/rules/a009_readme_size_limit.py` |
| S008 | Function complexity: Ruff C901 10, PLR0912 12 branches, PLR0915 50 statements | `vidbyte/` | 19 | `lint/rules/s008_bounded_function_complexity.py` |
| S015 | `__all__` is unique and bound, and root imports are listed | packages | 13 | `lint/rules/s015_public_export_integrity.py` |
| S016 | No `raise Exception/RuntimeError/TypeError/ValueError`; raise `vidbyte.lib.errors` types instead | `vidbyte/tools/builtins/`, providers, `tools/mcp`, `lib/runners`, cli | 50 | `lint/rules/s016_typed_boundary_errors.py` |
| S017 | Inside an `except`, no `str(exc)`, `repr(exc)`, or f-string `{exc}` that is passed to `.error(...)`, `*Error(...)`, or `_failed_result`, returned, or assigned to `.error`/`.message` | all of `vidbyte/tools/`, providers, mcp_server, `lib/runners` | 79 | `lint/rules/s017_no_raw_exception_disclosure.py` |
| S020 | A README with a `## File Index` heading lists every direct tracked child | READMEs | 1 | `lint/rules/s020_readme_file_index_parity.py` |
| S021 | No public module-level functions | `vidbyte/lib/registries/` | 0 | (read in full) |
| S024 | Control-flow nesting of 3 or less | `vidbyte/` | 25 | `lint/rules/s024_maximum_control_flow_nesting.py` |
| S025 | Every statically resolvable `ToolSpec(description=...)` and `ToolParameter(description=...)` in a `BaseTool` subclass with its own `spec()` has 4 or more sentences | `vidbyte/` | 263 | `lint/rules/s025_model_facing_description_depth.py` |
| S051 | Ruff I001 import sort plus UP typing modernization | `vidbyte/` | 259 | `lint/rules/s051_modernized_import_and_syntax_hygiene.py` |
| S060 | No `dict[str, Any]` in public seams, including `vidbyte/lib/dataclasses/` | `vidbyte/` | 32 | `lint/rules/s060_typed_public_seam_mappings.py` (header only) |
| S062 | No implicit adjacent string-literal concatenation | every tracked `.py` | 889 | `lint/rules/s062_no_implicit_string_concatenation.py` |
| C006 | Validator-named functions (`_?(validate\|validated\|require\|ensure\|normalize\|coerce\|check)`) and `__init__`/`__post_init__` with numeric range guards must reject True, NaN, and ±inf | `vidbyte/` | 104 | `lint/rules/c006_finite_numeric_guards.py` (head) |
| C008 | Primitive validators (positive int, finite number, strict bool, timeout, limit, temperature) must come from the shared module; tool-call argument normalizers are exempt | `vidbyte/` | 45 | header only; shared-module path unverified |
| C015 | Non-Python files under `vidbyte/` ship via `[tool.setuptools.package-data]`; README.md must not ship | `vidbyte/` | 3 | `lint/rules/c015_package_data_coverage.py` (header) |
| C016 | `contracts/sdk-public-api.json` equals the generator output for `vidbyte.__all__` | root API | 0 | `lint/rules/c016_public_api_contract_current.py` (header) |
| S007 | Public function annotations (Ruff ANN) | `vidbyte/` | 16 | header only |
| S042 | Ruff TRY002 | `vidbyte/` | 0 | header only |
| S012 | A method named `request` counts as an outbound call | `vidbyte/` | 0 | field guide `blocking-lint-invariants.md` |

S025 resolution details (from the rule source):
- It follows module constants, imports up to 3 hops, f-strings, `+`, and `self.attr` assigned in `__init__`.
- Descriptions built by a method call, or from attributes it cannot resolve, are exempt.
- `@tool`/`FunctionTool` functions are not scanned.
- Abbreviations such as e.g., i.e., etc., vs., and approx. do not end a sentence.

Ruff settings:
- Selectors are fixed in `lint/core/ruff.py` and scan only `vidbyte` plus `pyproject.toml`.
- `lint/ruff.toml` bans `typing.TypedDict`, `typing.assert_never`, and `asyncio.Lock`.

### 1.3 Gate and commands (read from source; none executed by S0)

- **Install once:** `python -m pip install -e ".[dev]"` (from `.github/workflows/ci.yml`).
- **Full gate:** `python scripts/run_ci.py`. Stages: `--stage source`, `--stage package --dist-dir dist`, or `--stage all`.
- **Source stage, in order** (`scripts/run_ci.py`):
  1. Assert no tracked bytecode.
  2. `python lint/run.py`
  3. `compileall -q vidbyte`
  4. `scripts/check_context_write_paths.py`
  5. `scripts/check_context_primitive_introductions.py`
  6. `scripts/check_reasoning_trace_contracts.py`
  7. `python -m pytest`
- **Package stage:**
  1. `python -m build`, then `twine check`.
  2. Wheel inspection: requires `vidbyte/prompts/prompts/error_correction_auditor.md` and no bytecode.
  3. Clean venv install, `pip check`, smoke import.
- **From a worktree** (field guide `local-ci-verification.md`):
  1. `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
  2. `python scripts/run_ci.py --stage package` without PYTHONPATH.
  3. Sanity check: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"`.
- **Lint:**
  - `python lint/run.py`, or narrowed to one rule with `python lint/run.py --rule S025`, with `--format json` for machine output.
  - Never `--update-baseline`.
- **Import sort:** `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`.
- **Public API contract**, after any change to `vidbyte.__all__`:
  - Regenerate with `python scripts/generate-sdk-public-api.py`.
  - Check with `python scripts/generate-sdk-public-api.py --check`.
- **Semgrep is not part of `run_ci.py`.** It runs in `.github/workflows/static-policy.yml:24-30`:
  - `python -m pip install semgrep==1.170.1`
  - `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
  - `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
  - Rule `no-untyped-mapping-fallback`: a function with an `object`/`Any` parameter that does `if not isinstance(x, Mapping/dict): return ...` is flagged.
  - Excluded paths: `vidbyte/lib/http`, providers, `mcp_server`, `tools/mcp`. Tools under `vidbyte/tools/builtins/` are not excluded.
  - It scans only git-tracked files.
- **CI workflow** (`.github/workflows/ci.yml`): runs the source stage on Python 3.11 and 3.12, then the package stage. Triggers are currently `workflow_dispatch` only.

### 1.4 Field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)

| Entry | Trigger | Quick check | Path |
|---|---|---|---|
| Model-facing tool contracts | Adding or changing any builtin tool's spec, parameters, or events | Tool and every parameter have a consistent 4–5 sentence general description with no concrete examples. Categorical vocabularies are `str, Enum` in `vidbyte/lib/enums`, not tuples in constants. Field-name lists go in `vidbyte/lib/constants`. Customization stays bound to the existing schema | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/model-facing-tool-contracts.md` |
| Prebuilt agents | Shipping a preloaded tool bundle | Bundle is `<Name>Tools(Tools)` in `vidbyte/tools/toolsets/<name>.py` with static `authenticate_tools`/`get_tools`. No `vidbyte-sdk` CLI command; `vidbyte/cli/` holds only skills | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/prebuilt-agents.md` |
| Strict config dataclasses | Any bound, cap, or settings value validated in more than one place | Becomes a frozen lib dataclass (precedent `PauseDuration`). Bounds are named constants in `vidbyte/lib/constants/`. Caps are generous. No union fields | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/strict-config-dataclasses.md` |
| Blocking lint invariants | New error class, new lib record, new import edge, method named `request`, or `read(N)` | A003 full packet. No A006 cycles. S060 and the TypedDict ban. S012 naming. A007: use `os.fstat`, not `read(CAP+1)`. A lib record that holds a higher-layer object checks its shape under TYPE_CHECKING | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/blocking-lint-invariants.md` |
| Local CI verification | Before declaring done in a worktree | Use the PYTHONPATH form of the source stage, then the package stage without it. Known flaky MCP stdio test | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/local-ci-verification.md` |
| Review scope | A review says "belongs in another PR" or "overcomplicated" | Leave main's files byte-identical, or rebuild from main and minimize the diff | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/review-scope.md` |
| Comment format | Writing any multi-line `#` comment | Wrap at 72 columns, directly above the line explained, `# @intent <name>` on its own first line. Check: `awk 'length($0) > 72' <file> \| grep -E '^\s*#'` | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/comment-format.md` |
| Class-bound helpers | Writing more than one free function in a module | Prefer a static helper class over module-level free functions. One `try` in must-not-raise callbacks | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/class-bound-helpers.md` |
| Agents.md map | Adding a folder or regenerating a `REPO_MAP.md` entry | Entry is 4–5 general sentences with no file names or commands | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/agents-md-map.md` |
| Declarative config resolution | Making a tool declarable from YAML `{ref, options}` | Refs resolve through `ComponentRegistry` from public `BaseTool` subclass exports of `vidbyte.tools.builtins`. `CalculatorTool` is deliberately not declarable | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/declarative-config-resolution.md` |
| Runtime boundaries | Touching agent runtime boundaries | Read; not directly relevant to stateless tools | `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/runtime-boundaries.md` |

## 2. Files this change will touch

The spec author decides organization and tool list. The entries below are the files any shape of this change must touch, extend, or respect, plus the nearest precedents. "Will change" is conditional where the outcome depends on a spec decision.

### 2.1 Tool mechanism (read-only dependencies; no change expected)

#### `vidbyte/tools/base.py` (181 lines)
- **Today:**
  - `BaseTool(ABC)` with abstract `spec() -> ToolSpec` and `async execute(call: ToolCall) -> ToolResult`.
  - `name` comes from the spec.
  - `validate_call` checks required params.
  - Argument helpers: `_resolve_bool_argument` (strict bool, raises `ToolExecutionError`) and `_optional_argument` (JSON null means default).
  - Other members: `customize(description=..., parameter_descriptions=...)`, `with_activity()`, `rebind_context_manager`.
- **Change:** none expected. Every new class-based tool subclasses it.
- **Pattern:** full A001 header (FILE / PURPOSE / ROLE IN CODEBASE / ARCHITECTURE NOTE / COMMON MODIFICATION PATTERNS / KNOWN EDGE CASES / RELATED DOCS / TESTS).

#### `vidbyte/tools/function_tool.py` (249 lines, no A001 header)
- **Today:** `FunctionTool(func, *, name, description, permission=SAFE, output_schema)` builds a pydantic `{Name}Args` model from the signature (`:136-151`).
  - `*args`, `**kwargs`, and positional-only parameters raise `TypeError` (`:142-145`).
  - The description falls back to the first docstring paragraph, else "Custom function tool." (`:32`, `:192-195`).
  - Parameter descriptions come only from the pydantic schema `description` (`:117`), so a plain annotated argument gets `""`.
  - Arguments validate in JSON mode (`:180-189`).
  - Sync functions run in `asyncio.to_thread` (`:72`).
  - A raised exception becomes `ToolResult.failure(name, str(exc), metadata={"error": "execution_error", ...})` (`:76-81`).
  - Output goes through `_stringify_output` (`:206-225`): str passes through; everything else is `json.dumps(..., sort_keys=True, ensure_ascii=False)`, with dataclasses and Mappings turned into objects.
- **Change:** none expected. It is the `@tool` path, if the spec chooses it.

#### `vidbyte/tools/decorators.py` (44 lines)
- **Today:** `@tool` / `@tool(name=, description=, permission=)` returns a `FunctionTool`. `vidbyte_tool = tool`.
- **Change:** none expected.

#### `vidbyte/tools/catalog.py` (164 lines)
- **Today:** `Tools(Sequence[BaseTool])` is an agent-local collection, not a global registry.
  - It accepts tools or nested `Tools`.
  - It raises `ToolRegistrationError("Tool already exists: ...")` on a duplicate name (`:38`, `:79`).
  - Methods: `all/names/specs/describe/provider_schemas/add/extend/without/subset(names)`.
- **Change:** none expected. Any bundle of new tools is a `Tools` or a `Tools` subclass.

#### `vidbyte/lib/dataclasses/tools.py` (368 lines)
- **Today:**
  - `ToolParameter(name, type, description, required=True, default=None)` validates non-blank name and type (`:75-79`).
  - `ToolSpec(name, description, parameters=(), permission=SAFE, metadata, input_schema=None, binds_to_primitive=None, output_schema=None, activity=None)` validates only non-blank name and description (`:128-132`). There is no name regex or length cap.
  - `ToolResult(tool_name, status, output: str, metadata)` with `.success/.error/.failure`.
  - Enums `ToolStatus` and `ToolPermission` (SAFE/READ/WRITE/EXECUTE) are defined here, predating the rule.
- **Change:** possibly extended in place if a new tool-domain record is needed. A new domain module would be a sibling file.
- **Pattern:** frozen, slots, `__post_init__` validation.

#### `vidbyte/lib/tools/formatter.py` (844 lines)
- **Today:** `ToolsFormatter` renders specs for openai, anthropic, gemini, codex, and grok.
  - `_parameters_schema` (`:794`) emits only `type` and `description` per `ToolParameter`, with `additionalProperties: False` (`:809`).
  - Type aliases: bool→boolean, dict→object, float→number, int→integer, list→array, str→string.
  - An `items: {}` patch for arrays exists at `:276-281`. Whether it is applied on the `ToolParameter` path rather than only the `input_schema` path is unverified.
  - No name sanitization.
- **Change:** none expected. Relevant to how array or object parameters reach the model.

#### `vidbyte/tools/executor.py` (98 lines)
- **Today:** `ToolExecutor.execute_call` runs lookup, then permission (`PermissionPolicy`), then `validate_call`, then `execute`.
  - An uncaught exception becomes `ToolResult.error(..., f"Tool execution failed: {exc}", metadata={"error": "execution_error"})` (`:69-76`).
- **Change:** none.

#### `vidbyte/lib/registries/components.py`
- **Today:** `ComponentRegistry._discover` (`:101`) scans `vars(vidbyte.tools.builtins)` for public names that are classes and subclasses of `BaseTool` (`:113`, `:124`). This is how YAML `{ref, options}` finds tools.
- **Change:** none expected.
- **Fact:** `FunctionTool` instances are not classes, so they are never discovered. S021 forbids public module-level functions in this folder.

### 2.2 Export and attachment surfaces (change if new tools are exported or bundled)

#### `vidbyte/tools/builtins/__init__.py` (325 lines)
- **Today:**
  - Explicit imports plus `__all__`.
  - Reasoning classes are injected by a loop, `globals()[_reasoning_trace_class.__name__] = ...` (`:180`), and `__all__.extend(...)` (`:321`).
  - The header says "182 deep reasoning trace tools" (`:19`).
  - `CalculatorTool` and `DocumentRetrievalTool` are not exported.
- **Change:** would gain exports, by explicit names or an extend loop, if new tools are to be importable from `vidbyte.tools.builtins` or YAML-declarable. The header docstring also needs updating.
- **Pattern:** the reasoning loop at `:180` and `:321` is the precedent for exporting many classes without hand-listing them.

#### `vidbyte/tools/__init__.py` (82 lines)
- **Today:** exports `BaseTool`, `FunctionTool`, `Tools`, `tool`, `vidbyte_tool`, `ToolExecutor`, `ToolsFormatter`, and more. `ToolRegistry` loads lazily via `__getattr__`.
- **Change:** only if a new top-level name (for example a toolset) is exported here.

#### `vidbyte/tools/toolsets/__init__.py`, `coding.py` (138 lines), `paradigm_minimal.py` (67 lines)
- **Today:** two bundles:
  - `CodingAgentTools(Tools)` with static `authenticate_tools`/`get_tools`.
  - `ParadigmMinimalToolset(root, include_execution, include_write)` with `.tools() -> Tools` and `.all()`.
- **Change:** a new toolset module and export, if the spec bundles the tools.
- **Pattern:** `coding.py` (field guide `prebuilt-agents.md`).

#### `vidbyte/__init__.py` (1,297 lines; already over the 1,000-line guideline)
- **Today:** the root `__all__` includes some builtins and the toolsets `CodingAgentTools` and `ParadigmMinimalToolset`.
- **Change:** only if new names are exported at the root. That triggers C016, which requires regenerating `contracts/sdk-public-api.json` with `python scripts/generate-sdk-public-api.py`.

#### `contracts/sdk-public-api.json`
- **Today:** a snapshot of `vidbyte.__all__`.
- **Change:** regenerated only if the root `__all__` changes.

#### `vidbyte/agents/base.py`
- **Today:**
  - `Agent(..., tools=Tools([...]) | [tool, ...])`. Nested `Tools` inside a list are flattened (`:186`, `# @intent nested-tool-catalogs-are-flattened`).
  - `BaseAgent.add_tool(tool_or_Tools)` is at `:334`.
  - Duplicate names raise.
- **Change:** none expected. This is the attachment API new tools plug into.

### 2.3 Homes required by the placement rules (new or extended)

#### `vidbyte/lib/dataclasses/<domain>.py` (new) or `vidbyte/lib/dataclasses/tools.py` (extend)
- **Today:** no general-purpose tool-definition record exists in lib. The reasoning `ReasoningTraceDefinition` sits in the tools layer and is not precedent.
- **Change:** any new definition, input, or result dataclass goes here. Also re-export it from `vidbyte/lib/dataclasses/__init__.py` (481 lines; it re-exports `tools.py` records) if that is the local convention for the domain.
- **Pattern:** `PauseDuration` (cited by field guide `strict-config-dataclasses.md`). S060 forbids `dict[str, Any]` in these public seams.

#### `vidbyte/lib/enums/<domain>.py` (new) and `vidbyte/lib/enums/__init__.py` (235 lines)
- **Today:** there is no `vidbyte/lib/enums/tools.py` and no tool-category enum anywhere.
- **Change:** any closed set, such as tool categories or a mode argument with a fixed vocabulary, becomes an enum here and is added to the alphabetical `__all__`.
- **Pattern:** sibling-module import plus alphabetical `__all__`.

#### `vidbyte/lib/constants/<domain>.py`
- **Today:** constants per domain. `vidbyte/lib/constants/codex.py:183-185` holds `CODEX_DYNAMIC_TOOL_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"`, max length 128, and reserved name `"mcp"`.
- **Change:** input-size caps and bounds for new tools become UPPERCASE constants here (A007, `strict-config-dataclasses.md`).

#### `vidbyte/lib/errors/`
- **Today:**
  - `VidbyteSdkError(message, *, details)`.
  - `ToolExecutionError(VidbyteSdkError)` with no extra fields, in `vidbyte/lib/errors/base.py`.
  - `ReasoningTraceArgumentError` is the A003-complete shape, with `DIAGNOSTIC_FIELDS`.
- **Change:** only if a new error class is added, which then needs all 8 A003 fields. S016 means tools under `vidbyte/tools/builtins/` must raise these types, not `ValueError` and the like.

### 2.4 New tool modules (location chosen by the spec)

#### Precedent A: `vidbyte/tools/builtins/reasoning/` (220 files; 182 trace tools plus 36 named tools, `_base.py`, `_parsing.py`)
- `__init__.py` (717 lines) imports every leaf and builds `ReasoningTraceCatalog`, an immutable `MappingProxyType` mapping slug to class with `definitions()`, `tool_class()`, and `tool_classes()`. It exports `REASONING_TRACE_TOOL_CLASSES` and `REASONING_TRACE_DEFINITIONS`.
- `_base.py` (283 lines): `ReasoningTraceTool(BaseTool)` with `definition: ClassVar`, `__init__(context_manager)`, and `spec()` built from the definition. Because the description comes from a class attribute, S025 probably cannot resolve it statically (unverified). Description depth is guarded instead by `scripts/check_reasoning_trace_contracts.py`.
- A leaf such as `swot_trace.py` (55 lines) is one class holding one `definition = ReasoningTraceDefinition(...)`.
- A hand-written leaf such as `fermi_estimate.py` (211 lines) is a full `BaseTool` with 4-sentence parameter descriptions.
- **Pattern for scale:** one leaf per tool, a shared base class, and a catalog object in the package `__init__`. Do not copy the placement of `ReasoningTraceDefinition`.

#### Precedent B: `vidbyte/tools/filesystem/` (31–79 lines per file)
- `_base_tool.py` defines `FileSystemTool(BaseTool)`, configured by a lib `FileSystemToolConfig`.
- Leaves have no module header, one-sentence descriptions, and `except Exception as exc: return ToolResult.error(self.name, str(exc))`.
- The headers, description depth, and error pattern are all baseline debt (A001, S025, S017). Do not copy them.

#### Precedent C: `vidbyte/tools/builtins/calculator.py` (95 lines) and `code_execution.py` (166 lines)
- `CalculatorTool` (name `calculator`) evaluates through `CalculatorExpression(SafePrintExpression)`, an AST walk bounded by `MAX_PRINT_EXPONENT=128` and `MAX_PRINT_INT_BITS=4096` from `code_execution.py`.
- It returns `ToolResult.error` with `f"Evaluation failed: {exc}"`, which is S017 debt.
- **Pattern:** reuse the safe-expression evaluator if any new tool evaluates arithmetic.

#### Precedent D: `vidbyte/tools/builtins/pause.py` (180 lines)
- Full A001 header, a `_TOOL_NAME` constant (`:88`), and an explicit `input_schema` with min/max.
- Validation is delegated to the lib dataclass `PauseDuration`.
- Its header notes that there is no feature-specific test file.
- **Pattern:** a single fully compliant class-based builtin.

### 2.5 Maps and READMEs

#### `vidbyte/tools/README.md` (6,343 chars)
- **Today:** says "`vidbyte.tools.builtins.reasoning` exposes 182 strategy-specific tools" (`:44`). `## Key Modules` (`:80`) lists the `builtins/` contents (`:89`).
- **Change:** describe the new tools and their folder. Stay under 40,000 chars.

#### `REPO_MAP.md` (62,470 chars)
- **Today:** the `vidbyte/tools/toolsets/` entry (`:335-337`) says it "currently holds one such bundle", which is stale: there are two. No entry exists for any `builtins/` subfolder.
- **Change:** possibly a new folder entry and a regenerated toolsets entry, each 4–5 general sentences with no file names (field guide `agents-md-map.md`).

#### New folder README (if a new folder is created)
- If it has a `## File Index`, S020 requires every direct tracked child to be listed. It must stay at 40,000 chars or less. C015 forbids shipping README.md as package data.

#### `llms.txt` (83,907 chars) and `artifacts/file_index.md` (33,408 chars)
- AGENTS.md names these as deeper indexes. Whether they must be updated or regenerated is unverified: their generators were not opened.

### 2.6 CI scripts (only if the spec adds a count or contract guard)

#### `scripts/check_reasoning_trace_contracts.py` (79 lines)
- **Today:** hard-codes `len(definitions) != 182 or len(REASONING_TRACE_TOOL_CLASSES) != 182` (`:39`), 6–8 sentence descriptions, no example markers, and at least 12 shapes.
- **Change:** none, unless the reasoning catalog is touched. It is the precedent for a count-guarding script.

#### `scripts/run_ci.py` (287 lines)
- **Today:** the source stage runs the three `check_*.py` scripts by explicit path.
- **Change:** a new contract script would be added to that list.

### 2.7 `pyproject.toml`

- **Today:**
  - `requires-python >=3.11`. Dependencies: `pydantic>=2,<3`, `httpx>=0.27`, `PyYAML>=6,<7`.
  - The `dev` extra pins pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1, build 1.5.0, and twine 6.2.0.
  - `[tool.setuptools.packages.find] include=["vidbyte*"]` picks up new subpackages automatically.
  - package-data covers only prompts and paradigms.
- **Change:** none under assumption A (stdlib only). Shipping any non-`.py` data file, such as a word list or a JSON table, requires a package-data entry (C015).

## 3. Tests that cover those files

### 3.1 Framework and configuration

- **Runner:** pytest 8.3.5 with pytest-asyncio 1.3.0 (`pyproject.toml` `dev` extra).
- **`[tool.pytest.ini_options]`:**
  - `testpaths=["tests"]`
  - `--strict-config --strict-markers` (an unregistered marker fails)
  - `asyncio_default_fixture_loop_scope="function"`
  - Whether `asyncio_mode` is set (strict versus auto) is unverified.
- **Existing tool tests use `unittest` classes, collected by pytest:**
  - `tests/test_tools_catalog.py` (80 lines, no header): `@tool` alias, catalog names and describe, duplicate rejection, provider schemas, `ToolRegistry`.
  - `tests/test_tool_core.py` (572 lines): `unittest.IsolatedAsyncioTestCase` with `EchoTool`/`LookupOrderTool` fixture classes defined in the file.
  - `tests/test_custom_function_tools.py` (570 lines): `FunctionTool` behavior and output serialization.
  - `tests/test_function_tool_parameter_types.py` (50 lines): has a full A001 header whose TESTS field gives `python -m pytest -q tests/test_function_tool_parameter_types.py`.
- **Feature packs** (`tests/features/<pack>/`, no `__init__.py`):
  - `FEATURE.md` sections: High-Level Feature Description, Contract, Actors / Callers, Inputs and Preconditions, Observable Outcomes, State Transitions, Invariants, External Dependencies, Known Failure Modes, Historical Regressions, Test Suite Map, Omitted Testing Strategies.
  - `README.md` sections: Folder Description / Intent, Non-Goals, `## File Index` (S020 applies), Logs.
  - Plain pytest-function tests with full A001 headers. `tests/features/coding_agent/` has its own `conftest.py`.
- **Fixtures:** there is no `tests/conftest.py`. `tests/__init__.py` and `tests/agent_test_support.py` exist.
- **A001 applies to new test files too**, because the scope is every tracked `.py`. So does S062.

### 3.2 Tests that touch the surfaces in section 2

- **Catalog behavior and duplicate names:** `tests/test_tools_catalog.py`.
- **BaseTool and executor contracts:** `tests/test_tool_core.py`.
- **FunctionTool and `@tool`:** `tests/test_custom_function_tools.py`, `tests/test_function_tool_parameter_types.py`.
- **Builtins export surface:** `tests/features/coding_agent/test_coding_agent_contract.py:102-109` asserts `BashTool` is exported from `vidbyte.tools.builtins` and listed in `__all__`.
  - No test enumerates the full builtins `__all__` or the `ComponentRegistry` names, so adding exports breaks no existing equality assertion that I found.
  - `tests/test_agent_abstractions.py` imports `CalculatorTool` directly from its module.
- **Reasoning count guard:** `scripts/check_reasoning_trace_contracts.py`, run by the gate rather than by pytest.

### 3.3 Exact commands (read from source; not executed)

- **One file:** `python -m pytest -q tests/test_tools_catalog.py`
- **One feature pack:** `python -m pytest -q tests/features/<pack>` (precedent `python -m pytest -q tests/features/sdk_operation_costs`).
- **From the worktree:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent`
- **Whole suite:** `python -m pytest` (last step of the source stage).
- **Full gate:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`.
- **Basename collisions:** feature dirs have no `__init__.py`. Under pytest's default import mode, two test files with the same basename in different feature dirs would collide. This is standard pytest behavior, unverified here. For example, `test_contract.py` already exists in `tests/features/sdk_loop_settings/`.

## 4. Notes for the spec author

1. **Builtin count.** The request assumes the SDK's builtins are a modest set (`calculator.py`, `bash.py`, ...) to which 250+ will be added. The code shows `vidbyte/tools/builtins/reasoning/` already ships 218 tool classes (182 trace tools plus 36 named), guarded by a hard-coded `182` at `scripts/check_reasoning_trace_contracts.py:39`, and described as "182" at `vidbyte/tools/builtins/__init__.py:19` and `vidbyte/tools/README.md:44`. The new tools must not disturb those counts unless the spec says so.
2. **`calculator.py` reachability.** The request names `calculator.py` as an existing builtin. The code shows `CalculatorTool` and `DocumentRetrievalTool` are not exported from `vidbyte/tools/builtins/__init__.py`, so they are not YAML-declarable. Field guide `declarative-config-resolution.md` says this is deliberate.
3. **"Tool catalog."** The request assumes `vidbyte/tools/catalog.py` is a tool catalog that new tools register into. The code shows `Tools` is an agent-local `Sequence[BaseTool]` with no global registry or import scan (`vidbyte/tools/catalog.py`). The only discovery is `ComponentRegistry._discover` at `vidbyte/lib/registries/components.py:101-124`, which accepts public `BaseTool` subclasses exported from `vidbyte.tools.builtins` (`:113`, `:124`). A `@tool` function (a `FunctionTool` instance) is never discovered.
4. **Name uniqueness.** The request assumes tool names are free to choose. The code shows names must be unique within one `Tools` (`vidbyte/tools/catalog.py:38`, `:79`) and on an agent (`vidbyte/agents/base.py:334`).
   - Reserved names: `isDone` (`vidbyte/tools/_internal.py:11`, `vidbyte/agents/settings/tool.py:28`), `updateTrace` (`vidbyte/tools/continual_trace.py:23`), and `mcp` for Codex (`vidbyte/lib/constants/codex.py:185`).
   - Confirmed existing generic names: `calculator`, `code_execution`, `document_retrieval`, `pause_agent`, `fermi_estimate`, `glob`, `grep`, `semantic_search`, `patch_file`, `append_text`, `checksum`, `copy`, `delete`, `diff`, `exists`, `find`, `list_dir`, `make_dir`, `move`, `read_binary`, `read_lines`, `read_text`, `replace_text`, `stat`, `touch`, `tree`, `write_text`, `zip`, and `unzip` (filesystem names at `vidbyte/tools/filesystem/*.py`, lines 13–49). Session names: `fork_conversation`, `batch_fork`, `checkpoint`, `fork`, `resume_append`, `resume_output`, `resume_replace`, `rewind`, `session`. Jev names: `run_bulk_work`, `launch_swarm`.
   - A grep of `name="..."` literals also shows operations, memory, and context names, such as `brave_search`, `tavily_search`, `mem0_add_memory`, `context_list`, and `compact_context`, mixed with parameter names. These are unverified individually.
5. **Name format.** The request assumes nothing about name format. The code shows `ToolSpec` validates only non-blank name and description (`vidbyte/lib/dataclasses/tools.py:128-132`), so the SDK does not enforce a format.
   - Codex dynamic tools require `^[A-Za-z0-9_-]+$`, at most 128 chars (`vidbyte/lib/constants/codex.py:183-185`).
   - Agent names exposed as tools use the same pattern, at most 64 chars (`vidbyte/lib/dataclasses/config.py:69`, `:81`).
   - Provider name and tool-count limits (for example about 64 chars per name, or a cap on tools per request) are unverified in the repo.
   - Existing names mix snake_case (`pause_agent`) and hyphenated slugs (reasoning `*-trace`).
6. **Description depth by authoring path.** The request assumes "simple, easy to understand" tools. The code shows two description-depth regimes:
   - S025 requires 4 or more sentences for every statically resolvable `ToolSpec`/`ToolParameter` description in a `BaseTool` subclass with its own `spec()` (`lint/rules/s025_model_facing_description_depth.py`).
   - `@tool` functions are not scanned by S025. Their parameter descriptions default to `""` (`vidbyte/tools/function_tool.py:117`); only `Annotated[..., Field(description=...)]` populates them (unverified by test).
   - Field guide `model-facing-tool-contracts.md` asks for consistent 4–5 sentence descriptions on the tool and every parameter, with no concrete examples, regardless of authoring path.
7. **Headers on every file.** The request assumes following existing patterns. The code shows the nearest small-tool precedents carry no A001 header: `vidbyte/tools/builtins/calculator.py`, `vidbyte/tools/filesystem/*.py`, and `vidbyte/tools/function_tool.py`. Their S017 `str(exc)` error reporting is baseline debt (`vidbyte/tools/builtins/calculator.py`, `vidbyte/tools/filesystem/checksum.py`). Copying them adds A001, S025, and S017 violations. A001 covers tests as well (`lint/rules/a001_agent_readable_file_headers.py:24-31`).
8. **YAML cap.** The request assumes a developer can attach all tools. The code shows YAML/declarative documents cap tool entries at 128 (`vidbyte/lib/dataclasses/config.py:75`, `:755`; `vidbyte/lib/dataclasses/agent_descriptor.py:49`, `:284`). 250+ tools cannot all be declared one by one in a single document. The Python API (`Agent(tools=...)`, `add_tool`, `Tools`) has no such cap that I found.
9. **Schema payload size.** The request assumes giving tools to an agent is free. The code shows every attached tool's schema is sent with each request (`ToolsFormatter`, `vidbyte/lib/tools/formatter.py`). Attaching 250+ at once multiplies prompt size; any provider cap on tools per request is unverified in the repo.
10. **Placement versus the reasoning precedent.** The request assumes following existing patterns. The code shows the only many-tool precedent defines its record `ReasoningTraceDefinition` in `vidbyte/tools/builtins/reasoning/_base.py`, which AGENTS.md "Existing code" says is not precedent. A new definition record goes in `vidbyte/lib/dataclasses/<domain>.py`, and a category set is an enum in `vidbyte/lib/enums/<domain>.py`. No tool enum module exists today: there is no `vidbyte/lib/enums/tools.py`.
11. **Root export cost.** The request is silent on root exports. The code shows `vidbyte/__init__.py` is 1,297 lines, already over the 1,000-line guideline. Any `__all__` change triggers C016 and a regenerated `contracts/sdk-public-api.json` (`python scripts/generate-sdk-public-api.py`).
12. **Array and object parameters.** The request is silent. The code shows `_parameters_schema` at `vidbyte/lib/tools/formatter.py:794` emits only `type` and `description` per `ToolParameter`. Array parameters may reach providers without `items`; the patch at `:276-281` may apply only to `input_schema` (unverified). `FunctionTool` always supplies a full pydantic `input_schema` (`vidbyte/tools/function_tool.py:126`). `pause.py` supplies an explicit one.
13. **Stdlib-only assumption.** Orchestrator assumption A (stdlib only, no network) is consistent with `pyproject.toml` dependencies: pydantic, httpx, and PyYAML are already installed, and Python is 3.11 or later. One exception: `zoneinfo` on Windows needs the `tzdata` package, which is not a dependency. Unverified at runtime; it matters for any time-zone tool.
14. **Semgrep scope.** The request assumes the full gate is `run_ci.py`. The code shows Semgrep runs only in `.github/workflows/static-policy.yml:24-30`. Its `no-untyped-mapping-fallback` rule is likely to fire on JSON-manipulating tools that check `isinstance(x, Mapping)` on an `object`/`Any` parameter and return early, and `vidbyte/tools/builtins/` is not excluded.
15. **Stale map and README.** The request is silent. The code shows the `REPO_MAP.md:337` toolsets entry says "one such bundle" while `vidbyte/tools/toolsets/__init__.py` exports two. `vidbyte/tools/README.md:89` lists the `builtins/` contents and would need the new tools added.
16. **Lint traps in tool code.** The request is silent. The code shows:
    - A002 flags helper names containing `redact`, `secret`, `price`, `fetch`, `send`, `request`, `checkpoint`, `transition`, or `fallback` unless an `# @intent` comment is present.
    - A007 flags numeric literals near names containing `limit`, `char`, `byte`, `depth`, or `token`.
    - S016 flags `raise ValueError` and similar in `vidbyte/tools/builtins/`.
    - S062 flags adjacent string literals, the usual way to wrap long descriptions; use one literal or explicit `+`.
    - Rule sources are under `lint/rules/` (see the table in 1.2).
17. **Error reporting.** The request is silent. The code shows `FunctionTool` already turns any raised exception into a failure result carrying `str(exc)` (`vidbyte/tools/function_tool.py:76-81`). A `@tool` function can therefore raise `ToolExecutionError` with a clear message without tripping S017 in its own file. A `BaseTool.execute` that catches and formats `exc` itself trips S017 (unverified for the raise-only case).
