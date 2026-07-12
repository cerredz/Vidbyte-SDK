# Harness execution contract

`vidbyte.harnesses` is a small outer envelope for arbitrary harness
implementations. It standardizes the repeated work around a harness—loading its
behavior config, identifying exact variants, recording executions, and exporting
raw datasets—without standardizing the harness algorithm itself.

The implementation contract is intentionally one method:

```python
class MyHarness:
    async def execute(self, request, context):
        await context.emit("research.started", {"query": request})
        output = await run_any_algorithm_you_want(request)
        context.link_session("se_existing_session")
        context.add_artifact("s3://my-bucket/report.json", media_type="application/json")
        return output
```

No base class, graph shape, agent loop, provider, prompt format, tool system,
retry strategy, or model API is required.

## Configuration and identity

`HarnessClient.load()` accepts a mapping or a `.json`, `.yaml`, or `.yml` path.
The common top-level envelope is strict so typos fail early; fields within
`harness`, each `agents` entry, and `params` remain open for implementations.

```yaml
schema_version: 1
harness:
  type: research-swarm
  version: "1"
agents:
  - name: planner
    provider: anthropic
    model: claude-sonnet
    system_prompt:
      $file: prompts/planner.md
params:
  max_workers: 4
  review_rounds: 2
```

An exact `{"$file": "..."}` object is replaced in resolved config by the UTF-8
file content and its SHA-256 digest. `spec_id` is the SHA-256 hash of canonical
resolved JSON. Reordering mapping keys produces the same ID; changing a prompt,
agent option, model name, or any other behavior value produces a different ID.
Every execution receives a separate random `run_id`, so repeated trials never
overwrite each other.

Credentials are not behavior hyperparameters. Credential-like config keys are
rejected before hashing or persistence; inject secrets through environments or
provider objects instead.

The SDK does not hash Python source or inspect hidden implementation state. Put
every behavior-affecting runtime tweak in `agents`/`params`, and bump
`harness.version` whenever implementation code changes. Run request and metadata
are intentionally per-invocation data and do not change `spec_id`.

```text
implementation code + resolved config -> reusable hspec_...
reusable hspec_... + one invocation   -> unique hrun_...
unique hrun_...                        -> ordered events + terminal record
```

## Direct loading and execution

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
store = sdk.harnesses.file_store(".vidbyte/harness-runs")

loaded = sdk.harnesses.load(
    "harness.yaml",
    implementation=MyHarness(),
    store=store,
    capture="full",
    persistence="required",
)

result = await loaded.execute(
    {"topic": "durable agent runtimes"},
    metadata={"experiment": "baseline"},
    timeout_seconds=300,
)

print(loaded.spec.spec_id, result.run.run_id, result.run.status)
```

`load()` reads and validates config but does not create a run or write to a
store. Persistence begins only when `execute()` is entered. The raw implementation
output is returned in `HarnessExecutionResult.output`; the paired `run` is the
safe canonical record.

Synchronous and asynchronous `execute` methods are accepted. Async implementations
are recommended when they emit context events or need cancellable work.

## Exact factory registration

Registration is optional and client-local. It is useful when config alone should
select an implementation:

```python
class ResearchSwarmFactory:
    harness_type = "research-swarm"
    harness_version = "1"

    def create(self, spec):
        return MyHarness(spec.resolved_config)

sdk.harnesses.register(ResearchSwarmFactory())
loaded = sdk.harnesses.load("harness.yaml", store=store)
```

Resolution uses the exact `(type, version)` pair. Duplicate registrations and
implicit “latest version” fallback are rejected.

## Persistence policy and stores

Every `HarnessClient` owns one shared `InMemoryHarnessStore` by default. Use
`memory_store()` for another ephemeral store or `file_store(path)` for local,
inspectable JSON snapshots plus append-only JSONL events. `FileHarnessStore` is
single-process storage; future database adapters can implement the asynchronous
`HarnessStore` protocol without changing harness implementations.

- `best_effort` keeps implementation results usable when storage fails and adds
  safe operation diagnostics to `run.persistence_errors`. Partial records may
  remain in the backend.
- `required` refuses to run when spec/start persistence fails and raises a typed
  store error if a successful implementation cannot be finalized.

Implementation exceptions remain primary even if failure finalization also has a
storage problem. Successful, failed, timed-out, and cancelled paths all attempt a
terminal record.

## Capture and evidence

`capture="full"` stores secret-scrubbed JSON-safe request, response, metadata,
event payload, and artifact metadata projections. `capture="minimal"` stores the
lifecycle and typed references but omits those payloads. Unsupported objects are
marked as dropped rather than stringified with an unsafe `repr`.

`HarnessContext` provides explicit `emit`, `add_artifact`, and `link_session`
seams. By default a run declares `capture_scope="boundary"`. An implementation
may declare `capture_scope = "instrumented"` only if it actually routes relevant
internal work through captured seams.

Full capture is not magical interception. Direct model calls, tool calls,
filesystem writes, subprocesses, network activity, and external side effects are
invisible unless the implementation emits evidence or uses another instrumented
SDK component. Timeouts cannot forcibly terminate synchronous Python code or
undo side effects already started. Retention, deletion, licensing, and sensitive
data policy remain the caller's responsibility.

The context closes when terminalization starts. Implementations should await
their own child tasks before returning; a retained background task cannot append
late evidence after the canonical run has ended. Separate `execute()` calls may
run concurrently, so a stateful implementation owns its own concurrency policy.

## Raw dataset export

Export joins each selected run to its exact spec and ordered events. It writes
one self-contained JSON object per line through a sibling temporary file and
atomically replaces the destination:

```python
count = await sdk.harnesses.export_jsonl(
    store,
    "datasets/research-runs.jsonl",
    spec_id=loaded.spec.spec_id,
    statuses=["succeeded", "failed"],
)
```

The output is deliberately raw. Build chat, SFT, preference, RL, eval, or custom
training schemas downstream so canonical evidence does not acquire one task's
assumptions.

## Relationship to adjacent layers

- `vidbyte.sessions` stores resumable agent checkpoint DAGs. A harness run may
  link session IDs, but its trajectory ledger does not replace Session state.
- `vidbyte.trace` is optional observability and may be sampled, truncated, or
  provider-hosted. It is not the canonical run dataset.
- `vidbyte.evals` grades behavior. Harness storage records what happened without
  assigning scores or labels.
- `vidbyte.paradigms` contains concrete, opinionated algorithms. A paradigm can
  be adapted behind this envelope, while the envelope itself stays algorithm-free.

## Key modules

- `client.py`: load/register/store/export facade and durable Sessions namespace.
- `config.py`: strict common envelope, safe references, deterministic spec IDs.
- `contracts.py`: public specification, run, event, artifact, and policy records.
- `registry.py`: structural implementation protocol and exact local registry.
- `execution.py`: run lifecycle and implementation-facing context.
- `store.py`: asynchronous persistence port and shared state invariants.
- `stores/`: zero-config memory and inspectable local-file adapters.
- `serialization.py`: versioned JSON shapes and capture scrubbing.
- `dataset.py`: atomic one-run-per-line raw export.

The full architecture and rejected alternatives are recorded in
[`docs/design/harness-execution-contract.md`](../../docs/design/harness-execution-contract.md).
