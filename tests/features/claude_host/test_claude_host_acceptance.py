"""FILE: tests/features/claude_host/test_claude_host_acceptance.py

PURPOSE: Runs the two developer snippets from spec section 4 end to end over the fake SDK: the host snippet prints the status, the answer and the cost (or the not-installed line), and the agent snippet launches two Claude sessions through ClaudeTools, waits on both and returns both answers. Also proves that a sync agent.run() with ClaudeTools gets the precondition error instead of driving the host from a foreign loop.
ROLE IN CODEBASE: Acceptance layer of tests/features/claude_host/ (spec AC-1, EC-25, INV-15, section 4 "Developer usage"). Exercises ClaudeHost, ClaudeTools and BaseAgent together; only the vendor SDK, shutil.which and the model runner are replaced.
ARCHITECTURE NOTE: main() and compare_reviews() are the section 4 snippets with their imports moved inside the function, because the pack never imports feature symbols at module level. compare_reviews() builds its agent with build_test_agent and a scripted runner instead of BaseAgent with a real model; every other line is the snippet's. The scripted runners answer in the OpenAI Responses shape (an "output" list of function_call items) and finish with isDone.
COMMON MODIFICATION PATTERNS: When section 4 changes, copy the new snippet into main() or compare_reviews() and keep the imports inside. When the agent loop changes how it hands tool results to the runner, update OrchestratorRunner.tool_messages, which reads the role "tool" messages.
WHAT NOT TO DO IN THIS FILE: 1. Do not start a real claude process or a real model call; the seam patch, the which patch and the scripted runner keep every run offline. 2. Do not import feature symbols at module level. 3. Do not run asyncio.run inside an async test; the host snippet runs in a sync TestCase, as a developer's script would.
KNOWN EDGE CASES: The host snippet calls ClaudeHost() with no cli_path, so the CLI must be found: shutil.which is patched in the probe module (it must call shutil.which through the module). On a machine with Claude Code installed, ~/.local/bin/claude.exe may exist, so the not-installed case patches ClaudeProbe.locate_cli rather than which alone.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 4, 6.1 (INV-15) and 6.2 (AC-1, EC-25).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_acceptance.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest import mock

from tests.agent_test_support import build_test_agent
from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    FAKE_CLI_PATH,
    HANG_GUARD_SECONDS,
    PRECONDITION_FAILED,
    PRECONDITION_NEXT_STEP,
    WHICH_TARGET,
    WORK_DIR,
    ClaudeHostCase,
    FakeClaudeSdk,
    answer_for,
    assistant_message,
    init_message,
    result_message,
)

TODO_PROMPT = "List the TODO comments in this repository."
TODO_ANSWER = "Found 3 TODO comments."
TODO_COST = 0.0421
REVIEW_PROMPTS = ("Review src/ for bugs and list each one with its file.", "Review src/ for missing tests and list each gap.")
CLAUDE_TOOL_NAMES = (
    "check_claude_ready",
    "list_claude_models",
    "get_claude_rate_limits",
    "spawn_claude_session",
    "continue_claude_session",
    "fork_claude_session",
    "launch_claude_subagents",
    "list_claude_sessions",
    "get_claude_session_info",
    "get_claude_session_messages",
    "wait_claude_turn",
    "get_claude_turn_result",
    "steer_claude_session",
    "interrupt_claude_turn",
    "track_claude_session_usage",
)


async def main() -> None:
    """The section 4 host snippet, with its imports moved inside."""
    from vidbyte.harnesses.native.claude import ClaudeHost
    from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
    from vidbyte.lib.enums.claude import ClaudePermissionMode

    async with ClaudeHost() as host:
        readiness = await host.check_claude_ready()
        if readiness.failure is not None:
            print(readiness.failure.code.value, readiness.failure.next_step)
            return
        request = ClaudeSpawnRequest(
            prompt="List the TODO comments in this repository.",
            cwd="C:/work/repo",
            permission_mode=ClaudePermissionMode.PLAN,
            max_budget_usd=0.50,
        )
        handle = await host.spawn_claude_session(request)
        result = await host.wait_claude_turn(handle, timeout_seconds=600)
        print(result.status.value, result.result_text)
        usage = await host.track_claude_session_usage(handle)
        print(usage.total_cost_usd)


async def compare_reviews(runner: Any) -> str:
    """The section 4 agent snippet, with its imports moved inside and build_test_agent binding the scripted runner."""
    from vidbyte import ToolPermission
    from vidbyte.harnesses.native.claude import ClaudeHost
    from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
    from vidbyte.lib.dataclasses.security import PermissionPolicy
    from vidbyte.tools.toolsets.claude import ClaudeTools

    async with ClaudeHost(max_live_sessions=4) as host:
        agent = build_test_agent(
            name="orchestrator",
            system_prompt="Run Claude Code sessions with your tools and compare what they find.",
            tools=ClaudeTools(host, ClaudeSpawnRequest(cwd="C:/work/repo", max_budget_usd=1.0)),
            permission_policy=PermissionPolicy(allowed=frozenset({ToolPermission.SAFE, ToolPermission.READ, ToolPermission.WRITE})),
            provider="openai",
            model_name="gpt-4.1",
            runner=runner,
        )
        reply = await agent.arun("Launch two Claude sessions that each review src/, then compare their findings.")
        return reply.content


class ScriptedResponse:
    """What a runner returns: the text and the raw provider payload the agent loop parses."""

    def __init__(self, text: str, raw: dict[str, Any]) -> None:
        self.text = text
        self.raw = raw


def function_call(name: str, arguments: dict[str, Any], call_id: str) -> ScriptedResponse:
    """Return a Responses-shaped reply that calls one tool."""
    return ScriptedResponse("", {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


class RecordingRunner:
    """Base for the scripted models: records each request and the tool messages it carried."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.tool_messages: list[dict[str, Any]] = []

    def record(self, prompt: str, kwargs: Mapping[str, Any]) -> list[dict[str, Any]]:
        messages = [dict(message) for message in kwargs.get("messages") or [] if isinstance(message, Mapping)]
        self.calls.append({"prompt": prompt, "tools": kwargs.get("tools"), "messages": messages})
        self.tool_messages = [message for message in messages if message.get("role") == "tool"]
        return self.tool_messages


class OrchestratorRunner(RecordingRunner):
    """The model in the agent snippet: launch two sessions, wait on each handle, then answer with both results."""

    def __init__(self, prompts: tuple[str, ...]) -> None:
        super().__init__()
        self.prompts = prompts

    def run(self, prompt: str, **kwargs: Any) -> ScriptedResponse:
        # Read the tool results so far, then take the next step of the plan.
        tool_messages = self.record(prompt, kwargs)
        step = len(self.calls)
        if step == 1:
            return function_call("launch_claude_subagents", {"prompts": list(self.prompts), "limit": 2}, "call_1")
        handles = json.loads(tool_messages[0]["content"])
        if step <= len(handles) + 1:
            return function_call("wait_claude_turn", {"handle_id": handles[step - 2]["handle_id"], "timeout_seconds": HANG_GUARD_SECONDS}, f"call_{step}")
        answers = [json.loads(message["content"])["result_text"] for message in tool_messages[1:]]
        return function_call("isDone", {"final_answer": "\n".join(answers)}, f"call_{step}")


class ToolSequenceRunner(RecordingRunner):
    """A model that calls the given tools in order, then finishes."""

    def __init__(self, steps: tuple[tuple[str, dict[str, Any]], ...]) -> None:
        super().__init__()
        self.steps = steps

    def run(self, prompt: str, **kwargs: Any) -> ScriptedResponse:
        self.record(prompt, kwargs)
        step = len(self.calls)
        if step <= len(self.steps):
            name, arguments = self.steps[step - 1]
            return function_call(name, arguments, f"call_{step}")
        return function_call("isDone", {"final_answer": "The Claude tools were unavailable."}, f"call_{step}")


def plain(value: Any) -> Any:
    """Return an enum's wire value, or the value itself."""
    return getattr(value, "value", value)


class HostSnippetTests(unittest.TestCase):
    """AC-1: the section 4 host snippet, run as a developer's script runs it."""

    def setUp(self) -> None:
        # Replace only the vendor SDK, through the seam.
        self.fake = FakeClaudeSdk()
        self.enterContext(self.fake.patched())

    def run_main(self) -> list[str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            asyncio.run(asyncio.wait_for(main(), HANG_GUARD_SECONDS))
        return buffer.getvalue().splitlines()

    def test_the_snippet_prints_the_status_the_answer_and_the_cost(self) -> None:
        self.fake.reply(TODO_PROMPT, init_message(), assistant_message("Searching for TODO comments."), result_message(result=TODO_ANSWER, total_cost_usd=TODO_COST))
        with mock.patch(WHICH_TARGET, return_value=FAKE_CLI_PATH):
            lines = self.run_main()
        self.assertEqual(lines, [f"completed {TODO_ANSWER}", str(TODO_COST)])
        # One readiness probe and one turn, both fakes, each closed once; only the turn sent a prompt.
        self.assertEqual(len(self.fake.clients), 2)
        turns = self.fake.turn_clients()
        self.assertEqual(len(turns), 1)
        self.assertEqual(self.fake.all_queries(), [TODO_PROMPT])
        self.assertEqual([client.disconnect_calls for client in self.fake.clients], [1, 1])
        for client in self.fake.clients:
            self.assertEqual(Path(client.options.cli_path), Path(FAKE_CLI_PATH))
        options = turns[0].options
        self.assertEqual(plain(options.permission_mode), "plan")
        self.assertEqual(options.max_budget_usd, 0.5)
        self.assertEqual(Path(options.cwd), Path("C:/work/repo"))

    def test_the_snippet_prints_the_not_installed_line_when_no_cli_is_found(self) -> None:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        with mock.patch.object(ClaudeProbe, "locate_cli", return_value=""):
            lines = self.run_main()
        self.assertEqual(lines, ["claude.not_installed " + CLAUDE_NEXT_STEPS["claude.not_installed"]])
        self.assertEqual(self.fake.clients, [])


class AgentSnippetTests(ClaudeHostCase):
    """Section 4's agent snippet, and EC-25 with INV-15 for a sync agent.run()."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.enterContext(mock.patch(WHICH_TARGET, return_value=FAKE_CLI_PATH))

    async def test_an_agent_launches_two_sessions_waits_on_both_and_compares_them(self) -> None:
        runner = OrchestratorRunner(REVIEW_PROMPTS)
        reply = await asyncio.wait_for(compare_reviews(runner), HANG_GUARD_SECONDS * 2)
        self.assertEqual(reply, "\n".join(answer_for(prompt) for prompt in REVIEW_PROMPTS))
        self.assertEqual(len(runner.calls), 4)
        offered = json.dumps(runner.calls[0]["tools"], default=str)
        for name in CLAUDE_TOOL_NAMES:
            self.assertIn(f'"{name}"', offered)
        # Two turns ran from the developer's bound request, and the host closed both clients.
        self.assertEqual(sorted(self.fake.all_queries()), sorted(REVIEW_PROMPTS))
        turns = self.fake.turn_clients()
        self.assertEqual(len(turns), 2)
        for client in turns:
            self.assertEqual(Path(client.options.cwd), Path("C:/work/repo"))
            self.assertEqual(client.options.max_budget_usd, 1.0)
            self.assertEqual(Path(client.options.cli_path), Path(FAKE_CLI_PATH))
        self.assertEqual([client.disconnect_calls for client in self.fake.clients], [1] * len(self.fake.clients))

    async def test_a_sync_agent_run_gets_the_precondition_error_and_starts_nothing(self) -> None:
        from vidbyte import ToolPermission
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.lib.dataclasses.security import PermissionPolicy
        from vidbyte.tools.toolsets.claude import ClaudeTools

        host = await self.open_host()
        runner = ToolSequenceRunner((("get_claude_rate_limits", {}), ("spawn_claude_session", {"prompt": "Review src/ for bugs."})))
        agent = build_test_agent(
            name="orchestrator",
            system_prompt="Run Claude Code sessions with your tools.",
            tools=ClaudeTools(host, ClaudeSpawnRequest(cwd=WORK_DIR)),
            permission_policy=PermissionPolicy(allowed=frozenset({ToolPermission.SAFE, ToolPermission.READ, ToolPermission.WRITE})),
            runner=runner,
        )
        # agent.run() starts its own event loop, here on a worker thread, while the host stays on this one.
        await asyncio.wait_for(asyncio.to_thread(agent.run, "Check the Claude rate limits, then review src/."), HANG_GUARD_SECONDS)
        contents = [str(message.get("content", "")).rstrip() for message in runner.tool_messages]
        self.assertEqual(len(contents), 2)
        for content in contents:
            self.assertIn(f"{PRECONDITION_FAILED}: ", content)
            self.assertTrue(content.endswith(f" Next step: {PRECONDITION_NEXT_STEP}"), content)
        self.assertEqual(self.fake.clients, [])


if __name__ == "__main__":
    unittest.main()
