# S4 findings verifier: provider-onboarding-skill

Stage: S4 findings verifier · Branch tip read: `d9021ee5` (implementation `32ca7991`; `d9021ee5` and `1144e198` add only `docs/spec` files) · Base: `origin/main` 845a4d9b · Output: `review.md` beside `spec.md` · Commits: none

## What this stage did

1. It merged the three S4 reviews (`S4-review-conformance.md` R-C1–R-C4, `S4-review-conventions.md` R-V1–R-V5, `S4-review-engineering.md` R-E1–R-E8) into one list.
2. It proved or refuted every Blocker and Major by its own execution. The reviewers' reproducers were inspected first and rerun only when they write nothing outside the scratchpad. The verifier added its own reproducers for each claim: a shared scratch clone, a scratch git repository, and mutation copies.
3. It ran a blind-spot check: a full simulated provider run of the wiring checklist through the real source-stage gate (V-9).
4. It calibrated severities against the brief's rules: weighted words; Blocker for a test gap only where `test-plan.md` claims the coverage; scope-adding fixes become Minor follow-ups.

Every reproducer lives in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/` (below, `<scratch>`). Each one cleans up after itself, and none writes inside the repository. `git -C <worktree> status --short` showed only `?? docs/spec/provider-onboarding-skill/review.md` after every run.

S2 pack on the real tree, for reference: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `46 passed in 0.88s`.

## Merge map

| Reviewer ID | Reviewer severity | Merged ID | Verifier result |
|---|---|---|---|
| R-C2 | Blocker | R-1 | Confirmed Blocker (weighted word "Never invent a URL"; INV-13) |
| R-V1 | Blocker | R-2 | Confirmed Blocker; its fix is endorsed |
| R-C1 | Blocker | R-2 | Same defect as R-V1, from the other side (§3.8 / A13); its fix is the runner-up |
| R-E2 (a)(b)(h)(i)(j) | Major | R-3 | Confirmed and **raised to Blocker**, because test-plan rows S5, X8, X9 and A5 (AC-13) claim exactly this coverage. Routed to the S2 author |
| R-V3 | Major | R-4 | Confirmed Major |
| R-C3 | Major | R-5 | Confirmed Major |
| R-E1 | Major | R-6 | Confirmed Major |
| R-V2 | Major | R-7 | Confirmed Major; fix (c) dropped as cosmetic |
| R-E2 (c)(d)(e)(k) | Major | R-8 | Confirmed Major (no test-plan row claims it). Routed to the S2 author |
| R-E2 (f) | Major | R-E2f | Downgraded to Minor follow-up |
| R-E2 (g) | Major | — | Refuted (behaviorally benign) |
| R-C4, R-V4, R-V5, R-E3, R-E4, R-E8 | Minor | same | Passed through as `trivial` |
| R-E5, R-E6 | Minor | same | Passed through as `follow-up` |
| R-E7 | Minor [scope-adding] | same | Passed through as `follow-up` |

Totals: 3 Blockers and 5 Majors confirmed, 10 Minors, 1 refuted, 1 downgraded. Verdict: **MERGEABLE AFTER FIXES**.

## Verifications

### V-1 → R-1 (R-C2): INV-13 is not stated where the procedure asks for URLs

Spec `spec.md:215`: "**INV-13** — The skill never invents a vendor, URL, price or model ID. Every URL in a provider PR is one the subagent opened during that run." The request weights "**Never** invent a URL, price, or model ID".

Command: `grep -n -i -E 'invent|opened|you fetched|never write a url'` over SKILL.md and provider-run.md.
- **SKILL.md.** Every hit is about PRs: `:22`, `:85` "the PRs this session opened", `:141` `PR_OPENED`, and `:188-203` output lines.
- **provider-run.md.**
  - `:23`, `:362`: outcome names.
  - `:50`: "The date in that line is the 'opened' date the PR cites for every fact from the page."
  - `:64`: "Record each fact as one line of `<evidence>/facts.md`".
  - `:132`, `:169`, `:177`: pricing and key-source dates.
  - `:330`: "a table with one row per fact".
  - `:333`: the signature line.
  - No line states the rule for URLs.

`:40`: "A fact is a base URL, chat path, auth scheme, environment variable, model ID, price, price unit, key prefix, tool support or structured-output tier. Nothing else from a page enters code or the PR." A documentation link is not a fact kind.

`:186`: "| D1 | `vidbyte/providers/README.md` | Endpoint And Auth Matrix; Official Provider Documentation | one row each (D-24) |". `:213`: "One row in each table, shaped like its neighbours". On `origin/main`, that table's header (`vidbyte/providers/README.md:91`) is `| Provider | API overview | Contract reference |`. Every provider run therefore writes two URLs per vendor that no rule ties to `<evidence>/fetch-log.txt`. FR-11's four checks (`SKILL.md:152-157`) do not read URLs.

Severity: Blocker. It breaks a user-weighted "Never" on a path every provider run takes. Fix: see review.md R-1. It interacts with R-V4, which changes the same D1 row.

### V-2 → R-2 (R-V1 + R-C1): A13 makes every run end `PROOF_FAILED gate-source`

The test (`tests/features/harness_threads/test_harness_threads_surface.py:224-232` on `origin/main`) compares the working tree against `merge-base origin/main HEAD` for `vidbyte/tools`, `vidbyte/lib/configs` and an old spec folder, and asserts that the diff is empty.

Reproducer: `bash <scratch>/s4ver/a13_probe.sh`. It makes a `--shared --no-checkout` clone under `<scratch>/s4ver/clone`, sets `origin/main` to 845a4d9b, and removes the clone at the end. Output, quoted:

```
== 1. twin: detached at the base, as provider-run.md section 8 builds it
merge-base: 845a4d9bd5f144b1e083b5dc3c76bff17c75b235
scoped run 1: 1 passed in 0.14s
scoped run 2: 1 passed in 0.14s
scoped run 3: 1 passed in 0.19s
failure-codes run: ...test_harness_threads_surface.py:193: AssertionError: assert 148 == 120 1 failed in 1.27s
== 2. provider branch: A1 member plus an A13 tier, committed (as section 7 commits before the gate)
scoped diff the test asserts empty: [vidbyte/lib/configs/structured_output.py ]
harness test file unchanged on the branch: exit 0
scoped run 1: ...test_harness_threads_surface.py:232: AssertionError: assert (['vidbyte/lib...ed_output.py'] == [] 1 failed in 0.14s
scoped run 2: (same) 1 failed in 0.14s
scoped run 3: (same) 1 failed in 0.14s
failure-codes run: ...:193: AssertionError: assert 148 == 120 1 failed in 1.22s
== 3. option A (R-C1): provider branch with A1 only, no A13
scoped run: 1 passed in 0.14s
== 4. option B (R-V1): twin at the base plus the field guide's one-line control edit, uncommitted
scoped run: ...:232: AssertionError: assert (['vidbyte/lib...ed_output.py'] == [] 1 failed in 0.14s
== clone removed
```

Reading against `provider-run.md:300-310`:
- The node fails all three reruns on the branch (`:301`), so it is not flaky.
- Its file is unchanged (exit 0), but the node passes 3 of 3 on `<worktree>-main` (`:305-307`), so the "fails on the twin" condition is false.
- That leaves `:310`: "Anything else ends the run `PROOF_FAILED gate-source`."

Frequency: the A13 tier is the norm, not an edge. `structured_output.py:37-49` on `origin/main` gives NATIVE_SCHEMA or JSON_MODE to Mistral, DeepSeek, GLM, Kimi and MiniMax. Of the six compatible siblings, only Meta is PROMPT_ONLY.

The field guide predicted this: `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/local-ci-verification.md:45-50`. The entry is "Two `harness_threads` surface tests fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports". It says "Do: Classify it as pre-existing. Prove it with a one-line edit to a `vidbyte/tools` file on a clean main worktree", and "Check: The control edit on main fails the same way". Spec §11 (`spec.md:729`) claims to apply `local-ci-verification.md`, but lists only its PYTHONPATH, tracked-files, MCP-flake and conflict-staging lessons, not this `harness_threads` entry.

V-9 confirms the claim end to end through the real gate.

### V-3 → R-3 (R-E2, claimed coverage): four S2 tests cannot fail for their claimed defect

The test-plan claims, quoted from `test-plan.md`:
- Row 35 (S5): "Qualify forgets the rule; a self-check line is missing".
- Row 32 (X8): "the known-red rule loses its detached twin, its unchanged-file check or its up-to-3 reruns".
- Row 20 (X9, AC-8): "… or counts the table-pinning contract test".
- Row 25 (A5, AC-13): "the cleanup or keep rule missing for an outcome".

The A5 test's own comment (`test_onboard_skill_acceptance.py:71-82`) says PROOF_FAILED, PUBLISH_FAILED and RESULT_UNVERIFIED keep the worktree "so unpushed work is never destroyed". The test checks only the names plus `keep|kept`.

Reproducer 1: `py -3.11 <scratch>/s4ver/mut2.py`, run from the worktree. It mutates a copy (`<scratch>/s4eng/real`, verified byte-identical to the worktree's two skill files with `cmp`) under `<scratch>/s4ver/mutant`. It then runs the pack with S2's own fixture-redirect plugin `<scratch>/s4eng/s2_harness.py`. Output:

```
[CONTROL unmutated] 46 passed in 0.94s
[S5 claim: Qualify forgets the D-29 rule (bullet clause and eligibility reading removed, probe kept)] 46 passed in 0.83s
[S5 control: self-check D-29 assert line deleted outright] FAILED test_onboard_skill_security.py::test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it | 1 failed, 45 passed in 0.84s
[X8 claim: known-red unchanged-file condition dropped (command kept as a log step)] 46 passed in 0.84s
[X8 control: unchanged-file command deleted from section 8] FAILED test_onboard_skill_commands.py::test_gate_commands_and_output_lines_are_the_repositorys_real_ones | 1 failed, 45 passed in 0.87s
[X9 claim: the contract test may be the mutation proof] 46 passed in 0.90s
[unclaimed: C9 template loses its Bearer assertion] 46 passed in 0.88s
[unclaimed: whole C9 template fence deleted] 46 passed in 0.85s
[unclaimed: back-pressure drops the union with this session's PRs] 46 passed in 0.84s
[unclaimed: PROOF_FAILED cleaned up (unpushed work deleted)] 46 passed in 0.83s
```

Note on the last row's label: it is a claimed case (A5 / AC-13). The mutation removes PROOF_FAILED from the keep line and adds it to the cleanup line.

Reproducer 2: the reviewer's `<scratch>/s4eng/mut.py`, inspected first (it writes only `<scratch>/s4eng/mutant`) and then rerun. Its rows for the claimed sub-items:

```
[D-29 qualify condition negated] 46 passed in 0.83s
[D-29 self-check line removed] 46 passed in 0.83s
[known-red: exclude when file CHANGED] 46 passed in 0.82s
[mutation: contract test counts] 46 passed in 0.80s
[cleanup deletes branch before clean check] 46 passed in 0.85s
```

Its three caught rows, `jev check: any number of lines`, `push forced` and `fetch dropped from pass`, fail as the reviewer reported.

The mechanism, read from the test files:
- S5 (`test_onboard_skill_security.py:125-137`) checks only that `_normalize_provider_and_model` appears in Qualify. The `qualify_ids.py` probe line satisfies that without the rule. In §6 it checks only for the fragment `Runner._normalize_provider_and_model(None`.
- X8 (`test_onboard_skill_commands.py:226-255`) checks the regex `diff\s+--quiet`.
- X9 (`:257-277`) checks `re.search(r"test_provider_keys_contract|\bC5\b", text)`, which any mention satisfies.

Severity: Blocker, by the brief's rule: the coverage is explicitly claimed, and the tests cannot fail for it. Route: the S2 test author, not the repair agent. The smallest assertions are listed in review.md R-3.

### V-4 → R-4 (R-V3): the C9 template has a 93-column comment

Command: `git show 32ca7991:.claude/skills/onboard-model-provider/references/provider-run.md | awk '/^[[:space:]]*#/ && length($0) > 72 {print NR": len="length($0)": "$0}'`. Output, the only line:

```
200: len=93:         # The gateway does not serve <s>, so the call is DIRECT, and only the <s> key leaves.
```

With `<s>` = `cerebras`, the line is 103 columns.

`comment-format.md:5`: "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too." `:8`: "Not a lint rule". The procedure's own `:148` says "`#` lines wrapped at 72 columns".

Tier: Major, as the reviewer rated it. The gate cannot catch it, and the owner has rejected this format before (PR #690), so every provider PR draws the same review comment. It is not a Blocker, because nothing computes wrongly.

### V-5 → R-5 (R-C3): the `-c` probes import from the launcher checkout

Reproducer: `bash <scratch>/s4ver/cwd_demo.sh`. It puts a decoy `vidbyte` package in a scratch "launcher" directory and removes it afterwards. Output:

```
== -c form, shell in the launcher checkout (provider-run.md:123 and :192 as written)
['', 'C:\\Users\\422mi\\vidbyte-repos\\worktrees\\vidbyte-sdk-provider-onboarding-skill']
launcher checkout (decoy)
== script form, same shell (how qualify_ids.py and the self-check run)
['...\\scratchpad\\s4ver\\cwd', 'C:\\Users\\422mi\\vidbyte-repos\\worktrees\\vidbyte-sdk-provider-onboarding-skill']
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py
== -c form after cd <worktree> (the fix)
['', 'C:\\Users\\422mi\\vidbyte-repos\\worktrees\\vidbyte-sdk-provider-onboarding-skill']
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py
```

`provider-run.md:16` (the procedure's own rule): "Every other command that uses a repository-relative path … starts with `cd <worktree> && `, because each shell call starts in another directory." Lines `:123` (`from tests.features.sdk_provider_keys import provider_keys_fixtures`) and `:192` (`from vidbyte.lib.agents.modality_detector import ModalityDetector`) do not follow it.

The orchestrator's subagent shell starts in the launcher checkout, so both lines import the launcher's tree. That tree is a real `Vidbyte-SDK` checkout, so the import succeeds silently against stale code.

Tier: Major. A fail-closed collision check (EC-33, D-13) becomes fail-open. The property test in the green run may still catch a collision with a proven fake, but as a `PROOF_FAILED` stop rather than the intended `DISQUALIFIED key-prefix-collision` skip.

### V-6 → R-6 (R-E1): a failed `git worktree add` is hidden

Reproducer: `bash <scratch>/s4ver/wt_race.sh`. It works in a scratch origin and clone under `<scratch>/s4ver/race`, which it removes. It runs `SKILL.md:107-111` verbatim, twice. Output:

```
== session A
Preparing worktree (new branch 'feat/provider-cerebras')
branch 'feat/provider-cerebras' set up to track 'origin/main'.
HEAD is now at dd98563 base
dd985634113598e7f6520f41733d2abe3df6fb8f
block exit 0
== session B (its skip walk ran before A's add)
Preparing worktree (new branch 'feat/provider-cerebras')
fatal: a branch named 'feat/provider-cerebras' already exists
dd985634113598e7f6520f41733d2abe3df6fb8f
block exit 0
== the cleanup block run while the worktree is in use by the other session (...)
error: cannot delete branch 'feat/provider-cerebras' used by worktree at '.../race/checkout-onboard-cerebras'
cleanup tail exit 0
```

Session B records A's SHA as its own `<base>` and proceeds in A's worktree. That falsifies spec EC-52's "the second push is refused" backstop for two sessions in one clone. It also falsifies the skill's own promise at `SKILL.md:207`: "GitHub then refuses the second push, and that session stops with `PUBLISH_FAILED`". Either orchestrator's cleanup (`SKILL.md:173-178`) then removes the other's worktree. The cleanup also deletes the evidence directory after `branch -D` fails.

Tier: Major. It needs two sessions in one clone, which `SKILL.md:207` ("Run one session at a time") discourages but does not prevent, and when it happens it destroys data silently.

### V-7 → R-7 (R-V2): the response path and usage keys are never checked

On `origin/main`:
- `vidbyte/agents/pricing/compatible.py:41-58`: `from_usage_payload` reads only `prompt_tokens`, `completion_tokens`, `total_tokens`, and returns `None` when all are absent.
- `vidbyte/providers/README.md:558-561`: "The Responses API renamed OpenAI's fields … Because `compatible.py`, `xai.py`, and `openrouter.py` target OpenAI-*compatible* surfaces, a vendor behind those adapters may emit either naming depending on which OpenAI API it mirrors."
- `:608-612` ("Adding A Provider", step 1): "record, in the tables above: base endpoint, auth header style, request fields sent, the response path to generated text, and the exact usage key names."
- Field guide `provider-api-contracts.md:5`: "check every field type … and response shape against them". `:7`: "Check: A scripted-transport test per documented answer example".

The skill's side:
- `provider-run.md:40` closes the fact kinds ("Nothing else from a page enters code or the PR"), so neither item can be recorded.
- §3.2 Dialect (`:84`) checks only Bearer, the fixed base URL and the chat path.
- Row A2 maps the vendor to `ChatCompletionUsage`, and C9 asserts only the request.

Scope judgment: **not** scope-adding. Spec §11 (`spec.md:727`) lists `provider-api-contracts.md` as an applied entry, and §12.4 binds the folder READMEs of edited folders. The check comes from sources the spec already adopts.

Tier: Major, not Blocker. A vendor that mirrors the Responses naming still returns text, so the run's outcome is not wrong. Usage and cost are silently `None`, which breaks the SDK's pricing promise for that provider.

Fix (c), adding the provider to `_CHAT_PROVIDERS`, is cosmetic: the C9 test asserts nothing about usage. The verifier drops it from the smallest fix.

### V-8 → R-8 (R-E2, unclaimed coverage)

From the same two reruns:
- `[unclaimed: C9 template loses its Bearer assertion] 46 passed`
- `[unclaimed: whole C9 template fence deleted] 46 passed`
- `[C9 wire test accepts x-api-key] 46 passed`
- `[backpressure ignores this session's PRs] 46 passed`
- `[format-bound without first-party statement] 46 passed`

X4 (`test_onboard_skill_commands.py:155-172`) checks only that the phrase "this session" appears. The test-plan X4 row claims INV-4, INV-5, T-4 and EC-10, not the INV-3/EC-9 union. No row claims the C9 template or D-13's first-party rule.

Tier: Major. These are the user's key-safety and back-pressure outcomes, but no row claims the coverage, so the brief's rule caps them below Blocker.

### V-9 [verifier blind-spot check]: a full simulated provider run through the real gate

Question: do any wiring rows besides A13 break the source stage? The reviewers checked rows one at a time, and the scout never ran the gate on a wired branch.

Reproducer: `py -3.11 <scratch>/s4ver/fullsim.py`, about 5 minutes. It makes a `--shared` clone under `<scratch>/s4ver/fclone` at 845a4d9b and runs `scripts/run_ci.py --stage source` as a baseline. It then applies every applicable checklist row for a Cerebras-shaped vendor: no key rule (C4 "any" row), one model `gpt-oss-120b`, the JSON_MODE tier, with the rows listed in review.md. It refreshes the vintage lock (B3), runs the §6 self-check, commits as §7 does, and runs the source stage again. Output:

```
== baseline: run_ci exit 1; log baseline-source.log
   SDK-LINT: PASS
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
   =========== 1 failed, 6245 passed, 16 skipped in 102.66s (0:01:42) ============
== B3 refresh-lock exit 0: Refreshed lint/pricebook_vintage_lock.json: PRICING_AS_OF 2026-10-11 -> 2026-10-17.
== self-check exit 0: self-check passed: cerebras, 1 models
== commit exit 0; changed: [abridged by the verifier; 20 files: README.md, lint/pricebook_vintage_lock.json, 7 test files, structured_output.py, jev.py, runners.py, model_modality.py, model_provider.py, registries/README.md, models.py, pricing.py, providers/README.md, providers/__init__.py, compatible.py]
== wired: run_ci exit 1; log wired-source.log
   SDK-LINT: PASS
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
   ============ 2 failed, 6252 passed, 16 skipped in 98.44s (0:01:38) ============
== clone removed
```

The wired failure, from `<scratch>/s4ver/wired-source.log:606-611`: `AssertionError: assert (['vidbyte/lib...ed_output.py'] == []` at `test_harness_threads_surface.py:232`.

Result:
- No new finding. Apart from R-2's node and the known-red failure-codes test, every row passes lint and the full source suite, including 8 new tests. That is 6254 tests collected against 6246; the scoped node moved from passed to failed.
- The two failures sit in one file but do not interact. failure_codes fails on both the branch and the twin and is excluded legitimately; the scoped node is R-2.
- This is recorded in review.md under "What the implementation gets right". The script's own removal left an empty `fclone/.git/objects` tree behind, which the verifier then deleted.

Other blind spots looked at, with no finding:
- **The root-`__all__` import test in the same harness file.** It compares the root `__all__` against the merge-base. The root `__all__` is a literal with no provider classes, and A12 edits `vidbyte/providers/__init__.py`, not the root, so it stays green. V-9 confirms this.
- **Whether R-E6's `sk-`/`eyJ` gap reaches a live constant.** `provider_keys.py` on `origin/main` holds `OPENAI_KEY_PREFIX = "sk-"`, `OPENAI_JWT_PREFIX = "eyJ"` and `RESERVED_PREFIXES = ()`. The gap is real but needs an unusual vendor prefix, so it stays a Minor follow-up.

## Adjudications

1. **R-2 fix: R-V1's exclusion or R-C1's "no A13"?** R-V1's, narrowed. The field guide prescribes it.
   - **Preserves the 33 refs.** W1 still holds, because no checklist row changes.
   - **Cannot hide a regression.** The node's only assertion is the scoped diff, and the exclusion requires that diff to be exactly A13's file and the twin's control edit to fail identically (V-2, step 4).
   - **Runner-up, R-C1.** Never apply A13. It is equally small and proven (V-2, step 3: `1 passed`), but it ships every vendor as PROMPT_ONLY and needs a follow-up PR per vendor. In effect it drops checklist row A13, and §3.8 then needs a spec deviation.
   - **When the choice flips.** Choose R-C1 if the person wants no new exclusion text in §8.3.
   - **Interaction.** The exclusion is per node, and the failure-codes node follows the existing rule. Neither fix may exclude the whole file, because it also holds the import-surface test.
2. **R-E2 rating.** It is split by the brief's rule. Sub-items whose coverage a test-plan row or the test's own comment claims become Blocker R-3: (a) and (b) under S5, (h) under X8, (i) under X9, (j) under A5/AC-13. Unclaimed sub-items stay Major as R-8: (c), (d), (e), (k). (f) is downgraded: an inverted vintage stops every session at once with `VINTAGE_DEFERRED`, loudly, and writes nothing. (g) is refuted: all three dispositions skip, so the precedence changes only the ledger label. Both R-3 and R-8 route to the S2 author.
3. **R-1 (R-C2) severity.** Blocker. The request weights "Never", INV-13 restates it, and D1 makes every run write URLs that no rule binds to the fetch-log. The fix is two sentences, so the rating costs little.
4. **R-7 (R-V2) scope.** In scope, because the control comes from sources the spec adopts (§11, §12.4). Major, not Blocker: the failure is missing usage, not wrong text.
5. **R-4 (R-V3) tier.** Major, as rated: a known owner-rejected pattern, uncatchable by the gate, and repeated in every provider PR.
6. **R-E7.** Tagged `[scope-adding]`, because a fifth FR-11 check is a control neither the spec nor the request contains, so it is a Minor follow-up.
7. **Ordering.** Within each tier, the smallest fix comes first.
   - Blockers: R-1 is two sentences. R-2 is one bullet plus a spec citation. R-3 is four test assertions.
   - Majors: R-4 wraps one line. R-5 adds two prefixes. R-6 adds `&&` and one sentence. R-7 adds two procedure edits and two spec lines. R-8 adds three test assertions across files.

## For the repair agent and the S2 author

- **Re-read before each fix:**
  - R-2: field guide `local-ci-verification.md:45-50` and spec D-15 (`spec.md:422`), EC-39 and EC-40.
  - R-4: `comment-format.md`.
  - R-7: `provider-api-contracts.md` and `vidbyte/providers/README.md` "Usage Key Divergence" and "Adding A Provider".
  - R-5: the procedure's own `:16` rule.
  - R-1: spec INV-13 (`:215`) and D-24 (`:431`).
- **Spec amendments that go with the procedure edits:** D-15 and §11 for R-2; D-11 (`:418`) and INV-9 (`:211`) for R-7; D-24 if R-V4 is taken.
- **Fixes that touch the same text:**
  - R-1 and R-V4 both touch row D1 (`provider-run.md:186`, `:213`).
  - R-2 and R-E4 both touch the §8.3 twin (`:300-310`). Make the control edit after the other known-red twin reruns, and add `$WORKTREE-main` to skip rule (d) and to the rollback commands.
  - R-3's new assertions should pin the final wording of any sentence R-2 or R-7 rewrites.
- **Re-verify** with the S2 pack command (`46 passed` expected), then rerun `mut2.py` and `mut.py`. Every "claim" and "unclaimed" row must then fail, and CONTROL must stay `46 passed`. If an edit changes an anchor sentence, the script prints `SKIPPED`; update the anchor to the new text.
