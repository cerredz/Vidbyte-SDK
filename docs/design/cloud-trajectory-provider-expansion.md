# Cloud Trajectory Provider Expansion

## 1. Overview

The cloud trajectory sink feature introduced in PR #393 gives the SDK one
redacted, one-JSONL-object-per-run export contract for AWS S3, Google Cloud
Storage, and Azure Blob Storage. This design expands that contract to the
customer-owned object stores that were identified as the next useful coverage:
Cloudflare R2, Backblaze B2, DigitalOcean Spaces, Oracle Cloud Infrastructure
Object Storage, and Alibaba Cloud OSS. The S3-compatible implementation also
gets named profiles for IBM Cloud Object Storage, Wasabi, and MinIO so callers
do not need to hand-build endpoints for those compatible targets.

Implementation status: complete on branch `feat/cloud-trajectory-provider-expansion`.
The focused feature pack passes 33 cases, and the package gate passes. The
repository-wide source gate remains blocked by unrelated lint debt already
present in this SDK baseline; provider-file focused lint checks are clean.

The expansion is intentionally additive. Existing `TrajectorySink` callers
continue to receive a redacted `TrajectoryRecord`, and `Harness.execute()`
continues to fail open when export fails. The new provider code stays behind
lazy optional SDK imports, keeps credentials separate from behavior
configuration, and adds production features at the adapter boundary: explicit
timeouts, provider-owned retry configuration, metadata and tags, checksums,
encryption settings, conditional creation, multipart thresholds, bounded
concurrency, client lifecycle cleanup, write receipts, and diagnostic
capability validation.

## 2. Goals and Non-Goals

### Goals

1. Add first-class factories and typed configuration for R2, B2, Spaces, OCI,
   and Alibaba OSS.
2. Make S3-compatible endpoint profiles explicit for R2, B2, Spaces, IBM COS,
   Wasabi, and MinIO, including provider-specific storage and encryption
   capability validation.
3. Add native OCI and Alibaba adapters without importing their SDKs at module
   import time or adding large cloud SDKs to the base package dependencies.
4. Preserve the redaction boundary: adapters receive only the finished
   `TrajectoryRecord` and never a `SessionStore`.
5. Encode and size-check before any network call, so invalid records cannot
   trigger preflight traffic or partial uploads.
6. Support safe repeated writes for the same `run_id`, with an explicit
   create-only mode for buckets where overwrites are forbidden.
7. Surface provider failures as typed, safe, agent-readable harness errors and
   expose a structured write receipt for operators that need object identity.
8. Provide a feature-owned test pack and an executable test runner covering
   contract, provider mapping, security, retry, failure, idempotency, and
   package-import behavior.

### Non-Goals

1. Do not change the `TrajectorySink` protocol's required `write()` method or
   make a cloud SDK a base installation dependency.
2. Do not manage customer bucket/container lifecycle, versioning, retention,
   legal holds, replication, or event subscriptions from a run-time sink.
   Those are provider control-plane responsibilities and must be configured
   outside the harness process; the sink may validate or attach object-level
   settings where the provider supports them.
3. Do not claim universal semantics for storage tiers, encryption, object lock,
   or versioning. Capability profiles reject combinations that a provider does
   not support rather than silently translating them.
4. Do not implement a durable local export queue. Fail-open delivery remains
   the PR #393 contract; durable retry belongs in a separate delivery service.
5. Do not expose raw credentials, signed URLs, request bodies, or provider
   exception strings that contain secrets through diagnostics or receipts.

## 3. Background and Current Constraints

PR #393 deliberately separates operational persistence from licensed export:
`SessionStore` owns unredacted checkpoints and run state, while
`TrajectorySink` receives a post-redaction `TrajectoryRecord`. Cloud sinks use
one object per run because object stores do not provide a cheap append
primitive. The current implementation already has typed configuration,
credential wrappers, lazy imports, provider-specific errors, and a fail-open
`on_sink_error` hook.

The audit found five correctness gaps that this expansion closes:

- Existing cloud `write()` methods preflight before encoding, so an oversized
  record can cause a network call before `HarnessSinkPayloadError` is raised.
- `GcsSinkConfig.max_retries` is validated but is not passed into the GCS
  client's retry or timeout policy.
- S3 uploads omit the JSONL content type even though GCS and Azure set it.
- A failed memoized preflight task remains failed forever, so a transient
  outage poisons a sink instance until it is rebuilt.
- The existing adapters have no common lifecycle, receipt, object metadata,
  checksum, conditional-create, or multipart extension point.

## 4. Requirements

### Functional requirements

1. `s3_sink()` must accept a named S3-compatible provider profile and provide
   convenience factories for R2, B2, Spaces, IBM COS, Wasabi, and MinIO.
2. `oci_sink()` must support OCI API-key, session-token, instance-principal,
   resource-principal, and config-file credential paths where the optional OCI
   SDK supports them.
3. `oss_sink()` must support Alibaba default/environment credentials, explicit
   access-key credentials, and STS security tokens.
4. All providers must support prefix-safe deterministic keys and one JSONL
   record per run.
5. All providers must support content type, user metadata, native tags where
   the provider SDK supports tags, storage tier, encryption settings, bounded
   retries, connect/read timeouts, and optional create-only semantics. GCS
   callers use custom metadata because its object API has no S3-style tags;
   OCI maps tags to reserved user metadata.
6. Providers with a native multipart/resumable API must expose a threshold and
   part/concurrency settings; below the threshold they should use the simplest
   atomic single-object operation.
7. Every provider must implement `verify()`, `write()`, and `aclose()` and
   expose a safe write receipt after a successful write.
8. `verify()` must memoize concurrent checks, reset its task after failure, and
   report whether the check is metadata-only or a destructive-free
   write-probe. The default must remain metadata-only.
9. Configuration validation must reject unsupported provider/feature
   combinations locally, before optional SDK import or network traffic.
10. `write()` must perform encoding and size validation before preflight or
    upload, and retries must preserve the same deterministic object key.

### Safety and compatibility requirements

1. No new base dependency is added to `pyproject.toml`.
2. Optional SDK imports remain inside `_import_driver()` helpers.
3. `Secret.__repr__`, `Secret.__str__`, error details, receipts, and callback
   events must not contain secret values.
4. Existing PR #393 constructors and default behavior remain valid.
5. Existing S3/GCS/Azure tests continue to pass unchanged, with regression
   tests added for the five audited gaps.

## 5. High-Level Design

The implementation has four layers:

```text
Harness._maybe_collect()
        |
        v
TrajectorySink.write(TrajectoryRecord)
        |
        +-- shared encoding / size / key / receipt helpers
        |
        +-- S3TrajectorySink + named S3CompatibleProfile
        |       +-- AWS, R2, B2, Spaces, IBM COS, Wasabi, MinIO
        |
        +-- OciTrajectorySink
        |
        +-- AlibabaOssTrajectorySink
        |
        v
customer-owned object store
```

The shared layer owns behavior that must be consistent across providers:
payload encoding, size enforcement, key construction, common metadata,
preflight task lifecycle, receipt normalization, and safe error details. Each
adapter owns SDK object construction, provider-specific request fields,
credential resolution, retry/timeout wiring, multipart mechanics, and error
translation.

The control-plane boundary is explicit. The sink never creates a bucket,
changes lifecycle rules, turns on versioning, grants permissions, or mutates a
retention policy. It can attach object-level metadata, tags, storage class,
encryption, checksum, and conditional-write fields; it can optionally perform
a reserved-object write/delete probe only when the caller explicitly enables
it and has both permissions.

## 6. Detailed Design

### 6.1 Shared sink options

Extend the cloud sink dataclasses with immutable, validated values:

- `content_type`, default `application/x-ndjson`.
- `metadata` and `tags` as sorted tuples of string pairs, never mutable dicts.
- `checksum_algorithm` using a provider-neutral request intent that each
  adapter maps only when supported.
- `overwrite_mode`: `OVERWRITE` (default, retry-safe) or `CREATE_ONLY`.
- `preflight_mode`: `METADATA` (default) or `WRITE_PROBE`.
- `connect_timeout_seconds` and `read_timeout_seconds`.
- `multipart_threshold_bytes`, `multipart_part_size_bytes`, and
  `multipart_max_concurrency`, with conservative shared bounds.

The dataclass validation is deliberately local. It checks pair shapes, safe
prefixes, positive timeouts, part-size ordering, and provider capability
compatibility. It does not check whether a bucket exists or whether an
identity has permission.

### 6.2 S3-compatible profiles

`S3CompatibleProvider` is an enum whose profile table carries stable endpoint
and capability facts:

| Profile | Endpoint/region behavior | Supported object features |
|---|---|---|
| AWS | caller supplies region; AWS endpoint resolution remains available | S3 tiers, SSE-S3/SSE-KMS/SSE-C, checksums, tags, object lock fields |
| Cloudflare R2 | account endpoint; region is `auto` | Standard/Infrequent Access, SSE-C, checksums, multipart; S3-style tags and object lock remain unsupported/control-plane concerns |
| Backblaze B2 | regional `s3.<region>.backblazeb2.com` endpoint | Standard storage, supported S3 encryption request fields, multipart; object lock remains a provider policy prerequisite |
| DigitalOcean Spaces | regional Spaces endpoint | Standard storage, multipart, limited S3 metadata; unsupported lifecycle/tag/version management is rejected as sink behavior |
| IBM COS | caller supplies endpoint/region | S3-compatible standard storage and provider-specific endpoint behavior |
| Wasabi | caller supplies region endpoint | S3-compatible standard storage, versioning/object lock controlled outside sink |
| MinIO | caller supplies endpoint and region | S3-compatible local/private deployment behavior; no cloud-only capability is assumed |

The profile resolver fills defaults only when the caller omitted them. An
explicit endpoint or region always wins, but the resolver validates known
incompatibilities such as R2 with an AWS region or a non-supported storage
class. The profile is included in diagnostics and receipts.

The existing `S3TrajectorySink` remains the implementation. New convenience
factory methods construct `S3SinkConfig(provider=...)`; there is no duplicate
S3 client implementation per vendor.

### 6.3 S3 request features

The S3 adapter will:

1. Encode and guard the record before `_ensure_ready()`.
2. Construct `botocore.config.Config` with adaptive retries and explicit
   connect/read timeouts.
3. Preserve STS AssumeRole and session-token behavior.
4. Set `ContentType`, `Metadata`, `Tagging`, checksum, storage class, SSE-S3,
   SSE-KMS, SSE-C, object-lock fields, and `IfNoneMatch="*"` where supported.
5. Use multipart upload for payloads at or above the configured threshold,
   with abort-on-failure and bounded concurrency. The default threshold stays
   above normal trajectory sizes, so normal writes retain one simple atomic
   request.
6. Normalize ETag/version/checksum/bytes into `SinkWriteReceipt`.
7. Close the boto3 client when `aclose()` is called if the SDK exposes a close
   method.

S3-compatible vendors do not all implement the full AWS API. The profile
capability check rejects unsupported encryption, checksum, tag, or object-lock
fields rather than sending a request that fails ambiguously at runtime.

### 6.4 OCI Object Storage adapter

Add `OciSinkConfig`, `OciCredentials`, and `OciStorageTier` types. The adapter
uses the OCI Object Storage client lazily and runs its synchronous SDK calls in
`asyncio.to_thread`.

Credential modes:

- `CONFIG_FILE`: path and profile passed to `oci.config.from_file`.
- `API_KEY`: tenancy, user, fingerprint, private key, and optional passphrase.
- `SESSION_TOKEN`: config plus security token signer.
- `INSTANCE_PRINCIPAL`, `RESOURCE_PRINCIPAL`, and `OKE_WORKLOAD_IDENTITY`:
  signer factories from `oci.auth.signers`/`oci.auth` when available.

Object requests attach `content_type`, user metadata, storage tier, optional
Vault KMS key id, checksum, and `if_none_match` for create-only mode. Payloads
above the threshold use OCI `UploadManager` with an in-memory stream, bounded
parallelism, and abort/cleanup on failure. Bucket preflight reads bucket
properties and never changes bucket configuration. Error mapping uses OCI
status codes and service codes to distinguish setup, auth, authorization,
availability, payload, and generic sink failures.

OCI-specific control-plane features such as versioning, retention rules,
auto-tiering, replication, events, and object lifecycle are represented in the
design documentation and checked as deployment prerequisites, but are not
mutated by a run-time sink.

### 6.5 Alibaba OSS adapter

Add `OssSinkConfig`, `OssCredentials`, and `OssStorageClass` types. The adapter
uses the Alibaba Cloud OSS Python v2 SDK lazily and performs synchronous calls
through `asyncio.to_thread`.

Credential modes:

- environment/default provider chain;
- explicit AccessKey ID + secret;
- STS access key + security token;
- optional STS session-token settings; `role_arn` and `role_session_name` are
  retained for callers that obtain the token through an external RAM/STS
  broker, because the OSS v2 SDK does not ship an STS role-assumption client.

Object requests attach `Content-Type`, user metadata, tags, storage class,
SSE-OSS/SSE-KMS settings, CRC/checksum settings, and overwrite prevention when
create-only mode is selected. Large payloads use the SDK's multipart/resumable
uploader with configurable part size, concurrency, checkpoint directory, and
abort-on-failure cleanup. Checkpoint files are opt-in, local to the caller,
and never contain credentials or record contents.

OSS-specific BucketWorm/ObjectWorm, versioning, lifecycle filters, cross-region
replication, and restore behavior remain bucket/control-plane configuration.
The adapter reports unsupported per-object combinations early and includes the
provider's object key and request id in safe receipts/diagnostics.

### 6.6 Preflight and lifecycle

Every adapter shares these lifecycle semantics:

- constructor: validate config, import optional driver, build a client, do no
  network I/O;
- `verify()`: one shared task per sink instance; if it fails, clear the task so
  a later call can retry after a transient outage;
- `write()`: encode, guard, preflight, upload, return `None` for protocol
  compatibility, and retain a safe `last_receipt`;
- `write_with_receipt()`: same operation but returns the normalized receipt;
- `aclose()`: close the driver/client and any async credential resources;
- context manager helpers: `async with sink` calls `aclose()` on exit.

The optional write probe uses a random reserved key under the configured
prefix, writes a tiny marker with the configured content type, then deletes it
in a `finally` block. It is opt-in because it requires delete permission and
can conflict with retention/object-lock policy. Metadata-only preflight is the
safe default.

### 6.7 Error and diagnostic behavior

Provider mappings retain the PR #393 subclasses and add no new public failure
category unless a distinct behavior cannot be represented honestly. Error
details include provider, operation, bucket/container, object key when known,
HTTP/status code, retryability, and request id when safe. They exclude access
keys, secrets, SAS strings, private key paths, signed URLs, and raw bodies.

The error class descriptions and fix approaches will be updated to name native
OCI and OSS files and the new feature-test pack. Every adapter's raw exception
is chained as `__cause__` but never rendered directly into a public receipt or
event.

### 6.8 API surface

`HarnessClient` gains:

- `r2_sink(config, credentials)`
- `b2_sink(config, credentials)`
- `spaces_sink(config, credentials)`
- `ibm_cos_sink(config, credentials)`
- `wasabi_sink(config, credentials)`
- `minio_sink(config, credentials)`
- `oci_sink(config, credentials)`
- `oss_sink(config, credentials)`

Existing `s3_sink`, `gcs_sink`, and `azure_blob_sink` signatures remain
compatible. All new factories are thin pass-throughs and do not duplicate
validation.

## 7. Data Model

New public types:

- `S3CompatibleProvider` and `S3ChecksumAlgorithm` enums;
- `S3CompatibleCapabilities` immutable capability description;
- `OciStorageTier`, `OciAuthMode`, `OciSinkConfig`, `OciCredentials`;
- `OssStorageClass`, `OssAuthMode`, `OssSinkConfig`, `OssCredentials`;
- `SinkWriteReceipt` with provider, object key, byte count, checksum/etag,
  version id, request id, and UTC completion time.

Secret fields remain wrapped in `Secret`. Metadata/tag tuples are normalized
and sorted on construction so request ordering and receipt diagnostics are
deterministic.

## 8. API Changes

The public behavior is additive. `TrajectorySink` remains a runtime-checkable
protocol with `write(record) -> None`; `write_with_receipt`, `verify`, and
`aclose` are optional capabilities exposed by concrete cloud sinks. No
existing harness config file gains credential fields. No cloud SDK is imported
when callers only import `vidbyte` or `vidbyte.harnesses`.

## 9. File Manifest

### New files

- `vidbyte/harnesses/stores/oci.py` - OCI native adapter.
- `vidbyte/harnesses/stores/oss.py` - Alibaba OSS native adapter.
- `vidbyte/harnesses/stores/_cloud_common.py` - shared options, receipts,
  preflight lifecycle, and request normalization helpers.
- `tests/features/cloud_trajectory_provider_expansion/FEATURE.md` - executable
  feature contract and failure inventory.
- `tests/features/cloud_trajectory_provider_expansion/test_contract.py` - public
  API, capability, and optional-import contract tests.
- `tests/features/cloud_trajectory_provider_expansion/test_adapters.py` - fake
  OCI/OSS/provider adapter behavior tests.
- `tests/features/cloud_trajectory_provider_expansion/test_security.py` - secret
  redaction and policy-boundary tests.
- `tests/features/cloud_trajectory_provider_expansion/test_resilience.py` -
  retry, preflight reset, idempotency, and failure-injection tests.
- `scripts/test-cloud-trajectory-provider-expansion.py` - complete feature-pack
  runner that reports every test case.

### Modified files

- `vidbyte/lib/dataclasses/cloud_sinks.py` - new configs, credentials, enums,
  shared option validation, and S3 profile capabilities.
- `vidbyte/lib/constants/cloud_sinks.py` - shared multipart/time bounds.
- `vidbyte/harnesses/stores/s3.py` - named profiles and advanced request paths.
- `vidbyte/harnesses/stores/gcs.py` - retry/timeout, receipts, and lifecycle
  fixes.
- `vidbyte/harnesses/stores/azure_blob.py` - receipts, lifecycle fixes, and
  common request options.
- `vidbyte/harnesses/stores/__init__.py` - public exports.
- `vidbyte/harnesses/__init__.py` - public exports.
- `vidbyte/harnesses/client.py` - new provider factories.
- `vidbyte/harnesses/errors.py` - expanded safe blast radius and diagnostics.
- `skills/harnesses/cloud-trajectory-sinks.md` - provider matrix and feature
  checklist.

## 10. Testing Plan

The feature test pack will be created before implementation. Its failure
inventory includes malformed configuration, unsupported capability combinations,
missing optional SDKs, wrong endpoints, credential absence, policy denials,
throttling/timeouts, oversized payloads, metadata/tag loss, secret leakage,
duplicate writes, failed preflight caching, multipart cleanup, and accidental
bucket control-plane mutation.

Cases include:

- contract tests for every public export, named factory, profile default, and
  backward-compatible constructor;
- unit/property tests for tuple normalization, deterministic keys, capability
  validation, size-before-network ordering, and safe receipt serialization;
- adapter tests with fake vendor modules for R2/B2/Spaces profile mapping,
  OCI auth/tier/KMS/multipart behavior, and OSS auth/class/checksum/multipart;
- negative/error tests for each typed harness sink error with safe context
  packets and chained causes;
- security tests proving secrets do not appear in `repr`, errors, receipts,
  callback events, tags, or checkpoint paths;
- resilience tests proving provider retry settings are wired, preflight
  failures can recover, create-only mode is sent, multipart failures abort, and
  repeated run IDs are safe;
- integration tests using the real `Harness.execute()` boundary to verify
  redaction, fail-open behavior, and one object per run;
- package/import smoke tests with optional SDK modules absent.

Manual QA remains required for one real bucket per provider: verify identity,
prefix-scoped write, storage class/tier, encryption, tags/metadata, a large
multipart record, create-only behavior, and explicit `aclose()` cleanup. No
manual credential is committed or used by automated CI.

## 11. Dependencies and External Services

Optional, lazily imported dependencies:

- `boto3`/`botocore` for AWS and S3-compatible profiles;
- `oci` for OCI Object Storage;
- `alibabacloud-oss-v2` for Alibaba OSS.

The base package's dependency graph is unchanged. Tests inject fake driver
namespaces and do not require cloud accounts or optional SDKs.

## 12. Rollout and Deployment

The change is additive and can ship in one SDK release after PR #393. Existing
S3/GCS/Azure users see only bug fixes: payload validation happens earlier,
content type is standardized, failed preflight can recover, and GCS retries are
honored. New providers are opt-in through new factories and optional SDK
installation instructions.

Rollback is a code revert. No bucket policy, lifecycle rule, versioning
setting, retention rule, or durable local checkpoint is created by the sink.

## 13. Open Questions

1. Which optional SDK minor versions should be pinned in provider-specific
   extras? This implementation leaves them unpinned in the base package and
   records installation guidance; a future release can add tested extras once
   support policy is chosen.
2. Should a future delivery service persist receipts for redelivery? This
   change exposes receipts to the caller but does not create a queue.
3. Should control-plane policy verification become a separate admin CLI? It is
   intentionally outside the run-time sink and should not be added here.

## 14. Alternatives Considered

### One native implementation per compatible provider

Rejected because R2, B2, Spaces, IBM COS, Wasabi, and MinIO expose an S3
surface. Duplicated adapters would drift on redaction, retries, keying, and
error safety. Named capability profiles retain provider differences without
duplicating the transport.

### A generic HTTP PUT adapter for OCI and OSS

Rejected because each provider has important auth, multipart, checksum, and
error semantics that their SDKs already encode. A generic HTTP layer would
reimplement signing and weaken diagnostics.

### Bucket policy/versioning/lifecycle management inside the sink

Rejected because a run-time process should not mutate customer control-plane
policy as a side effect of exporting a trajectory. It also requires broader
permissions than a prefix-scoped writer and would make `verify()` destructive.

### Always using multipart

Rejected because ordinary trajectory records are small. A configurable
threshold gives large records a resumable path without making every small write
pay multipart setup and cleanup costs.

## Summary

The expansion adds five first-class providers and three named compatible
profiles while preserving the PR #393 contract. The highest-value reliability
changes are encode-before-network, capability-aware configuration, resettable
preflight, explicit provider retry/timeout wiring, safe receipts, and cleanup
for multipart and client lifecycles. The implementation remains dependency
light at install time and leaves bucket-level retention, lifecycle, versioning,
replication, and policy management in the customer's existing cloud
control-plane tooling.
