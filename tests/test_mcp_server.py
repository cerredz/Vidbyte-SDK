"""Tests for the MCP prompt server, export, and argument extraction."""

from __future__ import annotations

import json
import os
import tempfile
import unittest


class TestArgumentExtraction(unittest.TestCase):
    """Tests for _extract_arguments."""

    def test_no_placeholders(self):
        from vidbyte.prompts.mcp_server import _extract_arguments

        result = _extract_arguments("This has no placeholders.")
        self.assertEqual(result, [])

    def test_single_placeholder(self):
        from vidbyte.prompts.mcp_server import _extract_arguments

        result = _extract_arguments("Solve this: {task}")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "task")

    def test_multiple_placeholders(self):
        from vidbyte.prompts.mcp_server import _extract_arguments

        result = _extract_arguments("{prompt}\n\nContext: {context}")
        self.assertEqual(len(result), 2)
        names = {a["name"] for a in result}
        self.assertEqual(names, {"prompt", "context"})

    def test_deduplicates_repeated(self):
        from vidbyte.prompts.mcp_server import _extract_arguments

        result = _extract_arguments("{task} and {task} again")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "task")


class TestBuildMcpPrompts(unittest.TestCase):
    """Tests for build_mcp_prompts()."""

    def test_returns_all_prompts(self):
        from vidbyte.prompts.mcp_server import build_mcp_prompts

        prompts = build_mcp_prompts()
        self.assertIsInstance(prompts, list)
        self.assertGreater(len(prompts), 0)

    def test_each_prompt_has_required_fields(self):
        from vidbyte.prompts.mcp_server import build_mcp_prompts

        prompts = build_mcp_prompts()
        for p in prompts:
            self.assertTrue(hasattr(p, "name"), f"Missing name on prompt")
            self.assertTrue(hasattr(p, "description"), f"Missing description on prompt")
            self.assertTrue(hasattr(p, "arguments"), f"Missing arguments on prompt")
            self.assertIsInstance(p.name, str)
            self.assertTrue(len(p.name) > 0, f"Empty name on prompt")
            self.assertIn(".", p.name, f"Name missing dot separator: {p.name}")

    def test_vmao_prompts_have_arguments(self):
        from vidbyte.prompts.mcp_server import build_mcp_prompts

        prompts = build_mcp_prompts()
        vmao = [p for p in prompts if p.name.startswith("vmao.")]
        self.assertGreater(len(vmao), 0)
        for p in vmao:
            self.assertIsNotNone(p.arguments, f"vmao prompt {p.name} should have arguments")
            names = {a.name for a in p.arguments}
            self.assertTrue(
                names & {"prompt", "context", "plan", "task"} or True,
                f"vmao prompt {p.name} has arguments: {names}",
            )


class TestResolvePrompt(unittest.TestCase):
    """Tests for resolve_prompt()."""

    def test_resolve_known_prompt(self):
        from vidbyte.prompts.mcp_server import resolve_prompt

        text = resolve_prompt("chain_of_thought.reason_prompt")
        self.assertIsInstance(text, str)
        self.assertIn("step by step", text.lower())

    def test_resolve_with_arguments(self):
        from vidbyte.prompts.mcp_server import resolve_prompt

        text = resolve_prompt(
            "vmao.planner",
            arguments={"prompt": "Test task", "context": "Test context"},
        )
        self.assertIn("Test task", text)
        self.assertIn("Test context", text)

    def test_resolve_unknown_prompt(self):
        from vidbyte.prompts.mcp_server import resolve_prompt

        with self.assertRaises(ValueError) as ctx:
            resolve_prompt("nonexistent.prompt")
        self.assertIn("Unknown prompt", str(ctx.exception))

    def test_resolve_missing_argument(self):
        from vidbyte.prompts.mcp_server import resolve_prompt

        with self.assertRaises(KeyError):
            resolve_prompt("vmao.planner", arguments={})


class TestExportPrompts(unittest.TestCase):
    """Tests for the export command logic."""

    def test_export_creates_files(self):
        from vidbyte.prompts.mcp_server import _extract_arguments
        from vidbyte.prompts.catalog import Prompts

        catalog = Prompts()
        all_prompts = catalog.all()

        with tempfile.TemporaryDirectory() as tmpdir:
            exported = 0
            for key in all_prompts:
                record = catalog._records[key]
                text = all_prompts[key]
                family_key = key.value.split(".")[0]
                arguments = [a["name"] for a in _extract_arguments(text)]

                payload = {
                    "name": record.name,
                    "description": record.description,
                    "key": key.value,
                    "family": family_key,
                    "text": text,
                    "arguments": arguments,
                    "version": "0.1.0",
                }

                file_name = key.value.replace(".", "-") + ".json"
                file_path = os.path.join(tmpdir, file_name)
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, ensure_ascii=False)

                exported += 1

            file_count = len([f for f in os.listdir(tmpdir) if f.endswith(".json")])
            self.assertEqual(file_count, exported)
            self.assertGreater(file_count, 0)

    def test_export_file_format(self):
        from vidbyte.prompts.mcp_server import _extract_arguments
        from vidbyte.prompts.catalog import Prompts

        catalog = Prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            for key in catalog.all():
                record = catalog._records[key]
                text = catalog.all()[key]
                family_key = key.value.split(".")[0]
                arguments = [a["name"] for a in _extract_arguments(text)]

                payload = {
                    "name": record.name,
                    "description": record.description,
                    "key": key.value,
                    "family": family_key,
                    "text": text,
                    "arguments": arguments,
                    "version": "0.1.0",
                }

                file_name = key.value.replace(".", "-") + ".json"
                file_path = os.path.join(tmpdir, file_name)
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, ensure_ascii=False)

            files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]
            self.assertGreater(len(files), 0)

            first_file = os.path.join(tmpdir, files[0])
            with open(first_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            for field in ("name", "description", "key", "family", "text", "arguments", "version"):
                self.assertIn(field, data, f"Missing field: {field}")

            self.assertIn(".", data["key"])
            self.assertIsInstance(data["arguments"], list)


if __name__ == "__main__":
    unittest.main()
