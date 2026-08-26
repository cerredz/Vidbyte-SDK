# Context primitives

This folder owns immutable, typed units managed by `ContextManager`. A primitive
defines structural context data plus a compact compatibility rendering; placement,
registry identity, and freezing remain manager responsibilities.

## File index

- `base.py` - `ContextItem` protocol and shared primitive helpers.
- `documents.py` - text, file, diff, document, environment, and memory primitives.
- `tasks.py` - task, progress, and plan primitives.
- `records.py` - artifact, response, and tool-call primitives.
- `checkpoints.py` - reflexion and trajectory checkpoint primitives.
- `reasoning.py` - problem-space and error-correction primitives.
- `reasoning_traces.py` - bounded public checkpoints for 182 strategy-specific reasoning trace tools.
- `multi_agent.py` - request, team, ledger, report, limit, and terminal primitives used by `MultiAgentContext`.
- `framing.py` - problem-frame, objective, boundary, ambiguity, and perspective challenges.
- `epistemics.py` - assumption, model, and evidence challenges.
- `decisions.py` - decision, alternative, and tradeoff challenges.
- `execution.py` - invariant, dependency, intervention-risk, and feedback-gap challenges.
- `closure.py` - process-stall, completion-gate, and risk-escalation challenges.
- `__init__.py` - supported public primitive exports.

Multi-agent primitives preserve explicit trust boundaries: user requests, ledger
values, worker reports, candidate answers, and finish rationales render inside
`<untrusted_data>` sections. Context construction belongs in
`vidbyte/context/multi_agent.py`, not in an agent runtime.

Reasoning trace primitives are also explicitly model-authored and untrusted.
They keep method application, evidence, assumptions, alternatives,
disconfirmation signals, confidence, and next action visible across iterations,
but they do not verify the claims or execute the named reasoning strategy.
