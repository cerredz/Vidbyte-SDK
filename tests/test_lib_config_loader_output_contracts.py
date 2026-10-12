"""FILE: tests/test_lib_config_loader_output_contracts.py

PURPOSE:
    Regression tests for the descriptor loader exported from vidbyte.lib.config: a
    `loop.output_contracts` list in an agent YAML is built into concrete floor objects,
    and an unknown floor type fails as a ConfigurationError carrying the file path.

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

from vidbyte.agents.contracts import MinToolCalls
from vidbyte.lib.config import YamlLoader
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


if __name__ == "__main__":
    unittest.main()
