# Claude harness future-work checklist

Reviewed 2026-09-07. This is a proposed backlog, not an implemented API catalog. The comparison baseline is the `feat/claude-harness-agent` branch, which was **open and unmerged** when reviewed. Documentation inspection targeted `claude-agent-sdk` 0.2.152; the provider can add fields and events without changing Vidbyte's provider-neutral contracts.

## What the baseline already supplies

`vidbyte/agents/claude/` ships a facade, transport, config translation, context translation, result translation, and fork collaborator, plus validated records in `vidbyte/lib/dataclasses/claude.py`, closed vocabularies in `vidbyte/lib/enums/claude.py`, shared literals in `vidbyte/lib/constants/claude.py`, ten `claude.`-prefixed failure codes, and `ClaudeAgentError`.

Concretely, the baseline has: constructor-time Vidbyte translation; SDK option translation with provider-default sentinels dropped; one-shot `query()` per turn; session start, adopted-identity resume, and lazy `fork_session` branching; live `ContextManager` rendering into the system prompt and around the turn prompt; draft-07 structured output with provider-validated `structured_output` bridged back through `OutputSchemaFormatter`; typed result records with `total_cost_usd`; thinking-block exclusion at the serialization boundary; declarative tool, permission-mode, MCP, skill, subagent, sandbox, plugin, model, effort, thinking, and budget settings; explicit `setting_sources` declaration; and guaranteed stream teardown.

Do not count those as new work. Their deeper semantics, the callback surfaces, the persistent client, and their integration into other Vidbyte abstractions are the tasks below. In particular, `session_persistence_supported = False`, `history` is unbounded, each turn spawns a new CLI subprocess, `AgentMessage.claude.items` carries generic payload fields, and `capabilities` is descriptive metadata rather than an enforced contract.

## Read the surface labels correctly

| Label | Meaning |
|---|---|
| N | Function or method exists on the documented Python SDK public surface; the Vidbyte wrapper is pending. |
| P | Documented CLI or protocol behavior; a public Python wrapper is not established here. Check the installed package before promising it. |
| E | Experimental, beta, platform-specific, or version-gated; verify maturity and OS support before implementing. |
| CFG | Native configuration surface; the baseline's typed records may already carry it, but semantic mapping or enforcement is pending. |
| V | Proposed Vidbyte or application behavior; it must be implemented and verified outside or across exposed provider boundaries. |

A label names the implementation route, not a guarantee of availability for every platform, model, account, or runtime. Follow each task's caveat and its official source.

There are **133 pending tasks**. IDs are stable. Mark one complete only with an implementation commit and evidence; move changed assumptions into the baseline section rather than silently resetting checkbox meanings.

## Contents

- [C: Capability and version contracts](#c)
- [L: Connection lifecycle and persistent client](#l)
- [T: Live turns, streaming, and intervention](#t)
- [R: Messages, blocks, and artifacts](#r)
- [S: Provider session management](#s)
- [F: Forks and file checkpointing](#f)
- [D: Vidbyte durable sessions](#d)
- [X: Context, prompts, and compaction](#x)
- [U: Vidbyte tools and output contracts](#u)
- [M: MCP lifecycle and in-process servers](#m)
- [P: Permissions and approvals](#p)
- [H: Hooks and middleware](#h)
- [K: Skills, plugins, and settings sources](#k)
- [A: Authentication and model discovery](#a)
- [G: Typed configuration and precedence](#g)
- [N: Native subagents and tasks](#n)
- [O: Tracing, accounting, and speed](#o)
- [B: Budgets, failures, and recovery](#b)
- [V: Composition and evaluation](#v)

<a id="c"></a>

## C: Capability and version contracts

Evidence: [S01](sources.md#s01), [S02](sources.md#s02). Implementation seam: proposed `ClaudeCapabilities`; `vidbyte/lib/enums/claude.py`.

- [ ] **C01 [V] Declare support levels per operation.** Publish native, translated, supervised, observe-only, emulated, and unsupported dispositions as data the adapter can answer questions about, not only as skill prose.
- [ ] **C02 [V] Record resolved versions.** Capture the installed `claude-agent-sdk` version and the bundled CLI version, and expose both in result metadata so a bug report names them.
- [ ] **C03 [V] Detect API drift.** Compare the adapter's emitted option keys, enum values, and read result fields against the installed package's own types, and fail loudly on a mismatch rather than silently dropping a field.
- [ ] **C04 [V] Reject unsupported controls before launch.** `temperature`, `top_p`, and stop sequences have no Claude equivalent; reject them at construction instead of accepting a runner config that cannot be honored.
- [ ] **C05 [V] Define the shared harness-agent contract.** Specify the accepted input, result, streaming, cancellation, persistence, and fork guarantees that `CodexHarnessAgent` and `ClaudeHarnessAgent` both satisfy, before any caller treats them interchangeably.
- [ ] **C06 [V] Verify result field names against source.** The baseline reads `ResultMessage` defensively via `getattr` because the public docs disagreed with themselves; confirm each name against the installed package and tighten the reads.

Completion evidence: a requested unsupported control fails before a subprocess starts; SDK and CLI versions appear on a reply.

<a id="l"></a>

## L: Connection lifecycle and persistent client

Evidence: [S02](sources.md#s02), [S03](sources.md#s03). Implementation seam: proposed `ClaudeSessionTransport` behind the existing `ClaudeTransport.run()` boundary.

- [ ] **L01 [N] Add a persistent `ClaudeSDKClient` mode.** Own explicit connect and disconnect lifetimes so multiple turns reuse one subprocess instead of spawning one per turn.
- [ ] **L02 [V] Choose the mode explicitly.** Expose one-shot and persistent as distinct, caller-selected modes; never silently switch, because their session semantics differ.
- [ ] **L03 [V] Give the facade a close boundary.** A persistent client makes the agent a resource owner, which needs `aclose`/`__aenter__` on both harness adapters or on neither.
- [ ] **L04 [V] Bound concurrent turns per agent.** Define whether a second `arun` on one agent serializes, rejects, or queues; independent agents must still run concurrently.
- [ ] **L05 [N] Read server info.** Surface `get_server_info()` as a diagnostic record, not as a control surface.
- [ ] **L06 [V] Bound subprocess startup.** Apply and verify `load_timeout_ms` and `max_buffer_size` so a hung or chatty CLI cannot exhaust memory or block a run indefinitely.
- [ ] **L07 [E] Measure the per-turn spawn cost.** Quantify one-shot subprocess overhead before choosing a default mode; the baseline's choice is a design decision, not a measurement.

Completion evidence: a two-turn conversation in persistent mode spawns one subprocess; every mode closes its connection on success, failure, and cancellation.

<a id="t"></a>

## T: Live turns, streaming, and intervention

Evidence: [S03](sources.md#s03), [S04](sources.md#s04). Implementation seam: proposed `ClaudeStream`; `vidbyte/agents/claude/transport.py`.

- [ ] **T01 [N] Support streaming output.** Set `include_partial_messages` and normalize `StreamEvent` deltas into a Vidbyte stream API while retaining opt-in raw event access.
- [ ] **T02 [N] Support streaming input.** Accept an `AsyncIterable[dict]` prompt so images, queued prompts, and generator failures have defined ordering and cancellation semantics.
- [ ] **T03 [N] Expose `interrupt()`.** Persistent mode only; map the resulting partial state onto the failure vocabulary rather than reporting a clean stop.
- [ ] **T04 [N] Expose `stop_task()`.** Stop one background task and record its terminal reason and partial output.
- [ ] **T05 [N] Expose `set_model()` and `set_permission_mode()`.** Validate the requested change against Vidbyte policy first, then record it as a session event.
- [ ] **T06 [V] Add image input.** Streaming input carries content blocks, which is the point at which a content-anchor concept becomes meaningful; the baseline deliberately has none.
- [ ] **T07 [observe_only] Forward subagent text.** `forward_subagent_text` yields complete child messages with attribution; token-level child events are main-session only.
- [ ] **T08 [V] Define backpressure.** A slow consumer of a streamed turn must not silently drop events or deadlock the subprocess.

Completion evidence: a streamed turn yields ordered deltas whose concatenation equals the final text; an interrupt mid-turn produces a typed partial result.

<a id="r"></a>

## R: Messages, blocks, and artifacts

Evidence: [S02](sources.md#s02), [S04](sources.md#s04). Implementation seam: `vidbyte/agents/claude/result.py`.

- [ ] **R01 [V] Type the item payloads.** `ClaudeItem.fields` is a generic mapping; give each block kind its own typed record so callers stop reading dictionaries.
- [ ] **R02 [V] Preserve tool-result content.** The baseline records a bounded block count only; define a size-capped, redacted representation for callers that need the payload.
- [ ] **R03 [V] Preserve parent attribution.** Carry `parent_tool_use_id` and `parent_agent_id` so a child's output is traceable to the tool call that spawned it.
- [ ] **R04 [N] Handle task notifications.** `TaskNotificationMessage` reports background task status; normalize it instead of ignoring it.
- [ ] **R05 [N] Handle hook event messages.** `include_hook_events` yields `HookEventMessage`; expose it through an opt-in diagnostic channel with redaction.
- [ ] **R06 [observe_only] Expose thinking visibility policy.** Thinking is excluded at serialization today; if a caller ever needs summaries, make the choice explicit and redacted, never a default.
- [ ] **R07 [V] Surface rate-limit information.** Report reset windows and scope where the provider gives them; never fabricate a limit the provider did not state.
- [ ] **R08 [V] Bound the reply history.** `history` grows without limit across turns; define a retention policy or hand ownership to a session store.

Completion evidence: a tool-heavy turn produces typed items with parent attribution; hook and task messages appear only when opted into.

<a id="s"></a>

## S: Provider session management

Evidence: [S05](sources.md#s05), [S06](sources.md#s06). Implementation seam: proposed `ClaudeSessions` facade; `vidbyte/agents/claude/`.

- [ ] **S01 [N] Wrap `list_sessions()`.** Enumerate on-disk sessions with metadata for pickers and cleanup, without treating them as Vidbyte checkpoints.
- [ ] **S02 [N] Wrap `get_session_messages()`.** Read a past transcript for inspection or replay, with an explicit size bound.
- [ ] **S03 [N] Wrap `get_session_info()`, `rename_session()`, and `tag_session()`.** Give provider sessions human-readable organization.
- [ ] **S04 [N] Support `SessionStore`.** Mirror transcripts to a caller-owned backend so another host can resume; define serialization, locking, ownership, and encryption.
- [ ] **S05 [CFG] Support `session_store_flush`.** Make durability and flush failures visible; never report a persisted turn before persistence succeeded.
- [ ] **S06 [CFG] Validate `resume_session_at` boundaries.** Map a message UUID only when the provider can prove that boundary exists; otherwise reject rather than silently resuming the whole session.
- [ ] **S07 [V] Validate resume compatibility.** Check working directory, model, and policy before resuming a session created under different settings.
- [ ] **S08 [P] Suppress transcript writes.** `CLAUDE_CODE_SKIP_PROMPT_HISTORY` is the Python route to a stateless run; expose it as a typed setting rather than raw env passthrough.
- [ ] **S09 [V] Document cross-host limits.** Session files are machine-local; state that plainly wherever resume is offered.

Completion evidence: a session created in one process is listed, renamed, resumed, and read from another; a mismatched resume is rejected with a specific code.

<a id="f"></a>

## F: Forks and file checkpointing

Evidence: [S05](sources.md#s05), [S07](sources.md#s07). Implementation seam: `vidbyte/agents/claude/fork.py`.

- [ ] **F01 [N] Enable file checkpointing.** Set `enable_file_checkpointing` and track checkpoint identity and filesystem scope.
- [ ] **F02 [N] Expose `rewind_files()`.** Persistent mode only; state in the API that this reverts file changes, not conversation history.
- [ ] **F03 [V] Separate the two branch axes.** A session fork branches history while the filesystem stays shared; a caller branching to "try something else" usually wants both, and must be told they are separate.
- [ ] **F04 [V] Confirm fork lineage after the fact.** A child's own session id appears only after its first run; expose a way to assert the branch actually happened.
- [ ] **F05 [V] Bound fork depth.** `fork_depth` is recorded but never limited; decide whether an unbounded chain of branches needs a ceiling.
- [ ] **F06 [V] Reconcile concurrent forks.** Two children forked from one parent edit the same working tree; define whether that is rejected, isolated by worktree, or documented as the caller's problem.

Completion evidence: a fork that edits files can be reverted without reverting the parent's history; a same-directory concurrent fork has documented behavior.

<a id="d"></a>

## D: Vidbyte durable sessions

Evidence: [S05](sources.md#s05). Implementation seam: `vidbyte/sessions/`; the agent facade.

- [ ] **D01 [V] Flip `session_persistence_supported`.** Only after provider session identity is genuinely bound to a Vidbyte checkpoint, not merely stored beside it.
- [ ] **D02 [V] Map checkpoints to provider sessions.** Define which Vidbyte checkpoint operations a provider session can honor and which are emulated outside it.
- [ ] **D03 [V] Keep the two identities distinct.** A Claude `session_id` is not a Vidbyte checkpoint id and not a Codex `thread_id`; the mapping must be explicit and one-directional.
- [ ] **D04 [V] Support export and import.** Decide whether a Vidbyte session export carries the provider transcript, a reference to it, or neither.
- [ ] **D05 [V] Define rewind semantics.** Vidbyte rewind restores runtime state Claude cannot restore; state the gap rather than approximating it.

Completion evidence: a Vidbyte session resumed from a store continues the same provider session, and every unsupported checkpoint operation names itself.

<a id="x"></a>

## X: Context, prompts, and compaction

Evidence: [S02](sources.md#s02), [S08](sources.md#s08). Implementation seam: `vidbyte/agents/claude/context.py`.

- [ ] **X01 [supervised] Observe compaction boundaries.** `PreCompact` and `PostCompact` report when the provider compacted; Vidbyte cannot substitute its own algorithm inside that loop.
- [ ] **X02 [N] Read context usage.** Expose the provider's own context-window estimate as a diagnostic, kept distinct from Vidbyte token accounting.
- [ ] **X03 [V] Resolve prompt files under trust rules.** `ClaudeSystemPromptKind.FILE` reads a path; define who may set it and never accept one from untrusted YAML.
- [ ] **X04 [V] Report the memory that actually loaded.** With `setting_sources` enabled the provider loads CLAUDE.md files the adapter never sees; `InstructionsLoaded` is the route to reporting them.
- [ ] **X05 [V] Bound the rendered context.** A large registry silently produces a very large prompt; add a measured ceiling with a specific failure rather than a provider-side truncation.
- [ ] **X06 [V] Decide on conversation-zone honesty.** Conversation placements render as current-turn text, not native history; consider whether that mapping should be rejected instead of approximated.

Completion evidence: a compaction event is observable; the loaded instruction files are reportable; an oversized context fails with its own code.

<a id="u"></a>

## U: Vidbyte tools and output contracts

Evidence: [S09](sources.md#s09), [S10](sources.md#s10). Implementation seam: `vidbyte/tools/`; proposed `vidbyte/agents/claude/tools.py`.

- [ ] **U01 [N] Bridge Vidbyte `ToolSpec` to SDK `@tool`.** Preserve schema, annotations, result limits, pricing identity, and async error semantics.
- [ ] **U02 [N] Create in-process MCP servers.** Wrap `create_sdk_mcp_server()` so Vidbyte tools run in the caller's process rather than a subprocess.
- [ ] **U03 [CFG] Map tool annotations.** `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` inform policy; they are never authorization.
- [ ] **U04 [CFG] Map result truncation.** Relate `maxResultSizeChars` to `ToolSettings.result_max_chars` and keep provider truncation distinguishable from Vidbyte compaction.
- [ ] **U05 [E] Handle tool search.** Deferred tool loading means the provider selects tools; Vidbyte cannot promise its own per-call ordering.
- [ ] **U06 [V] Decide built-in tool observability.** Claude's Read, Write, Edit, and Bash run inside its loop; decide whether they stay provider-owned or surface as observable Vidbyte tool events.
- [ ] **U07 [V] Report structured-output retries.** The provider retries invalid output internally; expose that count instead of letting it look like a single clean turn.
- [ ] **U08 [V] Validate the schema draft properly.** The baseline rewrites `$schema` to draft-07; detect constructs that draft-07 genuinely cannot express and reject them instead.

Completion evidence: a Vidbyte tool executes inside a Claude turn with its pricing identity intact; a structured-output retry is visible on the reply.

<a id="m"></a>

## M: MCP lifecycle and in-process servers

Evidence: [S09](sources.md#s09). Implementation seam: `vidbyte/tools/mcp/`.

- [ ] **M01 [N] Expose `get_mcp_status()`.** Report per-server state in diagnostics, not in the model prompt by default.
- [ ] **M02 [N] Expose `reconnect_mcp_server()`.** Never silently reconnect a server that a policy decision disabled.
- [ ] **M03 [N] Expose `toggle_mcp_server()`.** Record enable and disable as auditable session events.
- [ ] **M04 [CFG] Validate MCP config strictly.** `strict_mcp_config` should reject unknown or malformed server entries at construction, before any subprocess starts.
- [ ] **M05 [N] Handle MCP elicitation.** `Elicitation` and `ElicitationResult` let a server request user input mid-task; define who answers and whether Vidbyte may.
- [ ] **M06 [V] Attach Vidbyte MCP servers.** Reuse the existing `vidbyte.tools.mcp` bridge rather than a second, Claude-only configuration path.

Completion evidence: a failed MCP server is visible, reconnectable, and cannot be revived past a denial.

<a id="p"></a>

## P: Permissions and approvals

Evidence: [S11](sources.md#s11). Implementation seam: proposed `vidbyte/agents/claude/permissions.py`.

- [ ] **P01 [N] Support the `can_use_tool` callback.** Convert to typed allow, deny, ask, and defer results and preserve `updated_input`.
- [ ] **P02 [N] Support `PermissionUpdate`.** Handle rule add, replace, remove, mode change, and directory add/remove, and audit every applied update.
- [ ] **P03 [V] Fail closed with no callback.** A caller omitting a callback must not be read as blanket approval.
- [ ] **P04 [V] Define allow/deny precedence.** The baseline rejects an explicit conflict at construction; define precedence for rules that only conflict at runtime.
- [ ] **P05 [CFG] Constrain `bypassPermissions`.** Make the most dangerous mode opt-in, logged, and refusable by Vidbyte policy.
- [ ] **P06 [N] Handle `permission_prompt_tool_name`.** Route a host approval prompt to a real human channel rather than an auto-approver.
- [ ] **P07 [E] Map sandbox platform gaps.** Sandbox support is OS-specific; report the gap rather than claiming Windows parity.
- [ ] **P08 [V] Audit denials.** Preserve the denial reason without logging sensitive tool input.

Completion evidence: a denied tool stays denied through every path; every permission change is audited; no default approves anything.

<a id="h"></a>

## H: Hooks and middleware

Evidence: [S12](sources.md#s12). Implementation seam: proposed `vidbyte/agents/claude/hooks.py`; `vidbyte/middleware/`.

- [ ] **H01 [N] Support tool hooks.** `PreToolUse`, `PostToolUse`, and `PostToolUseFailure`, including `permissionDecision`, `permissionDecisionReason`, and `updatedInput`.
- [ ] **H02 [N] Support prompt and message hooks.** `UserPromptSubmit` and `MessageDisplay`, distinguishing host prompt mutation from Vidbyte context mutation.
- [ ] **H03 [N] Support terminal hooks.** `Stop` and `StopFailure`, mapping the final reason onto the failure vocabulary.
- [ ] **H04 [N] Support subagent hooks.** `SubagentStart` and `SubagentStop`, carrying parent session and tool-use identity.
- [ ] **H05 [N] Support session hooks.** `SessionStart`, `SessionEnd`, and `Setup`.
- [ ] **H06 [N] Support permission hooks.** `PermissionRequest` and `PermissionDenied`, preserving the most restrictive outcome.
- [ ] **H07 [N] Support environment hooks.** `ConfigChange`, `InstructionsLoaded`, `CwdChanged`, `FileChanged`, `DirectoryAdded`, `WorktreeCreate`, and `WorktreeRemove`.
- [ ] **H08 [V] State the middleware boundary.** Claude hooks are not `AgentMiddleware`; event timing, allowed outputs, and failure policy all differ, and the adapter must not present them as equivalent.
- [ ] **H09 [V] Solve the callable-in-a-frozen-record problem.** Hooks and permission callbacks are live functions, which the current frozen slots records and the fork's `deepcopy` cannot carry; this blocks P01 and H01 through H07.
- [ ] **H10 [V] Handle parallel hook results.** Matching hooks run in parallel and the most restrictive result wins; do not promise sequential middleware semantics.
- [ ] **H11 [E] Handle `defer`.** A `PreToolUse` deferral ends the query for later resumption, which interacts directly with session resume.

Completion evidence: a hook blocks a dangerous write; a deferral is resumable; hook failures have a defined policy.

<a id="k"></a>

## K: Skills, plugins, and settings sources

Evidence: [S13](sources.md#s13), [S14](sources.md#s14). Implementation seam: `vidbyte/agents/claude/config.py`.

- [ ] **K01 [CFG] Validate skill names.** The baseline forwards names verbatim; verify a named skill actually resolves before the run rather than after.
- [ ] **K02 [CFG] Validate plugin paths.** Load only explicitly allowed local paths and record their versions and requested permissions.
- [ ] **K03 [V] Do not conflate skill registries.** Vidbyte's own `vidbyte.skills` registry is not loaded by the provider; say so wherever `skills` appears.
- [ ] **K04 [P] Support slash commands.** Commands load from `.claude/` when settings sources allow it; decide whether Vidbyte exposes them at all.
- [ ] **K05 [V] Make precedence visible.** With user, project, and local sources enabled, report the resolved precedence rather than leaving it implicit.
- [ ] **K06 [V] Reconsider the settings default.** The baseline declares no sources, so nothing on disk loads; confirm that is right for a harness and document the trade.

Completion evidence: a missing skill or plugin fails before the run; the effective configuration precedence is reportable.

<a id="a"></a>

## A: Authentication and model discovery

Evidence: [S01](sources.md#s01), [S15](sources.md#s15). Implementation seam: `vidbyte/agents/claude/config.py`; deployment docs.

- [ ] **A01 [V] Define credential injection.** Accept API keys only from the process environment or an application-owned provider; reject them in settings, metadata, and traces.
- [ ] **A02 [V] Reject claude.ai login.** Third-party products need Anthropic approval; make the unsupported path an explicit message, not a silent failure.
- [ ] **A03 [V] Surface commercial terms.** Reference Anthropic's Commercial Terms in the install and integration docs for the optional extra.
- [ ] **A04 [V] Redact `env` passthrough.** `ClaudeProcessSettings.env` is documented as unredacted; add redaction before it can reach a trace or a log.
- [ ] **A05 [P] Discover available models.** A caller naming an unavailable model should learn that before the run, not from a provider error mid-turn.
- [ ] **A06 [V] Support alternate providers.** Bedrock and Vertex routing is environment-driven; decide whether the adapter models it or documents it.

Completion evidence: no credential appears in any record the adapter produces; an unavailable model fails at construction.

<a id="g"></a>

## G: Typed configuration and precedence

Evidence: [S02](sources.md#s02). Implementation seam: `vidbyte/lib/dataclasses/claude.py`; `vidbyte/config/`.

- [ ] **G01 [V] Add YAML construction.** Let `YamlLoader` build a `ClaudeHarnessAgent` through the existing `{ref, options}` resolution and registries.
- [ ] **G02 [V] Type `mcp_servers` per transport.** The mapping is JSON-validated but structurally loose; give stdio, SSE, and HTTP their own records.
- [ ] **G03 [V] Type `extra_args`.** Raw CLI passthrough is an escape hatch; keep it, name it as one, and exclude it from portability claims.
- [ ] **G04 [V] Model `task_budget`.** Distinguish an API-side token budget from the dollar budget and the turn ceiling.
- [ ] **G05 [CFG] Add remaining option coverage.** `betas` semantics, `user` tenancy, and any option added after 0.2.152 need typed records rather than passthrough.
- [ ] **G06 [V] Validate `cwd` before launch.** Resolve and check the working root and `add_dirs` to prevent traversal and unintended host writes.

Completion evidence: an agent builds from YAML with the same validation as a direct construction; every escape hatch is labeled.

<a id="n"></a>

## N: Native subagents and tasks

Evidence: [S16](sources.md#s16). Implementation seam: proposed `vidbyte/agents/claude/subagents.py`.

- [ ] **N01 [CFG] Complete `AgentDefinition` coverage.** `memory`, `mcpServers`, and `initialPrompt` are documented fields the baseline's record omits.
- [ ] **N02 [supervised] Track child lifecycle.** Correlate `SubagentStart` and `SubagentStop` with the tool call that spawned the child.
- [ ] **N03 [supervised] Handle background subagents.** Expose a task handle and status; this is not Vidbyte actor-model concurrency.
- [ ] **N04 [V] Constrain child resources.** A child must not inherit parent secrets or context by accident.
- [ ] **N05 [P] Support the Task tool family.** `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`, `TaskOutput`, and `TaskStop`, kept separate from Vidbyte ledger tasks.
- [ ] **N06 [V] Attribute child output.** `AgentMessage.claude.subagents` currently names delegating tool calls only; carry the child's own result.
- [ ] **N07 [unsupported] State the orchestration boundary.** Claude subagents are not drop-in `MultiAgent` ledger workers, and Vidbyte MCTS and actor runtimes do not run inside Claude's loop.

Completion evidence: a parallel subagent run reports per-child identity, status, and output with correct parent attribution.

<a id="o"></a>

## O: Tracing, accounting, and speed

Evidence: [S17](sources.md#s17). Implementation seam: `vidbyte/trace/`, `vidbyte/agents/pricing/`, `vidbyte/agents/speed/`.

- [ ] **O01 [V] Wire usage into `UsageTracker`.** `ClaudeUsage` exists but nothing consumes it; fold it into the existing usage and rollup surfaces.
- [ ] **O02 [V] Reconcile provider cost with Vidbyte pricing.** `total_cost_usd` is the provider's own figure; record its source and model rather than mixing it into a Vidbyte rate table silently.
- [ ] **O03 [V] Track latency.** Feed `duration_ms` and `duration_api_ms` into `AgentSpeedTracker`; time-to-first-token needs streaming from T01.
- [ ] **O04 [V] Emit trace spans.** Translate turns, tool calls, and subagents into the repository's typed trace shapes, reusing the OTel GenAI work.
- [ ] **O05 [N] Translate provider OpenTelemetry.** The provider emits its own telemetry through settings; relate it to Vidbyte spans instead of duplicating them.
- [ ] **O06 [V] Redact by default.** Prompts, tool inputs, and file contents must not reach logs or traces without explicit consent.
- [ ] **O07 [observe_only] Handle todos and progress.** Provider todo state is telemetry, never the source of truth for a Vidbyte workflow.

Completion evidence: a run's cost, latency, and spans appear in the existing Vidbyte surfaces with no credential or prompt leakage.

<a id="b"></a>

## B: Budgets, failures, and recovery

Evidence: [S02](sources.md#s02), [S18](sources.md#s18). Implementation seam: `vidbyte/lib/enums/failure.py`; `vidbyte/sessions/failure/`.

- [ ] **B01 [V] Add automatic ceiling recovery.** A run ending in `error_max_turns` or `error_max_budget_usd` is resumable with a raised ceiling; offer that as a policy rather than a manual step.
- [ ] **B02 [V] Distinguish terminal subtypes.** `ClaudeResultSubtype` is defined but only `SUCCESS` drives behavior; give each error subtype its own failure code and disposition.
- [ ] **B03 [V] Route into the failure vocabulary.** Connect `claude.*` codes to `vidbyte/sessions/failure/` recovery handlers so a Claude failure is routable like any other.
- [ ] **B04 [V] Classify retryability.** A missing CLI is not retryable; a lost connection is. Encode that instead of leaving it to the caller.
- [ ] **B05 [V] Reconcile provider fallback.** `fallback_model` is provider-owned and must not be double-counted against `AgentFallbackSettings` attempts.
- [ ] **B06 [V] Enforce a Vidbyte-side budget.** `max_budget_usd` is enforced by the provider; decide whether Vidbyte also caps spend across turns, which the provider cannot see.

Completion evidence: each terminal subtype maps to a distinct code with a documented recovery, and a ceiling failure recovers without manual session handling.

<a id="v"></a>

## V: Composition and evaluation

Evidence: [S01](sources.md#s01), [S19](sources.md#s19). Implementation seam: `vidbyte/harnesses/`, `vidbyte/evals/`, `vidbyte/agents/multi/`.

- [ ] **V01 [V] Capture inside a `Harness`.** Let the outer execution envelope capture a Claude run's trajectory with redaction and consent, without absorbing Claude's loop.
- [ ] **V02 [V] Use as a `MultiAgent` participant.** Define the contract that lets a Claude-backed agent take part in Vidbyte coordination as a worker.
- [ ] **V03 [V] Score with `Harness.score()`.** Make Claude runs evaluable by the existing eval surfaces.
- [ ] **V04 [V] Export trajectories.** Route Claude runs through `TrajectorySink` for cloud export.
- [ ] **V05 [V] Add a cookbook example.** One notebook showing a Claude harness agent doing real work, following the repository's one-notebook-per-folder rules.
- [ ] **V06 [V] Add an opt-in integration smoke test.** One documented live test against a real key and CLI, kept out of the default gate.
- [ ] **V07 [V] Publish provider-parity docs.** Document what differs between the Codex and Claude adapters so a reader picking one knows the trade.

Completion evidence: a Claude run is capturable, scorable, exportable, and demonstrated end to end in a committed example.

## Suggested delivery waves

1. **Correctness of what exists** — C06, R01, B02, B04, S06, G06. Confirm field names and give every terminal state a code before adding surface area.
2. **The callback unlock** — H09 first, then P01, P03, H01 through H07, U01, U02. Nothing in the permissions or hooks families can ship until a live callable can live in the settings path and survive a fork.
3. **Persistent client and streaming** — L01 through L04, T01 through T05. These arrive together because interrupts require the persistent connection and streaming makes it worth having.
4. **Sessions and durability** — S01 through S09, F01 through F06, D01 through D05. Provider session management first, Vidbyte durable-session binding last.
5. **Accounting and composition** — O01 through O07, V01 through V07. Most valuable once the earlier waves settle what there is to measure.
