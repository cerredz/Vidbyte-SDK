"""Context Protocol Header

Description:
    Defines the AgentRuntimeType enum mapping execution runtimes.
Purpose:
    Allows developers to select linear or non-linear agent runtimes as standardized
    string-backed enums, supporting validation checks.
Architecture:
    - AgentRuntimeType: String-backed Enum class.
Relations:
    Imported by vidbyte.lib.enums and consumed by BaseAgent.
Similar Files:
    - vidbyte/lib/enums/model_modality.py: Standard string-backed enums.
"""

from __future__ import annotations
from enum import Enum


class AgentRuntimeType(str, Enum):
    """String-backed enum class representing the swappable agent loops."""

    LINEAR = "linear"
    MCTS_SEARCH = "mcts_search"
    ACTOR_MODEL = "actor_model"
