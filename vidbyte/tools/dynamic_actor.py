"""
FILE: vidbyte/tools/dynamic_actor.py

PURPOSE:
    Defines the DynamicActorTool allowing active actors to dynamically spawn sub-actors. Enables autonomous model-driven agent creation during execution to solve sub-tasks.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - DynamicActorTool (class): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""
from __future__ import annotations
from typing import Any
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolParameter


class DynamicActorTool(BaseTool):
    """Allows active agent actors to dynamically spawn and register new sub-actors."""

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def spec(self) -> ToolSpec:
        """Returns the model-facing declaration for the dynamic spawn tool."""
        return ToolSpec(
            name="spawn_actor",
            description="Spawn a new specialized actor dynamically to solve a sub-task. Provide a unique actor name, a descriptive system prompt, and optionally a specific model name to run the actor with.",
            parameters=(
                ToolParameter(
                    name="actor_name",
                    type="str",
                    description="The unique name or ID of the actor to spawn (e.g., 'coder_assistant_1').",
                    required=True,
                ),
                ToolParameter(
                    name="system_prompt",
                    type="str",
                    description="Detailed system prompt or persona instructions for the spawned actor.",
                    required=True,
                ),
                ToolParameter(
                    name="model_name",
                    type="str",
                    description="Optional specialized model name to run this actor with. If not provided, falls back to worker_model or orchestrator model.",
                    required=False,
                ),
            ),
            permission=ToolPermission.SAFE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Invokes the broker spawn registry at runtime."""
        actor_name = call.arguments.get("actor_name")
        system_prompt = call.arguments.get("system_prompt")
        model_name = call.arguments.get("model_name")

        if not actor_name or not system_prompt:
            return ToolResult.error(self.name, "Both actor_name and system_prompt are required.")

        try:
            await self._broker.spawn(actor_name, system_prompt, model_name)
            return ToolResult.success(
                self.name,
                f"Successfully spawned actor '{actor_name}' with the specified system prompt.",
                metadata={"spawned_actor": actor_name},
            )
        except Exception as e:
            return ToolResult.error(self.name, f"Failed to spawn actor: {e}")
