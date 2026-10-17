# Feature: the `/onboard-model-provider` project skill (continuous provider onboarding)

## High-Level Feature Description

A person types `/onboard-model-provider` in a Claude Code session opened in a clone of the SDK. The session then runs in continuous mode: each pass picks the next qualifying seed vendor, hands it to one fresh subagent in its own worktree built from `origin/main`, and that subagent researches the vendor from dated first-party pages, wires it through the repository's 33 touch points, proves the change (red-first tests, mutation checks, full gate) and opens exactly one pull request on `feat/provider-<slug>`. The loop stops with one STOP line and a ledger when no candidate is left, when 3 or more provider PRs are open, or when a provider fails its proof bar.

The skill is two Markdown files, `.claude/skills/onboard-model-provider/SKILL.md` (the orchestrator) and `.claude/skills/onboard-model-provider/references/provider-run.md` (the per-provider procedure), plus the regenerated `.claude/` entry in `REPO_MAP.md`. The text **is** the program: an agent executes it with an admin's `gh` identity and no person watching. If it regresses, one of five things happens: a PR-opening side effect starts unasked; a vendor fact enters the SDK without a first-party source; a key is misrouted to another vendor; the run writes where it must not (the person's checkout, `main`, someone else's PR); or every provider run ends in a false stop because the procedure no longer matches the repository it wires. Contract: `docs/spec/provider-onboarding-skill/spec.md` r3 (§4, §6, §8.5, §9, §10, §12.3).

## Contract

- **Manual-only invocation** (AC-2, INV-22, D-17): the frontmatter is exactly `name`, `description` (≤ 1,536 characters) and `disable-model-invocation: true`; the skill takes no arguments.
- **Fixed anchors** (AC-5, AC-7, §8.5): both files carry exactly the §8.5 H2 headings in order, the §8.5 constants, the subagent brief, the PROVIDER RESULT block, and every enumeration (stop reasons, prereq names, disqualification reasons, proof checks, skip dispositions, unverified checks).
- **Output grammar** (AC-1, INV-1, §9.2): every pass, STOP, remedy and ledger line form appears in `## Output`.
- **Read-only until the first write** (AC-5, NFR-3): no preflight or pass-top shell command writes before `git worktree add`; the pass runs fetch, vintage, back-pressure, selection, then the worktree, in that order (FR-3).
- **Commands that work on this repository** (AC-8, D-15, D-20, §12.4): every interpreter command is `<py>`; `PYTHONPATH=` only prefixes one command and never the package stage; the pass-top and checklist `sed` commands parse the real sources and the real wiring table.
- **The wiring checklist** (AC-4, §12.3): 33 rows A1..D2 in order, each path existing and each symbol present at HEAD, silent rows marked.
- **The seed list** (AC-6, §9.1, D-19): ten vendors in rank order, no researched fact baked in, every URL on its row's first-party hosts.
- **GitHub and git writes** (INV-18, INV-19, AC-15): GitHub only through `gh api`; the only write is one `POST .../pulls`; the only push is `HEAD:refs/heads/feat/provider-<slug>`, unforced.
- **Key safety** (D-29, EC-60, INV-16): a one-`/` ID whose first segment is a `ModelProvider` value is ineligible and self-checked; no literal key shape in the skill.
- **Forbidden constructs** (AC-3, INV-21): no `gh pr`/`gh issue`, `git stash`, force push, PowerShell, `$env:`, `.exe`, drive-letter or backslash paths, or `path:line` references.
- **The map** (AC-9): the `REPO_MAP.md` `.claude/` entry describes both the review-agent settings and invoked project skills, in 4 or 5 sentences with no file name or command.

## Actors / Callers

The person who types the command (operator); the orchestrator session executing SKILL.md; the provider subagent executing provider-run.md; the person reviewing each provider PR; future agents editing the skill or the files it wires.

## Inputs and Preconditions

The two skill files and `REPO_MAP.md` on disk, and the repository files the skill names (the wiring checklist's paths, `scripts/run_ci.py`, `lint/rules/c010_pricebook_vintage_bump.py`, `vidbyte/lib/registries/pricing.py`, `vidbyte/lib/enums/model_provider.py`, `vidbyte/lib/runners/utility.py`). Tests read files only. They never call the network, `gh`, `git` or Claude.

## Observable Outcomes

The text of the skill files (headings, tables, fenced shell commands, inline code), the result of running the skill's own `sed` extraction commands over the real sources in Python, and the answers of the real `Runner._normalize_provider_and_model` for provider-prefixed IDs.

## State Transitions

None at test time. The skill's state machine (candidate, skipped, DISQUALIFIED, PR_OPENED, STOP) is enforced by the agent executing the text; the tests pin the text that defines it.

## Invariants

- Every committed test stays green on every provider branch the skill opens (a provider PR adds a `ModelProvider` member, rates, a newer `PRICING_AS_OF`, key rules and tests). No test compares against `base_commit` or a merge-base, pins the member count, the provider list, `PRICING_AS_OF` or a line number, or asserts that a seed slug is not a member.
- Every collection check has an explicit count or presence guard tied to a spec number, so an empty parse never passes.

## External Dependencies

The filesystem only. PyYAML parses the frontmatter. `vidbyte` is imported for `ModelProvider`, `PRICING_AS_OF`, `Runner` and the self-check classes, so the parsing checks have an independent oracle.

## Known Failure Modes

Each line is input + state → wrong output. The test that catches it is in the Test Suite Map.

- Frontmatter without `disable-model-invocation: true` (or with the string `"true"`) → Claude loads the skill by itself, and a PR-opening run starts unasked (C1).
- An `allowed-tools` or `argument-hint` key, or `$ARGUMENTS` in the body → a control Q-7 rejected, or arguments the skill promises to ignore (C1).
- SKILL.md at 500 lines or more, or the checklist copied into it → the loop's own rules compete with provider detail (NFR-2) (C1, C9).
- A helper `.py` or a README in the skill folder → A001, S062, A009 and S020 scope; NG-5 (C12).
- A heading renamed or reordered → the brief's "read to the end" anchors and AC-5/AC-7 drift (C2).
- A STOP line form missing from `## Output` → the person and the PR-time run cannot parse the stop (A2).
- `pip install`, `-X POST` or a `>` redirect in preflight or pass-top → a session that stops before any subagent has already written (NFR-3: 0 writes) (X1).
- Selection before back-pressure, or the vintage check after the worktree add → a fourth PR, or a worktree on a day the run must stop (X2).
- `git worktree add -B`, `--force`, or from local `HEAD` → a kept branch overwritten (EC-17), or a stale base (D-3) (X2).
- The vintage `sed` no longer matches `PRICING_AS_OF: str = "…"` → an empty vintage, so VINTAGE_DEFERRED never or always fires (X3).
- The members `sed` misses a member → a merged vendor is selected again, and a duplicate provider PR opens (INV-5a) (X3).
- The back-pressure filter drops `head.repo.full_name` or pagination → fork PRs block the loop (T-4, EC-10), or more than 30 open PRs are undercounted (X4).
- The per-slug query reads only open PRs → a vendor the person closed unmerged is onboarded again (INV-5b, "skip it forever") (X4, C8).
- A bare `python -m pytest` in the procedure → on the user's machine bare `python` lacks pytest, so every provider run ends PROOF_FAILED (R-7, EC-2) (X6).
- `export PYTHONPATH`, or `PYTHONPATH=` before the package stage → the clean install skips the wheel, so every run ends `gate-package` (D-15) (X7).
- `run_ci.py` renames its smoke line, or the c010 module drops `--refresh-lock` → FR-11 check (4) refuses every PR, or the lock is hand-edited and C010 fails closed (X8).
- The known-red rule loses its detached base twin, its unchanged-file check or its up-to-3 reruns → a failing test the branch added is excluded as pre-existing, or the MCP waiter flake stops a sound provider (D-15, review r2-2) (X8).
- The mutation check runs before the commit, restores by stash, or never confirms `git diff --quiet` → the mutation leaks into the PR or work is lost; counting the table-pinning contract test makes the proof vacuous (INV-15) (X9).
- A summarizing fetch as the only evidence, no `date -u`, or a plain vendor 403 treated as NETWORK_BLOCKED → unauditable facts (G-2), or every later invocation stalls on that vendor (R-5) (X10).
- A named path renamed or deleted upstream → the subagent edits a missing file or creates a new one (INV-14) (X11, W3).
- A wiring row dropped or reordered (for example A2, the usage class) → usage and cost are silently not recorded for every new provider (W1, W2, W4).
- A table row padded as `|  A1 |` → the orchestrator's `sed` extracts no checklist path, so every PR ends RESULT_UNVERIFIED `diff-paths`; an extra matching table lets out-of-checklist edits pass (W6).
- The C6 swap case removed → the two-key swap of `test_an_openai_access_token_beside_a_deepseek_key_is_refused_not_swapped` ships for the new vendor (W5).
- A seed row with an invented vendor, a different order, or a baked-in price, model ID or key prefix → FR-17 broken, or a stale fact enters code (C4).
- A seed URL off its row's pinned hosts → the run's own entry page is not first-party, or an attacker's page counts as first-party (T-5, T-6, EC-53) (C5).
- The brief without `base:` or `interpreter (<py>):` → the subagent builds on a moving `origin/main` or with the wrong interpreter (C6).
- The result block's fields differ between producer and consumer → the orchestrator cannot verify, and every pass ends RESULT_UNVERIFIED `no-result` (C7).
- A disqualification reason missing from `## 3. Qualify` → the subagent writes a free-form reason the grammar does not define (C8).
- `## Verifying a result` lists the PRs instead of reading one by number → list lag gives a false stop (C9).
- The PR quote cap or the inline-code rule dropped → vendor text reaches the hosted `@claude` agent as the owner's words (T-2b); a local path in the body → the auto-mode classifier refuses the PR (C10).
- REPO_MAP still says local sessions do not load `.claude/` → agents ignore the skill folder (C11).
- `gh pr`, `git stash`, a force push, PowerShell, `.exe`, `C:/` or `path:line` in the skill → GraphQL refusals in cloud, the person's untracked files touched, history rewritten, a Linux run broken, or references that rot (S1).
- Any GitHub write other than the PR create (merge, close, label, comment, review) → NG-3 broken under an admin identity (S2).
- A push of any other refspec, or a forced one → `main` overwritten under an identity that bypasses branch protection (T-3) (S3).
- An instruction to add the vendor to `VIDBYTE_MANAGED_TEXT_PROVIDERS` → AUTO routes an unserved provider to the gateway (D-12) (S4).
- The D-29 rule or its self-check line missing → `openai/gpt-oss-120b` is catalogued under the new vendor, and that vendor's key is bound to openai when a caller omits `provider=` (S5).
- A literal key shape in the skill → push protection trips, or a key-shaped string sits in the tree (INV-16) (S6).
- The intro hides the three stops, a disqualification stops the loop, or closing a PR is not said to skip the vendor forever → the person cannot predict the run (AC-13, FR-15) (A3, A4, A5).

The lines below are rules whose words, not only whose tokens, the tests pin (review R-3 and R-8). Each was proven by a mutation of the real skill that passed the 46-test pack and now fails the named test.

- The D-29 condition inverted to "is not None", the eligibility reading without "derived provider None", or the self-check `assert` turned into a bare call, while the probe still names `_normalize_provider_and_model` → provider-prefixed IDs qualify again (S5).
- The known-red exclusion rewritten to "when its file is changed … exits 1", or `diff --quiet` only logged → a failing test the branch edited is excluded as pre-existing (D-15) (X8).
- The A13 exception widened to the whole file or to either check, "exactly one line" weakened, "the same `AssertionError` line" dropped, the scoped diff unscoped, or the control edit appended on the branch instead of the twin → a real tools or configs regression is waved through (D-15) (X8).
- "Any one counts, `test_provider_keys_contract.py` included", or "Prefer one outside" → a mutation proof that only the table-pinning test caught (INV-15) (X9).
- `PROOF_FAILED` or `PUBLISH_FAILED` moved into the cleanup bullet, cleanup run "always", or the cleanup chain's `&&` replaced by `;` → unpushed work deleted, or the branch deleted after a failed worktree remove (D-8) (A5).
- The C9 template without the `authorization` Bearer assertion, asserting `x-api-key`, without the other-key absence check, with one key instead of a mixed list, in AUTO mode, or the C9 Add cell without the Bearer outcome → the only wire proof passes when the key leaves in the wrong header or beside another vendor's key (EC-43, D-12) (W7).
- Back-pressure counting only the PRs GitHub lists, without the union with this session's PRs → list lag lets a fourth provider PR open (INV-3, EC-9, D-5) (X12).
- The vintage check inverted to "is before today" → every normal day stops, and the day main is already current runs (FR-3, D-10, EC-19) (X13).
- `FORMAT_BOUND_PROVIDERS` allowed on an example key, or the first-party statement weakened → a format-bound vendor refuses its own unprefixed key, and elimination hands that key to another vendor (D-13, EC-33) (S7).

## Historical Regressions

- Spec review r1 R-1: a committed diff-against-base test would fail every provider PR. No test here reads git state.
- Spec review r1 R-7: literal `python …` commands fail on the user's machine (X6).
- Spec review r2 R-1: provider-prefixed one-`/` IDs misroute keys (S5).
- Spec review r2 R-6: the checklist paths had no stated source in SKILL.md (W6, C9).
- Implementation review R-3 and R-8 (2026-10-17): S5, X8, X9 and A5 checked that a token was present, so an inverted rule passed, and the C9 Bearer template, the back-pressure union and the D-13 example-key rule were unpinned. The tests now pin each rule's final sentence outside fences, forbid the inverted wording, bind each outcome to its bullet, pin the commands exactly, and compile the python fences (S5, X8, X9, A5, W7, X12, X13, S7).

## Test Suite Map

- `onboard_skill_fixtures.py`: paths, the spec-r3 constants the tests compare against (headings, constants, enumerations, the 33 wiring rows, the seed slugs, the §9.2 grammar), a fence-aware Markdown reader that separates prose from fenced code, and a POSIX `sed -n 's/…/…/p'` emulator.
- `test_onboard_skill_acceptance.py`: the invocation line and the §9.2 grammar (AC-1), the stop conditions, the continue-on-disqualify rule, the rules a person relies on, and what each outcome leaves behind (AC-13, FR-15, D-8).
- `test_onboard_skill_contract.py`: frontmatter and size (AC-2), the two-file folder (D-1), headings (AC-5, AC-7), constants, seed table and hosts (AC-6, D-19), brief, result block both sides, enumerations, verification, publish rules, and the REPO_MAP entry (AC-9).
- `test_onboard_skill_wiring_checklist.py`: the wiring table's header, refs, cell grammar, spec paths and symbols, existence at HEAD, silent markers, the C6 swap case (AC-4, AC-7), the C9 DIRECT wire-test template with its Bearer assertion (EC-43, D-12), and the orchestrator's extraction command run over the real table (FR-11, D-28).
- `test_onboard_skill_commands.py`: read-only preflight and pass-top (AC-5), pass order (FR-3), the pass-top `sed` commands run over the real sources (AC-1), back-pressure and selection filters (INV-4, INV-5, T-4), the back-pressure union with this session's PRs (INV-3, EC-9), the vintage stop (FR-3, D-10), preflight and permission setup (FR-2, D-27), `<py>` spelling (AC-8), `PYTHONPATH` (D-15), gate commands (§12.4, INV-17), mutation order (AC-8, INV-15), research protocol (D-19, INV-20), and named paths (INV-21).
- `test_onboard_skill_security.py`: forbidden constructs (AC-3), GitHub writes (INV-18, INV-19, AC-15), the push refspec, the managed provider set, D-29 key safety with the real `Runner` and the exact self-check, the D-13 first-party rule for format binding, and key shapes (INV-16).

Run `python -m pytest tests/features/onboard_model_provider_skill -q` from the repository root (on this machine `py -3.11 -m pytest …`).

## Omitted Testing Strategies

- **End-to-end runs of the skill**: a Claude session cannot run inside pytest, and `disable-model-invocation: true` stops an agent from invoking it. The behavior half of AC-1 and AC-10, AC-11, AC-12, INV-23 to INV-26 are PR-time evidence recorded in the PR body (spec §13).
- **Running the preflight and pass-top commands against GitHub**: tests never touch the network or `gh`. The read-only commands are run live at PR time (AC-1); here only their `sed` parsing is executed, offline, over the real sources.
- **Diff and merge-base tests**: forbidden by spec §13 (R-1), because they would fail every provider PR.
- **The optional `.claude/ci-settings.json` content guard** (§13): it already passes on main, so it proves nothing about this feature; INV-24 is PR-time evidence.
- **Property-based, fuzz and metamorphic tests**: the feature has no algebraic invariant in code. Its selection and loop are prose executed by a model.
- **Concurrency and idempotency** (EC-52, INV-5): two sessions and a re-invocation are behaviors of a model against live GitHub. The text guards (skip rules a to e, one session at a time, the unforced single refspec that makes GitHub refuse a second push) are tested; the runtime behavior is not testable offline.
- **Liveness of seed URLs and first-party facts**: needs the network, and the facts drift by design (they are re-researched every run).
- **Pinning display names, URLs and Reason text of the seed rows**: a reviewed seed edit would need a second edit here without protecting a spec rule; C5 checks the security property (URLs on the pinned hosts) instead.
- **Asserting that seed slugs are not `ModelProvider` members**: false on the first provider branch.
