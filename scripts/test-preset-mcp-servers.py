"""Context Protocol Header

Description:
    Verification script executing automated unit tests for the MCP preset servers feature.
Purpose:
    Validates preset registry lookup, environment validation, extra arguments appending,
    and lazy mixin configuration to ensure high reliability.
Architecture:
    Contains unit tests grouped under test categories matching the design doc testing plan.
    Prints status for each test case and returns a final summary and exit code.
Relations:
    Tests the implementations of vidbyte/tools/mcp/presets.py and vidbyte/agents/mixins.py.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.lib.errors import McpAttachmentError
from vidbyte.tools.mcp import (
    McpPresetConfigurationError,
    McpPresetNotFoundError,
    McpPresetRegistry,
    McpServerConfig,
    McpToolPermission,
)

if TYPE_CHECKING:
    from vidbyte.tools.base import BaseTool


class MockAgent(McpAttachableMixin):
    """A lightweight mock agent inheriting the attachable mixin for unit testing."""

    def __init__(self) -> None:
        # Instantiates a mock agent for preset tests.
        self._mcp_handles = []
        self._pending_mcp_configs = []
        self.tools = []

    def _attach_tools(self, tools: Sequence[BaseTool]) -> None:
        # Appends bridged tools to the mock agent's tools collection.
        self.tools.extend(tools)


# Test State Tracking
tests_run = 0
tests_passed = 0


def report_result(name: str, passed: bool, error: Exception | None = None) -> None:
    # Prints the PASS or FAIL result of a test case and updates statistics.
    global tests_run, tests_passed
    tests_run += 1
    if passed:
        tests_passed += 1
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}")
        if error:
            print(f"      Error: {error}")


# ==========================================
# 1. McpPresetRegistry Tests
# ==========================================

def test_registry_retrieval_success() -> None:
    # [Edge Case] Verifies successful metadata retrieval for registered presets.
    try:
        preset = McpPresetRegistry.get("github")
        assert preset.name == "github"
        assert "repository" in preset.description.lower()
        report_result("McpPresetRegistry - Retrieve github preset success [Edge Case]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Retrieve github preset success [Edge Case]", False, e)


def test_registry_retrieval_not_found() -> None:
    # [Edge Case] Ensures McpPresetNotFoundError is raised when a preset is not registered.
    try:
        McpPresetRegistry.get("non-existent-preset-999")
        report_result("McpPresetRegistry - Raise not found for invalid key [Edge Case]", False)
    except McpPresetNotFoundError:
        report_result("McpPresetRegistry - Raise not found for invalid key [Edge Case]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Raise not found for invalid key [Edge Case]", False, e)


def test_registry_missing_env_error() -> None:
    # [Hidden Failure] Verifies McpPresetConfigurationError is raised when required env keys are missing.
    try:
        McpPresetRegistry.build_config("brave-search", env={})
        report_result("McpPresetRegistry - Raise configuration error on missing required env [Hidden Failure]", False)
    except McpPresetConfigurationError as e:
        assert "BRAVE_API_KEY" in str(e)
        report_result("McpPresetRegistry - Raise configuration error on missing required env [Hidden Failure]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Raise configuration error on missing required env [Hidden Failure]", False, e)


def test_registry_env_merging() -> None:
    # [Hidden Assumption] Confirms that custom env values correctly override defaults.
    try:
        config = McpPresetRegistry.build_config("brave-search", env={"BRAVE_API_KEY": "test_key", "CUSTOM_VAR": "val"})
        assert config.env is not None
        assert config.env.get("BRAVE_API_KEY") == "test_key"
        assert config.env.get("CUSTOM_VAR") == "val"
        report_result("McpPresetRegistry - Correctly merge environment variables [Hidden Assumption]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Correctly merge environment variables [Hidden Assumption]", False, e)


def test_registry_extra_args_appending() -> None:
    # [Edge Case] Checks that extra_args are correctly appended to the preset execution command.
    try:
        config = McpPresetRegistry.build_config("sqlite", extra_args=("/path/to/test.db",))
        assert len(config.command) > 0
        assert config.command[-1] == "/path/to/test.db"
        report_result("McpPresetRegistry - Append extra_args correctly [Edge Case]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Append extra_args correctly [Edge Case]", False, e)


def test_registry_handle_none_env() -> None:
    # [Edge Case] Verifies the registry handles None environments cleanly when building configurations.
    try:
        config = McpPresetRegistry.build_config("duckduckgo", env=None)
        assert config.env is None
        report_result("McpPresetRegistry - Handle None env parameter cleanly [Edge Case]", True)
    except Exception as e:
        report_result("McpPresetRegistry - Handle None env parameter cleanly [Edge Case]", False, e)


# ==========================================
# 2. McpAttachableMixin Preset Tests
# ==========================================

def test_mixin_lazy_configuration() -> None:
    # [Hidden Assumption] Ensures with_preset_mcp_server stores config and defers live connections.
    try:
        agent = MockAgent()
        agent.with_preset_mcp_server("github", env={"GITHUB_PERSONAL_ACCESS_TOKEN": "token"})
        assert len(agent._pending_mcp_configs) == 1
        assert agent._pending_mcp_configs[0].name == "github"
        assert len(agent._mcp_handles) == 0
        report_result("McpAttachableMixin - Lazily defer preset configuration [Hidden Assumption]", True)
    except Exception as e:
        report_result("McpAttachableMixin - Lazily defer preset configuration [Hidden Assumption]", False, e)


def test_mixin_lazy_attaches_active_configs() -> None:
    # [Silent Failure] Verifies lazy connection execution converts configurations without losing items.
    try:
        agent = MockAgent()
        agent.with_preset_mcp_server("duckduckgo")
        assert len(agent._pending_mcp_configs) == 1

        # We inject a mock function for attach_mcp_servers to simulate lazy resolution without running the subprocess
        async def mock_attach_mcp_servers(servers):
            # Simulated attach operation.
            for s in servers:
                agent._mcp_handles.append(s)
            return agent

        agent.attach_mcp_servers = mock_attach_mcp_servers
        asyncio.run(agent._ensure_mcp_connected())
        assert len(agent._pending_mcp_configs) == 0
        assert len(agent._mcp_handles) == 1
        assert agent._mcp_handles[0].name == "duckduckgo"
        report_result("McpAttachableMixin - Correctly resolve lazy configs on execution [Silent Failure]", True)
    except Exception as e:
        report_result("McpAttachableMixin - Correctly resolve lazy configs on execution [Silent Failure]", False, e)


def test_mixin_attach_failure_cleanup() -> None:
    # [Hidden Failure] Ensures partial attachment errors clean up already connected handles.
    try:
        agent = MockAgent()
        # Simulated fail-safe test. If we attach an invalid command alongside a preset, does it rollback?
        server1 = McpServerConfig(command=("invalid_command_to_fail_spawn_999",))
        server2 = McpPresetRegistry.build_config("duckduckgo")
        try:
            asyncio.run(agent.attach_mcp_servers([server1, server2]))
            report_result("McpAttachableMixin - Fail-safe concurrent rollback [Hidden Failure]", False)
        except McpAttachmentError:
            assert len(agent._mcp_handles) == 0
            report_result("McpAttachableMixin - Fail-safe concurrent rollback [Hidden Failure]", True)
    except Exception as e:
        report_result("McpAttachableMixin - Fail-safe concurrent rollback [Hidden Failure]", False, e)


def test_mixin_custom_naming_override() -> None:
    # [Silent Failure] Validates custom names overriding the standard preset name.
    try:
        agent = MockAgent()
        agent.with_preset_mcp_server("duckduckgo", name="custom-search-engine")
        assert agent._pending_mcp_configs[0].name == "custom-search-engine"
        report_result("McpAttachableMixin - Respect custom overridden name [Silent Failure]", True)
    except Exception as e:
        report_result("McpAttachableMixin - Respect custom overridden name [Silent Failure]", False, e)


# ==========================================
# Main Test Executor
# ==========================================

def main() -> None:
    # Runs the full test suite sequentially and returns appropriate exit status code.
    print("==================================================")
    print("Running MCP Preset Servers Automated Verification")
    print("==================================================")

    test_registry_retrieval_success()
    test_registry_retrieval_not_found()
    test_registry_missing_env_error()
    test_registry_env_merging()
    test_registry_extra_args_appending()
    test_registry_handle_none_env()

    test_mixin_lazy_configuration()
    test_mixin_lazy_attaches_active_configs()
    test_mixin_attach_failure_cleanup()
    test_mixin_custom_naming_override()

    print("==================================================")
    print(f"Summary: {tests_passed}/{tests_run} tests passed.")
    print("==================================================")

    if tests_passed == tests_run:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
