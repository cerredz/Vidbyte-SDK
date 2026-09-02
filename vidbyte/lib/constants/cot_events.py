"""Context Protocol Header

FILE: vidbyte/lib/constants/cot_events.py

PURPOSE: Owns the numeric bounds, defaults, display labels, and collection
limits shared by the deep chain-of-thought event tools and primitives. This
module stores stable configuration values only; it does not validate input,
construct tool specifications, or render context.

ROLE IN CODEBASE: `vidbyte/tools/builtins/cot_events.py` imports parser bounds
and tool defaults. `vidbyte/context/primitives/cot_events.py` imports the
rendering defaults and titles. The enum members used to derive categorical
defaults are defined in `vidbyte/lib/enums/cot_events.py`.

ARCHITECTURE NOTE: Centralizing these values under `vidbyte.lib` keeps public
SDK contracts independent from the builtins implementation and prevents
numeric or display drift between tool schemas and context records.

FUNCTION INVENTORY: This module exports constants only; it defines no public
functions and raises no runtime errors.

COMMON MODIFICATION PATTERNS: Change a shared bound or default here, then
inspect every tool parser, primitive renderer, design-doc requirement, and
smoke check that consumes it. Add a new categorical value in the enum module,
not as a second tuple in this file.

WHAT NOT TO DO IN THIS FILE:
1. Do not add parsing or validation logic; that belongs to
   `vidbyte/tools/builtins/cot_events.py`.
2. Do not add model-facing prose; descriptions belong to the tool specs.
3. Do not place provider pricing, runtime policy, or persistence settings here.

KNOWN EDGE CASES: Confidence bounds are inclusive and optional confidence
values may remain `None` after parsing. The rejected-alternative limit is an
input cap, so callers must still validate the shape of every retained entry.

RELATED DOCS: `https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/deep-cot-tools.md`
describes the values' consumers and lifecycle.

AUTO-GENERATED FLAG: No; maintained source data.

TESTS: No dedicated test file exists in the source PR; import and value
smoke checks are part of resolver verification.

CONCURRENCY MODEL: Immutable module-level values; no shared mutable state.
"""

from __future__ import annotations

from vidbyte.lib.enums.cot_events import (
    AssumptionAction,
    BasisType,
    ImpactLevel,
    ReturnableOption,
    Reversibility,
)

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
MAX_REJECTED_ALTERNATIVES = 3
DEFAULT_MAX_CHARS = 2000

DEFAULT_BASIS_TYPE = BasisType.INFERENCE.value
DEFAULT_REVERSIBLE = Reversibility.YES.value
DEFAULT_IMPACT_IF_WRONG = ImpactLevel.MAJOR.value
DEFAULT_RETURNABLE = ReturnableOption.YES.value
DEFAULT_SALVAGE = "nothing"

HYPOTHESIS_TITLE = "Hypothesis"
DECISION_TITLE = "Decision"
ASSUMPTION_CHECK_TITLE = "Assumption Check"
UNCERTAINTY_TITLE = "Uncertainty Reading"
BACKTRACK_TITLE = "Backtrack"

DEFAULT_ASSUMPTION_ACTION = AssumptionAction.DECLARED.value

__all__ = [
    "ASSUMPTION_CHECK_TITLE",
    "BACKTRACK_TITLE",
    "DECISION_TITLE",
    "DEFAULT_ASSUMPTION_ACTION",
    "DEFAULT_BASIS_TYPE",
    "DEFAULT_IMPACT_IF_WRONG",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_RETURNABLE",
    "DEFAULT_REVERSIBLE",
    "DEFAULT_SALVAGE",
    "HYPOTHESIS_TITLE",
    "MAX_CONFIDENCE",
    "MAX_REJECTED_ALTERNATIVES",
    "MIN_CONFIDENCE",
    "UNCERTAINTY_TITLE",
]
