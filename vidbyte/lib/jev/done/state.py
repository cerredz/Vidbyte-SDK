"""FILE: vidbyte/lib/jev/done/state.py

PURPOSE: Defines DONE_STATE, the one description of the batched Jev state that every done question's brief uses as its `state` section.
ROLE IN CODEBASE: Every JevDoneQuestion in this folder (multi_part.py, expert_depth.py) sets `JevBrief.state` to DONE_STATE, because JevRunState.combine() sends every enabled check's questions to Jev in one request over one shared state.
ARCHITECTURE NOTE: The state always holds `request`, plus one top-level field per enabled done check, so this text describes each field together with the condition under which it is present and must stay true for every combination of enabled checks (skills/jev-continuation/SKILL.md step 11). It lives in its own module so that no question module imports another.
COMMON MODIFICATION PATTERNS: When a done check adds a top-level state field, describe it here with its presence condition, and name its entry fields exactly as the JEV_DONE_*_FIELD constants in vidbyte/lib/constants/jev.py spell them.
KNOWN EDGE CASES: Two checks' entries both carry `deliverable` and `evidence`; the text defines them once for both fields, and the question's focus rule keeps each question on its own field and id.
RELATED DOCS: docs/design/jev-expert-depth-done-criteria.md, docs/design/jev-multipart-done-criteria.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

# Every done question reads the same shared state, so every brief describes it with the same words.
DONE_STATE = "The state always holds `request`, and it holds one more field for each kind of check that is enabled, so it may hold `deliverables`, `expert_details`, or both. `request` is the message a user sent to an AI agent to start a task, holding the user's own words together with any text, code, or data the user pasted into it. `deliverables`, present only when the check for separate outputs is enabled, maps the id of every separate output that `request` asks for to an entry with three fields. In that entry, `deliverable` describes that one output, written from `request` before the agent started any work, and `completion_signal` is the visible condition, written at the same time, that shows this one output is done. `expert_details`, present only when the check for depth is enabled, maps the id of every weak point of an output that `request` asks for to an entry with five fields. In that entry, `deliverable` describes the output the point belongs to, `detail` names one specific part of that output that a careful version handles and a quick version handles thinly or skips, `shallow_version` describes what the quick version of that part looks like, and `done_when` is the visible condition that shows the part handled in depth, all written from `request` before the agent started any work. In both fields, `evidence` is a report compiled after the agent tried to finish, from the agent's own record of its run, that gathers every part of the run that concerns its entry: passages of the agent's final answer and earlier responses, the tool calls it made with their arguments and outputs, and the results of the commands or tests it ran, each marked with where it came from. The question names one field and one id, and every other entry, in either field, is checked separately, each by its own question."


__all__ = ["DONE_STATE"]
