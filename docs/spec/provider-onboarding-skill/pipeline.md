---
slug: provider-onboarding-skill
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill
branch: feat/onboard-model-provider-skill
base_commit: 72a4ade129d74bab45b4fc12764d951df6d1ec3b
pr:
until: none
started: 2026-10-15 18:41
---

# Pipeline: In-repo skill that onboards one new model provider per run, unattended

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 18:41 | 19:05 | reports/S0-scout.md | base 72a4ade1; code-map.md (4 sections, 37 per-provider touch points) |
| S1 spec + review | running | 2026-10-15 19:10 | | reports/S1-spec-author.md | spec r1 @9da36eb1 (author done; review round 1 next) |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Fixed values
- REPO_ROOT `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (main checkout: never touched; has untracked files)
- WORKTREE_PATH `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill`
- BRANCH `feat/onboard-model-provider-skill` (no upstream; push with `git push -u origin feat/onboard-model-provider-skill`)
- PR_BASE `main` · BASE_COMMIT `72a4ade129d74bab45b4fc12764d951df6d1ec3b`
- AGENTS_MD_PATH `<WORKTREE_PATH>/AGENTS.md` · REPO_MAP_PATH `<WORKTREE_PATH>/REPO_MAP.md`
- FIELD_GUIDE_INIT `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md`
- SKILL_DIR `C:/Users/422mi/.claude/skills/spec-pipeline` · AGENTIC_ENGINEERING_DIR `C:/Users/422mi/.claude/skills/agentic-engineering`

## Decisions the orchestrator made
- 2026-10-15 18:45 — Unset the branch's upstream right after `git worktree add` (it tracked origin/main) — so no bare `git push` from the branch can ever target main.
- 2026-10-15 19:06 — Renamed the branch from `feat/provider-onboarding-skill` to `feat/onboard-model-provider-skill` before anything was pushed — the old name matches the `feat/provider-<vendor-slug>` prefix the skill itself uses to count open provider PRs (back-pressure) and to skip closed-unmerged vendors, so this PR would have been miscounted as a provider PR named "onboarding-skill". The slug (`provider-onboarding-skill`) and the docs path are unchanged, as the parent fixed them.
- 2026-10-15 19:06 — Allowed every stage to read `docs/spec/byok-api-keys/` (the parent session's spec for PR #1027) because the user named that work (request.md §C "Constraints").

- 2026-10-15 21:33 — S1 spec author (first launch) terminated on an API session limit before writing anything (no spec, no commit). Resumed the same agent via SendMessage with the user's decision verbatim, rather than relaunching, so its grounding reads are kept.
- 2026-10-15 21:33 — Added a superseding "USER DECISION RECEIVED DURING THE RUN" block at the top of request.md §C (original notes kept below it) so every later agent that reads request.md sees the no-routine / continuous-mode decision first.

## User replies (verbatim)
- 2026-10-15 21:32 — (relayed by the parent session; changes a settled decision) The user was asked how to schedule the 24/7 cloud routine and answered: "dont add as routine, just explain in system prompt, should be good enough for now", and "no cloud routine".
  Parent's statement of what changes: no cloud routine or cron infrastructure will be created by anyone; the skill's SKILL.md must explain continuous operation (onboard one provider → open its PR → return to an up-to-date main → pick the next qualifying vendor → repeat, one branch and one PR per provider, until: no qualifying candidate left, ≥ 3 provider-onboarding PRs open, or a run fails its proof bar; on any stop, exit with a clear report); the skill must say how a long continuous run keeps its context small (recommended: a fresh subagent per provider with a self-contained brief, the looping agent keeps only a ledger; the spec decides). Unchanged: location `.claude/skills/onboard-model-provider/`, idempotent selection (skip members, open PRs, closed-unmerged), first-party-only facts, the proof bar, no merging. Final report: instead of "a 10-line summary to paste into the routine", give a 10-line summary of exactly how a user starts continuous mode and what each loop iteration does.
  Recorded in request.md §C (top block). To be recorded verbatim in spec §0.2 by the S1 author.


## Niche facts accumulated (carried into every later briefing)
- On this machine the bare `python` on PATH may be a browser-use env without pytest. If `python -m pytest` fails to import, use `py -3.11` (Python 3.11 at `C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe` ran the SDK gate successfully before). — *source:* parent session 21:32
- code-map.md §2b lists 37 per-provider touch points (traced via kimi, mistral, meta); it is the source for the skill's checklist. — *source:* S0
- C009 (baseline 0): every token-priced default text model must resolve to a price; only OpenRouter is exempt (`_PRICED_PER_RESPONSE`). So a vendor whose default text model has no first-party price cannot pass the gate; "the repo's rule for unpriced models" (pricing.py:61-64 "omitted") only covers non-default models. — *source:* S0 §4.1.1
- C010: new rates need a later `PRICING_AS_OF` (pricing.py:58) + lock refreshed ONLY via `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock` (hand edits fail closed) + the vintage pin in `test_catalog_pricing_contract.py:376-379`. Every priced provider PR edits those same lines, so concurrent open provider PRs conflict once one merges. — *source:* S0 §4.1.2
- A new provider works ONLY in DIRECT mode: default `TextModelConfig.mode` is AUTO, which refuses providers outside `VIDBYTE_MANAGED_TEXT_PROVIDERS` (6 providers, `vidbyte/lib/constants/jev.py:74-81`, changed "only when the backend gateway contract changes"). The skill must not add vendors to that set. — *source:* S0 §4.1.3
- Table A's "any" row exists only in `vidbyte/lib/registries/README.md:64`; in code it is the fall-through `True` in `accepts_unproven` (`provider_keys.py:105`). A no-prefix vendor needs no `provider_keys.py` edit, only the README row. — *source:* S0
- `test_provider_keys_contract.py:70-76` pins table F order/prefixes, the format-bound set, and `RESERVED_PREFIXES == ()` — natural mutation-check target. `test_provider_keys_matching.py:43` iterates `tuple(ModelProvider)`; format-bound vendors also go into `FORMAT_BOUND` at `:44`. — *source:* S0
- Silent-skip traps: `_usage_class_map` (`model_provider.py:54-74`; only `tests/test_agent_pricing.py:124` catches it); `UNMANAGED_TEXT_PROVIDERS` (`managed_text_fixtures.py:49-55`); `PROVIDER_DEFAULT_RUNNER_TYPE_MAP` (no known test). — *source:* S0
- Any tracked `.py` (even under `.claude/skills/`) must carry A001's 7 header fields and must not join string literals by adjacency (S062). — *source:* S0
- `run_ci.py` has NO semgrep (semgrep is only in dispatch-only `static-policy.yml:24-30`); lint prints `SDK-LINT: PASS` (not AGENT-LINT). A pytest failure stops the gate before the package stage, so run `python scripts/run_ci.py --stage package` separately. — *source:* S0
- The harness-threads known-red test SKIPS when origin/main is missing (shallow clone) and FAILS on a full clone. — *source:* S0
- `REPO_MAP.md:11` describes `.claude/` as hosted-automation-only, deny-push, "Interactive sessions ... do not load it" — that describes `ci-settings.json` (loaded only by `claude.yml:50`); adding `.claude/skills/` makes the entry stale, so REPO_MAP needs an update. — *source:* S0 §4.1.7
- Title search for "provider" hits unrelated closed-unmerged PRs (#504, #697, #406); no `feat/provider-*` branch exists yet. Key provider-PR detection on the exact branch prefix, not titles. — *source:* S0 §4.1.12
- `provider_keys.py` is 312 lines vs byok NFR-4 "under 300" (unenforced); each table F rule adds ~3-5 lines. — *source:* S0
- Environment: Windows + Git Bash for this pipeline (heredocs collapse `\\`; CRLF); the routine runs on Linux. Known-red on pristine main: harness_threads `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (148 != 120) and mcp stdio `test_cancelled_waiter_does_not_break_transport` (flaky). GitHub CI never attaches to PRs (0 checks); merges need `--admin` by the user. — *source:* orchestrator brief
