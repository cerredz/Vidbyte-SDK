# S0 scout report: codex-host-hardening

- **Stage:** S0 scout. **Branch/HEAD:** `feat/codex-host-first-class` at `6f5a7310` (= merge-base with `origin/main`). **Commits made:** none. **Files created:** `context/code-map.md` and this report; nothing else changed (`git status --short` shows only `?? docs/spec/codex-host-hardening/`). No installs, no gate runs, no state-changing git commands. Every Python probe ran with `PYTHONDONTWRITEBYTECODE=1`.
- **Output:** `docs/spec/codex-host-hardening/context/code-map.md`, with exactly four numbered `## ` sections: rules, files, tests, notes.

## Planned file list (what the slice will touch)

**Production:**
- `vidbyte/harnesses/native/codex/`: `host.py`, `connection.py`, `errors.py`, `preflight.py`, `turns.py`, `wire.py`, `thread_helpers.py`, `skill_functions.py`, `oneshot.py`, plus `__init__.py` only if a new public name is exported.
- `vidbyte/lib/`: `dataclasses/codex_host.py`, `dataclasses/codex.py`, `enums/codex.py`, `enums/__init__.py`, `enums/failure.py`, `constants/codex.py`, `errors/base.py`.
- `vidbyte/tools/builtins/codex/`: `_base.py`, `threads.py`, `descriptions.py`, plus `toolsets/codex.py` and the builtins `__init__.py` only if a tool is added.
- `vidbyte/agents/codex/config.py`, shared with `CodexHarnessAgent`.
- `pyproject.toml`.

**Pattern references (read-only):**
- `vidbyte/agents/codex/tools.py`;
- `vidbyte/lib/tracing/base.py`, `vidbyte/trace/{base,controller,debug}.py`, `vidbyte/agents/runtime.py:1279-1288`;
- `vidbyte/agents/codex/{agent,middleware}.py`;
- `vidbyte/lib/jev/managed.py`, the logger precedent.

**Tests:**
- `tests/features/codex_host/`: the pinned modules listed in code-map §3, plus `README.md`, `FEATURE.md` and the three helper modules.
- `tests/test_codex_*.py` must keep passing (NG-5).

## Files actually read

**Read in full:**
- `AGENTS.md`, `lint/README.md`, `pyproject.toml`;
- `vidbyte/harnesses/native/codex/`: `host.py`, `connection.py`, `errors.py`, `preflight.py`, `turns.py`, `wire.py`, `thread_helpers.py`, `skill_functions.py`, `oneshot.py`;
- `vidbyte/tools/builtins/codex/_base.py`, `vidbyte/agents/codex/tools.py`;
- `vidbyte/lib/tracing/base.py`, `vidbyte/trace/base.py`;
- in `tests/features/codex_host/`: `README.md`, `FEATURE.md`, `codex_host_support.py`, `codex_host_fakes.py`, `codex_host_helper_fakes.py`, `test_codex_host_router.py`, `test_codex_host_sdk_contract.py`;
- the field-guide pages quoted in code-map §1;
- `docs/spec/codex-host-hardening/request.md` and `context/codex-gap-report.md` (sections §0, §1, the server-request table, §5, §6, §8–§12).

**Read by targeted ranges, an index or grep:**
- In `vidbyte/lib/`:
  - `dataclasses/codex.py` (1,205 lines) and `dataclasses/codex_host.py`;
  - `enums/codex.py`, `enums/failure.py`, `enums/__init__.py`;
  - `constants/codex.py`;
  - `errors/base.py` (`CodexAgentError`).
- Elsewhere in `vidbyte/`:
  - `tools/builtins/codex/threads.py`, `descriptions.py`;
  - `agents/codex/config.py`, `agent.py`, `middleware.py`;
  - `trace/controller.py`, `trace/debug.py`;
  - `agents/multi/tracing.py`, `sessions/trace_capture.py`, `agents/runtime.py` (span site), `lib/jev/managed.py`.
- READMEs: `vidbyte/harnesses/README.md`, `vidbyte/agents/codex/README.md`, `vidbyte/lib/README.md`, `vidbyte/tools/README.md`, `vidbyte/trace/README.md` (checked for `## Notes for agents`; none has one).
- The other 15 `test_codex_host_*.py` modules (test-name index plus the pinned ranges).
- In `tests/features/harness_threads/`: `test_harness_threads_surface.py` and `test_harness_threads_static_policy.py`.
- `scripts/run_ci.py`, `.github/workflows/ci.yml`, `lint/rules/s012_explicit_outbound_timeout.py`.
- `docs/spec/codex-host-hardening/context/coverage-matrix.md` (header plus grep).
- In `docs/spec/codex-host/spec.md`, only the grepped ID ranges: INV-9, -10, -11, -15, -16, -23, -27, -28, -36, -37; NG-13; EC-65; D-2, -13, -16, -18, -27.
- In `docs/spec/codex-host-thread-helpers/spec.md`, only INV-16, INV-18 and D-13.
- Nothing else under `docs/` was opened.

**External sources:**
- Installed `openai_codex` 0.162.1: `client.py` (typed methods, retry, `_reader_loop`, version gate), `errors.py`, `retry.py`, and `generated/v2_all.py` (`ReasoningEffort`, `TurnStartParams`, `ThreadForkParams`, sandbox policies).
- JSON schemas generated into the scratchpad with `--experimental` from the bundled 0.162.1 binary and from the PATH 0.163.0 binary, then diffed.
- `codex --version` of both binaries.

**Reproductions (read-only, in-process):**
- **X1:** `thread_id` is dropped.
- **X5:** busy, internal and invalid-request errors all map to `codex.session_not_found`.
- **X6/S5:** the router's answers, `accept` or `{}`.
- **X8:** a `RuntimeError` escapes `_run`.
- **X4:** there is no `retryable` attribute.
- **S1:** the `REJECTED_FIELDS` keys.
- **S2:** the effort list.
- **Pre-existing test failure:** `FailureCode` has 167 members (counted with `ast`) against the harness_threads assertion of 120.

**Self-check after writing:** about 40 line citations in the code map were re-grepped. Four were corrected before finishing:
- router pin: :60-65;
- records `details` test: :488;
- helper_tools 26-tool pin: :133;
- `run_ci.py` `run_source`: :79-93.

## What the likely-areas list (request implementation hints) got wrong or missed

- **Missing `vidbyte/agents/codex/config.py`.** It maps effort, service tier and sandbox for every turn (`config.py:196,201,247`) and is shared with `CodexHarnessAgent`, so S2/S3/S8 reach the harness agent too.
- **Missing these files:**
  - `vidbyte/lib/enums/failure.py` (a new code has exactly one legal slot, after `CODEX_GOAL_UNFINISHED`, which two tests pin);
  - `vidbyte/lib/enums/__init__.py` (the `Codex*` export order is pinned);
  - `vidbyte/lib/errors/base.py` (X1/X4 fields; A003);
  - `pyproject.toml` plus `CodexClientSettings.client_version` plus the fake's `FAKE_VERSION` for S10;
  - the pack's `README.md`/`FEATURE.md` (NG-13 and "live runs are manual QA", which X9 overturns).
- **Missing a design constraint.** `vidbyte/lib/dataclasses/codex.py` is already 1,205 lines and `host.py` is 893, so AGENTS.md principle 3 forces new logic into collaborators or new modules.
- **X9 says "All 20 test files use the fake app-server".** There are 17 test modules plus 3 helpers, and only 10 modules drive the fake.
- **X5 and X7 are framed as defects.** Both are written into the shipped spec as accepted behaviour (D-13 / thread-helpers INV-16; EC-65) and pinned by tests, so the spec must supersede those IDs explicitly.
- **D-16's premise that there is "no decline decision" is false** for both binaries. The pinned `CODEX_HOST_USER_REVIEWER_TEXT` names `set_codex_approval_handler`.
- **S7.** `review/start` has no model, effort or tier parameters in either schema.
- **X4 omits a constraint.** S012's baseline of 0 forbids calling `client.request` (spec D-2), so the fix must reuse the SDK's `retry_on_overload` or `request_with_retry_on_overload`. Whether `thread/start` and `thread/resume` are safe to retry is unverified.

## What `vidbyte-gates.md` got wrong

- **No `PYTHONPATH` on the source stage.** Verified: outside the worktree, `import vidbyte` resolves to the main checkout's editable install, and `test_codex_host_packaging.py` starts fresh interpreters. Per the field guide, the source stage is `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.
- **`PYTHONPATH` must not reach the package stage.** It runs `python scripts/run_ci.py` for all stages without unsetting `PYTHONPATH`, which the field guide says breaks the package stage.
- **It implies CI covers the host.** `.[dev]` excludes the `codex` extra, and CI triggers are manual only, so every `requires_sdk` class skips there. They run only locally, where openai-codex 0.162.1 is installed.
- **It omits the pre-existing local failures:**
  - `test_harness_threads_surface.py:193` (120 vs 167 `FailureCode` members);
  - `:224-232`, which fails for any `vidbyte/tools` change outside the codex-scoped excludes.
- **It omits Semgrep's tracked-files caveat.** `git add` is needed before a clean scan means anything; that step belongs to the implementer, not the scout.
