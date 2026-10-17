# S5 repair 2: provider-onboarding-skill

Stage: S5 repair, iteration 2 of 8 · Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch `feat/onboard-model-provider-skill` · Start `b2101e1d` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1175 (draft, left a draft)

`<scratch>` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad`. This iteration's reproducer is `<scratch>/s5r2/guard_exec.py`, with its outputs beside it (below, `<s5r2>`). It reads the guard line from the file it is given, so every result below is for the committed text.

Defects in: R-11 (Major) and R-12 (Minor, trivial) from `review.md` "Re-review round 1", plus the optional §9.1 Cerebras note. R-9 and R-10 are test findings routed to the S2 test author and were not touched. No file under `tests/` changed (`git diff --name-only b2101e1d..HEAD -- tests` is empty).

## Gate matrix

All gates ran in this worktree at HEAD `c660063e`, in this iteration, in the order the brief gives.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 pack) | `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` | PASS (50/50) | `50 passed in 0.79s` |
| lint | `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` (exit 0; every change committed first) | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited known-red test | log line 182 `SDK-LINT: PASS` · `E       AssertionError: assert 148 == 120` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `============ 1 failed, 5819 passed, 16 skipped in 86.45s (0:01:26) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-provider-onboarding-skill).` |
| inherited proof | `git worktree add --detach "C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-r2-probe" origin/main` (6f5a7310); `PYTHONPATH="<probe>" py -3.11 -m pytest "<node>" -q -p no:cacheprovider`; `git worktree remove --force "<probe>"` | red on main too | `E       AssertionError: assert 167 == 120` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed in 1.62s` · `remove exit 0`, probe path gone, `git worktree list` no longer shows it. The branch leaves the harness file unchanged against base 72a4ade1 (`git diff --quiet` exit 0) and changes nothing under `vidbyte/` or `.semgrep/`. The count differs (148 on the branch, 167 on main) because the branch sits on the older base; the 120 snapshot is stale on both, as the field guide's `local-ci-verification.md` entry says. |
| MCP flake | — | not triggered | `test_cancelled_waiter_does_not_break_transport` passed inside the source stage; no rerun was needed. |
| import path | `PYTHONPATH="<worktree>" py -3.11 -c "import inspect, vidbyte; print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py` |
| full local gate, package | `py -3.11 scripts/run_ci.py --stage package`, run as `env -u PYTHONPATH …` (exit 0) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep | remote-only (dispatch) | not run; its inputs are unchanged | `git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175` | none attached (CI is dispatch-only) | `no checks reported on the 'feat/onboard-model-provider-skill' branch` (exit 1) |

The push went `b2101e1d..c660063e feat/onboard-model-provider-skill -> feat/onboard-model-provider-skill`, a fast-forward (`git merge-base --is-ancestor origin/feat/… HEAD` held first). The docs commit that carries this report is pushed after it.

## R-11 (Major) · fixed @8edfdec1

### Reproduced first, with the current line
`py -3.11 <s5r2>/guard_exec.py <provider-run.md> <s5r2>/provider-run.b2101e1d.md <s5r2> gitbash` reads the old line from `git show b2101e1d:…/provider-run.md`. On the clean body it gives `grep exit 0` in cases A (checkout `/workspace`, HOME `/root`), B (`/app`), C (HOME `/`), C2 (HOME empty), D (HOME `/home/dev`, a `/dev/` URL segment) and E (devcontainer user `node`), and `grep exit 2` for a missing body. Total 96 of 107 cells as expected; every miss is the defect. Output: `<s5r2>/guard_exec_gitbash_out.txt`, section `CURRENT (b2101e1d)`.

### Root cause
The line matched `$(dirname "<worktree>")`, which is `/` whenever the checkout sits directly under `/`, and `$HOME`, which is `/` for a container uid with no passwd entry. A pattern of `/` matches every line that holds a slash. The user-name segment `/<name>/` also matched vendor URL path segments. Then three rules collided: provider-run.md :357 said to rerun until `grep exit 1`, :23 allowed no repeats outside section 8, and no outcome existed, so a run in such a container did all its work and could never publish.

### The change
- **:354, the command.** It is F1b with one change: it matches `$(basename "$W")`, the worktree's last path segment, instead of `$W`:
  `W="<worktree>"; H="${HOME%/}"; H="${H:-$W}"; { sed -E 's#https?://[^[:space:]]*##g' "<evidence>/pr-body.md" || echo 'pr-body.md was not read'; } | grep -n -F -e "$(basename "$W")" -e "$H" -e "/$(basename "$H")/" -e "$(printf '\134%s\134' "$(basename "$H")")" -e 'pr-body.md was not read'; echo "grep exit $?"`
- **:357, the prose.** It describes each pattern, names the fallback and the sentinel, and adds the outcome. A false match ends the run `PUBLISH_FAILED push local-path-guard` at once. Any other match gets one rewrite and one rerun; if the rerun still does not print `grep exit 1`, the run ends the same way. The R-E8 sentences on `-i -F` and `\134` are kept byte-identical. The R-E8 user-name sentence is kept as the "third" item, with its wording unchanged after "The third is".
- **:23.** "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats, and code never changes after a proof step failed."
- **Spec.** New EC-63 names the outcome and the guard's patterns. §16 row s5r2-1, §17 r8, `revision: 8`, status stays `reviewed`. D-16's rule ("no absolute local path and no user name") is unchanged; only how it is checked changed.
- The outcome fits the existing grammar `PUBLISH_FAILED <slug> <push|pr> <reason>` (SKILL.md `## Output`), and SKILL.md `## What each outcome leaves behind` already keeps the worktree, its evidence and the branch for `PUBLISH_FAILED`. The next session skips the vendor as `local-branch` until the person cleans up. No remote branch exists, because the push never ran.

### Why the worktree's last segment instead of F1b's full worktree path
`basename "$W"` is a substring of `$W`, so the change can only add matches. It always ends in `-onboard-<slug>`, so it never equals `/` or an ordinary word. It is the one spelling-independent part of the three paths the run writes (`<worktree>`, `<evidence>`, `<worktree>-main`). F1b's `$W` is spelled `D:/src/…` on Windows, while Windows Python prints `D:\src\…` (pytest's `rootdir:` line, `run_ci.py`'s `cwd=`). When the checkout is outside HOME, nothing else in F1b, or in the old line, catches that spelling. Executed: F1b misses 6 cells, all backslash or `/c/` spellings of the worktree (cases A, B, E, H ×2, I), and FINAL misses none.

### Executed evidence (the line read from the committed file)

| Run | Shell and tools | Result |
|---|---|---|
| `guard_exec.py … gitbash` | Git for Windows `bash.exe`, GNU grep 3.0, the same binaries the agent's Bash tool uses | FINAL **107/107** as expected · F1b 101/107 · CURRENT 96/107 |
| `guard_exec.py … linux-script`, then `wsl.exe -d MuseUbuntu1 -u root -- sh <s5r2>/lin/run.sh`, then `linux-parse` | real Linux userland as root (WSL1): dash 0.5 as `sh`, GNU grep 3.11, GNU sed 4.9, `HOME=/root` | FINAL **107/107** under `sh` (dash) and **107/107** under `bash` |
| `<s5r2>/e2e.sh` in the same root userland, HOME not overridden | real directories `/workspace-onboard-cerebras-evidence` and `/app-onboard-cerebras-evidence` under `/` | each checkout: clean `grep exit 1`; worktree path appended `17:rootdir: /workspace-onboard-cerebras/tests` (or `/app-…`) `grep exit 0`; body missing `1:pr-body.md was not read` `grep exit 0` |
| The line typed through this agent's own Bash tool (Windows), HOME `/c/Users/422mi` | the path the subagent uses | clean `grep exit 1`; `17:C:\Users\422mi\AppData\Local\Temp\x.txt` `grep exit 0`; missing body `1:pr-body.md was not read` `grep exit 0`; worktree `D:/src/vidbyte-sdk-onboard-cerebras` with `rootdir: D:\src\vidbyte-sdk-onboard-cerebras\tests` `grep exit 0`; `HOME=/`, checkout `/workspace`, clean `grep exit 1`. The octal `\134` survives the tool. |

The 107 cells are 10 cases × (1 clean body + the dirty bodies that apply to the case) + 2 missing-body cells.
- **Cases:** A, B, C, C2 (HOME empty), D, E, F (Linux control), G (this machine), H (Windows checkout `D:/src` outside HOME) and I (Linux checkout `/srv/build` outside HOME).
- **Clean body:** Sources URLs with `/app/`, `/dev/`, `/node/`, `/root/` and `/workspace/` segments, a Markdown link, the words "node IDs", "root cause", "dev extras" and "app", `<worktree>` and `<evidence>` placeholders, the gate lines, and the 🤖 attribution line.
- **Dirty bodies:** the worktree; the evidence path; the twin; the worktree in backslash spelling; a local path right after a URL; for Windows worktrees, the `/c/` spelling; for `/workspace-onboard-` worktrees, the container form `/workspace-onboard-cerebras/tests/…`; and, when the case has a user name, the home path plus the four forms the brief names: Git Bash `/c/Users/<name>/…`, `C:\Users\<name>\…`, `C:/Users/<name>/…` and Linux `/home/<name>/…`.
- **Missing body:** with no evidence directory, and with an evidence directory that holds no body.

The expected verdict is fixed per cell in the script, and the summary line counts mismatches.

### Hypotheses tried, in order (including the ones that failed)
1. **F1b as proposed.** It works for cases A–G, but the harness showed it misses the backslash and `/c/` spellings of the worktree (6 cells). Replaced by the basename form above.
2. **Also match the launcher checkout, `${W%-onboard-*}` (F2's idea).** Rejected. For checkout `/app` it is `/app`, which matches page text quoted without a scheme (`cloud.cerebras.ai/app/keys`, from the rank-1 seed vendor), so a false match would end good runs. A run never needs that path: every procedure command uses `cd <worktree> && ` or `git -C`.
3. **Also strip scheme-less URLs** (`host.tld/…`). Rejected. The rule is harder to state and to trust, and it can delete a real local path that has a dotted segment (`/mnt/data.disk/<name>/…`).
4. **Match the user name with a single leading backslash (`\<name>`) to catch a home path at the end of a string.** Rejected. It reopens R-E8's ordinary-word matches, and no command output the run pastes ends at the bare home directory.
5. **First outcome wording:** "When it prints a line, replace every local path and name … When a printed line holds no local path or user name … end the run …". The harness's informational rows showed that, with HOME `/home/dev` or `/home/node`, page text quoted without a scheme (`inference-docs.cerebras.ai/dev/node/`) still matches the user-name segment. It fails closed, but an agent that reads "replace every … name" first could edit a verbatim quote and break request §C, "cites **every** first-party source". The false-match sentence now comes first and names the quote case. The rewrite comes second and is bounded to one rerun.
6. **A Linux run through WSL2 `Ubuntu`.** It failed (`HCS_E_HYPERV_NOT_INSTALLED`, virtualization is off). The WSL1 distribution `MuseUbuntu1` needs no VM and gave a real root userland.

### Trade-offs and residuals (named, not fixed)
- **Dropped:** the old `dirname "<worktree>"` pattern also caught the launcher checkout and its siblings when they sit outside HOME, for example `/srv/build/Vidbyte-SDK/…`. That pattern was the defect: it is `/` in every root container and a short common path elsewhere. The guard now keys on the paths that identify the person or the machine (the worktree family, HOME and the user name), and the :351 instruction to look for other spellings still applies. **Flip condition:** if a provider PR body is ever seen with a launcher-checkout path outside HOME, add `"${W%-onboard-*}/"` as a pattern and accept its false-match cost.
- **Residual false match, fail-closed:** page text quoted without a scheme whose path segment equals the user name. The run ends `PUBLISH_FAILED push local-path-guard`, keeping the worktree for the person. Measured: only cases D and E, and only on the informational body.
- **Not caught by any variant, and not a user identifier:** system paths such as `/usr/local/lib/python3.11/site-packages`.

## R-12 (Minor, trivial) · fixed @1cac918e
- provider-run.md:16 gains one final sentence: "The one exception is the pull-request attribution line your session's instructions give, which section 9 puts last." Every existing sentence on the line is byte-identical (verified with an anchored `grep -c … $` that prints `1`), so R-10's planned pins of "Never invent a URL." and "A URL you did not fetch never enters the PR, even when you know it." still hold.
- Spec INV-13 gains the same sentence as a provider-run.md quote, in INV-13's existing quoting style: `provider-run.md: "The one exception …" (r8, S5 repair 2 R-12)`. In the spec, "section 9" would otherwise read as the spec's own §9, so quoting keeps it unambiguous. §16 row s5r2-2.

## Optional: §9.1 Cerebras note · c660063e
The reason began "Every check was verified on first-party pages", which predates the r6 response-example check (D-11). It now reads "Every r3 check was verified on first-party pages. The r6 response-example check (D-11) passes through the first-party `/api-reference/chat-completions` page (opened 2026-10-17 in re-review round 1), whose example puts the text at `choices[0].message.content` and the usage under `prompt_tokens` and `completion_tokens`." I did not take this on trust. I re-read the re-reviewer's raw copy: `<scratch>/rr1/dl_r7/fetch-log.txt` has `2026-10-17T07:55:23Z https://inference-docs.cerebras.ai/api-reference/chat-completions 200 … curl-exit=0`, and `pages/cerebras-chat.txt` holds `"choices" : [ { "finish_reason" : "stop" , "index" : 0 , "message" : { "role" : "assistant" , "content" : "Hello! How can I assist you today?"` and `"usage" : { "prompt_tokens" : 69 , "completion_tokens" : 45 , "total_tokens" : 114 }`. §16 row s5r2-3. The §5 flowchart is untouched (S6 owns it).

## For the S2 test author: wording and command to pin

The text is in `.claude/skills/onboard-model-provider/references/provider-run.md`.

**R-11, `## 9. Publish`, the one `sh` fence holding `pr-body.md`.** Pin this command as a whole string:
```sh
W="<worktree>"; H="${HOME%/}"; H="${H:-$W}"; { sed -E 's#https?://[^[:space:]]*##g' "<evidence>/pr-body.md" || echo 'pr-body.md was not read'; } | grep -n -F -e "$(basename "$W")" -e "$H" -e "/$(basename "$H")/" -e "$(printf '\134%s\134' "$(basename "$H")")" -e 'pr-body.md was not read'; echo "grep exit $?"
```
**R-11, `## 9. Publish` prose (one line). Sentences to pin:**
- "It first deletes every `http://` and `https://` URL from the body it reads, because a local path never sits inside one, so a Sources URL segment such as `/app/` or `/dev/` cannot block the push."
- "The first is the worktree's last path segment, which ends in `-onboard-<slug>` and which `<evidence>` and the `-main` twin share, so those paths match in any spelling."
- "When HOME is `/` or empty, as for a container user with no home directory, the worktree path stands in for it."
- "A body it cannot read becomes the line `pr-body.md was not read`, which it matches, so a check that did not run never prints `grep exit 1`."
- "When a printed line holds no local path or user name, as when the match sits inside a quote from a vendor page, end the run `PUBLISH_FAILED push local-path-guard` without pushing."
- "Otherwise replace every local path and name in each printed line of the body with `<worktree>` or `<evidence>`, and run it once more; when that second run does not print `grep exit 1` either, end the run the same way."
- "Any exit other than 1 means the body is not yet clean or the check did not run: never push until it prints `grep exit 1`."

**R-11, `Rules for the whole run`.** Pin: "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats, and code never changes after a proof step failed."

**R-12, `Rules for the whole run`.** Pin, on the same prose line as "Never invent a URL.": "The one exception is the pull-request attribution line your session's instructions give, which section 9 puts last."

**Mutations a pinned test should turn red.** I executed these with `py -3.11 <s5r2>/mut_r11_r12.py <worktree>`, which edits the real file in place, runs the pack and writes the original bytes back (output `<s5r2>/mut_out.txt`, ending `restored: byte-identical`). The control gives `50 passed`. Each mutation also gives `50 passed` today, because nothing pins this text:
- `-e "$(basename "$W")"` changed to `-e "$(dirname "$W")"`;
- the `sed -E` URL strip replaced by `cat`;
- the `H="${H:-$W}"; ` fallback removed;
- ` || echo 'pr-body.md was not read'` removed;
- the bounded rerun changed to "and run it again until it prints `grep exit 1`.";
- the outcome changed to "end the run `PROOF_FAILED local-path-guard`.";
- the :23 clause ", and the body check's rerun in section 9 step 1," removed;
- the R-12 sentence deleted.

A behavioural test could also run the fenced line through `sh` over a temporary body, as `<s5r2>/guard_exec.py` does, if the pack allows a shell.

## Commands run (final output lines)
- `py -3.11 <s5r2>/guard_exec.py …/provider-run.md <s5r2>/provider-run.b2101e1d.md <s5r2> gitbash` at HEAD `c660063e`: `SUMMARY CURRENT (b2101e1d): 96/107` · `SUMMARY F1b (verifier): 101/107` · `SUMMARY FINAL (edited file): 107/107 cells as expected; failures: []`.
- `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -u root -- sh -c "id -un; …"`: `root` · `Linux 4.4.0-26100-Microsoft` · `/usr/bin/dash` · `grep (GNU grep) 3.11` · `sed (GNU sed) 4.9` · `HOME=/root`.
- `wsl.exe -d MuseUbuntu1 -u root -- sh|bash <s5r2>/lin/run.sh`, parsed: `SUMMARY linux: 107/107 cells as expected; failures: []`, under both shells.
- `wsl.exe -d Ubuntu …`: `WSL2 is unable to start since virtualization is not enabled on this machine` (`HCS_E_HYPERV_NOT_INSTALLED`).
- The S2 pack after each edit: `50 passed in 0.82s`, `0.77s`, `0.78s`, then `0.79s` in the gate.
- `py -3.11 <s5r2>/mut_r11_r12.py <worktree>`: `[CONTROL (no change)] 50 passed in 0.78s` … `[R-12 sentence deleted] 50 passed in 0.77s` (all nine rows `50 passed`) · `restored: byte-identical`; `git status --short` showed only this report afterwards.
