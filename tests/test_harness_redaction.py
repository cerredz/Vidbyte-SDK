"""FILE: tests/test_harness_redaction.py

PURPOSE:
    Regression tests for HarnessRedactor's free-text pass: credential
    assignments inside string values bound for a TrajectorySink are redacted,
    not only credential-like mapping keys.

ROLE IN CODEBASE:
    Exercises vidbyte/harnesses/serialization.py, the redaction chokepoint the
    TrajectoryCollector applies to every task/output/history value.

WHAT NOT TO DO IN THIS FILE:
    Do not assert a secret value survives redaction anywhere in the output.

RELATED DOCS: docs/design/harness-free-text-redaction.md
TESTS: python -m pytest tests/test_harness_redaction.py
"""

from __future__ import annotations

import json
import unittest

from vidbyte.harnesses.serialization import HarnessRedactor


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

    def test_error_message_scrub_matches_value_scrub(self) -> None:
        text = "Connect with api_key=sk-live-9f8e7d6c5b4a and password: hunter2 then retry"
        redactor = HarnessRedactor()

        self.assertEqual(redactor.safe_error_message(text), redactor.redact(text))


if __name__ == "__main__":
    unittest.main()
