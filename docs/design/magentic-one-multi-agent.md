# Design Doc: Magentic-One-Inspired Multi-Agent Orchestration

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-12
**Last Updated:** 2026-07-12

---

## 1. Overview

Add a first-class `MultiAgent` under `vidbyte/agents/multi/`. Like `BaseAgent`, it is an SDK agent that can be run, forked, registered, exposed as a tool, or placed in a string pipeline. Unlike `BaseAgent`, it owns a team: one orchestrator controls a dynamic sequence of worker-agent calls against a shared, run-local `TaskLedger`.

The control loop is adapted from [Magentic-One](https://arxiv.org/abs/2411.04468): an outer loop creates or revises a plan and task ledger, while an inner loop assesses progress, chooses one worker, gives that worker a bounded assignment, records the result, and detects stalls. Repeated failure or lack of progress returns control to the outer loop for reflection and replanning. Completion and all resource limits are enforced by code, not left solely to a model prompt.

Vidbyte extends the paper's natural-language ledgers with explicit SDK records for goals, subtasks, dependencies, owners, statuses, evidence, blockers, attempts, next actions, decisions, and ordered events. This extension is intentional: those fields are requested product behavior, not a claim about the paper's exact data structure.

The central API principle is controlled information flow. Developers may replace the orchestrator as a whole and configure an `AgentTransfer` for every worker. A transfer defines the exact `str` or `AgentInput` delivered to a worker, may gate dispatch through a fail-closed approval/policy callback, converts the worker's `AgentMessage` into a proposed `AgentReport`, and may validate/filter that report before commit. The default transfer sends only the selected task's identity, goal, acceptance criteria, instruction, and explicitly supplied JSON-safe payload. It never broadcasts the whole ledger, other workers' messages, or team history. Only the controller mutates the authoritative ledger; orchestrators and workers receive structurally read-only snapshots or developer-selected projections.

---

## 2. Goals & Non-Goals

### Goals

- Introduce `MultiAgent(BaseAgent)` as the standard agent-level facade for an orchestrated team.
- Provide a public `TaskLedger` with run-local goals, paper-inspired facts and plan state, typed task records, evidence, blockers, attempts, owners, statuses, and next actions.
- Provide a replaceable `MultiAgentOrchestrator` protocol and a useful model-backed `MagenticOneOrchestrator` default.
- Implement the paper-inspired plan, act, assess, stall-detect, replan, and finalize loop with finite limits.
- Dispatch exactly one worker per orchestration round in v1 so the ledger has an unambiguous mutation order.
- Give developers fine-grained control over every worker boundary through pre-dispatch gates, request builders, report parsers, and post-response validators/filters.
- Make developer callbacks support synchronous or asynchronous implementations without requiring inheritance.
- Keep the ledger mutation authority in controller code; models may propose plans, decisions, and reports but cannot mutate shared state directly.
- Preserve completed tasks and their evidence across replans while superseding obsolete unfinished work.
- Distinguish semantic task attempts from low-level invocation retries and default invocation retries to zero.
- Preserve the normal agent experience: `run`, `arun`, `receive`, `behavior`, `card`, `fork`, `as_tool`, registries, and pipelines.
- Isolate the caller's worker instances with per-run forks, preserve their inner-loop context, and reset selected forks after a replan by default.
- Add semantic tracing for orchestration, worker dispatch, ledger mutation, replanning, and finalization without recording raw payloads by default.
- Fail explicitly when v1 functionality cannot be represented safely, especially durable `Session` persistence and non-serializable default transfer payloads.
- Add a visible, overrideable prompt family for the four orchestration phases without adding a runtime dependency on AutoGen.
- Follow current `origin/main` conventions: Python 3.11+, frozen slotted public dataclasses, Pydantic 2 structured outputs, SDK error types, explicit exports, package READMEs, and skill documentation.

### Non-Goals

- Do not claim an exact reproduction of Magentic-One. Vidbyte combines the paper's task/progress working memory into one typed ledger plus events and adds product-specific fields.
- Do not ship the paper's fixed WebSurfer, FileSurfer, Coder, or terminal team. Developers supply ordinary Vidbyte agents with their own tools and models.
- Do not add parallel or batched worker dispatch in v1. Dynamic fan-out introduces merge, conflict, cancellation, and stale-revision semantics that deserve a separate design.
- Do not change pipeline source code. Pipelines remain fixed, stateless, string-in/string-out composition.
- Do not implement this as a new `AgentRuntimeType` or build it on the actor mailbox runtime. That runtime is an inner agent execution topology and has no task-ledger contract.
- Do not replace `AggregateAgent`; aggregate fan-out/synthesis and ledger-based dynamic delegation solve different problems.
- Do not replace deterministic workflow/state-machine primitives. A model-directed team chooses its next action dynamically; a code-declared graph enforces predefined transitions.
- Do not implement distributed workers, remote queues, cross-process locking, networking protocols, or durable job scheduling.
- Do not implement nested `MultiAgent` teams as workers in v1. `as_tool()` remains available for deliberate composition, but recursive team participation is not a supported orchestration contract yet.
- Do not implement durable team session save/resume, cold restore, or ledger rehydration in v1. The current `RunState` cannot serialize live workers, orchestrator objects, or callback transfers.
- Do not promise rollback of filesystem, browser, network, tool, or other external side effects when a task fails or a plan is superseded.
- Do not silently retry potentially irreversible worker calls. Invocation retries are opt-in and require caller-owned idempotency or approval controls.
- Do not add a new dependency on AutoGen or copy its prompt text. The SDK will implement the pattern using existing Vidbyte primitives and newly authored prompts.
- Do not remove or rename the existing legacy multi-agent/aggregate dataclasses in `vidbyte/lib/dataclasses/multi_agent.py`.
- Do not add test files or verification scripts in this no-tests workflow. Implementation will still run existing checks and ephemeral inline smoke commands.

---

## 3. Background & Context

### Magentic-One behavior being adapted

The [Magentic-One paper](https://arxiv.org/html/2411.04468) describes a lead Orchestrator that plans, tracks progress, assigns work to specialized agents, detects loops or lack of progress, and revises its plan. Its outer loop maintains a Task Ledger containing given/verified facts, facts to look up, facts to derive, educated guesses, and a plan. Its inner loop maintains a Progress Ledger that asks whether the task is complete, whether the team is looping, whether progress was made, which agent should act next, and what instruction that agent should receive. One worker acts at a time. A stall counter sends execution back to the outer loop for reflection and replanning, and parameterized termination conditions such as maximum attempts or time bound the run.

The paper reports that common failures include persistent inefficient actions and insufficient verification before completion. Those findings motivate deterministic stall accounting, finite attempts, an explicit distinction between submitted and verified evidence, optional report validators, and a completion gate in this design. The safe defaults improve inspectability but do not prove a worker's answer correct; correctness still requires a developer verifier, trusted deterministic check, or completion predicate. The findings also do not establish that this architecture is optimal for every Vidbyte workload.

The [official AutoGen Magentic-One guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/magentic-one.html) confirms the outer Task Ledger / inner Progress Ledger shape and warns that browser, code, and file agents need isolation, least privilege, monitoring, human oversight, and defenses against prompt injection. The [reference API](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.teams.html#autogen_agentchat.teams.MagenticOneGroupChat) exposes finite turn and stall limits. The implementation is useful prior art, but this feature will not import it.

Two information-flow choices deliberately diverge from the paper and [official orchestration implementation](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_magentic_one/_magentic_one_orchestrator.py). Those implementations synchronize participants by broadcasting team messages, while Vidbyte defaults to assignment-only projection through `AgentTransfer`. The paper also resets worker context/state after every plan update; Vidbyte follows that default but permits an explicit `reset_on_replan=False` for domain cases that need continuity.

Magentic-One also has fixed orchestration cost and latency, and the paper notes that extra coordination can create more opportunities for failure on simple work. `MultiAgent` is therefore intended for complex, open-ended tasks that benefit from planning/recovery—not simple, deterministic, or latency-sensitive calls that a `BaseAgent`, tool, pipeline, or workflow can handle directly.

### Repository audit

The design targets `origin/main` at `d575a3f`, not the stale checked-out feature branch. The following current SDK boundaries materially shape the design:

- `BaseAgent` is the single-actor abstraction. It owns model/provider execution, tools, middleware, output contracts, context, tracing, handoff, and agent-native session hooks.
- `BaseAgent.fork(AgentForkSettings)` safely clones base-agent tools, runtimes, MCP configs, context settings, tracing, and output schemas, but its generic `AgentForker` constructs a plain `BaseAgent`. Specialized subtypes must override it; `AggregateAgent` does, while other subtypes may silently erase behavior. `AgentBinding.fork_factory` and strict subtype validation are therefore required seams.
- `AggregateAgent` is the closest subclass precedent. It overrides `generate_reply()` and `fork()` while retaining the common agent surface.
- `AgentRegistry` and `AgentCard` already provide local team discovery/capability descriptions; no second registry is necessary.
- Pipelines deliberately have no shared state, evidence, blockers, retry ledger, or dynamic replanning. A `MultiAgent` may be a pipeline node because its final boundary is still `AgentMessage`, but pipelines do not become the orchestration engine.
- The actor runtime provides mailbox-based point-to-point and broadcast execution inside one agent runtime. It does not provide task planning, ledger ownership, evidence, completion gates, or typed transfer adapters, and the new subsystem must remain independent of it.
- `vidbyte/lib/dataclasses/multi_agent.py` already holds aggregate and unused legacy DAG records. It is the right central home for new frozen value contracts, while `vidbyte/agents/multi/types.py` provides feature-local re-exports.
- Semantic tracing already separates aggregate, agent, runtime, session, and other components. Multi-agent orchestration warrants its own filterable `multi_agent` component.
- Sessions serialize a generic `RunState` and restore it through `BaseAgent.restore()`. That state has no discriminator or codec for a live team and its callbacks. Inherited team persistence would silently lose semantics.
- Prompt assets are catalogued and packaged through existing setuptools package-data rules. `origin/main` currently has 47 prompt enum members across 18 families even though several docs still report older totals; four new phase prompts will make the actual total 51 prompts across 19 families.

There is an older unmerged `feat/multi-agent-orchestration-strategies` branch. It was designed against an early SDK scaffold and puts several unrelated topologies under a strategy framework that is not present on current `main`. Its reusable lesson is that every loop needs finite call limits; its package and BaseAgent changes are not a viable integration base now.

A separate local design for validated state-machine workflows is also adjacent. That design makes a declared code graph authoritative. `MultiAgent` instead lets an orchestrator propose the next task dynamically within code-enforced ledger, ownership, transition, and limit rules. Neither should depend on the other.

---

## 4. Requirements

### Functional Requirements

1. `MultiAgent` must subclass `BaseAgent` and be importable from `vidbyte.agents.multi`, `vidbyte.agents`, and the root `vidbyte` package.
2. `sdk.agents.multi(...)` must construct a `MultiAgent` without changing `VidbyteSDK` construction.
3. Construction must require a non-empty unique set of worker names and one orchestrator, supplied either as a `MultiAgentOrchestrator` implementation or a `BaseAgent` wrapped by `MagenticOneOrchestrator`.
4. Workers must be supplied as `BaseAgent` instances or `AgentBinding` values that pair a worker with an `AgentTransfer`.
5. A fresh mutable `TaskLedger` must be created for every `generate_reply()` call. Mutable ledgers may never be shared between runs or forks.
6. The ledger must expose structurally read-only `TaskLedgerSnapshot` views containing the root goal, plan summary, paper-inspired fact groups, task records, next action, ordered events, revision, and metadata.
7. Each task must have a stable id, goal, optional owner, dependencies, required flag, acceptance criteria, status, explicit payload, result, evidence, blockers, attempt count, maximum attempts, next action, and metadata.
8. Construction and plan application must reject blank task ids/goals, duplicate ids, unknown owners, unknown dependencies, self-dependencies, and dependency cycles.
9. Stored task status must use `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `BLOCKED`, or `SUPERSEDED`. Readiness is derived from dependency completion rather than stored as another mutable status.
10. Only the controller-owned `TaskLedger` methods may commit mutations. Orchestrators, transfers, and workers receive frozen snapshots and return proposed values.
11. Ledger updates must be copy/validate/commit operations. A failed validation must leave the ledger and revision unchanged.
12. Every successful ledger mutation must increment the revision and append a bounded event containing safe control metadata.
13. Replanning must merge by task id, retain completed task results/evidence/attempt history, prohibit rewriting completed goals into different work, and mark omitted unfinished tasks `SUPERSEDED`.
14. A worker report may propose only `COMPLETED`, `FAILED`, or `BLOCKED`; the ledger decides the resulting authoritative transition.
15. A worker exception derived from `Exception` must become a safe failed report after opt-in invocation retries are exhausted. `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and other control-flow `BaseException` values must propagate.
16. Failed semantic attempts must increment the task attempt counter. Exhausting a task's maximum attempts must block that task and make replanning eligible.
17. Low-level invocation retry count must be configured separately per transfer and default to zero. Starting a dispatch increments the semantic task attempt exactly once; retries inside that same dispatch must not increment it again.
18. The default transfer request builder must send only task id, goal, owner, acceptance criteria, instruction, attempt, and explicit payload. It must never include the full ledger, worker histories, other tasks' evidence, or other agents' messages.
19. The default transfer builder must deterministically encode strings and JSON-safe values. For any other payload it must raise `AgentTransferError` directing the developer to supply a custom builder; it must not call arbitrary-object `repr()` or `str()`.
20. A custom request builder must be able to return either `str` or `AgentInput` and may be synchronous or asynchronous.
21. A custom report parser must receive the worker reply, dispatch, and structurally read-only ledger snapshot; return an `AgentReport`; and may be synchronous or asynchronous.
22. The default report parser must treat a non-blank worker reply as an accepted completed result and unverified evidence sourced to that worker. A blank reply must be a failed report. Documentation must state that this structural acceptance is not correctness verification.
23. Each run must fork every worker with history excluded by default. A run-local fork may preserve context across inner-loop calls; transfers control whether it is reset on replan and may supply additional `AgentForkSettings`.
24. The caller's original worker instances must never receive orchestration messages unless an explicit future API opts into that behavior.
25. `MultiAgentOrchestrator` must define asynchronous `plan`, `decide`, and `replan` operations over a structurally read-only `OrchestrationContext`, `finalize` over `FinalizationContext`, synchronous `fork()` for run isolation, and asynchronous `aclose()` for owned-resource cleanup.
26. The concrete `MagenticOneOrchestrator` must use a compatible schema-free manager `BaseAgent`, the four catalog phase prompts, phase-specific structured-output schemas for plan/decision/replan, and plain-text finalization.
27. Developers must be able to replace every default phase prompt, the orchestration-context renderer, and the finalization-context renderer or replace the entire orchestrator implementation.
28. The default context renderer must use explicit tagged sections and safe deterministic rendering. Prompt templates must not interpolate arbitrary user content through Python `.format()` placeholders.
29. Invalid structured orchestrator output must be re-requested only up to `orchestrator_parse_retries`, then raise `MultiAgentExecutionError` with phase/round details but no raw credentials or unbounded payloads.
30. If the team has exactly one worker, an omitted owner may resolve deterministically to it. Otherwise, the controller must reject unknown/missing owners instead of guessing.
31. The initial outer-loop action must call `plan()` and atomically apply its tasks and fact state.
32. Each inner-loop round must call `decide()` and accept exactly one of `DELEGATE`, `REPLAN`, or `FINISH`.
33. One `DELEGATE` decision may start at most one dependency-ready, nonterminal task and invoke exactly one named worker.
34. Invalid task selection, owner selection, dependency state, or no-op decisions must be recorded as rejected decisions and count as lack of progress rather than mutating the ledger.
35. Meaningful progress must be defined by code as a task-status transition, newly committed evidence, or a newly introduced valid task. Repeated text alone must not count as progress.
36. Lack of progress, a loop signal, a failed/blocked report, or a rejected decision must increase the stall counter. Meaningful progress must reduce the counter toward zero.
37. Reaching `replan_after_stalls` must invoke `replan()`, merge the returned plan, reset the stall counter, and refresh run-local worker forks whose transfers request reset-on-replan.
38. `FINISH` must be accepted by default only when every required task is complete, dependencies are satisfied, and the optional verified-evidence requirement and developer completion predicate pass.
39. `allow_partial_finish=True` may accept an orchestrator's explicit partial answer, but the result must say it is partial and must not report successful completion.
40. `max_rounds`, `max_replans`, task attempts, orchestrator parse attempts, per-call timeouts, and optional whole-run timeout must be validated and enforced by controller code.
41. On round, replan, or unrecoverable-work limits, `return_partial_on_limit=True` must call `finalize()` with the terminal snapshot and return the best available answer with an explicit stop reason. A consumed whole-run timeout may return only an already captured nonblank orchestrator candidate. When partial returns are disabled or no safe timeout candidate exists, the controller must raise `MultiAgentExecutionError`.
42. `generate_reply()` must preserve BaseAgent's `str | AgentInput`, `context`, `history`, `recipient`, and `**options` call contract and return a normal `AgentMessage` whose content is the final answer. Caller history/context is available to a custom orchestrator renderer but is never forwarded to workers by default.
43. `generate_reply()` must update `history`, `last_prompt`, `last_reply`, `last_result`, `last_ledger`, and `_active_prompt` consistently and close traces on success, ordinary failure, and cancellation.
44. The final `AgentMessage.metadata["multi_agent"]` must expose the stop reason, completion flag, rounds, replans, final ledger revision, and structurally read-only result/snapshot references without pretending arbitrary payloads are JSON-serializable.
45. `MultiAgent.card()` must describe the team and expose safe worker capability summaries without exposing worker system prompts, payloads, secrets, or live objects; the facade's own system prompt remains part of the existing `AgentCard` contract.
46. `MultiAgent.fork(settings)` must preserve the subtype, fork the orchestrator/worker agents, never share a ledger, support only documented safe `AgentForkSettings` overrides, and reject unsupported overrides with `ConfigurationError`.
47. The inherited `arun`, `run`, `run_sequentially`, queued-prompt, `receive`, `behavior`, and `as_tool` behavior must continue to work through the overridden `generate_reply()` and subtype-preserving `fork()`. Handoff generation requires an explicit runner-backed `HandoffAgent` (or compatible `generate_handoff` implementation) through `by=`; automatic facade handoff is unsupported.
48. `MultiAgent` must declare team-level durable session persistence unsupported in v1. `persist`, `bind_session`, `export_state`, and `restore` must fail with actionable errors.
49. `Session` construction must fail before writing session state when an agent explicitly declares `session_persistence_supported = False`; ordinary `BaseAgent` behavior must remain unchanged.
50. Individual worker agents may still use existing sessions independently outside a `MultiAgent` run, but a team run must not call `_notify_session()`.
51. Tracing must include `multi_agent.run`, `multi_agent.orchestrator`, `multi_agent.worker`, `multi_agent.ledger_update`, `multi_agent.replan`, and `multi_agent.finalize` semantics under a filterable `multi_agent` component.
52. Trace attributes may include run id, phase, task id, owner, attempt, round, stall count, replan count, ledger revision, status, and stop reason. Raw prompts, payloads, evidence values, results, and worker transcripts must be excluded by default.
53. The prompt catalog must add planning, progress, replanning, and finalization prompts under one `multi_agent_orchestrator` family and expose corresponding `Prompt` enum members.
54. Public API errors must include `MultiAgentExecutionError`, `TaskLedgerError`, and `AgentTransferError`, with configuration faults continuing to use `ConfigurationError`.
55. All new source files must follow the repository's context-protocol header convention. Every function and method signature must occupy exactly one physical line, with a concise one- or two-line intent comment immediately below it.
56. Root docs, package docs, `llms.txt`, the file index, relevant SDK skills, agent/pipeline/runtime/session/forking guides, prompt counts, and the future-maintenance skill matrix must be updated coherently.
57. `TaskEvidence` must distinguish submitted evidence from developer-verified evidence. Worker/model output must be unverified by default, and `require_verified_evidence=True` must require verified evidence for every required completed task.
58. `AgentTransfer` must support an optional synchronous/asynchronous post-response validator/filter that runs after parsing and before ledger commit. It may sanitize values, add verified evidence, or return a failed/blocked report; exceptions fail closed.
59. Worker replies, tool output, webpages, files, and evidence must be treated as untrusted data. Renderers must keep them explicitly delimited, and docs must state that delimiters do not neutralize prompt injection; developers use report filters, restricted context projection, tool guardrails, and red-team evaluation for the actual trust boundary.
60. `AgentTransfer` must support an optional synchronous/asynchronous `before_dispatch` gate. Returning a blocker must prevent worker invocation and commit a blocked report; gate exceptions fail closed. This supplies a policy/human-approval seam for high-cost or irreversible work while preserving worker/tool-level approvals.
61. Each worker binding must accept an optional `fork_factory`. The default calls `agent.fork(settings)` and validates that the result preserves the worker's behavioral subtype; subtype erasure or an unsupported fork override must fail with guidance to provide a factory.
62. `MagenticOneOrchestrator` must accept an optional manager phase/fork factory. Without one it accepts only an exact `BaseAgent` with `output_schema is None`; specialized subtypes and schema-bound managers must fail construction rather than silently degrade or inherit a schema into finalization.
63. `MultiAgent.system_prompt` must be carried as `OrchestrationContext.team_instructions`. Finalization must receive a distinct terminal context containing stop reason, completion, finish decision, and latest explicit candidate answer.
64. Because the facade has no runner/tool runtime of its own, it must override team-level `add_tool`, MCP attach/builder methods, automatic handoff configuration, and runner-dependent handoff defaults to raise actionable `ConfigurationError`. Explicit `await team.handoff(..., by=handoff_agent)` remains supported.
65. After `start_task()` commits, every ordinary gate/builder/worker/parser/validator failure must be normalized into and atomically commit a safe `FAILED` or `BLOCKED` report. Cancellation/control-flow exceptions still propagate and may leave the last observable snapshot in progress because the run itself was aborted.
66. Snapshots are structurally read-only, not recursively immutable. Tuple/frozen-record structure and copied mapping containers cannot freeze arbitrary payload/result/evidence objects; docs must disclose aliasing and recommend immutable values or custom copy/codec policy when revision-pure values are required.
67. A consumed whole-run timeout must skip model finalization. With partial returns enabled it may return only a previously captured nonblank `OrchestratorDecision.final_answer`; without one it raises `MultiAgentExecutionError` and preserves `last_ledger` for inspection.
68. Every run-local worker, manager, and phase fork must close owned MCP/resources in `finally`, including success, failure, timeout, replan reset, and cancellation. Bindings may supply a subtype-aware closer; custom orchestrator forks must implement `aclose()`; returning `self` is valid only for resource-free concurrency-safe implementations.

### Non-Functional Requirements

- **Control:** The controller, not an LLM response, is authoritative for valid agents, valid tasks, dependency readiness, status transitions, attempts, completion, and limits.
- **Privacy:** Information movement is deny-by-default. A worker sees only the default dispatch envelope or what its custom transfer deliberately selects. Traces omit content-bearing fields by default.
- **Reliability:** All loops and retries are finite. Ledger mutations are atomic, dependency graphs are validated, completed evidence survives replans, and ordinary worker failures are explicit state.
- **Cancellation:** Cancellation and process-level control flow propagate immediately after trace cleanup. They are never converted into task failures or retries.
- **Cost:** The default loop is sequential and makes one orchestrator decision call plus at most one worker call per round, with additional calls for initial planning, replanning, and finalization. It should not be recommended for simple or latency-sensitive work.
- **Performance:** Controller overhead must be linear in the number of tasks/events inspected per round. No new network or disk I/O occurs outside developer-supplied agents/callbacks.
- **Concurrency:** All mutable orchestration state is run-local. Like current mutable `BaseAgent` history, a single `MultiAgent` instance is not promised safe for overlapping calls; callers use `fork()` for concurrent runs.
- **Extensibility:** Custom orchestrators, transfers, ledger factories, completion predicates, and event observers use structural/callback contracts rather than requiring inheritance.
- **Compatibility:** The change is additive. Existing agents, registries, tools, pipelines, actor runtimes, aggregate agents, prompts, sessions, and legacy multi-agent dataclasses keep their behavior.
- **Packaging:** Existing setuptools discovery and package-data globs must include the new Python package and nested prompt assets without a `pyproject.toml` change.
- **Security:** The SDK cannot make unsafe worker tools or untrusted content safe. Documentation must require caller-owned sandboxing, least privilege, dispatch/tool approvals for irreversible actions, restricted context projection, prompt-injection filtering/red-teaming, and idempotency before enabling retries.
- **Observability:** The frozen final result structure, ordered ledger events, and semantic spans must make ownership, attempts, stalls, replans, and termination inspectable without requiring raw transcript capture.
- **Documentation:** Documentation must clearly distinguish paper behavior from Vidbyte extensions and distinguish MultiAgent from pipelines, actor runtime, AggregateAgent, and deterministic workflows.
- **Verification:** No new tests or persistent verification scripts are added by this workflow. Existing repository tests, compile/import checks, inline fake-agent smoke cases, and wheel inspection remain required before a later PR is opened.

---

## 5. High-Level Design

The feature has five cooperating layers:

1. `MultiAgent` is the BaseAgent-compatible team facade and owns one run at a time.
2. `MagenticOneOrchestrator` (or a developer implementation of `MultiAgentOrchestrator`) proposes plans, next actions, replans, and the final answer.
3. `TaskLedger` is the sole mutable structural authority for task/fact/event state and gives all collaborators structurally read-only snapshots.
4. `AgentBinding` and `AgentTransfer` define each worker boundary, including exact request construction, report parsing, fork behavior, timeouts, and opt-in invocation retries.
5. Central enums/dataclasses, semantic tracing, prompt assets, and public exports make the behavior inspectable and reusable.

```text
caller: str | AgentInput
          |
          v
+----------------------- MultiAgent(BaseAgent) -----------------------+
| create run id, fresh TaskLedger, and isolated run-local workers      |
|                                                                      |
|  OUTER LOOP                                                          |
|  +---------------------+        read-only context                    |
|  | MultiAgentOrchestrator | <-------------------------------+        |
|  | plan / replan / final  |                                 |        |
|  +-----------+-----------+                                 |        |
|              | proposed plan                               |        |
|              v                                             |        |
|  +---------------------+  validate + atomic commit          |        |
|  |     TaskLedger      |------------------------------------+        |
|  +----------+----------+                                             |
|             | read-only snapshot                                     |
|             v                                                        |
|  INNER LOOP: decide -> validate -> one dispatch -> report -> commit  |
|             |                                                        |
|             v                                                        |
|  AgentBinding(owner)                                                 |
|  +-------------------- AgentTransfer -----------------------------+  |
|  | request_builder(dispatch, snapshot) -> str | AgentInput         |  |
|  | report_parser(reply, dispatch, snapshot) -> AgentReport         |  |
|  +---------------------------+-------------------------------------+  |
|                              v                                        |
|                     isolated worker BaseAgent                         |
|                                                                      |
|  progress -> continue; stalls/failure -> replan; complete/limit ->   |
|  finalize -> MultiAgentResult -> AgentMessage                         |
+----------------------------------------------------------------------+
```

The ledger is "shared" as the single source of truth, not as a globally mutable object passed to every model. The orchestrator reads a rendered snapshot. A transfer may select any snapshot data for its worker, but the default does not. Workers propose reports; the controller validates and commits them.

This design intentionally keeps execution serial. A ledger revision therefore has a single writer and a total event order. If parallel dispatch is added later, each dispatch will need a base revision plus explicit optimistic-conflict and evidence-merge rules.

---

## 6. Detailed Design

### 6.1 Public Enums and Structurally Read-Only Value Contracts

**File(s):** `vidbyte/lib/enums/multi_agent.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/dataclasses/multi_agent.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/__init__.py`, `vidbyte/agents/multi/types.py`
**Type:** New enum file; modified central exports; new feature re-export file

#### What it does

Defines the stable, data-only language shared by the facade, controller, orchestrator, ledger, transfers, traces, and caller. Public records use `@dataclass(frozen=True, slots=True)` and `Mapping`/tuple fields. `TaskLedger` itself is the deliberate mutable exception and lives in the feature package.

#### Interface / API

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"

class OrchestratorAction(str, Enum):
    DELEGATE = "delegate"
    REPLAN = "replan"
    FINISH = "finish"

class MultiAgentStopReason(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    MAX_ROUNDS = "max_rounds"
    MAX_REPLANS = "max_replans"
    TIMEOUT = "timeout"
    UNRECOVERABLE = "unrecoverable"

@dataclass(frozen=True, slots=True)
class TaskEvidence:
    source: str
    value: Any
    kind: str = "output"
    verified: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class TaskBlocker:
    code: str
    message: str
    retryable: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    goal: str
    owner: str | None = None
    depends_on: tuple[str, ...] = ()
    required: bool = True
    acceptance_criteria: tuple[str, ...] = ()
    payload: Any = None
    max_attempts: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    goal: str
    owner: str | None
    status: TaskStatus
    depends_on: tuple[str, ...]
    required: bool
    acceptance_criteria: tuple[str, ...]
    payload: Any
    result: Any
    evidence: tuple[TaskEvidence, ...]
    blockers: tuple[TaskBlocker, ...]
    attempts: int
    max_attempts: int
    next_action: str | None
    metadata: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class LedgerEvent:
    index: int
    kind: str
    revision: int
    task_id: str | None = None
    owner: str | None = None
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class TaskLedgerSnapshot:
    run_id: str
    goal: str
    plan_summary: str
    verified_facts: tuple[str, ...]
    facts_to_find: tuple[str, ...]
    facts_to_derive: tuple[str, ...]
    educated_guesses: tuple[str, ...]
    tasks: tuple[TaskRecord, ...]
    next_action: str | None
    events: tuple[LedgerEvent, ...]
    revision: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class OrchestratorPlan:
    plan_summary: str
    tasks: tuple[TaskSpec, ...]
    verified_facts: tuple[str, ...] = ()
    facts_to_find: tuple[str, ...] = ()
    facts_to_derive: tuple[str, ...] = ()
    educated_guesses: tuple[str, ...] = ()
    next_action: str | None = None
    rationale: str = ""

@dataclass(frozen=True, slots=True)
class OrchestratorDecision:
    action: OrchestratorAction
    task_id: str | None = None
    owner: str | None = None
    instruction: str | None = None
    payload: Any = None
    next_action: str | None = None
    final_answer: str | None = None
    loop_detected: bool = False
    progress_made: bool = False
    rationale: str = ""

@dataclass(frozen=True, slots=True)
class AgentDispatch:
    run_id: str
    base_revision: int
    task_id: str
    owner: str
    goal: str
    acceptance_criteria: tuple[str, ...]
    instruction: str
    payload: Any
    attempt: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class AgentReport:
    task_id: str
    status: TaskStatus
    result: Any = None
    evidence: tuple[TaskEvidence, ...] = ()
    blockers: tuple[TaskBlocker, ...] = ()
    next_action: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class OrchestrationContext:
    request: AgentInput
    team_instructions: str
    team: tuple[AgentCard, ...]
    ledger: TaskLedgerSnapshot
    settings: MultiAgentSettings
    context: BaseContext | None = None
    history: tuple[AgentMessage, ...] = ()
    round: int = 0
    replans: int = 0
    stalls: int = 0
    last_report: AgentReport | None = None

@dataclass(frozen=True, slots=True)
class FinalizationContext:
    orchestration: OrchestrationContext
    stop_reason: MultiAgentStopReason
    completed: bool
    candidate_answer: str | None = None
    finish_decision: OrchestratorDecision | None = None

@dataclass(frozen=True, slots=True)
class MultiAgentSettings:
    max_rounds: int = 20
    max_replans: int = 3
    max_task_attempts: int = 3
    replan_after_stalls: int = 3
    orchestrator_parse_retries: int = 2
    run_timeout_seconds: float | None = None
    orchestrator_timeout_seconds: float | None = None
    worker_timeout_seconds: float | None = None
    require_verified_evidence: bool = False
    allow_partial_finish: bool = False
    return_partial_on_limit: bool = True
    max_events: int = 500

@dataclass(frozen=True, slots=True)
class MultiAgentResult:
    content: str
    completed: bool
    stop_reason: MultiAgentStopReason
    ledger: TaskLedgerSnapshot
    rounds: int
    replans: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

`OrchestratorDecision.__post_init__()` enforces action-specific shape: `DELEGATE` requires task/owner/instruction, `REPLAN` may carry only replan-oriented fields, and `FINISH` may carry a candidate final answer but no dispatch target. `AgentReport.__post_init__()` accepts only `COMPLETED`, `FAILED`, or `BLOCKED`. `MultiAgentSettings.__post_init__()` validates positive bounds, nonnegative retries, and timeouts greater than zero when present.

`TaskEvidence.value`, task payload/result, and metadata intentionally allow `Any` because the caller asked to define the actual objects passed between agents. These are in-process contracts, not an implicit persistence or JSON wire format. Every boundary that must render them requires an explicit codec or a JSON-safe default. `verified=True` is trusted only because developer-owned parser/validator code set it; a worker's prose cannot promote its own evidence merely by claiming verification.

"Frozen" is structural: fields cannot be reassigned and ledger-owned sequence/mapping containers are copied into tuples and read-only mapping proxies, but an opaque value, nested mapping leaf, `BaseContext`, or `ContextManager` referenced by a field may itself be mutable. Callers must not mistake a frozen dataclass for recursive immutability.

#### Edge Cases & Error Handling

- Existing `CandidateResult`, `CandidateFailure`, `EvaluationDecision`, `DagNode`, `Verification`, `NodeState`, `ProposerSpec`, and `AggregateConfig` stay unchanged and exported.
- Ledger-owned mapping/sequence containers are copied into read-only mapping proxies/tuples on construction and commit. Opaque values nested inside them or `Any` fields are not recursively frozen or copied.
- Blank evidence sources, blocker codes/messages, and negative attempts are rejected early.
- Event history is bounded by `max_events`; the event index remains monotonic even if old events are dropped from snapshots.

---

### 6.2 TaskLedger: Single Mutable Authority

**File:** `vidbyte/agents/multi/ledger.py`
**Type:** New file

#### What it does

Owns the authoritative task/fact/event structure for exactly one run. It validates every proposed plan or report, applies updates atomically, computes readiness/completion/progress, and returns structurally read-only snapshots. The orchestrator and workers never receive this object.

#### Interface / API

```python
class TaskLedger:
    def __init__(self, *, run_id: str, goal: str, owners: Sequence[str], settings: MultiAgentSettings, metadata: Mapping[str, Any] | None = None) -> None:
        # Initialize one empty run-local ledger and validate its stable owner set.
        ...

    def apply_plan(self, plan: OrchestratorPlan, *, replan: bool = False) -> TaskLedgerSnapshot:
        # Validate and atomically commit an initial or revised plan.
        ...

    def start_task(self, dispatch: AgentDispatch) -> TaskLedgerSnapshot:
        # Mark one dependency-ready task in progress and record its attempt.
        ...

    def apply_report(self, report: AgentReport, *, owner: str) -> tuple[TaskLedgerSnapshot, bool]:
        # Commit a validated worker report and return whether state made progress.
        ...

    def record_dispatch_failure(self, task_id: str, *, owner: str, blocker: TaskBlocker, blocked: bool = False) -> TaskLedgerSnapshot:
        # Resolve one started dispatch into a safe failed/blocked terminal report.
        ...

    def record_decision_rejection(self, message: str, *, task_id: str | None = None, owner: str | None = None) -> TaskLedgerSnapshot:
        # Record a safe rejected-decision event without changing task state.
        ...

    def set_next_action(self, next_action: str | None) -> TaskLedgerSnapshot:
        # Update the controller-visible next action as one atomic ledger change.
        ...

    def task(self, task_id: str) -> TaskRecord:
        # Return one frozen task record or raise a typed unknown-task error.
        ...

    def is_ready(self, task_id: str) -> bool:
        # Report whether the task is pending/failed and all dependencies completed.
        ...

    def all_required_complete(self, *, require_verified_evidence: bool = False) -> bool:
        # Evaluate the default deterministic completion gate.
        ...

    def snapshot(self) -> TaskLedgerSnapshot:
        # Return fresh frozen containers while preserving explicitly opaque values.
        ...
```

#### Logic / Algorithm

1. `apply_plan()` builds a candidate task map and validates all fields, owners, dependencies, and cycles before changing live state.
2. The initial plan creates all tasks as `PENDING` with per-task `max_attempts` falling back to settings.
3. A replan merges tasks by id. Completed tasks are copied verbatim. Compatible unfinished tasks keep attempts/evidence/blockers; changed owner, next action, dependencies, and metadata may be updated. Omitted unfinished tasks become `SUPERSEDED`. New tasks are added pending.
4. Reusing a completed id for a different goal, owner, dependencies, or acceptance criteria raises `TaskLedgerError`. Its original payload/result/evidence are retained without attempting arbitrary-object equality; completed work cannot be rewritten by replanning.
5. `start_task()` verifies the dispatch's `base_revision`, owner, readiness, and attempts, then changes the status to `IN_PROGRESS`, increments attempts, and records dispatch. The returned snapshot has the next revision and is the snapshot supplied to the transfer.
6. `apply_report()` requires the report task id to match the dispatch and an in-progress task. `COMPLETED` stores the result/evidence and clears retryable blockers. `FAILED` stores evidence/blockers and returns to a retryable state when attempts remain. Exhaustion becomes `BLOCKED`. An explicit `BLOCKED` stays blocked until a replan changes the work.
7. `record_dispatch_failure()` is the controller's recovery path after `start_task()` when a gate, builder, worker invocation, parser, or validator fails ordinarily. It commits a safe blocker and resolves `IN_PROGRESS` to `FAILED` or `BLOCKED`, so no ordinary adapter failure strands the ledger.
8. A report makes progress only when it adds nonduplicate evidence, moves status forward, or changes a blocker/next action materially. Merely returning the same text or metadata does not reset stalls.
9. Every commit uses candidate copies, validates the complete dependency graph, then swaps internal fields, increments revision once, and appends events. An exception before the swap has no effect.
10. The snapshot orders tasks by plan order and events by index for deterministic rendering and debugging.

#### Legal Status Transitions

| From | Allowed next states | Trigger |
|---|---|---|
| `PENDING` | `IN_PROGRESS`, `SUPERSEDED` | valid dispatch; replan removes task |
| `FAILED` | `IN_PROGRESS`, `BLOCKED`, `SUPERSEDED` | retry; attempts exhausted; replan removes task |
| `IN_PROGRESS` | `COMPLETED`, `FAILED`, `BLOCKED` | committed worker report |
| `BLOCKED` | `PENDING`, `SUPERSEDED` | replan revises task; replan removes task |
| `COMPLETED` | `COMPLETED` only | immutable across replan |
| `SUPERSEDED` | terminal | replacement requires a new task id |

#### Edge Cases & Error Handling

- A replan that contains no tasks is invalid unless the current snapshot already satisfies completion.
- A required task may depend on optional tasks; those dependencies still must complete unless the replan removes the edge.
- Evidence deduplication uses value equality only when safe; otherwise distinct evidence records remain distinct.
- With `require_verified_evidence=True`, a required task's transfer must add verified evidence before committing `COMPLETED`; the default parser alone cannot satisfy that gate.
- The ledger cannot undo worker side effects. `SUPERSEDED` describes planning state, not transactional rollback.
- The public ledger deliberately has no `save()`/`load()` in v1.
- Payload, result, evidence value, and metadata leaf objects are opaque and may alias caller-owned mutable objects. Such out-of-band mutation is not a ledger revision. Callers that require revision-pure values use immutable domain records or a custom ledger/transfer codec that copies/freezes them.

---

### 6.3 AgentBinding and Developer-Controlled Transfers

**File:** `vidbyte/agents/multi/transfer.py`
**Type:** New file

#### What it does

Pairs a concrete worker with the policy for crossing that worker's boundary. This is the main fine-grained control surface: the developer determines exactly what the worker sees and exactly how its reply becomes a typed report.

#### Interface / API

```python
BeforeDispatch = Callable[[AgentDispatch, TaskLedgerSnapshot], TaskBlocker | None | Awaitable[TaskBlocker | None]]
RequestBuilder = Callable[[AgentDispatch, TaskLedgerSnapshot], str | AgentInput | Awaitable[str | AgentInput]]
ReportParser = Callable[[AgentMessage, AgentDispatch, TaskLedgerSnapshot], AgentReport | Awaitable[AgentReport]]
ReportValidator = Callable[[AgentReport, AgentDispatch, TaskLedgerSnapshot], AgentReport | Awaitable[AgentReport]]
WorkerForkFactory = Callable[[BaseAgent, AgentForkSettings], BaseAgent]
WorkerCloser = Callable[[BaseAgent], None | Awaitable[None]]

@dataclass(frozen=True, slots=True)
class AgentTransfer:
    before_dispatch: BeforeDispatch | None = None
    request_builder: RequestBuilder | None = None
    report_parser: ReportParser | None = None
    report_validator: ReportValidator | None = None
    fork_settings: AgentForkSettings = field(default_factory=AgentForkSettings)
    reset_on_replan: bool = True
    timeout_seconds: float | None = None
    max_invocation_retries: int = 0

@dataclass(frozen=True, slots=True)
class AgentBinding:
    agent: BaseAgent
    transfer: AgentTransfer = field(default_factory=AgentTransfer)
    fork_factory: WorkerForkFactory | None = None
    closer: WorkerCloser | None = None
```

`AgentTransfer.approve_dispatch()`, `build_request()`, `parse_report()`, and `validate_report()` are concrete one-line-signature methods that normalize sync/async callbacks, validate return types, and wrap callback failures in `AgentTransferError` with worker/task context.

#### Default Request Envelope

The default builder emits deterministic JSON from this bounded shape:

```json
{
  "task_id": "collect-primary-sources",
  "goal": "Collect primary sources supporting the claim",
  "owner": "researcher",
  "acceptance_criteria": ["Return at least two independent primary-source URLs"],
  "instruction": "Find two independent primary sources and report URLs.",
  "attempt": 1,
  "payload": {"claim_id": "claim-17"}
}
```

It accepts `None`, booleans, numbers, strings, lists/tuples of JSON-safe values, and mappings with string keys and JSON-safe values. Other objects fail closed. The developer may intentionally carry a file handle, Pydantic model, image reference, domain object, or selected ledger evidence by supplying a custom builder that chooses its own encoding or returns an `AgentInput` with context items.

The default parser returns `COMPLETED`, sets `result=reply.content`, and adds one `TaskEvidence(source=worker_name, value=reply.content, verified=False)`. Blank content returns `FAILED` with a retryable `empty_reply` blocker. `COMPLETED` here means the transfer accepted a structurally valid response; it is not a correctness claim. A custom parser may extract `reply.metadata["structured"]`, preserve typed values, require citations, or mark the task blocked.

An optional `report_validator` runs after parsing and before ledger commit. It is the recommended developer-owned seam for deterministic schema/citation checks, a verifier agent, content filtering, provenance validation, or prompt-injection screening. It returns the report to commit, potentially sanitized or changed to `FAILED`/`BLOCKED`. Developer-owned parser/validator code may deliberately add `verified=True` evidence; the defaults never promote trust.

An optional `before_dispatch` gate runs before request construction or worker invocation. Returning `None` approves. Returning a `TaskBlocker` prevents the call and commits a blocked report carrying that reason. An exception fails closed as `AgentTransferError`. This can pause for human approval or enforce cost/risk policy, but the SDK cannot infer which calls are irreversible; worker tool approvals and sandboxes remain necessary.

#### Worker Isolation and Retry Logic

1. At run start, each binding creates a run-local worker through its `fork_factory` or `agent.fork()` using the transfer's settings (`include_history=False` by default). Lineage is passed at invocation time rather than injected into fork settings.
2. The run-local worker is reused inside one outer-loop plan cycle so it can retain task conversation context.
3. On replan, bindings with `reset_on_replan=True` discard that fork and create a new one. The caller's original agent remains untouched.
4. `timeout_seconds` overrides the team-level worker timeout for that binding.
5. `max_invocation_retries` retries only worker invocation exceptions, not a valid `FAILED` report. The default is zero. `start_task()` records one semantic attempt for the dispatch; its low-level invocation retries are traced but do not increment that task attempt again.
6. Before a reset discards a worker and in the run's outer `finally`, the controller invokes `AgentBinding.closer` or defaults to `close_mcp_servers()` on each unique run-local worker. Cleanup is shielded long enough to attempt every resource, errors are safely traced/aggregated without skipping remaining resources, and cancellation is re-raised afterward.

The default worker fork path calls `agent.fork(transfer.fork_settings)` without injecting lineage overrides that specialized agents may reject, then verifies that the returned object is an instance of the original behavioral subtype. Correlation metadata is supplied per call through `trace_metadata`. A `HandoffAgent` or other subtype that inherits the subtype-erasing base fork fails fast unless `AgentBinding.fork_factory` deliberately reconstructs it. `AggregateAgent` works with its supported default fork but rejects incompatible custom fork settings normally; compound subtypes that own resources beyond their facade's MCP handles also supply a custom `closer`.

#### Edge Cases & Error Handling

- Duplicate worker names fail construction because owner identity must be stable.
- A subtype-erasing or incompatible worker fork fails before orchestration starts; it never silently becomes a plain `BaseAgent`.
- A gate, custom builder, parser, or validator returning an unsupported type or mismatched task id/status produces `AgentTransferError`; the controller catches that ordinary error and commits a safe failed dispatch record before continuing/replanning.
- Worker replies and their embedded tool/web/file content remain untrusted even inside tagged sections. A custom validator/filter plus minimized context projection is required when this data may be hostile.
- Callback errors never expose arbitrary payload representations in their error details.
- Retrying a side-effecting worker can duplicate effects; docs require idempotency or approvals before setting invocation retries above zero.

---

### 6.4 Orchestrator Protocol and Magentic-One Default

**File:** `vidbyte/agents/multi/orchestrator.py`
**Type:** New file

#### What it does

Separates coordination policy from the controller. A developer can implement the structural protocol with deterministic Python, another model framework, or a domain planner. The default wraps a normal `BaseAgent` and applies the paper-inspired four-phase prompt protocol.

#### Interface / API

```python
ManagerAgentFactory = Callable[[BaseAgent, str, AgentForkSettings], BaseAgent]
ManagerAgentCloser = Callable[[BaseAgent, str], None | Awaitable[None]]
OrchestrationRenderer = Callable[[OrchestrationContext], str]
FinalizationRenderer = Callable[[FinalizationContext], str]

@runtime_checkable
class MultiAgentOrchestrator(Protocol):
    def fork(self) -> MultiAgentOrchestrator:
        # Return an independent coordinator for one run or team fork.
        ...

    async def plan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Propose the initial facts, task graph, ownership, and next action.
        ...

    async def decide(self, context: OrchestrationContext) -> OrchestratorDecision:
        # Assess progress and propose one delegate, replan, or finish action.
        ...

    async def replan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Reflect on stalls/failures and propose a compatible revised plan.
        ...

    async def finalize(self, context: FinalizationContext) -> str:
        # Produce the final answer or clearly qualified best partial answer.
        ...

    async def aclose(self) -> None:
        # Release every manager/phase resource owned by this orchestrator fork.
        ...

class MagenticOneOrchestrator:
    def __init__(self, agent: BaseAgent, *, planning_prompt: str | None = None, progress_prompt: str | None = None, replanning_prompt: str | None = None, final_prompt: str | None = None, context_renderer: OrchestrationRenderer | None = None, finalization_renderer: FinalizationRenderer | None = None, parse_retries: int | None = None, manager_agent_factory: ManagerAgentFactory | None = None, manager_agent_closer: ManagerAgentCloser | None = None) -> None:
        # Bind one manager agent to visible, replaceable phase prompts and rendering.
        ...

    def fork(self) -> MagenticOneOrchestrator:
        # Fork the manager agent and preserve immutable prompt/renderer policy.
        ...

    async def aclose(self) -> None:
        # Close the run-local manager and any still-owned phase resources.
        ...
```

An explicit `parse_retries` on `MagenticOneOrchestrator` wins; `None` uses `context.settings.orchestrator_parse_retries`. The same context exposes the finite run limits to custom orchestrators and to the default `<limits>` prompt section without granting mutation access.

Without `manager_agent_factory`, construction requires `type(agent) is BaseAgent` and `agent.output_schema is None`. This deliberately rejects specialized subtypes whose inherited fork erases behavior and managers whose schema would be inherited into free-text finalization. The default creates one schema-free run-local manager, creates short-lived plan/progress/replan forks with the requested Pydantic schema, and uses the schema-free manager itself for finalization. A factory receives the source manager, phase name, and requested `AgentForkSettings`; it must preserve intended behavior and honor schema-free finalization explicitly. `manager_agent_closer` supplies subtype-aware cleanup; the default calls `close_mcp_servers()`.

#### Structured Output

Private Pydantic 2 models in `orchestrator.py` define the model-facing JSON contracts for `plan`, `decide`, and `replan`. Each structured phase calls a history-isolated short-lived manager fork with `AgentForkSettings(output_schema=<phase model>)`, prefers the provider-validated object from `AgentMessage.metadata["structured"]`, and performs one explicit local validation before translating it to public frozen dataclasses. A fenced-JSON fallback is allowed for providers that return text but cannot attach structured metadata. Invalid output is re-requested with concise schema feedback up to the configured parse bound. Every short-lived phase fork closes its MCP/resources in `finally`.

`finalize()` is deliberately free text. Its distinct `FinalizationContext` supplies team instructions, terminal reason, completion flag, the latest explicit orchestrator candidate, the accepted/premature finish decision when present, and the structurally read-only ledger context so a limit result is described as partial rather than falsely complete.

#### Prompt Construction and Fine-Grained Orchestrator Control

- Catalog prompts contain instructions only. Runtime context is appended in explicit `<request>`, `<team>`, `<ledger>`, `<last_report>`, and `<limits>` sections.
- User content is concatenated, not passed through `.format()`, so braces in prompts/payloads cannot become template placeholders.
- The default context renderer includes the facade's `team_instructions`, current request, team cards, task/control fields, fact groups, blockers, and bounded JSON-safe evidence/result summaries needed for coordination. All worker/external content stays in explicit untrusted-data delimiters; those delimiters organize context but do not neutralize hostile instructions. Non-JSON-safe values become a type-only omission marker unless a custom renderer deliberately encodes them. It excludes worker system prompts, credentials, live objects, worker histories, and caller-supplied prior history/context unless a custom renderer selects them.
- The default finalization renderer includes that bounded orchestration view plus stop reason, completion flag, candidate answer, and finish-decision rationale in separate tagged sections.
- A developer may replace any phase prompt, the normal orchestration renderer, and the terminal finalization renderer independently. Replacing the orchestrator object gives complete control over model/provider choice and all intermediate representations.
- The orchestrator receives no mutable ledger method. Even a malicious or malformed decision is only a proposal validated by the controller.

#### Decision Validation

- `DELEGATE` must identify a known task and owner, use an owner compatible with the task, and target a ready nonterminal task.
- If there is exactly one worker, a missing owner is filled deterministically. With multiple workers it is an error.
- `REPLAN` returns control to `replan()` and does not dispatch a worker in that round.
- `FINISH` is only a request. The controller's completion policy decides whether it is accepted or recorded as premature.

#### Edge Cases & Error Handling

- Manager timeouts and exhausted parse retries raise `MultiAgentExecutionError`; there is no safe team operation without a valid controller decision.
- Prompt/model stochasticity is expected. The ledger/controller guarantees structural validity, not optimal planning.
- A deterministic orchestrator can bypass prompts and Pydantic models by implementing the protocol directly.

---

### 6.5 MultiAgent BaseAgent Facade

**File(s):** `vidbyte/agents/multi/agent.py`, `vidbyte/agents/multi/__init__.py`, `vidbyte/agents/multi/README.md`, `vidbyte/agents/__init__.py`, `vidbyte/agents/client.py`, `vidbyte/__init__.py`
**Type:** New feature package; modified public exports/factory

#### What it does

Presents the team as one normal agent while owning controller state, worker bindings, lifecycle hooks, tracing, and the paper-inspired loop.

#### Interface / API

```python
LedgerFactory = Callable[[str, AgentInput, tuple[str, ...], MultiAgentSettings], TaskLedger]
CompletionCheck = Callable[[OrchestrationContext, OrchestratorDecision], bool | Awaitable[bool]]
EventHandler = Callable[[LedgerEvent, TaskLedgerSnapshot], None | Awaitable[None]]

class MultiAgent(BaseAgent):
    session_persistence_supported = False

    def __init__(self, *, name: str, system_prompt: str, orchestrator: BaseAgent | MultiAgentOrchestrator, agents: Sequence[BaseAgent | AgentBinding], settings: MultiAgentSettings | None = None, ledger_factory: LedgerFactory | None = None, completion_check: CompletionCheck | None = None, on_event: EventHandler | None = None, description: str = "", capabilities: Sequence[str] = (), agent_metadata: AgentMetadata | None = None, metadata: Mapping[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None:
        # Validate the team and initialize the BaseAgent-compatible facade.
        ...

    async def generate_reply(self, message: str | AgentInput, *, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
        # Run one fresh ledger-driven orchestration and return its final answer.
        ...

    def card(self) -> AgentCard:
        # Describe the team using safe aggregate capabilities and worker names.
        ...

    def fork(self, settings: AgentForkSettings | None = None) -> MultiAgent:
        # Rebuild an isolated team while preserving the MultiAgent subtype.
        ...

    async def handoff(self, spec: Handoff | None = None, *, by: BaseAgent | None = None) -> Handoff:
        # Generate a handoff only through an explicit HandoffAgent-compatible generator.
        ...

    @property
    def last_result(self) -> MultiAgentResult | None:
        # Return the most recent structured result for this facade.
        ...

    @property
    def last_ledger(self) -> TaskLedgerSnapshot | None:
        # Return the structurally read-only final ledger from the most recent run.
        ...
```

The facade calls `super().__init__()` only for shared identity, description/metadata, and tracing, with no provider/model, tools, MCP, output schema, or automatic handoff. Each manager/worker agent owns those capabilities normally. The override keeps BaseAgent's explicit `context`, `history`, and `recipient` call contract; those values enter `OrchestrationContext`, but the default renderer does not broadcast full history/context to workers.

Runner-dependent mutation methods are explicitly closed rather than left half-functional. `add_tool()` and public MCP attach/builder methods raise `ConfigurationError` directing the caller to configure the manager or a worker. `mcp_servers()` remains empty. `handoff()` requires `by=<HandoffAgent or compatible generate_handoff object>` and uses the existing handoff rendering over the team's final history/result; omitting/incompatible `by` fails immediately. `as_tool()` remains supported because it wraps the entire team and uses subtype-preserving `fork()`.

`AgentClient.multi(**kwargs)` lazily imports and constructs `MultiAgent`, matching `.base()`, `.handoff()`, `.continual_trace()`, and `.aggregate()`.

#### Fork Semantics

Inherited `BaseAgent.fork()` cannot be used because its `AgentForker` constructs a plain `BaseAgent`. `MultiAgent.fork()` therefore:

1. Accepts the exact `AgentForkSettings | None` signature.
2. Supports the safe fields current `AgentForkSettings` can express unambiguously: `name`, `system_prompt`, `metadata`, and explicit history inclusion/replacement.
3. Rejects runtime/tools/middleware/context/output-schema/session-state overrides that have no team-level meaning.
4. Calls the orchestrator's required `fork()` and forks every original worker. `MagenticOneOrchestrator.fork()` forks its manager; a custom immutable/stateless orchestrator may deliberately return itself only when concurrent use is safe.
5. Reuses frozen settings and configured callback/factory references but creates no ledger until the child is run; stateful callbacks remain developer-owned and must be concurrency-safe.
6. Ensures `MultiAgent.as_tool()` works because `AgentTool` receives another `MultiAgent`, not a degraded `BaseAgent`.

#### Card Semantics

The card uses the facade's name/description/system prompt plus explicitly declared team capabilities. Metadata contains a bounded list of worker names and their advertised capabilities/tool names, not raw agent metadata or prompts. This makes registry discovery useful without making the card a secret-bearing transcript.

---

### 6.6 Controller Loop, Completion, Limits, and Failures

**File(s):** `vidbyte/agents/multi/agent.py`, `vidbyte/agents/multi/ledger.py`
**Type:** New files

#### Run Algorithm

1. Normalize `str` to `AgentInput`, allocate a run id, set `_active_prompt`, and open the normal `agent.run` root trace plus a `multi_agent.run` child span.
2. Build a fresh ledger through `ledger_factory` (or `TaskLedger`), fork an independent run-local orchestrator, and build isolated run-local workers from all bindings.
3. Build an `OrchestrationContext` and call the run-local orchestrator's `plan()` under its timeout. Validate and atomically apply the plan. After every successful ledger commit, update `last_ledger` immediately so failures/timeouts expose the latest structurally read-only snapshot even when no `MultiAgentResult` is produced.
4. Enter the bounded inner loop. Increment `round` before each `decide()` call so every decision consumes budget, including invalid decisions and explicit replans.
5. For `DELEGATE`, validate task/owner/readiness; build an `AgentDispatch`; mark the task in progress; run the transfer's fail-closed dispatch gate; map an approved assignment through its request builder; invoke the run-local worker; parse and validate/filter the reply; and atomically apply the resulting report. A gate blocker skips request construction/invocation and commits a blocked report. Any ordinary error after the start commit is caught, safely summarized, and resolved through `record_dispatch_failure()`; cancellation/control-flow exceptions propagate.
6. For an invalid decision, record a rejection and increment stalls. No worker runs and no task mutates.
7. For `REPLAN`, or whenever stalls reach the threshold, call `orchestrator.replan()`, atomically merge it, increment replans, reset stalls, and refresh configured worker forks.
8. For `FINISH`, run the deterministic completion gate and optional callback. If it fails, record a premature-finish rejection and continue/replan. If it passes, set stop reason `COMPLETED`.
9. If a valid partial finish is enabled, set `completed=False` and stop reason `PARTIAL`. Every nonblank `OrchestratorDecision.final_answer` is retained in controller-local `latest_candidate` for an explicit partial/timeout fallback; worker output is never promoted implicitly.
10. If round/replan/time limits fire, either prepare an explicit partial result or raise according to `return_partial_on_limit`.
11. For every non-timeout terminal condition, call `orchestrator.finalize()` once with `FinalizationContext`; finalization owns the returned string. A consumed hard timeout skips this step and may return only `latest_candidate` when partial returns are enabled.
12. Build `MultiAgentResult`, then `AgentMessage`, and update history/last fields. Deliberately skip session notification and automatic handoff. A caller may request a later handoff with an explicit runner-backed `HandoffAgent` through `by=`.
13. In `finally`, close every unique run-local worker and the run-local orchestrator, record cleanup outcomes, close the root trace with the primary output/error, and clear `_active_prompt`. A replan closes discarded worker forks before replacing them. Cleanup runs on success, failure, hard timeout, and cancellation.
14. After a successful primary run has completed cleanup/trace closure, run the inherited bounded queued-prompt drain when configured, then return the primary reply.

#### Progress and Replanning

The controller combines the orchestrator's self-assessment with objective ledger change. `loop_detected=True` always counts against stalls. `progress_made=True` cannot override a no-op ledger update. A real task transition or new submitted evidence decreases stalls by one toward zero; a failure, block, rejected decision, loop, or no-op increments by one. Submitted evidence can demonstrate activity without being verified evidence for completion. This keeps the paper's reflective behavior while preventing a model from resetting the counter merely by claiming progress.

Replans are not destructive rewrites. Completed facts/evidence remain; unfinished obsolete tasks become `SUPERSEDED`; new work gets new ids; and worker histories reset according to transfer settings. A replan that makes no material change counts as another stall and consumes the replan budget.

#### Stop Behavior

| Condition | Default result |
|---|---|
| All required work complete and completion gate passes | `completed=True`, `COMPLETED` |
| Orchestrator explicitly finishes with `allow_partial_finish=True` | `completed=False`, `PARTIAL` |
| Round limit with partial returns enabled | `completed=False`, `MAX_ROUNDS` |
| Replan limit with partial returns enabled | `completed=False`, `MAX_REPLANS` |
| Whole-run timeout with partial returns enabled and a captured orchestrator candidate | `completed=False`, `TIMEOUT`; skip finalization |
| Required work is blocked and replanning cannot produce a viable change | `completed=False`, `UNRECOVERABLE` when partial returns are enabled; otherwise raise |
| Invalid configuration, ledger corruption, or exhausted manager parsing | raise typed error; trace closes |
| Cancellation/control-flow exception | propagate unchanged; trace closes |

A whole-run `asyncio.timeout()` cannot safely make another model call after it expires. The controller captures nonblank `OrchestratorDecision.final_answer` values as `latest_candidate`; timeout returns that value only when partial returns are enabled, otherwise it raises and leaves `last_ledger` at the latest snapshot. This avoids pretending finalization can run outside a consumed hard deadline or treating an arbitrary worker reply as a team answer.

#### Event Callback

`on_event` receives each committed `LedgerEvent` plus the latest snapshot after commit. It is fail-open telemetry for UI/progress reporting: callback errors are traced and included in result metadata without interrupting ledger control flow. Safety/approval decisions belong in the pre-commit `before_dispatch` gate, not an after-commit observer.

---

### 6.7 Durable Session Boundary

**File(s):** `vidbyte/agents/multi/agent.py`, `vidbyte/sessions/session.py`, `skills/sessions.md`
**Type:** New fail-fast overrides; narrow session guard modification; documentation update

#### What it does

Prevents a team from being attached to a persistence format that cannot restore it correctly.

`MultiAgent.persist()`, `bind_session()`, `export_state()`, and `restore()` raise an actionable `ConfigurationError` or session-specific error explaining that v1 supports structurally read-only ledger inspection/tracing but not durable team restore. `generate_reply()` never calls `_notify_session()`.

`Session.__init__()` checks `getattr(agent, "session_persistence_supported", True)` before writing metadata or binding tools. An explicit `False` raises `SessionError`; all current agents retain the default `True`. This is necessary because the existing session constructor swallows some binding errors and record-turn persistence is fail-open, which would otherwise defer or hide semantic loss.

Full support is deferred because it requires:

- A `RunState` subtype/discriminator for teams.
- Versioned serialization of ledger snapshots/settings.
- A registry or caller callback that re-supplies live manager/worker agents and transfer callables.
- `Session._restore_agent()` dispatch by state type instead of hard-coded `BaseAgent.restore()`.
- Compatibility rules for prompt/catalog/settings changes across checkpoints.

---

### 6.8 Semantic Tracing

**File(s):** `vidbyte/trace/components/agents.py`, `vidbyte/trace/components/__init__.py`, `vidbyte/trace/profiles.py`, `vidbyte/trace/controller.py`, `vidbyte/trace/README.md`
**Type:** Modified files

#### What it does

Adds `MultiAgentTrace` span factories and a dedicated `multi_agent` profile component. The controller maps `multi_agent.*` names to that component so users can enable detailed orchestration tracing independently of worker model/tool traces.

#### Span Model

- `agent.run`: normal BaseAgent-compatible root, with `strategy="multi_agent"`.
- `multi_agent.run`: team lifecycle and final stop reason.
- `multi_agent.orchestrator`: phase, round, stalls, replans, ledger revision.
- `multi_agent.worker`: task id, owner, attempt, invocation retry, status.
- `multi_agent.ledger_update`: revision transition and event kind.
- `multi_agent.replan`: old/new revision, stall count, replan count.
- `multi_agent.finalize`: completion flag and stop reason.

Every child worker already emits its own agent/model/tool spans. `run_id`, `task_id`, `owner`, and `ledger_revision` are passed through safe trace metadata for correlation. Full prompts, payloads, evidence, results, callback objects, credentials, and transcripts are never span attributes by default.

---

### 6.9 Prompt Catalog Integration

**File(s):** `vidbyte/prompts/prompts/multi_agent_orchestrator/*`, `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/README.md`, `skills/usage/import_prompt.md`
**Type:** New prompt family; modified enum/docs

#### What it does

Adds four newly authored instruction assets:

- `planning_prompt.md`: build given/verified facts, facts to look up/derive, educated guesses, task graph, owners, and next action.
- `progress_prompt.md`: answer completion/loop/progress/next-worker/next-instruction questions and emit one action.
- `replanning_prompt.md`: reflect on failure, preserve verified work, revise facts/tasks, and avoid repeating the same strategy.
- `final_prompt.md`: synthesize an evidence-grounded final or explicitly qualified partial answer.

`multi_agent_orchestrator.json` describes the family. The `Prompt` enum adds four `MULTI_AGENT_ORCHESTRATOR_*` members. The actual catalog count becomes 51 prompt members across 19 families, and all current user/contributor inventory docs are corrected. Historical design records keep their point-in-time counts.

These prompts are defaults, not hidden policy. A `MagenticOneOrchestrator` constructor override wins over catalog content, and a custom protocol implementation bypasses the family entirely.

---

### 6.10 Error Hierarchy

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified files

```python
class MultiAgentExecutionError(AgentExecutionError):
    """Raised when a team cannot produce a valid orchestration outcome."""

class TaskLedgerError(MultiAgentExecutionError):
    """Raised when a proposed ledger mutation violates task invariants."""

class AgentTransferError(MultiAgentExecutionError):
    """Raised when request/report adaptation fails at a worker boundary."""
```

`ConfigurationError` remains the type for duplicate workers, invalid settings, unsupported fork overrides, and missing required callbacks. Runtime errors carry safe details such as phase, task id, owner, attempt, round, and revision. They do not interpolate arbitrary payload/result/evidence representations.

---

### 6.11 Documentation and Maintenance Guidance

**File(s):** root/package READMEs, `llms.txt`, `artifacts/file_index.md`, SDK/usage/runtime/session/forking/pipeline skills, and `skills/vidbyte-sdk/multi-agent.md`
**Type:** New dedicated skill; modified navigation and decision guides

Documentation will include:

- A minimal team example and a fully custom transfer example.
- The outer/inner loop and every ledger field/transition.
- The default information boundary, untrusted-content/prompt-injection boundary, and non-serializable-payload failure mode.
- Submitted-versus-verified evidence, report validators/filters, and pre-dispatch human/policy gates.
- Retry versus attempt semantics, completion rules, event/tracing fields, cancellation, and side-effect warnings.
- The v1 durable-session limitation, subtype-preserving/factory fork behavior, resource cleanup, and unsupported team-level runner/tool/MCP/automatic-handoff surfaces.
- A decision table: Pipeline for fixed text wiring, Actor runtime for mailbox topology within one runtime, AggregateAgent for concurrent proposal/synthesis, MultiAgent for dynamic shared-ledger control, and workflow/state machine for code-declared transitions.
- A maintenance-matrix row requiring future MultiAgent API changes to update package exports, root docs, prompt docs/counts, tracing, sessions/forking, the file index, and the dedicated skill.

---

## 7. Data Model Changes

This change adds in-memory orchestration records but no database, migration, wire protocol, or durable session schema.

### New Stable Models

| Model | Purpose | Mutability / serialization |
|---|---|---|
| `TaskSpec` | Plan proposal for one task | Frozen; may contain arbitrary in-process payload |
| `TaskRecord` | Authoritative task state | Frozen snapshot value |
| `TaskEvidence` | Typed provenance/value plus developer-owned verification flag | Frozen; value not assumed JSON-safe |
| `TaskBlocker` | Structured reason work cannot proceed | Frozen |
| `LedgerEvent` | Ordered control-plane audit event | Frozen; bounded history |
| `TaskLedgerSnapshot` | Structurally read-only shared source-of-truth view | Frozen containers; opaque values may alias; not a persistence promise |
| `OrchestratorPlan` | Proposed initial/revised plan and paper-inspired facts | Frozen proposal |
| `OrchestratorDecision` | Proposed delegate/replan/finish action | Frozen and action-validated |
| `AgentDispatch` | Exact controller-to-transfer assignment | Frozen |
| `AgentReport` | Worker-to-controller proposed outcome | Frozen and status-validated |
| `OrchestrationContext` | Read-only manager phase context | Frozen |
| `FinalizationContext` | Terminal reason/completion/candidate context | Frozen |
| `MultiAgentSettings` | Validated finite limits/policies | Frozen |
| `MultiAgentResult` | Final answer plus terminal ledger/metrics | Frozen |

### Ownership and Lifecycle

```text
MultiAgent invocation
  owns TaskLedger (mutable, never escapes)
    creates TaskLedgerSnapshot revision 0..N (structurally read-only)
      read by orchestrator and transfers
      retained by final MultiAgentResult / last_ledger

AgentDispatch + snapshot
  -> AgentTransfer -> worker
  <- AgentTransfer <- AgentMessage
  -> AgentReport proposal
  -> TaskLedger validates/commits
```

The result may hold arbitrary caller values through payload/result/evidence. Callers that need storage or network transport must supply their own codec and schema. V1 intentionally does not put these records into `RunState`, `Checkpoint`, or session serialization.

---

## 8. API Changes

All changes are additive except for the new fail-fast check when an explicitly unsupported agent is passed to `Session`.

### Primary Imports

```python
from vidbyte import AgentBinding, AgentTransfer, MagenticOneOrchestrator, MultiAgent, MultiAgentSettings, TaskLedger
from vidbyte.agents.multi import AgentDispatch, AgentReport, MultiAgentOrchestrator, TaskLedgerSnapshot, TaskStatus
```

### Minimal Usage

```python
from vidbyte import BaseAgent, MultiAgent

manager = BaseAgent(name="manager", system_prompt="Coordinate the team carefully.", provider="openai", model_name="gpt-5")
researcher = BaseAgent(name="researcher", system_prompt="Collect primary evidence.", provider="openai", model_name="gpt-5-mini")
writer = BaseAgent(name="writer", system_prompt="Write only from supplied evidence.", provider="anthropic", model_name="claude-sonnet-4-5")

team = MultiAgent(name="research-team", system_prompt="Produce an evidence-backed report.", orchestrator=manager, agents=[researcher, writer])
reply = team.run("Compare the two approaches and cite the strongest evidence.")
print(reply.content)
print(team.last_ledger)
```

Passing a `BaseAgent` as `orchestrator` is shorthand for `MagenticOneOrchestrator(manager)`.

### Fine-Grained Transfer Usage

```python
from vidbyte import AgentBinding, AgentTransfer
from vidbyte.agents.multi import AgentInput, AgentReport, TaskEvidence, TaskStatus

async def build_writer_request(dispatch, snapshot):
    # Select only approved evidence for this writer; omit every other ledger field.
    approved = [item.value for task in snapshot.tasks for item in task.evidence if item.kind == "approved_source"]
    return AgentInput(prompt=dispatch.instruction, metadata={"task_id": dispatch.task_id, "approved_evidence": approved})

def parse_writer_reply(reply, dispatch, snapshot):
    # Preserve the writer's structured document as the authoritative task result.
    document = reply.metadata["structured"]
    return AgentReport(task_id=dispatch.task_id, status=TaskStatus.COMPLETED, result=document, evidence=(TaskEvidence(source=reply.sender, value=document, kind="draft"),))

writer_binding = AgentBinding(agent=writer, transfer=AgentTransfer(request_builder=build_writer_request, report_parser=parse_writer_reply, reset_on_replan=False))
```

### Custom Deterministic Orchestrator

Any object with the four phase methods, a run-isolating `fork()`, and resource-releasing `aclose()` can replace model-backed coordination. This enables domain code to choose owners or completion deterministically while still reusing `TaskLedger`, transfers, worker isolation, tracing, and the BaseAgent facade.

### SDK Factory

```python
sdk = VidbyteSDK()
team = sdk.agents.multi(name="team", system_prompt="...", orchestrator=manager, agents=[researcher, writer])
```

### Compatibility Notes

- `MultiAgent` works as an `AgentRegistry` member and a fixed pipeline node through its normal `AgentMessage` boundary.
- `MultiAgent.as_tool()` works because its fork preserves the subtype.
- Team-level tools/MCP and automatic handoff are rejected because the facade has no runner; configure those on manager/workers, and pass an explicit runner-backed `HandoffAgent` through `by=` for handoff generation.
- Team-level `.persist()` and `Session(team)` construction fail explicitly in v1.
- Existing agents and sessions that do not opt out are unaffected.

---

## 9. File Change Manifest

### Files to Create (15)

| File | Purpose |
|---|---|
| `docs/design/magentic-one-multi-agent.md` | Approved architecture and implementation contract |
| `vidbyte/agents/multi/__init__.py` | Stable feature exports |
| `vidbyte/agents/multi/README.md` | Package architecture, invariants, and usage |
| `vidbyte/agents/multi/agent.py` | `MultiAgent` facade and controller loop |
| `vidbyte/agents/multi/orchestrator.py` | Protocol and `MagenticOneOrchestrator` default |
| `vidbyte/agents/multi/ledger.py` | Mutable run-local ledger authority |
| `vidbyte/agents/multi/transfer.py` | `AgentBinding`, `AgentTransfer`, and default codecs |
| `vidbyte/agents/multi/types.py` | Feature-local stable type re-exports |
| `vidbyte/lib/enums/multi_agent.py` | Task/action/stop enums |
| `vidbyte/prompts/prompts/multi_agent_orchestrator/multi_agent_orchestrator.json` | Prompt-family descriptor |
| `vidbyte/prompts/prompts/multi_agent_orchestrator/planning_prompt.md` | Initial planning instructions |
| `vidbyte/prompts/prompts/multi_agent_orchestrator/progress_prompt.md` | Inner progress/next-action instructions |
| `vidbyte/prompts/prompts/multi_agent_orchestrator/replanning_prompt.md` | Reflection/replan instructions |
| `vidbyte/prompts/prompts/multi_agent_orchestrator/final_prompt.md` | Final/partial synthesis instructions |
| `skills/vidbyte-sdk/multi-agent.md` | Dedicated implementation and usage guide |

### Files to Modify (34)

| File | Purpose |
|---|---|
| `vidbyte/lib/dataclasses/multi_agent.py` | Add frozen orchestration contracts without removing legacy records |
| `vidbyte/lib/dataclasses/__init__.py` | Re-export central contracts |
| `vidbyte/lib/enums/__init__.py` | Re-export new enums |
| `vidbyte/lib/enums/prompts.py` | Add four prompt keys |
| `vidbyte/lib/__init__.py` | Re-export common multi-agent value contracts |
| `vidbyte/lib/errors/base.py` | Add multi-agent/ledger/transfer runtime errors |
| `vidbyte/lib/errors/__init__.py` | Export new errors |
| `vidbyte/agents/__init__.py` | Export primary multi-agent API |
| `vidbyte/agents/client.py` | Add `sdk.agents.multi(...)` factory |
| `vidbyte/__init__.py` | Add root convenience exports and header inventory |
| `vidbyte/trace/components/agents.py` | Add `MultiAgentTrace` factories |
| `vidbyte/trace/components/__init__.py` | Export trace factories |
| `vidbyte/trace/profiles.py` | Add filterable `multi_agent` component |
| `vidbyte/trace/controller.py` | Map `multi_agent.*` legacy names to semantic component/detail |
| `vidbyte/sessions/session.py` | Reject explicitly non-persistable agent subtypes before mutation |
| `README.md` | Document the team facade, example, and decision guide |
| `llms.txt` | Add compressed API/behavior inventory |
| `vidbyte/agents/README.md` | Add package map and distinguish agent/team/aggregate/runtime roles |
| `vidbyte/pipelines/README.md` | Identify MultiAgent as the dynamic shared-ledger owner and explain team-node compatibility |
| `vidbyte/prompts/README.md` | Add the prompt-family row and phase descriptions |
| `vidbyte/trace/README.md` | Document multi-agent spans and safe attributes |
| `artifacts/file_index.md` | Add the new subsystem and public types |
| `skills/sdk/SKILL.md` | Add API/package/prompt inventory and correct counts |
| `skills/sdk/update-skill-files.md` | Add the future MultiAgent documentation-update matrix |
| `skills/vidbyte-sdk/SKILL.md` | Add package map and route readers to the dedicated guide |
| `skills/vidbyte-sdk-doc/SKILL.md` | Add public API/prompt documentation and correct counts |
| `skills/usage/create_agents.md` | Show when/how to create a team agent |
| `skills/usage/available_features.md` | Add feature/prompt inventory and correct counts |
| `skills/usage/import_prompt.md` | Add four prompt enum examples and family |
| `skills/usage/create_pipeline.md` | Clarify pipeline node compatibility versus orchestration responsibility |
| `skills/vidbyte-sdk/pipelines.md` | Distinguish fixed pipelines from shared-ledger teams |
| `skills/agent-runtimes/SKILL.md` | Distinguish actor mailboxes from team orchestration |
| `skills/sessions.md` | Document v1 persistence exclusion and fail-fast behavior |
| `skills/forking.md` | Document subtype/team fork and worker isolation semantics |

### Files to Delete (0)

No files are deleted.

### Explicit No-Change Areas

- `vidbyte/agents/base.py`: no team branch or constructor overload.
- `vidbyte/client.py`: `AgentClient` is already wired into `VidbyteSDK`.
- `vidbyte/pipelines/*.py`: no shared state is added to pipeline source code.
- `vidbyte/agents/runtimes/*`: actor/runtime code remains independent.
- Session dataclasses, serializer, and stores: no lossy team schema is introduced.
- `pyproject.toml`: existing `vidbyte*` discovery and nested prompt package-data globs cover the additions.
- `.github/workflows/publish.yml`: current build/install checks remain; no workflow mutation is required.
- `tests/*` and verification scripts: none are created or modified by the selected no-tests workflow.

---

## 10. Dependencies & External Services

### Runtime Dependencies

No new dependency is required.

- Python 3.11 standard library supplies dataclasses, enums, protocols, `asyncio.timeout`/`wait_for`, JSON validation, and callback normalization.
- Existing Pydantic 2 support supplies private phase output schemas and validation.
- Existing Vidbyte `BaseAgent`, `AgentForkSettings`, prompt catalog, tracing, errors, registries, and SDK client supply all integration points.

### Research / Attribution Dependencies

- [Magentic-One paper](https://arxiv.org/abs/2411.04468): architectural inspiration for the outer/inner loop, facts/plan working memory, serial worker selection, stall recovery, and final synthesis.
- [Official AutoGen guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/magentic-one.html): implementation-oriented confirmation and security cautions.
- [AutoGen reference API](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.teams.html#autogen_agentchat.teams.MagenticOneGroupChat): prior art for finite turns/stalls and team construction.

These are design references only. Vidbyte does not call an external service or import AutoGen for orchestration.

### Operational Dependencies

Actual worker/orchestrator provider calls, tools, browsers, sandboxes, and credentials remain whatever the supplied `BaseAgent` instances already use. The team facade neither broadens permissions nor isolates those resources automatically.

---

## 11. Rollout & Deployment

This is a library-only additive feature. There is no database migration, service deployment, or feature flag.

### Implementation Sequence After Approval

1. Create a dedicated worktree/branch from the latest clean `main` as required by this workflow.
2. Add enums, frozen dataclasses, errors, and exports first so all later modules share one contract.
3. Add `TaskLedger` and validate plans, dependencies, transitions, attempts, replans, and snapshots.
4. Add transfers/bindings with safe defaults and run-local worker-fork lifecycle.
5. Add the orchestrator protocol, private Pydantic schemas, prompt assets, and model-backed implementation.
6. Add `MultiAgent.generate_reply()`, completion/limit behavior, subtype fork, card, factory, session fail-fast boundary, and root exports.
7. Add semantic trace component/factories and safe correlation metadata.
8. Update package/root docs, `llms.txt`, file index, prompt inventory/counts, and all manifest skills.
9. Run existing verification and review the final diff against this manifest before committing.

### Verification Without New Tests or Scripts

The implementation PR must still run:

- `python -m compileall vidbyte`
- The repository's existing standard-library test discovery suite.
- Public import/factory smoke checks for every primary export.
- Ephemeral inline fake-orchestrator/fake-worker cases covering plan -> completion, failure -> retry, stalls -> replan, premature finish rejection, limit -> partial result, cancellation propagation, non-JSON payload failure, custom transfer success, and subtype-preserving `as_tool()` fork.
- Ephemeral inline trust-boundary cases covering unverified evidence, verified-evidence gating, report filtering, and a denied/erroring `before_dispatch` gate with no worker invocation.
- Ephemeral fork/resource cases covering subtype-erasure rejection, custom worker/manager factories, schema-free finalization, post-start adapter failure recovery, hard-timeout candidate/no-candidate behavior, and MCP close calls on replan/success/failure/cancellation.
- Existing session checks plus an inline check that `Session(MultiAgent(...))` fails before writing state while `Session(BaseAgent(...))` remains valid.
- `python -m build`, `twine check`, clean-environment wheel install/import, and wheel inspection confirming all five prompt-family assets are packaged and no bytecode artifacts are included.
- Documentation inventory checks ensuring all stated prompt counts and exported names match the source.

The absence of committed feature tests is a material risk accepted by this no-tests workflow; it does not waive runtime validation before PR creation.

### Rollback

Because the feature is additive and unused unless constructed, rollback is a normal revert of the feature PR. The only cross-cutting behavior is the `Session` capability check, which activates only for agent classes that explicitly opt out.

---

## 12. Open Questions

No product decision blocks implementation if this document is approved. Approval confirms these v1 choices:

- Serial one-worker-per-round dispatch rather than parallel batches.
- A visible `MagenticOneOrchestrator` default plus completely replaceable orchestrator and worker transfers.
- One typed `TaskLedger` plus events rather than literal separate paper Task/Progress Ledger objects.
- Run-local worker forks reused within a plan cycle and reset on replan by default.
- Strict subtype-preserving worker/manager fork validation with explicit factory escape hatches and mandatory cleanup.
- Strict default payload encoding instead of arbitrary-object stringification.
- Structurally read-only snapshots with disclosed opaque-value aliasing rather than a false recursive-immutability promise.
- Deterministic completion gates and finite defaults.
- Explicitly unsupported durable team sessions in v1.
- Explicitly unsupported team-level tools/MCP/automatic handoff; handoff requires a runner-backed `HandoffAgent` through `by=`.
- No new test files or verification scripts.

Follow-up designs may answer:

- How revisioned parallel dispatch and conflicting reports should merge.
- How to serialize a team while safely re-supplying live agents/callbacks.
- Whether hierarchical/nested teams need a separate binding type and budget propagation.
- Whether whole-plan approval deserves a first-class controller action in addition to per-dispatch and worker-tool approval seams.
- Whether event/evidence storage should support external sinks and content-addressed artifacts.

---

## 13. Alternatives Considered

### Use a Pipeline

Rejected as the implementation base. Pipelines are ideal for fixed string dataflow, including sequential and parallel composition, but intentionally have no shared mutable state, typed task ownership, evidence, blockers, attempts, completion gate, or dynamic replanning. Making pipelines own those concerns would break their narrow contract.

### Build on the Actor Runtime

Rejected. Actor mailboxes provide point-to-point/broadcast topology inside an agent runtime, not a high-level team controller. They share runtime/tool machinery and do not define ledger snapshots, task dependencies, evidence, completion, transfer codecs, or replanning. The new class can later use a worker whose own inner runtime is actor-based without coupling the layers.

### Extend AggregateAgent

Rejected. `AggregateAgent` concurrently asks proposers the same question and synthesizes their outputs. It does not assign changing subtasks, retain task state, or recover by revising a plan. It remains the right primitive for mixture-of-agents fan-out; `MultiAgent` is the right primitive for dynamic coordinated work.

### Implement a Deterministic Workflow Graph

Rejected for this request, but complementary. A state machine is best when developers know legal transitions ahead of time and code must choose from them. This request specifically needs an orchestrator to own progress and dynamically replan after failure. The controller still deterministically enforces the safe envelope around model proposals.

### Revive the Old Multi-Agent Strategy Branch

Rejected. That unmerged branch predates the current BaseAgent, fork, session, tracing, prompt, runtime, and error architecture. It also groups consensus, conversations, economic gates, and verified DAGs under a strategy layer absent from current `main`. Porting it would add unrelated abstractions and miss the requested first-class agent/ledger boundary.

### Depend on AutoGen's MagenticOneGroupChat

Rejected. It would introduce a large framework dependency, foreign agent/message/state contracts, and less control over the exact Vidbyte worker boundary. Reimplementing the small coordination pattern over ordinary `BaseAgent` instances preserves SDK consistency and lets developers own payloads.

### Let Every Worker Mutate a Shared Ledger

Rejected. Direct shared structural mutation makes model/tool concurrency unsafe, weakens auditability, and allows one worker to overwrite another's evidence or completion state. Structurally read-only snapshots plus proposed reports keep one validation/commit authority while still making the ledger the shared source of truth.

### Require a Fully Custom Orchestrator and Transfers With No Defaults

Rejected. It maximizes explicitness but makes the class little more than a loop framework and fails to deliver a useful paper-inspired primitive. Visible catalog prompts, safe default transfers, and replaceable protocols give an ergonomic baseline without hiding control.

### Send the Whole Ledger and Transcript to Every Worker

Rejected. It raises cost, leaks irrelevant or sensitive context, increases prompt-injection surface, and reduces specialization. The default sends only the assignment envelope; custom transfers opt into additional facts or evidence deliberately.

### Parallel Dispatch in V1

Rejected. Parallel work is attractive for independent tasks, but it requires base-revision checks, conflict resolution, deterministic event ordering, cancellation semantics, and merge policies for duplicate evidence/results. Serial delegation matches the core Magentic-One loop and gives v1 a coherent ledger authority.

### Persist the Team Through Existing RunState

Rejected as unsafe. The existing state cannot encode the team subtype, manager/worker construction, transfer callbacks, arbitrary payload codecs, or current ledger, and session restore constructs a `BaseAgent`. Failing explicitly is safer than a checkpoint that appears valid but restores different behavior.
