# Vidbyte SDK

`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface.

This package is intentionally minimal right now. It establishes the SDK package identity, Python import path, and first harness helpers without including private Vidbyte service logic.

## Status

This package is not published. It is marked `UNLICENSED` until Vidbyte's release, licensing, and open-source strategy are finalized.

## Usage

```python
from vidbyte_sdk import define_harness, run_harness


def run_example(input, context):
    return {
        "ok": True,
        "input": input,
        "context": context,
    }


harness = define_harness(
    name="example-harness",
    run=run_example,
)

result = await run_harness(harness, {"topic": "limits"})
```

## Public Boundary

The SDK should contain reusable harness contracts, helpers, and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte_sdk
python -c "from vidbyte_sdk import define_harness, run_harness; print(define_harness(name='smoke', run=lambda input, context: input).name)"
```
