# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the HarnessClient namespace class for the Vidbyte SDK.
# Purpose: Exposes the primary developer API for interacting with execution harnesses.
# Architecture & Functions:
#   - HarnessClient (class): Entry client for harness tasks.
# Codebase Relation:
#   - Instantiated as the `sdk.harnesses` property in `VidbyteSDK`.
# Similar Files:
#   - vidbyte/tools/client.py (client for the tool subsystem)
# ==============================================================================

from __future__ import annotations

from vidbyte.harnesses.conditional.loop_agent import ConditionalLoopAgentHarness
from vidbyte.harnesses.conditional.stopping_evaluator import ConditionalStoppingEvaluator


class HarnessClient:
    """
    Namespace client for all harness execution operations.
    Provides easy access to orchestrators like Conditional Loop Agents.
    """

    def __init__(self) -> None:
        self.conditional_loop = ConditionalLoopAgentHarness()
        self.stopping_evaluator = ConditionalStoppingEvaluator()
