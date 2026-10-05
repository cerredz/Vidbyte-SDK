"""Context Protocol Header

PURPOSE: Owns safe failures and result details for runtime skill-source resolution.
ROLE IN CODEBASE: Skill source adapters and Jev preload share these caller-facing diagnostics.
ARCHITECTURE NOTE: Messages use SDK-authored reasons and never include source bodies, credentials, or upstream response text.
COMMON MODIFICATION PATTERNS: Add stable failure categories here and preserve the eight-sentence actionable diagnostic.
KNOWN EDGE CASES: Provider status codes are useful; response excerpts and exception strings from transports are not safe to expose.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md.
TESTS: tests/test_jev_skill_providers.py and tests/test_jev_skill_remote_sources.py.
"""

from __future__ import annotations

from vidbyte.lib.errors.base import SourceError

SOURCE_FAILURE_DETAIL = """\
The configured skill source could not be resolved. Check that the source identifier and any pinned revision identify the intended skill.
Confirm that the skill exists and that its account can access it. For remote sources, check network access, credentials, and provider rate limits.
For local sources, check that SKILL.md is readable UTF-8, has valid frontmatter, and is within the SDK size limit.
Correct the source details or wait for a temporary service issue to clear, then retry.
This diagnostic omits source contents, credentials, and raw upstream response bodies.""".replace("\n", " ")
DUPLICATE_SOURCE_DETAIL = "Resolved skill name is ambiguous."
DECISION_FAILURE_DETAIL = "Skill relevance could not be evaluated."
UNSUPPORTED_NATIVE_DETAIL = "Native Claude skills require an Anthropic model."
OVERSIZED_DETAIL = "Skill candidate exceeds Jev's request size limit."
NATIVE_CAP_DETAIL = "Anthropic supports at most 20 skills per request."
_STATUS_MESSAGE_REPLACEMENT_COUNT = 1
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_REQUEST_TIMEOUT = 408
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_GATEWAY_TIMEOUT = 504
_HTTP_SERVER_ERROR_MIN = 500
_HTTP_SERVER_ERROR_MAX = 599


class SkillSourceError(SourceError):
    """A safe source lookup failure that Jev can record for one candidate."""

    DIAGNOSTIC_FIELDS = (
        "error_kind",
        "expected",
        "actual",
        "safe_runtime_details",
        "likely_causes",
        "repair_approaches",
        "related_docs",
        "relevant_tests",
    )

    def __init__(self, reason: str, *, source_kind: str = "configured", status_code: int | None = None) -> None:
        # Stores a source-specific reason while exposing only SDK-authored, actionable guidance.
        self.reason = reason.rstrip(" .")
        self.source_kind = source_kind
        self.status_code = status_code
        self.error_kind = "skill_source_resolution"
        self.expected = "The configured source should resolve to one valid SKILL.md or native Claude skill reference."
        self.actual = "The skill source was unavailable or did not satisfy the SDK source contract."
        self.safe_runtime_details = {"source_kind": source_kind, **({"status_code": status_code} if status_code is not None else {})}
        self.likely_causes = (
            "The source identifier, requested name, or pinned revision did not match an available skill.",
            "The source could not be read because of access, transport, encoding, response-size, or metadata validation failure.",
        )
        self.repair_approaches = (
            "Check the source identifier, pinned revision, and required access credentials.",
            "Confirm SKILL.md is readable UTF-8 with valid frontmatter, or check remote service availability and rate limits.",
        )
        self.related_docs = ("docs/design/jev-skill-providers.md", "field-guide/vidbyte-sdk/runtime-boundaries.md")
        self.relevant_tests = ("tests/test_jev_skill_providers.py", "tests/test_jev_skill_remote_sources.py")
        source = source_kind.replace("_", " ")
        detail = f"""\
The {source} skill source could not be resolved. Reason: {self.reason}.
Check that the source identifier and any pinned revision identify the intended skill.
Confirm that the skill exists and that its account can access it.
For remote sources, check network access, credentials, and provider rate limits.
For local sources, check that SKILL.md is readable UTF-8, has valid frontmatter, and is within the SDK size limit.
Correct the source details or wait for a temporary service issue to clear, then retry.
This diagnostic omits source contents, credentials, and raw upstream response bodies.""".replace("\n", " ")
        if status_code is not None:
            detail = detail.replace("Reason: ", f"Reason (HTTP {status_code}): ", _STATUS_MESSAGE_REPLACEMENT_COUNT)
        super().__init__(
            detail,
            details={
                "error_kind": self.error_kind,
                "expected": self.expected,
                "actual": self.actual,
                "safe_runtime_details": self.safe_runtime_details,
                "likely_causes": self.likely_causes,
                "repair_approaches": self.repair_approaches,
                "related_docs": self.related_docs,
                "relevant_tests": self.relevant_tests,
            },
        )


def provider_failure_reason(status_code: int | None, *, message: str | None = None) -> str:
    """Map an HTTP status to a safe explanation without reading provider response text."""
    if message == "Provider response exceeded the configured size ceiling.":
        return "the response exceeded the SDK size limit"
    if status_code in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
        return "the source service rejected the request or its credentials"
    if status_code == _HTTP_NOT_FOUND:
        return "the requested skill or pinned revision was not found"
    if status_code == _HTTP_TOO_MANY_REQUESTS:
        return "the source service is rate limiting requests"
    if status_code in (_HTTP_REQUEST_TIMEOUT, _HTTP_GATEWAY_TIMEOUT):
        return "the source service did not answer before the request timed out"
    if status_code is not None and _HTTP_SERVER_ERROR_MIN <= status_code <= _HTTP_SERVER_ERROR_MAX:
        return "the source service returned a temporary server error"
    if message in {"Provider returned invalid JSON.", "Provider returned non-object JSON."}:
        return "the source service returned data that the SDK could not parse"
    if status_code is not None:
        return f"the source service returned HTTP {status_code}"
    return "the remote request did not produce a usable response"


__all__ = [
    "DECISION_FAILURE_DETAIL",
    "DUPLICATE_SOURCE_DETAIL",
    "NATIVE_CAP_DETAIL",
    "OVERSIZED_DETAIL",
    "SOURCE_FAILURE_DETAIL",
    "SkillSourceError",
    "UNSUPPORTED_NATIVE_DETAIL",
    "provider_failure_reason",
]
