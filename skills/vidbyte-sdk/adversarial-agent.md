# Adversarial Agent

Use `AdversarialAgent` when one configured worker should produce the implementation or answer and one configured adversary role should challenge that work before the worker revises it.

## Ownership Boundary

`AdversarialAgent` is a runnerless `BaseAgent`-compatible facade. Its constructor intentionally has no `runner`, provider, model, API key, temperature, tools, middleware, output schema, or catch-all `**kwargs` parameter.

Configure execution on the child prototypes:

- `worker` owns implementation models, tools, permissions, middleware, context-window behavior, structured output, and MCP servers.
- `adversary` owns review models and explicitly read-only inspection tools when review must not mutate artifacts.
- The facade owns workflow instructions, exact stage ordering, public history, tracing, summary metadata, and `last_result`.

Passing `runner=` or another undeclared execution argument to the facade raises Python's normal unexpected-keyword `TypeError`.

## Basic Usage

```python
from vidbyte import AdversarialAgent, AdversarialSettings, BaseAgent

worker = BaseAgent(
    name="implementation-worker",
    system_prompt="Implement the task, inspect the repository, and verify your result.",
    provider="openai",
    model_name="gpt-5",
    tools=worker_tools,
)

adversary = BaseAgent(
    name="implementation-challenger",
    system_prompt="Find concrete correctness and completeness defects. Never mutate artifacts.",
    provider="openai",
    model_name="gpt-5-mini",
    tools=read_only_tools,
)

reviewed_worker = AdversarialAgent(
    name="reviewed-implementation",
    system_prompt="Deliver a correct implementation that satisfies the request and repository constraints.",
    worker=worker,
    adversary=adversary,
    settings=AdversarialSettings(
        num_adversaries=2,
        adversarial_rounds=2,
        min_successful_adversaries=1,
    ),
)

reply = await reviewed_worker.arun("Implement the requested SDK feature.")
print(reply.content)
print(reviewed_worker.last_result.rounds)
```

The facade's `system_prompt` is workflow-level guidance included in every deterministic child envelope. The child system prompts still define how the worker implements and how adversaries review.

## Exact Execution Model

One successful run performs:

1. Fork one run-local worker and `num_adversaries` run-local adversaries.
2. Ask the worker for an initial result.
3. For each exact adversarial round:
   1. Give every adversary the same immutable worker snapshot, sequentially.
   2. Capture blank, timed-out, or erroring adversaries as failed review records.
   3. Enforce `min_successful_adversaries` after every configured adversary has been attempted.
   4. Give the successful challenges to the same run-local worker for one full revision.
4. Return only the final worker revision as the facade reply.

The child-call formula is:

```text
1 + adversarial_rounds * (num_adversaries + 1)
```

For two adversaries and two rounds, the run makes seven child calls. `adversarial_rounds` is an exact count; v1 has no early stopping.

Reviewers run sequentially. Forked agents may share custom runner or tool objects, and the SDK does not assume those objects are concurrency-safe.

## Settings

| Setting | Default | Meaning |
|---|---:|---|
| `num_adversaries` | `1` | Number of isolated adversary forks created per run |
| `adversarial_rounds` | `1` | Exact number of review + worker-revision rounds |
| `min_successful_adversaries` | `1` | Required non-blank successful reviews in every round |
| `per_adversary_timeout` | `None` | Optional timeout in seconds for each reviewer call |
| `max_review_chars` | `4000` | Per-review forwarding limit in the next worker prompt |
| `max_worker_output_chars` | `12000` | Worker-output forwarding limit in review/revision prompts |

Counts and character limits must be positive integers. The success floor cannot exceed the adversary count, and a configured timeout must be positive.

Forwarding limits bound only later child prompts. Full successful worker and reviewer outputs remain available in the typed `last_result` records.

## Result And Public Agent State

`await facade.arun(...)` returns an ordinary `AgentMessage`. Its content and existing metadata come from the final worker reply. `metadata["adversarial"]` adds only a bounded summary: configured/completed rounds, child-call count, successful/failed review counts, and child prototype names.

After success:

- `last_result` is an `AdversarialResult` with the full initial output, ordered `AdversarialRoundResult` records, full review records, and final output.
- `history` receives exactly one facade reply for the invocation.
- `last_prompt` is the caller's original task, not an internal review envelope.
- `last_reply` is the final facade message.
- Worker tool-call contexts are copied to the facade for behavior inspection and handoff rendering.

`last_result` resets to `None` at the start of every run and is set only when all exact stages succeed.

## Input Forwarding

Every worker pass preserves the caller's:

- `AgentInput.metadata`
- context items and context manager
- explicit `BaseContext`
- external history and facade history
- call-level modality
- safe worker call options

Worker options are not forwarded to adversaries. Reviewers run from their own configuration plus safe workflow trace metadata.

## Failure Policy

Reviewer failures are partial until the per-round threshold is evaluated. A blank response, timeout, or ordinary reviewer exception creates an `AdversarialReview` with `error` and safe error-type metadata.

The run raises `AdversarialExecutionError` when:

- the worker raises during its initial pass or a revision;
- the worker returns blank content; or
- a round finishes below `min_successful_adversaries`.

The error details include safe phase, round, counts, child names, and remediation context. They do not embed prompts, review bodies, credentials, or raw exception text. Cancellation propagates after child spans and run-local MCP resources are closed.

Specialized worker/adversary subclasses must preserve their behavioral subtype from `fork()`. If a fork silently returns `BaseAgent`, the facade raises `ConfigurationError` before the first model call. Use an exact `BaseAgent` or add a subtype-preserving fork override.

## Tools, MCP, And Side Effects

Facade-level `add_tool()`, MCP attach methods, and MCP builder methods raise `ConfigurationError` before side effects. Configure the child that should own the capability:

```python
worker.add_tool(write_file_tool)
await adversary.attach_mcp_server(read_only_server_command)
```

An adversary is not automatically read-only. Give it only read-safe tools and permissions when mutation is undesirable.

The worker runs once initially and once after every round. Write-side tools can therefore repeat side effects. Make worker tools idempotent where possible, or make the worker inspect existing state before applying a revision.

## BaseAgent Compatibility

The facade supports normal `run`, `arun`, sequential-run helpers, `receive`, `history`, `behavior`, registries, fixed pipelines, `as_tool`, cards, explicit handoff, and subtype-preserving `fork()`.

Safe facade fork overrides are limited to `name`, `system_prompt`, `metadata`, and `include_history`:

```python
isolated = reviewed_worker.fork(name="reviewed-implementation-branch", include_history=True)
```

Default `await facade.handoff()` derives a `HandoffAgent` from the worker's provider/model configuration and renders the facade's final transcript and worker tool calls. A caller-supplied handoff generator passed with `by=` is honored.

## Tracing

The facade emits an `agent.run` root trace with `strategy="adversarial"`, plus `adversarial.worker` and `adversarial.review` spans carrying role, phase, round, index, child name, and bounded counts. Raw reviewer bodies are not trace attributes. Child agents still emit their own configured traces.

## Choosing The Right Primitive

- Use `BaseAgent` for one model/tool loop without adversarial revision.
- Use `AdversarialAgent` for one worker that must remain final authority while configured reviewers challenge every exact round.
- Use `AggregateAgent` for independent proposer answers followed by one synthesis.
- Use pipelines for predetermined string-in/string-out stage topology.
- Use workflows when Python code owns legal state transitions and validation gates.
- Use `MultiAgent` when a manager owns a shared task ledger, adaptive delegation, evidence, blockers, and replanning.

Review envelopes use explicit tags and JSON string encoding to preserve deterministic boundaries. This reduces ambiguity but does not neutralize prompt injection; treat worker output and reviewer text as untrusted model content.
