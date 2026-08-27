"""Context Protocol Header

Description:
    Public package for selectable verifier runtime algorithm modes.
Purpose:
    Gives AgentRuntime one stable import surface for each lifecycle strategy.
Role in codebase:
    Re-exports the four mode classes and their shared lifecycle contract.
Architecture note:
    Concrete modes live in separate modules and are delegated through
    AgentVerifierRuntime rather than embedded in AgentRuntime.
Common modification patterns:
    Add a mode module, export its class, and wire only its selection/config.
Known edge cases:
    Keep imports free of runtime construction side effects to avoid cycles.
Related docs:
    docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by verifier runtime import smoke tests and the full SDK suite.
"""

from vidbyte.agents.runtimes.verifier.algorithms.as_tool import VerifierAsToolMode, VerifierTool
from vidbyte.agents.runtimes.verifier.algorithms.base import RunOnce, VerifierRuntimeMode
from vidbyte.agents.runtimes.verifier.algorithms.finalization_gate import FinalizationGateMode
from vidbyte.agents.runtimes.verifier.algorithms.periodic import PeriodicVerificationMode
from vidbyte.agents.runtimes.verifier.algorithms.post_run import PostRunVerificationMode

__all__ = [
    "FinalizationGateMode",
    "PeriodicVerificationMode",
    "PostRunVerificationMode",
    "RunOnce",
    "VerifierAsToolMode",
    "VerifierRuntimeMode",
    "VerifierTool",
]
