"""FILE: vidbyte/lib/jev/done/state.py

PURPOSE: Defines DONE_STATE, the one description of the shared Jev state that every done question's brief uses, true for every combination of enabled done checks.
ROLE IN CODEBASE: Every JevDoneQuestion in this folder sets its brief's `state` to DONE_STATE, and JevRunState.combine (vidbyte/agents/jev/done/run_state.py) builds the state it describes: `request` plus one top-level field per enabled check.
ARCHITECTURE NOTE: Every enabled check's questions go to Jev in one request over one state, so a question's brief must describe fields its own check did not add; one shared description keeps every brief comparable line by line (skills/asking-jev-questions/SKILL.md, "Writing a full question").
COMMON MODIFICATION PATTERNS: When a done check adds a top-level state field, describe it here together with the condition under which it is present, and keep the sentence that each question judges only the field and id it names.
KNOWN EDGE CASES: A field is present only when its check is enabled, so the description never claims a fixed number of fields.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-self-review-done-criteria.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

# @intent the-shared-state-describes-itself-truthfully
# Every enabled check's questions read the same batched state, so this one description names every field a
# check can add and when it is present; a brief that described only its own check's fields would misdescribe
# the state as soon as a second check is enabled.
DONE_STATE = "The state always has `request`, and it holds one further field for each check that is turned on, so it has `deliverables`, `objections`, or both. `request` is the message a user sent to an AI agent to start a task, holding the user's own words together with any text, code, or data the user pasted into it. `deliverables` is present only when the check for separate outputs is on, and it maps the id of every separate output that `request` asks for to an entry with three fields: `deliverable` describes that one output and `completion_signal` is the visible condition that shows it is done, both written from `request` before the agent started any work, and `evidence` gathers every part of the agent's run that concerns `deliverable`. `objections` is present only when the strict-review check is on, and it maps the id of every objection that a strict reviewer raised against the agent's finished work to an entry with three fields: `objection` says what the reviewer would reject and where, and `resolved_when` is the visible condition under which the reviewer would accept the work, both written by the reviewer after the agent tried to finish, and `evidence` gathers every part of the agent's run that bears on `objection`. Each `evidence` is a report compiled after the agent tried to finish, from the agent's own record of its run: passages of the agent's final answer and earlier responses, the tool calls it made with their arguments and outputs, and the results of the commands or tests it ran, each marked with where it came from. The question names one field and one id, and every other entry, in that field or in the other, is checked separately, each by its own question."

__all__ = ["DONE_STATE"]
