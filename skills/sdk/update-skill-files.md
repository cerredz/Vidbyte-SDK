# Update Skill Files

When you change the Vidbyte SDK repository, you must update the corresponding skill files so documentation stays accurate. This reference maps every type of change to the exact files and sections you need to update.

## How To Use This Skill

1. Identify what type of change you made (add tool, add pipeline, add strategy, etc.).
2. Find that change type in the table below.
3. Update every file listed with the specified content.

---

## Change Type → Skill File Matrix

### Add a New Tool Category

**Example:** Creating `vidbyte/tools/builtins/image_generation/` with `ImageGenTool`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_tools.md` | New section with category name, import path, tool table (name, description), and code example showing usage |
| `skills/usage/create_agent_with_tools.md` | Add example in the Built-in Tools or a new subsection showing how to attach the new tools to an agent |
| `skills/usage/available_features.md` | Reference in the Tools section linking to the tools catalog |
| `skills/sdk/SKILL.md` | Add the category name to the "built-in tool categories" rule; update Framework Boundaries if the tools introduce a new concept |

### Add or Change Durable Sessions

**Example:** Adding `Session.batch_fork`, portable session bundles, usage rollups, or tag lookup.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/sessions.md` | Public API, code examples, checkpoint policy, tool binding, tags, usage, export/import, and rules of thumb |
| `skills/forking.md` | Fork/resume semantics, lineage, batch fork behavior, and cross-agent patterns |
| `skills/usage/available_features.md` | Durable Sessions feature summary and key APIs |
| `skills/usage/available_tools.md` | Session tools table if model-callable tools changed |
| `skills/usage/create_agent.md` | `agent.persist(...)`, `agent.session`, or constructor-related session entry points |
| `README.md` | Central durable-session examples and package/layer guide |
| `llms.txt` | Agent-facing summary, imports, feature map, and design-doc links |
| `skills/sdk/SKILL.md` | Framework boundary, package rules, and built-in tool category rules |
| `skills/vidbyte-sdk-doc/SKILL.md` | Public import surface, package map, design-doc references, and test map |

### Add or Change Agent Forking

**Example:** Adding `ForkConversationTool` or changing `BaseAgent.fork(...)` non-escalation rules.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/forking.md` | Distinguish immediate agent-native forks from durable session DAG forks |
| `skills/usage/available_tools.md` | Agent Forking tool section and safety boundaries |
| `skills/usage/create_agent_with_tools.md` | Code example attaching `ForkConversationTool` |
| `skills/usage/available_features.md` | Agent Forking feature notes |
| `README.md` | Tool catalog or agent-forking overview |
| `llms.txt` | Agent-facing summary and imports |
| `skills/sdk/SKILL.md` | Built-in tool category and non-escalation rules |

### Add or Change Tool Error Policy

**Example:** Adding `ToolErrorPolicyMiddleware` or changing `AgentLoopSettings.tool_error_policy`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/middleware.md` | Built-in catalog entry, count, arguments, and rendering semantics |
| `skills/usage/available_features.md` | Middleware summary and code example |
| `skills/usage/create_agent.md` | `AgentLoopSettings` example and constructor docs |
| `README.md` | Middleware overview and loop-settings example |
| `llms.txt` | Agent-facing feature summary and correct import paths |
| `skills/sdk/SKILL.md` | Middleware rules and removed/stable API notes |
| `skills/vidbyte-sdk-doc/SKILL.md` | Public import surface and tests/design docs |

### Add or Change Repository Artifacts

**Example:** Adding or regenerating `artifacts/file_index.md`.

**Files to update:**

| File | What to add |
|------|-------------|
| `artifacts/file_index.md` | Regenerated or newly documented artifact content |
| `README.md` | Central reference for why the artifact exists and who uses it |
| `llms.txt` | Agent-facing retrieval/navigation guidance |
| `skills/sdk/SKILL.md` | Repository-artifact maintenance rule |
| `skills/vidbyte-sdk-doc/SKILL.md` | Package map or playbook entry |

### Add a New Individual Tool (within existing category)

**Example:** Adding a `SummarizeTool` to `vidbyte/tools/builtins/context/`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_tools.md` | Add the tool to the existing category's tool table with name, description, and import |
| `skills/usage/create_agent_with_tools.md` | Add to an existing example or create a new inline example if the tool has novel usage |

### Add a New Pipeline Topology

**Example:** Creating `vidbyte/pipelines/map_reduce.py` with `MapReducePipeline`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/create_pipeline.md` | New section: name, description of what it does, constructor signature, code example, error handling table entries |
| `skills/usage/available_features.md` | Add the pipeline type to the Pipelines section with description and import |
| `skills/vidbyte-sdk/pipelines.md` | New topology subsection under Topology Types with description, code example, composability notes, and error handling; add entry to Error Handling table; update Module Layout |
| `skills/sdk/SKILL.md` | Add the new file to Current Layout tree; update the pipelines rule if the new type introduces a new pattern |

### Add a New Context-Window Algorithm

**Example:** Creating `vidbyte/context/algorithms/graph_reflexion.py` + `vidbyte/agents/algorithms/graph_reflexion.py` with a `ContextWindow.preset.graph_reflexion`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/adding-context-window-algorithms.md` | This is the process reference — follow it; confirm the steps are still accurate |
| `skills/vidbyte-sdk-doc/SKILL.md` | Add to the Context-Window Algorithms section (public config export + adapter path) |
| `skills/sdk/SKILL.md` | Update Framework Boundaries / Core Use Cases if it introduces a new concept |
| `skills/vidbyte-sdk/context-algorithm-to-tool.md` | Add a worked example if you also ship a model-callable tool form |

### Add a New Agent Runtime

**Example:** Creating a new runtime under `vidbyte/agents/runtimes/` with an `AgentRuntimeType` value.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/agent-runtimes/SKILL.md` | Add the runtime, its topology, and middleware/algorithm compatibility |
| `skills/usage/create_agent.md` | Add the `AgentRuntimeType` value to the `runtime` parameter docs |
| `skills/vidbyte-sdk-doc/SKILL.md` | Add to the Agent Runtimes section |

### Add a New Prompt Family

**Example:** Adding `vidbyte/prompts/prompts/code_review.json` with `code_review` prompts.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/import_prompt.md` | Add the new family section to the Complete Prompt Listing; add enum names + direct imports; update the family/prompt counts in the header |
| `skills/vidbyte-sdk/adding-prompts.md` | (This doc is the process reference; confirm the steps are still accurate) |
| `skills/sdk/SKILL.md` | Update the prompt-family count in Core Use Cases (currently 13) |
| `skills/usage/available_features.md` | Update the prompt-family count in the Prompt Collection section |
| `skills/vidbyte-sdk-doc/SKILL.md` | Update the "Current prompt families" list |

### Add a New Agent Constructor Parameter

**Example:** Adding `max_history_tokens: int | None = None` to `Agent.__init__`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/create_agent.md` | Add to Agent Constructor signature; add a short section explaining what it controls and code example |
| `skills/sdk/SKILL.md` | Update Framework Boundaries if the parameter represents a new layer concept; update rules if it changes conventions |

### Add a New Agent Method

**Example:** Adding `agent.export_history() -> list[AgentMessage]`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/create_agent.md` | Add to a relevant section (or new section) with a description and code example |
| `skills/usage/create_agents.md` | Add example if the method is relevant to multi-agent workflows |

### Add a New Middleware Built-in

**Example:** Creating `vidbyte/middleware/builtins/content_filter.py` with `ContentFilterMiddleware`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/middleware.md` | Add to the Built-in Middleware Catalog with class, module, purpose, and arguments; update the count |
| `skills/usage/available_features.md` | Add to the Built-in Middleware list |
| `skills/sdk/SKILL.md` | Add to the Built-in Middleware paragraph; if it is also a root export, note it |
| `skills/vidbyte-sdk-doc/SKILL.md` | Add to the Middleware bullet in the Public Import Surface if it becomes a root export |

### Add a Compaction Middleware or Strategy

**Example:** Adding a new compaction strategy under `vidbyte/middleware/compaction/strategies.py`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/middleware.md` | Add to §5.1 Context Compaction Middleware |
| `skills/usage/available_tools.md` | If it changes the compaction story, update the legacy-tool note in the Context section |

### Add a Memory Tool Provider

**Example:** Adding `vidbyte/tools/builtins/memory/<provider>.py`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/memory-tools.md` | Add the provider and its tool family + constructor notes |
| `skills/usage/available_tools.md` | Add a row to the Memory section table |

### Add a Context Primitive or Context Tool

**Example:** Adding a new `ContextItem` in `vidbyte/context/primitives/` or a tool in `vidbyte/tools/builtins/context_primitives/`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/context-primitives.md` | Document the primitive/tool and its placement/usage |
| `skills/usage/available_tools.md` | Add the tool to the Context Primitives section if model-callable |
| `skills/vidbyte-sdk/context-algorithm-to-tool.md` | Add a worked example if it has both an algorithm and a tool form |

### Add an Eval Grader

**Example:** Adding `vidbyte/evals/graders/semantic.py` with `SemanticGrader`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/vidbyte-sdk/evals.md` | Add the grader to the Grader Catalog and follow the "Adding a New Grader" steps |

### Add Support for a New Model Provider

**Example:** Adding `ModelProvider.COHERE` and `vidbyte/providers/cohere.py`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_features.md` | Add the provider to the Provider Support section |
| `skills/sdk/SKILL.md` | Add to the Provider row in Framework Boundaries |

### Add a New Modality

**Example:** Adding `ModelModality.AUDIO`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_features.md` | Add to Modality Routing section |
| `skills/usage/create_agent.md` | Add to modality parameter docs and AgentInput examples |
| `skills/sdk/SKILL.md` | Update Framework Boundaries as needed |

### Add New MCP Functionality

**Example:** Adding `agent.list_mcp_servers()` method.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_tools.md` | Update MCP Bridge section with new types or usage |
| `skills/usage/available_features.md` | Update MCP Server Attachment section with new code examples |
| `skills/usage/create_agent.md` | Add example if agent-level API is involved |

### Change the Package Structure (move/rename/delete modules)

**Example:** Renaming `vidbyte/lib/` to `vidbyte/_internal/`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/sdk/SKILL.md` | Update Current Layout tree and every rule referencing the old path |
| `skills/vidbyte-sdk-doc/SKILL.md` | Update Package Map |
| `skills/vidbyte-sdk/pipelines.md` | Update Module Layout if pipeline paths changed |
| **All usage skill files** | Update any import paths that reference moved modules |

### Add a New Built-in Tool Category Under `vidbyte/tools/builtins/`

**Example:** Creating `vidbyte/tools/builtins/web_search/`.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_tools.md` | New section with category description, import path, tool table |
| `skills/usage/create_agent_with_tools.md` | Add import + usage example |
| `skills/usage/available_features.md` | Reference in Tools section |
| `skills/sdk/SKILL.md` | Add category to built-in tool categories rule; update Current Layout |

### Add New Permissions or Security Abstractions

**Example:** Adding `PermissionPreset.CUSTOM` with user-defined rules.

**Files to update:**

| File | What to add |
|------|-------------|
| `skills/usage/available_features.md` | Update Context Budgets & Permissions section |
| `skills/usage/create_agent_with_tools.md` | Update Permission Policy section |
| `skills/usage/create_tool.md` | Update Permission Levels section |
| `skills/sdk/SKILL.md` | Update relevant rules |

---

## Example Scenario

**When we add a new tool category called `web_search`:**

| Step | File | Change |
|------|------|--------|
| 1 | `skills/usage/available_tools.md` | Add `## Web Search` section with import, tool table (`WebSearchTool`, `ScrapeTool`) |
| 2 | `skills/usage/create_agent_with_tools.md` | Add web search example under Built-in Tools |
| 3 | `skills/usage/available_features.md` | Add `## Tools` section reference to web search |
| 4 | `skills/sdk/SKILL.md` | Add `web_search` to built-in tool categories rule; add `web_search/` to Current Layout |

---

## Verification Checklist

After updating skill files, verify:

- [ ] Every import path in code examples matches the current package structure
- [ ] Every file path reference (`[link](path)`) resolves to an existing file
- [ ] Every `from vidbyte import ...` example compiles against the current SDK
- [ ] All constructor signatures match the current `BaseAgent.__init__` parameter list
- [ ] All provider names match the current `ModelProvider` enum (10 members: openai, anthropic, gemini, xai, deepseek, glm, minimax, openrouter, elevenlabs, playai)
- [ ] All `Prompt.<X>` enum names and direct imports resolve (13 families / 34 prompts)
- [ ] No skill references the removed `vidbyte/strategies/` package, `sdk.strategies`, removed Strategy classes, or the old `MiddlewareDecision.ALLOW/BLOCK/SKIP` API
- [ ] All tool names match the current tool files
- [ ] Session changes mention `agent.persist`, session tools, `BatchForkTool`, tag lookup, usage rollups, and portable export/import where applicable
- [ ] Agent-forking changes distinguish durable session forks from immediate `ForkConversationTool` execution and preserve non-escalation rules
- [ ] Tool-error-policy docs use `AgentLoopSettings(tool_error_policy=ToolErrorPolicy(...))` and do not mention removed verbosity/render-options APIs
- [ ] Repository artifacts such as `artifacts/file_index.md` are listed in README/llms when they are agent-facing
- [ ] The Usage Skill Files table in `skills/sdk/SKILL.md` lists all usage files
- [ ] The SDK Developer Reference table in `skills/sdk/SKILL.md` lists all reference docs (including evals, memory-tools, context-primitives, middleware, agent-runtimes)

---

## Rules

- Update skill files immediately when the corresponding code changes land — not in a follow-up PR.
- Do not delete or rename existing sections in usage skill files unless the underlying feature is removed.
- When adding a new file to the skills directory, add a row to at least one reference table.
- Keep code examples compilable. If an import or API changes, update every example that uses it.
- If a change affects multiple skill files, update them all in the same commit.
