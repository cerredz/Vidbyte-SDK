# Handoffs

## What a handoff is

A handoff is a structured document describing what an agent did, so another agent
(or a human) can continue the work cold. In the Vidbyte SDK a handoff is one object,
`Handoff`, that plays three roles at once:

- **Context primitive** — it implements the `ContextItem` protocol, so a finished
  handoff drops straight into another agent via `context_items=[...]`.
- **Spec** — its ordered `sections` mapping (title → description) tells a `HandoffAgent`
  what structure to produce.
- **Output** — once produced, the same object holds the filled content (`fill()` returns
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
problem-solving process* — each models a distinct reasoning/execution topology, not a
domain. Pick the one whose structural element matches how the work actually unfolded:

| Variant | Shape | Section skeleton |
|---------|-------|------------------|
| `TreeSearchHandoff` | search frontier | Search Goal · Frontier · Explored Branches · Pruned / Dead Branches · Best So Far · Next Expansion |
| `DecompositionHandoff` | subproblem tree | Top-Level Problem · Decomposition · Solved Subproblems · Open Subproblems · Composition Status · Next Steps |
| `RefinementLoopHandoff` | iteration journal | Objective · Current Draft State · Iteration Log · Open Critiques · Convergence Status · Next Revision |
| `ConstraintSatisfactionHandoff` | constraint ledger | Objective · Constraints · Current Candidate · Conflicts & Tensions · Trade-offs Made · Next Steps |
| `BacktrackingHandoff` | decision stack | Objective · Decision Stack · Tentative Choices · Backtrack Points · Abandoned Paths · Next Steps |
| `TradeoffHandoff` | Pareto frontier | Decision to Make · Objectives & Priorities · Options Evaluated · Frontier · Leaning / Chosen · Open Questions |
| `GoalStackHandoff` | goal hierarchy | Root Goal · Goal Hierarchy · Active Path · Satisfied Goals · Suspended Goals · Next Steps |
| `CoverageHandoff` | coverage map | Objective & Scope · Coverage Map · Completed · Gaps & Skipped · Systematic Next |
| `BudgetBoundedHandoff` | budget curve | Objective · Budget Status · Value Delivered · Remaining Work · Cut Line · Next Steps |
| `MigrationHandoff` | state delta | Target State · Current State · Completed Migrations · Remaining Delta · Reversibility · Next Steps |

```python
from vidbyte import TreeSearchHandoff, RefinementLoopHandoff, BudgetBoundedHandoff

spec = TreeSearchHandoff()        # for branch-and-prune exploration agents
```

### Software-engineering catalog

Prebuilts tuned to common software-engineering task types:

| Variant | SWE task | Section skeleton |
|---------|----------|------------------|
| `CodeReviewHandoff` | reviewing a PR/diff | Scope Reviewed · Review Method · Blocking Issues · Non-Blocking Suggestions · Approved Aspects · Test & Verification Notes · Compatibility & API Impact · Security & Data Handling · Unresolved Threads · Verdict |
| `BugFixHandoff` | fixing a defect | Symptom · Impact & Priority · Reproduction · Investigation Trail · Root Cause · Fix Applied · Tests Added · Verification Results · Regression Risk · Follow-up Work |
| `RefactorHandoff` | restructure, no behavior change | Motivation · Scope & Boundaries · Old Structure · New Structure · Changes by Module · Behavior-Preservation Evidence · Compatibility Notes · Risk Areas · Follow-up Cleanups · Reviewer Notes |
| `PerformanceOptimizationHandoff` | profiling/optimization | Performance Goal · Baseline Metrics · Profiling Method · Bottlenecks Identified · Optimizations Applied · Measured Improvement · Correctness Safeguards · Trade-offs · Remaining Hotspots · Monitoring Plan |
| `TestAuthoringHandoff` | writing tests / coverage | Coverage Goal · Test Strategy · Areas Covered · Test Cases Added · Fixtures & Test Data · Execution Results · Gaps & Untested Paths · Flaky/Skipped Tests · Maintenance Notes · Next Tests |
| `APIDesignHandoff` | designing an endpoint/contract | Purpose & Consumers · Endpoints/Contracts · Request/Response Schemas · Authentication & Authorization · State & Side Effects · Versioning & Compatibility · Error Model · Examples & Edge Cases · Implementation Notes · Open Design Questions |
| `SchemaMigrationHandoff` | DB schema change | Schema Change · Current Data Shape · Target Data Shape · Migration Steps · Backfill Plan · Forward/Backward Compatibility · Data-Integrity Checks · Operational Risks · Rollback Plan · Post-Migration Cleanup |
| `DependencyUpgradeHandoff` | lib/framework bump | Target Versions · Upgrade Motivation · Breaking Changes · Code Adjustments Made · Config & Build Changes · Compatibility Verification · Runtime Behavior Changes · Remaining Deprecations · Rollback · Follow-up Monitoring |
| `IncidentResponseHandoff` | on-call / outage | Impact & Severity · Detection & Alerts · Timeline · Current Mitigation · Root-Cause Status · Systems & Owners · Action Items · Comms Status · Verification & Recovery · Post-Incident Follow-up |
| `ArchitectureDecisionHandoff` | system design / ADR | Problem & Context · Requirements & Constraints · Options Considered · Evaluation Evidence · Decision & Rationale · Consequences & Trade-offs · Implementation Plan · Open Risks · Review & Reversal Criteria · Next Steps |
| `CodebaseOnboardingHandoff` | understanding unfamiliar code | Goal · Repository Layout · System Map · Key Components & Responsibilities · Entry Points & Data Flow · Configuration & Environment · Conventions & Gotchas · Testing & Verification Map · Useful Files & Commands · Open Questions |
| `CICDPipelineHandoff` | build/deploy pipeline work | Pipeline Goal · Current Pipeline Topology · Stages & Status · Build/Deploy Config · Secrets & Environments · Artifacts & Outputs · Failing/Flaky Stages · Changes Applied · Validation & Rollback · Next Steps |
| `IntegrationHandoff` | third-party integration | Integration Goal · External Contract · Auth & Credentials · Implemented Surface · Data Mapping · Error Handling & Retries · Edge Cases & Failure Modes · Local & Test Setup · Verification Status · Untested Paths |
| `SecurityRemediationHandoff` | fixing vulnerabilities | Vulnerabilities · Severity & Exploitability · Threat Model · Affected Surface · Fixes Applied · Verification · Regression & Abuse Tests · Operational Rollout · Residual Risk · Remaining Items |
| `ReleaseHandoff` | cutting a release/deploy | Release Scope · Release Readiness · Changelog · Versioning & Artifacts · Pre-Deploy Checklist · Deploy Steps · Verification & Smoke · Communications · Rollback Plan · Post-Release Follow-up |

### Discovering handoffs with the registry

`HandoffRegistry` is a prefilled catalog of every prebuilt handoff (general + process-shape
+ software-engineering). Use it to browse, construct by name, or build an agent in one step:

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

You rarely build it directly — `BaseAgent.handoff()` does it for you.

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
- Make each section description detailed enough to steer generation: use about 4-5
  sentences, explain what information belongs in the section, specify what the model
  should output, and include enough structure for roughly up to 500 tokens per section.
- Prefer richer handoffs with enough sections to preserve the task state. For new
  domain-specific prebuilts, use around 9-10 sections unless the shape has a strong
  reason to be smaller.
- Add a unit test asserting the new variant exposes a non-empty, distinct section map and
  that `fill()` preserves its type.
