"""FILE: vidbyte/harnesses/native/claude/session.py

PURPOSE: Runs one Claude Code turn from start to close: it sends the prompt, reads the stream to the prompt's own result, sends a steer as the next prompt, bounds every interrupt, and publishes the classified result once its one close has completed.
ROLE IN CODEBASE: ClaudeHost (host.py) builds one ClaudeLiveSession for each spawn, continue or launch prompt, starts its pump, and hands wait, get, steer, interrupt, usage and close to it. Rate-limit windows from the stream go back to the host through the on_window callback.
ARCHITECTURE NOTE: run is the pump, one task per turn. The client is closed by one close task that runs disconnect() and that nothing cancels; the pump waits for it through asyncio.shield, and only then publishes the terminal status, fires done and frees its launch slot, so the session id stays busy until the process is gone. The watchdog, a caller's interrupt and a steer each send interrupt() from a task the session owns, and every interrupt() that returns arms one grace task aimed at the prompt it stopped.
COMMON MODIFICATION PATTERNS: A new stream message kind adds one isinstance branch in _read and one small _on_<kind> helper. A new turn condition records one ClaudeTurnOutcome field where it is seen, and ClaudeFailureMapper.classify_turn (failures.py) gives it its code.
WHAT NOT TO DO IN THIS FILE: 1. Do not cancel the close task, or wrap disconnect() or a read in asyncio.wait_for or asyncio.timeout; the SDK warns that a cancelled close skips its terminate and kill and leaves claude running. 2. Do not send a steer while a prompt is open; it waits for the interrupted prompt's result, so Claude Code never holds two prompts. 3. Do not copy CLAUDE_INTERRUPT_GRACE_SECONDS into a local or a default argument; the grace reads this module's name when it starts.
KNOWN EDGE CASES: Only a result whose origin is absent or human ends the turn; an injected turn's result only updates usage. An interrupt can return after the pump has already read that prompt's result and sent a steer, so the grace is aimed at the prompt number noted when the interrupt was sent. A steer can also arrive after the prompt's result was emitted but before the pump read it; the pump then yields once before it sends the steered prompt, so the steer's own interrupt is written first and finds nothing to stop. The stream can end while the close is still running, because the SDK sends its end marker before it terminates the process. The time budget's stop is recorded apart from the caller's, so it ends the turn FAILED with claude.budget_exhausted rather than INTERRUPTED.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable, Mapping
from dataclasses import replace
from typing import Any

from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
from vidbyte.harnesses.native.claude.options import ClaudeOptionsTranslator
from vidbyte.harnesses.native.claude.probe import ClaudeProbe
from vidbyte.harnesses.native.claude.sdk import _ClaudeClient
from vidbyte.harnesses.native.claude.tool_server import ClaudeToolServer
from vidbyte.lib.constants.claude import (
    CLAUDE_ABSENT_SOURCE,
    CLAUDE_ACCOUNT_FIELD,
    CLAUDE_API_KEY_SOURCE_FIELD,
    CLAUDE_CONNECT_OPERATION,
    CLAUDE_INTERRUPT_GRACE_SECONDS,
    CLAUDE_MIN_CLI_VERSION,
    CLAUDE_PRECONDITION_NEXT_STEP,
    CLAUDE_STEER_YIELD_SECONDS,
    CLAUDE_VERSION_FIELD,
)
from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
from vidbyte.lib.dataclasses.claude_host import (
    ClaudeFailure,
    ClaudeModelUsage,
    ClaudePermissionDenial,
    ClaudeRateLimitWindow,
    ClaudeSdkTypes,
    ClaudeSessionHandle,
    ClaudeTaskUsage,
    ClaudeTurnOutcome,
    ClaudeTurnResult,
    ClaudeUsageSnapshot,
)
from vidbyte.lib.enums.claude import (
    ClaudeRateLimitStatus,
    ClaudeRateLimitType,
    ClaudeTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError

# The origin kind of a result that answers the caller's own prompt; any
# other kind is a turn Claude Code injected (D-28).
_HUMAN_ORIGIN = "human"
# The window types and statuses a rate-limit window can be kept under;
# an event with any other type, status or overage status is skipped
# (EC-52).
_WINDOW_TYPES = frozenset(kind.value for kind in ClaudeRateLimitType)
_WINDOW_STATUSES = frozenset(status.value for status in ClaudeRateLimitStatus)
# The operations a turn's failures name, besides connect.
_INFO_OPERATION = "get_server_info"
_QUERY_OPERATION = "query"
_READ_OPERATION = "receive_messages"
_INTERRUPT_OPERATION = "interrupt"
_STEER_OPERATION = "steer_claude_session"


class ClaudeLiveSession:
    """One Claude Code turn: its client, its pump, the tasks that stop it, and the result it publishes once."""

    def __init__(self, spawn: ClaudeSpawnRequest, *, cli_path: str, sdk: ClaudeSdkTypes, slots: asyncio.Semaphore | None, on_window: Callable[[ClaudeRateLimitWindow], None]) -> None:
        # What the turn runs: its request, the CLI to start, the loaded
        # SDK, a launch's slots, and where windows go.
        self._spawn = spawn
        self._cli_path = cli_path
        self._sdk = sdk
        self._slots = slots
        self._on_window = on_window
        # A new or forked session runs under the caller's chosen id or a
        # fresh one, which Claude Code is told to use; a plain resume
        # keeps the resumed id, and a plain continue learns its id from
        # the result (section 9.1, EC-34).
        if spawn.session_id or spawn.fork_session or not (spawn.resume or spawn.continue_conversation):
            self._session_option = spawn.session_id or str(uuid.uuid4())
            session_id = self._session_option
        else:
            self._session_option = ""
            session_id = spawn.resume
        self.handle = ClaudeSessionHandle(handle_id=str(uuid.uuid4()), session_id=session_id)
        self.pump: asyncio.Task[None] | None = None
        # The published snapshot, what the pump saw for the
        # classification, and the usage figures.
        self._result = ClaudeTurnResult(handle_id=self.handle.handle_id, session_id=session_id, status=ClaudeTurnStatus.QUEUED)
        self._outcome = ClaudeTurnOutcome(
            result_seen=False,
            is_error=False,
            subtype="",
            terminal_reason="",
            api_error_status=None,
            structured_output_missing=False,
            permission_denials=(),
            assistant_errors=(),
            rate_limit_rejected=False,
            interrupted=False,
            budget_expired=False,
            precondition_failure=None,
            stream_failure=None,
        )
        self._done = asyncio.Event()
        self._cost: float | None = None
        self._models: tuple[ClaudeModelUsage, ...] = ()
        self._tasks: dict[str, ClaudeTaskUsage] = {}
        # The client, the stop flag, the one pending steer with the
        # numbers of the last steer stored and the last one sent, and
        # the counts of prompts sent and of their own results read, by
        # which the grace is aimed.
        self._client: _ClaudeClient | None = None
        self._connected = False
        self._stopping = False
        self._steer: str | None = None
        self._steers = 0
        self._steered = 0
        self._prompts_sent = 0
        self._results_read = 0
        # Every other task the turn owns: the watchdog, the grace, the
        # one close, and the interrupt tasks.
        self._watchdog: asyncio.Task[None] | None = None
        self._grace: asyncio.Task[None] | None = None
        self._closing: asyncio.Task[None] | None = None
        self._interrupts: set[asyncio.Task[ClaudeOperationError | None]] = set()

    def start(self) -> None:
        """Start the pump; the host calls this once, after it has registered the handle."""
        self.pump = asyncio.create_task(self.run())

    async def run(self) -> None:
        """The pump: connect, check the process, send the prompt and any steer, read to the result, then close and publish."""
        # A launch prompt waits here for one of its launch's slots,
        # which bound how many of its clients run at once.
        if self._slots is not None:
            await self._slots.acquire()
        try:
            # An interrupt or a close that arrived while the turn was
            # queued ends it without starting Claude Code.
            if self._stopping:
                return
            # Start Claude Code, then check its version and login type,
            # so a turn it cannot run spends nothing.
            client = await self._connect()
            await self._check_process(client)
            if self._stopping or self._outcome.precondition_failure is not None:
                return
            # The prompt goes out now, so the turn is running and its
            # time budget starts.
            self._result = replace(self._result, status=ClaudeTurnStatus.RUNNING)
            if self._spawn.timeout_seconds is not None:
                self._watchdog = asyncio.create_task(self._watch(client, self._spawn.timeout_seconds))
            # Send the prompt and read to its own result. A steer stored
            # meanwhile goes out next as one more prompt; the turn is
            # over once a result arrives with no steer pending, or once
            # the stream ends.
            prompt: str | AsyncIterable[dict[str, Any]] | None = ClaudeOptionsTranslator.to_prompt(self._spawn)
            stream = client.receive_messages()
            while prompt is not None:
                await self._query(client, prompt)
                prompt = self._take_steer() if await self._read(stream) else None
        except ClaudeOperationError as error:
            # A failed start or a broken stream becomes the turn's
            # failure; the classification decides whether it wins.
            self._outcome = replace(self._outcome, stream_failure=ClaudeFailure(code=FailureCode(error.failure_code), reason=error.reason, next_step=error.next_step))
        finally:
            # The pump reads no more, so the turn is stopping: drop a
            # pending steer and cancel the watchdog, the grace and any
            # interrupt still waiting. None of them awaits the close, so
            # cancelling one never cuts a close short.
            self._stopping = True
            self._steer = None
            self._stop_waiting()
            # Close the client once and wait for that close, through a
            # cancellation too. Only then publish the terminal status,
            # fire done and free the launch slot, so the session id
            # stays busy until claude is gone.
            try:
                await self._await_close(self._start_close())
            finally:
                self._publish()
                if self._slots is not None:
                    self._slots.release()

    async def _connect(self) -> _ClaudeClient:
        """Build the client from the turn's options and start Claude Code; the client is kept before it connects, so a close can reach it."""
        spawn, sdk = self._spawn, self._sdk
        try:
            tool_server = ClaudeToolServer.build(spawn.tools, sdk) if spawn.tools else None
            options = ClaudeOptionsTranslator.to_options(spawn, cli_path=self._cli_path, session_id=self._session_option, tool_server=tool_server, auto_allowed=ClaudeToolServer.auto_allowed(spawn.tools), sdk=sdk)
            client: _ClaudeClient = sdk.client_class(options=options)
            self._client = client
            await client.connect()
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=CLAUDE_CONNECT_OPERATION, sdk=sdk) from exc
        self._connected = True
        return client

    async def _check_process(self, client: _ClaudeClient) -> None:
        """Read what Claude Code reported while starting, and record a version or login-type problem before any prompt is sent."""
        try:
            info = dict(await client.get_server_info() or {})
            self._result = replace(self._result, hooks_applied=info.get("hooks_applied"))
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=_INFO_OPERATION, sdk=self._sdk) from exc
        version = str(info.get(CLAUDE_VERSION_FIELD) or "")
        account = info.get(CLAUDE_ACCOUNT_FIELD)
        key_source = account.get(CLAUDE_API_KEY_SOURCE_FIELD) if isinstance(account, Mapping) else None
        failure = None
        if not ClaudeProbe.version_ok(version):
            failure = ClaudeFailureMapper.failure(FailureCode.CLAUDE_VERSION_UNSUPPORTED, f"Claude Code reported version {version or 'none'}, older than {CLAUDE_MIN_CLI_VERSION}.")
        elif (self._spawn.betas or self._spawn.bare) and key_source in (None, CLAUDE_ABSENT_SOURCE):
            failure = ClaudeFailureMapper.failure(FailureCode.CLAUDE_AUTH_MODE_UNSUPPORTED, "betas and bare need an API key login, but Claude Code reports no API key source.")
        self._outcome = replace(self._outcome, precondition_failure=failure)

    async def _query(self, client: _ClaudeClient, prompt: str | AsyncIterable[dict[str, Any]]) -> None:
        """Send one prompt, counting it first, so an interrupt sent meanwhile is aimed at it."""
        self._prompts_sent += 1
        # A steer that arrived after the last result was emitted, but
        # before the pump read it, has its interrupt task scheduled
        # behind the pump. Yielding once lets that interrupt reach
        # Claude Code before the steered prompt, which it would
        # otherwise abort (EC-19).
        if self._steered:
            await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)
        try:
            await client.query(prompt)
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=_QUERY_OPERATION, sdk=self._sdk) from exc

    async def _read(self, stream: AsyncIterator[Any]) -> bool:
        """Read the stream up to the prompt's own result and return True, or return False when the stream ends first."""
        sdk = self._sdk
        try:
            async for message in stream:
                if isinstance(message, sdk.result_message) and self._on_result(message):
                    return True
                if isinstance(message, sdk.assistant_message):
                    self._on_assistant(message)
                elif isinstance(message, sdk.rate_limit_event):
                    self._on_rate_limit(message)
                elif isinstance(message, (sdk.task_progress_message, sdk.task_notification_message)):
                    self._on_task(message)
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=_READ_OPERATION, sdk=sdk) from exc
        return False

    def _take_steer(self) -> str | None:
        """Hand the pending steer to the pump as its next prompt and note its number as sent, or return None to end the turn."""
        steer, self._steer = self._steer, None
        if steer is not None:
            self._steered = self._steers
        return steer

    def _on_result(self, message: Any) -> bool:
        """Record a result's cumulative usage; for the prompt's own result, also record its fields and return True (D-28)."""
        # Every result carries the session's cumulative cost and
        # per-model usage, an injected turn's result too (INV-20).
        models = tuple(
            ClaudeModelUsage(
                model=name,
                input_tokens=usage["inputTokens"],
                output_tokens=usage["outputTokens"],
                cache_read_input_tokens=usage["cacheReadInputTokens"],
                cache_creation_input_tokens=usage["cacheCreationInputTokens"],
                web_search_requests=usage["webSearchRequests"],
                cost_usd=usage["costUSD"],
            )
            for name, usage in (message.model_usage or {}).items()
        )
        self._cost, self._models = message.total_cost_usd, models
        # @intent only-the-prompts-own-result-ends-the-turn
        # A result whose origin names another kind answers a turn that
        # Claude Code injected, such as a background task waking the
        # session, so it never ends or classifies this prompt (D-28).
        origin = message.origin
        if origin is not None and origin.get("kind") != _HUMAN_ORIGIN:
            return False
        # The prompt's own result: build its records first, so a
        # malformed result changes nothing.
        is_error = message.is_error
        denials = tuple(ClaudePermissionDenial(tool_name=denial["tool_name"], tool_use_id=denial["tool_use_id"]) for denial in message.permission_denials or ())
        result = replace(
            self._result,
            session_id=message.session_id or self._result.session_id,
            result_text=message.result or "",
            structured_output=message.structured_output,
            num_turns=message.num_turns,
            duration_ms=message.duration_ms,
            total_cost_usd=self._cost,
            stop_reason=message.stop_reason or "",
            terminal_reason=message.terminal_reason or "",
            permission_denials=denials,
        )
        outcome = replace(
            self._outcome,
            is_error=is_error,
            subtype=message.subtype,
            terminal_reason=result.terminal_reason,
            api_error_status=message.api_error_status,
            structured_output_missing=self._spawn.output_schema is not None and not is_error and result.structured_output is None,
            permission_denials=denials,
        )
        # Count the result, and stop a grace that was waiting for it,
        # which frees the grace for a later interrupt.
        self._result, self._outcome = result, outcome
        self._results_read += 1
        if self._grace is not None:
            self._grace.cancel()
            self._grace = None
        return True

    def _on_assistant(self, message: Any) -> None:
        """Record the error kind an assistant message carries, such as rate_limit or billing_error."""
        kind = message.error
        if kind:
            self._outcome = replace(self._outcome, assistant_errors=(*self._outcome.assistant_errors, str(kind)))

    def _on_rate_limit(self, message: Any) -> None:
        """Hand a keyed rate-limit window to the host, and mark the turn when the window refuses new sessions (D-29)."""
        info = message.rate_limit_info
        kind, status, overage = info.rate_limit_type, info.status, info.overage_status
        unknown_overage = overage is not None and overage not in _WINDOW_STATUSES
        if kind not in _WINDOW_TYPES or status not in _WINDOW_STATUSES or unknown_overage:
            return
        window = ClaudeRateLimitWindow(
            rate_limit_type=ClaudeRateLimitType(kind),
            status=ClaudeRateLimitStatus(status),
            resets_at=info.resets_at,
            utilization=info.utilization,
            overage_status=None if overage is None else ClaudeRateLimitStatus(overage),
            overage_resets_at=info.overage_resets_at,
            overage_disabled_reason=info.overage_disabled_reason or "",
        )
        self._on_window(window)
        if ClaudeFailureMapper.usage_limited(window):
            self._outcome = replace(self._outcome, rate_limit_rejected=True)

    def _on_task(self, message: Any) -> None:
        """Record a background task's latest figures: progress names the task, and a notification without usage keeps the last figures."""
        task_id = message.task_id
        earlier = self._tasks.get(task_id) or ClaudeTaskUsage(task_id=task_id, description="", total_tokens=0, tool_uses=0, duration_ms=0)
        usage = message.usage or {}
        # Only a progress message declares a description; a
        # notification carries a summary instead, so it keeps the name.
        progress = isinstance(message, self._sdk.task_progress_message)
        named = message.description if progress else ""
        self._tasks[task_id] = ClaudeTaskUsage(
            task_id=task_id,
            description=named or earlier.description,
            total_tokens=usage.get("total_tokens", earlier.total_tokens),
            tool_uses=usage.get("tool_uses", earlier.tool_uses),
            duration_ms=usage.get("duration_ms", earlier.duration_ms),
        )

    async def _watch(self, client: _ClaudeClient, seconds: float) -> None:
        """When the time budget runs out, stop the turn: drop a pending steer and send interrupt() from an interrupt task."""
        await asyncio.sleep(seconds)
        if self._stopping:
            return
        # The budget sets its own flag, never the caller's interrupt
        # flag, so the turn reports budget_exhausted.
        self._stopping = True
        self._steer = None
        self._outcome = replace(self._outcome, budget_expired=True)
        self._interrupts.add(asyncio.create_task(self._interrupt_client(client, self._prompts_sent, None)))

    async def _interrupt_client(self, client: _ClaudeClient, prompt: int, steer: int | None) -> ClaudeOperationError | None:
        """Send interrupt() for prompt number prompt: arm the grace when it returns; when it raises, withdraw the steer or start the close."""
        try:
            await client.interrupt()
        except Exception as exc:
            # A steer's failed interrupt withdraws only its own unsent
            # message, and the turn goes on; a failed interrupt from the
            # watchdog or the caller closes the client instead.
            if steer is None:
                self._start_close()
            elif self._steers == steer and self._steer is not None:
                self._steer = None
            return ClaudeFailureMapper.from_exception(exc, operation=_INTERRUPT_OPERATION, sdk=self._sdk)
        self._arm_grace(prompt)
        return None

    def _arm_grace(self, prompt: int) -> None:
        """Start the grace task for prompt number prompt, unless one is armed, that prompt's result was read, or the turn is over."""
        if self._grace is None and self._results_read < prompt and not self._done.is_set():
            self._grace = asyncio.create_task(self._expire(prompt))

    async def _expire(self, prompt: int) -> None:
        """Wait the grace period; if prompt number prompt still has no result, drop a pending steer, record the stop and start the close."""
        # The module's grace name is read here, when the grace starts,
        # so changing it on this module takes effect.
        await asyncio.sleep(CLAUDE_INTERRUPT_GRACE_SECONDS)
        if self._results_read >= prompt:
            return
        self._steer = None
        self._stopping = True
        self._outcome = replace(self._outcome, interrupted=self._outcome.interrupted or not self._outcome.budget_expired)
        self._start_close()

    def _stop_waiting(self) -> None:
        """Cancel the watchdog, the grace and every interrupt task still waiting; none of them awaits the close."""
        for task in (self._watchdog, self._grace, *self._interrupts):
            if task is not None:
                task.cancel()

    def _start_close(self) -> asyncio.Task[None] | None:
        """Start the one close task that runs disconnect(), or return the one already started; None while no client exists."""
        if self._closing is None and self._client is not None:
            self._closing = asyncio.create_task(self._client.disconnect())
        return self._closing

    @staticmethod
    async def _await_close(closing: asyncio.Task[None] | None) -> None:
        """Wait for the close task through asyncio.shield; a cancelled caller waits for it again, then goes on cancelling."""
        if closing is None:
            return
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            await asyncio.wait({closing})
            raise
        except Exception:
            # A failed disconnect leaves the turn's classification
            # unchanged.
            return

    def _publish(self) -> None:
        """Classify the finished turn, publish its terminal status and failure, and fire done; later calls change nothing."""
        if self._done.is_set():
            return
        outcome = replace(self._outcome, result_seen=bool(self._prompts_sent) and self._results_read == self._prompts_sent)
        status, failure = ClaudeFailureMapper.classify_turn(outcome)
        self._result = replace(self._result, status=status, failure=failure)
        self._done.set()

    async def steer(self, message: str) -> None:
        """Store one message and interrupt the running prompt from an interrupt task; the message goes out after that prompt's result (D-3)."""
        # Only a running turn that is not stopping and has no steer
        # pending takes a message (INV-18).
        client = self._client
        if client is None or self._result.status is not ClaudeTurnStatus.RUNNING:
            raise self._refused(f"The turn is {self._result.status.value}; only a running turn can be steered.")
        if self._stopping:
            raise self._refused("The turn is stopping, so it takes no steer.")
        if self._steer is not None:
            raise self._refused("A steer is already pending on this turn; wait until it is sent.")
        # Store the message under the next number, then interrupt the
        # prompt from a task the session owns.
        self._steers += 1
        number = self._steers
        self._steer = message
        task = asyncio.create_task(self._interrupt_client(client, self._prompts_sent, number))
        self._interrupts.add(task)
        # Wait without cancelling the task, so a caller-side timeout
        # stops only this wait and the task still arms the grace
        # (EC-59).
        await asyncio.wait({task})
        error = None if task.cancelled() else task.result()
        if error is not None:
            raise error
        # The message was dropped before the pump sent it: the turn was
        # interrupted, ran out of time or ended first.
        if self._steer is None and self._steered < number:
            raise self._refused("The steer was discarded before it was sent, because the turn was interrupted, ran out of time or ended first.")

    def interrupt(self) -> ClaudeTurnResult:
        """Stop the turn and return the snapshot at once (D-26): a turn with no client ends now, and a running one gets an interrupt task."""
        # A stopping or finished turn sends nothing more (EC-23).
        if self._stopping:
            return self._result
        # The caller's stop drops a pending steer, and the turn ends
        # INTERRUPTED, which is not a failure.
        self._stopping = True
        self._steer = None
        self._outcome = replace(self._outcome, interrupted=True)
        # With no client nothing has started, so the turn ends here; a
        # connect in flight is finished by the pump.
        if self._client is None:
            self._publish()
        elif self._result.status is ClaudeTurnStatus.RUNNING:
            self._interrupts.add(asyncio.create_task(self._interrupt_client(self._client, self._prompts_sent, None)))
        return self._result

    async def close(self) -> None:
        """Stop the turn for a closing host and, once its client is connected, wait for the one close the way the pump does."""
        # A turn that is not stopping yet ends INTERRUPTED; one already
        # stopping keeps the reason it stopped for.
        if not self._stopping:
            self._stopping = True
            self._steer = None
            self._outcome = replace(self._outcome, interrupted=True)
        if self._connected:
            await self._await_close(self._start_close())

    async def wait(self, timeout_seconds: float) -> ClaudeTurnResult:
        """Return the snapshot once the turn is terminal or timeout_seconds have passed; waiting never changes the turn (INV-9)."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._done.wait(), timeout_seconds)
        return self._result

    def snapshot(self) -> ClaudeTurnResult:
        """Return the turn's current state: live while it runs, then its terminal result."""
        return self._result

    def usage(self) -> ClaudeUsageSnapshot:
        """Return the latest cumulative cost and per-model usage, and the latest figures of each background task."""
        return ClaudeUsageSnapshot(handle_id=self.handle.handle_id, session_id=self._result.session_id, total_cost_usd=self._cost, models=self._models, tasks=tuple(self._tasks.values()))

    @staticmethod
    def _refused(reason: str) -> ClaudeOperationError:
        """Return the action.precondition_failed error for a steer the turn cannot take."""
        return ClaudeFailureMapper.error(FailureCode.ACTION_PRECONDITION_FAILED, reason, operation=_STEER_OPERATION, next_step=CLAUDE_PRECONDITION_NEXT_STEP)


__all__ = ["ClaudeLiveSession"]
