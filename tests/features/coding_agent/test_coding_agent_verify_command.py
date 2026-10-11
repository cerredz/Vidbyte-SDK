"""FILE: tests/features/coding_agent/test_coding_agent_verify_command.py

PURPOSE: Prove CodingAgent's verify_command end to end: the run may finish only when the command exits with code 0, a failure goes back to the model as "Not done yet" feedback, and after max_verify_attempts failures the run ends with the model's last answer marked contract_unsatisfied instead of raising.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real tool loop (AgentRuntime, MiddlewarePipeline.review_finish, VerifyCommandMiddleware) with an offline scripted model and real bash subprocesses; also unit-tests FinishReview and the pipeline's default review.
ARCHITECTURE NOTE: Only the model is replaced. Each test scripts the model's turns, either an isDone tool call or a plain text answer, so both finish paths are covered, and counts command runs through a log file the command itself appends to. Commands are portable between Linux bash and Git for Windows bash.
FUNCTION INVENTORY: ReplayRunner replays scripted turns; tool_turn, finish_turn, and text_turn build them; _finish builds either finish turn by path; _verify_log counts command runs; _tool_feedback and _user_feedback read what the model was shown. Tests cover construction (invalid arguments, missing bash, middleware wiring), FinishReview and the pipeline, and run behavior (pass, fail then fix, never fixed, output cap, timeout, working directory, the model's own bash calls, contracts first, a fresh count per run, and a plain BaseAgent).
COMMON MODIFICATION PATTERNS: Script one more turn per scenario and assert on reply.content, reply.metadata, the log file, and the messages the model was sent, never on private agent state.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock BashTool, the runtime, or the middleware; they are the seams under test. 2. Do not use a real API key or open a socket.
KNOWN EDGE CASES: The isDone path shows feedback as the isDone tool result; the text path shows it as a user message after the model's own answer. On Windows a timed-out command keeps running after the call returns (BashTool EC-14), so the timeout test sleeps only briefly there.
RELATED DOCS: docs/design/coding-agent-verify-command.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

import itertools
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentLoopSettings, MinToolCalls
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.agents import FinishReview, FinishReviewAction
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.pipeline import MiddlewarePipeline

FIX_COMMAND = 'test -f done.txt || { echo "missing done.txt"; exit 3; }'
LOGGED_FAILURE = "echo run >> verify.log; echo still broken; exit 1"
FINISH_PATHS = ("is_done", "text")
CAP_BYTES = 50_000  # BASH_MAX_OUTPUT_BYTES, the real cap
OVER_CAP_BYTES = 60_000
TIME_LIMIT_SECONDS = 1.0  # patched over BASH_TIMEOUT_SECONDS
KILL_GRACE_SECONDS = 1.0  # patched over BASH_KILL_GRACE_SECONDS
SLEEP_SECONDS = 8 if sys.platform == "win32" else 30  # Windows cannot stop the sleep (EC-14)
_call_ids = itertools.count(1)


class ReplayRunner:
    """Offline model stand-in that replays scripted turns in order and records every request it receives."""

    def __init__(self, *turns: object) -> None:
        self._turns = list(turns)
        self.requests: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.requests.append(dict(kwargs))
        assert self._turns, "the runtime asked the model for more turns than the test scripted"
        return self._turns.pop(0)


class Bystander(AgentMiddleware):
    """Middleware that overrides no hook, so it accepts every finish."""


class RecordingReviewer(AgentMiddleware):
    """Middleware that returns a fixed finish review and records each time it is asked."""

    def __init__(self, review: FinishReview) -> None:
        self.review = review
        self.calls = 0

    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        self.calls += 1
        return self.review


def tool_turn(name: str, arguments: Mapping[str, object]) -> SimpleNamespace:
    # One chat-completions response that asks for one tool call.
    call = {"id": f"call_{next(_call_ids)}", "type": "function", "function": {"name": name, "arguments": json.dumps(dict(arguments))}}
    return SimpleNamespace(text="", raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]})


def finish_turn(answer: str) -> SimpleNamespace:
    # The model finishes by calling isDone with its answer.
    return tool_turn("isDone", {"final_answer": answer})


def text_turn(answer: str) -> SimpleNamespace:
    # The model finishes by answering in plain text, with no tool call.
    return SimpleNamespace(text=answer, raw={"choices": [{"message": {"role": "assistant", "content": answer}}]})


def _finish(path: str, answer: str) -> SimpleNamespace:
    # A finish attempt on the given path.
    return finish_turn(answer) if path == "is_done" else text_turn(answer)


def _verify_log(root: Path) -> list[str]:
    # One line per verification run, appended by the command itself.
    log = root / "verify.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _is_done_answer(request: Mapping[str, Any]) -> str:
    # The answer to the last isDone call the model was shown.
    [content] = [message["content"] for message in request["messages"] if message.get("role") == "tool" and message.get("name") == "isDone"][-1:]
    return str(content)


def _feedback_messages(request: Mapping[str, Any]) -> list[str]:
    # Every verification feedback message the model was shown.
    return [str(message["content"]) for message in request["messages"] if message.get("role") == "user" and str(message.get("content", "")).startswith("Not done yet")]


def _agent(coding_agent_cls: type, root: Path, runner: ReplayRunner, **options: Any) -> Any:
    # A CodingAgent over root with the offline runner bound.
    return build_test_agent(name="coder", system_prompt="Work.", root_dir=root, runner=runner, agent_type=coding_agent_cls, **options)


# --- construction ---------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "field"),
    [
        ({"verify_command": ""}, "verify_command"),
        ({"verify_command": "   "}, "verify_command"),
        ({"verify_command": 5}, "verify_command"),
        ({"verify_command": b"pytest"}, "verify_command"),
        ({"verify_command": "true", "max_verify_attempts": 0}, "max_verify_attempts"),
        ({"verify_command": "true", "max_verify_attempts": -1}, "max_verify_attempts"),
        ({"verify_command": "true", "max_verify_attempts": True}, "max_verify_attempts"),
        ({"verify_command": "true", "max_verify_attempts": 2.5}, "max_verify_attempts"),
        ({"verify_command": "true", "max_verify_attempts": "3"}, "max_verify_attempts"),
        ({"max_verify_attempts": 0}, "max_verify_attempts"),
    ],
)
def test_invalid_verify_arguments_fail_at_construction_naming_the_field(coding_agent_cls, tmp_path, options, field) -> None:
    # A bad argument fails before BaseAgent builds anything, and the
    # error names the field, never a later model turn.
    with pytest.raises(ConfigurationError) as raised:
        coding_agent_cls(name="coder", system_prompt="Work.", root_dir=tmp_path, **options)

    assert field in str(raised.value)
    assert raised.value.details["parameter"] == field


def test_missing_bash_with_verify_command_fails_at_construction(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # Without bash every verification would fail, so the agent is not
    # built at all; without a verify_command the same agent builds.
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    monkeypatch.chdir(empty_path)

    with pytest.raises(ConfigurationError) as raised:
        coding_agent_cls(name="coder", system_prompt="Work.", root_dir=tmp_path, verify_command="true")

    assert "bash" in str(raised.value)
    assert raised.value.details["parameter"] == "verify_command"
    assert coding_agent_cls(name="coder", system_prompt="Work.", root_dir=tmp_path).middleware == ()


def test_verifier_goes_after_the_caller_middleware_only_when_set(coding_agent_cls, tmp_path) -> None:
    # The caller's middleware passes through as-is without a command,
    # and the verifier is appended last with one.
    caller = Bystander()

    plain = coding_agent_cls(name="coder", system_prompt="Work.", root_dir=tmp_path, middleware=(caller,))
    verified = coding_agent_cls(name="coder", system_prompt="Work.", root_dir=tmp_path, middleware=(caller,), verify_command="true")

    assert plain.middleware == (caller,)
    assert verified.middleware[0] is caller
    assert [type(item).__name__ for item in verified.middleware] == ["Bystander", "VerifyCommandMiddleware"]
    assert verified.export_state() == plain.export_state()


# --- FinishReview and the pipeline ----------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        lambda: FinishReview.continue_with(""),
        lambda: FinishReview.continue_with("  \n"),
        lambda: FinishReview(action="accept"),
        lambda: FinishReview(action=FinishReviewAction.CONTINUE, feedback=None),
    ],
)
def test_finish_review_requires_feedback_to_continue(build) -> None:
    # A review that sends the model back with nothing to read, or with
    # an action that is not a FinishReviewAction, fails when built.
    with pytest.raises(ValueError):
        build()


@pytest.mark.asyncio
async def test_pipeline_without_reviewers_accepts_every_finish() -> None:
    # An empty pipeline, and middleware that overrides nothing, accept.
    ctx = MiddlewareContext(hook=MiddlewareHook.REVIEW_FINISH, agent_name="worker")

    assert (await MiddlewarePipeline(()).review_finish(ctx)).action is FinishReviewAction.ACCEPT
    assert (await MiddlewarePipeline((Bystander(), Bystander())).review_finish(ctx)).action is FinishReviewAction.ACCEPT


@pytest.mark.asyncio
async def test_pipeline_stops_at_the_first_review_that_refuses() -> None:
    # The first refusal decides, and a later reviewer, which may run a
    # slow command, is never asked.
    ctx = MiddlewareContext(hook=MiddlewareHook.REVIEW_FINISH, agent_name="worker")
    first = RecordingReviewer(FinishReview.continue_with("keep going"))
    second = RecordingReviewer(FinishReview.stop("stop"))

    review = await MiddlewarePipeline((Bystander(), first, second)).review_finish(ctx)

    assert (review.action, review.feedback) == (FinishReviewAction.CONTINUE, "keep going")
    assert (first.calls, second.calls) == (1, 0)


# --- runs -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_passing_command_lets_the_first_finish_end_the_run(coding_agent_cls, tmp_path) -> None:
    # One verification, a normal is_done stop, one model call, and the
    # command is not a tool call the model made.
    runner = ReplayRunner(finish_turn("All tests pass."))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command="echo run >> verify.log")

    reply = await agent.arun("Fix the bug.")

    assert reply.content == "All tests pass."
    assert reply.metadata["stop_reason"] == "is_done"
    assert reply.metadata["verify_command"] == {"passed": True, "attempts": 1, "last_exit_code": 0}
    assert reply.metadata["tool_call_states"] == ("succeeded",)
    assert len(runner.requests) == 1
    assert _verify_log(tmp_path) == ["run"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", FINISH_PATHS)
async def test_failed_command_sends_feedback_and_the_fixed_run_finishes(coding_agent_cls, tmp_path, path) -> None:
    # The model claims it is done too early, reads why it is not, fixes
    # the problem, and finishes again; only then does the run end.
    runner = ReplayRunner(
        _finish(path, "Done!"),
        tool_turn("write_text", {"path": "done.txt", "content": "ok"}),
        _finish(path, "Done, and the check passes."),
    )
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=FIX_COMMAND)

    reply = await agent.arun("Make the check pass.")

    assert reply.content == "Done, and the check passes."
    assert reply.metadata["stop_reason"] == ("is_done" if path == "is_done" else "final_response")
    assert reply.metadata["verify_command"] == {"passed": True, "attempts": 2, "last_exit_code": 0}
    assert len(runner.requests) == 3
    [feedback] = _feedback_messages(runner.requests[1])
    assert f"Not done yet: the verification command `{FIX_COMMAND}` failed (exit code 3)." in feedback
    assert "Fix the problem, then finish again." in feedback
    assert "missing done.txt" in feedback
    assert "exit code: 3" in feedback
    # The feedback is the last message on both paths. Before it, the
    # model reads its own answer, or on the isDone path the answer to
    # its isDone call, so no provider sees a call left unanswered.
    messages = list(runner.requests[1]["messages"])
    assert messages[-1] == {"role": "user", "content": feedback}
    if path == "text":
        assert messages[-2] == {"role": "assistant", "content": "Done!"}
    else:
        assert "finish attempt not accepted yet" in _is_done_answer(runner.requests[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("path", FINISH_PATHS)
@pytest.mark.parametrize("max_attempts", [1, 3])
async def test_never_fixed_run_ends_unverified_after_the_last_attempt(coding_agent_cls, tmp_path, path, max_attempts) -> None:
    # The run never reports success it did not earn: exactly
    # max_attempts command runs, the model's last answer, a failure stop
    # reason, and no exception.
    runner = ReplayRunner(*(_finish(path, f"Done, take {attempt}.") for attempt in range(1, max_attempts + 1)))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=LOGGED_FAILURE, max_verify_attempts=max_attempts)

    reply = await agent.arun("Make the check pass.")

    assert reply.content == f"Done, take {max_attempts}."
    assert reply.metadata["stop_reason"] == "contract_unsatisfied"
    assert reply.metadata["verify_command"] == {"passed": False, "attempts": max_attempts, "last_exit_code": 1}
    assert _verify_log(tmp_path) == ["run"] * max_attempts
    assert len(runner.requests) == max_attempts


@pytest.mark.asyncio
async def test_default_limit_is_three_attempts(coding_agent_cls, tmp_path) -> None:
    # Without max_verify_attempts the run gets three finish attempts.
    runner = ReplayRunner(*(finish_turn("Done.") for _ in range(3)))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=LOGGED_FAILURE)

    reply = await agent.arun("Make the check pass.")

    assert reply.metadata["verify_command"]["attempts"] == 3
    assert _verify_log(tmp_path) == ["run"] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize("path", FINISH_PATHS)
async def test_without_verify_command_the_run_is_unchanged(coding_agent_cls, tmp_path, path) -> None:
    # No command means no review: one model call, the normal stop
    # reason, and no verify_command metadata.
    runner = ReplayRunner(_finish(path, "Done."))
    agent = _agent(coding_agent_cls, tmp_path, runner, middleware=(Bystander(),))

    reply = await agent.arun("Fix the bug.")

    assert reply.content == "Done."
    assert reply.metadata["stop_reason"] == ("is_done" if path == "is_done" else "final_response")
    assert "verify_command" not in reply.metadata
    assert len(runner.requests) == 1


@pytest.mark.asyncio
async def test_output_over_the_cap_reaches_the_model_truncated_by_bash(coding_agent_cls, tmp_path) -> None:
    # The feedback carries the bash tool's own capped output whole:
    # the first 50,000 bytes, its truncation note, and the exit code,
    # with nothing cut by the tool-error formatter on the isDone path.
    runner = ReplayRunner(finish_turn("Done."), finish_turn("Done again."))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=f"yes | head -c {OVER_CAP_BYTES}; exit 1", max_verify_attempts=2)

    reply = await agent.arun("Make the check pass.")

    [feedback] = _feedback_messages(runner.requests[1])
    kept = "y\n" * (CAP_BYTES // 2)
    assert feedback.endswith(f"again.\n\n{kept}\n[output truncated: {OVER_CAP_BYTES - CAP_BYTES:,} bytes not shown]\nexit code: 1")
    assert reply.metadata["verify_command"] == {"passed": False, "attempts": 2, "last_exit_code": 1}


@pytest.mark.asyncio
async def test_command_past_the_time_limit_counts_as_a_failure(coding_agent_cls, bash_module, tmp_path, monkeypatch) -> None:
    # A command that never ends is stopped at the bash tool's limit, the
    # model is told it timed out, and the run ends with no exit code.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", TIME_LIMIT_SECONDS)
    monkeypatch.setattr(bash_module, "BASH_KILL_GRACE_SECONDS", KILL_GRACE_SECONDS)
    runner = ReplayRunner(finish_turn("Done."), finish_turn("Done again."))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=f"echo started; sleep {SLEEP_SECONDS}", max_verify_attempts=2)

    reply = await agent.arun("Make the check pass.")

    [feedback] = _feedback_messages(runner.requests[1])
    assert "failed (it timed out)." in feedback
    assert "started" in feedback
    assert "1-second time limit" in feedback
    assert reply.metadata["stop_reason"] == "contract_unsatisfied"
    assert reply.metadata["verify_command"] == {"passed": False, "attempts": 2, "last_exit_code": None}


@pytest.mark.asyncio
async def test_command_runs_in_root_dir_after_the_working_directory_changes(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # A relative root_dir is fixed at construction, so a later chdir to
    # a folder holding a decoy with the same name changes nothing.
    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    (project / "root").mkdir(parents=True)
    (elsewhere / "root").mkdir(parents=True)
    (project / "root" / "marker.txt").write_text("here", encoding="utf-8")
    monkeypatch.chdir(project)
    runner = ReplayRunner(finish_turn("Done."))
    agent = _agent(coding_agent_cls, Path("root"), runner, verify_command="test -f marker.txt && echo ran > ran-here.txt")
    monkeypatch.chdir(elsewhere)

    reply = await agent.arun("Fix the bug.")

    assert reply.metadata["verify_command"] == {"passed": True, "attempts": 1, "last_exit_code": 0}
    assert (project / "root" / "ran-here.txt").exists()
    assert not (elsewhere / "root" / "ran-here.txt").exists()
    assert not (elsewhere / "ran-here.txt").exists()


@pytest.mark.asyncio
async def test_model_bash_calls_do_not_trigger_verification(coding_agent_cls, tmp_path) -> None:
    # Only a finish attempt runs the command, even when the model runs
    # the very same command through its bash tool.
    command = "echo run >> verify.log"
    runner = ReplayRunner(tool_turn("bash", {"command": command}), tool_turn("bash", {"command": "echo hi"}), finish_turn("Done."))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=command)

    reply = await agent.arun("Fix the bug.")

    assert _verify_log(tmp_path) == ["run", "run"]
    assert reply.metadata["verify_command"] == {"passed": True, "attempts": 1, "last_exit_code": 0}
    assert reply.metadata["tool_call_states"] == ("succeeded", "succeeded", "succeeded")


@pytest.mark.asyncio
async def test_output_contracts_run_before_the_command(coding_agent_cls, tmp_path) -> None:
    # An answer the contracts reject never costs a command run; the
    # command runs once the contracts accept the finish.
    loop = AgentLoopSettings(output_contracts=(MinToolCalls(1),), max_contract_rejections=2)
    runner = ReplayRunner(finish_turn("Done."), tool_turn("bash", {"command": "echo working"}), finish_turn("Done now."))
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command="echo run >> verify.log", agent_loop_settings=loop)

    reply = await agent.arun("Fix the bug.")

    assert _feedback_messages(runner.requests[1]) == []
    assert "Not done yet" not in _is_done_answer(runner.requests[1])
    assert _verify_log(tmp_path) == ["run"]
    assert reply.content == "Done now."
    assert reply.metadata["verify_command"] == {"passed": True, "attempts": 1, "last_exit_code": 0}


@pytest.mark.asyncio
async def test_each_run_counts_its_own_attempts(coding_agent_cls, tmp_path) -> None:
    # The attempt count lives with the run, not the agent, so a second
    # run on the same agent starts again at one.
    runner = ReplayRunner(
        finish_turn("Done."),
        tool_turn("write_text", {"path": "done.txt", "content": "ok"}),
        finish_turn("Done now."),
        finish_turn("Still done."),
    )
    agent = _agent(coding_agent_cls, tmp_path, runner, verify_command=FIX_COMMAND, max_verify_attempts=2)

    first = await agent.arun("Make the check pass.")
    second = await agent.arun("Check again.")

    assert first.metadata["verify_command"] == {"passed": True, "attempts": 2, "last_exit_code": 0}
    assert second.metadata["verify_command"] == {"passed": True, "attempts": 1, "last_exit_code": 0}
    assert second.content == "Still done."


@pytest.mark.asyncio
@pytest.mark.parametrize("path", FINISH_PATHS)
async def test_plain_base_agent_finishes_as_before(tmp_path, path) -> None:
    # A BaseAgent with no finish reviewer ends on its first finish
    # attempt, with the normal stop reason and no extra model call.
    runner = ReplayRunner(_finish(path, "Done."))
    agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner, agent_type=BaseAgent, middleware=(Bystander(),))

    reply = await agent.arun("Do the task.")

    assert reply.content == "Done."
    assert reply.metadata["stop_reason"] == ("is_done" if path == "is_done" else "final_response")
    assert "verify_command" not in reply.metadata
    assert len(runner.requests) == 1
