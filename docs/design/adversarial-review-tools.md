# Design Doc: Adversarial Review Tool Scaffolds

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

Add a family of prebuilt, model-callable adversarial review tools under `vidbyte.tools.builtins` without implementing adversarial orchestration yet. Each public class is a `BaseTool` with a stable tool name, topology-specific description, bounded input schema, conservative permission, and metadata marking it as a TODO scaffold. Until the separately developed `AdversarialAgent` has a reusable review/topology contract, every tool returns a deterministic `ToolResult.error` explaining that execution is unavailable. This reserves the SDK entry points and makes the remaining integration work explicit without inventing another public review abstraction or pretending the tools can already launch agents.

---

## 2. Goals & Non-Goals

### Goals

- Add distinct public `BaseTool` subclasses for the first sixteen requested adversarial review topologies.
- Make the tools importable from `vidbyte.tools.builtins` and the dedicated `vidbyte.tools.builtins.adversarial` module.
- Give every tool a unique, stable snake-case model-facing name.
- Give every tool a topology-appropriate input schema rather than exposing one generic strategy switch.
- Keep developer-owned topology policy out of model-call arguments: reviewer counts, rounds, specialties, providers, thresholds, tools, timeouts, and budgets are not model-controlled fields.
- Mark every public tool class with a precise `TODO(adversarial-agent)` comment describing the missing orchestration behavior.
- Mark every `ToolSpec` with structured scaffold metadata so catalogs and developer tooling can identify unfinished launchers.
- Return a normal, bounded `ToolResult.error` if a scaffold is invoked, preserving the agent tool loop instead of raising `NotImplementedError`.
- Use `ToolPermission.EXECUTE` because the finished tools will initiate provider/model work and may run configured child tools.
- Reuse one private implementation helper inside the tool module; do not add a public adversarial-review framework or strategy hierarchy.
- Document the scaffolds and their unavailable execution state in the tools package README.
- Add no test files or persistent verification scripts, per the explicitly selected `design-doc-no-tests` workflow.

### Non-Goals

- Do not implement, modify, or merge `AdversarialAgent` in this change.
- Do not launch any agent, model, provider request, tool, subprocess, thread, or task from the scaffolds.
- Do not implement self-reflection, panels, debate, adjudication, candidate generation, tournament selection, mutation, fuzzing, evidence checking, or revision logic yet.
- Do not add adversarial review behavior to context-window algorithms, middleware, pipelines, harnesses, runtimes, or `BaseAgent`.
- Do not add live-action gates, periodic trajectory critics, terminal acceptance gates, or offline/shadow review tools; those four items are execution-placement policies, not model-callable review topologies.
- Do not add a new public `AdversarialReview`, `ReviewStrategy`, registry, service, controller, factory, protocol, or settings abstraction.
- Do not bind the unfinished tools to `BaseAgent._bind_agent_tool_context()`.
- Do not import the unmerged `AdversarialAgent` module at runtime or accept an untyped placeholder agent dependency in constructors.
- Do not expose model-call arguments that can reduce developer-selected review rigor or change providers, models, permissions, reviewer tools, or cost limits.
- Do not auto-register these tools on agents or in `ToolsClient`.
- Do not add root-level `from vidbyte import ...` exports for the scaffold classes.
- Do not advertise the tools as production-ready or show successful execution examples.
- Do not add or modify tests, verification scripts, package dependencies, provider adapters, schemas, migrations, or external services.

---

## 3. Background & Context

The repository is a Python 3.11+ setuptools package with Pydantic 2 and `httpx` as its only declared runtime dependencies. `BaseTool` defines the native tool contract: `spec() -> ToolSpec` and `async execute(call: ToolCall) -> ToolResult`. `ToolExecutor` performs lookup, permission checks, required-parameter validation, execution, and exception normalization. Provider schemas are derived from `ToolSpec` through `ToolsFormatter`, and builtins are opt-in objects exported from `vidbyte.tools.builtins` rather than automatically registered.

Existing builtins establish two relevant patterns. `ReflexionTool` and `TrajectoryCheckpointTool` are ordinary `BaseTool` classes with explicit specs and safe `ToolResult` failures. `AttachMcpServerTool` is an agent-bound tool, but that binding works only because its concrete runtime dependency and attach contract already exist. `AgentTool` can fork and call one configured `BaseAgent`, but it is a zero-parameter delegation wrapper that serializes the current parent context; it does not accept an arbitrary candidate, distinguish review topologies, enforce adversarial isolation, or return review-specific metadata.

Open draft PR [#275](https://github.com/cerredz/Vidbyte-SDK/pull/275), `feat/adversarial-agent` at head commit `847b442`, is the upstream source of truth for the separately developed agent rather than the stale untracked local design copy. Read-only inspection of its actual `vidbyte/agents/adversarial.py` shows a runnerless `AdversarialAgent(BaseAgent)` facade with one worker prototype, one adversary prototype, and exact sequential worker -> N blind reviewers -> worker-revision rounds. `AdversarialSettings` contains `num_adversaries`, `adversarial_rounds`, `min_successful_adversaries`, `per_adversary_timeout`, `max_review_chars`, and `max_worker_output_chars`. The agent exposes `generate_reply()` and `fork()` but no reusable `review(candidate, ...)` method, topology selector, specialist/provider panels, debate, adjudication, candidate generation/selection, mutation, tool-backed verification, or evidence verification. Consequently, these scaffolds must not claim PR #275 can execute all sixteen topologies or route calls through its fixed workflow.

This design therefore treats the requested classes as coordination scaffolds. The public shape that can be stated truthfully now is the tool identity, model-facing subject schema, conservative permission, and unavailable result. The future `AdversarialAgent` integration remains contained behind one private `execute()` implementation seam. When the agent contract is finalized, a follow-up design must replace the scaffold behavior without changing the model-facing tool names or allowing the calling model to weaken developer policy.

The checkout is currently on `feat/context-minimal-fanout-trace` and contains many unrelated untracked user files, including the stale local adversarial-agent design. Phase 2 creates only this document and does not touch those files. The required branch stack is PR #275 (`feat/adversarial-agent`) -> `feat/adversarial-agent-settings` -> `feat/adversarial-review-tools`. After approval, the tools worktree must be created from the approved `feat/adversarial-agent-settings` branch, and its draft PR must target `feat/adversarial-agent-settings`, not `main`. The scaffold source nevertheless remains import-independent so `vidbyte.tools.builtins.adversarial` does not import or construct the upstream classes. Commit this design document before source changes.

---

## 4. Requirements

### Functional Requirements

1. Create `vidbyte/tools/builtins/adversarial.py` as the single implementation module for the scaffold family.
2. Define a private `_AdversarialLaunchTool(BaseTool)` helper in that module to centralize `ToolSpec` construction and unavailable execution behavior.
3. The private helper must not be exported and must not become a public review abstraction.
4. Define `LaunchSelfReflectionAgentTool` with tool name `launch_self_reflection_agent` and topology metadata `self_reflection`.
5. Define `LaunchIndependentCriticAgentTool` with tool name `launch_independent_critic_agent` and topology metadata `independent_critic`.
6. Define `LaunchParallelPanelTool` with tool name `launch_parallel_panel` and topology metadata `parallel_panel`.
7. Define `LaunchSpecialistPanelTool` with tool name `launch_specialist_panel` and topology metadata `specialist_panel`.
8. Define `LaunchCrossProviderPanelTool` with tool name `launch_cross_provider_panel` and topology metadata `cross_provider_panel`.
9. Define `LaunchCritiqueReviseAgentTool` with tool name `launch_critique_revise_agent` and topology metadata `critique_and_revise`.
10. Define `LaunchCritiqueAdjudicateReviseAgentTool` with tool name `launch_critique_adjudicate_revise_agent` and topology metadata `critique_adjudicate_and_revise`.
11. Define `LaunchProsecutorDefenderJudgeTool` with tool name `launch_prosecutor_defender_judge` and topology metadata `prosecutor_defender_judge`.
12. Define `LaunchAdversarialDebateTool` with tool name `launch_adversarial_debate` and topology metadata `adversarial_debate`.
13. Define `LaunchDelphiReviewTool` with tool name `launch_delphi_review` and topology metadata `delphi_review`.
14. Define `LaunchCandidateTournamentTool` with tool name `launch_candidate_tournament` and topology metadata `candidate_tournament`.
15. Define `LaunchAdversarialSelectorTool` with tool name `launch_adversarial_selector` and topology metadata `n_sample_adversarial_selector`.
16. Define `LaunchCounterexampleSearchTool` with tool name `launch_counterexample_search` and topology metadata `counterexample_search`.
17. Define `LaunchMutationReviewTool` with tool name `launch_mutation_review` and topology metadata `mutation_fuzz_review`.
18. Define `LaunchToolBackedVerifierTool` with tool name `launch_tool_backed_verifier` and topology metadata `tool_backed_verifier`.
19. Define `LaunchEvidenceVerifierTool` with tool name `launch_evidence_verifier` and topology metadata `evidence_verifier`.
20. Every public scaffold class must inherit from `_AdversarialLaunchTool`, and therefore be a `BaseTool` subclass usable by `Tools`, `ToolRegistry`, `ToolExecutor`, and agent-local tool catalogs.
21. Every public scaffold class must include a topology-specific `# TODO(adversarial-agent): ...` comment that names the missing launch/review behavior to implement after the agent contract lands.
22. Every `spec()` must return `ToolPermission.EXECUTE`.
23. Every `spec()` must include metadata with `category="adversarial_review"`, the fixed topology, `implementation_status="todo"`, and `requires="AdversarialAgent"`.
24. Every description must state that the tool is a scaffold and does not launch an agent yet.
25. Candidate-review tools must require `original_request` and `candidate`, and may accept optional `focus`.
26. Candidate-set comparison tools must require `original_request` and a `candidates` array with at least two entries, and may accept optional `focus`.
27. `LaunchAdversarialSelectorTool` must require `original_request` and may accept optional `focus`; candidate count remains developer-owned configuration rather than a model-call argument.
28. `LaunchMutationReviewTool` must require `original_request` and `candidate`, and may accept optional `mutation_inputs` and `focus`.
29. `LaunchToolBackedVerifierTool` must require `original_request` and `candidate`, and may accept optional `verification_requirements` and `focus`; child tool selection remains developer-owned configuration.
30. `LaunchEvidenceVerifierTool` must require `original_request`, `candidate`, and a nonempty `evidence` array, and may accept optional `focus`.
31. Input schemas for array fields must use `ToolSpec.input_schema` with explicit `items` and `minItems`, while the corresponding `ToolParameter` entries remain present so `BaseTool.validate_call()` can identify required fields.
32. No spec may expose `topology`, `strategy`, `num_adversaries`, `reviewer_count`, `adversarial_rounds`, `specialties`, `providers`, `models`, `threshold`, `min_successful`, `timeout`, `budget`, `tools`, or `permission` as model-call arguments.
33. Scaffold classes must remain zero-argument constructible and must not accept or store a placeholder agent, runner, provider, settings, or callback dependency.
34. Calling a scaffold through `ToolExecutor` with missing required arguments must continue to produce the executor's existing validation error before `execute()`.
35. Calling a scaffold with required arguments must return `ToolResult.error`; it must not raise `NotImplementedError` or another ordinary exception.
36. The unavailable result must use the concrete tool's stable name and explain that `AdversarialAgent` integration is unfinished.
37. The unavailable result metadata must include `error="adversarial_agent_unavailable"`, `category="adversarial_review"`, the fixed topology, and `implementation_status="todo"`.
38. Scaffold execution must ignore candidate bodies when building the error and metadata so user/model content is not echoed into logs or results.
39. Export all sixteen public classes from `vidbyte.tools.builtins.adversarial.__all__`.
40. Import and export all sixteen public classes from `vidbyte.tools.builtins.__init__`.
41. Do not export the private helper, schema constants, or definition constants.
42. Do not add root `vidbyte` exports or automatic registration.
43. Update `vidbyte/tools/README.md` to list the adversarial builtin family, all sixteen classes, their scaffold-only status, import path, and deterministic unavailable behavior.
44. Do not add or modify any test file or persistent verification script.
45. Live-action gating, periodic trajectory review, terminal acceptance gating, and offline/shadow review must remain out of this module because their defining behavior is when review is injected into execution, not which review agent topology a model-callable tool launches.
46. Future executable integration must be a follow-up change reviewed against the finalized topology-aware `AdversarialAgent` API; PR #275's fixed `generate_reply()` workflow alone is insufficient, and TODO removal is not authorized by approval of this scaffold design.

### Non-Functional Requirements

- **Performance:** `spec()` and `execute()` must be constant-time apart from constructing small fixed mappings and strings. Scaffold execution makes no network, model, filesystem, subprocess, or child-tool call.
- **Scalability:** N/A for scaffold execution. The final nested model-call/concurrency/token/cost limits are explicitly deferred until the `AdversarialAgent` integration contract exists.
- **Security:** Use `ToolPermission.EXECUTE`, do not echo supplied candidates/evidence in errors, do not accept model-controlled policy settings, and do not import or instantiate unfinished runtime dependencies.
- **Observability:** Stable `ToolSpec.metadata` and `ToolResult.metadata` must expose category, topology, implementation status, and the stable unavailable error code without raw review inputs.
- **Reliability:** Invocation must fail closed through `ToolResult.error`, keeping the parent agent loop alive and making unavailability explicit. Names, specs, and exports must be deterministic.
- **Compatibility:** Existing builtins and root exports remain unchanged. The new classes are additive, zero-argument constructible, and opt-in only.
- **Maintainability:** One private helper and a small number of immutable schema tuples/maps avoid duplicating the same TODO behavior sixteen times. Each public topology remains a distinct class and model-facing tool rather than a prompt variation hidden behind one strategy argument.
- **No-tests constraint:** No committed test or verification-script files are added or modified. Existing compile/import/provider-schema smoke commands are still required before a PR.

---

## 5. High-Level Design

Create one new builtin module containing a private `_AdversarialLaunchTool` and sixteen thin public subclasses. The private helper owns the shared `spec()` and `execute()` methods. Each subclass contributes only immutable class attributes for its stable tool name, topology, description, and one of several fixed input-schema families, plus a precise topology-specific TODO comment. This is private code reuse, not a new public SDK abstraction.

The tool schemas separate model-provided review subjects from developer-owned orchestration policy. A caller may supply the original request, candidate(s), evidence, mutation inputs, verification focus, or verification requirements as appropriate. The caller may not choose reviewer count, rounds, specialties, providers, models, permissions, tools, thresholds, or budgets. Once the agent class is ready, those settings must be injected by developer construction or another finalized SDK binding mechanism, not accepted from the calling model.

During this scaffold phase, the runtime path deliberately terminates before orchestration. `ToolExecutor` still performs normal lookup, authorization, and required-field validation. Valid calls enter the shared `execute()` implementation, which returns a bounded error with safe status metadata. No tool imports `AdversarialAgent`, no tool is bound to an owning agent, and no hidden fallback uses `BaseAgent` or `AgentTool` to approximate the requested topology.

```text
Developer explicitly attaches scaffold tool
                  |
                  v
        [agent-local Tools catalog]
                  |
          provider sees ToolSpec
                  |
          model calls launch_* tool
                  |
                  v
 [ToolExecutor: permission + required fields]
                  |
                  v
 [_AdversarialLaunchTool.execute()]
                  |
                  +--> TODO(adversarial-agent): no child launch yet
                  |
                  `--> ToolResult.error(
                         error="adversarial_agent_unavailable",
                         topology="...",
                         implementation_status="todo"
                       )

Future follow-up after the agent contract lands:
                  |
                  `--> fork isolated AdversarialAgent reviewer topology
                       --> bounded review result
                       --> recursion/cost/permission guards
```

Key decisions are: distinct tools instead of one generic strategy tool; one module instead of sixteen nearly empty files; `ToolResult.error` instead of raising; `EXECUTE` instead of `SAFE`; no root export; no placeholder dependency injection; and no attempt to make the sequential critique/revise agent draft impersonate unsupported topologies.

---

## 6. Detailed Design

### 6.1 Shared Scaffold Module And Private Helper

**File(s):** `vidbyte/tools/builtins/adversarial.py`
**Type:** New file

#### What it does

Defines immutable shared parameter/schema constants, a private `BaseTool` helper, and the shared unavailable execution result. The module follows repository conventions with a Context Protocol Header, postponed annotations, class-first tool design, one-line method signatures, and a short comment immediately below every method signature.

#### Interface / API

```python
_CANDIDATE_REVIEW_PARAMETERS: tuple[ToolParameter, ...]
_CANDIDATE_SET_PARAMETERS: tuple[ToolParameter, ...]
_REQUEST_PARAMETERS: tuple[ToolParameter, ...]
_MUTATION_PARAMETERS: tuple[ToolParameter, ...]
_TOOL_VERIFICATION_PARAMETERS: tuple[ToolParameter, ...]
_EVIDENCE_PARAMETERS: tuple[ToolParameter, ...]

class _AdversarialLaunchTool(BaseTool):
    tool_name: ClassVar[str]
    topology: ClassVar[str]
    summary: ClassVar[str]
    parameters: ClassVar[tuple[ToolParameter, ...]]
    input_schema: ClassVar[Mapping[str, Any]]

    def spec(self) -> ToolSpec:
        # Builds the fixed model-facing scaffold declaration for this topology.

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns a stable unavailable result until AdversarialAgent can launch this topology.
```

Every schema has `type="object"`, `additionalProperties=False`, explicit `required`, and explicit property types. The candidate-set array uses `items={"type": "string"}` and `minItems=2`; the evidence array uses the same item type and `minItems=1`. Optional arrays use the same item type without `minItems` unless an empty list would be meaningless.

`spec()` returns:

```python
ToolSpec(
    name=self.tool_name,
    description=(
        f"Scaffold only: {self.summary} "
        "This tool does not launch an agent yet; execution is reserved for the pending AdversarialAgent integration."
    ),
    parameters=self.parameters,
    permission=ToolPermission.EXECUTE,
    metadata={
        "category": "adversarial_review",
        "topology": self.topology,
        "implementation_status": "todo",
        "requires": "AdversarialAgent",
    },
    input_schema=self.input_schema,
)
```

`execute()` returns:

```python
ToolResult.error(
    self.name,
    (
        f"{self.name} is an adversarial review scaffold and cannot launch "
        "review agents until the AdversarialAgent review/topology API is available."
    ),
    metadata={
        "error": "adversarial_agent_unavailable",
        "category": "adversarial_review",
        "topology": self.topology,
        "implementation_status": "todo",
    },
)
```

#### Logic / Algorithm

1. A concrete subclass inherits `spec()` and `execute()` and supplies fixed class metadata.
2. `spec()` constructs a fresh `ToolSpec` using the subclass's fixed topology and schema.
3. `ToolExecutor` enforces `EXECUTE` permission and required-field presence through the existing pipeline.
4. `execute()` does not inspect or render `call.arguments`.
5. `execute()` returns the stable unavailable error and safe metadata.
6. A future follow-up replaces the body behind this private seam only after the agent's reusable review/topology contract is approved.

#### Edge Cases & Error Handling

- A missing required argument is handled by existing `BaseTool.validate_call()` when called through `ToolExecutor`.
- A direct `execute()` call with any argument shape still returns the same unavailable result.
- User-provided candidate/evidence text is never copied into the error output or metadata.
- The helper raises no ordinary exception for expected scaffold invocation.
- Provider schemas declare the meaningful minimum immediately: two candidates for a tournament and one evidence item for evidence verification. The executable follow-up must enforce the same bounds at runtime before launching children.
- The private helper is omitted from both module and package `__all__`.

### 6.2 Candidate Review And Interaction Launchers

**File(s):** `vidbyte/tools/builtins/adversarial.py`
**Type:** New file

#### What it does

Adds ten distinct tools that review one candidate through different agent interaction topologies. All use the candidate-review schema: required `original_request`, required `candidate`, and optional `focus`.

#### Interface / API

```python
class LaunchSelfReflectionAgentTool(_AdversarialLaunchTool): ...
class LaunchIndependentCriticAgentTool(_AdversarialLaunchTool): ...
class LaunchParallelPanelTool(_AdversarialLaunchTool): ...
class LaunchSpecialistPanelTool(_AdversarialLaunchTool): ...
class LaunchCrossProviderPanelTool(_AdversarialLaunchTool): ...
class LaunchCritiqueReviseAgentTool(_AdversarialLaunchTool): ...
class LaunchCritiqueAdjudicateReviseAgentTool(_AdversarialLaunchTool): ...
class LaunchProsecutorDefenderJudgeTool(_AdversarialLaunchTool): ...
class LaunchAdversarialDebateTool(_AdversarialLaunchTool): ...
class LaunchDelphiReviewTool(_AdversarialLaunchTool): ...
```

| Class | Tool name | Reserved behavior after integration |
|---|---|---|
| `LaunchSelfReflectionAgentTool` | `launch_self_reflection_agent` | Launch a fresh isolated fork of the producer identity to critique its candidate without recursively calling the active parent |
| `LaunchIndependentCriticAgentTool` | `launch_independent_critic_agent` | Launch one separate critic without producer scratch history |
| `LaunchParallelPanelTool` | `launch_parallel_panel` | Launch multiple independent critics against the same immutable candidate snapshot |
| `LaunchSpecialistPanelTool` | `launch_specialist_panel` | Launch developer-configured specialist critics, such as correctness, security, completeness, evidence, or performance |
| `LaunchCrossProviderPanelTool` | `launch_cross_provider_panel` | Launch critics across developer-configured provider/model families to reduce correlated failure |
| `LaunchCritiqueReviseAgentTool` | `launch_critique_revise_agent` | Send critic findings to an authoritative producer revision stage |
| `LaunchCritiqueAdjudicateReviseAgentTool` | `launch_critique_adjudicate_revise_agent` | Adjudicate invalid/duplicate findings before the producer revision stage |
| `LaunchProsecutorDefenderJudgeTool` | `launch_prosecutor_defender_judge` | Run attack, defense, and judgment roles over one candidate |
| `LaunchAdversarialDebateTool` | `launch_adversarial_debate` | Run bounded reviewer cross-examination before producing a verdict |
| `LaunchDelphiReviewTool` | `launch_delphi_review` | Run independent reviews, anonymized synthesis, and a second independent review round |

Each class includes its own `TODO(adversarial-agent)` comment. For example:

```python
class LaunchSpecialistPanelTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for a specialist adversarial panel."""

    # TODO(adversarial-agent): Launch isolated developer-configured specialists and synthesize bounded findings once the review API exists.
    tool_name = "launch_specialist_panel"
    topology = "specialist_panel"
    summary = "Review one candidate with a developer-configured panel of independent specialists."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA
```

#### Logic / Algorithm

1. Define each topology as a separate class with no public strategy parameter.
2. Reuse the common candidate-review fields.
3. Describe the reserved behavior precisely while stating that execution is unavailable.
4. Record the fixed topology in spec/result metadata.
5. Defer all counts, roles, specialties, providers, rounds, visibility, adjudication, and revision policy to developer configuration in the future agent integration.

#### Edge Cases & Error Handling

- Self-reflection must eventually use an isolated fork and a recursion-depth guard; it must not recursively call the active parent agent.
- Panels must eventually review one immutable candidate snapshot; reviewers must not see peer outputs unless the topology explicitly requires interaction.
- Cross-provider configuration is never accepted from the calling model.
- Revision tools must eventually preserve worker authority; reviewer text is untrusted input, not executable instruction.
- Debate and Delphi need bounded turn/round policies before their TODOs can be removed.
- During this scaffold phase, all ten classes return the same structured unavailable error with their own topology metadata.

### 6.3 Selection, Search, Mutation, And Verification Launchers

**File(s):** `vidbyte/tools/builtins/adversarial.py`
**Type:** New file

#### What it does

Adds six tools whose review subjects need schemas other than a single candidate alone.

#### Interface / API

```python
class LaunchCandidateTournamentTool(_AdversarialLaunchTool): ...
class LaunchAdversarialSelectorTool(_AdversarialLaunchTool): ...
class LaunchCounterexampleSearchTool(_AdversarialLaunchTool): ...
class LaunchMutationReviewTool(_AdversarialLaunchTool): ...
class LaunchToolBackedVerifierTool(_AdversarialLaunchTool): ...
class LaunchEvidenceVerifierTool(_AdversarialLaunchTool): ...
```

| Class | Tool name | Model-provided subject | Reserved behavior after integration |
|---|---|---|---|
| `LaunchCandidateTournamentTool` | `launch_candidate_tournament` | `original_request`, at least two `candidates`, optional `focus` | Compare supplied candidates pairwise until one survives |
| `LaunchAdversarialSelectorTool` | `launch_adversarial_selector` | `original_request`, optional `focus` | Generate a developer-configured number of diverse candidates, then select by counterexample resistance |
| `LaunchCounterexampleSearchTool` | `launch_counterexample_search` | `original_request`, `candidate`, optional `focus` | Search for concrete breaking inputs or situations |
| `LaunchMutationReviewTool` | `launch_mutation_review` | `original_request`, `candidate`, optional `mutation_inputs`, optional `focus` | Mechanically mutate configured subjects and retest the candidate |
| `LaunchToolBackedVerifierTool` | `launch_tool_backed_verifier` | `original_request`, `candidate`, optional `verification_requirements`, optional `focus` | Require reviewers to use developer-configured tests, schemas, lookup, calculators, or analysis tools |
| `LaunchEvidenceVerifierTool` | `launch_evidence_verifier` | `original_request`, `candidate`, nonempty `evidence`, optional `focus` | Map every material claim to supplied evidence or reject it |

#### Logic / Algorithm

1. Candidate tournament uses the candidate-set parameter/schema family.
2. N-sample selection uses the request-only parameter/schema family; the number and diversity of samples remain settings, not tool-call arguments.
3. Counterexample search uses the common candidate-review family.
4. Mutation/fuzz review adds an optional string array of explicit mutation subjects or inputs.
5. Tool-backed verification adds optional textual verification requirements but never accepts tool identities or permissions from the model.
6. Evidence verification requires a nonempty string array of supplied evidence.
7. Each class has a topology-specific TODO naming the missing generation, orchestration, mechanical verification, or evidence mapping step.

#### Edge Cases & Error Handling

- Candidate tournament requires at least two candidates in its provider schema; the executable follow-up must enforce the same bound before launching reviewers.
- N-sample generation must eventually use developer-owned candidate count, diversity, timeout, and budget settings.
- Mutation/fuzz execution must eventually distinguish safe mechanical transforms from external side effects and report every mutation attempted.
- Tool-backed verification must eventually derive permission from the strongest configured child capability and prevent adversarial launch tools from appearing in child catalogs.
- Evidence verifier must eventually reject unsupported claims without inventing evidence and must bound evidence forwarded to reviewers.
- During this scaffold phase, no array bodies are inspected or copied; every valid invocation returns the safe unavailable error.

### 6.4 Builtin Export Surface

**File(s):** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

#### What it does

Re-exports the sixteen scaffold classes from the established builtin namespace without adding root-level convenience exports or automatic registration.

#### Interface / API

```python
from vidbyte.tools.builtins import (
    LaunchAdversarialDebateTool,
    LaunchAdversarialSelectorTool,
    LaunchCandidateTournamentTool,
    LaunchCounterexampleSearchTool,
    LaunchCritiqueAdjudicateReviseAgentTool,
    LaunchCritiqueReviseAgentTool,
    LaunchCrossProviderPanelTool,
    LaunchDelphiReviewTool,
    LaunchEvidenceVerifierTool,
    LaunchIndependentCriticAgentTool,
    LaunchMutationReviewTool,
    LaunchParallelPanelTool,
    LaunchProsecutorDefenderJudgeTool,
    LaunchSelfReflectionAgentTool,
    LaunchSpecialistPanelTool,
    LaunchToolBackedVerifierTool,
)
```

#### Logic / Algorithm

1. Extend the module header's architecture summary with the adversarial scaffold category.
2. Import the sixteen public classes from `vidbyte.tools.builtins.adversarial`.
3. Add all sixteen names to `__all__` in deterministic alphabetical order.
4. Preserve all existing imports and exports exactly.
5. Do not change `vidbyte/__init__.py`, `vidbyte/tools/__init__.py`, `ToolsClient`, or registries.

#### Edge Cases & Error Handling

- Importing `vidbyte.tools.builtins` must not import the unfinished `AdversarialAgent` module or create an agent/provider resource.
- Existing imports remain backward compatible.
- Duplicate tool names are still rejected by the existing `Tools` catalog if a developer attaches multiple instances with the same name.

### 6.5 Tools Package Documentation

**File(s):** `vidbyte/tools/README.md`
**Type:** Modified

#### What it does

Documents the new builtin family as explicit scaffolding for a concurrent agent workstream, not as an executable feature.

#### Interface / API

```python
from vidbyte.tools.builtins import LaunchSelfReflectionAgentTool, LaunchSpecialistPanelTool

tools = [LaunchSelfReflectionAgentTool(), LaunchSpecialistPanelTool()]
```

The example is limited to construction/catalog usage and must immediately state that calls currently return `adversarial_agent_unavailable`; it must not show a successful review or recommend attaching the tools to production agents.

#### Logic / Algorithm

1. Add `adversarial` to the `builtins/` module inventory.
2. Add an "Adversarial review scaffolds" section listing the sixteen class/tool-name pairs.
3. Explain that the classes reserve schemas and names while `AdversarialAgent` is being finalized.
4. State that every call currently returns `ToolResult.error` and no child agent is launched.
5. State that executable integration, recursion guards, nested budgets, and child capability permissions are deferred.

#### Edge Cases & Error Handling

- Documentation must not claim any topology is currently operational.
- Documentation must not describe TODO metadata as a feature flag.
- Documentation must not imply these tools are automatically attached or exported from root `vidbyte`.

### 6.6 Existing Verification Without New Tests

**File(s):** N/A - no test or verification-script files are created or modified.
**Type:** N/A - command-only verification during implementation

#### What it does

Uses package compilation and ephemeral import/schema/execution smoke commands to verify the additive scaffolds without committing new tests.

#### Interface / API

```powershell
python -m compileall vidbyte
python -c "from vidbyte.tools import BaseTool; from vidbyte.tools.builtins import LaunchSelfReflectionAgentTool; assert issubclass(LaunchSelfReflectionAgentTool, BaseTool)"
python -c "import asyncio; from vidbyte.tools.builtins import LaunchSpecialistPanelTool; from vidbyte.tools import ToolCall; result = asyncio.run(LaunchSpecialistPanelTool().execute(ToolCall('launch_specialist_panel', {'original_request': 'r', 'candidate': 'c'}))); assert result.metadata['error'] == 'adversarial_agent_unavailable'"
python -c "from vidbyte.tools import Tools; from vidbyte.tools.builtins import LaunchCandidateTournamentTool, LaunchEvidenceVerifierTool; schemas = Tools([LaunchCandidateTournamentTool(), LaunchEvidenceVerifierTool()]).provider_schemas('openai'); assert len(schemas) == 2"
python -m build
```

An additional ephemeral command must instantiate all sixteen classes and assert that tool names are unique, permissions are `execute`, metadata status is `todo`, and `vidbyte.tools.builtins.__all__` contains every public class.

#### Logic / Algorithm

1. Compile the package.
2. Smoke-import the module and builtin re-exports.
3. Confirm every public class is a `BaseTool` subclass and zero-argument constructible.
4. Confirm names, topologies, permissions, metadata, required schema fields, and array schemas.
5. Execute representative scaffolds directly and through `ToolExecutor` to confirm validation and unavailable errors.
6. Format representative schemas for OpenAI, Anthropic, and Gemini through the existing formatter.
7. Build the source/wheel distributions and confirm the new module is packaged.

#### Edge Cases & Error Handling

- Any compilation, import, schema, execution, or package-build failure blocks PR creation.
- No smoke command may call an external provider or instantiate an agent.
- The no-tests workflow is an explicit limitation; command smoke checks do not replace future regression tests for executable orchestration.

---

## 7. Data Model Changes

### 7.1 Adversarial ToolSpec Metadata

**Change type:** New values in an existing in-memory mapping contract

```python
{
    "category": "adversarial_review",
    "topology": "<fixed_topology>",
    "implementation_status": "todo",
    "requires": "AdversarialAgent",
}
```

**Migration strategy:**

- Forward migration: additive metadata on new tool specs only.
- Rollback plan: remove the scaffold module and exports; no stored data requires cleanup.

### 7.2 Adversarial ToolResult Error Metadata

**Change type:** New values in an existing in-memory result mapping contract

```python
{
    "error": "adversarial_agent_unavailable",
    "category": "adversarial_review",
    "topology": "<fixed_topology>",
    "implementation_status": "todo",
}
```

**Migration strategy:**

- Forward migration: additive result metadata returned only by explicitly invoked new tools.
- Rollback plan: remove the scaffold module and exports.

### 7.3 Database, Session, And Persistent Schemas

**Change type:** N/A - no database, migration, session, checkpoint, wire protocol, or persistent storage schema changes.

**Migration strategy:**

- Forward migration: N/A.
- Rollback plan: N/A.

---

## 8. API Changes

### 8.1 Python Builtin Tool Imports

**Change type:** New

**Request:**

```python
from vidbyte.tools.builtins import LaunchSpecialistPanelTool

tool = LaunchSpecialistPanelTool()
spec = tool.spec()
```

**Response:**

```python
assert spec.name == "launch_specialist_panel"
assert spec.permission.value == "execute"
assert spec.metadata["topology"] == "specialist_panel"
assert spec.metadata["implementation_status"] == "todo"
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| `ToolResult.ERROR` | Required arguments are present but executable `AdversarialAgent` integration is unavailable |
| Existing validation error | A call through `ToolExecutor` omits a required parameter |
| Existing permission error | The permission policy denies an `EXECUTE` tool |

### 8.2 Model-Facing Tool Call Families

**Change type:** New

**Request:**

```json
{
  "original_request": "The task or question the candidate attempted",
  "candidate": "The proposed answer or artifact to review",
  "focus": "Optional review emphasis"
}
```

Candidate tournament uses `candidates: string[]`; N-sample selection omits `candidate`; mutation/fuzz may include `mutation_inputs: string[]`; tool-backed verification may include `verification_requirements: string`; evidence verification requires `evidence: string[]`.

**Response:**

```json
{
  "status": "error",
  "output": "<stable explanation that AdversarialAgent integration is unavailable>",
  "metadata": {
    "error": "adversarial_agent_unavailable",
    "category": "adversarial_review",
    "topology": "<fixed_topology>",
    "implementation_status": "todo"
  }
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| `ToolResult.ERROR` | Every otherwise valid scaffold call until the follow-up integration is implemented |
| Existing validation error | Missing required `original_request`, `candidate`, `candidates`, or `evidence`, depending on the topology |
| Existing permission error | Agent/tool policy denies `ToolPermission.EXECUTE` |

### 8.3 HTTP Or External Service Endpoints

**Change type:** N/A - no HTTP route, RPC method, webhook, MCP method, provider endpoint, or external service API changes.

---

## 9. File Change Manifest

Complete list of every file expected to change during implementation:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/adversarial-review-tools.md` | Approved source-of-truth design document for the scaffold family |
| CREATE | `vidbyte/tools/builtins/adversarial.py` | Sixteen public topology-specific `BaseTool` scaffolds and one private shared implementation helper |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Re-export all sixteen scaffold classes from the established builtin namespace |
| MODIFY | `vidbyte/tools/README.md` | Document names, import surface, TODO status, and unavailable execution semantics |

Files to create: **2**. Files to modify: **2**. Files to delete: **0**.

Explicit no-change areas:

- `vidbyte/agents/**`, including the separately developed `AdversarialAgent`
- `vidbyte/context/**`
- `vidbyte/middleware/**`
- `vidbyte/pipelines/**`
- `vidbyte/paradigms/**`
- `vidbyte/providers/**`
- `vidbyte/prompts/**`
- `vidbyte/tools/base.py`, `types.py`, `executor.py`, `catalog.py`, `client.py`, and `agent_tool.py`
- `vidbyte/tools/__init__.py`
- `vidbyte/__init__.py`
- `tests/**`
- `scripts/**`
- `pyproject.toml`
- `.github/workflows/publish.yml`

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python 3.11+ | `ClassVar`, immutable tuples/mappings, postponed annotations | Low; already required |
| `vidbyte.tools.base.BaseTool` | Current repository implementation | Native tool subclass contract | Low; stable internal SDK contract |
| `vidbyte.tools.types` | Current repository implementation | `ToolCall`, `ToolParameter`, `ToolPermission`, `ToolResult`, and `ToolSpec` | Low; established builtin pattern |
| `AdversarialAgent` from PR #275 | Open draft `feat/adversarial-agent` at `847b442`; not imported or called in this change | Upstream fixed sequential critique/revise facade and eventual foundation for a topology-aware review contract | High integration uncertainty; the implemented API exposes `generate_reply()` but no generic external-candidate/topology launcher |
| Model/provider services | N/A in this change | No calls are made by scaffolds | None during scaffold phase; future cost/reliability risks require a follow-up design |

No new package dependency, credential path, external endpoint, runtime service, or deployment dependency is introduced.

---

## 11. Rollout & Deployment

- This is an additive Python package change with no database migration, feature flag, service deployment, or automatic agent behavior.
- The classes are opt-in and inert except when explicitly attached and called.
- After explicit design approval, create an isolated `feat/adversarial-review-tools` worktree from the approved `feat/adversarial-agent-settings` branch; do not implement in the current dirty checkout or base the tools branch directly on PR #275.
- Commit this design document first, before any source or README change.
- Implement in this order: shared schema constants/private helper; sixteen public classes and TODOs; module/package exports; README; command-only verification; structured self-critique/refinement.
- Run compile, import, provider-schema, representative unavailable-execution, and package-build smoke checks before pushing.
- Open a draft PR targeting `feat/adversarial-agent-settings` with the design document as its body, preserving the stack `feat/adversarial-agent` -> `feat/adversarial-agent-settings` -> `feat/adversarial-review-tools`.
- The scaffolds must remain visibly unavailable until a separate approved follow-up integrates the finalized `AdversarialAgent` review/topology contract.
- If the agent workstream lands first and changes the dependency shape, update this design and obtain renewed approval before implementing any executable behavior; the current approval covers scaffolds only.
- Rollback is a normal revert removing `vidbyte/tools/builtins/adversarial.py`, its builtin imports/exports, and the README section. No user data, sessions, migrations, or external resources require cleanup.

---

## 12. Open Questions

Approval of this document confirms the following scaffold choices: sixteen distinct public classes; fixed model-facing names; one private helper in one module; `ToolPermission.EXECUTE`; zero-argument construction; builtin-only exports; explicit TODO descriptions/metadata; and deterministic `ToolResult.error` execution.

The following questions are intentionally deferred to the executable-integration follow-up and do not block creating the scaffolds:

- [ ] What exact reusable API will the finalized `AdversarialAgent` expose for reviewing an externally supplied candidate without first producing a new candidate itself?
- [ ] Will topology selection be represented by methods, validated settings/presets, or private dispatch inside `AdversarialAgent`?
- [ ] How will each finished tool receive developer-owned agent prototypes/settings while preserving the scaffold's zero-argument construction path: optional constructor injection, an agent binding hook, or a separate configured factory?
- [ ] Which of the sixteen topologies will the first executable `AdversarialAgent` version actually support, and should unsupported ones continue returning topology-specific unavailable errors?
- [ ] What structured review result contract will tools return in `ToolResult.metadata`, and what character/token bounds will apply to output and findings?
- [ ] How will nested reviewer model calls count against the parent run's call, token, time, concurrency, and cost budgets?
- [ ] How will child catalogs strip all adversarial launch tools and enforce a review-depth guard to prevent recursive launches?
- [ ] How will the finished tool permission reflect the strongest configured child capability when tool-backed verifiers can use read, write, or execute tools?
- [ ] Which topologies allow peer visibility, which require blind immutable snapshots, and how are anonymization and adjudication represented?
- [ ] Should successful executable tools retain these sixteen public classes or later consolidate some aliases after real usage data exists?

---

## 13. Alternatives Considered

### Alternative 1: One Generic `LaunchAdversarialReviewTool`

- What: Add one tool with a model-provided `strategy` or `topology` argument.
- Why rejected: These are genuinely different orchestration graphs, schemas, cost profiles, and trust boundaries. A model-controlled switch also lets the model choose a cheaper/weaker review path and contradicts the request for tools such as "launch a self reflection agent" and "launch a specialist panel."

### Alternative 2: Add A Public Review Strategy Hierarchy

- What: Introduce public `AdversarialReviewStrategy`, topology subclasses, a registry, and a service/controller layer for the tools.
- Why rejected: The user explicitly does not want a new repository-wide abstraction. The tools only need public `BaseTool` identities; shared scaffold mechanics stay private and eventual orchestration belongs in `AdversarialAgent`.

### Alternative 3: Wrap Agents With Existing `AgentTool`

- What: Preconfigure sixteen agents and expose each through `BaseAgent.as_tool()` / `AgentTool`.
- Why rejected: `AgentTool` has a zero-parameter, current-context delegation contract. It cannot express candidate sets, evidence, mutation inputs, or topology-specific structured results, and it provides no review recursion/cost/isolation policy.

### Alternative 4: Approximate Every Topology With `BaseAgent` Now

- What: Use prompt templates and generic `BaseAgent` forks to make the tools appear executable before `AdversarialAgent` is ready.
- Why rejected: Panels, adjudication, debate, Delphi, selection, mutation, and tool-backed verification require different control flow. Prompt-only approximations would mislabel behavior, duplicate the agent workstream, and create unsafe recursion/permission/accounting gaps.

### Alternative 5: Raise `NotImplementedError`

- What: Leave `execute()` abstract-like and raise when a model calls a scaffold.
- Why rejected: Direct calls would escape the ordinary `ToolResult` contract, while `ToolExecutor` would convert them into a generic execution error that loses the stable topology/status metadata. A deterministic `ToolResult.error` is explicit and keeps the parent loop healthy.

### Alternative 6: Mark Scaffold Tools `SAFE`

- What: Match `AgentTool` and current context-writing tools by declaring `ToolPermission.SAFE` while execution is inert.
- Why rejected: The stable spec should describe the intended authority boundary. Finished launchers will initiate model/provider work and may invoke configured verifier tools, so `EXECUTE` is the conservative permission and avoids a later silent permission escalation.

### Alternative 7: Create Sixteen Separate Source Files

- What: Follow a strict one-file-per-tool layout under a new adversarial package.
- Why rejected: During the scaffold phase every class shares one tiny spec/error implementation. Sixteen files and a package hierarchy would create structure without behavior, whereas existing builtin families already group related classes by domain/provider.

### Alternative 8: Export Every Scaffold From Root `vidbyte`

- What: Add all sixteen classes to `vidbyte/__init__.py` for the shortest imports.
- Why rejected: Root exports are reserved for especially common contracts and selected builtins. Adding sixteen unfinished classes would crowd the root namespace and imply broader stability/readiness than the scaffold provides.

### Alternative 9: Wait Until `AdversarialAgent` Is Complete

- What: Add no tools until the agent workstream finalizes every topology.
- Why rejected: The user explicitly wants TODO scaffolds now so names, schemas, export locations, and integration seams are visible to parallel work. The design mitigates the risk by failing closed and labeling every surface as unfinished.
