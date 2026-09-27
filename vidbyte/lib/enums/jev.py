"""FILE: vidbyte/lib/enums/jev.py

PURPOSE: Defines the closed Jev vocabularies: the TypeSafe question types, the preflight presets a JevAgent user can enable, and the key of every preflight question.
ROLE IN CODEBASE: `vidbyte/lib/dataclasses/jev.py` validates questions against these members, `vidbyte/providers/typesafe.py` serializes question types onto the wire, `vidbyte/lib/jev/presets.py` maps each fixed-question preset to its question keys, `vidbyte/lib/jev/preflight/` registers one question per key, and `vidbyte/agents/jev/gate/` matches on the presets when it acts on Jev's answers.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the provider layer, the record layer, and the tool layer all read it, and the lower two may not import the tool layer.
COMMON MODIFICATION PATTERNS: Add a question type only when TypeSafe documents one, then extend JevQuestion validation and TypeSafeProvider answer normalization in the same change. Add a preflight question key together with its question dataclass in `vidbyte/lib/jev/preflight/` and its preset's key list in `vidbyte/lib/jev/presets.py`.
KNOWN EDGE CASES: `noul` is TypeSafe's own spelling for a yes/no question; keep the serialized value exactly as the API expects it. A question key's value is the answer name Jev returns, so it must stay unique across every preset. TOOL_SELECTOR has no question keys because it asks one question per configured tool, built at run time.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, and https://docs.typesafe.ai/api.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, scripts/test-jev-agent-scaffold.py, and scripts/test-jev-preflight.py.
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


class JevPreflightPreset(str, Enum):
    """The preflight flags a JevAgent user can enable; each one turns on a fixed policy that JevPreflightGate (fixed-question presets) or the tool selector acts on."""

    CLARITY = "clarity"
    TOOL_SELECTOR = "tool_selector"
    SECURITY = "security"


class JevPreflightQuestionKey(str, Enum):
    """The key of every fixed preflight question, prefixed by the preset that asks it.

    The value is the question name sent to Jev and the key its answer comes back under.
    """

    CLARITY_ACTION = "clarity.action"
    CLARITY_OBJECT = "clarity.object"
    CLARITY_DELIVERABLE = "clarity.deliverable"
    CLARITY_TARGET = "clarity.target"
    CLARITY_REFERENCES = "clarity.references"
    CLARITY_SCOPE_PARTS = "clarity.scope_parts"
    CLARITY_SCOPE_SIZE = "clarity.scope_size"
    CLARITY_COMPLETION = "clarity.completion"
    CLARITY_INFORMATION = "clarity.information"
    CLARITY_CONSTRAINTS = "clarity.constraints"
    CLARITY_PRIORITIES = "clarity.priorities"
    CLARITY_CONSISTENCY = "clarity.consistency"
    CLARITY_TIME_CONTEXT = "clarity.time_context"
    CLARITY_SINGLE_READING = "clarity.single_reading"

    SECURITY_PASSWORDS_PINS = "security.passwords_pins"
    SECURITY_API_SERVICE_SECRETS = "security.api_service_secrets"
    SECURITY_SESSION_TOKENS = "security.session_tokens"
    SECURITY_PRIVATE_CRYPTO_MATERIAL = "security.private_crypto_material"
    SECURITY_PERSONAL_CONTACT = "security.personal_contact"
    SECURITY_GOVERNMENT_IDS = "security.government_ids"
    SECURITY_PAYMENT_BANK = "security.payment_bank"
    SECURITY_PERSONAL_FINANCES = "security.personal_finances"
    SECURITY_HEALTH = "security.health"
    SECURITY_BIOMETRIC_GENETIC = "security.biometric_genetic"
    SECURITY_PRECISE_LOCATION = "security.precise_location"
    SECURITY_MINORS_STUDENTS = "security.minors_students"
    SECURITY_SENSITIVE_TRAITS = "security.sensitive_traits"
    SECURITY_EMPLOYMENT_HR = "security.employment_hr"
    SECURITY_LEGAL_MATTERS = "security.legal_matters"
    SECURITY_CUSTOMER_CLIENT_RECORDS = "security.customer_client_records"
    SECURITY_CONFIDENTIAL_COMMUNICATIONS = "security.confidential_communications"
    SECURITY_PROPRIETARY_WORK = "security.proprietary_work"
    SECURITY_INTERNAL_BUSINESS = "security.internal_business"
    SECURITY_SYSTEM_DETAILS = "security.security_system_details"


class JevSecurityAction(StrEnum):
    """What JevAgent does when the security preflight detects sensitive data."""

    BLOCK = "block"
    PAUSE = "pause"
    REPORT = "report"
    CONTAIN = "contain"


class JevSecurityCategory(StrEnum):
    """Sensitive-data categories reported by the security preflight."""

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


__all__ = ["JevPreflightPreset", "JevPreflightQuestionKey", "JevQuestionType", "JevSecurityAction", "JevSecurityCategory"]
