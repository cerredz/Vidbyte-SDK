"""FILE: vidbyte/agents/codex/fork.py

PURPOSE: Owns native Codex thread-fork execution and child configuration propagation.
ROLE IN CODEBASE: Separates fork preconditions, lineage, and overrides from the public agent facade.
ARCHITECTURE NOTE: Returns typed child settings so this module never imports or constructs the facade.
COMMON MODIFICATION PATTERNS: Add fork-only controls to CodexForkSettings and propagate them here.
KNOWN EDGE CASES: A parent must have a successful thread id; cancellation must remain unwrapped.
RELATED DOCS: docs/design/codex-harness-agent.md; https://developers.openai.com/codex/app-server.
TESTS: python scripts/run_ci.py.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import replace

from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.constants.codex import CODEX_NEXT_FORK_DEPTH, CODEX_ROOT_FORK_DEPTH
from vidbyte.lib.dataclasses.codex import (
    CodexForkRequest,
    CodexForkResult,
    CodexHarnessAgentSettings,
    CodexTransportForkRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError


class CodexFork:
    """Owns fork preconditions, transport, overrides, lineage, and failures."""

    def __init__(self, transport: CodexTransport) -> None:
        # @intent single-provider-transport
        # Reuse the facade's transport so forks cannot bypass its cleanup and
        # provider-failure classification boundary.
        self._transport = transport

    async def afork(self, request: CodexForkRequest) -> CodexForkResult:
        # @intent provider-native-lineage
        # Validate and copy local settings before creating a provider resource;
        # publish the child only after Codex confirms its native thread id.
        if not request.parent_thread_id:
            raise CodexAgentError(
                "CodexHarnessAgent cannot fork before its first successful thread start.",
                failure_code=FailureCode.CODEX_FORK_FAILED.value,
                operation="fork_precondition",
            )
        try:
            child = self._prepare_child(request)
            identity = await self._transport.fork_thread(
                CodexTransportForkRequest(
                    thread_id=request.parent_thread_id,
                    system_prompt=child.system_prompt,
                    settings=child.codex,
                )
            )
            return CodexForkResult(
                settings=replace(child, thread_id=identity.thread_id)
            )
        except asyncio.CancelledError:
            raise
        except CodexAgentError:
            raise
        except Exception as exc:
            raise CodexAgentError(
                "Codex fork settings could not be prepared or propagated.",
                failure_code=FailureCode.CODEX_FORK_FAILED.value,
                operation="prepare_fork",
                error_type=type(exc).__name__,
            ) from exc

    @staticmethod
    def _prepare_child(request: CodexForkRequest) -> CodexHarnessAgentSettings:
        # @intent validate-before-native-fork
        # Copy mutable context and resolve schemas before making an external
        # thread so an invalid override cannot leave behind an unusable branch.
        parent = request.parent
        settings = request.overrides
        child_codex = settings.codex if settings.codex is not None else parent.codex
        child_system_prompt = settings.system_prompt or parent.system_prompt
        metadata = {
            **dict(parent.metadata),
            **dict(settings.metadata),
            "forked_from_thread_id": request.parent_thread_id,
            "fork_depth": int(
                parent.metadata.get("fork_depth", CODEX_ROOT_FORK_DEPTH)
                or CODEX_ROOT_FORK_DEPTH
            )
            + CODEX_NEXT_FORK_DEPTH,
        }
        child_settings = CodexHarnessAgentSettings(
            name=settings.name or parent.name,
            system_prompt=child_system_prompt,
            codex=child_codex,
            additional_context=parent.additional_context
            if settings.additional_context is None
            else settings.additional_context,
            context_manager=copy.deepcopy(
                settings.context_manager
                if settings.context_manager is not None
                else parent.context_manager
            ),
            output_schema=parent.output_schema
            if settings.output_schema is None
            else settings.output_schema,
            description=parent.description
            if settings.description is None
            else settings.description,
            capabilities=parent.capabilities
            if settings.capabilities is None
            else settings.capabilities,
            metadata=metadata,
            context_placements=parent.context_placements
            if settings.context_placements is None
            else settings.context_placements,
        )
        if settings.clear_context_manager:
            child_settings = replace(child_settings, context_manager=None, context_placements=())
        if settings.clear_output_schema:
            child_settings = replace(child_settings, output_schema=None)
        return CodexVidbyteTranslator().translate_agent(child_settings).settings

    def fork(self, request: CodexForkRequest) -> CodexForkResult:
        # @intent no-nested-fork-loop
        # Run the async fork only outside an active loop so synchronous callers
        # cannot strand an in-flight native fork.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.afork(request))
        raise CodexAgentError(
            "CodexHarnessAgent.fork() cannot run inside an active event loop; use await afork().",
            failure_code=FailureCode.CODEX_FORK_FAILED.value,
            operation="fork_sync_guard",
        )


__all__ = ["CodexFork"]
