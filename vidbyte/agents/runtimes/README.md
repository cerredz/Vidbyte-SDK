# Agent Runtimes

## Folder Intent

This folder owns runtime configuration exports and concrete runtime implementations for linear loops, search, and actor-model execution.

## Non-Goals

Do not add public Agent construction policy here; keep construction and compatibility guards in `vidbyte/agents/base.py`.

## File Index

- `__init__.py`: Exposes all swappable agent loop execution runtimes. Allows BaseAgent to dynamically import and dispatch different runtime loop paradigms (linear execution, search trees, and actor mailboxes). Key symbols: LinearAgentRuntime, SearchTreeRuntimeComponent, PointToPointActorRuntime, BroadcastActorRuntime, LinearRuntime, MctsSearchRuntime.
- `configs.py`: Defines configuration classes for Linear, MCTS Search, and Actor runtimes. Allows developers to cleanly configure runtime settings inside a single structured parameter, avoiding main agent constructor clutter. Key symbols: LinearRuntime, MctsSearchRuntime, ActorRuntime.
- `linear.py`: Compatibility shim re-exporting AgentRuntime as LinearAgentRuntime. Keeps the vidbyte.agents.runtimes.linear import path stable after the canonical AgentRuntime implementation was consolidated into vidbyte.agents.runtime. Key symbols: AgentRuntime.
- `search.py`: Implements a branching search runtime using Monte Carlo Tree Search (MCTS). Allows agents to explore multiple parallel reasoning paths, score them, and execute rollbacks to historical parent nodes when a path hits a dead end. Key symbols: SearchNode, SearchTreeRuntimeComponent.

## Subfolder Routing

- `actor/`: Actor-model message passing, inboxes, and broker runtimes.

## Logs

- 2026-07-07: Runtime config exports are part of the public agent API and should stay synchronized with BaseAgent runtime handling.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
