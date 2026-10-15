# InfiniteMemory agent

## Folder Description / Intent

This folder holds the feature tests for `InfiniteMemoryAgent`: a root agent that hands work to generator→verifier pairs of fresh subagents through `launch_subagent`, keeps memory in one guarded workspace folder, and resumes a crashed or cancelled run from its journal. The tests are offline. The only fake is the model runner, patched at `BaseAgent._runner_for_model` so it reaches every agent in the tree. The workspace, the journal, `ParallelPipeline`, the prompt catalog, the filesystem, and `bash` all run for real under `tmp_path`. The behavior itself lives in `vidbyte/agents/infinite/`, with its records, enums, and constants in `vidbyte/lib/`, not here. The contract comes from `docs/spec/infinite-memory-agent/spec.md`.

The pack was written before the implementation, so until the feature lands every test here fails on a missing import or name, and the rest of the suite still collects and passes.

## File Index

- `README.md` describes the scope and how to run the pack.
- `FEATURE.md` defines the contract, the invariants, the known failure modes with the test that catches each, and the strategies left out on purpose.
- `infinite_memory_fixtures.py` provides the scripted model tree routed by agent name, the Gate and Signal used to order concurrent agents without sleeps, settings and agent builders, and readers for the workspace files, the journal, and prompt templates.
- `test_infinite_memory_acceptance.py` runs the spec's section 4 snippet as written, staging then commit, the usage roll-up, and a second agent on the same workspace.
- `test_infinite_memory_contract.py` covers exports, enum values, the prompt family, the runtime registry and refusal, the session opt-out, settings validation and defaults, the exact tools and schemas offered, `TokenEstimate`, prompt text, and the complexity budget.
- `test_infinite_memory_delegation.py` covers `launch_subagent`: concurrency, card order and caps, batch validation, depth and role tools, `max_agents`, failure isolation, partial generators, extras by name, context, replay, the verifier's input, and the tool-limit exemption.
- `test_infinite_memory_verification.py` covers verdict parsing, `unchecked` handling, `drop_entry`, and the commit re-check against a corrupted `entries.jsonl`.
- `test_infinite_memory_workspace.py` covers `remember`, supersede, `write_note`, `edit_file`, the caps including a bash bypass, large bookkeeping files, grep, and the workspace map.
- `test_infinite_memory_resume.py` covers journal order and fsync, `resume` replay and refusals, torn and malformed journals, cancellation, the reserved-name check, and key secrecy.
- `test_infinite_memory_context.py` covers history trimming and a clean context for each run.

## Run

From the repository root: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`. One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_resume.py -q`. The bash cases need a POSIX bash, or Git for Windows bash on Windows hosts.

## Logs

- 2026-10-15 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
