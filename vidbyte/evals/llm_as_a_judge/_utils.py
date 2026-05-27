"""Context Protocol Header

Description:
    Shared utilities for all LLM-as-a-judge strategy graders.
Purpose:
    Eliminates code duplication across the 19 strategy files by centralising
    runner dispatch, response text extraction, and JSON block parsing.
Architecture:
    - invoke_runner: Async dispatcher for any runner interface.
    - extract_text: Converts heterogeneous runner results to plain strings.
    - parse_json_block: Extracts and decodes the first JSON object from model output.
Relations:
    Imported by every file in vidbyte/evals/llm_as_a_judge/.
"""

from __future__ import annotations

import inspect
import json
import re


async def invoke_runner(runner: object, prompt: str, temperature: float = 0.0) -> str:
    # Dispatches prompt to runner via arun/generate_reply/async-run/sync-run; raises TypeError if none found.
    if hasattr(runner, "arun"):
        res = await runner.arun(prompt, temperature=temperature)
    elif hasattr(runner, "generate_reply"):
        res = await runner.generate_reply(prompt, temperature=temperature)
    elif hasattr(runner, "run"):
        if inspect.iscoroutinefunction(runner.run):
            res = await runner.run(prompt, temperature=temperature)
        else:
            res = runner.run(prompt, temperature=temperature)
    else:
        raise TypeError("Judge runner must expose run(), generate_reply(), or arun() method.")
    return extract_text(res)


def extract_text(res: object) -> str:
    # Converts runner response to string: handles str, .text, .content, dict["text"], or str(res).
    if isinstance(res, str):
        return res
    if hasattr(res, "text"):
        return str(res.text)
    if hasattr(res, "content"):
        return str(res.content)
    if isinstance(res, dict) and "text" in res:
        return str(res["text"])
    return str(res)


def parse_json_block(text: str) -> dict:
    # Extracts first {...} JSON block from text; raises ValueError if none found or parse fails.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON block found in response: {text[:200]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON block: {exc}") from exc


__all__ = [
    "invoke_runner",
    "extract_text",
    "parse_json_block",
]
