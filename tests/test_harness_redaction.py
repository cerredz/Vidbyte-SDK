"""FILE: tests/test_harness_redaction.py

PURPOSE:
    Regression tests for HarnessRedactor's free-text pass: credential
    assignments inside string values bound for a TrajectorySink are redacted,
    not only credential-like mapping keys.

ROLE IN CODEBASE:
    Exercises vidbyte/harnesses/serialization.py, the redaction chokepoint the
    TrajectoryCollector applies to every task/output/history value.

ARCHITECTURE NOTE:
    Runs offline against the real redactor; no sink or session is needed
    because the leak lived entirely in HarnessRedactor's string handling.

COMMON MODIFICATION PATTERNS:
    When the credential-assignment pattern grows, add the new key shape to the
    nested-record case and keep a neighbouring benign phrase in the
    ordinary-text case.

WHAT NOT TO DO IN THIS FILE:
    Do not assert a secret value survives redaction anywhere in the output.

KNOWN EDGE CASES:
    "Tokens used: 42" is not an assignment ("Tokens" is not the bare word
    "token"), so it must stay untouched; "password: x" normalizes to
    "password=<redacted>".

RELATED DOCS: docs/design/harness-free-text-redaction.md
TESTS: python -m pytest tests/test_harness_redaction.py
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from vidbyte.harnesses.serialization import HarnessRedactor, HarnessSecretPolicy


@dataclass
class _DeployReport:
    service: str
    api_key: str


class HarnessRedactorFreeTextTests(unittest.TestCase):
    def test_nested_free_text_credentials_are_redacted(self) -> None:
        record = {
            "task": {"question": "my token=tok_ABC123 failed, what changed?"},
            "output": "Connect with api_key=sk-live-9f8e7d6c5b4a and password: hunter2 then retry",
            "history": [{"role": "assistant", "content": ["see secret_key=abc.def"]}],
            "api_key": "dropped-by-key",
        }

        safe = HarnessRedactor().redact(record)

        dumped = json.dumps(safe)
        for secret in ("tok_ABC123", "sk-live-9f8e7d6c5b4a", "hunter2", "abc.def", "dropped-by-key"):
            self.assertNotIn(secret, dumped)
        self.assertEqual(safe["task"]["question"], "my token=<redacted> failed, what changed?")
        self.assertEqual(safe["output"], "Connect with api_key=<redacted> and password=<redacted> then retry")
        self.assertEqual(safe["history"][0]["content"], ["see secret_key=<redacted>"])
        self.assertNotIn("api_key", safe)

    def test_ordinary_text_is_unchanged(self) -> None:
        record = {"task": "Summarize the author's notes.", "output": "Tokens used: 42", "history": ["ok"]}

        self.assertEqual(HarnessRedactor().redact(record), record)

    def test_quoted_key_and_auth_scheme_credentials_are_redacted(self) -> None:
        cases = {
            '{"url": "x", "api_key": "S3-json"}': "S3-json",
            "{'url': 'x', 'api_key': 'S6-repr'}": "S6-repr",
            '{"password": "S7-json", "n": 1}': "S7-json",
            "Authorization: Bearer S5-bearer": "S5-bearer",
            "authorization=Basic S8-basic then": "S8-basic",
        }
        redactor = HarnessRedactor()

        for text, secret in cases.items():
            self.assertNotIn(secret, redactor.redact(text), text)
            self.assertNotIn(secret, redactor.safe_error_message(text), text)
        self.assertEqual(redactor.redact('{"password": "S7-json", "n": 1}'), '{"password=<redacted>, "n": 1}')
        self.assertEqual(redactor.redact("tokens used: 42"), "tokens used: 42")

    def test_token_and_api_key_auth_schemes_are_redacted(self) -> None:
        cases = {
            "Authorization: Token S9-token": "S9-token",
            "authorization: token ghp_S10": "ghp_S10",
            "Authorization: Api-Key S11-zep": "S11-zep",
        }
        redactor = HarnessRedactor()

        for text, secret in cases.items():
            self.assertNotIn(secret, redactor.redact(text), text)
            self.assertNotIn(secret, redactor.safe_error_message(text), text)
        self.assertEqual(redactor.redact("Authorization: Token S9-token"), "Authorization=<redacted>")
        for text in ("token budget: 5 tokens", "api-key rotation is due"):
            self.assertEqual(redactor.redact(text), text)

    def test_prefixed_credential_names_are_redacted(self) -> None:
        cases = {
            "OPENAI_API_KEY=sk-proj-1": "sk-proj-1",
            "export GITHUB_TOKEN=ghp_2": "ghp_2",
            "DATABASE_PASSWORD: pg-3": "pg-3",
            '{"client_secret": "cs-4"}': "cs-4",
            '{"githubToken": "gho-5"}': "gho-5",
        }
        redactor = HarnessRedactor()

        for text, secret in cases.items():
            self.assertNotIn(secret, redactor.redact(text), text)
            self.assertNotIn(secret, redactor.safe_error_message(text), text)
        self.assertEqual(redactor.redact("OPENAI_API_KEY=sk-proj-1"), "OPENAI_API_KEY=<redacted>")
        for text in ("token_estimate: 5", "max_tokens: 5", "nosecret: x", "maxTokens: 5"):
            self.assertEqual(redactor.redact(text), text)

    def test_error_message_scrub_matches_value_scrub(self) -> None:
        text = "Connect with api_key=sk-live-9f8e7d6c5b4a and password: hunter2 then retry"
        redactor = HarnessRedactor()

        self.assertEqual(redactor.safe_error_message(text), redactor.redact(text))


class HarnessSecretPolicyCamelCaseTests(unittest.TestCase):
    def test_camel_case_credential_keys_are_secret(self) -> None:
        for key in ("accessToken", "clientSecret", "privateKey", "sessionToken", "githubToken", "apiKey", "APIKey", "OAuthToken"):
            self.assertTrue(HarnessSecretPolicy.is_secret_key(key), key)

    def test_camel_case_ordinary_keys_are_not_secret(self) -> None:
        for key in ("author", "tokenizer", "maxTokens", "promptTokenCount", "totalTokenCount", "authFlow"):
            self.assertFalse(HarnessSecretPolicy.is_secret_key(key), key)

    def test_camel_case_credential_key_is_scrubbed_from_capture(self) -> None:
        safe = HarnessRedactor().redact({"accessToken": "tok_camel123", "maxTokens": 5})

        self.assertEqual(safe, {"maxTokens": 5})

    def test_dataclass_credential_field_is_scrubbed_like_mapping_key(self) -> None:
        redactor = HarnessRedactor()

        safe = redactor.redact(_DeployReport(service="billing", api_key="sk_live_DEPLOY_KEY_123"))

        self.assertEqual(safe, {"service": "billing"})
        self.assertEqual(safe, redactor.redact({"service": "billing", "api_key": "sk_live_DEPLOY_KEY_123"}))


class HarnessSecretPolicyAcronymTests(unittest.TestCase):
    def test_acronym_camel_case_credential_keys_are_secret(self) -> None:
        for key in ("AWSSecretKey", "AWSAccessKeyId", "MyAPIKey", "JWTToken", "APIToken", "IDToken"):
            self.assertTrue(HarnessSecretPolicy.is_secret_key(key), key)

    def test_acronym_ordinary_keys_are_not_secret(self) -> None:
        for key in ("HTTPStatus", "URLPath", "XMLParser", "APIKeyName"):
            self.assertFalse(HarnessSecretPolicy.is_secret_key(key), key)


if __name__ == "__main__":
    unittest.main()
