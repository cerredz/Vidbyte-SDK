from __future__ import annotations

import json
import unittest

from vidbyte.agents.runtime import _args_fingerprint, _output_fingerprint
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools import ToolCall


class FormatAssistantToolCallsTests(unittest.TestCase):
    """Covers the inverse serializer that echoes a turn's tool calls into context."""

    def _openai_raw(self, message: dict) -> object:
        # Wraps an OpenAI assistant message into a chat-completions raw payload for parsing.
        tool_calls = message["tool_calls"]
        return type("R", (), {"raw": {"choices": [{"message": {"tool_calls": tool_calls}}]}})()

    def test_openai_round_trip_preserves_name_and_arguments(self) -> None:
        # [Silent Failure] wrong serialization that still looks valid would corrupt the echoed call.
        call = ToolCall("read_file", {"path": "a.py", "start": 1}, call_id="call_1")
        msg = ToolsFormatter.format_assistant_tool_calls([call], "draft", "openai")
        parsed = ToolsFormatter.parse_tool_calls(self._openai_raw(msg), "openai")
        self.assertEqual(parsed[0].tool_name, "read_file")
        self.assertEqual(dict(parsed[0].arguments), {"path": "a.py", "start": 1})

    def test_anthropic_round_trip_preserves_name_and_arguments(self) -> None:
        # [Silent Failure] anthropic tool_use input must survive serialization.
        call = ToolCall("grep", {"pattern": "TODO"}, call_id="toolu_1")
        msg = ToolsFormatter.format_assistant_tool_calls([call], "", "anthropic")
        raw = type("R", (), {"raw": {"content": msg["content"]}})()
        parsed = ToolsFormatter.parse_tool_calls(raw, "anthropic")
        self.assertEqual(parsed[0].tool_name, "grep")
        self.assertEqual(dict(parsed[0].arguments), {"pattern": "TODO"})

    def test_gemini_round_trip_preserves_name_and_arguments(self) -> None:
        # [Silent Failure] gemini functionCall args must survive serialization.
        call = ToolCall("glob", {"pattern": "**/*.py"})
        msg = ToolsFormatter.format_assistant_tool_calls([call], "", "gemini")
        raw = type("R", (), {"raw": {"candidates": [{"content": {"parts": msg["parts"]}}]}})()
        parsed = ToolsFormatter.parse_tool_calls(raw, "gemini")
        self.assertEqual(parsed[0].tool_name, "glob")
        self.assertEqual(dict(parsed[0].arguments), {"pattern": "**/*.py"})

    def test_multi_call_turn_is_one_message_with_n_calls_openai(self) -> None:
        # [Hidden Assumption] the runtime must not assume one-call-per-turn.
        calls = [ToolCall("a", {"x": 1}, call_id="c1"), ToolCall("b", {"y": 2}, call_id="c2")]
        msg = ToolsFormatter.format_assistant_tool_calls(calls, "", "openai")
        self.assertEqual(msg["role"], "assistant")
        self.assertEqual(len(msg["tool_calls"]), 2)

    def test_multi_call_turn_anthropic_pairs_with_results(self) -> None:
        # [Hidden Failure] anthropic assistant tool_use blocks must align with tool_result blocks.
        calls = [ToolCall("a", {"x": 1}, call_id="c1"), ToolCall("b", {"y": 2}, call_id="c2")]
        msg = ToolsFormatter.format_assistant_tool_calls(calls, "", "anthropic")
        tool_use_ids = [block["id"] for block in msg["content"] if block["type"] == "tool_use"]
        self.assertEqual(tool_use_ids, ["c1", "c2"])

    def test_cap_truncates_oversized_string_value_but_keeps_key(self) -> None:
        # [Edge Case] a huge write body must not dominate context tokens, yet the key stays.
        call = ToolCall("write", {"body": "x" * 50_000, "path": "f.py"})
        msg = ToolsFormatter.format_assistant_tool_calls([call], "", "anthropic", max_arg_chars=10)
        body = msg["content"][0]["input"]["body"]
        self.assertTrue(body.endswith("...[truncated]"))
        self.assertIn("path", msg["content"][0]["input"])

    def test_cap_does_not_redact_secret_value_in_context(self) -> None:
        # [Hidden Assumption] context policy is truncate-only; the model needs the real value.
        call = ToolCall("auth", {"api_key": "xai-secret-123"})
        msg = ToolsFormatter.format_assistant_tool_calls([call], "", "anthropic", max_arg_chars=1000)
        self.assertEqual(msg["content"][0]["input"]["api_key"], "xai-secret-123")

    def test_empty_text_omits_text_block_anthropic(self) -> None:
        # [Edge Case] no assistant text means no leading text block.
        msg = ToolsFormatter.format_assistant_tool_calls([ToolCall("a", {})], "", "anthropic")
        self.assertTrue(all(block["type"] == "tool_use" for block in msg["content"]))

    def test_empty_text_sets_content_none_openai(self) -> None:
        # [Edge Case] OpenAI assistant content is None when there is no text.
        msg = ToolsFormatter.format_assistant_tool_calls([ToolCall("a", {})], "", "openai")
        self.assertIsNone(msg["content"])

    def test_missing_call_id_falls_back_to_tool_name(self) -> None:
        # [Edge Case] a None call_id must not produce a null id.
        msg = ToolsFormatter.format_assistant_tool_calls([ToolCall("lookup", {})], "", "openai")
        self.assertEqual(msg["tool_calls"][0]["id"], "lookup")

    def test_non_serializable_argument_value_does_not_raise(self) -> None:
        # [Hidden Failure] non-JSON values must coerce via default=str, never crash the loop.
        msg = ToolsFormatter.format_assistant_tool_calls([ToolCall("a", {"s": {1, 2, 3}})], "", "openai")
        json.loads(msg["tool_calls"][0]["function"]["arguments"])  # must be valid JSON


class FingerprintTests(unittest.TestCase):
    """Covers the stable fingerprints used to correlate repeated tool calls."""

    def test_args_fingerprint_is_key_order_independent(self) -> None:
        # [Silent Failure] a key-order-sensitive hash would falsely separate identical calls.
        self.assertEqual(_args_fingerprint({"a": 1, "b": 2}), _args_fingerprint({"b": 2, "a": 1}))

    def test_args_fingerprint_differs_for_different_arguments(self) -> None:
        # [Edge Case] different inputs must produce different fingerprints.
        self.assertNotEqual(_args_fingerprint({"a": 1}), _args_fingerprint({"a": 2}))

    def test_args_fingerprint_of_empty_is_stable_and_nonempty(self) -> None:
        # [Edge Case] an empty-argument call still yields a usable fingerprint.
        fp = _args_fingerprint({})
        self.assertEqual(fp, _args_fingerprint({}))
        self.assertTrue(fp)

    def test_output_fingerprint_matches_for_identical_output(self) -> None:
        # [Silent Failure] identical outputs must share a fingerprint for correlation.
        self.assertEqual(_output_fingerprint("same"), _output_fingerprint("same"))

    def test_output_fingerprint_differs_for_different_output(self) -> None:
        # [Edge Case] differing outputs must not collide.
        self.assertNotEqual(_output_fingerprint("a"), _output_fingerprint("b"))


if __name__ == "__main__":
    unittest.main()
