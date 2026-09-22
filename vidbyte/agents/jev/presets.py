"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Defines named, fixed Jev preflight policies and their internal questions.
ROLE IN CODEBASE: JevAgentSettings accepts the public preset objects and JevRuntime executes their registered policy.
ARCHITECTURE NOTE: Callers select named capabilities; question wording and answer mapping remain internal policy.
COMMON MODIFICATION PATTERNS: Add a named immutable preset and keep its questions and action contract together.
KNOWN EDGE CASES: Security questions share positive polarity; one positive flag is sufficient to trigger on_detected.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums.jev import JevQuestionType
from vidbyte.lib.errors import ConfigurationError


class SecurityAction(StrEnum):
    """Action JevAgent takes when a security question detects sensitive input."""

    BLOCK = "block"
    PAUSE = "pause"
    REPORT = "report"


@dataclass(frozen=True, slots=True)
class SecurityPreset:
    """Options for the fixed sensitive-data security preflight."""

    on_detected: SecurityAction = SecurityAction.BLOCK

    def __post_init__(self) -> None:
        # Normalizes the documented enum/string form and rejects unknown actions at construction.
        try:
            normalized = self.on_detected if isinstance(self.on_detected, SecurityAction) else SecurityAction(self.on_detected)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("Preset.Security.on_detected must be 'block', 'pause', or 'report'.") from exc
        object.__setattr__(self, "on_detected", normalized)


class Preset:
    """Namespace for named, opinionated Jev preflight preset settings."""

    Security = SecurityPreset


_SECURITY_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("passwords_pins", "Does the request contain a real or plausibly real password, passphrase, or PIN? Count values that appear usable to sign in or unlock a private resource, even when embedded in a longer example. Do not count instructions that merely discuss passwords or clearly fake placeholders such as YOUR_PASSWORD."),
    ("api_service_secrets", "Does the request contain an API key, service token, client secret, or database credential? Count values that could grant access to an account, service, or data store, including values labeled examples when they look usable. Do not count variable names, instructions to create credentials, or obvious placeholder strings."),
    ("session_tokens", "Does the request contain a session cookie, access token, refresh token, or authentication code? Count bearer values, cookie contents, and one-time codes that could authenticate a person or application. Do not count protocol descriptions or visibly fabricated token placeholders."),
    ("private_crypto_material", "Does the request contain a private key, recovery phrase, seed phrase, signing secret, or equivalent cryptographic material? Count content that could decrypt, sign, or restore access to protected data or accounts. Do not count public keys, public wallet addresses, or general cryptography discussion."),
    ("personal_contact", "Does the request identify a private person through their name together with an email address, phone number, or home address? Count contact details tied to a real or plausibly real individual, including details in pasted correspondence or records. Do not count public business contact pages or fictional examples clearly marked as such."),
    ("government_ids", "Does the request contain a government-issued identity number or a readable transcription of an identity document? Count passport, national identity, tax identity, or driver's license details tied to a person. Do not count instructions about these documents or a masked value that cannot identify or authenticate anyone."),
    ("payment_bank", "Does the request contain payment card data, bank account details, or credentials for a payment account? Count full or partially exposed account details when they remain useful for identifying, accessing, or charging the account. Do not count general payment instructions or clearly fictional test values."),
    ("personal_finances", "Does the request contain a person's nonpublic income, tax, credit, debt, or investment information? Count records or values tied to an identifiable or plausibly identifiable individual. Do not count public market data, generic financial examples, or business financials that do not identify a private person."),
    ("health", "Does the request contain an identifiable person's medical history, diagnosis, treatment, prescription, or health record? Count information that connects a person to a health condition, care episode, or treatment. Do not count general health questions without private patient details."),
    ("biometric_genetic", "Does the request contain biometric identifiers or genetic information about an identifiable person? Count face, voice, fingerprint, iris, DNA, or similar measurements when they could identify a person or reveal inherited traits. Do not count general discussion of biometric systems or non-identifying synthetic examples."),
    ("precise_location", "Does the request reveal a person's precise current location, private travel plans, or location history? Count details that could locate or track a person beyond a broad public region. Do not count public venue addresses or general travel recommendations."),
    ("minors_students", "Does the request contain identifiable information about a minor or a student's nonpublic education record? Count names or identifiers paired with school, grades, attendance, support plans, discipline, or other private student details. Do not count generic classroom examples or public school information without private student data."),
    ("sensitive_traits", "Does the request reveal a private person's nonpublic religious, political, sexual, or similarly sensitive personal traits? Count the trait when linked to an identifiable or plausibly identifiable individual. Do not count public statements made in a public role or abstract discussion of these topics."),
    ("employment_hr", "Does the request contain a private personnel record, performance review, salary, disciplinary matter, or hiring decision? Count nonpublic information linked to an employee, candidate, or identifiable worker. Do not count general HR templates or public job descriptions."),
    ("legal_matters", "Does the request contain confidential legal advice, privileged communications, or private case information? Count nonpublic details tied to a client, party, witness, or active matter. Do not count public court filings or general legal questions without private case facts."),
    ("customer_client_records", "Does the request contain nonpublic records about identifiable customers, clients, or patients? Count account, transaction, support, usage, or service details that can be tied to an individual or customer organization. Do not count aggregated statistics that do not reveal a specific record."),
    ("confidential_communications", "Does the request contain private correspondence, a confidential agreement, or negotiation details? Count nonpublic messages or terms shared with an expectation of limited access, including quoted excerpts. Do not count published announcements or generic contract examples."),
    ("proprietary_work", "Does the request contain nonpublic source code, research, designs, formulas, or other proprietary work product? Count material that appears owned by a person or organization and not intended for public release. Do not count public open-source code or general technical questions."),
    ("internal_business", "Does the request contain nonpublic business plans, pricing, forecasts, financial results, or acquisition plans? Count material whose disclosure could reveal an organization's private commercial position. Do not count published investor information or generic planning templates."),
    ("security_system_details", "Does the request contain private infrastructure details, vulnerability information, incident records, or security controls whose disclosure could expose a system? Count exploitable configurations, active weaknesses, or nonpublic incident facts. Do not count general defensive guidance or already-public advisories without private system details."),
)

SECURITY_QUESTIONS = tuple(
    JevQuestion(
        name=f"security.{name}",
        question_type=JevQuestionType.NOUL,
        instructions=instructions,
        options=(
            JevOption(name="true", description="This category is present in the supplied request."),
            JevOption(name="false", description="This category is not present in the supplied request."),
        ),
    )
    for name, instructions in _SECURITY_QUESTIONS
)

SECURITY_FLAGS = tuple(name for name, _ in _SECURITY_QUESTIONS)

__all__ = ["SECURITY_FLAGS", "SECURITY_QUESTIONS", "Preset", "SecurityAction", "SecurityPreset"]
