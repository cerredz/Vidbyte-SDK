# Vidbyte-to-Codex translation map

Reviewed 2026-09-05 against the [baseline](sources.md#implementation-baseline). This file contains **proposed designs**, not classes that callers can import today. The checkbox state lives only in [checklist.md](checklist.md).

## Translation fidelity

- **Exact/native:** preserve the documented provider operation and its scope.
- **Policy mapping:** similar intent, but the provider's enforcement/lifecycle differs; document that difference.
- **Boundary emulation:** Vidbyte implements behavior around native turns, not inside the native loop.
- **Unsupported:** no reliable matching control; reject the requested contract or explicitly choose a different behavior with the caller.

A type with a similar name is not evidence of matching behavior. In particular, a turn can contain many model/tool iterations, a completion event arrives too late to prevent its action, and a native thread is not a Vidbyte checkpoint DAG.

## Existing abstractions and proposed seams

All locations below are relative to the repository root. They identify real existing types/domains; all suggested Codex collaborator names are new proposals unless explicitly described as extensions.

| Existing Vidbyte abstraction and location | Tasks | Proposed translation | What must be proven |
|---|---|---|---|
| AgentInput / AgentMessage / AgentCard — `vidbyte/lib/dataclasses/agents.py` | C05, R01-R05, V01 | New input/binding and event translators around CodexRunInput and the existing typed result envelope | Main's AgentInput carries prompt, metadata, context items, and ContextManager; media requires a separately defined bridge. AgentCard metadata is not capability enforcement. |
| ContextManager and ContextItem — `vidbyte/context/` | X01-X05 | Extend CodexContextTranslator with revision/provenance accounting and a native compaction controller | Replacing local context is not equivalent to deleting already-persisted native history. Preserve documented placement and identify emulated placement. |
| ContextWindowAlgorithm / compaction middleware — `vidbyte/context/algorithms/`, `vidbyte/middleware/compaction/` | X04, H04 | Policy mapping to native compaction requests and hooks | Never claim the Vidbyte pruning algorithm controls every internal Codex model request. Completion and resulting state must be observed. |
| Prompts — `vidbyte/prompts/` | X03, G01-G05 | Resolve prompt assets into existing instruction/context translation with provenance | Base/developer instructions, discovered AGENTS.md, and user input have different scopes. Avoid duplicate instruction injection. |
| Source / DocumentSource / LlmsTxtSource — `vidbyte/sources/` | X02, M05 | Convert selected artifacts into bounded ContextItems or MCP resources | Preserve source identity, selection, and trust; loading documentation does not grant it instruction authority. |
| Tools / BaseTool / ToolSpec — `vidbyte/tools/` | U01-U04 | Proposed CodexToolTranslator backed by Vidbyte's outbound MCP server or a gated dynamic-tool dispatcher | Tool descriptions alone cannot execute Python. Validate arguments, permissions, call IDs, results, and cleanup. |
| MCP declarations — `vidbyte/lib/dataclasses/mcp.py`, `vidbyte/tools/mcp/` | M01-M05 | Proposed CodexMcpTranslator for Codex-hosted server connections | Vidbyte's inbound MCP client is not automatically the client used by Codex. Translate the declaration and own each distinct connection correctly. |
| ToolSettings / ToolErrorPolicy — `vidbyte/agents/settings/` | U04, B03-B05 | Native config plus callback-execution policy where supported | Provider-owned built-ins do not automatically obey Vidbyte's local executor. Dependencies, concurrency, and retries need real interception. |
| Permission models / sandbox contracts — `vidbyte/tools/security/`, `vidbyte/lib/dataclasses/security.py`, `vidbyte/lib/dataclasses/sandbox.py` | P01-P05 | Proposed CodexPermissionTranslator and approval router | Preserve the stricter effective restriction and identify the enforcing process. A host callback may execute outside the native sandbox. |
| AgentMiddleware / MiddlewareContext / MiddlewareDecision — `vidbyte/middleware/base.py`, `vidbyte/lib/dataclasses/middleware.py` | H01-H05 | Proposed CodexHookTranslator plus outer before/after-run hooks | Map each hook independently. Native hook trust/failure semantics may not satisfy `fail_closed=True`. |
| AgentLoopSettings — `vidbyte/agents/settings/loop.py` | B01-B02, U04-U05, X04 | Proposed CodexRunPolicy for deadlines, admission checks, and supported native limits | Distinguish max_iterations, max_tokens, max_tool_calls, max_retries, parallelism, and contract rejection counts; no universal one-to-one translation. |
| OutputContract / output-schema formatter — `vidbyte/agents/contracts/`, `vidbyte/providers/output_schema.py` | U05, T05 | Extend existing schema translation and post-run validation; optional native Stop hook where semantics fit | A valid JSON object does not prove required tools ran. Rejection/retry is a new native turn and consumes work. |
| AgentFallbackSettings — `vidbyte/agents/settings/fallback.py` | B05 | Recovery coordinator at safe native turn/thread boundaries | Preserve native history and failure provenance; swapping provider models does not establish cross-provider thread portability. |
| Session / SessionStore / CheckpointPolicy — `vidbyte/sessions/` | D01-D05 | Proposed CodexSessionAdapter with explicit export/restore | PR #409 explicitly disables session persistence. Provider rollout availability and Vidbyte checkpoint state both matter. |
| AgentForkSettings and native CodexFork — shared agent records and PR #409 | F01-F05 | Extend the existing CodexFork collaborator; add external workspace isolation separately | Parent checkpoint, selected turn, inherited policy, copied context, and file workspace are independent decisions. |
| TraceOption / TracerBase — `vidbyte/lib/dataclasses/trace.py`, `vidbyte/lib/tracing/` | O01, O05 | Proposed CodexTraceTranslator | Trace identities and parent spans survive concurrent turns; no raw private reasoning or secret-bearing payloads. |
| UsageTracker — `vidbyte/agents/pricing/tracker.py` | O02-O03, B02 | Proposed CodexUsageTranslator | Deduplicate cumulative usage, distinguish absent from zero, and label estimated cost versus authoritative billing. |
| AgentSpeedTracker — `vidbyte/agents/speed/tracker.py` | O04 | Event-derived timing bridge | Native startup, first text, tool time, and end-to-end latency are separately measured; avoid inventing unavailable internal metrics. |
| FailureRouter / FailureCode — `vidbyte/sessions/failure/`, `vidbyte/lib/enums/failure.py` | B03-B05 | Extend existing Codex failure vocabulary and operation context | Preserve cause and cancellation; distinguish a confirmed failure from an unknown completion after disconnect. |
| Skills / SkillRecord — `vidbyte/skills/catalog.py` | K01-K03 | Proposed CodexSkillTranslator | Carry instruction/resources paths and discovery scope. Registration in Vidbyte's catalog does not install a native Codex skill. |
| Handoff / AgentTransfer / AgentBinding / TaskLedger — `vidbyte/context/handoff/`, `vidbyte/agents/multi/` | N01-N05 | Explicit worker request/report translation and application-owned scheduling | Native role configuration is not deterministic task routing. Validate transfer outputs and clean up child lifetimes. |
| Pipelines — `vidbyte/pipelines/`; workflows — `vidbyte/workflows/` | V01, V03 | Proposed CodexAgentBinding implementing the actual required call contract | Existing string/AgentInput call sites cannot directly assume CodexRunInput compatibility; parallel work needs separate threads. |
| YamlLoader / registries — `vidbyte/config/loader.py`, `vidbyte/lib/registries/` | V02, G01-G05 | Declarative construction of validated Codex settings | Reject unknown/untranslatable options and keep config precedence visible; do not dynamically import code from untrusted config. |
| Harness / TrajectorySink — `vidbyte/harnesses/execution.py`, `vidbyte/harnesses/stores/base.py` | V04 | Run/trajectory adapter with provider IDs and artifacts | A serializable trace is not sufficient to reproduce the native model, filesystem, tools, and account state. |
| EvalSuite / Behavior — `vidbyte/evals/` | V05 | Harness-compatible evaluation bindings and event-backed behavioral evidence | Grade both final output and observable execution; record capability gaps so missing evidence is not a passing score. |

## Concrete examples of the work involved

### A Vidbyte tool

Existing path: `Tools` contains a schema plus executable behavior. Proposed path: `CodexToolTranslator` exposes that schema through an MCP server Codex can call; the server invokes the Vidbyte executor and returns a correlated result. A permissions check must run where the tool actually executes. Passing the tool description into a prompt would cover none of the execution/error contract.

Primary tasks: U01, U03, U04, M01, P05. Dynamic tools are an alternative gated route (U02), not an assumed SDK constructor argument.

### A timeout setting

Existing `AgentLoopSettings.timeout_seconds` constrains Vidbyte execution. Proposed translation owns a native turn handle, tracks the deadline, calls interrupt, and observes the terminal state. If the connection disappears before confirmation, return an indeterminate outcome; do not immediately repeat a potentially mutating task.

Primary tasks: L04, T03, B01, B04. This is outer control and does not prove an exact model-iteration ceiling.

### A durable session

Existing `Session` expects an agent that can export and restore state. Proposed translation checkpoints a provider thread/turn reference plus Vidbyte settings and provenance. Resume verifies that the native rollout still exists on the selected host. Exporting a text transcript alone cannot make a native thread portable, and restoring a conversation cannot undo file edits.

Primary tasks: S01, D01-D05, F05.

### Middleware that inspects tool calls

Existing `before_tool_call` can decide before Vidbyte's local executor runs. A Codex adapter must route to a supported pre-tool hook or callback and translate its accepted decision schema. A `PostToolUse` notification only supplies after-the-fact evidence. If missing/failed native hooks allow execution to proceed, the adapter cannot represent a mandatory fail-closed policy as satisfied.

Primary tasks: H01, H03, H05, P05. Consult [S06](sources.md#s06) for each event rather than assuming generic hook output fields.

## Questions to resolve per implementation slice

- What exact input/outcome does the caller need, and which task IDs cover it?
- Which SDK version, native executable, operation, config layer, or hook supplies the control?
- Which layer owns the process, tool execution, stored state, and cleanup?
- Is the mapping exact, policy-based, boundary-emulated, or unavailable?
- What changes during a fork/resume/model switch, and what is deliberately inherited?
- What happens if the connection fails after the operation may already have happened?
- What evidence proves behavior, beyond the settings object accepting a field?

These are design questions for selected work, not a reason to stop a documentation or explanation request.
