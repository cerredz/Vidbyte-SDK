# Environments

The Vidbyte SDK includes RL-environment primitives for turning agent harnesses
into resettable, verifiable practice worlds with recordable rollout data.

## Role In The SDK

`vidbyte.environments` provides the `Environment` contract (seeded task
generator, materialized workspace, authoritative tool surface, out-of-band
verifier), the declarative `HarnessSpec` describing how an agent is assembled
from SDK primitives, the `EnvironmentRunner` rollout loop, JSONL
`RolloutRecorder` persistence, the `EnvironmentAudit` verifier stress-test kit,
and an `EnvironmentRegistry`. It is exposed through `VidbyteSDK().environments`.

## Design Philosophy

An environment and a harness are the same artifact pointed in opposite
directions: the harness acts on the real world, the environment is a frozen,
replayable copy of that world with a grader attached. Three rules keep rollout
data trustworthy: worlds materialize deterministically from `task.seed` (reset
is re-setup, never snapshot restore), the environment owns the action surface
(specs select within what `Environment.tools()` permits), and the verifier
reads final world state through `EnvSession.verifier_state` channels the agent
cannot touch. Harness configuration is data, not objects: `HarnessSpec` is a
versioned pydantic model, so every recorded pass rate is attributable to an
exact, diffable configuration.

## Usage

```python
from vidbyte import (
    EnvironmentRunner, HarnessSpec, LoopSpec, ModelSpec, RolloutRecorder,
)

spec = HarnessSpec(
    name="baseline",
    system_prompt="You are a careful software maintenance agent.",
    model=ModelSpec(provider="openai", model="gpt-4o"),
    loop=LoopSpec(max_iterations=12),
    tools=({"name": "read_text"}, {"name": "write_text", "settings": {"allow_write": True}}),
    middleware=({"name": "token_budget", "settings": {"max_total_tokens": 200_000}},),
)

runner = EnvironmentRunner(my_env, recorder=RolloutRecorder("rollouts.jsonl"))
record = await runner.arollout(spec, seed=7)
print(record.reward.score, record.reward.passed)
```

Calibration sweeps produce the pass-rate spec sheet across harness specs:

```python
report = await runner.acalibrate([spec_a, spec_b], n_tasks=20)
for cell in report.cells:
    print(cell.spec_name, cell.pass_rate, cell.mean_score)
```

Before publishing an environment, run the audit kit:

```python
from vidbyte import EnvironmentAudit

audit = await EnvironmentAudit(my_env).arun()
assert audit.ok, audit.notes
```

## Key Modules

- `types.py`: `EnvTask`, `EnvSession`, `Reward`, `RolloutRecord`, calibration types.
- `base.py`: `Environment` ABC, `TaskGenerator` protocol, `StaticTaskSet`.
- `spec.py`: `HarnessSpec` plus middleware/tool/algorithm/primitive dispatch tables.
- `resolver.py`: `HarnessSpecResolver` building live `BaseAgent`s from specs.
- `runner.py`: `EnvironmentRunner` rollout and calibration orchestration.
- `records.py`: `RolloutRecorder` append-only JSONL persistence.
- `audit.py`: `DoNothingPolicy`, `EchoPolicy`, `EnvironmentAudit`.
- `registry.py`: `EnvironmentRegistry` name registry.
- `client.py`: `EnvironmentsClient` namespace client.

See `skills/environments/SKILL.md` for the full authoring guide and the
complete HarnessSpec configuration reference.
