"""Context Protocol Header

Description:
    Exports the reasoning-strategy builtin tools.
Purpose:
    Provides agent-accessible tools that anchor the model to named strategies
    from the scientific-reasoning literature: deduction, induction, abduction,
    analogy, causal-chain reasoning, Bayesian updating, differential diagnosis,
    Fermi estimation, steelmanning, falsification, and twenty-five further
    strategies covering formal disproof, consistency, dilemmas, quantifier
    scope, transitivity, identity, partition, modality, equivocation,
    necessity-sufficiency, composition-division, circularity, regress,
    burden of proof, testimony, absence of evidence, defeasible reasoning,
    statistical syllogism, Socratic interrogation, dialectic, paradox,
    strawman audits, prediction, thought experiments, and instantiation.
Architecture:
    - DeduceTool / InduceTool / AbduceTool: Classical inference forms.
    - AnalogyTool / CausalChainTool: Structural and causal transfer.
    - BayesianUpdateTool: Explicit numeric belief revision.
    - DifferentialDiagnosisTool / FermiEstimateTool: Elimination and estimation.
    - SteelmanTool / FalsifyTool: Adversarial self-testing of a claim.
    - CounterexampleTool / QuantifierTool / TransitivityTool / IdentityTool /
      EquivocationTool / NecessarySufficientTool: Formal claim audits.
    - ConsistencyTool / PartitionTool / CompositionDivisionTool: Structural audits.
    - DilemmaTool / ModalTool / RegressTool / CircularityTool: Argument forms.
    - BurdenOfProofTool / TestimonyTool / AbsenceEvidenceTool / DefeasibleTool /
      StatisticalSyllogismTool: Evidence discipline.
    - SocraticTool / DialecticTool / ParadoxTool / StrawmanTool: Interrogation.
    - PredictTool / ThoughtExperimentTool / InstantiateTool: Application and testing.
Relations:
    Related to vidbyte.context.primitives.reasoning_strategies and
    vidbyte.tools.builtins. The package-private ReasoningToolInput helper in
    _parsing.py is intentionally not re-exported here.
"""

from __future__ import annotations

from vidbyte.tools.builtins.reasoning.abduce import AbduceTool
from vidbyte.tools.builtins.reasoning.absence_evidence import AbsenceEvidenceTool
from vidbyte.tools.builtins.reasoning.analogy import AnalogyTool
from vidbyte.tools.builtins.reasoning.bayesian_update import BayesianUpdateTool
from vidbyte.tools.builtins.reasoning.burden_of_proof import BurdenOfProofTool
from vidbyte.tools.builtins.reasoning.causal_chain import CausalChainTool
from vidbyte.tools.builtins.reasoning.circularity import CircularityTool
from vidbyte.tools.builtins.reasoning.composition_division import CompositionDivisionTool
from vidbyte.tools.builtins.reasoning.consistency import ConsistencyTool
from vidbyte.tools.builtins.reasoning.counterexample import CounterexampleTool
from vidbyte.tools.builtins.reasoning.deduce import DeduceTool
from vidbyte.tools.builtins.reasoning.defeasible import DefeasibleTool
from vidbyte.tools.builtins.reasoning.dialectic import DialecticTool
from vidbyte.tools.builtins.reasoning.differential_diagnosis import DifferentialDiagnosisTool
from vidbyte.tools.builtins.reasoning.dilemma import DilemmaTool
from vidbyte.tools.builtins.reasoning.equivocation import EquivocationTool
from vidbyte.tools.builtins.reasoning.falsify import FalsifyTool
from vidbyte.tools.builtins.reasoning.fermi_estimate import FermiEstimateTool
from vidbyte.tools.builtins.reasoning.identity import IdentityTool
from vidbyte.tools.builtins.reasoning.induce import InduceTool
from vidbyte.tools.builtins.reasoning.instantiate import InstantiateTool
from vidbyte.tools.builtins.reasoning.modal import ModalTool
from vidbyte.tools.builtins.reasoning.necessary_sufficient import NecessarySufficientTool
from vidbyte.tools.builtins.reasoning.paradox import ParadoxTool
from vidbyte.tools.builtins.reasoning.partition import PartitionTool
from vidbyte.tools.builtins.reasoning.predict import PredictTool
from vidbyte.tools.builtins.reasoning.quantifier import QuantifierTool
from vidbyte.tools.builtins.reasoning.regress import RegressTool
from vidbyte.tools.builtins.reasoning.socratic import SocraticTool
from vidbyte.tools.builtins.reasoning.statistical_syllogism import StatisticalSyllogismTool
from vidbyte.tools.builtins.reasoning.steelman import SteelmanTool
from vidbyte.tools.builtins.reasoning.strawman import StrawmanTool
from vidbyte.tools.builtins.reasoning.testimony import TestimonyTool
from vidbyte.tools.builtins.reasoning.thought_experiment import ThoughtExperimentTool
from vidbyte.tools.builtins.reasoning.transitivity import TransitivityTool

__all__ = [
    "AbduceTool",
    "AbsenceEvidenceTool",
    "AnalogyTool",
    "BayesianUpdateTool",
    "BurdenOfProofTool",
    "CausalChainTool",
    "CircularityTool",
    "CompositionDivisionTool",
    "ConsistencyTool",
    "CounterexampleTool",
    "DeduceTool",
    "DefeasibleTool",
    "DialecticTool",
    "DifferentialDiagnosisTool",
    "DilemmaTool",
    "EquivocationTool",
    "FalsifyTool",
    "FermiEstimateTool",
    "IdentityTool",
    "InduceTool",
    "InstantiateTool",
    "ModalTool",
    "NecessarySufficientTool",
    "ParadoxTool",
    "PartitionTool",
    "PredictTool",
    "QuantifierTool",
    "RegressTool",
    "SocraticTool",
    "StatisticalSyllogismTool",
    "SteelmanTool",
    "StrawmanTool",
    "TestimonyTool",
    "ThoughtExperimentTool",
    "TransitivityTool",
]
