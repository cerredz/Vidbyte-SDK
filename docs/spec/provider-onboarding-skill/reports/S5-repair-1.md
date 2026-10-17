# S5 repair 1: provider-onboarding-skill

Stage: S5 repair, iteration 1 of 8 · Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-provider-onboarding-skill` · Branch `feat/onboard-model-provider-skill` · Start `c84f577c` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1175 (draft)

`<scratch>` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad`. This iteration's reproducers are in `<scratch>/s5r1/` (below, `<s5r1>`); the verifier's are in `<scratch>/s4ver/`. Each one reads the command it tests from the skill file itself, runs it, and cleans up after itself.

## Gate matrix

All gates were run in this worktree, at HEAD `39e37702`, in this iteration.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 pack) | `PYTHONPATH="<worktree>" py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` | PASS (46/46) | `46 passed in 0.94s` |
| lint | `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py` (exit 0) | PASS | `S063 IMPROVED 4 -> 3. Lower it with: …` · `S064 RATCHETED: 4 known finding(s). …` · `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH="<worktree>" py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited known-red test | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `============ 1 failed, 5815 passed, 16 skipped in 90.76s (0:01:30) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-provider-onboarding-skill).` The log also holds `SDK-LINT: PASS` (line 182) and `E       AssertionError: assert 148 == 120` |
| inherited proof | detached probe at `origin/main` 6f5a7310: `git worktree add --detach "C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-pos-probe" origin/main`, then `PYTHONPATH="<probe>" py -3.11 -m pytest "<node>" -q -p no:cacheprovider`, then `git worktree remove --force` | red on main too | `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed in 1.48s` · `probe removed: yes`. The harness file is unchanged against base 72a4ade1 (`git diff --quiet` exit 0). |
| import path | `PYTHONPATH="<worktree>" py -3.11 -c "import inspect, vidbyte; print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-provider-onboarding-skill\vidbyte\__init__.py` |
| full local gate, package | `py -3.11 scripts/run_ci.py --stage package` (PYTHONPATH unset; exit 0) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep | remote-only (dispatch) | not run; its inputs are unchanged | `git diff --name-only 72a4ade1..HEAD -- vidbyte .semgrep` lists nothing. The local `semgrep` binary raises a Traceback, and `py -3.11 -m semgrep` prints only a deprecation notice. |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1175` | none attached (CI is dispatch-only) | `no checks reported on the 'feat/onboard-model-provider-skill' branch` |
| tests contract | `git diff 8e9b8b7f..HEAD -- tests` | empty | 0 lines |

The push went `1144e198..39e37702 feat/onboard-model-provider-skill -> feat/onboard-model-provider-skill`, a fast-forward. The remote branch had been at `1144e198`, so this push also carried the two S4 docs commits.

## Per finding

Every fix is one commit. "Before" means the file at `c84f577c` (or the commit just before the fix); "after" means the fixed file.

### R-1 (Blocker) · fixed @42834bc5
- **Root cause.** INV-13 ("never invent a URL") was stated nowhere in the procedure, and row D1 made every run write two documentation links that no rule tied to a page the run opened.
- **Change.** One rule in "Rules for the whole run": every URL the run writes into code, a test, a README or the PR body is either the base URL fact from section 3's Endpoint check (or its scheme and host, as row C7 writes it) or the final URL of a 2xx line in `<evidence>/fetch-log.txt`. The rule names the pricing and key-source comments, the D1 links and the Sources URLs. The D1 note and the Sources bullet now tie D1's links to the fetch log and list them with their opened date.
- **Evidence.** `grep -n -i -E 'invent|fetch-log'` over provider-run.md now finds the rule at line 16, the D1 note and the Sources bullet. S2 pack `46 passed`.
- **Judgment call, flagged.** INV-13 says "Every URL in a provider PR is one the subagent opened". A base URL such as `https://api.<vendor>/v1` is an API endpoint, not a page to open. The rule treats it as an INV-9 fact quoted from a page the run opened, which is how the spec already treats it. If the orchestrator reads INV-13 strictly, the base URL would also need a fetch-log line.

### R-2 (Blocker) · fixed @0e972f8c
- **Root cause.** `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` diffs the branch against the merge-base under `vidbyte/tools` and `vidbyte/lib/configs`. Row A13 edits `vidbyte/lib/configs/structured_output.py`, so the node fails on the branch and passes on the base twin. The known-red rule therefore ended every A13 run `PROOF_FAILED gate-source`.
- **Reproduced first.** `bash <scratch>/s4ver/a13_probe.sh` gave: twin `1 passed` ×3; branch `assert (['vidbyte/lib...ed_output.py'] == []` ×3; A1-only `1 passed`; twin plus the control edit gives the same failure.
- **Change.** A new §8.3 bullet, the field guide's method narrowed. It applies to that node only, never its whole file, when both checks hold. (1) `git -C <worktree> diff --name-only <base> HEAD -- vidbyte/tools vidbyte/lib/configs` prints exactly `vidbyte/lib/configs/structured_output.py`. (2) On a new twin, `echo '# control edit' >> …/structured_output.py` makes the node fail with the same `AssertionError` line as on the branch. That check runs last, after every other node's twin block. Spec D-15 (decision and reasons), §11 (`local-ci-verification.md:45-50`), §16 row s5r1-1, §17 r6, `revision: 6`.
- **Evidence (executed from the skill text).** `py -3.11 <s5r1>/r2_exec.py 6f5a7310…` builds a scratch `--shared` clone at the current `origin/main` and a real sibling worktree on `feat/provider-cerebras`. It then runs the procedure's own fences, read from provider-run.md:
  ```
  == case A13: branch changes ['vidbyte/lib/configs/structured_output.py', 'vidbyte/lib/enums/model_provider.py']
     check 1 (procedure's scoped diff) printed ['vidbyte/lib/configs/structured_output.py'] -> holds
     control-edit twin: add+edit exit 0; run exit 1; E       AssertionError: assert (['vidbyte/lib...ed_output.py'] == []; remove exit 0
     check 2 (same AssertionError line as the branch) -> holds
     verdict: EXCLUDE
  == case WIDE: branch changes ['vidbyte/lib/configs/__init__.py', 'vidbyte/lib/configs/structured_output.py', ...]
     check 1 (procedure's scoped diff) printed ['vidbyte/lib/configs/__init__.py', 'vidbyte/lib/configs/structured_output.py'] -> FAILS
     check 2 (same AssertionError line as the branch) -> holds
     verdict: PROOF_FAILED gate-source
  == case A1: branch run: exit 0; 1 passed
  ```
- **What this taught.** The `AssertionError` line truncates the path list (`['vidbyte/lib...ed_output.py']`), so it is the same for one changed file and for two. Check 2 alone would let an extra `vidbyte/lib/configs` change hide. The scoped-diff check is what bounds the exclusion. Spec D-15 records this.
- **Not changed, flagged.** EC-40 ("passes 3 of 3 runs there → PROOF_FAILED") falls outside the grant. The §16 row says EC-40 is read subject to the D-15 exception. Whether EC-39 or EC-40 gets an explicit line is the orchestrator's call.

### R-4 (Major) · fixed @6dc92270
- **Change.** The C9 template comment is now `# The gateway does not serve <s>, so the call is` / `# DIRECT, and only the <s> key leaves.`
- **Evidence.** `awk '/^[[:space:]]*#/ && length($0) > 72'` over provider-run.md prints nothing. With `<s>` replaced by each 9-character seed slug (sambanova, deepinfra, fireworks), it also prints nothing. Only a slug of 20 characters or more reaches 73 columns, and no seed slug is that long.

### R-5 (Major) · fixed @ff307d1e
- **Change.** The fixture-fake collision probe (§3.7) and the A9 modality probe now start with `cd <worktree> && `.
- **Evidence.** `py -3.11 <s5r1>/r5_exec.py` runs every `PYTHONPATH=<worktree> <py> -c` command, as the file spells it, from a decoy launcher holding fake `vidbyte` and `tests` packages. Before: the collision probe printed `['K_DECOY']`, and the A9 probe raised the decoy's ImportError. After: `[]` and `['ModelModality.AUTO']`, both imported from the worktree.

### R-6 (Major) · fixed @02102cdb
- **Change.** Step 3 is now `git worktree add … && git -C "$WORKTREE" rev-parse HEAD; echo "add exit $?"`. When `add exit` is not 0, the orchestrator launches no subagent, records `local-branch` and continues the walk. The cleanup is one `&&` chain ending `; echo "cleanup exit $?"`. When it fails, the orchestrator leaves what is left and continues. The rollback text now says "the cleanup block above". `## Rules` now says what happens with two sessions in one clone and with two sessions in two clones.
- **Evidence.** `py -3.11 <s5r1>/r6_exec.py` reads both fences from SKILL.md and runs them as two sessions in one scratch clone. Before: session B printed session A's SHA and the shell exited 0. A failed remove was followed by `rm -rf` of the evidence (`left: worktree True, evidence False`). After: session B prints `add exit 255` and no SHA. A failed remove prints `cleanup exit 128` and keeps everything (`left: worktree True, evidence True, branch True`). After an unlock, the same block cleans up fully.
- **Spec.** EC-52's "the second push is refused" still holds for two clones. In one clone, the failed add now stops the second session earlier. EC-52 is outside the grant and is unchanged.

### R-7 (Major) · fixed @1c0ec03c
- **Change.** (a) The fact kinds now include the response text path and the usage key names. (b) §3.2 Dialect now needs first-party quotes from a response example. They must show the text at `choices[0].message.content` and the usage as `prompt_tokens` and `completion_tokens`. Otherwise the vendor is `not-openai-compatible`; this includes no response example and the Responses names. Spec D-11 (decision and reasons), INV-9 (fact kinds), §16 row s5r1-2.
- **Evidence for the claim the text makes.** `ChatCompletionUsage.from_usage_payload({'input_tokens': 12, 'output_tokens': 2})` returns `None`. With `total_tokens` added, it returns `(None, None)` token counts. With the chat names it returns `(12, 2)`.
- **Not taken: optional (c)**, adding the vendor to `_CHAT_PROVIDERS` in `managed_text_fixtures.py` so that C9's canned answer uses the chat names. The verifier dropped it as cosmetic, because C9 asserts nothing about usage. It would also change the §12.3 C11 row, which is outside the grant. If the orchestrator wants it: add `` `_CHAT_PROVIDERS` `` to the C11 Symbol cell (W2 and W3 accept it, and `_CHAT_PROVIDERS` exists in that file). Then add one C9 assertion, `ModelProvider.<E>.usage_class().from_usage_payload(response.usage)` is not None, which needs `response = …run("Hi")`.
- **Effect on expected outcomes.** A seed vendor whose first-party pages show no response example now ends `not-openai-compatible`. It no longer gets wired with usage that might go unrecorded. This fails closed, as the field guide requires ("check … response shape against them").

### Minors tagged trivial
| ID | Commit | Change | Evidence |
|---|---|---|---|
| R-V4 | 7b61eaee | D1 adds only the Official Provider Documentation row. The Symbol cell still names both headings, because W2 pins it. D-24 is amended, and the §12.3 D1 row is kept byte-identical to provider-run.md's. | `vidbyte/providers/README.md` on `origin/main`: the matrix lists adapter modules, the `Generic \| compatible.py` row covers the six `OpenAICompatibleProvider` subclasses, and none has a row of its own. `compatible.py` defines exactly DeepSeek, GLM, MiniMax, Kimi, Meta and Mistral. |
| R-V5 | ccbba23d | The description gains "Use it when a person wants the SDK to gain new model vendors, each as a source-backed pull request to review, without wiring them by hand." | The YAML still has exactly 3 keys. The description is 895 characters (limit 1,536). |
| R-C4 | 5e89c83b | `## Seed vendors` states the request's three criteria and the D-23 rank order. | Text matches request.md §C and spec D-23. C4 and C5 still pass. |
| R-E3 | 1dbdfede | Both `gh api` reads end with `; echo "prs exit $?"`. Any value but 0 is `NETWORK_BLOCKED - api.github.com <status>`, never an empty list. | Live run: both reads print `prs exit 0`. A 404 control prints `gh: Not Found (HTTP 404)` and `prs exit 1`. |
| R-E4 | 416483ad | Skip rule (d) adds `\|\| test -e "$WORKTREE-main"`. The `local-branch` text and the person's rollback now name the twin, and the rollback includes `git worktree remove --force "$WORKTREE-main"`. | The line as written prints `paths exit 1` with no twin and `paths exit 0` with only a `-main` directory present. |
| R-E8 | 39e37702 | See below: a new defect was found while fixing it. | `py -3.11 <s5r1>/re8_exec.py` |

**R-E8, and the defect found while fixing it.** The guard is the `grep -n -i -F … "$(id -un)" pr-body.md` line before the push. On this machine it could never pass, for two independent reasons:
1. Git for Windows ships GNU grep 3.0, which aborts on `-i -F` in the C locale. Plain `grep -n -i -F -e x file` prints `Aborted` and exits 134 when `LANG`/`LC_ALL` are unset, which they are in the agent's Bash tool. With `LC_ALL=en_US.UTF-8`, the same command works. `grep -i` without `-F` works, so the `x-deny-reason` check in §2 is fine. `git grep -i -F` (§3.4) is git's own grep and is fine too.
2. `id -un` prints `PC` here, while every local path holds the home folder name `422mi`. So the login pattern never matched a real local path, yet it matched "pc" anywhere in the body, for example "JSON-RPC".

The guard therefore always printed `grep exit 134`, never the `grep exit 1` the push waits for, and the procedure named no outcome. **Fix:** drop `-i`. Match the home directory's last segment only as a path segment: `-e "/$(basename "$HOME")/"`, plus the backslash form `-e "$(printf '\134%s\134' "$(basename "$HOME")")"`. Say to rewrite the body and rerun until it prints `grep exit 1`, and never to push before that.

The backslash is octal because a doubled backslash in a command collapses to one on its way through the agent's Bash tool on Windows. `printf '[%s]\n' "\\$(basename "$HOME")\\"` run through the tool printed `[$(basename /c/Users/422mi)\]`. The octal form, run through the same tool, printed `[\422mi\]` and matched a `C:\Users\422mi\…` body.

Simulation results after the fix, with HOME set to `/c/Users/422mi` and then to a home whose last segment is `node`. The body that names "node IDs" and "JSON-RPC" gives `grep exit 1`. The Git Bash path, the drive-letter backslash path and the Linux path bodies each give `grep exit 0` under the home they belong to, and `grep exit 1` otherwise. Before the fix, every case gave `grep exit 134`.

I also scanned both skill files for any other doubled backslash. The only one left is the C4 Add cell (`\\|`). It is README text the agent writes with the file tool, not a shell command.

### Not mine: R-3, R-8
Both stay `open — routed to S2 author (orchestrator decision)`. For the S2 author, these are the sentences my fixes left in place or rewrote. Pin the final wording:
- S5 / D-29: Qualify step 5's fourth filter is unchanged, and self-check line `assert Runner._normalize_provider_and_model(None, model)[0] is None, model` is unchanged.
- X8: the known-red bullet "Otherwise exclude it only when its file is unchanged, meaning `git -C <worktree> diff --quiet <base> HEAD -- <file>` exits 0, …" is unchanged. R-2 added a separate bullet after the twin fence. A test should pin both of its checks: `prints exactly one line, \`vidbyte/lib/configs/structured_output.py\`` and `the same \`AssertionError\` line as on the branch`.
- X9: the §7 sentence "At least one must be outside `test_provider_keys_contract.py`" is unchanged.
- A5: the keep bullet now reads "… keep the worktree, its `-evidence` directory and the branch, so no unpushed work is lost; … until the person runs the cleanup block above, and `git worktree remove --force "$WORKTREE-main"` when that twin exists …". The cleanup block is now one `&&` line ending `echo "cleanup exit $?"`.
- R-8: the C9 template's Bearer line is unchanged; only its comment was wrapped. The back-pressure union sentence is unchanged. "An example key alone is not enough" is unchanged.
- `<scratch>/s4eng/real` and `mut2.py` mutate a copy taken at 32ca7991. Refresh that copy from the current files before re-running them.

## Findings I believe are wrong
None. Every assigned finding reproduced before its fix.

## Test changes proposed
None. `git diff 8e9b8b7f..HEAD -- tests` is empty, and no test contradicts the spec.

## Still open, and what I would try next
- R-3 and R-8: routed to the S2 author.
- Follow-ups not taken (verifier tag `follow-up`): R-E5 (rerun the whole file before calling a node flaky), R-E6 (an `sk-`/`eyJ` overlap arm), R-E7 (scope-adding), R-E2f (a test that pins the vintage direction).
- Spec lines outside the grant, which the orchestrator may want aligned: EC-40 (R-2 exception), EC-52 (the same-clone case now ends at the add), and EC-30 (it could name "no chat-completions response example" as an R-7 cause).
