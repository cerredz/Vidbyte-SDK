"""FILE: tests/features/coding_agent/test_coding_agent_cli.py

PURPOSE: Prove that `vidbyte-sdk coding run` builds a CodingAgent over the folder it is given, runs one task through the real tool loop, prints only the final reply, reads a fetch key only from the environment variable a flag names, and fails cleanly on a bad folder or an unset variable.
ROLE IN CODEBASE: Calls vidbyte.cli.main in-process, as tests/test_cli_interface.py does, with the offline scripted model from conftest.py bound to the agent that vidbyte/cli/coding.py builds.
ARCHITECTURE NOTE: The only seam is CodingCommandGroup.build_agent, wrapped so the real CodingAgent it returns gets the scripted runner; the flags, the environment lookup, the tools, the permission policy, and the provider client are real, and the provider HTTP send is faked by conftest.py.
FUNCTION INVENTORY: test_coding_run_runs_the_task_* (the CLI runs one task under the default policy); test_coding_run_reads_the_fetch_key_* (key from the named variable, never printed); test_coding_run_fails_naming_* (unset variable); test_coding_run_rejects_a_root_* (bad folder).
COMMON MODIFICATION PATTERNS: A new flag gets one assertion on the agent captured from build_agent; script tool calls with conftest's ScriptedToolRunner, never a real model.
WHAT NOT TO DO IN THIS FILE: 1. Do not use a real API key or open a socket. 2. Do not stub CodingAgent; a broken agent must fail these tests.
KNOWN EDGE CASES: The scripted turns use the OpenAI chat-completions shape, so every run passes --provider openai.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; vidbyte/cli/README.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_cli.py
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.cli import main
from vidbyte.cli.coding import CodingCommandGroup

OFFLINE_MODEL_FLAGS = ["--provider", "openai", "--model", "gpt-4.1-mini"]
KEY_VARIABLE = "VIDBYTE_TEST_FIRECRAWL_KEY"
KEY_VALUE = "fc-cli-SECRET-5d21"
PAGE_URL = "https://docs.example.com/guide"


def _bind_offline_model(monkeypatch: pytest.MonkeyPatch, runner: object) -> list[Any]:
    # Wraps build_agent so the real CodingAgent it builds answers from
    # the scripted runner; returns the list each built agent lands in.
    built: list[Any] = []
    build = CodingCommandGroup.build_agent

    def build_offline(self: CodingCommandGroup, args: argparse.Namespace, keys: dict[str, str]) -> Any:
        agent = build(self, args, keys)
        built.append(agent)
        return bind_test_runner(agent, runner)

    monkeypatch.setattr(CodingCommandGroup, "build_agent", build_offline)
    return built


def test_coding_run_runs_the_task_in_the_root_folder_and_prints_only_the_reply(script_model, tmp_path, monkeypatch, capsys) -> None:
    # A write_text call succeeds only under CodingAgent's allow-all
    # default, so the file proves both the folder and the policy.
    runner = script_model([("write_text", {"path": "notes.txt", "content": "written by the cli"})], final_answer="Wrote notes.txt.")
    built = _bind_offline_model(monkeypatch, runner)

    code = main(["coding", "run", "--root-dir", str(tmp_path), *OFFLINE_MODEL_FLAGS, "Write notes.txt."])

    assert code == 0
    assert capsys.readouterr().out == "Wrote notes.txt.\n"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "written by the cli"
    [agent] = built
    assert agent.name == "coding-agent"
    assert agent.root_dir == tmp_path.resolve()
    assert agent.tools.names()[6] == "direct_http_fetch"


def test_coding_run_reads_the_fetch_key_from_the_named_variable_and_never_prints_it(script_model, fake_provider_http, tmp_path, monkeypatch, capsys) -> None:
    # The flag names a variable; its value must reach the provider as
    # the key and must never show up in the command's output.
    monkeypatch.setenv(KEY_VARIABLE, KEY_VALUE)
    sends = fake_provider_http(lambda send: (200, {"data": {"markdown": "# Guide", "metadata": {"sourceURL": PAGE_URL}}}))
    runner = script_model([("firecrawl_fetch", {"url": PAGE_URL})], final_answer="Read the guide.")
    built = _bind_offline_model(monkeypatch, runner)

    code = main(["coding", "run", "--root-dir", str(tmp_path), "--firecrawl-key-env", KEY_VARIABLE, *OFFLINE_MODEL_FLAGS, "Read the guide."])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "Read the guide.\n"
    assert KEY_VALUE not in captured.out + captured.err
    [agent] = built
    assert agent.tools.names()[6] == "firecrawl_fetch"
    [request] = sends
    assert any(KEY_VALUE in value for value in request["headers"].values())


def test_coding_run_fails_naming_an_unset_variable_before_building_an_agent(tmp_path, monkeypatch, capsys) -> None:
    # An unset variable is a setup mistake: report the flag and the
    # variable, and never start an agent with a missing key.
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    built = _bind_offline_model(monkeypatch, runner=None)

    code = main(["coding", "run", "--root-dir", str(tmp_path), "--firecrawl-key-env", KEY_VARIABLE, *OFFLINE_MODEL_FLAGS, "Read the guide."])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "--firecrawl-key-env" in captured.err
    assert KEY_VARIABLE in captured.err
    assert built == []


def test_coding_run_rejects_a_root_that_is_not_a_folder(tmp_path, capsys) -> None:
    # CodingAgentSettings owns the folder check; the CLI only reports
    # its error and exits with status 1.
    missing = tmp_path / "missing-folder"

    code = main(["coding", "run", "--root-dir", str(missing), *OFFLINE_MODEL_FLAGS, "Do anything."])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "root_dir must be an existing directory" in captured.err
