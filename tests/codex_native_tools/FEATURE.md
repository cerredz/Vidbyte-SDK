# Native Codex tool enforcement

When a fresh Codex thread requests a registered Vidbyte function, the native
response waits for ToolExecutor permission checks, validation, and execution.
The original bound tool instance receives the call on its owning asyncio loop.

The acceptance pack covers registration schemas and input modalities, permission
denials, invalid routing, duplicate delivery, tool failures, timeouts, cancellation,
native cleanup, and unsupported resume/fork rejection. It uses the real executor
and pinned SDK models with an offline client seam. This catches protocol mapping
and policy regressions without depending on a model choosing a particular tool.

Run `python scripts/test-codex-native-tools.py` for named results. Paid model calls,
browser tests, and throughput benchmarks are omitted: this feature promises an
execution boundary, not model selection reliability or browser behavior.

Known limits: built-in Codex tools bypass this dispatcher; thread resume and forks
cannot yet verify dynamic registration. Cancellation cannot undo prior tool effects.
