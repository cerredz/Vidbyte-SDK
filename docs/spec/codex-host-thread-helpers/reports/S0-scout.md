# S0 scout report: codex-host-thread-helpers

- **Stage:** S0 scout.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-thread-helpers`, HEAD `c181be65`.
- **Output:** `docs/spec/codex-host-thread-helpers/context/code-map.md`. It has 4 `## ` sections, and §4 holds the subsections 4.0 and 4.a–4.f.
- **Commits:** none.
- **What I did not do:** no installs, no gate runs, no state-changing git, and no `codex` run of any kind. I also did not regenerate the schema, because the provided copy had every file I needed.

## 1. Planned list (the area guess, then the additions I made while reading)

**From the orchestrator's guess:**
- **Host package:**
  - `vidbyte/harnesses/native/codex/`: `host.py`, `turns.py`, `wire.py`, `connection.py`, `errors.py`, `oneshot.py`, `preflight.py` and `__init__.py`.
- **Tool layer:**
  - `vidbyte/tools/builtins/codex/` (all files).
  - `vidbyte/tools/toolsets/codex.py`.
  - `vidbyte/tools/builtins/__init__.py` and `vidbyte/tools/toolsets/__init__.py`.
- **Lib layer:**
  - `vidbyte/lib/constants/codex.py`.
  - `vidbyte/lib/enums/codex.py`, `vidbyte/lib/enums/__init__.py` and `vidbyte/lib/enums/failure.py`.
  - `vidbyte/lib/errors/base.py`.
  - `vidbyte/lib/dataclasses/codex_host.py`.
- **Documentation and contracts:**
  - `vidbyte/harnesses/README.md` and `REPO_MAP.md`.
  - `contracts/sdk-public-api.json`.
- **Tests:**
  - `tests/features/codex_host/` (all files).
  - `tests/features/harness_threads/` (patterns and exclusions).
- **Outside the repo:**
  - `openai_codex` in the venv.
  - The schema copy.
  - `C:/Users/422mi/.codex/skills/.system/`.

**Added while reading** (each was found by following a reference from a listed file):
- **`vidbyte/lib/dataclasses/codex.py`** (1,205 lines). `CodexSkillInput` and `CodexRunInput` live here, and spec NG-12 forbids editing the file.
- **`vidbyte/lib/enums/native_threads.py` and `vidbyte/lib/dataclasses/native_threads.py`.** These hold #1036's `NativeHarness` and `NativeThreadResult`. The `NativeHarness` members are pinned.
- **`vidbyte/harnesses/native/__init__.py` and `vidbyte/harnesses/native/grok/threads.py`.** The `__init__` is SHA-pinned; `grok/threads.py` is #1036's function pattern.
- **`tests/test_codex_failure_recovery.py:190-203`.** Every `codex.*` code needs a classification row.
- **The field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`.** I read `init.md`, `comment-format.md`, `model-facing-tool-contracts.md`, `provider-api-contracts.md`, `blocking-lint-invariants.md` (headings and the relevant entries), `local-ci-verification.md` (headings and the relevant entries), `class-bound-helpers.md` (headings and Check lines) and `strict-config-dataclasses.md` (headings and Check lines).
- **`lint/core/report.py:58`,** to settle the wording of the lint pass line.
- **The installed CLI's version,** from `C:/Users/422mi/AppData/Roaming/npm/node_modules/@openai/codex/package.json`.

## 2. Files actually read

**Read in full:**
- **Repo rules and request:**
  - `AGENTS.md` and `CLAUDE.md`.
  - `docs/spec/codex-host-thread-helpers/request.md` and `reports/S0-merge-main.md`.
- **Host package:**
  - `vidbyte/harnesses/native/codex/`: `host.py`, `preflight.py`, `__init__.py`, `oneshot.py`, `connection.py`, `errors.py`, `wire.py` and `turns.py`.
- **Lib layer:**
  - `vidbyte/lib/constants/codex.py`, `vidbyte/lib/enums/codex.py` and `vidbyte/lib/dataclasses/codex_host.py`.
- **Tool layer:**
  - `vidbyte/tools/builtins/codex/`: `__init__`, `_base`, `threads`, `descriptions`, `readiness`, `live` and `delegation`.
  - `vidbyte/tools/toolsets/codex.py`.
- **Tests:**
  - `tests/features/codex_host/`: `codex_host_fakes.py`, `codex_host_support.py`, `test_codex_host_packaging.py`, `test_codex_host_tools.py`, `test_codex_host_sdk_contract.py`, `README.md` and `FEATURE.md`.
  - `tests/features/harness_threads/test_harness_threads_static_policy.py`.
- **Bundled system skills** (all five `SKILL.md` files):
  - `C:/Users/422mi/.codex/skills/.system/{imagegen,openai-docs,review-agent,skill-creator,skill-installer}/SKILL.md`.
  - Each skill's `agents/openai.yaml`.
- **SDK:** `openai_codex/errors.py`.

**Read in part** (the sections that bear on this change):
- **Codex-host spec:**
  - `docs/spec/codex-host/spec.md`: §0–§4, §8 (all of §8.1–8.5), §12.1–12.3 and §13. I skimmed the outline of the rest.
  - `docs/spec/codex-host/request.md`: the ★ scope notes and the function checklist rows for Threads, Goals and Skills.
  - `docs/spec/codex-host/pr-body.md`: Compatibility, Verification and Follow-ups.
- **Lib layer:**
  - `vidbyte/lib/enums/failure.py`: the codex block and the code order.
  - `vidbyte/lib/enums/__init__.py`: the Codex entries.
  - `vidbyte/lib/dataclasses/codex.py`: the input records at 440-520 and the helpers at 55-78.
  - `vidbyte/lib/errors/base.py`: `NativeThreadError` at 550-600.
- **#1036 code:**
  - `vidbyte/lib/dataclasses/native_threads.py:200-228`.
  - `vidbyte/lib/enums/native_threads.py`: the class and member lines.
  - `vidbyte/harnesses/native/grok/threads.py:1-60`.
  - `vidbyte/harnesses/native/__init__.py`.
- **Tool layer:** `vidbyte/tools/builtins/__init__.py`, the Codex lines only.
- **Docs and contracts:**
  - `REPO_MAP.md:159-163` and `vidbyte/harnesses/README.md:176-182`.
  - `contracts/sdk-public-api.json`, the header and a Codex grep.
- **Tests:**
  - `test_codex_host_records.py`: the enum table, the constants and the AC-29 checks.
  - `test_codex_host_lifecycle.py`: the test list, the closed-host test and the module-function test.
  - `test_codex_host_threads.py`: the list test, plus the continue, fork and read tests via the earlier session.
  - `test_codex_host_review_goals.py`: the goal request order.
  - `tests/features/harness_threads/test_harness_threads_surface.py`: 20-60 and 170-240.
- **SDK:**
  - `openai_codex/client.py`: the typed methods 465-760.
  - `openai_codex/api.py`: method names only.
  - `openai_codex/_inputs.py:32-37`.
  - `openai_codex/generated/v2_all.py`: every class named in code-map §4.a and §4.d.
- **Schema copy** (`<schema>/v2/*.json` and `ClientRequest.json`):
  - `ThreadCompactStart*`, `ThreadDelete*`, `ThreadGoalGet*`, `SkillsListParams` and `ThreadTurnsListParams`.
  - The Skill `UserInput` variant inside `TurnStartParams.json`.
  - The method list in `ClientRequest.json`.

**Not opened** (by rule or because nothing referred to it):
- **Under `docs/`:** every file except the five allowed.
- **Forbidden locations:** the sibling worktree and the main checkout.
- **Remaining `codex_host` test modules:**
  - `test_codex_host_turns.py`, `test_codex_host_failures.py`, `test_codex_host_review_gaps.py`, `test_codex_host_router.py` and `test_codex_host_bridge.py`.
  - I know them only from FEATURE.md and README.md descriptions, and they hold no pins on counts or names (git grep).
- **Elsewhere in the repo:**
  - `vidbyte/agents/codex/result.py`.
  - The other #1036 modules (opencode, muse, hostkit).

## 3. What the area guess or the workspace-facts file got wrong

**The area guess:**
- **Missed `vidbyte/lib/dataclasses/codex.py`.** It holds `CodexSkillInput(name, path)` and `CodexRunInput`, which a skill-turn helper builds on. The file is 1,205 lines, and spec D-26/NG-12 forbid editing it, so the guess should have listed it as read-only.
- **Listed `vidbyte/lib/errors/base.py` as touched.** Nothing in the request needs a new error class (all codex failures are `CodexAgentError`), and adding one triggers A003. It is most likely untouched.
- **Listed `REPO_MAP.md`, `vidbyte/harnesses/README.md` and `contracts/sdk-public-api.json` as likely touched.**
  - The two texts are byte-pinned, and they already describe the host generically, so no edit is needed.
  - The public-API contract holds no CodexHost name, and spec D-25 forbids root exports.
- **Listed `vidbyte/tools/toolsets/__init__.py`.** It needs no change unless a new toolset is added; its `__all__` is pinned.
- **Treated `tests/features/harness_threads/` as pattern-only.** It holds three binding constraints for this change:
  - the static-policy skip only covers `native/codex/`;
  - INV-21 allows only four `vidbyte/tools` paths;
  - the FailureCode tail must stay #1036's 28 codes.
- **Missed `vidbyte/lib/enums/native_threads.py`.** `NativeHarness` has no CODEX member and its members are pinned, which bears on cross-harness summary parity.
- **Missed `tests/test_codex_failure_recovery.py`.** It requires a classification row for every `codex.*` code.

**The workspace-facts file (`vidbyte-gates.md`):**
- **Line 28 says "Final line must read `AGENT-LINT: PASS`".** This repo prints `SDK-LINT: PASS` (`lint/core/report.py:58`); the AGENT-LINT wording belongs to the `vidbyte/` repo.
- **Line 19's install, `python -m pip install -e ".[dev]"`, must not be used in this worktree.** request.md §C forbids `pip install -e` into the global Python, and the isolated venv already has `.[dev,codex]`.
- **The `.[dev]` install does not run this feature's host tests.** They need the `codex` extra and skip without it; this is also why CI skips them, since CI installs only `.[dev]`.

**The request** (recorded in code-map §4.0):
- **Bundled skills:** the request expects four; the disk has five (`review-agent` too).
- **Spawn goal path:** it never reads the goal back with `thread/goal/get`.
- **`read_codex_thread(include_turns=True)`:** it returns summaries without items, not a full transcript.
- **`list_codex_threads`:** it has no `limit`. Its `search` filters titles only.
- **Default source filter:** by default `thread/list` lists only interactive sources.
- **`SkillUserInput`:** it needs a `path` as well as a name.
- **Delete without a tool:** a delete operation with no tool breaks `test_codex_host_records.py:61`'s derivation of `CodexHostOperation` from `TOOL_NAMES`.
