from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.context import ContextBudget, ContextPermissions, ContextResponse, ContextToolCall, TaskContextItem
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses import AgentCard, AgentMessage, CandidateResult, ToolSpec
from vidbyte.lib.enums import BudgetPreset, PermissionPreset
from vidbyte.prompts import Prompts


class ContextDataclassTests(unittest.TestCase):
    def test_public_dataclasses_are_centralized_and_shimmed(self) -> None:
        card = AgentCard(name="agent", description="", system_prompt="Review carefully.")
        candidate = CandidateResult(index=1, strategy_name="s", output="ok")
        tool = ToolSpec(name="lookup", description="Lookup")

        self.assertEqual(card.system_prompt, "Review carefully.")
        self.assertEqual(candidate.output, "ok")
        self.assertIn("lookup", tool.to_prompt_str())

    def test_context_builds_separate_files_tools_and_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("file body", encoding="utf-8")
            context = BaseContext(
                system_prompt="system",
                file_paths=[str(path)],
                run_metadata={"step": "draft"},
                tool_calls=[ContextToolCall(name="lookup", output="tool body")],
                responses=[ContextResponse(content="response body")],
                budget=ContextBudget.from_preset(BudgetPreset.TIGHT),
                permissions=ContextPermissions.from_preset(PermissionPreset.READ_ONLY),
                memory="prior summary",
                metadata={"run_env": "test"},
            )

            built = context.build_context()

        self.assertIn("file body", built)
        self.assertIn("Tool calls:", built)
        self.assertIn("Responses:", built)
        self.assertIn("Memory summary", built)
        self.assertIn("Run metadata", built)

    def test_non_utf8_context_file_renders_placeholder_like_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readable = Path(tmp) / "runbook.txt"
            readable.write_text("runbook body", encoding="utf-8")
            windows_export = Path(tmp) / "customers.csv"
            windows_export.write_bytes("Jürgen Müller,€ 612.40".encode("cp1252"))
            missing = Path(tmp) / "missing.txt"
            context = BaseContext(
                file_paths=[str(readable), str(windows_export), str(missing)],
                permissions=ContextPermissions.from_preset(PermissionPreset.READ_ONLY),
            )

            built = context.build_context()

        self.assertIn("runbook body", built)
        self.assertIn(f"File: {windows_export}\n<unable to read file: UnicodeDecodeError>", built)
        self.assertIn(f"File: {missing}\n<unable to read file:", built)

    def test_context_items_are_included_in_compatibility_context_build(self) -> None:
        context = BaseContext(context_items=[TaskContextItem(goal="document the public API")])

        built = context.build_context()

        self.assertIn("Context items:", built)
        self.assertIn("document the public API", built)

    def test_history_agent_message_renders_content_without_metadata(self) -> None:
        # [Context Bloat] Prior replies' metadata (tool outputs, usage) must not re-enter the prompt.
        big_output = "TOOL-OUTPUT-" + "x" * 5000
        message = AgentMessage(
            sender="r",
            recipient="orchestrator",
            content="short answer",
            metadata={"iteration_outputs": [big_output], "usage": {"total_tokens": 123}},
        )

        body = BaseContext(history=(message,)).build_context_body()

        self.assertIn("History:\nr -> orchestrator: short answer", body)
        self.assertNotIn("TOOL-OUTPUT-", body)
        self.assertNotIn("metadata", body)
        self.assertNotIn("AgentMessage(", body)

    def test_history_non_agent_message_items_render_via_str(self) -> None:
        body = BaseContext(history=("plain note", {"role": "user"})).build_context_body()

        self.assertIn("History:\nplain note\n{'role': 'user'}", body)

    def test_response_renders_its_sender_when_one_is_set(self) -> None:
        # A response's sender must reach the model, as history and artifacts keep theirs.
        built = BaseContext(responses=[ContextResponse(content="the discount is 30%", sender="pricing-bot")]).build_context()
        unattributed = BaseContext(responses=[ContextResponse(content="no sender here")]).build_context()

        self.assertIn("Responses:\nResponse from pricing-bot:\nthe discount is 30%", built)
        self.assertEqual(unattributed, "Responses:\nno sender here")

    def test_prompt_catalog_contains_reflexion_prompts(self) -> None:
        prompts = Prompts().family("reflexion")
        self.assertIn("agent_system_prompt", prompts)


if __name__ == "__main__":
    unittest.main()
