# Coding agent feature tests

## Folder Description / Intent

This folder checks the public promise of `vidbyte.CodingAgent` and `vidbyte.tools.builtins.BashTool`. One constructor call gives a model working file, search, shell and web-fetch tools over one root folder. Every shell call returns in bounded time with bounded output. A fetch key reaches only its own provider. The tests drive the real `BaseAgent` tool loop, real file tools, real bash processes and the real provider clients. Only the model runner and the single provider HTTP send are faked.

The implementations belong in `vidbyte/agents/coding.py` and `vidbyte/tools/builtins/bash.py`. The file, search and fetch tools these tests compose belong in `vidbyte/tools/builtins/`, and the permission check belongs in `vidbyte/agents/runtime.py`.

## Non-Goals

- Do not test the file, search or fetch tools' own behaviour here. Their existing test modules under `tests/` own it.
- Do not add sandboxing, allow-lists or configurable bash limits. The spec defers them (Q-2 to Q-6).
- Do not make live provider calls or use real keys. `conftest.py` fakes `HttpTransport._send_once`.
- Do not test `fork` or non-linear runtimes. `tests/test_agent_fork_isolation.py` and the runtime tests own them.

## File Index

- `README.md` explains the boundary of the pack and routes changes to their owners.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `conftest.py` imports the feature lazily (`coding_agent_cls`, `bash_module`). It also provides an offline scripted model that makes one tool call per turn (`script_model`) and a recording fake for the provider HTTP send (`fake_provider_http`).
- `test_coding_agent_acceptance.py` checks the end-to-end runs through the agent loop. Start here for a caller-visible regression.
- `test_coding_agent_contract.py` checks the constructor contract: public names, the subclass surface, export and restore parity, caller tools, identity errors, and root validation and pinning.
- `test_coding_agent_web_fetch.py` checks fetch-key selection, authentication, confinement and secrecy, and the keyed fetch view against the bare priced tool.
- `test_bash_tool_contract.py` checks `BashTool`'s input and output contract: the spec, validation, streams, `cwd`, argv, stdin, spawn errors, decoding, the output cap, and the bash lookup.
- `test_bash_tool_process_bounds.py` checks the time limit, process-group kill, cancellation and pipe cleanup on real processes. Start here for a hang or a leftover process.

## Logs

- 2026-10-10 - The pack was written red before implementation from spec r3 - every test fails at import until `vidbyte/agents/coding.py` and `vidbyte/tools/builtins/bash.py` exist.
