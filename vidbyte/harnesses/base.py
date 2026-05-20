# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the abstract BaseHarness class for the Vidbyte SDK.
# Purpose: Establishes a standard contract for all agent evaluation and execution harnesses.
# Architecture & Functions:
#   - BaseHarness (ABC): Abstract class demanding an async execute method.
# Codebase Relation:
#   - Forms the base interface implemented by all concrete SDK harnesses.
# Similar Files:
#   - vidbyte/strategies/base.py (abstract class for strategies subsystem)
# ==============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseHarness(ABC):
    """
    Abstract Base Class for all Vidbyte orchestration harnesses.
    Coordinates agents, evaluators, and external resources in structured environments.
    """

    @abstractmethod
    async def execute(self, task: str, **kwargs: Any) -> Any:
        """
        Runs the harness environment on a specific task asynchronously.
        """
        pass
