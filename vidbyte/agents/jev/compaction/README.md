# Jev dynamic compaction

This package implements JevAgent's dynamic compaction. Jev recognizes when the agent turns from one unit of work to the next. Code tracks those units, and once finished units together hold enough tokens to be worth one cache miss, it replaces each one in the canonical message history with a short written record.

Users turn it on with one flag per trigger:

```python
JevAgentSettings(..., dynamic_compaction=JevDynamicCompactionSettings(unit_of_work=True))
```

Each pass through the loop does three things:

1. The ledger records which messages the latest iteration added.
2. Every enabled trigger contributes state fields and questions to one batched Jev request. A boundary splits the ledger before the latest step.
3. Once eligible closed units (all but the newest) reclaim at least `min_reclaim_tokens`, each one is replaced by one `user` record message. `JevDynamicCompaction` writes the record with the main agent's model, or falls back to a deterministic record if that fails.

To add a trigger:

1. Subclass `JevCompactionTrigger`.
2. Add a `JevCompactionTriggerKey` member and a matching boolean on `JevDynamicCompactionSettings`.
3. Register the class in `JEV_COMPACTION_TRIGGERS`.

Write its question with `skills/asking-jev-questions/SKILL.md`. The ledger, the policy, and the writer do not change.

See `docs/design/jev-dynamic-compaction.md`.

## File Index

- `__init__.py`: public exports of the capability.
- `agent.py`: `JevDynamicCompaction`, which runs the boundary question, the compaction policy, and the record writer.
- `ledger.py`: `JevUnitLedger` and `JevWorkUnit`, which map messages to iterations and units and splice records in.
- `report.py`: `JevCompactionRun` (run-local state) and the frozen `JevCompactionReport`.
- `steps.py`: `JevRunStep` collection and rendering for Jev, the writer, and the fallback record.
- `triggers.py`: the `JevCompactionTrigger` contract and `JevUnitOfWorkTrigger` with its fixed Jev question.
