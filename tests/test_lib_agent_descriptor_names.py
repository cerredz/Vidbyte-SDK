"""FILE: tests/test_lib_agent_descriptor_names.py

PURPOSE:
    Regression tests for AgentDescriptor's name and ref patterns: a value that ends in a
    newline (what a YAML block scalar such as `name: |` produces) is rejected like any
    other character outside the pattern, while a plain kebab-case name still loads.

ROLE IN CODEBASE:
    Exercises _NAME_PATTERN and _REF_PATTERN in vidbyte/lib/dataclasses/agent_descriptor.py
    through the public vidbyte.lib.config.YamlLoader.load_agent entry point.

ARCHITECTURE NOTE:
    Each test writes a small agent YAML into a temporary folder and loads it, so the
    real parse and AgentDescriptor validation path runs. No model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when a descriptor field gains a character pattern.

KNOWN EDGE CASES:
    Python's `$` also matches just before one trailing newline, so the patterns must
    be applied with fullmatch rather than match.

RELATED DOCS:
    vidbyte/lib/dataclasses/agent_descriptor.py (_NAME_PATTERN, _REF_PATTERN).

TESTS:
    python -m pytest tests/test_lib_agent_descriptor_names.py -q
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.config import YamlLoader
from vidbyte.lib.errors import ConfigurationError

BODY = "system_prompt: Help customers.\n"


class LibAgentDescriptorNamePatternTests(unittest.TestCase):
    def _load(self, folder: str, text: str) -> object:
        path = Path(folder) / "agent.yaml"
        path.write_text(text, encoding="utf-8")
        return YamlLoader().load_agent(path)

    def test_values_ending_in_a_newline_are_rejected(self) -> None:
        cases = {
            "name": "name: |\n  support-agent\n" + BODY,
            "tool ref": "name: support-agent\n" + BODY + "tools:\n  - ref: |\n      web_search\n",
            "middleware ref": "name: support-agent\n" + BODY + "middleware:\n  - |\n    audit-log\n",
        }
        with tempfile.TemporaryDirectory() as folder:
            for field, text in cases.items():
                with self.subTest(field=field), self.assertRaises(ConfigurationError):
                    self._load(folder, text)

    def test_plain_kebab_case_values_still_load(self) -> None:
        text = "name: support-agent\n" + BODY + "tools:\n  - ref: web_search\nmiddleware:\n  - audit-log\n"
        with tempfile.TemporaryDirectory() as folder:
            descriptor = self._load(folder, text)
        self.assertEqual(descriptor.name, "support-agent")


if __name__ == "__main__":
    unittest.main()
