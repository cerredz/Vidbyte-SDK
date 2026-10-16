# S0 scout report — harness-thread-functions

- Stage: S0 scout (code side). Date: 2026-10-15.
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-functions`, branch `feat/native-grok-opencode-meta-hosts`, HEAD `1c0d264b` (merge of origin/main `179d8adc` into PR head `c1fdaef9`). No commits made.
- Output: `docs/spec/harness-thread-functions/context/code-map.md` (§1 rules/commands/lint/field guide, §2 files, §3 tests, §4 notes).

## Planned list (before reading)

1. Rulebook: `AGENTS.md`; `REPO_MAP.md` entries for the touched folders; the folder READMEs the PR edits; the request file; the workspace-facts file `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`; field guide `init.md` plus the ten entries the request names; `lint/README.md`.
2. Every non-doc file PR #1036 adds or changes, from `git diff --name-status origin/main..HEAD -- . ':!docs'`: 63 `.py` files under `vidbyte/` (native hosts, hostkit, backends, lib process/dataclasses/enums/constants/configs/errors, tools builtins/toolsets, transport), 5 Markdown files (`REPO_MAP.md` and four folder READMEs), 49 test-pack files.
3. Neighbours on origin/main that show the patterns the request asks about (caller-supplied keys, skills, enums for wire values, constants modules, module-level async functions, the Codex harness adapter).

## Files actually read

In full:
- `AGENTS.md`; `docs/spec/harness-thread-functions/request.md`; the workspace-facts file; `vidbyte/harnesses/README.md`, `vidbyte/lib/README.md`, `vidbyte/tools/README.md`, `vidbyte/tools/mcp/README.md`; `lint/README.md`.
- Field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): `init.md`, `review-scope.md`, `cli-backed-source-integrations.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `comment-format.md`, `provider-api-contracts.md`, `blocking-lint-invariants.md`, `prebuilt-agents.md`, `local-ci-verification.md`, and `model-facing-tool-contracts.md` (not in the request's list; the PR's tool files follow it).
- Every PR file under `vidbyte/harnesses/native/**`, `vidbyte/lib/process/**`, the PR's `vidbyte/lib/{constants,configs,dataclasses,enums,errors}` files and edits, `vidbyte/tools/builtins/{grok,opencode,muse,harness_backends}/**`, `vidbyte/tools/builtins/native_host_tool.py`, `vidbyte/tools/toolsets/{grok,opencode,muse,harness_backends,__init__}.py`, and the `vidbyte/tools/mcp/transport.py` diff.
- Test packs: the four `FEATURE.md`, the four `README.md`, the four `conftest.py`, and the three fakes (`fake_grok_peer.py`, `fake_opencode_serve.py`, `fake_muse_peer.py`).
- origin/main neighbours (via `git show origin/main:<path>`): `vidbyte/lib/constants/codex.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/dataclasses/coding.py`, `vidbyte/lib/util/credential_keys.py`, `vidbyte/harnesses/serialization.py` (HarnessRedactor), `vidbyte/agents/skills/README.md`, the `vidbyte/skills/` catalog, `vidbyte/tools/mcp/attach.py`, the Codex agent and settings files.

Partly (by range or grep):
- `REPO_MAP.md`: the PR's diff and the two entries it adds; the rest was not read (unverified).
- The other 38 test files: every `def test_` name and every `vidbyte` import by grep, plus these ranges: grok acceptance 1–184, reads 155–283, turns 430–478, tools 25–105, shared_contract 1–200 and 420–518; opencode owned_server 40–80 and 170–210; muse wsl 150–195, wire 155–182; backends profiles 100–182, security 100–125.
- `scripts/run_ci.py` (head, 79–112, the argument parser near 260); `pyproject.toml` pytest config; the heads of lint rules a001, a002, a007, c008; `.github/workflows/static-policy.yml` (grep for semgrep).

Not read:
- `docs/spec/native-grok-opencode-meta-hosts/**` (AGENTS.md treats `docs/` as opaque; the vendor scout covers it). Counted only, by `git diff --name-only`: 26 files.
- `CONTRIBUTING.md`: its `## Pull Requests` heading (line 75) was found by grep only.
- The source of lint rule S054 (so whether it flags relocated `*KEY*` constants is listed as unverified in §4).

## What the likely-areas guess or the workspace-facts file got wrong

- The likely-areas list left out `vidbyte/lib/configs/__init__.py`. The PR modifies it (+2 lines, re-exporting `HARNESS_BACKENDS`). Every other entry matched the diff, and the "49 files" test count is right (16 grok, 11 opencode, 13 muse, 9 backends).
- The likely-areas list left out the transport tests on main, `tests/test_mcp_stdio_transport.py` and `tests/test_mcp_studio_server.py`. They cover `vidbyte/tools/mcp/transport.py`, and the PR does not change them. It also named no origin/main neighbours, although the request's open questions (keys, skills, enums for wire values, async vs sync) can only be answered from them.
- The workspace-facts file's SDK row says "CI runs the same `run_ci.py`; semgrep is part of it". That is wrong for this checkout. `scripts/run_ci.py` contains no `semgrep`, and Semgrep runs in `.github/workflows/static-policy.yml:24–30`.
- The workspace-facts file's SDK gate sequence (`python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py`) has no `PYTHONPATH`. From a worktree, the field guide's `local-ci-verification.md` requires `PYTHONPATH=$(pwd)` for the source stage and none for the package stage, because the global `python` imports the canonical checkout.
- The workspace-facts file's worktree convention is "branch `feat/<slug>`". This worktree is on `feat/native-grok-opencode-meta-hosts`, which is intended (KD-6, PR updated in place) and not an error.
- The request (not a workspace file) gives a few line ranges that are slightly off. The `grok/cli.py` constants are at 26–36, not 32–42, and the `grok/host.py` constants are at 57–64, not 55–64. Both comment anchors match. The request also says AGENTS.md puts constants in `vidbyte/lib/constants/<domain>.py`, but AGENTS.md states that only for JEV. These are recorded in code-map §4.1 items 1 and 8.

## Process notes

- Rule breach: I ran Python once by accident. Inside a `sed` pipeline I called `python -` with stdin from `/dev/null`. The program was empty: it imported nothing and wrote nothing, and its output was not used. No other interpreter, test, lint, gate, install or commit was run.
- The only files written are `context/code-map.md` and this report. `docs/spec/harness-thread-functions/` is untracked (`git status`: `?? docs/spec/harness-thread-functions/`). `__pycache__` folders under `vidbyte/harnesses/native/` already existed and are git-ignored; the empty `python -` run imports no vidbyte module, so it did not create them.
