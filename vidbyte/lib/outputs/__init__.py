"""FILE: vidbyte/lib/outputs/__init__.py

PURPOSE: Re-exports the provider side of output delivery: the connector base, its helpers, and one connector class per destination.
ROLE IN CODEBASE: Imported by vidbyte/agents/output/__init__.py, which publishes the connectors next to the agent-side contract.
ARCHITECTURE NOTE: Provider work only; nothing in this package imports vidbyte.agents, and connectors satisfy OutputConnector structurally.
COMMON MODIFICATION PATTERNS: Add a new connector's import and its __all__ entry here together.
KNOWN EDGE CASES: The helper classes are exported for connector authors but are not root vidbyte exports.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/
"""

from __future__ import annotations

from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp, OutputSmtp
from vidbyte.lib.outputs.text import OutputText

__all__ = [
    "BaseOutput",
    "OutputArguments",
    "OutputHttp",
    "OutputSmtp",
    "OutputText",
]
