# Runnable SDK consumer probes

## Folder Description / Intent

These programs act like external SDK consumers rather than asserting private helper methods. Each scenario builds a real SDK agent or handoff and calls its public run API with a deterministic offline model response. The one private `_runner_cache` injection replaces only the network boundary, so running the probes needs no credentials and creates no charges.

## Non-Goals

- Do not put production SDK logic here; `vidbyte/` owns it.
- Do not call live providers or require API keys.
- Do not treat a failing expectation as proof of a product bug until the public contract and a minimal reproduction are checked.

## File Index

- `README.md` records the probe boundary, how to execute it and findings.
- `run.py` exercises a composed agent/tool/middleware/usage/trace run, a second run with the same agent, validated structured output, typed and prose-fallback handoffs, and a JevAgent preflight with priced usage. Start here to add a new standalone consumer scenario.

## Run

From the repository root: `python -m scripts.sdk_edge_probes.run`.

## Logs

- 2026-10-08 - Use a real priced `TextModelResponse` with an offline runner. A fake with no provider usage cannot prove cost rollups or JEV accounting.
- 2026-10-08 - HandoffAgent intentionally retries invalid structured replies before parsing markdown; provide four scripted responses to exercise the fallback instead of mistaking an exhausted fake for an SDK bug.
