# Codex harness future-work checklist

Reviewed 2026-09-05. This is a proposed backlog, not an implemented API catalog. The comparison baseline is [PR #409](https://github.com/cerredz/Vidbyte-SDK/pull/409) at [c3842585](https://github.com/cerredz/Vidbyte-SDK/tree/c3842585822bb2eb950bc3a419ae1ae52ecaa21d/vidbyte/agents/codex), which was **open and unmerged** when reviewed. Main at `c27dac4f` does not yet include that adapter. Python SDK inspection used `openai-codex==0.147.0`; current documentation can describe a broader or newer runtime.

## What the PR already supplies

The baseline has validated client/thread/turn/subagent records; constructor-time Vidbyte translation; SDK argument translation; system/developer instructions; turn-boundary ContextManager rendering; output schema validation; five native input variants; run/arun; start/resume; native fork/fork overrides; typed result envelopes; and eight classified failures.

Do not count those as new work. Their deeper semantics, additional operation methods, and integration into other Vidbyte abstractions are future tasks below. In particular, `session_persistence_supported = False`, `AgentMessage.codex.items` still uses generic payload fields, each transport operation opens a new connection, and a `capabilities` tuple is descriptive metadata rather than an enforced capability contract.

## Read the surface labels correctly

| Label | Meaning |
|---|---|
| N | Method exists on the inspected Python SDK public facade; the Vidbyte wrapper is pending. |
| P | Documented app-server protocol operation; a public Python wrapper is not established here. Check installed generated schemas and transport access. |
| E | Experimental, beta, under-development, or exploratory integration; verify feature maturity before implementation. |
| CFG | Native configuration surface; raw config may already pass through the PR, but typed records and semantic mapping are pending. |
| V | Proposed Vidbyte/application behavior; it must be implemented and verified outside or across exposed provider boundaries. |

A label names the implementation route, not a guarantee of availability for every platform, model, account, or runtime. Any experimental child field remains gated even when its parent row says P/CFG. Follow the task's caveat and official source.

There are **100 pending tasks**. IDs are stable. Mark one complete only with an implementation commit and evidence; move changed assumptions into the baseline rather than silently resetting checkbox meanings.

## Contents

- [C: Capability and version contracts](#c)
- [L: Process and connection lifecycle](#l)
- [T: Live turns and intervention](#t)
- [R: Events, messages, and artifacts](#r)
- [S: Native thread management](#s)
- [F: Forks and workspace branches](#f)
- [D: Vidbyte durable sessions](#d)
- [X: Context, prompts, and compaction](#x)
- [U: Vidbyte tools and output contracts](#u)
- [M: MCP lifecycle and resources](#m)
- [P: Permissions and approvals](#p)
- [H: Hooks and middleware](#h)
- [K: Skills, plugins, and connectors](#k)
- [A: Authentication and model discovery](#a)
- [G: Typed configuration and precedence](#g)
- [N: Native subagents and team behavior](#n)
- [O: Tracing, accounting, and speed](#o)
- [B: Budgets, failures, and recovery](#b)
- [V: Composition, configuration, and evaluation](#v)
- [Z: Advanced protocol and product integrations](#z)

<a id="c"></a>

## C: Capability and version contracts

Evidence: [S01](sources.md#s01), [S02](sources.md#s02). Implementation seam: Proposed CodexCapabilities; central settings and enums.

- [ ] **C01 [V] Declare support levels.** Publish native, policy-mapped, emulated, experimental, and unavailable capabilities per operation.
- [ ] **C02 [V] Detect compatibility.** Record the installed Python SDK and resolved CLI runtime; verify the selected feature against both.
- [ ] **C03 [P] Negotiate protocol features.** Model initialization capabilities, notification opt-outs, and experimental feature discovery explicitly.
- [ ] **C04 [V] Detect API drift.** Compare wrapper fields, enum values, input variants, and result items with installed signatures/generated schemas.
- [ ] **C05 [V] Define shared agent contracts.** Specify accepted input/result, streaming, cancellation, persistence, and fork contracts before claiming BaseAgent compatibility.

Completion evidence: A requested unsupported behavior fails before launch; SDK and CLI versions are recorded.

<a id="l"></a>

## L: Process and connection lifecycle

Evidence: [S01](sources.md#s01), [S02](sources.md#s02), [S10](sources.md#s10). Implementation seam: Proposed CodexConnection owner; transport.py.

- [ ] **L01 [V] Keep a reusable connection.** Add explicit sync/async open and close lifetimes around the native SDK.
- [ ] **L02 [V] Support ephemeral continuation.** Keep in-memory threads alive across turns; reject resume after their owning process is gone.
- [ ] **L03 [V] Control concurrent calls.** Define a per-thread serialization/rejection policy while allowing independent threads to run concurrently.
- [ ] **L04 [V] Handle disconnects and shutdown.** Bound startup/initialization/shutdown waits and drain or interrupt owned turns before cleanup.
- [ ] **L05 [V] Inject transport dependencies.** Permit deterministic fakes and external process ownership without duplicating SDK internals.

Completion evidence: Cancellation or disconnect leaves no unowned process; ephemeral continuation stays on its owning connection.

<a id="t"></a>

## T: Live turns and intervention

Evidence: [S01](sources.md#s01), [S02](sources.md#s02). Implementation seam: Proposed CodexTurnController; transport.py.

- [ ] **T01 [N] Stream a running turn.** Expose AsyncThread.turn() and AsyncTurnHandle.stream() through a typed Vidbyte stream.
- [ ] **T02 [N] Steer the current turn.** Translate additional input through steer(); preserve thread/turn correlation and reject stale targets.
- [ ] **T03 [N] Interrupt explicitly.** Call interrupt(), await the terminal outcome, and distinguish interruption from ordinary failure.
- [ ] **T04 [V] Allow per-call overrides.** Add a typed request for model, effort, schema, permissions, and other supported turn settings; document which persist.
- [ ] **T05 [V] Handle partial outcomes.** Return useful partial output on interruption, failure, or an empty final message without falsely marking success.

Completion evidence: A caller can start, observe, steer, and interrupt the correct turn without losing its terminal state.

<a id="r"></a>

## R: Events, messages, and artifacts

Evidence: [S02](sources.md#s02); PR #409 result.py. Implementation seam: Proposed CodexEventTranslator; result.py and shared records.

- [ ] **R01 [V] Use item-specific result records.** Replace generic payload access with typed variants for messages, plans, commands, changes, MCP, and subagents.
- [ ] **R02 [V] Assemble streamed updates.** Correlate item starts/deltas/completions and terminal turns without duplicating content.
- [ ] **R03 [V] Preserve artifact provenance.** Attach file changes, diff snapshots, command exit details, tool results, and artifact paths with bounded payloads.
- [ ] **R04 [V] Version the event contract.** Handle new item types and optional fields deliberately; surface warnings instead of silently losing useful data.
- [ ] **R05 [V] Separate display and telemetry.** Redact secrets and exclude private reasoning content while retaining exposed summaries and operational events.

Completion evidence: Event order and provider identity survive translation; unknown items and absent fields are explicit.

<a id="s"></a>

## S: Native thread management

Evidence: [S01](sources.md#s01), [S02](sources.md#s02). Implementation seam: Proposed CodexThreadManager.

- [ ] **S01 [N] Read and list threads.** Wrap read() and thread_list() with typed pagination, filters, and history-loading options supported by the SDK.
- [ ] **S02 [N] Rename and archive threads.** Expose set_name(), archive, and unarchive, preserving native identities and descendant behavior.
- [ ] **S03 [E] Page turns and items.** Integrate experimental history pagination only where the runtime and active store support it.
- [ ] **S04 [P] Track loaded-thread state.** Expose status, loaded-thread listing, unsubscribe, and persisted metadata updates independently of local facade history.
- [ ] **S05 [P] Define deletion and retention.** Offer explicit thread deletion with descendant scope and recovery implications; do not equate archive with delete.

Completion evidence: Read/list operations do not accidentally resume a run, and destructive lifecycle calls have explicit targets.

<a id="f"></a>

## F: Forks and workspace branches

Evidence: [S02](sources.md#s02), [S19](sources.md#s19); PR #409 fork.py. Implementation seam: Extend CodexFork and CodexForkSettings.

- [ ] **F01 [P] Fork at a selected turn.** Expose lastTurnId through a version-checked protocol path; reject an in-progress source turn.
- [ ] **F02 [V] Specify fork timing.** Define behavior when the parent is busy and capture the exact inherited settings/history boundary.
- [ ] **F03 [V] Batch forks safely.** Return per-child outcomes, limit concurrent creation, and clean up failed local preparation without hiding partial success.
- [ ] **F04 [V] Isolate files when requested.** Compose native thread forks with application-owned Git worktrees; a copied conversation does not copy the filesystem.
- [ ] **F05 [V] Preserve complete lineage.** Carry provider ancestry, Vidbyte checkpoint identity, branch/worktree location, and child override provenance.

Completion evidence: Fork lineage is native; filesystem isolation is independently owned and verified.

<a id="d"></a>

## D: Vidbyte durable sessions

Evidence: [S02](sources.md#s02); vidbyte/sessions/session.py. Implementation seam: Proposed CodexSessionAdapter and serializable state records.

- [ ] **D01 [V] Implement export and restore.** Persist provider identity, translated settings, schema references, and version metadata using a bounded state contract.
- [ ] **D02 [V] Align checkpoints with turns.** Map completed native turns to Session checkpoints and preserve incomplete/failure state separately.
- [ ] **D03 [V] Define portability.** Detect missing native rollouts, incompatible hosts, absent credentials, and expired ephemeral threads on import/resume.
- [ ] **D04 [V] Translate session operations.** Specify checkpoint selection, fork_from, tagging, adoption, and usage semantics before enabling Session compatibility.
- [ ] **D05 [V] Separate history and file recovery.** Use native branches for alternate history; keep file restoration explicit and avoid building new features on deprecated rollback.

Completion evidence: Session export/restore works across process restarts without treating transcript text as provider state.

<a id="x"></a>

## X: Context, prompts, and compaction

Evidence: [S02](sources.md#s02), [S06](sources.md#s06), [S12](sources.md#s12); vidbyte/context/. Implementation seam: Extend CodexContextTranslator; proposed CodexCompactionController.

- [ ] **X01 [V] Track context revisions.** Send intentional additions/replacements without repeatedly appending identical large ContextManager snapshots.
- [ ] **X02 [V] Preserve source meaning.** Carry Source and ContextItem provenance, trust labels, size limits, and supported media instead of flattening everything to text.
- [ ] **X03 [V] Explain instruction precedence.** Separate base/developer instructions, AGENTS.md discovery, skills, hook context, and user-turn context.
- [ ] **X04 [N] Request native compaction.** Expose AsyncThread.compact() and observe completion; specify what Vidbyte state needs refreshing afterward.
- [ ] **X05 [P] Evaluate history injection.** Version-gate thread/inject_items for advanced context insertion; do not imply arbitrary control of hidden native prompt state.

Completion evidence: Context updates have known placement and lifetime; compaction completion is observed rather than assumed.

<a id="u"></a>

## U: Vidbyte tools and output contracts

Evidence: [S02](sources.md#s02), [S08](sources.md#s08); vidbyte/tools/ and vidbyte/agents/contracts/. Implementation seam: Proposed CodexToolTranslator and CodexOutputContractTranslator.

- [ ] **U01 [V] Export tool schemas.** Translate Tools/BaseTool names, descriptions, arguments, and capabilities into an MCP-exposed catalog.
- [ ] **U02 [E] Support dynamic tools.** Evaluate experimental dynamicTools registration plus item/tool/call dispatch when an MCP bridge is unsuitable.
- [ ] **U03 [V] Execute tool callbacks correctly.** Validate inputs, preserve call IDs, encode outputs/errors/media, and propagate cancellation and timeout.
- [ ] **U04 [V] Translate tool policy.** Map allow/deny, concurrency, dependencies, and tool-error policy only where a pre-execution control point exists.
- [ ] **U05 [V] Extend output contracts.** Map final structured-output validation and applicable OutputContract checks; do not substitute output shape for required tool behavior.

Completion evidence: A real Vidbyte tool executes once with validated arguments, clear authorization, and a correctly returned result.

<a id="m"></a>

## M: MCP lifecycle and resources

Evidence: [S08](sources.md#s08), [S03](sources.md#s03), [S02](sources.md#s02). Implementation seam: Proposed CodexMcpTranslator and CodexMcpManager.

- [ ] **M01 [CFG] Model server configuration.** Add typed stdio/HTTP declarations, cwd/environment, headers, enabled tools, and required-server/time-limit options.
- [ ] **M02 [P] Manage server state.** Expose startup status, paginated tool/resource/auth inventory, and config reload with per-thread refresh semantics.
- [ ] **M03 [P] Support MCP authentication.** Handle OAuth login completion and credential references without embedding credentials in agent settings or traces.
- [ ] **M04 [P] Handle elicitation.** Translate form and URL requests, accept/decline/cancel responses, and pending-request lifetimes into application UI contracts.
- [ ] **M05 [P] Use resources and direct calls.** Map resource reads and explicit server-tool calls; distinguish these from model-selected MCP calls and preserve provenance.

Completion evidence: Configured tools/resources remain discoverable and authenticated, with bounded calls and explicit startup failures.

<a id="p"></a>

## P: Permissions and approvals

Evidence: [S09](sources.md#s09), [S10](sources.md#s10), [S11](sources.md#s11), [S15](sources.md#s15), [S02](sources.md#s02). Implementation seam: Proposed CodexPermissionTranslator and CodexApprovalRouter.

- [ ] **P01 [CFG] Model filesystem/network profiles.** Add typed profile rules and legacy sandbox settings with explicit precedence, platform support, and network-proxy requirements.
- [ ] **P02 [P] Route approval requests.** Handle command, file-change, permission-grant, and tool/user-input requests with stable IDs and documented decision vocabularies.
- [ ] **P03 [CFG] Respect effective requirements.** Read managed constraints and allowed profiles; explain conflicts instead of silently overriding organization policy.
- [ ] **P04 [CFG] Translate command rules.** Support reviewed command-prefix policies and distinguish an execution rule from a tool allowlist or prompt instruction.
- [ ] **P05 [V] Separate execution boundaries.** Model native sandbox, auto-review, externally executed Vidbyte tools, and unsandboxed host operations as distinct authority paths.

Completion evidence: Every permission claim identifies the enforcing provider boundary, effective policy, and failure behavior.

<a id="h"></a>

## H: Hooks and middleware

Evidence: [S06](sources.md#s06); vidbyte/middleware/base.py. Implementation seam: Proposed CodexHookTranslator; optional external hook bridge.

- [ ] **H01 [CFG] Define hook configuration.** Represent event matchers, command/MCP handlers, platform variants, deadlines, context limits, and background execution.
- [ ] **H02 [CFG] Map prompt and session hooks.** Evaluate UserPromptSubmit, SessionStart, SessionEnd, Stop, and Interrupt separately against Vidbyte before/after-run semantics.
- [ ] **H03 [CFG] Map tool and approval hooks.** Translate supported PreToolUse, PermissionRequest, and PostToolUse decisions/rewrites; reject unsupported response fields.
- [ ] **H04 [CFG] Map compaction/subagent hooks.** Support PreCompact, PostCompact, SubagentStart, and SubagentStop with their distinct IDs and lifetimes.
- [ ] **H05 [V] Specify trust and failure behavior.** Account for hook trust, multiple concurrent matches, timeouts, unavailable MCP tools, and fail-open native paths before using hooks for mandatory policy.

Completion evidence: Each supported middleware mapping is proven at its actual decision point; observational events are never described as enforcement.

<a id="k"></a>

## K: Skills, plugins, and connectors

Evidence: [S13](sources.md#s13), [S14](sources.md#s14), [S02](sources.md#s02). Implementation seam: Proposed CodexSkillTranslator and extension discovery records.

- [ ] **K01 [P] Discover and refresh skills.** Expose skill listing, per-cwd roots, process-local extra roots, change notifications, and enable/disable configuration.
- [ ] **K02 [V] Translate Vidbyte skills.** Map Vidbyte skill content and explicit selection to native discovery/input while retaining scripts/resources and source provenance.
- [ ] **K03 [V] Package reusable capabilities.** Define how related skills, hooks, and MCP tools become a distributable plugin; do not claim runtime registration from prose alone.
- [ ] **K04 [P] Inspect connector availability.** Expose installed/enabled/callable state and tool summaries with account and policy limits.
- [ ] **K05 [E] Track plugin API readiness.** Keep plugin list/read/install/uninstall on a research backlog while official docs prohibit production use; separate marketplace mutations and explicit installation authority.

Completion evidence: Instruction loading, catalog configuration, and executable integration are distinct and version-gated.

<a id="a"></a>

## A: Authentication and model discovery

Evidence: [S01](sources.md#s01), [S16](sources.md#s16), [S18](sources.md#s18), [S02](sources.md#s02). Implementation seam: Proposed CodexAccountManager and CodexModelCatalog.

- [ ] **A01 [N] Expose account state.** Wrap account() and identify the auth/access mode relevant to execution.
- [ ] **A02 [N] Support login lifecycles.** Wrap API-key, browser, and device-code login, pending completion/cancellation, and logout in separate account operations.
- [ ] **A03 [N] Discover models dynamically.** Wrap models() and expose supported effort/input capabilities rather than hard-coding a universal menu.
- [ ] **A04 [P] Inspect provider and rate limits.** Version-gate provider capability bounds and account limit events for admission decisions.
- [ ] **A05 [V] Validate model/service choices.** Check model, effort, modality, and service-tier compatibility; distinguish subscription credits from API billing.

Completion evidence: Callers can discover supported choices without exposing secrets or assuming every account has the same capabilities.

<a id="g"></a>

## G: Typed configuration and precedence

Evidence: [S03](sources.md#s03), [S04](sources.md#s04), [S05](sources.md#s05), [S12](sources.md#s12). Implementation seam: Extend Codex settings dataclasses and content translator.

- [ ] **G01 [CFG] Add reusable profiles.** Represent current profile-file selection and effective config sources; do not generate removed legacy profile tables.
- [ ] **G02 [CFG] Type provider tuning.** Cover provider endpoints/auth references, retry/stream settings, model verbosity/context limits, and model catalogs.
- [ ] **G03 [CFG] Type tool/environment controls.** Cover web-search modes, shell environment/login behavior, writable roots, feature flags, and tool-output limits.
- [ ] **G04 [P] Inspect and edit config explicitly.** Expose effective config/requirements reads and separate atomic writes from per-run overrides.
- [ ] **G05 [V] Fix ambiguous override semantics.** Define provider-default versus explicit false/empty, raw-config collisions, and deliberate per-thread/per-turn cwd changes; the PR currently requires matching cwd values.

Completion evidence: A typed setting has a documented wire representation, scope, source, and conflict rule.

<a id="n"></a>

## N: Native subagents and team behavior

Evidence: [S07](sources.md#s07), [S06](sources.md#s06), [S02](sources.md#s02); vidbyte/agents/multi/. Implementation seam: Extend subagent settings; proposed CodexSubagentTranslator.

- [ ] **N01 [CFG] Expand role contracts.** Use typed role descriptions/config references, validate resources, and document inherited versus role-specific settings.
- [ ] **N02 [V] Normalize live subagent activity.** Track child identity, state, progress, outcomes, and parent lineage throughout the run.
- [ ] **N03 [V] Define delegation boundaries.** Distinguish Codex-decided spawning from Vidbyte-created worker threads; do not invent a public spawn_agent SDK method.
- [ ] **N04 [V] Coordinate child lifetimes.** Define waits, cancellation, partial failures, concurrency quotas, and cleanup in the outer orchestration layer.
- [ ] **N05 [V] Translate team handoffs.** Map AgentTransfer, TaskLedger reports, and Handoff context into explicit worker requests and validated return contracts.

Completion evidence: Role configuration and observed activity are distinguished from deterministic Vidbyte scheduling.

<a id="o"></a>

## O: Tracing, accounting, and speed

Evidence: [S02](sources.md#s02), [S05](sources.md#s05), [S18](sources.md#s18); vidbyte/trace/ and vidbyte/agents/pricing/. Implementation seam: Proposed CodexTraceTranslator and CodexUsageTranslator.

- [ ] **O01 [V] Create trace spans.** Translate thread/turn/tool/subagent lifecycles into TraceOption/TracerBase spans with provider correlation.
- [ ] **O02 [V] Normalize usage accurately.** Map cached/input/output/reasoning totals into UsageTracker; distinguish cumulative thread totals from per-turn usage.
- [ ] **O03 [V] Report cost honestly.** Use actual available billing data or explicitly labeled estimates; service tier and token counts are not a hard dollar budget.
- [ ] **O04 [V] Measure runtime performance.** Record startup latency, first event/text, tool time, total turn time, and interruption latency with AgentSpeed-compatible semantics.
- [ ] **O05 [CFG] Integrate telemetry controls.** Model OTel/exporter/feedback settings, payload redaction, retention, and user consent independently of model context.

Completion evidence: One native operation creates one accounting record; trace hierarchy preserves provider IDs without leaking payloads.

<a id="b"></a>

## B: Budgets, failures, and recovery

Evidence: [S02](sources.md#s02); vidbyte/agents/settings/ and vidbyte/sessions/failure/. Implementation seam: Extend FailureCode handling; proposed CodexRunPolicy.

- [ ] **B01 [V] Translate time limits.** Map wall-clock deadlines to owned interruption and cleanup; expose interrupted/unknown state when completion cannot be confirmed.
- [ ] **B02 [V] Define budget semantics.** Distinguish external token/cost admission checks from provider-enforced ceilings; reject unsupported exact inner-loop iteration promises.
- [ ] **B03 [V] Expand failure classification.** Cover authentication, rate limits, config, approvals, callback, stream, disconnect, cancellation, and protocol-version failures.
- [ ] **B04 [V] Make retry state-aware.** Identify whether a turn started or a tool executed before reconnecting/retrying; surface indeterminate outcomes.
- [ ] **B05 [V] Translate fallback policies.** Apply AgentFallbackSettings between safe native lifecycle boundaries, carrying state/provenance and declaring cross-provider portability limits.

Completion evidence: Recovery reconciles native state before retry; a timeout cannot silently duplicate a side effect.

<a id="v"></a>

## V: Composition, configuration, and evaluation

Evidence: [S01](sources.md#s01); vidbyte/config/, pipelines/, workflows/, harnesses/, evals/. Implementation seam: Proposed CodexAgentBinding plus registry/config integration.

- [ ] **V01 [V] Bridge generic AgentInput.** Convert Vidbyte prompt/context/metadata to CodexRunInput; design media input separately because the current AgentInput has no media field.
- [ ] **V02 [V] Register declarative construction.** Teach YAML/config/registries how to build typed Codex agents and reject unsupported settings.
- [ ] **V03 [V] Integrate pipelines and workflows.** Provide explicit bindings for sequential, parallel, conditional, map-reduce, and state-machine execution.
- [ ] **V04 [V] Support harness trajectories.** Map run artifacts/checkpoints to Harness records and reproducible input/config/environment snapshots.
- [ ] **V05 [V] Add provider-aware evaluations.** Evaluate output schemas, tools, approval decisions, failure recovery, and completion criteria; distinguish replayed evidence from deterministic reruns.

Completion evidence: A supported pipeline/workflow/harness can invoke the adapter through its real input contract and assess both output and behavior.

<a id="z"></a>

## Z: Advanced protocol and product integrations

Evidence: [S02](sources.md#s02), [S17](sources.md#s17), [S19](sources.md#s19), [S20](sources.md#s20). Implementation seam: Proposed optional app-server extension modules.

- [ ] **Z01 [P] Expose native goals and reviews.** Model goal set/get/clear and review/start with their outcomes; do not equate a persisted goal record with an implemented Vidbyte scheduler.
- [ ] **Z02 [P] Manage command terminals.** Wrap sandboxed command execution, stdin, PTY resize, output, and termination; separately gate experimental background-terminal controls.
- [ ] **Z03 [P] Evaluate filesystem operations.** Assess app-server file access/watch APIs against Vidbyte filesystem backends; independently validate paths and the operation's real enforcement boundary.
- [ ] **Z04 [E] Assess remote/host capabilities.** Investigate configured remote environments and unsandboxed process APIs separately; desktop computer-use, recording, or realtime features need their own proven integration surface.
- [ ] **Z05 [P] Plan explicit migration tooling.** Evaluate externalAgentConfig detect/import and progress reporting for selected settings, skills, and sessions; handle partial/asynchronous imports and preserve originals.

Completion evidence: Every extension declares availability, transport/schema requirements, and authority; desktop features do not imply Python support.

## Dependency order

These waves are a recommended decomposition, not permission to implement the entire backlog.

1. **Contracts and connection ownership:** C01-C05, L01-L05. Establish provider capability checks and shared data/operation contracts.
2. **Interactive execution and visibility:** T01-T05, R01-R05, O01-O05. A live turn handle enables reliable intervention, tracing, and subsequent policy work.
3. **User capabilities and enforcement:** U01-U05, M01-M05, P01-P05, H01-H05. Prefer a supported MCP bridge; evaluate dynamic tools separately.
4. **Durable and collaborative work:** S01-S05, F01-F05, D01-D05, X01-X05, N01-N05. Define native versus Vidbyte state and filesystem ownership first.
5. **Product integration:** A01-A05, G01-G05, K01-K05, B01-B05, V01-V05. Authentication discovery may move earlier if required by deployment.
6. **Optional deep integrations:** Z01-Z05 and gated K05. Select only features the product needs and the runtime can support.

## Hard boundaries and non-goals

- Codex continues to own its internal model/tool loop. An external event stream is not a hook before every model invocation.
- A native thread fork branches conversation state. Git worktree isolation and file rollback are separate features.
- Prompt instructions are not hard policy. Mandatory enforcement must use a real authorization boundary and account for native fail-open paths.
- Current docs deprecate `thread/rollback`; do not add it as the default recovery primitive. Use explicit branch/history design and separately owned file recovery.
- Current docs say not to use plugin list/read/install/uninstall in production. K05 is readiness tracking, not a shipping recommendation.
- `thread/shellCommand` and experimental `process/spawn` run outside the thread sandbox; they are not interchangeable with sandboxed command execution.
- Record & Replay is a desktop workflow, not deterministic SDK event replay. Desktop computer-use or voice availability does not prove a Codex Python SDK API.
- Provider token budgets, outer deadlines, monetary estimates, and hard limits are different contracts. No exact general inner-loop iteration or dollar ceiling is established by this roadmap.
- Typed config passthrough cannot by itself make a Vidbyte abstraction work. For semantic mappings and concrete caveats, read [translation-map.md](translation-map.md).

## Maintenance

Refresh the PR/merge status, baseline commit, SDK version, and relevant official pages before selecting work. Update the affected source and checkbox together when an API becomes stable, is removed, or changes shape. Evidence comes from [sources.md](sources.md); facts not established there remain implementation questions.
