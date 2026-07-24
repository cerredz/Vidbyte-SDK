# Design Doc: llms.txt Agent, Context, and Built-in Tool Reference

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-18
**Last Updated:** 2026-07-18

---

## 1. Overview

Add one source-backed `llms.txt` reference section covering Vidbyte agent output contracts, structured output, handoffs, loop settings, context-window primitives and management, and every current built-in tool. This is a Markdown-only update: no SDK behavior or public imports change.

---

## 2. Goals & Non-Goals

### Goals

- Document `AgentMessage`, `output_schema`, `OutputContract`, all prebuilt output-contract floors, and their linear-runtime termination behavior.
- Document automatic and explicit handoffs, their result/agent attributes, the handoff presets, and `CreateHandoffTool`.
- Enumerate `AgentLoopSettings`, `ToolSettings`, and `ToolErrorPolicy` configuration surfaces and validation boundaries.
- Document `ContextManager`, all public primitives, placements, and `ContextWindow` presets.
- List every concrete tool under `vidbyte/tools/builtins/` by category and distinguish agent-callable tools from support types.

### Non-Goals

- Change Python source, runtime control flow, package exports, tests, or release configuration.
- Enable, register, or configure any tool automatically.
- Promise availability of external MCP, memory, database, or provider services.
- Rewrite unrelated `llms.txt` sections.

---

## 3. Background & Context

The clean `main` worktree is authoritative. It contains output contracts that are absent from the dirty source worktree first audited: `AgentLoopSettings.output_contracts` owns `OutputContract` instances through `AgentLoopSettingsOutputContract`; the linear runtime rejects premature finalization, adds corrective feedback, and records `contract_evaluations` metadata. `output_schema` is a separate response-format and validation surface.

The current `llms.txt` has partial agent, handoff, context, and tool coverage, but not a complete index of these requested APIs. The package is Python 3.11+ with setuptools, Pydantic, and HTTPX. `scripts/run_ci.py` exists on `main`, so the required SDK CI gate is available after implementation.

---

## 4. Requirements

### Functional Requirements

1. Add one additive section to `llms.txt` beside the existing agent and tool guidance.
2. Document `AgentMessage(sender, recipient, content, message_type, metadata)` and distinguish `output_schema` from output contracts.
3. Document `OutputContract`, `AgentLoopSettingsOutputContract`, `output_contracts`, `max_contract_rejections`, `AgentStopReason.CONTRACT_UNSATISFIED`, corrective feedback at both linear-runtime terminal boundaries, and `AgentResult.metadata["contract_evaluations"]`.
4. Enumerate every current output-contract floor: `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds`, `MinTimeTaken`, `MinSuccessfulToolCalls`, `MinDistinctTools`, `MinFinalOutputChars`, `MinFinalOutputTokens`, `MinToolCallsById`, `MinCompactions`, and `MinCostSpent`.
5. Document handoff configuration (`BaseAgent(handoff=...)`), explicit `await agent.handoff(...)`, `last_handoff`, `handoffs`, successful automatic-reply metadata `handoff`, `HandoffAgent`, `Handoff`, `MinimalHandoff`, `EngineeringHandoff`, `ResearchHandoff`, and `CreateHandoffTool`.
6. Enumerate `AgentLoopSettings`: `max_iterations`, `max_tokens`, `max_tool_calls`, `max_queued_prompts`, `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`, `tool_error_policy`, `tool_settings`, `output_contracts`, and `max_contract_rejections`.
7. State the settings validation rules: positive limits, positive `timeout_seconds`, `compaction_target_tokens < compaction_trigger_tokens`, nested type validation, `ToolSettings.max_calls` agreement with `max_tool_calls`, and output-floor/ceiling compatibility where defined.
8. Document `ToolSettings` and `ToolErrorPolicy` as nested configuration objects rather than claiming their fields are top-level `AgentLoopSettings` arguments.
9. Document `ContextManager` unmanaged (`add`, `extend`, `remove`, `clear`, `items`, `by_kind`, `to_context`) and managed (`upsert`, `get_by_id`, `remove_by_id`, `clear_registry`, `place_after_system_prompt`, `place_after_tools`, rendering) APIs, frozen primitive protection, and all four `ContextWindowPlacement` values.
10. Enumerate all current public context primitives by their source groups: documents/records/tasks, checkpoint/reasoning, multi-agent, framing, epistemics, decisions, execution, and closure. The catalog must name every concrete `*ContextItem` re-exported by `vidbyte.context.primitives` and identify `MultiAgentContextSerializer` as support API rather than a primitive.
11. List `ContextWindow.preset`: `default` / `raw_tool_outputs`, `compact_tool_outputs`, `hide_tool_outputs` / `no_raw_tool_outputs`, `reflexion`, `multi_provider_agentic_grader`, `prosecutor_defender_judge`, `independent_critic`, `trajectory_checkpoints`, `problem_space_search`, and `error_correction`, including the non-linear-runtime restriction for non-default algorithms.
12. Catalog every concrete tool shipped by the SDK's built-in and filesystem tool packages, grouping it by capability and marking `CalculatorTool` and `DocumentRetrievalTool` as direct-module imports when applicable.
13. State that tools are explicit agent-local instances subject to `PermissionPolicy`; tool family builders, registries, and result/schema types are support APIs rather than tools to pass directly to an agent.

### Non-Functional Requirements

- **Accuracy:** Current `main` source and tests are authoritative.
- **Maintainability:** Use tables and capability groups; preserve one local documentation block for this inventory.
- **Performance:** N/A - Markdown-only change.
- **Security:** Include permission and external-service caveats; include no credentials.
- **Observability:** N/A - no behavior changes.
- **Reliability:** Preserve all existing `llms.txt` content and make no claims beyond source behavior.

---

## 5. High-Level Design

Insert a new `### Agent Output Contracts, Handoffs, Context, and Built-ins` section after the existing tools description and before middleware. Its subsections will cover output contracts/structured output, handoffs and settings, context management, and the complete tool catalog.

```text
AgentLoopSettings(output_contracts) -> AgentLoopSettingsOutputContract
  -> linear runtime terminal check -> feedback or final AgentResult.metadata

BaseAgent(handoff) -> HandoffAgent -> last_handoff / handoffs / reply metadata
ContextManager + primitives -> ContextWindow placement and presets
Explicit Agent(tools=[...]) + PermissionPolicy -> built-in tool execution
```

---

## 6. Detailed Design

### 6.1 llms.txt reference section

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Adds the requested complete LLM-facing API reference without changing code.

#### Interface / API

```markdown
### Agent Output Contracts, Handoffs, Context, and Built-ins

#### Output contracts and structured output
#### Handoffs and loop settings
#### ContextManager and context windows
#### Complete prebuilt-tool catalog
```

#### Logic / Algorithm

1. Preserve the current surrounding `llms.txt` prose and insert the new section at the approved location.
2. Explain output contracts as minimum effort floors before finalization, separately from `output_schema` formatting/validation.
3. List the output, handoff, settings, context, and tool symbols required in Section 4 from their source packages, including all current primitive groups rather than only the original document/task/checkpoint subset.
4. Present concrete built-ins by these groups:
   - Utilities/search: `CalculatorTool`, `CodeExecutionTool`, `DocumentRetrievalTool`, `GlobTool`, `GrepTool`, `SemanticSearchTool`.
   - Filesystem: `AppendTool`, `ChecksumTool`, `CopyTool`, `DeleteTool`, `DiffTool`, `ExistsTool`, `FindTool`, `ListDirTool`, `MakeDirTool`, `MoveTool`, `RenameTool`, `ReadBinaryTool`, `ReadLinesTool`, `ReadTextTool`, `ReplaceTextTool`, `StatTool`, `TouchTool`, `TreeTool`, `UnzipTool`, `WriteTextTool`, and `ZipTool`.
   - Context: `ContextCompactionTool`, `CreateContextPrimitiveTool`, `ContextEditTool`, `ContextListTool`, `ContextMoveTool`, `ContextReciteTool`, `ContextRemoveTool`, `ContextStatsTool`, `ContextUpsertTool`, `ReflexionTool`, `TrajectoryCheckpointTool`.
   - Output/handoff/control: `DeclareOutputSchemaTool`, `AppendOutputTool`, `ExtendOutputSchemaTool`, `PatchTool`, `ForkConversationTool`, `CreateHandoffTool`, `RunPromptsSequentiallyTool`.
   - MCP: `SearchMcpServersTool`, `AttachMcpServerTool`.
   - Sessions: `SessionTool`, `CheckpointTool`, `ForkTool`, `BatchForkTool`, `RewindTool`, `ResumeReplaceTool`, `ResumeAppendTool`, `ResumeOutputTool`.
   - Provider/database: `MongoCreateCollectionTool`, `MongoCreateIndexTool`, `MongoInsertDocumentTool`, `MongoFindDocumentsTool`, `MongoUpdateDocumentsTool`, `MongoDeleteDocumentsTool`, `ProviderCreateSchemaTool`, `ProviderCreateTableTool`, `ProviderInsertRowTool`, `ProviderSelectRowsTool`, `ProviderUpdateRowsTool`, `ProviderDeleteRowsTool`.
   - Memory: `SupermemoryAddMemoryTool`, `SupermemorySearchMemoryTool`, `SupermemoryDeleteMemoryTool`, `Mem0AddMemoryTool`, `Mem0SearchMemoryTool`, `Mem0GetMemoriesTool`, `Mem0DeleteMemoryTool`, `ZepAddMemoryTool`, `ZepGetMemoryTool`, `ZepSearchMemoryTool`, `ZepDeleteSessionTool`, `CogneeAddTool`, `CogneeCognifyTool`, `CogneeSearchTool`, `CogneeDeleteTool`, `LettaAddArchivalMemoryTool`, `LettaSearchArchivalMemoryTool`, `LettaDeleteArchivalMemoryTool`, and `LettaGetMemoryBlockTool`.
5. Check every named symbol against source exports and direct module paths, then scan the completed document for omissions and inaccurate automatic-registration claims.

#### Edge Cases & Error Handling

- Mark direct-module-only utilities distinctly from flat `vidbyte.tools.builtins` exports.
- State binding prerequisites for agent-bound, context-bound, and session-bound tools.
- State third-party prerequisites for memory, MCP, and provider/database tools.
- If source changes while implementing, update this design doc and obtain approval again before expanding scope.

---

## 7. Data Model Changes

N/A - no dataclasses, schemas, persisted data, or migrations change.

---

## 8. API Changes

N/A - no SDK endpoint or Python API changes. Existing APIs are documented only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/llms-agent-context-tools-reference.md` | Design source of truth for the documentation change |
| MODIFY | `llms.txt` | Add the requested current API and full built-in-tool reference |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Clean `main` source | Current checked-out branch | Authoritative SDK behavior and tool inventory | Must re-audit if source changes before editing |
| External memory, MCP, and provider services | Developer configured | Optional built-in tool backends | Documentation must not imply credentials or connectivity |
| `python scripts/run_ci.py` | Repository CI gate | Required post-change verification | Must remain green before PR creation |

---

## 11. Rollout & Deployment

- Create the feature worktree and commit this approved design doc before editing `llms.txt`.
- Run targeted documentation checks, then `python -m pip install -e ".[dev]"` and `python scripts/run_ci.py`.
- Open a draft PR against `main` and wait for required checks.
- Roll back by reverting the documentation commit; no migration or feature flag is needed.

---

## 12. Open Questions

- [ ] Should the full built-in inventory remain in one dense table, or should memory/provider/session categories link to their package-level docs after listing every class once? The proposed implementation uses concise grouped tables and source-package paths.
- [ ] `CalculatorTool` and `DocumentRetrievalTool` are current direct modules rather than flat `vidbyte.tools.builtins` exports. The proposed implementation documents that distinction; a future API-consistency PR could choose to re-export them.

---

## 13. Alternatives Considered

### Alternative 1: Document output contracts as part of `output_schema`

- What: Combine minimum-completion contracts with JSON/Pydantic response formatting.
- Why rejected: The runtime uses them for different responsibilities: contracts gate termination, while `output_schema` requests and validates structured output.

### Alternative 2: List only flat `vidbyte.tools.builtins` exports

- What: Omit current concrete tools that require direct-module imports.
- Why rejected: It would not fulfill the requested complete built-in-tool coverage.

### Alternative 3: Expand README together with llms.txt

- What: Duplicate the full catalog in the human-facing README.
- Why rejected: The requested artifact is `llms.txt`; duplicating it broadens scope and creates additional maintenance without improving this task's outcome.
