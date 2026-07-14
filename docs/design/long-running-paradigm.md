# Design Doc: Long-Running Paradigm with Verified Procedure Learning

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-12
**Last Updated:** 2026-07-12

---

## 1. Overview

This feature adds a LongRunningParadigm to the Vidbyte SDK: a durable, dependency-aware execution harness that decomposes a broad goal into independently verifiable subproblems, runs every attempt in a fresh and deliberately small context, promotes only locally verified, globally aligned, fidelity-checked reusable procedures into cross-run memory, and continually checks committed progress against the immutable original goal. The design adapts Voyager's successful-task procedure library, bottom-up curriculum, and execution-feedback loop to a provider-neutral SDK while adding the explicit task graph, summary/index-plus-expand memory, versioned verification provenance, append-only run ledger, downstream invalidation, and final drift audit needed for general long-running work.

---

## 2. Goals & Non-Goals

### Goals

- Add the stable paradigm key long_running and the public LongRunningParadigm class.
- Give the paradigm one obvious asynchronous start path, one inherited synchronous start path, and explicit asynchronous/synchronous resume paths.
- Freeze the exact original request, success criteria, invariants, and limits into an immutable run contract.
- Decompose the run into a validated directed acyclic graph of small tasks with dependencies, ownership, acceptance criteria, verification expectations, and procedure-retrieval queries.
- Schedule only dependency-ready tasks and execute them one at a time in v1 so rejected work cannot race ahead or contaminate dependent work.
- Run planning, work, repair, verification, curation, synthesis, and global audit in fresh role-specific BaseAgent instances with separate ContextManager objects.
- Prevent context pollution by keeping model-visible context bounded to the run contract, current task, verifier-approved dependency summaries, relevant procedure cards, and the latest actionable failure evidence.
- Preserve full available model/tool transcripts and state transitions in a separate append-only audit ledger that is never injected wholesale into a later model.
- Add a reusable vidbyte.procedures lower layer with typed candidates, immutable versions, verifier evidence, outcome history, pluggable stores, deterministic retrieval, and retirement.
- Ship zero-dependency in-memory and atomic JSON file procedure stores.
- Add model-callable procedure_search, procedure_load, and procedure_stage tools.
- Return only verified procedure summaries from search; expand one explicitly selected full procedure on demand.
- Ensure procedure_stage can create only a candidate and that no model-callable operation can mark a procedure verified.
- Promote a candidate only after the source task passes its independent verification gate, its post-commit drift review confirms that it remains aligned, and a separate candidate-fidelity gate confirms that the saved procedure is supported by the successful trace and evidence.
- Store the compact procedure summary separately from the full body and retain exact source provenance, content fingerprint, task/drift evidence, procedure-fidelity evidence, and the exact loaded version in later outcome records.
- Version changed procedures instead of overwriting prior verified artifacts.
- Record procedure outcomes and retire repeatedly implicated stale procedures under a deterministic threshold.
- Verify each task with a fresh read-only verifier plus optional caller-provided deterministic validators.
- Retry failed work in a fresh context using only the latest candidate, verifier critique, current task, and relevant verified procedures.
- Detect repeated failure signatures or unchanged strategies and replan instead of repeating a stalled attempt.
- Reconcile plan revisions deterministically, preserve verified history, and invalidate transitive descendants when a verified dependency is explicitly invalidated or materially replaced.
- Run a global goal-alignment audit after task commits and after exhausted failures.
- Synthesize only verifier-approved task outputs and require a final independent audit before reporting success.
- Enforce harness-wide attempt, replan, cycle, runtime, and observed-token limits in addition to per-agent middleware limits.
- Persist a resumable outer run ledger through in-memory or atomic file-backed stores.
- Preserve optional links to durable Session records and tracing metadata when callers configure those existing SDK surfaces.
- Follow current origin/main conventions: frozen/slotted dataclasses, class-first orchestration, OutputSchemaBuilder-based structured stages, central prompt catalog assets, explicit exports, typed errors, and async-first execution.
- Update central docs, skills, tool catalogs, prompt docs, and the repository file index in the same change.

### Non-Goals

- Reproducing Minecraft, Mineflayer, Voyager's JavaScript action space, or its exact prompts.
- Claiming that the new task DAG, expandable context store, verifier evidence model, descendant invalidation, or global drift guard are mechanisms implemented by Voyager; they are deliberate SDK extensions.
- Adding embedding or vector-database dependencies. V1 uses deterministic lexical ranking behind an injectable ranker contract.
- Adding hosted databases, dashboards, remote queues, proprietary scoring, or private Vidbyte service orchestration.
- Replacing existing third-party Mem0, Zep, Supermemory, Letta, or Cognee tools.
- Treating durable Session checkpoints, continual trace artifacts, or trace-provider spans as the canonical outer run ledger or procedure library.
- Replacing ContextMinimalFanoutParadigm. That paradigm remains the fast parallel fanout option; long_running is the slower verification-gated option.
- Running multiple mutating task nodes concurrently in v1.
- Providing generic rollback for arbitrary filesystem, browser, network, database, or third-party tool side effects. Logical candidate state is gated; physical rollback requires a caller-provided attempt isolator or transactional tools.
- Automatically executing arbitrary planner-authored shell commands outside the normal permission-controlled tool path.
- Letting summaries replace raw evidence. Summaries are retrieval indexes and context capsules only.
- Persisting or promising access to hidden chain-of-thought. The ledger stores only messages, tool records, outputs, and metadata available through public SDK objects.
- Guaranteeing that an LLM verifier is objectively correct. VERIFIED means the configured verification gate approved the evidence; deterministic validators are supported for stronger claims.
- Adding human approval queues or UI.
- Adding new test files or verification scripts under the selected design-doc-no-tests workflow.
- Depending on the unmerged local harness-execution-contract or validated-state-machine-workflows branches. If either becomes a merged public API before implementation, this design must be revised and re-approved before depending on it.

---

## 3. Background & Context

The primary research reference is the official Voyager paper, Voyager: An Open-Ended Embodied Agent with Large Language Models (arXiv:2305.16291), together with its official MineDojo/Voyager source repository. Voyager has three core mechanisms: an automatic curriculum that proposes achievable frontier tasks, a library that retrieves executable skills and adds a program only after success, and an iterative prompting loop that incorporates environment feedback, execution errors, and a separate critic's self-verification. The paper describes committing a new skill only after the critic approves task completion and abandoning a task after a bounded number of failed generations.

Voyager's transferable control loop is:

~~~text
select task
  -> retrieve relevant verified procedures
  -> attempt
  -> observe environment/errors
  -> independently verify
  -> repair or abandon
  -> promote the successful procedure
~~~

Voyager does not provide a general conversation-memory system, an arbitrary context-fragment API, a typed dependency DAG, provenance-rich immutable procedure versions, descendant invalidation, deterministic rollback, or a global objective drift guard. Its implementation indexes a short generated description and retrieves the full program through a vector database. This design therefore preserves the verified-artifact loop but explicitly labels summary cards, on-demand expansion, task graphs, durable ledgers, procedure retirement, and global audits as general-purpose Vidbyte extensions.

Repository audit was anchored to the verified remote main head origin/main at d575a3ff13e80a69de3739d8cb96ef679776c7ce (2026-07-11), not the checked-out feat/context-minimal-fanout-trace branch at 97e9720. The checkout is 58 mainline commits behind and dirty with user-owned tracked bytecode changes, untracked design documents, and nested worktree artifacts. Those files must remain untouched. The eventual implementation must start from the latest main in an isolated worktree after approval.

Relevant current SDK capabilities:

- ParadigmHarness defines async arun(prompt, **options) and the synchronous run bridge.
- ContextMinimalFanoutParadigm demonstrates the current concrete-paradigm shape: per-role settings, fresh agents, OutputSchemaBuilder tools, typed frozen results, deterministic plan validation, namespace factories, and central/root exports.
- ParadigmMinimalToolset provides bounded read/search/execute and optional write tools for local workspaces.
- ContextManager and TaskContextItem, PlanContextItem, ProgressContextItem, and MemoryContextItem provide typed model-visible capsules.
- ContextReciteTool can re-surface one already-loaded primitive, but it is not a persistent compact index or lazy procedure store.
- MessageHistoryCompactionMiddleware and ToolResultCompactionMiddleware can reduce one agent's model-visible history while raw runtime records remain available.
- Session, SessionStore, InMemorySessionStore, and FileSessionStore preserve one agent's history as a checkpoint DAG. They do not persist an outer multi-agent state machine or indexed procedure records.
- Continual trace and semantic trace providers are valuable observations but are model-generated or fail-open and therefore cannot decide task commitment.
- Reflexion, error correction, problem-space search, trajectory checkpoints, loop detection, runtime limits, and budgets operate inside one agent run. They cannot collectively enforce cross-task dependency and promotion invariants.
- Existing memory tools are third-party HTTP adapters and have no local candidate/verified lifecycle, evidence, versioning, or deterministic retrieval.
- Pipelines remain string-in/string-out topologies with no shared typed state, verification gate, or durable ledger.

The central primitive gap is therefore a verified procedure library. The paradigm gap is a deterministic outer controller that keeps unverified work out of dependency context and memory, builds fresh context capsules, journals raw evidence, and repeatedly compares local progress with the original request.

Primary references:

- Voyager paper: https://arxiv.org/html/2305.16291
- Voyager official repository: https://github.com/MineDojo/Voyager
- Official skill manager: https://github.com/MineDojo/Voyager/blob/main/voyager/agents/skill.py
- Official curriculum agent: https://github.com/MineDojo/Voyager/blob/main/voyager/agents/curriculum.py
- Official critic: https://github.com/MineDojo/Voyager/blob/main/voyager/agents/critic.py

---

## 4. Requirements

### Functional Requirements

1. Add an importable vidbyte.paradigms.long_running package.
2. Add LongRunningParadigm as a concrete ParadigmHarness subclass.
3. LongRunningParadigm.arun(prompt, *, run_options=LongRunningRunOptions(), **options) must start a new run and return LongRunningResult; execution-critical inputs must use the typed run_options contract rather than unstructured options.
4. LongRunningParadigm must inherit ParadigmHarness.run(prompt, **options) for new synchronous runs.
5. Add LongRunningParadigm.aresume(run_id, *, resume_options=LongRunningResumeOptions(), **options) for asynchronous continuation from the latest persisted ledger state.
6. Add LongRunningParadigm.resume(run_id, *, resume_options=LongRunningResumeOptions(), **options) as a synchronous bridge that fails inside an active event loop.
7. Add LongRunningClient with callable and create factory methods and attach it as sdk.paradigms.long_running.
8. Direct LongRunningParadigm construction must remain the primary documented entry point.
9. Every new run must receive a unique lr_<uuid> run id.
10. The exact original prompt must be stored unchanged and must never be replaced by a planner or summary; a prompt above max_contract_chars fails before run creation rather than being truncated.
11. The initial planning stage must produce a GoalContract containing explicit success criteria, invariants, and non-goals while retaining the exact prompt separately.
12. Caller-supplied success criteria, invariants, and non-goals in LongRunningRunOptions must be preserved verbatim and take precedence. Planner additions are appended only when non-duplicative; they may not weaken, replace, or remove caller entries.
13. The controller must compute a safe settings fingerprint and persist it with the run.
14. Resume must reject a settings fingerprint mismatch unless LongRunningResumeOptions explicitly allows the change with a non-empty reason; accepted changes must journal old/new fingerprints and a safe component-level diff, while schema/store identity and original goal contract remain immutable.
15. Settings snapshots and persisted records must exclude credential values and live runner/tool/store objects.
16. The planner must emit a typed TaskGraph.
17. Every LongRunningTask must contain a stable id, title, instructions, dependencies, acceptance criteria, priority, and a procedure query.
18. Tasks may additionally declare owned paths, read-only paths, verification expectations, expected artifacts, and notes.
19. TaskGraph validation must reject an empty graph.
20. TaskGraph validation must reject duplicate task ids.
21. TaskGraph validation must reject unknown dependency ids.
22. TaskGraph validation must reject self-dependencies and cycles.
23. TaskGraph validation must reject tasks without acceptance criteria and reject instructions, criteria, summaries, evidence expectations, or artifact metadata above their configured per-field/count bounds.
24. TaskGraph validation must reject more than max_tasks tasks.
25. TaskGraph validation must reject equal or ancestor/descendant normalized owned-path overlap between tasks that are not transitively dependency-ordered. Ordered tasks may intentionally hand off the same path; read-only overlap is allowed.
26. Planner output that fails validation must be retried in a fresh planner context with only the candidate graph and deterministic validation errors.
27. Plan retries must be bounded by max_plan_attempts.
28. The scheduler must select only tasks whose dependencies are VERIFIED.
29. V1 must execute one selected task at a time in deterministic priority/id order.
30. A task must not become VERIFIED from worker self-report alone.
31. Every worker attempt must run in a fresh BaseAgent and a fresh ContextManager.
32. Every repair attempt must run in a fresh BaseAgent and a fresh ContextManager.
33. Planner, task verifier, procedure curator, procedure verifier, synthesizer, and auditor calls must also use fresh agent instances and managers.
34. No mutable ContextManager may be shared across role calls or task attempts.
35. Each worker context must contain only the immutable run contract, the current task, verified dependency summary/handle cards, compact relevant procedure cards, current budget state, and at most the latest repair evidence.
36. To prevent context pollution, raw prior transcripts and the complete run event log must never be injected wholesale into a later role.
37. Retrieved procedure bodies and full dependency result/artifact bodies must not be injected automatically.
38. Procedure search must expose compact cards and stable handles only.
39. Procedure load must expand exactly one requested verified procedure, and verified_context_load must expand exactly one allowed verified dependency result/artifact, into frozen MemoryContextItem values bound to that role's ContextManager. Both enforce per-role unique-load and cumulative expanded-character budgets.
40. Loaded procedure/dependency text must be framed as untrusted reference data that cannot override the system prompt, run contract, permissions, or task acceptance criteria; dependency loads must re-check committed VERIFIED status and content hash at load time.
41. Procedure bodies must be bounded by max_procedure_body_chars when staged.
42. Every role must install default model-visible tool-result truncation plus a final provider-boundary-aware history guard enforcing max_role_messages and max_role_history_chars while retaining raw runtime records outside the model-visible projection.
43. Every role capsule must enforce deterministic character budgets even when provider token counts are unavailable. Exact original prompts/task definitions that cannot fit their declared caps must fail configuration/plan validation rather than be silently truncated. Optional context-token trimming is an additional bound applied only when max_visible_context_tokens is configured.
44. Structured planner, worker, repairer, task-verifier, curator, procedure-verifier, synthesizer, and auditor outputs must use run-local OutputSchemaBuilder tools and typed parsing.
45. A worker attempt must return a summary, strategy description, produced artifacts, evidence claims, and blockers; model-claimed procedure usage is non-authoritative.
46. The controller must persist the available raw agent history and reply metadata for every role call before using its structured result, and it must derive exact loaded procedure id/version/fingerprint references from successful procedure_load tool records rather than model self-report.
47. The verifier must be a fresh agent with no write tools.
48. The verifier must receive the exact run contract, current task and acceptance criteria, candidate output, observable evidence, and READ-permission inspection tools only. Generic CodeExecutionTool and every non-READ tool must be rejected for verifier/auditor/finalizer roles; caller-owned deterministic validators perform executable checks.
49. The verifier must emit one result per acceptance criterion plus an overall passed flag, critique, evidence, failure signature, suspected exact loaded ProcedureRef values, and requires_replan flag.
50. Optional caller-provided deterministic TaskValidator objects must run as part of the same gate.
51. Verification must fail closed when the verifier output is invalid, a required validator rejects, or a required validator errors.
52. A task is VERIFIED only when the model verifier and every configured required validator pass.
53. Rejected attempts must be recorded but must not unlock dependents.
54. Rejected attempts must not become verified procedure inputs or promoted procedures.
55. A retry context must include only the latest candidate summary, verifier critique/evidence, the immutable contract, current task, verified dependencies, and relevant verified procedures.
56. Retry count must be bounded by max_attempts_per_task.
57. A retry must supply a changed strategy or new evidence; repeated normalized strategy/failure pairs must count as no progress.
58. Reaching the no-progress threshold must trigger a replan/audit path instead of another identical retry.
59. A verifier result marked requires_replan must bypass ordinary repair and request plan revision.
60. Plan revision must use a fresh planner and the compact committed state, not the full transcript log.
61. Plan reconciliation must preserve all historical task/attempt records.
62. A revision must not silently mutate a VERIFIED task definition.
63. Explicit invalidation of a verified task must record the reason and invalidate every transitive descendant that consumed it.
64. Invalidated task results must no longer count as ready dependency inputs.
65. Plan revisions must be bounded by max_replans.
66. The drift auditor must run after every locally committed task and after any exhausted task failure; procedure learning must wait for this review.
67. The drift auditor must compare committed progress and the remaining graph with the exact original request and immutable invariants.
68. Auditor route suggestions must use bounded semantic decisions that the deterministic controller maps to continue, replan, synthesize, or fail.
69. The auditor must not directly modify run state or mark the run complete, and invalid/missing auditor output must fail closed for procedure promotion.
70. When all required work appears complete, the synthesizer must build a candidate final output from currently VERIFIED, non-invalidated task results only.
71. A fresh final auditor must verify the candidate final output and actual observable state against the original run contract.
72. A failed final audit must create bounded targeted repair/replan work or terminate with a non-success stop reason.
73. The controller must never return COMPLETED unless the final audit passes.
74. Add a public vidbyte.procedures package.
75. Add ProcedureCandidate, ProcedureLimits, ProcedureRecord, ProcedureRef, ProcedureSummary, ProcedureMatch, ProcedureCheckResult, ProcedureVerificationEvidence, and ProcedureOutcome typed contracts.
76. ProcedureStatus must distinguish CANDIDATE, VERIFIED, REJECTED, and RETIRED.
77. Procedure records must carry a namespace, stable id, immutable version, deterministic learning-operation id, title, compact summary, full body, applicability, preconditions, expected outcomes, tags, required tools, environment fingerprint, provenance, content fingerprint, timestamps, and status.
78. VERIFIED records must include source run/task/attempt identifiers, the source task-verification event, the aligned drift-review event, the candidate content fingerprint, and procedure-specific fidelity-verification evidence.
79. A replacement or retirement must create a new immutable version rather than overwriting a prior file/store record.
80. Add a ProcedureStore protocol.
81. Add InMemoryProcedureStore.
82. Add FileProcedureStore using inspectable atomic JSON files.
83. FileProcedureStore must document and enforce its single-process-writer limitation.
84. Add ProcedureLibrary as the only service that owns stage, promote, reject, search, load, outcome recording, deduplication, versioning, and retirement.
85. Procedure staging must create only a CANDIDATE record.
86. Within LongRunningParadigm, procedure promotion must require ProcedureVerificationEvidence whose source task is VERIFIED in the active run ledger, whose latest applicable drift review is aligned and does not invalidate the source, whose candidate fingerprint matches, and whose procedure-specific verifier plus required validators pass.
87. Procedure rejection must create a REJECTED version with a reason.
88. Procedure search and load must expose only the derived active VERIFIED version for each namespace/id chain; candidate/rejected heads do not hide it, and a retirement tombstone removes it.
89. Candidate, rejected, superseded, and retired records must not appear in normal model retrieval.
90. Procedure search and direct load must enforce namespace and compatible environment fingerprint.
91. Procedure search and direct load must reject records whose required tools are unavailable to the target worker.
92. V1 ranking must use a deterministic lexical ranker over query, summary, applicability, tags, and preconditions.
93. ProcedureLibrary must accept an injectable ranker for later embedding-backed retrieval without adding a dependency now.
94. Identical normalized procedure fingerprints must deduplicate rather than create equivalent verified entries.
95. Add ProcedureSearchTool with READ permission and compact-summary output.
96. Add ProcedureLoadTool with READ permission for one active procedure and VerifiedContextLoadTool with READ permission for one allowlisted verified dependency result/artifact, each expanding into its bound ContextManager under cumulative limits.
97. Add StageProcedureTool with WRITE permission and candidate-only behavior.
98. Do not add a model-callable promote, verify, retire, or delete operation.
99. The curator must run only after its source task is VERIFIED and its post-commit drift review confirms that the task remains aligned and not invalidated.
100. The curator may stage zero procedures when the work is not genuinely reusable.
101. The controller must deterministically validate staged candidate completeness, then use a fresh read-only procedure verifier plus optional required ProcedureValidator objects to verify that the exact candidate is faithful to the successful trace, preserves prerequisites and limits, and makes no unsupported claims before promotion.
102. Every promoted procedure must retain both compact retrieval text and the full source-of-truth body.
103. The controller must record success outcomes for exact procedure versions loaded by accepted attempts only after the source task's post-commit drift review passes.
104. It must record failure outcomes only for exact loaded ProcedureRef values explicitly implicated by the verifier, not for every retrieved card or ambiguous id.
105. An exact active ProcedureRef reaching retire_after_suspected_failures for that same version/fingerprint must receive a RETIRED tombstone version and disappear from normal retrieval; failures from older versions must not count against a replacement.
106. Add a deterministic append-only RunLedger with typed events and a current state snapshot.
107. Ledger events must cover run start/resume, plan attempts/acceptance, task start, role calls, attempt results, verification, repair, task commit/rejection, procedure learning intent/stage/fidelity/promotion/rejection/retirement/completion, procedure outcome intent/completion, drift review, plan revision, invalidation, synthesis, final audit, checkpoint, pause, failure, and completion.
108. Ledger event sequence numbers must be monotonic within one run.
109. The ledger must store only public model messages/tool records/metadata and must not claim hidden reasoning.
110. Persisted mappings must recursively scrub credential-looking keys.
111. Unsupported live values must be represented by an explicit dropped-type marker instead of breaking serialization.
112. Add InMemoryRunLedgerStore as the default zero-write store.
113. Add FileRunLedgerStore for explicit durable resume.
114. FileRunLedgerStore must atomically write an immutable per-transition envelope containing the event and resulting compact state snapshot before replacing the state head; resume must recover from the newest valid envelope when the head lags after a crash.
115. FileRunLedgerStore must document one controller process as the only writer for a run.
116. The controller must checkpoint after every accepted state transition and before launching the next role. Cross-store procedure mutations must use a ledgered intent/completion saga with deterministic operation ids so resume can reconcile safely without duplicate promotion/outcomes.
117. File persistence must be required by default once a caller explicitly selects FileRunLedgerStore.
118. A checkpoint failure in required mode must stop execution before additional side effects.
119. Cancellation must make a best-effort PAUSED checkpoint including the current attempt/isolator reference and then re-raise asyncio.CancelledError.
120. Infrastructure failure must make a best-effort FAILED checkpoint and raise a typed LongRunningError containing the run id.
121. Resume must restore deterministic graph/task/counter/procedure-reference state but re-supply live runners, tools, middleware, validators, stores, and isolators; their behavioral fingerprints must match or follow the explicit settings-change path.
122. Resume must not replay already committed task nodes. An interrupted ACTIVE attempt may retry automatically only when its recorded tools were READ-only or its isolator proves rollback; unknown external side effects force RECOVERY_REQUIRED until a caller explicitly records reconciliation and accepts retry.
123. The controller must enforce max_cycles, max_replans, max_attempts_per_task, max_controller_runtime_seconds, max_observed_tokens, and max_no_progress_cycles. Every awaited role, validator, isolator, and async adapter operation must run under the smaller of its local timeout and remaining controller deadline.
124. Observed token accounting must aggregate reply metadata when present. When max_observed_tokens is configured with require_usage_reporting_for_token_budget=True, the first role lacking usage must checkpoint/stop with USAGE_UNAVAILABLE before another model call; otherwise the result marks accounting incomplete and the observed limit is explicitly best effort.
125. Budget/deadline exhaustion must checkpoint and return a typed non-success stop reason rather than silently truncating the run. Per-role max_tokens remains the provider-requested per-call cap; the controller deadline requests cancellation but cannot promise to kill cancellation-resistant external side effects.
126. LongRunningResult must expose run id, run status, resumable flag, final output, stop reason, success flag, immutable contract, final graph, verified task results, attempt/verification summaries, promoted procedures, procedure outcomes, usage, ledger snapshot/event references, and trace/session metadata.
127. Add typed feature errors for configuration, plan, verification, procedure, ledger, store, and resume failures.
128. Add eight central prompt assets: planner, worker, repair, task verifier, procedure curator, procedure verifier, synthesizer, and auditor.
129. Add matching Prompt enum members and prompt-family metadata.
130. Update root, paradigm, prompt, tool, procedure, skill, llms.txt, and file-index documentation.
131. Correct stale paradigm docs that still claim no concrete paradigm exists or that context-minimal fanout ships only skills.
132. Add no test files and no verification scripts.

### Non-Functional Requirements

- **Correctness:** Unverified work must never become a dependency input or retrievable procedure. A locally verified but globally misaligned task must not teach cross-run memory. A curator's transformed candidate must be fidelity-checked as the exact artifact being promoted. Final success must require the final audit.
- **Durability:** File stores use schema-versioned JSON, immutable record/event files, crash-recoverable transition envelopes, atomic state-head replacement, and explicit corruption/version errors.
- **Auditability:** Raw available transcripts/evidence stay separately inspectable even when model-visible context uses summaries or compaction.
- **Context bounds:** Every generated capsule, procedure card, loaded procedure/dependency item, provider history, latest-attempt excerpt, and verifier evidence block has explicit item and aggregate character/message bounds, with optional additional token trimming.
- **Security:** Retrieved procedures are untrusted data; credential-like mapping keys are scrubbed; live credentials are never serialized; normal tool permission policy remains authoritative.
- **Privacy:** Documentation must warn that full ledger capture can contain prompts, outputs, tool results, source content, and other sensitive data. The caller controls the durable root and retention.
- **Reliability:** Model/schema/store failures are typed, checkpointed where possible, and bounded. Verification and procedure promotion fail closed.
- **Side-effect containment:** Non-READ attempts require an isolator by default. If a caller explicitly runs without one, any rejected/interrupted successful non-READ call blocks the entire run in RECOVERY_REQUIRED until external state is reconciled; unverified mutation is never silently treated as a clean base for later tasks.
- **No-progress safety:** Identical failure/strategy loops stop or replan under deterministic limits.
- **Compatibility:** Existing agents, paradigms, pipelines, sessions, memory-provider tools, prompts, and public imports keep their behavior.
- **Extensibility:** Provider/model/runner/tools/middleware are configurable per role; deterministic validators, procedure ranker, attempt isolator, procedure store, and ledger store are injectable.
- **Performance:** V1 schedules tasks sequentially. Lexical procedure search is linear in version-chain records for one namespace and is intended for small/medium local libraries; vector indexing/materialized active indexes are deferred.
- **Concurrency:** In-memory stores are lock-protected within one process. File stores are atomic for a single writer but do not claim multi-process transactions.
- **Observability:** Every role is tagged with run id, role, graph version, task id, and attempt number. Existing trace/session surfaces may be attached but are not commitment authority.
- **Packaging:** Central prompt assets must be present in wheels through the existing prompt package-data glob; no new runtime dependency is added.
- **Verification:** Implementation must run compileall, the existing unittest suite, inline smoke exercises, public import checks, prompt-catalog checks, and distribution build/twine validation without adding new tests/scripts.
- **Regression limitation:** The selected no-tests workflow cannot provide durable automated regression coverage for crash points, CAS/locking, resume idempotency, immutable version chains, or retirement. The feature remains alpha; a tests-enabled follow-up is required before any stability claim.

---

## 5. High-Level Design

The feature has three deliberately separate state planes.

1. **Committed run state:** The deterministic controller owns the immutable goal contract, task graph, task statuses, accepted results, invalidations, counters, and stop reason. Only this state unlocks work.
2. **Raw audit state:** RunLedger stores every available role transcript, authoritative procedure-load record, tool/evidence record, candidate, verifier decision, and state transition. It is a source for humans and resume, not a prompt automatically sent to models.
3. **Cross-run procedure memory:** ProcedureLibrary stores versioned procedures and outcome history. Candidates, rejected versions, superseded versions, and retired versions are auditable but hidden from normal retrieval; only the derived active compatible VERIFIED version is searchable/loadable.

The model-visible plane is rebuilt for every role call by LongRunningContextBroker. It projects a small capsule from committed state, verified dependency handles/summaries, and procedure summaries. Full raw audit history stays offline. A full procedure or verified dependency result/artifact enters the window only when a role explicitly calls the matching one-item load tool within its cumulative budget.

~~~text
                             +---------------------------+
                             | ProcedureLibrary          |
                             | candidate -> VERIFIED     |
                             | summary search -> load one|
                             +-------------+-------------+
                                           |
                                           v
[exact user request] -> [immutable GoalContract] -> [fresh planner]
                                                    |
                                                    v
                                      [validated dependency DAG]
                                                    |
                                      select one READY task
                                                    |
                +-----------------------------------+-----------------------------------+
                |                                                                       |
                v                                                                       |
      [fresh worker / repair] -- candidate + evidence --> [fresh verifier + validators]|
                ^                                          |                            |
                |                             reject -------+------- approve             |
                |                               |                    |                   |
                |                        fresh repair/replan         v                   |
                |                                           commit task result           |
                |                                                  |                    |
                +------------------------- [fresh drift auditor] <--+                    |
                |                                                  | aligned            |
                |                                       curate -> fidelity verify        |
                |                                                  |                    |
                |                                       promote exact candidate          |
                |                                                  |                    |
                +--------------------------------------------------+                    |
                                                   |                                     |
                                      continue / replan / synthesize / fail              |
                                                   |                                     |
                                                   v                                     |
                                      [fresh synthesizer + final auditor]                |
                                                   |                                     |
                                           COMPLETED only on pass                        |
                                                                                         |
Every transition/transcript/evidence ----------------> [append-only RunLedger] <---------+
                                                        |
                                                        +-> resume checkpoint
~~~

The controller is intentionally sequential in v1. Parallel fanout is already served by ContextMinimalFanoutParadigm, whereas this feature prioritizes verification ordering and side-effect containment. A later design can execute independent read-only nodes concurrently if it supplies conflict and commit semantics.

The procedure layer is extracted below the paradigm because search/load/stage, typed evidence, versioning, and store adapters are reusable primitives. The task controller, drift policy, retry rules, and outer ledger remain in vidbyte.paradigms.long_running because they are the owned strategy.

---

## 6. Detailed Design

### 6.1 Procedure Contracts and Errors

**File(s):** vidbyte/procedures/contracts.py, vidbyte/procedures/errors.py
**Type:** New files

#### What it does

Defines immutable public records for staged, verified, rejected, and retired procedures; compact search results; verifier provenance; procedure-use outcomes; ranker/store protocols; and the feature-local error hierarchy.

#### Interface / API

~~~python
class ProcedureStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RETIRED = "retired"

@dataclass(frozen=True, slots=True)
class ProcedureCandidate:
    namespace: str
    title: str
    summary: str
    body: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]
    environment_fingerprint: str
    source_run_id: str
    source_task_id: str
    source_attempt_id: str
    source_evidence_event_ids: tuple[str, ...]
    proposed_procedure_id: str | None = None

@dataclass(frozen=True, slots=True)
class ProcedureLimits:
    max_title_chars: int = 200
    max_summary_chars: int = 1200
    max_body_chars: int = 20000
    max_list_items: int = 32
    max_list_item_chars: int = 500

@dataclass(frozen=True, slots=True)
class ProcedureCheckResult:
    validator_id: str
    validator_version: str
    config_fingerprint: str
    required: bool
    passed: bool
    evidence: tuple[str, ...]
    error_code: str
    error_message: str
    duration_ms: int

@dataclass(frozen=True, slots=True)
class ProcedureVerificationEvidence:
    run_id: str
    task_id: str
    attempt_id: str
    source_task_verification_event_id: str
    source_drift_review_event_id: str
    candidate_content_fingerprint: str
    criteria: tuple[str, ...]
    observations: tuple[str, ...]
    source_task_validator_results: tuple[ProcedureCheckResult, ...]
    procedure_fidelity_results: tuple[ProcedureCheckResult, ...]
    verifier_name: str
    verified_at: str
    evidence_hash: str

@dataclass(frozen=True, slots=True)
class ProcedureRef:
    namespace: str
    procedure_id: str
    version: int
    content_fingerprint: str

@dataclass(frozen=True, slots=True)
class ProcedureRecord:
    schema_version: int
    procedure_id: str
    version: int
    namespace: str
    learning_operation_id: str
    status: ProcedureStatus
    title: str
    summary: str
    body: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]
    environment_fingerprint: str
    content_fingerprint: str
    source_run_id: str
    source_task_id: str
    source_attempt_id: str
    source_evidence_event_ids: tuple[str, ...]
    verification: ProcedureVerificationEvidence | None
    reason: str
    created_at: str
    supersedes_version: int | None

@dataclass(frozen=True, slots=True)
class ProcedureSummary:
    ref: ProcedureRef
    title: str
    summary: str
    applicability: tuple[str, ...]
    preconditions: tuple[str, ...]
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ProcedureMatch:
    summary: ProcedureSummary
    score: float
    matched_terms: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ProcedureOutcome:
    outcome_id: str
    procedure: ProcedureRef
    run_id: str
    task_id: str
    attempt_id: str
    succeeded: bool
    suspected_failure: bool
    reason: str
    created_at: str

class ProcedurePromotionAuthority(Protocol):
    def authorize(self, candidate: ProcedureRecord, evidence: ProcedureVerificationEvidence) -> None: ...

class ProcedureError(VidbyteSdkError): ...
class ProcedureStoreError(ProcedureError): ...
class ProcedureVersionError(ProcedureError): ...
class ProcedurePromotionError(ProcedureError): ...
class ProcedureNotFoundError(ProcedureError): ...
~~~

#### Logic / Algorithm

1. ProcedureCandidate is caller/model input and intentionally has no status, version, fingerprint, verification, reason, or timestamps. ProcedureLibrary alone assigns those fields when staging.
2. Normalize every text/tuple/mapping field in post-init methods.
3. Reject blank ids, namespace, title, summary, body, applicability, preconditions, and expected outcomes where the status requires them.
4. Validate namespace and caller-proposed ids against [A-Za-z0-9][A-Za-z0-9._-]{0,127}; operation/outcome ids are SDK-generated from safe prefixes plus lowercase hashes. File stores still verify resolved containment before every I/O.
5. Compute content_fingerprint from title, summary, body, applicability, preconditions, expected outcomes, tags, required tools, and environment fingerprint; exclude ids, provenance, timestamps, version, status, and reason.
6. Require task, aligned-drift, exact-candidate-fingerprint, and procedure-fidelity evidence for VERIFIED records and forbid verification on CANDIDATE records.
7. Use ProcedureRef whenever a later run records a load/outcome so a newer version cannot be confused with the artifact actually used.
8. Keep public records frozen and slotted so store implementations cannot mutate prior versions in place.

#### Edge Cases & Error Handling

- Unsupported schema versions raise ProcedureVersionError.
- A candidate may not be loaded through the normal library API.
- A retired/rejected record retains its body/evidence for audit but is hidden from retrieval.
- Content fingerprints are not authorization or correctness proofs; they identify equivalent normalized procedure content.

---

### 6.2 Procedure Serialization, Stores, and Library

**File(s):** vidbyte/procedures/serialization.py, vidbyte/procedures/store.py, vidbyte/procedures/library.py, vidbyte/procedures/stores/__init__.py, vidbyte/procedures/stores/memory.py, vidbyte/procedures/stores/file.py
**Type:** New files

#### What it does

Provides one store protocol, reference in-memory/file backends, schema-safe serialization, deterministic lexical ranking, candidate promotion, compatible retrieval, outcome tracking, deduplication, and retirement.

#### Interface / API

~~~python
class ProcedureStore(Protocol):
    def put(self, record: ProcedureRecord, *, expected_latest_version: int | None) -> None: ...
    def get(self, namespace: str, procedure_id: str, version: int) -> ProcedureRecord: ...
    def latest(self, namespace: str, procedure_id: str) -> ProcedureRecord: ...
    def versions(self, namespace: str, procedure_id: str) -> tuple[ProcedureRecord, ...]: ...
    def list_ids(self, namespace: str) -> tuple[str, ...]: ...
    def list_latest(self, namespace: str) -> tuple[ProcedureRecord, ...]: ...
    def find_by_operation(self, namespace: str, learning_operation_id: str) -> tuple[ProcedureRecord, ...]: ...
    def append_outcome(self, outcome: ProcedureOutcome) -> bool: ...
    def outcomes(self, procedure: ProcedureRef) -> tuple[ProcedureOutcome, ...]: ...

class ProcedureRanker(Protocol):
    def rank(self, query: str, records: Sequence[ProcedureRecord]) -> tuple[ProcedureMatch, ...]: ...

class LexicalProcedureRanker:
    def rank(self, query: str, records: Sequence[ProcedureRecord]) -> tuple[ProcedureMatch, ...]: ...

class ProcedureLibrary:
    def __init__(self, store: ProcedureStore, *, limits: ProcedureLimits | None = None, ranker: ProcedureRanker | None = None) -> None: ...
    def stage(self, candidate: ProcedureCandidate, *, operation_id: str) -> ProcedureRecord: ...
    def promote(self, candidate: ProcedureRef, evidence: ProcedureVerificationEvidence, *, operation_id: str, authority: ProcedurePromotionAuthority) -> ProcedureRecord: ...
    def reject(self, candidate: ProcedureRef, reason: str, *, operation_id: str) -> ProcedureRecord: ...
    def search(self, query: str, *, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = (), limit: int = 5) -> tuple[ProcedureMatch, ...]: ...
    def load(self, procedure_id: str, *, version: int | None = None, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = ()) -> ProcedureRecord: ...
    def record_outcome(self, outcome: ProcedureOutcome, *, retire_after_suspected_failures: int) -> ProcedureRecord | None: ...

class InMemoryProcedureStore(BaseProcedureStore): ...
class FileProcedureStore(BaseProcedureStore):
    def __init__(self, root: str | Path) -> None: ...
~~~

#### Logic / Algorithm

1. Stage validates ProcedureCandidate through library-level ProcedureLimits, computes canonical content fingerprint, chooses a safe deterministic id from operation_id when no prior id is proposed, reads a consistent version-chain snapshot, and writes version 1 CANDIDATE or the next version for an intentional revision with expected_latest_version compare-and-swap. Repeating the same operation returns the byte-equivalent existing record, while reusing an operation id for different content fails closed; a CAS conflict is re-read and retried within a small bound.
2. Promotion requires an exact candidate namespace/id/version/fingerprint ref plus ProcedurePromotionAuthority. It verifies that exact version is CANDIDATE, source ids match, the evidence candidate fingerprint equals the staged content fingerprint, task/drift/fidelity event references are present, every required procedure-fidelity result passed, and evidence is non-empty; then the authority checks the evidence against the active ledger. No latest-candidate inference, default authority, or caller-evidence-only promotion path exists.
3. Before writing a new VERIFIED record, compare content fingerprints with latest verified records in the namespace. When active equivalent content exists, write a terminal REJECTED duplicate version for the candidate with a duplicate-of namespace/id/version reason and return the existing verified record as the learning result.
4. Otherwise promotion writes a new VERIFIED version whose supersedes_version names the prior active VERIFIED version when one exists; it never overwrites the candidate file. REJECTED versions close only their candidate, while RETIRED versions explicitly tombstone the active verified version.
5. Rejection writes a new REJECTED version with a reason.
6. For each namespace/id chain, active_verified scans versions in order: CANDIDATE and REJECTED do not change the active record; VERIFIED replaces it; RETIRED clears it only when it tombstones the active version. A later VERIFIED version may explicitly reactivate the identity. This derived active head is separate from the latest audit record.
7. Search examines active_verified heads for the requested namespace, enforces environment/tool compatibility, ranks lexically, and returns at most the bounded limit.
8. Load recomputes the active head and repeats namespace/environment/required-tool validation instead of trusting a prior search result. It rejects a requested version that is no longer active. Historical versions remain available only through the audit-oriented store API, not normal model retrieval.
9. Outcome recording atomically/idempotently appends immutable evidence against an exact namespace/id/version/fingerprint ProcedureRef. outcome_id is deterministically derived from the source verification event and ProcedureRef. Retirement counts only suspected failures for that exact ref/fingerprint, never older/newer versions. Crossing the threshold writes a RETIRED version that tombstones that still-active version with CAS; resume/retry recalculates if a crash occurs between outcome append and retirement.
10. Every in-memory chain mutation and outcome append holds one store RLock for the whole read/allocate/check/write operation. FileProcedureStore holds its one-writer process lock plus an in-process lock across the same operation and uses temp-file/fsync/os.replace writes; expected_latest_version provides CAS defense against stale callers.
11. FileProcedureStore encodes safe segments under procedures/<namespace>/<id>/<version>.json and outcomes as immutable JSON files.

#### Edge Cases & Error Handling

- Duplicate id/version or operation-id writes return the existing record only when canonical content is identical; conflicting duplicates and exhausted CAS retries fail closed.
- Corrupt JSON, missing required fields, or version mismatch raise typed errors.
- FileProcedureStore supports one writer process; multi-process transactions are not claimed.
- Empty libraries return no matches.
- A tool-set mismatch excludes a record rather than asking the worker to call unavailable capabilities.
- Direct load repeats the same required-tools subset check as search, so a known id cannot bypass compatibility.
- An absent environment fingerprint accepts only records with no fingerprint; callers opt into broader compatibility explicitly.
- Search scoring is deterministic and stable for equal input/order.
- Namespace, procedure, operation, and outcome identifiers are allowlisted/encoded; every resolved read/write path must remain below the configured root before I/O.
- ProcedureStore is a trusted application adapter, not a tamper-proof database. The SDK's VERIFIED guarantee applies to records promoted through ProcedureLibrary with an authority; callers who edit JSON or call low-level store mutation directly are responsible for invalidating that guarantee, and file documentation says so.

---

### 6.3 Procedure Tools

**File(s):** vidbyte/tools/builtins/procedures/__init__.py, vidbyte/tools/builtins/procedures/search.py, vidbyte/tools/builtins/procedures/load.py, vidbyte/tools/builtins/procedures/stage.py, vidbyte/tools/builtins/verified_context/__init__.py, vidbyte/tools/builtins/verified_context/contracts.py, vidbyte/tools/builtins/verified_context/load.py, vidbyte/tools/builtins/__init__.py
**Type:** New tool category plus modified aggregate export

#### What it does

Exposes compact verified procedure retrieval, explicit full procedure/dependency expansion, and candidate-only staging to agents without exposing promotion authority or unverified run state.

#### Interface / API

~~~python
class ProcedureSearchTool(BaseTool):
    def __init__(self, library: ProcedureLibrary, *, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = (), max_results: int = 5) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...

class ProcedureLoadTool(BaseTool):
    def __init__(self, library: ProcedureLibrary, context_manager: ContextManager, *, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = (), max_body_chars: int = 20000, max_loaded_records: int = 3, max_total_loaded_chars: int = 30000) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...

class StageProcedureTool(BaseTool):
    def __init__(self, library: ProcedureLibrary, *, run_id: str, task_id: str, attempt_id: str, namespace: str, environment_fingerprint: str = "", max_body_chars: int = 20000) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...

@dataclass(frozen=True, slots=True)
class VerifiedContextRef:
    kind: str  # task_result | artifact
    run_id: str
    task_id: str
    item_id: str
    content_hash: str
    summary: str

class VerifiedContextSource(Protocol):
    def load_verified(self, ref: VerifiedContextRef, *, allowed_task_ids: Sequence[str]) -> str: ...

class VerifiedContextLoadTool(BaseTool):
    def __init__(self, source: VerifiedContextSource, context_manager: ContextManager, *, allowed_task_ids: Sequence[str], max_loaded_items: int = 3, max_total_loaded_chars: int = 30000, max_item_chars: int = 16000) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
~~~

#### Logic / Algorithm

1. procedure_search accepts query and optional bounded limit, returning ref/title/summary/applicability/preconditions/tags/required-tools and score.
2. procedure_load accepts one id and optional version inside its constructor-bound namespace, rechecks environment and constructor-bound available-tools compatibility, loads only the active VERIFIED record, enforces unique-record and cumulative-character budgets shared by that role's tool instance, formats the full record as untrusted reference text, and upserts a frozen MemoryContextItem with primitive id procedure:<namespace>:<id>:<version>.
3. procedure_load returns only a compact acknowledgment in ToolResult so the full body is not duplicated in both the tool result and context primitive.
4. procedure_stage accepts title, summary, body, applicability, preconditions, expected outcomes, tags, required tools, source evidence event ids, and optional prior id. Evidence ids must belong to the constructor-bound successful attempt allowlist. It derives a deterministic learning-operation id from namespace/run/task/attempt, proposed prior id-or-new marker, and candidate fingerprint, calls ProcedureLibrary.stage idempotently, and returns the namespace/id/version/fingerprint candidate handle.
5. verified_context_load accepts one stable VerifiedContextRef handle already advertised in the capsule, revalidates that the source task is a currently VERIFIED transitive dependency with matching definition/content hash, resolves the committed TaskResult or ArtifactRef through the ledger/source, applies item/cumulative bounds, and upserts one frozen untrusted-data MemoryContextItem.
6. The curator receives StageProcedureTool. Planner/worker/repair roles receive procedure search/load. Worker/repair scopes of verified_context_load include only transitive VERIFIED dependencies; revision-planner/auditor/synthesizer scopes include all currently VERIFIED non-invalidated run results. Task/procedure verifiers receive neither retrieval family and instead receive their exact bounded evidence directly.

#### Edge Cases & Error Handling

- Search/load use READ permission; stage uses WRITE.
- Load rejects candidate/rejected/retired/superseded records, stale search handles, wrong namespace, incompatible environment, and oversized bodies.
- Stage rejects empty/oversized/invalid candidates and cannot accept status or verification arguments.
- No promote/verify/retire/delete tool exists.
- Procedure contents are framed as data and cannot alter permission policy.
- Verified-context load rejects unrelated, pending, rejected, invalidated, hash-mismatched, missing, oversized, or path-escaping artifact references. It never reads arbitrary handles supplied outside the capsule allowlist.

---

### 6.4 Long-Running Public Contracts, Settings, and Errors

**File(s):** vidbyte/paradigms/types.py, vidbyte/paradigms/context_minimal_fanout/types.py, vidbyte/paradigms/long_running/types.py, vidbyte/paradigms/long_running/errors.py
**Type:** New shared/feature files plus backward-compatible extraction from an existing file

#### What it does

Extracts the existing AgentRoleSettings into the shared paradigm layer (with its current normalization and with_overrides behavior), re-exports it from context_minimal_fanout for compatibility, and defines the immutable goal/task/attempt/verification/drift/result/state/event contracts, typed start/resume options, controller limits, optional validation/isolation protocols, and typed errors.

#### Interface / API

~~~python
class LongRunningTaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    BLOCKED = "blocked"

class LongRunningStopReason(str, Enum):
    COMPLETED = "completed"
    PARTIAL_BLOCKED = "partial_blocked"
    VERIFICATION_EXHAUSTED = "verification_exhausted"
    NO_PROGRESS = "no_progress"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMEOUT = "timeout"
    USAGE_UNAVAILABLE = "usage_unavailable"
    RECOVERY_REQUIRED = "recovery_required"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"

class LongRunningRunStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"

class InterruptedAttemptPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    RETRY_IF_READ_ONLY = "retry_if_read_only"
    ACCEPT_CALLER_RECONCILIATION = "accept_caller_reconciliation"

class DriftDecision(str, Enum):
    CONTINUE = "continue"
    REPLAN = "replan"
    SYNTHESIZE = "synthesize"
    FAIL = "fail"

@dataclass(frozen=True, slots=True)
class GoalContract:
    original_prompt: str
    success_criteria: tuple[str, ...]
    invariants: tuple[str, ...]
    non_goals: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class LongRunningTask:
    task_id: str
    title: str
    instructions: str
    dependencies: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    procedure_query: str
    priority: int = 0
    owned_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    verification_expectations: tuple[str, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    definition_hash: str = ""

@dataclass(frozen=True, slots=True)
class LongRunningTaskState:
    task_id: str
    status: LongRunningTaskStatus = LongRunningTaskStatus.PENDING
    attempt_count: int = 0
    verified_result_id: str = ""
    invalidation_reason: str = ""
    consumed_dependency_hashes: tuple[tuple[str, str], ...] = ()

@dataclass(frozen=True, slots=True)
class TaskGraph:
    version: int
    tasks: tuple[LongRunningTask, ...]
    rationale: str = ""

@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    uri: str
    media_type: str
    summary: str
    content_hash: str
    size_bytes: int | None

@dataclass(frozen=True, slots=True)
class TaskAttempt:
    attempt_id: str
    task_id: str
    attempt_number: int
    strategy: str
    summary: str
    artifacts: tuple[ArtifactRef, ...]
    evidence: tuple[str, ...]
    loaded_procedures: tuple[ProcedureRef, ...]
    blockers: tuple[str, ...]
    transcript_event_id: str
    tokens_used: int | None

@dataclass(frozen=True, slots=True)
class TaskResult:
    result_id: str
    task_id: str
    definition_hash: str
    summary: str
    detail: str
    artifacts: tuple[ArtifactRef, ...]
    evidence: tuple[str, ...]
    verification_event_id: str
    content_hash: str

@dataclass(frozen=True, slots=True)
class ValidatorResult:
    validator_id: str
    validator_version: str
    config_fingerprint: str
    required: bool
    passed: bool
    evidence: tuple[str, ...]
    error_code: str
    error_message: str
    duration_ms: int

@dataclass(frozen=True, slots=True)
class CriterionResult:
    criterion_id: str
    criterion: str
    passed: bool
    observations: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    violations: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    criteria: tuple[CriterionResult, ...]
    evidence: tuple[str, ...]
    violations: tuple[str, ...]
    repair_instructions: tuple[str, ...]
    failure_signature: str
    suspected_procedures: tuple[ProcedureRef, ...]
    requires_replan: bool
    validator_results: tuple[ValidatorResult, ...]
    transcript_event_id: str

@dataclass(frozen=True, slots=True)
class DriftReview:
    decision: DriftDecision
    aligned: bool
    issues: tuple[str, ...]
    invalidate_task_ids: tuple[str, ...]
    proposed_work: tuple[str, ...]
    rationale: str

@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    source_event_id: str
    content_hash: str
    summary: str
    payload: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class TaskValidationContext:
    run_id: str
    contract: GoalContract
    task: LongRunningTask
    attempt: TaskAttempt
    evidence: tuple[EvidenceRecord, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    workspace_root: str
    deadline_at: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ProcedureValidationContext:
    run_id: str
    contract: GoalContract
    task: LongRunningTask
    attempt: TaskAttempt
    task_verification: VerificationResult
    drift_review: DriftReview
    candidate: ProcedureRecord
    source_event_ids: tuple[str, ...]
    source_records: tuple[EvidenceRecord, ...]
    available_tools: tuple[str, ...]
    environment_fingerprint: str
    deadline_at: str | None

@dataclass(frozen=True, slots=True)
class LongRunningRunOptions:
    run_id: str | None = None
    success_criteria: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class LongRunningResumeOptions:
    allow_settings_change: bool = False
    settings_change_reason: str = ""
    interrupted_attempt_policy: InterruptedAttemptPolicy = InterruptedAttemptPolicy.FAIL_CLOSED
    reconciliation_reason: str = ""

class BehaviorFingerprintProvider(Protocol):
    def behavior_fingerprint(self) -> Mapping[str, Any]: ...

@dataclass(frozen=True, slots=True)
class LongRunningUsage:
    observed_input_tokens: int
    observed_output_tokens: int
    calls_with_unknown_usage: int
    complete: bool

@dataclass(frozen=True, slots=True)
class LongRunningState:
    run_id: str
    status: LongRunningRunStatus
    contract: GoalContract
    graph: TaskGraph
    task_states: tuple[LongRunningTaskState, ...]
    task_results: tuple[TaskResult, ...]
    attempts: tuple[TaskAttempt, ...]
    verifications: tuple[VerificationResult, ...]
    drift_reviews: tuple[DriftReview, ...]
    usage: LongRunningUsage
    settings_fingerprint: str
    revision: int
    cycle_count: int
    replan_count: int
    started_at: str
    deadline_at: str | None
    stop_reason: LongRunningStopReason | None

@dataclass(frozen=True, slots=True)
class LongRunningSettings:
    planner: AgentRoleSettings = ...
    worker: AgentRoleSettings = ...
    repairer: AgentRoleSettings = ...
    verifier: AgentRoleSettings = ...
    curator: AgentRoleSettings = ...
    procedure_verifier: AgentRoleSettings = ...
    synthesizer: AgentRoleSettings = ...
    auditor: AgentRoleSettings = ...
    max_tasks: int = 32
    max_plan_attempts: int = 3
    max_attempts_per_task: int = 3
    max_replans: int = 4
    max_cycles: int = 128
    max_no_progress_cycles: int = 2
    max_controller_runtime_seconds: float | None = None
    max_observed_tokens: int | None = None
    require_usage_reporting_for_token_budget: bool = True
    procedure_search_limit: int = 5
    max_procedure_body_chars: int = 20000
    retire_after_suspected_failures: int = 3
    max_finalization_attempts: int = 2
    require_procedure_promotion: bool = False
    include_minimal_toolset: bool = True
    worker_include_execution: bool = False
    worker_include_write: bool = False
    unsafe_allow_unisolated_side_effects: bool = False
    default_tool_root: str | Path = "."
    procedure_namespace: str = "default"
    environment_fingerprint: str = ""
    component_fingerprints: Mapping[str, str] = field(default_factory=dict)
    max_visible_tool_result_chars: int = 4000
    max_role_messages: int = 80
    max_role_history_chars: int = 60000
    max_context_capsule_chars: int = 48000
    max_contract_chars: int = 20000
    max_task_instructions_chars: int = 12000
    max_plan_summary_chars: int = 12000
    max_dependency_summary_chars: int = 4000
    max_task_result_detail_chars: int = 16000
    max_artifact_excerpt_chars: int = 12000
    max_procedure_card_chars: int = 1200
    max_loaded_procedures_per_role: int = 3
    max_loaded_procedure_chars_per_role: int = 30000
    max_loaded_verified_context_items_per_role: int = 3
    max_loaded_verified_context_chars_per_role: int = 30000
    max_latest_evidence_chars: int = 12000
    max_procedure_verification_evidence_chars: int = 30000
    max_visible_context_tokens: int | None = None
    require_ledger_persistence: bool = True

@dataclass(frozen=True, slots=True)
class LongRunningResult:
    run_id: str
    status: LongRunningRunStatus
    resumable: bool
    final_output: str
    stop_reason: LongRunningStopReason
    succeeded: bool
    contract: GoalContract
    graph: TaskGraph
    task_states: tuple[LongRunningTaskState, ...]
    task_results: tuple[TaskResult, ...]
    attempts: tuple[TaskAttempt, ...]
    verifications: tuple[VerificationResult, ...]
    promoted_procedures: tuple[ProcedureSummary, ...]
    procedure_outcomes: tuple[ProcedureOutcome, ...]
    usage: LongRunningUsage
    ledger: RunLedgerSnapshot
    metadata: Mapping[str, Any]
~~~

#### Logic / Algorithm

1. AgentRoleSettings moves without behavioral or import breakage to vidbyte.paradigms.types; the old concrete-family module imports/re-exports the same class.
2. Settings validate every positive bound, paired option, namespace, path, role name, exact-input size, and child context budget against max_context_capsule_chars.
3. Tuple/live-object fields normalize through the existing AgentRoleSettings and LongRunningSettings.with_overrides behavior.
4. TaskGraph contains immutable task definitions. LongRunningTaskState carries status, attempts, accepted-result links, invalidation reason, and consumed dependency hashes separately so plan identity cannot be silently changed by runtime mutation.
5. Graph/state helpers validate structure, compute ready tasks, descendants, owned-path conflicts, and stable definition hashes that exclude runtime state.
6. GoalContract always retains original_prompt exactly; caller criteria are preserved first, and non-duplicative planner additions follow without weakening caller text.
7. LongRunningResult is constructed from committed ledger state, never from an unverified worker response.
8. COMPLETED and FAILED are terminal. PAUSED results (for safe budget/deadline/usage stops) and RECOVERY_REQUIRED results are resumable; cancellation checkpoints PAUSED and re-raises rather than returning a result.

#### Edge Cases & Error Handling

- LongRunningConfigurationError handles invalid limits/settings.
- LongRunningPlanError carries validation conflicts and candidate graph version.
- LongRunningVerificationError carries run/task/attempt ids.
- LongRunningLedgerError and LongRunningResumeError carry safe run/store details.
- Infrastructure errors raise; expected bounded failure returns a non-success LongRunningResult.

---

### 6.5 Run Ledger and Resume

**File(s):** vidbyte/paradigms/long_running/ledger.py
**Type:** New file

#### What it does

Implements the deterministic append-only event ledger, JSON-safe serializer, state checkpoints, in-memory store, atomic file store, settings fingerprinting, and resume loading.

#### Interface / API

~~~python
class LongRunningEventKind(str, Enum):
    RUN_STARTED = "run_started"
    RUN_RESUMED = "run_resumed"
    SETTINGS_CHANGE_ACCEPTED = "settings_change_accepted"
    PLAN_ATTEMPTED = "plan_attempted"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"
    PLAN_ACCEPTED = "plan_accepted"
    TASK_STARTED = "task_started"
    ROLE_STARTED = "role_started"
    ROLE_COMPLETED = "role_completed"
    ATTEMPT_RECORDED = "attempt_recorded"
    VERIFICATION_COMPLETED = "verification_completed"
    REPAIR_SCHEDULED = "repair_scheduled"
    TASK_VERIFIED = "task_verified"
    TASK_REJECTED = "task_rejected"
    DRIFT_REVIEWED = "drift_reviewed"
    PLAN_REVISED = "plan_revised"
    TASK_INVALIDATED = "task_invalidated"
    PROCEDURE_LEARNING_INTENT = "procedure_learning_intent"
    PROCEDURE_STAGED = "procedure_staged"
    PROCEDURE_FIDELITY_VERIFIED = "procedure_fidelity_verified"
    PROCEDURE_PROMOTED = "procedure_promoted"
    PROCEDURE_REJECTED = "procedure_rejected"
    PROCEDURE_RETIRED = "procedure_retired"
    PROCEDURE_LEARNING_COMPLETED = "procedure_learning_completed"
    PROCEDURE_OUTCOME_INTENT = "procedure_outcome_intent"
    PROCEDURE_OUTCOME_COMPLETED = "procedure_outcome_completed"
    SYNTHESIZED = "synthesized"
    FINAL_AUDITED = "final_audited"
    CHECKPOINTED = "checkpointed"
    RUN_PAUSED = "run_paused"
    RECOVERY_REQUIRED = "recovery_required"
    RUN_FAILED = "run_failed"
    RUN_COMPLETED = "run_completed"

@dataclass(frozen=True, slots=True)
class LongRunningEvent:
    schema_version: int
    event_id: str
    run_id: str
    seq: int
    revision: int
    kind: LongRunningEventKind
    created_at: str
    state_hash_after: str
    task_id: str = ""
    attempt_id: str = ""
    role: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class RunLedgerSnapshot:
    schema_version: int
    run_id: str
    revision: int
    last_event_seq: int
    state: LongRunningState
    settings_fingerprint: str
    last_event_hash: str
    created_at: str
    updated_at: str

class RunLedgerStore(Protocol):
    def create(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent) -> None: ...
    def commit(self, snapshot: RunLedgerSnapshot, event: LongRunningEvent, *, expected_last_event_seq: int) -> None: ...
    def load(self, run_id: str) -> RunLedgerSnapshot: ...
    def events(self, run_id: str) -> tuple[LongRunningEvent, ...]: ...

class RunLedger:
    def __init__(self, snapshot: RunLedgerSnapshot, store: RunLedgerStore, *, required: bool = True) -> None: ...
    def append(self, kind: LongRunningEventKind, payload: Mapping[str, Any]) -> LongRunningEvent: ...
    def commit(self, state: LongRunningState, kind: LongRunningEventKind, payload: Mapping[str, Any]) -> LongRunningEvent: ...
    def snapshot(self) -> RunLedgerSnapshot: ...

class InMemoryRunLedgerStore: ...
class FileRunLedgerStore:
    def __init__(self, root: str | Path) -> None: ...
~~~

#### Logic / Algorithm

1. New run creates revision 0 state and RUN_STARTED event.
2. Every transition computes the next event and compact post-transition snapshot together and passes them to one store commit operation with expected_last_event_seq before another role begins.
3. Available public transcripts are always obtained from BaseAgent.export_state().history plus normalized tool/reply metadata after SDK/provider capture limits; there is no disable flag and no hidden reasoning field is invented. The compact state snapshot keeps references/hashes, while the immutable event envelope owns the raw role record once.
4. Serializer recursively converts dataclasses/enums/tuples/mappings to JSON-safe data, scrubs secret-looking keys, and emits a dropped-type marker for live objects.
5. Behavioral fingerprinting separately hashes all non-secret controller limits, role provider/model/temperature/max-token settings, prompt key/content hashes, tool name/version/permission/input-schema fingerprints, middleware identity/config, validator/isolator/ranker ids and versions, procedure/ledger schema and store identity, and caller-supplied safe component_fingerprints. api_key/credentials and ephemeral object ids are excluded.
6. Live behavioral components implement BehaviorFingerprintProvider. Durable resume configuration fails closed when a live component cannot be stably fingerprinted and has no explicit component_fingerprints entry; a class name alone is insufficient.
7. File layout is runs/<run_id>/state.json plus immutable events/<seq>-<event_id>.json transition envelopes. Each envelope contains the public event and the compact resulting snapshot with matching revision, sequence, and hashes.
8. In-memory commit holds one RLock across sequence/revision check and update. Under its in-process plus one-writer process lock, file commit compare-checks expected_last_event_seq, atomically writes/fsyncs the immutable envelope first, then atomically replaces the state.json head. The envelope is the crash-recovery authority; state.json is the fast head.
9. Resume loads and validates monotonic envelopes, uses the newest valid envelope snapshot when state.json is absent or lags, repairs the head when writable, and rejects a head that points beyond or disagrees with the immutable envelope chain.
10. Resume then validates schema, terminal/resumable status, event sequence, settings fingerprint, and referenced task ids. An allowed mismatch requires a non-empty reason and journals old/new fingerprints plus safe field/component diffs before work; goal contract, run/store identity, schema, procedure namespace, and existing artifact hashes cannot change.
11. Before launching a role, resume reconciles incomplete PROCEDURE_LEARNING_INTENT and PROCEDURE_OUTCOME_INTENT events by querying ProcedureStore with their deterministic operation/outcome ids. It records completion for an already-applied equivalent mutation, safely retries an absent mutation, and fails closed on conflicting content.

#### Edge Cases & Error Handling

- Duplicate run ids, duplicate sequence files, envelope/hash disagreement, and non-monotonic revisions fail closed.
- Caller-provided run ids must match the canonical lr_<lowercase-hex> form. Run/event file segments are internally generated or allowlisted, and every resolved FileRunLedgerStore path must remain under its configured root.
- Corrupt or unsupported files raise LongRunningResumeError.
- Required persistence failure stops the controller. Best-effort mode is available only when explicitly configured and records errors in memory/result metadata.
- Cancellation writes PAUSED best effort and propagates.
- Completed runs cannot resume unless an explicit future design adds reopening.
- File store is one writer per run; readers may inspect immutable events concurrently.
- RunLedgerStore and ProcedureStore are not one transaction. The intent/idempotency/reconciliation protocol gives exactly-once logical effects for one controller writer; it does not claim a distributed transaction.
- InMemoryRunLedgerStore retains all captured events/transcripts until the store object is released and therefore scales with the bounded run. It is for ephemeral/small runs; FileRunLedgerStore is the documented default recommendation for genuinely long runs and caller-controlled retention.

---

### 6.6 Context Broker and Role Agent Factory

**File(s):** vidbyte/paradigms/long_running/context.py, vidbyte/middleware/compaction/context_compaction.py, vidbyte/middleware/compaction/engine.py, vidbyte/middleware/compaction/strategies.py
**Type:** New feature file plus additive reusable compaction enhancement

#### What it does

Builds fresh role contexts, frozen managed primitives, bounded procedure/dependency cards, retrieval tools, structured-output tools, minimal filesystem toolsets, mandatory aggregate compaction guards, and role metadata. It also extends the existing provider-boundary compactor with a deterministic character ceiling reusable outside this paradigm.

#### Interface / API

~~~python
class LongRunningContextBroker:
    def build_planner(self, state: LongRunningState, builder: OutputSchemaBuilder, *, validation_errors: Sequence[str] = ()) -> BaseAgent: ...
    def build_worker(self, state: LongRunningState, task: LongRunningTask, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> BaseAgent: ...
    def build_repairer(self, state: LongRunningState, task: LongRunningTask, latest_attempt: TaskAttempt, verification: VerificationResult, matches: Sequence[ProcedureMatch], builder: OutputSchemaBuilder) -> BaseAgent: ...
    def build_verifier(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, builder: OutputSchemaBuilder) -> BaseAgent: ...
    def build_procedure_verifier(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, candidate: ProcedureRecord, builder: OutputSchemaBuilder) -> BaseAgent: ...
    def build_role(self, role: str, state: LongRunningState, manager: ContextManager, builder: OutputSchemaBuilder | None = None, extra_tools: Sequence[object] = ()) -> BaseAgent: ...

MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(
    max_messages: int | None = None,
    max_tokens: int | None = None,
    token_counter: TokenCounter | None = None,
    max_chars: int | None = None,
) -> MessageHistoryCompactionMiddleware
~~~

#### Logic / Algorithm

1. Allocate a new ContextManager for every method call.
2. Place a frozen TaskContextItem containing the exact root contract at top-of-context.
3. Place a compact PlanContextItem with task titles/status/current selection, not full raw attempts.
4. Place ProgressContextItem with bounded verified dependency summaries, stable VerifiedContextRef handles for each result/artifact, and current budget.
5. Place procedure cards as a bounded frozen MemoryContextItem containing handles/summaries only; truncate per-card text and total card count/characters deterministically without changing stored source records.
6. Bind ProcedureSearchTool and ProcedureLoadTool to planner/worker/repair contexts. Bind VerifiedContextLoadTool to worker/repair (current task's transitive VERIFIED dependencies) and revision-planner/auditor/synthesizer (all current VERIFIED non-invalidated results), with a fresh allowlist/budget per role.
7. Bind StageProcedureTool only to curator context.
8. Give the fresh procedure verifier the exact staged candidate, the successful attempt's bounded public tool/action trace, task verification evidence, and drift-review evidence; it receives no staging/promotion or write tools.
9. Add OutputSchemaBuilder tools for structured roles.
10. Add only READ-permission ParadigmMinimalToolset tools to planning/verifier/auditor/finalizer roles. Add optional execution/write tools only to worker/repairer. Reject every non-READ tool configured for verification roles.
11. Apply item caps first. If the initial capsule still exceeds max_context_capsule_chars, remove lowest-ranked procedure cards, then optional artifact summaries, then dependency detail beyond stable handles; never remove/alter the exact contract, current task, acceptance criteria, or latest bounded repair evidence. Fail closed if mandatory content still cannot fit.
12. Append caller tools/middleware without mutating settings, then append ToolResultCompactionMiddleware.truncate(max_visible_tool_result_chars) and a mandatory final trim_with_provider_boundaries(max_messages=max_role_messages, max_tokens=max_visible_context_tokens, max_chars=max_role_history_chars) guard. The character count covers canonical visible roles/names/text/tool arguments/results. The strategy preserves system/current-user inputs, drops oldest complete provider/tool-call groups until all configured bounds pass, never separates a tool result from its call, and fails before the model call if mandatory messages alone exceed a bound.
13. Reject an original prompt/run contract above max_contract_chars and planner tasks/instructions/criteria above their declared caps; exact immutable inputs are never silently clipped.
14. Tag agents with run id, role, graph version, task id, and attempt number.

#### Edge Cases & Error Handling

- A role with no configured runner/provider/model follows current BaseAgent inference behavior and surfaces normal configuration errors.
- Tool names are deduplicated deterministically; conflicting distinct tools with the same name raise configuration error.
- Verifier/auditor/finalizer receive only READ-permission tools; executable verification belongs in trusted TaskValidator/ProcedureValidator objects. Unknown-permission or non-READ role tools fail configuration.
- max_visible_context_tokens is optional because token counting is model/provider dependent.
- Character caps remain mandatory and cumulative, so repeated procedure_load calls cannot grow one role context without bound.
- Mandatory provider-history trimming is the final before-model-call transform; caller middleware cannot disable it. Raw pre-compaction public history still goes to the audit ledger.
- Compaction changes only model-visible provider messages; the ledger captures raw available state.

---

### 6.7 Planning and Plan Reconciliation

**File(s):** vidbyte/paradigms/long_running/planning.py
**Type:** New file

#### What it does

Runs initial/revision planning, parses structured outputs, validates task graphs, schedules ready tasks, and reconciles revisions without erasing verified history.

#### Interface / API

~~~python
class LongRunningPlanner:
    async def create(self, prompt: str, state: LongRunningState) -> tuple[GoalContract, TaskGraph]: ...
    async def revise(self, state: LongRunningState, review: DriftReview) -> TaskGraph: ...

class TaskGraphValidator:
    def validate(self, graph: TaskGraph, *, max_tasks: int) -> None: ...
    def conflicts(self, graph: TaskGraph) -> tuple[str, ...]: ...

class TaskGraphReconciler:
    def reconcile(self, current: TaskGraph, states: Sequence[LongRunningTaskState], proposed: TaskGraph, *, invalidations: Mapping[str, str]) -> tuple[TaskGraph, tuple[LongRunningTaskState, ...]]: ...
    def invalidate_descendants(self, graph: TaskGraph, states: Sequence[LongRunningTaskState], task_ids: Sequence[str], reason: str) -> tuple[LongRunningTaskState, ...]: ...

class ReadyTaskScheduler:
    def next(self, graph: TaskGraph, states: Sequence[LongRunningTaskState]) -> LongRunningTask | None: ...
~~~

#### Logic / Algorithm

1. Planner receives procedure cards relevant to the root goal plus read-only exploration tools.
2. It declares GoalContract/tasks output fields and appends structured tasks.
3. Invalid structured output or deterministic graph errors feed one fresh planning retry.
4. Scheduler joins immutable definitions with runtime states, filters PENDING tasks whose dependencies are VERIFIED, and sorts by priority descending then id.
5. Revision input contains the exact contract, current compact graph, verified result summaries, latest failure, drift issues, and budgets.
6. Reconciler preserves verified definitions unless an explicit invalidation reason exists.
7. Explicit invalidation changes runtime state for the named task and all descendants to INVALIDATED without mutating definitions; historical results and consumed dependency hashes remain in the ledger.
8. Removed pending tasks become BLOCKED/CANCELLED-style historical entries instead of disappearing.
9. Owned-path checks normalize separators/case according to the configured workspace, detect equal and ancestor/descendant overlap, and require overlapping writers to be ordered by dependency so consumed dependency hashes can drive invalidation.
10. The revised graph is validated before commit.

#### Edge Cases & Error Handling

- No ready task with pending nodes indicates missing/invalidated dependencies and triggers audit/replan, not success.
- A proposed graph that mutates a verified node without invalidation is rejected.
- Reusing an id for different normalized instructions/criteria is rejected.
- Owned-path validation is conservative metadata validation, not proof of semantic isolation; undeclared external side effects remain outside its guarantee.

---

### 6.8 Task Execution and Repair

**File(s):** vidbyte/paradigms/long_running/execution.py
**Type:** New file

#### What it does

Runs one fresh worker or repair attempt, captures raw records, parses TaskAttempt, invokes optional attempt isolation hooks, and decides retry versus replan/no-progress.

#### Interface / API

~~~python
class TaskExecutionService:
    async def execute(self, state: LongRunningState, task: LongRunningTask) -> TaskAttempt: ...
    async def repair(self, state: LongRunningState, task: LongRunningTask, latest_attempt: TaskAttempt, verification: VerificationResult) -> TaskAttempt: ...
    def no_progress(self, attempts: Sequence[TaskAttempt], verifications: Sequence[VerificationResult]) -> bool: ...

class AttemptIsolationStatus(str, Enum):
    OPEN = "open"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    UNKNOWN = "unknown"

@dataclass(frozen=True, slots=True)
class AttemptLease:
    isolator_id: str
    isolator_version: str
    lease_id: str
    metadata: Mapping[str, Any]

class AttemptIsolator(Protocol):
    isolator_id: str
    isolator_version: str
    def behavior_fingerprint(self) -> Mapping[str, Any]: ...
    async def begin(self, run_id: str, task: LongRunningTask, attempt_id: str) -> AttemptLease: ...
    async def recover(self, lease: AttemptLease) -> AttemptIsolationStatus: ...
    async def commit(self, lease: AttemptLease, verification: VerificationResult) -> None: ...
    async def rollback(self, lease: AttemptLease, verification: VerificationResult) -> None: ...
~~~

#### Logic / Algorithm

1. Retrieve compatible procedure cards from ProcedureLibrary using task.procedure_query.
2. Inspect the effective worker/repair tool permissions. Non-READ tools require an AttemptIsolator unless unsafe_allow_unisolated_side_effects is explicitly set; record the unsafe opt-in before work.
3. Begin an optional serializable attempt isolation lease and checkpoint it before exposing non-READ tools.
4. Build a fresh worker/repairer context and run the agent.
5. Persist raw public transcript, procedure_load tool records, and reply metadata before parsing/verification.
6. Parse the run-local output builder into TaskAttempt; fallback assistant text may populate summary but cannot fabricate missing strategy/evidence fields. Replace any model-claimed procedure usage with authoritative ProcedureRef values derived from successful load records.
7. A rejected verification calls isolator.rollback; accepted verification calls isolator.commit. Neither transition is considered complete until checkpointed.
8. Without an isolator, a rejected/interrupted attempt that successfully invoked any non-READ tool moves the run to RECOVERY_REQUIRED and blocks every other task; it never silently continues on a possibly contaminated environment.
9. Normalize strategy plus verifier failure signature. Repeated pairs meet the no-progress rule.
10. Provider/tool exceptions become failed attempt events and follow the same bounded repair/replan policy only when isolation/read-only evidence makes recovery safe.

#### Edge Cases & Error Handling

- No isolator means logical rollback only; the result/ledger flags external_side_effects_not_rolled_back when any non-READ tool actually succeeded.
- The prior warning is terminal for scheduling after a rejected non-READ call: unsafe allowance permits the attempt to start, not automatic continuation after contamination.
- Rollback failure is recorded and moves the run to RECOVERY_REQUIRED (or terminal FAILED with no further scheduling); ordinary replan is forbidden on potentially contaminated state.
- Worker output may be empty, malformed, or omit evidence; verifier then fails closed.
- A procedure load performed during an attempt is captured by successful tool metadata as an exact id/version/content fingerprint and linked to outcome accounting; failed loads and mere search results do not count as use.
- Resume calls isolator.recover for an ACTIVE lease. ROLLED_BACK permits a fresh attempt. COMMITTED permits logical task commit only when a matching persisted passing verification event exists; otherwise it becomes RECOVERY_REQUIRED. OPEN/UNKNOWN pauses for rollback or explicit caller reconciliation. A READ-only interrupted attempt is recorded as rejected/interrupted and may retry under its normal budget.

---

### 6.9 Verification, Drift, Procedure Learning, and Finalization

**File(s):** vidbyte/paradigms/long_running/verification.py
**Type:** New file

#### What it does

Owns task verification, deterministic validator combination, drift review, procedure curation/promotion/outcomes, final synthesis, and final global audit.

#### Interface / API

~~~python
class TaskValidator(Protocol):
    validator_id: str
    validator_version: str
    required: bool
    timeout_seconds: float
    def behavior_fingerprint(self) -> Mapping[str, Any]: ...
    async def validate(self, context: TaskValidationContext) -> ValidatorResult: ...

class ProcedureValidator(Protocol):
    validator_id: str
    validator_version: str
    required: bool
    timeout_seconds: float
    def behavior_fingerprint(self) -> Mapping[str, Any]: ...
    async def validate(self, context: ProcedureValidationContext) -> ProcedureCheckResult: ...

class VerificationService:
    async def verify_task(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt) -> VerificationResult: ...
    async def audit_drift(self, state: LongRunningState, latest: VerificationResult | None = None) -> DriftReview: ...
    async def verify_final(self, state: LongRunningState, candidate: str) -> VerificationResult: ...

class ProcedureLearningService:
    async def curate_verify_and_promote(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult, drift: DriftReview) -> tuple[ProcedureRecord, ...]: ...
    def record_loaded_outcomes(self, state: LongRunningState, task: LongRunningTask, attempt: TaskAttempt, verification: VerificationResult) -> tuple[ProcedureOutcome, ...]: ...

class LedgerProcedurePromotionAuthority(ProcedurePromotionAuthority):
    def __init__(self, ledger: RunLedger) -> None: ...
    def authorize(self, candidate: ProcedureRecord, evidence: ProcedureVerificationEvidence) -> None: ...

class FinalizationService:
    async def synthesize(self, state: LongRunningState, critique: VerificationResult | None = None) -> str: ...
~~~

TaskValidator and ProcedureValidator are trusted, side-effect-free inspection contracts. Implementations that need commands must use read-only checks or their own transactional sandbox; the paradigm cannot police arbitrary Python supplied by the caller.

#### Logic / Algorithm

1. Verifier uses fresh READ-permission inspection tools and emits exactly one CriterionResult per stable acceptance-criterion id; missing, duplicate, unknown, or reordered-with-changed-text criteria fail closed. Trusted deterministic validators, not the model, run executable assertions.
2. Run configured deterministic validators under the smaller of their declared timeout and the remaining controller deadline. Normalize every return/timeout/exception into ValidatorResult (task) or ProcedureCheckResult (procedure) with stable id/version/config fingerprint, required flag, safe error, evidence, and duration; all required results must pass.
3. Reject duplicate validator ids and build the combined VerificationResult with fail-closed semantics.
4. After local task success, run the drift auditor before recording procedure success outcomes or teaching new procedures.
5. If the drift review is aligned and does not invalidate the source task, record exact-version success outcomes and run the curator with StageProcedureTool.
6. Deterministically validate each staged candidate and its source_evidence_event_ids against the successful attempt allowlist. Materialize those exact public records up to max_procedure_verification_evidence_chars; reject/decline promotion rather than truncate away required evidence. Then run a fresh procedure verifier against the exact candidate fingerprint, selected successful action/tool evidence, task verification evidence, and aligned drift review. Combine it fail-closed with configured required ProcedureValidator results.
7. Re-read the candidate by namespace/id/version, reject if its fingerprint differs from the verified fingerprint, and attach all task/drift/fidelity evidence.
8. Commit a PROCEDURE_LEARNING_INTENT containing the deterministic operation id and exact candidate/evidence hashes, then call idempotent promotion with LedgerProcedurePromotionAuthority. The authority re-reads the active ledger and matches source task status, attempt, task-verification event, latest applicable aligned drift event, procedure-fidelity results, and candidate fingerprint before the library writes. Commit PROCEDURE_LEARNING_COMPLETED afterward. A rejected candidate remains auditable but non-retrievable.
9. Write every success/failure outcome through the same intent/idempotent-mutation/completion sequence. On task failure, record outcomes only for exact ProcedureRef values explicitly suspected by the verifier.
10. Auditor receives exact contract plus compact committed state and emits bounded decision codes.
11. Synthesis receives only VERIFIED, non-invalidated task result bodies/summaries and root contract.
12. Final verification uses the same fail-closed task-verification combination against root criteria and actual read-only state.

#### Edge Cases & Error Handling

- Curator may stage zero candidates; this does not undo task success.
- A locally verified task that fails/invalidates under drift review teaches no success outcome and stages no procedure.
- Candidate stage/fidelity/promotion errors are recorded. By default they remain visible warnings and do not undo task success. When require_procedure_promotion=True, the run cannot return COMPLETED unless at least one candidate from the run is newly promoted or deduplicated to an existing active VERIFIED procedure; individual non-reusable tasks may still curate zero.
- A crash can leave a non-retrievable candidate whose stage tool record was not yet journaled. Its deterministic operation id makes replay return the same record; orphan candidates remain harmless/auditable and may be cleaned only by an explicit future maintenance API.
- A verifier false positive remains possible. Documentation defines VERIFIED operationally and recommends deterministic validators for commands/schema/state assertions.
- Final audit failure cannot be turned into success by the synthesizer.

---

### 6.10 Controller and Public Paradigm

**File(s):** vidbyte/paradigms/long_running/controller.py, vidbyte/paradigms/long_running/paradigm.py
**Type:** New files

#### What it does

Implements the deterministic outer state machine and exposes it through the ParadigmHarness contract.

#### Interface / API

~~~python
class LongRunningController:
    async def start(self, prompt: str, options: LongRunningRunOptions) -> LongRunningResult: ...
    async def resume(self, run_id: str, options: LongRunningResumeOptions) -> LongRunningResult: ...
    async def run(self, state: LongRunningState) -> LongRunningResult: ...

class LongRunningParadigm(ParadigmHarness):
    def __init__(self, settings: LongRunningSettings | None = None, *, procedure_library: ProcedureLibrary | None = None, ledger_store: RunLedgerStore | None = None, validators: Sequence[TaskValidator] = (), procedure_validators: Sequence[ProcedureValidator] = (), attempt_isolator: AttemptIsolator | None = None, **kwargs: Any) -> None: ...
    async def arun(self, prompt: str, *, run_options: LongRunningRunOptions | None = None, **options: Any) -> LongRunningResult: ...
    async def aresume(self, run_id: str, *, resume_options: LongRunningResumeOptions | None = None, **options: Any) -> LongRunningResult: ...
    def resume(self, run_id: str, *, resume_options: LongRunningResumeOptions | None = None, **options: Any) -> LongRunningResult: ...
~~~

#### Logic / Algorithm

1. start creates immutable state/ledger, calls planner, validates, and commits graph.
2. start/resume reconciles any incomplete cross-store procedure intents before model work.
3. run checks deadline/cycle/observed-token/replan/no-progress budgets before each stage and wraps every awaited role/validator/isolator operation in asyncio.timeout(remaining_deadline or local_timeout). Timeout normalization checkpoints before any retry or return.
4. Select one ready task.
5. Execute or repair in a fresh context.
6. Verify independently and commit only on pass.
7. On pass: mark VERIFIED, commit, run drift audit, and route. Only an aligned review that leaves the source task valid may record success outcomes and curate/fidelity-check/promote procedures through ledgered idempotent sagas.
8. On fail: rollback isolation lease, record rejection, retry when allowed/new strategy exists, otherwise audit/replan/fail.
9. Replan through planner/reconciler and commit invalidations/revision.
10. When work is complete or auditor suggests synthesis, synthesize and final-audit under bounded attempts.
11. Return COMPLETED only after final pass; all other terminal limits return their explicit stop reason.
12. Unexpected error/cancellation checkpoints before propagation.

#### Edge Cases & Error Handling

- Empty prompts fail configuration.
- Resume on unknown/terminal/corrupt run raises LongRunningResumeError.
- No ready task plus all required tasks VERIFIED proceeds to synthesis; no ready task with pending work triggers replan/blocked result.
- When an observed-token limit requires complete reporting, missing provider usage stops the run with USAGE_UNAVAILABLE. In best-effort mode it remains visibly incomplete; max_observed_tokens is never described as total actual usage.
- asyncio timeout cancellation is a controller deadline, not an operating-system kill. A cancellation-resistant external tool may continue; non-READ ambiguity follows the same RECOVERY_REQUIRED rule as an interrupted attempt.
- The controller does not infer authorization for write/execute tools.
- Unknown **options keys are rejected with LongRunningConfigurationError; all execution-critical start/resume inputs use the typed option objects.
- Effective non-READ worker/repair tools without an isolator fail construction unless unsafe_allow_unisolated_side_effects is explicit; that opt-in still cannot bypass RECOVERY_REQUIRED after an unrolled-back rejection/interruption.

---

### 6.11 Client, Exports, and Package Documentation

**File(s):** vidbyte/paradigms/long_running/client.py, vidbyte/paradigms/long_running/__init__.py, vidbyte/paradigms/long_running/README.md, vidbyte/paradigms/client.py, vidbyte/paradigms/__init__.py, vidbyte/paradigms/README.md, vidbyte/paradigms/context_minimal_fanout/README.md, vidbyte/procedures/__init__.py, vidbyte/procedures/README.md, vidbyte/__init__.py
**Type:** New family/procedure files plus modified exports/docs

#### What it does

Adds the public construction/discovery surface, procedure exports, accurate package boundaries, and corrected paradigm documentation.

#### Interface / API

~~~python
class LongRunningClient:
    def __call__(self, **kwargs: Any) -> LongRunningParadigm: ...
    def create(self, **kwargs: Any) -> LongRunningParadigm: ...

sdk.paradigms.long_running(...)
sdk.paradigms.long_running.create(...)
~~~

Primary root exports:

~~~python
from vidbyte import (
    FileProcedureStore,
    InMemoryProcedureStore,
    LongRunningClient,
    LongRunningParadigm,
    LongRunningResult,
    LongRunningResumeOptions,
    LongRunningRunOptions,
    LongRunningSettings,
    ProcedureCandidate,
    ProcedureLibrary,
    ProcedureRef,
    ProcedureRecord,
    ProcedureStatus,
)
~~~

Run-ledger stores and advanced task contracts remain importable from vidbyte.paradigms.long_running to avoid overloading root exports.

#### Logic / Algorithm

1. Attach LongRunningClient in ParadigmClient.__init__.
2. Re-export primary family contracts from family, paradigms, and root packages.
3. Re-export procedure contracts/library/stores from vidbyte.procedures and selected primary names at root.
4. Correct existing READMEs that still describe concrete paradigms as absent.
5. Document verified as a configured-gate result, context isolation, persistence choices, side-effect limitations, and resume rehydration.

#### Edge Cases & Error Handling

- Client methods construct only real implementations.
- Imports remain additive.
- Specialized procedure and verified-context tools stay in their vidbyte.tools.builtins categories rather than root vidbyte.

---

### 6.12 Prompt Assets and Prompt Catalog

**File(s):** vidbyte/prompts/prompts/long_running/long_running.json, vidbyte/prompts/prompts/long_running/planner.md, vidbyte/prompts/prompts/long_running/worker.md, vidbyte/prompts/prompts/long_running/repair.md, vidbyte/prompts/prompts/long_running/verifier.md, vidbyte/prompts/prompts/long_running/procedure_curator.md, vidbyte/prompts/prompts/long_running/procedure_verifier.md, vidbyte/prompts/prompts/long_running/synthesizer.md, vidbyte/prompts/prompts/long_running/auditor.md, vidbyte/lib/enums/prompts.py, vidbyte/prompts/README.md
**Type:** New prompt family/assets plus modified enum/docs

#### What it does

Defines inspectable role instructions in the central prompt catalog.

#### Interface / API

~~~python
Prompt.LONG_RUNNING_PLANNER
Prompt.LONG_RUNNING_WORKER
Prompt.LONG_RUNNING_REPAIR
Prompt.LONG_RUNNING_VERIFIER
Prompt.LONG_RUNNING_PROCEDURE_CURATOR
Prompt.LONG_RUNNING_PROCEDURE_VERIFIER
Prompt.LONG_RUNNING_SYNTHESIZER
Prompt.LONG_RUNNING_AUDITOR
~~~

#### Logic / Algorithm

1. long_running.json registers every Markdown asset with key long_running.
2. Planner prompt requires small dependency-aware tasks and explicit acceptance criteria.
3. Worker prompt treats procedures as untrusted references and reports observable evidence.
4. Repair prompt requires a changed strategy based on the latest verifier feedback.
5. Verifier prompt requires criterion-by-criterion evidence and conservative failure.
6. Curator prompt stages only generic, reusable, prerequisite-aware procedures and may decline.
7. Procedure-verifier prompt checks the exact candidate against the source trace, task/drift evidence, prerequisites, limits, and unsupported generalization claims.
8. Synthesizer prompt uses verified, non-invalidated results only.
9. Auditor prompt treats the original request/invariants as immutable and emits bounded route codes.

#### Edge Cases & Error Handling

- Prompt enum/catalog sync fails at import if an asset/member is missing.
- Existing setuptools prompt globs already include nested JSON/Markdown, so pyproject.toml does not change.
- Prompt injection inside retrieved procedures is explicitly demoted to data.

---

### 6.13 Central Documentation and Skills

**File(s):** README.md, llms.txt, artifacts/file_index.md, skills/paradigm/SKILL.md, skills/sdk/SKILL.md, skills/usage/available_features.md, skills/usage/available_tools.md, skills/usage/create_agent_with_tools.md, skills/vidbyte-sdk-doc/SKILL.md, vidbyte/tools/README.md
**Type:** Modified files

#### What it does

Documents the new layer/tool category/API, updates quick navigation artifacts, and keeps contributor guidance synchronized.

#### Logic / Algorithm

1. Root README adds the procedures layer and long-running usage.
2. llms.txt adds machine-readable contracts/invariants.
3. file_index adds vidbyte/procedures, procedure tools, and long_running package.
4. paradigm skill describes both concrete paradigms and the verified-memory placement rule.
5. tool/usage skills list procedure search/load/stage plus verified_context_load names and permissions, emphasizing that stage cannot verify and dependency loading cannot escape its verified allowlist.
6. SDK skills/package map include the new package and maintenance paths.

#### Edge Cases & Error Handling

- All code examples must compile against the implemented signatures.
- Documentation must not repeat stale flat ContextMinimalFanout settings.
- Documentation must not promise rollback, objective verification, vector retrieval, or hidden reasoning.

---

## 7. Data Model Changes

### 7.1 Procedure Store Schema

**Change type:** New

~~~text
ProcedureRecord v1
  identity:
    schema_version
    namespace
    procedure_id
    version
    learning_operation_id
    status
  retrieval:
    title
    summary
    applicability[]
    preconditions[]
    tags[]
    required_tools[]
    environment_fingerprint
  source of truth:
    body
    expected_outcomes[]
    content_fingerprint
  provenance:
    source_run_id
    source_task_id
    source_attempt_id
    source_evidence_event_ids[]
    task verification event
    aligned drift-review event
    exact candidate fingerprint
    procedure-fidelity verification
    created_at
    supersedes_version
    reason

ProcedureOutcome v1
  outcome_id
  exact ProcedureRef (namespace/id/version/content fingerprint)
  run_id/task_id/attempt_id
  succeeded
  suspected_failure
  reason
  created_at
~~~

**Migration strategy:**

- Forward migration: new stores begin at schema version 1; no existing SDK data is converted.
- Rollback plan: remove feature usage. Caller-created procedure directories remain inert inspectable JSON and may be deleted by the caller.
- Schema mismatch: fail closed with ProcedureVersionError; no silent coercion.
- Versioning: every status/content change creates a new immutable record version. Candidate/rejected audit heads do not displace the derived active VERIFIED version; promotion replaces it, and retirement explicitly tombstones an exact active version.

### 7.2 Run Ledger Schema

**Change type:** New

~~~text
RunLedgerSnapshot v1
  run_id
  schema_version
  settings_fingerprint
  revision
  last_event_seq
  created_at / updated_at
  status / stop_reason
  exact GoalContract
  current TaskGraph
  separate LongRunningTaskState records
  verified TaskResults
  VerifiedContextRef handles for dependency results/artifacts
  compact attempt/verification indexes
  procedure handles/outcomes
  usage and budget counters
  trace/session references
  persistence warnings

LongRunningEvent v1
  event_id
  run_id
  seq
  kind
  created_at
  task_id / attempt_id / role
  JSON-safe payload

File transition envelope v1
  public LongRunningEvent
  compact post-transition RunLedgerSnapshot
  matching revision / sequence / hashes
~~~

**Migration strategy:**

- Forward migration: InMemoryRunLedgerStore is zero-config; FileRunLedgerStore creates a new explicit root.
- Rollback plan: revert code and stop using the store. Existing JSON remains readable as an audit artifact.
- Resume requires matching schema and settings fingerprint unless explicit mismatch override is recorded. If state.json lags after a crash, the newest valid immutable transition envelope restores the head; disagreement that cannot be explained by a lag fails closed.

### 7.3 In-Process Task and Verification Types

**Change type:** New

No database schema is introduced. GoalContract, LongRunningTask, LongRunningTaskState, TaskGraph, ArtifactRef, VerifiedContextRef, TaskAttempt, TaskResult, EvidenceRecord, CriterionResult, ValidatorResult, VerificationResult, DriftReview, TaskValidationContext, ProcedureValidationContext, LongRunningState, and LongRunningResult are frozen/slotted Python contracts serialized by the run-ledger codec where persisted. Definitions and runtime task state remain separate; full verified dependency detail remains referenced and loadable without entering every prompt.

---

## 8. API Changes

### 8.1 New Python Paradigm API

**Change type:** New

~~~python
from vidbyte import LongRunningParadigm, LongRunningRunOptions, LongRunningSettings
from vidbyte.paradigms.long_running import FileRunLedgerStore
from vidbyte.procedures import FileProcedureStore, ProcedureLibrary

procedure_library = ProcedureLibrary(FileProcedureStore("./.vidbyte/procedures"))
ledger_store = FileRunLedgerStore("./.vidbyte/long-running")

harness = LongRunningParadigm(
    settings=LongRunningSettings(
        procedure_namespace="vidbyte-sdk",
        max_attempts_per_task=3,
        max_replans=4,
    ),
    procedure_library=procedure_library,
    ledger_store=ledger_store,
)

result = await harness.arun(
    "Analyze the requested multi-step change and produce a verified implementation plan.",
    run_options=LongRunningRunOptions(
        success_criteria=("The plan covers every requested behavior and is independently verified.",),
        invariants=("Do not modify files outside the authorized workspace.",),
    ),
)
~~~

For mutating work, callers set worker_include_execution/worker_include_write and provide an AttemptIsolator. The SDK rejects that configuration without an isolator unless the explicit unsafe flag is set, and even unsafe mode blocks on any rejected/interrupted non-READ side effect.

Resume is for a previously PAUSED/RECOVERY_REQUIRED persisted run, not the terminal result returned above:

~~~python
from vidbyte import LongRunningResumeOptions

resumed = await harness.aresume(
    "lr_<persisted-paused-run-id>",
    resume_options=LongRunningResumeOptions(),
)
~~~

Namespace equivalent:

~~~python
harness = sdk.paradigms.long_running(
    settings=settings,
    procedure_library=procedure_library,
    ledger_store=ledger_store,
)
~~~

### 8.2 New Procedure API

**Change type:** New

~~~python
from vidbyte.procedures import FileProcedureStore, ProcedureLibrary

library = ProcedureLibrary(FileProcedureStore("./.vidbyte/procedures"))
matches = library.search(
    "resolve an async tool timeout without losing raw evidence",
    namespace="vidbyte-sdk",
    available_tools=("grep", "read_text", "patch_file"),
    limit=5,
)
record = library.load(
    matches[0].summary.ref.procedure_id,
    version=matches[0].summary.ref.version,
    namespace=matches[0].summary.ref.namespace,
    available_tools=("grep", "read_text", "patch_file"),
)
~~~

### 8.3 HTTP / MCP APIs

N/A - no HTTP endpoint, MCP tool, request body, response body, or network status code is added. The API is local Python. A future hosted or MCP adapter must wrap the same verified-procedure and run-result semantics.

### 8.4 Existing APIs

**Change type:** Additive modification

- sdk.paradigms gains long_running.
- Root vidbyte and vidbyte.paradigms gain additive imports.
- Prompt enum/catalog gains eight members.
- vidbyte.tools.builtins gains a procedure category.
- Existing signatures and behaviors do not change.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | docs/design/long-running-paradigm.md | Approved source of truth for the feature |
| CREATE | vidbyte/procedures/__init__.py | Public procedure-layer exports |
| CREATE | vidbyte/procedures/README.md | Procedure lifecycle, storage, verification, and limits |
| CREATE | vidbyte/procedures/contracts.py | Procedure records, summaries, evidence, outcomes, and protocols |
| CREATE | vidbyte/procedures/errors.py | Typed procedure error hierarchy |
| CREATE | vidbyte/procedures/library.py | Stage/promote/reject/search/load/outcome/retire service |
| CREATE | vidbyte/procedures/serialization.py | Versioned JSON-safe procedure codec |
| CREATE | vidbyte/procedures/store.py | ProcedureStore protocol and shared store behavior |
| CREATE | vidbyte/procedures/stores/__init__.py | Store exports |
| CREATE | vidbyte/procedures/stores/memory.py | In-memory procedure store |
| CREATE | vidbyte/procedures/stores/file.py | Atomic JSON file procedure store |
| CREATE | vidbyte/tools/builtins/procedures/__init__.py | Procedure tool exports |
| CREATE | vidbyte/tools/builtins/procedures/search.py | Compact verified procedure search tool |
| CREATE | vidbyte/tools/builtins/procedures/load.py | Explicit verified procedure expansion tool |
| CREATE | vidbyte/tools/builtins/procedures/stage.py | Candidate-only procedure staging tool |
| CREATE | vidbyte/tools/builtins/verified_context/__init__.py | Verified within-run context tool export |
| CREATE | vidbyte/tools/builtins/verified_context/contracts.py | Generic verified-context handle/source protocols |
| CREATE | vidbyte/tools/builtins/verified_context/load.py | Dependency result/artifact expansion tool |
| CREATE | vidbyte/paradigms/types.py | Shared AgentRoleSettings extracted from the concrete fanout family |
| CREATE | vidbyte/paradigms/long_running/__init__.py | Long-running family public exports |
| CREATE | vidbyte/paradigms/long_running/README.md | Usage, lifecycle, guarantees, and limitations |
| CREATE | vidbyte/paradigms/long_running/client.py | Namespace factory |
| CREATE | vidbyte/paradigms/long_running/errors.py | Typed paradigm/controller errors |
| CREATE | vidbyte/paradigms/long_running/types.py | Goal/task/attempt/verification/settings/result contracts |
| CREATE | vidbyte/paradigms/long_running/ledger.py | Append-only ledger, serialization, stores, and resume |
| CREATE | vidbyte/paradigms/long_running/context.py | Fresh context capsules, tools, agents, and compaction |
| CREATE | vidbyte/paradigms/long_running/planning.py | Planner, validator, reconciler, and scheduler |
| CREATE | vidbyte/paradigms/long_running/execution.py | Worker/repair attempts, isolation, and no-progress logic |
| CREATE | vidbyte/paradigms/long_running/verification.py | Verification, drift audit, learning, and finalization services |
| CREATE | vidbyte/paradigms/long_running/controller.py | Deterministic outer state machine |
| CREATE | vidbyte/paradigms/long_running/paradigm.py | Public ParadigmHarness implementation |
| CREATE | vidbyte/prompts/prompts/long_running/long_running.json | Prompt family manifest |
| CREATE | vidbyte/prompts/prompts/long_running/planner.md | Task graph planner prompt |
| CREATE | vidbyte/prompts/prompts/long_running/worker.md | Fresh worker prompt |
| CREATE | vidbyte/prompts/prompts/long_running/repair.md | Evidence-driven changed-strategy repair prompt |
| CREATE | vidbyte/prompts/prompts/long_running/verifier.md | Independent verification prompt |
| CREATE | vidbyte/prompts/prompts/long_running/procedure_curator.md | Verified-source procedure distillation prompt |
| CREATE | vidbyte/prompts/prompts/long_running/procedure_verifier.md | Candidate fidelity and evidence-checking prompt |
| CREATE | vidbyte/prompts/prompts/long_running/synthesizer.md | Verified-results-only synthesis prompt |
| CREATE | vidbyte/prompts/prompts/long_running/auditor.md | Global goal drift/final audit prompt |
| MODIFY | artifacts/file_index.md | Add procedures, tools, and long-running package map |
| MODIFY | README.md | Add layer/API/usage/limits documentation |
| MODIFY | llms.txt | Add machine-readable long-running/procedure contracts |
| MODIFY | skills/paradigm/SKILL.md | Correct stale scaffold claims and document long_running |
| MODIFY | skills/sdk/SKILL.md | Add new package/tool category to framework boundaries |
| MODIFY | skills/usage/available_features.md | Add long-running paradigm and verified procedures |
| MODIFY | skills/usage/available_tools.md | Add procedure and verified-context tool catalog |
| MODIFY | skills/usage/create_agent_with_tools.md | Add governed procedure/dependency-tool example |
| MODIFY | skills/vidbyte-sdk-doc/SKILL.md | Update package map and public exports |
| MODIFY | vidbyte/__init__.py | Root convenience exports |
| MODIFY | vidbyte/lib/enums/prompts.py | Add eight long-running prompt keys |
| MODIFY | vidbyte/middleware/compaction/context_compaction.py | Add backward-compatible aggregate character bound option |
| MODIFY | vidbyte/middleware/compaction/engine.py | Route the provider-boundary character bound |
| MODIFY | vidbyte/middleware/compaction/strategies.py | Enforce group-safe message/token/character trimming |
| MODIFY | vidbyte/paradigms/__init__.py | Export long-running public contracts |
| MODIFY | vidbyte/paradigms/client.py | Attach LongRunningClient |
| MODIFY | vidbyte/paradigms/README.md | Document both concrete paradigms |
| MODIFY | vidbyte/paradigms/context_minimal_fanout/types.py | Re-export shared AgentRoleSettings without breaking imports |
| MODIFY | vidbyte/paradigms/context_minimal_fanout/README.md | Correct obsolete skills-only description |
| MODIFY | vidbyte/prompts/README.md | Add long_running prompt family |
| MODIFY | vidbyte/tools/builtins/__init__.py | Re-export procedure tools |
| MODIFY | vidbyte/tools/README.md | Document procedure/verified-context categories and promotion/allowlist boundaries |

Summary: **40 files created**, **22 files modified**, **0 files deleted**.

No tests or verification scripts are created or modified.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python >=3.11 | asyncio, dataclasses, enums, hashing, JSON, pathlib, atomic file writes, locks, UUIDs, time | Low; already required |
| Existing Pydantic dependency | >=2,<3 | Existing prompt/trace/output schema contracts and optional validator adapters | Low; already required |
| Vidbyte BaseAgent | In-repo origin/main API | Fresh role actors and provider-neutral model/tool loops | Medium; model behavior is nondeterministic |
| OutputSchemaBuilder tools | In-repo | Typed structured role outputs after exploratory transcripts are discarded | Medium; malformed/omitted model tool calls must fail closed/retry |
| ContextManager and context primitives | In-repo | Small frozen role capsules and explicit procedure expansion | Low |
| ParadigmMinimalToolset | In-repo | Standard permission-governed workspace tools | Medium; write/execute side effects are caller-authorized |
| Existing middleware | In-repo | Per-role budgets, runtime limits, loop detection, and model-visible compaction | Low to medium |
| Optional SessionStore/Trace | In-repo | Additional agent-level audit/observability links | Low; non-authoritative |
| External model provider | Caller configured | Planning, work, verification, curation, synthesis, audit | High; outages/cost/nondeterminism are bounded but not eliminated |
| Voyager paper/source | arXiv/GitHub references only | Design provenance | None at runtime |

No new third-party package, vector database, hosted memory provider, database, queue, credential, environment variable, or network endpoint is required.

---

## 11. Rollout & Deployment

- This is an additive alpha SDK feature.
- Because this design intentionally adds no tests, the PR must not label the persistence/procedure contracts stable. A follow-up tests-enabled design/PR covering crash injection, locking, idempotency, chain-head/retirement rules, and recovery is recommended immediately after merge and required before promotion from alpha.
- No feature flag is required; no behavior changes until callers construct the new paradigm or procedure classes.
- InMemoryProcedureStore and InMemoryRunLedgerStore are defaults, so construction causes no hidden filesystem writes.
- Durable writes occur only when callers explicitly provide FileProcedureStore or FileRunLedgerStore roots.
- No existing data migration is required.
- Store schemas begin at version 1 and reject unsupported versions.
- Implementation starts only after explicit approval, from the latest main in an isolated feat/long-running-paradigm worktree. The dirty stale checkout is not cleaned or used for implementation.
- The design document is committed first in the feature worktree.
- Recommended implementation sequence:
  1. Commit this approved design doc.
  2. Implement procedure contracts, serialization, stores, and library.
  3. Implement procedure tools and exports.
  4. Add long-running contracts, ledger, and resume.
  5. Add prompt assets/catalog entries.
  6. Implement context broker, planning, execution, verification, and controller.
  7. Add public paradigm/client/exports.
  8. Update all docs/skills/index artifacts.
  9. Run structured self-critique/refinement.
  10. Push and open a draft PR into main.
- No test files/scripts are added, but implementation verification must run:

~~~powershell
python -m compileall vidbyte
python -m unittest discover -s tests -v
python -c "from vidbyte import LongRunningParadigm, ProcedureLibrary, VidbyteSDK; print(LongRunningParadigm.__name__, ProcedureLibrary.__name__, type(VidbyteSDK().paradigms.long_running).__name__)"
python -c "from vidbyte import Prompt, Prompts; print(Prompts().get(Prompt.LONG_RUNNING_PLANNER)[:40])"
python -m build
python -m twine check dist/*
~~~

- An inline temporary-directory smoke exercise must cover candidate invisibility, curator-candidate fidelity rejection, post-drift promotion ordering, verified promotion/search/load, namespace/version identity, immutable versioning, idempotent cross-store intent reconciliation after injected crash points, retirement, invalid DAG rejection, failed-verification non-commit, accepted dependency unlock, no-progress replan, file-ledger head recovery/resume, settings mismatch rejection, and final-audit gating. It must not be committed as a script.
- Rollback is a normal code revert. Existing caller-created procedure/ledger directories are left intact for audit; callers decide retention/deletion.
- A future migration to generic workflow/harness execution primitives requires a separate approved design and backward-compatible adapters.

---

## 12. Open Questions

- [ ] Should the reusable verified-memory primitive be public as vidbyte.procedures in v1, or private under the long-running family until a second consumer appears? **Recommendation: public**, because procedure stores, versioning, search/load/stage tools, and evidence contracts are lower-level capabilities and the paradigm skill explicitly requires reusable mechanics to live outside the harness.
- [ ] Is sequential dependency-ready task execution the correct v1 tradeoff? **Recommendation: yes**. It directly limits error compounding and side-effect races; ContextMinimalFanoutParadigm remains available for parallel independent work.
- [ ] Is the operational definition of task VERIFIED acceptable: model verifier pass plus all configured required TaskValidator objects, with documentation that this is not objective truth? Procedure promotion adds two more conditions—an aligned post-commit drift review and a pass over the exact curated candidate by its fresh procedure verifier plus required ProcedureValidator objects. **Recommendation: yes**, while strongly recommending deterministic validators for code/state claims.
- [ ] Should FileRunLedgerStore resumability remain in the initial feature or be deferred? **Recommendation: keep it**. The paradigm is explicitly long-running, and a raw append-only resume point is materially different from procedure persistence alone.
- [ ] If the unmerged harness-execution-contract or validated-state-machine-workflows features land before implementation, should this PR integrate them immediately? **Recommendation: no automatic dependency**. Revise this doc and obtain fresh approval before changing the architecture.

Approval of this document confirms the recommended answers unless the approval message calls out a different choice.

---

## 13. Alternatives Considered

### Alternative 1: Exact Voyager Clone

- What: Reproduce automatic curriculum, JavaScript skill programs, Chroma retrieval, and a four-attempt critic loop.
- Why rejected: The SDK is provider/domain neutral, and the user explicitly needs arbitrary expandable context, subproblem solving, pollution control, and drift reduction. Voyager supplies the verified-procedure inspiration but not the required general contracts.

### Alternative 2: Extend ContextMinimalFanoutParadigm

- What: Add memory, verification, retries, resume, and drift auditing to the current four-stage parallel paradigm.
- Why rejected: Context-minimal fanout optimizes independent parallel ownership. Long-running execution needs dependency ordering, per-node commitment, revision/invalidation, procedure outcomes, and final verification. Combining them would blur two valuable strategies and complicate the existing API.

### Alternative 3: Reuse Pipelines

- What: Compose planner, worker, verifier, and curator through sequential/conditional pipelines.
- Why rejected: Pipelines carry strings and do not own typed shared state, loops, dependency readiness, retries, commitment, invalidation, persistence, or memory promotion.

### Alternative 4: Store Procedures in SessionStore

- What: Encode procedures or outer state as Session checkpoints.
- Why rejected: SessionStore persists one agent's resumable history DAG. Procedure records require namespace search, immutable versions, compatibility filters, evidence, outcomes, and retirement. Outer task state also has different identity and transition semantics.

### Alternative 5: Use Third-Party Memory Tools

- What: Require Mem0, Zep, Supermemory, Letta, or Cognee for procedure storage/search.
- Why rejected: They add service/credential requirements and do not guarantee the candidate/verified/rejected/retired lifecycle, provenance, immutable versions, or harness-only promotion gate.

### Alternative 6: Keep Procedure Mechanics Private to the Paradigm

- What: Put store, records, and tools entirely under vidbyte/paradigms/long_running.
- Why rejected: Search/load/stage and verified/versioned records are reusable primitives. The repo's paradigm placement rules say reusable mechanics belong in lower layers. The public surface is deliberately narrow and domain-neutral.

### Alternative 7: Vector Retrieval in V1

- What: Add an embedding client/vector store and retrieve semantically as Voyager does.
- Why rejected: It adds dependencies, credentials, cost, network failure, and index synchronization before the lifecycle invariants are proven. An injectable ranker preserves the extension seam.

### Alternative 8: One Persistent Agent with Compaction

- What: Keep one agent running, periodically summarize/compact its history, and let it manage its own plan/memory.
- Why rejected: Compaction alone does not prevent role confusion, unverified memory promotion, local-goal drift, dependency contamination, or false completion. Fresh role contexts and an external deterministic controller are the core safeguards.

### Alternative 9: Trust Worker Self-Assessment

- What: Let a worker mark its task complete and save a procedure.
- Why rejected: This is the main procedure-poisoning and error-compounding path. Promotion must be controlled by an independent gate.

### Alternative 10: Parallel DAG Execution

- What: Run all dependency-ready tasks concurrently.
- Why rejected for v1: Parallel mutation requires conflict detection, transaction/merge semantics, cancellation propagation, and downstream invalidation across in-flight work. Sequential readiness is safer and still satisfies decomposition.

### Alternative 11: Continual Trace as Canonical State

- What: Use ContinualTraceAgent artifacts as the plan/progress ledger and feed them back through trace replacement.
- Why rejected: Continual trace is model-generated and fail-open. It is excellent observational context but cannot decide commitment, verification, versioning, or resume correctness.

### Alternative 12: Depend on Unmerged Generic Harness/Workflow Designs

- What: Build directly on the local harness-execution-contract or validated-state-machine-workflows drafts.
- Why rejected: They are not in origin/main and are not callable stable APIs. This design may later adapt to merged primitives only through an approved revision.

### Alternative 13: Guarantee Side-Effect Rollback

- What: Automatically undo every failed attempt.
- Why rejected: Arbitrary tools may mutate external systems that do not expose transactions or compensation. The design provides an AttemptIsolator seam, defaults writes off, gates logical state, and documents the limit instead of making a false guarantee.

---

END OF DESIGN DOC
