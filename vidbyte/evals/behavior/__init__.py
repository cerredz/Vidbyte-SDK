"""Context Protocol Header

Description:
    Declares root level exports for the Vidbyte SDK agent behavior module.
Purpose:
    Exposes RunProbe, Behavior, and all category behavior classes under the
    unified vidbyte.evals.behavior namespace.
Architecture:
    Consolidates probe, behavior facade, and category modules (tool,
    tool_arguments, stop, handoff, output) under one package interface.
Relations:
    Imported by vidbyte.evals to expose behavior predicates on the root eval
    namespace and by vidbyte.agents.base for the agent.behavior property.
"""

from __future__ import annotations

from vidbyte.evals.behavior.behavior import Behavior
from vidbyte.evals.behavior.handoff import HandoffBehavior
from vidbyte.evals.behavior.output import OutputBehavior
from vidbyte.evals.behavior.probe import RunProbe
from vidbyte.evals.behavior.stop import StopBehavior
from vidbyte.evals.behavior.tool import ToolBehavior
from vidbyte.evals.behavior.tool_arguments import ToolArgumentBehavior

__all__ = [
    "Behavior",
    "HandoffBehavior",
    "OutputBehavior",
    "RunProbe",
    "StopBehavior",
    "ToolBehavior",
    "ToolArgumentBehavior",
]
