"""FILE: tests/features/claude_code_agent/test_claude_code_surface.py

PURPOSE: Contract tests of the Claude Code harness agent's public surface as the cross-repo suggest-BYOK contract (section 2) pins it: the names import from vidbyte.agents.claude_code, vidbyte.agents and the root vidbyte package as the same objects; ClaudeCodeAgentError imports from vidbyte.lib.errors and vidbyte and is a VidbyteSdkError; the pinned fields keep their names and order; the seven failure kinds keep their names; and contracts/sdk-public-api.json lists every root name.
ROLE IN CODEBASE: vidbyte-cli builds and reads these records by name, and its lint rule C028 accepts only names in vidbyte.__all__ (the vendored public-API contract), so these tests are what keeps the CLI's Claude Code path importable.
ARCHITECTURE NOTE: The contract check reads the committed JSON directly, as the CLI's lint does.
FUNCTION INVENTORY: One test per promise.
COMMON MODIFICATION PATTERNS: A new public name joins PUBLIC_NAMES after it joins the three __all__ lists and the regenerated contract.
KNOWN EDGE CASES: Optional fields may be appended after the pinned ones, so the field checks compare prefixes.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md; contracts/README.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent/test_claude_code_surface.py
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import vidbyte
import vidbyte.agents
import vidbyte.agents.claude_code as package
from vidbyte.lib.errors import AgentExecutionError, ClaudeCodeAgentError, VidbyteSdkError

PUBLIC_NAMES = (
    "ClaudeCodeAgentError",
    "ClaudeCodeEffort",
    "ClaudeCodeFailureKind",
    "ClaudeCodeHarnessAgent",
    "ClaudeCodeHarnessAgentSettings",
    "ClaudeCodeImage",
    "ClaudeCodeRunInput",
    "ClaudeCodeRunResult",
    "ClaudeCodeUsage",
)
ROOT = Path(__file__).resolve().parents[3]


def test_names_are_the_same_objects_everywhere() -> None:
    assert set(package.__all__) == set(PUBLIC_NAMES)
    for name in PUBLIC_NAMES:
        assert name in vidbyte.__all__
        assert getattr(vidbyte, name) is getattr(package, name)
    for name in set(PUBLIC_NAMES) - {"ClaudeCodeAgentError"}:
        assert getattr(vidbyte.agents, name) is getattr(package, name)


def test_error_is_an_sdk_error_from_lib_errors() -> None:
    assert vidbyte.ClaudeCodeAgentError is ClaudeCodeAgentError
    assert issubclass(ClaudeCodeAgentError, AgentExecutionError)
    assert issubclass(ClaudeCodeAgentError, VidbyteSdkError)


def test_pinned_fields_keep_their_names_and_order() -> None:
    def names(record: type) -> list[str]:
        return [item.name for item in dataclasses.fields(record)]

    pinned_settings = ["name", "instructions", "model", "output_schema", "effort", "allowed_tools", "workspace", "claude_bin", "timeout_seconds"]
    assert names(package.ClaudeCodeHarnessAgentSettings)[: len(pinned_settings)] == pinned_settings
    assert names(package.ClaudeCodeRunInput) == ["prompt", "images"]
    assert names(package.ClaudeCodeImage) == ["media_type", "data_base64"]
    assert names(package.ClaudeCodeUsage) == ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"]
    pinned_result = ["output", "text", "session_id", "usage", "cost_usd", "model"]
    assert names(package.ClaudeCodeRunResult)[: len(pinned_result)] == pinned_result


def test_failure_kinds_are_the_contracts_seven() -> None:
    assert [member.name for member in package.ClaudeCodeFailureKind] == ["NOT_INSTALLED", "NOT_AUTHENTICATED", "TIMEOUT", "EXIT_NONZERO", "SCHEMA_VIOLATION", "UNSUPPORTED_INPUT", "MALFORMED_OUTPUT"]


def test_agent_exposes_the_thread_handle() -> None:
    agent = package.ClaudeCodeHarnessAgent(package.ClaudeCodeHarnessAgentSettings(name="surface", instructions="x"))
    assert agent.session_id is None and agent.name == "surface" and agent.workspace is None
    assert callable(agent.arun) and callable(agent.run) and callable(agent.close)


def test_public_api_contract_lists_every_name() -> None:
    contract = json.loads((ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert set(PUBLIC_NAMES) <= set(contract["exports"])
