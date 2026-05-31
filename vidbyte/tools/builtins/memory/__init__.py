"""Context Protocol Header

Description:
    Exports all memory provider tool classes for the Vidbyte SDK.
Purpose:
    Gives developers a single import path for all five memory provider tool sets:
    Supermemory, Mem0, Zep, Cognee, and Letta.
Architecture:
    - Each provider module exports 3-4 BaseTool subclasses.
    - All are re-exported here for convenient flat-namespace access.
Relations:
    Re-exported by vidbyte.tools.builtins and accessible via the memory sub-namespace.
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.cognee import (
    CogneeAddTool,
    CogneeCognifyTool,
    CogneeDeleteTool,
    CogneeSearchTool,
)
from vidbyte.tools.builtins.memory.letta import (
    LettaAddArchivalMemoryTool,
    LettaDeleteArchivalMemoryTool,
    LettaGetMemoryBlockTool,
    LettaSearchArchivalMemoryTool,
)
from vidbyte.tools.builtins.memory.mem0 import (
    Mem0AddMemoryTool,
    Mem0DeleteMemoryTool,
    Mem0GetMemoriesTool,
    Mem0SearchMemoryTool,
)
from vidbyte.tools.builtins.memory.supermemory import (
    SupermemoryAddMemoryTool,
    SupermemoryDeleteMemoryTool,
    SupermemorySearchMemoryTool,
)
from vidbyte.tools.builtins.memory.zep import (
    ZepAddMemoryTool,
    ZepDeleteSessionTool,
    ZepGetMemoryTool,
    ZepSearchMemoryTool,
)

__all__ = [
    # Supermemory
    "SupermemoryAddMemoryTool",
    "SupermemorySearchMemoryTool",
    "SupermemoryDeleteMemoryTool",
    # Mem0
    "Mem0AddMemoryTool",
    "Mem0SearchMemoryTool",
    "Mem0GetMemoriesTool",
    "Mem0DeleteMemoryTool",
    # Zep
    "ZepAddMemoryTool",
    "ZepGetMemoryTool",
    "ZepSearchMemoryTool",
    "ZepDeleteSessionTool",
    # Cognee
    "CogneeAddTool",
    "CogneeCognifyTool",
    "CogneeSearchTool",
    "CogneeDeleteTool",
    # Letta
    "LettaAddArchivalMemoryTool",
    "LettaSearchArchivalMemoryTool",
    "LettaDeleteArchivalMemoryTool",
    "LettaGetMemoryBlockTool",
]
