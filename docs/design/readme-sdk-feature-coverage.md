# Design Doc: README SDK Feature Coverage

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-05
**Last Updated:** 2026-06-05

---

## 1. Overview

Update the root README so it accurately documents the current Vidbyte SDK feature surface for registries, MCP servers, prompt imports, eval helpers, and pipelines. This is a documentation-only change: the README should teach the public APIs that already exist, list the MCP preset catalog at a useful level of detail, and connect readers to concise examples without changing runtime behavior, package exports, tests, or scripts.

---

## 2. Goals & Non-Goals

### Goals

- Add a README section for every registry currently exported from `vidbyte.lib.registries`.
- Add README guidance for using the SDK as an MCP Studio server and for attaching third-party MCP preset servers to agents.
- Document the full MCP preset catalog from `vidbyte/lib/config/mcp_presets.py`, which currently contains 201 presets across 12 categories.
- Expand the prompt docs so readers know they can import SDK prompts directly from `vidbyte.prompts`, use enum keys through `Prompts`, list prompt metadata, and load prompt families.
- Add README guidance for `vidbyte.evals` so developers can create eval suites, graders, runners, and local eval workflows more quickly.
- Add README guidance for the pipeline feature, including sequential, parallel, conditional, map-reduce, nested pipelines, and sync usage.
- Keep examples credential-safe and aligned with public imports that already exist.
- Keep the implementation scoped to README documentation after approval.

### Non-Goals

- No SDK runtime code changes.
- No tests or scripts for this request, per user instruction.
- No changes to `pyproject.toml`, packaging metadata, public exports, provider behavior, MCP transport behavior, or prompt assets.
- No live MCP subprocess launches, external provider calls, credential validation, or network calls.
- No redesign of the MCP Studio server prompt-loading behavior.
- No creation of new docs beyond the design doc required by this workflow.

---

## 3. Background & Context

The current README already covers package status, basic `VidbyteSDK` usage, agents, context, tracing, runtimes, tools, middleware, a basic prompt accessor, package structure, public boundary, and local verification. It does not yet describe several implemented SDK areas that are present in the repository:

- `vidbyte/lib/registries/` exports `AgentRegistry`, `ProviderModelRegistry`, `PromptRecord`, `Prompts`, `RuntimeRegistry`, `ToolRegistry`, `ActorRegistry`, and the shared `actor_registry`.
- `vidbyte/tools/mcp/presets.py` and `vidbyte/lib/config/mcp_presets.py` define an MCP preset registry and 201 preset definitions across search, development, databases, productivity, document parsing, communications, cloud, AI APIs, reference, native utilities, e-commerce, and automation.
- `vidbyte/agents/mixins.py` exposes `attach_preset_mcp_server(...)`, `with_preset_mcp_server(...)`, raw `attach_mcp_server(...)`, and lazy `with_mcp_server(...)`.
- `vidbyte/mcp_server/` exposes the `vidbyte-mcp-server` CLI and `McpStudioServer`, with MCP handlers for `initialize`, `tools/list`, `tools/call`, `prompts/list`, and `prompts/get`.
- `vidbyte/mcp_server/handlers.py` registers Studio tools named `studio.agents.list`, `studio.agents.run`, `studio.tools.list`, `studio.strategies.list`, `studio.strategies.run`, `studio.prompts.list`, `studio.prompts.get`, and `studio.pipelines.list`.
- `vidbyte/prompts/` contains a catalog of 34 prompt assets across 13 prompt families and dynamically exports direct prompt constants from `vidbyte.prompts`.
- `vidbyte/evals/` exports eval case, suite, runner, registry, client, result dataclasses, and six built-in graders.
- `vidbyte/pipelines/` exports `BasePipeline`, `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, `MapReducePipeline`, `PipelineNode`, and separator constants.
- `skills/usage/import_prompt.md`, `skills/usage/create_pipeline.md`, `skills/vidbyte-sdk/evals.md`, and `skills/vidbyte-sdk/pipelines.md` already contain concise usage guidance that can inform README examples.

The working tree is dirty before this task, mostly due to modified and untracked `__pycache__` files plus existing untracked design docs. This work must not revert or clean unrelated changes.

---

## 4. Requirements

### Functional Requirements

1. The README must add a "Registries" section that names and briefly explains every registry exported by `vidbyte.lib.registries`.
2. The registry section must show at least one concise code example using `ProviderModelRegistry`, `RuntimeRegistry`, `ToolRegistry`, and `actor_registry` or `ActorRegistry`.
3. The README must add an MCP section that separates two concepts: running Vidbyte itself as an MCP Studio server, and attaching third-party MCP preset servers to a Vidbyte agent.
4. The MCP Studio server subsection must show `vidbyte-mcp-server` and `python -m vidbyte.mcp_server` as equivalent launch paths.
5. The MCP Studio server subsection must mention the Studio tools exposed through MCP: `studio.agents.list`, `studio.agents.run`, `studio.tools.list`, `studio.strategies.list`, `studio.strategies.run`, `studio.prompts.list`, `studio.prompts.get`, and `studio.pipelines.list`.
6. The MCP preset subsection must show `McpPresetRegistry.list_presets()`, `McpPresetRegistry.build_config(...)`, `agent.attach_preset_mcp_server(...)`, and `agent.with_preset_mcp_server(...)`.
7. The MCP preset subsection must list the 12 preset categories and the preset names in each category.
8. The MCP examples must not include real secrets; all env values must be placeholder strings or loaded from `os.environ`.
9. The README prompt section must document both enum-keyed lookup and direct imports from `vidbyte.prompts`.
10. The prompt section must mention that there are 34 prompt assets across 13 families and that `Prompts().keys()`, `Prompts().descriptions()`, `Prompts().import_names()`, and `Prompts().family(...)` are available.
11. The README evals section must show how `EvalCase`, `EvalSuite`, `EvalRunner`, and at least one built-in grader make eval scripts easier to write.
12. The evals section must list the built-in graders: `ExactMatchGrader`, `ContainsGrader`, `RegexMatchGrader`, `JSONSchemaGrader`, `LLMJudgeGrader`, and `RubricGrader`.
13. The README pipeline section must explain the string-in/string-out contract.
14. The pipeline section must show examples for `SequentialPipeline`, `ParallelPipeline`, `ConditionalPipeline`, and `MapReducePipeline`.
15. The pipeline section must mention nested pipelines and `run_sync()`.
16. The README package structure block must be updated if needed so it includes `evals/`, `pipelines/`, `mcp_server/`, and `lib/registries/`.
17. The README local verification section may be updated with existing commands only; it must not add a new test script or require live external services.

### Non-Functional Requirements

- Performance: N/A - documentation-only change.
- Scalability: N/A - documentation-only change.
- Security: Examples must avoid real secrets and warn that MCP preset env values come from caller-provided environment mappings.
- Observability: N/A - no runtime logging, tracing, or metrics changes.
- Reliability: README examples must be based on audited local code, not inferred APIs.
- Maintainability: Long MCP catalog content should be generated from or clearly traceable to `vidbyte/lib/config/mcp_presets.py`; README wording should encourage programmatic discovery with `McpPresetRegistry.list_presets()`.
- Compatibility: The README must not claim new APIs, new exports, or behavior not present in the current repo.

---

## 5. High-Level Design

The implementation will revise `README.md` by adding focused sections after the related existing areas. The existing "Prompts" section will be expanded rather than replaced wholesale. New sections for "Registries", "MCP Servers", "Evals", and "Pipelines" will be inserted before "Package Structure" so the README builds from core agent usage into advanced SDK composition features.

The README examples will use current public imports from the root `vidbyte` namespace where available, and specialized imports from subpackages where that is clearer. For MCP presets, the README will point to `McpPresetRegistry` as the authoritative discovery interface and include the full category/name list so readers can see what the SDK offers without opening source files.

```text
README.md
  |
  +-- Registries: existing SDK registry classes and examples
  +-- MCP Servers: Studio server plus third-party preset attachment
  +-- Prompts: enum lookup plus direct imports and families
  +-- Evals: suites, cases, runners, graders, registry
  +-- Pipelines: sequential, parallel, conditional, map-reduce
```

No code or package data will change. Verification for this request will be manual/local documentation inspection only, respecting the user's explicit request not to create tests or scripts.

---

## 6. Detailed Design

### 6.1 Root README Feature Coverage

**File(s):** `README.md`
**Type:** Modified

#### What it does

Adds documentation for implemented SDK features that are currently missing or underdocumented in the root README.

#### Interface / API

```python
from vidbyte.lib.registries import ProviderModelRegistry, RuntimeRegistry, ToolRegistry, actor_registry
from vidbyte.tools.mcp.presets import McpPresetRegistry
from vidbyte.prompts import handoff_system_prompt
from vidbyte import Prompts, Prompt, EvalCase, EvalSuite, EvalRunner, ContainsGrader
from vidbyte import SequentialPipeline, ParallelPipeline, ConditionalPipeline, MapReducePipeline
```

#### Logic / Algorithm

1. Add a "Registries" section after the existing runtimes/tools coverage or before "Prompts".
2. In "Registries", list:
   - `AgentRegistry`: in-process agent discovery by name, capability, tool, or metadata.
   - `ProviderModelRegistry`: provider defaults, endpoints, env var names, credential resolution, and active provider/model maps.
   - `Prompts` / `PromptRecord`: prompt catalog registry and metadata.
   - `RuntimeRegistry`: maps `AgentRuntimeType` values to runtime classes.
   - `ToolRegistry`: compatibility wrapper around the agent-local `Tools` catalog.
   - `ActorRegistry` / `actor_registry`: prebuilt/custom actor role registry.
3. Add an "MCP Servers" section with two subsections:
   - "Vidbyte as an MCP Studio Server"
   - "Preset MCP Servers for Agents"
4. In the Studio server subsection, document CLI startup, programmatic launcher usage, and the exposed Studio tools.
5. In the preset subsection, document preset discovery, config building, eager attachment, lazy attachment, and the full category/name catalog.
6. Expand "Prompts" to include direct import examples, family lookup, metadata methods, and prompt catalog size.
7. Add "Evals" with a minimal eval suite example, grader catalog, tag filtering, JSON/CSV suite loading, and registry mention.
8. Add "Pipelines" with topology examples and error/contract notes.
9. Update "Package Structure" so the listed tree reflects the audited modules.
10. Keep examples concise enough that the README remains approachable despite the large catalog.

#### Edge Cases & Error Handling

- If a preset requires environment variables, README examples must pass placeholders such as `os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]` rather than literals.
- If a server or third-party package is not installed on the host, the README should not imply the SDK installs every dependency at `pip install` time; presets define commands and env requirements.
- The README should avoid claiming default `McpStudioServer()` automatically exposes prompt catalog content until the prompt-loading implementation is clarified, because `core.py` currently references `Prompts()._data` and catches errors.
- The README must distinguish `vidbyte.tools.mcp.presets` as the authoritative named preset export surface; `vidbyte.tools.mcp.__init__` may not re-export every one of the 201 named constants.

---

### 6.2 Design Doc

**File(s):** `docs/design/readme-sdk-feature-coverage.md`
**Type:** New file

#### What it does

Captures the audited scope and approval gate for the README update before any README implementation starts.

#### Interface / API

```markdown
# Design Doc: README SDK Feature Coverage
```

#### Logic / Algorithm

1. Use every template section in order.
2. Record exact requirements, non-goals, file manifest, verification plan, risks, and open questions.
3. Stop after design-doc creation until explicit user approval.

#### Edge Cases & Error Handling

- If the approved implementation scope changes, update this design doc or call out the deviation in the handoff.
- If the repo's existing dirty worktree blocks later worktree setup, stop and report it during the post-approval phase rather than cleaning unrelated files.

---

## 7. Data Model Changes

N/A - documentation-only README change. No dataclasses, schemas, database tables, migrations, prompt assets, package data, serialized formats, or persistence models will change.

---

## 8. API Changes

N/A - no SDK API, HTTP endpoint, CLI behavior, MCP protocol method, provider, runner, grader, registry, or pipeline interface changes. The README will document existing APIs only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/readme-sdk-feature-coverage.md` | Design-doc workflow source of truth for the README update |
| MODIFY | `README.md` | Add documentation for registries, MCP servers, prompt imports, evals, and pipelines |

---

## 10. Testing Plan

The user explicitly requested that this README-only task not create tests or scripts. The plan below is therefore a documentation verification plan using local inspection commands and manual checks, with each case labeled under the required categories.

### Unit Tests

- N/A - no code units will be created or modified.

### Integration Tests

- N/A - no runtime integration behavior will be created or modified.

### Manual / QA Test Cases

1. [Edge Case] Given the updated README, when a reader wants the complete registry surface, then the "Registries" section names all exports from `vidbyte.lib.registries`: `AgentRegistry`, `ProviderModelRegistry`, `PromptRecord`, `Prompts`, `RuntimeRegistry`, `ToolRegistry`, `ActorRegistry`, and `actor_registry`.
2. [Silent Failure] Given the updated README, when a reader follows MCP preset guidance, then the examples use `McpPresetRegistry.list_presets()` and `build_config(...)` rather than a hardcoded subset that could appear complete but omit presets.
3. [Hidden Assumption] Given the updated README, when a reader configures preset MCP credentials, then examples show env values coming from caller-provided mappings or `os.environ`, not embedded secrets.
4. [Edge Case] Given the updated README, when a reader scans the MCP catalog, then all 12 categories and 201 preset names are represented.
5. [Hidden Failure] Given the updated README, when a reader starts `vidbyte-mcp-server`, then the docs describe it as a stdio MCP server launched by an MCP client and do not imply it is a long-running HTTP service.
6. [Silent Failure] Given the updated README, when a reader uses prompt imports, then both `Prompts().get(Prompt.X)` and `from vidbyte.prompts import <direct_prompt_name>` patterns are shown.
7. [Hidden Assumption] Given the updated README, when a reader uses prompt families, then the docs explain `Prompts().family("reflexion")` returns family prompt text keyed by leaf prompt name.
8. [Edge Case] Given the updated README, when a reader creates a tiny eval suite, then the example works with one or more `EvalCase` instances and a built-in grader.
9. [Silent Failure] Given the updated README, when a reader compares eval options, then all six built-in graders are named so the docs do not accidentally narrow the feature surface.
10. [Hidden Failure] Given the updated README, when a reader builds a pipeline, then the docs make the string-in/string-out contract clear and do not imply pipeline-level shared context, budget, artifacts, streaming, or retries.
11. [Edge Case] Given the updated README, when a reader needs pipeline topology options, then examples cover sequential, parallel, conditional, and map-reduce.
12. [Hidden Assumption] Given the updated README, when a reader checks the package layout, then `evals/`, `pipelines/`, `mcp_server/`, and `lib/registries/` appear in the package structure block.
13. [Silent Failure] Given the updated README, when rendered on a Markdown viewer, then fenced code blocks and tables remain syntactically valid and readable.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Source of documented SDK APIs | Low; already required by package |
| `pydantic` | `>=2,<3` from `pyproject.toml` | Existing SDK dependency, not changed | Low; no new use |
| `httpx` | `>=0.27` from `pyproject.toml` | Existing SDK dependency, not changed | Low; no new use |
| Node / `npx` | Host-provided | Some MCP presets use `npx -y ...` commands | Medium; README must present this as runtime host requirement for those presets, not SDK install behavior |
| External provider APIs | Various | Required only when readers run examples with real agents or MCP presets | Medium; README examples must avoid live credentials and network assumptions |

---

## 12. Rollout & Deployment

- Feature flags: N/A - documentation-only.
- Breaking change: No.
- Migration path: N/A - users gain better docs for existing APIs.
- Deployment order after approval:
  1. Create isolated worktree per the design-doc workflow.
  2. Commit this design doc first.
  3. Modify only `README.md`.
  4. Run local documentation inspection checks; no new tests or scripts.
- Rollback procedure: Revert the README documentation commit and design-doc commit. No data, runtime, or package rollback is required.

---

## 13. Open Questions

- [ ] Should the README include all 201 MCP preset names inline, or should it show category summaries plus a short programmatic listing snippet to avoid making the root README too long?
- [ ] Should the README mention the current `McpStudioServer` prompt auto-load caveat, or should it only document explicit `prompt_content={...}` injection until the implementation is fixed in a separate PR?
- [ ] Should root README examples import MCP preset constants directly from `vidbyte.tools.mcp.presets`, or should the README primarily teach string preset keys through `McpPresetRegistry`?

---

## 14. Alternatives Considered

### Alternative 1: Add Separate Top-Level Docs Instead Of README Coverage

- What: Create new docs files for registries, MCP, prompts, evals, and pipelines and link from the README.
- Why rejected: The user specifically asked to update the README. The README should still expose the SDK's main capabilities at a glance.

### Alternative 2: Add Automated README Verification Script

- What: Create a script that checks for section headings, examples, and catalog names.
- Why rejected: The user explicitly said tests and scripts are not needed for this request.

### Alternative 3: Fix MCP Studio Prompt Loading While Updating Docs

- What: Change `McpStudioServer` to load prompt content through current `Prompts` APIs instead of the stale `_data` access.
- Why rejected: That is a runtime behavior change. It should be handled in a separate implementation design if desired.
