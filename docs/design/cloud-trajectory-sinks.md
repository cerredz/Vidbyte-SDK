# Design Doc: Cloud Trajectory Sinks (S3 / GCS / Azure Blob)

**Status:** Implemented
**Author:** Claude
**Created:** 2026-08-31
**Last Updated:** 2026-09-02

---

## 1. Overview

Enterprise buyers — AWS-run ones especially — want a harness's output to land inside storage they own (their own S3 bucket, GCS bucket, or Azure container), not to sit only on Vidbyte's servers. This design adds three new `TrajectorySink` backends — `S3TrajectorySink`, `GcsTrajectorySink`, `AzureBlobTrajectorySink` — that plug into the harness envelope's existing, deliberately narrow export seam (`vidbyte/harnesses/stores/base.py`'s `TrajectorySink` protocol) with zero changes to `Harness.execute()`'s control flow. Each sink writes one redacted, self-contained `TrajectoryRecord` per finished run as a single JSONL object keyed by `run_id`, using the storage tier and encryption settings the customer chooses, authenticating through each cloud's own keyless-preferred credential model. A small, backward-compatible hook is added to `execute()` so a swallowed sink failure — which today vanishes with zero trace, even for the existing file/memory sinks — becomes observable without breaking the documented fail-open guarantee.

---

## 2. Goals & Non-Goals

### Goals
- Ship `S3TrajectorySink`, `GcsTrajectorySink`, and `AzureBlobTrajectorySink`, each implementing the existing `TrajectorySink` protocol (`async def write(self, record: TrajectoryRecord) -> None`) with no change to that protocol's shape.
- Let a customer choose their storage tier natively per provider (S3 storage class, GCS storage class, Azure Blob access tier) and encryption settings, without inventing one fake cross-vendor abstraction.
- Support keyless/short-lived credentials as the preferred path for every provider (AWS cross-account role assumption, GCP Application Default Credentials / Workload Identity, Azure Managed Identity / SAS token), with static keys as an explicit fallback.
- Guarantee credentials never cross into a `HarnessSpec`, a `TrajectoryRecord`, or any hashed/persisted structure — only ever passed as runtime Python objects.
- Handle every failure category in the checklist below (Section 4) with a specific, typed, richly-diagnosed error owned by the dependency-light `vidbyte/lib/errors` layer and re-exported by `harnesses/errors.py`.
- Preserve the documented fail-open guarantee: a cloud sink failure must never fail a harness run, exactly like the existing file/memory sinks today.
- Close the silent-failure gap that fail-open currently creates, via an opt-in, backward-compatible observability hook — without changing default behavior for any existing caller.
- Cover every new class with unit tests using mocked vendor clients (this repo's `harnesses/` package currently ships with zero dedicated test files under an "approved no-tests workflow" — Section 14 explains why this PR deviates from that for cloud-credential code specifically).

### Non-Goals
- Not building multipart/chunked upload. A size guard rejects a record before the network call instead; see Section 6.3 and Section 14.
- Not exposing the full API surface of any vendor SDK. Destination-wide versioning, soft delete, lifecycle, and retention policies remain management-plane concerns; the sink exposes the per-object controls that belong on a single write, plus conditional writes so callers can safely use those destination policies.
- Not building a universal cross-vendor "storage tier" enum. Each sink exposes that provider's real tier vocabulary.
- Not adding retry-loop code of our own. Each vendor SDK's native retry/backoff configuration is used instead (see Section 6, "Network & availability").
- Not adding cloud storage as an MCP-attachable tool — that already exists (`AwsS3MCP`, `GcpStorageMCP`, `AzureBlobMCP` in `vidbyte/lib/config/mcp_presets.py`) and serves a different purpose (an agent calling storage as a tool mid-run, not the harness envelope auto-exporting its own output).
- Not adding new `pyproject.toml` dependencies, hard or optional-extra. `boto3`, `google-cloud-storage`, and `azure-storage-blob` stay lazily imported, exactly like `supabase` in `vidbyte/lib/providers/supabase.py`.

---

## 3. Background & Context

This follows directly from a prior investigation (recorded in this session's memory as `vidbyte-sdk-cloud-export-trajectorysink`) that established two things about the existing codebase:

1. **The insertion point is `TrajectorySink`, not `SessionStore`.** `vidbyte/sessions/store.py`'s `SessionStore` is the *operational* backend behind a live run — unredacted, read-write, typed to a 15-field `RunState`. `vidbyte/harnesses/stores/base.py`'s `TrajectorySink` is the *licensed export* backend — write-only, one method, and only ever handed a record after `HarnessRedactor` has scrubbed it (`vidbyte/harnesses/serialization.py`). The harness README and `harnesses/client.py`'s own docstring already name the gap: *"A future WarehouseTrajectorySink implements the same TrajectorySink protocol with zero harness changes."* Nobody has built it yet.
2. **No cloud storage code exists anywhere in this SDK today.** A repo-wide search for `S3`, `boto3`, `google-cloud-storage`, `azure-storage`, and `blob` turns up only that one doc-comment mention, plus the unrelated MCP presets noted above.

`FileTrajectorySink` (`vidbyte/harnesses/stores/file.py`) already writes the exact format AWS's own docs point at — one compact JSON object per line (JSONL) — so the wire format isn't new; only the destination is.

**Constraint this design must respect, verified in `vidbyte/harnesses/execution.py`:** `Harness._maybe_collect()` wraps the entire collect-and-write path in `except Exception: return` with **no logging of any kind today** — this is true right now for the existing file and memory sinks, not just a risk for the new cloud ones. `execution.py`'s own file header states: *"Do not let a collection or sink error propagate out of execute()."* Any change here must keep that guarantee exactly, while making the swallowed failure observable to a caller who opts in.

---

## 4. Requirements

### Functional Requirements

1. `S3TrajectorySink`, `GcsTrajectorySink`, `AzureBlobTrajectorySink` each implement `TrajectorySink.write(record) -> None`, writing one object per call at key `{prefix}/{run_id}.jsonl` (or `{run_id}.jsonl` when `prefix` is empty), containing exactly one JSON line — the same encoding `FileTrajectorySink` already uses (compact, sorted keys, `ensure_ascii=False`, `allow_nan=False`).
2. Each sink's `Config` dataclass exposes that provider's native storage tier as a required-or-defaulted enum field (`S3StorageClass`, `GcsStorageClass`, `AzureBlobTier`), plus server-side encryption settings where the provider supports customer-managed keys.
3. Each sink accepts credentials as a separate, distinct object from its `Config` — never merged — and falls back to that provider's default/keyless credential resolution when no explicit credentials object is supplied.
4. `S3SinkConfig` supports cross-account role assumption (`role_arn`, `external_id`) as a first-class option, not a workaround.
5. A retried `write()` call for the same `run_id` overwrites the same object idempotently by default; provider-native conditional fields are available when callers need no-clobber or compare-and-swap semantics.
6. A record whose encoded size exceeds `MAX_TRAJECTORY_RECORD_BYTES` (Section 6.1) raises before any network call is attempted.
7. `HarnessClient` (`vidbyte/harnesses/client.py`) gains `s3_sink()`, `gcs_sink()`, and `azure_blob_sink()` factory methods, matching the shape of the existing `file_sink()`/`memory_sink()`.
8. `Harness.__init__` gains an optional `on_sink_error: Callable[[SinkFailureEvent], None] | None = None` parameter. When set, a swallowed collection/sink failure invokes it with a credential-free, structured event before `_maybe_collect()` returns. When unset (the default), behavior is byte-for-byte identical to today.
9. Every failure category in the checklist (Setup & configuration, Authentication & authorization, Network & availability, Data & encoding, Concurrency & idempotency) raises one of five new `HarnessSinkError` subclasses (Section 6.7), each carrying a complete safe diagnostic packet. The hierarchy lives in `vidbyte/lib/errors`; `harnesses/errors.py` re-exports it for compatibility.
10. A missing vendor SDK (`boto3` / `google-cloud-storage` / `azure-storage-blob`) raises `vidbyte.lib.errors.ConfigurationError` naming the exact `pip install` command — matching `SupabaseSessionStore._import_driver()` exactly, not a new error type.

### Non-Functional Requirements
- **Security:** credentials are structurally distinct from config (separate dataclasses), secret fields are wrapped in a masked `Secret` value type so an accidental `print()`/log statement cannot leak them, and no credential object is ever passed through `HarnessConfigLoader`/`harness.yaml` (which gets hashed into `spec_id` and persisted — `HarnessCredentialConfigError` already exists to police the YAML path; this design keeps sink credentials entirely outside that path).
- **Reliability:** a cloud sink failure never fails a harness run (existing invariant, preserved exactly).
- **Observability:** a cloud sink failure is no longer silent by default *when the caller opts in* via `on_sink_error`; silent-by-default behavior is preserved for callers who don't opt in, so this is additive, not a behavior change.
- **Concurrency:** two concurrent `write()` calls on one sink instance (e.g. two harness runs sharing one long-lived sink) must not run preflight verification twice or interleave badly; two different processes writing the same `run_id` must not corrupt either object (guaranteed by construction — every write is a single, whole-object `PutObject`/`upload_blob` call, never a partial append). Provider-native conditional fields opt into no-clobber or compare-and-swap behavior when overwrite-by-default is unsafe.
- **Performance:** no additional latency for existing sinks (file/memory) — the shared encoding helper introduced in Section 6.2 is a pure refactor of logic `FileTrajectorySink` already runs.

---

## 5. High-Level Design

```
Harness.execute()
   -> _finalize() -> _maybe_collect()  [existing, MODIFIED: adds failure hook]
        -> TrajectoryCollector.collect()        [UNCHANGED — redaction already happens here]
        -> sink.write(record)                    [existing protocol, UNCHANGED shape]
              |
              +-- FileTrajectorySink        [existing, MODIFIED: shares SinkEncoding]
              +-- InMemoryTrajectorySink    [existing, UNCHANGED]
              +-- S3TrajectorySink          [NEW]
              +-- GcsTrajectorySink         [NEW]
              +-- AzureBlobTrajectorySink   [NEW]
```

Each new sink follows the same three-stage shape:

1. **Construction (sync, no network):** build a `Config` dataclass (validates syntactically in `__post_init__`, raising `vidbyte.lib.errors.ConfigurationError` — same layer, same error type the dataclass's own guide prescribes) and an optional `Credentials` object; lazily import the vendor SDK (raising `ConfigurationError` with a `pip install` message if missing, exactly like `SupabaseSessionStore`); construct the vendor client.
2. **Verification (async, first-write-or-explicit, cached):** an internal `_ensure_ready()` — or an explicit `verify()` a caller can invoke eagerly — confirms the bucket/container exists and is writable, translating any remote failure into one of the five new `HarnessSinkError` subclasses. A shared `asyncio.Task` memoizes the in-flight preflight without introducing a banned lock primitive.
3. **Write (async, one object per call):** encode the record via the shared `SinkEncoding` helper (also used by the refactored `FileTrajectorySink`), guard its size, and issue exactly one `PutObject`/`upload_blob`/`upload_from_string` call keyed by `run_id`. Encoding and the 100 MiB guard happen before preflight, so an oversized record causes zero provider activity. Any vendor exception is translated into the matching typed error before propagating — `_maybe_collect()` still swallows it, but now it's a specific, diagnosable type instead of an opaque one, and (if the caller opted in) `on_sink_error` sees it.

This keeps the change entirely additive at the harness layer: `Harness.execute()`, `TrajectoryCollector`, and the `TrajectorySink` protocol itself are untouched. The only modification to `execution.py` is the observability hook, which is `None`-by-default and therefore invisible to every existing caller.

Key design decisions:
- **Config vs. Credentials as separate types**, not one merged object, so the non-secret half stays freely loggable/inspectable and the secret half is structurally distinguishable at a glance in every constructor signature.
- **One JSONL object per run, not one growing object per bucket.** S3/GCS/Azure have no cheap append primitive; since `write()` is already called exactly once per finished run (never mid-run), one object per `run_id` maps perfectly onto a single atomic PUT, sidesteps the multi-process-append limitation `FileTrajectorySink`'s own docstring already admits to, and matches the many-small-JSONL-files-under-a-prefix shape data lake tooling (Athena, Redshift COPY, Snowflake external stages) already expects.
- **Five new error subclasses under the existing `HarnessSinkError`, not a `details["category"]` field on the existing one.** `vidbyte/lib/errors` owns the hierarchy so dataclasses and stores can share it without an upward import; `harnesses/errors.py` re-exports the types for compatibility. The classes follow the existing rule: one subclass per distinct failure mode, each carrying a complete safe context packet.
- **A two-stage validation split**, driven by the "Strict Config Dataclasses" field-guide rule that a dataclass's `__post_init__` must raise the same error type its old call site raised, combined with `AGENTS.md`'s one-directional layering rule (`vidbyte/lib/dataclasses` may not import from the `vidbyte/harnesses` domain layer above it):
  - **Stage 1 — local, syntactic, at config construction:** `vidbyte.lib.errors.ConfigurationError` (empty bucket name, invalid character, `storage_class` not a member of its enum, negative `max_retries`).
  - **Stage 2 — remote, semantic, at verify()/first-write:** the five new `vidbyte.lib.errors` subclasses (bucket doesn't exist, wrong region, access denied, credentials expired, throttled after retries), re-exported from `harnesses.errors`.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/constants/cloud_sinks.py`

**File(s):** `vidbyte/lib/constants/cloud_sinks.py`
**Type:** New file

#### What it does
Centralizes the numeric bounds every cloud sink's `__post_init__` and encoding guard reference, following the "Keep reusable validation bounds in the shared constants package" field-guide rule — matching the existing `vidbyte/lib/constants/cot_events.py` / `runners.py` one-file-per-feature-area pattern.

#### Interface / API
```python
MAX_TRAJECTORY_RECORD_BYTES: int = 100 * 1024 * 1024   # 100 MiB single-PUT guard (S3's hard ceiling is 5 GiB; this stays conservative since a JSONL trajectory record is normally KB-to-low-MB)
MIN_BUCKET_NAME_LENGTH: int = 3
MAX_BUCKET_NAME_LENGTH: int = 63
DEFAULT_SINK_MAX_RETRIES: int = 3
```

#### Logic / Algorithm
Plain module-level constants; no logic.

#### Edge Cases & Error Handling
N/A — pure constants module.

---

### 6.2 `vidbyte/lib/dataclasses/cloud_sinks.py`

**File(s):** `vidbyte/lib/dataclasses/cloud_sinks.py`
**Type:** New file

#### What it does
Houses every strictly-validated `Config`/`Credentials` shape and storage-tier enum for the three new sinks, following the exact pattern `vidbyte/lib/dataclasses/agents.py` already uses for `AgentFallbackConfig`/`PauseDuration` — one frozen, slotted dataclass per shape, all validation in `__post_init__`, raising `vidbyte.lib.errors.ConfigurationError`.

#### Interface / API
```python
class S3StorageClass(str, Enum):
    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"
    GLACIER_IR = "GLACIER_IR"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    ONEZONE_IA = "ONEZONE_IA"
    OUTPOSTS = "OUTPOSTS"
    EXPRESS_ONEZONE = "EXPRESS_ONEZONE"

class GcsStorageClass(str, Enum):
    STANDARD = "STANDARD"
    NEARLINE = "NEARLINE"
    COLDLINE = "COLDLINE"
    ARCHIVE = "ARCHIVE"

class AzureBlobTier(str, Enum):
    HOT = "Hot"
    COOL = "Cool"
    COLD = "Cold"
    ARCHIVE = "Archive"

@dataclass(frozen=True, slots=True)
class Secret:
    """Wraps one credential value so repr()/str() never renders it."""
    value: str | bytes
    def __post_init__(self) -> None: ...        # rejects empty string
    def __repr__(self) -> str: ...               # always returns "Secret(<redacted>)"
    def reveal(self) -> str: ...                 # the only way to read the real value

@dataclass(frozen=True, slots=True)
class S3SinkConfig:
    bucket: str
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None              # S3-compatible vendors: R2, MinIO, B2, Spaces
    storage_class: S3StorageClass = S3StorageClass.STANDARD
    sse: Literal["AES256", "aws:kms", "aws:kms:dsse"] | None = None
    kms_key_id: str | None = None
    role_arn: str | None = None                  # cross-account AssumeRole target
    external_id: str | None = None                # confused-deputy protection for AssumeRole
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    def __post_init__(self) -> None: ...

@dataclass(frozen=True, slots=True)
class S3Credentials:
    access_key_id: str | None = None
    secret_access_key: Secret | None = None
    session_token: Secret | None = None
    def __post_init__(self) -> None: ...          # access_key_id and secret_access_key must both be set, or both None

@dataclass(frozen=True, slots=True)
class GcsSinkConfig:
    bucket: str
    prefix: str = ""
    storage_class: GcsStorageClass = GcsStorageClass.STANDARD
    kms_key_name: str | None = None                # customer-managed encryption key (CMEK)
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    def __post_init__(self) -> None: ...

@dataclass(frozen=True, slots=True)
class GcsCredentials:
    service_account_json_path: str | None = None   # None => Application Default Credentials
    def __post_init__(self) -> None: ...

@dataclass(frozen=True, slots=True)
class AzureBlobSinkConfig:
    container: str
    prefix: str = ""
    tier: AzureBlobTier = AzureBlobTier.HOT
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    def __post_init__(self) -> None: ...

@dataclass(frozen=True, slots=True)
class AzureBlobCredentials:
    account_url: str
    connection_string: Secret | None = None         # least-preferred: embeds the account key
    sas_token: Secret | None = None                  # scoped, time-limited — preferred over connection_string
    def __post_init__(self) -> None: ...             # both None => DefaultAzureCredential (managed identity / AAD)
```

The implemented configs extend these shapes with provider-native object
controls. `S3SinkConfig` adds `metadata`, `tags`, content headers, SSE-C
algorithm, `aws:kms:dsse`, KMS encryption context, bucket-key selection,
Object Lock, `IfMatch`/`IfNoneMatch`, ACL/grants, checksums, requester-pays,
accelerate/dual-stack endpoints, `Expires`, and
`WebsiteRedirectLocation`; `S3Credentials` carries the raw 32-byte SSE-C key
and optional MD5. `GcsSinkConfig` adds metadata/content properties,
generation/metageneration conditions, checksum, holds, object retention,
`bucket_retention_period`, and `user_project`; `GcsCredentials` carries the
optional raw customer-supplied key. `AzureBlobSinkConfig` adds metadata/tags,
content settings, MD5 validation, ETag/tag conditions, immutability/legal
hold, and encryption scope; `AzureBlobCredentials` carries an optional
base64-encoded 32-byte customer-provided key. These fields stay out of
`HarnessSpec` and are never serialized into the run manifest.

#### Logic / Algorithm
1. Each `*SinkConfig.__post_init__` strips and validates its bucket/container name: non-empty, within `MIN_BUCKET_NAME_LENGTH`–`MAX_BUCKET_NAME_LENGTH`, matches a conservative `^[a-z0-9.-]+$`-style pattern. This is deliberately *not* the full AWS/GCS/Azure naming spec (consecutive dots, IP-address-shaped names, per-region reserved prefixes) — the real source of truth for "does this bucket actually exist and work" is the Stage 2 preflight check against the live API, not a hand-rolled regex trying to replicate vendor documentation.
2. Each `__post_init__` asserts `isinstance(self.storage_class, <Enum>)` (or `self.tier`) explicitly — a dataclass field type hint does not enforce the type at runtime, so this is required to catch a bad value before it ever reaches the API, matching `PauseDuration`'s own explicit-isinstance style.
3. Each `__post_init__` asserts `max_retries` is a non-negative `int` (not `bool`).
4. `S3SinkConfig.__post_init__` asserts `sse == "aws:kms"` implies `kms_key_id is not None`, and that `external_id` is only meaningful alongside `role_arn` (warns/ignored, not rejected, if given without one — a customer might reasonably set both defensively).
5. `Secret.__post_init__` rejects an empty string; `Secret.__repr__`/`__str__` always return the literal string `"Secret(<redacted>)"` regardless of the wrapped value, so no code path anywhere — including an accidental `print(config)` — can render the real value. `reveal()` is the one explicit, named escape hatch, called only at the point a vendor client is actually constructed.
6. `*Credentials.__post_init__` enforces "all-or-nothing" pairing where one field implies another is required (e.g., `S3Credentials`: `access_key_id` and `secret_access_key` must both be set or both `None` — a lone access key ID with no secret is a configuration mistake, not a valid "use the default chain" signal).

#### Edge Cases & Error Handling
- Empty/whitespace-only bucket name → `ConfigurationError`.
- `storage_class="GLACIER"` (a plain string, not the enum member) → `ConfigurationError` naming the accepted enum members in the message.
- `max_retries=-1` or `max_retries=True` (bool is an `int` subclass in Python — must be explicitly excluded, matching `PauseDuration`'s own `isinstance(self.seconds, bool)` guard) → `ConfigurationError`.
- `S3Credentials(access_key_id="AKIA...")` with `secret_access_key=None` → `ConfigurationError` ("both or neither").
- `sse="aws:kms"` with no `kms_key_id` → `ConfigurationError`.

---

### 6.3 `vidbyte/harnesses/stores/_sink_support.py`

**File(s):** `vidbyte/harnesses/stores/_sink_support.py`
**Type:** New file (internal, not exported from `vidbyte/harnesses/stores/__init__.py`)

#### What it does
Shares the encoding-and-size-guard logic across every sink — file, memory-adjacent, and all three new cloud sinks — so the JSON encoding rules (`ensure_ascii=False`, `sort_keys=True`, `separators=(",", ":")`, `allow_nan=False`) live in exactly one place instead of four. Follows the "Class-Bound Helpers" field-guide rule: a static helper class, not a bag of free functions.

#### Interface / API
```python
class SinkEncoding:
    @staticmethod
    def encode_record(record: TrajectoryRecord) -> bytes: ...
    @staticmethod
    def guard_size(payload: bytes, *, run_id: str) -> None: ...
```

#### Logic / Algorithm
1. `encode_record`: identical to `FileTrajectorySink._append`'s existing `json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`, encoded to UTF-8 bytes; on `TypeError`/`ValueError`, raises `HarnessSinkPayloadError` (new, replacing the generic `HarnessSinkError` currently raised inline in `file.py`).
2. `guard_size`: compares `len(payload)` against `MAX_TRAJECTORY_RECORD_BYTES`; raises `HarnessSinkPayloadError` with the actual and allowed byte counts in `details` if it's exceeded, *before* any caller attempts a network call.

#### Edge Cases & Error Handling
- A record containing a value `json.dumps` cannot serialize (e.g. a raw non-JSON-safe object that slipped past `HarnessRedactor`) → `HarnessSinkPayloadError`, not a raw `TypeError`.
- A record that serializes but produces `NaN`/`Infinity` → already rejected by `allow_nan=False` today; behavior preserved.
- A 150 MB record (over the 100 MiB guard) → `HarnessSinkPayloadError` raised locally, zero network calls made — this is the specific "silently timing out on huge tool-output histories" failure mode from the checklist, converted into an immediate, clear error instead.

---

### 6.4 `vidbyte/harnesses/stores/s3.py`

**File(s):** `vidbyte/harnesses/stores/s3.py`
**Type:** New file

#### What it does
`TrajectorySink` backed by AWS S3 (and any S3-API-compatible vendor via `endpoint_url` — Cloudflare R2, Backblaze B2, DigitalOcean Spaces, MinIO).

#### Interface / API
```python
class S3TrajectorySink:
    def __init__(self, config: S3SinkConfig, *, credentials: S3Credentials | None = None) -> None: ...
    async def verify(self) -> None: ...
    async def write(self, record: TrajectoryRecord) -> None: ...
    def _build_client(self) -> Any: ...
    def _assume_role_if_configured(self, base_client_kwargs: dict[str, Any]) -> dict[str, Any]: ...
    async def _ensure_ready(self) -> None: ...
    async def _run_preflight(self) -> None: ...
    def _object_key(self, run_id: str) -> str: ...
    async def _put(self, key: str, payload: bytes) -> None: ...
    def _translate_error(self, exc: Exception) -> HarnessSinkError: ...
    @staticmethod
    def _import_driver() -> Any: ...
```

#### Logic / Algorithm
1. `__init__`: stores `config`/`credentials`; calls `_import_driver()` (lazy `import boto3`, `botocore.config.Config`, `botocore.exceptions`; on `ImportError`, raises `vidbyte.lib.errors.ConfigurationError("S3TrajectorySink requires the 'boto3' package. Install it with `pip install boto3`.")` — exact mirror of `SupabaseSessionStore`); calls `_build_client()` (sync, no network — botocore client construction doesn't itself call the network); creates a nullable `asyncio.Task` slot for verification.
2. `_build_client()`: constructs a `botocore.config.Config(retries={"max_attempts": config.max_retries, "mode": "adaptive"}, region_name=config.region)`; if `config.role_arn` is set, calls `_assume_role_if_configured` first to obtain temporary credentials via STS (`sts.assume_role(RoleArn=..., RoleSessionName=f"vidbyte-{uuid4().hex[:8]}", ExternalId=config.external_id)`), using whichever base credentials resolved (explicit static keys or boto3's own default chain); constructs `boto3.client("s3", endpoint_url=config.endpoint_url, config=that_config, **resolved_credential_kwargs)`. When `credentials` is `None` and `role_arn` is unset, no explicit credential kwargs are passed at all — boto3's own default chain (env vars → shared config file → IAM role) resolves it, which is the preferred keyless path.
3. `verify()`: calls `_run_preflight()` directly (explicit, caller-invoked, not cached against `_ensure_ready`'s cache — callable any time, e.g. right after building the harness, to fail fast before a long run).
4. `_run_preflight()`: runs `head_bucket(Bucket=config.bucket)` via `asyncio.to_thread` (boto3 is synchronous); on success, sets nothing itself (caller sets `_verified`); on failure, calls `_translate_error` and raises.
5. `write(record)`: encodes and guards via `SinkEncoding.prepare_payload` before calling `_ensure_ready()`, computes `_object_key(record.run_id)`, and calls `_put`. This ordering makes the 100 MiB rejection a zero-network operation, including when preflight would otherwise be the first remote call.
6. `_ensure_ready()`: if `_verified`, returns immediately; otherwise acquires the lock, re-checks `_verified` inside it (double-checked locking — avoids two concurrent first-writes both running preflight), runs `_run_preflight()`, sets `_verified = True`.
7. `_object_key(run_id)`: `f"{self._config.prefix.rstrip('/')}/{run_id}.jsonl"` if `prefix` is non-empty, else `f"{run_id}.jsonl"`.
8. `_put(key, payload)`: builds `put_object` kwargs from four explicit groups: object identity/content (`StorageClass`, content headers, metadata, URL-encoded tags, expiry/redirect), retention (`ObjectLock*`), encryption (`AES256`, `aws:kms`, `aws:kms:dsse`, KMS context/bucket key, or per-request SSE-C), and safety/billing (`IfMatch`/`IfNoneMatch`, ACL/grants, checksums, `RequestPayer`). It calls the synchronous SDK via `asyncio.to_thread`; on any vendor exception, `_translate_error` raises the matching shared error type.
9. `_translate_error(exc)`: inspects the exception type and, for `ClientError`, `exc.response["Error"]["Code"]` / `exc.response["ResponseMetadata"]["HTTPStatusCode"]`, mapping:
   - `NoSuchBucket`, `PermanentRedirect` (wrong region) → `HarnessSinkSetupError`
   - `NoCredentialsError`, `ExpiredToken`, `InvalidAccessKeyId`, `SignatureDoesNotMatch`, AssumeRole failures → `HarnessSinkAuthenticationError`
   - `AccessDenied` (including the KMS-header-missing case, which surfaces as `AccessDenied` even though the real cause is encryption policy, not permissions — the error message explicitly calls this out per the checklist) → `HarnessSinkAuthorizationError`
   - `SlowDown`, `RequestTimeout`, `EndpointConnectionError`, `ConnectTimeoutError`, any 5xx → `HarnessSinkUnavailableError`
   - anything else → `HarnessSinkError` (base), never a bare, unwrapped vendor exception.

#### Edge Cases & Error Handling
- `boto3` not installed → `ConfigurationError` at construction, before any config validation runs on the network side.
- Bucket name syntactically valid but the bucket doesn't exist → `HarnessSinkSetupError` from `verify()`/first `write()`, not a confusing raw `ClientError`.
- Bucket exists in `us-west-2` but `config.region` says `us-east-1` → `PermanentRedirect` → `HarnessSinkSetupError` with both regions in `details`.
- Credentials resolve to nothing (no static keys, empty default chain, e.g. running outside AWS with no `~/.aws/credentials`) → `NoCredentialsError` → `HarnessSinkAuthenticationError`.
- Valid credentials, bucket policy doesn't grant `s3:PutObject` on the prefix → `AccessDenied` → `HarnessSinkAuthorizationError`, message explicitly distinguishes "this is a permissions problem, not a network problem."
- `role_arn` set, trust policy doesn't list the caller, or `external_id` mismatch → AssumeRole `ClientError` → `HarnessSinkAuthenticationError`, `details` names the role ARN (never the resolved temporary credentials).
- Session token expires between `verify()` and a `write()` minutes later → caught by `_put`'s own `_translate_error` at write time (expiry isn't and can't be checked proactively) → `HarnessSinkAuthenticationError`.
- Bucket requires `aws:kms` SSE but `config.sse` is unset → `AccessDenied` → `HarnessSinkAuthorizationError`, `fix_approaches` explicitly names "set sse='aws:kms' and kms_key_id" as the likely fix, not just "check your IAM policy."
- Two harness runs finish within the same millisecond with different `run_id`s → two independent `PutObject` calls to two different keys; no collision possible by construction.
- The same `run_id` retried after a transient failure → overwrites the same key with (expected-identical) content by default; configure provider-native generation, ETag, or `IfNoneMatch` conditions when a retry must not clobber a newer object.
- Corporate egress firewall blocks `*.amazonaws.com` → `EndpointConnectionError`/`ConnectTimeoutError` → `HarnessSinkUnavailableError`, message names this as a likely cause distinct from a generic timeout.
- `endpoint_url` set to a Cloudflare R2 endpoint with the wrong signature version → R2-specific `ClientError` surfaces through the same `_translate_error` path; `S3SinkConfig`'s docstring documents that `endpoint_url` targets any S3-compatible vendor and that `region_name` still must be set (R2 requires `"auto"`).

---

### 6.5 `vidbyte/harnesses/stores/gcs.py`

**File(s):** `vidbyte/harnesses/stores/gcs.py`
**Type:** New file

#### What it does
`TrajectorySink` backed by Google Cloud Storage.

#### Interface / API
```python
class GcsTrajectorySink:
    def __init__(self, config: GcsSinkConfig, *, credentials: GcsCredentials | None = None) -> None: ...
    async def verify(self) -> None: ...
    async def write(self, record: TrajectoryRecord) -> None: ...
    def _build_client(self) -> Any: ...
    async def _ensure_ready(self) -> None: ...
    async def _run_preflight(self) -> None: ...
    def _object_key(self, run_id: str) -> str: ...
    async def _put(self, key: str, payload: bytes) -> None: ...
    def _translate_error(self, exc: Exception) -> HarnessSinkError: ...
    @staticmethod
    def _import_driver() -> Any: ...
```

#### Logic / Algorithm
Mirrors S3 exactly except:
1. `_import_driver()` lazily imports `google.cloud.storage` and `google.api_core.exceptions`; missing → `ConfigurationError("...requires the 'google-cloud-storage' package. Install it with `pip install google-cloud-storage`.")`.
2. `_build_client()`: if `credentials.service_account_json_path` is set, loads explicit credentials via `google.oauth2.service_account.Credentials.from_service_account_file(path)` and passes them to `storage.Client(credentials=...)`; otherwise constructs `storage.Client()` with no arguments, letting google-auth resolve Application Default Credentials (env var, `gcloud` user login, or the GCE/GKE/Cloud Run metadata server — Workload Identity, keyless) automatically.
3. `_run_preflight()`: `client.get_bucket(config.bucket)` via `asyncio.to_thread` (the google-cloud-storage client is synchronous, same as boto3). When `bucket_retention_period` is configured, the returned bucket's retention period is reconciled with that value and patched; this is the only explicit bucket-policy mutation in the sink.
4. `_put()`: builds a `Blob(key, bucket)` with either `kms_key_name` or the per-request customer-supplied encryption key, sets storage class/metadata/cache/content-encoding/disposition/holds/retention properties, then calls `upload_from_string` with content type, checksum, generation/metageneration preconditions, and optional predefined ACL. `user_project` is passed to bucket construction and preflight for requester-pays billing.
5. `_translate_error(exc)` maps `google.api_core.exceptions.NotFound` → `HarnessSinkSetupError`; `Forbidden`/`Unauthorized` → distinguished the same way as S3 (`Forbidden` with valid-looking credentials → `HarnessSinkAuthorizationError`; credential resolution itself failing, e.g. `google.auth.exceptions.DefaultCredentialsError` → `HarnessSinkAuthenticationError`); `TooManyRequests`/`ServiceUnavailable`/`DeadlineExceeded` → `HarnessSinkUnavailableError`.

#### Edge Cases & Error Handling
- No ADC resolvable at all (not on GCE, no `GOOGLE_APPLICATION_CREDENTIALS`, no `gcloud auth application-default login`) → `google.auth.exceptions.DefaultCredentialsError` → `HarnessSinkAuthenticationError`, message names the three ways to fix it.
- Bucket exists but the client's project doesn't have `storage.objects.create` on it → `Forbidden` → `HarnessSinkAuthorizationError`.
- CMEK (`kms_key_name`) set, but the service account lacks `Encrypt/Decrypt` on that key → `Forbidden` → `HarnessSinkAuthorizationError`, `fix_approaches` names the specific IAM role needed (`roles/cloudkms.cryptoKeyEncrypterDecrypter`).
- Bucket in a different project than the credentials' default → `NotFound` (GCS reports missing-permission as not-found by design, to avoid leaking bucket existence) → `HarnessSinkSetupError`, message notes this ambiguity explicitly rather than asserting the bucket definitely doesn't exist.
- Same size-guard, idempotent-retry, and firewall-egress edge cases as S3 (Section 6.4), applied identically via the shared `SinkEncoding` helper and the same error taxonomy.

---

### 6.6 `vidbyte/harnesses/stores/azure_blob.py`

**File(s):** `vidbyte/harnesses/stores/azure_blob.py`
**Type:** New file

#### What it does
`TrajectorySink` backed by Azure Blob Storage.

#### Interface / API
```python
class AzureBlobTrajectorySink:
    def __init__(self, config: AzureBlobSinkConfig, *, credentials: AzureBlobCredentials) -> None: ...
    async def verify(self) -> None: ...
    async def write(self, record: TrajectoryRecord) -> None: ...
    def _build_client(self) -> Any: ...
    async def _ensure_ready(self) -> None: ...
    async def _run_preflight(self) -> None: ...
    def _object_key(self, run_id: str) -> str: ...
    async def _put(self, key: str, payload: bytes) -> None: ...
    def _translate_error(self, exc: Exception) -> HarnessSinkError: ...
    @staticmethod
    def _import_driver() -> Any: ...
```

Note the one intentional signature difference from S3/GCS: `credentials` is **required**, not optional, because `account_url` (which identifies *which* storage account to talk to) lives on the `Credentials` object, not on `Config` — Azure has no single implicit "current account" the way AWS/GCP have an implicit default project/account. `account_url` alone with no secret is still valid (it selects the keyless `DefaultAzureCredential` path).

#### Logic / Algorithm
1. `_import_driver()` lazily imports `azure.storage.blob.aio` (the **native async client** — unlike boto3/google-cloud-storage, `azure-storage-blob` ships a first-party asyncio surface, so this sink does not use `asyncio.to_thread` at all) plus `azure.core.exceptions`; if `credentials.connection_string`/`sas_token` are both unset, also lazily imports `azure.identity.aio.DefaultAzureCredential`. Missing package → `ConfigurationError("...requires the 'azure-storage-blob' package (and 'azure-identity' for keyless auth). Install with `pip install azure-storage-blob azure-identity`.")`.
2. `_build_client()`: if `connection_string` is set, `BlobServiceClient.from_connection_string(credentials.connection_string.reveal())`; elif `sas_token` is set, `BlobServiceClient(account_url=f"{credentials.account_url}?{credentials.sas_token.reveal()}")`; else `BlobServiceClient(account_url=credentials.account_url, credential=DefaultAzureCredential())` (managed identity / AAD — the keyless path). Retry policy is passed via `retry_total=config.max_retries` on the client constructor, Azure's own native retry configuration.
3. `_run_preflight()`: `await container_client.get_container_properties()` — genuinely async, no thread wrapping needed.
4. `_put()`: builds `ContentSettings` from content type/encoding/cache/disposition/MD5 and calls `upload_blob` with metadata, tags, the native access tier, optional wire validation, ETag/tag conditions, immutability policy/legal hold, customer-provided encryption key, and encryption scope. `overwrite=True` remains the default, but `if_none_match=True` switches to `If-Missing` so callers can reject an existing blob.
5. `_translate_error(exc)` maps `azure.core.exceptions.ResourceNotFoundError` → `HarnessSinkSetupError`; `ClientAuthenticationError` → `HarnessSinkAuthenticationError`; `HttpResponseError` with `status_code == 403` → `HarnessSinkAuthorizationError`; `ServiceRequestError` (network-level) and `HttpResponseError` with `status_code in (429, 503)` → `HarnessSinkUnavailableError`.

#### Edge Cases & Error Handling
- `connection_string` given but malformed (wrong key format) → raised at `_build_client()` time, wrapped as `HarnessSinkSetupError` (this is a local, non-network failure but still surfaces through the same taxonomy since it's about "can we even address the account," not "is the request shape valid" — kept in Stage 2's error types rather than `ConfigurationError` because it requires parsing Azure-specific string structure the dataclass layer shouldn't need to know about).
- No `connection_string`/`sas_token`, and `DefaultAzureCredential` can't resolve any credential source (not running under a managed identity, no `az login`, no env vars) → `ClientAuthenticationError` → `HarnessSinkAuthenticationError`.
- SAS token expired → `HttpResponseError(403)` at write time (Azure reports an expired SAS as an authorization failure, not a distinct "expired" code) → `HarnessSinkAuthorizationError`, message explicitly calls out "check whether this is actually a SAS token expiry, not a policy problem" — the checklist item about a misleading-surface-error applies here as much as to S3's KMS case.
- Container tier set to `Archive` on write — valid, but Azure blocks reads of archived blobs until manually rehydrated; this is not an error the sink can catch (the write itself succeeds), so `AzureBlobSinkConfig`'s docstring and the README explicitly warn that `Archive` is a write-mostly tier unsuitable for data the customer expects to query soon after export.
- Same size-guard and idempotent-retry edge cases as S3/GCS.

---

### 6.6.1 Provider-native object contract

The sink configs preserve each provider's real object API instead of collapsing
important governance controls into a lowest-common-denominator abstraction.
Unset fields are omitted from the request so the original PR behavior and
provider defaults remain intact.

| Concern | S3 | GCS | Azure Blob |
|---|---|---|---|
| Lineage/cost metadata | `metadata` -> `x-amz-meta-*`; `tags` -> URL-encoded `Tagging` | `metadata` -> `blob.metadata` | `metadata` and `tags` on `upload_blob` |
| Content controls | `ContentType`, `ContentEncoding`, `CacheControl`, `ContentDisposition` | blob content properties and upload `content_type` | `ContentSettings` |
| Customer key | `SSECustomerAlgorithm`, `SSECustomerKey`, `SSECustomerKeyMD5` | `Blob(encryption_key=...)` | `CustomerProvidedEncryptionKey` as `cpk` |
| Managed encryption | `AES256`, `aws:kms`, `aws:kms:dsse`, KMS context, bucket key | `kms_key_name` or customer key | customer-provided key, encryption scope, or account defaults |
| Retention | `ObjectLockMode`, `ObjectLockRetainUntilDate`, legal hold | object retention mode/time and holds | `immutability_policy`, legal hold |
| Safe concurrency | `IfMatch` / `IfNoneMatch` | generation and metageneration preconditions | ETag match conditions and tag condition |
| Integrity/billing | checksum algorithm, `ContentMD5`, `RequestPayer` | upload checksum, `user_project` | `content_md5`, `validate_content` |

S3 also exposes canned ACL/grants, `Expires`, `WebsiteRedirectLocation`,
dual-stack and transfer-acceleration endpoint flags, and `OUTPOSTS`/
`EXPRESS_ONEZONE` storage classes. `aws:kms:dsse` is a distinct encryption
mode; bucket keys and KMS encryption context are modeled for `aws:kms`.
SSE-C is deliberately separate from managed encryption: the caller supplies a
raw 32-byte key on each request and is responsible for secure key lifecycle.

GCS's `bucket_retention_period` is applied during preflight because retention
policy is a bucket property, not an object PUT field. GCS soft delete and
object versioning, S3 versioning, Azure soft delete, and every lifecycle or
expiration rule are likewise destination policies. Configure those with the
provider management plane; the sink does not mutate them during object upload.

`content_encoding="gzip"` compresses the JSONL bytes before the provider call
and sets the corresponding content header/property. The shared encoder guards
the uncompressed representation and then the compressed bytes before
preflight/network activity. Multipart/chunked upload remains intentionally
absent: if the 100 MiB guard is reached, raise the bound only after confirming
all provider single-PUT ceilings and downstream reader support.

### 6.7 `vidbyte/lib/errors` and `vidbyte/harnesses/errors.py` (MODIFY)

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`, and `vidbyte/harnesses/errors.py`
**Type:** Modified

#### What it does
Adds the five new `HarnessSinkError` subclasses to the dependency-light shared error layer, each following the exact existing shape (`description`, `expected_vs_actual`, `blast_radius`, `possible_causes`, `fix_approaches`, `doc_links`, `test_files`, inherited `to_context_packet()`). `vidbyte/harnesses/errors.py` re-exports them for compatibility; it does not own the provider error hierarchy.

#### Interface / API
```python
class HarnessSinkSetupError(HarnessSinkError):
    """Raised when a cloud sink's destination cannot be resolved (missing bucket, wrong region, bad endpoint)."""

class HarnessSinkAuthenticationError(HarnessSinkError):
    """Raised when a cloud sink cannot establish who it is (missing/invalid/expired credentials, failed role assumption)."""

class HarnessSinkAuthorizationError(HarnessSinkError):
    """Raised when a cloud sink is identified but not permitted to write (policy denial, missing encryption grant)."""

class HarnessSinkUnavailableError(HarnessSinkError):
    """Raised when a cloud sink's destination could not be reached after the vendor SDK's own retries were exhausted."""

class HarnessSinkPayloadError(HarnessSinkError):
    """Raised when a trajectory record cannot be encoded, or exceeds the sink's size guard, before any I/O is attempted."""
```

Each carries its own multi-sentence `description`/`expected_vs_actual` (per the "Agent-Facing Diagnostic Context" field-guide rule — several complete sentences naming the protected boundary, caller-visible consequence, canonical repair, and rejected shortcuts), plus provider-agnostic `possible_causes`/`fix_approaches` naming the concrete scenarios from Section 6.4–6.6 (e.g. `HarnessSinkAuthorizationError.fix_approaches` explicitly includes "if this bucket requires server-side encryption, confirm `sse`/`kms_key_id` (S3) or `kms_key_name` (GCS) is set — a missing encryption header surfaces as a permission denial, not an encryption error").

#### Logic / Algorithm
Pure declarative subclassing, matching every existing class in the file — no new logic.

#### Edge Cases & Error Handling
N/A — these are the typed error surface, not logic that itself has edge cases.

---

### 6.8 `vidbyte/harnesses/stores/file.py` (MODIFY)

**File(s):** `vidbyte/harnesses/stores/file.py`
**Type:** Modified

#### What it does
Refactors `_append`'s inline `json.dumps(...)` call to use `SinkEncoding.encode_record`, and its `TypeError`/`ValueError` handler to raise the new `HarnessSinkPayloadError` instead of the generic `HarnessSinkError` it raises today — a small consistency fix so every sink (file and cloud alike) reports a serialization failure with the same specific type.

#### Interface / API
No public signature changes — `FileTrajectorySink.write()`'s contract is identical.

#### Logic / Algorithm
1. Replace the inline `json.dumps(...)` block in `_append` with `payload = SinkEncoding.encode_record(record)`.
2. Replace the `except (TypeError, ValueError) as exc: raise HarnessSinkError(...)` with letting `SinkEncoding.encode_record` raise `HarnessSinkPayloadError` directly (it already wraps the same exception types).
3. `OSError` handling for the actual file write is unchanged — that failure mode is genuinely file-sink-specific (disk full, permission denied) and stays a plain `HarnessSinkError`, since no cloud-specific subclass applies to local disk I/O.

#### Edge Cases & Error Handling
- Existing behavior for a genuinely unwritable path (permission denied, missing parent that can't be created) is unchanged.
- A record that fails to serialize now raises `HarnessSinkPayloadError` instead of `HarnessSinkError` — this is a narrowing of an existing error type to a subclass, so any caller catching the current `HarnessSinkError` still catches it (subclass), but a caller specifically distinguishing serialization failures gains the ability to do so.

---

### 6.9 `vidbyte/harnesses/stores/__init__.py` (MODIFY)

**File(s):** `vidbyte/harnesses/stores/__init__.py`
**Type:** Modified

#### What it does
Exports the three new sinks alongside the existing two, keeping `SinkEncoding` unexported (internal helper, leading underscore module).

#### Interface / API
```python
from vidbyte.harnesses.stores.azure_blob import AzureBlobTrajectorySink
from vidbyte.harnesses.stores.base import TrajectorySink
from vidbyte.harnesses.stores.file import FileTrajectorySink
from vidbyte.harnesses.stores.gcs import GcsTrajectorySink
from vidbyte.harnesses.stores.memory import InMemoryTrajectorySink
from vidbyte.harnesses.stores.s3 import S3TrajectorySink

__all__ = ["AzureBlobTrajectorySink", "FileTrajectorySink", "GcsTrajectorySink", "InMemoryTrajectorySink", "S3TrajectorySink", "TrajectorySink"]
```

#### Edge Cases & Error Handling
N/A — pure re-export.

---

### 6.10 `vidbyte/harnesses/client.py` (MODIFY)

**File(s):** `vidbyte/harnesses/client.py`
**Type:** Modified

#### What it does
Adds three factory methods matching the existing `file_sink()`/`memory_sink()` shape exactly, so a developer's only code change to switch destinations is the one call site.

#### Interface / API
```python
def s3_sink(self, config: S3SinkConfig, *, credentials: S3Credentials | None = None) -> S3TrajectorySink: ...
def gcs_sink(self, config: GcsSinkConfig, *, credentials: GcsCredentials | None = None) -> GcsTrajectorySink: ...
def azure_blob_sink(self, config: AzureBlobSinkConfig, *, credentials: AzureBlobCredentials) -> AzureBlobTrajectorySink: ...
```

#### Logic / Algorithm
Each is a one-line pass-through constructor call, identical in shape to `file_sink(self, path)`.

#### Edge Cases & Error Handling
Delegates entirely to the sink's own `__init__` — no additional validation at this layer, matching `file_sink`'s own zero-validation pass-through today.

---

### 6.11 `vidbyte/harnesses/execution.py` (MODIFY) — the observability hook

**File(s):** `vidbyte/harnesses/execution.py`
**Type:** Modified

#### What it does
Closes the silent-failure gap verified in Section 3: `_maybe_collect`'s `except Exception: return` currently swallows every sink failure with zero trace, for every sink, today. This adds an **opt-in** hook so a caller who wants visibility can get it, while every existing caller (who passes nothing) observes byte-identical behavior.

#### Interface / API
```python
class Harness:
    def __init__(self, *, store: SessionStore | None = None, sink: TrajectorySink | None = None, collect: bool = False, on_sink_error: Callable[[SinkFailureEvent], None] | None = None) -> None: ...
```
`wrap_implementation()` gains the same `on_sink_error` parameter, passed through to the constructed `Harness`.

`SinkFailureEvent` (new, in `vidbyte/lib/dataclasses/harnesses.py`, re-exported via `vidbyte/harnesses/contracts.py`):
```python
@dataclass(frozen=True, slots=True)
class SinkFailureEvent:
    run_id: str
    sink_type: str
    error_type: str
    message: str
    occurred_at: str
    error: Mapping[str, Any]  # complete safe packet from HarnessSinkError.to_context_packet()
```
`message` is passed through `HarnessRedactor.safe_error_message()` (already exists, already used elsewhere for exactly this purpose) before being placed on the event — so even if a vendor exception's string representation happened to echo back part of a request (some SDKs include request parameters in error text), the existing credential-assignment redaction pass still runs over it. `error` contains the complete safe diagnostic packet (`expected`, `actual`, causes, repairs, docs, tests, and provider-safe runtime details) when the exception implements `to_context_packet()`, with a minimal type/message/details fallback for unrelated collection failures. `sink_type`/`error_type` are `type(sink).__name__`/`type(exc).__name__` — class names, never instance state, so nothing sink-instance-specific (bucket name, endpoint, credentials) can leak through them either.

#### Logic / Algorithm
1. `Harness.__init__` stores `self._on_sink_error = on_sink_error`.
2. `_maybe_collect`'s `except Exception: return` becomes `except Exception as exc: self._report_sink_failure(exc); return` — the `return` (and therefore the fail-open guarantee) is completely unchanged; only the newly-added line before it is new.
3. New `_report_sink_failure(self, exc: Exception) -> None`: if `self._on_sink_error is None`, returns immediately (byte-identical to today). Otherwise builds a `SinkFailureEvent` and calls `self._on_sink_error(event)` inside its own `try: ... except Exception: pass` — a broken callback must never itself break fail-open, so a raising callback is silently ignored, same as everything else in this method.

#### Edge Cases & Error Handling
- `on_sink_error` not supplied (every existing caller) → `_report_sink_failure` is a no-op; `_maybe_collect`'s observable behavior is unchanged bit-for-bit.
- `on_sink_error` supplied but itself raises → swallowed, does not propagate, does not affect the run — this is the one place this design deliberately breaks the "make failures loud" instinct, because a broken observability callback breaking a customer's production harness run would be a materially worse outcome than staying silent.
- The failure occurred inside `TrajectoryCollector.collect()` (a `SessionStore` read failure) rather than inside `sink.write()` — `_report_sink_failure` still fires, with `sink_type` set to the bound sink's class name even though the sink itself never got a chance to fail; this is intentional (both `except Exception` clauses in `_maybe_collect` already treat collection failures and sink-write failures identically, so the new hook does too, rather than trying to distinguish stages that the existing code doesn't distinguish).
- Two concurrent runs on the same `Harness` instance both fail collection at once — not a new race condition; `Harness` is already documented as "not concurrently reentrant... use a fresh instance per concurrent execution," so this is out of scope exactly like every other cross-run state on `Harness` today.

---

## 7. Data Model Changes

### 7.1 `SinkFailureEvent` (new)

**Change type:** New

```python
# vidbyte/lib/dataclasses/harnesses.py
@dataclass(frozen=True, slots=True)
class SinkFailureEvent:
    """Credential-free record of one swallowed collection/sink failure."""
    run_id: str
    sink_type: str
    error_type: str
    message: str
    occurred_at: str
    error: Mapping[str, Any]
```

`error` is the complete safe packet returned by `HarnessSinkError.to_context_packet()`;
it includes the expected/actual boundary, runtime-safe details, likely causes,
repair approaches, related docs, and relevant tests. Unrelated collection
failures use a minimal type/message/details packet. No credentials or raw
payloads are included.

**Migration strategy:** N/A — purely additive, no existing data affected. Not persisted anywhere; it exists only as an in-process callback argument.

### 7.2 New `Config`/`Credentials`/enum shapes (new)

**Change type:** New — see Section 6.2 in full. Not database or wire schema changes; these are constructor-argument shapes, never serialized, never part of `spec_id` hashing, never touched by `HarnessConfigLoader`.

**Migration strategy:** N/A.

---

## 8. API Changes

N/A — this SDK has no network-facing API surface of its own; `vidbyte/harnesses/client.py`'s new methods are Python constructor factories, not HTTP endpoints. Covered fully in Section 6.10.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/constants/cloud_sinks.py` | Shared numeric bounds (Section 6.1) |
| CREATE | `vidbyte/lib/dataclasses/cloud_sinks.py` | Config/Credentials/enum/Secret shapes (Section 6.2) |
| CREATE | `vidbyte/harnesses/stores/_sink_support.py` | Shared encoding + size-guard helper (Section 6.3) |
| CREATE | `vidbyte/harnesses/stores/s3.py` | `S3TrajectorySink` (Section 6.4) |
| CREATE | `vidbyte/harnesses/stores/gcs.py` | `GcsTrajectorySink` (Section 6.5) |
| CREATE | `vidbyte/harnesses/stores/azure_blob.py` | `AzureBlobTrajectorySink` (Section 6.6) |
| CREATE | `tests/test_cloud_trajectory_sinks.py` | Unit/integration tests (Section 10) |
| CREATE | `scripts/test_cloud_trajectory_sinks.py` | Phase 5 standalone verification script |
| MODIFY | `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`, `vidbyte/harnesses/errors.py` | Shared +5 `HarnessSinkError` subclasses and compatibility re-exports (Section 6.7) |
| MODIFY | `vidbyte/harnesses/stores/file.py` | Shares `SinkEncoding`; raises `HarnessSinkPayloadError` (Section 6.8) |
| MODIFY | `vidbyte/harnesses/stores/__init__.py` | Exports the three new sinks (Section 6.9) |
| MODIFY | `vidbyte/harnesses/client.py` | +`s3_sink()`/`gcs_sink()`/`azure_blob_sink()` (Section 6.10) |
| MODIFY | `vidbyte/harnesses/execution.py` | +`on_sink_error` observability hook (Section 6.11) |
| MODIFY | `vidbyte/harnesses/contracts.py` | Re-exports `SinkFailureEvent` |
| MODIFY | `vidbyte/lib/dataclasses/harnesses.py` | +`SinkFailureEvent` (Section 7.1) |
| MODIFY | `vidbyte/harnesses/README.md` | Replaces the "future WarehouseTrajectorySink" line with real usage examples for all three sinks, cross-account role assumption, and the `on_sink_error` hook |

No files are deleted.

---

## 10. Testing Plan

`vidbyte/harnesses/` currently ships with **zero** dedicated pytest files (every module's docstring notes "no dedicated test file was added under the approved no-tests workflow," and `tests/` has no `test_harness*.py` at all). This design deliberately departs from that local precedent — Section 14 explains why — and adds real, mocked-vendor-client unit tests. No real AWS/GCP/Azure account, network access, or installed vendor SDK is required to run them: every test either monkeypatches `_import_driver`/`_build_client` to return a stub client, or constructs `Config`/`Credentials` objects directly against `__post_init__` without touching any sink.

### Unit Tests

**`S3SinkConfig` / `GcsSinkConfig` / `AzureBlobSinkConfig` / `*Credentials` / `Secret`**
- `describe('S3SinkConfig')` → `it('rejects an empty bucket name')` — [Edge Case]
- `describe('S3SinkConfig')` → `it('rejects a bucket name shorter than 3 characters')` — [Edge Case]
- `describe('S3SinkConfig')` → `it('rejects a storage_class value that is not an S3StorageClass member')` — [Hidden Assumption] (the field is type-hinted as the enum, but nothing stops a caller from passing a plain string at runtime)
- `describe('S3SinkConfig')` → `it('rejects max_retries=True (bool is an int subclass)')` — [Hidden Failure]
- `describe('S3SinkConfig')` → `it('rejects sse="aws:kms" with kms_key_id=None')` — [Silent Failure] (without this check, the sink would build a request AWS rejects with a confusing error instead of failing at construction with a clear one)
- `describe('S3Credentials')` → `it('rejects access_key_id set with secret_access_key=None')` — [Hidden Assumption]
- `describe('S3Credentials')` → `it('accepts both fields None as the default-credential-chain signal')` — [Edge Case]
- `describe('Secret')` → `it('never includes the wrapped value in repr() or str()')` — [Silent Failure] (this is the single highest-value security test in the whole plan — a regression here is a credential leak, not a wrong answer)
- `describe('Secret')` → `it('reveal() returns the exact original value')` — [Edge Case]
- `describe('AzureBlobSinkConfig')` → `it('rejects an empty container name')` — [Edge Case]
- `describe('GcsSinkConfig')` → `it('rejects a storage_class value that is not a GcsStorageClass member')` — [Hidden Assumption]

**`SinkEncoding`**
- `describe('SinkEncoding.encode_record')` → `it('produces byte-identical output to the pre-refactor FileTrajectorySink encoding for the same record')` — [Silent Failure] (this is the regression the file.py refactor could introduce without anyone noticing — same-looking JSON with a different key order or escaping would silently corrupt existing downstream JSONL consumers)
- `describe('SinkEncoding.encode_record')` → `it('raises HarnessSinkPayloadError, not TypeError, for a record containing a non-serializable value')` — [Hidden Failure]
- `describe('SinkEncoding.guard_size')` → `it('accepts a payload exactly at MAX_TRAJECTORY_RECORD_BYTES')` — [Edge Case] (boundary, not just over/under)
- `describe('SinkEncoding.guard_size')` → `it('rejects a payload one byte over MAX_TRAJECTORY_RECORD_BYTES with HarnessSinkPayloadError, before any I/O')` — [Edge Case]

**`S3TrajectorySink`** (mirrored for `GcsTrajectorySink`/`AzureBlobTrajectorySink` with provider-appropriate stub exceptions)
- `describe('S3TrajectorySink.__init__')` → `it('raises ConfigurationError, not ImportError, when boto3 is not installed')` — [Hidden Assumption] — simulated via monkeypatching `_import_driver` to raise `ImportError`
- `describe('S3TrajectorySink.write')` → `it('writes to key "{prefix}/{run_id}.jsonl" when prefix is set')` — [Silent Failure] (a wrong key format would "succeed" with no visible error while writing to a location the customer's downstream tooling never reads)
- `describe('S3TrajectorySink.write')` → `it('writes to key "{run_id}.jsonl" with no leading slash when prefix is empty')` — [Edge Case]
- `describe('S3TrajectorySink.write')` → `it('sends exactly one PutObject call for one write() call')` — [Hidden Assumption] (guards against an accidental retry loop double-writing)
- `describe('S3TrajectorySink.write')` → `it('sets StorageClass on the PutObject call to the configured S3StorageClass value')` — [Silent Failure] (the tier setting silently doing nothing is exactly the kind of wrong-but-not-erroring behavior this category exists to catch)
- `describe('S3TrajectorySink.write')` → `it('overwrites rather than errors on a second write() with the same run_id')` — [Hidden Assumption]
- `describe('S3TrajectorySink._ensure_ready')` → `it('runs head_bucket only once across two concurrent write() calls on a fresh instance')` — [Hidden Failure] — spins up two concurrent `write()` coroutines against a stub client that counts `head_bucket` calls
- `describe('S3TrajectorySink._translate_error')` → `it('maps a ClientError with Code=NoSuchBucket to HarnessSinkSetupError')` — [Edge Case]
- `describe('S3TrajectorySink._translate_error')` → `it('maps a ClientError with Code=AccessDenied to HarnessSinkAuthorizationError, not HarnessSinkAuthenticationError')` — [Silent Failure] (conflating these two would mean the error message tells a customer to check their credentials when the real fix is their bucket policy — a "correct-looking" wrong answer)
- `describe('S3TrajectorySink._translate_error')` → `it('maps NoCredentialsError to HarnessSinkAuthenticationError')` — [Edge Case]
- `describe('S3TrajectorySink._translate_error')` → `it('maps EndpointConnectionError to HarnessSinkUnavailableError')` — [Edge Case]
- `describe('S3TrajectorySink.write')` → `it('raises HarnessSinkPayloadError and makes zero PutObject calls for an oversized record')` — [Hidden Failure]
- `describe('S3TrajectorySink.__init__')` → `it('never logs, prints, or includes the resolved secret_access_key value anywhere in the constructed client kwargs captured by the stub')` — [Silent Failure]

**`AzureBlobTrajectorySink`-specific**
- `describe('AzureBlobTrajectorySink.__init__')` → `it('requires credentials to be supplied (not Optional, unlike S3/GCS)')` — [Hidden Assumption] — a `TypeError` at the Python level for a missing required kwarg, confirming the deliberate signature asymmetry documented in Section 6.6 is real, not accidental
- `describe('AzureBlobTrajectorySink.write')` → `it('passes overwrite=True on every upload_blob call')` — [Silent Failure]
- `describe('AzureBlobTrajectorySink._translate_error')` → `it('maps HttpResponseError(status_code=403) to HarnessSinkAuthorizationError')` — [Edge Case]

**`vidbyte.harnesses.execution.Harness` — the observability hook**
- `describe('Harness._maybe_collect')` → `it('does not call on_sink_error when it is None (default)')` — [Hidden Assumption] — the single most important backward-compatibility test in this plan
- `describe('Harness._maybe_collect')` → `it('still returns normally (does not raise) when sink.write() fails and on_sink_error is set')` — [Silent Failure] (a change here that accidentally re-raised would silently break the fail-open guarantee for every existing caller, not just new ones)
- `describe('Harness._maybe_collect')` → `it('still returns normally when sink.write() fails and on_sink_error itself raises')` — [Hidden Failure]
- `describe('Harness._maybe_collect')` → `it('calls on_sink_error with a SinkFailureEvent whose message has been passed through HarnessRedactor.safe_error_message')` — [Silent Failure] — construct a fake sink whose `write()` raises an exception whose string contains an `api_key=sk-live-...`-shaped substring; assert the event's `message` does not contain it verbatim
- `describe('Harness._maybe_collect')` → `it('fires on_sink_error for a TrajectoryCollector.collect() failure, not only a sink.write() failure')` — [Hidden Assumption]

### Integration Tests

- **End-to-end flow:** `Harness.execute()` with `collect=True`, a real `InMemorySessionStore`, and a stub `S3TrajectorySink` (real class, stubbed boto3 client) — asserts a genuine multi-agent run produces exactly one JSONL-shaped object at the expected key, matching what `FileTrajectorySink` would have produced for the same run byte-for-byte except for destination.
- **Silent failure path across components:** stub client raises on `put_object`; assert `execute()` still returns `HarnessExecutionResult` with `status=SUCCEEDED` (the harness's own run succeeded even though export failed) — this is exactly the failure path a unit test on `_maybe_collect` alone cannot fully prove, since it requires the real `execute()` control flow around it.
- **Hidden assumption surfaced only at integration level:** a harness with `collect=True` but `sink=None` — assert no sink methods are invoked and no error of any kind occurs (existing `_maybe_collect` guard, `if ... or self._sink is None ...: return` — worth an explicit regression test since the new cloud sinks make this branch easy to forget when reasoning only about the new file).
- **External dependencies:** boto3/google-cloud-storage/azure-storage-blob are never installed or called for real in CI; every integration test stubs at the `_import_driver`/`_build_client` boundary. A separate, clearly-labeled *manual* verification (Section 10, Manual/QA below) is the only place real cloud credentials are ever used.

### Manual / QA Test Cases

1. Given a real, empty S3 bucket the tester owns and a valid IAM policy scoped to `s3:PutObject` on one prefix, when a harness with `collect=True` and `sink=sdk.harnesses.s3_sink(...)` runs to completion, then exactly one `{run_id}.jsonl` object appears at the configured prefix with the configured storage class. — [Edge Case: first-ever write to an empty bucket]
2. Given the same setup but with the IAM policy's `Resource` scoped to the wrong prefix, when the harness runs, then `execute()` still returns successfully (fail-open, confirmed against real AWS, not just the mocked test suite) and a debug run with `on_sink_error` set observes exactly one `HarnessSinkAuthorizationError`. — [Hidden Failure: production IAM misconfiguration]
3. Given `role_arn` set to a role whose trust policy does not list the caller's principal, when `verify()` is called explicitly before running the harness, then it raises `HarnessSinkAuthenticationError` immediately, before the harness's own (potentially expensive, multi-minute) `run()` ever executes. — [Edge Case: fail-fast vs. fail-late]
4. Given a GCS bucket with a CMEK the service account cannot use, when the harness runs, then the resulting `HarnessSinkAuthorizationError.fix_approaches` names the specific missing IAM role, verified against the real GCS error text (not just the mocked exception shape used in unit tests). — [Silent Failure: the raw google-api-core error text alone does not obviously say "grant this role"]
5. Given a corporate network with egress to `*.blob.core.windows.net` blocked by a firewall rule, when the harness runs, then the failure surfaces as `HarnessSinkUnavailableError` rather than hanging until some outer timeout. — [Hidden Failure: enterprise network conditions the unit test suite cannot reproduce]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `boto3` | latest, lazily imported, not pinned in `pyproject.toml` | S3 client + STS role assumption | Not installed by default; `ConfigurationError` guides install. No pyproject change (matches `supabase` precedent). |
| `google-cloud-storage` | latest, lazily imported | GCS client | Same as above. |
| `google-auth` | transitive dependency of `google-cloud-storage` | Application Default Credentials resolution | Same as above. |
| `azure-storage-blob` | latest, lazily imported (async submodule `azure.storage.blob.aio`) | Azure Blob client | Same as above. |
| `azure-identity` | latest, lazily imported (only when neither `connection_string` nor `sas_token` is set) | `DefaultAzureCredential` (keyless path) | Same as above; only required for the keyless path, not for connection-string/SAS auth. |
| AWS STS | `sts.amazonaws.com` (regional or global, per `boto3` defaults) | Cross-account `AssumeRole` | Only called when `S3SinkConfig.role_arn` is set. |

No new dependency is added to `[project.optional-dependencies]` in `pyproject.toml` — see Section 14 for why this matches, rather than deviates from, existing precedent.

---

## 12. Rollout & Deployment

- No feature flag — this is purely additive: three new classes, three new client factory methods, and a `None`-default constructor parameter. No existing call site changes behavior.
- Not a breaking change. `Harness.__init__`'s new `on_sink_error` parameter is keyword-only with a `None` default; `wrap_implementation()`'s new parameter is the same. `FileTrajectorySink`'s narrowed exception type (`HarnessSinkPayloadError` instead of `HarnessSinkError`) is a subclass, so any existing `except HarnessSinkError` catch site is unaffected.
- Deployment order: single package release — everything lands in one `vidbyte-sdk` version bump, since the three sinks, the shared encoding helper, and the observability hook are one cohesive change with no useful intermediate state.
- Rollback: revert the PR. No persisted state (database rows, migrations) is introduced anywhere in this design — every new type is either an in-memory constructor argument or a class definition.

---

## 13. Open Questions

- [x] Validation bounds live in `vidbyte/lib/constants/cloud_sinks.py`, matching the one-file-per-feature-area precedent.
- [x] `MAX_TRAJECTORY_RECORD_BYTES = 100 MiB` remains a shared guard. It is checked before preflight/network activity, and multipart is deferred until a real workload demonstrates that a larger single-PUT bound is necessary.
- [ ] Should the manual QA cases in Section 10 be run against real Vidbyte-owned or engineer-owned cloud accounts before merge, or is mocked-only coverage sufficient for the initial PR, with manual verification tracked as a follow-up?
- [ ] Should `HarnessSinkAuthenticationError`/`HarnessSinkAuthorizationError` also be added as importable names from `vidbyte.harnesses` (the top-level package `__init__.py`), matching how deeply callers are expected to catch specific sink failures versus the broader `HarnessSinkError`?

---

## 14. Alternatives Considered

### Alternative 1: Add cloud backends to `SessionStore` instead of `TrajectorySink`
- What: extend `vidbyte/lib/providers/` (which already holds `SessionStore` DB backends) with S3/GCS/Azure variants, following the `SupabaseSessionStore` pattern directly.
- Why rejected: `SessionStore` is the unredacted operational source of truth. Writing it to a customer's bucket would ship raw internal `Checkpoint`/`RunState` data — including whatever a `HarnessRedactor` never sees, since redaction only runs on the `TrajectorySink` path — which is exactly the consent/redaction boundary the harness README says this split exists to protect. See Section 3.

### Alternative 2: One universal cross-vendor storage-tier enum
- What: a single `StorageTier` enum (`HOT`, `WARM`, `COLD`, `ARCHIVE`) mapped internally to each vendor's real tier names.
- Why rejected: the mapping is lossy in both directions (S3 has seven tiers with genuinely different retrieval-time/cost tradeoffs GCS's four don't capture 1:1, and `INTELLIGENT_TIERING` has no cross-vendor equivalent at all), and it hides real vendor-specific tradeoffs the customer explicitly asked to control. Exposing each vendor's real enum, per the user's own stated requirement, is more precise and no harder to use.

### Alternative 3: Hand-rolled retry/backoff wrapper shared across all three sinks
- What: a `with_retries()` helper in `_sink_support.py` wrapping every network call.
- Why rejected: every vendor SDK already ships its own retry/backoff engine (`botocore.config.Config(retries=...)`, google-api-core's default retry policies, Azure's `retry_total`/retry policy classes), tuned to that vendor's actual error taxonomy and rate-limit signals. Reimplementing this is exactly the kind of thing easy to get subtly wrong, and was explicitly flagged as a risk to avoid in the original failure-mode checklist this design implements.

### Alternative 4: Multipart/chunked upload support in v1
- What: switch to multipart upload above some size threshold instead of guarding and rejecting.
- Why rejected: a `TrajectoryRecord` is one harness run's redacted history — normally KB to low-single-digit-MB. Building multipart handling (its own failure modes: dangling incomplete uploads on crash, abort-on-failure bookkeeping, cross-provider API differences) to solve a problem no real trajectory record produces yet is scope creep. The size guard converts the rare pathological case into an immediate, clear `HarnessSinkPayloadError` instead. If a real need for larger records appears, multipart can be added later entirely inside `_put()` with zero change to the `TrajectorySink` protocol or any caller.

### Alternative 5: Per-sink `on_failure` callback instead of one `Harness`-level `on_sink_error` hook
- What: give `S3TrajectorySink`/`GcsTrajectorySink`/`AzureBlobTrajectorySink` each their own `on_failure` constructor parameter.
- Why rejected: every sink failure — file, memory, or cloud — already funnels through the exact same `Harness._maybe_collect()` choke point today. Duplicating an observability contract three times per-provider, when one hook at the existing choke point covers every sink (including the two that already exist), contradicts the "Fallback Coordination" field-guide's own stated principle: keep this kind of policy behind one coordinator rather than scattering the same feature into every neighboring class.

### Alternative 6: Keep the existing "approved no-tests workflow" for this PR, matching every other file in `vidbyte/harnesses/`
- What: ship these sinks with only inline smoke verification, like every existing file in this package.
- Why rejected: this PR is materially different in risk profile from the existing harness-envelope code that earned that exception — it's the first code in this package that handles third-party credentials and makes outbound network calls to external services. A regression here (a credential leaked into a log line, a wrong-tier write silently going to the wrong storage class, an error miscategorized as "auth" when it's actually "no permission") is a security or trust incident, not a functional bug. Dedicated mocked-client tests are proportionate to that risk; Section 10's manual QA cases are the one place real cloud credentials are used, deliberately kept out of the automated suite.

---

## Summary

**Implementation status:** Complete. The provider-native object contract, shared error packets, preflight-before-write flow, and focused tests described above are implemented. The design remains intentionally write-only: destination lifecycle, versioning, soft delete, and bucket/account retention policies are configured outside an object PUT.

**Key risks:**
- Getting each vendor's error-code-to-`HarnessSinkError`-subclass mapping right depends on details (exact `botocore` error codes, `google.api_core.exceptions` class names, Azure `status_code` values) that are best double-checked against each SDK's current version during implementation, not assumed from this doc alone.
- The `AzureBlobTrajectorySink` async-native-client vs. `asyncio.to_thread`-wrapped-sync-client asymmetry (Section 6.6) is a real implementation detail that needs care — mixing the two styles inconsistently across the three sinks would be an easy, subtle bug.
- Real-account manual QA remains deployment-specific because the automated suite uses mocked vendor clients; the provider mappings are covered by focused request-shape tests and the public configuration exports are smoke-tested.

**Deviations from local convention, called out explicitly rather than silently:** this PR adds real pytest tests to `vidbyte/harnesses/`, the first in that package, departing from its "approved no-tests workflow" precedent — reasoning in Alternative 6.
