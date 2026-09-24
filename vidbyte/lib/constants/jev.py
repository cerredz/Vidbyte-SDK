"""FILE: vidbyte/lib/constants/jev.py

PURPOSE: Declares the TypeSafe Jev limits, defaults, and wire literals shared by the decision records and provider adapter.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates against these bounds and `vidbyte/providers/typesafe.py` builds requests from the same values.
ARCHITECTURE NOTE: Values live in `vidbyte.lib` so both lower-layer modules and the tool layer can import them without a layering inversion.
COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it; local sanity caps stay generous because the API enforces the real (token) limits itself.
KNOWN EDGE CASES: Vendor limits are the 255 Choice options and the 2-10 Score levels; question count, state size, and option-name length are local caps only.
RELATED DOCS: docs/design/jev-agent-scaffold.md, https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/sdk/python/api/retries.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
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

# JevAgent run state and the required-sequence done check (docs/design/jev-required-sequence.md).
# A sequence of one stage is just a task, and past twelve the stage list is almost certainly a plan
# rather than an order the user asked for; either bound makes the section inactive for the run.
JEV_REQUIRED_SEQUENCE_MIN_STAGES: int = 2
JEV_REQUIRED_SEQUENCE_MAX_STAGES: int = 12
# Rejected finish attempts sent back to the agent before the next rejection stops the run.
JEV_MAX_FINISH_REVIEW_CONTINUATIONS: int = 3
# One build plus one rebuild carrying the validation error of the first handoff.
JEV_HANDOFF_BUILD_ATTEMPTS: int = 2
# Builders answer in one JSON response; the headroom covers schema-repair turns only.
JEV_BUILDER_MAX_ITERATIONS: int = 4
# Longest single event body shown to the handoff builder before an explicit truncation marker.
JEV_EVENT_LOG_MAX_EVENT_CHARS: int = 4_000
JEV_EVENT_ID_PREFIX: str = "E"
JEV_STAGE_ID_PREFIX: str = "stage_"
JEV_RUN_REPORT_METADATA_KEY: str = "jev_run_report"

__all__ = [
    "JEV_BUILDER_MAX_ITERATIONS",
    "JEV_DEFAULT_MODEL",
    "JEV_DEFAULT_RETRY_COUNT",
    "JEV_DEFAULT_TIMEOUT_SECONDS",
    "JEV_EVENT_ID_PREFIX",
    "JEV_EVENT_LOG_MAX_EVENT_CHARS",
    "JEV_HANDOFF_BUILD_ATTEMPTS",
    "JEV_MAX_CHOICE_OPTIONS",
    "JEV_MAX_FINISH_REVIEW_CONTINUATIONS",
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
    "JEV_PROBABILITY_SUM_TOLERANCE",
    "JEV_REQUIRED_SEQUENCE_MAX_STAGES",
    "JEV_REQUIRED_SEQUENCE_MIN_STAGES",
    "JEV_RETRY_BACKOFF_SECONDS",
    "JEV_RETRY_STATUS_CODES",
    "JEV_RUN_REPORT_METADATA_KEY",
    "JEV_STAGE_ID_PREFIX",
    "JEV_STATUS_OVERLOADED",
    "JEV_STATUS_RATE_LIMITED",
    "JEV_STATUS_REQUEST_TIMEOUT",
    "JEV_STATUS_SERVER_ERROR_CEILING",
    "JEV_STATUS_SERVER_ERROR_FLOOR",
    "JEV_STATUS_UNAUTHORIZED",
    "JEV_STATUS_UNPROCESSABLE",
    "JEV_SYSTEMONE_PATH",
    "JEV_TIMEOUT_FLOOR_SECONDS",
]
