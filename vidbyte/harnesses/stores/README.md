# `vidbyte.harnesses.stores`

## Folder Description / Intent

This folder contains local reference implementations of the public
`HarnessStore` contract. It exists so a harness can accumulate canonical
specifications, runs, and ordered events without adopting a hosted service or
writing a database adapter. The folder optimizes for zero-configuration local
development, inspectable persistence, and exact agreement with the shared store
invariants.

The stores here are persistence mechanisms, not harness algorithms. They do not
construct agents, interpret `params`, execute implementations, derive rewards,
or decide what counts as a useful dataset. Those responsibilities belong to the
loader/execution/dataset modules in `vidbyte.harnesses` or to concrete algorithms
in `vidbyte.paradigms`.

## Blast Radius

These stores are constructed through `HarnessClient.memory_store()` and
`HarnessClient.file_store()` and can be imported directly by SDK consumers.
Changes affect run durability, event ordering, dataset export, public root
imports, and any closed-repo adapter that treats these implementations as the
reference semantics for `HarnessStore`.

## Non-Goals

- Do not add harness orchestration or agent construction; concrete algorithms belong in `vidbyte.paradigms` or external implementations.
- Do not parse JSON/YAML behavior configuration; `vidbyte/harnesses/config.py` owns loading and identity.
- Do not add execution lifecycle branching; `vidbyte/harnesses/execution.py` owns success, failure, timeout, and cancellation paths.
- Do not redefine contracts or serializer payload shapes; those belong in `vidbyte/lib/dataclasses/harnesses.py` and `vidbyte/harnesses/serialization.py`.
- Do not add Session checkpoint or resume behavior; durable threads belong in `vidbyte.sessions`.
- Do not add provider-specific model, trace, or tool behavior; those belong in `vidbyte.providers`, `vidbyte.trace`, and `vidbyte.tools`.
- Do not materialize SFT, RL, preference, or eval schemas; raw dataset projection belongs in `vidbyte/harnesses/dataset.py`.
- Do not silently delete, prune, migrate, or repair caller-owned run data; retention and migrations require explicit public contracts.
- Do not place hosted/private Vidbyte database access here; closed service adapters remain outside the public SDK.

## File Index

- `README.md` - This comprehension cache defines why local stores exist and where adjacent responsibilities belong. Read it before adding a backend so the new code does not absorb config, execution, or dataset behavior. Update the index and append one concise log entry whenever the folder contract changes.
- `__init__.py` - Re-exports the local in-memory and filesystem implementations. Open it when a new local store is ready for public import. Keep it dependency-light so importing `vidbyte.harnesses` never opens files or databases.
- `memory.py` - Implements the process-local reference store over dictionaries while inheriting shared validation from `BaseHarnessStore`. Open it when debugging default SDK behavior or backend-independent store semantics. It is ephemeral by design and must not pretend to be durable across processes.
- `file.py` - Implements inspectable local durability with versioned JSON snapshots and JSONL events. Open it for atomic-write, path-safety, corruption, or local persistence behavior. It is the canonical local durable example, not a multi-process database substitute.

## Logs

- 2026-07-12 - Created local store package around the shared async contract - keeps backend code separate from harness algorithms and Session checkpoints.
- 2026-07-12 - Documented single-process filesystem semantics - prevents future callers from assuming JSONL append is a distributed concurrency mechanism.
