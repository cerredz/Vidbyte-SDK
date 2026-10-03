# Feature: Cloud trajectory provider expansion

## High-Level Feature Description

Cloud trajectory provider expansion lets a harness export its consented,
redacted `TrajectoryRecord` into customer-owned Cloudflare R2, Backblaze B2,
DigitalOcean Spaces, OCI Object Storage, or Alibaba OSS, while retaining named
S3-compatible profiles for IBM COS, Wasabi, and MinIO. The feature matters to
enterprise SDK users who need their run data to land in a storage account they
control, with the provider's actual tier, encryption, retention posture, and
operational controls preserved rather than hidden behind a lossy universal
abstraction.

The behavior crosses configuration, optional dependency loading, the Harness
redaction boundary, provider SDK request construction, retry/lifecycle
management, and failure reporting. A regression can silently leak credentials,
write to the wrong bucket or storage class, duplicate an export, poison a sink
after one transient failure, or make a successful harness appear failed. This
pack therefore treats provider adapters as a security- and reliability-critical
feature, not as thin happy-path wrappers.

## Contract

The SDK exposes typed, dependency-light factories for each supported provider.
Each constructed sink accepts only a redacted `TrajectoryRecord`, writes one
deterministic JSONL object per run, applies the configured provider capabilities
without silent translation, and reports typed safe failures. The sink validates
payloads before any network call, uses provider-owned retry settings plus
explicit timeouts, supports safe repeated writes or explicit create-only mode,
and can be closed without leaking client or credential resources. Harness
execution remains fail-open when export fails, with the existing optional
`on_sink_error` hook receiving no secrets.

## Actors / Callers

- SDK users construct sinks through `HarnessClient` or direct concrete classes.
- `Harness._maybe_collect()` calls `TrajectorySink.write()` after a successful,
  consented, redacted run.
- Operators call `verify()` before long runs, inspect `last_receipt`, and call
  `aclose()` during application shutdown.
- CI and future agents use this pack to verify public exports, optional import
  behavior, provider mapping, and failure safety.
- Customer cloud control-plane tooling configures bucket policies, versioning,
  retention, lifecycle, replication, events, and restore behavior outside the
  run-time sink.

## Inputs and Preconditions

- A valid provider-specific immutable Config and Credentials pair.
- A bucket/container and prefix that are syntactically valid; remote existence
  and permissions are checked only at `verify()`/first write.
- Optional provider SDK installed only for the selected concrete sink.
- A finished `TrajectoryRecord` already scrubbed by `HarnessRedactor`.
- Provider capability choices must be supported by the selected profile.
- Timeouts, retry counts, multipart thresholds, metadata, tags, and conditional
  write options pass local validation.
- Credentials are runtime constructor values; they are never stored in harness
  YAML or included in error/receipt payloads.

## Observable Outcomes

- The provider receives exactly one JSONL object per `run_id` for normal-sized
  records, with deterministic key, content type, metadata/tags, storage class,
  encryption, checksum, and conditional-write settings where supported.
- Large records use the configured provider multipart/resumable path, bounded
  by part size and concurrency, and failed multipart sessions are aborted.
- `write_with_receipt()` returns provider name, object key, byte count, safe
  object identity/checksum fields, request id when available, and UTC time.
- `write()` remains protocol-compatible and returns `None`; the same receipt is
  available as `last_receipt`.
- `verify()` performs one concurrent-safe metadata check by default and can
  perform an explicit write/delete probe only when requested.
- Typed `HarnessSinkSetupError`, `HarnessSinkAuthenticationError`,
  `HarnessSinkAuthorizationError`, `HarnessSinkUnavailableError`,
  `HarnessSinkPayloadError`, or `HarnessSinkError` includes safe remediation
  context and the original exception as a cause.
- Failed export does not change a successful Harness run into a failed run.
- No optional cloud module is imported by base package imports.

## State Transitions

1. Sink is constructed with validated config and a lazily selected driver; no
   network call occurs.
2. Sink is unverified; concurrent `verify()`/first writes share one preflight
   task.
3. Successful preflight marks the sink ready until a close or explicit reset.
4. Failed preflight clears the cached task, allowing a later call to recover.
5. A write encodes and guards first, then preflights, then performs one atomic
   or multipart upload.
6. Repeating the same `run_id` overwrites by default or is rejected by
   create-only mode; it must never create a second logical trajectory object.
7. `aclose()` closes provider clients and async credential resources; repeated
   close is harmless.

## Invariants

- Redaction occurs before the sink boundary; cloud adapters never receive a
  `SessionStore` or unredacted checkpoint.
- Encoding and size rejection happen before preflight or upload I/O.
- Object keys are prefix-safe and deterministic from the run id.
- `application/x-ndjson` is the default content type for every provider.
- Secrets never appear in `repr`, `str`, receipts, errors, callback events,
  request metadata, tags, or multipart checkpoint paths.
- Named S3-compatible profiles reject unsupported capabilities instead of
  silently sending a misleading request.
- Provider retry policy is configured once at the SDK boundary; no second
  generic retry loop can duplicate a non-idempotent operation.
- Multipart failures abort/clean up the in-progress upload when the provider
  supports cleanup.
- Bucket-level lifecycle/versioning/retention/replication/policy features are
  never mutated by a run-time export sink.
- `Harness.execute()` remains fail-open for all sink failures, including
  optional driver errors and callback errors.

## External Dependencies

- `boto3` and `botocore` for AWS and named S3-compatible profiles.
- `oci` for OCI Object Storage, auth signers, and `UploadManager`.
- `alibabacloud-oss-v2` for Alibaba OSS auth, object, and multipart APIs.
- `asyncio.to_thread` for synchronous provider SDKs.
- Harness redaction, trajectory contracts, and existing typed sink errors.
- Customer cloud endpoints, credentials, bucket policies, and control-plane
  settings during manual verification only.

## Known Failure Modes

Failure inventory before test generation:

```text
Feature: redacted one-object-per-run export across five first-class providers
Core contract: deterministic JSONL object with provider-specific safe features
Actors / callers: SDK users, Harness._maybe_collect, operators, CI agents
Valid inputs: validated config/credentials and finished redacted records
Invalid inputs: bad names, unsupported tiers/encryption/checksum, empty secrets,
  invalid metadata/tag pairs, bad thresholds, oversized records
Preconditions: optional SDK available; remote bucket reachable and authorized
Observable outcomes: object request, receipt, typed error, fail-open Harness run
State transitions: unverified -> ready -> uploaded; failed preflight is retryable
Invariants: no secret leak, no network before payload guard, no raw exception leak
External boundaries: boto3, OCI SDK, Alibaba OSS SDK, redaction, Harness runtime
Security and policy risks: wrong tenant, path/prefix escape, secret exposure,
  over-broad role, unsupported capability silently ignored, control-plane mutation
Concurrency and idempotency risks: shared first preflight, duplicate run_id,
  retry after timeout, simultaneous multipart uploads, close during write
Historical bugs: PR #393 encoded after preflight; GCS max_retries was unused;
  S3 content type was omitted; failed preflight tasks were permanently cached
Resource limits: record size, multipart part size/count, concurrency, timeout,
  retry budget, provider single-upload limits
Observability promises: safe provider/key/error/request-id receipt and callback
What an easy generated test would miss: real Harness fail-open boundary, secret
  redaction in diagnostics, capability rejection, cleanup after multipart failure,
  recovery after failed preflight, and the difference between metadata and write
  probe permissions
```

Specific failure cases include absent optional SDKs, wrong auth mode, expired or
missing credentials, endpoint/region mismatch, bucket-not-found ambiguity,
403/429/5xx/timeouts, unsupported profile options, metadata/tag loss, checksum
mismatch, create-only conflicts, duplicate overwrite behavior, preflight task
poisoning, close races, multipart abort failures, and callback exceptions.

## Historical Regressions

- PR #393 oversized-record regression: `write()` preflighted before encoding;
  regression test must prove zero provider calls on payload rejection.
- PR #393 GCS retry regression: `max_retries` was validated but not wired into
  the client; regression test inspects the configured retry policy.
- PR #393 content-type regression: S3 omitted `application/x-ndjson`;
  regression test covers cross-provider content-type parity.
- PR #393 preflight-cache regression: one transient preflight failure poisoned
  the sink forever; regression test verifies a second call can recover.

## Test Suite Map

- `test_contract.py` protects public exports, factory signatures, profile
  defaults, backward compatibility, capability matrices, and lazy imports.
- `test_adapters.py` protects fake-driver request mapping for S3 profiles, OCI,
  and Alibaba OSS, including tiers, auth, encryption, metadata, checksums,
  multipart thresholds, receipts, and close behavior.
- `test_security.py` protects secret redaction, prefix/tenant boundaries,
  unsupported feature rejection, and the no-control-plane-mutation policy.
- `test_resilience.py` protects encode-before-network, typed errors, retry and
  timeout wiring, failed-preflight recovery, idempotent/create-only writes,
  multipart cleanup, concurrency, and Harness fail-open execution.
- `scripts/test-cloud-trajectory-provider-expansion.py` runs every test in this
  folder and reports a per-case result; run it from the repository root.
- Existing `tests/test_cloud_trajectory_sinks.py` remains the compatibility suite
  for the PR #393 S3/GCS/Azure behavior and must run alongside this pack.

## Omitted Testing Strategies

- Real cloud end-to-end tests are omitted from automated CI because they require
  customer credentials, incur storage/network cost, and would make failures
  dependent on external control-plane state. Manual QA cases are documented in
  the design doc and must cover one real bucket per provider before release.
- Browser and accessibility tests are omitted because this is a Python SDK and
  has no UI.
- Mutation testing is documented as a review target but not automated in the
  feature runner because the repository has no mutation framework baseline; the
  resilience and security tests name the mutations they must catch.
- Long-duration load testing is omitted from the default runner; bounded stress
  tests cover many records and concurrent writes without requiring a cloud
  account. A future delivery-service feature should own sustained throughput.
- Provider control-plane migration tests are omitted because the sink never
  mutates lifecycle, retention, versioning, replication, or event configuration.
