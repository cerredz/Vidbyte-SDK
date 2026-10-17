# S1 spec author report — provider-onboarding-skill r1

Spec: `docs/spec/provider-onboarding-skill/spec.md`, committed as `9da36eb1` ("docs(spec): add provider-onboarding-skill spec r1") on top of `ae34de61`.

The spec was redesigned around the user's mid-run reply ("dont add as routine…", "no cloud routine"). That reply is recorded verbatim in §0.2 as r1.

## 1. What I read

**Pipeline references.**
- `spec-template.md`.
- `house-style.md`.
- `vidbyte-gates.md`. I found it wrong on two points: there is no semgrep step in `run_ci.py`, and the lint pass line is `SDK-LINT: PASS`.

**Pipeline inputs.**
- `request.md`, including the §C block added in `ae34de61`.
- `context/code-map.md`, all 380 lines.
- `reports/S0-scout.md`.
- `pipeline.md`.

**Repository rules.**
- `AGENTS.md` and `REPO_MAP.md`: the `.claude/` and `skills/` entries.
- `CONTRIBUTING.md`.
- `.github/pull_request_template.md`.
- `skills/README.md`.
- `skills/jev-continuation/SKILL.md`, the house-style exemplar.
- Commit `336fe4ec`, the vendored `.claude/skills/` precedent.

**Code.** I traced every per-provider touch point at HEAD:
- `model_provider.py`
- `provider_keys.py`, including the full matcher semantics of `accepts_unproven` and `RESERVED_PREFIXES`
- `registries/README.md`
- `pricing.py`
- `models.py` (`provider_for_model`, `validate_provider_model_pair`, `_catalog_name`, `known_models`)
- `runners.py`
- `runners/utility.py` (`resolve_runner_type`, `_normalize_provider_and_model`)
- `model_modality.py`
- `modality_detector.py`
- `tools/formatter.py` (`_PROVIDER_FAMILY_HINTS`)
- `compatible.py`
- `providers/__init__.py`
- `structured_output.py`
- `constants/jev.py`
- `scripts/run_ci.py`
- lint rules C009, C010, S014, A001, S062, A009 and S009

**Tests.**
- The `sdk_provider_keys` pack: fixtures, contract, matching, property and modes.
- `managed_text_fixtures.py`.
- `test_catalog_pricing_contract.py`.
- `tests/test_agent_pricing.py`.
- `test_output_connectors_contract.py`, as prior art for static doc tests.

**Prior spec (named readable).** `docs/spec/byok-api-keys/` — the PR body, verify log and test plan.

**First-party docs, opened 2026-10-15.**
- Claude Code: skills (frontmatter, `disable-model-invocation`, `${CLAUDE_SKILL_DIR}`, under 500 lines, 1,536-character listing cap), routines, cloud environments.
- GitHub REST pulls API.
- The `gh api` manual.

**Vendor pages.** For each of the 14 candidates I opened the vendor's own pages (§5 below), plus the gitleaks default config and GitHub's secret-scanning pattern list.

### Mechanical checks run, all read-only
- Every wiring-checklist row: 33 rows, each path and symbol verified at HEAD by a script over `git show HEAD:<path>`. Result: 0 problems.
- Every ID the spec references is defined.
- `grep -c "^## §"` returns 18. `grep -n "^| [0-9]"` matches only §12.3 rows 1–3.
- The selection commands, live against GitHub:
  - open provider PRs: 0 of 6 open PRs;
  - `head=cerredz:feat/jev-skill-providers` returned #504 as an exact match, while the prefix form returned nothing;
  - `.permissions.push` is `true`;
  - `git ls-remote --exit-code` exits 2 for `feat/provider-cerebras`;
  - the members `sed` and the vintage `sed` both work on `git show origin/main:` blobs, which are LF even in this CRLF working copy.
- No seed slug appears as `<slug>/` in any catalogue string under `vidbyte/`. `gpt-oss-120b` is in the modality map but in no runner map.

## 2. Approaches weighed

1. **Context strategy for continuous mode (D-2).**
   - Chosen: one sequential fresh subagent per selected vendor, with a self-contained brief and a PROVIDER RESULT block. The looping session keeps only a ledger.
   - Rejected: an inline loop in one context. One provider run touches 33 rows and several long READMEs (the providers README is 40,944 characters), and also reads vendor pages and gate logs, so inline the loop rules would be compacted away after about two providers.
   - Fallback when there is no Agent tool: handle providers inline, open at most one PR, then `STOP NO_SUBAGENTS`.
2. **Clean base per provider (D-3).**
   - Chosen: `git worktree add -b feat/provider-<slug> <checkout>-onboard-<slug> origin/main`.
   - Rejected: switching the launcher checkout. It has untracked files, and `git stash` is forbidden.
   - Cleanup depends on the outcome (D-8): never destroy unpushed work, and kept state makes the next invocation skip the vendor (`local-branch`).
3. **Helper script versus Markdown only (D-1).** Markdown only, two files. A helper `.py` would bring in A001 and S062, tests that fake `gh`, and duplicated rules. The smaller design I rejected, a single SKILL.md, fails NFR-2 and the 500-line guidance.
4. **Seed table location.** The seed table lives in SKILL.md, and each vendor's row is copied into its subagent's brief. A separate `seed-vendors.md` would be a third file with no consumer of its own.
5. **Slash model IDs (D-14).** Excluded for now, as a qualification-time skip.
   - `_catalog_name` drops the first `/` segment, while `Runner.resolve_runner_type` retries after the last one. A slash ID would need twin bare entries that no existing provider uses.
   - Getting this wrong after wiring would be a proof failure, which stops the loop. A skip is cheap.
   - Cost: Groq, DeepInfra, Together and Fireworks are expected to end `no-usable-model-id` (Q-3, default no).
6. **Interpreter (D-20).** Probe `python`, then `python3`, then `py -3.11` for Python ≥ 3.11 with the dev extras. Never install into the person's interpreter. Rejected: a per-session virtual environment, because it costs a network install every time and adds a path the person never sees.
7. **`disable-model-invocation: true` (D-17).**
   - The skill has side effects: it opens PRs.
   - The flag keeps the hosted `@claude` reviewer, which loads `.claude/`, from starting it.
   - It removes the description from every session's skill listing.
   - The person always starts it by typing the command.

## 3. Where I disagree with the scout or the request, with evidence

1. **"No `feat/provider-*` branch exists yet" (code-map §1.4, §4.1 #12) is false.** `git ls-remote --heads origin 'refs/heads/feat/provider-*'` lists three branches:
   - `feat/provider-aware-tool-error-rendering` (#234, closed unmerged);
   - `feat/provider-native-structured-outputs` (#96, closed unmerged);
   - `feat/provider-registry-predicate` (#319, merged).

   None matches a seed slug, and closed PRs do not count toward back-pressure. An open non-onboarding PR on such a branch would still be counted, which fails closed (EC-11).
2. **The request's unpriced-model rule cannot apply to a default model.** C009 (baseline 0) requires every token-priced default to resolve, and its `will_not_work` forbids the workarounds. So "no first-party price for a usable default" is a disqualification (D-9), not "follow the repo's rule".
3. **Table A's "any" row is not code.** It is the fall-through `True` in `accepts_unproven`. A no-prefix vendor needs no `provider_keys.py` edit (code-map §4.1 #4, which I confirmed).
4. **`provider_for_model == slug` is only a valid self-check because D-14 requires each catalogued ID to be uncatalogued on main.** `validate_provider_model_pair` refuses a second owner of a bare ID. If Cerebras merges `gpt-oss-120b` first, SambaNova's `gpt-oss-120b` becomes ineligible (EC-28).
5. **A new provider value can change existing behavior through `Runner._normalize_provider_and_model`.** An undeclared-provider model string `<slug>/<rest>` would be re-routed. This is guarded by the `slug-collision` qualification check (EC-38). No seed slug collides today.
6. **Fireworks' first-party example uses `OPENAI_API_KEY`.** Copying it would break S014 one-name-per-provider semantics and read the wrong key, so D-25 falls back to `<ENUM>_API_KEY`.
7. **Prompt injection is real.** Groq's models page (console.groq.com/docs/models, 2026-10-15) contained text addressed to AI agents. The fetch tool flagged it, and I treated it as data. This is the motivating evidence for INV-10 and T-2.
8. **Briefing item "gh pr in cloud"** is now moot (no routine). I kept `gh api` REST anyway (D-4) for its exact `head=` filters and `head.repo.full_name`, and because it still works in GraphQL-blocked environments.

## 4. Least-certain assumptions

- **A-10.** "The vendor's pricing page" is read as any first-party page that states per-token USD rates. Cerebras' `/pricing` renders its tables with JavaScript, and the rates were readable only on a model page. A stricter reading turns the rank-1 vendor into `no-first-party-price`.
- **A-2.** I assume a subagent has Bash, Edit and web fetch, and returns its final message to the caller. If a launcher session lacks the Agent tool on every invocation, continuous mode degrades to one PR per invocation.
- **A-1.** I assume `${CLAUDE_SKILL_DIR}` is substituted, and that `disable-model-invocation: true` still allows `/onboard-model-provider` typed by a person. Both are per the docs; neither has been exercised in this repo.
- **A-6.** The sdist not including `.claude/` was not verified (no gate runs allowed). AC-11 checks only the wheel.
- **Cost of re-research.** No persistence (Q-1, default no) means a session that reaches ranks 6–10 re-researches vendors that are expected to fail. With back-pressure at 3, a session opens at most 3 PRs before it stops.

## 5. Seed evidence (all pages opened 2026-10-15; details in spec §9.1)

The order is cerebras, ai21, cohere, sambanova, upstage, groq, deepinfra, together, fireworks, nebius. Ranking: first by evidence that every qualification check can pass from first-party pages, then by tool support, then by fewest wiring hazards.

**Ranked vendors.**
1. **Cerebras** — every check verified. Base `https://api.cerebras.ai/v1`, `CEREBRAS_API_KEY`, tool calling. `gpt-oss-120b` is priced at $0.35/$0.75 per 1M on `inference-docs.cerebras.ai/models/openai-oss`.
2. **AI21** — `/studio/v1/chat/completions`, Bearer `AI21_API_KEY`, tools (`stream` must be false). Jamba Mini is $0.2/$0.4 and Large $2/$8. Open: the response shape, and the link from display name to ID.
3. **Cohere** — Compatibility API at `https://api.cohere.ai/compatibility/v1` with tools. Per-token rates were visible only for some models.
4. **SambaNova** — "Our APIs are OpenAI compatible". USD per 1M pricing page. `docs.sambanova.ai` answered 403 twice.
5. **Upstage** — `https://api.upstage.ai/v1`, `solar-pro4`. The rates showed no currency symbol.
6. **Groq** — strong docs, but every token-priced text ID has a slash, and the no-slash Llama rows say "ContactSales". The page also carries the injection text noted above.
7. **DeepInfra** — `https://api.deepinfra.com/v1/openai`. Slash IDs, plus Claude- and Gemini-family names.
8. **Together** — `https://api.together.ai/v1`. Priced by display name; slash IDs.
9. **Fireworks** — `https://api.fireworks.ai/inference/v1`. Tools not stated; priced by display name and tier; `accounts/fireworks/models/…` IDs.
10. **Nebius** — `https://api.tokenfactory.nebius.com/v1/`. No public rates: the prices URL redirects to a console page that shows only a title.

**Excluded vendors.**
- **Perplexity** — Sonar endpoint, no tools, per-request fees.
- **Writer** — `/v1/chat` is not `/chat/completions`, and there is no price.
- **DashScope** — per-workspace base URL.
- **NVIDIA NIM** — `build.nvidia.com/pricing` returned 404, and the IDs use slashes.

**Fetches that failed.**
- `groq.com/pricing` showed no rates. I used the console models page instead.
- `www.cerebras.ai/pricing` tables were empty (JavaScript). I used the model page instead.
- `deepinfra.com/docs/openai_api` returned a 308. I used `docs.deepinfra.com/chat/overview` instead.
- `docs.sambanova.ai` returned 403.
- `nebius.com/token-factory/prices` showed a title only.
- `docs.ai21.com/docs/openai-compatibility` returned 404.
- `build.nvidia.com/pricing` returned 404.

## 6. Counts

- G 4, NG 13, INV 26 (4 of them must-not-regress), AC 15, EC 56, FR 17, NFR 7, D 26, T 6, W 6, A 10, Q 5. No Q is blocking.
- §12.3 has 3 rows. The wiring checklist has 33 rows.
- Budget: 2 new files, 1 modified file, 0 `.py`, 0 dependencies, 0 config keys, 1 command.

## 7. Revision r2 (2026-10-16)

Applied review round 1 (`reports/S1-spec-review.md`). §16 records every finding. Twelve were accepted. R-12 became Q-6, R-2's optional `allowed-tools` idea became Q-7 (default no), and R-5's optional "all unreachable means `NETWORK_BLOCKED`" rule was rejected.

**What I checked myself while revising:**
- **`provider_for_model`.** It matches a full ID, or a full qualified key, so a catalog name shared with another provider is not a conflict. I narrowed D-14 (d) to the full ID. Groq's `openai/gpt-oss-120b` therefore stays eligible after Cerebras merges `gpt-oss-120b`.
- **`Runner._normalize_provider_and_model`.** It routes an undeclared `<existing provider>/<model>` string to that provider. I recorded this as a limitation (EC-60), not a new check.
- **Groq models page.** Raw HTML on 2026-10-16 shows `openai/gpt-oss-120b` at $0.15 input / $0.60 output per 1M, and `openai/gpt-oss-20b` at $0.075 / $0.30. The Llama IDs say "Contact Sales".
- **`run_ci.py`.** It prints `CI passed.` for any stage that passes. An excepted known-red failure makes the source stage print `CI failed`, so FR-11 checks for `SDK-LINT: PASS` and `passed smoke checks.` instead.
- **Two repo facts.** `.claude/ci-settings.json` denies `Bash(git push *)`. `claude.yml` has `contents: write` and trusts `cerredz`.
- **The wiring checklist, re-checked under the strict §8.5 cell grammar.** All 33 rows pass: every path exists at HEAD, every backticked symbol and every dotted part appears in its file, and every heading appears verbatim.

**Counts after r2:**
- G 4, NG 13, INV 26.
- AC 15 (AC-14 withdrawn), EC 60 (EC-1 withdrawn), FR 17 (FR-14 withdrawn), NFR 7.
- D 28, T 6, W 6.
- A 10 (A-10 withdrawn), Q 7. None is blocking.

## 8. Revision r3 (2026-10-16)

Applied review round 2 (`reports/S1-spec-review-r2.md`), the last round. §16 records every finding as rows r2-1 to r2-7.
- **Accepted:** six findings.
- **r2-3, accepted in part:** the single-quote rate binding became Q-10, with default yes.
- **r2-7's optional re-run:** became Q-8, with default no.

I then set `status: approved` and moved the spec to revision 3.

**What I checked myself while revising:**
- **R-1 fix chosen.** I chose to exclude these IDs (D-29) rather than the reviewer's prefix-rule fix. It is smaller: no new rule kind, no extra test case, and no dependence on a source for the vendor's key prefix.
- **The key-leak mechanism, by read-only probe at HEAD.** `Runner._normalize_provider_and_model(None, id)[0]` returns `deepseek` for `deepseek/x` and `openai` for `openai/gpt-oss-120b`. It also returns `openai` for `OpenAI/x`: the match ignores case and takes no aliases. An unprefixed key binds to deepseek. `provider_for_model("deepseek/deepseek-chat")` is None, so r2's EC-28 example was wrong.
- **Groq models page (raw and text form).** `qwen/qwen3.8-27b` ($0.80 input / $4.00 output) is in the "Preview Models" table. That is Groq's only priced text model that D-29 leaves eligible, so Groq moves to rank 6 and Q-9 was added.
- **Cerebras model page (raw).** The only price record, ``pricing:{inputPrice:`$0.35 / M tokens`,outputPrice:`$0.75 / M tokens`}``, sits 457 bytes after `` modelId:`gpt-oss-120b` ``, with no other model ID between them. A one-quote binding is therefore impossible, which is why Q-10 exists.
- **Claude Code permission docs** (`permission-modes`, `permissions`, raw on 2026-10-16). Verified quotes:
  - auto mode is the starting mode from v2.1.283;
  - `acceptEdits` covers only the working directory and `additionalDirectories`;
  - "An allow rule won't match past an assignment of any other variable";
  - `bypassPermissions` is for isolated containers or VMs only;
  - the auto-mode classifier treats internal file paths in public-repo PR bodies as outbound content.
- **Checklist-path extraction command.** Run against the spec's own wiring table, it prints the 22 unique checklist paths.
- **Self-checks, all clean:**
  - 18 sections; only the three §12.3 rows start with a number;
  - no undefined or duplicate IDs;
  - every Markdown table keeps a constant GFM cell count;
  - both checklist checkers report `rows=33 problems=0`.

**Counts after r3:**
- G 4, NG 13, INV 26.
- AC 15 (AC-14 withdrawn), EC 61 (EC-1 withdrawn), FR 17 (FR-14 withdrawn), NFR 7.
- D 29, T 6, W 6.
- A 10 (A-10 withdrawn), Q 10. None is blocking.

## 9. Revision r4 (2026-10-16): alignment with the S2 tests

This was not a review round. I made the smallest edits that bring the spec into line with the 46 committed tests, covering the seven spec defects in the S2 report. They are recorded in §16 as rows s2-1 to s2-7. The status stays approved.

**How I checked that the edits fit the tests:**
- **The brief.** The brief test, `test_onboard_skill_contract.py::test_subagent_brief_carries_every_field_and_rule`, does not pin the PYTHONPATH wording. Rewording the brief therefore creates no new mismatch.
- **The PYTHONPATH rule.** The X7 test bans `export PYTHONPATH` in shell commands, and `export PYTHONPATH=` anywhere. AC-8 now says exactly that.
- **The spec's own checkers.** Both checklist checkers report `rows=33 problems=0`. The table check reports `table problems=0`, and `check_ids.py` is clean.
