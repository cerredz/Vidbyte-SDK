# `vidbyte/procedures`

## Folder Description / Intent

This folder owns Vidbyte's reusable, cross-run procedure memory. It exists so a
successful run can stage a bounded procedure candidate, prove that candidate
against task, drift, and fidelity evidence, and later retrieve only the active
compatible verified version. The package optimizes for auditable learning:
immutable versions and compact retrieval cards make every reuse traceable to the
exact content that was verified.

The package separates lifecycle policy from storage. `ProcedureLibrary` is the
only supported service for staging, promotion, rejection, normal retrieval,
outcome accounting, and retirement. Store adapters preserve audit records but
are trusted application infrastructure, not an authorization boundary or a
tamper-proof database.

This folder is not a task controller, vector database, or arbitrary conversation
memory. Long-running planning, retries, drift control, and promotion authority
belong in `vidbyte/paradigms/long_running`; model-callable adapters belong in
`vidbyte/tools/builtins/procedures`.

## Blast Radius

The namespace is exported from the root `vidbyte` package and consumed by the
long-running paradigm and procedure tools. Changes to active-head derivation,
fingerprinting, compatibility checks, or outcome version pinning can change what
future agents learn and reuse.

## Non-Goals

- Do not add task DAG scheduling; orchestration belongs in `vidbyte/paradigms/long_running`.
- Do not add model-agent construction or prompt rendering; those belong in `vidbyte/paradigms` and `vidbyte/prompts`.
- Do not expose promotion as a model-callable tool; trusted controller code owns authorization.
- Do not add arbitrary semantic/vector provider dependencies; inject a `ProcedureRanker` instead.
- Do not store raw conversation history as reusable procedure content; bounded public evidence belongs in the run ledger.
- Do not treat content hashes as verification or authorization; they identify exact normalized content only.
- Do not infer active state from the numerically latest audit record; use the library's chain reduction.
- Do not claim file-store multi-writer or distributed-transaction safety; the reference file backend allows one writer process.

## File Index

- `__init__.py` - Re-exports the supported public procedure surface. Open this when a caller-facing contract or backend becomes stable.
- `contracts.py` - Defines frozen candidate, record, verification, retrieval, ref, and outcome shapes. Open this for public data changes, not lifecycle algorithms.
- `errors.py` - Defines typed repair-oriented failures with safe context packets. Open this when a distinct invariant needs its own failure type.
- `library.py` - Owns lifecycle commands, active-head queries, lexical ranking, compatibility, deduplication, exact outcomes, and retirement. Open this for behavior policy.
- `serialization.py` - Owns schema-v1 JSON, canonical content fingerprints, timestamps, and safe deterministic ids. Open this for durable shape changes.
- `store.py` - Defines the trusted append-only `ProcedureStore` protocol. Open this before implementing a new backend.
- `stores/__init__.py` - Exports reference backends without performing I/O.
- `stores/memory.py` - Provides thread-safe ephemeral storage for local and small runs.
- `stores/file.py` - Provides inspectable atomic JSON persistence with root containment and one-writer-process enforcement.

## Logs

- 2026-07-14 - Separated latest audit records from derived active verified heads - prevents candidates and rejections from hiding the last reusable procedure.
- 2026-07-14 - Pinned every outcome to version plus fingerprint - prevents failures from compounding against a later replacement procedure.
