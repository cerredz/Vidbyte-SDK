# SDK consumer programs

## Folder Description / Intent

This folder keeps executable consumer-style SDK programs in the regular test gate. The programs themselves live in `scripts/sdk_edge_probes/run.py` and construct agents, tools, middleware, handoffs and a JEV preflight. Tests call each program rather than reimplementing it so developers can also run `python -m scripts.sdk_edge_probes.run` directly.

## Non-Goals

- Do not test private SDK functions here; add behavioral scenarios to the runnable consumer script.
- Do not call live model or Jev providers; the script substitutes only network boundaries.
- Do not move production behavior here; `vidbyte/` owns implementation.

## File Index

- `README.md` describes why runnable programs are in CI.
- `FEATURE.md` states the observable cross-subsystem behavior.
- `test_consumer_programs.py` runs each example through pytest so regressions fail CI.

## Logs

- 2026-10-08 - Only adding manual scripts leaves them untested in CI; call each real program from this feature pack.
