"""FILE: tests/test_lib_agent_descriptor_secrets.py

PURPOSE:
    Regression tests for the descriptor loader's secret guard: a metadata key or tool
    option that ENDS in a credential name (openai_api_key, github_token, db_password) is
    rejected just like the bare name is, while a plain key such as region still loads.

ROLE IN CODEBASE:
    Exercises _has_secret_like_keys in vidbyte/lib/dataclasses/agent_descriptor.py
    through the public vidbyte.lib.config.YamlLoader.load_agent entry point.

ARCHITECTURE NOTE:
    Each test writes a small agent YAML into a temporary folder and loads it, so the
    real parse and AgentDescriptor validation path runs. No model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when the list of secret-like key suffixes or prefixes changes.

KNOWN EDGE CASES:
    Only top-level keys of metadata and tool options are checked; nested mappings are
    not scanned by this guard.

RELATED DOCS:
    vidbyte/lib/dataclasses/agent_descriptor.py (_SECRET_KEY_SUFFIXES, _SECRET_KEY_PREFIXES).

TESTS:
    python -m pytest tests/test_lib_agent_descriptor_secrets.py -q
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.lib.config import YamlLoader
from vidbyte.lib.errors import ConfigurationError

HEAD = "name: support-agent\nsystem_prompt: Help customers.\n"


class LibAgentDescriptorSecretSuffixTests(unittest.TestCase):
    def _load(self, folder: str, text: str) -> object:
        path = Path(folder) / "agent.yaml"
        path.write_text(HEAD + text, encoding="utf-8")
        return YamlLoader().load_agent(path)

    def test_metadata_keys_ending_in_a_secret_name_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for key in ("openai_api_key", "github_token", "db_password"):
                with self.subTest(key=key), self.assertRaises(ConfigurationError):
                    self._load(folder, f"metadata:\n  {key}: sk-live-123\n")

    def test_tool_option_ending_in_a_secret_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ConfigurationError):
                self._load(folder, "tools:\n  - ref: web_search\n    options:\n      github_token: ghp_x\n")

    def test_plain_metadata_key_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for key in ("region", "team"):
                with self.subTest(key=key):
                    self.assertIsNotNone(self._load(folder, f"metadata:\n  {key}: eu\n"))


if __name__ == "__main__":
    unittest.main()
