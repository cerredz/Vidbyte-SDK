LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the procedure's commands run as written in Git Bash, the D-29 key-safety check works, and all 46 S2 tests stay green inside a simulated provider PR. But the worktree-add block hides a failed write, so two sessions in one clone share a worktree. The test pack also lets 11 of 14 plausible safety defects through, including an inverted D-29 rule and a C9 wire test with no auth assertion.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The D-29 key-routing check works.** I ran the `qualify_ids.py` probe from `references/provider-run.md` §3, copied verbatim to scratch, with `PYTHONPATH=<worktree>`. It marks `deepseek/x` → `derived provider deepseek` and `openai/gpt-oss-120b` → `derived provider openai` (both ineligible). It marks `meta-llama/Llama-3.3-70B` and `qwen/qwen3-32b` → `derived provider None; catalogued under None` (eligible). It also fails closed on `MiniMaxAI/MiniMax-M2`, which carries the substring hint token `xai`. The §6 self-check line `assert Runner._normalize_provider_and_model(None, model)[0] is None` re-proves the rule after wiring.
- **The S2 tests stay green inside provider PRs.** I applied a realistic Cerebras wiring to a `git archive` copy of the branch: the A1 member, A2, A3, A4, A5, A6, A8, A11 and A12, a B1 block, B2 bumped to 2026-10-17, the C4 "any" row, the C7 fake, and the verbatim C9 template. In that tree the whole S2 pack passes (`46 passed`), the verbatim §6 self-check prints `self-check passed: cerebras, 1 models`, and the verbatim C9 test passes. No S2 test pins members, the vintage or rows, so a provider PR does not hit `PROOF_FAILED` because of this pack.
- **Command blocks are portable and fail closed where it matters.** The pass-top `sed` reads print `2026-10-11` and the 14 members from `origin/main` blobs. The FR-11 `diff-paths` pipeline prints every non-checklist path, and with an empty `sed` result it prints every path, so it fails closed. The text-form command bridges Groq's markup-split rates (`qwen/qwen3.8-27b 450 $0.80 input $4.00 output`), and the `grep -F -b -o -f` quote check finds Cerebras' two-quote binding 457 bytes apart. A CRLF quote file still matches. `PRICING_AS_OF` is compared in UTC on both sides, and C010 never compares with today (`lint/rules/c010_pricebook_vintage_bump.py` header: "Do not … compare against today's date"), so a local/UTC rollover cannot create a vintage C010 rejects.
- **Back-pressure is re-read from live GitHub at the top of every pass**, counting the union with this session's PRs (`SKILL.md` lines 72–85). Forks are filtered by `head.repo.full_name`, and the per-slug query uses the exact `head=cerredz:` ref.

FINDINGS (ranked, most severe first, max 15)
R-E1 [Major] [failure modes / concurrency] .claude/skills/onboard-model-provider/SKILL.md:107-111 (with :66 "Run each fenced block as one shell call") — A failed `git worktree add` is hidden by the next command, so a second session adopts the first session's worktree, and EC-52's "GitHub refuses the second push" backstop does not hold.
  Evidence: I ran the block as written, twice, in a scratch repo (`.../scratchpad/s4eng/wtdemo`), simulating two sessions in one clone that both pass the skip checks before either adds the worktree. The second run printed `fatal: a branch named 'feat/provider-cerebras' already exists`, then `8dc3c8297d55acbc1d5cfff69698c1a70218bc66`, then `block exit 0`. The block's last command, `git -C "$WORKTREE" rev-parse HEAD`, succeeds against the first session's worktree. SKILL.md defines no STOP reason for a failed worktree add. The cleanup block at :173-178 has the same shape: a failed `worktree remove` is followed by `branch -D` and then `rm -rf` of the evidence directory.
  Failure: two sessions in one clone (two terminals in the same checkout, the natural way to "run it twice") + a race between the skip check and the add → session B records session A's HEAD as `<base>` and starts a second subagent in the same worktree on the same branch. Then:
    - two agents edit and commit at once;
    - B's later push of the shared branch is a fast-forward of A's pushed commit, so GitHub accepts it and changes A's PR after A's FR-11 verification;
    - either orchestrator's `git worktree remove --force` deletes the other's in-flight work.
  Spec EC-52 and T-1 assume each session has its own branch and that the second push is refused.
  Smallest fix: make the add fail visibly and stop on it. Write `git worktree add -b "feat/provider-$SLUG" "$WORKTREE" origin/main && git -C "$WORKTREE" rev-parse HEAD`, and add a sentence: "If the add fails, record `local-branch` for the vendor and continue the walk" (or stop with an existing reason). Chain the cleanup the same way with `&&`.
  Spec IDs: EC-52, T-1, INV-2, INV-8, D-3

R-E2 [Major] [test quality] tests/features/onboard_model_provider_skill/test_onboard_skill_security.py:131-132, test_onboard_skill_commands.py:171 — The S2 pack lets through 11 of 14 plausible defects in the real skill text, including three that break the user's key-safety outcome. Two test-plan claims do not hold.
  Evidence: `.../scratchpad/s4eng/mut.py` applies each defect to a copy of the real SKILL.md and provider-run.md and runs the pack through S2's own `s2_harness.py`. Unmutated, the copy gives `46 passed`. Defects that still give `46 passed`:
    - (a) the D-29 condition in Qualify inverted to "`[0]` is not None";
    - (b) the self-check `assert … [0] is None` replaced by a bare call (the S5 fragment `Runner._normalize_provider_and_model(None` is still present);
    - (c) the C9 template's `self.assertEqual(header(sent, "authorization"), f"Bearer {K_<E>}")` deleted;
    - (d) the same line rewritten to assert an `x-api-key` header;
    - (e) back-pressure reduced to "the numbers printed", dropping the union with this session's PRs (X4 only checks that the phrase "this session" appears in the section, and `this session's ledger` satisfies it);
    - (f) the vintage comparison inverted;
    - (g) the skip precedence reversed;
    - (h) the known-red rule rewritten to "exclude it when its file is changed";
    - (i) "One may be `test_provider_keys_contract.py`" (X9 checks only that the name appears);
    - (j) cleanup always run, before the clean check;
    - (k) FORMAT_BOUND allowed on "an example key".
  Only the jev-diff, forced-push and dropped-fetch defects were caught. The test plan's S5 row claims "Qualify forgets the rule; a self-check line is missing → caught"; it does not catch (a) or (b). No test covers EC-9 or INV-3's union.
  Failure: a later edit to the skill inverts D-29, drops the Bearer assertion that is the user's "key reaches the vendor's endpoint in its auth header" proof, or drops the session-PR union (EC-9 overshoot). The gate stays green and every later provider run follows the broken rule.
  Smallest fix: pin the safety sentences by content, not by fragment presence:
    - Qualify contains `_normalize_provider_and_model(None, <id>)[0]` is None;
    - §6 contains `assert Runner._normalize_provider_and_model(None, model)[0] is None`;
    - the C9 fence contains `header(sent, "authorization")` and `Bearer {K_<E>}`;
    - `## Each pass` names "union" together with "this session opened";
    - the known-red bullet contains "unchanged" next to `diff --quiet`;
    - the mutation bullet contains "outside `test_provider_keys_contract.py`".
  Then re-run `mut.py` and expect all 14 defects killed.
  Spec IDs: D-29, INV-3, INV-4, FR-4, EC-9, INV-15, D-15, AC-7, AC-8 (test-plan rows for D-29 and INV-4)

R-E3 [Minor] [error handling] .claude/skills/onboard-model-provider/SKILL.md:78-79, 91-92 — The two `gh api` reads that enforce weighted rules ("no changes" at 3 or more open PRs; closed-unmerged "skip forever") have no exit-code signal, unlike the `ls-remote`, `show-ref` and `test` lines beside them.
  Evidence: I ran the per-slug block with `GH_TOKEN=invalid-token-for-review`. gh printed the error body `{"message": "Bad credentials", … "status": "401"}` on stdout, then `remote-branch exit 2 / local-branch exit 1 / paths exit 1`, and the block exited 0 (`block exit 0`). With `--jq`, an HTTP error skips the filter, so "no `#n` line" and "query failed" differ only in free text.
  Failure: a transient 5xx, rate limit or expired token during the per-slug read, misread as "no PR" → a closed-unmerged vendor is researched and opened again. During the open-PR read → back-pressure is undercounted.
  Smallest fix: append `; echo "prs exit $?"` to both gh lines, and state that a non-zero exit is `NETWORK_BLOCKED - api.github.com <status>` (the rule already exists at :83).
  Spec IDs: INV-4, INV-5b, INV-20, request §D "skip it forever", "makes no changes"

R-E4 [Minor] [failure modes / crash recovery] .claude/skills/onboard-model-provider/SKILL.md:95, :180; references/provider-run.md:305-307 — The `-main` twin is in neither skip rule (d) nor the person's cleanup commands, so a crash inside section 8 leaves a registered worktree that breaks the vendor's next run.
  Evidence: skip rule (d) tests only `test -e "$WORKTREE" || test -e "$WORKTREE-evidence"`. The rollback at :180 is "the three commands above": `worktree remove` of `$WORKTREE`, `branch -D`, and `rm -rf` of the evidence directory. provider-run.md:305 runs `git -C <worktree> worktree add --detach <worktree>-main <base>`, with no handling if that path already exists.
  Failure: the session is interrupted during the known-red re-confirmation → the person runs the three documented commands → the next session reselects the vendor → section 8's `worktree add --detach` fails on the existing `-main` path → the outcome is undefined (most likely `PROOF_FAILED gate-source` for a cause outside the vendor).
  Smallest fix: add `|| test -e "$WORKTREE-main"` to skip rule (d), and `git worktree remove --force "$WORKTREE-main"` to the documented cleanup.
  Spec IDs: INV-5d, INV-8, D-8, EC-55

R-E5 [Minor] [failure modes / known-red rule] references/provider-run.md:301 — "Flaky" means "passes when rerun alone", so a failure the provider causes through test ordering or state leaks is waved through.
  Evidence: `Rerun it up to 3 times on the branch with cd <worktree> && PYTHONPATH=<worktree> <py> -m pytest '<node>' …. A pass on any rerun means the test is flaky … and it does not block.` The rerun runs the node in isolation, not in the context where it failed.
  Failure: the provider's new test leaks state (for example a class attribute or environment variable that is not restored), and that state breaks an unchanged test later in the full source stage → the victim passes alone, is labelled flaky, the gate counts as passed, and the PR ships a regression. This contradicts request §C: "full gate passes, with known-red tests excepted".
  Smallest fix: before calling a node flaky, rerun its whole file on the branch. Or require that a flaky node's file is unchanged and that it also fails at least once on `<worktree>-main`, the evidence the deterministic branch of the rule already uses.
  Spec IDs: D-15, EC-41, INV-15

R-E6 [Minor] [security / misroute] references/provider-run.md:119-124 — The collision check compares a new prefix P with `KEY_FORMATS`, `RESERVED_PREFIXES` and the fixture fakes, but not with table A's `OPENAI_KEY_PREFIX` (`sk-`) and `OPENAI_JWT_PREFIX` (`eyJ`). Its secondary-source arm is empty for every "any" vendor.
  Evidence: the gitleaks config the procedure cites (S1's copy, `.../scratchpad/gitleaks.toml`) has no rule for deepseek, kimi/moonshot, minimax, glm or mistral, and only a generic `jwt` rule. EC-34 covers only P equal to `sk-` or `eyJ`, or a prefix of them, not a P that extends them. The C6 swap pairs are `K_UNPROVEN` and `K_SK_UNPROVEN`, never `K_OPENAI_JWT`. I added a table-F rule `(CEREBRAS, ("eyJ0eXAiOi",), …)` to the matcher at run time in scratch and called `match` on an OpenAI workload-identity token (`[jwt], primary='openai'`):
    - before the rule: `{'openai': 'eyJ0eX'}`;
    - after: `refused: api_keys holds keys for cerebras but none for openai`.
  This is not a fixture fake: K_OPENAI_JWT starts with `eyJhbGciOi`.
  Failure: a vendor whose first-party docs show JWT-shaped keys (or a P that extends `sk-` with no hyphenated tag) passes all three collision arms → OpenAI tokens are proven as the new vendor's keys and refused in every OpenAI configuration. That is the "refused not swapped" family the user's method names.
  Smallest fix: add "P and `sk-` or `eyJ` overlap, unless P adds a character that OpenAI, DeepSeek and Kimi keys never have at that position (as `sk-ant-` does)" to the overlap arm, and add the pair `K_<E>` + `K_OPENAI_JWT`, in both orders, to the C6 swap case.
  Spec IDs: D-13, EC-33, EC-34, R-6 (r1)

R-E7 [Minor] [security / T-2] [scope-adding] .claude/skills/onboard-model-provider/SKILL.md:152-157 — A prompt-injected or confused subagent can weaken an existing vendor's key rule, and nothing but the person's review notices. `jev.py` (the managed set) gets a machine check; `provider_keys.py` (the user's key-safety outcome) does not.
  Evidence: FR-11 checks only the paths, added files, the `jev.py` one-line diff and the gate words in the body. `vidbyte/lib/registries/provider_keys.py` and its pin `test_provider_keys_contract.py` (C5) are both checklist paths, so editing an existing rule together with its pin passes checks (2) to (4). Mutation checks cover only new rules (provider-run.md:270).
  Failure: an injected vendor page says, for example, "remove ANTHROPIC from FORMAT_BOUND_PROVIDERS" → the subagent does it and updates C5 → the gate is green and FR-11 passes → only the person's review stands between that PR and an `--admin` merge.
  Smallest fix (follow-up for the user, because it adds a control the spec does not have): a fifth verification that every line removed from `provider_keys.py` reappears in an added line whose members are a superset.
  Spec IDs: T-2, FR-11, D-28

R-E8 [Minor] [failure modes / PR body] references/provider-run.md:338 — The local-path guard `grep -n -i -F … -e "$(id -un)"` matches ordinary words when the user name is short or common, and no outcome is defined when it keeps matching.
  Evidence: `-i -F` treats the login as a case-insensitive substring. §9 requires the body to list "the node IDs that newly failed" and every "excluded or flaky node". In a container whose user is `node` (the Node-based containers that the `bypassPermissions` advice points to), the guard always prints a match. The same happens for logins such as `test` or `dev`. Section 9 defines `PUBLISH_FAILED` only for push and PR failures.
  Failure: the guard can never print `grep exit 1` → the subagent stalls, rewrites the body arbitrarily, or skips the guard.
  Smallest fix: use `grep -w` for the login, or match only path-shaped strings (`/$(id -un)/`), and name an outcome for a body that cannot be cleaned (for example `PUBLISH_FAILED pr body-path`).
  Spec IDs: D-16, INV-16 (spirit), §12.4 "no absolute local path"

VERIFIED CLAIMS:
- Held: S3 "46 S2 tests pass" → I got `46 passed in 0.97s` at 1144e198, and it holds in the simulated provider tree.
- Held: S3 "the brief is byte-identical to §8.5" → `diff` of the spec block and the SKILL.md block printed nothing ("brief identical").
- Held: S3 "the 33-row wiring table is byte-identical to spec §12.3" → `diff` printed nothing ("wiring identical"). Every C/B-row symbol still exists on `origin/main` (`git grep -c` returned 1 or more for all 8 test symbols).
- Held: S3 "`git diff 8e9b8b7f HEAD -- tests` is empty" and "nothing under vidbyte/ lint/ scripts/ .github/ or ci-settings changed" → `git diff --quiet` exited 0 for both.
- Held: spec AC-1 behavior half → I re-ran the preflight and pass-top reads, all except `git fetch`, which writes refs: `true`, `py: python`, vintage `2026-10-11`, `date -u` `2026-10-17` while local time was 2026-10-16 22:01 EDT, no open provider PR, 14 members, cerebras and groq `remote-branch exit 2 / local-branch exit 1 / paths exit 1`.
- Held: FR-11 check (2) → the `grep -vxF -e "$(sed …)"` pipeline over `72a4ade1..32ca7991` printed exactly the 22 non-checklist paths. The `sed` emits the 33 Path cells with no stray characters, even on CRLF input, because `.*` absorbs `\r`.
- Held: the D-29 probe on the four briefed IDs (see the first strength bullet).
- Held: the self-check template and the C9 template execute (see the second strength bullet).
- Held: the green run's file set is green on base → `448 passed` on an `origin/main` (845a4d9b) snapshot. A1 alone keeps it collectable and green (`448 passed`), so red-first depends only on the new tests, as §4 intends.
- Held: no time-zone defect → C010 and the tests never compare `PRICING_AS_OF` with today (grep over tests/, lint/ and scripts/ found nothing). Both sides use UTC.
- Held: no tracked `.pyc` that a probe could dirty → `git ls-files '*.pyc'` printed 0, and `.gitignore` has `__pycache__/`. The DISQUALIFIED clean check is therefore not tripped by imports.
- Did not hold: test-plan S5 "Qualify forgets the rule; a self-check line is missing" (R-E2 (a) and (b)).
- Did not hold: test-plan X4 as a guard for the session-PR union (R-E2 (e)).
- Did not hold: spec EC-52 "the second push is refused" when both sessions run in one clone (R-E1).

COMMANDS RUN:
- `PYTHONPATH=<wt> py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `46 passed in 0.97s`
- Preflight: `git rev-parse --show-toplevel` → `C:/Users/422mi/…/vidbyte-sdk-provider-onboarding-skill`; `gh api repos/cerredz/Vidbyte-SDK --jq .permissions.push` → `true`; the probe loop → `py: python`
- Pass top (fetch skipped): vintage `2026-10-11`; `date -u +%F` → `2026-10-17`; open-PR read → no line, `open exit 0`; members → `openai … typesafe`, `members exit 0`
- Per-slug walk for cerebras and groq → `prs exit 0`, `remote-branch exit 2`, `local-branch exit 1`, `paths exit 1`
- `PYTHONPATH=<wt> python <scratch>/probes/qualify_ids.py deepinfra 'deepseek/x' 'openai/gpt-oss-120b' 'meta-llama/Llama-3.3-70B' 'qwen/qwen3-32b' …` → deepseek / openai / None / None, and `MiniMaxAI/MiniMax-M2: … hint tokens ['xai']`
- FR-11 `diff-paths` pipeline with `CLAUDE_SKILL_DIR` set → 22 lines, `grep exit 0`
- The text-form command on Cerebras and Groq raw pages → exit 0. `grep -F -b -o -f` → `cerebras.txt:266062:modelId:`…`` and `266519:pricing:{…}` (457 bytes apart); `groq.txt:9490:qwen/qwen3.8-27b 450 $0.80 input $4.00 output`
- `py -3.11 <scratch>/s4eng/mut.py` → 11 of 14 defects `46 passed`; jev-diff, forced push and dropped fetch killed
- `<scratch>/s4eng/sim_provider.py` + `sim_wire.py`, then the S2 pack in the sandbox → `46 passed in 1.45s`; self-check → `self-check passed: cerebras, 1 models`; C9 → `2 passed, 17 deselected`
- Green-run set on an origin/main snapshot → `448 passed in 3.29s`; with only A1 added → `pytest exit 0`, `448 passed`
- Scratch-repo worktree-add demo → second run `fatal: a branch named 'feat/provider-cerebras' already exists` … `block exit 0`
- Per-slug block with an invalid token → error JSON on stdout, `block exit 0`; the open-PR read alone → `gh: Bad credentials (HTTP 401)`, `gh exit 1`
- Run-time `eyJ0eXAiOi` table-F probe → before `{'openai': 'eyJ0eX'}`, after `refused: api_keys holds keys for cerebras but none for openai`
- `git status --short` in the worktree → clean, apart from the parallel reviewers' report files (`S4-review-conventions.md`)
