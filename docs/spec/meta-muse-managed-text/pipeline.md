---
slug: meta-muse-managed-text
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text
branch: feat/meta-muse-managed-text
base_commit: 845a4d9bd5f144b1e083b5dc3c76bff17c75b235
pr: none yet
until: none
started: 2026-10-16 18:25
---

# Pipeline: Let the SDK's gateway text modes (AUTO and VIDBYTE_MANAGED) use provider `meta`

Run B of two sequential runs. Run A (cerredz/Vidbyte, slug `meta-muse-gateway`) reached S6: draft PR https://github.com/cerredz/Vidbyte/pull/710 (head `da96273c0`), which is this run's wire contract (`context/wire-contract.md`, a verbatim copy of its spec §9.2–§9.4). This run's PR body must say it merges only after Run A is deployed.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-16 18:25 | 2026-10-16 21:55 | reports/S0-scout.md | base_commit 845a4d9b; code-map.md (4 sections, 303 lines); one gate in code (`_require_gateway_shape`) |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-16 18:25 — Worktree from origin/main `845a4d9b`; upstream unset (`git worktree add` set it to origin/main). Push with `git push -u origin feat/meta-muse-managed-text`.
- 2026-10-16 18:25 — Copied Run A spec §9.2–§9.4 verbatim into `context/wire-contract.md` (source commit `c395349bd`; §9.2 unchanged through Run A's final head) so every stage reads one stable contract text.
- 2026-10-16 21:45 — The S0 scout died on an API session limit mid-task; resumed the same agent via SendMessage after the coordinator said the limit had reset. Not counted against any cap.
- 2026-10-16 21:56 — Scout disclosure accepted: one early grep was not excluded from `docs/` and printed lines from other specs; the scout used none of them.

## User replies (verbatim)
- none

## Niche facts accumulated (carried into every later briefing)
- **One gate in code.** `VIDBYTE_MANAGED_TEXT_PROVIDERS` (`vidbyte/lib/constants/jev.py:74-81`) is read by `_require_gateway_shape` (`vidbyte/lib/dataclasses/model_configs.py:193`, called at `:96`) and by the M-18 message (`vidbyte/lib/registries/provider_keys.py:308`). There is no per-provider gateway map, builder, cap rule, or export elsewhere. — *source:* S0 scout
- **The cap is already guaranteed.** `vidbyte/lib/runners/text.py:57-62` sets `max_output_tokens` to 32,768 in every gateway mode, so `MetaProvider` always sends `max_tokens`. The request's and wire contract's "every call answers output_cap_missing" premise does not hold in gateway mode. `test_managed_text_wire_contract.py:130` asserts that no managed body carries `max_completion_tokens`, which conflicts with Run A's recommendation. The spec must decide. — *source:* S0 scout
- **The relay is already vendor-exact.** `ProviderKeys.key_for` matches the provider exactly, and META accepts only Meta-shaped keys. `K_META` already exists at `tests/.../provider_keys_fixtures.py:39`, built by concatenation. — *source:* S0 scout
- **Tests that change by design:** `GatewayShapeTests` (`tests/features/sdk_provider_keys/test_provider_keys_modes.py:223`) and `tests/features/sdk_managed_text/test_managed_text_selection.py:245-261` (`UNMANAGED_TEXT_PROVIDERS` lists META). The packs' COMMON MODIFICATION PATTERNS lines name the tables to extend: `managed_text_fixtures.py:7` (MANAGED_MODELS, provider_answer, relayed_provider_error; `_CHAT_PROVIDERS` at :58 omits META) and the provider_keys wire-contract module :6 (RELAY_KEYS, CAP_FIELD). The acceptance test iterates MANAGED_MODELS through ORACLE_KEYS (:102), so a META entry without an oracle key raises KeyError. — *source:* S0 scout
- **No model check in gateway mode.** A Muse id the backend does not serve (1.2, 1.3, contributor) reaches the gateway and gets its 422, worded at `vidbyte/lib/http/vidbyte_gateway.py:124`. The SDK prices `muse-spark-1.1` at `pricing.py:284`, matching Meta's first-party page. No price changes. — *source:* S0 scout
- **Docs that list served providers:** README lists at :337 and :343-345, the comment at `jev.py:72-73`, and the byok spec EC-15 (`docs/spec/byok-api-keys/spec.md:436`) and M-12 (`:907`). — *source:* S0 scout
- **Gates.** One file: `PYTHONPATH=$(pwd) py -3.11 -m pytest <file>`. Area: `PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys`, with `DEEPSEEK_API_KEY` unset. Full: `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`, then `py -3.11 scripts/run_ci.py --stage package` with no PYTHONPATH, then the proof run `py -3.11 scripts/run_ci.py` with PYTHONPATH unset. Never export PYTHONPATH before a full run. — *source:* S0 scout, field guide `local-ci-verification.md`, memory
- **Known red on pristine SDK main (as of 2026-10-15, unverified at 845a4d9b):** `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (148 != 120; PR #1147 may have fixed it) and `test_mcp_stdio_transport.py::...::test_cancelled_waiter_does_not_break_transport` (Windows timing flake). Confirm on a detached origin/main worktree before excusing either. SDK CI never attaches to PRs (0 checks). — *source:* coordinator prompt §4
- Windows/Git Bash. Heredocs collapse `\\`, so scripts with backslashes are written with the Write tool. Working copies use CRLF. Use `py -3.11`. Fake keys are built by concatenation. Never use bare `git stash`. Do not touch the main checkouts. — *source:* coordinator
