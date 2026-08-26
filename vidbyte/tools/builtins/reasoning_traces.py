"""FILE: vidbyte/tools/builtins/reasoning_traces.py

PURPOSE:
    Provides 182 model-callable reasoning trace tools derived from the complete
    default reasoning families in the Vidbyte Skills repository. The module owns
    source-grounded strategy definitions, long example-free model descriptions,
    eight-field validation, public generated tool classes, and context upserts.
    It records public reasoning telemetry only; it never executes a framework,
    calls a provider, or treats model-authored claims as verified truth.
ROLE IN CODEBASE:
    Agents import generated classes from vidbyte.tools.builtins and pass an
    injected ContextManager into a selected class. This module calls
    vidbyte.tools.base, vidbyte.tools.types, and
    vidbyte.context.primitives.reasoning_traces, while ContextManager owns the
    registry, placement, and freezing semantics after the upsert.
ARCHITECTURE NOTE:
    A frozen definition catalog drives generated public subclasses of one shared
    class-first execution implementation. This preserves explicit provider tool
    schemas and ComponentRegistry discovery without copying 182 implementations.
    The schema and description contract follows SDK PR #361 review guidance and
    docs/design/reasoning-deep-observability-tools.md.
FUNCTION INVENTORY:
    ReasoningTraceDefinition: immutable source skill identity and purpose value.
    _ReasoningTraceTool.spec() -> ToolSpec: builds the strategy-specific schema.
    _ReasoningTraceTool.execute(ToolCall) -> ToolResult: validates, upserts, and
    returns one bounded public trace. ReasoningTraceCatalog.definitions() and
    tool_class() expose the fixed catalog and lookup; all failures are returned
    as ToolResult errors except invalid catalog construction, which raises ValueError.
COMMON MODIFICATION PATTERNS:
    Add or revise a strategy by changing the catalog definition and updating the
    design inventory, then run the description/parameter smoke command before CI.
    Change the shared contract only in the parameter templates, primitive, and
    design doc together. Never hand-edit generated class names separately from
    the catalog source.
WHAT NOT TO DO IN THIS FILE:
    1. Do not execute the reasoning framework; source skill files remain the workflow source.
    2. Do not add context placement or compaction; vidbyte/context/manager.py owns those concerns.
    3. Do not add network calls, provider adapters, pricing, or hidden scratchpad persistence.
    4. Do not weaken the eight-field contract to make a shallow tool call convenient.
KNOWN EDGE CASES:
    Class names are generated from hyphenated slugs and must remain collision-free.
    Primitive IDs use a per-tool readable counter and consult the manager before
    reuse. Confidence is rejected when malformed, non-finite, or outside the
    inclusive zero-to-one range; field text is bounded only at primitive rendering.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/reasoning-deep-observability-tools.md
    https://github.com/cerredz/Vidbyte-SDK/pull/361
TEST FILES:
    Existing tests/test_tool_core.py, tests/test_tools_catalog.py, and the source
    and package stages in scripts/run_ci.py cover the shared tool contracts. The
    no-tests design adds no feature test file; focused smoke checks are run manually.
CONCURRENCY MODEL:
    Tool instances hold a local sequence counter and share the injected manager.
    Manager registry mutation is caller-owned; IDs are checked immediately before
    upsert but this module does not add a lock around an external manager.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.context.manager import ContextManager


@dataclass(frozen=True, slots=True)
class ReasoningTraceDefinition:
    """Describe one source reasoning skill represented by a generated tool."""

    skill_name: str
    purpose: str


_REASONING_TRACE_DEFINITION_DATA = (
    ("a3-problem-solving-trace", "A3 single-sheet problem analysis, root cause, countermeasure, check, and follow-up."),
    ("ab-testing-trace", "Compare variants using metrics, sampling rules, and decision thresholds."),
    ("abductive-trace", "Generate and compare explanations to identify the best-supported account."),
    ("adaptive-reasoning-trace", "Select and adjust the reasoning strategy to fit the problem."),
    ("affect-heuristic-trace", "Use emotional response to assess perceived risks and benefits."),
    ("after-action-review-trace", "Compare expectations with outcomes and derive improvements."),
    ("alternative-futures-trace", "Build and compare multiple futures from key uncertainties."),
    ("analogical-trace", "Transfer insight from a source case to a target case."),
    ("analysis-of-competing-hypotheses-trace", "Test competing explanations and prefer the one with least conflicting evidence."),
    ("analytic-hierarchy-process-trace", "Rank alternatives through hierarchical criteria and pairwise comparisons."),
    ("ansoff-matrix-trace", "Analyze growth options across existing or new products and markets."),
    ("argument-map-trace", "Map claims, supports, objections, and rebuttals."),
    ("assumption-ladder-trace", "Inspect the climb from observations to interpretations, beliefs, and actions."),
    ("backward-chaining-trace", "Work backward from a goal to required premises or actions."),
    ("balanced-scorecard-trace", "Translate strategy across financial, customer, process, and learning perspectives."),
    ("base-rate-trace", "Start forecasts from reference frequencies before applying case-specific evidence."),
    ("bayesian-trace", "Update priors as evidence changes confidence."),
    ("bcg-matrix-trace", "Classify business units by growth and relative market share."),
    ("biomimicry-trace", "Adapt useful patterns from biological systems to design problems."),
    ("blue-ocean-strategy-trace", "Create uncontested market space through value innovation."),
    ("bottleneck-trace", "Locate the constraint governing overall throughput."),
    ("bowtie-risk-trace", "Connect threats, preventive controls, events, recovery controls, and consequences."),
    ("business-model-canvas-trace", "Map the nine building blocks of a business model."),
    ("causal-loop-trace", "Represent reinforcing and balancing feedback loops."),
    ("causal-trace", "Separate causes from correlations and test intervention mechanisms."),
    ("comparative-case-trace", "Compare cases to isolate similarities, differences, and transfer limits."),
    ("concept-mapping-trace", "Organize knowledge as a network of linked concepts."),
    ("cone-of-plausibility-trace", "Separate probable, plausible, and possible futures."),
    ("constraint-removal-trace", "Temporarily remove assumed constraints to discover options."),
    ("constraint-satisfaction-trace", "Search constraints, domains, conflicts, and feasible assignments."),
    ("correlation-causation-trace", "Distinguish association from mechanism, sequence, and intervention evidence."),
    ("cost-benefit-trace", "Compare costs, benefits, timing, risk, and distribution."),
    ("counterfactual-trace", "Test what would change under altered conditions."),
    ("customer-journey-mapping-trace", "Map customer actions, thoughts, emotions, and pain points across touchpoints."),
    ("cynefin-trace", "Classify a situation as simple, complicated, complex, chaotic, or disordered."),
    ("data-quality-audit-trace", "Audit completeness, accuracy, freshness, lineage, and measurement bias."),
    ("deception-detection-trace", "Test how evidence could be manipulated, omitted, or misread."),
    ("decision-matrix-trace", "Score alternatives against weighted criteria."),
    ("decision-tree-trace", "Represent choices, uncertain events, probabilities, and outcomes as branches."),
    ("deductive-trace", "Derive necessary conclusions from stated premises."),
    ("default-heuristic-trace", "Accept a preset option rather than actively comparing alternatives."),
    ("defeasible-reasoning-trace", "Make provisional conclusions that can be withdrawn."),
    ("delphi-method-trace", "Iteratively aggregate anonymous expert forecasts."),
    ("dependency-mapping-trace", "Map prerequisites, blockers, interfaces, and sequencing."),
    ("design-thinking-trace", "Empathize, define, ideate, prototype, and test."),
    ("devils-advocacy-trace", "Argue against the favored answer to expose weaknesses."),
    ("dialectical-trace", "Develop thesis, antithesis, and synthesis."),
    ("dmaic-trace", "Apply Define, Measure, Analyze, Improve, and Control."),
    ("double-diamond-trace", "Diverge and converge on the problem, then on the solution."),
    ("double-loop-learning-trace", "Question governing assumptions, values, and variables behind actions."),
    ("elimination-by-aspects-trace", "Eliminate alternatives one criterion at a time."),
    ("empathy-mapping-trace", "Capture what users say, think, do, and feel."),
    ("error-analysis-trace", "Categorize failures, estimate frequency, and prioritize fixes."),
    ("ethical-matrix-trace", "Compare stakeholder impacts against wellbeing, autonomy, fairness, and responsibility."),
    ("ethnographic-reasoning-trace", "Interpret practices, language, setting, and participant perspective."),
    ("event-tree-trace", "Branch from an initiating event through controls and outcomes."),
    ("evidence-triangulation-trace", "Combine independent evidence streams and test convergence."),
    ("expected-value-trace", "Combine payoffs with probabilities."),
    ("experimental-design-trace", "Define variables, controls, measures, randomization, and validity risks."),
    ("fairness-analysis-trace", "Analyze equity across affected groups and outcomes."),
    ("familiarity-heuristic-trace", "Infer value or risk from familiarity."),
    ("fast-and-frugal-trees-trace", "Classify quickly using a minimal-cue tree."),
    ("fault-tree-trace", "Analyze failures through causal fault trees."),
    ("feedback-loop-trace", "Analyze how system outputs feed back into behavior."),
    ("fermi-estimation-trace", "Decompose rough quantitative questions into tractable estimates."),
    ("first-principles-trace", "Reduce a problem to foundational facts and constraints."),
    ("fishbone-trace", "Categorize and investigate possible root causes."),
    ("five-whys-trace", "Repeatedly ask why to reach a deeper cause."),
    ("fluency-heuristic-trace", "Treat ease of processing as a cue for value or truth."),
    ("fmea-trace", "Identify component failure modes and assess effects."),
    ("force-field-trace", "Identify driving and restraining forces."),
    ("forward-chaining-trace", "Apply data-driven inference from facts toward conclusions."),
    ("fuzzy-logic-trace", "Reason with graded rather than binary truth."),
    ("game-theory-trace", "Model players, payoffs, moves, information, and equilibria."),
    ("gemba-walk-trace", "Observe work where it actually happens and ask why."),
    ("hazop-trace", "Examine deviations from design intent for hazards."),
    ("hermeneutic-trace", "Refine interpretation by moving between parts and whole."),
    ("historical-reasoning-trace", "Analyze chronology, context, sources, causation, and contingency."),
    ("horizon-scanning-trace", "Identify weak signals, emerging patterns, and discontinuities."),
    ("hypothesis-testing-trace", "State testable claims and define disconfirming evidence."),
    ("iceberg-model-trace", "Move from events to patterns, structures, and mental models."),
    ("incentive-analysis-trace", "Explain behavior through rewards, penalties, constraints, and information."),
    ("indicators-signposts-trace", "Define signals that confirm, weaken, or redirect an assessment."),
    ("inductive-trace", "Generalize patterns from observations while marking failure conditions."),
    ("influence-diagram-trace", "Map decisions, uncertainties, objectives, and dependencies."),
    ("inversion-trace", "Ask what would guarantee failure, then avoid it."),
    ("issue-tree-trace", "Branch a central question into subissues and roll findings upward."),
    ("jobs-to-be-done-trace", "Identify functional, social, and emotional customer jobs."),
    ("key-assumptions-check-trace", "Surface critical assumptions and test conclusion fragility."),
    ("kolb-learning-cycle-trace", "Cycle through experience, reflection, abstraction, and experimentation."),
    ("lateral-thinking-trace", "Break habitual frames and generate indirect solutions."),
    ("legal-reasoning-trace", "Identify governing rules, apply facts, and distinguish contrary authorities."),
    ("leverage-points-trace", "Find small interventions that materially shift system behavior."),
    ("linchpin-analysis-trace", "Test assumptions or evidence holding a conclusion together."),
    ("mece-decomposition-trace", "Split a problem into mutually exclusive, collectively exhaustive parts."),
    ("mental-simulation-trace", "Envision future events step by step to assess feasibility and obstacles."),
    ("metacognitive-audit-trace", "Audit reasoning for bias, gaps, overconfidence, and poor framing."),
    ("mind-map-trace", "Explore associations radiating from a central idea."),
    ("minimax-trace", "Choose by comparing worst-case outcomes."),
    ("minto-pyramid-trace", "Organize communication as conclusion first, supported by grouped reasoning."),
    ("modal-reasoning-trace", "Reason about possibility, necessity, and modal alternatives."),
    ("morphological-analysis-trace", "Recombine alternatives across problem dimensions."),
    ("multi-attribute-utility-trace", "Quantify preferences across conflicting objectives."),
    ("naive-diversification-trace", "Spread selections evenly across available options."),
    ("narrative-reasoning-trace", "Trace actors, motives, conflicts, turning points, and causal arcs."),
    ("nine-windows-trace", "Examine past, present, and future across subsystem, system, and supersystem."),
    ("nonmonotonic-reasoning-trace", "Allow new information to invalidate earlier conclusions."),
    ("nth-order-effects-trace", "Extend consequence chains while pruning speculation."),
    ("null-hypothesis-trace", "Test whether evidence justifies rejecting no effect or no difference."),
    ("occams-razor-trace", "Prefer the simplest explanation retaining explanatory power."),
    ("ooda-loop-trace", "Observe, orient, decide, and act while updating."),
    ("ooda-red-team-trace", "Run OODA from an opposing actor's perspective."),
    ("opportunity-cost-trace", "Make the next-best alternative explicit."),
    ("outside-view-trace", "Calibrate a forecast against comparable cases."),
    ("pareto-principle-trace", "Focus on the vital few causes producing most effects."),
    ("pdca-cycle-trace", "Iterate through Plan, Do, Check, and Act."),
    ("peak-end-rule-trace", "Evaluate experiences mainly by peak and ending."),
    ("pestle-trace", "Scan political, economic, social, technological, legal, and environmental forces."),
    ("phenomenology-trace", "Bracket assumptions and examine lived experience."),
    ("policy-analysis-trace", "Compare policy goals, feasibility, effects, equity, and implementation risk."),
    ("porters-five-forces-trace", "Assess rivalry, entrants, substitutes, suppliers, and buyers."),
    ("postmortem-trace", "Reconstruct failure, separate symptoms from causes, and extract safeguards."),
    ("pragmatism-trace", "Evaluate ideas by practical consequences and usefulness."),
    ("precautionary-principle-trace", "Recommend preventive action despite incomplete certainty about harm."),
    ("predicate-logic-trace", "Translate claims into predicates, quantifiers, and relations."),
    ("premortem-trace", "Assume failure and convert likely causes into mitigations."),
    ("probabilistic-trace", "Represent uncertainty and compare likelihoods."),
    ("proof-by-cases-trace", "Prove a conclusion separately across exhaustive cases."),
    ("proof-by-contradiction-trace", "Assume the opposite and derive inconsistency."),
    ("propositional-logic-trace", "Test propositions, implications, conjunctions, disjunctions, and negations."),
    ("provocation-trace", "Use deliberate unreasonable statements to generate insight."),
    ("quasi-experimental-trace", "Use natural comparisons while documenting validity threats."),
    ("random-stimulus-trace", "Introduce an unrelated cue to force useful connections."),
    ("randomized-control-trial-trace", "Compare treatment and control while guarding against confounds."),
    ("recognition-heuristic-trace", "Infer greater value from recognition of one option."),
    ("red-team-trace", "Simulate an opponent to stress-test plans and claims."),
    ("reference-class-forecasting-trace", "Build an empirical baseline from comparable cases."),
    ("reframing-trace", "Shift frame, owner, time horizon, or success definition."),
    ("regression-reasoning-trace", "Model relationships while checking controls, residuals, and limits."),
    ("regret-minimization-trace", "Choose by reducing future remorse or cost of being wrong."),
    ("reverse-brainstorming-trace", "Ask how to worsen an outcome, then reverse the causes."),
    ("root-cause-trace", "Distinguish proximate symptoms from durable causes."),
    ("rubber-duck-debugging-trace", "Explain the problem aloud step by step to expose flaws."),
    ("satisficing-trace", "Choose the first option meeting minimum requirements."),
    ("scamper-trace", "Modify an existing idea through structured transformation prompts."),
    ("scarcity-heuristic-trace", "Assign greater value to perceived limited opportunities."),
    ("scenario-planning-trace", "Analyze futures under major uncertainties."),
    ("scientific-method-trace", "Form hypotheses, test them, and update from observations."),
    ("second-order-effects-trace", "Extend analysis to downstream consequences."),
    ("sensitivity-analysis-trace", "Test how conclusions change when inputs vary."),
    ("simulation-heuristic-trace", "Mentally simulate events to judge likelihood or emotional impact."),
    ("six-thinking-hats-trace", "Analyze deliberately through six parallel thinking lenses."),
    ("social-proof-trace", "Infer appropriate behavior from what others do."),
    ("socratic-questioning-trace", "Drive inquiry through successive clarifying questions."),
    ("spatial-reasoning-trace", "Reason about geometry, layout, and spatial relationships."),
    ("speed-accuracy-tradeoff-trace", "Balance decision speed against required accuracy."),
    ("spider-mapping-trace", "Radiate related ideas outward from a central concept."),
    ("stakeholder-analysis-trace", "Analyze stakeholder interests, influence, and relationships."),
    ("steelman-trace", "Strengthen an opposing argument before evaluating it."),
    ("stock-and-flow-trace", "Model accumulations, rates, delays, and system dynamics."),
    ("storyboarding-trace", "Sequence visual frames to explore a narrative or user experience."),
    ("swot-trace", "Analyze strengths, weaknesses, opportunities, and threats."),
    ("syllogistic-trace", "Test categorical syllogisms and their validity."),
    ("synectics-trace", "Generate solutions through structured creative analogy."),
    ("systematic-inventive-thinking-trace", "Apply five closed-world creative thinking patterns."),
    ("systems-thinking-trace", "Analyze boundaries, components, feedback, delays, and leverage."),
    ("take-the-best-trace", "Search cues by validity and stop at the first discriminator."),
    ("tallying-trace", "Count favorable cues and select the alternative with most positives."),
    ("temporal-reasoning-trace", "Order events, durations, deadlines, lags, and temporal constraints."),
    ("theory-of-constraints-trace", "Identify, exploit, subordinate to, and reassess the system constraint."),
    ("tradeoff-matrix-trace", "Score options while exposing their compromises."),
    ("trial-and-error-trace", "Try candidate solutions and learn from failures."),
    ("triz-trace", "Resolve contradictions using inventive principles."),
    ("uncertainty-quantification-trace", "Express confidence ranges, uncertainty sources, and narrowing evidence."),
    ("utility-trace", "Weight preferences and compare options by expected usefulness."),
    ("value-chain-analysis-trace", "Examine activities as sources of value and advantage."),
    ("value-focused-thinking-trace", "Derive alternatives from fundamental values."),
    ("value-stream-mapping-trace", "Map material and information flow to identify waste."),
    ("values-tradeoff-trace", "Make competing values and conditional priorities explicit."),
    ("vrio-framework-trace", "Evaluate resources by Value, Rarity, Imitability, and Organization."),
    ("what-if-analysis-trace", "Vary one important condition and track the result."),
    ("why-because-analysis-trace", "Trace necessary and sufficient causes through counterfactual tests."),
)

_PARAMETER_ORDER = (
    "question",
    "strategy_application",
    "evidence",
    "assumptions",
    "alternatives",
    "disconfirming_signals",
    "confidence",
    "next_action",
)
_PARAMETER_TYPES = {name: "number" if name == "confidence" else "string" for name in _PARAMETER_ORDER}
_MIN_CONFIDENCE = 0.0
_MAX_CONFIDENCE = 1.0


_PARAMETER_TEMPLATES = {
    "question": (
        "This field states the precise question or problem that the strategy is being used to examine. "
        "It keeps the trace anchored to a decision target instead of allowing the record to become an untethered narrative. "
        "It lets later readers compare the reasoning move with the need that motivated it. "
        "Keep the scope stable enough that the conclusion and next action can be judged against the same question."
    ),
    "strategy_application": (
        "This field records how the selected reasoning strategy was applied to the current question. "
        "It should identify the operative reasoning move, the stage reached, and the structure used to organize the work. "
        "It distinguishes actual application of the named strategy from a generic statement that reasoning occurred. "
        "It gives observers enough process detail to assess whether the strategy was used deliberately and completely."
    ),
    "evidence": (
        "This field records the observations, sources, calculations, or tool results supporting the current trace. "
        "It separates what was encountered from what the agent inferred from those observations. "
        "It allows a later reviewer to assess provenance, freshness, coverage, and relevance without guessing at the foundation. "
        "Include the material that materially changes the conclusion rather than treating confidence as a substitute for support."
    ),
    "assumptions": (
        "This field lists the premises the reasoning currently treats as true without complete verification. "
        "It makes hidden dependencies visible before they silently determine the conclusion or next action. "
        "It allows later iterations to test, downgrade, replace, or explicitly accept each load-bearing premise. "
        "State assumptions separately from evidence because an unverified premise is not the same thing as an observation."
    ),
    "alternatives": (
        "This field records the materially different interpretations, explanations, options, or paths considered beside the current line. "
        "It prevents the trace from presenting a single path as inevitable when other plausible paths were available. "
        "It lets observers inspect what was ruled out, what remains open, and whether comparison was proportionate to the stakes. "
        "Include the decision-relevant distinction for each alternative rather than padding the record with nominal variations."
    ),
    "disconfirming_signals": (
        "This field names observations or conditions that would weaken, falsify, or redirect the current reasoning. "
        "It prevents the trace from becoming a closed argument that can only collect confirming information. "
        "It gives the next iteration a concrete trigger for updating confidence and changing course. "
        "Treat disconfirmation as a normal control on reasoning quality rather than as evidence that the trace failed."
    ),
    "confidence": (
        "This field gives the current calibrated confidence in the trace's working conclusion or direction. "
        "It must be a finite number from zero through one so changes can be compared across checkpoints and strategies. "
        "It communicates uncertainty separately from evidence quality, consequence, and action urgency. "
        "Use the value to expose uncertainty honestly rather than to make an unsupported conclusion appear precise."
    ),
    "next_action": (
        "This field states the next observable action that will advance, test, narrow, or safely pause the reasoning. "
        "It turns the trace from a retrospective description into an operational checkpoint for the following iteration. "
        "It lets monitors compare declared direction with subsequent tool activity and outcome evidence. "
        "Make the action specific enough that its result can update the assumptions, alternatives, or confidence recorded here."
    ),
}


class _ReasoningTraceTool(BaseTool):
    """Shared execution path inherited by every generated reasoning trace tool."""

    definition: ClassVar[ReasoningTraceDefinition]

    def __init__(self, context_manager: ContextManager) -> None:
        # Retains the manager and a local sequence used to create readable event IDs.
        self._manager = context_manager
        self._counter = 0

    def spec(self) -> ToolSpec:
        # Builds the strategy-specific model contract from the fixed definition.
        return ToolSpec(
            name=self.definition.skill_name,
            description=ReasoningTraceCatalog.tool_description(self.definition),
            parameters=ReasoningTraceCatalog.parameters(self.definition),
            permission=ToolPermission.SAFE,
            binds_to_primitive="reasoning_trace",
            metadata={"source_skill": self.definition.skill_name},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates one public trace, writes its primitive, and returns observability metadata.
        args = dict(call.arguments)
        validation_error = self._validate_text_fields(args)
        if validation_error:
            return ToolResult.error(call.tool_name, validation_error)
        confidence = self._parse_confidence(args.get("confidence"))
        if confidence is None:
            return ToolResult.error(call.tool_name, "Field 'confidence' must be a finite number between 0.0 and 1.0.")
        item = self._build_item(args, confidence)
        return await self._record_item(item, call)

    def _validate_text_fields(self, args: Mapping[str, Any]) -> str | None:
        # Returns the first missing or blank text field so the model can repair the call.
        for field_name in _PARAMETER_ORDER:
            if field_name == "confidence":
                continue
            value = args.get(field_name)
            if value is None or not str(value).strip():
                return f"Missing or empty required field: '{field_name}'."
        return None

    def _parse_confidence(self, value: Any) -> float | None:
        # Converts confidence to a finite inclusive-range float without silent clamping.
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed) or not _MIN_CONFIDENCE <= parsed <= _MAX_CONFIDENCE:
            return None
        return parsed

    def _build_item(self, args: Mapping[str, Any], confidence: float) -> Any:
        # Constructs the immutable primitive from the validated public fields.
        from vidbyte.context.primitives import ReasoningTraceContextItem

        self._counter += 1
        return ReasoningTraceContextItem(
            primitive_id=self._next_primitive_id(),
            strategy_name=self.definition.skill_name,
            strategy_purpose=self.definition.purpose,
            question=str(args["question"]).strip(),
            strategy_application=str(args["strategy_application"]).strip(),
            evidence=str(args["evidence"]).strip(),
            assumptions=str(args["assumptions"]).strip(),
            alternatives=str(args["alternatives"]).strip(),
            disconfirming_signals=str(args["disconfirming_signals"]).strip(),
            confidence=confidence,
            next_action=str(args["next_action"]).strip(),
            metadata={"source_skill": self.definition.skill_name},
        )

    def _next_primitive_id(self) -> str:
        # Finds the next manager-local ID without overwriting a prior trace record.
        while True:
            primitive_id = f"reasoning_trace:{self.definition.skill_name}:{self._counter}"
            if self._manager.get_by_id(primitive_id) is None:
                return primitive_id
            self._counter += 1

    async def _record_item(self, item: Any, call: ToolCall) -> ToolResult:
        # Upserts the primitive and exposes only bounded text plus safe trace metadata.
        try:
            self._manager.upsert(item)
        except ValueError as exc:
            return ToolResult.error(call.tool_name, str(exc))
        return ToolResult.success(
            call.tool_name,
            item.to_context_text(),
            metadata={
                "strategy": item.strategy_name,
                "confidence": item.confidence,
                "primitive_id": item.primitive_id,
            },
        )


class ReasoningTraceCatalog:
    """Resolve fixed source skill definitions into explicit public tool classes."""

    _classes: ClassVar[dict[str, type[_ReasoningTraceTool]] | None] = None

    @classmethod
    def definitions(cls) -> tuple[ReasoningTraceDefinition, ...]:
        # Returns the immutable source-grounded reasoning definition catalog.
        return REASONING_TRACE_DEFINITIONS

    @classmethod
    def tool_class(cls, skill_name: str) -> type[_ReasoningTraceTool]:
        # Resolves one exact source skill slug without importing caller-provided paths.
        classes = cls.tool_classes()
        try:
            return classes[skill_name]
        except KeyError as exc:
            raise KeyError(f"Unknown reasoning trace skill: {skill_name}") from exc

    @classmethod
    def tool_classes(cls) -> Mapping[str, type[_ReasoningTraceTool]]:
        # Returns the lazily built slug-to-class map used by direct callers and exports.
        if cls._classes is None:
            cls._classes = cls._build_classes()
        return cls._classes

    @classmethod
    def tool_description(cls, definition: ReasoningTraceDefinition) -> str:
        # Builds five complete sentences that teach the model the strategy boundary and purpose.
        display_name = definition.skill_name.replace("-", " ")
        return (
            f"Use the {display_name} reasoning trace when the current task benefits from {definition.purpose.lower()} "
            "The tool records a bounded public checkpoint in the active context window so later iterations can inspect the question, method, evidence, and direction. "
            "Its fields require the agent to separate observations from interpretation, expose assumptions and alternatives, and name signals that could disconfirm the current line. "
            "Use it at a meaningful reasoning checkpoint rather than as a replacement for ordinary tool execution or private chain-of-thought. "
            "The resulting primitive is auditable model-authored telemetry, so monitors can compare process signals across runs without treating the record as ground truth."
        )

    @classmethod
    def parameters(cls, definition: ReasoningTraceDefinition) -> tuple[ToolParameter, ...]:
        # Builds the same eight required deep-observability fields for every strategy.
        return tuple(
            ToolParameter(
                name=name,
                type=_PARAMETER_TYPES[name],
                description=cls._parameter_description(name, definition),
                required=True,
            )
            for name in _PARAMETER_ORDER
        )

    @classmethod
    def _parameter_description(cls, name: str, definition: ReasoningTraceDefinition) -> str:
        # Adds the bound strategy identity to the shared field-specific guidance.
        template = _PARAMETER_TEMPLATES[name]
        if name == "strategy_application":
            return f"This field records application of {definition.skill_name}, whose purpose is to {definition.purpose.lower()} The field identifies the operative reasoning move, the stage reached, and the structure used to organize the work. It distinguishes actual application of the named strategy from a generic statement that reasoning occurred. It gives observers enough process detail to assess whether the strategy was used deliberately and completely."
        return template

    @classmethod
    def _build_classes(cls) -> dict[str, type[_ReasoningTraceTool]]:
        # Creates one collision-checked public subclass for every fixed definition.
        classes: dict[str, type[_ReasoningTraceTool]] = {}
        for definition in REASONING_TRACE_DEFINITIONS:
            class_name = cls._class_name(definition.skill_name)
            if class_name in globals() or class_name in classes:
                raise ValueError(f"Reasoning trace class name collision: {class_name}")
            classes[definition.skill_name] = type(
                class_name,
                (_ReasoningTraceTool,),
                {
                    "__module__": __name__,
                    "__doc__": f"Model-facing {definition.skill_name} reasoning trace tool.",
                    "definition": definition,
                },
            )
        return classes

    @staticmethod
    def _class_name(skill_name: str) -> str:
        # Converts a source slug into a stable public PascalCase class name.
        return "".join(part[:1].upper() + part[1:] for part in skill_name.split("-")) + "Tool"


REASONING_TRACE_DEFINITIONS = tuple(
    ReasoningTraceDefinition(skill_name=skill_name, purpose=purpose)
    for skill_name, purpose in _REASONING_TRACE_DEFINITION_DATA
)

_REASONING_TRACE_TOOL_CLASSES = dict(ReasoningTraceCatalog.tool_classes())
for _skill_name, _tool_class in _REASONING_TRACE_TOOL_CLASSES.items():
    globals()[_tool_class.__name__] = _tool_class

REASONING_TRACE_TOOL_CLASSES: Mapping[str, type[_ReasoningTraceTool]] = _REASONING_TRACE_TOOL_CLASSES

__all__ = [
    "ReasoningTraceCatalog",
    "ReasoningTraceDefinition",
    "REASONING_TRACE_DEFINITIONS",
    "REASONING_TRACE_TOOL_CLASSES",
    *(_tool_class.__name__ for _tool_class in _REASONING_TRACE_TOOL_CLASSES.values()),
]
