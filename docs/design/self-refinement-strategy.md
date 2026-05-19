# Design Doc: Self-Refinement Strategy

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-19
**Last Updated:** 2026-05-19

---

## 1. Overview

Add a Self-Refine prompt/API strategy to the Vidbyte SDK. The strategy will implement the core loop from Madaan et al. (2023): generate an initial answer, ask the same text model for specific actionable feedback, then refine the answer using the feedback, repeating for a configured number of iterations or stopping early when feedback indicates no further changes are needed. The public API will expose the user-requested parameters: create system prompt, refine system prompt, and number of loop repetitions, plus a small feedback system prompt and early-stop controls needed to faithfully implement the paper.

---

## 2. Goals & Non-Goals

### Goals

- Add `SelfRefinementStrategy` under the SDK strategy layer.
- Implement a create/feedback/refine loop using `TextModelRunner.run()`.
- Support user-provided `create_system_prompt`, `refine_system_prompt`, and `iterations`.
- Add a feedback prompt parameter because the paper's loop explicitly requires a feedback-generation step.
- Preserve iteration history in strategy metadata so callers can inspect drafts and feedback.
- Support early stopping when feedback indicates the draft is already sufficient.
- Wire the strategy into `StrategyClient`, package exports, README, SDK skill docs, and tests.
- Update the Obsidian product note with the Self-Refine implementation explanation.

### Non-Goals

- No supervised training, reinforcement learning, reward-model training, or fine-tuning.
- No separate evaluator model or external scoring model.
- No code execution or tool use inside the self-refinement loop.
- No task-specific few-shot prompt library in this PR.
- No automatic best-output selection across multiple divergent trajectories.
- No live provider tests that require API keys or paid calls.

---

## 3. Background & Context

- The standalone SDK repo is `cerredz/Vidbyte-SDK`.
- PR #2 (`feat/prompt-api-strategies-sdk`) adds the strategy framework that this feature depends on:
  - `BaseStrategy`
  - `StrategyResult`
  - `StrategyClient`
  - `TextModelRunner`
  - existing strategy tests under `tests/`
- PR #2 is currently open as a draft and mergeable. This Self-Refinement feature should be implemented after PR #2 is merged into `main`, or as a stacked PR based on `feat/prompt-api-strategies-sdk`.
- The Self-Refine paper is "Self-Refine: Iterative Refinement with Self-Feedback" (`arXiv:2303.17651`, submitted March 30, 2023, revised May 25, 2023).
- The paper describes a loop with three prompts: initial generation, feedback, and refinement. Algorithm 1 defines:
  - `y0 = M(pgen || x)`
  - `fb_t = M(pfb || x || y_t)`
  - stop if `stop(fb_t, t)` is true
  - `y_{t+1} = M(prefine || x || y0 || fb0 || ... || y_t || fb_t)`
- The paper reports that Self-Refine requires no supervised training, additional training, or reinforcement learning; it uses a single LLM as generator, feedback provider, and refiner.
- The analysis section emphasizes that specific, actionable feedback outperforms generic feedback or no feedback, and that most gains occur in early iterations with diminishing returns.
- The paper also notes that quality may not improve monotonically for multi-aspect tasks, so iteration history matters for inspection.

---

## 4. Requirements

### Functional Requirements

1. `SelfRefinementStrategy` must be importable from `vidbyte.strategies.agent_loops`.
2. `StrategyClient` must expose `self_refinement(...)`.
3. `SelfRefinementStrategy` must accept:
   - `create_system_prompt: str`
   - `refine_system_prompt: str`
   - `iterations: int`
4. `SelfRefinementStrategy` must also accept an optional `feedback_system_prompt: str | None`.
5. If `feedback_system_prompt` is omitted, the strategy must use a default prompt that asks for specific, actionable feedback.
6. `iterations` must be positive.
7. Running the strategy must make exactly one initial create call, then up to `iterations` feedback/refine pairs.
8. Feedback calls must include the original task and the current draft.
9. Refine calls must include the original task, the initial draft, the current draft, the latest feedback, and prior loop history.
10. The returned `StrategyResult.output` must be the final refined draft.
11. `StrategyResult.calls` must include every `TextModelResponse` in order.
12. `StrategyResult.metadata` must include structured iteration history containing draft and feedback text.
13. The strategy must support optional early stopping when feedback indicates no changes are needed.
14. The strategy must be fully testable with a fake runner and no network calls.
15. README and SDK skill docs must document the strategy API.
16. The Obsidian note `Vidbyte/product/prompt_engineering_strategies.md` must gain a Self-Refine section.

### Non-Functional Requirements

- Cost control: default iterations should be conservative because each iteration can add two model calls.
- Reliability: if the feedback model returns empty text, raise `StrategyExecutionError`.
- Reliability: if the refine model returns empty text, raise `StrategyExecutionError`.
- Maintainability: keep implementation in `agent_loops/` because Self-Refine is a repeated actor-feedback-refiner loop.
- Compatibility: Python `>=3.11`, zero new runtime dependencies.
- Observability: preserve full loop metadata but do not log secrets or provider headers.
- Security: no tool execution, filesystem access, or arbitrary code execution in this strategy.

---

## 5. High-Level Design

The strategy will live under `vidbyte/strategies/agent_loops/self_refinement.py` and implement the existing `BaseStrategy` contract from PR #2. It will be a prompt/API-only strategy: every create, feedback, and refine step calls `TextModelRunner.run()` with a task-specific prompt and optional system prompt.

The core object will be initialized with prompts and loop controls. `create_system_prompt` drives the initial draft. `feedback_system_prompt` drives critique generation and defaults to a paper-aligned instruction that requests specific, actionable feedback. `refine_system_prompt` drives revised output generation from the original task, drafts, and feedback history. `iterations` controls the maximum number of feedback/refine loops. Early stopping is optional and uses configurable stop phrases in feedback text.

```text
SelfRefinementStrategy.run(prompt, runner)
  |
  |-- create: runner.run(prompt, system=create_system_prompt) -> y0
  |
  |-- for t in range(iterations):
  |     |-- feedback: runner.run(original task + current draft, system=feedback_system_prompt) -> fb_t
  |     |-- stop? feedback says no change needed
  |     `-- refine: runner.run(task + y0 + history + current draft + fb_t, system=refine_system_prompt) -> y_t+1
  |
  `-- StrategyResult(output=current draft, calls=all responses, metadata=history)
```

This implementation follows the paper closely while fitting the SDK's existing strategy model. It does not add a new runner or provider capability; it composes the `TextModelRunner` that already exists in PR #2.

---

## 6. Detailed Design

### 6.1 Self-Refinement Types

**File(s):** `vidbyte/strategies/agent_loops/self_refinement.py`
**Type:** New file

#### What it does

Defines `SelfRefinementStep` and `SelfRefinementStrategy`.

#### Interface / API

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class SelfRefinementStep:
    iteration: int
    draft: str
    feedback: str
    refined: str | None
    stopped: bool = False

class SelfRefinementStrategy(BaseStrategy):
    name: ClassVar[str] = "self_refinement"

    def __init__(
        self,
        *,
        create_system_prompt: str,
        refine_system_prompt: str,
        iterations: int,
        feedback_system_prompt: str | None = None,
        stop_phrases: tuple[str, ...] | None = None,
        stop_on_no_feedback: bool = True,
    ) -> None: ...

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult: ...
```

#### Logic / Algorithm

1. Validate all required prompts are non-empty strings.
2. Validate `iterations > 0`.
3. Generate the initial draft:
   - `runner.run(prompt, system=create_system_prompt)`
4. For each iteration:
   - Build feedback prompt containing original task and current draft.
   - Call `runner.run(feedback_prompt, system=feedback_system_prompt)`.
   - Validate non-empty feedback.
   - If early stop is enabled and feedback includes a stop phrase, append a stopped step and break.
   - Build refinement prompt containing:
     - original task
     - initial draft
     - prior feedback/refinement history
     - current draft
     - latest feedback
   - Call `runner.run(refinement_prompt, system=refine_system_prompt)`.
   - Validate non-empty refined draft.
   - Append a step with draft, feedback, and refined output.
   - Set current draft to refined output.
5. Return `StrategyResult` with the current draft and metadata history.

#### Edge Cases & Error Handling

- Empty `create_system_prompt` raises `StrategyExecutionError`.
- Empty `refine_system_prompt` raises `StrategyExecutionError`.
- Empty generated draft raises `StrategyExecutionError`.
- Empty feedback raises `StrategyExecutionError`.
- Empty refined draft raises `StrategyExecutionError`.
- Stop phrases are matched case-insensitively.
- If the model stops at the feedback stage, no refine call is made for that iteration.

---

### 6.2 Strategy Client Wiring

**File(s):** `vidbyte/strategies/client.py`
**Type:** Modified

#### What it does

Adds a factory method for `SelfRefinementStrategy`.

#### Interface / API

```python
def self_refinement(
    self,
    *,
    create_system_prompt: str,
    refine_system_prompt: str,
    iterations: int,
    feedback_system_prompt: str | None = None,
) -> SelfRefinementStrategy: ...
```

#### Logic / Algorithm

1. Import `SelfRefinementStrategy`.
2. Return a configured instance with provided prompts and iteration count.

#### Edge Cases & Error Handling

- Validation remains inside the strategy constructor.

---

### 6.3 Package Exports

**File(s):** `vidbyte/strategies/__init__.py`, `vidbyte/strategies/agent_loops/__init__.py`
**Type:** Modified

#### What it does

Exports `SelfRefinementStrategy` and `SelfRefinementStep`.

#### Interface / API

```python
from vidbyte.strategies.agent_loops import SelfRefinementStrategy, SelfRefinementStep
```

#### Logic / Algorithm

1. Add imports.
2. Add names to `__all__`.

#### Edge Cases & Error Handling

N/A - package export only.

---

### 6.4 Tests

**File(s):** `tests/test_self_refinement_strategy.py`
**Type:** New file

#### What it does

Adds unit tests for the create/feedback/refine loop.

#### Interface / API

```python
class SelfRefinementStrategyTests(unittest.TestCase): ...
```

#### Logic / Algorithm

Tests cover:

1. Creates an initial draft, then repeats feedback/refine for N iterations.
2. Passes the configured create/refine/feedback system prompts into `runner.run()`.
3. Stores structured iteration history in metadata.
4. Stops early when feedback contains a stop phrase.
5. Rejects invalid prompt/iteration configuration.
6. Raises on empty feedback or refinement.

#### Edge Cases & Error Handling

- Fake runner returns deterministic `TextModelResponse` values.
- Tests assert call count exactly matches expected loop behavior.

---

### 6.5 README And Skill Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Documents the new Self-Refinement strategy and its parameters.

#### Interface / API

```python
strategy = sdk.strategies.self_refinement(
    create_system_prompt="Create a strong first draft.",
    refine_system_prompt="Refine using the feedback.",
    iterations=3,
)

result = strategy.run("Write a short explanation of retrieval practice.", runner=runner)
```

#### Logic / Algorithm

1. Add Self-Refinement to the implemented strategy list.
2. Add a short usage example.
3. Update SDK skill's implemented strategy batch.

#### Edge Cases & Error Handling

N/A - documentation only.

---

### 6.6 Obsidian Product Note

**File(s):** external note `Vidbyte/product/prompt_engineering_strategies.md`
**Type:** External note update

#### What it does

Adds a Self-Refine section to the product note.

#### Interface / API

N/A - external documentation note.

#### Logic / Algorithm

1. Add paper reference.
2. Explain SDK class and parameters.
3. Explain create/feedback/refine loop and limitations.

#### Edge Cases & Error Handling

- Use Obsidian Local REST API if available; filesystem fallback is acceptable.
- Do not include secrets or raw provider responses.

---

## 7. Data Model Changes

### 7.1 `SelfRefinementStep`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class SelfRefinementStep:
    iteration: int
    draft: str
    feedback: str
    refined: str | None
    stopped: bool = False
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

---

## 8. API Changes

N/A - no HTTP endpoint changes.

Python SDK API additions:

```python
from vidbyte.strategies.agent_loops import SelfRefinementStrategy, SelfRefinementStep

sdk.strategies.self_refinement(
    create_system_prompt="...",
    refine_system_prompt="...",
    iterations=3,
)
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/self-refinement-strategy.md` | Design doc for this feature |
| CREATE | `vidbyte/strategies/agent_loops/self_refinement.py` | Self-Refine strategy implementation |
| CREATE | `tests/test_self_refinement_strategy.py` | Unit tests for loop behavior |
| MODIFY | `vidbyte/strategies/client.py` | Add `self_refinement()` factory |
| MODIFY | `vidbyte/strategies/__init__.py` | Export Self-Refinement public API |
| MODIFY | `vidbyte/strategies/agent_loops/__init__.py` | Export Self-Refinement from agent-loop namespace |
| MODIFY | `README.md` | Document usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK skill reference |

Summary: 3 files created, 5 files modified, 0 files deleted.

External non-repo artifact:

| Action | Artifact | Reason |
|--------|----------|--------|
| UPDATE | `Vidbyte/product/prompt_engineering_strategies.md` in Obsidian | Add Self-Refine implementation note |

---

## 10. Testing Plan

### Unit Tests

- `SelfRefinementStrategyTests.test_runs_create_feedback_refine_for_n_iterations`
- `SelfRefinementStrategyTests.test_passes_configured_system_prompts`
- `SelfRefinementStrategyTests.test_metadata_contains_iteration_history`
- `SelfRefinementStrategyTests.test_stops_early_when_feedback_says_no_changes_needed`
- `SelfRefinementStrategyTests.test_rejects_empty_required_prompts`
- `SelfRefinementStrategyTests.test_rejects_non_positive_iterations`
- `SelfRefinementStrategyTests.test_raises_on_empty_feedback`
- `SelfRefinementStrategyTests.test_raises_on_empty_refined_output`

### Integration Tests

- N/A - no live provider integration test. The strategy is tested with fake runners because live provider calls require credentials and cost money.

### Manual / QA Test Cases

1. Create a `TextModelRunner` with a provider API key.
2. Create a self-refinement strategy with 2 iterations.
3. Run it on a writing task.
4. Confirm the final output is returned.
5. Inspect `result.metadata["steps"]` to confirm feedback and refinements are preserved.

Verification commands:

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.strategies.self_refinement(create_system_prompt='create', refine_system_prompt='refine', iterations=1)).__name__)"
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Dataclasses and unit tests | Low |
| Existing `TextModelRunner` | From PR #2 | Executes create, feedback, and refine calls | Feature depends on PR #2 |
| arXiv paper | https://arxiv.org/abs/2303.17651 | Research basis for loop design | Low |
| Obsidian note | `Vidbyte/product/prompt_engineering_strategies.md` | Product documentation | Local vault may be unavailable |

---

## 12. Rollout & Deployment

- Package-only SDK change; no deployed service changes.
- Rollout path:
  1. Merge PR #2 into `main`, then branch this feature from updated `main`; or
  2. Create a stacked PR based on `feat/prompt-api-strategies-sdk`.
- Default branch target remains `main` if PR #2 has merged before implementation.
- If stacked, PR target should be `feat/prompt-api-strategies-sdk` for review clarity.
- Rollback is reverting the feature merge commit.
- No migration is required.

---

## 13. Open Questions

- [ ] Should implementation wait for PR #2 to merge, or should this be a stacked PR against `feat/prompt-api-strategies-sdk`?
- [ ] Should `feedback_system_prompt` be a required parameter to mirror the paper's three-prompt design, or optional with the default described above?
- [ ] Should early stopping be enabled by default, or should exactly `iterations` loops always run to match the user's "how many times this loop should repeat" wording?
- [ ] Should metadata store full draft/feedback text, or should there be an option to store only summaries for lower memory usage?

---

## 14. Alternatives Considered

### Alternative 1: Only Create/Refine Without Feedback

- What: Implement exactly two prompts: create and refine.
- Why rejected: The paper's central contribution is feedback then refinement. Without a feedback step, this becomes generic iterative rewriting and loses the mechanism shown to matter in the ablation analysis.

### Alternative 2: Add Self-Refine Under `sampling/`

- What: Treat self-refinement as another test-time compute sampling strategy.
- Why rejected: It is not independent sampling or voting; it is a stateful feedback/refine loop, so `agent_loops/` better matches the existing SDK categories.

### Alternative 3: Use Separate Create, Feedback, And Refine Runners

- What: Let callers provide different models for draft, critique, and refinement.
- Why rejected: The paper emphasizes a simple standalone approach using the same LLM as generator, feedback provider, and refiner. Multi-model variants can be added later if needed.

### Alternative 4: Select The Best Draft Across Iterations Automatically

- What: Score every iteration and return the best rather than the last.
- Why rejected: That needs a reliable evaluator/scoring prompt or reward model. The first implementation should preserve all history and return the latest refined draft.

---

END OF DESIGN DOC
