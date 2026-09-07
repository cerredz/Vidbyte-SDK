# Harness execution contract

`vidbyte.harnesses` is a small outer envelope for arbitrary harness
implementations. It standardizes the repeated work around a harness — loading its
behavior config, identifying exact variants, running one execution, and collecting
a self-contained trajectory dataset — **without** standardizing the harness
algorithm and **without** building a second capture system. Per-agent capture and
durable persistence come from `vidbyte.sessions`; this package only adds the run
envelope and the consented, redacted export.

The developer surface is a base class you subclass:

```python
from vidbyte.harnesses import Harness

class ResearchSwarm(Harness):
    type = "research-swarm"      # identity of the implementation *kind* (matches config)
    version = "2"                # code identity; NOT in the YAML

    async def run(self, request):
        planner = self.session(build_planner())   # full-trace, run-tagged session
        plan = await planner.arun(request["topic"])
        for chunk in fan_out(plan):
            worker = self.session(build_worker())
            await worker.arun(chunk)
        return {"answer": "..."}

h = ResearchSwarm(store=store, sink=sink, collect=True)
h.load("harness.yaml")
result = await h.execute({"topic": "durable agent runtimes"})
```

`type`/`version` are class attributes on the code, not YAML fields: version tracks
*implementation code*, so bumping it is a code edit, not a config edit. A foreign
object exposing `run(request)` still works via `HarnessClient.load(implementation=...)`
or `wrap_implementation(...)` — no inheritance required.

## Configuration is the single source of truth

The YAML holds **every** behavior hyperparameter: each agent, each agent's own
`params` and `tools`, and all between-agent `orchestration` knobs. A behavior
variant is a config edit, never a code edit. The strict top-level envelope is
`schema_version`, `harness`, `agents`, plus optional `metadata` and
`orchestration`; unknown/misspelled top-level keys fail early.

```yaml
schema_version: 1

harness:
  type: research-swarm          # identity of the implementation *kind*; NO version here

metadata:                       # descriptive only — excluded from spec_id
  name: Research swarm (baseline)
  description: Planner fans out to workers, reviewer gates.
  labels: [experimental]

agents:
  - name: planner
    provider: anthropic
    model: claude-sonnet
    system_prompt: { $file: prompts/planner.md }
    params:                     # per-agent hyperparameters live WITH the agent
      temperature: 0.2
      max_tokens: 4096
    tools: [web_search, read_file]
  - name: worker
    provider: anthropic
    model: claude-haiku
    params: { temperature: 0.7 }
    tools: [web_search]

orchestration:                  # harness-level knobs NOT owned by a single agent
  max_workers: 4
  review_rounds: 2
```

Agent validation is strict so an invalid hyperparameter fails at `load()`, not
three agents deep at runtime: `name` is required and unique across agents;
`provider`/`model` are optional strings; `system_prompt` is a string or a
`{$file: ...}` reference; `params` is an open object; `tools` is a list of names
or specs. `metadata` and `orchestration` are optional (absent ⇒ `{}`) so a
single-agent harness stays terse.

Credentials are not behavior hyperparameters. Credential-like config keys are
rejected before hashing or persistence; inject secrets through environments or
provider objects instead.

## Identity: `spec_id` vs `run_id`

An exact `{"$file": "..."}` object is replaced in resolved config by the UTF-8
file content and its SHA-256 digest, so editing a referenced prompt changes the
specification. `spec_id` is the SHA-256 of canonical JSON over
`{type, version, agents, orchestration}`:

- **code `version` is folded in**, so two code versions with identical config never
  collide on one id — a code change is a new variant;
- **`metadata` is excluded**, so renaming a harness never silently forks identity;
- reordering mapping keys yields the same id; changing a prompt, an agent param, a
  tool, orchestration, or the code version yields a different id.

Every execution receives a separate random `run_id`, so repeated trials never
overwrite each other.

```text
implementation code (version) + resolved config -> reusable hspec_...
reusable hspec_... + one invocation              -> unique hrun_...
unique hrun_... + tagged Sessions                -> one TrajectoryRecord
```

## Persistence and capture come from Sessions

There is no bespoke harness store, event stream, or capture enum. `self.session(agent)`
is the auto-instrument seam: it returns a durable `Session` bound to the harness's
`SessionStore`, forced to `PER_STEP` policy and `FULL` trace, and **tagged with the
`run_id`**. The developer writes no tracing code; every model call, tool call, and
reasoning trace is persisted as checkpoints automatically. The `run_id` tag is the
fan-in that later reconstructs the whole multi-agent run
(`store.list_sessions(tag=run_id)`).

`execute()` owns the lifecycle: it assigns the `run_id`, runs your `run()` (with an
optional `timeout_seconds`), and returns `HarnessExecutionResult(output, run)` where
`run` is the lightweight operational manifest (`run_id`, `spec_id`, `status`,
timestamps, `session_ids`). Failures raise `HarnessExecutionError`/`HarnessTimeoutError`
carrying the finalized run.

## Trajectory collection, consent, and redaction

The sellable unit is a self-contained `TrajectoryRecord`. Collection is automatic,
in `execute()`'s `finally`, and **fail-open — it can never fail the run**:

```python
store = sdk.harnesses.file_store(".vidbyte/sessions")   # operational source of truth
sink  = sdk.harnesses.file_sink("datasets/research.jsonl")  # LICENSED, redacted export

h = ResearchSwarm(store=store, sink=sink, collect=True)     # collect = opt-in consent
h.load("harness.yaml")
await h.execute({"topic": "..."})
```

- The operational `SessionStore` and the licensed `TrajectorySink` are **distinct
  surfaces on purpose** so the consent/redaction boundary stays sharp.
- `collect=True` is the per-run/tenant consent gate. With it off, or with no sink,
  nothing leaves the box.
- Every `task`, `output`, and `history`/`trace` value passes through one redaction
  pass (`HarnessRedactor`) before it reaches the sink — key- and free-text
  credential scrubbing, not just top-level keys. The redactor is pluggable.
- `TrajectoryRecord.spec` inlines the full resolved config (prompts, tools,
  orchestration) so a buyer consumes one JSONL line with no dependency on our store.
  Override `Harness.score(request, output)` to attach an optional eval `reward`.

## Exporting into a customer's own cloud storage

`S3TrajectorySink`, `GcsTrajectorySink`, and `AzureBlobTrajectorySink` implement the
same `TrajectorySink` protocol as `file_sink`/`memory_sink`, with zero harness
changes — swap the sink, nothing else in your code changes:

```python
from vidbyte.harnesses import S3SinkConfig, S3StorageClass

sink = sdk.harnesses.s3_sink(
    S3SinkConfig(bucket="acme-corp-vidbyte", prefix="research-runs/", storage_class=S3StorageClass.STANDARD_IA),
)  # credentials=None falls back to boto3's default credential chain — an attached IAM role, not a static key

h = ResearchSwarm(store=store, sink=sink, collect=True)
h.load("harness.yaml")
await h.execute({"topic": "..."})
```

Each finished run lands as exactly one JSONL object keyed by `run_id`
(`s3://acme-corp-vidbyte/research-runs/hrun_....jsonl`), not one growing shared
file — S3/GCS/Azure have no cheap append primitive, and `write()` is only ever
called once per finished run, so one object per run is both the simplest and the
most concurrency-safe design. A retried write for the same `run_id` overwrites
the same object rather than erroring, which is intentional: it's the same
redacted content being retried.

**Credentials never go through `harness.yaml`.** `Config` (bucket, prefix,
storage tier, encryption) and `Credentials` (secrets, wrapped in `Secret` so they
never render in a `repr()`/log line) are separate objects, passed directly into
`s3_sink()`/`gcs_sink()`/`azure_blob_sink()` at runtime — the same rule that
already rejects credential-like keys from the YAML applies here by construction,
not by convention. Every provider prefers a keyless credential path when no
static credentials are supplied: AWS's own default credential chain (or
cross-account `role_arn` assumption, for the common enterprise case where
Vidbyte's execution identity isn't the bucket owner's), GCP's Application
Default Credentials, and Azure's `DefaultAzureCredential`.

Setup and permission problems raise a specific `HarnessSinkError` subclass —
`HarnessSinkSetupError` (bucket/container doesn't exist or is misconfigured),
`HarnessSinkAuthenticationError` (no usable identity), `HarnessSinkAuthorizationError`
(a valid identity without permission — including the case where a bucket
requires server-side encryption the sink's request didn't include, which a
cloud provider reports as a plain permission denial), `HarnessSinkUnavailableError`
(network/throttling after the vendor SDK's own retries), and
`HarnessSinkPayloadError` (a record too large or too malformed to encode, caught
before any network call). Call `await sink.verify()` before a long `execute()`
run to surface a setup/auth problem immediately instead of only after the run's
own `finally` swallows it.

Because `_maybe_collect()` is fail-open by design, a sink failure — cloud or
local — never fails the harness run, and by default it also raises silently.
Pass `on_sink_error` to `Harness(...)` to observe it instead:

```python
def log_failure(event):  # SinkFailureEvent: run_id, sink_type, error_type, message, occurred_at — credential-free
    logger.warning("trajectory export failed: %s", event)

h = ResearchSwarm(store=store, sink=sink, collect=True, on_sink_error=log_failure)
```

`on_sink_error` defaults to `None`, so every existing caller's behavior is
unchanged; a raising callback is itself swallowed so a broken observer can never
turn into a broken run. Full design rationale, the error taxonomy, and the
per-provider implementation notes are in
[`docs/design/cloud-trajectory-sinks.md`](../../docs/design/cloud-trajectory-sinks.md).

### Expanded provider coverage

The S3 adapter also exposes named profiles for Cloudflare R2, Backblaze B2,
DigitalOcean Spaces, IBM Cloud Object Storage, Wasabi, and MinIO. Use the
short factories (`r2_sink`, `b2_sink`, and `spaces_sink`) or their explicit
names, and pass the matching `S3CompatibleProvider` so unsupported tiers,
checksums, tags, or encryption modes fail before network I/O.

OCI and Alibaba OSS have native adapters:

```python
from vidbyte.harnesses import OciSinkConfig, OssSinkConfig

oci_sink = sdk.harnesses.oci_sink(OciSinkConfig(namespace="acme", bucket="runs", prefix="exports"))
oss_sink = sdk.harnesses.oss_sink(OssSinkConfig(bucket="runs", region="cn-hangzhou", prefix="exports"))
```

All cloud configs support deterministic per-run keys, JSONL content type,
sorted metadata, explicit connect/read timeouts, provider-owned retries,
overwrite or create-only writes, metadata-only or write/delete preflight,
optional checksums and encryption, and safe `write_with_receipt()` results.
Native object tags are supported by S3-compatible profiles, Azure, and OSS;
GCS rejects them so callers use its custom metadata, while OCI represents tags
as reserved `tag-` metadata. OCI uses config-file/API-key/session-token/principal
signers and native `UploadManager`; OSS uses default/static/STS credentials and
its native resumable uploader with bounded parts, concurrency, optional
checkpoints, SSE-KMS, CRC64, object WORM fields, and cleanup on failure.
Install only the optional SDK for the provider you use; none is required to
import the SDK.

## Relationship to adjacent layers

- `vidbyte.sessions` is the operational persistence layer this envelope binds; a
  harness run is a fan-in over N tagged session checkpoint DAGs.
- `vidbyte.trace` is optional observability and may be sampled or provider-hosted.
- `vidbyte.evals` grades behavior; a `reward` label can be attached to a record.
- `vidbyte.paradigms` contains concrete algorithms; a paradigm can be adapted behind
  this envelope while the envelope itself stays algorithm-free.

## Key modules

- `client.py`: store/sink constructors, foreign-implementation load, Sessions namespace.
- `config.py`: strict config-as-source-of-truth envelope, `$file` resolution, spec ids.
- `contracts.py`: public specification, run manifest, and trajectory-record records.
- `registry.py`: structural `run(request)` implementation protocol and exact registry.
- `execution.py`: the `Harness` base class — load/execute/session lifecycle.
- `dataset.py`: `TrajectoryCollector` — joins tagged Sessions into one redacted record.
- `stores/`: `TrajectorySink` port (`base.py`) plus in-memory and atomic-JSONL file
  sinks (`memory.py`, `file.py`), mirroring the `vidbyte/sessions/stores/` layout,
  plus S3-compatible profiles, native OCI/OSS adapters, and the shared cloud
  lifecycle/receipt helper (`_cloud_common.py`).
- `serialization.py`: the single redaction pass and shared secret-key policy.

Cloud sink `Config`/`Credentials`/enum construction types live in
`vidbyte/lib/dataclasses/cloud_sinks.py` (Stage 1, local/syntactic validation),
one layer beneath this package; the numeric bounds they validate against live in
`vidbyte/lib/constants/cloud_sinks.py`.

The full architecture and rejected alternatives are recorded in
[`docs/design/harness-execution-contract.md`](../../docs/design/harness-execution-contract.md).
