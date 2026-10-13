"""FILE: tests/features/native_backends/test_native_backends_tools.py

PURPOSE: The three backend tools and their toolset (§9.2 rows 41-43, FR-5): names, READ permissions, parameters, the success result shape with harness "backend", the EC-147 and EC-138 argument rows, ToolExecutor behaviour under the default PermissionPolicy (EC-142 does not apply: all three are READ), and cancellation (EC-141).
ROLE IN CODEBASE: Start here when a model-facing backend tool misbehaves. Covers vidbyte.tools.builtins.harness_backends (HarnessBackendTool and its three subclasses) and vidbyte.tools.toolsets.HarnessBackendTools.
ARCHITECTURE NOTE: The tools run the real backend functions against the autouse fake DeepSeek endpoint; the host-error rows these tools share with their functions run in tool mode in test_native_backends_errors.py.
FUNCTION INVENTORY: run_tool executes one tool directly; the test_* functions each pin one promise.
COMMON MODIFICATION PATTERNS: A new backend tool is one more entry in EXPECTED_TOOLS plus its success-shape test.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert description wording; S025 owns it. 2. Do not route WRITE-only assertions here; the backend tools are all READ.
KNOWN EDGE CASES: A missing required parameter under ToolExecutor is reported by the executor ("validation_error") before execute runs, while a direct execute reports configuration.invalid_argument (EC-138).
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.7, §8.5, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_tools.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

EXPECTED_TOOLS = {"list_harness_backends": (), "check_backend_ready": ("backend",), "get_deepseek_balance": ()}
RECEIVED_WITHIN_SECONDS = 10.0


async def run_tool(tool: Any, api: Any, arguments: dict[str, Any]) -> Any:
    return await tool.execute(api.ToolCall(tool.name, arguments))


def test_toolset_holds_exactly_the_three_read_tools(backend_tools_api) -> None:
    # FR-5 / §9.2 rows 41-43: one tool per public backend function except the three internal ones; all READ.
    toolset = backend_tools_api.HarnessBackendTools()
    specs = {tool.name: tool.spec() for tool in toolset.all()}
    assert set(specs) == set(EXPECTED_TOOLS)
    for name, spec in specs.items():
        assert spec.name == name
        assert spec.permission is backend_tools_api.ToolPermission.READ, name
        assert tuple(parameter.name for parameter in spec.parameters) == EXPECTED_TOOLS[name], name
    assert [parameter.required for parameter in specs["check_backend_ready"].parameters] == [True]
    assert specs["check_backend_ready"].parameters[0].type == "string"


def test_tool_classes_share_the_backend_tool_base_and_are_exported(backend_tools_api) -> None:
    # §8.5 / §12.3 rows 59-61 and 66: <FunctionInPascalCase>Tool over HarnessBackendTool; the toolset exported.
    import vidbyte.tools.toolsets as toolsets

    classes = {
        "list_harness_backends": backend_tools_api.ListHarnessBackendsTool,
        "check_backend_ready": backend_tools_api.CheckBackendReadyTool,
        "get_deepseek_balance": backend_tools_api.GetDeepseekBalanceTool,
    }
    for name, cls in classes.items():
        tool = cls()
        assert isinstance(tool, backend_tools_api.HarnessBackendTool)
        assert tool.name == name
    assert {type(tool) for tool in backend_tools_api.HarnessBackendTools().all()} == set(classes.values())
    assert "HarnessBackendTools" in toolsets.__all__


@pytest.mark.asyncio
async def test_list_tool_returns_both_profiles_as_sorted_json(backend_tool, backend_tools_api) -> None:
    # §9.2 tool results: success metadata {"harness": "backend", "operation", "truncated"}; output is JSON with sorted keys.
    result = await run_tool(backend_tool("list_harness_backends"), backend_tools_api, {})
    assert result.status is backend_tools_api.ToolStatus.SUCCESS, result.output
    assert dict(result.metadata) == {"harness": "backend", "operation": "list_harness_backends", "truncated": False}
    payload = json.loads(result.output)
    assert [item["name"] for item in payload] == ["glm", "deepseek"], "enums are written as their values"
    assert all(list(item) == sorted(item) for item in payload), "keys are sorted"
    assert payload[0]["balance_url"] is None and payload[1]["balance_url"] == "https://api.deepseek.com/user/balance"
    assert payload[0]["claude_models"] == ["glm-5.3[1m]", "glm-5.3-flash[1m]"], "tuples are written as lists"


@pytest.mark.asyncio
async def test_balance_tool_writes_decimals_as_strings(backend_tool, backend_tools_api, backend_keys) -> None:
    # §9.2: Decimal values are written as strings, so no balance is rounded through a float.
    result = await run_tool(backend_tool("get_deepseek_balance"), backend_tools_api, {})
    assert result.status is backend_tools_api.ToolStatus.SUCCESS, result.output
    assert result.metadata["harness"] == "backend" and result.metadata["operation"] == "get_deepseek_balance"
    payload = json.loads(result.output)
    assert payload["is_available"] is True
    assert payload["balances"][0] == {"currency": "CNY", "granted_balance": "10.00", "topped_up_balance": "100.00", "total_balance": "110.00"}
    assert backend_keys.deepseek not in result.output


@pytest.mark.asyncio
async def test_ready_tool_reports_glm_without_a_remote_call(backend_tool, backend_tools_api, backend_keys, deepseek_endpoint) -> None:
    # D-17 through the tool: GLM readiness is the key check only, with remote_verified false and no balance.
    result = await run_tool(backend_tool("check_backend_ready"), backend_tools_api, {"backend": "glm"})
    assert result.status is backend_tools_api.ToolStatus.SUCCESS, result.output
    assert json.loads(result.output) == {"backend": "glm", "balance": None, "remote_verified": False}
    assert deepseek_endpoint.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"backend": "kimi"}, {"backend": "GLM"}, {"backend": ""}, {"backend": 7}, {"backend": ["glm"]}, {}], ids=["unknown", "wrong_case", "empty", "number", "list", "missing"])
async def test_ready_tool_refuses_a_backend_that_is_not_glm_or_deepseek(arguments: dict[str, Any], backend_tool, backend_tools_api, backend_keys, deepseek_endpoint, check_tool_error) -> None:
    # EC-147 / EC-138: anything but "glm" or "deepseek" (case included), or no backend at all, is invalid_argument naming "backend".
    result = await run_tool(backend_tool("check_backend_ready"), backend_tools_api, arguments)
    check_tool_error(result, code="configuration.invalid_argument", token="backend", tool_name="check_backend_ready")
    assert "backend" in result.output
    assert deepseek_endpoint.requests == []


@pytest.mark.asyncio
async def test_default_policy_runs_every_backend_tool(backend_tools_api, backend_keys) -> None:
    # EC-142 contrast: READ tools pass the default PermissionPolicy, so all three run under ToolExecutor.
    executor = backend_tools_api.ToolExecutor(backend_tools_api.HarnessBackendTools(), permission_policy=backend_tools_api.PermissionPolicy())
    calls = {"list_harness_backends": {}, "check_backend_ready": {"backend": "deepseek"}, "get_deepseek_balance": {}}
    for name, arguments in calls.items():
        result = await executor.execute_call(backend_tools_api.ToolCall(name, arguments))
        assert result.status is backend_tools_api.ToolStatus.SUCCESS, (name, result.output, dict(result.metadata))


@pytest.mark.asyncio
async def test_executor_reports_a_missing_backend_before_execute(backend_tools_api) -> None:
    # EC-138: under ToolExecutor a missing required parameter is the executor's own validation_error, unchanged.
    executor = backend_tools_api.ToolExecutor(backend_tools_api.HarnessBackendTools())
    result = await executor.execute_call(backend_tools_api.ToolCall("check_backend_ready", {}))
    assert result.status is backend_tools_api.ToolStatus.ERROR
    assert result.metadata["error"] == "validation_error"


@pytest.mark.asyncio
async def test_cancelling_a_backend_tool_propagates(backend_tool, backend_tools_api, backend_keys, deepseek_endpoint) -> None:
    # EC-141: CancelledError is the only exception a tool lets through.
    deepseek_endpoint.hold_forever()
    task = asyncio.create_task(run_tool(backend_tool("get_deepseek_balance"), backend_tools_api, {}))
    await asyncio.wait_for(deepseek_endpoint.received.wait(), timeout=RECEIVED_WITHIN_SECONDS)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
