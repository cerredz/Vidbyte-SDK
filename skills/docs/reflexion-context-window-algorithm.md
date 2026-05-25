# Reflexion Context Window Algorithm

Implementation of the Noah Shinn Reflexion algorithm (verbal reinforcement learning for LLM agents) as a context window algorithm and prompt family in vidbyte-sdk.

Source: https://github.com/noahshinn/reflexion (NeurIPS 2023)

## Requirements

### Context Window Algorithm
- `ReflexionAdmission` enum with values: `NONE`, `LAST_ATTEMPT`, `REFLEXION`, `LAST_ATTEMPT_AND_REFLEXION`
- `ReflexionConfig` frozen dataclass that wraps admission mode + token/length controls (`max_reflection_tokens`, `max_scratchpad_tokens`, `include_context_in_reflection`)
- Extend `ContextWindowAlgorithm` with a `reflexion: ReflexionConfig | None` field (default `None` — backward compatible, opt-in)
- Helper functions for building reflexion context strings from prior trial data:
  - `format_reflections(reflections)` — join accumulated self-reflections with header
  - `format_last_attempt(question, scratchpad)` — format the previous trial scratchpad with header
  - `build_reflexion_context(config, question, scratchpad, reflections, context)` — dispatch on admission strategy
- Presets in `ContextWindowPresets`:
  - `reflexion` — `ReflexionAdmission.REFLEXION`
  - `reflexion_last_attempt` — `ReflexionAdmission.LAST_ATTEMPT`
  - `reflexion_last_attempt_and_reflexion` — `ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION`
- Public exports from `vidbyte.context.algorithms`, `vidbyte.context`, and `vidbyte`

### Prompt Family
- New `reflexion.json` prompt asset in `vidbyte/prompts/prompts/`
- Prompt keys:
  - `reflect_prompt` — self-reflection prompt: diagnose previous failure, devise new high-level plan
  - `agent_prompt` — agent action prompt with `{reflections}` slot for injecting accumulated reflections
- `ReflexionPrompts` bundle class in `vidbyte/prompts/strategies/strategy_prompts.py`
- Enum entries in `vidbyte/lib/enums/prompts.py`:
  - `REFLEXION_REFLECT_PROMPT = "reflexion.reflect_prompt"`
  - `REFLEXION_AGENT_PROMPT = "reflexion.agent_prompt"`

## Non-goals

- Modifying `AgentRuntime` to consume the reflexion algorithm — the algorithm config and helpers are declarative; runtime integration is a separate follow-up
- Modifying the existing `ReflexionStrategy` class (which uses the `multi_agent_reflexion` prompts for a different multi-agent pattern)
- Modifying the existing `multi_agent_reflexion.json` prompt file
- Implementing the full ReAct or CoT agent loop — only the reflexion context admission layer
- Tokenizer-based truncation — use character-based length limits consistent with existing `max_tool_result_chars` pattern

## Risks

| Risk | Mitigation |
|------|-----------|
| Name collision with existing `ReflexionStrategy` class in `vidbyte/strategies/` | Use distinct name `ReflexionAdmission` for the enum; `ReflexionConfig` is a dataclass not a strategy |
| Enum naming confusion with existing `multi_agent_reflexion` prompt family | New prompt family is `reflexion` (no prefix); existing is `multi_agent_reflexion` |
| Accumulated reflections overflow context window | `max_reflection_tokens` config with character-based truncation in helper functions |
| Missing runtime hook prevents reflexion from working | Not applicable for this change — the algorithm is declarative; runtime integration is a separate concern |

## Open Questions

- Should reflexion prompts be domain-agnostic (general-purpose) or task-specific (HotPotQA/ReAct style)? **Decision:** General-purpose, matching the vidbyte prompt style. The original prompts are adapted to remove environment-specific references (Docstore, Wikipedia, Search/Lookup actions) in favor of abstract "tool" and "task" language.
- Should `format_reflections` and `format_last_attempt` return plain strings or structured `ContextItem` objects? **Decision:** Return plain strings — they are injected as prompt text, not as standalone context items. This matches how the original algorithm appends them to the scratchpad.

## Rollout

1. Create `vidbyte/context/algorithms/reflexion.py` with `ReflexionAdmission`, `ReflexionConfig`, and helpers
2. Modify `vidbyte/context/algorithms/tool_results.py` — add `reflexion` field to `ContextWindowAlgorithm`
3. Modify `vidbyte/context/algorithms/__init__.py` — export new types
4. Modify `vidbyte/context/__init__.py` — export new types
5. Modify `vidbyte/context/presets.py` — add reflexion presets
6. Modify `vidbyte/__init__.py` — export `ReflexionAdmission`, `ReflexionConfig`
7. Create `vidbyte/prompts/prompts/reflexion.json` — prompt assets
8. Modify `vidbyte/lib/enums/prompts.py` — add enum entries
9. Modify `vidbyte/prompts/strategies/strategy_prompts.py` — add `ReflexionPrompts` bundle
10. Modify `vidbyte/prompts/strategies/__init__.py` — export bundle
11. Create `tests/test_reflexion_algorithm.py` — algorithm config and helpers tests
12. Create `tests/test_reflexion_prompt.py` — prompt loading and access tests
- No migrations, no breaking changes (new fields default to `None`)

## Rollback

- Delete `reflexion.py`, `reflexion.json`, and both test files
- Revert the `reflexion` field addition to `ContextWindowAlgorithm`
- Revert `__init__.py` and enum exports
- No other code depends on these additions

## High-Level Design

The Reflexion algorithm wraps prior-trial data (scratchpads, self-reflections) for injection into an agent's context on subsequent attempts. The algorithm is purely declarative — it produces configuration and provides helper functions to build context strings. Actual execution/iteration is the responsibility of `AgentRuntime` or strategy implementations.

```
Trial N (failed)
  ├── scratchpad (reasoning trace)
  └── self-reflection prompt → LLM → reflection text

Trial N+1
  ├── resolve reflexion admission strategy
  ├── build_reflexion_context() → formatted string
  └── inject into agent prompt via {reflections} variable
```

**Admission strategies:**
- `NONE` — no prior data injected (baseline, no reflexion)
- `LAST_ATTEMPT` — inject the full previous trial scratchpad
- `REFLEXION` — inject accumulated self-reflections (diagnoses + new plans)
- `LAST_ATTEMPT_AND_REFLEXION` — inject both previous scratchpad and reflections

## Detailed Design

### File: `vidbyte/context/algorithms/reflexion.py`

```python
@dataclass(frozen=True, slots=True)
class ReflexionAdmission(str, Enum):
    """How a context-window algorithm admits reflexion data into model context."""
    NONE = "none"
    LAST_ATTEMPT = "last_attempt"
    REFLEXION = "reflexion"
    LAST_ATTEMPT_AND_REFLEXION = "last_attempt_and_reflexion"

@dataclass(frozen=True, slots=True)
class ReflexionConfig:
    admission: ReflexionAdmission = ReflexionAdmission.REFLEXION
    max_reflection_tokens: int = 250
    max_scratchpad_tokens: int = 1600
    include_context_in_reflection: bool = True

def format_reflections(reflections: Sequence[str]) -> str:
    ...

def format_last_attempt(question: str, scratchpad: str) -> str:
    ...

def build_reflexion_context(
    config: ReflexionConfig,
    question: str,
    scratchpad: str,
    reflections: Sequence[str],
    context: str | None = None,
) -> str:
    ...
```

### File: `vidbyte/context/algorithms/tool_results.py` (modification)

Add `reflexion` field to `ContextWindowAlgorithm`:
```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reflexion: ReflexionConfig | None = None       # NEW — backward-compatible default
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

The import for `ReflexionConfig` is added at the top of `tool_results.py` from `.reflexion`.

### File: `vidbyte/context/presets.py` (modification)

Add three preset properties:
```python
@property
def reflexion(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="reflexion",
        reflexion=ReflexionConfig(strategy=ReflexionAdmission.REFLEXION),
    )

@property
def reflexion_last_attempt(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="reflexion_last_attempt",
        reflexion=ReflexionConfig(strategy=ReflexionAdmission.LAST_ATTEMPT),
    )

@property
def reflexion_last_attempt_and_reflexion(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="reflexion_last_attempt_and_reflexion",
        reflexion=ReflexionConfig(strategy=ReflexionAdmission.LAST_ATTEMPT_AND_REFLEXION),
    )
```

### File: `vidbyte/prompts/prompts/reflexion.json`

```json
{
  "name": "Reflexion",
  "description": "Reflexion (Noah Shinn et al., NeurIPS 2023) is a verbal reinforcement learning technique where an agent learns from its own mistakes. After each failed attempt, the agent self-reflects: it diagnoses what went wrong and devises a new high-level plan to avoid repeating the failure. These accumulated reflections are injected into the agent's context on subsequent attempts, creating a feedback loop that improves performance over multiple trials. The algorithm defines four strategies: none (baseline, no prior trial data), last_attempt (previous scratchpad only), reflexion (accumulated self-reflections), and last_attempt_and_reflexion (both).",
  "key": "reflexion",
  "prompts": {
    "reflect_prompt": "You are an advanced reasoning agent that can improve through self-reflection. You will be given a previous trial where you attempted a task and were unsuccessful. In a few sentences, diagnose a possible reason for the failure and devise a new, concise, high-level plan that aims to mitigate the same failure in your next attempt. Use complete sentences.\n\nPrevious trial:\nTask: {question}\n{scratchpad}\n\nReflection:",
    "agent_prompt": "Solve the following task using available tools and reasoning steps. Learn from past mistakes: if reflections from previous failed attempts are provided below, use them to improve your strategy.\n{reflections}\nTask: {question}\n{scratchpad}"
  }
}
```

## File Change Manifest

| Action | File | Description |
|--------|------|-------------|
| CREATE | `vidbyte/context/algorithms/reflexion.py` | `ReflexionAdmission`, `ReflexionConfig`, helper functions |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add `reflexion` field to `ContextWindowAlgorithm` |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export `ReflexionAdmission`, `ReflexionConfig` |
| MODIFY | `vidbyte/context/__init__.py` | Export `ReflexionAdmission`, `ReflexionConfig` |
| MODIFY | `vidbyte/context/presets.py` | Add reflexion preset properties |
| MODIFY | `vidbyte/__init__.py` | Export `ReflexionAdmission`, `ReflexionConfig` |
| CREATE | `vidbyte/prompts/prompts/reflexion.json` | Reflexion prompt family |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `REFLEXION_REFLECT_PROMPT`, `REFLEXION_AGENT_PROMPT` |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Add `ReflexionPrompts` bundle class |
| MODIFY | `vidbyte/prompts/strategies/__init__.py` | Export `ReflexionPrompts` |
| CREATE | `tests/test_reflexion_algorithm.py` | Algorithm config and helpers tests |
| CREATE | `tests/test_reflexion_prompt.py` | Prompt loading and access tests |

**Summary:** 4 files created, 8 files modified, 0 files deleted.

## Testing Plan

### Unit Tests (`tests/test_reflexion_algorithm.py`)

1. **`test_reflexion_admission_enum_values`** — verify all four enum members exist with correct values
2. **`test_reflexion_config_defaults`** — verify default admission is `REFLEXION`, defaults for max tokens
3. **`test_reflexion_config_custom`** — construct with custom admission and verify fields
4. **`test_reflexion_config_is_frozen`** — verify immutability
5. **`test_context_window_algorithm_default_no_reflexion`** — verify `reflexion` field defaults to `None`
6. **`test_context_window_algorithm_with_reflexion`** — construct with reflexion config
7. **`test_format_reflections_empty`** — returns empty string for empty list
8. **`test_format_reflections_non_empty`** — returns formatted string with header and bullet points
9. **`test_format_last_attempt`** — returns question, truncated scratchpad, and trial marker
10. **`test_build_reflexion_context_none`** — returns empty string for `NONE` strategy
11. **`test_build_reflexion_context_reflexion`** — returns only formatted reflections
12. **`test_build_reflexion_context_last_attempt`** — returns only formatted last attempt
13. **`test_build_reflexion_context_last_attempt_and_reflexion`** — returns both reflections and last attempt
14. **`test_presets_reflexion`** — preset resolves correctly
15. **`test_presets_reflexion_last_attempt`** — preset resolves correctly
16. **`test_presets_reflexion_last_attempt_and_reflexion`** — preset resolves correctly
17. **`test_public_exports`** — verify `ReflexionAdmission` and `ReflexionConfig` are importable from `vidbyte`

### Unit Tests (`tests/test_reflexion_prompt.py`)

1. **`test_reflexion_prompt_family_exists`** — `Prompts().family("reflexion")` returns a dict with `reflect_prompt` and `agent_prompt`
2. **`test_reflexion_reflect_prompt_is_non_empty`** — prompt text is a non-empty string
3. **`test_reflexion_agent_prompt_is_non_empty`** — prompt text is a non-empty string
4. **`test_reflexion_enum_entries`** — `Prompt.REFLEXION_REFLECT_PROMPT` and `Prompt.REFLEXION_AGENT_PROMPT` resolve
5. **`test_reflexion_prompts_bundle`** — `ReflexionPrompts().export()` returns expected dict
6. **`test_reflexion_prompt_contains_placeholders`** — `reflect_prompt` contains `{question}` and `{scratchpad}`; `agent_prompt` contains `{reflections}`, `{question}`, `{scratchpad}`

### Manual Verification

```powershell
python -m compileall vidbyte
python -m unittest tests.test_reflexion_algorithm tests.test_reflexion_prompt
```
