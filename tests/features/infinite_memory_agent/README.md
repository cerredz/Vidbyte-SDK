# InfiniteMemory agent

## Folder Description / Intent

This folder holds the feature tests for `InfiniteMemoryAgent`: a root agent that hands work to generator→verifier pairs of fresh subagents through `launch_subagent`, keeps memory in one guarded workspace folder, and resumes a crashed or cancelled run from its journal. The tests are offline. The only fake is the model runner, patched at `BaseAgent._runner_for_model` so it reaches every agent in the tree. The workspace, the journal, `ParallelPipeline`, the prompt catalog, the filesystem, and `bash` all run for real under `tmp_path`. The behavior itself lives in `vidbyte/agents/infinite/`, with its records, enums, and constants in `vidbyte/lib/`, not here. The contract comes from `docs/spec/infinite-memory-agent/spec.md`.

The pack covers every acceptance criterion from AC-1 to AC-42, plus the regression and guardrail tests added after the S4 review, and `docs/spec/infinite-memory-agent/test-plan.md` maps each test to the spec IDs it proves.

The live event stream (`on_event`, `InfiniteEvent`) and the run handoff (`run_handoff`, `InfiniteHandoff`) are covered by the `test_infinite_memory_events_*.py` files and `test_infinite_memory_handoff.py`, from `docs/spec/infinite-memory-events/spec.md`; `docs/spec/infinite-memory-events/test-plan.md` maps those tests to their spec IDs.

## File Index

- `README.md` describes the scope and how to run the pack.
- `FEATURE.md` defines the contract, the invariants, the known failure modes with the test that catches each, and the strategies left out on purpose.
- `infinite_memory_fixtures.py` provides the scripted model tree routed by agent name, the Gate and Signal used to order concurrent agents without sleeps, settings and agent builders, and readers for the workspace files, the journal, and prompt templates.
- `test_infinite_memory_acceptance.py` runs the spec's section 4 snippet as written, staging then commit, the usage roll-up, and a second agent on the same workspace.
- `test_infinite_memory_contract.py` covers exports, enum values, the prompt family, the runtime registry and refusal, the session opt-out, settings validation and defaults, the exact tools and schemas offered, `TokenEstimate`, prompt text, and the complexity budget.
- `test_infinite_memory_delegation.py` covers `launch_subagent`: concurrency, card order and caps, batch validation, depth and role tools, `max_agents`, failure isolation (including a card or journal record that cannot be written as given), partial generators, extras by name, context, replay (including a superseded context entry), the verifier's input, and the tool-limit exemption.
- `test_infinite_memory_verification.py` covers verdict parsing, `unchecked` handling, `drop_entry`, the entry rules at stage time, the `by` stamp on a verifier's entry, and the commit re-check against a corrupted `entries.jsonl`.
- `test_infinite_memory_workspace.py` covers `remember` and its EC-18 advice, supersede, `write_note`, `edit_file` and its caps, the caps including a bash bypass, writes the disk refuses, large bookkeeping files, grep, and the workspace map.
- `test_infinite_memory_resume.py` covers journal order and fsync, `resume` replay and refusals, torn and malformed journals, cancellation, the reserved-name check, and key secrecy.
- `test_infinite_memory_context.py` covers history trimming and a clean context for each run.
- `infinite_events_fixtures.py` provides the events tests' shared helpers: the spec's cut rule stated independently, stream readers, the portability and size check every collected event must pass, the AC-2 one-pair script, and run views that compare two runs once run ids, stamps, and tmp paths are replaced.
- `test_infinite_memory_events_stream.py` covers the live stream as a caller sees it: the events spec's section 4 snippet, the exact kinds and details of a one-pair run, the root's `memory_saved`, durable-before-announced delivery, raising and coroutine-returning sinks, no sink, token totals, quiet tools, `infinite_run_id`, and refused runs.
- `test_infinite_memory_events_lifecycle.py` covers how the stream ends when a run does not finish: cancellation and its resume, a runner error, a `KeyboardInterrupt`, and the handoff of a cancelled run.
- `test_infinite_memory_events_pairs.py` covers launch, pair, memory, and note events: `batch_rejected`, replay order, structured drops, `file_written`, `tool_refused`, caps and omitted counts, nesting, a failing generator, path spellings, a lone surrogate, and middleware denials.
- `test_infinite_memory_events_records.py` covers the event vocabulary and records directly: exports, the `on_event` check, the worst-case size of every details record, every cap and one-line rule, the envelope checks, costs, key shortening, usage reading, and clamped limits.
- `test_infinite_memory_handoff.py` covers `run_handoff`: the nine sections and the byte-exact file, old journals, refused run ids, the section and line caps, hand-edited journals, which entries and cards each section lists, and a note replaced by a symlink loop.

## Run

From the repository root: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`. One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_resume.py -q`. The bash cases need a POSIX bash, or Git for Windows bash on Windows hosts.

## Logs

- 2026-10-15 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
- 2026-10-15 - S4 review additions (S2 test author, spec r5): guardrail tests for stage-time entry rules, the verifier's `by` stamp, and `edit_file`'s caps; regression tests for findings R-1, R-3, R-4, R-6 and R-8.
- 2026-10-15 - S5 re-review additions (S2 test author, spec r5): regression tests for findings R-26 (a read-only seed on a second attach) and R-27 (refused two-file memory writes, and an unwritable staged entry in a pair).
- 2026-10-16 - Events and handoff tests added red, ahead of the implementation, from `docs/spec/infinite-memory-events/spec.md` r3 (S2 test author); the complexity-budget test now allows the events and handoff modules (spec section 12.3 row 22).
