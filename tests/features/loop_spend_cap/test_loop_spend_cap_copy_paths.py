"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_copy_paths.py

PURPOSE: Prove the spend cap survives every path that copies loop settings (checkpoint
export and restore, YAML agent.loop, AgentForker with a max_iterations override, and
the model-facing fork tool) and that the model can never set, raise, lower or clear it
through the fork tool.
ROLE IN CODEBASE: Behavior tests for spec INV-15 and AC-16 against BaseAgent.export_state
and restore, YamlLoader, AgentForker._loop_settings and ForkConversationTool.
ARCHITECTURE NOTE: Each test builds a capped agent and reads the cap back from the copy's
own agent_loop_settings and runtime_config, the two places the runtime reads. The fork
tool runs for real against an OfflineTestAgent parent, whose forks keep the scripted
runner, so the child actually replies. YAML documents are written to pytest's tmp_path.
FUNCTION INVENTORY: test_a_checkpoint_carries_the_cap_and_an_uncapped_one_omits_it;
test_a_yaml_loop_cap_reaches_the_built_agent; test_a_yaml_loop_cap_is_validated_like_the_keyword;
test_a_fork_with_a_max_iterations_override_keeps_the_cap;
test_a_fork_tool_loop_override_keeps_the_parents_cap;
test_the_fork_tool_refuses_any_model_supplied_cap.
COMMON MODIFICATION PATTERNS: A new copy path for loop settings adds one case that copies
a capped agent and asserts the cap on the copy.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare whole AgentLoopSettings objects; compare
the cap field. 2. Do not read a pinned fork tool error text other than the one the spec
quotes. 3. Do not network; the child fork runs a scripted runner.
KNOWN EDGE CASES: A null fork-tool loop field is kept for an unknown field, so
{"max_spend_usd": None} is refused, not ignored. An uncapped checkpoint omits the key, so
a checkpoint written before this feature restores uncapped (EC-30).
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-15, AC-16, EC-4, EC-28, EC-29, EC-30.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_copy_paths.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.agent_test_support import OfflineTestAgent
from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    PRICED_MODEL,
    ScriptedRunner,
    capped_settings,
    priced_agent,
    text_response,
    usage,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.config import YamlLoader
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.fork import ForkConversationTool
from vidbyte.tools.types import ToolCall

CAP = 0.25


class RecordingForkAgent(OfflineTestAgent):
    """Records the children its forks create, so the fork tool's child can be inspected."""

    def fork(self, settings: AgentForkSettings | None = None) -> BaseAgent:
        child = super().fork(settings)
        self.children.append(child)
        return child


def _yaml(tmp_path: Path, loop_value: str) -> Path:
    path = tmp_path / "researcher.yaml"
    path.write_text(
        f"type: base\nname: researcher\nsystem_prompt: You research.\nprovider: openai\nmodel_name: {PRICED_MODEL}\nloop:\n  max_spend_usd: {loop_value}\n",
        encoding="utf-8",
    )
    return path


def _fork_parent(
    loop: AgentLoopSettings,
) -> tuple[RecordingForkAgent, ForkConversationTool]:
    parent = priced_agent(
        ScriptedRunner(text_response("branch done", usage=usage(10, 1))),
        loop=loop,
        agent_type=RecordingForkAgent,
    )
    parent.children = []
    tool = ForkConversationTool()
    tool.bind_agent(parent)
    return parent, tool


def _fork_call(tool: ForkConversationTool, loop_settings: dict[str, object]) -> object:
    return asyncio.run(
        tool.execute(
            ToolCall(
                tool_name="fork_conversation",
                arguments={
                    "prompt": "Try another branch.",
                    "loop_settings": loop_settings,
                },
            )
        )
    )


def test_a_checkpoint_carries_the_cap_and_an_uncapped_one_omits_it() -> None:
    # AC-16 and EC-30: export writes the cap and restore reads it back; an uncapped export writes no key, as before.
    capped = priced_agent(ScriptedRunner(), loop=capped_settings(CAP))
    state = capped.export_state()
    restored = BaseAgent.restore(state)

    assert state.loop_settings["max_spend_usd"] == CAP
    assert (
        restored.agent_loop_settings.max_spend_usd,
        restored.runtime_config.max_spend_usd,
    ) == (CAP, CAP)

    uncapped_state = priced_agent(
        ScriptedRunner(), loop=AgentLoopSettings(max_iterations=3)
    ).export_state()
    assert "max_spend_usd" not in uncapped_state.loop_settings
    assert BaseAgent.restore(uncapped_state).agent_loop_settings.max_spend_usd is None


def test_a_yaml_loop_cap_reaches_the_built_agent(tmp_path: Path) -> None:
    # AC-16: agent.loop.max_spend_usd is a loop field like any other, carried into the agent the loader builds.
    loader = YamlLoader()
    settings = loader.load_agent(_yaml(tmp_path, str(CAP)))
    agent = loader.build_agent(settings)

    assert settings.loop.max_spend_usd == CAP
    assert (
        agent.agent_loop_settings.max_spend_usd,
        agent.runtime_config.max_spend_usd,
    ) == (CAP, CAP)


@pytest.mark.parametrize("loop_value", [".nan", ".inf", "0", "-1", '"5"', "true"])
def test_a_yaml_loop_cap_is_validated_like_the_keyword(
    tmp_path: Path, loop_value: str
) -> None:
    # EC-1..EC-4 through YAML: the document's value meets the same AgentLoopSettings validation.
    with pytest.raises(ConfigurationError, match=r"AgentLoopSettings\.max_spend_usd"):
        YamlLoader().load_agent(_yaml(tmp_path, loop_value))


def test_a_fork_with_a_max_iterations_override_keeps_the_cap() -> None:
    # AC-16: AgentForker rebuilds the loop settings field by field when max_iterations changes, and must not drop the cap.
    parent = priced_agent(ScriptedRunner(), loop=capped_settings(CAP, max_iterations=5))

    child = parent.fork(AgentForkSettings(max_iterations=2))

    assert child.agent_loop_settings.max_iterations == 2
    assert (
        child.agent_loop_settings.max_spend_usd,
        child.runtime_config.max_spend_usd,
    ) == (CAP, CAP)
    assert parent.fork().agent_loop_settings.max_spend_usd == CAP


def test_a_fork_tool_loop_override_keeps_the_parents_cap() -> None:
    # AC-16 and EC-29: a model-chosen loop override rebuilds the child's settings, with the cap as a guardrail it inherits.
    parent, tool = _fork_parent(capped_settings(CAP, max_iterations=5))

    result = _fork_call(tool, {"max_iterations": 3})

    assert result.status.value == "success", result.output
    (child,) = parent.children
    assert child.agent_loop_settings.max_iterations == 3
    assert (
        child.agent_loop_settings.max_spend_usd,
        child.runtime_config.max_spend_usd,
    ) == (CAP, CAP)


@pytest.mark.parametrize(
    "requested", [1000, 0.5 * CAP, None], ids=["raise", "lower", "clear"]
)
def test_the_fork_tool_refuses_any_model_supplied_cap(requested: float | None) -> None:
    # AC-16 and EC-28: the model can neither set, raise, lower nor clear the cap; the schema does not offer the field.
    parent, tool = _fork_parent(capped_settings(CAP, max_iterations=5))

    result = _fork_call(tool, {"max_spend_usd": requested})

    assert result.status.value == "error"
    assert result.output == "loop_settings does not support field 'max_spend_usd'."
    assert parent.children == []
    assert parent.agent_loop_settings.max_spend_usd == CAP
    assert (
        "max_spend_usd"
        not in tool.spec().input_schema["properties"]["loop_settings"]["properties"]
    )
