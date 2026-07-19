# Design Doc: Harness Config Loader — Pydantic Validation Collapse

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-19
**Last Updated:** 2026-07-19

---

## 1. Overview

`vidbyte/harnesses/config.py` (404 lines) hand-rolls the entire validation and
normalization pipeline for the harness behavior envelope: top-level key checks,
schema-version gating, per-agent shape checks, recursive JSON-safety normalization,
and a recursive credential-key scan — all as ~20 bespoke `_validate_*` / `_normalize_*`
methods. This is exactly the shape of validation that a declarative `pydantic` model
does for free, and `pydantic>=2,<3` is already a first-class SDK dependency used
across `main` with `ConfigDict(extra="forbid")` + `model_validator`.

This change replaces the bespoke structural validation and JSON-normalization with a
single declarative pydantic schema (`HarnessConfigSchema`) while **preserving every
externally observable contract**: the public `HarnessConfigLoader.load(...) ->
HarnessSpec` signature, the `HarnessSpec` dataclass shape, the typed `Harness*Error`
family, the `$file` reference resolution semantics, and — critically — the exact
content-addressed `spec_id` for any given config. The loader keeps only the two pieces
that are genuinely not declarative validation: `$file` resolution (does I/O, needs a
base path) and `spec_id` computation (deterministic SHA-256 over the canonical resolved
identity view).

---

## 2. Goals & Non-Goals

### Goals
- Replace the ~10 hand-rolled structural `_validate_*` methods and the ~3 `_normalize_*`
  methods in `config.py` with one declarative pydantic `HarnessConfigSchema`.
- Eliminate the double validation pass (today `_validate_config` runs on both the
  requested and resolved dicts).
- Keep `HarnessConfigLoader.load(source, *, base_path=None, code_version=None) ->
  HarnessSpec` byte-for-byte contract-compatible with today's behavior, including an
  **identical `spec_id`** for identical input.
- Keep the public `HarnessSpec` dataclass (`vidbyte/lib/dataclasses/harnesses.py`)
  unchanged — it is consumed by `execution.py`, `registry.py`, `dataset.py`, `client.py`.
- Preserve the typed error contract (`HarnessConfigurationError`,
  `HarnessCredentialConfigError`, `HarnessFileReferenceError`, `HarnessVersionError`):
  callers may `except` these, so pydantic's `ValidationError` is wrapped, never leaked.
- Preserve the credential-rejection security invariant over open config regions.
- Keep required CI (`python scripts/run_ci.py`) green.

### Non-Goals
- **No changes to PR #296 / `vidbyte/environments/`.** The user is handling the
  `environments.spec` / `AgentSpec` convergence separately. This PR imports nothing
  from `vidbyte/environments` and does not depend on that branch merging.
- No change to the `HarnessSpec` dataclass fields, `HarnessRun`, `TrajectoryRecord`,
  or any consumer of them.
- No change to the content-addressing algorithm, the identity view
  (`{type, version, agents, orchestration}`), or the `hspec_<sha256>` format.
- No change to the open/closed philosophy of the *config*: `agents[].params`,
  `agents[].tools` objects, `metadata`, and `orchestration` stay open leaves
  (`dict[str, Any]`). We do **not** close them into a fully typed agent schema in this PR.
- No new tests (per `/design-doc-no-tests`); existing CI must stay green.
- No conversion of `HarnessSpec` itself to a pydantic model.

---

## 3. Background & Context

PR #297 (merged into `main` on ~2026-07-14) shipped the harness execution contract.
Its `config.py` treats the harness config as an **open, untyped** document and therefore
must hand-validate everything: it walks the structure recursively to reject non-JSON
values, non-finite floats, cyclic containers, and credential-like keys, and it checks
every field shape by hand. That is ~200 lines of machinery that exists *because* the
loader chose to do validation imperatively rather than declaratively.

The user's observation (talk session, 2026-07-19): a pydantic model can absorb the bulk
of this — "load the YAML, pass it through the pydantic model, and pydantic does all of
the validation." That is correct for the **structural validation and JSON-normalization**
half. Two pieces are irreducible and stay custom:

1. **`$file` resolution** — reads a local UTF-8 file, inlines `{content, sha256}`,
   resolves relative paths against the config file's directory (or an explicit
   `base_path`). This is I/O with contextual path resolution; keeping it out of pydantic
   validators keeps the model pure.
2. **`spec_id`** — deterministic SHA-256 over canonical JSON of the resolved identity
   view, folding in the code-supplied `code_version`. This is content-addressing, not
   validation, and pydantic does not provide it.

Constraint that shapes the whole design: `spec_id` is a **content address** already
threaded through `execution.py` (`self.spec.spec_id`), `dataset.py`
(`spec.resolved_config`), and `registry.py` (`spec.harness_type` / `harness_version`).
Any drift in the hash silently forks identity and corrupts dataset/eval cardinality.
So the refactor must be provably identity-preserving.

---

## 4. Requirements

### Functional Requirements
1. `HarnessConfigLoader.load(source, *, base_path=None, code_version=None)` MUST accept
   the same inputs as today: an in-memory `Mapping`, or a `str`/`Path` to a `.json`,
   `.yaml`, or `.yml` file.
2. Structural validation MUST enforce the same rules as today:
   - required top-level keys `{schema_version, harness, agents}`; optional
     `{metadata, orchestration}`; no other top-level keys (`extra="forbid"`).
   - `schema_version` MUST equal `HARNESS_SCHEMA_VERSION` (currently `1`); a mismatch
     MUST raise `HarnessVersionError` (not a generic validation error).
   - `harness.type` MUST be a non-empty string; extra `harness` descriptor fields are
     preserved.
   - `agents` MUST be a non-empty-shaped list of objects, each with a required non-empty
     unique `name`; optional non-empty `provider`/`model` strings; optional
     `system_prompt` that is either a string or a lone `{$file: <non-empty str>}`;
     optional open `params` object; optional `tools` list whose entries are strings or
     objects.
   - `metadata` and `orchestration`, when present, MUST be objects; when absent they
     default to `{}`.
3. Any credential-like key (per `HarnessSecretPolicy.is_secret_key`) appearing anywhere
   in the config — including inside open leaves (`params`, `metadata`, `orchestration`,
   `tools` objects, extra `harness` fields) — MUST raise `HarnessCredentialConfigError`
   before the config is retained, hashed, stored, or exported.
4. Values MUST be JSON-safe: non-finite floats, non-JSON Python objects, and cyclic
   containers MUST be rejected with a typed `HarnessConfigurationError`.
5. `{$file: ...}` references MUST resolve exactly as today: relative to `base_path`
   (mapping input) or the config file's parent (file input); absolute paths honored;
   sibling keys alongside `$file` rejected; unreadable/non-file/non-UTF-8 targets raise
   `HarnessFileReferenceError`; resolved form is `{content, sha256}`.
6. The returned `HarnessSpec` MUST carry the same fields with the same values as today:
   `schema_version`, `spec_id`, `harness_type`, `harness_version`, `agents`,
   `orchestration`, `metadata`, `requested_config` (normalized, `$file` unresolved),
   `resolved_config` (`$file` resolved).
7. `spec_id` MUST be byte-identical to the pre-refactor implementation for the same
   `(config, code_version)` input.
8. `HarnessConfigLoader.canonical_json(value)` MUST remain a public method with identical
   output (`sort_keys=True`, compact separators, `ensure_ascii=False`, `allow_nan=False`).
9. `pydantic.ValidationError` MUST NOT escape `load()`; it is caught and re-raised as
   `HarnessConfigurationError` with the field context in `details`.

### Non-Functional Requirements
- **Security:** credential rejection must remain total across every retained
  representation (requested, resolved, hash input, error diagnostics). No regression.
- **Backward compatibility:** zero changes to any public import, dataclass, or error type.
- **Observability:** typed errors keep their `to_context_packet()` diagnostics and
  `details` payloads (field path, actual type, etc.).
- **Maintainability:** the "single source of truth" for config shape becomes one
  declarative schema instead of ~10 imperative methods.
- **Performance:** neutral; single validation pass replaces two, so marginally fewer
  traversals.

---

## 5. High-Level Design

Introduce `vidbyte/harnesses/schema.py` containing pydantic v2 models that declare the
harness config envelope: `HarnessConfigSchema` (top level) composing `HarnessDescriptor`
and `AgentEntry`. These models own **structural** validation (required/optional keys,
types, non-empty strings, unique agent names, `system_prompt` union, `extra="forbid"`).

`config.py` is rewritten around these models. The loader becomes a thin pipeline:

```
load(source, base_path, code_version)
  │
  ├─ _parse(source)              # mapping | .json | .yaml  →  raw dict        (kept, small)
  ├─ HarnessConfigSchema.model_validate(raw)   # structural validation        (NEW: replaces _validate_*)
  │     └─ on ValidationError → HarnessConfigurationError (wrapped)
  ├─ _reject_and_assert(dict)    # secret keys + JSON-safety + cycle guard     (kept, single merged walk)
  ├─ _resolve_files(dict, base)  # $file → {content, sha256}                   (kept, custom I/O)
  └─ _build_spec(requested, resolved, code_version)  # canonical SHA-256 id    (kept, UNCHANGED algorithm)
        └─ returns HarnessSpec dataclass (UNCHANGED shape)
```

Key design decisions:

- **Pydantic is a validator + normalizer, not the output type.** The public output stays
  the frozen `HarnessSpec` dataclass. `model_validate(...).model_dump(mode="json")` yields
  the normalized JSON-safe requested dict (replacing `_normalize_*`); the dict pipeline
  after that point is unchanged, which is what guarantees `spec_id` stability.
- **Open leaves stay open.** `params`, `tools` object entries, `metadata`, `orchestration`,
  and extra `harness` descriptor fields are typed as `dict[str, Any]` / permissive unions.
  This preserves the "YAML is a forward-compatible single source of truth" property —
  new harness knobs do not require an SDK release.
- **The credential scan survives, scoped to what pydantic cannot see.** `extra="forbid"`
  rejects undeclared keys at the *structured* levels for free, but open leaves can still
  contain `{api_key: ...}`. One retained recursive walk enforces the secret-key invariant
  plus JSON-safety (non-finite / non-JSON / cycle) over the whole validated document. This
  is the single most security-sensitive line of code in the module and is preserved
  behaviorally, not rewritten.
- **`spec_id` and `$file` are untouched in spirit.** Their code moves verbatim (modulo
  the surrounding pipeline) so the content address and reference semantics cannot drift.

What this deletes: `_validate_config`, `_validate_top_level_keys`,
`_validate_schema_version`, `_validate_harness`, `_validate_agents`, `_validate_agent`,
`_validate_system_prompt`, `_validate_tools`, `_validate_object_field`, `_required_text`
(structural validation → pydantic), and `_normalize_mapping`/`_normalize_value`/
`_normalize_sequence` (→ `model_dump(mode="json")` + the retained safety walk).

What this keeps: the parse dispatch, the `$file` resolver family, the credential/safety
walk (merged), `_build_spec`, and `canonical_json`.

---

## 6. Detailed Design

### 6.1 HarnessConfigSchema (and sub-models)

**File(s):** `vidbyte/harnesses/schema.py`
**Type:** New file

#### What it does
Declares the harness config envelope as pydantic v2 models so structural validation is
declarative. Owns *only* shape validation; no I/O, no hashing, no `$file` resolution.

#### Interface / API
```python
class HarnessDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")   # extra descriptor fields preserved
    type: str = Field(min_length=1)

class AgentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    system_prompt: str | FileReference | None = None   # FileReference = {"$file": non-empty str}
    params: dict[str, Any] = Field(default_factory=dict)
    tools: tuple[str | dict[str, Any], ...] | None = None

class HarnessConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    harness: HarnessDescriptor
    agents: tuple[AgentEntry, ...] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    orchestration: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_schema_version_and_unique_agents(self) -> "HarnessConfigSchema": ...
```

#### Logic / Algorithm
1. `schema_version` typed as `int`; `bool` is rejected (pydantic v2 does not coerce `bool`
   into `int` under strict field typing — confirm during impl; if needed, a
   `field_validator` rejects `bool` explicitly to match `isinstance(version, bool)` today).
2. `model_validator(mode="after")` raises `HarnessVersionError` when
   `schema_version != HARNESS_SCHEMA_VERSION`, and raises `HarnessConfigurationError`
   on duplicate agent `name`s — mirroring today's messages and `details`.
3. `system_prompt` union accepts a plain string or a `FileReference` model whose only
   field is `$file` (aliased) and which forbids siblings, matching `_validate_system_prompt`.
4. `str` fields carry `min_length=1`; whitespace-only strings are normalized/rejected via
   a shared `field_validator` that reproduces `_required_text`'s `.strip()` semantics.

#### Edge Cases & Error Handling
- Unknown top-level or agent key → pydantic `ValidationError` → wrapped as
  `HarnessConfigurationError` in `load()` with `details={"unknown": [...], ...}` shape
  reconstructed from the error.
- `harness` extra fields (e.g. a descriptor `label`) are preserved via `extra="allow"`.
- Empty `agents` → `min_length=1` violation → wrapped.
- Because the models are used for validation and immediately dumped, `frozen` is not
  required; we set `extra` policy per model as above.

### 6.2 HarnessConfigLoader (rewrite)

**File(s):** `vidbyte/harnesses/config.py`
**Type:** Modified (major internal rewrite; public API unchanged)

#### What it does
Parses a config source, validates it via `HarnessConfigSchema`, enforces the
credential/JSON-safety invariant, resolves `$file` references, and builds the immutable
content-addressed `HarnessSpec`. Public methods and their signatures are unchanged.

#### Interface / API
```python
class HarnessConfigLoader:
    def load(self, source: Mapping[str, Any] | str | Path, *, base_path: str | Path | None = None, code_version: str | None = None) -> HarnessSpec: ...
    def canonical_json(self, value: Mapping[str, Any]) -> str: ...   # UNCHANGED
```

#### Logic / Algorithm
`load`:
1. `parsed, base = self._parse_source(source, base_path)` — dispatch mapping vs file;
   file dispatch reads UTF-8, parses JSON or `yaml.safe_load`, requires an object,
   derives `base` from the file's parent. (Consolidates today's `_load_source`,
   `_load_path`, `_read_config_text`, `_parse_config_text`.)
2. `requested = self._validate_structure(parsed)` — call
   `HarnessConfigSchema.model_validate(parsed)`, catch `ValidationError` → raise
   `HarnessConfigurationError`/`HarnessVersionError` (the validator raises the typed one
   directly; only shape/type failures are wrapped). Return `model.model_dump(mode="json")`
   as the normalized requested dict.
3. `self._assert_safe_and_secret_free(requested)` — single recursive walk: reject
   credential-like keys (`HarnessCredentialConfigError`), non-finite floats / non-JSON
   values (`HarnessConfigurationError`), and cyclic containers. Uses the retained
   `_enter_container` cycle guard and `HarnessSecretPolicy.is_secret_key`.
4. `resolved = self._resolve_files(requested, base)` — the retained `$file` resolver
   family, unchanged.
5. `return self._build_spec(requested, resolved, code_version)` — unchanged: canonical
   identity view `{type, version, agents, orchestration}`, `hspec_<sha256>`, and the
   `HarnessSpec(...)` dataclass construction.

`canonical_json`: unchanged.

#### Edge Cases & Error Handling
- Mapping input containing a cycle inside an open leaf (`params`) survives pydantic
  (leaves are `Any`) and is caught by the step-3 walk — preserving today's guarantee.
- Non-finite float inside an open leaf: caught in step 3; also independently guarded by
  `canonical_json(allow_nan=False)` at hash time. Error site is step 3, matching today.
- `code_version` folding into `spec_id` is unchanged.

### 6.3 Errors, serialization, dataclasses — unchanged

**File(s):** `vidbyte/harnesses/errors.py`, `serialization.py`,
`vidbyte/lib/dataclasses/harnesses.py`
**Type:** Unchanged

The typed `Harness*Error` family is a deliberate public contract and is preserved as-is;
only the *raise sites* consolidate. `HarnessSecretPolicy` (serialization.py) stays the
shared secret predicate. The `HarnessSpec` dataclass is untouched.

### 6.4 Caller compatibility — no changes required

**File(s):** `vidbyte/harnesses/client.py`, `execution.py`, `dataset.py`, `registry.py`
**Type:** Unchanged

All four consume only the preserved surface (`load(...)`, `spec_id`, `harness_type`,
`harness_version`, `resolved_config`). No edits expected; verified during self-review.

---

## 7. Data Model Changes

N/A — no persisted schema changes. The in-memory `HarnessSpec` dataclass and its
`spec_id` content address are explicitly preserved byte-for-byte.

---

## 8. API Changes

N/A — no HTTP/RPC API. The only "API" is the Python surface
`HarnessConfigLoader.load()` / `canonical_json()`, which is contract-preserved.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/harnesses/schema.py` | Declarative pydantic v2 config schema (`HarnessConfigSchema`, `HarnessDescriptor`, `AgentEntry`, `FileReference`) replacing hand-rolled structural validation. |
| MODIFY | `vidbyte/harnesses/config.py` | Rewrite `HarnessConfigLoader` to parse → `model_validate` → safety/secret walk → `$file` resolve → build spec. Delete ~10 `_validate_*` and 3 `_normalize_*` methods; keep `$file`, `_build_spec`, `canonical_json`, cycle guard. |
| MODIFY | `docs/design/harness-config-pydantic-loader.md` | This design doc (committed first). |

No changes to `errors.py`, `serialization.py`, `stores/`, `execution.py`, `registry.py`,
`dataset.py`, `client.py`, or `vidbyte/lib/dataclasses/harnesses.py`.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `pydantic` | `>=2,<3` (already in `pyproject.toml`) | Declarative validation | None — already a core dependency used across `main`. |
| `PyYAML` | `>=6,<7` (already present) | Safe YAML parsing | None — retained, unchanged usage. |

No new dependencies.

---

## 11. Rollout & Deployment

- **Feature flags:** none. Pure internal refactor behind a stable public API.
- **Breaking change:** none intended. The refactor is validated by an identity check
  (Section 4, req. 7): representative configs must yield an identical `spec_id`
  pre/post-refactor.
- **Deployment order:** single package; no cross-service coordination.
- **Rollback:** revert the PR; no state or schema migration involved.

---

## 12. Open Questions

- [ ] **`bool`-as-`schema_version` rejection.** Today `isinstance(version, bool)` is
      explicitly rejected. Confirm pydantic v2's `int` field rejects `True`/`False`
      under our config; if it coerces, add a `field_validator` to match. (Assumption:
      add the explicit validator to be safe.)
- [ ] **`model_dump(mode="json")` vs. retaining `_normalize_*`.** Design assumes the
      json dump reproduces today's normalized dict exactly (str keys, lists, JSON scalars)
      so `spec_id` is stable. If the identity check reveals any drift (e.g. int/float
      coercion in an open leaf), fall back to retaining a minimal `_normalize_*` pass and
      use pydantic purely as a gate. The identity check in Section 4 req. 7 is the gate
      that decides this.
- [ ] **`harness` descriptor openness.** Design keeps `extra="allow"` on `HarnessDescriptor`
      to preserve today's "keep additional descriptor fields" behavior. Confirm no secret
      key can hide there — the step-3 secret walk covers it, so this is safe, but worth a
      conscious sign-off.

---

## 13. Alternatives Considered

### Alternative 1: Convert `HarnessSpec` itself to a pydantic model
- What: Make the output `HarnessSpec` a pydantic `BaseModel` with a `@computed_field`
  `spec_id`, instead of a frozen dataclass.
- Why rejected: `HarnessSpec` is a **merged public contract** re-exported from `vidbyte`
  and consumed by four modules; changing its type risks downstream breakage and touches
  `lib/dataclasses/harnesses.py` for no functional gain. Keeping it a dataclass gives the
  minimal blast radius the "simple and minimalistic" ask calls for.

### Alternative 2: Adopt PR #296's `environments/spec.py` `HarnessSpec` as the per-agent type
- What: Import #296's typed `AgentSpec`/`HarnessSpec` and make `agents[]` fully typed.
- Why rejected (for this PR): #296 is an unmerged draft the user is handling separately;
  depending on it couples this refactor to another branch and closes the open-config
  property. Convergence is a deliberate follow-up, noted as a Non-Goal here.

### Alternative 3: Inline the pydantic models inside `config.py`
- What: Define `HarnessConfigSchema` in `config.py` rather than a new `schema.py`.
- Why rejected: `config.py`'s file header scopes it to loading/resolving/fingerprinting;
  a dedicated `schema.py` keeps the declarative shape separable and matches the repo's
  one-concern-per-file convention (e.g. `lib/dataclasses/*`). Low cost, cleaner seam.

### Alternative 4: Do `$file` resolution inside a pydantic `mode="before"` validator
- What: Resolve references declaratively via validation context (`base_path`).
- Why rejected: puts filesystem I/O inside the validation layer and threads `base_path`
  through validation context — a smell that couples pure validation to the environment.
  Keeping `$file` as an explicit pipeline step is clearer and keeps the model pure.

---

## CI Command (recorded per workflow)

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

Identity verification (added to the PR's smoke evidence, not a new test file): load a
representative multi-agent config with a `$file` prompt through both the pre- and
post-refactor loader and assert `spec_id` is byte-identical.

END OF DESIGN DOC
