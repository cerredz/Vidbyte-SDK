"""Context Protocol Header

Path: vidbyte/tools/builtins/verified_context/__init__.py
Purpose: Export the verified dependency handle/source contracts and load tool.
Architecture: Contracts remain lower-level and reusable; long-running ledger adapters
implement the trusted source protocol.
Exports: VerifiedContextRef, VerifiedContextSource, and VerifiedContextLoadTool.
Invariants: Importing this package performs no ledger, artifact, or filesystem access.
Do not: Add arbitrary context lookup or unverified memory search here.
Related: vidbyte/tools/README.md and paradigms/long_running/context.py.
Tests: Existing import verification; no new tests by approved workflow.
"""

from vidbyte.tools.builtins.verified_context.contracts import VerifiedContextRef, VerifiedContextSource
from vidbyte.tools.builtins.verified_context.load import VerifiedContextLoadTool

__all__ = ["VerifiedContextLoadTool", "VerifiedContextRef", "VerifiedContextSource"]
