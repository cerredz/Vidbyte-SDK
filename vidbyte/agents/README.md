# Agents

## Folder Intent

This folder owns executable agent construction, runtime selection, session restoration, handoff/fork helpers, context-window algorithm wiring, and agent-facing state contracts.

## Non-Goals

Do not place provider transport, low-level dataclasses, or concrete tool implementations here. Keep this layer focused on agent orchestration and public agent APIs.

## Usage

```python
from vidbyte import Agent

agent = Agent(
    name="assistant",
    system_prompt="Answer directly and use tools when useful.",
    runner=my_runner,
)

result = await agent.arun("Summarize the current project state.")
print(result.output)
```

## File Index

- `__init__.py`: Exposes agents and orchestration primitives for Vidbyte SDK. Allows easy package-level import of BaseAgent, registries, client schemas, and swappable execution runtimes. Key symbols: Agent, AggregateAgent, AggregateConfig, AggregateResult, AgentClient, AgentLoopSettings.
- `aggregation.py`: Implements the Multi-Provider Aggregator (Mixture-of-Agents) engine and the AggregateAgent class that exposes it as a first-class SDK agent. Fans a request out to several proposer models concurrently and routes their candidate answers to a final aggregator model that synthesizes a new response grounded in all of them (it composes its own answer, it does not select one). Key symbols: AggregateResult, MultiProviderAggregator, AggregateAgent.
- `base.py`: Defines the baseline agent implementation (BaseAgent) and configured runner wrappers. Combines prompting, tool registration, runtime state tracking, and execution into a unified developer-facing executable actor (the agent). Key symbols: ConfiguredAgentRunner, BaseAgent.
- `client.py`: Owns client behavior inside the vidbyte/agents layer. Key symbols: AgentClient.
- `context_algorithms.py`: Owns context algorithms behavior inside the vidbyte/agents layer. Key symbols: AgentRuntimeContextAlgorithms.
- `continual_trace.py`: Defines ContinualTraceAgent, a dedicated BaseAgent that fills a trace schema. Performs one continual trace update pass over a read-only snapshot of a main agent run, filling a typed trace schema through the updateTrace tool. Mirrors the HandoffAgent pattern so trace updates use normal SDK agent and tool primitives. Key symbols: ContinualTraceAgent.
- `fork.py`: Houses AgentForker, the utility class that owns all BaseAgent fork logic. Keeps base.py focused on agent execution by extracting fork config resolution, tool cloning, lineage metadata, and run-state carry into one cohesive place driven entirely by a validated AgentForkSettings. Key symbols: AgentForker.
- `handoff.py`: Defines HandoffAgent, a thin configuration over BaseAgent that produces structured handoff documents from a completed agent run. Turns the comprehensive handoff system prompt plus a Handoff spec into an executable agent whose generate_handoff() returns a filled Handoff document. Key symbols: HandoffAgent.
- `mixins.py`: Defines mixins that equip agents and harnesses with lifecycle-managed and preset MCP servers. Enforces identical APIs and automated cleanup routines for attached subprocesses without duplicating logic across agents and harnesses. Key symbols: McpAttachableMixin.
- `runtime.py`: Defines the internal direct execution runtime for Vidbyte agents. Keeps agent loop execution, context-window construction, tool execution, permission checks, and provider-reported token accounting out of BaseAgent. Key symbols: AgentRuntime.
- `types.py`: Owns types behavior inside the vidbyte/agents layer. Key symbols: AgentCard, AgentForkSettings, AgentInput, AgentMessage, AgentSpec, ModelModality.

## Subfolder Routing

- `algorithms/`: Compatibility shims for context-window algorithms.
- `runtimes/`: Runtime configuration exports and concrete linear/search/actor runtime code.
- `settings/`: Agent-loop configuration models and tool-error policy settings.

## Logs

- 2026-07-07: Runtime compatibility checks are load-bearing because non-linear runtimes do not support every linear-loop extension.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
