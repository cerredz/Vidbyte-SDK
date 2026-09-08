# Design Doc — Codex Custom Tools (`CodexHarnessAgent` + Vidbyte tools)

## 1. Overview

Give `CodexHarnessAgent` a real custom-tool seam so Vidbyte `BaseTool` definitions can be translated once and used with Codex-owned turns. Today the harness has no tools field at all: `CodexHarnessAgentSettings` carries only name, system prompt, codex client/thread/turn/subagents, context, and output schema, and `CodexRunInput` carries only text/image/local-image/skill/mention items. The pinned `openai-codex 0.147` SDK also exposes no `tools=` parameter on `thread_start` or `thread.run`, so even a perfect schema translation has nowhere to go natively.

This change adds the Vidbyte-side seam without pretending the upstream seam exists: a frozen `CodexToolDefinition` data record in `lib`, a translator plus prompt renderer plus MCP-config builder plus outer-loop executor in `vidbyte/agents/codex/tools.py`, an optional `tools=` constructor path on the facade, and fork propagation. That unblocks three real usages today (prompt-described tools with outer-loop execution, MCP sidecar servers, and a ready native slot when the SDK opens one) and directly serves the `vidbyte-cli` task-board `decompose_tool`.

## 2. Goals / Non-Goals

### Goals

- Add a frozen, validated `CodexToolDefinition(name, description, input_schema)` record in `lib/dataclasses/codex.py` with no tool imports.
- Add `CodexToolTranslator` that converts `BaseTool`/`ToolLike` objects into definitions via `spec()`, failing fast on blank names, short descriptions, and non-JSON schemas.
- Render tool schemas into deterministic developer-context text the Codex model can actually read, since native function calling is unavailable.
- Build an MCP-server config block (`mcp_servers`) from definitions so Codex can call the tools natively as MCP tools through a sidecar.
- Execute tool calls in-process through the existing `Tools` catalog semantics (`validate_call` then `execute`) for the outer-loop pattern.
- Propagate tools across `afork`/`fork` with inherit/replace/clear semantics matching `context_manager`.
- Export the new surface from `vidbyte/agents/codex/__init__.py` without breaking existing imports.

### Non-Goals

- N/A — Pumping native `dynamicToolCall`/`customToolCall` turn-stream events requires an upstream `openai-codex` registration seam that does not exist in 0.147, so no transport event loop is built here.
- N/A — No permission-policy or middleware re-architecture; execution reuses `BaseTool.validate_call` and caller-owned catalogs.
- N/A — No new built-in tools ship here; the CLI owns `decompose_tool` semantics.

## 3. Background

`CodexHarnessAgent` (`vidbyte/agents/codex/agent.py`) is a thin facade over the Codex app-server: construction translates Vidbyte settings once, `arun` translates context, `CodexTransport.run` opens a client, starts or resumes one thread, runs one turn, and `CodexResultSerializer` copies `TurnResult` into bounded `CodexItem`s. `CodexContentTranslator` maps only five input modalities. `TurnResult.items` already passes through `mcpToolCall` and `dynamicToolCall` item types, so executed MCP-tool history is observable even though registration is not.

`BaseAgent` owns the opposite loop in `vidbyte/agents/runtime.py`: it sends provider tool schemas, executes permitted calls, and folds results into history. `BaseTool` (`vidbyte/tools/base.py`) pairs `spec()` with `async execute(call)`, and `Tools` catalogs validate and prepare calls. The field guide requires class-bound helpers, strict config dataclasses, model-facing tool contracts with 4–5 sentence descriptions, and blocking lint invariants including `A006` (nothing in `lib` may import `tools`).

## 4. Requirements

### Functional

- R1: `CodexToolDefinition` is frozen, slots, validated: non-empty name matching `[A-Za-z0-9_-]{1,64}`, description 4+ sentences, `input_schema` a JSON-compatible mapping with `type: object`.
- R2: `CodexHarnessAgent(settings, tools=())` accepts `BaseTool`/`ToolLike`/existing definitions; construction translates once and stores `self.tool_definitions: tuple[CodexToolDefinition, ...]` plus a private catalog for execution.
- R3: `describe_tools()` returns deterministic text (`Tool: <name>\nDescription: ...\nArguments: {...}` joined by blank lines) for developer-context injection; empty tools return `""`.
- R4: `build_mcp_config(command, *, server_name="vidbyte-tools")` returns `{"mcp_servers": {server_name: {"command": command, "tools": [names]}}}` for thread-config passthrough.
- R5: `execute_tool_call(name, arguments)` validates against the catalog (`validate_call`), executes `BaseTool.execute` with a constructed `ToolCall`, and returns `ToolResult`; unknown tools raise `ConfigurationError`.
- R6: Fork inherits parent tool definitions by default; `CodexForkSettings` gains `tools: tuple[...] | None` plus `clear_tools: bool` with cannot-clear-and-replace validation.
- R7: All new validation failures raise `ConfigurationError` (typed-boundary rule), never raw `ValueError`.

### Non-functional

- Zero network or SDK imports in translator/config-builder unit paths; `openai-codex` stays optional.
- `mypy strict`, `ruff check`, `ruff format`, `python lint/run.py`, and `python scripts/run_ci.py --stage source` green.
- No secrets in errors; tool schemas never log argument values.

## 5. High-Level Design

One new collaborator class plus data records, following the existing per-file collaborator pattern. `lib` owns data only; `agents/codex` owns behavior. The facade composes the translator at construction and exposes three read paths (prompt text, MCP config, in-process execution) that three different callers use: CLI outer loops use prompt plus execution, sidecar deployments use MCP config, and a future native pump reuses the same definitions.

Flow: caller builds `BaseTool`s → passes to `CodexHarnessAgent(settings, tools=[...])` → translator converts via `spec()` → facade stores definitions plus catalog → per turn the caller appends `describe_tools()` to developer context (or merges MCP config into thread config) → model names a tool plus args in its response or MCP call → caller invokes `execute_tool_call` → feeds `ToolResult.output` back as the next turn's input.

## 6. Detailed Design

### 6.1 Data (`vidbyte/lib/dataclasses/codex.py`)

Class `CodexToolDefinition(frozen, slots)` with `name: str`, `description: str`, `input_schema: Mapping[str, Any]`. Validators: name regex, description must contain 4+ sentence terminators and 20+ words, schema must be a mapping with `type == "object"` and JSON-compatible values (reuse local `_is_json_value`). Extend `CodexHarnessAgentSettings` with `tools: tuple[CodexToolDefinition, ...] = ()` plus tuple-of-definitions validation. Extend `CodexForkSettings` with `tools: tuple[CodexToolDefinition, ...] | None = None` and `clear_tools: bool = False` with mutual-exclusion checks.

### 6.2 Behavior (`vidbyte/agents/codex/tools.py`)

Class `CodexToolTranslator` with methods (single-line signatures, 1–2 line comment under each):

- `from_sdk_tools(tools)` — accepts `BaseTool` (via `spec()`), `ToolLike` (via `spec()`), or existing `CodexToolDefinition` passthrough; returns sorted-by-name tuple; raises `ConfigurationError` on duplicates or bad specs.
- `to_prompt_block(definitions)` — deterministic rendering for developer context; empty returns `""`.
- `to_mcp_config(definitions, command, server_name)` — returns the `mcp_servers` mapping; validates non-empty command.
- `build_call(tool_name, arguments)` — constructs a `ToolCall` record for execution.
- `validate_schema_compatibility(spec)` — JSON-compatibility plus object-shape check used by the translator.

Class `CodexToolExecutor` wrapping a caller-owned catalog mapping name to `BaseTool`:

- `has_tool(tool_name)` — membership check.
- `execute_tool_call(tool_name, arguments)` — async; looks up the tool, runs `validate_call`, raises `ConfigurationError` on validation failure, otherwise awaits `execute` and returns `ToolResult`.

### 6.3 Facade (`vidbyte/agents/codex/agent.py`)

`__init__(self, settings, tools=())` — second parameter is a sequence of tool inputs; translates via `CodexToolTranslator.from_sdk_tools`, merges with `settings.tools` (explicit param wins when non-empty, else settings), stores `self.tool_definitions` and `self._tool_executor` built from the `BaseTool` subset (definitions without implementations are describable but not executable). New methods `describe_tools()`, `build_mcp_config(command, server_name)`, `has_tool(tool_name)`, and `execute_tool_call(tool_name, arguments)` delegate to the collaborator classes. `afork`/`fork` propagate `self.tool_definitions` through `CodexForkSettings(tools=...)` unless overrides specify otherwise.

### 6.4 Exports (`vidbyte/agents/codex/__init__.py`)

Export `CodexToolDefinition`, `CodexToolTranslator`, `CodexToolExecutor` alongside existing names.

### 6.5 Untouched layers

`transport.py`, `context.py`, `result.py`, `config.py` wire code unchanged except where imports demand it. No new provider behavior, no pricing, no tracing changes.

## 7. Data Model Changes

- N/A — No database, ledger, or backend DTO changes.
- Python-only: `CodexToolDefinition` plus `tools` fields on `CodexHarnessAgentSettings` and `CodexForkSettings` (§6.1).

## 8. API Changes

- N/A — No HTTP routes or CLI surface changes.
- Python surface only: `CodexHarnessAgent(..., tools=...)`, `describe_tools`, `build_mcp_config`, `execute_tool_call`, plus the two new collaborator classes.

## 9. File Change Manifest

- CREATE `docs/design/codex-custom-tools.md` — this doc.
- CREATE `vidbyte/agents/codex/tools.py` — translator, prompt renderer, MCP config builder, executor.
- CREATE `scripts/test-codex-custom-tools.py` — Phase 5 verification script.
- CREATE `tests/test_codex_custom_tools.py` — pytest suite mirroring the script.
- MODIFY `vidbyte/lib/dataclasses/codex.py` — tool definition plus settings/fork fields and validators.
- MODIFY `vidbyte/agents/codex/agent.py` — tools constructor path plus delegate methods.
- MODIFY `vidbyte/agents/codex/__init__.py` — exports.
- MODIFY `vidbyte/agents/codex/fork.py` — tool propagation on fork.
- MODIFY `vidbyte/__init__.py` — top-level re-exports if the pattern requires it.

Count: create 4, modify 5, delete 0.

## 10. Testing Plan

Executed via `scripts/test-codex-custom-tools.py` (offline, no SDK import) plus `tests/test_codex_custom_tools.py` in the full gate.

- [Edge Case] Empty tools tuple constructs, describes as `""`, and builds no MCP entries.
- [Edge Case] Single tool with minimal valid 4-sentence description and `{type: object}` schema translates.
- [Edge Case] Tool name at 64 chars passes; 65 chars rejected.
- [Hidden Failure] Duplicate tool names across mixed `BaseTool` plus definition inputs rejected at construction, never silently deduplicated.
- [Hidden Failure] `execute_tool_call` on unknown name raises `ConfigurationError` rather than returning empty output.
- [Hidden Failure] `validate_call` failure surfaces as `ConfigurationError` before any `execute` runs (assert via recording fake).
- [Silent Failure] `to_prompt_block` ordering is name-sorted so repeated runs render byte-identical text.
- [Silent Failure] `to_mcp_config` includes exactly the translated names, never extra catalog entries.
- [Silent Failure] Fork inherits parent tools by default; `clear_tools=True` with replacement tools rejected.
- [Hidden Assumption] Non-JSON schema values (e.g. `set`, bytes) rejected at translation, not at turn time.
- [Hidden Assumption] Blank or short (<4-sentence) descriptions rejected at translation per model-facing contracts.
- [Hidden Assumption] `lib/dataclasses/codex.py` imports no `vidbyte.tools` symbols (assert via module import scan for `A006`).
- [Hidden Assumption] Task text containing `{{...}}` braces passes through prompt rendering uninterpolated.

## 11. Dependencies

- In-repo only: `vidbyte.tools` (`BaseTool`, `ToolCall`, `ToolResult`), `vidbyte.lib` dataclasses and errors.
- No new packages; `openai-codex` stays an optional extra with no version bump.

## 12. Rollout

1. Land the seam behind default empty tools; existing `CodexHarnessAgent(settings)` constructions behave identically.
2. Prove offline: run the new script plus `pytest tests/test_codex_custom_tools.py`.
3. Run `python lint/run.py`, then full `python scripts/run_ci.py --stage source` before PR.
4. CLI follows up by passing its `decompose_tool` through this seam.

## 13. Open Questions

- Q1: What exact `mcp_servers` config shape does the pinned app-server honor, and does `experimental_api=True` unlock more?
- Q2: Should tool subsets be allowlisted per harness, and how do Vidbyte `PermissionPolicy` plus Codex `approval_mode`/`sandbox` compose?
- Q3: When upstream adds native registration, do executed outputs become new `CodexItem` types or folded text?

## 14. Alternatives Considered

- A1: Put `BaseTool` objects directly on `CodexHarnessAgentSettings`. Rejected because `lib` must never import `tools` (`A006`); settings hold translated data, the agent layer holds implementations.
- A2: Build the native turn-stream pump now. Rejected because 0.147 exposes no registration or event seam; the definitions are shaped so the pump can land later without re-translation.
- A3: Standalone functions instead of collaborator classes. Rejected per field-guide class-bound-helper restraint and to keep fork/context/transport boundaries clean.
