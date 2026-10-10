<!--
Context Protocol Header

Description:
    Why and how vidbyte/harnesses gained S3/GCS/Azure Blob TrajectorySink backends.
Purpose:
    Explains the design decisions behind the cloud-trajectory-sinks feature so a
    future reader — human or agent — can extend, review, or reason about it
    without re-deriving why it looks the way it does.
Architecture:
    - Documents the SessionStore-vs-TrajectorySink insertion-point decision, the
      two-stage validation split, the credential model, the one-object-per-run
      design, and the on_sink_error observability hook.
Relations:
    Complements skills/harnesses/SKILL.md; full detail in
    docs/design/cloud-trajectory-sinks.md.
-->

# Cloud Trajectory Sinks Skill

Use this skill when touching `vidbyte/harnesses/stores/{s3,gcs,azure_blob}.py`,
`vidbyte/lib/dataclasses/cloud_sinks.py`, `vidbyte/lib/constants/cloud_sinks.py`,
or the `on_sink_error` hook on `Harness`. It explains *why* this feature looks
the way it does, not just what it does — read
[`docs/design/cloud-trajectory-sinks.md`](../../docs/design/cloud-trajectory-sinks.md)
for full per-provider detail.

## Why this exists

Enterprise buyers — AWS-run ones especially — want a harness's output delivered
into storage *they* own, not left sitting only on Vidbyte's servers. Before this
feature, nothing in this SDK talked to any cloud storage vendor at all.

## The insertion-point decision: TrajectorySink, not SessionStore

This repo has two "store" concepts that are easy to conflate:

- `vidbyte/sessions/store.py`'s `SessionStore` is the **operational** backend
  behind a live run — unredacted, read-write, typed to the internal
  `Checkpoint`/`RunState` domain.
- `vidbyte/harnesses/stores/base.py`'s `TrajectorySink` is the **licensed
  export** backend — write-only, one method, and only ever handed a record
  after `HarnessRedactor` has scrubbed it.

Cloud storage export belongs on `TrajectorySink`. Shipping raw `SessionStore`
checkpoints into a customer's bucket would leak unredacted internal state and
defeat the consent/redaction boundary the architecture exists to protect. If
asked to add a fourth cloud provider, extend `TrajectorySink`'s family under
`vidbyte/harnesses/stores/`, never `SessionStore`.

## The two-stage validation split

- **Stage 1 — local, syntactic, at `Config`/`Credentials` construction:**
  `vidbyte/lib/dataclasses/cloud_sinks.py`'s `__post_init__` methods raise
  `vidbyte.lib.errors.ConfigurationError` for things checkable without a
  network call (empty bucket name, a `storage_class` that isn't an enum
  member, `max_retries < 0`). This file sits in `vidbyte/lib` — a layer
  beneath `vidbyte/harnesses` — so it must never import from `vidbyte.harnesses`.
- **Stage 2 — remote, semantic, at `verify()`/first `write()`:** each sink's
  `_translate_error()` maps a vendor exception to one of five
  `HarnessSinkError` subclasses in `vidbyte/harnesses/errors.py`:
  `HarnessSinkSetupError` (bucket doesn't exist / wrong region / bad
  endpoint), `HarnessSinkAuthenticationError` (no usable identity),
  `HarnessSinkAuthorizationError` (a valid identity without permission —
  including the case where a bucket requires server-side encryption the
  request didn't include, which surfaces as a plain permission denial),
  `HarnessSinkUnavailableError` (network/throttling after the vendor SDK's
  own retries), `HarnessSinkPayloadError` (shared with `FileTrajectorySink`:
  a record too large or malformed to encode).

Adding a new failure category means adding a new subclass here, per
`harnesses/errors.py`'s own documented rule: one subclass per distinct
failure mode, each carrying full `description`/`expected_vs_actual`/
`blast_radius`/`possible_causes`/`fix_approaches` diagnostic fields.

## The credential model

`Config` (bucket, prefix, storage tier, encryption) and `Credentials` (secrets)
are **separate types, never merged** — a sink's non-secret settings stay
freely loggable while its secret half is structurally distinguishable in every
constructor signature. Secret string fields are wrapped in `Secret`
(`vidbyte/lib/dataclasses/cloud_sinks.py`), whose `__repr__`/`__str__` always
return `"Secret(<redacted>)"`; `.reveal()` is the one named escape hatch, called
only at the point a vendor client is actually constructed.

Every provider prefers a keyless credential path when no static credentials
are supplied: AWS's own default credential chain (or cross-account `role_arn`
assumption via STS, for the common case where Vidbyte's execution identity
isn't the bucket owner), GCP's Application Default Credentials, and Azure's
`DefaultAzureCredential`.

Sink credentials are **runtime constructor arguments only** — never written
into `harness.yaml`. This isn't a new rule invented for this feature; it's the
same one `HarnessCredentialConfigError` already enforces for the harness
config envelope, applied consistently to the export path too.

## Why one JSONL object per run, not one growing file

`FileTrajectorySink` opens a file in append mode and adds a line per run. S3,
GCS, and Azure Blob have no cheap append primitive — appending to an existing
object means downloading and re-uploading the whole thing. Since `write()` is
only ever called once per finished run (never mid-run), each cloud sink
instead uploads exactly one object per run, keyed by `run_id`
(`{prefix}/{run_id}.jsonl`). This is a single atomic `PutObject`/upload with no
read-modify-write, makes a retried `write()` for the same `run_id` safely
idempotent (it overwrites, not errors), and sidesteps the multi-process-append
limitation `FileTrajectorySink`'s own docstring already admits to.

Preflight verification (does the bucket/container exist and accept writes) is
memoized once per sink instance as a single shared `asyncio.Task`, not an
`asyncio.Lock` — this repo's banned-api-policy (lint rule S039) bans
`asyncio.Lock` with no built SDK-owned replacement existing yet, and a
synchronous check-then-create between `await` points needs no lock in the
first place, since asyncio only yields control at an `await`.

## The `on_sink_error` hook

`Harness._maybe_collect()` has always swallowed every sink failure completely
silently — true for the pre-existing file/memory sinks too, not just the new
cloud ones. That's correct (a sink failure must never fail the harness run),
but it also means a cloud export could fail on every single run forever and
nobody would notice. `on_sink_error: Callable[[SinkFailureEvent], None] | None`
on `Harness`/`wrap_implementation` closes that gap: `None` by default (every
existing caller's behavior is byte-identical), and when set, a swallowed
failure is reported as a credential-free `SinkFailureEvent`
(`run_id`/`sink_type`/`error_type`/`message`/`occurred_at` — class names only,
`message` passed through `HarnessRedactor.safe_error_message()`). The callback
itself is wrapped so a broken observer can never turn into a broken run.

If adding a new run-lifecycle observer, follow this exact shape — a
`None`-default constructor parameter invoked from inside an existing fail-open
`except` clause, itself swallowed. Don't add a second bespoke callback shape.

## Verification

The expansion adds named S3-compatible profiles for R2, B2, Spaces, IBM COS,
Wasabi, and MinIO plus native OCI and Alibaba OSS sinks. Every provider keeps
the PR #393 contract while adding metadata/tags, content type, timeouts,
provider-owned retries, checksums/encryption, conditional creation,
metadata-only or explicit write/delete preflight, safe receipts, and native
multipart/resumable transfer settings. OCI adds API-key, config-file,
session-token, instance-principal, resource-principal, and OKE workload
identity modes. OSS adds default/static/STS modes, SSE-KMS, CRC64, object WORM
fields, and optional checkpointed uploads. Control-plane lifecycle,
versioning, replication, and bucket policy remain deployment responsibilities.

```bash
python -c "from vidbyte.harnesses import OciTrajectorySink, OssTrajectorySink, S3CompatibleProvider, SinkWriteReceipt; print('ok')"
PYTHONPATH=$(pwd) python scripts/test-cloud-trajectory-provider-expansion.py
```
