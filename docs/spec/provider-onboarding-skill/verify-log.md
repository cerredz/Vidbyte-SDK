# Verification log: Onboard-model-provider skill

Gate set (from context/code-map.md §1 and AGENTS.md):
- **S2 pack (local).** `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider`
- **Lint (local).** `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py`. Lint reads tracked files only, so commit or `git add` first. The last line must be `SDK-LINT: PASS`.
- **Full local gate, source stage (local).** `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source`. PYTHONPATH is a one-command prefix and is never exported. The stage runs lint, then pytest.
- **Full local gate, package stage (local).** `py -3.11 scripts/run_ci.py --stage package` with no PYTHONPATH.
- **Semgrep (remote-only).** `static-policy.yml` runs only on dispatch, and `run_ci.py` does not run semgrep. It scans `vidbyte/` only, and this branch changes no file under `vidbyte/` or `.semgrep/` (`git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing).
- **Remote checks.** `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175`. CI is dispatch-only, so nothing attaches to the PR.

Known red on pristine main, not this branch's:
- `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 148 == 120`).
- The MCP stdio flake `test_cancelled_waiter_does_not_break_transport`.

## Iteration 1 — 2026-10-17 — agent report: reports/S5-repair-1.md
Scratch reproducers: `<s5r1>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/s5r1/`. Each reads the command it tests from the skill file and cleans up after itself.

**Defects in:**
- Blockers R-1 and R-2.
- Majors R-4, R-5, R-6 and R-7.
- Minors tagged trivial: R-V4, R-V5, R-C4, R-E3, R-E4 and R-E8.
- R-3 and R-8 were routed to the S2 test author by the orchestrator and were not touched.
- Gates in: the S2 pack `46 passed`, `SDK-LINT: PASS`, the source stage with only the known-red failure, and the package stage passing.

**Hypotheses and attempts, in order:**
- **R-1.** Root cause: no rule stated INV-13 where URLs are written. One rule bullet now says every written URL is either the base URL fact or the final URL of a 2xx fetch-log line. The D1 note and the Sources bullet now tie D1's links to the fetch log. It worked first time. A base URL is treated as a quoted INV-9 fact, not a page the run opened (flagged in the report).
- **R-2.** The verifier's endorsed fix was taken: one §8.3 bullet for that one node, requiring the exact scoped diff plus a control edit on a new twin. Executing it from the skill text (`<s5r1>/r2_exec.py`) showed something the review did not say. The node's `AssertionError` line truncates the path list, so it reads the same when the branch changes `structured_output.py` alone and when it changes that file plus another configs file. The control-edit comparison alone would therefore let an extra configs change hide, and the scoped-diff check is the real bound. The WIDE case confirmed this: check 1 fails, check 2 holds, and the verdict is `PROOF_FAILED gate-source`. Not tried: the runner-up from R-C1, "never apply A13". It ships every vendor as PROMPT_ONLY.
- **R-4.** Wrapped the comment. A first split, after "DIRECT,", would reach 64 + slug length − 3 columns. I wrapped earlier, after "call is", so any slug up to 19 characters fits.
- **R-5.** Added `cd <worktree> && ` to both `-c` probes. A decoy-launcher run of every `-c` command as written proved the before and after.
- **R-6.** Chained the add and rev-parse, and added `echo "add exit $?"` so the orchestrator sees the failure. A failed add records `local-branch` and the walk continues. The cleanup became one `&&` chain with `echo "cleanup exit $?"`. A first scratch harness called plain `bash` from Python, which resolved to WSL's `System32\bash.exe` and did nothing. Use `C:/Program Files/Git/usr/bin/bash.exe`. `shutil.rmtree` cannot delete git object files on Windows; use `rm -rf` through Git Bash.
- **R-7.** Taken: (a), the fact kinds, and (b), Dialect requiring a first-party response example with `choices[0].message.content`, `prompt_tokens` and `completion_tokens`. Not taken: (c), `_CHAT_PROVIDERS`. The verifier judged it cosmetic, and it would change the §12.3 C11 row, which is outside the grant. Verified the text's claim: `ChatCompletionUsage.from_usage_payload` gives `None` or `(None, None)` for the Responses names.
- **R-E8.** First attempt: `-e "/$(id -un)/" -e "\\$(id -un)\\"`. Testing it exposed three facts:
  1. `id -un` prints `PC` here, not the `422mi` that appears in local paths.
  2. Git for Windows' grep 3.0 aborts (exit 134) on `-i -F` in the C locale, which is the agent's Bash tool environment. The guard therefore could never print `grep exit 1` on this machine, even before my change.
  3. A doubled backslash in a command collapses to one on its way through the agent's Bash tool, which turned the backslash pattern into the literal `$(basename …)\`.

  Final form: no `-i`; the home directory's last segment, matched only between slashes; and the backslash form spelled `$(printf '\134%s\134' …)`. The procedure now names the outcome: rewrite the body and rerun until it prints `grep exit 1`. A simulation over sample bodies under two homes passes, and the same line run through the Bash tool matched a `C:\Users\422mi\…` body.
- **R-V4, R-V5, R-C4, R-E3, R-E4.** Each worked first time. The evidence is in the report.

**Changes:**
- `42834bc5` R-1
- `0e972f8c` R-2, with spec D-15, §11 and r6
- `6dc92270` R-4
- `ff307d1e` R-5
- `02102cdb` R-6
- `1c0ec03c` R-7, with spec D-11 and INV-9
- `7b61eaee` R-V4, with spec D-24 and the §12.3 D1 row
- `ccbba23d` R-V5
- `5e89c83b` R-C4
- `1dbdfede` R-E3
- `416483ad` R-E4
- `39e37702` R-E8

All are pushed to `feat/onboard-model-provider-skill`. `git diff 8e9b8b7f..HEAD -- tests` is empty.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 pack) | `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` | PASS (46/46) | `46 passed in 0.94s` |
| lint | `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited known-red test | `SDK-LINT: PASS` (log line 182) · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 5815 passed, 16 skipped in 90.76s (0:01:30)` · `CI failed: Command failed with exit code 1: … -m pytest` |
| inherited proof | `git worktree add --detach …/vidbyte-sdk-pos-probe origin/main` (6f5a7310); `PYTHONPATH=<probe> py -3.11 -m pytest <node> -q`; `git worktree remove --force` | red on main | `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed in 1.48s`. The harness file is unchanged against base 72a4ade1 (`diff --quiet` exit 0). The probe was removed. |
| import path | `PYTHONPATH="<worktree>" py -3.11 -c "import inspect, vidbyte; print(inspect.getfile(vidbyte))"` | PASS | `…\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py` |
| full local gate, package | `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep | remote-only (dispatch) | not run, inputs unchanged | `git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175` | none attached (CI is dispatch-only) | `no checks reported on the 'feat/onboard-model-provider-skill' branch` |

**Still open:**
- R-3 and R-8, routed to the S2 test author. The report lists the final wording to pin.
- Follow-ups R-E5, R-E6, R-E7 and R-E2f, not in scope.
- Spec lines outside the grant that the orchestrator may want aligned: EC-40 (the R-2 exception), EC-52 (in one clone, a second session now stops at the add) and EC-30 (an R-7 cause).

## Iteration 2 — 2026-10-17 — agent report: reports/S5-repair-2.md
Scratch reproducers: `<s5r2>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/s5r2/`. `guard_exec.py` reads the guard line from the file it is given. `mut_r11_r12.py` mutates the real file, runs the pack, and restores the file byte for byte.

**Defects in:**
- R-11 (Major) and R-12 (Minor, trivial) from `review.md` "Re-review round 1".
- The optional §9.1 Cerebras note.
- R-9 and R-10 are test findings routed to the S2 test author and were not touched.
- Gates in: the S2 pack `50 passed`, `SDK-LINT: PASS`, the source stage with only the known-red failure, and the package stage passing (all at b2101e1d, per the re-review).

**Hypotheses and attempts, in order:**
- **R-11, reproduced first.** The old line, read from `git show b2101e1d:…`, matches 96 of 107 cells as expected. The clean body gives `grep exit 0` in the `/workspace`, `/app`, HOME `/`, HOME empty, `/dev/` and devcontainer cases, and a missing body gives `grep exit 2`. The root cause is that `dirname "<worktree>"` and `$HOME` can both be `/`.
- **F1b (verifier) executed: 101/107.** It misses every backslash or `/c/` spelling of the worktree (6 cells). Windows Python prints `D:\src\…-onboard-<slug>` (pytest `rootdir:`, run_ci `cwd=`), and nothing else catches that when the checkout is outside HOME.
- **Final: F1b with `$(basename "$W")` in place of `$W`.** That is a substring of `$W`, so the change only adds matches. It always ends `-onboard-<slug>`, and `<evidence>` and the twin share it.
  - The final line gives 107/107 under Git Bash.
  - It gives 107/107 under both dash and bash as root in a real Linux userland (WSL1 `MuseUbuntu1`, GNU grep 3.11, GNU sed 4.9).
  - End to end as root, with real `/workspace-onboard-cerebras-evidence` and `/app-…-evidence` directories, it gives clean `1`, dirty `0`, missing `0` with the sentinel.
  - Typed through the agent's Bash tool on Windows it gives clean `1`, `C:\Users\422mi\…` `0`, missing `0` with the sentinel, a worktree outside HOME in backslash spelling `0`, and HOME `/` clean `1`.
- **Rejected:**
  - matching the launcher checkout `${W%-onboard-*}`, because `/app` false-matches quoted page text such as `cloud.cerebras.ai/app/keys`;
  - stripping scheme-less URLs, because the rule gets harder to trust and can delete a real path with a dotted segment;
  - matching `\<name>` with no trailing separator, because it reopens R-E8's ordinary-word matches.
- **First outcome wording reordered.** The harness showed that, with HOME `/home/dev` or `/home/node`, quoted page text without a scheme (`…/dev/node/`) still matches. That fails closed. But "replace every local path and name" came first and could lead an agent to edit a verbatim quote. The false-match sentence now comes first and names the quote case, and the rewrite is bounded to one rerun.
- **Dropped on purpose.** The old parent pattern also caught a launcher checkout outside HOME. Flip condition: add `"${W%-onboard-*}/"` if a provider PR ever shows one.
- **Environment.** WSL2 `Ubuntu` does not start here (`HCS_E_HYPERV_NOT_INSTALLED`, virtualization off). The WSL1 distribution `MuseUbuntu1` works with `-u root`. Pass `MSYS_NO_PATHCONV=1` so Git Bash leaves `/mnt/c/…` arguments alone.
- **R-12.** It worked first time. One final sentence was appended to provider-run.md:16, and every existing sentence is byte-identical (anchored `grep -c` prints `1`). INV-13 quotes it in INV-13's existing style, so "section 9" cannot be read as the spec's §9.
- **§9.1 Cerebras note.** It was corrected after I re-read the re-reviewer's raw copy of `/api-reference/chat-completions` (fetch-log `2026-10-17T07:55:23Z … 200`). It holds `"message" : { "role" : "assistant" , "content" : …` and `"usage" : { "prompt_tokens" : 69 , "completion_tokens" : 45`.
- **Mutations (for the S2 author).** Eight R-11 and R-12 text mutations each give `50 passed`, and so does the control. Nothing pins the new text yet.

**Changes:**
- `8edfdec1` R-11, with spec EC-63, s5r2-1, r8 and `revision: 8`
- `1cac918e` R-12, with spec INV-13 and s5r2-2
- `c660063e` the §9.1 Cerebras note, with s5r2-3

All are pushed to `feat/onboard-model-provider-skill` as a fast-forward (`b2101e1d..c660063e`). `git diff --name-only b2101e1d..HEAD -- tests` is empty.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 pack) | `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` | PASS (50/50) | `50 passed in 0.79s` |
| lint | `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited known-red test | `SDK-LINT: PASS` (log line 182) · `E       AssertionError: assert 148 == 120` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 5819 passed, 16 skipped in 86.45s (0:01:26)` · `CI failed: Command failed with exit code 1: … -m pytest` |
| inherited proof | `git worktree add --detach …/vidbyte-sdk-r2-probe origin/main` (6f5a7310); `PYTHONPATH=<probe> py -3.11 -m pytest <node> -q -p no:cacheprovider`; `git worktree remove --force` | red on main | `E       AssertionError: assert 167 == 120` / `1 failed in 1.62s`. The harness file is unchanged against base 72a4ade1 (`diff --quiet` exit 0); the counts differ because the branch sits on the older base. The probe was removed (`remove exit 0`). |
| MCP flake | — | not triggered | it passed inside the source stage |
| import path | `PYTHONPATH="<worktree>" py -3.11 -c "import inspect, vidbyte; print(inspect.getfile(vidbyte))"` | PASS | `…\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py` |
| full local gate, package | `py -3.11 scripts/run_ci.py --stage package` (`env -u PYTHONPATH`) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep | remote-only (dispatch) | not run, inputs unchanged | `git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175` | none attached (CI is dispatch-only) | `no checks reported on the 'feat/onboard-model-provider-skill' branch` |

**Still open:**
- R-9 and R-10, routed to the S2 test author.
- Pins for the R-11 and R-12 text. `reports/S5-repair-2.md` lists the exact command, the sentences and eight mutations that a pinned test should turn red.
- Follow-ups R-E5, R-E6, R-E7 and the RR-2 observation (an unwritable checkout parent leaves stray branches), not in scope.
- The §5 flowchart still says only "push or PR fails" for `PUBLISH_FAILED`. S6 owns it.
