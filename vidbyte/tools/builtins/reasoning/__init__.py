"""Context Protocol Header

Description:
    Exports the reasoning-strategy builtin tools.
Purpose:
    Provides agent-accessible tools that anchor the model to named strategies
    from the scientific-reasoning literature: deduction, induction, abduction,
    analogy, causal-chain reasoning, Bayesian updating, differential diagnosis,
    Fermi estimation, steelmanning, and falsification.
Architecture:
    - DeduceTool / InduceTool / AbduceTool: Classical inference forms.
    - AnalogyTool / CausalChainTool: Structural and causal transfer.
    - BayesianUpdateTool: Explicit numeric belief revision.
    - DifferentialDiagnosisTool / FermiEstimateTool: Elimination and estimation.
    - SteelmanTool / FalsifyTool: Adversarial self-testing of a claim.
Relations:
    Related to vidbyte.context.primitives.reasoning_strategies and
    vidbyte.tools.builtins. The package-private ReasoningToolInput helper in
    _parsing.py is intentionally not re-exported here.
"""

from __future__ import annotations

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

__all__ = [
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
]
