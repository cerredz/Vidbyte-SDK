"""FILE: vidbyte/harnesses/native/claude/host.py

PURPOSE: ClaudeHost, the owner of every Claude Code turn one event loop starts. It offers the fifteen small Claude Code functions, checks each call, and hands the work to a live session, the session-file reader or the probe.
ROLE IN CODEBASE: The public entry point of vidbyte.harnesses.native.claude. Developers call its methods directly, and the fifteen tools in vidbyte/tools/builtins/claude/ call one method each. It builds one ClaudeLiveSession (session.py) per turn, reads and forks session files through ClaudeHistory (history.py), and checks the CLI through ClaudeProbe (probe.py).
ARCHITECTURE NOTE: Every public method runs the same steps: the guard refuses a host that is not entered, is closed or is called from another event loop; the SDK is loaded; the arguments are checked; then one live session, history read or probe does the work. _admit runs the admission checks and registers the new turns with no await in between, so two calls can never both pass the cap or busy check. aclose stops every turn through its session's own close and waits for every pump, so each client is disconnected exactly once.
COMMON MODIFICATION PATTERNS: A new Claude Code function adds one public method with the same guard, load, check and delegate steps, and one tool in vidbyte/tools/builtins/claude/. A new admission rule adds one check in _admit at its place in the spawn order.
WHAT NOT TO DO IN THIS FILE: 1. Do not await inside _admit; an await between its checks and the registration lets two calls pass the cap or busy check together. 2. Do not call disconnect() here; each session's one close task disconnects its client. 3. Do not let a request's cli_path that screens to "" fall back to the host's path.
KNOWN EDGE CASES: A native background subagent that is still running when its turn's result arrives is stopped, because the host disconnects at that result and each turn is one process (EC-45). Two hosts, or an interactive claude, working on one session id cannot be detected, because the busy guard sees only this host's turns (EC-47). An interrupt that Claude Code acknowledges but never answers with a result ends the turn after CLAUDE_INTERRUPT_GRACE_SECONDS, when its close starts (EC-53). A second __aenter__ never reopens a closed host (EC-61).
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import TracebackType

from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
from vidbyte.harnesses.native.claude.history import ClaudeHistory
from vidbyte.harnesses.native.claude.probe import ClaudeProbe
from vidbyte.harnesses.native.claude.sdk import ClaudeSdkLoader
from vidbyte.harnesses.native.claude.session import ClaudeLiveSession
from vidbyte.lib.constants.claude import (
    CLAUDE_EMPTY_INPUT_NEXT_STEP,
    CLAUDE_LIVE_CAP_NEXT_STEP,
    CLAUDE_PRECONDITION_NEXT_STEP,
    CLAUDE_WINDOWS_PLATFORM,
)
from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest, _ClaudeFieldRules
from vidbyte.lib.dataclasses.claude_host import (
    ClaudeFailure,
    ClaudeHostSettings,
    ClaudeModelInfo,
    ClaudeRateLimitWindow,
    ClaudeReadiness,
    ClaudeSdkTypes,
    ClaudeSessionHandle,
    ClaudeSessionMessage,
    ClaudeSessionSummary,
    ClaudeTurnResult,
    ClaudeUsageSnapshot,
)
from vidbyte.lib.enums.claude import ClaudeRateLimitType, ClaudeTurnStatus
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError

# A turn in either status still counts against the cap and still holds
# its session id (INV-4, INV-5).
_LIVE_STATUSES = (ClaudeTurnStatus.QUEUED, ClaudeTurnStatus.RUNNING)


class ClaudeHost:
    """Runs Claude Code turns for one event loop and offers each Claude Code function as one small method."""

    def __init__(self, *, cli_path: str = "", max_live_sessions: int | None = None) -> None:
        # The settings check both arguments now, so a bad value fails
        # where it is passed.
        self._settings = ClaudeHostSettings(cli_path=cli_path, max_live_sessions=max_live_sessions)
        # Set on entry: the event loop the host serves, the platform and
        # home folder the CLI lookup uses, and the CLI found.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._windows = False
        self._home = Path()
        self._cli_path = ""
        self._closed = False
        # Every turn this host started, by handle id, and the latest
        # rate-limit window of each type its streams reported.
        self._sessions: dict[str, ClaudeLiveSession] = {}
        self._rate_limits: dict[ClaudeRateLimitType, ClaudeRateLimitWindow] = {}

    async def __aenter__(self) -> ClaudeHost:
        """Bind the host to the running event loop and find the Claude Code executable once (D-5)."""
        # From now on the host serves only this loop (INV-15); entering
        # again never reopens a closed host (EC-61).
        self._loop = asyncio.get_running_loop()
        # Find the executable now: the given path, else the installed
        # one, and never a Windows batch script.
        self._windows = sys.platform == CLAUDE_WINDOWS_PLATFORM
        self._home = Path.home()
        self._cli_path = ClaudeProbe.locate_cli(self._settings.cli_path, windows=self._windows, home=self._home)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        """Close the host when its async with block ends."""
        await self.aclose()

    async def aclose(self) -> None:
        """Stop every turn, wait until each one's client is closed and its status published, and refuse every later call."""
        # A second aclose has nothing left to stop (EC-61).
        if self._closed:
            return
        # Refuse every call from now on, so no new turn can start while
        # the others stop.
        self._closed = True
        sessions = tuple(self._sessions.values())
        # Stop every turn still going: it ends INTERRUPTED unless it was
        # already stopping, and a connected client is closed by its own
        # session's close task, so no client is ever disconnected twice.
        outcomes = await asyncio.gather(*(session.close() for session in sessions), return_exceptions=True)
        # Wait for every pump, so each turn has published its terminal
        # status before aclose returns; a launch turn still waiting for
        # a slot finishes as soon as it gets one, without connecting
        # (EC-27).
        pumps = {session.pump for session in sessions if session.pump is not None}
        if pumps:
            await asyncio.wait(pumps)
        # close() handles every Exception itself, so only a cancellation
        # or another BaseException comes back; pass it on.
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome

    def get_handle(self, handle_id: str) -> ClaudeSessionHandle:
        """Return the handle this host issued under handle_id, so a tool can turn a model's handle_id back into a handle."""
        self._guard("get_handle")
        _ClaudeFieldRules.text(handle_id, "handle_id")
        return self._session(handle_id, "get_handle").handle

    async def check_claude_ready(self) -> ClaudeReadiness:
        """Report whether Claude Code can run here: the extra, the CLI, its version and the sign-in; a problem is reported, never raised."""
        self._guard("check_claude_ready")
        # A missing claude extra is reported in the record, like every
        # other readiness problem.
        try:
            sdk = ClaudeSdkLoader.load()
        except ClaudeOperationError as error:
            missing = ClaudeFailure(code=FailureCode(error.failure_code), reason=error.reason, next_step=error.next_step)
            return ClaudeReadiness(cli_path=self._cli_path, cli_version="", signed_in=False, failure=missing)
        # Start Claude Code once with no prompt, and report what it
        # answered.
        readiness, _ = await ClaudeProbe.readiness(sdk, self._cli_path)
        return readiness

    async def list_claude_models(self) -> tuple[ClaudeModelInfo, ...]:
        """Return the models Claude Code offers this account, read from one probe that sends no prompt."""
        operation = "list_claude_models"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        # Probe once; a CLI that is missing, too old or signed out
        # raises its readiness code instead of listing models.
        readiness, info = await ClaudeProbe.readiness(sdk, self._cli_path)
        failure = readiness.failure
        if failure is not None:
            raise ClaudeFailureMapper.error(failure.code, failure.reason, operation=operation, next_step=failure.next_step)
        return ClaudeProbe.models(info)

    async def get_claude_rate_limits(self) -> tuple[ClaudeRateLimitWindow, ...]:
        """Return the latest rate-limit window of each type this host's turns reported, in ClaudeRateLimitType order (D-8)."""
        self._guard("get_claude_rate_limits")
        ClaudeSdkLoader.load()
        # Windows arrive only on this host's own streams, so before any
        # turn there are none.
        return tuple(self._rate_limits[kind] for kind in ClaudeRateLimitType if kind in self._rate_limits)

    async def spawn_claude_session(self, request: ClaudeSpawnRequest) -> ClaudeSessionHandle:
        """Start one Claude Code turn from a request and return its handle at once, while the turn runs in the background (INV-3)."""
        # @intent spawn-returns-before-the-turn-runs
        # The turn is registered and its pump started before this
        # returns, so the handle comes back QUEUED or RUNNING and never
        # terminal; the caller waits, steers or interrupts the turn
        # through that handle.
        operation = "spawn_claude_session"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        # An empty prompt has nothing to run, so it is refused before
        # anything else.
        if not request.prompt:
            raise self._empty("prompt", operation)
        # Check the CLI path, the cap, the session id and the rate
        # windows, then register and start the turn.
        (handle,) = self._admit((request,), sdk, operation, None)
        return handle

    async def continue_claude_session(self, session_id: str, prompt: str, *, request: ClaudeSpawnRequest | None = None) -> ClaudeSessionHandle:
        """Resume a known, idle session with a new prompt as a new turn, in the session's recorded cwd unless the request sets one (D-27)."""
        # @intent continue-resumes-exactly-this-session
        # The request is cleared of every other session setting and
        # resumes session_id itself, so a continue can never fork, pick
        # a new id or resume a different session than the one the caller
        # named.
        operation = "continue_claude_session"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        # Check the arguments; an empty prompt is refused before any
        # session file is read.
        _ClaudeFieldRules.text(session_id, "session_id")
        _ClaudeFieldRules.text(prompt, "prompt")
        if not prompt:
            raise self._empty("prompt", operation)
        # Read the session's summary in a worker thread; an unknown
        # session is claude.session_not_found.
        info = await ClaudeHistory.session_info(sdk, session_id)
        # A turn already writing to this session would collide with a
        # second writer (INV-4).
        if any(session.snapshot().status in _LIVE_STATUSES and session.snapshot().session_id == session_id for session in self._sessions.values()):
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_SESSION_BUSY, "A live turn in this host is already running this session.", operation=operation)
        # Resuming from another folder would not find the session's
        # transcript, so two different cwds are refused (D-27, D-33).
        template = request or ClaudeSpawnRequest()
        if template.cwd and info.cwd and os.path.normcase(os.path.abspath(template.cwd)) != os.path.normcase(os.path.abspath(info.cwd)):
            raise _ClaudeFieldRules.conflict("cwd names a different folder than the session's recorded cwd; leave cwd empty to use the recorded one.")
        # Resume exactly this session as a new turn, clearing every
        # other session setting the request carries.
        spawn = replace(template, prompt=prompt, cwd=template.cwd or info.cwd, resume=session_id, session_id="", fork_session=False, continue_conversation=False, resume_session_at="", resume_drops_turn="")
        # The remaining spawn checks and the registration follow with no
        # await in between.
        (handle,) = self._admit((spawn,), sdk, operation, None)
        return handle

    async def fork_claude_session(self, session_id: str, up_to_message_id: str = "", title: str = "") -> str:
        """Copy a session into a new one, offline and up to one message when given, and return the new session's id (D-19)."""
        operation = "fork_claude_session"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        _ClaudeFieldRules.text(session_id, "session_id")
        _ClaudeFieldRules.text(up_to_message_id, "up_to_message_id")
        _ClaudeFieldRules.text(title, "title")
        # The copy runs in a worker thread and starts no process, so a
        # live session can be forked too.
        return await ClaudeHistory.fork(sdk, session_id, up_to_message_id, title)

    async def list_claude_sessions(self, directory: str = "", limit: int | None = None, offset: int = 0, include_worktrees: bool = True) -> tuple[ClaudeSessionSummary, ...]:
        """Return one page of a project's sessions, or of every project when directory is empty, most recent first."""
        operation = "list_claude_sessions"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        _ClaudeFieldRules.text(directory, "directory")
        if limit is not None:
            _ClaudeFieldRules.count(limit, "limit")
        _ClaudeFieldRules.count(offset, "offset", low=0)
        _ClaudeFieldRules.flag(include_worktrees, "include_worktrees")
        # The SDK reads the session files in a worker thread, so a slow
        # folder scan never blocks the event loop (INV-16).
        return await ClaudeHistory.list_sessions(sdk, directory, limit, offset, include_worktrees)

    async def get_claude_session_info(self, session_id: str) -> ClaudeSessionSummary:
        """Return one session's summary, or raise claude.session_not_found when Claude Code has none for it (EC-29)."""
        operation = "get_claude_session_info"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        _ClaudeFieldRules.text(session_id, "session_id")
        return await ClaudeHistory.session_info(sdk, session_id)

    async def get_claude_session_messages(self, session_id: str, limit: int | None = None, offset: int = 0) -> tuple[ClaudeSessionMessage, ...]:
        """Return one page of a session's transcript, oldest first, each message rendered as text."""
        operation = "get_claude_session_messages"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        _ClaudeFieldRules.text(session_id, "session_id")
        if limit is not None:
            _ClaudeFieldRules.count(limit, "limit")
        _ClaudeFieldRules.count(offset, "offset", low=0)
        messages = await ClaudeHistory.session_messages(sdk, session_id, limit, offset)
        # The SDK returns an empty page for an unknown session too, so
        # an empty page checks that the session exists (EC-30).
        if not messages:
            await ClaudeHistory.session_info(sdk, session_id)
        return messages

    async def wait_claude_turn(self, handle: ClaudeSessionHandle, *, timeout_seconds: float) -> ClaudeTurnResult:
        """Wait up to timeout_seconds for the turn to end and return its snapshot; on timeout the live snapshot comes back and the turn goes on (INV-9)."""
        operation = "wait_claude_turn"
        self._guard(operation)
        ClaudeSdkLoader.load()
        _ClaudeFieldRules.amount(timeout_seconds, "timeout_seconds")
        return await self._session(handle.handle_id, operation).wait(timeout_seconds)

    async def get_claude_turn_result(self, handle: ClaudeSessionHandle) -> ClaudeTurnResult:
        """Return the turn's current snapshot without waiting: live while it runs, then its terminal result."""
        operation = "get_claude_turn_result"
        self._guard(operation)
        ClaudeSdkLoader.load()
        return self._session(handle.handle_id, operation).snapshot()

    async def steer_claude_session(self, handle: ClaudeSessionHandle, message: str) -> None:
        """Redirect a running turn: interrupt its current step, then send message as the next turn once that step's result arrives (D-3)."""
        operation = "steer_claude_session"
        self._guard(operation)
        ClaudeSdkLoader.load()
        _ClaudeFieldRules.text(message, "message")
        if not message:
            raise self._empty("message", operation)
        # The session refuses a turn that is not running, is stopping or
        # already has a steer pending (INV-18).
        await self._session(handle.handle_id, operation).steer(message)

    async def interrupt_claude_turn(self, handle: ClaudeSessionHandle) -> ClaudeTurnResult:
        """Stop the turn and return its snapshot at once; it ends INTERRUPTED once Claude Code answers or the grace runs out (D-26)."""
        operation = "interrupt_claude_turn"
        self._guard(operation)
        ClaudeSdkLoader.load()
        return self._session(handle.handle_id, operation).interrupt()

    async def track_claude_session_usage(self, handle: ClaudeSessionHandle) -> ClaudeUsageSnapshot:
        """Return the session's latest cumulative cost and per-model usage, and the latest figures of each background task (INV-20)."""
        operation = "track_claude_session_usage"
        self._guard(operation)
        ClaudeSdkLoader.load()
        return self._session(handle.handle_id, operation).usage()

    async def launch_claude_subagents(self, prompts: tuple[str, ...], request: ClaudeSpawnRequest, limit: int) -> tuple[ClaudeSessionHandle, ...]:
        """Start one turn per prompt from one template request, with at most limit of them connected at once; all are registered or none (INV-6)."""
        # @intent a-launch-never-shares-one-session
        # Several prompts from a template that names one session would
        # all write to one transcript, so that template is refused
        # before anything is registered; each prompt otherwise gets the
        # id a spawn of it would get.
        operation = "launch_claude_subagents"
        self._guard(operation)
        sdk = ClaudeSdkLoader.load()
        # Check the prompts and the limit: a tuple of text with no empty
        # item, and a whole number of at least one.
        if not isinstance(prompts, tuple) or not all(isinstance(prompt, str) for prompt in prompts):
            raise _ClaudeFieldRules.invalid("prompts must be a tuple of text.")
        if not prompts or not all(prompts):
            raise self._empty("prompts", operation)
        _ClaudeFieldRules.count(limit, "limit")
        # One session_id cannot name several new sessions, and several
        # prompts resuming one session would collide (D-30, EC-33).
        several = len(prompts) > 1
        if several and request.session_id:
            raise _ClaudeFieldRules.conflict("session_id names one session, so it cannot be used for several launch prompts; leave it empty.")
        if several and (request.resume or request.continue_conversation) and not request.fork_session:
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_SESSION_BUSY, "Several launch prompts cannot resume or continue one session without fork_session.", operation=operation)
        # Each prompt runs as the template with its own prompt, and one
        # semaphore bounds how many of them connect at once.
        spawns = tuple(replace(request, prompt=prompt) for prompt in prompts)
        return self._admit(spawns, sdk, operation, asyncio.Semaphore(limit))

    def _guard(self, operation: str) -> None:
        """Refuse a call made before entry, after aclose, or from an event loop other than the one that entered the host (INV-15)."""
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            # A call made outside any running loop is not on the loop
            # that entered the host either.
            loop = None
        if self._loop is None:
            reason = "The host has not been entered; use it inside async with ClaudeHost() as host."
        elif self._closed:
            reason = "The host is closed and is never reopened; open a new ClaudeHost."
        elif loop is not self._loop:
            reason = "The host was called from an event loop other than the one that entered it."
        else:
            return
        raise ClaudeFailureMapper.error(FailureCode.ACTION_PRECONDITION_FAILED, reason, operation=operation, next_step=CLAUDE_PRECONDITION_NEXT_STEP)

    def _admit(self, spawns: tuple[ClaudeSpawnRequest, ...], sdk: ClaudeSdkTypes, operation: str, slots: asyncio.Semaphore | None) -> tuple[ClaudeSessionHandle, ...]:
        """Check the CLI path, the live cap, busy session ids and the rate windows in that order, then register and start every turn, or none."""
        # Each turn starts its request's own screened CLI path, or the
        # host's when the request names none; a request path that
        # screens to "" never falls back to the host's (INV-10).
        paths = tuple(ClaudeProbe.locate_cli(spawn.cli_path, windows=self._windows, home=self._home) if spawn.cli_path else self._cli_path for spawn in spawns)
        if not all(paths):
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_NOT_INSTALLED, "No Claude Code executable was found or given; a Windows .cmd or .bat script cannot be started.", operation=operation)
        # Every queued or running turn counts against the cap, and a
        # launch needs room for all of its turns (INV-5, D-22).
        live = [session for session in self._sessions.values() if session.snapshot().status in _LIVE_STATUSES]
        cap = self._settings.max_live_sessions
        if cap is not None and len(live) + len(spawns) > cap:
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_SESSION_BUSY, f"The host already runs {len(live)} of at most {cap} live sessions.", operation=operation, next_step=CLAUDE_LIVE_CAP_NEXT_STEP)
        # A new turn may not target a session id a live turn holds; a
        # continue_conversation turn has no id yet (INV-4).
        sessions = tuple(ClaudeLiveSession(spawn, cli_path=path, sdk=sdk, slots=slots, on_window=self._record_window) for spawn, path in zip(spawns, paths, strict=True))
        held = {session.snapshot().session_id for session in live} - {""}
        if any(session.handle.session_id in held for session in sessions):
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_SESSION_BUSY, "A live turn in this host is already running that session id.", operation=operation)
        # A window that refuses new sessions stops every spawn until it
        # resets (D-8, D-29).
        if any(ClaudeFailureMapper.usage_limited(window) for window in self._rate_limits.values()):
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_USAGE_LIMITED, "A rate-limit window refuses new sessions until it resets; get_claude_rate_limits shows when.", operation=operation)
        # Register and start every turn; a pump first runs at the
        # caller's next await, so each handle exists before its turn can
        # finish (INV-3, INV-6).
        for session in sessions:
            self._sessions[session.handle.handle_id] = session
            session.start()
        return tuple(session.handle for session in sessions)

    def _session(self, handle_id: str, operation: str) -> ClaudeLiveSession:
        """Return the turn this host issued handle_id for, or raise claude.session_not_found for a handle from another host or none."""
        session = self._sessions.get(handle_id)
        if session is None:
            raise ClaudeFailureMapper.error(FailureCode.CLAUDE_SESSION_NOT_FOUND, "This host issued no handle with that handle_id; a handle from another host is unknown here.", operation=operation)
        return session

    def _record_window(self, window: ClaudeRateLimitWindow) -> None:
        """Keep a rate-limit window a turn reported, replacing the earlier one of its type (D-8)."""
        self._rate_limits[window.rate_limit_type] = window

    @staticmethod
    def _empty(name: str, operation: str) -> ClaudeOperationError:
        """Return the input.empty error for an empty prompt, message or prompts tuple (EC-49)."""
        return ClaudeFailureMapper.error(FailureCode.INPUT_EMPTY, f"{name} is empty, so there is nothing to send.", operation=operation, next_step=CLAUDE_EMPTY_INPUT_NEXT_STEP)


__all__ = ["ClaudeHost"]
