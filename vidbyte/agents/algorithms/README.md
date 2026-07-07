# Agent Algorithms

## Folder Intent

This folder preserves agent-facing imports for context-window algorithms that now live under the context layer.

## Non-Goals

Do not implement new algorithm logic here; add implementations under `vidbyte/context/algorithms` and keep this package as a compatibility surface.

## File Index

- `__init__.py`: Exposes agent-runtime context-window algorithm implementations. Keeps algorithm-specific runtime orchestration outside AgentRuntime. Key symbols: ReflexionRuntimeAlgorithm, MultiProviderAgenticGraderRuntimeAlgorithm.
- `multi_provider_agentic_grader.py`: Owns multi provider agentic grader behavior inside the vidbyte/agents layer. Key symbols: MultiProviderAgenticGraderRuntimeAlgorithm.
- `reflexion.py`: Owns reflexion behavior inside the vidbyte/agents layer. Key symbols: ReflexionRuntimeAlgorithm.

## Subfolder Routing

- No source subfolders.

## Logs

- 2026-07-07: Compatibility exports are intentional for existing agent imports.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
