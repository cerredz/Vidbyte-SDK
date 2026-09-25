"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: TypeSafe question types, JevAgent preflight presets, security actions, and security categories.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, and `vidbyte/lib/jev/` keys its presets and preflight questions by the rest.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one; add a JevSecurityCategory member together with its question dataclass in `vidbyte/lib/jev/preflight/security.py`.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. Security category values are public response flag names, so renaming one breaks callers.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-sensitive-data.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_tool_selector.py, and tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class JevQuestionType(str, Enum):
    """TypeSafe System One question types."""

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the serialized values in declaration order."""
        return tuple(member.value for member in cls)


class JevPreflightPreset(StrEnum):
    """Named Jev preflight capabilities a caller can enable on JevAgent."""

    TOOL_SELECTOR = "tool_selector"
    SECURITY = "security"


class JevSecurityAction(StrEnum):
    """What JevAgent does when the security preflight detects sensitive data in a request."""

    BLOCK = "block"
    PAUSE = "pause"
    REPORT = "report"
    CONTAIN = "contain"


class JevSecurityCategory(StrEnum):
    """The sensitive-data categories the security preflight asks Jev about, one question each."""

    PASSWORDS_PINS = "passwords_pins"
    API_SERVICE_SECRETS = "api_service_secrets"
    SESSION_TOKENS = "session_tokens"
    PRIVATE_CRYPTO_MATERIAL = "private_crypto_material"
    PERSONAL_CONTACT = "personal_contact"
    GOVERNMENT_IDS = "government_ids"
    PAYMENT_BANK = "payment_bank"
    PERSONAL_FINANCES = "personal_finances"
    HEALTH = "health"
    BIOMETRIC_GENETIC = "biometric_genetic"
    PRECISE_LOCATION = "precise_location"
    MINORS_STUDENTS = "minors_students"
    SENSITIVE_TRAITS = "sensitive_traits"
    EMPLOYMENT_HR = "employment_hr"
    LEGAL_MATTERS = "legal_matters"
    CUSTOMER_CLIENT_RECORDS = "customer_client_records"
    CONFIDENTIAL_COMMUNICATIONS = "confidential_communications"
    PROPRIETARY_WORK = "proprietary_work"
    INTERNAL_BUSINESS = "internal_business"
    SECURITY_SYSTEM_DETAILS = "security_system_details"


__all__ = ["JevPreflightPreset", "JevQuestionType", "JevSecurityAction", "JevSecurityCategory"]
