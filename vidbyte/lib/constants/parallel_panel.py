"""Context Protocol Header

Description:
    Public safety limits and prompt-field constants for Parallel Panel.
Purpose:
    Keeps Parallel Panel configuration bounds centralized under lib/constants so
    the public algorithm config and runtime adapter share one source of truth.
Architecture:
    - Integer and character ceilings used by ParallelPanelAlgorithm validation.
    - Required reviewer-prompt placeholder set for exact-input rendering.
Relations:
    Imported by vidbyte.context.algorithms.parallel_panel.
"""

from __future__ import annotations

MAX_REVIEWERS = 16
MAX_TIMEOUT_SECONDS = 3_600.0
MAX_CANDIDATE_CHARS = 100_000
MAX_REVIEW_CHARS = 100_000
MAX_ARTIFACT_CHARS = 100_000
MAX_TOTAL_ARTIFACT_CHARS = 1_000_000
MAX_ARTIFACT_NAME_CHARS = 256
REQUIRED_REVIEW_PROMPT_FIELDS = frozenset({"task", "candidate", "artifacts"})
NO_ARTIFACTS_PLACEHOLDER = "No permitted artifacts."
REVIEW_TRUNCATION_SUFFIX = "\n...[review truncated]"

__all__ = [
    "MAX_ARTIFACT_CHARS",
    "MAX_ARTIFACT_NAME_CHARS",
    "MAX_CANDIDATE_CHARS",
    "MAX_REVIEWERS",
    "MAX_REVIEW_CHARS",
    "MAX_TIMEOUT_SECONDS",
    "MAX_TOTAL_ARTIFACT_CHARS",
    "NO_ARTIFACTS_PLACEHOLDER",
    "REQUIRED_REVIEW_PROMPT_FIELDS",
    "REVIEW_TRUNCATION_SUFFIX",
]
