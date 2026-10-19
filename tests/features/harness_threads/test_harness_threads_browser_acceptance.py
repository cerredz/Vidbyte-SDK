"""FILE: tests/features/harness_threads/test_harness_threads_browser_acceptance.py

PURPOSE: AC-1 of docs/spec/harness-browser-tools/spec.md: the §4 developer snippet, copied verbatim, runs end to end against the offline fakes and prints exactly the shown shape: the fake's thread id and text, the playwright and firecrawl calls the fake opencode made through the fake node servers, `()` for the first result's artifacts and, for the continue that takes a screenshot, one file under the remaining per-call artifacts folder.
ROLE IN CODEBASE: The one end-to-end proof of the public usage. Start here when the README example or the public signatures change.
ARCHITECTURE NOTE: The snippet has no config, so opencode is found on PATH: an `opencode` stand-in in the sandbox bin folder plays it, with calls_by_prompt mapping "screenshot" to Playwright's screenshot tool. Node, the tool cache and Chrome come from browser_world. Only the workspace literal is replaced, and the snippet runs as a script with its own asyncio.run, so the test is synchronous.
FUNCTION INVENTORY: snippet_for returns the §4 snippet with the sandbox workspace; artifact_paths reads the paths out of a printed tuple repr; the test_* function runs the snippet.
COMMON MODIFICATION PATTERNS: When spec §4 changes, copy the new snippet into SNIPPET unchanged and update the expected lines.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SNIPPET beyond the workspace replacement; its point is that the documented code runs as written. 2. Do not set real keys; the two variables hold fake keys shaped like real ones.
KNOWN EDGE CASES: The PATH stand-in is an `.exe` on win32 and needs pip's console-script launcher; the test skips when pip lacks it, as the pack's other PATH tests do.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-browser-tools/spec.md §4, §6.2 AC-1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_browser_acceptance.py
"""

from __future__ import annotations

import re

SNIPPET = '''import asyncio
import os

from vidbyte.harnesses.native import continue_opencode_with_browser, run_opencode_with_browser


async def main() -> None:
    result = await run_opencode_with_browser(
        "Open https://example.com and tell me the page heading.",
        api_key=os.environ["DEEPSEEK_API_KEY"],          # the harness key, as for run_opencode_thread
        workspace="C:/work/site",
        model="deepseek/deepseek-v4-pro",
        tools=["playwright", "firecrawl:search"],         # registry strings: <tool>[:<capability>,...]
        tool_keys={"firecrawl": os.environ["FIRECRAWL_API_KEY"]},
    )
    print(result.thread_id, result.text)                  # e.g. ses_8f2c... Example Domain
    for call in result.tool_calls:                        # e.g. playwright browser_navigate completed
        print(call.tool.value, call.name, call.status.value)
    print(result.artifacts)                               # absolute paths of screenshots, or ()

    again = await continue_opencode_with_browser(result.thread_id, "Now take a screenshot.", api_key=os.environ["DEEPSEEK_API_KEY"], workspace="C:/work/site", model="deepseek/deepseek-v4-pro", tools=["playwright"])
    print(again.artifacts)                                # e.g. (WindowsPath('C:/Users/u/AppData/Local/Temp/vidbyte-browser-k3x9/artifacts/page-2026-10-17T10-00-00-000Z.png'),)


asyncio.run(main())
'''
WORKSPACE_LITERAL = '"C:/work/site"'
FIRST_PROMPT = "Open https://example.com and tell me the page heading."
DEEPSEEK_KEY = "sk-" + "5e8a1c3f7b9d2e4a" + "6c8f0b1d3e5a7c9f"
FIRECRAWL_KEY = "fc-" + "3f9a2b7c4d1e8f6a" + "5b0c9d2e7f1a4b8c"
SCREENSHOT_CALLS = {"screenshot": ["vidbyte-playwright_browser_take_screenshot"]}
EXPECTED_CALLS = ["firecrawl firecrawl_search completed", "playwright browser_navigate completed"]
PATH_IN_REPR = re.compile(r"Path\('([^']*)'\)")


def snippet_for(workspace: str) -> str:
    assert SNIPPET.count(WORKSPACE_LITERAL) == 2
    return SNIPPET.replace(WORKSPACE_LITERAL, repr(workspace))


def artifact_paths(line: str) -> list[str]:
    # Path reprs spell the path with forward slashes on every platform.
    return PATH_IN_REPR.findall(line)


def test_the_developer_snippet_runs_as_documented(browser_world, sandbox, monkeypatch, capsys, pack) -> None:
    # AC-1 / §4: two BrowserThreadResults with the fake's thread id and
    # text, the fake's tool calls, and the second result's artifacts
    # under the per-call artifacts folder.
    sandbox.stand_in(sandbox.bin, "opencode", "opencode", calls_by_prompt=SCREENSHOT_CALLS)
    monkeypatch.setenv("DEEPSEEK_API_KEY", DEEPSEEK_KEY)
    monkeypatch.setenv("FIRECRAWL_API_KEY", FIRECRAWL_KEY)
    exec(compile(snippet_for(str(sandbox.workspace)), "<spec §4 snippet>", "exec"), {"__name__": "__main__"})
    lines = capsys.readouterr().out.splitlines()
    first, second = sandbox.answers("opencode")
    assert second["session"] == first["session"], "the continue answered on the same thread"
    assert lines[0] == f"{first['session']} opencode answer to: {FIRST_PROMPT}"
    assert sorted(lines[1:3]) == EXPECTED_CALLS and lines[3] == "()" and len(lines) == 5
    (folder,) = sandbox.call_folders()
    printed = artifact_paths(lines[4])
    (written,) = sorted((folder / "artifacts").iterdir())
    assert len(printed) == 1 and pack.same_path(printed[0], written), lines[4]
    assert lines[4].startswith("(") and lines[4].endswith(",)")
