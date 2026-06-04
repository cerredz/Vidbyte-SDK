# Handoffs

## What a handoff is

A handoff is a structured document describing what an agent did, so another agent
(or a human) can continue the work cold. In the Vidbyte SDK a handoff is one object,
`Handoff`, that plays three roles at once:

- **Context primitive** â€” it implements the `ContextItem` protocol, so a finished
  handoff drops straight into another agent via `context_items=[...]`.
- **Spec** â€” its ordered `sections` mapping (title â†’ description) tells a `HandoffAgent`
  what structure to produce.
- **Output** â€” once produced, the same object holds the filled content (`fill()` returns
  the same subclass with `metadata["filled"] = True`).

There is intentionally **no** `vidbyte/handoff/` subsystem. The primitive lives in
`vidbyte/context/handoffs.py` and the agent in `vidbyte/agents/handoff.py`, built from
existing SDK primitives.

## Prebuilt handoffs (objects, not functions)

Prebuilt variants are subclasses that preset a curated section map. Construct them as objects:

```python
from vidbyte import EngineeringHandoff, ResearchHandoff, MinimalHandoff

spec = EngineeringHandoff()      # Objective, Changes Made, Verification Status, Open Threads, Risks & Gotchas, Next Steps
spec = ResearchHandoff()         # Question, Findings, Sources, Confidence & Gaps, Recommended Next Queries
spec = MinimalHandoff()          # Summary, Next Steps  (the default when none is given)
```

### Process-shape catalog

Beyond the three above, the SDK ships prebuilts keyed to the *shape of the agent's
problem-solving process* â€” each models a distinct reasoning/execution topology, not a
domain. Pick the one whose structural element matches how the work actually unfolded:

| Variant | Shape | Section skeleton |
|---------|-------|------------------|
| `TreeSearchHandoff` | search frontier | Search Goal Â· Frontier Â· Explored Branches Â· Pruned / Dead Branches Â· Best So Far Â· Next Expansion |
| `DecompositionHandoff` | subproblem tree | Top-Level Problem Â· Decomposition Â· Solved Subproblems Â· Open Subproblems Â· Composition Status Â· Next Steps |
| `RefinementLoopHandoff` | iteration journal | Objective Â· Current Draft State Â· Iteration Log Â· Open Critiques Â· Convergence Status Â· Next Revision |
| `ConstraintSatisfactionHandoff` | constraint ledger | Objective Â· Constraints Â· Current Candidate Â· Conflicts & Tensions Â· Trade-offs Made Â· Next Steps |
| `BacktrackingHandoff` | decision stack | Objective Â· Decision Stack Â· Tentative Choices Â· Backtrack Points Â· Abandoned Paths Â· Next Steps |
| `TradeoffHandoff` | Pareto frontier | Decision to Make Â· Objectives & Priorities Â· Options Evaluated Â· Frontier Â· Leaning / Chosen Â· Open Questions |
| `GoalStackHandoff` | goal hierarchy | Root Goal Â· Goal Hierarchy Â· Active Path Â· Satisfied Goals Â· Suspended Goals Â· Next Steps |
| `CoverageHandoff` | coverage map | Objective & Scope Â· Coverage Map Â· Completed Â· Gaps & Skipped Â· Systematic Next |
| `BudgetBoundedHandoff` | budget curve | Objective Â· Budget Status Â· Value Delivered Â· Remaining Work Â· Cut Line Â· Next Steps |
| `MigrationHandoff` | state delta | Target State Â· Current State Â· Completed Migrations Â· Remaining Delta Â· Reversibility Â· Next Steps |

```python
from vidbyte import TreeSearchHandoff, RefinementLoopHandoff, BudgetBoundedHandoff

spec = TreeSearchHandoff()        # for branch-and-prune exploration agents
```

### Software-engineering catalog

Prebuilts tuned to common software-engineering task types:

| Variant | SWE task | Section skeleton |
|---------|----------|------------------|
| `CodeReviewHandoff` | reviewing a PR/diff | Scope Reviewed Â· Blocking Issues Â· Non-Blocking Suggestions Â· Approved Aspects Â· Unresolved Threads Â· Verdict |
| `BugFixHandoff` | fixing a defect | Symptom Â· Reproduction Â· Root Cause Â· Fix Applied Â· Tests Added Â· Regression Risk |
| `RefactorHandoff` | restructure, no behavior change | Motivation Â· Scope & Boundaries Â· Behavior-Preservation Evidence Â· Changes by Module Â· Risk Areas Â· Follow-up Cleanups |
| `PerformanceOptimizationHandoff` | profiling/optimization | Baseline Metrics Â· Bottlenecks Identified Â· Optimizations Applied Â· Measured Improvement Â· Trade-offs Â· Remaining Hotspots |
| `TestAuthoringHandoff` | writing tests / coverage | Coverage Goal Â· Areas Covered Â· Test Cases Added Â· Gaps & Untested Paths Â· Flaky/Skipped Tests Â· Next Tests |
| `APIDesignHandoff` | designing an endpoint/contract | Purpose & Consumers Â· Endpoints/Contracts Â· Request/Response Schemas Â· Versioning & Compatibility Â· Error Model Â· Open Design Questions |
| `SchemaMigrationHandoff` | DB schema change | Schema Change Â· Migration Steps Â· Backfill Plan Â· Forward/Backward Compatibility Â· Data-Integrity Checks Â· Rollback Plan |
| `DependencyUpgradeHandoff` | lib/framework bump | Target Versions Â· Breaking Changes Â· Code Adjustments Made Â· Compatibility Verification Â· Remaining Deprecations Â· Rollback |
| `IncidentResponseHandoff` | on-call / outage | Impact & Severity Â· Timeline Â· Current Mitigation Â· Root-Cause Status Â· Action Items Â· Comms Status |
| `ArchitectureDecisionHandoff` | system design / ADR | Problem & Context Â· Options Considered Â· Decision & Rationale Â· Consequences & Trade-offs Â· Open Risks Â· Next Steps |
| `CodebaseOnboardingHandoff` | understanding unfamiliar code | Goal Â· System Map Â· Key Components & Responsibilities Â· Entry Points & Data Flow Â· Conventions & Gotchas Â· Open Questions |
| `CICDPipelineHandoff` | build/deploy pipeline work | Pipeline Goal Â· Stages & Status Â· Build/Deploy Config Â· Secrets & Environments Â· Failing/Flaky Stages Â· Next Steps |
| `IntegrationHandoff` | third-party integration | Integration Goal Â· External Contract Â· Auth & Credentials Â· Implemented Surface Â· Edge Cases & Failure Modes Â· Untested Paths |
| `SecurityRemediationHandoff` | fixing vulnerabilities | Vulnerabilities Â· Severity & Exploitability Â· Fixes Applied Â· Verification Â· Residual Risk Â· Remaining Items |
| `ReleaseHandoff` | cutting a release/deploy | Release Scope Â· Changelog Â· Pre-Deploy Checklist Â· Deploy Steps Â· Verification & Smoke Â· Rollback Plan |

### Domain catalog

Prebuilts tuned to high-fit professional fields:

| Variant | Field | Section skeleton |
|---------|-------|------------------|
| `PatientHandoff` | healthcare (SBAR) | Situation; Background; Assessment; Recommendation; Pending Tasks; Watch-fors; Medications & Treatments; Care Team & Family Context; Escalation Criteria |
| `CareTransitionHandoff` | healthcare | Diagnosis & Status; Medications; Procedures Done/Pending; Follow-up Plan; Red Flags; Receiving Team Responsibilities; Patient Constraints; Documentation Gaps |
| `DiagnosticWorkupHandoff` | healthcare | Presentation; Differential; Tests Ordered/Resulted; Leading Diagnosis; Next Steps; Ruled-Out Concerns; Urgency & Safety Plan; Consults & Ownership |
| `ContractReviewHandoff` | legal | Parties & Purpose; Key Terms; Risk Flags; Redlines Proposed; Open Negotiation Points; Recommendation; Business Context; Fallback Positions; Approval Path |
| `LegalResearchHandoff` | legal | Issue; Authorities Found; Holdings & Application; Counterarguments; Confidence & Gaps; Research Trail; Fact Dependencies; Draft Answer |
| `DueDiligenceHandoff` | legal | Scope; Findings by Category; Material Risks; Documents Reviewed; Outstanding Requests; Decision Impact; Assumptions & Limits; Next Review Pass |
| `TicketEscalationHandoff` | support | Customer Goal; Actions Tried; Current State; Reproduction; Why Escalated; Suggested Next Step; Environment Details; Artifacts & Evidence; Customer Communication |
| `AccountHealthHandoff` | customer success | Account Status; Usage & Risk Signals; Open Issues; Relationship Notes; Renewal/Expansion Posture; Success Plan; Executive Narrative; Next Touchpoints |
| `AlertTriageHandoff` | SOC | Alerts in Queue; Triaged & Dispositioned; Under Investigation; Suspected Scope; Next Actions; Evidence Collected; Containment Status; Escalation Path |
| `ThreatHuntHandoff` | SOC | Hypothesis; Data Sources Queried; Findings; Ruled Out; Open Leads; Coverage Map; Detection Opportunities; Response Readiness |
| `InvestmentThesisHandoff` | finance | Thesis; Supporting Evidence; Key Risks; Valuation View; Catalysts; Open Diligence; Positioning & Sizing; Variant Views; Monitoring Plan |
| `DealHandoff` | finance (M&A) | Deal Status; Workstreams; Open Items by Workstream; Key Risks; Next Milestones; Negotiation State; Stakeholder Map; Integration or Closing Readiness |
| `CreditAnalysisHandoff` | finance | Borrower & Facility; Financial Assessment; Risk Factors; Rating/Recommendation; Open Questions; Covenants & Protections; Scenario Analysis; Approval Conditions |

### Agent-native catalog

Prebuilts tuned to the artifacts and transition moments of agentic execution - these map
onto SDK runtime concepts (the context window, the `ToolCallContext` trace, sub-agents,
memory, permissions):

| Variant | Agent moment | Section skeleton |
|---------|--------------|------------------|
| `ContextWindowHandoff` | running out of context | Task State; Key Facts to Preserve; Decisions Made; Compacted/Dropped Context; Active Working Set; Resume Instructions; Token Budget Strategy; Validation Needed; Lost Nuance |
| `ToolTrajectoryHandoff` | tool-heavy execution | Available Tools; Calls Made & Results; Failed Calls & Errors; Current Tool State; Next Tool Action; Artifacts Produced; Permission Boundaries; Ordering Dependencies |
| `SubAgentDelegationHandoff` | delegating to sub-agents | Top Goal; Subagents Spawned; Results Received; Pending Delegations; Synthesis State; Next Delegation; Conflict Resolution; Quality Gates; Shared Context |
| `OrchestrationHandoff` | multi-agent orchestration | Plan; Agent Assignments; Completed/In-Flight/Blocked; Cross-Agent Conflicts; Next Dispatch; Shared State; Coordination Rules; Completion Criteria |
| `HumanEscalationHandoff` | agent -> human | What I Was Doing; Where I'm Stuck; What I Tried; Specific Decision Needed; Options & Recommendation; Risk of Proceeding; Needed Context From Human; Safe Holding Pattern |
| `CheckpointResumeHandoff` | long-horizon checkpoint | Goal; Progress So Far; Current Step; Environment State; Blockers; Resume Point; Verification Snapshot; Rollback or Recovery; Budget Remaining |
| `DeepResearchHandoff` | agentic research | Question; Search Queries Run; Sources Gathered; Synthesis So Far; Contradictions; Confidence & Next Queries; Source Quality Notes; Unanswered Subquestions; Citation Trail |
| `RetrievalHandoff` | RAG | Query; Chunks Retrieved; Relevance Assessment; Coverage Gaps; Re-query Plan; Corpus Assumptions; Answer Candidates; Deduplication Notes |
| `BrowserSessionHandoff` | browser automation | Current Location; Session & Auth State; Action Trail; Extracted Data; Blockers; Next Action; Viewport & Timing Notes; Download or Upload State; Safety Constraints |
| `ComputerUseHandoff` | desktop/computer use | Desktop State; Apps & Windows Open; Action Trail; Files Touched; Blockers; Next Step; Input State; System Constraints; Recovery Notes |
| `MemoryHandoff` | memory-backed agent | Working Memory; Long-Term Facts Learned; Updated/Stale Beliefs; Open Questions; What to Persist; What Not to Persist; Source Evidence; Memory Conflicts |
| `VerificationHandoff` | self-verification | Claims Made; Verified vs Unverified; Failed Checks; Confidence per Claim; What Still Needs Checking; Verification Methods; Corrections Applied; Residual Risk |
| `ReasoningTraceHandoff` | reasoning continuity | Goal; Reasoning So Far; Key Inferences; Assumptions Made; Dead Ends; Current Direction; Decision Points; Evidence Ledger; Output Implications |
| `GuardrailHandoff` | guardrail/policy stop | Requested Action; Policy Triggered; What Was Blocked; Safe Alternatives; Needs Human Approval; Risk Rationale; Allowed Progress; Escalation Record |
| `EvaluationHandoff` | grading/evaluation | Rubric; Items Graded; Scores & Rationale; Uncertain/Disputed; Remaining to Grade; Calibration Notes; Evidence Reviewed; Finalization Criteria |
### Discovering handoffs with the registry

`HandoffRegistry` is a prefilled catalog of every prebuilt handoff (general + process-shape
+ software-engineering + domain + agent-native). Use it to browse, construct by name, or
build an agent in one step:

```python
from vidbyte import HandoffRegistry

registry = HandoffRegistry()
registry.list()                       # every prebuilt slug, e.g. "code_review", "tree_search", "engineering"
registry.describe()                   # slug -> {class, title, sections} for the whole catalog
spec = registry.create("bug_fix")     # a BugFixHandoff instance
agent = registry.build_agent("code_review", provider="anthropic", model_name="claude-opus-4-8")

registry.register("my_handoff", MyHandoff)   # add a custom handoff to this registry instance
```

`get(name)` raises `ConfigurationError` for an unknown slug, listing the available names.

Bring your own structure by passing `sections` (or subclassing `Handoff`):

```python
from vidbyte import Handoff

spec = Handoff(sections={
    "Decision Log": "Key decisions and their rationale.",
    "Blockers": "What is currently blocking progress.",
}, title="Decision Handoff")
```

## The handoff agent

`HandoffAgent` is a thin configuration over `BaseAgent`. It builds its system prompt from
the comprehensive handoff prompt asset (`Prompt.HANDOFF_SYSTEM_PROMPT`, stored at
`vidbyte/prompts/prompts/handoff/handoff.json`) plus the spec's section brief, then parses
the model's `## Title` blocks back into a filled `Handoff`.

```python
from vidbyte import VidbyteSDK, EngineeringHandoff

sdk = VidbyteSDK()
ho = sdk.agents.handoff(EngineeringHandoff(), provider="anthropic", model_name="claude-opus-4-8")
doc = await ho.generate_handoff(run_digest_text)   # -> filled EngineeringHandoff
```

You rarely build it directly â€” `BaseAgent.handoff()` does it for you.

## Producing a handoff from an agent's own run

Any agent can hand off its most recent run. The agent renders a digest of its system
prompt, the task, the transcript, the tool-call log, and the final result, then a
`HandoffAgent` (reusing the same runner by default) fills the document:

```python
agent = sdk.agents.base(system_prompt="...", runner=runner)
await agent.arun("do the task")
doc = await agent.handoff(EngineeringHandoff())     # -> filled Handoff
next_agent = sdk.agents.base(system_prompt="...", runner=runner, context_items=[doc])
```

Pass `by=` to use a specific generator agent (e.g. a cheaper model, or one with
trace-querying tools):

```python
doc = await agent.handoff(EngineeringHandoff(), by=my_custom_handoff_agent)
```

## Automatic handoff after a run

Set `handoff=` on any agent. When set, the agent automatically produces the handoff after
`generate_reply()` completes and attaches it to the reply:

```python
agent = sdk.agents.base(system_prompt="...", runner=runner, handoff=EngineeringHandoff())
reply = await agent.arun("do the task")

doc = reply.metadata["handoff"]    # the produced Handoff
doc = agent.last_handoff           # also cached here
```

Auto-handoff is **non-fatal**: if generation fails, the primary reply is still returned,
`reply.metadata["handoff_error"]` is set, and `agent.last_handoff` stays `None`. The
return type of `generate_reply()` is unchanged (still `AgentMessage`), so pipelines are
unaffected.

## Customization summary

| Want to change | How |
|----------------|-----|
| Document structure | Pass a prebuilt (`EngineeringHandoff()`), `Handoff(sections=...)`, or subclass `Handoff` |
| Output title / intent | `Handoff(title=..., instructions=...)` |
| Generating model / tools | `sdk.agents.handoff(spec, provider=..., model_name=..., tools=[...])` or `handoff(by=...)` |
| When it runs | Call `agent.handoff(...)` manually, or set `agent = ...(handoff=spec)` for auto-run |

## Module layout

```
vidbyte/context/handoffs.py     Handoff base + EngineeringHandoff/ResearchHandoff/MinimalHandoff
vidbyte/agents/handoff.py       HandoffAgent (thin BaseAgent subclass)
vidbyte/agents/base.py          handoff= param, handoff() method, run digest, auto-run hook
vidbyte/prompts/prompts/handoff/handoff.json   comprehensive handoff system prompt
```

Public imports:

```python
from vidbyte import HandoffAgent, Handoff, EngineeringHandoff, ResearchHandoff, MinimalHandoff
# also from vidbyte.context import Handoff, EngineeringHandoff, ResearchHandoff, MinimalHandoff
# also from vidbyte.agents import HandoffAgent
```

## Rules for adding a new prebuilt handoff

- Subclass `Handoff`, set `DEFAULT_TITLE`, and override `default_sections()` with a
  `{title: description}` map. Do not add a new module or subsystem.
- Export it from `vidbyte/context/handoffs.py` `__all__`, `vidbyte/context/__init__.py`,
  and `vidbyte/__init__.py`.
- Keep sections decision-oriented: each section title should map to something the next
  agent must know to continue.
- Add a unit test asserting the new variant exposes a non-empty, distinct section map and
  that `fill()` preserves its type.
