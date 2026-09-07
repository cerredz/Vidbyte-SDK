# Vidbyte-to-Claude translation map

Maps each Vidbyte abstraction to its Claude Agent SDK counterpart, its disposition,
and its state in the `feat/claude-harness-agent` baseline. Dispositions use the
vocabulary defined in
[`skills/claude-agent-sdk-translation/SKILL.md`](../../claude-agent-sdk-translation/SKILL.md):
`native`, `translated`, `supervised`, `observe_only`, `emulated`, `unsupported`.

"Shipped" means the baseline implements it. "Pending" links the checklist task that
would implement it. A pending row is not a bug; it is scoped-out work with a stable
id.

## Agent construction and identity

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `system_prompt` | `system_prompt` string | `native` | Shipped |
| `system_prompt` as preset append | `SystemPromptPreset.append` | `translated` | Shipped |
| `system_prompt` from a file | `SystemPromptFile.path` | `translated` | Shipped; trust rules pending [X03](checklist.md#x) |
| `additional_context` | prompt prefix text | `translated` | Shipped |
| `description`, `capabilities`, `metadata` | no counterpart | `emulated` | Shipped as Vidbyte-only metadata; enforcement pending [C01](checklist.md#c) |
| YAML `{ref, options}` construction | no counterpart | `emulated` | Pending [G01](checklist.md#g) |

## Model and reasoning

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `runner_config.model_name` | `model` | `native` | Shipped |
| `AgentFallbackSettings` | `fallback_model` | `translated` | Shipped as a distinct provider-owned control; attempt reconciliation pending [B05](checklist.md#b) |
| reasoning effort | `effort` | `native` | Shipped |
| thinking budget | `ThinkingConfig` | `translated` | Shipped |
| `temperature`, `top_p`, stop sequences | none | `unsupported` | Pending explicit rejection [C04](checklist.md#c) |
| provider extensions | `betas` | `native` | Shipped as a labeled escape hatch |

## Loop bounds and budgets

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `AgentLoopSettings.max_iterations` | `max_turns` | `translated` | Shipped; a Claude turn is not a Vidbyte iteration |
| cost budget | `max_budget_usd` | `translated` | Shipped; the provider enforces it |
| cross-turn spend cap | none | `emulated` | Pending [B06](checklist.md#b) |
| task token budget | `task_budget` | `translated` | Pending [G04](checklist.md#g) |

## Context

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `ContextManager` primitives zone | appended to `system_prompt` | `translated` | Shipped |
| conversation-zone placements | current-turn prompt text | `translated` | Shipped; the adapter states this is not native history |
| per-run `ContextItem`s | prompt prefix text | `translated` | Shipped |
| native input anchors | none, because the prompt is one string | `unsupported` | Deliberately not ported; becomes meaningful only with [T02](checklist.md#t) |
| Vidbyte compaction algorithms | provider-owned compaction | `supervised` | Observation pending [X01](checklist.md#x) |
| context budget accounting | `get_context_usage()` | `observe_only` | Pending [X02](checklist.md#x) |

## Sessions and branching

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| conversation continuity | `resume` by session id | `native` | Shipped; the adopted id wins over a settings-level resume |
| most-recent continuation | `continue_conversation` | `translated` | Shipped; rejected together with `resume` |
| `BaseAgent.fork` | `resume` plus `fork_session` | `translated` | Shipped as a **lazy** fork: the child has no id until its first run |
| message-level branch | `resume_session_at` | `translated` | Shipped; boundary proof pending [S06](checklist.md#s) |
| `vidbyte.sessions` checkpoint DAG | none | `emulated` | Pending [D01](checklist.md#d) through [D05](checklist.md#d) |
| session stores | `SessionStore` | `translated` | Pending [S04](checklist.md#s) |
| file rewind | `rewind_files()` | `native` | Pending [F02](checklist.md#f) |

## Tools, MCP, and permissions

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `AgentLoopSettings.allowed_tools` | `allowed_tools` | `translated` | Shipped |
| `ToolSettings.denied_tools` | `disallowed_tools` | `translated` | Shipped; an allow/deny conflict is rejected at construction |
| built-in tool catalog | `tools` preset | `translated` | Shipped; observability pending [U06](checklist.md#u) |
| `ToolSpec` | SDK `tool()` plus in-process MCP server | `translated` | Pending [U01](checklist.md#u), [U02](checklist.md#u) |
| external MCP servers | `mcp_servers` | `native` | Shipped as validated config; lifecycle pending [M01](checklist.md#m) through [M05](checklist.md#m) |
| `ToolSettings.result_max_chars` | `maxResultSizeChars` | `translated` | Pending [U04](checklist.md#u) |
| security policy | `permission_mode` | `translated` | Shipped as a declarative mode |
| approval callback | `can_use_tool` | `translated` | Pending [P01](checklist.md#p), blocked on [H09](checklist.md#h) |
| sandbox boundary | `SandboxSettings` | `translated` | Shipped as config; platform gaps pending [P07](checklist.md#p) |

## Lifecycle interception

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `AgentMiddleware` | Claude hooks | **not equivalent** | Pending [H01](checklist.md#h) through [H08](checklist.md#h); timing, outputs, and failure policy all differ |
| `before_model_call` | no counterpart | `unsupported` | Claude owns its model calls, and `PreToolUse` is not this |
| deterministic middleware order | parallel hooks, most restrictive wins | `translated` | Pending [H10](checklist.md#h) |

## Results, output, and failures

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `AgentMessage` | assistant messages plus `ResultMessage` | `translated` | Shipped |
| `output_schema` | `output_format` json_schema | `native` | Shipped, including the draft-07 downgrade |
| output contract validation | provider validation plus retry | `supervised` | Shipped; retry visibility pending [U07](checklist.md#u) |
| content primitives | text, tool_use, tool_result blocks | `translated` | Shipped; typed payloads pending [R01](checklist.md#r) |
| reasoning traces | thinking blocks | `observe_only` | Excluded at serialization by design; policy pending [R06](checklist.md#r) |
| `FailureCode` | SDK error classes plus result subtypes | `translated` | Ten codes shipped; per-subtype codes pending [B02](checklist.md#b) |
| recovery handlers | none | `emulated` | Pending [B03](checklist.md#b) |
| streaming | `include_partial_messages` | `translated` | Pending [T01](checklist.md#t) |

## Subagents and orchestration

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| child agent definitions | `AgentDefinition` | `translated` | Shipped; `memory`, `mcpServers`, `initialPrompt` pending [N01](checklist.md#n) |
| child lifecycle events | `SubagentStart` and `SubagentStop` | `translated` | Pending [N02](checklist.md#n) |
| `MultiAgent` ledger | none inside Claude's loop | `emulated` | Pending [V02](checklist.md#v); a Claude agent is a worker, not a ledger participant |
| MCTS and actor runtimes | none inside Claude's loop | `unsupported` | Outer composition only |

## Accounting and observability

| Vidbyte abstraction | Claude counterpart | Disposition | State |
|---|---|---|---|
| `UsageTracker` and `UsageRollup` | token counters on the result | `translated` | Record shipped; wiring pending [O01](checklist.md#o) |
| pricing | `total_cost_usd` | `translated` | Captured; reconciliation pending [O02](checklist.md#o) |
| `AgentSpeedTracker` | `duration_ms`, `duration_api_ms` | `observe_only` | Captured; wiring pending [O03](checklist.md#o) |
| trace shapes | provider OpenTelemetry | `translated` | Pending [O04](checklist.md#o), [O05](checklist.md#o) |
| `Harness` capture and redaction | none | `emulated` | Pending [V01](checklist.md#v) |
| `TrajectorySink` export | none | `emulated` | Pending [V04](checklist.md#v) |

## Reading this map

Three rules keep it honest. A `native` row means Claude offers the same useful
guarantee, not merely a similarly named field. A `translated` row must state what
precision was lost, which is why the turn, fork, and conversation-zone rows carry
qualifiers. An `unsupported` row is rejected or reported, never silently accepted:
the adapter's job is to make a missing guarantee visible, not to approximate it.
