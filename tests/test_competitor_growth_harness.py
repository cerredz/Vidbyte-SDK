"""Context Protocol Header

Description:
    Unit and integration tests for the Competitor Growth Analyzer Harness.
Purpose:
    Verifies database creation, URL/query tracking, Obsidian adapter behavior (including filesystem fallbacks),
    and end-to-end agentic runs using a mock runner.
Architecture:
    - CompetitorGrowthHarnessTests: Test suite containing unit and mock integration tests.
Relation to codebase as a whole:
    Tests the vidbyte.harnesses.competitor_growth module to ensure reliability of custom harnesses.
Similar files:
    - tests/test_agent_base.py: Agent abstraction unit tests.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from vidbyte.harnesses.competitor_growth import (
    CompetitorGrowthAnalysis,
    CompetitorGrowthHarness,
    SQLiteHarnessMemory,
    ObsidianOutputAdapter,
)
from vidbyte.tools import ToolCall


class FakeResponse:
    """Mock model response for tool calling and text completion."""

    def __init__(self, text: str, raw: dict) -> None:
        # Save output fields.
        self.text = text
        self.raw = raw


class MockRunner:
    """Mock model runner to simulate final_answer with structured output."""

    def __init__(self, json_output: str) -> None:
        # Pre-configures the output string to return inside isDone arguments.
        self.json_output = json_output
        self.calls: list[dict] = []

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        # Saves input details and returns the pre-packaged isDone response.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        escaped_json = self.json_output.replace('"', '\\"')
        return FakeResponse(
            "",
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "isDone",
                        "arguments": f'{{"final_answer": "{escaped_json}"}}',
                        "call_id": "call_123",
                    }
                ]
            },
        )


class CompetitorGrowthHarnessTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for SQLite memory, Obsidian adapter, and competitor growth harness."""

    def setUp(self) -> None:
        # Setup temporary directories and database file paths for tests.
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        self.vault_path = os.path.join(self.temp_dir, "test_vault")
        self.harnesses_to_close: list[CompetitorGrowthHarness] = []

    def tearDown(self) -> None:
        # Clean up temporary test files and directories.
        for h in self.harnesses_to_close:
            try:
                h.close()
            except Exception:
                pass
        shutil.rmtree(self.temp_dir)

    def test_sqlite_memory_initialization(self) -> None:
        # Verifies SQLite database tables are created successfully.
        db = SQLiteHarnessMemory(self.db_path)
        cursor = db.conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='visited_urls'")
        self.assertIsNotNone(cursor.fetchone())

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='completed_searches'")
        self.assertIsNotNone(cursor.fetchone())
        db.close()

    def test_sqlite_record_and_lookup(self) -> None:
        # Verifies recording visited URLs and queries works correctly.
        db = SQLiteHarnessMemory(self.db_path)
        
        self.assertFalse(db.has_visited_url("https://test.com"))
        db.record_visit("https://test.com", "TestCompetitor")
        self.assertTrue(db.has_visited_url("https://test.com"))

        self.assertFalse(db.has_searched("test query"))
        db.record_search("test query")
        self.assertTrue(db.has_searched("test query"))
        db.close()

    async def test_obsidian_fallback_to_filesystem(self) -> None:
        # Verifies Obsidian output adapter falls back to direct filesystem write when REST API fails.
        adapter = ObsidianOutputAdapter(vault_path=self.vault_path, api_key="invalid_key", port="9999")
        analysis = CompetitorGrowthAnalysis(
            competitor_name="TestComp",
            website="https://testcomp.com",
            early_wedge="Viral invitations",
            growth_channels=["Referrals"],
            early_playbook_step_by_step="Step 1: Invite users.",
            borrowable_ideas_for_vidbyte=["Idea 1"],
            sources=["https://source1.com"],
        )

        success = await adapter.save_analysis(analysis)
        self.assertTrue(success)

        expected_file = Path(self.vault_path) / "Competitors" / "TestComp.md"
        self.assertTrue(expected_file.exists())
        content = expected_file.read_text(encoding="utf-8")
        self.assertIn("TestComp", content)
        self.assertIn("Viral invitations", content)

    async def test_agent_tools_called(self) -> None:
        # Verifies the agent tools returned by the harness execute successfully.
        harness = CompetitorGrowthHarness(db_path=self.db_path, vault_path=self.vault_path, port="9999")
        self.harnesses_to_close.append(harness)
        tools = harness._build_agent_tools("TestComp")
        
        has_visited_tool = next(t for t in tools if t.name == "has_visited_url")
        record_visit_tool = next(t for t in tools if t.name == "record_visited_url")

        res_record = await record_visit_tool.execute(ToolCall("record_visited_url", {"url": "https://checked.com"}))
        self.assertIn("Recorded URL", res_record.output)

        res_check = await has_visited_tool.execute(ToolCall("has_visited_url", {"url": "https://checked.com"}))
        self.assertIn("true", res_check.output.lower())
        harness.close()

    async def test_competitor_growth_harness_run(self) -> None:
        # Runs CompetitorGrowthHarness using a mock runner to test the end-to-end flow.
        harness = CompetitorGrowthHarness(db_path=self.db_path, vault_path=self.vault_path, port="9999")
        self.harnesses_to_close.append(harness)
        mock_data = {
            "competitor_name": "TurboLearn",
            "website": "https://turbolearn.ai",
            "early_wedge": "TikTok coordinated swarm",
            "growth_channels": ["TikTok UGC", "SEO"],
            "early_playbook_step_by_step": "Step 1: Swarm TikTok accounts. Step 2: Scale templates.",
            "borrowable_ideas_for_vidbyte": ["Swarm accounts for target hooks"],
            "sources": ["https://sources.com"],
        }
        runner = MockRunner(json.dumps(mock_data))

        result = await harness.run_analysis("TurboLearn", runner=runner)
        self.assertIsInstance(result, CompetitorGrowthAnalysis)
        self.assertEqual(result.competitor_name, "TurboLearn")
        self.assertEqual(result.early_wedge, "TikTok coordinated swarm")

        expected_file = Path(self.vault_path) / "Competitors" / "TurboLearn.md"
        self.assertTrue(expected_file.exists())
        harness.close()


if __name__ == "__main__":
    unittest.main()
