"""FILE: vidbyte/harnesses/native/codex/host_core.py

PURPOSE: CodexHostCore, the base CodexHost and its four feature mixins share: the attributes the host sets when it is built and opened, the two checks every public method runs first, _guard (an open host, called on the loop that opened it, with a live process when the call talks to Codex) and _owned (a handle this host registered), and _change_idle, the one sequence every history-changing call runs (first-class INV-34).
ROLE IN CODEBASE: The bottom class of CodexHost's hierarchy in vidbyte/harnesses/native/codex/. CodexSettingsMethods, CodexStreamMethods, CodexThreadMethods and CodexGoalMethods subclass it, and CodexHost inherits all four, so a mixin reads the host's parts through self with their types and never imports host.py (first-class D-1).
ARCHITECTURE NOTE: Imports no openai-codex module and none of the host's SDK-loading collaborators at runtime; their types appear only under TYPE_CHECKING, so importing a mixin or CodexHost still loads no SDK (first-class INV-45). The attributes are declarations only: CodexHost.__init__ sets the settings, the handler and the state flags, and CodexHost._open builds every collaborator, so none of them exists before the host opened.
COMMON MODIFICATION PATTERNS: A new collaborator the mixins need is one more annotation here, built in CodexHost._open. A check every public method shares goes here beside _guard and _owned, and a sequence two mixins share goes here beside _change_idle; a check one feature needs stays in its mixin or in CodexPreflight.
KNOWN EDGE CASES: _guard calls asyncio.get_running_loop, so a method called with no running loop raises Python's own RuntimeError before any record or request (first-class EC-3). A call that does not talk to Codex (a wait, a stream, a usage read, forget_codex_turns, the worktree) passes on a closing or dead host; one that talks gets codex.process_exited (INV-6). _change_idle reserves the thread before its first await and releases it in finally, so a second change on the same thread is refused rather than raced (INV-34).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.1 D-1, 8.5 and 12.3 row 21, INV-1, INV-34, INV-45); docs/spec/codex-host/spec.md (INV-6, INV-23, D-33)
TESTS: tests/features/codex_host/test_codex_host_feature_structure.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_lifecycle.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_thread_admin.py, tests/features/codex_host/test_codex_host_goal_control.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_NOT_OPEN_MESSAGE,
    CODEX_HOST_OTHER_LOOP_MESSAGE,
    CODEX_HOST_UNKNOWN_HANDLE_MESSAGE,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.feature_wire import (
        CodexFeatureParamsTranslator,
        CodexFeatureResponseTranslator,
    )
    from vidbyte.harnesses.native.codex.preflight import CodexPreflight
    from vidbyte.harnesses.native.codex.reviews import CodexReviews
    from vidbyte.harnesses.native.codex.skill_functions import CodexSkillFunctions
    from vidbyte.harnesses.native.codex.thread_helpers import CodexThreadHelpers
    from vidbyte.harnesses.native.codex.turn_events import CodexTurnEvents
    from vidbyte.harnesses.native.codex.turn_starts import CodexTurnStarts
    from vidbyte.harnesses.native.codex.turns import (
        CodexLiveTurn,
        CodexTurnRegistry,
    )
    from vidbyte.harnesses.native.codex.wire import (
        CodexParamsTranslator,
        CodexResponseTranslator,
    )
    from vidbyte.lib.dataclasses.codex import CodexClientSettings
    from vidbyte.lib.dataclasses.codex_host import (
        CodexServerAnswer,
        CodexServerRequest,
        CodexTurnHandle,
    )
    from vidbyte.lib.enums.codex import CodexHostOperation

ResultT = TypeVar("ResultT")


class CodexHostCore:
    """The parts and the first checks every CodexHost method shares; CodexHost builds the parts when it opens."""

    _settings: CodexClientSettings
    _approval_handler: Callable[[CodexServerRequest], Awaitable[CodexServerAnswer]] | None
    _loop: asyncio.AbstractEventLoop | None
    _opened: bool
    _closing: bool
    _connection: CodexConnection
    _params: CodexParamsTranslator
    _responses: CodexResponseTranslator
    _registry: CodexTurnRegistry
    _preflight: CodexPreflight
    _threads: CodexThreadHelpers
    _events: CodexTurnEvents
    _reviews: CodexReviews
    _skills: CodexSkillFunctions
    _starts: CodexTurnStarts
    _feature_params: CodexFeatureParamsTranslator
    _feature_responses: CodexFeatureResponseTranslator

    def _guard(self, operation: CodexHostOperation, *, talks: bool) -> None:
        # Every method needs an open host and the loop that opened it; a
        # call that talks to Codex also needs a live, open process
        # (INV-6).
        if not self._opened:
            raise ConfigurationError(CODEX_HOST_NOT_OPEN_MESSAGE.format(operation=operation.value))
        if asyncio.get_running_loop() is not self._loop:
            raise ConfigurationError(CODEX_HOST_OTHER_LOOP_MESSAGE.format(operation=operation.value))
        if talks and (self._closing or self._connection.is_dead()):
            raise CodexErrorMapper.process_exited(operation)

    def _owned(self, operation: CodexHostOperation, handle: CodexTurnHandle) -> CodexLiveTurn:
        # A handle must name a turn this host registered (INV-23, D-33).
        turn = self._registry.get(handle)
        if turn is None:
            message = CODEX_HOST_UNKNOWN_HANDLE_MESSAGE.format(turn_id=handle.turn_id, thread_id=handle.thread_id)
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, message, operation)
        return turn

    async def _change_idle(self, operation: CodexHostOperation, thread_id: str, method: str, function: Callable[[], ResultT], *, loads: bool) -> ResultT:
        # @intent a-history-change-runs-on-an-idle-thread-only
        # A call that changes stored history needs a thread no
        # client is running: it reserves the thread on this host
        # before its first await, refuses a turn Codex reports
        # running, loads a thread that is not loaded when the change
        # needs it, sends its one call, and always releases the
        # thread (first-class INV-34).
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            status = await self._threads.idle_status(operation, thread_id)
            if loads:
                await self._threads.load(operation, thread_id, status)
            return await self._connection.call(operation, method, function, thread_id=thread_id)
        finally:
            self._registry.release(thread_id)


__all__ = ["CodexHostCore"]
