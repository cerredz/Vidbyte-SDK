"""FILE: tests/test_output_text_truncate_marker.py

PURPOSE: Proves the marker option of OutputText.truncate that the InfiniteMemory events and handoff use: the cut keeps the caller's marker inside the limit, a one-line text stays one line, a text within the limit is unchanged, and a call without the option still ends with OUTPUT_TRUNCATION_MARKER.
ROLE IN CODEBASE: Unit tests for vidbyte/lib/outputs/text.py, row 24 of docs/spec/infinite-memory-events/spec.md section 12.3 (AC-37 e; INV-12, INV-38; FR-23). The output connector tests in tests/features/agent_output_connectors/ keep pinning the default marker through their own callers.
ARCHITECTURE NOTE: The expected strings are written out from the spec (the infinite marker is " … [cut]"), never read from the constants, so a changed marker or an off-by-one cut shows up as a mismatch.
FUNCTION INVENTORY: test_truncate_keeps_the_callers_marker_inside_the_limit_and_the_default_is_unchanged (AC-37 e, INV-12, INV-38).
COMMON MODIFICATION PATTERNS: A new truncate option adds one case here beside the default case, in the same test, so the default is proven unchanged by the same run.
WHAT NOT TO DO IN THIS FILE: 1. Do not split the default-marker case into its own test; alone it passes before the option exists. 2. Do not import the infinite marker constant to build the expectation.
KNOWN EDGE CASES: The default marker starts with two line breaks, so a default cut of a one-line text is no longer one line; the infinite marker has none, which is why events pass it.
RELATED DOCS: vidbyte/lib/outputs/README.md; docs/spec/infinite-memory-events/spec.md sections 6.1 (INV-12, INV-38), 8.5 and 12.3; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_output_text_truncate_marker.py -q
"""

from __future__ import annotations

from vidbyte.lib.constants.outputs import OUTPUT_TRUNCATION_MARKER
from vidbyte.lib.outputs.text import OutputText

INFINITE_MARKER = " … [cut]"


def test_truncate_keeps_the_callers_marker_inside_the_limit_and_the_default_is_unchanged() -> None:
    """AC-37 (e), INV-12, INV-38: truncate("a" * 50, 20, marker=" … [cut]") is 12 characters plus the marker, exactly 20 long and still one line; a text within the limit comes back unchanged; without marker the cut still ends with OUTPUT_TRUNCATION_MARKER and is 20 long."""
    cut = OutputText.truncate("a" * 50, 20, marker=INFINITE_MARKER)
    assert cut == "a" * 12 + INFINITE_MARKER and len(cut) == 20
    assert cut.splitlines() == [cut]
    assert OutputText.truncate("a" * 20, 20, marker=INFINITE_MARKER) == "a" * 20
    default = OutputText.truncate("a" * 50, 20)
    assert default == "a" * (20 - len(OUTPUT_TRUNCATION_MARKER)) + OUTPUT_TRUNCATION_MARKER and len(default) == 20
