# Feature: System-prompt presets (Working Principles)

## High-Level Feature Description

A system-prompt preset is a fixed, reviewed paragraph that a developer attaches to any SDK agent with one keyword, `system_prompt_presets=[SystemPromptPreset.WORKING_PRINCIPLES]`. The first preset, Working Principles, distills Felix Rieseberg's essay "How to be more ambitious: a tutorial for humans with models" (https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/) into eight example-free sentences: aim at the outcome beyond the literal request, work like the best professional in the field from the rawest material, hold demanding targets, test assumptions and verify independently, borrow the methods of other fields that solve the same problem, finish the given task before taking the larger move, and carry the principles into every subagent prompt. The text lives in `vidbyte/prompts/prompts/working_principles/system_prompt.md`, so a developer can read exactly what is added.

## Contract

- `BaseAgent(system_prompt_presets=...)` accepts `None` (the default), or a list of `SystemPromptPreset` members or their string values. A bare string, a non-iterable, an unknown value, or a repeated preset raises `ConfigurationError` at construction.
- `None` means "inherit the presets of the run this agent is started in"; an explicit value, including `()`, is final and is also what the agent hands to its own children.
- The runtime's system prompt is the agent's own prompt, one blank line, then each enabled preset's text in enum order, then the agentic-loop note. With no effective preset the prompt is sent byte for byte as before. A preset whose text the prompt already holds (whitespace-insensitive) is not added again. `agent.system_prompt` itself never changes.
- While an agent runs, its effective presets are the active scope (`SystemPromptPresetScope`, a ContextVar) for every agent the run starts: `as_tool()` specialists, agents built inside tools, Jev specialists, clones, swarm helpers, bulk workers, and fresh continuations.
- A reply's metadata carries `system_prompt_presets` (a list of values) only when presets applied.
- `fork()` copies the field, even when the fork replaces the system prompt. `export_state()` / `restore()` and the session serializer round-trip it; older states read as `None`.
- `JevAgentSettings.system_prompt_presets` sets it on a JevAgent.
- Fixed-prompt machinery opts out with `()`: JevRunState, JevHandoff, JevReviewer, JevRunBriefWriter, JevClarificationAgent, ContinualTraceAgent, and HandoffAgent (the last two also drop a caller's value).
- `ContextMinimalFanoutParadigm` builds its agents with `()` unless a role's `agent_options` names `system_prompt_presets`.

## Invariants

- No existing agent changes behavior unless a developer sets the field on it or on an agent whose run starts it.
- The preset text appears at most once in any system string.
- The scope is restored when a run ends, including when it raises.

## Known Failure Modes

- A child built during a run but run after it, an agent run in a raw thread or a foreign event loop, and a subclass that replaces `generate_reply` (MultiAgent, AggregateAgent) inherit nothing; `UncoveredPathTests` pins these limits.
- A per-call `system=` option, or a base context with its own `system_prompt`, replaces the composed prompt, as it replaces the agent's prompt today.
- CodexHarnessAgent is not a BaseAgent; compose the text into its `system_prompt` with `SystemPromptPresetComposer.compose`.

## Test Suite Map

- `test_system_prompt_presets_units.py`: the verbatim asset, the enum, `SystemPromptPresetSelection`, `SystemPromptPresetScope` (nesting, exceptions, tasks, threads, concurrency), and `SystemPromptPresetComposer`.
- `test_system_prompt_presets_propagation.py`: BaseAgent on and off, multi-turn runs, scope cleanup, the search and actor runtimes, `as_tool()` specialists, agents started in tools, `fork_conversation` children, opt-out children, duplicate prevention, forks, persistence, JevAgent and its children (a gate-chosen specialist and a CLONE launch through the real Jev loop, plus clones, swarm helpers, bulk workers, and fresh continuations), the opted-out machinery, the fan-out paradigm, and the documented uncovered paths (team facades, the Codex harness, late-run children, raw threads).
- `fakes.py`: the pack's own copy of the paragraph, the recording model, and the offline safety net.
- Run `python scripts/test-working-principles-preset.py` for the whole pack with PASS/FAIL lines.

## Omitted Testing Strategies

- No live model calls: whether the preset makes agents more ambitious is a model-quality question for an offline eval, not a unit test.
- Anthropic token counts are not measured, because the count endpoint needs a keyed API call.
