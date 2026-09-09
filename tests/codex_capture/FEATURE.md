# Observed Codex trajectory capture

Opted-in capture writes the existing TrajectoryRecord format to an existing
TrajectorySink. Required storage acknowledgment precedes history publication.
Records state observed-only scope, omitted native internals, and window truncation;
they do not pretend to be resumable Session checkpoints or invent rewards.

Tests cover actual file JSONL export, mandatory redaction, process-secret exclusion,
empty values, bounded windows, snapshot isolation, required/optional sink failures,
timeout, one-write semantics, original failure/cancellation preservation, rejected
candidate evidence, and independent fork/run IDs. Native execution is mocked;
paid model/training calls, browser tests, and crash-recovery guarantees are omitted.

Run `python scripts/test-codex-trajectory-capture.py` for every design case.
