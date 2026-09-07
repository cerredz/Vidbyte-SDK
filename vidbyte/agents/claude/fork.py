"""FILE: vidbyte/agents/claude/fork.py

PURPOSE: Owns Claude fork preconditions, override resolution, and child lineage.
ROLE IN CODEBASE: Separates fork policy from the public agent facade and the transport.
ARCHITECTURE NOTE: Claude has no fork wire call, so this collaborator is local and total.
COMMON MODIFICATION PATTERNS: Add a fork-only control to ClaudeForkSettings and resolve it here.
KNOWN EDGE CASES: A child holds no session id of its own until its first successful run.
RELATED DOCS: docs/design/claude-harness-agent.md; https://code.claude.com/docs/en/agent-sdk/sessions.
TESTS: python scripts/test-claude-harness-agent.py; python scripts/run_ci.py.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from vidbyte.agents.claude.config import ClaudeVidbyteTranslator
from vidbyte.lib.constants.claude import CLAUDE_NEXT_FORK_DEPTH, CLAUDE_ROOT_FORK_DEPTH
from vidbyte.lib.dataclasses.claude import (
    ClaudeAgentSettings,
    ClaudeForkRequest,
    ClaudeForkResult,
    ClaudeForkSettings,
    ClaudeHarnessAgentSettings,
    ClaudeSessionSettings,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeAgentError


class ClaudeFork:
    """Owns fork preconditions, overrides, lineage, and failure classification."""

    def fork(self, request: ClaudeForkRequest) -> ClaudeForkResult:
        # @intent lazy-provider-fork
        # Claude has no thread_fork call: a child carries resume plus fork_session and
        # receives its own session id from its first result message, so this is local.
        if not request.parent_session_id:
            raise ClaudeAgentError(
                "ClaudeHarnessAgent cannot fork before its first successful run.",
                failure_code=FailureCode.CLAUDE_FORK_FAILED.value,
                operation="fork_precondition",
            )
        try:
            return ClaudeForkResult(settings=self._prepare_child(request))
        # A malformed child override already has a more precise configuration failure.
        except ClaudeAgentError:
            raise
        # Invalid overrides or an uncopyable context manager fail before any child exists.
        except Exception as exc:
            raise ClaudeAgentError(
                "Claude fork settings could not be prepared or propagated.",
                failure_code=FailureCode.CLAUDE_FORK_FAILED.value,
                operation="prepare_fork",
                error_type=type(exc).__name__,
            ) from exc

    async def afork(self, request: ClaudeForkRequest) -> ClaudeForkResult:
        # @intent async-parity-without-a-fake-await
        # Both harness adapters expose afork, but Claude forks locally, so this must not
        # imply a provider round trip that never happens.
        return self.fork(request)

    @classmethod
    def _prepare_child(cls, request: ClaudeForkRequest) -> ClaudeHarnessAgentSettings:
        # @intent validate-the-child-before-returning-it
        # An invalid override must fail here, while nothing external exists yet, rather
        # than on the child's first run when a caller already holds the agent.
        parent = request.parent
        overrides = request.overrides
        child = ClaudeHarnessAgentSettings(
            name=overrides.name or parent.name,
            system_prompt=overrides.system_prompt or parent.system_prompt,
            claude=cls._child_claude(request),
            additional_context=cls._inherit(
                overrides.additional_context, parent.additional_context
            ),
            context_manager=copy.deepcopy(
                cls._inherit(overrides.context_manager, parent.context_manager)
            ),
            output_schema=cls._inherit(overrides.output_schema, parent.output_schema),
            description=cls._inherit(overrides.description, parent.description),
            capabilities=cls._inherit(overrides.capabilities, parent.capabilities),
            metadata=cls._child_metadata(request),
            session_id="",
        )
        child = cls._apply_clears(child, overrides)
        return ClaudeVidbyteTranslator().translate_agent(child).settings

    @staticmethod
    def _child_claude(request: ClaudeForkRequest) -> ClaudeAgentSettings:
        # @intent branch-from-the-parent-not-continue-it
        # The child must resume the parent's session with fork_session set, and must
        # not inherit a continuation or a message boundary meant for the parent.
        inherited = request.overrides.claude or request.parent.claude
        return replace(
            inherited,
            session=ClaudeSessionSettings(
                resume=request.parent_session_id,
                fork_session=True,
                continue_conversation=False,
                resume_session_at="",
            ),
        )

    @staticmethod
    def _child_metadata(request: ClaudeForkRequest) -> dict[str, Any]:
        # @intent lineage-outlives-the-fork-call
        # A child's own session id replaces the parent's on its first run, so the parent
        # link has to be recorded in metadata now or it is unrecoverable later.
        parent_depth = int(
            request.parent.metadata.get("fork_depth", CLAUDE_ROOT_FORK_DEPTH)
            or CLAUDE_ROOT_FORK_DEPTH
        )
        return {
            **dict(request.parent.metadata),
            **dict(request.overrides.metadata),
            "forked_from_session_id": request.parent_session_id,
            "fork_depth": parent_depth + CLAUDE_NEXT_FORK_DEPTH,
        }

    @staticmethod
    def _apply_clears(
        child: ClaudeHarnessAgentSettings, overrides: ClaudeForkSettings
    ) -> ClaudeHarnessAgentSettings:
        # Removes an inherited manager or schema when the caller asked to clear it.
        if overrides.clear_context_manager:
            child = replace(child, context_manager=None)
        if overrides.clear_output_schema:
            child = replace(child, output_schema=None)
        return child

    @staticmethod
    def _inherit(override: Any, inherited: Any) -> Any:
        # @intent none-means-inherit-not-empty
        # An empty tuple or empty string is a deliberate replacement, so only None can
        # mean "keep the parent's value" without making a real override unreachable.
        return inherited if override is None else override


__all__ = ["ClaudeFork"]
