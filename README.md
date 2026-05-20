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

### Red-Team Challenge Harness

`RedTeamChallengeHarness` coordinates separate blue-team and red-team pipelines. The blue pipeline updates an artifact, the red pipeline attacks the latest artifact, and the harness scores each round for resilience.

```python
from vidbyte.harnesses.red_team import (
    HarnessPipeline,
    RedTeamChallengeHarness,
)

blue = HarnessPipeline(name="builder", model_fn=blue_model)
red = HarnessPipeline(name="breaker", model_fn=red_model)

harness = RedTeamChallengeHarness(blue_pipeline=blue, red_pipeline=red)
result = await harness.arun("Build a validator for uploaded metadata")
```

Red-team tools are developer supplied. The SDK does not ship destructive scanners, fuzzers, or host-mutating tools with this harness.

### Context Remover Harness

`ContextRemoverHarness` wraps long-running execution and periodically replaces noisy active history with a compact semantic baseline.

```python
from vidbyte.harnesses.context_remover import (
    ConditionalHarnessState,
    ContextRemoverHarness,
)

state = ConditionalHarnessState(original_intent="Keep the migration focused.")
wrapper = ContextRemoverHarness(
    original_intent=state.original_intent,
    purifier_model_fn=purifier_model,
)

result = await wrapper.intercept_step(state, downstream_step)
```

This wrapper mutates `ConditionalHarnessState.history` by design. Keep any external audit log outside that active state when raw trace retention is required.

## Package Structure

```text
vidbyte/
|-- client.py
|-- harnesses/
|   |-- client.py
|   |-- context_remover/
|   `-- red_team/
|-- prompts/
|-- providers/
|   `-- client.py
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
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.harnesses).__name__)"
```
