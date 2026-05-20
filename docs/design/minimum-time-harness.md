# Design Doc: Minimum Time Harness

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

Add the SDK's first time-based harness: `MinimumTimeHarness`, an async template-method harness that runs user-customized work until a clock deadline is reached, ignoring inner completion signals before that deadline. The harness requires a date tool and compaction tool at construction time, validates optional required tool names, tracks start/end/iteration state, periodically compacts history, and gives developers controlled override hooks for the internal time-slice implementation without letting them bypass the outer time contract.

---

## 2. Goals & Non-Goals

### Goals

- Implement a public `MinimumTimeHarness` under `vidbyte.harnesses.time`.
- Require a `BaseDateTool` instance so the harness can use real or fake clocks.
- Require a `BaseCompactionTool` instance so long-running context can be compacted.
- Support both absolute `target_end_time` and relative `minimum_duration` configuration.
- Ensure normal iteration results cannot complete the harness before the deadline.
- Provide a template-method API centered on `execute_time_slice()` for developer customization.
- Validate optional `required_tool_names` against tools attached to the harness.
- Preserve Python `>=3.11` and no runtime dependency additions.
- Add focused stdlib `unittest` coverage using fake date and compaction tools.
- Update README and SDK skill docs with the new time-harness contract.

### Non-Goals

- No background process manager, scheduler, daemon supervisor, or cross-process persistence.
- No provider/model runner integration inside this PR.
- No live model summarization implementation for compaction; developers inject their own compaction tool.
- No generic agent loop, ReAct loop, or multi-agent strategy implementation.
- No guarantee against host process termination, cancellation, OS sleep, machine shutdown, or interpreter crashes.
- No automatic semantic validation of compaction quality in this PR.

---

## 3. Background & Context

- The current `vidbyte-sdk` source is a minimal Python package scaffold. `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`, but the namespace clients are empty.
- Existing design docs under `docs/design/` describe future tool, strategy, agent, and compaction systems, but the audited source does not yet contain those contracts.
- `pyproject.toml` declares Python `>=3.11` and `dependencies = []`.
- The SDK skill file currently says not to add concrete harness/tool/provider implementations until the structure is approved. This design doc is the approval artifact for this specific harness.
- The user request explicitly calls for a date tool, a compaction tool, optional required tools, deterministic time-based termination, and full customization of the internal implementation.

This design intentionally creates the narrow foundation needed by the first time-based harness rather than implementing the broader tool ecosystem from other design docs.

---

## 4. Requirements

### Functional Requirements

1. `MinimumTimeHarness` must be importable from `vidbyte.harnesses.time`.
2. The harness must require a `BaseDateTool` instance.
3. The harness must require a `BaseCompactionTool` instance.
4. The harness must accept either an absolute `target_end_time` or a relative `minimum_duration`.
5. The harness must reject configurations that supply neither or both time bounds.
6. The harness must reject naive datetimes returned by the date tool or passed as `target_end_time`.
7. The harness must record `start_time` from the supplied date tool when execution starts.
8. When `minimum_duration` is used, the harness must compute the target end time from `start_time + minimum_duration`.
9. If the computed or configured target end time is not in the future, the harness must raise a validation error before running work.
10. The harness loop must keep running until the date tool reports `current_time >= target_end_time`.
11. `TimeHarnessIterationResult.signals_completion=True` must not stop the harness before the deadline.
12. Developers must customize the inner work by subclassing `MinimumTimeHarness` and implementing `execute_time_slice(state)`.
13. The harness must provide override hooks for state creation, pre-iteration behavior, post-iteration behavior, compaction decisions, compaction application, iteration error handling, and finalization.
14. The harness must maintain mutable execution state containing input data, start time, target end time, current time, iteration count, status, last output, history, compaction summary, errors, tools, and metadata.
15. The harness must periodically call `BaseCompactionTool.compact_history(state)` based on a configurable compaction interval.
16. After compaction, the harness must store the compacted summary and trim retained history according to configuration.
17. The harness must accept an iterable of additional `BaseTool` objects.
18. The harness must accept `required_tool_names` and fail initialization if any required name is missing from supplied additional tools or the two mandatory tools.
19. Recoverable iteration exceptions must be handled by a configurable policy: record-and-continue by default, or raise immediately when configured.
20. `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` must not be swallowed by the record-and-continue policy.
21. The harness must optionally sleep between time slices using `asyncio.sleep()` to avoid a busy loop when configured.
22. The harness must expose the final `last_output` after the deadline is reached.
23. Tests must verify fake-clock behavior without sleeping in real time.

### Non-Functional Requirements

- Reliability: the time deadline is the only normal successful stop condition.
- Reliability: compaction failures should be surfaced through the same error policy as iteration failures.
- Security: tool metadata and errors must not include secrets by default.
- Maintainability: public package exports must use explicit `__all__`.
- Compatibility: Python `>=3.11`, standard library only.
- Testability: the date tool abstraction must support deterministic fake clocks.
- Observability: state metadata must make elapsed time, remaining time, iteration count, compaction count, and error count inspectable.
- Cost control: compaction interval, sleep interval, history retention, and optional safety iteration limit must be configurable.

---

## 5. High-Level Design

The feature adds a small tool contract and a time-harness package. `BaseDateTool` and `BaseCompactionTool` are specialized SDK tools. `MinimumTimeHarness` receives those tools plus any additional developer tools, validates the construction contract, then owns the outer loop.

The harness follows the Template Method Pattern. The SDK controls the invariant loop: read clock, stop only when the clock expires, compact history, call hooks, and update state. Developers control the useful work by overriding `execute_time_slice()` and optional hooks.

```text
Developer subclass
  `-- execute_time_slice(state)
          ^
          |
MinimumTimeHarness.run(input_data)
  -> date_tool.get_current_time()
  -> validate start/end
  -> while current_time < target_end_time
       -> maybe compact via compaction_tool.compact_history(state)
       -> before_time_slice(state)
       -> execute_time_slice(state)
       -> after_time_slice(state, result)
       -> ignore result.signals_completion for stopping
       -> optional sleep
  -> finalize(state)
  -> return state.last_output
```

Mandatory tools are included in required-tool validation by their `ToolSpec.name`, so developers can express invariants such as `required_tool_names={"date", "compaction", "web_search"}`.

---

## 6. Detailed Design

### 6.1 SDK Error Types

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** New file, Modified

#### What it does

Adds a small SDK exception hierarchy used by the harness and tool contracts.

#### Interface / API

```python
class VidbyteSdkError(Exception):
    """Base class for public SDK errors."""

class ConfigurationError(VidbyteSdkError):
    """Invalid SDK object construction or configuration."""

class ValidationError(VidbyteSdkError):
    """Invalid runtime input or state."""

class HarnessExecutionError(VidbyteSdkError):
    """Harness execution failed."""
```

#### Logic / Algorithm

1. Define typed exceptions without extra dependencies.
2. Export them from `vidbyte.lib.errors`.
3. Use `ConfigurationError` for bad constructor arguments and `ValidationError` for invalid clock/runtime state.

#### Edge Cases & Error Handling

- Error messages should be concise and safe to print.
- No exception details should include API keys, headers, or large raw tool output.

---

### 6.2 Core Tool Contract

**File(s):** `vidbyte/tools/types.py`, `vidbyte/tools/base.py`, `vidbyte/tools/__init__.py`
**Type:** New file, New file, Modified

#### What it does

Defines the minimal public tool metadata contract needed by required-tool validation and specialized date/compaction tools.

#### Interface / API

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

class BaseTool(ABC):
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return stable public metadata for this tool."""

    @property
    def name(self) -> str:
        return self.spec().name
```

#### Logic / Algorithm

1. Validate tool names are non-empty in `ToolSpec.__post_init__`.
2. Keep the contract intentionally small so future tool registry work can extend it without forcing this harness to know about execution semantics.
3. Export `BaseTool` and `ToolSpec` from `vidbyte.tools`.

#### Edge Cases & Error Handling

- Duplicate names are not handled globally here; `MinimumTimeHarness` validates names only within its own attached tools.
- This contract does not add model-facing tool execution APIs.

---

### 6.3 Built-In Time And Compaction Tool Contracts

**File(s):** `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/builtins/time.py`, `vidbyte/tools/builtins/compaction.py`
**Type:** New file, New file, New file

#### What it does

Defines the specialized tool contracts that `MinimumTimeHarness` requires.

#### Interface / API

```python
from abc import abstractmethod
from datetime import datetime, timezone

class BaseDateTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="date", description="Provides the current datetime.")

    @abstractmethod
    def get_current_time(self) -> datetime:
        """Return the current timezone-aware datetime."""

class SystemDateTool(BaseDateTool):
    def get_current_time(self) -> datetime:
        return datetime.now(timezone.utc)

class BaseCompactionTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="compaction", description="Compacts long-running harness state.")

    @abstractmethod
    async def compact_history(self, state: "TimeHarnessState") -> str:
        """Return a compact summary of the current harness state."""
```

#### Logic / Algorithm

1. `BaseDateTool` exposes only the current-time method.
2. `SystemDateTool` provides the production default implementation but is still explicitly passed by callers.
3. `BaseCompactionTool` accepts the current `TimeHarnessState` and returns a summary string.
4. Tests use fake subclasses of both contracts.

#### Edge Cases & Error Handling

- `MinimumTimeHarness` validates timezone awareness rather than trusting the date tool.
- No default no-op compaction tool is supplied, so the compaction requirement remains explicit.

---

### 6.4 Time Harness Types

**File(s):** `vidbyte/harnesses/time/types.py`
**Type:** New file

#### What it does

Defines state, result, status, and config dataclasses for time-based harnesses.

#### Interface / API

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")

class TimeHarnessStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(slots=True)
class TimeHarnessIterationResult(Generic[OutputT]):
    output: OutputT
    signals_completion: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MinimumTimeHarnessConfig:
    target_end_time: datetime | None = None
    minimum_duration: timedelta | None = None
    compaction_interval: int = 5
    history_retention: int = 2
    sleep_interval_seconds: float = 0.0
    continue_on_iteration_error: bool = True
    max_iterations: int | None = None

@dataclass(slots=True)
class TimeHarnessState(Generic[InputT, OutputT]):
    input_data: InputT
    start_time: datetime
    target_end_time: datetime
    current_time: datetime
    status: TimeHarnessStatus = TimeHarnessStatus.ACTIVE
    iteration: int = 0
    last_output: OutputT | None = None
    history: list[TimeHarnessIterationResult[OutputT]] = field(default_factory=list)
    compaction_summary: str | None = None
    compaction_count: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Config validates that exactly one time boundary is provided.
2. `target_end_time` must be timezone-aware when supplied.
3. `minimum_duration` must be positive when supplied.
4. Numeric config values must be non-negative or positive as appropriate.
5. State is intentionally mutable because hooks and compaction update it through the loop.

#### Edge Cases & Error Handling

- `max_iterations` is a safety escape hatch for tests or faulty clocks. The default is `None` so the normal contract remains time-based.
- If `max_iterations` is reached before the deadline, raise `HarnessExecutionError` rather than reporting success.

---

### 6.5 Minimum Time Harness

**File(s):** `vidbyte/harnesses/time/minimum_time.py`, `vidbyte/harnesses/time/__init__.py`, `vidbyte/harnesses/__init__.py`
**Type:** New file, New file, Modified

#### What it does

Implements the public abstract harness. The outer loop is owned by the SDK; useful work is delegated to developer hooks.

#### Interface / API

```python
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Generic

class MinimumTimeHarness(ABC, Generic[InputT, OutputT]):
    def __init__(
        self,
        *,
        date_tool: BaseDateTool,
        compaction_tool: BaseCompactionTool,
        config: MinimumTimeHarnessConfig,
        tools: Iterable[BaseTool] = (),
        required_tool_names: Iterable[str] = (),
    ) -> None: ...

    async def run(self, input_data: InputT) -> OutputT | None: ...

    @abstractmethod
    async def execute_time_slice(
        self,
        state: TimeHarnessState[InputT, OutputT],
    ) -> TimeHarnessIterationResult[OutputT]: ...

    async def before_time_slice(self, state: TimeHarnessState[InputT, OutputT]) -> None: ...
    async def after_time_slice(
        self,
        state: TimeHarnessState[InputT, OutputT],
        result: TimeHarnessIterationResult[OutputT],
    ) -> None: ...
    def should_compact(self, state: TimeHarnessState[InputT, OutputT]) -> bool: ...
    async def apply_compaction(self, state: TimeHarnessState[InputT, OutputT]) -> None: ...
    async def handle_iteration_error(self, state: TimeHarnessState[InputT, OutputT], error: Exception) -> None: ...
    async def finalize(self, state: TimeHarnessState[InputT, OutputT]) -> OutputT | None: ...
```

#### Logic / Algorithm

1. Constructor validates `date_tool` is a `BaseDateTool`.
2. Constructor validates `compaction_tool` is a `BaseCompactionTool`.
3. Constructor stores additional tools as an immutable tuple.
4. Constructor builds the available tool-name set from mandatory tools and additional tools.
5. Constructor verifies every `required_tool_names` entry is present.
6. `run()` reads `start_time` from the date tool and validates timezone awareness.
7. `run()` computes `target_end_time` from config.
8. `run()` creates initial `TimeHarnessState`.
9. Loop reads `current_time` at the top of each iteration.
10. If `current_time >= target_end_time`, mark state completed and break.
11. Validate optional `max_iterations` has not been exceeded.
12. Increment iteration.
13. If `should_compact(state)` returns true, call `apply_compaction(state)`.
14. Call `before_time_slice(state)`.
15. Call `execute_time_slice(state)`.
16. Store result output in `state.last_output`.
17. Append result to `state.history`.
18. Call `after_time_slice(state, result)`.
19. Ignore `result.signals_completion` for stopping decisions.
20. Optionally sleep for `min(config.sleep_interval_seconds, remaining_seconds)` when positive.
21. On recoverable exceptions, call `handle_iteration_error()`.
22. On deadline, call `finalize(state)` and return its value.

#### Edge Cases & Error Handling

- `signals_completion=True` is stored in history metadata but does not stop the loop.
- If `continue_on_iteration_error=True`, errors are recorded and the loop continues until the clock expires.
- `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` propagate.
- Compaction errors follow the same error policy as iteration errors.
- If history retention is `0`, compaction clears retained history after saving the summary.

---

### 6.6 Harness Client And Root SDK Exports

**File(s):** `vidbyte/harnesses/client.py`, `vidbyte/client.py`, `vidbyte/__init__.py`
**Type:** Modified, Modified, Modified

#### What it does

Makes the new harness discoverable while preserving existing `VidbyteSDK().harnesses` construction.

#### Interface / API

```python
class HarnessClient:
    @property
    def minimum_time(self) -> type[MinimumTimeHarness]:
        return MinimumTimeHarness
```

Public imports:

```python
from vidbyte.harnesses.time import MinimumTimeHarness, MinimumTimeHarnessConfig
from vidbyte.tools.builtins import BaseDateTool, SystemDateTool, BaseCompactionTool
```

#### Logic / Algorithm

1. Keep `VidbyteSDK.__init__()` unchanged except imports remain valid.
2. Add a property on `HarnessClient` to help discovery without trying to instantiate an abstract class.
3. Export new classes from package `__init__.py` files with explicit `__all__`.

#### Edge Cases & Error Handling

- The root SDK client must still instantiate with `VidbyteSDK()` and no arguments.
- `HarnessClient.minimum_time` is discoverability sugar; direct imports remain the primary API.

---

### 6.7 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified, Modified

#### What it does

Documents the time harness, required tool contracts, and subclassing pattern.

#### Interface / API

```python
from datetime import timedelta
from vidbyte.harnesses.time import (
    MinimumTimeHarness,
    MinimumTimeHarnessConfig,
    TimeHarnessIterationResult,
)
from vidbyte.tools.builtins import SystemDateTool, BaseCompactionTool

class MyCompactionTool(BaseCompactionTool):
    async def compact_history(self, state):
        return f"iterations={state.iteration}; last={state.last_output}"

class MyHarness(MinimumTimeHarness[str, str]):
    async def execute_time_slice(self, state):
        return TimeHarnessIterationResult(output=f"ran {state.iteration}")

harness = MyHarness(
    date_tool=SystemDateTool(),
    compaction_tool=MyCompactionTool(),
    config=MinimumTimeHarnessConfig(minimum_duration=timedelta(minutes=30)),
)
result = await harness.run("keep working")
```

#### Logic / Algorithm

1. README explains that the harness is duration/deadline based, not completion based.
2. README notes fake date tools are the recommended test pattern.
3. SDK skill updates package guidance to allow `vidbyte/harnesses/time/` and the two built-in tool contracts.

#### Edge Cases & Error Handling

- Documentation must not imply the harness can survive process termination.
- Examples must not include real credentials or provider integrations.

---

## 7. Data Model Changes

### 7.1 Tool Metadata

**Change type:** New

```python
ToolSpec
```

**Migration strategy:** N/A - in-memory SDK metadata only.

### 7.2 Time Harness Runtime State

**Change type:** New

```python
TimeHarnessStatus
TimeHarnessIterationResult
MinimumTimeHarnessConfig
TimeHarnessState
```

**Migration strategy:** N/A - in-memory SDK state only.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

Python SDK public API additions:

```python
from vidbyte.harnesses.time import (
    MinimumTimeHarness,
    MinimumTimeHarnessConfig,
    TimeHarnessIterationResult,
    TimeHarnessState,
    TimeHarnessStatus,
)

from vidbyte.tools import BaseTool, ToolSpec
from vidbyte.tools.builtins import BaseDateTool, SystemDateTool, BaseCompactionTool
```

Modified Python SDK API:

```python
class HarnessClient:
    @property
    def minimum_time(self) -> type[MinimumTimeHarness]: ...
```

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/minimum-time-harness.md` | Design doc for this feature |
| MODIFY | `vidbyte/__init__.py` | Export public time harness and tool contracts |
| MODIFY | `vidbyte/harnesses/__init__.py` | Update general harness entry point with Context Header |
| MODIFY | `vidbyte/harnesses/client.py` | Add `minimum_time` discoverability property |
| CREATE | `vidbyte/harnesses/time/__init__.py` | Time harness exports |
| CREATE | `vidbyte/harnesses/time/types.py` | Time harness config, state, result, status, error, and base tool types |
| CREATE | `vidbyte/harnesses/time/minimum_time.py` | `MinimumTimeHarness` implementation |
| CREATE | `tests/test_minimum_time_harness.py` | Unit tests for loop timing, validation, compaction, required tools, and error policy |

Summary: 5 files created, 3 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_minimum_time_harness.py` -> `test_runs_until_target_time_and_ignores_completion_signal`
- `tests/test_minimum_time_harness.py` -> `test_minimum_duration_computes_deadline_from_start_time`
- `tests/test_minimum_time_harness.py` -> `test_rejects_past_target_end_time`
- `tests/test_minimum_time_harness.py` -> `test_rejects_naive_target_end_time`
- `tests/test_minimum_time_harness.py` -> `test_rejects_naive_date_tool_time`
- `tests/test_minimum_time_harness.py` -> `test_requires_date_tool_contract`
- `tests/test_minimum_time_harness.py` -> `test_requires_compaction_tool_contract`
- `tests/test_minimum_time_harness.py` -> `test_validates_required_tool_names`
- `tests/test_minimum_time_harness.py` -> `test_calls_compaction_at_configured_interval_and_trims_history`
- `tests/test_minimum_time_harness.py` -> `test_records_and_continues_recoverable_iteration_errors_by_default`
- `tests/test_minimum_time_harness.py` -> `test_raises_recoverable_iteration_errors_when_configured`
- `tests/test_minimum_time_harness.py` -> `test_max_iterations_before_deadline_raises_harness_execution_error`
- `tests/test_minimum_time_harness.py` -> `test_harness_client_exposes_minimum_time_class`

### Integration Tests

- Use a fake date tool that advances on each `get_current_time()` call and a recording compaction tool.
- Use a concrete test subclass of `MinimumTimeHarness` whose `execute_time_slice()` returns `signals_completion=True` on the first iteration.
- Verify the returned output comes from the final iteration before the fake clock reaches the deadline.
- No live provider calls, external APIs, subprocesses, or real sleeping are required.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Run an import smoke test:

```python
from vidbyte import VidbyteSDK
from vidbyte.harnesses.time import MinimumTimeHarness, MinimumTimeHarnessConfig
from vidbyte.tools.builtins import SystemDateTool, BaseCompactionTool

sdk = VidbyteSDK()
print(sdk.harnesses.minimum_time)
print(MinimumTimeHarness, MinimumTimeHarnessConfig, SystemDateTool, BaseCompactionTool)
```

4. Run a fake-clock harness for three iterations and confirm it does not stop when the first iteration signals completion.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Dataclasses, datetime, abc, asyncio, unittest | No durable daemon supervision; process lifetime remains caller-owned |

No new package dependencies or external services are added.

---

## 12. Rollout & Deployment

- This is a package-only SDK change; no deployed service is updated.
- This feature is additive for the current scaffold.
- Implementation must occur in an isolated feature worktree after explicit design approval.
- Rollout sequence:
  1. Commit this design doc first in the feature branch.
  2. Add SDK error classes.
  3. Add minimal tool metadata and base contracts.
  4. Add built-in date and compaction tool contracts.
  5. Add time harness types.
  6. Implement `MinimumTimeHarness`.
  7. Wire exports and `HarnessClient.minimum_time`.
  8. Add tests.
  9. Update README and SDK skill docs.
- Rollback is reverting the feature branch merge commit.

---

## 13. Open Questions

- [ ] Should `continue_on_iteration_error` default to record-and-continue, as designed, or should the safer default be fail-fast with an explicit opt-in for endurance behavior?
- [ ] Should `SystemDateTool` return UTC only, or allow a timezone constructor parameter in the first implementation?
- [ ] Should the harness expose a sync `run_sync()` wrapper, or remain async-only for the first release?
- [ ] Should compaction run before or after the current iteration when `iteration % compaction_interval == 0`? This design runs compaction before the time slice for that iteration.
- [ ] Should required tool validation use exact names only, or also allow classes/types in the first release?
- [ ] Should semantic validation of compaction summaries be a later optional hook, or part of the required compaction contract?

---

## 14. Alternatives Considered

### Alternative 1: Hard-code `datetime.now()` inside the harness

- What: Have `MinimumTimeHarness` call the system clock directly.
- Why rejected: The user explicitly requested a date tool, and fake clocks are essential for deterministic tests.

### Alternative 2: Make completion signals stop the loop early

- What: Let `execute_time_slice()` return `signals_completion=True` to finish before the deadline.
- Why rejected: This conflicts with the central requirement that the harness runs until time expires no matter what the inner implementation reports.

### Alternative 3: Provide a default no-op compaction tool

- What: Make compaction optional by defaulting to a no-op implementation.
- Why rejected: The user explicitly wanted developers to pass a compaction tool. A no-op default would weaken the long-running context invariant.

### Alternative 4: Implement the full advanced tool ecosystem first

- What: Add `ToolRegistry`, `ToolExecutor`, MCP, search tools, patching, and compaction tools before the time harness.
- Why rejected: That broader design exists separately, but this feature needs only a narrow tool contract plus date/compaction abstractions. Keeping this PR focused reduces the implementation blast radius.

### Alternative 5: Make the harness a concrete class that accepts a callback function

- What: Construct `MinimumTimeHarness(execute_time_slice=callable, ...)` instead of requiring subclassing.
- Why rejected: The user asked for full customization of under-the-hood implementation. The Template Method Pattern gives developers a stable outer contract plus multiple override hooks without turning the constructor into a large callback surface.

---

END OF DESIGN DOC
