"""Context Protocol Header

Description:
    Type aliases for pipeline stage nodes.
Purpose:
    Centralises the PipelineNode union so base.py and concrete pipeline files
    share a single import rather than duplicating the forward-reference string.
Architecture:
    - PipelineNode: Union of BaseAgent and BasePipeline; accepted as a stage
      by all pipeline constructors.
Relations:
    Used by vidbyte.pipelines.base and all concrete pipeline implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.pipelines.base import BasePipeline

PipelineNode = Union["BaseAgent", "BasePipeline"]

__all__ = ["PipelineNode"]
