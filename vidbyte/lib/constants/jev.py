"""FILE: vidbyte/lib/constants/jev.py

PURPOSE: Declares the TypeSafe Jev limits, defaults, and wire literals shared by the decision records and provider adapter, plus the JevAgent preflight policy values.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates against these bounds, `vidbyte/providers/typesafe.py` builds requests from the same values, `vidbyte/lib/jev/` reads the preflight policy values, and `vidbyte/agents/jev/` reads the tool-selector and clarification values.
ARCHITECTURE NOTE: Values live in `vidbyte.lib` so both lower-layer modules and the tool layer can import them without a layering inversion.
COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it; local sanity caps stay generous because the API enforces the real (token) limits itself.
KNOWN EDGE CASES: Vendor limits are the 255 Choice options and the 2-10 Score levels; question count, state size, and option-name length are local caps only.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/sdk/python/api/retries.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

# Models and endpoints (https://docs.typesafe.ai/models.md). `jev-latest` and `jev-preview`
# are aliases; the response reports the versioned ID (currently `jev-1.13.0`) that answered.
JEV_DEFAULT_MODEL: str = "jev-latest"
JEV_PREVIEW_MODEL: str = "jev-preview"
JEV_SYSTEMONE_PATH: str = "/systemone"
JEV_MODELS_PATH: str = "/models"

# Documented vendor limits (https://docs.typesafe.ai/api.md#question-types).
JEV_MAX_CHOICE_OPTIONS: int = 255
JEV_MIN_SCORE_LEVELS: int = 2
JEV_MAX_SCORE_LEVELS: int = 10

# Local sanity caps. TypeSafe bounds a request by tokens (64k per request, 32k for the state plus
# the longest question), not by these counts, so each cap sits far above anything that fits.
JEV_MIN_CHOICE_OPTIONS: int = 2
JEV_MAX_OPTION_NAME_CHARS: int = 4_096
JEV_MAX_QUESTIONS: int = 10_000
JEV_MAX_STATE_CHARS: int = 1_000_000
JEV_PROBABILITY_SUM_TOLERANCE: float = 0.01

# Transport defaults. The timeout is deliberately longer than the TypeSafe SDK's 10 seconds so a
# large fan-out request is not cut off; retries mirror the SDK's RetryPolicy defaults
# (max_retries=2, 0.5s initial backoff doubling, statuses 408, 429, and every 5xx including 529).
JEV_DEFAULT_TIMEOUT_SECONDS: float = 60.0
JEV_DEFAULT_RETRY_COUNT: int = 2
JEV_NO_RETRIES: int = 0
JEV_TIMEOUT_FLOOR_SECONDS: float = 0.0
JEV_RETRY_BACKOFF_SECONDS: float = 0.5
JEV_MAX_RESPONSE_BYTES: int = 16_000_000

# HTTP statuses the API documents (https://docs.typesafe.ai/api.md#errors).
JEV_STATUS_REQUEST_TIMEOUT: int = 408
JEV_STATUS_UNAUTHORIZED: int = 401
JEV_STATUS_UNPROCESSABLE: int = 422
JEV_STATUS_RATE_LIMITED: int = 429
JEV_STATUS_OVERLOADED: int = 529
JEV_STATUS_SERVER_ERROR_FLOOR: int = 500
JEV_STATUS_SERVER_ERROR_CEILING: int = 600
JEV_RETRY_STATUS_CODES: tuple[int, ...] = (JEV_STATUS_REQUEST_TIMEOUT, JEV_STATUS_RATE_LIMITED, *range(JEV_STATUS_SERVER_ERROR_FLOOR, JEV_STATUS_SERVER_ERROR_CEILING))

# Noul wire literals: the optional criteria keys and the two outcomes a noul answer expands to.
JEV_NOUL_TRUE: str = "true"
JEV_NOUL_FALSE: str = "false"
JEV_NOUL_OPTIONS: tuple[str, ...] = (JEV_NOUL_TRUE, JEV_NOUL_FALSE)
JEV_NOUL_YES_THRESHOLD: float = 0.5

# Preflight policy. The request is the only state field preflight questions read, and a fixed-question
# preset's score is the mean P(yes) of its questions; below the threshold the preset fails.
# 0.75 is a starting point, not a value tuned on a labeled set.
JEV_PREFLIGHT_REQUEST_FIELD: str = "request"
JEV_CLARITY_THRESHOLD: float = 0.75
# A run the preflight gate stops reports this strategy name.
JEV_PREFLIGHT_STRATEGY_NAME: str = "jev_preflight"
# JevClarificationAgent limits: its loop and token budget, and the size of the structured reply it must
# return (a few clarifying questions, each with a few recommended answers the user can pick from).
JEV_CLARIFICATION_MAX_ITERATIONS: int = 25
JEV_CLARIFICATION_MAX_TOKENS: int = 100_000
JEV_CLARIFICATION_MAX_QUESTIONS: int = 6
JEV_CLARIFICATION_MIN_RECOMMENDATIONS: int = 2
JEV_CLARIFICATION_MAX_RECOMMENDATIONS: int = 4

# Tool-selector policy bounds and default: caller settings use probabilities on the closed unit interval.
JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD: float = 0.20
JEV_TOOL_SELECTOR_MAX_THRESHOLD: float = 1.0
JEV_TOOL_SELECTOR_MIN_THRESHOLD: float = 0.0

__all__ = [
    "JEV_CLARIFICATION_MAX_ITERATIONS",
    "JEV_CLARIFICATION_MAX_QUESTIONS",
    "JEV_CLARIFICATION_MAX_RECOMMENDATIONS",
    "JEV_CLARIFICATION_MAX_TOKENS",
    "JEV_CLARIFICATION_MIN_RECOMMENDATIONS",
    "JEV_CLARITY_THRESHOLD",
    "JEV_DEFAULT_MODEL",
    "JEV_DEFAULT_RETRY_COUNT",
    "JEV_DEFAULT_TIMEOUT_SECONDS",
    "JEV_MAX_CHOICE_OPTIONS",
    "JEV_MAX_OPTION_NAME_CHARS",
    "JEV_MAX_QUESTIONS",
    "JEV_MAX_RESPONSE_BYTES",
    "JEV_MAX_SCORE_LEVELS",
    "JEV_MAX_STATE_CHARS",
    "JEV_MIN_CHOICE_OPTIONS",
    "JEV_MIN_SCORE_LEVELS",
    "JEV_MODELS_PATH",
    "JEV_NOUL_FALSE",
    "JEV_NOUL_OPTIONS",
    "JEV_NOUL_TRUE",
    "JEV_NOUL_YES_THRESHOLD",
    "JEV_NO_RETRIES",
    "JEV_PREVIEW_MODEL",
    "JEV_PREFLIGHT_REQUEST_FIELD",
    "JEV_PREFLIGHT_STRATEGY_NAME",
    "JEV_PROBABILITY_SUM_TOLERANCE",
    "JEV_RETRY_BACKOFF_SECONDS",
    "JEV_RETRY_STATUS_CODES",
    "JEV_STATUS_OVERLOADED",
    "JEV_STATUS_RATE_LIMITED",
    "JEV_STATUS_REQUEST_TIMEOUT",
    "JEV_STATUS_SERVER_ERROR_CEILING",
    "JEV_STATUS_SERVER_ERROR_FLOOR",
    "JEV_STATUS_UNAUTHORIZED",
    "JEV_STATUS_UNPROCESSABLE",
    "JEV_SYSTEMONE_PATH",
    "JEV_TIMEOUT_FLOOR_SECONDS",
    "JEV_TOOL_SELECTOR_DEFAULT_THRESHOLD",
    "JEV_TOOL_SELECTOR_MAX_THRESHOLD",
    "JEV_TOOL_SELECTOR_MIN_THRESHOLD",
]
