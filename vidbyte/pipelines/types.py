"""Context Protocol Header

Description:
    Type aliases for pipeline stage nodes.
Purpose:
    Centralises the PipelineNode union so base.py and concrete pipeline files
    share a single import rather than duplicating the forward-reference string.
Architecture:
    - PipelineNode: Union of the VidbyteAgent protocol and BasePipeline; accepted
      as a stage by all pipeline constructors.
Relations:
    Used by vidbyte.pipelines.base and all concrete pipeline implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from vidbyte.lib.agents.protocol import VidbyteAgent
    from vidbyte.pipelines.base import BasePipeline

# Any agent satisfying the shared call contract, or a nested pipeline. Naming the
# protocol rather than one agent class keeps this module from depending on an
# implementation, and makes BasePipeline._invoke's dispatch a checked call.
PipelineNode = Union["VidbyteAgent", "BasePipeline"]

__all__ = ["PipelineNode"]
