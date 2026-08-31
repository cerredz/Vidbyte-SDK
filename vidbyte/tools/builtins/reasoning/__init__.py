"""Context Protocol Header

FILE: vidbyte/tools/builtins/reasoning/__init__.py
PURPOSE: Exports ten named reasoning tools and the fixed catalog of 182 strategy-specific public reasoning trace tools.
ROLE IN CODEBASE: vidbyte.tools.builtins imports this package to register reasoning tools in the SDK component registry.
ARCHITECTURE NOTE: The catalog is an immutable name-to-class index; leaf modules own schemas and _base.py owns shared execution behavior.
COMMON MODIFICATION PATTERNS: Add or remove a trace class and its export/catalog entry together, then run the contract checker.
KNOWN EDGE CASES: Tool names must remain unique and every catalog class must expose a matching immutable definition.
RELATED DOCS: docs/design/reasoning-deep-observability-tools.md and vidbyte/tools/README.md.
TESTS: scripts/check_reasoning_trace_contracts.py and the source/package stages in scripts/run_ci.py.

Description:
    Exports both named reasoning-strategy tools and the built-in reasoning trace
    catalog.
Purpose:
    Provides agent-accessible tools that anchor model reasoning to explicit
    strategies while retaining the SDK's larger trace-oriented catalog.
Architecture:
    - DeduceTool / InduceTool / AbduceTool: Classical inference forms.
    - AnalogyTool / CausalChainTool: Structural and causal transfer.
    - BayesianUpdateTool / DifferentialDiagnosisTool / FermiEstimateTool:
      Numeric belief revision, elimination, and estimation.
    - SteelmanTool / FalsifyTool: Adversarial self-testing.
    - ReasoningTraceCatalog: The fixed catalog of strategy-specific trace tools.
Relations:
    Related to vidbyte.context.primitives.reasoning_strategies,
    vidbyte.context.primitives.reasoning_traces, and vidbyte.tools.builtins.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from ._base import ReasoningTraceDefinition, ReasoningTraceTool, parameter
from vidbyte.tools.builtins.reasoning.abduce import AbduceTool
from vidbyte.tools.builtins.reasoning.analogy import AnalogyTool
from vidbyte.tools.builtins.reasoning.bayesian_update import BayesianUpdateTool
from vidbyte.tools.builtins.reasoning.causal_chain import CausalChainTool
from vidbyte.tools.builtins.reasoning.deduce import DeduceTool
from vidbyte.tools.builtins.reasoning.differential_diagnosis import DifferentialDiagnosisTool
from vidbyte.tools.builtins.reasoning.falsify import FalsifyTool
from vidbyte.tools.builtins.reasoning.fermi_estimate import FermiEstimateTool
from vidbyte.tools.builtins.reasoning.induce import InduceTool
from vidbyte.tools.builtins.reasoning.steelman import SteelmanTool
from .a3_problem_solving_trace import A3ProblemSolvingTraceTool
from .ab_testing_trace import AbTestingTraceTool
from .abductive_trace import AbductiveTraceTool
from .adaptive_reasoning_trace import AdaptiveReasoningTraceTool
from .affect_heuristic_trace import AffectHeuristicTraceTool
from .after_action_review_trace import AfterActionReviewTraceTool
from .alternative_futures_trace import AlternativeFuturesTraceTool
from .analogical_trace import AnalogicalTraceTool
from .analysis_of_competing_hypotheses_trace import (
    AnalysisOfCompetingHypothesesTraceTool,
)
from .analytic_hierarchy_process_trace import AnalyticHierarchyProcessTraceTool
from .ansoff_matrix_trace import AnsoffMatrixTraceTool
from .argument_map_trace import ArgumentMapTraceTool
from .assumption_ladder_trace import AssumptionLadderTraceTool
from .backward_chaining_trace import BackwardChainingTraceTool
from .balanced_scorecard_trace import BalancedScorecardTraceTool
from .base_rate_trace import BaseRateTraceTool
from .bayesian_trace import BayesianTraceTool
from .bcg_matrix_trace import BcgMatrixTraceTool
from .biomimicry_trace import BiomimicryTraceTool
from .blue_ocean_strategy_trace import BlueOceanStrategyTraceTool
from .bottleneck_trace import BottleneckTraceTool
from .bowtie_risk_trace import BowtieRiskTraceTool
from .business_model_canvas_trace import BusinessModelCanvasTraceTool
from .causal_loop_trace import CausalLoopTraceTool
from .causal_trace import CausalTraceTool
from .comparative_case_trace import ComparativeCaseTraceTool
from .concept_mapping_trace import ConceptMappingTraceTool
from .cone_of_plausibility_trace import ConeOfPlausibilityTraceTool
from .constraint_removal_trace import ConstraintRemovalTraceTool
from .constraint_satisfaction_trace import ConstraintSatisfactionTraceTool
from .correlation_causation_trace import CorrelationCausationTraceTool
from .cost_benefit_trace import CostBenefitTraceTool
from .counterfactual_trace import CounterfactualTraceTool
from .customer_journey_mapping_trace import CustomerJourneyMappingTraceTool
from .cynefin_trace import CynefinTraceTool
from .data_quality_audit_trace import DataQualityAuditTraceTool
from .deception_detection_trace import DeceptionDetectionTraceTool
from .decision_matrix_trace import DecisionMatrixTraceTool
from .decision_tree_trace import DecisionTreeTraceTool
from .deductive_trace import DeductiveTraceTool
from .default_heuristic_trace import DefaultHeuristicTraceTool
from .defeasible_reasoning_trace import DefeasibleReasoningTraceTool
from .delphi_method_trace import DelphiMethodTraceTool
from .dependency_mapping_trace import DependencyMappingTraceTool
from .design_thinking_trace import DesignThinkingTraceTool
from .devils_advocacy_trace import DevilsAdvocacyTraceTool
from .dialectical_trace import DialecticalTraceTool
from .dmaic_trace import DmaicTraceTool
from .double_diamond_trace import DoubleDiamondTraceTool
from .double_loop_learning_trace import DoubleLoopLearningTraceTool
from .elimination_by_aspects_trace import EliminationByAspectsTraceTool
from .empathy_mapping_trace import EmpathyMappingTraceTool
from .error_analysis_trace import ErrorAnalysisTraceTool
from .ethical_matrix_trace import EthicalMatrixTraceTool
from .ethnographic_reasoning_trace import EthnographicReasoningTraceTool
from .event_tree_trace import EventTreeTraceTool
from .evidence_triangulation_trace import EvidenceTriangulationTraceTool
from .expected_value_trace import ExpectedValueTraceTool
from .experimental_design_trace import ExperimentalDesignTraceTool
from .fairness_analysis_trace import FairnessAnalysisTraceTool
from .familiarity_heuristic_trace import FamiliarityHeuristicTraceTool
from .fast_and_frugal_trees_trace import FastAndFrugalTreesTraceTool
from .fault_tree_trace import FaultTreeTraceTool
from .feedback_loop_trace import FeedbackLoopTraceTool
from .fermi_estimation_trace import FermiEstimationTraceTool
from .first_principles_trace import FirstPrinciplesTraceTool
from .fishbone_trace import FishboneTraceTool
from .five_whys_trace import FiveWhysTraceTool
from .fluency_heuristic_trace import FluencyHeuristicTraceTool
from .fmea_trace import FmeaTraceTool
from .force_field_trace import ForceFieldTraceTool
from .forward_chaining_trace import ForwardChainingTraceTool
from .fuzzy_logic_trace import FuzzyLogicTraceTool
from .game_theory_trace import GameTheoryTraceTool
from .gemba_walk_trace import GembaWalkTraceTool
from .hazop_trace import HazopTraceTool
from .hermeneutic_trace import HermeneuticTraceTool
from .historical_reasoning_trace import HistoricalReasoningTraceTool
from .horizon_scanning_trace import HorizonScanningTraceTool
from .hypothesis_testing_trace import HypothesisTestingTraceTool
from .iceberg_model_trace import IcebergModelTraceTool
from .incentive_analysis_trace import IncentiveAnalysisTraceTool
from .indicators_signposts_trace import IndicatorsSignpostsTraceTool
from .inductive_trace import InductiveTraceTool
from .influence_diagram_trace import InfluenceDiagramTraceTool
from .inversion_trace import InversionTraceTool
from .issue_tree_trace import IssueTreeTraceTool
from .jobs_to_be_done_trace import JobsToBeDoneTraceTool
from .key_assumptions_check_trace import KeyAssumptionsCheckTraceTool
from .kolb_learning_cycle_trace import KolbLearningCycleTraceTool
from .lateral_thinking_trace import LateralThinkingTraceTool
from .legal_reasoning_trace import LegalReasoningTraceTool
from .leverage_points_trace import LeveragePointsTraceTool
from .linchpin_analysis_trace import LinchpinAnalysisTraceTool
from .mece_decomposition_trace import MeceDecompositionTraceTool
from .mental_simulation_trace import MentalSimulationTraceTool
from .metacognitive_audit_trace import MetacognitiveAuditTraceTool
from .mind_map_trace import MindMapTraceTool
from .minimax_trace import MinimaxTraceTool
from .minto_pyramid_trace import MintoPyramidTraceTool
from .modal_reasoning_trace import ModalReasoningTraceTool
from .morphological_analysis_trace import MorphologicalAnalysisTraceTool
from .multi_attribute_utility_trace import MultiAttributeUtilityTraceTool
from .naive_diversification_trace import NaiveDiversificationTraceTool
from .narrative_reasoning_trace import NarrativeReasoningTraceTool
from .nine_windows_trace import NineWindowsTraceTool
from .nonmonotonic_reasoning_trace import NonmonotonicReasoningTraceTool
from .nth_order_effects_trace import NthOrderEffectsTraceTool
from .null_hypothesis_trace import NullHypothesisTraceTool
from .occams_razor_trace import OccamsRazorTraceTool
from .ooda_loop_trace import OodaLoopTraceTool
from .ooda_red_team_trace import OodaRedTeamTraceTool
from .opportunity_cost_trace import OpportunityCostTraceTool
from .outside_view_trace import OutsideViewTraceTool
from .pareto_principle_trace import ParetoPrincipleTraceTool
from .pdca_cycle_trace import PdcaCycleTraceTool
from .peak_end_rule_trace import PeakEndRuleTraceTool
from .pestle_trace import PestleTraceTool
from .phenomenology_trace import PhenomenologyTraceTool
from .policy_analysis_trace import PolicyAnalysisTraceTool
from .porters_five_forces_trace import PortersFiveForcesTraceTool
from .postmortem_trace import PostmortemTraceTool
from .pragmatism_trace import PragmatismTraceTool
from .precautionary_principle_trace import PrecautionaryPrincipleTraceTool
from .predicate_logic_trace import PredicateLogicTraceTool
from .premortem_trace import PremortemTraceTool
from .probabilistic_trace import ProbabilisticTraceTool
from .proof_by_cases_trace import ProofByCasesTraceTool
from .proof_by_contradiction_trace import ProofByContradictionTraceTool
from .propositional_logic_trace import PropositionalLogicTraceTool
from .provocation_trace import ProvocationTraceTool
from .quasi_experimental_trace import QuasiExperimentalTraceTool
from .random_stimulus_trace import RandomStimulusTraceTool
from .randomized_control_trial_trace import RandomizedControlTrialTraceTool
from .recognition_heuristic_trace import RecognitionHeuristicTraceTool
from .red_team_trace import RedTeamTraceTool
from .reference_class_forecasting_trace import ReferenceClassForecastingTraceTool
from .reframing_trace import ReframingTraceTool
from .regression_reasoning_trace import RegressionReasoningTraceTool
from .regret_minimization_trace import RegretMinimizationTraceTool
from .reverse_brainstorming_trace import ReverseBrainstormingTraceTool
from .root_cause_trace import RootCauseTraceTool
from .rubber_duck_debugging_trace import RubberDuckDebuggingTraceTool
from .satisficing_trace import SatisficingTraceTool
from .scamper_trace import ScamperTraceTool
from .scarcity_heuristic_trace import ScarcityHeuristicTraceTool
from .scenario_planning_trace import ScenarioPlanningTraceTool
from .scientific_method_trace import ScientificMethodTraceTool
from .second_order_effects_trace import SecondOrderEffectsTraceTool
from .sensitivity_analysis_trace import SensitivityAnalysisTraceTool
from .simulation_heuristic_trace import SimulationHeuristicTraceTool
from .six_thinking_hats_trace import SixThinkingHatsTraceTool
from .social_proof_trace import SocialProofTraceTool
from .socratic_questioning_trace import SocraticQuestioningTraceTool
from .spatial_reasoning_trace import SpatialReasoningTraceTool
from .speed_accuracy_tradeoff_trace import SpeedAccuracyTradeoffTraceTool
from .spider_mapping_trace import SpiderMappingTraceTool
from .stakeholder_analysis_trace import StakeholderAnalysisTraceTool
from .steelman_trace import SteelmanTraceTool
from .stock_and_flow_trace import StockAndFlowTraceTool
from .storyboarding_trace import StoryboardingTraceTool
from .swot_trace import SwotTraceTool
from .syllogistic_trace import SyllogisticTraceTool
from .synectics_trace import SynecticsTraceTool
from .systematic_inventive_thinking_trace import SystematicInventiveThinkingTraceTool
from .systems_thinking_trace import SystemsThinkingTraceTool
from .take_the_best_trace import TakeTheBestTraceTool
from .tallying_trace import TallyingTraceTool
from .temporal_reasoning_trace import TemporalReasoningTraceTool
from .theory_of_constraints_trace import TheoryOfConstraintsTraceTool
from .tradeoff_matrix_trace import TradeoffMatrixTraceTool
from .trial_and_error_trace import TrialAndErrorTraceTool
from .triz_trace import TrizTraceTool
from .uncertainty_quantification_trace import UncertaintyQuantificationTraceTool
from .utility_trace import UtilityTraceTool
from .value_chain_analysis_trace import ValueChainAnalysisTraceTool
from .value_focused_thinking_trace import ValueFocusedThinkingTraceTool
from .value_stream_mapping_trace import ValueStreamMappingTraceTool
from .values_tradeoff_trace import ValuesTradeoffTraceTool
from .vrio_framework_trace import VrioFrameworkTraceTool
from .what_if_analysis_trace import WhatIfAnalysisTraceTool
from .why_because_analysis_trace import WhyBecauseAnalysisTraceTool


class ReasoningTraceCatalog:
    """Resolve only the fixed in-package reasoning trace catalog."""

    _classes: ClassVar[Mapping[str, type[ReasoningTraceTool]]] = MappingProxyType({
    'a3-problem-solving-trace': A3ProblemSolvingTraceTool,
    'ab-testing-trace': AbTestingTraceTool,
    'abductive-trace': AbductiveTraceTool,
    'adaptive-reasoning-trace': AdaptiveReasoningTraceTool,
    'affect-heuristic-trace': AffectHeuristicTraceTool,
    'after-action-review-trace': AfterActionReviewTraceTool,
    'alternative-futures-trace': AlternativeFuturesTraceTool,
    'analogical-trace': AnalogicalTraceTool,
    'analysis-of-competing-hypotheses-trace': AnalysisOfCompetingHypothesesTraceTool,
    'analytic-hierarchy-process-trace': AnalyticHierarchyProcessTraceTool,
    'ansoff-matrix-trace': AnsoffMatrixTraceTool,
    'argument-map-trace': ArgumentMapTraceTool,
    'assumption-ladder-trace': AssumptionLadderTraceTool,
    'backward-chaining-trace': BackwardChainingTraceTool,
    'balanced-scorecard-trace': BalancedScorecardTraceTool,
    'base-rate-trace': BaseRateTraceTool,
    'bayesian-trace': BayesianTraceTool,
    'bcg-matrix-trace': BcgMatrixTraceTool,
    'biomimicry-trace': BiomimicryTraceTool,
    'blue-ocean-strategy-trace': BlueOceanStrategyTraceTool,
    'bottleneck-trace': BottleneckTraceTool,
    'bowtie-risk-trace': BowtieRiskTraceTool,
    'business-model-canvas-trace': BusinessModelCanvasTraceTool,
    'causal-loop-trace': CausalLoopTraceTool,
    'causal-trace': CausalTraceTool,
    'comparative-case-trace': ComparativeCaseTraceTool,
    'concept-mapping-trace': ConceptMappingTraceTool,
    'cone-of-plausibility-trace': ConeOfPlausibilityTraceTool,
    'constraint-removal-trace': ConstraintRemovalTraceTool,
    'constraint-satisfaction-trace': ConstraintSatisfactionTraceTool,
    'correlation-causation-trace': CorrelationCausationTraceTool,
    'cost-benefit-trace': CostBenefitTraceTool,
    'counterfactual-trace': CounterfactualTraceTool,
    'customer-journey-mapping-trace': CustomerJourneyMappingTraceTool,
    'cynefin-trace': CynefinTraceTool,
    'data-quality-audit-trace': DataQualityAuditTraceTool,
    'deception-detection-trace': DeceptionDetectionTraceTool,
    'decision-matrix-trace': DecisionMatrixTraceTool,
    'decision-tree-trace': DecisionTreeTraceTool,
    'deductive-trace': DeductiveTraceTool,
    'default-heuristic-trace': DefaultHeuristicTraceTool,
    'defeasible-reasoning-trace': DefeasibleReasoningTraceTool,
    'delphi-method-trace': DelphiMethodTraceTool,
    'dependency-mapping-trace': DependencyMappingTraceTool,
    'design-thinking-trace': DesignThinkingTraceTool,
    'devils-advocacy-trace': DevilsAdvocacyTraceTool,
    'dialectical-trace': DialecticalTraceTool,
    'dmaic-trace': DmaicTraceTool,
    'double-diamond-trace': DoubleDiamondTraceTool,
    'double-loop-learning-trace': DoubleLoopLearningTraceTool,
    'elimination-by-aspects-trace': EliminationByAspectsTraceTool,
    'empathy-mapping-trace': EmpathyMappingTraceTool,
    'error-analysis-trace': ErrorAnalysisTraceTool,
    'ethical-matrix-trace': EthicalMatrixTraceTool,
    'ethnographic-reasoning-trace': EthnographicReasoningTraceTool,
    'event-tree-trace': EventTreeTraceTool,
    'evidence-triangulation-trace': EvidenceTriangulationTraceTool,
    'expected-value-trace': ExpectedValueTraceTool,
    'experimental-design-trace': ExperimentalDesignTraceTool,
    'fairness-analysis-trace': FairnessAnalysisTraceTool,
    'familiarity-heuristic-trace': FamiliarityHeuristicTraceTool,
    'fast-and-frugal-trees-trace': FastAndFrugalTreesTraceTool,
    'fault-tree-trace': FaultTreeTraceTool,
    'feedback-loop-trace': FeedbackLoopTraceTool,
    'fermi-estimation-trace': FermiEstimationTraceTool,
    'first-principles-trace': FirstPrinciplesTraceTool,
    'fishbone-trace': FishboneTraceTool,
    'five-whys-trace': FiveWhysTraceTool,
    'fluency-heuristic-trace': FluencyHeuristicTraceTool,
    'fmea-trace': FmeaTraceTool,
    'force-field-trace': ForceFieldTraceTool,
    'forward-chaining-trace': ForwardChainingTraceTool,
    'fuzzy-logic-trace': FuzzyLogicTraceTool,
    'game-theory-trace': GameTheoryTraceTool,
    'gemba-walk-trace': GembaWalkTraceTool,
    'hazop-trace': HazopTraceTool,
    'hermeneutic-trace': HermeneuticTraceTool,
    'historical-reasoning-trace': HistoricalReasoningTraceTool,
    'horizon-scanning-trace': HorizonScanningTraceTool,
    'hypothesis-testing-trace': HypothesisTestingTraceTool,
    'iceberg-model-trace': IcebergModelTraceTool,
    'incentive-analysis-trace': IncentiveAnalysisTraceTool,
    'indicators-signposts-trace': IndicatorsSignpostsTraceTool,
    'inductive-trace': InductiveTraceTool,
    'influence-diagram-trace': InfluenceDiagramTraceTool,
    'inversion-trace': InversionTraceTool,
    'issue-tree-trace': IssueTreeTraceTool,
    'jobs-to-be-done-trace': JobsToBeDoneTraceTool,
    'key-assumptions-check-trace': KeyAssumptionsCheckTraceTool,
    'kolb-learning-cycle-trace': KolbLearningCycleTraceTool,
    'lateral-thinking-trace': LateralThinkingTraceTool,
    'legal-reasoning-trace': LegalReasoningTraceTool,
    'leverage-points-trace': LeveragePointsTraceTool,
    'linchpin-analysis-trace': LinchpinAnalysisTraceTool,
    'mece-decomposition-trace': MeceDecompositionTraceTool,
    'mental-simulation-trace': MentalSimulationTraceTool,
    'metacognitive-audit-trace': MetacognitiveAuditTraceTool,
    'mind-map-trace': MindMapTraceTool,
    'minimax-trace': MinimaxTraceTool,
    'minto-pyramid-trace': MintoPyramidTraceTool,
    'modal-reasoning-trace': ModalReasoningTraceTool,
    'morphological-analysis-trace': MorphologicalAnalysisTraceTool,
    'multi-attribute-utility-trace': MultiAttributeUtilityTraceTool,
    'naive-diversification-trace': NaiveDiversificationTraceTool,
    'narrative-reasoning-trace': NarrativeReasoningTraceTool,
    'nine-windows-trace': NineWindowsTraceTool,
    'nonmonotonic-reasoning-trace': NonmonotonicReasoningTraceTool,
    'nth-order-effects-trace': NthOrderEffectsTraceTool,
    'null-hypothesis-trace': NullHypothesisTraceTool,
    'occams-razor-trace': OccamsRazorTraceTool,
    'ooda-loop-trace': OodaLoopTraceTool,
    'ooda-red-team-trace': OodaRedTeamTraceTool,
    'opportunity-cost-trace': OpportunityCostTraceTool,
    'outside-view-trace': OutsideViewTraceTool,
    'pareto-principle-trace': ParetoPrincipleTraceTool,
    'pdca-cycle-trace': PdcaCycleTraceTool,
    'peak-end-rule-trace': PeakEndRuleTraceTool,
    'pestle-trace': PestleTraceTool,
    'phenomenology-trace': PhenomenologyTraceTool,
    'policy-analysis-trace': PolicyAnalysisTraceTool,
    'porters-five-forces-trace': PortersFiveForcesTraceTool,
    'postmortem-trace': PostmortemTraceTool,
    'pragmatism-trace': PragmatismTraceTool,
    'precautionary-principle-trace': PrecautionaryPrincipleTraceTool,
    'predicate-logic-trace': PredicateLogicTraceTool,
    'premortem-trace': PremortemTraceTool,
    'probabilistic-trace': ProbabilisticTraceTool,
    'proof-by-cases-trace': ProofByCasesTraceTool,
    'proof-by-contradiction-trace': ProofByContradictionTraceTool,
    'propositional-logic-trace': PropositionalLogicTraceTool,
    'provocation-trace': ProvocationTraceTool,
    'quasi-experimental-trace': QuasiExperimentalTraceTool,
    'random-stimulus-trace': RandomStimulusTraceTool,
    'randomized-control-trial-trace': RandomizedControlTrialTraceTool,
    'recognition-heuristic-trace': RecognitionHeuristicTraceTool,
    'red-team-trace': RedTeamTraceTool,
    'reference-class-forecasting-trace': ReferenceClassForecastingTraceTool,
    'reframing-trace': ReframingTraceTool,
    'regression-reasoning-trace': RegressionReasoningTraceTool,
    'regret-minimization-trace': RegretMinimizationTraceTool,
    'reverse-brainstorming-trace': ReverseBrainstormingTraceTool,
    'root-cause-trace': RootCauseTraceTool,
    'rubber-duck-debugging-trace': RubberDuckDebuggingTraceTool,
    'satisficing-trace': SatisficingTraceTool,
    'scamper-trace': ScamperTraceTool,
    'scarcity-heuristic-trace': ScarcityHeuristicTraceTool,
    'scenario-planning-trace': ScenarioPlanningTraceTool,
    'scientific-method-trace': ScientificMethodTraceTool,
    'second-order-effects-trace': SecondOrderEffectsTraceTool,
    'sensitivity-analysis-trace': SensitivityAnalysisTraceTool,
    'simulation-heuristic-trace': SimulationHeuristicTraceTool,
    'six-thinking-hats-trace': SixThinkingHatsTraceTool,
    'social-proof-trace': SocialProofTraceTool,
    'socratic-questioning-trace': SocraticQuestioningTraceTool,
    'spatial-reasoning-trace': SpatialReasoningTraceTool,
    'speed-accuracy-tradeoff-trace': SpeedAccuracyTradeoffTraceTool,
    'spider-mapping-trace': SpiderMappingTraceTool,
    'stakeholder-analysis-trace': StakeholderAnalysisTraceTool,
    'steelman-trace': SteelmanTraceTool,
    'stock-and-flow-trace': StockAndFlowTraceTool,
    'storyboarding-trace': StoryboardingTraceTool,
    'swot-trace': SwotTraceTool,
    'syllogistic-trace': SyllogisticTraceTool,
    'synectics-trace': SynecticsTraceTool,
    'systematic-inventive-thinking-trace': SystematicInventiveThinkingTraceTool,
    'systems-thinking-trace': SystemsThinkingTraceTool,
    'take-the-best-trace': TakeTheBestTraceTool,
    'tallying-trace': TallyingTraceTool,
    'temporal-reasoning-trace': TemporalReasoningTraceTool,
    'theory-of-constraints-trace': TheoryOfConstraintsTraceTool,
    'tradeoff-matrix-trace': TradeoffMatrixTraceTool,
    'trial-and-error-trace': TrialAndErrorTraceTool,
    'triz-trace': TrizTraceTool,
    'uncertainty-quantification-trace': UncertaintyQuantificationTraceTool,
    'utility-trace': UtilityTraceTool,
    'value-chain-analysis-trace': ValueChainAnalysisTraceTool,
    'value-focused-thinking-trace': ValueFocusedThinkingTraceTool,
    'value-stream-mapping-trace': ValueStreamMappingTraceTool,
    'values-tradeoff-trace': ValuesTradeoffTraceTool,
    'vrio-framework-trace': VrioFrameworkTraceTool,
    'what-if-analysis-trace': WhatIfAnalysisTraceTool,
    'why-because-analysis-trace': WhyBecauseAnalysisTraceTool
    })

    @classmethod
    def definitions(cls) -> tuple[ReasoningTraceDefinition, ...]:
        """Return all strategy-owned definitions in stable source order."""
        return tuple(tool.definition for tool in cls._classes.values())

    @classmethod
    def tool_class(cls, skill_name: str) -> type[ReasoningTraceTool]:
        """Return one exact strategy class or a bounded lookup error."""
        try:
            return cls._classes[skill_name]
        except KeyError as exc:
            raise KeyError(f"Unknown reasoning trace skill: {skill_name}. Supported skills: {', '.join(cls._classes)}") from exc

    @classmethod
    def tool_classes(cls) -> Mapping[str, type[ReasoningTraceTool]]:
        """Return the immutable strategy-to-class catalog."""
        return cls._classes


REASONING_TRACE_TOOL_CLASSES = ReasoningTraceCatalog.tool_classes()
REASONING_TRACE_DEFINITIONS = ReasoningTraceCatalog.definitions()

__all__ = [
    "REASONING_TRACE_DEFINITIONS",
    "REASONING_TRACE_TOOL_CLASSES",
    'A3ProblemSolvingTraceTool',
    'AbTestingTraceTool',
    'AbductiveTraceTool',
    'AdaptiveReasoningTraceTool',
    'AffectHeuristicTraceTool',
    'AfterActionReviewTraceTool',
    'AlternativeFuturesTraceTool',
    'AnalogicalTraceTool',
    'AnalysisOfCompetingHypothesesTraceTool',
    'AnalyticHierarchyProcessTraceTool',
    'AnsoffMatrixTraceTool',
    'ArgumentMapTraceTool',
    'AssumptionLadderTraceTool',
    'BackwardChainingTraceTool',
    'BalancedScorecardTraceTool',
    'BaseRateTraceTool',
    'BayesianTraceTool',
    'BcgMatrixTraceTool',
    'BiomimicryTraceTool',
    'BlueOceanStrategyTraceTool',
    'BottleneckTraceTool',
    'BowtieRiskTraceTool',
    'BusinessModelCanvasTraceTool',
    'CausalLoopTraceTool',
    'CausalTraceTool',
    'ComparativeCaseTraceTool',
    'ConceptMappingTraceTool',
    'ConeOfPlausibilityTraceTool',
    'ConstraintRemovalTraceTool',
    'ConstraintSatisfactionTraceTool',
    'CorrelationCausationTraceTool',
    'CostBenefitTraceTool',
    'CounterfactualTraceTool',
    'CustomerJourneyMappingTraceTool',
    'CynefinTraceTool',
    'DataQualityAuditTraceTool',
    'DeceptionDetectionTraceTool',
    'DecisionMatrixTraceTool',
    'DecisionTreeTraceTool',
    'DeductiveTraceTool',
    'DefaultHeuristicTraceTool',
    'DefeasibleReasoningTraceTool',
    'DelphiMethodTraceTool',
    'DependencyMappingTraceTool',
    'DesignThinkingTraceTool',
    'DevilsAdvocacyTraceTool',
    'DialecticalTraceTool',
    'DmaicTraceTool',
    'DoubleDiamondTraceTool',
    'DoubleLoopLearningTraceTool',
    'EliminationByAspectsTraceTool',
    'EmpathyMappingTraceTool',
    'ErrorAnalysisTraceTool',
    'EthicalMatrixTraceTool',
    'EthnographicReasoningTraceTool',
    'EventTreeTraceTool',
    'EvidenceTriangulationTraceTool',
    'ExpectedValueTraceTool',
    'ExperimentalDesignTraceTool',
    'FairnessAnalysisTraceTool',
    'FamiliarityHeuristicTraceTool',
    'FastAndFrugalTreesTraceTool',
    'FaultTreeTraceTool',
    'FeedbackLoopTraceTool',
    'FermiEstimationTraceTool',
    'FirstPrinciplesTraceTool',
    'FishboneTraceTool',
    'FiveWhysTraceTool',
    'FluencyHeuristicTraceTool',
    'FmeaTraceTool',
    'ForceFieldTraceTool',
    'ForwardChainingTraceTool',
    'FuzzyLogicTraceTool',
    'GameTheoryTraceTool',
    'GembaWalkTraceTool',
    'HazopTraceTool',
    'HermeneuticTraceTool',
    'HistoricalReasoningTraceTool',
    'HorizonScanningTraceTool',
    'HypothesisTestingTraceTool',
    'IcebergModelTraceTool',
    'IncentiveAnalysisTraceTool',
    'IndicatorsSignpostsTraceTool',
    'InductiveTraceTool',
    'InfluenceDiagramTraceTool',
    'InversionTraceTool',
    'IssueTreeTraceTool',
    'JobsToBeDoneTraceTool',
    'KeyAssumptionsCheckTraceTool',
    'KolbLearningCycleTraceTool',
    'LateralThinkingTraceTool',
    'LegalReasoningTraceTool',
    'LeveragePointsTraceTool',
    'LinchpinAnalysisTraceTool',
    'MeceDecompositionTraceTool',
    'MentalSimulationTraceTool',
    'MetacognitiveAuditTraceTool',
    'MindMapTraceTool',
    'MinimaxTraceTool',
    'MintoPyramidTraceTool',
    'ModalReasoningTraceTool',
    'MorphologicalAnalysisTraceTool',
    'MultiAttributeUtilityTraceTool',
    'NaiveDiversificationTraceTool',
    'NarrativeReasoningTraceTool',
    'NineWindowsTraceTool',
    'NonmonotonicReasoningTraceTool',
    'NthOrderEffectsTraceTool',
    'NullHypothesisTraceTool',
    'OccamsRazorTraceTool',
    'OodaLoopTraceTool',
    'OodaRedTeamTraceTool',
    'OpportunityCostTraceTool',
    'OutsideViewTraceTool',
    'ParetoPrincipleTraceTool',
    'PdcaCycleTraceTool',
    'PeakEndRuleTraceTool',
    'PestleTraceTool',
    'PhenomenologyTraceTool',
    'PolicyAnalysisTraceTool',
    'PortersFiveForcesTraceTool',
    'PostmortemTraceTool',
    'PragmatismTraceTool',
    'PrecautionaryPrincipleTraceTool',
    'PredicateLogicTraceTool',
    'PremortemTraceTool',
    'ProbabilisticTraceTool',
    'ProofByCasesTraceTool',
    'ProofByContradictionTraceTool',
    'PropositionalLogicTraceTool',
    'ProvocationTraceTool',
    'QuasiExperimentalTraceTool',
    'RandomStimulusTraceTool',
    'RandomizedControlTrialTraceTool',
    "ReasoningTraceCatalog",
    "ReasoningTraceDefinition",
    "ReasoningTraceTool",
    'RecognitionHeuristicTraceTool',
    'RedTeamTraceTool',
    'ReferenceClassForecastingTraceTool',
    'ReframingTraceTool',
    'RegressionReasoningTraceTool',
    'RegretMinimizationTraceTool',
    'ReverseBrainstormingTraceTool',
    'RootCauseTraceTool',
    'RubberDuckDebuggingTraceTool',
    'SatisficingTraceTool',
    'ScamperTraceTool',
    'ScarcityHeuristicTraceTool',
    'ScenarioPlanningTraceTool',
    'ScientificMethodTraceTool',
    'SecondOrderEffectsTraceTool',
    'SensitivityAnalysisTraceTool',
    'SimulationHeuristicTraceTool',
    'SixThinkingHatsTraceTool',
    'SocialProofTraceTool',
    'SocraticQuestioningTraceTool',
    'SpatialReasoningTraceTool',
    'SpeedAccuracyTradeoffTraceTool',
    'SpiderMappingTraceTool',
    'StakeholderAnalysisTraceTool',
    'SteelmanTraceTool',
    'StockAndFlowTraceTool',
    'StoryboardingTraceTool',
    'SwotTraceTool',
    'SyllogisticTraceTool',
    'SynecticsTraceTool',
    'SystematicInventiveThinkingTraceTool',
    'SystemsThinkingTraceTool',
    'TakeTheBestTraceTool',
    'TallyingTraceTool',
    'TemporalReasoningTraceTool',
    'TheoryOfConstraintsTraceTool',
    'TradeoffMatrixTraceTool',
    'TrialAndErrorTraceTool',
    'TrizTraceTool',
    'UncertaintyQuantificationTraceTool',
    'UtilityTraceTool',
    'ValueChainAnalysisTraceTool',
    'ValueFocusedThinkingTraceTool',
    'ValueStreamMappingTraceTool',
    'ValuesTradeoffTraceTool',
    'VrioFrameworkTraceTool',
    'WhatIfAnalysisTraceTool',
    'WhyBecauseAnalysisTraceTool',
    "AbduceTool",
    "AnalogyTool",
    "BayesianUpdateTool",
    "CausalChainTool",
    "DeduceTool",
    "DifferentialDiagnosisTool",
    "FalsifyTool",
    "FermiEstimateTool",
    "InduceTool",
    "SteelmanTool",
    "parameter",
]
