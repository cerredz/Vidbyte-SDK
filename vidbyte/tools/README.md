# Tools

Tools in the Vidbyte SDK bridge model-requested tool calls to local Python
capabilities, MCP-backed tools, and built-in utilities.

## Role In The SDK

`vidbyte.tools` exposes `@tool`, `FunctionTool`, `BaseTool`, `Tools`,
`ToolExecutor`, compatibility registries, tool specs, tool results, MCP bridges,
security policies, and built-in tools. Agents receive tools locally through
`tools=[...]`, describe them to model providers, execute permitted calls, and add
tool results back into the runtime context.

## Design Philosophy

Tooling should be agent-local, typed, and permission-aware. New application code
should pass tools directly to agents or wrap collections with `Tools`. Legacy
registries remain available for compatibility, but the catalog-first pattern
makes tool availability easier to inspect.

## Usage

```python
from vidbyte import Agent, Tools, tool

@tool
def lookup_user(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

catalog = Tools([lookup_user])
agent = Agent(
    name="tool-user",
    system_prompt="Use tools when they help.",
    provider="openai",
    model_name="gpt-4.1",
    tools=catalog,
)

print(catalog.names())
print(catalog.provider_schemas("openai"))
```

## Key Modules

- `decorators.py`: `@tool` and `vidbyte_tool` function wrappers.
- `function_tool.py`: `FunctionTool` creation from Python callables.
- `catalog.py`: agent-local immutable tool catalog.
- `executor.py`: local tool call execution.
- `security/`: permission policies and sandbox contracts.
- `mcp/`: MCP clients, transports, presets, and bridged tools.
- `builtins/`: adversarial review scaffolds, code search, context, context primitives, editing, memory, MCP, handoff, and utility tools.

## Adversarial Review Scaffolds

The built-in package exposes sixteen zero-argument tools that reserve stable
model-facing names and review-subject schemas for future adversarial-agent
topologies. Developers may construct them and place them in an agent-local
catalog today:

```python
from vidbyte.tools.builtins import (
    LaunchSelfReflectionAgentTool,
    LaunchSpecialistPanelTool,
)

tools = [
    LaunchSelfReflectionAgentTool(),
    LaunchSpecialistPanelTool(),
]
```

These classes are integration scaffolds, not production-ready launchers. Every
call fails closed with a `ToolResult.error` whose error code is
`adversarial_agent_unavailable`; no model, task, or child agent is launched.
They are not auto-attached to agents and are not re-exported from the root
`vidbyte` package.

| Class | Model-facing tool name |
| --- | --- |
| `LaunchSelfReflectionAgentTool` | `launch_self_reflection_agent` |
| `LaunchIndependentCriticAgentTool` | `launch_independent_critic_agent` |
| `LaunchParallelPanelTool` | `launch_parallel_panel` |
| `LaunchSpecialistPanelTool` | `launch_specialist_panel` |
| `LaunchCrossProviderPanelTool` | `launch_cross_provider_panel` |
| `LaunchCritiqueReviseAgentTool` | `launch_critique_revise_agent` |
| `LaunchCritiqueAdjudicateReviseAgentTool` | `launch_critique_adjudicate_revise_agent` |
| `LaunchProsecutorDefenderJudgeTool` | `launch_prosecutor_defender_judge` |
| `LaunchAdversarialDebateTool` | `launch_adversarial_debate` |
| `LaunchDelphiReviewTool` | `launch_delphi_review` |
| `LaunchCandidateTournamentTool` | `launch_candidate_tournament` |
| `LaunchAdversarialSelectorTool` | `launch_adversarial_selector` |
| `LaunchCounterexampleSearchTool` | `launch_counterexample_search` |
| `LaunchMutationReviewTool` | `launch_mutation_review` |
| `LaunchToolBackedVerifierTool` | `launch_tool_backed_verifier` |
| `LaunchEvidenceVerifierTool` | `launch_evidence_verifier` |

The future `AdversarialAgent` integration must add recursion guards, bounded
nested usage budgets, child-tool filtering, and explicit child permission
policy before any scaffold can execute. None of those controls are implied or
implemented by the current placeholders.

## Related Layers

Tools are attached to [`agents`](../agents/README.md), governed by
[`middleware`](../middleware/README.md), exposed through
[`mcp_server`](../mcp_server/README.md), and formatted for
[`providers`](../providers/README.md).
