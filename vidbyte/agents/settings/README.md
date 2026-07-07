# Agent Settings

## Folder Intent

This folder owns structured agent-loop settings, especially iteration limits, compaction thresholds, and tool-error policy configuration.

## Non-Goals

Do not execute policy here; settings should validate and describe configuration while runtimes and middleware enforce behavior.

## File Index

- `__init__.py`: Public exports for the vidbyte.agents.settings sub-package. Exposes AgentLoopSettings and nested settings objects for agentic loop parameters. Key symbols: AgentLoopSettings, ToolErrorPolicy, UnrecoverableAction.
- `loop.py`: Defines AgentLoopSettings, the canonical configuration object for all parameters that govern the agentic execution loop. Consolidates loop budget and behavioral constraints into a single validated class, replacing scattered flat kwargs with a structured developer-facing abstraction. Key symbols: AgentLoopSettings.
- `tool_error.py`: Defines tool-error retry policy settings for agent loops. Gives AgentLoopSettings a validated nested policy for deciding when failed tool calls should retry, continue, or abort the run. Key symbols: UnrecoverableAction, ToolErrorPolicy.

## Subfolder Routing

- No source subfolders.

## Logs

- 2026-07-07: Defaults here shape BaseAgent runtime behavior, so public compatibility matters more than local convenience.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
