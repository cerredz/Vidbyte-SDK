# `vidbyte/agents/jev/done_criteria`

## Folder Description / Intent

This package contains the named, deterministic criteria that decide whether a Jev run may accept a model-originated completion attempt. Criteria own their pass/fail rules and the feedback/result metadata those rules produce. The package optimizes for explicit, typed policy that can be evaluated without another model call.

The runtime clock, agent-loop continuation mechanics, and provider invocation do not belong here. Those responsibilities remain in `vidbyte/agents/jev/runtime.py` and `vidbyte/agents/runtime.py`; this package receives elapsed duration as an input and returns an evaluation.

## Non-Goals

- Do not add model or provider calls; provider adapters and runners belong in `vidbyte/providers/` and `vidbyte/lib/runners/`.
- Do not own generic agent budgets or output contracts; those belong in `vidbyte/agents/settings/` and `vidbyte/agents/contracts/`.
- Do not access `time.monotonic` or store per-run timestamps; runtime attempt state belongs in `vidbyte/agents/runtime.py`.
- Do not mutate or append provider messages; completion continuation belongs in the runtime loop.
- Do not add YAML parsing or construct agents from declarative configuration; that belongs in `vidbyte/config/`.
- Do not define general-purpose runtime interfaces used outside Jev; shared execution contracts belong in `vidbyte/agents/runtime.py`.
- Do not implement Jev decision transport or TypeSafe payload schemas; those belong in Jev's provider/data layers.

## File Index

- `__init__.py` exports the supported criteria API. Update it whenever a new criterion or preset is added.
- `base.py` defines the criterion result, abstract criterion contract, and AND-composing evaluator. Open it when changing how multiple criteria combine or produce feedback/metadata.
- `criteria.py` implements the minimum-time criterion and validates duration units. Open it when changing duration boundaries or adding a concrete criterion subclass.
- `presets.py` exposes named convenience factories. Keep factories thin and delegate all validation to the corresponding criterion class.

## Logs

- 2026-09-24 - Gate both plain final text and `isDone` - either path can otherwise bypass a minimum-duration rule.
