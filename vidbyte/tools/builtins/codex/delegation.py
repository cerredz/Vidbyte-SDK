"""FILE: vidbyte/tools/builtins/codex/delegation.py

PURPOSE: The two CodexHost tools that hand work to other Codex threads: launch_codex_subagents, which starts one thread per prompt, and start_codex_review, which starts a Codex code review; both start paid Codex work.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these last, in the order of the CodexHost functions.
ARCHITECTURE NOTE: Both tools hold cap slots while the host starts their turns: launch holds one per prompt, so a batch that would pass the cap is refused before any thread starts (INV-32). Launch runs every thread under the developer's spawn_defaults with no limit of its own, since the scope's cap already bounds it.
COMMON MODIFICATION PATTERNS: A new review target field is one schema property and one CodexReviewTarget field; the record checks the combination.
KNOWN EDGE CASES: Codex has deprecated detached review delivery, so inline is the default. The review tool takes any thread id (D-12).
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 tool table, rows 14 and 15)
TESTS: tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexReviewDelivery,
    CodexReviewTargetKind,
)
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    BRANCH_DESCRIPTION,
    DELIVERY_DESCRIPTION,
    INSTRUCTIONS_DESCRIPTION,
    LAUNCH_CODEX_SUBAGENTS_DESCRIPTION,
    PROMPTS_DESCRIPTION,
    SHA_DESCRIPTION,
    START_CODEX_REVIEW_DESCRIPTION,
    TARGET_KIND_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    TITLE_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

LAUNCH = CodexHostOperation.LAUNCH_CODEX_SUBAGENTS
REVIEW = CodexHostOperation.START_CODEX_REVIEW
ONE_TURN = 1
TARGET_KINDS = [member.value for member in CodexReviewTargetKind]
DELIVERIES = [member.value for member in CodexReviewDelivery]
TARGET_KIND_MESSAGE = f"'target_kind' must be one of: {', '.join(TARGET_KINDS)}."


class LaunchCodexSubagentsTool(_CodexHostTool):
    """Starts one new Codex thread per prompt, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # Only the prompts are the model's.
        return ToolSpec(
            name=LAUNCH.value,
            description=LAUNCH_CODEX_SUBAGENTS_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["prompts"],
                "properties": {"prompts": {"type": "array", "items": {"type": "string"}, "minItems": ONE_TURN, "description": PROMPTS_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return one handle per prompt, as a JSON array.
        return await self._run(LAUNCH.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Hold one cap slot per prompt while the host starts the
        # threads, so a batch that would pass the cap starts nothing
        # (INV-32).
        prompts = self._resolve_texts(call, "prompts")
        await self._scope.reserve(self._host, len(prompts), LAUNCH)
        try:
            handles = await self._host.launch_codex_subagents(prompts, request=self._scope.spawn_defaults, limit=None)
        finally:
            self._scope.release(len(prompts))
        self._scope.own(handles)
        return self._json(handles)


class StartCodexReviewTool(_CodexHostTool):
    """Starts a Codex code review of any thread's work."""

    def spec(self) -> ToolSpec:
        # The thread and the target are required; the rest fill the
        # target.
        return ToolSpec(
            name=REVIEW.value,
            description=START_CODEX_REVIEW_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id", "target_kind"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "target_kind": {"type": "string", "enum": TARGET_KINDS, "description": TARGET_KIND_DESCRIPTION},
                    "branch": {"type": "string", "description": BRANCH_DESCRIPTION},
                    "sha": {"type": "string", "description": SHA_DESCRIPTION},
                    "title": {"type": "string", "description": TITLE_DESCRIPTION},
                    "instructions": {"type": "string", "description": INSTRUCTIONS_DESCRIPTION},
                    "delivery": {"type": "string", "enum": DELIVERIES, "description": DELIVERY_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the review turn's handle as JSON.
        return await self._run(REVIEW.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Build the target from the model's fields; the record checks
        # that they fit the target kind.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        kind = self._resolve_choice(call, "target_kind", CodexReviewTargetKind)
        if kind is None:
            raise ToolExecutionError(TARGET_KIND_MESSAGE, details={"parameter": "target_kind"})
        target = CodexReviewTarget(
            kind=kind,
            branch=self._resolve_text(call, "branch"),
            sha=self._resolve_text(call, "sha"),
            title=self._resolve_text(call, "title"),
            instructions=self._resolve_text(call, "instructions"),
        )
        delivery = self._resolve_choice(call, "delivery", CodexReviewDelivery) or CodexReviewDelivery.INLINE
        # Hold one cap slot while the host starts the review.
        await self._scope.reserve(self._host, ONE_TURN, REVIEW)
        try:
            handle = await self._host.start_codex_review(thread_id, target, delivery=delivery)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


__all__ = ["LaunchCodexSubagentsTool", "StartCodexReviewTool"]
