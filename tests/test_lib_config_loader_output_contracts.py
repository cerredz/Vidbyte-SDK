"""FILE: tests/test_lib_config_loader_output_contracts.py

PURPOSE:
    Regression tests for the descriptor loader exported from vidbyte.lib.config: a
    `loop.output_contracts` list in an agent YAML is built into concrete floor objects,
    and an unknown floor type fails as a ConfigurationError carrying the file path; a
    `loop.tool_error_policy` mapping is built into a ToolErrorPolicy; YAML merge keys
    resolve as SafeLoader resolves them while own duplicate keys stay rejected; a file
    that is not UTF-8 text fails as a ConfigurationError carrying the file path.

ROLE IN CODEBASE:
    Exercises YamlLoader._construct_base_agent and YamlLoader._build_output_contracts in
    vidbyte/lib/config/loader.py through the public load_agent entry point.

ARCHITECTURE NOTE:
    Each test writes a small agent YAML into a temporary folder and loads it, so the
    real parse, dispatch, and AgentLoopSettings construction path runs. No model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when the loader learns a new loop field that YAML can only express
    as a mapping, or when the set of nameable floors changes.

KNOWN EDGE CASES:
    YAML safe-load only produces plain mappings, never OutputContract instances, so a
    document that declares contracts always goes through the build step under test.

RELATED DOCS:
    vidbyte/lib/dataclasses/config.py (_coerce_contract) applies the same naming rules
    for the vidbyte.config loader.

TESTS:
    python -m pytest tests/test_lib_config_loader_output_contracts.py -q
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from vidbyte.agents.contracts import MinToolCalls
from vidbyte.agents.settings import ToolErrorPolicy, UnrecoverableAction
from vidbyte.lib.config import YamlLoader
from vidbyte.lib.config.loader import _DuplicateKeySafeLoader
from vidbyte.lib.errors import ConfigurationError

BASE = "name: researcher\nsystem_prompt: Research things.\nloop:\n  max_iterations: 6\n  output_contracts:\n"


class LibConfigLoaderOutputContractsTests(unittest.TestCase):
    def test_builds_named_floor_and_rejects_unknown_type(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            floor = Path(folder) / "floor.yaml"
            floor.write_text(BASE + "    - type: MinToolCalls\n      minimum: 2\n", encoding="utf-8")
            contracts = YamlLoader().load_agent(floor).loop.output_contracts
            self.assertEqual(len(contracts), 1)
            self.assertIsInstance(contracts[0], MinToolCalls)
            self.assertEqual(contracts[0].minimum, 2)

            unknown = Path(folder) / "unknown.yaml"
            unknown.write_text(BASE + "    - type: NotAFloor\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError) as caught:
                YamlLoader().load_agent(unknown)
            self.assertEqual(caught.exception.details.get("path"), str(unknown))

    def test_builds_tool_error_policy_from_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            policy_file = Path(folder) / "policy.yaml"
            policy_file.write_text("name: researcher\nsystem_prompt: Research things.\nloop:\n  tool_error_policy:\n    max_retries_per_tool_call: 2\n    on_unrecoverable: abort_run\n", encoding="utf-8")
            policy = YamlLoader().load_agent(policy_file).loop.tool_error_policy
            self.assertIsInstance(policy, ToolErrorPolicy)
            self.assertEqual(policy.max_retries_per_tool_call, 2)
            self.assertEqual(policy.on_unrecoverable, UnrecoverableAction.ABORT_RUN)


class LibConfigLoaderMergeKeyTests(unittest.TestCase):
    def test_merge_keys_resolve_like_safe_loader(self) -> None:
        # @intent yaml-merge-keys-are-resolved
        documents = (
            "a: &a {x: 1, y: 2}\nb: {<<: *a, y: 3}\n",
            "a: &a {x: 1, y: 1}\nb: &b {y: 2, z: 2}\nc: {<<: [*a, *b], z: 3}\n",
            "defs: {mid: &mid {<<: {x: 1}, x: 2}}\ntop: {<<: *mid}\n",
        )
        for text in documents:
            with self.subTest(text=text):
                self.assertEqual(yaml.load(text, Loader=_DuplicateKeySafeLoader), yaml.load(text, Loader=yaml.SafeLoader))

    def test_own_duplicate_beside_a_merge_is_still_rejected(self) -> None:
        with self.assertRaisesRegex(yaml.constructor.ConstructorError, "Duplicate key 'y' is not allowed"):
            yaml.load("a: &a {x: 1, y: 2}\nb: {<<: *a, y: 1, y: 2}\n", Loader=_DuplicateKeySafeLoader)

    def test_two_merge_keys_in_one_mapping_are_rejected(self) -> None:
        # Verify a second `<<` in one mapping is rejected instead of letting the later merge hide the earlier one.
        # @intent one-merge-key-per-mapping
        documents = (
            "a: &a {x: 1}\nb: &b {x: 2}\nc: {<<: *a, <<: *b}\n",
            "a: &a {x: 1}\nb: &b {x: 2}\nc:\n  <<: *a\n  <<: *b\n",
        )
        for text in documents:
            with self.subTest(text=text):
                with self.assertRaisesRegex(yaml.constructor.ConstructorError, "Duplicate key '<<' is not allowed"):
                    yaml.load(text, Loader=_DuplicateKeySafeLoader)


class LibConfigLoaderReadErrorTests(unittest.TestCase):
    def test_non_utf8_file_is_a_configuration_error_with_path(self) -> None:
        # @intent unreadable-yaml-is-a-configuration-error
        text = "name: researcher\nsystem_prompt: Grüße aus der Forschung.\n"
        encodings = (("utf16.yaml", "utf-16"), ("cp1252.yaml", "cp1252"))
        with tempfile.TemporaryDirectory() as folder:
            for name, encoding in encodings:
                with self.subTest(encoding=encoding):
                    path = Path(folder) / name
                    path.write_bytes(text.encode(encoding))
                    with self.assertRaises(ConfigurationError) as caught:
                        YamlLoader().load_agent(path)
                    self.assertEqual(caught.exception.details.get("path"), str(path))
                    self.assertIsInstance(caught.exception.__cause__, UnicodeError)


if __name__ == "__main__":
    unittest.main()
