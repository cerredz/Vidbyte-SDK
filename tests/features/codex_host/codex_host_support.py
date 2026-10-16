"""FILE: tests/features/codex_host/codex_host_support.py

PURPOSE: Shared helpers for the CodexHost feature pack: the spec's literal texts and tables, the privacy canaries, the openai-codex skip gate, a duck-typed stub host for the tool tests, and HostTestCase, which runs a real CodexHost against the in-memory app-server.
ROLE IN CODEBASE: Imported by every test module in tests/features/codex_host/. It imports nothing the feature adds and nothing from openai-codex at module level, so every module still collects before the feature exists and on CI, which installs only the dev extra.
ARCHITECTURE NOTE: HostTestCase.asyncSetUp patches the one seam spec section 13 names, vidbyte.harnesses.native.codex.connection.CodexClient, with the fake client from codex_host_fakes.py, and shutil.which with a recorder. Everything above the seam (CodexHost, its translators, preflight, pricing, records) runs unmocked. StubCodexHost stands in for CodexHost only in the tool tests, which spec section 13 allows because the tools import CodexHost under TYPE_CHECKING only.
FUNCTION INVENTORY: requires_sdk skips a class when openai-codex is missing; error_texts(exc) returns every text an error shows, its visible chain included; input_texts(params) reads a turn request's input items; HostTestCase.open_host / close_host / spawn / wait_done / assert_problem / assert_codex_error / run_in_other_loop drive a host, and patch_connection / patch_skill_functions / patch_platform / wait_for_request / wait_until / ask / count script and observe the fake app-server; StubCodexHost answers the twenty-seven host methods from scripted records; make_echo_tool builds a small dynamic tool; thread_suffix is the " Thread: <id>." the error mapper appends. The thread-helpers spec adds HELPER_METHODS, its message texts, four codes, four rows and eleven tool rows.
COMMON MODIFICATION PATTERNS: When the spec changes a next-step text, a tool name or a classification row, change the literal here, never by reading the production constant. Add a host helper here only when two or more modules need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.harnesses.native, vidbyte.lib.dataclasses.codex_host, the new enums or openai_codex at module level: a missing feature must fail each test, not abort collection. 2. Do not start a process or touch the network. 3. Do not copy production logic; tests assert the spec's literal values.
KNOWN EDGE CASES: The privacy canaries are unique strings, so finding one in any output proves a leak. StubCodexHost reports a handle RUNNING until a test marks it finished, which is how the live-turn cap sees running turns.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 9.2, 9.3 and 13; docs/spec/codex-host-thread-helpers/spec.md sections 8.5, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import itertools
import os
import threading
import unittest
from collections.abc import Awaitable, Callable
from typing import Any
from unittest import mock

from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolResult, ToolSpec
from vidbyte.tools.base import BaseTool

# Every wait in this pack is bounded, so a broken host fails a test instead of hanging the suite.
WAIT_SECONDS = 10.0
# Close may wait for interrupts (5 s each) and the close thread (10 s); this bound covers both.
CLOSE_SECONDS = 30.0

SDK_AVAILABLE = importlib.util.find_spec("openai_codex") is not None
requires_sdk = unittest.skipUnless(SDK_AVAILABLE, "requires the optional openai-codex extra")

# The seam spec section 13 names, patched by HostTestCase.
CLIENT_SEAM = "vidbyte.harnesses.native.codex.connection.CodexClient"
# The connection module, where the bounds are read at call time (spec section 13 "Constants").
CONNECTION_MODULE = "vidbyte.harnesses.native.codex.connection"
# An absolute path shaped like the resolved npm launcher on this platform; nothing runs it.
FAKE_CODEX_PATH = os.path.abspath(os.path.join(os.sep, "fake-codex", "bin", "codex"))

# Privacy canaries (AC-34, INV-9): finding one in any error, record or tool output is a leak.
SECRET_EMAIL = "canary.owner.7f3a@example.invalid"
ENV_SECRET = "env-canary-5d1c9b"
STDERR_SECRET = "stderr-canary-a8e2"
LINE_SECRET = "stdout-line-canary-c4f6"
CANARIES = (SECRET_EMAIL, ENV_SECRET, STDERR_SECRET, LINE_SECRET)

MINIMUM_VERSION = "0.151.0"

# Spec section 9.3, verbatim.
EXPERIMENTAL_API_TEXT = "Dynamic tools on CodexHost require CodexClientSettings(experimental_api=True)."
USER_REVIEWER_TEXT = "Set approvals_reviewer=AUTO_REVIEW or GUARDIAN_SUBAGENT, and set it whenever approval_policy is set. To continue a thread whose reviewer is user, pass overrides=CodexSpawnRequest(approvals_reviewer=AUTO_REVIEW), or set it in the CodexHostTools spawn_defaults. Answering approval requests in code needs set_codex_approval_handler, which this release does not include."
UNREGISTERED_TOOL_TEXT = "No Vidbyte tool is registered for this thread on this host."
PIP_INSTALL_FRAGMENT = 'pip install "vidbyte-sdk[codex]"'

# Spec section 9.2 error-code table: value -> next step, verbatim.
NEXT_STEPS = {
    "codex.not_installed": "Install the Codex CLI (npm install -g @openai/codex) or pass CodexClientSettings(codex_bin=...).",
    "codex.version_unsupported": "Run codex update, then open a new CodexHost.",
    "codex.not_signed_in": "Run codex login, then retry.",
    "codex.usage_limited": "Wait until the usage window resets, or sign Codex in with an API key.",
    "codex.model_unknown": "Pick a model from list_codex_models.",
    "codex.session_not_found": "Find the thread with list_codex_threads, or use a handle this host returned; continue a finished turn instead of steering it.",
    "codex.session_busy": "Steer or wait on the running turn, or fork the thread.",
    "codex.budget_exhausted": "Raise max_output_tokens or the goal token_budget, or split the work.",
    "codex.api_error": "Retry with backoff, and check the service status if it persists.",
    "codex.permission_denied": "Allow the action (approval_policy, approvals_reviewer or sandbox), or ask for work that does not need it.",
    "codex.sandbox_not_ready": "Set up the Codex Windows sandbox, or run with sandbox=FULL_ACCESS.",
    "codex.schema_violation": "Continue the thread and ask for output that matches the schema; the raw text is in result.final_response.",
    "codex.process_exited": "Open a new CodexHost and continue the thread by id.",
    "codex.protocol_mismatch": "Match the Codex CLI and openai-codex versions (codex update), then open a new CodexHost.",
    "codex.turn_timed_out": "Raise timeout_seconds, or continue the thread to finish the work.",
    "codex.fork_failed": "Fork from a completed turn.",
    "codex.response_invalid": "Continue the thread and ask for a final answer.",
    "configuration.invalid_argument": "Fix the argument or setup named in the message, then call again.",
    "configuration.unsupported_combination": USER_REVIEWER_TEXT,
    # docs/spec/codex-host-thread-helpers/spec.md section 9.2 "New failure codes", verbatim.
    "codex.command_not_run": "Read what Codex recorded with get_codex_goal or list_codex_turns, then start the run again.",
    "codex.skill_not_found": "Pick a skill that list_codex_skills reports for the same working folder, and pass its exact name.",
    "codex.skill_disabled": "Enable the skill in your Codex configuration, or pick an enabled skill that list_codex_skills reports.",
    "codex.goal_unfinished": "Continue the thread with continue_codex_thread until its goal is complete, or clear the goal from a Codex client, then compact the thread again.",
}

# Spec section 12.3 row 1: the fifteen new FailureCode members, in their required order, then the four the
# thread-helpers spec (section 12.3 row 1) inserts right after CODEX_TURN_TIMED_OUT.
NEW_FAILURE_CODES = (
    ("CODEX_NOT_INSTALLED", "codex.not_installed"),
    ("CODEX_VERSION_UNSUPPORTED", "codex.version_unsupported"),
    ("CODEX_NOT_SIGNED_IN", "codex.not_signed_in"),
    ("CODEX_USAGE_LIMITED", "codex.usage_limited"),
    ("CODEX_MODEL_UNKNOWN", "codex.model_unknown"),
    ("CODEX_SESSION_NOT_FOUND", "codex.session_not_found"),
    ("CODEX_SESSION_BUSY", "codex.session_busy"),
    ("CODEX_BUDGET_EXHAUSTED", "codex.budget_exhausted"),
    ("CODEX_API_ERROR", "codex.api_error"),
    ("CODEX_PERMISSION_DENIED", "codex.permission_denied"),
    ("CODEX_SANDBOX_NOT_READY", "codex.sandbox_not_ready"),
    ("CODEX_SCHEMA_VIOLATION", "codex.schema_violation"),
    ("CODEX_PROCESS_EXITED", "codex.process_exited"),
    ("CODEX_PROTOCOL_MISMATCH", "codex.protocol_mismatch"),
    ("CODEX_TURN_TIMED_OUT", "codex.turn_timed_out"),
    ("CODEX_COMMAND_NOT_RUN", "codex.command_not_run"),
    ("CODEX_SKILL_NOT_FOUND", "codex.skill_not_found"),
    ("CODEX_SKILL_DISABLED", "codex.skill_disabled"),
    ("CODEX_GOAL_UNFINISHED", "codex.goal_unfinished"),
)

# Spec section 9.2: class / phase / severity / disposition values for each new code.
CLASSIFICATION_ROWS = {
    "codex.not_installed": ("terminal", "configuration", "critical", "raise"),
    "codex.version_unsupported": ("terminal", "configuration", "critical", "raise"),
    "codex.not_signed_in": ("terminal", "configuration", "error", "raise"),
    "codex.usage_limited": ("transient", "resource", "error", "stop"),
    "codex.model_unknown": ("terminal", "configuration", "error", "raise"),
    "codex.session_not_found": ("terminal", "session", "error", "raise"),
    "codex.session_busy": ("transient", "session", "warning", "route"),
    "codex.budget_exhausted": ("terminal", "resource", "warning", "stop"),
    "codex.api_error": ("transient", "model", "error", "route"),
    "codex.permission_denied": ("terminal", "action", "error", "stop"),
    "codex.sandbox_not_ready": ("terminal", "configuration", "error", "raise"),
    "codex.schema_violation": ("model_retryable", "output", "error", "route"),
    "codex.process_exited": ("transient", "resource", "critical", "route"),
    "codex.protocol_mismatch": ("terminal", "configuration", "critical", "raise"),
    "codex.turn_timed_out": ("transient", "resource", "warning", "stop"),
    "codex.command_not_run": ("terminal", "session", "error", "raise"),
    "codex.skill_not_found": ("terminal", "configuration", "error", "raise"),
    "codex.skill_disabled": ("terminal", "configuration", "error", "raise"),
    "codex.goal_unfinished": ("terminal", "session", "warning", "raise"),
}

# Spec section 9.2 tool table: (name, class name, permission, parameters, required), in R3 order.
TOOL_TABLE = (
    ("check_codex_ready", "CheckCodexReadyTool", "read", (), ()),
    ("get_codex_rate_limits", "GetCodexRateLimitsTool", "read", (), ()),
    ("list_codex_models", "ListCodexModelsTool", "read", ("include_hidden",), ()),
    (
        "spawn_codex_thread",
        "SpawnCodexThreadTool",
        "write",
        ("prompt", "goal_objective", "goal_token_budget", "model", "effort", "name", "max_output_tokens", "timeout_seconds", "output_schema"),
        (),
    ),
    (
        "continue_codex_thread",
        "ContinueCodexThreadTool",
        "write",
        ("thread_id", "prompt", "model", "effort", "max_output_tokens", "timeout_seconds"),
        ("thread_id", "prompt"),
    ),
    ("fork_codex_thread", "ForkCodexThreadTool", "write", ("thread_id", "from_turn_id", "exclude_turns"), ("thread_id",)),
    (
        "list_codex_threads",
        "ListCodexThreadsTool",
        "read",
        ("cwd", "search", "archived", "source_kinds", "sort", "sort_direction", "cursor"),
        (),
    ),
    ("read_codex_thread", "ReadCodexThreadTool", "read", ("thread_id", "include_turns"), ("thread_id",)),
    ("wait_codex_turn", "WaitCodexTurnTool", "read", ("thread_id", "turn_id", "timeout_seconds"), ("thread_id", "turn_id")),
    ("get_codex_turn_result", "GetCodexTurnResultTool", "read", ("thread_id", "turn_id"), ("thread_id", "turn_id")),
    ("steer_codex_turn", "SteerCodexTurnTool", "write", ("thread_id", "turn_id", "prompt"), ("thread_id", "turn_id", "prompt")),
    ("interrupt_codex_turn", "InterruptCodexTurnTool", "write", ("thread_id", "turn_id"), ("thread_id", "turn_id")),
    ("track_codex_thread_usage", "TrackCodexThreadUsageTool", "read", ("thread_id",), ("thread_id",)),
    ("launch_codex_subagents", "LaunchCodexSubagentsTool", "write", ("prompts",), ("prompts",)),
    (
        "start_codex_review",
        "StartCodexReviewTool",
        "write",
        ("thread_id", "target_kind", "branch", "sha", "title", "instructions", "delivery"),
        ("thread_id", "target_kind"),
    ),
    # docs/spec/codex-host-thread-helpers/spec.md section 9.2 tool table, rows 16 to 26; delete_codex_thread has no tool.
    ("list_recent_codex_threads", "ListRecentCodexThreadsTool", "read", ("cwd", "limit"), ()),
    ("list_codex_threads_since", "ListCodexThreadsSinceTool", "read", ("since", "cwd", "limit"), ("since",)),
    ("search_codex_threads", "SearchCodexThreadsTool", "read", ("query", "cwd", "limit"), ("query",)),
    ("get_codex_thread_lineage", "GetCodexThreadLineageTool", "read", ("thread_id",), ("thread_id",)),
    ("list_codex_turns", "ListCodexTurnsTool", "read", ("thread_id", "cursor", "limit"), ("thread_id",)),
    ("compact_codex_thread", "CompactCodexThreadTool", "write", ("thread_id",), ("thread_id",)),
    ("get_codex_goal", "GetCodexGoalTool", "read", ("thread_id",), ("thread_id",)),
    ("run_codex_goal", "RunCodexGoalTool", "write", ("objective", "token_budget"), ("objective",)),
    ("list_codex_skills", "ListCodexSkillsTool", "read", ("cwd",), ()),
    ("run_codex_skill", "RunCodexSkillTool", "write", ("skill", "prompt"), ("skill", "prompt")),
    ("run_codex_openai_docs", "RunCodexOpenaiDocsTool", "write", ("question",), ("question",)),
)
TOOL_NAMES = tuple(row[0] for row in TOOL_TABLE)

# docs/spec/codex-host-thread-helpers/spec.md section 8.5: the twelve new CodexHost methods, in their order.
HELPER_METHODS = (
    "list_recent_codex_threads",
    "list_codex_threads_since",
    "search_codex_threads",
    "get_codex_thread_lineage",
    "list_codex_turns",
    "compact_codex_thread",
    "delete_codex_thread",
    "get_codex_goal",
    "run_codex_goal",
    "list_codex_skills",
    "run_codex_skill",
    "run_codex_openai_docs",
)

# docs/spec/codex-host-thread-helpers/spec.md section 9.2 "Message constants" and tool texts, verbatim.
RUNNING_THREAD_MESSAGE = "Codex reports a running turn on the thread, so it cannot be compacted or deleted until that turn ends."
LIMIT_MESSAGE = "{operation} limit must be an integer from {minimum} to {maximum}."
SINCE_MESSAGE = "{operation} since must be a non-negative integer number of Unix seconds."
QUERY_MESSAGE = "{operation} query must be a non-empty string."
GOAL_UNFINISHED_MESSAGE = "Codex reports an unfinished goal (status {status}) on the thread, and loading the thread to compact it could let Codex continue that goal."
OWN_INPUT_MESSAGE = "{operation} takes its input as arguments; leave request.prompt and request.goal at their defaults."
EPHEMERAL_SKILL_MESSAGE = "{operation} needs a stored thread to confirm the skill run, so request.thread.ephemeral must be False."
SKILL_NAME_MESSAGE = "{operation} skill must be a non-empty string."
SKILL_NOT_FOUND_MESSAGE = "Codex lists no skill named '{skill}' for {place}. Enabled skills: {names}."
SKILL_DISABLED_MESSAGE = "The Codex skill '{skill}' is disabled for {place}."
NO_GOAL_MESSAGE = "Codex reports no goal on the thread after the goal run started."
OBJECTIVE_DIFFERS_MESSAGE = "Codex reports a goal objective different from the one sent."
BUDGET_DIFFERS_MESSAGE = "Codex reports a goal token budget of {stored}, not the {sent} that was sent."
GOAL_UNCHECKED_MESSAGE = " The goal run on thread {thread_id} was interrupted because its goal could not be checked."
INPUT_NOT_RECORDED_MESSAGE = "Codex recorded no input for the turn of skill '{skill}' within {seconds} seconds, so the skill run could not be confirmed."
SKILL_DROPPED_MESSAGE = "Codex recorded the turn's input without the skill '{skill}', so the run did not use the skill."
SKILL_UNCHECKED_MESSAGE = " The skill run on thread {thread_id} was interrupted because its input could not be checked."
COMPACT_STARTED_TEXT = "Compaction started on thread {thread_id}; Codex compacts its history in the background and finishes only while this host stays open."
NO_GOAL_TEXT = "Thread {thread_id} has no goal."
# {place} of the skill messages when the caller's cwd is "".
APP_SERVER_PLACE = "the app-server's working folder"
# The module that imports the read-back bounds by name, where spec section 13 says a test may patch them.
SKILL_FUNCTIONS_MODULE = "vidbyte.harnesses.native.codex.skill_functions"
# The existing preflight text for a thread with a running turn on this host (codex-host BUSY_MESSAGE, spec EC-17).
BUSY_TEXT = "The thread already has a running turn on this host."


def thread_suffix(thread_id: str) -> str:
    """The text CodexErrorMapper.error appends to a message when it names a thread (spec section 9.2)."""
    return f" Thread: {thread_id}."


def error_texts(exc: BaseException) -> list[str]:
    """Return every text an error shows: its message, repr, packet and next step, and those of its visible chain.

    Spec section 12.3 row 10 has every caller raise the mapped error from None, so a chained SDK
    exception (a TransportClosedError carries the stderr tail) is a leak like any other.
    """
    texts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        texts.extend((str(current), repr(current), str(getattr(current, "message", "")), str(getattr(current, "details", ""))))
        texts.append(str(getattr(current, "next_step", "")))
        # A suppressed context (raise ... from None) is shown to no one, so it is not followed.
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return texts


def assert_no_canary(case: unittest.TestCase, texts: list[str], canaries: tuple[str, ...] = CANARIES) -> None:
    """Fail when any canary appears in any of the given texts."""
    for text in texts:
        for canary in canaries:
            case.assertNotIn(canary, text)


def input_texts(params: dict[str, Any]) -> list[tuple[str, str]]:
    """The (type, text) pairs of a turn/start or turn/steer request's input items."""
    return [(item["type"], item.get("text", "")) for item in params["input"]]


class HostTestCase(unittest.IsolatedAsyncioTestCase):
    """Runs a real CodexHost against the in-memory app-server at the spec section 13 seam."""

    async def asyncSetUp(self) -> None:
        # The fake imports openai-codex, so it is loaded only here, inside gated classes.
        from tests.features.codex_host import codex_host_fakes

        self.fakes = codex_host_fakes
        self.server = codex_host_fakes.FakeAppServer()
        self.addCleanup(self._assert_fake_healthy)
        self.addCleanup(self.server.release_all)
        self.which_calls: list[str] = []
        self.which_result: str | None = FAKE_CODEX_PATH
        # Importing the connection module first makes a missing feature fail here, with ModuleNotFoundError.
        importlib.import_module(CONNECTION_MODULE)
        seam = mock.patch(CLIENT_SEAM, codex_host_fakes.client_class(self.server))
        seam.start()
        self.addCleanup(seam.stop)
        which = mock.patch("shutil.which", side_effect=self._which)
        which.start()
        self.addCleanup(which.stop)

    def _which(self, *args: Any, **kwargs: Any) -> str | None:
        self.which_calls.append(args[0] if args else kwargs.get("cmd"))
        return self.which_result

    def _assert_fake_healthy(self) -> None:
        # A bug in the fake must surface as a failure, never as a silently wrong answer.
        self.assertEqual(self.server.handler_errors, [])

    def patch_connection(self, name: str, value: Any) -> None:
        """Patch one bound in the connection module's namespace for this test."""
        patcher = mock.patch(f"{CONNECTION_MODULE}.{name}", value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def patch_skill_functions(self, name: str, value: Any) -> None:
        """Patch one read-back bound where skill_functions imported it by name (thread-helpers spec section 13)."""
        patcher = mock.patch(f"{SKILL_FUNCTIONS_MODULE}.{name}", value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def patch_platform(self, value: str) -> None:
        """Make CodexPreflight see this platform; spec section 13 says it reads sys.platform at call time."""
        patcher = mock.patch("sys.platform", value)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def wait_for_request(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None = None, count: int = 1) -> Any:
        """Wait, off the loop, until the count-th matching request reached the fake app-server."""
        return await asyncio.to_thread(self.server.wait_for, method, predicate, count)

    async def wait_until(self, condition: Callable[[], bool], what: str) -> None:
        """Wait, off the loop, until a condition on the fake app-server holds."""
        await asyncio.to_thread(self.server.wait_until, condition, what)

    async def ask(self, method: str, params: dict[str, Any] | None) -> Any:
        """Send a server request through the real SDK reader thread and return the client's answer."""
        future = self.server.server_request(method, params)
        return await asyncio.wait_for(asyncio.wrap_future(future), WAIT_SECONDS)

    def count(self, method: str, predicate: Callable[[dict[str, Any]], bool] | None = None) -> int:
        """How many matching requests the fake app-server has received so far."""
        return len(self.server.matching(method, predicate))

    async def open_host(self, settings: Any = None) -> Any:
        from vidbyte.harnesses.native.codex import CodexHost

        host = CodexHost(settings)
        await asyncio.wait_for(host.__aenter__(), WAIT_SECONDS)
        self.addAsyncCleanup(self.close_host, host)
        return host

    async def close_host(self, host: Any) -> None:
        await asyncio.wait_for(host.__aexit__(None, None, None), CLOSE_SECONDS)

    async def spawn(self, host: Any, prompt: Any = "Summarize the readme in one sentence.", **fields: Any) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        request = CodexSpawnRequest(prompt=prompt, **fields)
        return await asyncio.wait_for(host.spawn_codex_thread(request), WAIT_SECONDS)

    async def wait_done(self, host: Any, handle: Any) -> Any:
        snapshot = await asyncio.wait_for(host.wait_codex_turn(handle, timeout_seconds=WAIT_SECONDS), WAIT_SECONDS + 5.0)
        self.assertNotEqual(snapshot.status.value, "inProgress", f"turn {handle.turn_id} never ended")
        return snapshot

    def assert_problem(self, snapshot: Any, status: str, code: str | None) -> None:
        """Check a snapshot's wire status and its problem: none, or the code with its section 9.2 next step."""
        self.assertEqual(snapshot.status.value, status, snapshot)
        if code is None:
            self.assertIsNone(snapshot.problem, snapshot)
            return
        self.assertIsNotNone(snapshot.problem, snapshot)
        self.assertEqual(snapshot.problem.code.value, code, snapshot.problem.message)
        self.assertEqual(snapshot.problem.next_step, NEXT_STEPS[code])

    async def assert_codex_error(self, awaitable: Awaitable[Any], code: str) -> Any:
        """Await a host call, require CodexAgentError with the code, and check its contract (INV-8)."""
        from vidbyte.lib.enums.codex import CodexHostOperation
        from vidbyte.lib.errors import CodexAgentError

        with self.assertRaises(CodexAgentError) as caught:
            await asyncio.wait_for(awaitable, WAIT_SECONDS)
        error = caught.exception
        self.assertEqual(error.failure_code, code, error.message)
        self.assertIn(error.operation, {member.value for member in CodexHostOperation})
        self.assertEqual(error.next_step, NEXT_STEPS.get(code, error.next_step))
        self.assertTrue(error.next_step)
        return error

    async def run_in_other_loop(self, factory: Callable[[], Awaitable[Any]]) -> BaseException | None:
        """Run one host call on a second event loop in its own thread; return what it raised."""
        outcome: list[BaseException | None] = []

        def run() -> None:
            try:
                asyncio.run(asyncio.wait_for(factory(), WAIT_SECONDS))
                outcome.append(None)
            except BaseException as exc:  # the caller asserts on the exact type
                outcome.append(exc)

        worker = threading.Thread(target=run, name="other-loop", daemon=True)
        worker.start()
        await asyncio.get_running_loop().run_in_executor(None, worker.join, WAIT_SECONDS)
        self.assertEqual(len(outcome), 1, "the call on the other loop never finished")
        return outcome[0]


class _EchoTool(BaseTool):
    """A small READ tool used as a dynamic tool or as a spawn_defaults posture entry."""

    def __init__(self, name: str = "echo_text", permission: ToolPermission = ToolPermission.READ) -> None:
        self._name = name
        self._permission = permission
        self.calls: list[ToolCall] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description="Returns the text it was given.",
            permission=self._permission,
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult.success(self._name, f"echo: {call.arguments.get('text', '')}")


def make_echo_tool(name: str = "echo_text", permission: ToolPermission = ToolPermission.READ) -> BaseTool:
    """Build one fresh echo tool."""
    return _EchoTool(name, permission)


class StubCodexHost:
    """A duck-typed CodexHost for the tool tests: it records every call and answers from records."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.raises: dict[str, BaseException] = {}
        self.gates: dict[str, asyncio.Event] = {}
        self.finished: set[tuple[str, str]] = set()
        # When True, get_codex_goal answers None, as for a thread without a goal.
        self.goal_missing = False
        self._ids = itertools.count(1)

    def names(self) -> list[str]:
        return [call[0] for call in self.calls]

    def last(self, name: str) -> tuple[tuple[Any, ...], dict[str, Any]]:
        matches = [(args, kwargs) for called, args, kwargs in self.calls if called == name]
        if not matches:
            raise AssertionError(f"the stub host never received {name}; it received {self.names()}")
        return matches[-1]

    def finish(self, handle: Any) -> None:
        self.finished.add((handle.thread_id, handle.turn_id))

    async def _enter(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))
        gate = self.gates.get(name)
        if gate is not None:
            await gate.wait()
        error = self.raises.get(name)
        if error is not None:
            raise error

    def _handle(self, thread_id: str = "") -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        number = next(self._ids)
        return CodexTurnHandle(thread_id=thread_id or f"thr-stub-{number}", turn_id=f"turn-stub-{number}")

    def _snapshot(self, handle: Any) -> Any:
        from vidbyte.lib.dataclasses.codex import CodexItem, CodexRunResult, CodexUsage
        from vidbyte.lib.dataclasses.codex_host import CodexTurnSnapshot
        from vidbyte.lib.enums.codex import CodexTurnStatus

        if (handle.thread_id, handle.turn_id) not in self.finished:
            return CodexTurnSnapshot(handle=handle, status=CodexTurnStatus.RUNNING)
        result = CodexRunResult(
            thread_id=handle.thread_id,
            turn_id=handle.turn_id,
            status="completed",
            final_response="Stub final answer.",
            duration_ms=1200,
            usage=CodexUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            items=(CodexItem(id="item-stub-1", type="agentMessage", fields={"text": "Stub final answer."}),),
            last_usage=CodexUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            usage_available=True,
        )
        return CodexTurnSnapshot(handle=handle, status=CodexTurnStatus.COMPLETED, result=result)

    def _thread_info(self, thread_id: str) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadInfo
        from vidbyte.lib.enums.codex import CodexThreadStatus

        return CodexThreadInfo(
            thread_id=thread_id,
            name="",
            preview="stub preview",
            cwd=os.path.abspath(os.sep),
            status=CodexThreadStatus.IDLE,
            model="gpt-5.5",
            model_provider="openai",
            created_at=1,
            updated_at=2,
            forked_from_id="",
            ephemeral=False,
        )

    async def check_codex_ready(self) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexReadiness
        from vidbyte.lib.enums.codex import CodexAccountKind, CodexSandboxReadiness

        await self._enter("check_codex_ready")
        return CodexReadiness(
            ready=True,
            version="0.162.1",
            minimum_version=MINIMUM_VERSION,
            signed_in=True,
            account=CodexAccountKind.CHATGPT,
            plan_type="plus",
            sandbox=CodexSandboxReadiness.READY,
            problems=(),
        )

    async def get_codex_rate_limits(self) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexRateLimits, CodexRateLimitWindow

        await self._enter("get_codex_rate_limits")
        window = CodexRateLimitWindow(used_percent=12, resets_at=1_760_000_000, window_minutes=300)
        return CodexRateLimits(ordinary_usage_allowed=True, plan_type="plus", limit_reached="", primary=window, secondary=None)

    async def list_codex_models(self, include_hidden: bool = False) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexModelInfo

        await self._enter("list_codex_models", include_hidden=include_hidden)
        return (
            CodexModelInfo(
                model_id="gpt-5.5",
                model="gpt-5.5",
                display_name="GPT-5.5",
                description="Stub model.",
                hidden=False,
                is_default=True,
                default_effort="medium",
                efforts=("low", "medium"),
            ),
        )

    async def spawn_codex_thread(self, request: Any) -> Any:
        await self._enter("spawn_codex_thread", request)
        return self._handle()

    async def continue_codex_thread(self, thread_id: str, input: Any, overrides: Any = None) -> Any:
        await self._enter("continue_codex_thread", thread_id, input, overrides=overrides)
        return self._handle(thread_id)

    async def fork_codex_thread(self, thread_id: str, from_turn_id: str = "", exclude_turns: bool = False, overrides: Any = None) -> Any:
        await self._enter("fork_codex_thread", thread_id, from_turn_id=from_turn_id, exclude_turns=exclude_turns, overrides=overrides)
        return self._thread_info("thr-stub-fork")

    async def list_codex_threads(self, cwd: str = "", search: str = "", archived: bool = False, source_kinds: tuple[Any, ...] = (), sort: Any = None, sort_direction: Any = None, cursor: str = "") -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadPage

        await self._enter("list_codex_threads", cwd=cwd, search=search, archived=archived, source_kinds=source_kinds, sort=sort, sort_direction=sort_direction, cursor=cursor)
        return CodexThreadPage(threads=(self._thread_info("thr-stub-listed"),), next_cursor="stub-cursor")

    async def read_codex_thread(self, thread_id: str, include_turns: bool = False) -> Any:
        await self._enter("read_codex_thread", thread_id, include_turns=include_turns)
        return self._thread_info(thread_id)

    async def wait_codex_turn(self, handle: Any, timeout_seconds: float | None = None) -> Any:
        await self._enter("wait_codex_turn", handle, timeout_seconds=timeout_seconds)
        return self._snapshot(handle)

    async def get_codex_turn_result(self, handle: Any) -> Any:
        await self._enter("get_codex_turn_result", handle)
        return self._snapshot(handle)

    async def steer_codex_turn(self, handle: Any, input: Any) -> Any:
        await self._enter("steer_codex_turn", handle, input)
        return handle

    async def interrupt_codex_turn(self, handle: Any) -> None:
        await self._enter("interrupt_codex_turn", handle)

    async def track_codex_thread_usage(self, thread_id: str) -> Any:
        from vidbyte.lib.dataclasses.codex import CodexUsage
        from vidbyte.lib.dataclasses.codex_host import CodexThreadUsage, CodexTurnUsage
        from vidbyte.lib.enums.codex import CodexTurnStatus

        await self._enter("track_codex_thread_usage", thread_id)
        usage = CodexUsage(input_tokens=10, output_tokens=5, total_tokens=15)
        turn = CodexTurnUsage(turn_id="turn-stub-1", status=CodexTurnStatus.COMPLETED, usage=usage, usage_available=True)
        return CodexThreadUsage(thread_id=thread_id, total=usage, turns=(turn,), cost_usd=0.001, cost_complete=True)

    async def launch_codex_subagents(self, prompts: Any, request: Any = None, limit: int | None = None) -> Any:
        await self._enter("launch_codex_subagents", tuple(prompts), request=request, limit=limit)
        return tuple(self._handle() for _ in prompts)

    async def start_codex_review(self, thread_id: str, target: Any, delivery: Any = None) -> Any:
        await self._enter("start_codex_review", thread_id, target, delivery=delivery)
        return self._handle(thread_id)

    # ----- the twelve thread-helper methods (docs/spec/codex-host-thread-helpers/spec.md section 8.5) -----
    # Each records its arguments by name, however the tool passed them, so a test reads one normalized mapping.

    def _summary(self, thread_id: str, parent: str | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadSummary

        return CodexThreadSummary(thread_id=thread_id, title="Stub thread", created_at=1, updated_at=2, parent_thread_id=parent, model="gpt-5.5")

    async def list_recent_codex_threads(self, cwd: str, limit: int = 20) -> Any:
        await self._enter("list_recent_codex_threads", cwd=cwd, limit=limit)
        return (self._summary("thr-stub-recent"),)

    async def list_codex_threads_since(self, cwd: str, since: int, limit: int = 20) -> Any:
        await self._enter("list_codex_threads_since", cwd=cwd, since=since, limit=limit)
        return (self._summary("thr-stub-since"),)

    async def search_codex_threads(self, cwd: str, query: str, limit: int = 20) -> Any:
        await self._enter("search_codex_threads", cwd=cwd, query=query, limit=limit)
        return (self._summary("thr-stub-found"),)

    async def get_codex_thread_lineage(self, thread_id: str) -> Any:
        await self._enter("get_codex_thread_lineage", thread_id=thread_id)
        return (self._summary(thread_id, parent="thr-stub-parent"), self._summary("thr-stub-parent"))

    async def list_codex_turns(self, thread_id: str, cursor: str = "", limit: int | None = None) -> Any:
        from vidbyte.lib.dataclasses.codex import CodexItem
        from vidbyte.lib.dataclasses.codex_host import CodexStoredTurn, CodexTurnPage
        from vidbyte.lib.enums.codex import CodexTurnStatus

        await self._enter("list_codex_turns", thread_id=thread_id, cursor=cursor, limit=limit)
        items = (
            CodexItem(id="item-stub-user", type="userMessage", fields={"clientId": None, "content": [{"type": "text", "text": "Fix it.", "text_elements": []}]}),
            CodexItem(id="item-stub-final", type="agentMessage", fields={"text": "Stub final answer.", "phase": "final_answer"}),
        )
        turn = CodexStoredTurn(turn_id="turn-stub-1", status=CodexTurnStatus.COMPLETED, final_response="Stub final answer.", error_message="", started_at=1, completed_at=2, items=items)
        return CodexTurnPage(turns=(turn,), next_cursor="stub-turn-cursor")

    async def compact_codex_thread(self, thread_id: str) -> None:
        await self._enter("compact_codex_thread", thread_id=thread_id)

    async def delete_codex_thread(self, thread_id: str) -> None:
        await self._enter("delete_codex_thread", thread_id=thread_id)

    async def get_codex_goal(self, thread_id: str) -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadGoal
        from vidbyte.lib.enums.codex import CodexGoalStatus

        await self._enter("get_codex_goal", thread_id=thread_id)
        if self.goal_missing:
            return None
        return CodexThreadGoal(thread_id=thread_id, objective="Ship the fix.", status=CodexGoalStatus.ACTIVE, token_budget=500, tokens_used=120, time_used_seconds=30, created_at=1, updated_at=2)

    async def run_codex_goal(self, objective: str, token_budget: int | None = None, request: Any = None) -> Any:
        await self._enter("run_codex_goal", objective=objective, token_budget=token_budget, request=request)
        return self._handle()

    async def list_codex_skills(self, cwd: str = "") -> Any:
        from vidbyte.lib.dataclasses.codex_host import CodexSkillInfo
        from vidbyte.lib.enums.codex import CodexSkillScope

        await self._enter("list_codex_skills", cwd=cwd)
        path = os.path.abspath(os.path.join(os.sep, "stub-skills", "openai-docs", "SKILL.md"))
        return (CodexSkillInfo(name="openai-docs", description="Stub skill.", path=path, scope=CodexSkillScope.SYSTEM, enabled=True),)

    async def run_codex_skill(self, skill: str, prompt: str, request: Any = None) -> Any:
        await self._enter("run_codex_skill", skill=skill, prompt=prompt, request=request)
        return self._handle()

    async def run_codex_openai_docs(self, question: str, request: Any = None) -> Any:
        await self._enter("run_codex_openai_docs", question=question, request=request)
        return self._handle()
