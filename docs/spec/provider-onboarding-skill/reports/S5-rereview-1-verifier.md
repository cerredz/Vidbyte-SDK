# S4 findings verifier (scoped): S5 final re-review, round 1

Stage: S4 findings verifier, scoped to `reports/S5-rereview-1.md` (RR-1, RR-2, RR-3). Worktree `vidbyte-sdk-provider-onboarding-skill`, branch `feat/onboard-model-provider-skill`, HEAD `460898a9`. Read-only: no source edit, no commit. Outputs: this report and a new section at the end of `review.md`.

Scratch evidence is in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/rr1v/`, written `<v>` below. Every script reads the text it tests from the skill files at HEAD. None reuses the reviewer's scripts.

## Verdict

MERGEABLE AFTER FIXES. All three findings hold when executed. RR-1 is a Blocker of the R-3 class: two test-plan rows claim failures that X4 and X10 cannot catch. RR-1's add-on is split out as a Major of the R-8 class. RR-2 is a Major, and the reviewer's smallest fix for it is incomplete: two of the seven executed cases still block. RR-3 is a Minor with a one-sentence fix.

Confirmed: 1 Blocker, 2 Majors, 1 Minor. Refuted: 0. Downgraded: 0.

## Merge map

| Re-review ID | review.md ID | Severity | Fix kind | Who |
|---|---|---|---|---|
| RR-1, claimed rows (X10 plain 403; X4 evidence path, session ledger; plus X4 local and remote branch, which I added) | R-9 | Blocker | test | S2 test author (strengthen-only grant) |
| RR-1 add-on (R-1's URL rule, R-6's add-failure sentence) | R-10 | Major | test | S2 test author (same grant) |
| RR-2 (PR-body guard) | R-11 | Major | skill text, plus one spec line | repair agent |
| RR-3 (URL rule vs attribution line) | R-12 | Minor, `trivial` | skill text and spec | repair agent |

## RR-1: verified, Blocker (R-9), with a Major split out (R-10)

### Method

`<v>/v_mut.py` copies `SKILL.md`, `references/provider-run.md` and `REPO_MAP.md` into a fresh temp tree for every row. Before each edit it requires the anchor to occur exactly once. After the edit it re-reads the file and checks that the anchor is gone and the new text is present. It then runs the pack through the fixture-redirect plugin:

```
S2_SYNTH=<copy root> PYTHONPATH="<worktree>;<scratch>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider -p s2_harness --tb=no
```

Three positive controls show that the redirect reaches the tests. Output: `<v>/v_mut_out.txt`.

| Row | Edit (file) | Result |
|---|---|---|
| CONTROL | none | `50 passed in 0.85s` |
| POS-X4 | drop `--paginate` from the open-PR read (SKILL.md:78) | `1 failed, 49 passed` — X4 |
| POS-X10 | `--max-time 60` → `600` in the capture command (provider-run.md:48) | `1 failed, 49 passed` — X10 |
| POS-X4 all `-evidence` | remove the `-evidence` test at :95 **and** the `-evidence` words at :102 | `1 failed, 49 passed` — X4 (only deleting every token is caught) |
| X10-a (reviewer's) | provider-run.md:78 "is first checked against GitHub with" → "ends the run `NETWORK_BLOCKED` at once; it is not checked against GitHub with" | `50 passed` |
| X10-b (mine) | provider-run.md:77 "A match, or a sandbox …" → "A match, any HTTP status of 403, or a sandbox …, ends the run `NETWORK_BLOCKED`" | `50 passed` |
| X10-c (mine) | provider-run.md:78 "or an HTTP status of 400 or more without `x-deny-reason`) is first checked" → "other than an HTTP status of 403) is first checked" | `50 passed` |
| X4-a (reviewer's) | remove ` \|\| test -e "$WORKTREE-evidence"` from SKILL.md:95 | `50 passed` |
| X4-b (reviewer's) | SKILL.md:87 ledger sentence reduced to "Skip without a query a vendor whose slug is a member." | `50 passed` |
| X4-c (mine) | SKILL.md:87 ledger sentence deleted | `50 passed` |
| X4-d (mine) | SKILL.md:102 `local-branch` no longer names `show-ref` ("`local-branch`: the worktree path, …"); the command stays | `50 passed` |
| X4-e (mine) | SKILL.md:101 `remote-branch` exit codes swapped ("exits 2. Exit 0 means the branch is absent") | `50 passed` |
| ADD-1b | provider-run.md:16 bullet deleted whole | `50 passed` |
| ADD-2 | provider-run.md:16 "A URL you did not fetch never enters the PR, even when you know it." → "… may enter the PR when you know it." | `50 passed` |
| ADD-1 | :16 reworded to "Every value you write …" with its last sentence dropped | `50 passed` |
| ADD-3 | SKILL.md:112 add-failure sentence deleted | `50 passed` |
| ADD-4 | SKILL.md:112 → "The SHA that printed is the pass's `<base>`: launch the subagent on that worktree." | `50 passed` |

### What the tests claim

- test-plan.md:33 (row D-19 / INV-9 / INV-20 / R-5) and FEATURE.md:70 both say X10 catches "a plain vendor 403 called NETWORK_BLOCKED". X10 (`test_onboard_skill_commands.py:325-334`) only checks that tokens are present: `x-deny-reason`, `docs-unreachable` and `NETWORK_BLOCKED` in `## 2. Research`.
- test-plan.md:27 (row INV-4 / INV-5 a–e) says X4 catches "local or remote branch, evidence path or session ledger ignored". X4 (`:158-174`) checks that `ls-remote` and `show-ref` commands exist, and that the phrases `-evidence` and "this session" appear anywhere in `## Each pass`. "this session" still appears in the back-pressure bullet (SKILL.md:85), so dropping the ledger sentence leaves X4 green.
- test-plan.md:64 and FEATURE.md:129 go further: "The text guards (skip rules a to e, …) are tested".

So X4 and X10 match R-3 exactly: a test that cannot fail for the defect its test-plan row claims. The S4 verifier ruled that class a Blocker (`reports/S4-findings-verifier.md`), and the orchestrator accepted it. Each of the six claimed defects passes: plain 403, evidence path, session ledger, local branch and remote branch.

### Does "loops forever" hold? Traced by execution

`<v>/v_loop.py SKILL.md <v>/loopclone` runs SKILL.md's own blocks, read from the file, in a throwaway `--shared` clone whose origin is GitHub (`origin/main` = `6f5a7310`). Output: `<v>/v_loop_out.txt`.

1. Pass 1 walk for cerebras: `prs exit 0`, `remote-branch exit 2`, `local-branch exit 1`, `paths exit 1`, so cerebras is selected.
2. Add: `add exit 0`, base `6f5a7310…`.
3. A simulated DISQUALIFIED subagent makes only the writes the procedure allows before Qualify ends: the evidence directory and one fetch-log line.
4. Clean check: `HEAD equals base: True | porcelain empty: True`.
5. D-8 cleanup: `Deleted branch feat/provider-cerebras`, `cleanup exit 0`.
6. Pass 2 walk: `prs exit 0`, `remote-branch exit 2`, `local-branch exit 1`, `paths exit 1`. These are identical to pass 1. No worktree, no evidence directory and no branch remain, and GitHub holds nothing about the vendor.

So after a DISQUALIFIED outcome, the only rule that excludes the vendor is INV-5(e), the sentence at SKILL.md:87. Every other skip rule (member, any-state PR, remote branch, local branch or paths) reads live state, and D-8 has just erased that state. INV-7 and Q-1 forbid storing the disqualification anywhere outside the session.

`grep -n -i ledger` over both files finds two other places that bear on it. Neither is a skip rule of the walk:
- SKILL.md:21 defines the stop: "`NO_CANDIDATE`: every seed vendor is skipped or disqualified."
- SKILL.md:27 says "the loop continues with the next vendor".

The walk at :87 says "select the first one that no skip rule excludes", and the dispositions at :98-102 list no disqualified vendor. Without the sentence, therefore, the literal procedure selects the rank-1 vendor again on every pass, with a full research subagent each time, and never reaches a STOP. Nothing caps the number of passes. Whether a model would infer the missing rule from :21 or :27 is not something the skill guarantees. **Holds as stated, with that qualification.** The Blocker does not depend on it: the claimed test cannot fail either way.

### The other claimed failures, checked

- **Evidence path dropped.** The same script left only `<worktree>-evidence` behind, the state a cleanup leaves when its `rm -rf` does not finish, and added a stale fetch-log line.
  - The paths read as written printed `paths exit 0`, so the vendor is skipped as `local-branch`.
  - The X4-a mutant printed `paths exit 1`, so the vendor is selected. The add then succeeded (`add exit 0`).
  - The subagent's own first writes are `mkdir -p` (provider-run.md:28) and `tee -a` (:48). Both reuse the directory: `mkdir exit 0`, and the fetch log afterwards holds both `2026-09-01T00:00:00Z https://old.example.invalid/ 200 …` and the new line. A stale 2xx line can then satisfy :16's "final URL of a line in `<evidence>/fetch-log.txt`". **Holds.**
- **Plain 403 called NETWORK_BLOCKED.** Under X10-a or X10-b, a vendor host with bot protection ends the run `NETWORK_BLOCKED`. The seed table itself predicts this for sambanova (SKILL.md:229: "the docs host answered 403 to automated fetches with no x-deny-reason header").
  - `NETWORK_BLOCKED` stops the session (SKILL.md:25) and records nothing about the vendor (INV-20).
  - After the clean check and the D-8 cleanup, no state remains, so every later session stops at that vendor again. This is spec review r1-5's failure. **Holds.**

### Add-on: Major, not Blocker (R-10)

- No test-plan row claims INV-13: `grep -n 'INV-13\|invent' test-plan.md` finds only row AC-6's "An invented … vendor" (C4).
- Row FR-3 / D-3 (test-plan.md:28) names D-3. Its failure column lists only "`worktree add -B`, `-f`, or from `HEAD`", and it was written before r7 added the failed-add clause to D-3.
- test-plan.md:64 lists the text guards it says are tested for EC-52 as "skip rules, one session, single unforced refspec". The add-failure branch is not among them.

Both are unclaimed, so R-8's precedent applies: these are safety sentences the user's outcomes rest on, and they are unpinned. That makes them Major.
- provider-run.md:16 carries the request's weighted "**Never** invent a URL" (request.md:152, §D) and INV-13.
- SKILL.md:112 is the in-clone backstop of EC-52 and D-3 (r7). Without it, a second session adopts the first session's worktree (review R-6).

ADD-1b, ADD-2, ADD-3 and ADD-4 all give `50 passed`.

### Smallest fixes (S2 test author, strengthen-only)

Pin these sentences as whole strings on one prose line each, as R-3 and R-8 were pinned.

R-9, X10, in `## 2. Research` prose:
- "A match, or a sandbox or tool permission-denial message for the fetch, ends the run `NETWORK_BLOCKED`"
- "Any other failure on a vendor host (curl exit not 0 for DNS, connection, TLS or timeout, or an HTTP status of 400 or more without `x-deny-reason`) is first checked against GitHub with"
- "Otherwise the vendor page is unreachable, and section 3 decides whether that is `docs-unreachable`."
- A negative check: no Research prose line other than these and the "Network rule." line (:75) names `NETWORK_BLOCKED`. Kills X10-a, X10-b and X10-c.

R-9, X4, in `## Each pass`:
- Compare the paths command as a whole string: `test -e "$WORKTREE" || test -e "$WORKTREE-evidence" || test -e "$WORKTREE-main"; echo "paths exit $?"`.
- Pin "Skip without a query a vendor that already has an outcome in this session's ledger, or whose slug is a member."
- Pin the dispositions "`remote-branch`: `ls-remote` exits 0. Exit 2 means the branch is absent" and "`local-branch`: the local branch exists (`show-ref` exits 0), or the worktree path, its `-evidence` path or its `-main` twin exists (`paths exit 0`)".
- Kills X4-a to X4-e.

R-10:
- Pin "Never invent a URL." and "A URL you did not fetch never enters the PR, even when you know it." in `provider-run.md` "Rules for the whole run".
- Pin the add command as a whole string: `git worktree add -b "feat/provider-$SLUG" "$WORKTREE" origin/main && git -C "$WORKTREE" rev-parse HEAD; echo "add exit $?"`. X2 checks only `-b`, `feat/provider-` and `origin/main`.
- Pin "launch no subagent, record `local-branch` for the vendor, and continue the walk of step 2 with the next vendor".
- Kills ADD-1 to ADD-4.

None of this adds a persistent ledger (Q-1 stays settled). The tests pin only the session-ledger sentence.

## RR-2: verified, Major (R-11); the reviewer's smallest fix is incomplete

### Execution

`<v>/v_guard.py provider-run.md <v>` reads the one sh fence that holds `pr-body.md` and `grep -n -F` from the file. For each case it fills `<worktree>` and `<evidence>`, sets HOME, and runs the line with Git Bash's `bash.exe`.

There is one clean body: Changes, a Verification line with "node IDs" and "JSON-RPC", a Sources table, the closing line and the attribution line. It has three synthetic Sources URL shapes: `https://cloud.cerebras.ai/app/keys`, `https://inference-docs.cerebras.ai/dev/node/quickstart` and the base URL. There are five dirty bodies, each of which adds one local path: the worktree, the evidence directory, the twin, the home directory, and a backslash home path. Output: `<v>/v_guard_out.txt`.

| Case (worktree; HOME) | Current :354, clean body | F2 (reviewer's fix) | F1b (proposed) |
|---|---|---|---|
| A root container, checkout `/workspace` (`/workspace-onboard-cerebras`; `/root`) | `grep exit 0`, lines 2,4,8,9,10,13 (pattern `/`) | `grep exit 1` | `grep exit 1` |
| B root container, checkout `/app` (`/app-onboard-cerebras`; `/root`) | `grep exit 0`, 6 lines | **`grep exit 0`, line 9** (`/app` inside `…/app/keys`) | `grep exit 1` |
| C HOME=`/` (Docker `--user` uid with no passwd entry) | `grep exit 0`, 6 lines (pattern `/`) | `grep exit 1` | `grep exit 1` |
| D HOME=`/home/dev`, URL with a `/dev/` segment | `grep exit 0`, line 10 | **`grep exit 0`, line 10** | `grep exit 1` |
| E Claude Code devcontainer user (`/workspace-onboard-cerebras`; `/home/node`) | `grep exit 0`, 6 lines | **`grep exit 0`, line 10** (`/node/`) | `grep exit 1` |
| F control Linux (`/home/alice/src/…`; `/home/alice`) | `grep exit 1` | `grep exit 1` | `grep exit 1` |
| G control Git Bash, this machine (`C:/Users/422mi/…`; `/c/Users/422mi`) | `grep exit 1` | `grep exit 1` | `grep exit 1` |

Every dirty body gives `grep exit 0` under all three lines in every case. The one exception is the backslash-home body in case C, where there is no home directory to leak: F1b and F2 give 1 there, which is correct. A missing body gives `grep exit 2` for the current line and for F2. F1b prints `1:pr-body.md was not read` and `grep exit 0`, so a check that did not run never reports clean.

The first attempt, F1, wrote a temp file and printed `grep exit 1` when the evidence directory was missing. I rejected it, and F1b replaces it.

F1b, run directly through this agent's Bash tool (the path the subagent uses), caught `C:\Users\422mi\x\y.txt` with `grep exit 0` and passed a clean body with `grep exit 1`. The `printf '\134…'` octal survives the tool, as R-E8 established.

### Is the configuration realistic?

Yes.
- Spec §9.3 and D-27 allow `bypassPermissions` only "inside an isolated container or VM" (SKILL.md:33).
- Claude Code's own reference devcontainer mounts the checkout at `/workspace`. I fetched `https://raw.githubusercontent.com/anthropics/claude-code/main/.devcontainer/devcontainer.json` (HTTP 200): `"workspaceMount": "source=${localWorkspaceFolder},target=/workspace,…"`, `"workspaceFolder": "/workspace"`, `"remoteUser": "node"`.
- Ad-hoc `docker run -v "$PWD":/workspace` (or `/app`) as root, and `--user <uid>` with no passwd entry (HOME=/), are common container shapes.

Each one reaches §9 with a correct body and cannot pass the guard (cases A, B and C).

### Observation, not a finding

This is outside the mandate, which asks only for Blocker-class blind spots, but it bears on how real case E is. In the reference devcontainer itself, user `node` cannot create `/workspace-onboard-<slug>`, because `/` is owned by root. The run therefore fails earlier, at the worktree add.

I executed the same failure shape in `<v>/loopclone` with an uncreatable path:
```
fatal: could not create leading directories of 'Q:/no-such-drive/x-onboard-probe/.git'
add exit 128
local-branch exit 0
```
git 2.49 creates the branch before the directory fails and leaves it behind. Under SKILL.md:112, every vendor would be recorded `local-branch`, ten stray branches would be left, and the session would end `NO_CANDIDATE`. That is loud and writes nothing remote, so it is not Blocker-class. I record it so the orchestrator can decide whether a follow-up should state that the checkout's parent must be writable.

### Does the procedure name an outcome?

Not a usable one.
- :357 says: "When it prints a line, replace the path or name … and run it again. … never push until it prints `grep exit 1`." That is a loop with no exit when the match is permanent.
- The general rule at :23 says: "Sections 6 to 9 are proof: each step runs once … its first failure ends the run with `PROOF_FAILED <check>`. The reruns that section 8 allows are the only repeats." That rule contradicts :357's rerun. It would also end a fixable body on its first match, and it gives no `<check>` name for the guard.

R-E8 asked to "name an outcome", and commit 39e37702 did not name one. **Holds.**

### Severity

Major, not Blocker.
- It fails closed: it never pushes, and it never writes a wrong PR.
- It is confined to container setups that the spec supports.
- The default setup, auto mode on a workstation, passes (controls F and G).
- But in those setups every provider run does all its research, wiring and gate work and then cannot publish. The likely improvisations either corrupt Sources URLs, which breaks request §C "cites **every** first-party source", or end with an outcome the guard does not name.

### Smallest robust fix (repair agent: skill text, plus one spec line)

Replace the command at provider-run.md:354 with F1b:

```sh
W="<worktree>"; H="${HOME%/}"; H="${H:-$W}"; { sed -E 's#https?://[^[:space:]]*##g' "<evidence>/pr-body.md" || echo 'pr-body.md was not read'; } | grep -n -F -e "$W" -e "$H" -e "/$(basename "$H")/" -e "$(printf '\134%s\134' "$(basename "$H")")" -e 'pr-body.md was not read'; echo "grep exit $?"
```

How it works:
- It strips http(s) URLs first. A local path never sits inside one, so no Sources URL segment can match. This fixes cases B, D and E, which the reviewer's fix misses.
- It matches `<worktree>`, which `<evidence>` and the `-main` twin both start with. That path is never `/`, and it carries `-onboard-<slug>`.
- When HOME is `/` or empty, it uses `<worktree>` in place of the home directory.
- An unreadable body feeds a sentinel line that the guard itself matches.
- It has no doubled backslash and no `-i`. It runs in POSIX sh, and the agent's Bash tool on Windows passes it intact.

Then change the prose:
- In :357, describe the new patterns, and add: "When a printed line holds no local path or user name, or a line still prints after you replaced every one, end the run `PUBLISH_FAILED push local-path-guard` without pushing." This outcome fits the `PUBLISH_FAILED <slug> <push|pr> <reason>` grammar (SKILL.md:198), and SKILL.md:180 already keeps the worktree for it.
- In :23, add the body check's rerun to the allowed repeats: "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats".
- In the spec, add one line to D-16 or a new EC row naming `PUBLISH_FAILED push local-path-guard`.

A test could then pin the new command as a whole string, the outcome sentence, and the :23 clause. That is S2 work after the text lands.

## RR-3: verified, Minor (R-12), `trivial`

- provider-run.md:16: "Every URL you write into code, a test, a README or the PR body is either the base URL fact … or the final URL of a line in `<evidence>/fetch-log.txt` with a 2xx status … A URL you did not fetch never enters the PR, even when you know it."
- provider-run.md:349: "and last, the pull-request attribution line your session's instructions give, if any."
- Spec INV-13 (spec.md:216) has the same absolute wording, and D-16 (spec.md:425) says "The body ends with the attribution line."

Subagents do receive such a line. This verifier, a subagent, was given "End pull request descriptions with: 🤖 Generated with [Claude Code](https://claude.com/claude-code)", and that URL is never fetched. The PR template on `origin/main` holds no URL (`MSYS_NO_PATHCONV=1 git show origin/main:.github/pull_request_template.md | grep -E 'https?://'` → exit 1), so the attribution line is the only conflict. The commit attribution (§7) holds no URL.

**Holds.** The fix is one sentence, so it is `trivial`. Append it to :16 and to INV-13, leaving the existing sentences byte-identical so that R-10's pins hold: "The one exception is the pull-request attribution line your session's instructions give, which section 9 puts last." This is skill text plus spec. It does not touch the weighted word in spirit, because the attribution URL is not invented and does not come from a vendor.

## Blind spots (code changed since 32ca7991)

I read `git diff 32ca7991..HEAD -- .claude`: the add and cleanup chains, the `prs exit` reads, R-E4's twin path, the R-1 rule and D1 note, the R-7 Dialect clause, the R-2 A13 bullet and its two fences, and the R-E8 guard.

No Blocker-class defect is missing from the re-review. Two non-Blocker items are noted, not filed:
- The :23 versus :357 repeat conflict is folded into R-11's fix.
- The add failure in an unwritable parent leaves stray branches. See the RR-2 observation.

## Q-default and scope check

- No confirmed finding reopens Q-1 to Q-10.
- R-9 and R-10 pin text that already exists. R-11 changes only how a check the spec already requires (D-16 "no absolute local path") is run, and names an outcome inside the existing grammar. R-12 adds an exception the spec's own D-16 implies.
- None asks for behaviour the user declined in request §C: no routine, no `/loop`, no persistent ledger.

## Commands run (final output lines)

- `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `50 passed in 0.84s` (before) and `50 passed in 0.82s` (after). `git status --short` printed nothing both times. HEAD `460898a9f7f96ada935df66186fd2aee313faa70`.
- `py -3.11 <v>/v_mut.py`:
  - `[CONTROL] … 50 passed in 0.85s []`
  - `[POS-X4 pagination dropped] … 1 failed, 49 passed … ['test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5']`
  - `[X4-c own: ledger skip sentence deleted] … 50 passed in 0.82s []`
  - `[ADD-3 add-failure sentence deleted] … 50 passed in 0.87s []`
  - The full table is above.
- `git clone --quiet --shared <repo> <v>/loopclone`; `git -C <v>/loopclone remote set-url origin https://github.com/cerredz/Vidbyte-SDK.git`; `git -C <v>/loopclone fetch --quiet origin main` → `fetch exit 0`, `6f5a7310…`.
- `py -3.11 <v>/v_loop.py <SKILL.md> <v>/loopclone`:
  - pass 1 `prs exit 0 / remote-branch exit 2 / local-branch exit 1 / paths exit 1`
  - `add exit 0`
  - `HEAD equals base: True | porcelain empty: True`
  - `cleanup exit 0`
  - pass 2 `prs exit 0 / remote-branch exit 2 / local-branch exit 1 / paths exit 1`
  - stale case `paths exit 0` (as written) and `paths exit 1` (X4-a); two fetch-log lines after `mkdir -p` and `tee -a`
  - tidy `cleanup exit 0`
- In `<v>/loopclone`, `git worktree add -b "feat/provider-probe" "Q:/no-such-drive/x-onboard-probe" origin/main && …; echo "add exit $?"` → `fatal: could not create leading directories …`, `add exit 128`, `local-branch exit 0`. The branch was then deleted and the worktree pruned (scratch only).
- `py -3.11 <v>/v_guard.py <provider-run.md> <v>`: the table above. Missing body: `CURRENT ['grep exit 2']`, `F1 ['grep exit 1']` (rejected), `F1b ['1:pr-body.md was not read', 'grep exit 0']`, `F2 ['grep exit 2']`.
- F1b typed through the Bash tool with HOME=`/c/Users/422mi`: dirty `2:log C:\Users\422mi\x\y.txt` / `grep exit 0`; clean `grep exit 1`.
- `curl -sSL --max-time 60 … anthropics/claude-code/main/.devcontainer/devcontainer.json` → `200`; grep shows `"remoteUser": "node"`, `"workspaceFolder": "/workspace"`. The Dockerfile shows `WORKDIR /workspace` and `USER node`.
- `MSYS_NO_PATHCONV=1 git show origin/main:.github/pull_request_template.md | grep -n -i -E 'https?://|www\.'` → exit 1 (25 lines, no URL).
- `grep -n -E 'INV-13|D-3\b|EC-52|invent|add exit|add fail'` over test-plan.md, FEATURE.md and the pack → no row claims INV-13 or the failed add (test-plan.md:28 and :64, FEATURE.md:60 and :129 quoted above).
- `git diff 32ca7991..HEAD -- .claude` read in full (blind-spot pass).
