# Design Doc: Agentic-Only Trajectory Checkpoints

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

## 1. Overview

Based on user feedback, we will remove the deterministic (heuristic-based) mode from `TrajectoryCheckpointAlgorithm` entirely. Trajectory checkpoints will only be generated agentically via a model/runner call. All deterministic helper functions (`_reasoning_summary`, `_trajectory`, `_output`, `_score`, and `_feedback`) and the `mode` configuration field will be deleted. If the summarizer model call fails, the exception will be logged and recorded, but no deterministic fallback will be generated.

---

## 2. Goals & Non-Goals

### Goals

- Remove all deterministic heuristic code from `TrajectoryCheckpointAlgorithm`.
- Delete `mode` parameter from the algorithm config.
- Update `build_item` to only use the agentic (model-based) prompting and call structure.
- Remove all fallback code to the deterministic heuristic.
- Update unit and integration tests to verify only the agentic trajectory generation flow.

### Non-Goals

- Restoring the deterministic mode or providing hybrid configuration settings.
- Modifying other context-window algorithms like Reflexion.

---

## 3. Background & Context

- In the previous iteration, we supported both `deterministic` and `agentic` modes, retaining the deterministic heuristic methods as a fallback.
- The user has requested to remove the deterministic mode completely, making the trajectory checkpoint generation strictly agentic/model-based.

---

## 4. Requirements

### Functional Requirements

1. **Agentic-Only Generation**: `TrajectoryCheckpointAlgorithm` must only support model-based generation. The `mode` parameter must be removed.
2. **Deletions**: Remove the following methods from `TrajectoryCheckpointAlgorithm`:
   - `_reasoning_summary`
   - `_trajectory`
   - `_output`
   - `_score`
   - `_feedback`
   - `build_item` (the old deterministic one)
3. **Refactored `build_item`**: Rename/replace `build_item` to contain the async model-based call logic.
4. **Error Handling**: If the summarizer model call fails (due to API error, JSON decoding error, etc.), the error is recorded and propagated/raised, or skipped without returning a fallback item.

### Non-Functional Requirements

- **Maintainability**: Reduced codebase footprint by deleting over 100 lines of heuristic rules.

---

## 5. High-Level Design

We will modify `TrajectoryCheckpointAlgorithm` to remove all heuristic functions. Its `after_tool_calls` method will directly invoke the async `build_item` (renamed from `build_agentic_item`) which calls the model. Since there is no longer any deterministic fallback, any failure during LLM invocation will log/record a failure and raise/propagate the error (or gracefully skip injection if configured, but we will propagate it as it is an actual error in the configured mode).

---

## 6. Detailed Design

### 6.1 `TrajectoryCheckpointAlgorithm`
**File(s):** `vidbyte/context/algorithms/trajectory_checkpoints.py`  
**Type:** Modified  

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm(InnerContextWindowAlgorithm):
    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    checkpoint_title: str = "Runtime Checkpoint"
    placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm
1. Remove `mode` config and `score_enabled`.
2. Update `after_tool_calls` to call `await self.build_item(ctx, snapshot, checkpoint_index)` directly.
3. In `build_item`, load prompt asset, stringify history, format prompt, invoke runner, parse JSON, and return `TrajectoryCheckpointContextItem`.
4. If `build_item` fails, record/propagate the exception.

---

## 7. Data Model Changes

### 7.1 `TrajectoryCheckpointAlgorithm` Config
**Change type:** Modified

Remove `mode` and `score_enabled` fields.

---

## 8. API Changes

N/A

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/context/algorithms/trajectory_checkpoints.py` | Remove deterministic code, make build_item strictly agentic |
| MODIFY | `tests/test_trajectory_checkpoint_algorithm.py` | Remove deterministic tests, update integration tests to check agentic only |
| MODIFY | `scripts/test-trajectory-checkpoints.py` | Update verification test list |

---

## 10. Testing Plan

### Unit Tests

- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_prompt_asset_loads_successfully` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_parsing_valid_json` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_parsing_invalid_json_raises_error` [Hidden Failure]

### Integration Tests

- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_invokes_model_call_for_checkpoints` [Integration]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_handles_model_call_failure` [Hidden Failure]

### Manual / QA Test Cases

1. Verify that `python scripts/test-trajectory-checkpoints.py` passes 100%.

---

## 11. Dependencies & External Services

No changes.

---

## 12. Rollout & Deployment

- Trajectory Checkpoints are now strictly model-based.

---

## 13. Open Questions

None.

---

## 14. Alternatives Considered

None.
