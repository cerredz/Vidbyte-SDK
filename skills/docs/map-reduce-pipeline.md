# Map-Reduce Pipeline

## Requirements

- `MapReducePipeline` accepts `map_stages: Sequence[PipelineNode]` and `reduce_stage: PipelineNode`
- `map_stages` must be non-empty
- All map stages receive the same `prompt` and run concurrently via `asyncio.gather`
- Map outputs are joined with a configurable separator (default: `"\n\n---\n\n"`, same as `ParallelPipeline`)
- The joined string becomes the prompt to `reduce_stage`
- Returns `reduce_stage`'s output
- Raises `PipelineExecutionError` if `map_stages` is empty
- Supports nesting (map stages and reduce stage can be agents or pipelines)
- Exposes `run_sync()` through `BasePipeline` inheritance
- Export from `vidbyte.pipelines` and `vidbyte`

## Non-goals

- N/A — minimal, well-bounded scope

## Risks

| Risk | Mitigation |
|------|-----------|
| Long map outputs compound into enormous reducer prompt | Same risk as `ParallelPipeline`; no mitigation in this change |
| All map stages fail if one fails (`asyncio.gather` default) | Matches `ParallelPipeline` behavior; consistent |
| User confusion with `ParallelPipeline` | Clear naming and docstrings; MapReduce has a reducer, Parallel does not |

## Open Questions

- N/A — scope is fully determined by existing patterns

## Rollout

- Add `map_reduce.py` to `vidbyte/pipelines/`
- Add export to `vidbyte/pipelines/__init__.py`
- Add export to `vidbyte/__init__.py`
- Add test class to `tests/test_pipelines.py`
- No migrations, no breaking changes

## Rollback

- Remove `map_reduce.py`, revert `__init__.py` changes. No other code depends on pipelines.

## High-Level Design

`MapReducePipeline` composes the fan-out of `ParallelPipeline` with a final sequential reduction step:

```
prompt → [map_stage_1, map_stage_2, ..., map_stage_N]  (concurrent)
          ↓ outputs joined with separator
       reduce_stage → final output
```

It is a standalone `BasePipeline` subclass that reuses `_invoke` and `asyncio.gather` from existing conventions. It does not inherit from or wrap `ParallelPipeline`/`SequentialPipeline`.

## Detailed Design

**File:** `vidbyte/pipelines/map_reduce.py`

```python
class MapReducePipeline(BasePipeline):
    def __init__(
        self,
        map_stages: Sequence[PipelineNode],
        reduce_stage: PipelineNode,
        *,
        separator: str = MAP_REDUCE_JOIN_SEPARATOR,
    ) -> None:
        if not map_stages:
            raise PipelineExecutionError("MapReducePipeline requires at least one map stage.")
        self._map_stages = tuple(map_stages)
        self._reduce_stage = reduce_stage
        self._separator = separator

    async def run(self, prompt: str) -> str:
        outputs: list[str] = await asyncio.gather(
            *[self._invoke(stage, prompt) for stage in self._map_stages]
        )
        combined = self._separator.join(outputs)
        return await self._invoke(self._reduce_stage, combined)
```

**Constant:** `MAP_REDUCE_JOIN_SEPARATOR = "\n\n---\n\n"` (reusing `PARALLEL_JOIN_SEPARATOR`'s value for consistency across pipeline types).

## File Change Manifest

| Action | File |
|--------|------|
| CREATE | `vidbyte/pipelines/map_reduce.py` |
| MODIFY | `vidbyte/pipelines/__init__.py` |
| MODIFY | `vidbyte/__init__.py` |
| MODIFY | `tests/test_pipelines.py` |

## Data Model, API, Schema Impacts

N/A — no new data structures, no new API endpoints. Pure pipeline primitive addition.

## Testing Plan

**Unit tests** in `MapReducePipelineTests(unittest.IsolatedAsyncioTestCase)`:

1. `test_single_map_stage_produces_reduced_output` — one map stage + reducer
2. `test_multiple_map_stages_converge_to_reducer` — two PrefixAgents as map stages, PrefixAgent as reducer
3. `test_map_stages_receive_same_input` — RecordingAgents confirm identical prompt across map stages
4. `test_empty_map_stages_raises_at_construction` — assert `PipelineExecutionError`
5. `test_map_stage_failure_propagates` — `FailingAgent` in map stages aborts pipeline
6. `test_reduce_stage_failure_propagates` — `FailingAgent` as reducer propagates error
7. `test_custom_separator` — custom separator between map outputs
8. `test_nested_pipeline_as_map_stage` — `SequentialPipeline` as a map stage
9. `test_nested_pipeline_as_reduce_stage` — `ParallelPipeline` as reduce stage
10. `test_is_base_pipeline_instance` — `assertIsInstance(pipeline, BasePipeline)`

**Run sync test** in existing `RunSyncTests`:

- `test_run_sync_map_reduce` — `MapReducePipeline([PrefixAgent("map:")], PrefixAgent("reduce:")).run_sync("x")`

## Verification

```bash
python -m pytest tests/test_pipelines.py -v
```
