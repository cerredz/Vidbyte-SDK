"""FILE: vidbyte/harnesses/native/codex/oneshot.py

PURPOSE: The six module functions that each open one CodexHost, make one read or fork call through it, and close it: readiness, rate limits, models, thread listing, thread reads and forks.
ROLE IN CODEBASE: The one-call entry points of vidbyte/harnesses/native/codex/, exported beside CodexHost for callers that need a single answer rather than a long-lived host.
ARCHITECTURE NOTE: Each function is "async with CodexHost(settings) as host: return await host.<same name>(...)", so it opens, answers and closes exactly as the method does. Nothing here starts a turn, so no module function can leave one running.
COMMON MODIFICATION PATTERNS: A new module function mirrors one CodexHost method with the same name and arguments, plus a keyword-only settings argument.
KNOWN EDGE CASES: check_codex_ready never raises a CodexAgentError: a host that cannot open, or a check that fails, comes back as ready=False with that failure as its one problem (AC-31).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.5 module functions and 9.2)
TESTS: tests/features/codex_host/test_codex_host_lifecycle.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.codex.host import CodexHost
from vidbyte.lib.constants.codex import CODEX_HOST_MINIMUM_VERSION
from vidbyte.lib.dataclasses.codex import CodexClientSettings
from vidbyte.lib.dataclasses.codex_host import (
    CodexModelInfo,
    CodexProblem,
    CodexRateLimits,
    CodexReadiness,
    CodexSpawnRequest,
    CodexThreadInfo,
    CodexThreadPage,
)
from vidbyte.lib.enums.codex import (
    CodexAccountKind,
    CodexSandboxReadiness,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSourceKind,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError


async def check_codex_ready(*, settings: CodexClientSettings | None = None) -> CodexReadiness:
    """Open a CodexHost, check that Codex is ready to run turns, and close it; failures are reported, not raised."""
    # A host that cannot open, or a check that fails, is a not-ready
    # answer carrying that failure as its one problem (AC-31).
    try:
        async with CodexHost(settings) as host:
            return await host.check_codex_ready()
    except CodexAgentError as exc:
        problem = CodexProblem(code=FailureCode(exc.failure_code), message=exc.message, next_step=exc.next_step)
        return CodexReadiness(
            ready=False,
            version="",
            minimum_version=CODEX_HOST_MINIMUM_VERSION,
            signed_in=False,
            account=CodexAccountKind.NONE,
            plan_type="",
            sandbox=CodexSandboxReadiness.NOT_CHECKED,
            problems=(problem,),
        )


async def get_codex_rate_limits(*, settings: CodexClientSettings | None = None) -> CodexRateLimits:
    """Open a CodexHost, read the account's usage windows, and close it."""
    async with CodexHost(settings) as host:
        return await host.get_codex_rate_limits()


async def list_codex_models(include_hidden: bool = False, *, settings: CodexClientSettings | None = None) -> tuple[CodexModelInfo, ...]:
    """Open a CodexHost, list every model Codex offers, and close it."""
    async with CodexHost(settings) as host:
        return await host.list_codex_models(include_hidden)


async def list_codex_threads(
    cwd: str = "",
    search: str = "",
    archived: bool = False,
    source_kinds: tuple[CodexThreadSourceKind, ...] = (),
    sort: CodexThreadSortKey = CodexThreadSortKey.PROVIDER_DEFAULT,
    sort_direction: CodexSortDirection = CodexSortDirection.PROVIDER_DEFAULT,
    cursor: str = "",
    *,
    settings: CodexClientSettings | None = None,
) -> CodexThreadPage:
    """Open a CodexHost, list one page of stored Codex threads, and close it."""
    # @intent a-one-shot-listing-owns-its-host
    # The host opens for this one page and closes on return, so a caller
    # that lists once never keeps an app-server process alive.
    async with CodexHost(settings) as host:
        return await host.list_codex_threads(cwd, search, archived, source_kinds, sort, sort_direction, cursor)


async def read_codex_thread(thread_id: str, include_turns: bool = False, *, settings: CodexClientSettings | None = None) -> CodexThreadInfo:
    """Open a CodexHost, read one stored Codex thread, and close it."""
    async with CodexHost(settings) as host:
        return await host.read_codex_thread(thread_id, include_turns)


async def fork_codex_thread(
    thread_id: str,
    from_turn_id: str = "",
    exclude_turns: bool = False,
    overrides: CodexSpawnRequest | None = None,
    *,
    settings: CodexClientSettings | None = None,
) -> CodexThreadInfo:
    """Open a CodexHost, fork a Codex thread through one of its completed turns, and close it."""
    async with CodexHost(settings) as host:
        return await host.fork_codex_thread(thread_id, from_turn_id, exclude_turns, overrides)


__all__ = [
    "check_codex_ready",
    "fork_codex_thread",
    "get_codex_rate_limits",
    "list_codex_models",
    "list_codex_threads",
    "read_codex_thread",
]
