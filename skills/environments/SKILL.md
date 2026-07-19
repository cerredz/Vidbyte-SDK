<!-- Context Protocol Header
Description:
    Skill documentation for the RL environment abstraction in the Vidbyte SDK.
Purpose:
    Explains how environments are built from SDK primitives, the full HarnessSpec
    configuration reference, rollout/calibration workflows, and the audit rules
    an environment must pass before publication.
Architecture:
    SDK Skill Guide.
Relations:
    Located in skills/environments/SKILL.md. Documents vidbyte/environments.
Similar Files:
    - skills/agent-runtimes/SKILL.md: Runtime selection guide referenced here.
    - skills/agentic-loop-settings/SKILL.md: Loop budget guide mirrored by LoopSpec.
-->

# Environments Skill Guide

This guide explains how the Vidbyte SDK's environment abstraction is built, how to configure harnesses declaratively with `HarnessSpec`, and how to author, audit, and calibrate a new RL environment.

---

## 1. Why Environments

A **harness** runs an agent against the real world to do work. An **environment** is the same artifact pointed the other way: a frozen, replayable copy of that world with a grader attached. Labs buy environments — practice worlds where a model can attempt a task millions of times against an automatic verifier — because a pile of traces gets consumed once, while an environment produces training signal forever.

Three contracts make the duality work, and they are baked into `vidbyte.environments`:

1. **Every environment has a verifier.** `Environment.verify()` inspects the final world state (not the agent's chat output) and returns a `Reward` with per-criterion partial credit.
2. **Tools are binding-swappable.** SDK tools take their target as configuration (`FileSystemToolConfig(root=...)`, `root_dir=...`), so the same tool classes run live in a harness or sandboxed in an environment workspace.
3. **Every rollout is recorded.** `RolloutRecord` captures the task, the full harness configuration, the trajectory, the verified reward, consent level, and cost — one JSONL line per rollout.

## 2. Anatomy of an Environment

Every environment has five parts:

| Part | Where it lives | Rule |
|------|----------------|------|
| World/state | `Environment.setup(task)` → `EnvSession.workspace_dir` | Materialized **deterministically from `task.seed`** — reset is re-setup, never snapshot restore |
| Action surface | `EnvSession.tools` + `Environment.tools()` | The environment owns it; specs only select within it |
| Task generator | `Environment.generator` (`TaskGenerator` protocol) | `generate(seed, **knobs)`; equal seeds and knobs produce equal tasks |
| Verifier | `Environment.verify(session, trajectory)` | Reads final state via `session.verifier_state`, channels the agent cannot touch; awards partial credit |
| Difficulty | `EnvTask.difficulty` + `EnvironmentRunner.acalibrate` | Target 10–60% frontier pass rate; publish the calibration report |

Seeded materialization is the load-bearing trick: because `setup(task)` is a pure function of the task, rollouts parallelize without snapshot infrastructure, and `EnvironmentAudit` can verify determinism mechanically.

## 3. The Environment Contract

```python
from vidbyte import Environment, EnvSession, EnvTask, Reward, CriterionResult, StaticTaskSet

class MyEnvironment(Environment):
    name = "invoice-reconciliation"
    version = "0.1.0"                       # bump on ANY generator or verifier change

    def __init__(self) -> None:
        self.generator = MyTaskGenerator()  # or StaticTaskSet([...]) while bootstrapping

    def setup(self, task: EnvTask) -> EnvSession:
        # Build the workspace deterministically from task.seed, stash ground truth
        # in verifier_state (never inside the workspace the agent can grep).
        ...

    async def verify(self, session, trajectory) -> Reward:
        criteria = [CriterionResult(name="...", passed=..., score=..., detail="...")]
        return Reward.from_criteria(criteria)

    def teardown(self, session) -> None: ...

    def permitted_tool_names(self, session) -> tuple[str, ...] | None:
        return ("fs_read_text", "fs_write_text", "grep")   # pin the action surface
```

Rules the base class enforces or expects:

- **Authority rule.** `Environment.tools(session, requested)` starts from environment-owned tools, drops requested tools that collide or are not permitted (recorded in `session.metadata["dropped_tools"]`). Requested tools never widen the surface.
- **Verifier isolation.** Ground truth, rubrics, and canonical assets live in `session.verifier_state` or outside the workspace. If the agent can read or edit what the verifier checks, the environment is reward-hackable and worthless.
- **Versioning.** The tool contract, generator, and verifier are the environment's identity. Any change to them bumps `version`; `RolloutRecord` pins `env_version` so old data stays interpretable.
- **Empty criteria never pass.** `Reward.from_criteria([])` is `score=0.0, passed=False`.

### 3.1 Reusing evals graders in `verify`

You do not have to hand-roll grading. The `vidbyte.evals` grader catalog (`RubricGrader`, `LLMJudgeGrader`, `ContainsGrader`, `JSONSchemaGrader`, `RegexMatchGrader`, `ForbiddenContentGrader`, composite `AllOfGrader`/`WeightedGrader`, …) plugs straight into a verifier through `grade_with`:

```python
from vidbyte import grade_with
from vidbyte.evals.graders import RubricGrader, ForbiddenContentGrader
from vidbyte.evals.types import EvalCase

async def verify(self, session, trajectory) -> Reward:
    output = (session.workspace_dir / "answer.txt").read_text()   # or trajectory[-1]["content"]
    case = EvalCase(prompt=session.task.instructions, expected=session.verifier_state["expected"])
    return await grade_with([RubricGrader(...), ForbiddenContentGrader(...)], case, output)
```

Each grader becomes one criterion (named by `grader.name`), folded via `Reward.from_criteria` (all-pass AND, mean score). Two rules:

- **You choose the string.** evals graders score a string; environments grade world state. Feed the agent's final output for output-shaped criteria, or a file read out of `workspace_dir` for state-shaped criteria. Checks with no string (a file exists, tests exit 0, a checksum matches) stay hand-written — `grade_with` complements state grading, it does not replace it.
- **Graders belong to the environment, never the `HarnessSpec`.** The verifier is not a swept axis; grading with a config you are also sweeping makes pass rates uninterpretable.

## 4. HarnessSpec Reference

`HarnessSpec` is the declarative, versioned, JSON-round-trippable description of how an agent is assembled. Specs are **data, not objects**: recordable, diffable, sweepable. All models are pydantic v2 with `extra="forbid"` — typos are errors.

```python
from vidbyte import HarnessSpec, ModelSpec, LoopSpec, RuntimeSpec

spec = HarnessSpec(
    name="compaction-sweep-a",
    system_prompt="...",                     # or system_prompt_ref="<prompt catalog key>"
    model=ModelSpec(provider="anthropic", model="claude-sonnet-4-20250514", temperature=0.2),
    runtime=RuntimeSpec(kind="linear"),
    loop=LoopSpec(max_iterations=15, max_tokens=120_000),
    context_algorithm={"preset": "trajectory_checkpoints", "settings": {"interval": 4}},
    context_primitives=({"kind": "text", "fields": {"title": "Policy", "content": "..."}, "managed": True},),
    middleware=({"name": "token_budget", "settings": {"max_total_tokens": 250_000}},),
    tools=({"name": "fs_read_text"}, {"name": "grep"}),
    trace={"tracer": "debug", "continual": True, "every_n_iterations": 5},
    output_schema=None,
)
payload = spec.model_dump()                  # goes into RolloutRecord.harness verbatim
```

### 4.1 ModelSpec

| Field | Notes |
|-------|-------|
| `provider`, `model` | Validated against `ProviderModelRegistry` at spec time |
| `temperature` | Optional float |

API keys are **never** in specs; they resolve from provider environment variables at runtime.

### 4.2 LoopSpec (mirrors `AgentLoopSettings` field-for-field)

`max_iterations`, `max_tokens`, `max_tool_calls`, `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`. All budgets must be positive; the compaction target must stay below the trigger.

### 4.3 RuntimeSpec

| `kind` | Extra fields | Restrictions |
|--------|-------------|--------------|
| `linear` (default) | — | Fully compatible with every other axis |
| `mcts_search` | — | No middleware, no continual trace, no context algorithms |
| `actor` | `topology` (`actor_model` \| `actor_model_p2p` \| `actor_model_broadcast`), `dynamic_actors`, `max_loop`, `termination_mode` (`coordinator` \| `quiescence`), `worker_model` | Same restrictions as MCTS |

The spec validator rejects incompatible combinations at construction — the same rules `BaseAgent` enforces (see `skills/agent-runtimes/SKILL.md`).

**One HarnessSpec resolves to one top-level policy.** A multi-*actor* topology is expressed here through `kind="actor"`, not by declaring several agents — the resolver builds exactly one `BaseAgent` exposing `arun`, and the environment contract only needs `arun` plus a final world state to verify, so it is insulated from policy shape. Heterogeneous multi-agent DAGs (distinct model/tools/context per node) are a planned versioned extension: a reusable per-agent sub-spec composed recursively via agent-as-tool, added under a new `spec_version` (recorded rollout data is protected because `RolloutRecord.harness` stores the spec as an opaque mapping). See the design note in `vidbyte/environments/resolver.py`.

### 4.4 ContextAlgorithmSpec

`preset` is one of: `default`, `raw_tool_outputs`, `compact_tool_outputs`, `hide_tool_outputs`, `no_raw_tool_outputs`, `reflexion`, `multi_provider_agentic_grader`, `trajectory_checkpoints`, `problem_space_search`, `error_correction`. Optional overrides: `tool_result_admission` (`raw` \| `compact` \| `hide_raw`), `max_tool_result_chars`.

`settings` keys are validated against the preset's algorithm dataclass:

| Preset | Valid settings |
|--------|----------------|
| `reflexion` | `max_trials`, `max_reflection_chars`, `max_attempt_chars`, `agent_system_prompt`, `reflect_system_prompt`, `reflect_prompt` |
| `multi_provider_agentic_grader` | `grader_provider`, `grader_model`, `agent_system_prompt`, `grader_system_prompt`, `grader_prompt`, `max_grader_chars` |
| `trajectory_checkpoints` | `interval`, `max_checkpoints`, `max_checkpoint_chars`, `max_field_chars`, `include_tool_outputs`, `checkpoint_title`, `placement` |
| `problem_space_search` | `interval`, `max_notes`, `max_note_chars`, `max_field_chars`, `include_tool_outputs`, `note_title`, `explorer_prompt`, `placement` |
| `error_correction` | `interval`, `max_passes`, `max_notice_chars`, `max_field_chars`, `max_corrections`, `include_tool_outputs`, `notice_title`, `auditor_prompt`, `placement` |

### 4.5 ContextPrimitiveSpec

`kind` is one of: `text`, `file`, `git_diff`, `document`, `environment`, `memory`, `task`, `progress`, `plan`, `artifact`, `response`, `tool_call`. `fields` passes to the primitive constructor. `placement` is any `ContextWindowPlacement` value (`top_of_context`, `end_of_context`, `top_of_conversation`, `end_of_conversation`). `managed=True` upserts the primitive into a `ContextManager` (addressable, placement-aware); `managed=False` injects it as a plain context item.

### 4.6 MiddlewareSpec (linear runtime only)

Valid names: `audit_log`, `canary_tripwire`, `circuit_breaker`, `confused_deputy_guard`, `cost_budget`, `exponential_backoff_retry`, `honeypot_tool`, `loop_detection`, `message_history_compaction`, `model_retry`, `runtime_limits`, `summary_compaction`, `token_budget`, `token_rate_limit`, `tool_policy`, `tool_result_compaction`, `trace_replacement_compaction`, `trace_summary_tail_compaction`. `settings` passes to the middleware constructor; spec order is pipeline order; duplicates are rejected.

### 4.7 HarnessToolSpec

Valid names (spec names equal each tool's runtime `ToolSpec.name`, so `permitted_tool_names` and model-facing schemas share one namespace):

- **Builtins:** `calculator`, `code_execution`, `glob`, `grep`, `semantic_search`, `patch_file`, `document_retrieval`, `create_handoff`, `attach_mcp_server`, `search_mcp_servers`, `reflexion`, `trajectory_checkpoint`, `context_upsert`, `context_list`, `context_remove`.
- **Filesystem suite:** `read_text`, `read_lines`, `read_binary`, `write_text`, `append_text`, `replace_text`, `list_dir`, `tree`, `find`, `stat`, `exists`, `diff`, `checksum`, `copy`, `move`, `delete`, `make_dir`, `touch`, `zip`, `unzip`.

Workspace scoping is the default: filesystem tools get `root=str(session.workspace_dir)` and code-search/patch tools get `root_dir=...` unless `settings` overrides them. Write-capable filesystem tools still require `{"allow_write": true}`. Context tools (`reflexion`, `trajectory_checkpoint`, `context_*`) receive the resolved `ContextManager` automatically. Memory-provider tools (Cognee/Letta/Mem0/Supermemory/Zep) are excluded from spec v1 because they require external credentials; use the prebuilt-agent escape hatch for those.

Remember the authority rule: requested tools are filtered through `Environment.tools()`. A published pass rate is only comparable when the environment pinned its surface via `permitted_tool_names`.

**Registering a new spec-selectable builtin.** The valid names above (and for middleware and context primitives/algorithms) come from the dispatch tables in `vidbyte/lib/config/harness_tables.py` — `VIDBYTE_MIDDLEWARE_TABLE`, `VIDBYTE_TOOL_TABLE`, `VIDBYTE_FILESYSTEM_TOOL_TABLE`, `VIDBYTE_PRIMITIVE_TABLE`, `VIDBYTE_ALGORITHM_SETTINGS_OWNERS`, plus the companion name sets. When a new builtin should be spec-selectable: (1) add it to the matching table with its key **equal to its runtime name** (e.g. a tool's `ToolSpec.name`) — never prefix or rename the key, or you break the shared namespace with `permitted_tool_names` and the model-facing schema; (2) update the name list in this section. These tables are hand-maintained for now; a tracked follow-up derives them from the builtin registries so they cannot drift.

### 4.8 TraceSpec

`tracer`: `null` (default) or `debug`. `continual=True` enables the continual trace artifact with `schema_preset="action"` (the built-in `ActionTraceModel`) or an inline `schema_fields` name→description map, plus `every_n_iterations` (> 0) and `max_trace_iterations` (1–3). Continual tracing requires the linear runtime.

## 5. Running Rollouts

```python
from vidbyte import EnvironmentRunner, RolloutRecorder

runner = EnvironmentRunner(env, recorder=RolloutRecorder("rollouts.jsonl"), consent="private", concurrency=4)
record = await runner.arollout(spec, seed=42)                  # one seeded rollout
records = await runner.arollout_many(spec, tasks)              # bounded concurrency
report = await runner.acalibrate([spec_a, spec_b], n_tasks=20) # pass-rate spec sheet
```

Lifecycle per rollout: generate task → `setup` → build agent from spec → run → serialize trajectory → `verify` → `teardown` (guaranteed) → record. Agent and verifier failures become failed records (`error` set, `Reward.failure`), never crashes — except `setup` failures, which raise loudly because a broken world invalidates everything.

A prebuilt agent (anything with `arun`) may be passed instead of a spec for local experimentation. It is recorded as `{"opaque": ...}`, bypasses the authority filter, and is restricted to `concurrency=1`. **Never publish numbers from opaque rollouts.**

`CalibrationReport` cells carry `pass_rate`, `mean_score`, and `by_difficulty` per spec — this is the "Claude passes 34%, GPT passes 41%" spec sheet, and because the harness axis is declarative it also answers "which SDK feature moved the number" (e.g. compaction algorithm A vs B as two specs).

## 6. Auditing Before Publication

```python
from vidbyte import EnvironmentAudit

report = await EnvironmentAudit(env, max_baseline_score=0.05, n_tasks=3).arun()
assert report.ok, report.notes
```

The audit fails when:

- the **do-nothing** baseline (no tools, empty reply) scores above threshold — the verifier awards free reward;
- the **echo** baseline (replies with the instructions verbatim) scores above threshold — the verifier pattern-matches text instead of checking state;
- **double verification** of identical fresh sessions returns different rewards — nondeterminism that would poison training signal.

Publication rules: a publishable environment has a passing audit, a pinned `permitted_tool_names` surface, a calibration report on current frontier models, and a version that bumps with any generator/verifier change.

## 7. Authoring Walkthrough

1. **Pick a programmatically verifiable domain.** The verifier must check final world state (files, database rows, test results), not answer text.
2. **Write the generator first.** `generate(seed, **knobs)` with difficulty knobs (`n_records`, `error_rate`, `distractor_count`). Derive all randomness from `seed`. A `StaticTaskSet` is acceptable scaffolding but is an eval, not an environment.
3. **Materialize the world in `setup`.** Write everything the agent may touch under `workspace_dir`; put ground truth in `verifier_state`.
4. **Pin the action surface** with `permitted_tool_names`, seeding `EnvSession.tools` with environment-owned tools where the environment needs custom ones.
5. **Write `verify` with partial credit.** One `CriterionResult` per planted issue or invariant; restore canonical assets from pristine sources before checking (an agent deleting a failing test must not pass).
6. **Register and audit.** `EnvironmentRegistry.register(MyEnvironment)`, then run `EnvironmentAudit` until `ok`.
7. **Calibrate.** Sweep frontier-model specs with `acalibrate`; tune knobs until pass rates land in the 10–60% band; publish the report with the environment.
