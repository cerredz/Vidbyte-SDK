# Design Doc: Adversarial Agent Settings

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

Extend the `AdversarialSettings` introduced by draft PR #275 with a portable, immutable settings contract for controls that its existing sequential critique-and-revise implementation can honor now. The stacked change moves the contract to the low-level dataclass package, preserves every current import, adds specialty-lens assignment, fresh-reviewer rounds, a whole-run timeout, and a deterministic child-call ceiling, and updates the existing adversarial documentation. It deliberately does not add topology/provider/debate/tournament settings that the one-worker/one-adversary-prototype controller cannot execute.

---

## 2. Goals & Non-Goals

### Goals

- Stack the implementation branch and draft PR directly on PR #275's head branch, `feat/adversarial-agent`.
- Preserve the existing `AdversarialSettings` name, defaults, frozen/slotted semantics, validation behavior, and public imports.
- Move the contract to `vidbyte/lib/dataclasses/adversarial.py` so agents, future tools, and context algorithms can import it without a context-to-agents dependency.
- Add behaviorally authoritative `specialties`, `fresh_adversaries_each_round`, `run_timeout_seconds`, and `max_child_calls` settings.
- Add a `specialist_panel(...)` preset for the only panel shape PR #275 can currently express: independently prompted forks of one adversary prototype.
- Keep orchestration in `AdversarialAgent` and its private controller; add no public strategy hierarchy or review subsystem.
- Update all PR #275 documentation that describes settings location, lifecycle, limits, or reviewer reuse.
- Add no test files and no verification scripts.

### Non-Goals

- Implement self-reflection, cross-provider panels, prosecutor/defender/judge, debate, Delphi, tournament, multi-candidate selection, counterexample generation, mutation/fuzzing, tool-backed verification, evidence adjudication, live-action gates, trajectory critics, terminal gates, or shadow review.
- Add inert settings for unsupported topologies, provider/model ownership, peer visibility, parallel execution, candidate counts, debate turns, Delphi phases, tournament brackets, mutation counts, evidence thresholds, severity policy, acceptance scoring, or adjudication.
- Change the runnerless facade boundary, add facade-level runner/provider/model/tools/MCP configuration, or introduce a second settings abstraction.
- Parallelize reviewer calls; PR #275's child forks may share non-concurrency-safe runners and tools.
- Enforce aggregate child token or dollar-cost budgets; PR #275 does not expose reliable normalized child usage/cost accounting at the facade boundary.
- Integrate adversarial settings into context-window algorithms or add adversarial launch tools; those are follow-up stacked changes.

---

## 3. Background & Context

Draft PR #275 is open, mergeable, and based on `main`. Its head is `feat/adversarial-agent` at `847b442130b9a8e6f52d5bc34886fe55910a33b1`; its base snapshot is `main` at `213d3378f2b5a8c981318a9e1619daa998890f62`. It adds a runnerless `AdversarialAgent` with one worker prototype, one adversary prototype, sequential reviewer calls, exact review/revision rounds, and an in-module frozen/slotted `AdversarialSettings`.

The existing contract has `num_adversaries`, `adversarial_rounds`, `min_successful_adversaries`, `per_adversary_timeout`, `max_review_chars`, and `max_worker_output_chars`. A successful run makes exactly `1 + adversarial_rounds * (num_adversaries + 1)` child-agent invocations. Reviewer failures are collected and checked against the per-round success threshold; reviewers are reused by index across rounds.

The broader product direction includes many genuinely different adversarial topologies. Those cannot be represented honestly by settings alone: PR #275 accepts only one adversary prototype, has no judge/adjudicator/candidate collection, exposes unstructured review text, and intentionally runs reviewers sequentially without peer transcripts. This design therefore implements the narrow settings delta the current controller can enforce and records the full topology contract as future work.

The active checkout is dirty with unrelated untracked design files and old nested worktrees. Those files must remain untouched. After approval, implementation must occur in a new worktree based on PR #275's head, not in the active checkout and not from `main`.

---

## 4. Requirements

### Functional Requirements

1. `AdversarialSettings` remains a frozen, slotted dataclass and retains all six PR #275 fields and defaults.
2. Existing imports from `vidbyte`, `vidbyte.agents`, and `vidbyte.agents.adversarial` continue to resolve to the same class object.
3. `vidbyte.agents.settings` and `vidbyte.lib.dataclasses` additionally export `AdversarialSettings`.
4. `specialties` accepts an immutable sequence of nonblank strings in one of three shapes: empty for generic review, one shared specialty for every reviewer, or exactly `num_adversaries` index-aligned specialties.
5. Each specialty is trimmed and bounded to 500 characters before any child call.
6. Reviewer prompts include only the specialty assigned to that reviewer index; reviewers in one round still see the same worker snapshot and never see peer reviews.
7. `AdversarialReview` records its assigned specialty so typed results remain auditable without placing specialty text in trace attributes.
8. `AdversarialSettings.specialist_panel(...)` returns a validated settings object whose adversary count matches the supplied specialty count; conflicting explicit counts are rejected.
9. `fresh_adversaries_each_round=False` preserves PR #275 reviewer reuse. When true, each round receives newly forked adversaries with round-qualified names; the worker remains the same run-local fork.
10. Every fresh reviewer fork is included in the controller's existing cleanup ownership and is closed on success, error, timeout, or cancellation.
11. `run_timeout_seconds`, when set, bounds the complete child workflow rather than each individual review and raises a safe `AdversarialExecutionError` after cleanup.
12. `max_child_calls`, when set, is a positive integer and must be at least the deterministic `required_child_calls`; invalid budgets fail during settings construction before child forks or model calls.
13. `required_child_calls` is exposed as a derived read-only property using the existing exact-call formula. It counts child-agent invocations, not child tool calls.
14. Card, reply, result, and trace summaries include bounded policy facts (`specialty_count`, freshness, required child calls, and configured budgets) but never raw specialty strings in trace/card metadata.
15. Existing `min_successful_adversaries` remains the review-failure policy; failed reviews remain ordered data and the controller still attempts every configured reviewer in the round.
16. No topology or topology-specific field may be accepted unless the current controller makes it behaviorally authoritative.
17. Documentation must distinguish a specialty panel of homogeneous prototype forks from a cross-provider or independently configured agent panel.
18. The later draft PR must target `feat/adversarial-agent`, making it visibly and mechanically stacked on PR #275.

### Non-Functional Requirements

- **Performance:** Defaults preserve PR #275's sequential latency and exact call count. Fresh reviewers add fork/cleanup overhead but no additional model calls.
- **Scalability:** Specialty storage is bounded by `num_adversaries` and 500 characters per entry. `max_child_calls` provides a preflight ceiling over the deterministic workflow.
- **Security:** Specialty text is untrusted prompt input, JSON-encoded/tagged by the existing renderer, omitted from traces/cards, and never grants tools or permissions.
- **Observability:** Safe summaries expose counts and active limits; `AdversarialReview.specialty` provides full run-local audit detail through `last_result`.
- **Reliability:** Validation occurs before execution. Whole-run timeout and cancellation must preserve the controller's shielded run-local MCP cleanup.
- **Compatibility:** Default construction and existing public imports remain source compatible. The class's canonical module path changes before PR #275 merges, so no released pickle compatibility is promised.

---

## 5. High-Level Design

Move `AdversarialSettings` out of the facade module into a low-level immutable contract module, then re-export it through the existing agent-facing paths. This follows the repository's `MultiAgentSettings` placement under `vidbyte.lib.dataclasses` and keeps future context algorithms from importing `vidbyte.agents`.

The current controller remains the only workflow implementation. It asks settings for the specialty assigned to each reviewer, chooses whether reviewers are forked once or once per round, and executes under an optional total timeout. The deterministic call budget is validated from settings before execution; no generic strategy dispatcher or topology registry is introduced.

```text
AdversarialSettings (portable immutable contract)
        |
        v
AdversarialAgent -> _AdversarialRunController
        |                    |
        |                    +-> one persistent worker fork
        |                    +-> reused OR fresh sequential reviewer forks
        |                    +-> specialty-aware review prompts
        |                    +-> exact call-budget and total-time bounds
        v
AgentMessage + AdversarialResult
```

Requested settings that need additional agents, candidates, interaction graphs, structured verdicts, or provider ownership remain out of this PR. Adding them now would create settings that appear supported but are ignored, which is worse than an explicit future extension point.

---

## 6. Detailed Design

### 6.1 Portable Adversarial Settings Contract

**File(s):** `vidbyte/lib/dataclasses/adversarial.py`
**Type:** New file

#### What it does

Owns the validated, immutable configuration used by `AdversarialAgent` and future consumers without importing the agent package.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    num_adversaries: int = 1
    adversarial_rounds: int = 1
    min_successful_adversaries: int = 1
    per_adversary_timeout: float | None = None
    max_review_chars: int = 4000
    max_worker_output_chars: int = 12000
    specialties: tuple[str, ...] = ()
    fresh_adversaries_each_round: bool = False
    run_timeout_seconds: float | None = None
    max_child_calls: int | None = None

    @property
    def required_child_calls(self) -> int: ...

    def specialty_for(self, adversary_index: int) -> str | None: ...

    @classmethod
    def specialist_panel(cls, specialties: Sequence[str], **overrides: Any) -> "AdversarialSettings": ...
```

#### Logic / Algorithm

1. Normalize `specialties` to a tuple of stripped strings using `object.__setattr__`.
2. Apply existing positive integer, threshold, and timeout validation.
3. Validate specialty cardinality as zero, one, or `num_adversaries`; reject blank or over-500-character values.
4. Validate `fresh_adversaries_each_round` as an actual boolean.
5. Validate `run_timeout_seconds` like `per_adversary_timeout`.
6. Compute `required_child_calls` from the existing exact formula and reject a smaller `max_child_calls`.
7. Have `specialist_panel` require at least one specialty, derive `num_adversaries`, and delegate all other validation to the constructor.

#### Edge Cases & Error Handling

- Strings are not accepted as a sequence standing in for the entire `specialties` tuple.
- Duplicate specialty names are allowed because two independent reviewers may intentionally share a lens.
- A singleton specialty applies to every reviewer; an exact-length tuple maps one-to-one by one-based reviewer index.
- Invalid values raise `ConfigurationError` with safe field/expected/actual details before execution.
- The preset rejects a conflicting `num_adversaries` override instead of silently replacing it.

### 6.2 Facade And Controller Enforcement

**File(s):** `vidbyte/agents/adversarial.py`
**Type:** Modified

#### What it does

Imports the portable settings contract, makes every new setting affect execution, and keeps all orchestration private to the existing facade/controller.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AdversarialReview:
    round_index: int
    adversary_index: int
    adversary_name: str
    specialty: str | None = None
    content: str = ""
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

`AdversarialAgent.__init__`, `generate_reply`, and `fork` signatures remain unchanged.

#### Logic / Algorithm

1. Remove the in-module settings class and import the canonical contract.
2. Pass each index's assigned specialty into `render_review_prompt` and into success/failure `AdversarialReview` records.
3. Preserve one-time reviewer forking when freshness is false.
4. When freshness is true, fork a new sequential reviewer set at the beginning of each round, with names containing the round and index, and append every fork to `_run_agents` for final cleanup.
5. Execute the controller directly when no run timeout is configured; otherwise wrap the controller coroutine with `asyncio.wait_for`.
6. Convert total timeout into `AdversarialExecutionError` with safe `phase="run_timeout"`, configured timeout, and required-call details; do not include prompts or specialty text.
7. Extend bounded result/reply/card/trace summaries with policy counts and numeric/boolean limits.

#### Edge Cases & Error Handling

- Per-review timeout remains a failed review record; whole-run timeout is fatal.
- Whole-run timeout during reviewer or worker execution cancels the controller, whose `finally` block closes all run-local children.
- Fresh reviewer fork failure is fatal before that round's model calls; already-created forks remain cleanup-owned.
- Reviewer order, immutable per-round snapshot, threshold evaluation, and exact child invocation count do not change.
- No specialty is forwarded to the worker as an instruction; it is attached to each review record, while the successful review text still reaches the worker through the existing untrusted-review envelope.

### 6.3 Public Re-Exports

**File(s):** `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/agents/settings/__init__.py`, `vidbyte/agents/__init__.py`
**Type:** Modified

#### What it does

Exposes the canonical class through low-level, settings, agent, and existing root import paths without duplicating class definitions.

#### Interface / API

```python
from vidbyte import AdversarialSettings
from vidbyte.agents import AdversarialSettings
from vidbyte.agents.adversarial import AdversarialSettings
from vidbyte.agents.settings import AdversarialSettings
from vidbyte.lib.dataclasses import AdversarialSettings
```

#### Logic / Algorithm

1. Export the class from the low-level dataclass package.
2. Re-export it from `vidbyte.agents.settings`.
3. Import it into `vidbyte.agents` through the settings package while leaving root `vidbyte` unchanged.
4. Keep it imported and listed in `vidbyte.agents.adversarial.__all__` for compatibility.

#### Edge Cases & Error Handling

- Verification asserts every import path is object-identical.
- No alias subclass or wrapper is permitted because it would break `isinstance` checks in `AdversarialAgent`.

### 6.4 Documentation Alignment

**File(s):** `README.md`, `llms.txt`, `vidbyte/agents/README.md`, `skills/sdk/SKILL.md`, `skills/usage/available_features.md`, `skills/usage/create_agents.md`, `skills/vidbyte-sdk-doc/SKILL.md`, `skills/vidbyte-sdk/adversarial-agent.md`
**Type:** Modified

#### What it does

Updates every PR #275 surface that describes settings ownership or behavior.

#### Interface / API

N/A - documentation changes only.

#### Logic / Algorithm

1. Add examples for specialty assignment, the specialist-panel preset, fresh reviewers, and call/time ceilings.
2. Preserve the exact child-call formula and sequential-review warning.
3. Clarify that specialty panels still clone one adversary prototype and are not cross-provider panels.
4. Correct module ownership references after moving the settings class.
5. List unsupported topology families as future orchestration work, not accepted settings.

#### Edge Cases & Error Handling

- Examples must not imply parallelism, provider diversity, early stopping, structured adjudication, or aggregate token/cost enforcement.
- Documentation must keep facade runner/tool/MCP restrictions from PR #275.

---

## 7. Data Model Changes

### 7.1 `AdversarialSettings`

**Change type:** Modified and moved

```python
# Canonical module changes from vidbyte.agents.adversarial
# to vidbyte.lib.dataclasses.adversarial.
# Public compatibility re-exports remain.

specialties: tuple[str, ...] = ()
fresh_adversaries_each_round: bool = False
run_timeout_seconds: float | None = None
max_child_calls: int | None = None
```

**Migration strategy:** Existing construction requires no changes. Consumers may adopt new fields incrementally. Because PR #275 is unmerged, the canonical-module move happens before release; existing public import statements remain valid.

- Forward migration: merge PR #275, then this stacked PR, or retarget the stacked PR to `main` after #275 merges.
- Rollback plan: revert the stacked PR; PR #275's original in-module settings contract and fixed behavior remain intact.

### 7.2 `AdversarialReview`

**Change type:** Modified

```python
specialty: str | None = None
```

**Migration strategy:** The new field has a default and does not affect existing keyword construction.

- Forward migration: review records begin carrying their assigned lens.
- Rollback plan: remove the field and specialty prompt wiring together.

### 7.3 Database, Session, And External Schemas

N/A - settings and results remain in-process Python values; no database, durable session, wire, or migration schema changes are introduced.

---

## 8. API Changes

### 8.1 Python `AdversarialSettings`

**Change type:** Modified

**Request:**

```python
settings = AdversarialSettings.specialist_panel(
    ("security", "correctness", "evidence"),
    adversarial_rounds=2,
    min_successful_adversaries=2,
    fresh_adversaries_each_round=True,
    run_timeout_seconds=180.0,
    max_child_calls=9,
)
```

**Response:**

```python
assert settings.required_child_calls == 9
assert settings.specialty_for(1) == "security"
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| `ConfigurationError` | Specialty values are blank, too long, or have invalid cardinality |
| `ConfigurationError` | `max_child_calls` is below `required_child_calls` |
| `ConfigurationError` | Run/reviewer timeout or existing numeric fields are invalid |
| `AdversarialExecutionError` | The total run exceeds `run_timeout_seconds` |

### 8.2 Python Import Surface

**Change type:** Modified

**Request:**

```python
from vidbyte.agents.settings import AdversarialSettings
from vidbyte.lib.dataclasses import AdversarialSettings as PortableAdversarialSettings
```

**Response:**

```python
assert AdversarialSettings is PortableAdversarialSettings
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| Import failure | Indicates an export regression and blocks the PR |

### 8.3 HTTP Or External Service Endpoints

N/A - this SDK feature adds no HTTP endpoint or external request/response contract.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/adversarial-agent-settings.md` | Approved stacked design and implementation source of truth |
| CREATE | `vidbyte/lib/dataclasses/adversarial.py` | Portable frozen/slotted settings contract and validation |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export the portable settings contract |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Add the agent-settings namespace export |
| MODIFY | `vidbyte/agents/adversarial.py` | Consume settings and enforce specialty, freshness, timeout, and call budget behavior |
| MODIFY | `vidbyte/agents/__init__.py` | Route the public export through the canonical settings contract |
| MODIFY | `README.md` | Document new settings and honest panel boundary |
| MODIFY | `llms.txt` | Keep the model-facing SDK reference synchronized |
| MODIFY | `vidbyte/agents/README.md` | Update agent package ownership and examples |
| MODIFY | `skills/sdk/SKILL.md` | Correct settings ownership and modification guidance |
| MODIFY | `skills/usage/available_features.md` | Update adversarial settings usage |
| MODIFY | `skills/usage/create_agents.md` | Update construction examples |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Update module inventory and settings semantics |
| MODIFY | `skills/vidbyte-sdk/adversarial-agent.md` | Expand the authoritative adversarial-agent guide |

No files will be deleted. No test files or verification scripts will be created or modified.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `dataclasses`, `asyncio`, collections ABCs | Python 3.11+ | Immutable contract, replacement/preset construction, total timeout | Low |
| PR #275 `AdversarialAgent` implementation | Head `847b442130b9a8e6f52d5bc34886fe55910a33b1` at audit time | Required stacked base and enforcement point | High if the PR head changes before implementation |
| `ConfigurationError` / `AdversarialExecutionError` | Repository implementation | Safe validation and execution failures | Low |

No new package dependency or external service is introduced.

---

## 11. Rollout & Deployment

- No feature flag is needed; existing defaults preserve PR #275 behavior.
- After explicit approval, verify PR #275 is still open and resolve its current head OID.
- Fetch `origin/feat/adversarial-agent`, create `feat/adversarial-agent-settings` in an isolated worktree from that ref, and commit this design doc before implementation code.
- Do not check out/pull `main` for this stacked branch. If PR #275 advanced, use its latest head and reconcile this design before implementation.
- Push `feat/adversarial-agent-settings` and create a draft PR with `--base feat/adversarial-agent`, not `--base main`.
- If PR #275 merges first, rebase/retarget the stacked PR to `main` without changing feature scope.
- Verification commands (no test files or scripts):

```powershell
python -m compileall -q vidbyte
python -c "from vidbyte import AdversarialSettings as A; from vidbyte.agents.settings import AdversarialSettings as B; from vidbyte.lib.dataclasses import AdversarialSettings as C; assert A is B is C"
python -c "from vidbyte import AdversarialSettings; s=AdversarialSettings.specialist_panel(('security','evidence'), adversarial_rounds=2, max_child_calls=7); assert s.required_child_calls == 7 and s.specialty_for(2) == 'evidence'"
python -m build
git diff --check origin/feat/adversarial-agent...HEAD
```

- Rollback is one stacked-PR revert; PR #275 remains the functioning baseline.

---

## 12. Open Questions

- [ ] Does approval confirm the narrow behavior-first scope, with unsupported topology/provider/debate/tournament/evidence settings deferred rather than added as inert fields?
- [ ] Is the `specialist_panel(...)` name acceptable given that it applies distinct review lenses to forks of one adversary prototype, not independently configured or cross-provider agents?
- [ ] Should the hard 500-character specialty bound be configurable, or is a fixed safe envelope preferable for this initial contract?
- [ ] Should a later orchestration PR replace the single `adversary` prototype with explicit reviewer specifications before defining the broader topology settings?

---

## 13. Alternatives Considered

### Alternative 1: Add Every Future Topology Field Now

- What: Add topology, provider diversity, peer visibility, debate, Delphi, tournament, candidate, mutation, adjudication, evidence, severity, token, and cost fields immediately.
- Why rejected: PR #275 cannot honor them. Accepting those values would create a misleading API, while rejecting most combinations would provide little usable value and prematurely freeze names before orchestration contracts exist.

### Alternative 2: Put Settings Under `vidbyte.agents.settings`

- What: Move the dataclass to `vidbyte/agents/settings/adversarial.py`.
- Why rejected: Future context-window algorithms would need to import the agent package, increasing circular-dependency risk. The repository already places `MultiAgentSettings` in `vidbyte.lib.dataclasses` and re-exports it publicly.

### Alternative 3: Keep Settings Inside `vidbyte/agents/adversarial.py`

- What: Extend the existing in-module class without moving it.
- Why rejected: It couples a reusable policy contract to the high-level facade and makes later tool/context consumers depend on agent orchestration internals.

### Alternative 4: Introduce A Public Strategy Hierarchy

- What: Add strategy classes for every adversarial topology and have settings select one.
- Why rejected: The user explicitly does not want a new abstraction, and the current need is a validated data contract. Private controller logic remains the appropriate owner until multiple implemented topologies demonstrate a real shared interface.

### Alternative 5: Implement Parallel Or Cross-Provider Panels In This PR

- What: Accept multiple reviewer prototypes/providers and execute them concurrently.
- Why rejected: This materially expands PR #275's constructor and ownership model, invalidates its shared-runner/tool safety assumption, and exceeds a settings-focused stacked PR.

### Alternative 6: Make Specialty A Child System-Prompt Mutation

- What: fork an adversary and replace its system prompt for each specialty.
- Why rejected: subtype-specific fork behavior and system-prompt replacement are not uniform. Passing a bounded specialty lens in the existing deterministic review envelope preserves the prototype's authored identity and permissions.
