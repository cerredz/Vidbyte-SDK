# Onboard model provider skill feature tests

## Folder Description / Intent

This folder checks the `/onboard-model-provider` Claude Code project skill: the orchestrator instructions, the per-provider procedure with its 33-row wiring checklist, and the regenerated `.claude/` entry of the repository map. The skill is Markdown that an agent executes with push rights, so the tests read its text the way the agent would. They parse headings outside code fences, GFM tables, fenced shell commands and inline code, and compare them with the values spec r3 of `docs/spec/provider-onboarding-skill/` fixes. Where the skill extracts values with `sed`, the tests run those same `sed` scripts, translated to Python, over the real repository files, so a change on main that would break a provider run fails here first.

Every test here also runs inside every provider PR the skill opens. The tests therefore never compare against a base commit, never pin the provider list, the member count, `PRICING_AS_OF` or a line number, and never assert that a seed vendor is not yet a provider.

## Non-Goals

- Do not run the skill, Claude, `git`, `gh` or the network. The behavior half of AC-1, and AC-10, AC-11 and AC-12, are PR-time evidence recorded in the pull request body, as spec section 13 directs.
- Do not run the skill's shell commands, with one exception: G1 runs the PR-body guard line, read from provider-run.md, through `sh` over a temporary body file. It is offline, and it is skipped where no `sh` exists.
- Do not test the provider wiring itself (key matching, pricing, runner maps). `tests/features/sdk_provider_keys/`, `tests/features/sdk_model_catalog/` and `tests/test_agent_pricing.py` own it, and each provider PR extends those packs.
- Do not copy the skill files or stub them. A missing skill file must keep this pack red.

## File Index

- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `onboard_skill_fixtures.py` holds the paths, the spec-r3 values the tests compare against, the fence-aware Markdown reader, and the `sed` emulator.
- `test_onboard_skill_acceptance.py` checks the person-facing promises: the invocation line, the output grammar, the three stops, the rules, and what each outcome leaves behind. Start here for a regression a person would notice.
- `test_onboard_skill_contract.py` checks the frontmatter, the two-file folder, the headings, constants, seed table and hosts, the subagent brief, the result block, the enumerations, result verification, the publish rules, and the map entry.
- `test_onboard_skill_wiring_checklist.py` checks the wiring table against the spec and the tree, pins the C9 wire-test template that proves the key leaves as its Bearer token and the C4 note that a README quote contains the prefix, and runs the orchestrator's checklist-path command over it.
- `test_onboard_skill_commands.py` checks that preflight and pass-top commands are read-only and ordered, that the vintage and member reads parse the real sources, the interpreter, PYTHONPATH and probe spelling, the gate commands, the mutation check, the research protocol and its network rule, the skip reads and dispositions, the worktree add and its failure branch, and every named path.
- `test_onboard_skill_security.py` checks the forbidden constructs, the single GitHub write, the single push refspec, the managed provider set, the provider-prefixed model ID rule against the real runner, the first-party rule for format-bound keys, key shapes, the URL rule, the PR-body guard's exact command and outcome, and the rule that a run never edits an existing vendor's key entries.
- `test_onboard_skill_publish_guard.py` runs the PR-body guard line, read from the skill, through `sh` over clean and dirty bodies, so a guard that misses a local path or blocks a clean body fails here.

## Logs

- 2026-10-16 - Pack added red, ahead of the implementation, from spec r3 (S2 test author) - every test fails until the skill folder exists and the map entry is regenerated.
- 2026-10-17 - Review R-3 and R-8 - S5, X8, X9 and A5 now pin each rule's final wording instead of a token, and W7, X12, X13 and S7 pin the C9 Bearer template, the back-pressure union, the vintage stop and the D-13 format-binding rule; 50 tests.
- 2026-10-17 - Re-review round 1 (R-9 to R-12) - X2, X4, X5, X7, X10, A3, A4, S4, C10 and W7 now compare whole rules and commands, and S8, S9, C13 and G1 pin the URL rule, the PR-body guard, the Dialect step and the guard's behaviour under `sh`; 63 tests.
- 2026-10-17 - S5 repair 3 (spec r9 row s5r3-1) - S10 and W8 pin the rule that keeps an existing vendor's key entries, the Follow-ups record of a newer key shape, and the C4 quote that contains the prefix; 65 tests.
