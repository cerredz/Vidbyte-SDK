# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the abstract BaseStrategy class for the Vidbyte SDK.
# Purpose: Establishes a standard execution contract for all prompt-level and agentic reasoning loops.
# Architecture & Functions:
#   - BaseStrategy (ABC): Abstract class demanding an async run method.
# Codebase Relation:
#   - Forms the base interface implemented by all concrete SDK strategies (ReAct, ToT, etc.).
# Similar Files:
#   - vidbyte/harnesses/base.py (abstract class for harnesses subsystem)
# ==============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """
    Abstract Base Class for all Vidbyte reasoning strategies.
    Defines a unified `run` contract to decouple execution loops from model adapters.
    """

    @abstractmethod
    async def run(self, input_text: str, **kwargs: Any) -> Any:
        """
        Executes the strategy's reasoning logic asynchronously.
        Accepts the query text and custom runner/model configurations.
        """
        pass
