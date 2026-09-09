"""Native dynamic-tool parameter translation.

PURPOSE: Serialize reviewed Vidbyte settings through the pinned native models.
ROLE IN CODEBASE: Supplies raw request dictionaries to public CodexClient.
ARCHITECTURE NOTE: dynamicTools is an explicit experimental protocol extension.
COMMON MODIFICATION PATTERNS: Preserve generated aliases and existing tool schemas.
KNOWN EDGE CASES: Thread and turn sandbox fields use different native shapes.
RELATED DOCS: docs/design/codex-native-tools.md
TESTS: tests/codex_native_tools/test_native_tools.py
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from vidbyte.agents.codex.config import CodexContentTranslator
from vidbyte.lib.dataclasses.codex import CodexSdkTypes, CodexTransportRunRequest
from vidbyte.tools.catalog import Tools


class CodexToolWire:
    """Convert existing translations into generated native request models."""

    @staticmethod
    def declarations(tools: Tools) -> list[dict[str, Any]]:
        # Keep Vidbyte schema/activity formatting authoritative at registration.
        declarations = []
        for schema in tools.provider_schemas("openai"):
            function = schema["function"]
            declarations.append({"type": "function", "name": function["name"], "description": function["description"], "inputSchema": function["parameters"]})
        return declarations

    @classmethod
    def thread(cls, request: CodexTransportRunRequest, sdk: CodexSdkTypes, tools: Tools) -> dict[str, Any]:
        # @intent actual-native-tool-registration
        # Extend generated parameters only with the binary's reviewed experimental field.
        from openai_codex.generated.v2_all import ThreadStartParams

        values = CodexContentTranslator.thread_start_kwargs(request.system_prompt, request.settings, sdk)
        cls.approval(values, default=True)
        if "sandbox" in values:
            values["sandbox"] = cls.sandbox(values["sandbox"].value)
        result = ThreadStartParams.model_validate(values).model_dump(mode="json", by_alias=True, exclude_none=True)
        result["dynamicTools"] = cls.declarations(tools)
        return result

    @classmethod
    def turn(cls, request: CodexTransportRunRequest, sdk: CodexSdkTypes, thread_id: str) -> dict[str, Any]:
        # @intent preserve-native-turn-controls
        # Preserve native modality and turn controls through generated validation.
        from openai_codex.generated.v2_all import TurnStartParams

        values = CodexContentTranslator.turn_kwargs(request.settings, request.output_schema, sdk)
        cls.approval(values, default=False)
        if "sandbox" in values:
            mode = cls.sandbox(values.pop("sandbox").value)
            values["sandbox_policy"] = {"type": {"read-only": "readOnly", "workspace-write": "workspaceWrite", "danger-full-access": "dangerFullAccess"}[mode]}
        values["thread_id"] = thread_id
        values["input"] = [asdict(item) for item in request.prompt.items]
        return TurnStartParams.model_validate(values).model_dump(mode="json", by_alias=True, exclude_none=True)

    @staticmethod
    def approval(values: dict[str, Any], *, default: bool) -> None:
        # Match high-level SDK auto-review defaults without implying local tool permission.
        mode = values.pop("approval_mode", None)
        if mode is None and not default:
            return
        automatic = mode is None or mode.value == "auto_review"
        values["approval_policy"] = "on-request" if automatic else "never"
        if automatic:
            values["approvals_reviewer"] = "auto_review"

    @staticmethod
    def sandbox(value: str) -> str:
        # Normalize the one convenience enum spelling absent from the wire protocol.
        return "danger-full-access" if value == "full-access" else value


__all__ = ["CodexToolWire"]
