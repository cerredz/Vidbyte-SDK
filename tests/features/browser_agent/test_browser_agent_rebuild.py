"""FILE: tests/features/browser_agent/test_browser_agent_rebuild.py

PURPOSE: Proves the orchestrator context rebuild (INV-30): once the stored conversation passes BROWSER_HISTORY_MAX_TOKENS after a tool iteration or a refused finish, the next call carries exactly the newest whole call/result group (plus the gap message after a refusal), the task as its prompt, and the card with every recorded progress line; one context_rebuilt event and one counted rebuild mark each rebuild that removed messages, and a check that removes nothing records nothing.
ROLE IN CODEBASE: Rebuild layer of tests/features/browser_agent/ (spec AC-22, AC-33; INV-30, INV-14; EC-35, EC-36; D-11; FR-15). Exercises BrowserAgentRuntime._rebuild_history through _after_tool_iteration and _continue_finish_attempt, via BrowserAgent.run.
ARCHITECTURE NOTE: The recipe is spec section 13's: a developer extra tool returns plain letters longer than BROWSER_TOOL_RESULT_MAX_CHARS, so the loop's ToolSettings cuts each result to that size and each call in its own turn adds a little over 5,000 tokens of stored JSON. The tests do not hard-code the turn at which the cap is passed; they find the first call whose history shrank and check, with the spec's own measure (stored_tokens), that the check before it was under the cap and the stored history at that check was over it.
FUNCTION INVENTORY: test_history_over_the_cap_after_a_tool_iteration_is_rebuilt_to_the_last_exchange (AC-22, INV-30, INV-14); test_history_over_the_cap_at_a_refused_is_done_keeps_that_turn_and_the_gap (AC-33, INV-30, INV-16); test_a_single_group_over_the_cap_is_kept_whole_and_not_counted (EC-35, INV-30).
COMMON MODIFICATION PATTERNS: If BROWSER_TOOL_RESULT_MAX_CHARS or BROWSER_HISTORY_MAX_TOKENS changes, the step counts here stay valid as long as one bulk turn is a small fraction of the cap; the size checks would say so if not.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert the task as messages[0]; the scripted runner replaces the provider, so the task is only ModelCall.prompt (spec section 13). 3. Do not add compaction middleware to the agent under test; the rebuild must come from the runtime.
KNOWN EDGE CASES: The measure is the sum of TokenEstimate.count over each stored message's JSON text; json.dumps settings can move it by well under one percent, so the over/under checks allow 2 percent on each side of the cap.
RELATED DOCS: tests/features/browser_agent/FEATURE.md; docs/spec/browser-agent/spec.md sections 6.1 (INV-30), 6.2, 6.3, 8.1 (D-11) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_rebuild.py -q
"""

from __future__ import annotations

import json
from typing import Any

from tests.features.browser_agent.browser_agent_fixtures import (
    NAME,
    RECHECK,
    TASK,
    EventLog,
    FakeBrowserServers,
    ModelCall,
    ScriptedModel,
    assistant_turns,
    build_agent,
    card_section,
    installed,
    is_error,
    prompt_text,
    reply,
    stored_tokens,
    template_regex,
    tool_call,
    tool_calls,
    unpaired,
    verdict,
)
from vidbyte import tool

FINAL = "FINAL-ANSWER: the directory pages were read."
PROGRESS_LINE = "Seedcamp - https://seedcamp.com/apply - closes 30 November"
GAP = "The directory pages were read but no deadline was recorded."
TOLERANCE = 0.02


@tool(name="bulk_fetch")
def bulk_fetch(url: str) -> str:
    """Fetch one directory page in bulk and return its raw text."""
    return "A" * 25_000


def _bulk(page: int) -> Any:
    return tool_call("bulk_fetch", {"url": f"https://directory.example/page-{page}"})


def _url(call_turn: dict[str, Any]) -> str:
    return json.loads(call_turn["tool_calls"][0]["function"]["arguments"])["url"]


def _cap() -> int:
    from vidbyte.lib.constants.browser import BROWSER_HISTORY_MAX_TOKENS

    return BROWSER_HISTORY_MAX_TOKENS


def _first_shrink(calls: list[ModelCall]) -> int:
    for index in range(1, len(calls)):
        if len(calls[index].messages) < len(calls[index - 1].messages):
            return index
    raise AssertionError(f"no orchestrator call's history ever shrank: sizes {[stored_tokens(call.messages) for call in calls]}")


def test_history_over_the_cap_after_a_tool_iteration_is_rebuilt_to_the_last_exchange() -> None:
    """AC-22, INV-30, INV-14: after a progress patch and bulk turns that pass the cap, the next call holds exactly the last call turn and its result, the task as prompt, and the card with the progress; one context_rebuilt event came before it, and the run counts one rebuild."""
    log = EventLog()
    agent = build_agent(tools=(bulk_fetch,), on_event=log)
    model = ScriptedModel(
        {
            NAME: [tool_call("patch_goal", {"section": "progress", "text": PROGRESS_LINE}), *(_bulk(page) for page in range(1, 15)), tool_call("isDone", {"final_answer": FINAL})],
            RECHECK: [verdict("done", "Nothing is missing.")],
        }
    )
    log.model = model
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    calls = model.calls_by(NAME)
    shrink = _first_shrink(calls)
    before, rebuilt = calls[shrink - 1], calls[shrink]
    # The check after the previous iteration was under the cap, and the stored history at this check was over it.
    assert stored_tokens(before.messages) <= _cap() * (1 + TOLERANCE), "a rebuild was due one iteration earlier"
    assert stored_tokens(before.messages) + stored_tokens(rebuilt.messages) > _cap() * (1 - TOLERANCE), "the history was rebuilt below its cap"
    assert len(before.messages) > 2, "nothing older was there to remove"
    # Exactly the newest exchange: the bulk_fetch turn the model asked for on the previous call, and its result.
    assert len(rebuilt.messages) == 2
    turn, answer = rebuilt.messages
    assert assistant_turns([turn]) == [["bulk_fetch"]]
    assert _url(turn) == f"https://directory.example/page-{shrink - 1}"
    assert answer["role"] == "tool" and answer["tool_call_id"] == turn["tool_calls"][0]["id"] and str(answer["content"]).startswith("A" * 1_000)
    assert "patch_goal" not in json.dumps(rebuilt.messages)
    assert rebuilt.prompt == TASK
    assert PROGRESS_LINE in card_section(rebuilt.system)
    assert log.calls_at("context_rebuilt") == [shrink], "expected exactly one context_rebuilt event, just before the rebuilt call"
    # After the rebuild the history grows again from the kept exchange and never passes the cap a second time.
    for index in range(shrink + 1, len(calls)):
        assert calls[index].messages[:2] == rebuilt.messages
    assert agent.response.rebuilds == 1
    assert result.content == FINAL and agent.response.stop_reason == "is_done"


def test_history_over_the_cap_at_a_refused_is_done_keeps_that_turn_and_the_gap() -> None:
    """AC-33, INV-30, INV-16: when the cap is first passed in a turn that ends with isDone and the recheck says continue, the next call holds exactly that turn, its results with the isDone refusal, and the continue_prompt message, after exactly one context_rebuilt event."""
    log = EventLog()
    agent = build_agent(tools=(bulk_fetch,), on_event=log)
    model = ScriptedModel(
        {
            NAME: [
                tool_call("patch_goal", {"section": "progress", "text": PROGRESS_LINE}),
                *(_bulk(page) for page in range(1, 12)),
                tool_calls(("bulk_fetch", {"url": "https://directory.example/page-12"}), ("isDone", {"final_answer": "FIRST-ATTEMPT"})),
                reply(FINAL),
            ],
            RECHECK: [verdict("continue", GAP), verdict("done", "Nothing is missing.")],
        }
    )
    log.model = model
    with installed(model, FakeBrowserServers()):
        result = agent.run(TASK)
    model.assert_complete()
    calls = model.calls_by(NAME)
    assert len(calls) == 14
    finishing, after = calls[12], calls[13]
    assert stored_tokens(finishing.messages) <= _cap() * (1 + TOLERANCE), "the cap was passed before the isDone turn; the recipe no longer tests AC-33"
    assert log.calls_at("context_rebuilt") == [13], "expected exactly one context_rebuilt event, just before the call after the refusal"
    assert len(after.messages) == 4, [m.get("role") for m in after.messages]
    turn, fetched, refusal, gap = after.messages
    assert assistant_turns([turn]) == [["bulk_fetch", "isDone"]]
    assert fetched["role"] == "tool" and fetched["name"] == "bulk_fetch" and not is_error(str(fetched["content"]))
    assert refusal["role"] == "tool" and refusal["name"] == "isDone" and is_error(str(refusal["content"]))
    assert unpaired([turn, fetched, refusal]) == (set(), set())
    assert gap["role"] == "user"
    assert template_regex(prompt_text("continue_prompt"), verdict="continue", gap=GAP).fullmatch(str(gap["content"]).strip())
    assert after.prompt == TASK and PROGRESS_LINE in card_section(after.system) and GAP in card_section(after.system)
    assert agent.response.rebuilds == 1
    assert result.content == FINAL


def test_a_single_group_over_the_cap_is_kept_whole_and_not_counted() -> None:
    """EC-35, INV-30: one turn of many bulk calls that alone passes the cap is kept whole with no event; the next turn's check removes it, emits one event, and counts one rebuild."""
    log = EventLog()
    agent = build_agent(tools=(bulk_fetch,), on_event=log)
    many = tool_calls(*(("bulk_fetch", {"url": f"https://directory.example/batch-{page}"}) for page in range(1, 14)))
    model = ScriptedModel({NAME: [many, _bulk(14), reply(FINAL)], RECHECK: [verdict("done", "Nothing is missing.")]})
    log.model = model
    with installed(model, FakeBrowserServers()):
        agent.run(TASK)
    model.assert_complete()
    calls = model.calls_by(NAME)
    assert len(calls) == 3
    assert len(calls[1].messages) == 14, "the one oversized group was split or dropped"
    assert stored_tokens(calls[1].messages) > _cap() * (1 + TOLERANCE), "the recipe no longer passes the cap with one group"
    assert unpaired(calls[1].messages) == (set(), set())
    assert len(calls[2].messages) == 2 and _url(calls[2].messages[0]) == "https://directory.example/page-14"
    assert log.calls_at("context_rebuilt") == [2]
    assert agent.response.rebuilds == 1
