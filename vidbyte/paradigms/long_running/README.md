# Long-running paradigm

This package implements a durable, sequential task-DAG harness for broad goals that
cannot safely live in one model context. It decomposes the exact caller contract,
runs each attempt in a fresh bounded context, independently verifies results, audits
global drift, and saves only fidelity-checked successful procedures for later runs.

## Use

```python
from vidbyte import LongRunningParadigm, LongRunningRunOptions

harness = LongRunningParadigm()
result = harness.run(
    "Complete the repository migration and document the result.",
    run_options=LongRunningRunOptions(
        success_criteria=("The migration is complete and evidenced.",),
        invariants=("Do not weaken existing security boundaries.",),
    ),
)
```

Use `await harness.aresume(result.run_id)` (or `harness.resume(...)` outside an
event loop) when a bounded result is resumable. A file-backed `RunLedgerStore` is
required for process-restart durability; the default in-memory store supports only
same-process resume.

## Execution model

1. The planner produces a validated dependency DAG.
2. The scheduler selects one ready task.
3. A fresh worker or repairer receives the exact contract/current task, compact
   verified dependency and procedure cards, and bounded one-item expansion tools.
4. A separate read-only verifier and configured deterministic validators decide
   whether the attempt passes.
5. A global auditor detects drift and explicitly invalidates downstream work.
6. Only aligned successful work may stage and independently verify a reusable
   procedure. Promotion is reauthorized against the active append-only ledger.
7. A fresh synthesizer produces the final answer and a final audit gates COMPLETED.

`VERIFIED` means the configured model and deterministic gates passed; it is not a
mathematical guarantee. Add deterministic `TaskValidator` and `ProcedureValidator`
implementations for commands, schemas, external state, or domain assertions that
must be checked independently.

## Persistence and safety

- `FileRunLedgerStore` uses event-envelope-first commits and validated replay.
- `FileProcedureStore` stores append-only candidate/version/outcome records.
- Resume fingerprints settings, prompts, tools, middleware, validators, stores, and
  isolators; behavior changes require explicit typed authorization.
- Worker execute/write tools are off by default. Non-read tools require an
  `AttemptIsolator` unless `unsafe_allow_unisolated_side_effects=True` is explicitly
  chosen. The unsafe flag permits starting work but never permits continuing after a
  rejected or interrupted unrolled-back side effect.
- Full transcripts stay in the ledger. Models see compact projections, and procedure
  or verified dependency bodies enter only through bounded role-local load tools.

## Package map

- `controller.py`: finite durable state machine.
- `context.py`: fresh role contexts and verified-context resolver.
- `planning.py`: graph validation, scheduling, and reconciliation.
- `execution.py`: worker/repair attempts and isolation leases.
- `verification.py`: task/final verification, drift, procedure learning.
- `ledger.py`: codecs, behavior fingerprints, stores, replay facade.
- `types.py`: public immutable contracts and settings.

The complete architecture and edge-case contract lives in
`docs/design/long-running-paradigm.md`.
