"""FILE: vidbyte/lib/constants/jev.py

PURPOSE: Declares the TypeSafe Jev limits, defaults, and wire literals shared by the decision records and provider adapter.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates against these bounds and `vidbyte/providers/typesafe.py` builds requests from the same values.
ARCHITECTURE NOTE: Values live in `vidbyte.lib` so both lower-layer modules and the tool layer can import them without a layering inversion.
COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it; widen local sanity caps only with a reason in the design doc.
KNOWN EDGE CASES: JEV_MAX_OPTIONS is TypeSafe's documented 255-option ceiling; JEV_MAX_QUESTIONS and JEV_MAX_STATE_CHARS are local caps, not vendor limits.
RELATED DOCS: docs/design/jev-agent-scaffold.md and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from vidbyte.lib.enums.jev import JevQuestionType

JEV_DEFAULT_MODEL: str = "jev-latest"
JEV_SYSTEMONE_PATH: str = "/systemone"
JEV_MIN_OPTIONS: int = 2
JEV_MAX_OPTIONS: int = 255
JEV_MAX_OPTION_NAME_CHARS: int = 200
JEV_MAX_QUESTIONS: int = 64
JEV_MAX_STATE_CHARS: int = 200_000
JEV_DEFAULT_TIMEOUT_SECONDS: float = 10.0
JEV_DEFAULT_RETRY_COUNT: int = 0
JEV_NO_RETRIES: int = 0
JEV_TIMEOUT_FLOOR_SECONDS: float = 0.0
JEV_MAX_RESPONSE_BYTES: int = 1_000_000
JEV_STATUS_UNAUTHORIZED: int = 401
JEV_STATUS_UNPROCESSABLE: int = 422
JEV_STATUS_RATE_LIMITED: int = 429
JEV_STATUS_OVERLOADED: int = 529
JEV_RETRY_STATUS_CODES: tuple[int, ...] = (JEV_STATUS_RATE_LIMITED, JEV_STATUS_OVERLOADED)
JEV_NOUL_TRUE: str = "true"
JEV_NOUL_FALSE: str = "false"
JEV_NOUL_OPTIONS: tuple[str, ...] = (JEV_NOUL_TRUE, JEV_NOUL_FALSE)
JEV_DECIDE_QUESTION_NAME: str = "decision"
JEV_DECIDE_ANSWER_TYPES: tuple[str, ...] = (JevQuestionType.CHOICE.value, JevQuestionType.SCORE.value)
JEV_REDACTED: str = "<redacted>"

__all__ = [
    "JEV_DECIDE_ANSWER_TYPES",
    "JEV_DECIDE_QUESTION_NAME",
    "JEV_DEFAULT_MODEL",
    "JEV_DEFAULT_RETRY_COUNT",
    "JEV_DEFAULT_TIMEOUT_SECONDS",
    "JEV_MAX_OPTIONS",
    "JEV_MAX_OPTION_NAME_CHARS",
    "JEV_MAX_QUESTIONS",
    "JEV_MAX_RESPONSE_BYTES",
    "JEV_MAX_STATE_CHARS",
    "JEV_MIN_OPTIONS",
    "JEV_NOUL_FALSE",
    "JEV_NOUL_OPTIONS",
    "JEV_NOUL_TRUE",
    "JEV_NO_RETRIES",
    "JEV_REDACTED",
    "JEV_RETRY_STATUS_CODES",
    "JEV_STATUS_OVERLOADED",
    "JEV_STATUS_RATE_LIMITED",
    "JEV_STATUS_UNAUTHORIZED",
    "JEV_STATUS_UNPROCESSABLE",
    "JEV_SYSTEMONE_PATH",
    "JEV_TIMEOUT_FLOOR_SECONDS",
]
