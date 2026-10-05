from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.dataclasses.skills import (
    _ClaudeSessionDefault,
    _USE_CONFIGURED_CLAUDE_SESSION,
    ClaudeSkillReference,
    ClaudeSkillSession,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse

_MAX_CLAUDE_SKILLS = 20
_CODE_EXECUTION_TOOL = {"type": "code_execution_20250825", "name": "code_execution"}


class AnthropicProvider:
    provider = ModelProvider.ANTHROPIC

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._parser = response_parser or HttpResponseParser()

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None, claude_skills: tuple[ClaudeSkillReference, ...] | None = None, claude_skill_session: ClaudeSkillSession | None | _ClaudeSessionDefault = _USE_CONFIGURED_CLAUDE_SESSION) -> TextModelResponse:
        # Execute an Anthropic Messages API request with optional tools/history.
        config = self._config(config)
        native_skills = config.claude_skills if claude_skills is None else claude_skills
        native_session = config.claude_skill_session if claude_skill_session is _USE_CONFIGURED_CLAUDE_SESSION else claude_skill_session
        if claude_skills is not None or claude_skill_session is not _USE_CONFIGURED_CLAUDE_SESSION:
            config = self._native_call_config(config, native_skills, native_session)
        if native_skills or native_session is not None:
            config.validate()
        payload = self._create_payload(config, prompt, system, metadata)
        request_messages = deepcopy(payload["messages"])
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/messages", headers=self._create_headers(config), json_body=payload, timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        session = self._read_native_session(parsed, request_messages) if config.claude_skills or config.claude_skill_session is not None else None
        text = self._extract_text(parsed, allow_empty=session is not None and session.paused)
        return TextModelResponse(provider=self.provider, model=config.model, text=text, raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None, claude_skill_session=session)

    def _native_call_config(self, config: TextModelConfig, skills: tuple[ClaudeSkillReference, ...], session: ClaudeSkillSession | None) -> TextModelConfig:
        # Copies only typed, request-local native fields into the existing immutable call config.
        return replace(config, claude_skills=skills, claude_skill_session=session)

    def _config(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError("AnthropicProvider requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build Anthropic's top-level system plus stateless messages payload.
        payload: dict[str, Any] = {"model": config.model, "max_tokens": config.max_output_tokens or 1024, "messages": self._create_messages(config, prompt)}
        self._attach_instructions(payload, config, system)
        self._attach_sampling(payload, config)
        self._attach_tools(payload, config)
        self._attach_native_container(payload, config)
        self._attach_response_format(payload, config)
        self._attach_metadata(payload, config, metadata)
        self._attach_extra_body(payload, config)
        return payload

    def _attach_native_container(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Mounts native skills with one required code-execution tool and preserves unrelated local tool schemas.
        if not config.claude_skills and config.claude_skill_session is None:
            return
        extra = dict(config.extra_body or {})
        if "container" in extra or "tools" in extra:
            raise ConfigurationError("extra_body cannot override container or tools when Claude-native skills are enabled.")
        skill_refs = [
            {"type": reference.type.value, "skill_id": reference.skill_id, "version": reference.version}
            for reference in config.claude_skills
        ]
        container: dict[str, Any] = {"skills": skill_refs}
        if config.claude_skill_session is not None:
            container["id"] = config.claude_skill_session.container_id
        payload["container"] = container
        tools = payload.setdefault("tools", [])
        self._ensure_code_execution_tool(tools)

    def _ensure_code_execution_tool(self, tools: list[dict[str, Any]]) -> None:
        # Adds the protocol tool once and rejects caller entries that would shadow its reserved name or type.
        matches = [tool for tool in tools if tool.get("name") == _CODE_EXECUTION_TOOL["name"] or tool.get("type") == _CODE_EXECUTION_TOOL["type"]]
        if not matches:
            tools.append(dict(_CODE_EXECUTION_TOOL))
            return
        if len(matches) != 1 or matches[0] != _CODE_EXECUTION_TOOL:
            raise ConfigurationError("Caller tools conflict with the reserved Claude code-execution tool.")

    def _read_native_session(self, parsed: Mapping[str, Any], request_messages: list[Mapping[str, Any]]) -> ClaudeSkillSession:
        # @intent replay-exact-native-pause-history
        # The next pause request must reuse the exact sent messages and raw assistant blocks; reconstruction can lose prior history or server content.
        content = parsed.get("content")
        container = parsed.get("container")
        stop_reason = parsed.get("stop_reason")
        if not isinstance(content, list) or not content or not all(isinstance(block, dict) for block in content):
            raise ProviderResponseError("Anthropic native-skill response did not include valid content blocks.", provider=self.provider.value)
        if not isinstance(container, dict) or not isinstance(container.get("id"), str) or not container["id"].strip():
            raise ProviderResponseError("Anthropic native-skill response did not include a valid container ID.", provider=self.provider.value)
        if not isinstance(stop_reason, str) or not stop_reason:
            raise ProviderResponseError("Anthropic native-skill response did not include a stop reason.", provider=self.provider.value)
        paused = stop_reason == "pause_turn"
        resume_messages = (*request_messages, {"role": "assistant", "content": deepcopy(content)}) if paused else ()
        return ClaudeSkillSession(container_id=container["id"], paused=paused, resume_messages=resume_messages)

    def _attach_response_format(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Anthropic carries the schema under output_config.format rather than a response_format field.
        if config.response_format is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": dict(config.response_format)}}

    def _create_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Include the required Anthropic version and API key headers.
        return {"x-api-key": config.resolved_api_key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _create_messages(self, config: TextModelConfig, prompt: str) -> list[dict[str, Any]]:
        # Paused sessions replay their provider snapshot; active containers use runtime-maintained history.
        if config.claude_skill_session is not None:
            if config.claude_skill_session.paused:
                return [deepcopy(dict(message)) for message in config.claude_skill_session.resume_messages]
            return [deepcopy(dict(message)) for message in config.messages] + [{"role": "user", "content": prompt}]
        return [dict(message) for message in config.messages] + [{"role": "user", "content": prompt}]

    def _attach_instructions(self, payload: dict[str, Any], config: TextModelConfig, system: str | None) -> None:
        # Anthropic uses a top-level system parameter rather than a system role.
        instructions = system or config.system
        if instructions:
            payload["system"] = instructions

    def _attach_sampling(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Add shared generation controls only when users configure them.
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.top_p is not None:
            payload["top_p"] = config.top_p
        if config.stop_sequences:
            payload["stop_sequences"] = list(config.stop_sequences)

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Anthropic tools and tool_choice pass through to the Messages API.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_choice is not None:
            payload["tool_choice"] = config.tool_choice
        if config.thinking_config:
            payload["thinking"] = dict(config.thinking_config)

    def _attach_metadata(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Merge runner-call metadata with static config metadata.
        combined = {**dict(config.metadata or {}), **dict(metadata or {})}
        if combined:
            payload["metadata"] = combined

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Allow new Anthropic fields without changing the SDK surface each time.
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def stream_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> Iterator[str]:
        # POST to /messages with stream=True and yield text from content_block_delta events.
        config = self._config(config)
        if config.claude_skills or config.claude_skill_session is not None:
            raise ConfigurationError("Streaming Claude-native skill requests are not supported.")
        payload = self._create_payload(config, prompt, system, metadata)
        payload["stream"] = True
        for raw_line in transport.stream_request(method="POST", url=f"{config.resolved_endpoint()}/messages", headers=self._create_headers(config), json_body=payload, timeout_seconds=config.timeout_seconds):
            chunk = self._extract_stream_delta(raw_line)
            if chunk is not None:
                yield chunk

    def _extract_stream_delta(self, raw_line: str) -> str | None:
        # Parse one SSE JSON line and return the text delta, or None for non-delta events.
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = delta.get("text")
                return text if isinstance(text, str) else None
        return None

    def _extract_text(self, parsed: Mapping[str, Any], *, allow_empty: bool = False) -> str:
        # Collect text content blocks while leaving tool_use blocks in raw output.
        content = parsed.get("content")
        if not isinstance(content, list):
            raise ProviderResponseError("Anthropic response did not include content.", provider=self.provider.value, response_excerpt=str(parsed))
        chunks = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not chunks and allow_empty:
            return ""
        if not chunks:
            if any(isinstance(item, dict) and item.get("type") == "tool_use" for item in content):
                return ""
            raise ProviderResponseError("Anthropic response did not include text content.", provider=self.provider.value, response_excerpt=str(parsed))
        return "\n".join(chunks)


__all__ = [
    "AnthropicProvider",
]
