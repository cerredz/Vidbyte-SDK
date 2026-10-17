# S6 PR author report: provider-onboarding-skill

Stage: S6 PR author · Worktree `<worktree>` (`C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill`) · Branch `feat/onboard-model-provider-skill` · Start 451478b0 · Docs commit b726c6f8 (pushed `451478b0..b726c6f8`, fast-forward) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1175 (draft, left a draft)

`<scratch>` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad`. This stage's files are in `<scratch>/s6/`:

- `ac1_run.py` and `ac1_out.txt`: the AC-1 run.
- `clone/`: the shared clone.
- `dist/` and `package.log`: the package re-run.
- `flow.mmd`, `render.cjs` and the `*.png` files: the mermaid renders.
- `pr-body.body` and `pr-body.remote`: the body sent, and the body GitHub stored.

No file under `.claude/`, `tests/`, `vidbyte/` or `REPO_MAP.md` changed: `git diff --quiet 451478b0 HEAD -- .claude tests REPO_MAP.md vidbyte` exits 0.

## What the code does, in my own words

`/onboard-model-provider` is a manual-only project skill. A person types it in a Claude Code session in a clone. That session becomes the orchestrator.

**Preflight.** It runs six checks once: a git repo, `origin` is `cerredz/Vidbyte-SDK`, `gh` has push rights, a git e-mail, a Python 3.11+ interpreter with the dev extras (probed as `python`, then `python3`, then `py -3.11`), and the Agent tool. The first failure stops the session as `PREREQ_MISSING`.

**Each pass.**

1. It fetches `origin/main`.
2. It reads main's `PRICING_AS_OF` and today's UTC date, and stops `VINTAGE_DEFERRED` unless the pricebook date is earlier.
3. It counts the open same-repo `feat/provider-*` PRs, together with those it opened itself, and stops `BACKPRESSURE` at 3.
4. It walks ten ranked seed vendors and takes the first one that is not a member and has no PR in any state, no remote or local branch, and no leftover worktree, `-evidence` or `-main` path. It also skips a vendor that already has an outcome in this session's ledger.
5. Its first write is `git worktree add -b feat/provider-<slug> <checkout>-onboard-<slug> origin/main`. A failed add records `local-branch` and moves on.

**The subagent.** The orchestrator hands the vendor to one fresh general-purpose subagent with a 13-line brief and waits for a 6-line result block. The subagent follows `references/provider-run.md`:

1. It saves each first-party page raw with `curl`, keeping a UTC fetch log and a text form, and backs every fact with a verbatim quote that `grep -F` finds at a byte offset.
2. It qualifies the vendor through eight checks, any of which can disqualify it before an edit: OpenAI-compatible chat completions with the right response and usage names, a fixed endpoint, model IDs that cannot misroute a key, flat USD per-1M prices, the key-prefix decision with its cross-vendor collision check, and others.
3. It writes red-first tests and wires the 33-row checklist.
4. It proves the change: a self-check, a commit, a green run, a mutation check per new key rule, and the source and package stages with a bounded known-red rule.
5. It passes a local-path guard on the PR body, pushes once and opens one PR, ready for review.

**Checking the result.** The orchestrator never takes the result on trust:

- A `PR_OPENED` result passes four checks: the PR read by number, the changed paths against the checklist with no added file, `jev.py` changed by one added line, and the gate lines in the body.
- A `DISQUALIFIED` or `NETWORK_BLOCKED` result must leave the worktree at its base.

Then it cleans up and loops. `PROOF_FAILED`, `PUBLISH_FAILED` and `RESULT_UNVERIFIED` stop the session and keep the worktree. Every STOP prints the ledger. The orchestrator itself makes no GitHub write.

## The snippet, run (spec §4, AC-1 behavior half)

**How it was run.**

- `git clone --quiet --shared --branch feat/onboard-model-provider-skill <worktree> <scratch>/s6/clone`, then `git -C <scratch>/s6/clone remote set-url origin https://github.com/cerredz/Vidbyte-SDK.git`.
- `py -3.11 <scratch>/s6/ac1_run.py <worktree>/.claude/skills/onboard-model-provider/SKILL.md <scratch>/s6/clone`. The script reads the one preflight `sh` block and the first two `## Each pass` `sh` blocks from SKILL.md, and asserts that the third block, the only one holding `git worktree add`, is never run. It runs the commands through Git Bash.

**Output** (`<scratch>/s6/ac1_out.txt`, started 2026-10-17T22:31:35Z):

- Preflight:
  - `git rev-parse --show-toplevel` printed the clone path, exit 0.
  - `git remote get-url origin` printed `https://github.com/cerredz/Vidbyte-SDK.git`, exit 0.
  - The `gh api` permissions read printed `true`, exit 0.
  - `git config --get user.email` exited 0; the address is withheld.
  - The probe printed `py: python`, exit 0.
- Pass top, as one shell call (shell exit 0): `2026-10-11`, `2026-10-17`, `prs exit 0`, then the members, one per line: `openai anthropic gemini xai deepseek glm minimax kimi meta mistral openrouter elevenlabs playai typesafe`.
- Walk:
  - Rank 1 cerebras gave `prs exit 0` (no PR line), `remote-branch exit 2`, `local-branch exit 1` and `paths exit 1`, so it is the **first pick**.
  - Ranks 2 to 10 were read after the pick, for information only, and each gave the same four lines.

**Afterwards.**

- The clone's `git status --short` was empty, and its `origin/main` was 6f5a7310.
- In the shared repository, `refs/remotes/origin/main` (6f5a7310), the branch (451478b0) and the three historic `feat/provider-*` local branches were identical before and after (`diff` of `for-each-ref` output, exit 0).
- The three historic branches are #234 and #96 (closed, unmerged) and #319 (merged), as EC-11 records. None collides with a seed slug.

**Differences from earlier runs.** The result is the same as S3's run and re-review round 1's: the same vintage, date, members, empty open list and pick. Only `origin/main` moved, from 845a4d9b at S3 to 6f5a7310, and that changes no output.

## Other evidence S6 gathered at 451478b0

- **AC-10.**
  - `git diff --stat 72a4ade1 451478b0` ends `39 files changed, 7871 insertions(+), 1 deletion(-)`.
  - A `grep -vE` for paths outside the two skill files, `REPO_MAP.md`, the spec folder and the test pack printed nothing (exit 1).
  - `git diff --quiet 72a4ade1 451478b0 -- vidbyte lint scripts .github` exits 0, and `-- .claude/ci-settings.json` exits 0. The blob is `f5c44a2064b7b4c426a5ae7efd98987ddf82164b` at base and head.
  - `.github/workflows/claude.yml:50` still reads `settings: .claude/ci-settings.json`.
- **AC-11.**
  - `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package --dist-dir <scratch>/s6/dist` exited 0 and ended `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.`
  - The wheel has 1126 entries, its top-level names are `vidbyte` and `vidbyte_sdk-0.3.0.dist-info`, and 0 contain `.claude`.
  - The sdist has 1433 entries: 0 contain `.claude`, and 0 contain `onboard_model_provider_skill`.
- **Spec contracts.** The re-reviewer's `<scratch>/rr1/contracts_diff.py`, rerun at 451478b0, finds the following IDENTICAL between the spec and the skill: the 33 wiring rows, the subagent brief, the output grammar and the result block. The four pass-top and cleanup commands and the eight quoted rules are present in both.
- **Merge.** In the clone, `git merge-tree --write-tree --name-only origin/main HEAD` exits 0 and prints only the tree, so there is no conflict. `origin/main` is 70 commits past base. Of this PR's files, main changed only `REPO_MAP.md`, outside the `.claude/` entry.
- **Hygiene.**
  - No `.pyc`, wheel or `dist/` path is in the diff.
  - `git grep -F '422mi'` finds nothing under `tests`, `.claude` or `REPO_MAP.md`. It finds 22 spec-folder files, where 121 `docs/spec` files on `origin/main` already carry such paths.
  - No e-mail address appears in the spec folder, the pack or the skill.
- **Test names.** All 41 distinct backticked `test_*` names in the PR body exist. 40 of them are in the pack (`git grep -n "def <name>("`). The 41st, `test_cancelled_waiter_does_not_break_transport`, is the MCP flake at `tests/test_mcp_stdio_transport.py:360`.
- **Mermaid.** `node <scratch>/s6/render.cjs` renders every block of the PR body and of `spec.md` (the new flowchart and the unchanged sequence diagram) with mermaid 11.4.1 in headless Chromium: `blocks 1, failures 0` and `blocks 2, failures 0`.
- **The pack after the spec commit.** `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` gave `65 passed in 3.07s` at b726c6f8.
- **The local-path grep.** `grep -n -F -e '422mi' -e 'C:/Users' -e '/c/Users' docs/spec/provider-onboarding-skill/pr-body.md` printed nothing (exit 1), and so did the same grep over the body GitHub stored.

## Deviations found (shipped text compared with spec §4, §5, §8 and §12)

- **§4.** No deviation; the snippet's grammar and steps 1 to 6 match SKILL.md.
- **§8.5 and §12.3.** No deviation in the fixed contracts (see Spec contracts above).
- **§5, the flowchart.** It differed in seven framing places (`reports/S5-rereview-1.md`):
  - no ledger skip or path reads in the walk;
  - no clean check before a `DISQUALIFIED` cleanup;
  - no clean check or cleanup before a subagent `NETWORK_BLOCKED` STOP;
  - no edges for a failed fetch, `gh api` read or `ls-remote`;
  - no `no-result` edge;
  - no `cleanup exit` continuation;
  - the evidence directory missing from cleanup.

  It also labelled `PUBLISH_FAILED` only "push or PR fails", omitting the guard. All of this is fixed in r10: §5 is redrawn to the same flowchart as the PR body, and §17 has the r10 row and a note listing the seven.
- **Recorded and kept.**
  - The 14 S3 implementation deviations (spec §17).
  - INV-13's reading that the base URL is a quoted fact (s5a-10).
  - R-7 option (c), not taken.
- **Spec gap.** INV-20 lists only reachability failures, while SKILL.md:83 maps any failed `gh api` read, a 401 or 404 included, to `NETWORK_BLOCKED - api.github.com <status>`. The skill fails closed, and a one-line spec fix would close it (pipeline.md 04:30).
- **Inside the skill.** `provider-run.md:23` names `PROOF_FAILED` for the first failure in sections 6 to 9, while section 9's steps name `PUBLISH_FAILED` (R-15, follow-up).

The PR body's "Deviations from the spec" section carries all of these.

## Final PR state

```text
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1175 --json title,isDraft,baseRefName,headRefName,url,state,headRefOid
{"baseRefName":"main","headRefName":"feat/onboard-model-provider-skill","headRefOid":"b726c6f895ac9242d5a40a9f6faa6f4074e7e42b","isDraft":true,"state":"OPEN","title":"feat(skills): /onboard-model-provider onboards one model vendor per PR from first-party sources, continuously","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1175"}
$ gh pr view … --json body --jq .body | grep -c '```mermaid'
1
$ gh api repos/cerredz/Vidbyte-SDK/pulls/1175 --jq '.body | endswith("🤖 Generated with [Claude Code](https://claude.com/claude-code)\n") or …'
true
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175
no checks reported on the 'feat/onboard-model-provider-skill' branch   (exit 1; CI is dispatch-only)
```

**Body checks.**

- `gh pr edit` worked on the first call, so no fallback was needed.
- The stored body equals `pr-body.md` minus its title line. The one difference is the newline that `--jq` appends when it prints.
- The `headRefOid` above is the spec commit. The commit that adds this report follows it, so the PR head moves to that commit.

## Candidate field-guide lessons (report only; not written to the field guide)

1. **Test-plan claims must match what a check can fail for.**
   - Trigger: writing a test-plan row or a FEATURE.md failure column for a test that pins skill or doc text.
   - Preferred action: claim only the mutations you ran red, such as deleting the rule, inverting it, and the calibrated forms. A token-presence check claims presence, not the rule around it.
   - Reason: three rounds (R-3, R-9, R-13) found tests that passed with their claimed defect. One of them would have re-selected a disqualified vendor on every pass.
   - Quick check: run a mutation harness on a fresh copy per row. Assert that the anchor occurs exactly once and the edit applied, run the pack, and require every claimed row to be red.
   - Link: PR #1175.
2. **Git for Windows `grep -i -F` aborts.**
   - Trigger: a guard or check that uses `grep -i -F` and runs in Git Bash or an agent's Bash tool.
   - Preferred action: drop `-i`, or drop `-F`, or use `git grep -i -F`.
   - Reason: GNU grep 3.0 in Git for Windows exits 134 on `-i -F` when LANG and LC_ALL are unset. A guard waiting for exit 1 then never passes (R-E8).
   - Quick check: `printf 'A\n' | grep -i -F a; echo $?` prints `134` in that shell.
   - Link: PR #1175.
3. **A local-path guard built from `dirname` or `$HOME` becomes `/` in containers.**
   - Trigger: a check that keeps local paths out of a PR body or log by matching `dirname "$PWD"` or `$HOME`.
   - Preferred action:
     - strip `http(s)://` URLs first;
     - match the path's distinctive last segment (`basename`);
     - match the user name only between separators;
     - let the worktree stand in when HOME is `/` or empty;
     - fail closed when the input cannot be read.
   - Reason: with the checkout at `/workspace` or `/app`, or HOME `/`, the pattern is `/` and every line matches, so no run can publish (R-11).
   - Quick check: run the guard with `HOME=/` and a `/workspace` checkout over a clean body; it must print `grep exit 1`.
   - Link: PR #1175.
4. **Never record a key format from a summarized read, and never replace an old shape.**
   - Trigger: adding or changing a `KEY_FORMATS` rule, or a "Provider Key Format Sources" README row.
   - Preferred action:
     - fetch the page raw with its UTC time;
     - quote the sentence that holds the prefix verbatim, checked with `grep -F` against the saved page;
     - put the prefix itself in the README quote;
     - add a newer shape beside the old rule, never in its place.
   - Reason: #1027's Meta row quoted "API keys look like this:", a paraphrase with no prefix. Meta now documents `LLM_`, and a lone new-shape key with deepseek primary is bound to DeepSeek (S5 repair 3).
   - Quick check: the README quote contains the prefix literally, and `grep -F` finds it in a fresh raw fetch.
   - Link: PR #1175.
5. **`python -c` imports from the working directory before `PYTHONPATH`.**
   - Trigger: a `-c` probe meant to import a worktree's package, while the shell starts in another checkout.
   - Preferred action: prefix `cd <worktree> && `, or run a script file by path.
   - Reason: with `-c`, `sys.path[0]` is `''`, so the launcher's stale `vidbyte` wins over `PYTHONPATH=<worktree>` (R-5).
   - Quick check: `PYTHONPATH=<worktree> <py> -c "import vidbyte, inspect; print(inspect.getfile(vidbyte))"` must print a path inside the worktree.
   - Link: PR #1175.
6. **A worktree add followed by `; rev-parse` hides its own failure.**
   - Trigger: a shell block that creates a worktree and then reads its HEAD.
   - Preferred action: `git worktree add -b … && git -C "$WT" rev-parse HEAD; echo "add exit $?"`, with a non-zero exit treated as "not yours".
   - Reason:
     - the old block printed the other session's SHA with exit 0 (R-6);
     - git 2.49 creates the branch before failing on an unwritable parent, so a failed add also leaves a stray branch.
   - Quick check: run the block twice in a scratch repo; the second run must print `add exit 255`.
   - Link: PR #1175.

## Things that looked wrong (none fixed here; no source change was allowed)

- **The result-check read has no exit status.** `.claude/skills/onboard-model-provider/SKILL.md:147` (`## Verifying a result`) runs `gh api "repos/cerredz/Vidbyte-SDK/pulls/$PR" …` with no exit status, while `SKILL.md:83` says each `gh api` read in a pass prints one. A failed read therefore becomes `RESULT_UNVERIFIED <slug> pr-state`, with the worktree kept and the PR open, instead of `NETWORK_BLOCKED`. It fails closed, and only the label differs. Listed in the PR's Follow-ups.
- **The S10 assert message over-claims.** `tests/features/onboard_model_provider_skill/test_onboard_skill_security.py:305` says "no line may tell a run to edit, replace or narrow a key rule". R-13 narrowed that claim in the test plan and FEATURE.md, but the message keeps the broad form. Listed in Follow-ups with the S10 regex hardening.
- **The proof rule's label.** `.claude/skills/onboard-model-provider/references/provider-run.md:23` names `PROOF_FAILED` for section 9 failures (R-15).
- **The keep rule and the shared README lines.** `.claude/skills/onboard-model-provider/references/provider-run.md:129` (the keep rule) covers the shared README lines that `:190` (D2) and `:180` (C4) touch (R-14).
- **The C4 note and the registries README.** `.claude/skills/onboard-model-provider/references/provider-run.md:197` (the C4 note, "statement or example") conflicts with `vidbyte/lib/registries/README.md:43`, "No example key is copied here" (the verifier's C4 note).

## Open items

- The PR stays a draft. S6 never marked it ready and never merged it.
- Seen, not acted on: Meta's `LLM_` key shape and its `MODEL_API_KEY`. The PR's Follow-ups name both as urgent and outside this PR.
