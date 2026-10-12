# Coding agent feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.CodingAgent` and `vidbyte.tools.builtins.BashTool`. One constructor call gives a model working file, search, shell and web-fetch tools over one root folder. Every shell call returns in bounded time with bounded output. A fetch key reaches only its own provider. The root folder's `AGENTS.md`, then its `MAP.md`, reach the model right after the system prompt, and setup commands run once at construction with a pass/fail note for the model. The tests drive the real `BaseAgent` tool loop, real file tools, real bash processes and the real provider clients. Only the model runner and the single provider HTTP send are faked.

The implementations belong in `vidbyte/agents/coding.py`, `vidbyte/lib/dataclasses/coding.py` (the argument checks), `vidbyte/tools/toolsets/coding.py` (the seven tools and the keyed fetch view), `vidbyte/tools/builtins/bash.py`, `vidbyte/cli/coding.py` (the terminal command), and `vidbyte/agents/coding_context/` (the `AGENTS.md` and `MAP.md` loaders with their shared `RootFileLoader`, the setup-command loader, and the coding context window, with its order in `vidbyte/lib/enums/coding.py` and its cap in `vidbyte/lib/constants/coding.py`). The file tools these tests compose belong in `vidbyte/tools/filesystem/`, the search and fetch tools in `vidbyte/tools/builtins/`, and the permission check belongs in `vidbyte/agents/runtime.py`.

## Non-Goals

- Do not test the file, search or fetch tools' own behaviour here. Their existing test modules under `tests/` own it.
- Do not add sandboxing, allow-lists or configurable bash limits. The spec defers them (Q-2 to Q-6).
- Do not make live provider calls or use real keys. `conftest.py` fakes `HttpTransport._send_once`.
- Do not test `fork` isolation or non-linear runtimes. `tests/test_agent_fork_isolation.py` and the runtime tests own them. Only the `AGENTS.md` section surviving `fork()` is tested here, because it is this feature's promise.

## File Index

- `README.md` explains the boundary of the pack and routes changes to their owners.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py` imports the feature lazily (`coding_agent_cls`, `bash_module`). It also provides an offline scripted model that makes one tool call per turn (`script_model`) and a recording fake for the provider HTTP send (`fake_provider_http`).
- `test_coding_agent_acceptance.py` checks the end-to-end runs through the agent loop. Start here for a caller-visible regression.
- `test_coding_agent_contract.py` checks the constructor contract: public names, the subclass surface, export and restore parity, caller tools, identity errors, and root validation and pinning.
- `test_coding_agent_web_fetch.py` checks fetch-key selection, authentication, confinement and secrecy, and the keyed fetch view against the bare priced tool.
- `test_coding_agent_agents_md.py` checks the loading of the root folder's AGENTS.md file end to end on the request the model receives, and `CodingContextWindow`, the shared helper later sections build on. Start here when the model does not see the repository's rules.
- `test_coding_agent_map_md.py` checks the loading of the root folder's MAP.md file into the repository-map section, after the AGENTS.md section. Start here when the model does not see the repository map.
- `test_coding_agent_setup_commands.py` checks the setup commands end to end on the request the model receives: order, stop at the first failure, the time limit, the working directory, no bash, the empty default, validation, and the capped output tail. Start here when setup ran wrong or its note is missing.
- `test_coding_agent_progress_notes.py` checks the agent's own progress notes file: created when missing and never overwritten, hidden from git without hiding other tools' files, shown last, carried from one run to the next, and skipped on a root that cannot be written. Start here when a run does not see the last run's notes.
- `test_coding_agent_cli.py` checks `vidbyte-sdk coding run`: one task through the real loop, a fetch key read only from the named environment variable, and clean failures for an unset variable or a bad folder.
- `test_bash_tool_contract.py` checks `BashTool`'s input and output contract: the spec, validation, streams, `cwd`, argv, stdin, spawn errors, decoding, the output cap, and the bash lookup.
- `test_bash_tool_process_bounds.py` checks the time limit, process-group kill, cancellation and pipe cleanup on real processes. Start here for a hang or a leftover process.

## Logs

- 2026-10-10 - The pack was written red before implementation from spec r3 - every test fails at import until `vidbyte/agents/coding.py` and `vidbyte/tools/builtins/bash.py` exist.
- 2026-10-11 - `AGENTS.md` loading and the shared coding context window were added (`test_coding_agent_agents_md.py`); `test_coding_agent_contract.py`'s `EXPECTED_SIGNATURE` gained `load_agents` and `context_manager`.
- 2026-10-11 - `MAP.md` loading was added (`test_coding_agent_map_md.py`); `EXPECTED_SIGNATURE` gained `load_map`.
- 2026-10-11 - Setup commands were added (`test_coding_agent_setup_commands.py`); `EXPECTED_SIGNATURE` gained `setup_commands`.
- 2026-10-11 - Progress notes were added (`test_coding_agent_progress_notes.py`); `EXPECTED_SIGNATURE` gained `progress_notes`, and the tests that assert an exact request, an empty root, or export parity with `BaseAgent` pass `progress_notes=False`.
