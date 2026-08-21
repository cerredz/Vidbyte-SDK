<!--
Context Protocol Header

Description:
    Development rules for the Vidbyte SDK harness execution contract.
Purpose:
    Keeps future harness config loading, identity, execution, registry, trajectory
    collection, sinks, and redaction aligned with the reviewed package structure and
    the consent/redaction boundary.
Architecture:
    - Documents file placement, the Harness contract, config schema, identity model,
      persistence surfaces, the sink port, the registry, and verification.
Relations:
    Complements skills/sdk/SKILL.md, skills/sessions.md, and vidbyte/harnesses/.
-->

# Harness Execution Contract Skill

Use this skill when adding or changing `vidbyte/harnesses/`. The package is the
reusable outer envelope around an arbitrary harness: it owns configuration identity,
durable capture, and consented trajectory export, and it deliberately owns no agent
loop, topology, retry strategy, or reasoning algorithm.

## Package Placement

- Put the `Harness` base class and `wrap_implementation` in `vidbyte/harnesses/execution.py`.
- Put the config loader, `$file` resolution, credential rejection, and `spec_id`
  computation in `vidbyte/harnesses/config.py`.
- Put the `TrajectoryCollector` (Session fan-in join) in `vidbyte/harnesses/dataset.py`.
- Put the single redaction pass and the shared `HarnessSecretPolicy` in
  `vidbyte/harnesses/serialization.py`.
- Put the `HarnessImplementation`/`HarnessFactory` protocols and `HarnessRegistry` in
  `vidbyte/harnesses/registry.py`.
- Put the `TrajectorySink` port in `vidbyte/harnesses/stores/base.py` and each concrete
  sink in its own file under `vidbyte/harnesses/stores/` (`memory.py`, `file.py`),
  mirroring `vidbyte/sessions/stores/`. Do not reintroduce a flat `sinks.py`.
- Put the `sdk.harnesses` client (store/sink constructors, foreign-implementation and
  config-only load, the retained `sessions` namespace) in `vidbyte/harnesses/client.py`.
- Re-export contract dataclasses through `vidbyte/harnesses/contracts.py`; keep their
  definitions central in `vidbyte/lib/dataclasses/harnesses.py`.
- Keep `vidbyte/harnesses/__init__.py` an export shim only: no client construction,
  backend creation, config parsing, or execution at import time.

## The Harness Contract

A concrete harness subclasses `Harness` and provides:

- `type` (ClassVar): matches the config `harness.type`.
- `version` (ClassVar): code identity, folded into `spec_id`. It is NOT a YAML field.
- `async run(request) -> Any`: the orchestration. Use `self.session(agent)` to capture
  agents. May be sync or async.
- `async score(request, output) -> float | None` (optional): an eval reward stored on
  the trajectory record.
- `async after_execute(request, output, status, error) -> None` (optional): fail-open
  cleanup after every terminal `execute()` status, including `FAILED`, `TIMED_OUT`,
  and `CANCELLED`. Must not raise; the envelope swallows exceptions. `error` is set
  on non-success paths and `None` on `SUCCEEDED`.

Do not add an agent loop, topology, retry, or timeout policy to the base class beyond
the existing lifecycle. Do not make one `Harness` instance concurrently reentrant; it
holds one `run_id` at a time — use a fresh instance per concurrent execution.

## Config Schema (source of truth)

- Top-level keys: `schema_version`, `harness`, `agents` (required); `metadata`,
  `orchestration` (optional). There is no top-level `params` array.
- Per-agent `params`/`tools` live on each agent; between-agent knobs live under
  `orchestration`.
- `{ $file: path }` inlines an external file (resolve before identity is computed).
- Reject credential-like keys anywhere in the config (`HarnessSecretPolicy.is_secret_key`)
  before hashing or persistence. Credentials belong in provider/env injection.
- `HarnessConfigLoader.load` accepts a typed mapping, a JSON path, or a safe-YAML path
  (`yaml.safe_load` only — never `yaml.load`).

## Identity Model

Keep three identities distinct:

- Implementation: `harness.type` + code `version`.
- Configuration: `spec_id = hspec_<sha256>` over the canonical resolved config. It must
  be key-order-independent; changing any resolved value (prompt-file content, an agent
  param, the code `version`) changes it, while `metadata`, store/sink choice, and
  timestamps do not.
- Execution: a unique `run_id = hrun_<uuid>` per `execute()`.

## Persistence Surfaces (keep them distinct)

- Operational source of truth: `vidbyte.sessions` `SessionStore`. `self.session(agent)`
  returns a durable Session with per-step checkpoints, full trace, and the `run_id` tag.
  Reuse Sessions; never build a second capture/store system here.
- Licensed, redacted export: a `TrajectorySink`. This is a separate write-only port so
  the consent/redaction boundary stays sharp. Point the operational store and the export
  sink at different destinations.

Sinks are NOT SessionStores: the SessionStore is typed to the agent checkpoint domain
(`Checkpoint`/`RunState`), so do not adapt a `TrajectoryRecord` through it.

## Collection Rules

- Collection is opt-in: only when constructed with `collect=True` and a bound `sink`.
- `TrajectoryCollector` fans in every Session tagged with the `run_id`, inlines the
  resolved spec, and applies the single redaction pass. It never mutates checkpoints and
  never infers messages, rewards, or splits.
- Collection is fail-open: any sink/redaction/scoring error is swallowed inside
  `execute()` so it can never fail the run.

## Registry Rules

- Registration is client-local, optional, and exact `(type, version)`.
- No dynamic import from config paths; `harness.type` is a lookup key only.
- No silent duplicate replacement; raise `HarnessDuplicateRegistrationError`.
- No latest-version fallback; config-only `resolve_for_type` requires exactly one
  registered version for a type.
- Deepcopy the spec into `factory.create(spec)` and reject a factory that mutates it.

## Errors

Use the typed families in `vidbyte/harnesses/errors.py`: `HarnessConfigurationError`
(and `HarnessCredentialConfigError`, `HarnessVersionError`, `HarnessFileReferenceError`)
before/at load; `HarnessExecutionError`/`HarnessTimeoutError` at run; `HarnessSinkError`
for sink I/O; `HarnessRegistrationError`/`HarnessDuplicateRegistrationError` for the
registry. Keep every public error re-exported from the package `__init__`.

## Verification

Run these checks after harness changes:

```bash
python -c "from vidbyte import Harness, HarnessSpec, HarnessExecutionResult, TrajectorySink, InMemoryTrajectorySink, FileTrajectorySink, HARNESS_SCHEMA_VERSION; print('ok', HARNESS_SCHEMA_VERSION)"
python -m compileall vidbyte/harnesses
```
