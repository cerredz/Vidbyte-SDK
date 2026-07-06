from __future__ import annotations

import unittest

from vidbyte.providers import tool_spec_to_provider_schema
from vidbyte.tools import ToolCall, ToolResult, ToolsFormatter, tool, vidbyte_tool


class ProviderToolSchemaTranslationTests(unittest.TestCase):
    def test_openai_and_xai_schema_shape(self) -> None:
        @vidbyte_tool
        def fetch_user_metrics(user_id: int) -> str:
            """Fetches user metrics."""
            return str(user_id)

        schema = tool_spec_to_provider_schema(fetch_user_metrics.spec(), "openai")

        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "fetch_user_metrics")
        self.assertIn("user_id", schema["function"]["parameters"]["properties"])

    def test_anthropic_schema_shape(self) -> None:
        @vidbyte_tool
        def clear_cache(cache_key: str) -> str:
            """Clears a cache key."""
            return cache_key

        schema = tool_spec_to_provider_schema(clear_cache.spec(), "anthropic")

        self.assertEqual(schema["name"], "clear_cache")
        self.assertIn("cache_key", schema["input_schema"]["properties"])

    def test_gemini_schema_shape(self) -> None:
        @vidbyte_tool
        def clear_cache(cache_key: str) -> str:
            """Clears a cache key."""
            return cache_key

        schema = tool_spec_to_provider_schema(clear_cache.spec(), "gemini")

        self.assertEqual(schema["name"], "clear_cache")
        self.assertIn("cache_key", schema["parameters"]["properties"])

    def test_parse_provider_tool_call_payloads(self) -> None:
        openai_calls = ToolsFormatter.parse_tool_calls(
            {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "sdk"}', "call_id": "call-1"}]},
            "openai",
        )
        chat_calls = ToolsFormatter.parse_tool_calls(
            {"choices": [{"message": {"tool_calls": [{"id": "call-2", "function": {"name": "lookup", "arguments": '{"topic": "chat"}'}}]}}]},
            "openai",
        )
        anthropic_calls = ToolsFormatter.parse_tool_calls(
            {"content": [{"type": "tool_use", "id": "call-3", "name": "lookup", "input": {"topic": "claude"}}]},
            "anthropic",
        )
        gemini_calls = ToolsFormatter.parse_tool_calls(
            {"candidates": [{"content": {"parts": [{"functionCall": {"name": "lookup", "args": {"topic": "gemini"}}}]}}]},
            "gemini",
        )

        self.assertEqual(openai_calls[0].tool_name, "lookup")
        self.assertEqual(chat_calls[0].call_id, "call-2")
        self.assertEqual(anthropic_calls[0].arguments["topic"], "claude")
        self.assertEqual(gemini_calls[0].arguments["topic"], "gemini")

    def test_tool_alias_schema_shape(self) -> None:
        @tool
        def fetch_user_metrics(user_id: int) -> str:
            """Fetches user metrics."""
            return str(user_id)

        schema = tool_spec_to_provider_schema(fetch_user_metrics.spec(), "xai")

        self.assertEqual(schema["function"]["name"], "fetch_user_metrics")


class ProviderAwareToolErrorRenderingTests(unittest.TestCase):
    def test_success_result_shapes_are_unchanged(self) -> None:
        call = ToolCall("lookup", {"topic": "sdk"}, call_id="call-1")
        result = ToolResult.success("lookup", "ok")

        self.assertEqual(
            ToolsFormatter.format_tool_result(call, result, "anthropic"),
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": "ok"}]},
        )
        self.assertEqual(
            ToolsFormatter.format_tool_result(call, result, "gemini"),
            {"role": "function", "parts": [{"functionResponse": {"name": "lookup", "response": {"output": "ok", "status": "success"}}}]},
        )
        self.assertEqual(
            ToolsFormatter.format_tool_result(call, result, "openai"),
            {"role": "tool", "tool_call_id": "call-1", "name": "lookup", "content": "ok"},
        )

    def test_anthropic_error_sets_native_error_flag_and_envelope(self) -> None:
        call = ToolCall("lookup", call_id="tu-1")
        result = ToolResult.error(
            "lookup",
            "missing topic",
            metadata={"error": "invalid_arguments", "hint": "Pass topic.", "retryable": False},
        )

        formatted = ToolsFormatter.format_tool_result(call, result, "anthropic")
        block = formatted["content"][0]

        self.assertTrue(block["is_error"])
        self.assertEqual(block["tool_use_id"], "tu-1")
        self.assertIn("[tool_error kind=invalid_arguments retryable=false]", block["content"])
        self.assertIn("Hint: Pass topic.", block["content"])

    def test_gemini_error_uses_structured_response(self) -> None:
        call = ToolCall("lookup", call_id="fn-1")
        result = ToolResult.error(
            "lookup",
            "rate limited",
            metadata={"error": "rate_limited", "hint": "Wait and retry.", "retryable": True},
        )

        formatted = ToolsFormatter.format_tool_result(call, result, "gemini")
        response = formatted["parts"][0]["functionResponse"]["response"]

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "rate_limited")
        self.assertEqual(response["message"], "rate limited")
        self.assertEqual(response["hint"], "Wait and retry.")
        self.assertTrue(response["retryable"])

    def test_openai_error_encodes_envelope_in_content(self) -> None:
        call = ToolCall("lookup", call_id="call-1")
        result = ToolResult.error("lookup", "bad args", metadata={"error_type": "validation", "retryable": "false"})

        formatted = ToolsFormatter.format_tool_result(call, result, "openai")

        self.assertEqual(formatted["role"], "tool")
        self.assertEqual(formatted["tool_call_id"], "call-1")
        self.assertIn("[tool_error kind=invalid_arguments retryable=false]", formatted["content"])
        self.assertIn("bad args", formatted["content"])

    def test_openai_responses_error_uses_function_call_output_shape(self) -> None:
        call = ToolCall("lookup", call_id="fc-1", metadata={"provider_shape": "openai_responses"})
        result = ToolResult.error("lookup", "upstream failed", metadata={"error": "upstream_error", "retryable": True})

        formatted = ToolsFormatter.format_tool_result(call, result, "openai")

        self.assertEqual(formatted["type"], "function_call_output")
        self.assertEqual(formatted["call_id"], "fc-1")
        self.assertIn("[tool_error kind=upstream_error retryable=true]", formatted["output"])

    def test_default_error_rendering_includes_full_details(self) -> None:
        call = ToolCall("shell", call_id="call-1")
        result = ToolResult.error(
            "shell",
            "Tool execution failed: command exited 2",
            metadata={"error": "execution_error", "detail": "stderr: missing file"},
        )

        formatted = ToolsFormatter.format_tool_result(call, result, "openai")

        self.assertIn("Tool execution failed: command exited 2", formatted["content"])
        self.assertIn("Detail: stderr: missing file", formatted["content"])

    def test_error_rendering_always_includes_full_available_details(self) -> None:
        call = ToolCall("shell", call_id="call-1")
        result = ToolResult.error(
            "shell",
            "Tool execution failed: secret path C:/private",
            metadata={"error": "execution_error", "hint": "Check cwd.", "detail": "traceback"},
        )

        anthropic = ToolsFormatter.format_tool_result(call, result, "anthropic")
        openai = ToolsFormatter.format_tool_result(call, result, "openai")

        self.assertTrue(anthropic["content"][0]["is_error"])
        self.assertIn("secret path", anthropic["content"][0]["content"])
        self.assertIn("Hint: Check cwd.", anthropic["content"][0]["content"])
        self.assertIn("Detail: traceback", anthropic["content"][0]["content"])
        self.assertIn("secret path", openai["content"])
        self.assertIn("Hint: Check cwd.", openai["content"])
        self.assertIn("Detail: traceback", openai["content"])


class AssistantToolCallHistoryFormatterTests(unittest.TestCase):
    # ── OpenAI chat completions ──────────────────────────────────────────────

    def test_openai_returns_assistant_message_when_tool_calls_present(self) -> None:
        raw = {
            "choices": [
                {"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}}
            ]
        }
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "assistant")
        self.assertIsInstance(result["tool_calls"], list)
        self.assertEqual(result["tool_calls"][0]["id"], "call_1")

    def test_openai_returns_none_for_text_only_response(self) -> None:
        raw = {"choices": [{"message": {"role": "assistant", "content": "Hello!", "tool_calls": None}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertIsNone(result)

    def test_openai_returns_none_when_tool_calls_absent(self) -> None:
        raw = {"choices": [{"message": {"role": "assistant", "content": "Hello!"}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertIsNone(result)

    def test_openai_returns_none_for_responses_api_shape(self) -> None:
        raw = {"output": [{"type": "function_call", "name": "read", "arguments": "{}", "call_id": "fc_1"}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertIsNone(result)

    def test_openai_returns_none_for_empty_choices(self) -> None:
        result = ToolsFormatter.format_assistant_tool_calls({"choices": []}, "openai")
        self.assertIsNone(result)

    def test_openai_multiple_tool_calls_returns_single_message(self) -> None:
        raw = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                        {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
                    ],
                }
            }]
        }
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertIsNotNone(result)
        self.assertEqual(len(result["tool_calls"]), 2)

    # ── Anthropic ────────────────────────────────────────────────────────────

    def test_anthropic_returns_assistant_message_when_tool_use_present(self) -> None:
        raw = {"content": [{"type": "tool_use", "id": "tu_1", "name": "read", "input": {"path": "f.py"}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "assistant")
        self.assertEqual(result["content"][0]["type"], "tool_use")

    def test_anthropic_returns_none_for_text_only_content(self) -> None:
        raw = {"content": [{"type": "text", "text": "Hello!"}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
        self.assertIsNone(result)

    def test_anthropic_preserves_text_blocks_alongside_tool_use(self) -> None:
        raw = {
            "content": [
                {"type": "text", "text": "I'll check that."},
                {"type": "tool_use", "id": "tu_2", "name": "read", "input": {}},
            ]
        }
        result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
        self.assertIsNotNone(result)
        self.assertEqual(len(result["content"]), 2)
        self.assertEqual(result["content"][0]["type"], "text")

    def test_anthropic_returns_none_for_empty_content(self) -> None:
        result = ToolsFormatter.format_assistant_tool_calls({"content": []}, "anthropic")
        self.assertIsNone(result)

    # ── Gemini ───────────────────────────────────────────────────────────────

    def test_gemini_returns_model_content_when_function_call_present(self) -> None:
        raw = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "read", "args": {}}}]}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
        self.assertIsNotNone(result)
        self.assertEqual(result["role"], "model")
        self.assertIn("functionCall", result["parts"][0])

    def test_gemini_returns_none_for_text_only_parts(self) -> None:
        raw = {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello!"}]}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
        self.assertIsNone(result)

    def test_gemini_returns_none_for_empty_candidates(self) -> None:
        result = ToolsFormatter.format_assistant_tool_calls({"candidates": []}, "gemini")
        self.assertIsNone(result)

    # ── Generic / edge cases ─────────────────────────────────────────────────

    def test_returns_none_for_non_mapping_raw(self) -> None:
        result = ToolsFormatter.format_assistant_tool_calls("not a dict", "openai")
        self.assertIsNone(result)

    def test_returns_none_for_none_raw(self) -> None:
        result = ToolsFormatter.format_assistant_tool_calls(None, "openai")
        self.assertIsNone(result)

    def test_role_is_assistant_for_openai(self) -> None:
        raw = {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
        self.assertEqual(result["role"], "assistant")

    def test_role_is_model_for_gemini(self) -> None:
        raw = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "f", "args": {}}}]}}]}
        result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
        self.assertEqual(result["role"], "model")

    def test_raw_object_with_raw_attribute_is_unwrapped(self) -> None:
        class FakeResponse:
            raw = {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "y", "type": "function", "function": {"name": "g", "arguments": "{}"}}]}}]}
        result = ToolsFormatter.format_assistant_tool_calls(FakeResponse(), "openai")
        self.assertIsNotNone(result)
        self.assertEqual(result["tool_calls"][0]["id"], "y")


if __name__ == "__main__":
    unittest.main()

