# Vidbyte SDK

`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface.

This package is intentionally minimal right now. It establishes the SDK package identity and namespace layout without including private Vidbyte service logic.

## Status

This package is not published. It is marked `UNLICENSED` until Vidbyte's release, licensing, and open-source strategy are finalized.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.harnesses
sdk.tools
sdk.providers
```

## Minimum Time Harness

`MinimumTimeHarness` is the SDK's first time-based harness. It runs an
async, developer-defined time slice until a clock deadline is reached. Inner
iteration results can signal completion, but the harness does not stop early;
normal completion is based only on the supplied date tool reaching the target
time.

```python
from datetime import timedelta

from vidbyte.harnesses.time import (
    MinimumTimeHarness,
    MinimumTimeHarnessConfig,
    TimeHarnessIterationResult,
)
from vidbyte.tools.builtins import BaseCompactionTool, SystemDateTool


class SummaryCompactionTool(BaseCompactionTool):
    async def compact_history(self, state):
        return f"iterations={state.iteration}; last={state.last_output}"


class MonitorHarness(MinimumTimeHarness[str, str]):
    async def execute_time_slice(self, state):
        return TimeHarnessIterationResult(
            output=f"processed {state.iteration}",
            signals_completion=True,
        )


harness = MonitorHarness(
    date_tool=SystemDateTool(),
    compaction_tool=SummaryCompactionTool(),
    config=MinimumTimeHarnessConfig(minimum_duration=timedelta(minutes=30)),
)
```

Use fake `BaseDateTool` implementations in tests so time can advance without
real sleeps.

## Package Structure

```text
vidbyte/
|-- client.py
|-- harnesses/
|   |-- client.py
|   `-- time/
|-- providers/
|   `-- client.py
|-- tools/
|   |-- builtins/
|   `-- client.py
|-- shared/
`-- lib/
    `-- errors/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.harnesses.minimum_time).__name__)"
```
