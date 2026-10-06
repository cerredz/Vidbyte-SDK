# Jev dynamic-compute questions

This package holds the fixed evidence questions and registry for JevAgent's mid-run dynamic-compute checkpoint. `situations.py` contains twelve `JevComputeQuestion` objects for each of `FRESH_AGENT`, `FORK_AGENT`, and `SUBAGENT`; `compute.py` maps the options to those ordered question tuples. The existing question dataclass is used directly, with no question subclasses.

After a verified note-brief update, the recognizer puts all enabled questions into one Jev request over the shared state `{request, brief, facts, recent}`. The brief keeps the original request as its code-owned goal and only appends passages verified against their cited numbered event. State uses `JevRunBrief.render()`, the exact iteration, tool-call, error-streak, and known-token fields from `JevRunFacts`, and recent events from `JevRunEventLog.from_run`; request and event clipping stays in the agent-side state builder. The three options contribute 36 questions when all are enabled. Code selects the highest complete option mean P(true) that reaches `JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD`; ties follow enum order. The result is recorded for observation and does not launch compute.

## Write or review these questions

Load [`skills/asking-jev-dynamic-compute-questions/SKILL.md`](../../../../skills/asking-jev-dynamic-compute-questions/SKILL.md) before writing or reviewing these option questions. This feature uses that focused guidance and does not use the older `asking-jev-questions` skill for its prompts.

Each prompt is one string of 10–12 complete, connected sentences. It introduces an option's strength or failure mode, describes one distinct observable signal in general terms, asks whether that signal appears, and closes by clarifying the evidence boundary. Do not name state fields in the question text. Keep true/false criteria short and allow absent evidence to score false. Do not add eligibility rules, per-question vetoes, or a question asking whether to launch another agent.
