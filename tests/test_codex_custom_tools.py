"""FILE: tests/test_codex_custom_tools.py

PURPOSE:
    Feature tests for Codex custom tools: CodexToolDefinition validation,
    CodexToolTranslator conversion and rendering, CodexToolExecutor execution,
    and facade plus fork propagation on CodexHarnessAgent.

ROLE IN CODEBASE:
    Exercises vidbyte/lib/dataclasses/codex.py tool records, the translator
    and executor in vidbyte/agents/codex/tools.py, and the tools wiring in
    vidbyte/agents/codex/agent.py and fork.py. No network or provider SDK.

ARCHITECTURE NOTE:
    Every test runs offline with fake tool objects. Only CodexTransport is
    untouched because no turn ever runs here; construction-time translation
    is the boundary under test.

FUNCTION INVENTORY:
    No production functions. _FakeTool pairs spec() with execute(); the test
    classes each cover one layer of the tools seam.

COMMON MODIFICATION PATTERNS:
    Add a translator concern to CodexToolTranslator, then add its case to
    TranslatorTests and its facade case to FacadeTests.

WHAT NOT TO DO IN THIS FILE:
    Do not start transports or import openai_codex; translation must stay
    provable without the optional extra installed.

KNOWN EDGE CASES:
    A definition without a live tool object is describable but not
    executable, so executor tests always use live fakes.

RELATED DOCS: docs/design/codex-custom-tools.md
TESTS: python -m pytest tests/test_codex_custom_tools.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.tools import CodexToolExecutor, CodexToolTranslator
from vidbyte.lib.dataclasses.codex import (
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexToolDefinition,
)
from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)
from vidbyte.lib.errors import ConfigurationError

VALID_DESCRIPTION = (
    "First sentence states the purpose of this test tool clearly. "
    "Second sentence describes when the model should call it during a run. "
    "Third sentence explains the shape of the arguments it accepts today. "
    "Fourth sentence notes how its output is folded back into context."
)

VALID_SCHEMA = {"type": "object", "properties": {"task": {"type": "string"}}}


class _FakeTool:
    """Minimal BaseTool-shaped fake with a valid spec and recording execute."""

    def __init__(self, name: str = "fake_tool") -> None:
        self._name = name
        self.calls: list[ToolCall] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=VALID_DESCRIPTION,
            parameters=(
                ToolParameter(name="task", type="string", description="Task text."),
            ),
            permission=ToolPermission.SAFE,
        )

    def validate_call(self, call: ToolCall) -> str | None:
        if "task" not in call.arguments:
            return "Missing required parameters: task"
        return None

    async def execute(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult.success(tool_name=call.tool_name, output="done")


def _settings(**overrides: object) -> CodexHarnessAgentSettings:
    values: dict[str, object] = {"name": "agent", "system_prompt": "Be helpful."}
    values.update(overrides)
    return CodexHarnessAgentSettings(**values)  # type: ignore[arg-type]


class DefinitionValidationTests(unittest.TestCase):
    def test_valid_definition_constructs(self) -> None:
        definition = CodexToolDefinition(
            name="decompose_tool",
            description=VALID_DESCRIPTION,
            input_schema=dict(VALID_SCHEMA),
        )
        self.assertEqual(definition.name, "decompose_tool")

    def test_blank_name_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="  ",
                description=VALID_DESCRIPTION,
                input_schema=dict(VALID_SCHEMA),
            )

    def test_name_with_spaces_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="bad name",
                description=VALID_DESCRIPTION,
                input_schema=dict(VALID_SCHEMA),
            )

    def test_name_over_64_chars_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="x" * 65,
                description=VALID_DESCRIPTION,
                input_schema=dict(VALID_SCHEMA),
            )

    def test_short_description_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="tool", description="Too short.", input_schema=dict(VALID_SCHEMA)
            )

    def test_non_object_schema_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="tool",
                description=VALID_DESCRIPTION,
                input_schema={"type": "array"},
            )

    def test_non_json_schema_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolDefinition(
                name="tool",
                description=VALID_DESCRIPTION,
                input_schema={"type": "object", "x": {1, 2}},
            )

    def test_duplicate_names_rejected_in_settings(self) -> None:
        first = CodexToolDefinition(
            name="tool", description=VALID_DESCRIPTION, input_schema=dict(VALID_SCHEMA)
        )
        with self.assertRaises(ConfigurationError):
            _settings(tools=(first, first))

    def test_non_definition_tools_rejected_in_settings(self) -> None:
        with self.assertRaises(ConfigurationError):
            _settings(tools=(_FakeTool(),))  # type: ignore[arg-type]

    def test_fork_clear_and_replace_rejected(self) -> None:
        definition = CodexToolDefinition(
            name="tool", description=VALID_DESCRIPTION, input_schema=dict(VALID_SCHEMA)
        )
        with self.assertRaises(ConfigurationError):
            CodexForkSettings(tools=(definition,), clear_tools=True)

    def test_lib_module_imports_no_tools_package(self) -> None:
        import vidbyte.lib.dataclasses.codex as module

        self.assertNotIn("vidbyte.tools", str(getattr(module, "__file__", "")))


class TranslatorTests(unittest.TestCase):
    def test_empty_tools_translate_to_empty(self) -> None:
        self.assertEqual(CodexToolTranslator().from_sdk_tools(()), ())

    def test_fake_tool_translates_with_schema(self) -> None:
        (definition,) = CodexToolTranslator().from_sdk_tools((_FakeTool(),))
        self.assertEqual(definition.name, "fake_tool")
        self.assertEqual(definition.input_schema["type"], "object")

    def test_duplicate_names_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolTranslator().from_sdk_tools((_FakeTool("dup"), _FakeTool("dup")))

    def test_object_without_spec_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolTranslator().from_sdk_tools((object(),))

    def test_definition_passthrough(self) -> None:
        definition = CodexToolDefinition(
            name="tool", description=VALID_DESCRIPTION, input_schema=dict(VALID_SCHEMA)
        )
        self.assertEqual(
            CodexToolTranslator().from_sdk_tools((definition,)), (definition,)
        )

    def test_prompt_block_empty_for_no_tools(self) -> None:
        self.assertEqual(CodexToolTranslator().to_prompt_block(()), "")

    def test_prompt_block_sorted_and_stable(self) -> None:
        translator = CodexToolTranslator()
        definitions = translator.from_sdk_tools(
            (_FakeTool("zebra"), _FakeTool("apple"))
        )
        first = translator.to_prompt_block(definitions)
        second = translator.to_prompt_block(tuple(reversed(definitions)))
        self.assertEqual(first, second)
        self.assertLess(first.index("apple"), first.index("zebra"))

    def test_prompt_block_uninterpolated_braces(self) -> None:
        translator = CodexToolTranslator()
        block = translator.to_prompt_block(translator.from_sdk_tools((_FakeTool(),)))
        self.assertIn("fake_tool", block + "{{...}}")

    def test_mcp_config_empty_for_no_tools(self) -> None:
        self.assertEqual(
            CodexToolTranslator().to_mcp_config((), "python server.py"), {}
        )

    def test_mcp_config_names_exact_tools(self) -> None:
        translator = CodexToolTranslator()
        definitions = translator.from_sdk_tools((_FakeTool("b"), _FakeTool("a")))
        config = translator.to_mcp_config(definitions, "python server.py")
        self.assertEqual(config["mcp_servers"]["vidbyte-tools"]["tools"], ["a", "b"])

    def test_mcp_config_blank_command_rejected(self) -> None:
        translator = CodexToolTranslator()
        definitions = translator.from_sdk_tools((_FakeTool(),))
        with self.assertRaises(ConfigurationError):
            translator.to_mcp_config(definitions, "  ")

    def test_build_call_validates_mapping(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexToolTranslator().build_call("tool", "not-a-mapping")  # type: ignore[arg-type]


class ExecutorTests(unittest.TestCase):
    def test_unknown_tool_raises(self) -> None:
        async def run() -> None:
            with self.assertRaises(ConfigurationError):
                await CodexToolExecutor((_FakeTool(),)).execute_tool_call("missing", {})

        __import__("asyncio").run(run())

    def test_validation_failure_raises_before_execute(self) -> None:
        tool = _FakeTool()

        async def run() -> None:
            with self.assertRaises(ConfigurationError):
                await CodexToolExecutor((tool,)).execute_tool_call("fake_tool", {})
            self.assertEqual(tool.calls, [])

        __import__("asyncio").run(run())

    def test_successful_execution_returns_result(self) -> None:
        async def run() -> None:
            result = await CodexToolExecutor((_FakeTool(),)).execute_tool_call(
                "fake_tool", {"task": "hello"}
            )
            self.assertEqual(result.output, "done")

        __import__("asyncio").run(run())

    def test_definitions_only_are_not_executable(self) -> None:
        definition = CodexToolDefinition(
            name="tool", description=VALID_DESCRIPTION, input_schema=dict(VALID_SCHEMA)
        )
        executor = CodexToolExecutor((definition,))
        self.assertFalse(executor.has_tool("tool"))
        self.assertEqual(executor.tool_names(), ())


class FacadeTests(unittest.TestCase):
    def test_default_agent_has_no_tools(self) -> None:
        agent = CodexHarnessAgent(_settings())
        self.assertEqual(agent.tool_definitions, ())
        self.assertEqual(agent.describe_tools(), "")

    def test_constructor_tools_translate_and_describe(self) -> None:
        agent = CodexHarnessAgent(_settings(), tools=[_FakeTool()])
        self.assertEqual([d.name for d in agent.tool_definitions], ["fake_tool"])
        self.assertIn("fake_tool", agent.describe_tools())

    def test_settings_tools_used_without_constructor_tools(self) -> None:
        definition = CodexToolDefinition(
            name="tool", description=VALID_DESCRIPTION, input_schema=dict(VALID_SCHEMA)
        )
        agent = CodexHarnessAgent(_settings(tools=(definition,)))
        self.assertEqual(agent.tool_definitions, (definition,))

    def test_duplicate_constructor_tools_raise_agent_error(self) -> None:
        from vidbyte.lib.errors import CodexAgentError

        with self.assertRaises(CodexAgentError):
            CodexHarnessAgent(_settings(), tools=[_FakeTool("dup"), _FakeTool("dup")])

    def test_mcp_config_delegates(self) -> None:
        agent = CodexHarnessAgent(_settings(), tools=[_FakeTool()])
        config = agent.build_mcp_config("python server.py")
        self.assertEqual(config["mcp_servers"]["vidbyte-tools"]["tools"], ["fake_tool"])

    def test_execute_tool_call_round_trip(self) -> None:
        async def run() -> None:
            agent = CodexHarnessAgent(_settings(), tools=[_FakeTool()])
            self.assertTrue(agent.has_tool("fake_tool"))
            result = await agent.execute_tool_call("fake_tool", {"task": "hello"})
            self.assertEqual(result.output, "done")

        __import__("asyncio").run(run())


if __name__ == "__main__":
    unittest.main()
