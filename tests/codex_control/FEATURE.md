# Native live control

When a native turn starts, a configured callback receives its own control handle.
Steering and interruption invoke actual SDK operations; stale handles and invalid
acknowledgments cannot report success. Feedback is supplemental text, not an
arbitrary replacement of Codex-owned context.

The pack uses real generated acknowledgment models and offline SDK seams to cover
invalid input, identity mismatch, exceptions, timeout, cancellation, command
serialization, late responses, terminal observer ordering, and fork propagation.
Paid model calls and timing benchmarks are omitted: the promise is native request
routing and lifecycle enforcement, not deterministic next-action timing.

Run `python scripts/test-codex-live-control.py` for all design cases.
