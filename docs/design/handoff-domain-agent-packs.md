# Design Doc: Domain & Agent-Native Handoff Packs

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

> **Stacked PR.** Builds on `feat/handoff-registry` (PR #109) → `feat/handoff-primitive-catalog` (#108) → `feat/handoff-agent` (#105). This PR contains only the new code (28 new `Handoff` subclasses + their registry entries + tests) and assumes #105/#108/#109 are merged. No code from those PRs is repeated. Retarget the base to `main` once they land.

---

## 1. Overview

This change adds two new packs of prebuilt `Handoff` primitives: a **domain pack** covering the first five high-fit fields (Healthcare, Legal, Customer Support, Cybersecurity/SOC, Finance — 13 handoffs) and an **agent-native pack** of 15 handoffs tailored to the artifacts and transition moments of agentic execution (context-window overflow, tool trajectories, sub-agent delegation, human escalation, checkpoint/resume, retrieval, browser/computer use, memory, verification, reasoning traces, guardrails, evaluation). All 28 are registered in `HandoffRegistry`, bringing the discoverable catalog to 56 prebuilts. Each is a thin `Handoff` subclass with only a title and a section map — no new behavior, prompt, or runtime changes.

---

## 2. Goals & Non-Goals

### Goals

- Add 13 domain `Handoff` subclasses across the first five fields:
  - Healthcare: `PatientHandoff`, `CareTransitionHandoff`, `DiagnosticWorkupHandoff`.
  - Legal: `ContractReviewHandoff`, `LegalResearchHandoff`, `DueDiligenceHandoff`.
  - Customer Support: `TicketEscalationHandoff`, `AccountHealthHandoff`.
  - Cybersecurity/SOC: `AlertTriageHandoff`, `ThreatHuntHandoff`.
  - Finance: `InvestmentThesisHandoff`, `DealHandoff`, `CreditAnalysisHandoff`.
- Add 15 agent-native `Handoff` subclasses: `ContextWindowHandoff`, `ToolTrajectoryHandoff`, `SubAgentDelegationHandoff`, `OrchestrationHandoff`, `HumanEscalationHandoff`, `CheckpointResumeHandoff`, `DeepResearchHandoff`, `RetrievalHandoff`, `BrowserSessionHandoff`, `ComputerUseHandoff`, `MemoryHandoff`, `VerificationHandoff`, `ReasoningTraceHandoff`, `GuardrailHandoff`, `EvaluationHandoff`.
- Export all 28 from `vidbyte/context/handoffs.py` `__all__`, `vidbyte/context/__init__.py`, and the root `vidbyte/__init__.py`.
- Register all 28 in `HandoffRegistry` via `_DEFAULT_HANDOFFS`, keyed by stable slugs.
- De-hardcode the three count assertions in `tests/test_handoff_registry.py` so the registry tests survive catalog growth.
- Update the handoff skill doc and add tests + a verification script.

### Non-Goals

- No changes to the base `Handoff`, `HandoffAgent`, `BaseAgent` integration, the handoff prompt asset, or the `HandoffRegistry` class API (owned by #105/#108/#109).
- No new `HandoffRegistry` methods (no `categories()`), no global singleton, no prompt/enum changes.
- No re-implementation of any prior-PR code.
- Fields 6–10 from the industries discussion (Sales, Insurance, Recruiting, Consulting, Journalism) and the remaining domain variants are out of scope for this PR.

---

## 3. Background & Context

PRs #105/#108/#109 established the `Handoff` primitive, `HandoffAgent`, two prebuilt packs (general + process-shape, software-engineering), and the `HandoffRegistry`. The skill doc documents the recipe for adding prebuilts; the registry auto-includes anything added to `_DEFAULT_HANDOFFS`. This change applies that recipe to two new packs identified in discussion: the highest-fit professional domains and a set tailored to agent execution itself (the most on-brand pack, since handoffs exist for agent/harness continuity and these map onto SDK runtime artifacts such as the context window, `ToolCallContext` trace, sub-agent results, and memory).

Because the new classes subclass `Handoff` and register alongside #109's prebuilts, this PR stacks on `feat/handoff-registry`. The existing registry tests hard-code the catalog size (28) in three assertions (`tests/test_handoff_registry.py` lines 82, 104, 133); these must be de-hardcoded so the suite does not break as the catalog grows.

---

## 4. Requirements

### Functional Requirements

1. 28 new `Handoff` subclasses exist in `vidbyte/context/handoffs.py`, each overriding `DEFAULT_TITLE` and `default_sections()` with a non-empty ordered map.
2. All section maps are pairwise distinct across the full 56-prebuilt catalog.
3. `default_sections()` returns a fresh dict per call for each new class.
4. Each new class is exported from the three export sites and inherits `ContextItem` conformance and `fill()` type preservation.
5. All 28 are registered in `HandoffRegistry` under stable lowercase slugs; `HandoffRegistry().list()` returns 56 slugs.
6. Each new slug resolves via `get`/`create`, and `build_agent(slug, ...)` returns a `HandoffAgent` of the right spec type.
7. `HandoffRegistry.describe()` includes every new slug with class, title, and non-empty sections.
8. The three count assertions in `tests/test_handoff_registry.py` are changed to compare against the registry's own length (no magic number), so they remain correct at 56 and beyond.

### Non-Functional Requirements

- **Zero new runtime dependencies**; standard library only.
- **No import cycles**: new classes live in the existing `handoffs.py`; registry imports them at module load (safe).
- **Backward compatible**: purely additive except the test de-hardcoding.
- **Context Protocol Header** on new files; existing headers preserved.
- **Testing**: Python `unittest`, no network — fake runners only.

---

## 5. High-Level Design

Each new handoff is a ~10-line `Handoff` subclass (title + section map), mechanically identical to the existing prebuilts. The domain pack tunes section vocabulary to a profession's task; the agent-native pack tunes it to an agent runtime artifact or transition moment. All 28 are appended to `_DEFAULT_HANDOFFS` in the registry module, so `HandoffRegistry` discovers them automatically; no registry-class change is needed.

```
vidbyte/context/handoffs.py        Handoff base + 56 prebuilt subclasses (28 existing + 28 new)
                                        ^ imported by
vidbyte/lib/registries/handoffs.py _DEFAULT_HANDOFFS gains 28 slug -> class entries
                                        ^ unchanged HandoffRegistry API surfaces them
```

Key decisions: (1) new classes live in `handoffs.py` alongside the rest (established home); (2) no registry API change — only data (`_DEFAULT_HANDOFFS`) grows; (3) the registry test's hard-coded counts are replaced with registry-relative assertions so the suite is robust to future packs; (4) new feature tests live in a dedicated `tests/test_handoff_packs.py`.

---

## 6. Detailed Design

### 6.1 Domain + agent-native `Handoff` subclasses

**File(s):** `vidbyte/context/handoffs.py` — Modified (append 28 classes + extend `__all__`)

Each subclass overrides `DEFAULT_TITLE` and `default_sections()`. No other methods overridden. Full section maps in Appendix A.

### 6.2 Registry default entries

**File(s):** `vidbyte/lib/registries/handoffs.py` — Modified

Add 28 `slug -> class` entries to `_DEFAULT_HANDOFFS` and the corresponding imports. Slugs:

- Domain: `patient`, `care_transition`, `diagnostic_workup`, `contract_review`, `legal_research`, `due_diligence`, `ticket_escalation`, `account_health`, `alert_triage`, `threat_hunt`, `investment_thesis`, `deal`, `credit_analysis`.
- Agent-native: `context_window`, `tool_trajectory`, `sub_agent_delegation`, `orchestration`, `human_escalation`, `checkpoint_resume`, `deep_research`, `retrieval`, `browser_session`, `computer_use`, `memory`, `verification`, `reasoning_trace`, `guardrail`, `evaluation`.

No collisions with existing slugs (e.g. `deep_research` is distinct from the existing `research`).

### 6.3 Context + root exports

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/__init__.py` — Modified. Export all 28 new classes from both namespaces.

### 6.4 Registry test de-hardcoding

**File(s):** `tests/test_handoff_registry.py` — Modified

Replace the three `== 28` assertions (lines 82, 104, 133) with registry-relative checks:
- distinctness test: assert `len(maps) == len(set(maps))` and `len(maps) == len(registry.all())` (drop the literal 28); rename the test to drop the number.
- list test: assert all slugs are unique and `len(list()) == len(all())`, and that `code_review` is present; rename to drop the number.
- describe test: assert `len(described) == len(registry.all())`.

### 6.5 Skill doc

**File(s):** `skills/vidbyte-sdk/handoff.md` — Modified. Add a domain-pack catalog table and an agent-native-pack catalog table.

### 6.6 Tests + verification script

**File(s):** `tests/test_handoff_packs.py` (new), `scripts/test_handoff_packs.py` (new).

---

## 7. Data Model Changes

N/A — no schema/database changes. Additions are in-memory `Handoff` subclasses and registry dictionary entries.

---

## 8. API Changes

N/A for HTTP. New Python exports: 28 new handoff classes from `vidbyte` and `vidbyte.context`. The `HandoffRegistry` API is unchanged; only its default catalog grows. All additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/handoff-domain-agent-packs.md` | This design doc (first commit) |
| MODIFY | `vidbyte/context/handoffs.py` | Add 28 domain + agent-native `Handoff` subclasses + `__all__` |
| MODIFY | `vidbyte/context/__init__.py` | Export the 28 new classes |
| MODIFY | `vidbyte/__init__.py` | Root exports for the 28 new classes |
| MODIFY | `vidbyte/lib/registries/handoffs.py` | Register the 28 new prebuilts in `_DEFAULT_HANDOFFS` |
| MODIFY | `tests/test_handoff_registry.py` | De-hardcode the three catalog-size assertions |
| MODIFY | `skills/vidbyte-sdk/handoff.md` | Document the domain and agent-native packs |
| CREATE | `tests/test_handoff_packs.py` | Tests for the 28 new classes + registry coverage |
| CREATE | `scripts/test_handoff_packs.py` | Phase 5 verification script |

---

## 10. Testing Plan

Python `unittest` with fake runners, no network. `NEW` = the 28 new classes; `DOMAIN`/`AGENT` denote the two sub-lists.

### Unit Tests

- `it('every new variant exposes a non-empty default_sections map')` — [Edge Case] (iterates all 28)
- `it('all 56 prebuilt section maps are pairwise distinct via the registry')` — [Silent Failure] (catches a copy-pasted map between any two prebuilts, new or old)
- `it('every new variant fill() returns the same subclass')` — [Silent Failure]
- `it('every new variant is a ContextItem with a non-default title')` — [Hidden Assumption]
- `it('default_sections returns a fresh dict per instance for a domain and an agent-native variant')` — [Hidden Failure]
- `it('registry.list() contains every new slug and totals 56')` — [Edge Case]
- `it('registry.get(slug) resolves each new slug to its class')` — [Hidden Assumption] (iterates a slug→class expectation map for all 28)
- `it('registry.create(slug) returns the right type for a domain and an agent-native slug')` — [Edge Case]
- `it('registry.describe() includes every new slug with class, title, and non-empty sections')` — [Silent Failure]
- `it('new slugs do not collide with existing slugs (deep_research != research)')` — [Hidden Failure] (registering both keeps both)
- `it('agent-native variants with slash titles render and parse correctly')` — [Silent Failure] (e.g. `ToolTrajectoryHandoff` "Calls Made & Results"; `GuardrailHandoff` "Needs Human Approval")

### Integration Tests

- `it('registry.build_agent("patient", runner=fake).generate_handoff(...) returns a filled PatientHandoff')` — [Hidden Assumption] (domain variant through the unchanged agent path).
- `it('registry.build_agent("context_window", runner=fake).generate_handoff(...) returns a filled ContextWindowHandoff with all sections mapped')` — [Hidden Assumption] (agent-native variant end to end).
- Silent-failure path: a variant whose section titles contain `&` or `/` (e.g. `Calls Made & Results`, `Forward/Backward` is SWE; here `Verified vs Unverified`, `Confidence & Next Queries`) must round-trip through `## Title` parsing without mangling — [Silent Failure].
- Mock vs real: fake runner only.

### Manual / QA Test Cases

1. Given `from vidbyte import ContextWindowHandoff`, when `ContextWindowHandoff().to_context_text()` is rendered, then it contains `## Resume Instructions` and `## Compacted/Dropped Context` — [Edge Case: punctuated titles].
2. Given `HandoffRegistry().describe()["human_escalation"]`, then the title is "Human Escalation Handoff" and a "Specific Decision Needed" section is present — [Hidden Assumption].
3. Given `HandoffRegistry().build_agent("threat_hunt", runner=fake)`, when run, then a filled `ThreatHuntHandoff` is produced — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | 3.11+ | Types, unittest | None |
| `vidbyte.context.handoffs` + `HandoffRegistry` (PR #105/#108/#109) | stacked branch | Base + registry extended here | Medium — unmergeable to `main` until the stack lands; mitigated by stacking |

No new third-party packages.

---

## 12. Rollout & Deployment

- No feature flags. Additive (plus a test de-hardcoding that strengthens the suite).
- **Stacked PR**; base `feat/handoff-registry`. Merge order: #105 → #108 → #109 → `main`, then retarget this PR to `main`.
- Rollback: revert the PR; no migrations or persisted state.

---

## 13. Open Questions

- [x] Scope: first 5 fields (13 handoffs) + all 15 agent-native handoffs, per request.
- [x] Registry: no API change; new prebuilts added to `_DEFAULT_HANDOFFS` only.
- [ ] Catalog-size assertions: de-hardcode to registry-relative (chosen) rather than bump 28→56, so future packs don't require test edits.
- [ ] `OrchestrationHandoff` vs `SubAgentDelegationHandoff` overlap: kept as two distinct shapes (plan/assignment vs spawn/synthesis); their section maps differ, satisfying the distinctness test.

---

## 14. Alternatives Considered

### Alternative 1: Bump the hard-coded 28 to 56 in the registry tests
- What: update the literals.
- Why rejected: it would break again on the next pack; comparing to `len(registry.all())` is robust and self-maintaining.

### Alternative 2: Group prebuilts by category with a `categories()` helper
- What: add category grouping to the registry.
- Why rejected: out of scope per prior decision; the flat slug catalog plus `describe()` is sufficient, and adding category metadata is a separate change.

### Alternative 3: Separate modules per pack (`handoffs_domain.py`, `handoffs_agent.py`)
- What: split the growing `handoffs.py`.
- Why rejected: fragments the catalog and breaks the established single-home convention; if `handoffs.py` later needs splitting, that is its own refactor PR.

---

## Appendix A — Section maps

Each entry is `Section Title → guidance description`. Each section guidance is generated as four model-facing sentences that explain what to output, request roughly 500 tokens when the task has enough substance, and state what continuity details to preserve.

### Domain pack

**PatientHandoff** (Patient Handoff): Situation; Background; Assessment; Recommendation; Pending Tasks; Watch-fors; Medications & Treatments; Care Team & Family Context; Escalation Criteria.
**CareTransitionHandoff** (Care Transition Handoff): Diagnosis & Status; Medications; Procedures Done/Pending; Follow-up Plan; Red Flags; Receiving Team Responsibilities; Patient Constraints; Documentation Gaps.
**DiagnosticWorkupHandoff** (Diagnostic Workup Handoff): Presentation; Differential; Tests Ordered/Resulted; Leading Diagnosis; Next Steps; Ruled-Out Concerns; Urgency & Safety Plan; Consults & Ownership.
**ContractReviewHandoff** (Contract Review Handoff): Parties & Purpose; Key Terms; Risk Flags; Redlines Proposed; Open Negotiation Points; Recommendation; Business Context; Fallback Positions; Approval Path.
**LegalResearchHandoff** (Legal Research Handoff): Issue; Authorities Found; Holdings & Application; Counterarguments; Confidence & Gaps; Research Trail; Fact Dependencies; Draft Answer.
**DueDiligenceHandoff** (Due Diligence Handoff): Scope; Findings by Category; Material Risks; Documents Reviewed; Outstanding Requests; Decision Impact; Assumptions & Limits; Next Review Pass.
**TicketEscalationHandoff** (Ticket Escalation Handoff): Customer Goal; Actions Tried; Current State; Reproduction; Why Escalated; Suggested Next Step; Environment Details; Artifacts & Evidence; Customer Communication.
**AccountHealthHandoff** (Account Health Handoff): Account Status; Usage & Risk Signals; Open Issues; Relationship Notes; Renewal/Expansion Posture; Success Plan; Executive Narrative; Next Touchpoints.
**AlertTriageHandoff** (Alert Triage Handoff): Alerts in Queue; Triaged & Dispositioned; Under Investigation; Suspected Scope; Next Actions; Evidence Collected; Containment Status; Escalation Path.
**ThreatHuntHandoff** (Threat Hunt Handoff): Hypothesis; Data Sources Queried; Findings; Ruled Out; Open Leads; Coverage Map; Detection Opportunities; Response Readiness.
**InvestmentThesisHandoff** (Investment Thesis Handoff): Thesis; Supporting Evidence; Key Risks; Valuation View; Catalysts; Open Diligence; Positioning & Sizing; Variant Views; Monitoring Plan.
**DealHandoff** (Deal Handoff): Deal Status; Workstreams; Open Items by Workstream; Key Risks; Next Milestones; Negotiation State; Stakeholder Map; Integration or Closing Readiness.
**CreditAnalysisHandoff** (Credit Analysis Handoff): Borrower & Facility; Financial Assessment; Risk Factors; Rating/Recommendation; Open Questions; Covenants & Protections; Scenario Analysis; Approval Conditions.

### Agent-native pack

**ContextWindowHandoff** (Context Window Handoff): Task State; Key Facts to Preserve; Decisions Made; Compacted/Dropped Context; Active Working Set; Resume Instructions; Token Budget Strategy; Validation Needed; Lost Nuance.
**ToolTrajectoryHandoff** (Tool Trajectory Handoff): Available Tools; Calls Made & Results; Failed Calls & Errors; Current Tool State; Next Tool Action; Artifacts Produced; Permission Boundaries; Ordering Dependencies.
**SubAgentDelegationHandoff** (Sub-Agent Delegation Handoff): Top Goal; Subagents Spawned; Results Received; Pending Delegations; Synthesis State; Next Delegation; Conflict Resolution; Quality Gates; Shared Context.
**OrchestrationHandoff** (Orchestration Handoff): Plan; Agent Assignments; Completed/In-Flight/Blocked; Cross-Agent Conflicts; Next Dispatch; Shared State; Coordination Rules; Completion Criteria.
**HumanEscalationHandoff** (Human Escalation Handoff): What I Was Doing; Where I'm Stuck; What I Tried; Specific Decision Needed; Options & Recommendation; Risk of Proceeding; Needed Context From Human; Safe Holding Pattern.
**CheckpointResumeHandoff** (Checkpoint Resume Handoff): Goal; Progress So Far; Current Step; Environment State; Blockers; Resume Point; Verification Snapshot; Rollback or Recovery; Budget Remaining.
**DeepResearchHandoff** (Deep Research Handoff): Question; Search Queries Run; Sources Gathered; Synthesis So Far; Contradictions; Confidence & Next Queries; Source Quality Notes; Unanswered Subquestions; Citation Trail.
**RetrievalHandoff** (Retrieval Handoff): Query; Chunks Retrieved; Relevance Assessment; Coverage Gaps; Re-query Plan; Corpus Assumptions; Answer Candidates; Deduplication Notes.
**BrowserSessionHandoff** (Browser Session Handoff): Current Location; Session & Auth State; Action Trail; Extracted Data; Blockers; Next Action; Viewport & Timing Notes; Download or Upload State; Safety Constraints.
**ComputerUseHandoff** (Computer Use Handoff): Desktop State; Apps & Windows Open; Action Trail; Files Touched; Blockers; Next Step; Input State; System Constraints; Recovery Notes.
**MemoryHandoff** (Memory Handoff): Working Memory; Long-Term Facts Learned; Updated/Stale Beliefs; Open Questions; What to Persist; What Not to Persist; Source Evidence; Memory Conflicts.
**VerificationHandoff** (Verification Handoff): Claims Made; Verified vs Unverified; Failed Checks; Confidence per Claim; What Still Needs Checking; Verification Methods; Corrections Applied; Residual Risk.
**ReasoningTraceHandoff** (Reasoning Trace Handoff): Goal; Reasoning So Far; Key Inferences; Assumptions Made; Dead Ends; Current Direction; Decision Points; Evidence Ledger; Output Implications.
**GuardrailHandoff** (Guardrail Handoff): Requested Action; Policy Triggered; What Was Blocked; Safe Alternatives; Needs Human Approval; Risk Rationale; Allowed Progress; Escalation Record.
**EvaluationHandoff** (Evaluation Handoff): Rubric; Items Graded; Scores & Rationale; Uncertain/Disputed; Remaining to Grade; Calibration Notes; Evidence Reviewed; Finalization Criteria.
