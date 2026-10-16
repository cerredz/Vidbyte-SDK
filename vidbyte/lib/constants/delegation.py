"""FILE: vidbyte/lib/constants/delegation.py

PURPOSE: Defines the named bounds of DelegationLimits and DelegationLimitsMiddleware: the smallest depth and batch caps a delegating agent may be given, and the depth of the agent the developer built, at the top of its tree.
ROLE IN CODEBASE: Read by DelegationLimits (vidbyte/lib/dataclasses/middleware.py) to check its caps and by DelegationLimitsMiddleware (vidbyte/middleware/builtins/delegation_limits.py) to check the depth it is given.
ARCHITECTURE NOTE: Immutable constants only; enforcement lives in the middleware. The bounds are generic: any agent that delegates through one tool, such as InfiniteMemoryAgent's launch_subagent, uses them.
COMMON MODIFICATION PATTERNS: Add a named constant here before writing another delegation policy literal in the record or the middleware.
KNOWN EDGE CASES: A cap of 1 is the smallest that still allows delegation: max_depth=1 lets only the top agent delegate, and max_parallel=1 lets one task run per call.
RELATED DOCS: vidbyte/middleware/README.md (Built-in middleware); vidbyte/agents/infinite/README.md
TESTS: tests/test_delegation_limits_middleware.py
"""

from __future__ import annotations

# The smallest depth and batch caps: one level of subagents, and one
# task per call, so neither cap can switch delegation off by being 0.
DELEGATION_MIN_CAP = 1

# The depth of the agent the developer built; each level of subagents
# below it is one deeper.
DELEGATION_ROOT_DEPTH = 0

__all__ = ["DELEGATION_MIN_CAP", "DELEGATION_ROOT_DEPTH"]
