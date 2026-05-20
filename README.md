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
sdk.strategies
```

## Multi-Agent Orchestration

Multi-agent execution is modeled as composition:

- `vidbyte.agents` contains actor objects such as `BaseAgent` and `AgentRegistry`.
- `vidbyte.strategies.multi_agent` contains orchestration topologies such as consensus routing, AutoGen-style message passing, VMAO, economic gating, and evolving policy routing.
- Harnesses stay clean business boundaries. They attach strategies through `with_strategy()` or `with_strategies()` and do not need a single-agent/multi-agent flag.

```python
from vidbyte.harnesses import BaseHarness
from vidbyte.strategies import BaseStrategy, StrategyResult


class FastStrategy(BaseStrategy):
    async def arun(self, prompt, **kwargs):
        return StrategyResult(output="fast answer", strategy_name="fast")


class DeepStrategy(BaseStrategy):
    async def arun(self, prompt, **kwargs):
        return StrategyResult(output="deep answer", strategy_name="deep")


harness = BaseHarness().with_strategies([FastStrategy(), DeepStrategy()])
result = await harness.arun("Solve this task", runner=my_runner)
```

For custom agents, inject the model runner, reasoning strategy, and tools into `BaseAgent`; then pass those agents into multi-agent strategies.

## Package Structure

```text
vidbyte/
|-- client.py
|-- agents/
|-- harnesses/
|   `-- client.py
|-- providers/
|   `-- client.py
|-- strategies/
|   `-- multi_agent/
|-- tools/
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
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.strategies).__name__)"
```
