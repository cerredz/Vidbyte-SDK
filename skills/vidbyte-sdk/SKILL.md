# Vidbyte SDK Structure

Use this reference when modifying the Vidbyte SDK package structure.

## Current Layout

```text
vidbyte/
|-- client.py
|-- harnesses/
|   `-- client.py
|-- providers/
|   |-- client.py
|   |-- openai.py
|   |-- anthropic.py
|   |-- gemini.py
|   `-- xai.py
|-- strategies/
|   |-- reasoning/
|   |-- sampling/
|   |-- agent_loops/
|   `-- routing/
|-- tools/
|   |-- client.py
|   `-- filesystem/
|-- shared/
`-- lib/
    |-- config/
    |-- dataclasses/
    |-- errors/
    |-- prompts/
    |-- tools/
    |-- http/
    `-- runners/
```

## Rules

- Keep `vidbyte/` as the top-level Python package namespace.
- Keep namespace clients in `vidbyte/harnesses/`, `vidbyte/tools/`, and `vidbyte/providers/`.
- Keep internal library helpers under `vidbyte/lib/`.
- Keep SDK error modules under `vidbyte/lib/errors/`.
- Keep shared SDK scaffolding under `vidbyte/shared/`.
- Keep provider-specific HTTP adapters in `vidbyte/providers/`; strategy code must call runners, not provider adapters directly.
- Keep semantic runner classes in `vidbyte/lib/runners/`; `TextModelRunner.run()` is the required execution path for prompt/API strategies.
- Keep dataclass definitions in `vidbyte/lib/dataclasses/`; public feature packages may re-export them for compatibility.
- Keep provider config dataclasses re-exported from `vidbyte/lib/config/`; never hardcode API keys or secrets.
- Keep prompt JSON assets under `vidbyte/prompts/prompts/` and load them through `vidbyte/lib/prompts/PromptRegistry`.
- Keep filesystem tools under `vidbyte/tools/filesystem/`; every filesystem tool must use `vidbyte/lib/tools/filesystem/FileSystemPermissions` and a backend from `vidbyte/lib/tools/filesystem/backends/`.
- Keep prompt/API strategies under `vidbyte/strategies/`, grouped by category.
- Configure strategy runners at construction time, then call `run(prompt)` without passing a runner for each call.
- Do not implement model-internal, training-time, or arbitrary-code strategies without an explicit design for hidden-state access, fine-tuning, or sandboxing.

## Implemented Strategy Batch

- Chain of Thought: single-call sequential reasoning prompt.
- Step-Back: principles call followed by original task solve.
- Chain of Draft: concise intermediate reasoning with a per-step word budget.
- Skeleton of Thought: outline call followed by separate calls per skeleton point.
- Self-Consistency: multiple independent samples with normalized answer voting.
- Budget Forcing: continuation calls until a final answer marker or round cap.
- Answer Convergence: repeated samples until a recent answer window converges.
- Plan-and-Execute: plan first, execute each step, then synthesize.
- Paradigm Routing: selects a strategy with heuristics or a model-scored routing prompt.
