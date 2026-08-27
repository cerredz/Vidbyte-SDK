# Expose the Per-Model-Call Timeout in Agent Documents

## Overview

`BaseAgent(timeout_seconds=...)` sets the per-model-call HTTP timeout: it flows
through `AgentRunnerConfig.timeout_seconds` (vidbyte/agents/base.py:151) into
`TextModelConfig.timeout_seconds` on every provider request
(base.py:1160-1161), defaulting to 60s per call at the transport layer when
unset. The mechanism is complete — but the declarative YAML surface cannot
reach it: `AgentSettings._ALLOWED_FIELDS` rejects a document-level
`timeout_seconds`, so a YAML-configured agent cannot change its per-call HTTP
timeout and silently runs on the model-config default.

This PR adds `timeout_seconds` as an optional top-level agent-document field,
mirroring the `BaseAgent` constructor kwarg exactly, so standalone agent
documents and harness-declared agents can both configure it.

## Goals

- `timeout_seconds: <positive number>` is accepted at the top level of an
  agent document (and therefore inside harness `agents[]` entries, which
  translate through the same `AgentSettings` validation).
- The value reaches `BaseAgent(**settings.to_agent_kwargs(...))` unchanged,
  which is the entire runtime change: no runner, provider, or transport code
  is touched.
- Validation matches the existing declarative-field patterns: reject booleans,
  non-numbers, NaN/Infinity, and non-positive values, with a
  `ConfigurationError` naming `agent.timeout_seconds`.

## Non-Goals

- Changing `loop.timeout_seconds` semantics (the whole-run wall-clock deadline,
  enforced separately). The two fields keep their constructor-mirrored names;
  the distinction is documented below and in `expected_structure`.
- Per-model or per-provider timeout overrides, fallback-chain timeouts, or a
  `model_config` escape hatch. One field, one meaning.
- Updating `vidbyte/lib/config/loader.py` (the older `AgentDescriptor`
  dialect). The exported loader is `vidbyte/config/loader.py`; the descriptor
  loader is legacy and out of scope.

## Background

`AgentSettings` mirrors the YAML-serializable construction inputs of
`BaseAgent` (its header states this contract). Every other scalar constructor
input a document can express — `provider`, `model_name`, `temperature`,
`max_tool_rounds` — is already a field. `timeout_seconds` is the one scalar
`BaseAgent` constructor input the declarative surface omits.

The harness bridge passes unknown agent-entry keys straight into
`AgentSettings.from_mapping` (`vidbyte/config/loader.py:179-194` maps only
`role`/`params` exclusions and the `model` alias; harness agent entries are
otherwise open-leaf in `vidbyte/harnesses/config.py:203-218`), so allowlisting
the field in `AgentSettings` makes it available in harness `config.yaml`
agents with no loader change.

## Requirements

1. `AgentSettings` gains `timeout_seconds: float | None = None`, added to
   `_ALLOWED_FIELDS`, `from_payload`, `to_agent_kwargs`, and
   `expected_structure`.
2. `__post_init__` validates it through a new `_validated_timeout_seconds`
   classmethod following `_validated_temperature`'s shape (bool rejection,
   numeric coercion, finite check, positivity check).
3. The built agent's `runner_config.timeout_seconds` equals the document
   value; unset stays `None` so the model config keeps its own default.
4. All existing `AgentSettings` subclasses (`BaseAgentSettings` and the
   registered-but-not-loadable variants) inherit the field automatically via
   the shared `from_payload` hook.

## High-Level Design

One file changes. `vidbyte/lib/dataclasses/config.py` gains the field, its
allowlist entry, its validator, and its plumbing through the two mapping
methods plus `expected_structure`. `build_agent()` already forwards
`to_agent_kwargs()` verbatim to `BaseAgent`, and `BaseAgent.__init__` already
accepts the kwarg — the declarative surface is the only gap.

## Detailed Design

### Field and allowlist

```python
timeout_seconds: float | None = None   # placed after temperature
```

`_ALLOWED_FIELDS` gains `"timeout_seconds"`.

### Validation

```python
@classmethod
def _validated_timeout_seconds(cls, value: object) -> float | None:
    # Bounds the per-model-call HTTP timeout to a positive finite number, mirroring temperature's checks.
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise cls._error("'agent.timeout_seconds' must be a number.", "agent.timeout_seconds", actual_type=type(value).__name__)
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise cls._error(f"'agent.timeout_seconds' must be a finite number; got {value}.", "agent.timeout_seconds", actual_value=str(value))
    if number <= 0:
        raise cls._error(f"'agent.timeout_seconds' must be greater than zero; got {number}.", "agent.timeout_seconds", actual_value=number)
    return number
```

`__post_init__` wires it next to the temperature line:
`self.timeout_seconds = self._validated_timeout_seconds(self.timeout_seconds)`.

### Plumbing

- `from_payload`: `timeout_seconds=payload.get("timeout_seconds")` (placed
  after `temperature`).
- `to_agent_kwargs`: `"timeout_seconds": self.timeout_seconds` (placed after
  `"temperature"`).
- `expected_structure`: `"timeout_seconds": "<seconds|null>"` after
  `"temperature"`, making the field discoverable through `view_agent()`.

## Data Model Changes

N/A - in-memory declarative settings only; nothing persisted. Harness `spec_id`
fingerprints are unaffected because `spec.agents` stores the raw document
entries and this PR does not rewrite them (translate-on-read, per the harness
bridge contract).

## API Changes

Additive only: one optional `AgentSettings` field, one allowlist entry, one
kwargs key in `to_agent_kwargs()` output. Documents that omit the field
produce byte-identical agents. Documents that set it construct agents whose
per-model-call HTTP timeout changes from the model-config default to the
document value — which is the requested behavior.

## File Change Manifest

| Action | File | Change |
|---|---|---|
| MODIFY | `vidbyte/lib/dataclasses/config.py` | `AgentSettings.timeout_seconds` field, `_ALLOWED_FIELDS` entry, `_validated_timeout_seconds`, `__post_init__` line, `from_payload`, `to_agent_kwargs`, `expected_structure` |

1 file modified; 0 created; 0 deleted.

## Dependencies

None. `math` is already imported in the file.

## Rollout

Backward compatible: the field is optional with a `None` default and
`_ALLOWED_FIELDS` growth only widens what documents may say. Existing
documents load identically. Consumers adopt by adding
`timeout_seconds: 600` to an agent entry (the vidbyte research harness will
do this in a follow-up vidbyte-repo PR that also reviews its timeout values).

Canonical CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`
(worktree caveats per the local CI verification field guide).

## Open Questions

- The names `agent.timeout_seconds` (per model call) and
  `agent.loop.timeout_seconds` (whole loop) are close enough to confuse a
  reader. Alternative spellings (`model_timeout_seconds`) were rejected to
  preserve the constructor-mirroring contract; if reviewers prefer a distinct
  spelling this is the moment to say so, since it is cheaper to rename before
  any consumer adopts it.

## Alternatives Considered

- **Reuse `loop.timeout_seconds` for both meanings.** Rejected: the loop
  deadline is a whole-run budget enforced between iterations; the HTTP timeout
  is per provider request. One field cannot serve both without either
  cancelling runs at HTTP granularity or waiting a full iteration for a hung
  socket.
- **Name it `model_timeout_seconds`.** Rejected (see open questions):
  `AgentSettings` mirrors `BaseAgent.__init__` kwarg names by contract
  (`max_tool_rounds`, `temperature`, `model_name` all match); breaking that
  correspondence for one field creates a renaming rule with no precedent.
- **Programmatic-only configuration** (callers set `runner_config` after
  `build_agent`). Rejected: the research harness builds agents from YAML
  through `load_harness_agent`/`build_agent`; a programmatic-only knob forces
  post-construction mutation of a frozen-ish agent in application code.
