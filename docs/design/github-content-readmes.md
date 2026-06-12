# Design Doc: GitHub Content README Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-12
**Last Updated:** 2026-06-12

---

## 1. Overview

Expand `vidbyte-sdk` into a stronger GitHub content surface by improving the root README and adding developer-facing README files for the SDK abstraction layers under `vidbyte/`. Each new layer README will briefly explain what Vidbyte and the SDK are, describe the role of that package in the SDK, state the design philosophy behind the abstraction, and include small, audited code snippets that use APIs already present in the repository.

---

## 2. Goals & Non-Goals

### Goals

- Make the SDK repository more descriptive for developers, search crawlers, and awesome-list reviewers.
- Improve the root README so it explains Vidbyte as an agent engineering platform, not only a package namespace and install surface.
- Add README files for each top-level SDK abstraction layer under `vidbyte/`: `agents`, `context`, `evals`, `harnesses`, `lib`, `mcp_server`, `middleware`, `pipelines`, `prompts`, `providers`, `shared`, `tools`, and `trace`.
- For every layer README, include:
  - A short explanation of what Vidbyte and `vidbyte-sdk` are.
  - The role the package plays in the SDK architecture.
  - The design philosophy behind the abstraction.
  - At least one compact Python code snippet grounded in current local APIs, or a clear "reserved/internal" note for layers with no public runtime API.
- Keep README wording accurate to current source code and avoid claims about unreleased hosted services beyond the existing public boundary.
- Add a deterministic verification script for README coverage, section structure, and code fence presence.

### Non-Goals

- No SDK runtime code changes.
- No public API, package metadata, dependency, provider, MCP protocol, prompt asset, eval, or middleware behavior changes.
- No external web research, no awesome-list PRs, and no submissions to `awesome-mcp-servers`, `awesome-learning`, or `awesome-edtech` in this change.
- No generation of marketing images, badges, logos, or diagrams.
- No cleanup of existing dirty `__pycache__` files or unrelated untracked design docs.
- No docs for every nested implementation directory unless it is explicitly added to this design later.

---

## 3. Background & Context

The current SDK root README is already broad and includes sections for agents, context, tracing, runtimes, tools, middleware, registries, MCP servers, prompts, evals, pipelines, package structure, public boundary, and local verification. It still opens with a very narrow package-scaffold framing: "`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface." The user's content-surface request is different: READMEs should help a new reader understand what Vidbyte is, why the SDK exists, how the abstractions fit together, and why the repo belongs in agent, MCP, learning, or edtech discovery lists.

The audited repository is a Python package (`pyproject.toml`, Python `>=3.11`) with dependencies on `pydantic>=2,<3` and `httpx>=0.27`. Public exports are centralized in `vidbyte/__init__.py`, and the top-level package directories map to meaningful abstraction layers:

- `vidbyte.agents`: `BaseAgent`, `Agent`, runtimes, modality routing, handoff agents, and agent registries.
- `vidbyte.context`: context dataclasses, `ContextManager`, context-window algorithms, primitives, compaction, and handoff structures.
- `vidbyte.evals`: eval cases, suites, runners, registries, and built-in graders.
- `vidbyte.harnesses`: current namespace client placeholder for future harness integrations.
- `vidbyte.lib`: shared dataclasses, enums, errors, registries, runners, tracing contracts, and formatting helpers.
- `vidbyte.mcp_server`: stdio MCP Studio server exposing agents, tools, prompts, strategies, and pipelines.
- `vidbyte.middleware`: deterministic runtime hooks and built-in policy, safety, retry, rate-limit, budget, and compaction middleware.
- `vidbyte.pipelines`: sequential, parallel, conditional, and map-reduce agent composition.
- `vidbyte.prompts`: enum-keyed and direct-import prompt catalog.
- `vidbyte.providers`: provider adapter factories for text, image, video, audio, embedding, and streaming text modalities.
- `vidbyte.shared`: currently empty shared namespace.
- `vidbyte.tools`: tool contracts, decorators, catalogs, executors, MCP bridges, security policies, and built-ins.
- `vidbyte.trace`: trace facade, debug tracer, provider tracers, and continual trace artifact support.

The working tree is already dirty before this task, mostly generated `.pyc` files and untracked design docs. Future implementation must not revert or clean unrelated changes.

---

## 4. Requirements

### Functional Requirements

1. The root `README.md` SHALL explain Vidbyte as a platform for building, instrumenting, evaluating, and distributing agentic workflows.
2. The root `README.md` SHALL keep existing install, usage, public boundary, and verification information that remains accurate.
3. The root `README.md` SHALL include a navigation section pointing readers to the layer READMEs under `vidbyte/`.
4. The root `README.md` SHALL mention MCP, agent runtime abstractions, evals, tools, middleware, prompts, providers, pipelines, and traceability as part of the SDK surface.
5. `vidbyte/agents/README.md` SHALL explain agents as executable actors combining prompts, runners, tools, context, middleware-compatible runtimes, handoff, modality routing, and runtime choices.
6. `vidbyte/context/README.md` SHALL explain structured context, context-window algorithms, primitives, compaction, and handoff-oriented context objects.
7. `vidbyte/evals/README.md` SHALL explain local eval cases, suites, graders, runners, result summaries, registry comparisons, and agent isolation through `fork()`.
8. `vidbyte/harnesses/README.md` SHALL explain the namespace as the integration boundary for future custom harness clients and make clear it is intentionally minimal today.
9. `vidbyte/lib/README.md` SHALL explain `lib` as the internal contract layer for dataclasses, enums, registries, runners, errors, config, tool formatting, and tracing.
10. `vidbyte/mcp_server/README.md` SHALL explain the SDK's stdio MCP Studio server, MCP tool exposure, prompt exposure, and programmatic launcher pattern.
11. `vidbyte/middleware/README.md` SHALL explain deterministic lifecycle hooks, built-in middleware, decision semantics, fail-open/fail-closed behavior, and agent attachment.
12. `vidbyte/pipelines/README.md` SHALL explain string-in/string-out multi-agent topologies: sequential, parallel, conditional, map-reduce, nested pipelines, and sync use.
13. `vidbyte/prompts/README.md` SHALL explain prompt catalog loading, enum-keyed lookup, direct prompt imports, prompt families, and prompt asset validation.
14. `vidbyte/providers/README.md` SHALL explain provider adapter factories, modality-specific adapters, provider schema translation, and credential-safe configuration.
15. `vidbyte/shared/README.md` SHALL explain that `shared` is currently a reserved namespace and should not be treated as the stable public API.
16. `vidbyte/tools/README.md` SHALL explain `@tool`, `FunctionTool`, `BaseTool`, `Tools`, provider schemas, execution, permissions, MCP tools, and built-ins.
17. `vidbyte/trace/README.md` SHALL explain `Trace`, `DebugTracer`, provider tracers, `TraceOption.continual`, trace artifacts, and fail-open tracing behavior.
18. Every layer README SHALL contain the exact phrase `Vidbyte SDK` at least once.
19. Every public layer README SHALL contain sections named `Role In The SDK`, `Design Philosophy`, and `Usage`.
20. Every public layer README SHALL include at least one fenced Python code block, except `shared` if it is documented as reserved.
21. Code snippets SHALL use only locally audited imports and APIs.
22. Documentation SHALL avoid real secrets, tokens, API keys, and direct credential literals.
23. A verification script SHALL check that all required README files exist and contain required headings, phrases, and code fences.
24. Every SDK README SHALL include a section linking to the Vidbyte website at `https://vidbyte.pro`.
25. Every layer README SHALL explain that the abstraction participates in the SDK architecture used to power agents on the Vidbyte website.
26. Every layer README SHALL provide deeper feature coverage than a short overview, including the major public classes, factories, helpers, or boundaries for that abstraction.
27. Every public layer README SHOULD include multiple usage snippets when the abstraction has more than one developer-facing workflow.

### Non-Functional Requirements

- Performance: N/A - documentation-only change.
- Scalability: README structure should make adding future package-layer READMEs straightforward.
- Security: Examples must avoid real credentials and should use placeholders or `os.environ` for environment-backed secrets.
- Observability: N/A - no runtime logging, metrics, or tracing behavior changes.
- Reliability: Documentation must be grounded in audited source files, not inferred or aspirational APIs.
- Maintainability: The verification script should fail on missing or shallow docs so future changes do not silently erase the content surface.
- Compatibility: Existing README content should be preserved where still accurate; no import paths should be documented unless they exist locally.

---

## 5. High-Level Design

The implementation will treat README files as a documentation layer over the existing SDK architecture. The root README will become the top-level content surface: it will explain Vidbyte, list the core SDK capabilities, link to layer READMEs, then keep the current practical examples and verification guidance. The layer README files will be concise but substantial enough to stand alone when a reader lands directly on a GitHub folder page.

The layer README template will be consistent:

```text
# <Layer Name>

<Short Vidbyte SDK positioning>

## Role In The SDK
## Design Philosophy
## Usage
## Key Modules
## Related Layers
```

The approach intentionally avoids changing Python code. Verification will be done through a local script that scans Markdown files and checks expected headings, phrases, and code fences. This is enough for a documentation-only feature while still satisfying the design-doc workflow's required script verification phase after approval.

---

## 6. Detailed Design

### 6.1 Root SDK README

**File(s):** `README.md`
**Type:** Modified

#### What it does

Reframes the SDK as a developer-facing agent engineering toolkit and navigational content surface while preserving accurate existing usage sections.

#### Interface / API

```markdown
# Vidbyte SDK

Vidbyte is an agent engineering platform...

## Layer Guide
| Layer | Role |
| ... |
```

#### Logic / Algorithm

1. Replace the narrow opening scaffold description with a fuller description of Vidbyte and the SDK.
2. Add a compact "What You Can Build" or equivalent section covering agents, tools, middleware, MCP, evals, prompts, providers, pipelines, context, and tracing.
3. Add a "Layer Guide" table linking to all created layer README files.
4. Keep existing examples that match audited APIs.
5. Avoid overstating package publication, hosted service availability, or proprietary internals.

#### Edge Cases & Error Handling

- If an existing README section is still accurate, retain or lightly edit it instead of rewriting from scratch.
- If an API looks internal or placeholder-only, phrase it as internal/reserved rather than a developer promise.

### 6.2 Agents Layer README

**File(s):** `vidbyte/agents/README.md`
**Type:** New file

#### What it does

Documents agents as the main executable actor abstraction for prompts, runners, tools, context, runtimes, and handoff.

#### Interface / API

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(name="analyst", system_prompt="Answer directly.", runner=my_runner, tools=[lookup_metric])
reply = await agent.arun("Summarize this account.")
```

#### Logic / Algorithm

1. Explain `BaseAgent` / `Agent`.
2. Describe runner resolution, modalities, tools, context, trace, handoff, and runtimes.
3. Mention linear runtime is the middleware-compatible default.
4. Link related layers: context, tools, middleware, providers, pipelines, trace.

#### Edge Cases & Error Handling

- Do not imply non-linear runtimes support middleware or continual tracing; `BaseAgent` rejects those combinations.

### 6.3 Context Layer README

**File(s):** `vidbyte/context/README.md`
**Type:** New file

#### What it does

Documents context as structured, typed runtime information rather than ad hoc prompt concatenation.

#### Interface / API

```python
from vidbyte import ContextManager
from vidbyte.context.primitives import TaskContextItem, FileContextItem

context = ContextManager([
    TaskContextItem(goal="Fix tests", progress="Read failing output."),
    FileContextItem.from_path("README.md", include_content=True),
])
```

#### Logic / Algorithm

1. Explain `ContextManager`, `BaseContext`, primitives, placement, algorithms, compaction, and handoff models.
2. Show managed and unmanaged context item usage.
3. Explain context-window algorithms as runtime policy for how context is admitted or pruned.

#### Edge Cases & Error Handling

- Document that `upsert()` requires a non-empty `primitive_id`; unmanaged items use `add()` / constructor lists.

### 6.4 Evals Layer README

**File(s):** `vidbyte/evals/README.md`
**Type:** New file

#### What it does

Documents local evaluation primitives for agents and runner-like targets.

#### Interface / API

```python
from vidbyte import ContainsGrader, EvalCase, EvalRunner, EvalSuite

suite = EvalSuite("smoke", [EvalCase(prompt="2 + 2?", expected="4")])
result = await EvalRunner(agent, default_grader=ContainsGrader()).arun(suite)
```

#### Logic / Algorithm

1. Explain cases, suites, runner, graders, results, and registry.
2. Mention concurrency and state isolation through agent `fork()`.
3. List built-in graders.

#### Edge Cases & Error Handling

- Explain failed target calls become failed eval results rather than crashing the entire suite.

### 6.5 Harnesses Layer README

**File(s):** `vidbyte/harnesses/README.md`
**Type:** New file

#### What it does

Documents `harnesses` as the future integration namespace exposed through `VidbyteSDK().harnesses`.

#### Interface / API

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
harnesses = sdk.harnesses
```

#### Logic / Algorithm

1. Explain current minimal state honestly.
2. Explain intended role: adapting SDK abstractions into external execution harnesses.
3. Avoid promising concrete methods that do not exist.

#### Edge Cases & Error Handling

- Call out that current `HarnessClient` is a namespace marker, not a full adapter catalog.

### 6.6 Lib Layer README

**File(s):** `vidbyte/lib/README.md`
**Type:** New file

#### What it does

Documents `lib` as the internal contract and compatibility layer shared by public packages.

#### Interface / API

```python
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries import ProviderModelRegistry

default_model = ProviderModelRegistry.default_model(ModelProvider.OPENAI)
```

#### Logic / Algorithm

1. Explain dataclasses, enums, registries, errors, runners, tracing, tool formatting, and config.
2. Distinguish stable public imports from internal implementation helpers.
3. Link root exports where preferred.

#### Edge Cases & Error Handling

- Avoid encouraging application code to depend on internal helpers unless already documented in the root README.

### 6.7 MCP Server Layer README

**File(s):** `vidbyte/mcp_server/README.md`
**Type:** New file

#### What it does

Documents running Vidbyte as an MCP Studio server.

#### Interface / API

```bash
vidbyte-mcp-server
python -m vidbyte.mcp_server
```

```python
from vidbyte import McpStudioServer

server = McpStudioServer(name="my-studio", agents={"analyst": agent}, tools=[lookup_metric])
await server.run()
```

#### Logic / Algorithm

1. Explain stdio JSON-RPC operation.
2. List exposed Studio tools and prompt protocol support.
3. Show programmatic server construction.

#### Edge Cases & Error Handling

- Do not describe it as an HTTP server.
- Mention clients launch it as a subprocess.

### 6.8 Middleware Layer README

**File(s):** `vidbyte/middleware/README.md`
**Type:** New file

#### What it does

Documents middleware as deterministic runtime policy around the agent loop.

#### Interface / API

```python
from vidbyte import Agent, AgentMiddleware, MiddlewareDecision

class TenantPolicy(AgentMiddleware):
    async def before_run(self, ctx):
        return MiddlewareDecision.continue_(metadata={"tenant_checked": True})

agent = Agent(name="guarded", system_prompt="Work carefully.", runner=my_runner, middleware=[TenantPolicy()])
```

#### Logic / Algorithm

1. Explain lifecycle hooks.
2. Explain `MiddlewareDecision`, transforms, sleep, abort, deny, and metadata.
3. List built-ins by category.
4. Mention non-linear runtime limitations.

#### Edge Cases & Error Handling

- Document `fail_closed` vs fail-open behavior.

### 6.9 Pipelines Layer README

**File(s):** `vidbyte/pipelines/README.md`
**Type:** New file

#### What it does

Documents pipeline topologies for composing agents and pipelines.

#### Interface / API

```python
from vidbyte import SequentialPipeline

pipeline = SequentialPipeline([planner_agent, writer_agent, reviewer_agent])
result = await pipeline.run("Draft a release note.")
```

#### Logic / Algorithm

1. Explain string-in/string-out contract.
2. Cover sequential, parallel, conditional, map-reduce, nested, and `run_sync()`.
3. Link agents and evals.

#### Edge Cases & Error Handling

- Do not imply shared pipeline-level state, streaming, retries, artifacts, or voting.

### 6.10 Prompts Layer README

**File(s):** `vidbyte/prompts/README.md`
**Type:** New file

#### What it does

Documents prompt assets and catalog lookup.

#### Interface / API

```python
from vidbyte.prompts import Prompts
from vidbyte.lib.enums.prompts import Prompt

prompt_text = Prompts().get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT)
```

#### Logic / Algorithm

1. Explain enum-keyed lookup, direct imports, families, descriptions, import names, and asset validation.
2. State prompt assets are static SDK content, not runtime prompt mutation.

#### Edge Cases & Error Handling

- Mention `Prompts.get()` expects a `Prompt` enum member, not a raw string.

### 6.11 Providers Layer README

**File(s):** `vidbyte/providers/README.md`
**Type:** New file

#### What it does

Documents provider adapter selection and modality-specific factories.

#### Interface / API

```python
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.providers import ModelProviders

provider = ModelProviders.text(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4.1"))
```

#### Logic / Algorithm

1. Explain text, image, video, audio, embedding, and streaming text factories.
2. Explain provider schema translation for tools.
3. Mention credentials should come from caller configuration or environment.

#### Edge Cases & Error Handling

- Explain unsupported capability/provider pairs raise provider-selection errors.

### 6.12 Shared Layer README

**File(s):** `vidbyte/shared/README.md`
**Type:** New file

#### What it does

Documents `shared` as currently reserved.

#### Interface / API

```python
import vidbyte.shared
```

#### Logic / Algorithm

1. Explain that this namespace exists but currently exports no stable public symbols.
2. Direct users to root exports and `vidbyte.lib` for current contracts.

#### Edge Cases & Error Handling

- Avoid pretending there is an API where none exists.

### 6.13 Tools Layer README

**File(s):** `vidbyte/tools/README.md`
**Type:** New file

#### What it does

Documents tools as the bridge between model tool calls and local Python capabilities.

#### Interface / API

```python
from vidbyte import Agent, tool

@tool(permission="read")
def lookup_user(user_id: int) -> dict[str, int]:
    return {"user_id": user_id}

agent = Agent(name="tool-user", system_prompt="Use tools when useful.", runner=my_runner, tools=[lookup_user])
```

#### Logic / Algorithm

1. Explain `@tool`, `FunctionTool`, `BaseTool`, `Tools`, `ToolExecutor`, `ToolRegistry`, provider schemas, permissions, security, built-ins, and MCP attachment.
2. Recommend agent-local `tools=[...]` for new code.

#### Edge Cases & Error Handling

- Code snippets must use valid `ToolPermission` values or omit permission if a string value is uncertain during implementation.

### 6.14 Trace Layer README

**File(s):** `vidbyte/trace/README.md`
**Type:** New file

#### What it does

Documents runtime tracing and structured continual trace artifacts.

#### Interface / API

```python
from vidbyte import Agent, Trace

events = []
agent = Agent(name="debugged", system_prompt="Work carefully.", runner=my_runner, trace=Trace.debug(events))
```

#### Logic / Algorithm

1. Explain `Trace.off`, `Trace.debug`, `Trace.custom`, provider tracers, continual tracer, and `TraceOption.continual`.
2. Distinguish observability tracing from continual trace artifacts.
3. Mention fail-open behavior for trace artifacts where applicable.

#### Edge Cases & Error Handling

- Avoid saying continual trace writes into the main agent context; current README says it does not.

### 6.15 Verification Script

**File(s):** `scripts/test-github-content-readmes.py`
**Type:** New file

#### What it does

Verifies README coverage and required documentation structure.

#### Interface / API

```python
def main() -> int:
    # Runs Markdown coverage checks and exits non-zero if any check fails.
```

#### Logic / Algorithm

1. Define the required README file list.
2. For each file, assert it exists and is non-empty.
3. For public layer READMEs, assert `Vidbyte SDK`, `Role In The SDK`, `Design Philosophy`, `Usage`, and a Python code fence exist.
4. For `shared`, assert it clearly says reserved or currently exports no stable public symbols.
5. For the root README, assert Vidbyte positioning, layer links, and core capability keywords exist.
6. Print `PASS` or `FAIL` per case and `X/Y tests passed`.
7. Exit non-zero on failure.

#### Edge Cases & Error Handling

- Missing files fail explicitly with the missing path.
- Empty content fails explicitly.
- False-positive code fences are acceptable for this documentation-only verification; source correctness is handled by the audited design.

---

## 7. Data Model Changes

N/A - documentation-only change. No dataclasses, schemas, database tables, migrations, package data formats, prompt asset formats, or persisted state will change.

---

## 8. API Changes

N/A - no Python API, CLI entry point, MCP protocol method, HTTP endpoint, provider behavior, eval contract, pipeline contract, or package export changes.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/github-content-readmes.md` | Design-doc workflow source of truth for SDK README expansion |
| MODIFY | `README.md` | Reframe the SDK repository as a rich GitHub content surface |
| CREATE | `vidbyte/agents/README.md` | Explain the agent abstraction layer |
| CREATE | `vidbyte/context/README.md` | Explain context management and context-window abstractions |
| CREATE | `vidbyte/evals/README.md` | Explain local evaluation abstractions |
| CREATE | `vidbyte/harnesses/README.md` | Explain current and future harness integration boundary |
| CREATE | `vidbyte/lib/README.md` | Explain internal shared contracts and registries |
| CREATE | `vidbyte/mcp_server/README.md` | Explain the MCP Studio server layer |
| CREATE | `vidbyte/middleware/README.md` | Explain deterministic runtime middleware |
| CREATE | `vidbyte/pipelines/README.md` | Explain multi-agent pipeline topologies |
| CREATE | `vidbyte/prompts/README.md` | Explain prompt assets and prompt catalog usage |
| CREATE | `vidbyte/providers/README.md` | Explain model provider adapter factories |
| CREATE | `vidbyte/shared/README.md` | Explain reserved shared namespace status |
| CREATE | `vidbyte/tools/README.md` | Explain tool abstractions, catalogs, execution, and permissions |
| CREATE | `vidbyte/trace/README.md` | Explain tracing and continual trace artifacts |
| CREATE | `scripts/test-github-content-readmes.py` | Required verification script for README coverage |

Total: 15 files created, 1 file modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] `scripts/test-github-content-readmes.py` detects a missing required layer README and prints the missing path.
- [Edge Case] `scripts/test-github-content-readmes.py` detects an empty layer README.
- [Hidden Failure] `scripts/test-github-content-readmes.py` rejects a layer README that exists but lacks `Role In The SDK`.
- [Hidden Failure] `scripts/test-github-content-readmes.py` rejects a public layer README that lacks a fenced Python code block.
- [Silent Failure] `scripts/test-github-content-readmes.py` rejects a README that omits `Vidbyte SDK`, because the file could look complete while failing the cross-repo positioning requirement.
- [Silent Failure] `scripts/test-github-content-readmes.py` rejects the root README if the layer guide omits one of the required layer links.
- [Silent Failure] `scripts/test-github-content-readmes.py` rejects any SDK README that omits the `https://vidbyte.pro` website link.
- [Hidden Assumption] `scripts/test-github-content-readmes.py` verifies each layer README names `Vidbyte website`, because the docs assume readers should understand how the SDK relates to the hosted product.
- [Hidden Assumption] `scripts/test-github-content-readmes.py` checks `shared` separately because it assumes most layers are public but `shared` is currently reserved.
- [Hidden Assumption] `scripts/test-github-content-readmes.py` checks keyword coverage for MCP, tools, middleware, evals, providers, prompts, pipelines, context, agents, and trace.

### Integration Tests

- [Edge Case] Run `python scripts/test-github-content-readmes.py` from the repository root; it must print one PASS/FAIL line per documentation check and exit `0`.
- [Hidden Failure] Run `python -m compileall vidbyte` after the README additions to confirm no accidental Python source edits broke compilation.
- [Hidden Assumption] Run `python -m unittest discover -s tests` if the repository environment is available; docs should not affect runtime tests.
- [Silent Failure] Use local Markdown inspection to confirm code fences render as code blocks and tables render as tables, not as malformed plain text.

### Manual / QA Test Cases

1. [Edge Case] Open the root README and confirm a first-time reader can answer "what is Vidbyte?" within the first two sections.
2. [Edge Case] Open each layer directory on GitHub-style Markdown and confirm the README explains the layer without requiring navigation back to the root README.
3. [Hidden Failure] Compare every code snippet import path against the audited source exports before committing.
4. [Hidden Failure] Search for `sk-`, `vb_live_`, `token=`, `secret`, and `password` in README files to confirm no real-looking credentials are present.
5. [Silent Failure] Confirm `vidbyte/harnesses/README.md` and `vidbyte/shared/README.md` do not overstate currently empty/minimal APIs.
6. [Silent Failure] Confirm the root README does not claim awesome-list inclusion has already happened.
7. [Hidden Assumption] Confirm `vidbyte/mcp_server/README.md` calls the server a stdio subprocess server, not an HTTP service.
8. [Hidden Assumption] Confirm `vidbyte/middleware/README.md` notes middleware support applies to compatible direct/linear agent runtimes.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Verification script runtime and source API context | Low |
| `pydantic` | `>=2,<3` from `pyproject.toml` | Existing SDK dependency referenced by trace schema examples | Low; unchanged |
| `httpx` | `>=0.27` from `pyproject.toml` | Existing SDK dependency | Low; unchanged |
| External provider APIs | Various | Only relevant if readers run examples with real providers | Medium; examples must not embed credentials |
| MCP clients | Claude Code, Codex, Cursor, etc. | Consumers of `vidbyte-mcp-server` docs | Medium; docs should describe the protocol boundary accurately |

---

## 12. Rollout & Deployment

- Feature flags: N/A - documentation-only.
- Breaking change: No.
- Migration path: N/A.
- Deployment order after approval:
  1. Create isolated worktree from up-to-date `main`.
  2. Commit this design doc first.
  3. Add/modify README files from the manifest.
  4. Add and run `scripts/test-github-content-readmes.py`.
  5. Run relevant existing verification if environment allows.
  6. Commit documentation and verification script.
- Rollback procedure: Revert the documentation and script commits. No runtime rollback is required.

---

## 13. Open Questions

- [ ] Should nested public subpackages such as `vidbyte/tools/mcp`, `vidbyte/tools/security`, `vidbyte/middleware/builtins`, `vidbyte/context/primitives`, and `vidbyte/agents/runtimes` get their own README files in this PR, or should this first pass stay at top-level abstraction layers only?
- [ ] Should `vidbyte/shared/README.md` be included as a reserved namespace doc, or should empty/reserved namespaces be omitted from public content surfaces?
- [ ] Should the root README include a short "Awesome Lists" section describing suggested categories and repository positioning, or should that stay out of the repository until a separate submission task?

---

## 14. Alternatives Considered

### Alternative 1: Root README Only

- What: Expand only `README.md`.
- Why rejected: The user explicitly asked for README files at each SDK abstraction layer, and GitHub folder README rendering is useful when readers land in subdirectories.

### Alternative 2: README For Every Directory

- What: Add README files to every nested package directory under `vidbyte/`.
- Why rejected: The first pass would create a large amount of repetitive documentation and increase maintenance risk. Top-level abstraction layers match the user's examples and cover the primary GitHub content surface.

### Alternative 3: Generate READMEs From Source Comments

- What: Build README content mechanically from docstrings and context-protocol headers.
- Why rejected: Source comments are implementation-oriented. The request needs explanatory developer content, design philosophy, and examples, which are better written deliberately from audited APIs.

### Alternative 4: Add Awesome-List Submissions In The Same PR

- What: Submit PRs to external awesome lists alongside README changes.
- Why rejected: External submissions are outside this repo and require separate repository policies, contributor guidelines, and network/current-state review. This design only prepares the content surface.
