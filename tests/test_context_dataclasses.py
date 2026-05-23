from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.context import ContextBudget, ContextPermissions, ContextResponse, ContextToolCall, StrategyContext
from vidbyte.lib.dataclasses import AgentCard, CandidateResult, ToolSpec
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
            context = StrategyContext(
                system_prompt="system",
                file_paths=[str(path)],
                strategy_metadata={"step": "draft"},
                tool_calls=[ContextToolCall(name="lookup", output="tool body")],
                responses=[ContextResponse(content="response body")],
                budget=ContextBudget.from_preset(BudgetPreset.TIGHT),
                permissions=ContextPermissions.from_preset(PermissionPreset.READ_ONLY),
                memory="prior summary",
            )

            built = context.build_context()

        self.assertIn("file body", built)
        self.assertIn("Tool calls:", built)
        self.assertIn("Responses:", built)
        self.assertIn("Strategy progress metadata", built)

    def test_prompt_catalog_contains_vmao_prompts(self) -> None:
        prompts = Prompts().family("vmao")
        self.assertIn("planner", prompts)


if __name__ == "__main__":
    unittest.main()
