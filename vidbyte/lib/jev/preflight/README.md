# Jev preflight questions

This folder holds every fixed question JevAgent sends to Jev before its generative agent runs, one dataclass per question, and `JevPreflightRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here — a brief (`JevBrief`), a criterion (`JevCriterion`), or a `gap` — it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow it. That skill is the house style for every Jev question in this SDK. In particular, its "Writing a full question" section is the template each question in `clarity.py` follows:

- the brief opens with a 2–3 sentence introduction, then describes the state, then defines every term in dependency order with no examples, then states every rule, then asks one positive yes/no question about `request`;
- the rules place a request with no task at all (an empty message, a greeting) on one explicit side, then give the focus, then end with the shared `JUDGE_MEANING` and `IGNORE_CLAIMS` rules (research tips T7, T8, and T14 in the skill);
- each criterion opens with the verdict in the defined term, lists only the signs of its side, names what belongs to the other side, and gives labeled easy and boundary examples that form minimal pairs across the two sides;
- the `gap` makes sense on its own to the clarification agent, which never sees the brief.

Feedback on one question applies to every question, so when you change the pattern, change it everywhere and update the skill in the same change.

## Where things live

- `clarity.py` holds the clarity preset's questions.
- `skills.py` builds the dynamic indexed relevance question for each configured skill document.
- `bulk_work.py` holds three separate recognition questions for multiple targets, one repeated operation, and explicit independent execution.
- `run_state_relation.py` holds the fixed relationship question for an existing run-state record.
- `specialist.py` holds the specialist Choice question; its options are built per run from `JevAgentSettings.agents`, with `none` always last.
- `preflight.py` holds `JevPreflightRegistry` (`get`, `questions`, `specialists`, `validate`).
- The flags and their question keys are in `vidbyte/lib/jev/presets.py` and `vidbyte/lib/enums/jev.py`; the records are in `vidbyte/lib/dataclasses/jev.py`.
- The logic that asks Jev and acts on the answers is `JevPreflightGate` in `vidbyte/agents/jev/gate/`.

The bulk-work questions are submitted in the same batched Jev request as every other enabled fixed question and any specialist Choice question. They only recognize request structure; planner item counting, bounded execution, and worker failures belong to `vidbyte/agents/jev/bulk_work.py`.
