"""FILE: tests/features/sdk_loop_settings/test_tool_result_cap.py

PURPOSE: Prove tool-result limits bound the full model-visible text, including the truncation notice.
ROLE IN CODEBASE: Exercises ToolSettings.truncate with real ToolResult values, without a provider.
ARCHITECTURE NOTE: The output and metadata are public SDK behavior; no private helper is mocked.
FUNCTION INVENTORY: test_truncated_result_fits_limit probes zero, tiny, and large caps;
    test_exact_limit_keeps_original_result guards the no-truncation boundary.
COMMON MODIFICATION PATTERNS: Add a boundary case when the notice or metadata shape changes.
WHAT NOT TO DO IN THIS FILE: 1. Do not make provider requests; agent runtime tests own that boundary.
KNOWN EDGE CASES: A notice longer than the cap must not leak past it; metadata counts original payload characters.
RELATED DOCS: tests/features/sdk_loop_settings/FEATURE.md defines the configuration and output contract.
TESTS: This module; full gate via scripts/run_ci.py.
"""

from __future__ import annotations

import pytest

from vidbyte.agents.settings import ToolSettings
from vidbyte.tools import ToolResult


@pytest.mark.parametrize("limit", [0, 1, 2, 3, 5, 40, 41, 42, 80])
def test_truncated_result_fits_limit(limit: int) -> None:
    raw = ToolResult.success("lookup", "sensitive-long-text" * 10, metadata={"source": "local"})

    visible = ToolSettings(result_max_chars=limit).truncate(raw)

    assert len(visible.output) <= limit
    assert visible.metadata["tool_settings_truncated"] is True
    assert visible.metadata["original_chars"] == len(raw.output)
    assert visible.metadata["visible_chars"] + visible.metadata["truncated_chars"] == len(raw.output)
    assert visible.output.startswith(raw.output[:visible.metadata["visible_chars"]])
    if limit == 5:
        assert visible.output == "se..."
        assert visible.metadata["visible_chars"] == 2
    assert visible.metadata["source"] == "local"
    assert raw.output == "sensitive-long-text" * 10
    assert raw.metadata == {"source": "local"}


def test_exact_limit_keeps_original_result() -> None:
    raw = ToolResult.success("lookup", "short")

    assert ToolSettings(result_max_chars=len(raw.output)).truncate(raw) is raw
    assert ToolSettings().truncate(raw) is raw
