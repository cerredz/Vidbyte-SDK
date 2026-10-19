# S4 findings verifier — harness-browser-tools

Stage: S4, verifier step · Reviewed diff: `origin/main...d00bd8ba` (local HEAD 62cc8bd4; `git diff --stat d00bd8ba HEAD` touches only pipeline.md and the three S4 review reports, so the source under test is `d00bd8ba`) · Output: `docs/spec/harness-browser-tools/review.md` · Commits: none · Git state changes: none.

Scratch evidence lives under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad/s4verify/`:
- `test_r_e1_grok_failed_call.py` — the R-2 reproduction through the shipped fakes;
- `chains.py` — the AST three-level call-chain diff;
- `a002delta.py` — the per-file A002 delta;
- `fixcheck.py` — the R-3 fix shape run against S064, S024 and the chain check, with `browser_fixed.py` as its output;
- `s4_candidate_fixes.py` — a pytest plugin that applies the R-2 and R-3 fixes in memory.

Nothing in the worktree was written except review.md and this report.

## 1. Merge map (original → merged)

| Original | Lens | Proposed | Merged ID | Final severity | Disposition |
|---|---|---|---|---|---|
| R-V2 | conventions | Blocker | R-1 | Blocker | CONFIRMED |
| R-E1 | engineering | Major | R-2 | Blocker | CONFIRMED; raised one tier |
| R-V1 | conventions | Blocker | R-3 | Blocker | CONFIRMED |
| R-C2 | conformance | Minor | R-3 | Blocker (merged) | CONFIRMED; same root cause as R-V1 |
| R-V5 | conventions | Minor | R-3 | Blocker (merged) | CONFIRMED; same root cause as R-V1 |
| R-V4 | conventions | Major | R-4 | Major | CONFIRMED |
| R-C1 | conformance | Major | R-5 | Major | CONFIRMED |
| R-V3 | conventions | Major | R-6 | Major | CONFIRMED |
| R-E2 | engineering | Minor | R-7 | Minor | passed through (trivial) |
| R-V7 | conventions | Minor | R-8 | Minor | passed through (trivial) |
| R-V9 | conventions | Minor | R-9 | Minor | passed through (trivial) |
| R-V6 | conventions | Minor | R-10 | Minor | passed through (trivial) |
| R-V8 | conventions | Minor | R-11 | Minor | passed through (follow-up) |
| R-C3 | conformance | Minor | R-12 | Minor | passed through (follow-up) |
| R-E3 | engineering | Minor | R-13 | Minor | passed through (follow-up) |
| R-E4 | engineering | Minor | R-14 | Minor | passed through (follow-up) |
| R-E5 | engineering | Minor | R-15 | Minor | passed through (follow-up) |
| R-E6 | engineering | Minor | R-16 | Minor | passed through (follow-up) |
| R-E7 | engineering | Minor | R-17 | Minor | passed through (follow-up) |
| R-E8 | engineering | Minor | R-18 | Minor | passed through (follow-up) |
| R-V10 | conventions | Minor [scope-adding] | R-19 | Minor | passed through (follow-up, scope-adding) |

Totals: 21 raw findings become 19 merged ones. Confirmed: 3 Blockers and 3 Majors. Minors: 13. Refuted: 0. Downgraded: 0.

**Ordering.** Confirmed findings are listed most severe first. Within a tier they are ordered by the size of the fix:
- R-1 touches comment text only.
- R-2 changes about 3 code lines, plus spec wording and one test parameter.
- R-3 rewrites about 20 lines in one class.
- R-4 changes two text lines.
- R-5 changes the spec, the README and one test constant.
- R-6 adds 12 comment blocks.

## 2. Verifications

### R-1 (R-V2) — comment lines over 72 columns — CONFIRMED, Blocker

**Rule.** `field-guide/vidbyte-sdk/comment-format.md` says "Wrap every comment line at 72 columns, counting the indent". Its check, `awk 'length($0) > 72' <file> | grep -E '^\s*#'`, "prints nothing for the files you touched". The same entry says the rule is not a lint rule and that untouched files are left alone, so the check applies to the lines this PR adds.

**My scan.** I scanned the `+` lines of `git diff -U0 origin/main...d00bd8ba -- 'vidbyte/*.py'`, tracking line numbers from the hunk headers:
```
vidbyte/harnesses/native/grok/mounts.py:76 (73)
vidbyte/harnesses/native/grok/wire.py:134 (73)
vidbyte/harnesses/native/hostkit/browser.py:91 (73)
vidbyte/lib/constants/browser_tools.py:36 (75)
vidbyte/lib/constants/browser_tools.py:130 (73)
vidbyte/lib/constants/browser_tools.py:234 (73)
vidbyte/lib/constants/browser_tools.py:310 (73)
vidbyte/lib/constants/native_threads.py:112 (77)
vidbyte/lib/registries/browser_tools.py:65 (74)
vidbyte/lib/registries/browser_tools.py:303 (74)
```
That is 10 of 439 added comment lines (`grep -E '^\+[[:space:]]*#' | wc -l` gives 439).

**Severity.** The orchestrator's rubric makes contradicting a field-guide lesson a Blocker. The overflow is small (1–5 columns), but the guide's check is binary, and the owner rejected comment width in PR #690. The fix is mechanical. I kept the reviewer's tier.

### R-2 (R-E1) — Grok counts a failed "Tool not found" call as connection evidence — CONFIRMED, raised to Blocker

**Code.**
- `grok/wire.py:189-190`: `connected` appends `rawInput.tool_name` from every `tool_call` event, whatever its final status.
- `grok/browser.py:125`: `missing` adds `call.tool for call in calls.calls`, which includes `FAILED` calls.

**Vendor facts.**
- Line 147: a call to an absent tool returns `Tool not found: canary__echo_secret_ok`.
- Line 557: after a resume without `--agent`, `canary__canary_ping` → `Tool not found`.
- Line 158: "A server that cannot start is not fatal … rc=0".
- Line 122: "A `use_tool` call succeeds without a prior `search_tool` call", so the model can name a tool directly.

**Reproduction through the shipped fakes.** The fake models this branch at `fake_browser.py:689`: `session is None or not session.connected` → `"Tool not found"`, status `failed`. I ran a scratch test with the conftest loaded as a plugin:
```
PYTHONPATH="$W;$W/tests/features/harness_threads" py -3.11 -m pytest -q -s -p conftest --rootdir="$W" -c pyproject.toml <scratch>/test_r_e1_grok_failed_call.py -p no:cacheprovider
[control-no-call-playwright] raised code=browser.tools_unavailable :: run_grok_with_browser failed with browser.tools_unavailable. ...
[dead-mount-failed-call-playwright] RETURNED SUCCESS tool_calls=(BrowserToolCall(tool=<BrowserTool.PLAYWRIGHT: 'playwright'>, name='browser_navigate', status=<BrowserToolCallStatus.FAILED: 'failed'>),) thread=976b8c6d-...
[dead-mount-failed-call-jina] RETURNED SUCCESS tool_calls=(BrowserToolCall(tool=<BrowserTool.JINA: 'jina'>, name='read_url', status=<BrowserToolCallStatus.FAILED: 'failed'>),) thread=48df0892-...
FAILED ::test_dead_grok_mount_is_never_a_success[dead-mount-failed-call-playwright]
FAILED ::test_dead_grok_mount_is_never_a_success[dead-mount-failed-call-jina]
2 failed, 1 passed in 19.36s
```
The control passing shows that the fixture path is live, and that adding one failed call is the only thing that flips the outcome. The failure covers both the stdio case (EC-16) and the keyless remote case (EC-45, A-19).

**Spec reading.**
- FR-14's governing clause is "raises `browser.tools_unavailable` … when the vendor's own output shows the mount did not work". A "Tool not found" reply is exactly that output.
- A-19 says "nothing runs silently without the tool".
- EC-45 says "absent from `available_commands` and never called".

The letter "listed … or called" (FR-14, D-11, §9.1 line 643) was written on the premise that a call reaches the server; it is not a reasoned exception. See adjudication A.

**Why it is raised to a Blocker.** The rubric defines Blocker as "wrong, unsafe, or broken result". Returning success for a mount that never connected is a wrong result on a P0 requirement, and on the outcome this feature exists for ("a turn that never reached a browser is never reported as success").

**Mitigation, noted and judged insufficient.** The result's `tool_calls` do show `FAILED`. But an unattended caller is promised that success means the tools worked.

**Fix verified in scratch.** The plugin `s4_candidate_fixes.py` makes two changes:
- `connected` reads only `available_commands.tools`;
- `missing` adds only `COMPLETED` calls.

Results with the plugin loaded:
```
reproduction:  3 passed in 77.18s (0:01:17)   (all three cases raise browser.tools_unavailable)
PYTHONPATH="$W;$SP" py -3.11 -m pytest -q -p s4_candidate_fixes -p no:cacheprovider tests/features/harness_threads/test_harness_threads_browser_lifecycle.py
.............s...............                                            [100%]
28 passed, 1 skipped in 82.78s (0:01:22)
PYTHONPATH="$W;$SP" py -3.11 -m pytest -q -p s4_candidate_fixes -p no:cacheprovider tests/features/harness_threads/test_harness_threads_browser_mounts.py
.................................................                        [100%]
49 passed in 140.32s (0:02:20)
```
(The first attempt of the reproduction run hit a one-off collection `FileNotFoundError`. An identical rerun was clean.)

**Accepted cost of the fix.** A server that is slower than Grok's grace, so never listed, and whose only call failed for a tool-level reason, now raises `tools_unavailable` with the thread id. That error is loud and recoverable, which is the direction FR-14 chooses.

**Rejected alternative.** Matching "Tool not found" in the update text would parse vendor prose, which is brittle.

### R-3 (R-V1 + R-C2 + R-V5) — cleanup call chain and per-removal budget — CONFIRMED, Blocker

**Chain.** My `chains.py` maps same-class calls (`Class.x`, `self.x`, `cls.x`) and same-module function calls, looking for A → B → C. I ran it on the 32 changed `vidbyte/*.py` files at both revisions:
```
main: 1  pr: 3
--- new in PR:
vidbyte/harnesses/native/hostkit/browser.py :: NativeBrowserTools: complete -> _remove -> _remove_attempts
vidbyte/harnesses/native/hostkit/browser.py :: NativeBrowserTools: discard -> _remove -> _remove_attempts
```
The one chain already on `main` is `FailureCode.from_exception -> _from_exception_name -> _from_exception_fallback`, which is untouched and out of scope.

AGENTS.md principle 1: "that second function should not call a third". There is no exemption, because all three methods belong to `NativeBrowserTools`. Spec §12.4 has the matching checkbox. The rubric makes contradicting AGENTS.md a Blocker.

**Budget.** Reading `browser.py`:
- `complete` reaps with its own `timeout_seconds=BROWSER_REAP_TIMEOUT_SECONDS` (:292), then calls `_remove(profiles)` (:293) and, when there are no artifacts, `_remove(folder)` (:298).
- Each `_remove` opens a fresh `asyncio.timeout(BROWSER_REAP_TIMEOUT_SECONDS)` (:360).

So the worst case is 3 × 10 s on success and 2 × 10 s on discard. INV-12 asks for the kill and the profile removal within one `BROWSER_REAP_TIMEOUT_SECONDS`. The comments at :354-358 and `constants/browser_tools.py:57-60` claim a single shared budget, and AGENTS.md principle 2 forbids comments that describe behaviour that is not there.

**Typical case.** A locked file fails fast, so five attempts with 0.2 s pauses take about 1 s. Only a slow `rmtree` reaches the extra budgets. NFR-4 (the reap alone within 10 s) holds.

**Why merged.** One design choice causes both defects: wrapping each removal in its own `asyncio.timeout`. S3's own note in pipeline.md says the attempts were split into `_remove_attempts` because of S064 and S024 nesting under that wrapper. It also restarts the budget per removal. One edit fixes both.

**Fix shape verified.** `fixcheck.py` patches a scratch copy so that `complete` and `discard` compute one deadline before the reap and pass it to `_remove(folder, deadline)`. That function inlines the loop and returns when `not exists or loop.time() >= deadline`. Results:
```
[shipped] S064 findings: []
[shipped] S024 findings: []
[shipped] three-level chains: [('complete', '_remove', '_remove_attempts'), ('discard', '_remove', '_remove_attempts')]
[shared-deadline fix] S064 findings: []
[shared-deadline fix] S024 findings: []
[shared-deadline fix] three-level chains: []
[control: no deadline check] S064 findings: [(361, 'NativeBrowserTools._remove')]
[control: no deadline check] S024 findings: []
[control: no deadline check] three-level chains: []
```
The control shows that S064 does inspect the inlined loop. The shared-deadline version passes because of its clock comparison, not because the rule is blind.

The lifecycle file passes with this fix applied in memory (`28 passed, 1 skipped`, run above). A002 on the fixed copy flags `_remove` (`retries`, through `_attempt`) in place of `_remove_attempts`, so the fix must add an `@intent` block there (it ties to R-6):
```
fixed: [(203, '_install', ('external boundaries',)), (355, '_remove', ('retries',))]
shipped: [(203, '_install', ('external boundaries',)), (364, '_remove_attempts', ('retries',))]
```
**Rejected shapes.**
- The reviewer's per-`_remove` deadline is valid for principle 1, but it keeps the 3 × 10 s gap, so the comment would still need rewording.
- Moving the loop inside the existing `suppress` + `async with` reaches S024 depth 4.
- `NativeSkillFolders.remove` can raise (`shutil.rmtree`, `hostkit/skills.py:58`), so the inner `suppress(OSError)` must stay.

### R-4 (R-V4) — tavily comment and registries README key rule — CONFIRMED, Major

**The comment.** `registries/browser_tools.py:103-104` reads: "it exits at start without TAVILY_API_KEY (spec A-10)". The sources say otherwise:
- vendor facts line 274: tavily "needs key to start? no";
- line 436: "Firecrawl, Exa, Tavily and SearXNG start without keys";
- spec A-10: "needs a key to answer calls (it starts without one)".

**The README.** `registries/README.md:128-129` reads: "A tool that needs a key at start is `REQUIRED`; one that starts without a key but takes one is `OPTIONAL`". The tavily row is `key_rule=BrowserKeyRequirement.REQUIRED`, which contradicts that rule.

`grep` finds no test that pins either text, so the fix touches no test.

**Severity: Major, not Minor.** This README is the instruction AGENTS.md tells the next agent to read before changing the folder. Its rule produces the wrong key rule for exactly the class of tool tavily is, and the source comment invents a vendor fact to make the row fit. FR-18 and AC-24 require the docs to describe the code.

### R-5 (R-C1) — NG-2 states a false reason; Codex limitation unstated — CONFIRMED, Major

**Git evidence.**
```
git log --oneline -1 6f5a7310 → 6f5a7310 feat(harnesses): add CodexHost with agent tools, thread helpers and skill functions (#1055)
git merge-base --is-ancestor 6f5a7310 d00bd8ba → true;   ... 6f5a7310 origin/main → true
grep -c 'Q-19' spec.md → 0
```
`vidbyte/harnesses/native/codex/` exists.

**README.** README.md:178 introduces `native/codex/` and `CodexHost`, then later says "Each harness also has three browser functions", naming only the grok, opencode and muse functions. No sentence says `CodexHost` has none.

**Decision boundary.** pipeline.md (2026-10-17 "Scope call") records that Codex is out and that Q-19 is a follow-up. So the finding is about documentation honesty, never about building Codex support. A human reviewer comparing "every harness … so far in the repo" with the tree will ask about Codex, and the spec's stated reason is false.

**Interaction found by the verifier.** README.md:178 is pinned byte for byte by `tests/features/codex_host/test_codex_host_packaging.py:99` (`README_BULLET`), which is asserted at :204 as `lines[index + 1 : index + 3] == [README_BULLET, ""]`. Editing the bullet breaks that test unless the constant changes in the same commit. The fix in review.md gives both routes. The REPO_MAP pin (`REPO_MAP_SECTION`, :98) needs no change, because its "Each also has browser functions" refers to "Grok Build, opencode and Muse Code" in the same sentence.

### R-6 (R-V3) — 12 new A002 hits hidden by ratchet slack — CONFIRMED, Major

**My per-file analyzer run.** `a002delta.py` keys findings by (file, function name, categories). Its output:
```
changed files: 32  A002 at origin/main: 19  at d00bd8ba: 30
NEW at head:
  grok/browser.py:71 _call; grok/wire.py:92 read_stream; hostkit/browser.py:203 _install, :364 _remove_attempts;
  muse/browser.py:69 _call; muse/mounts.py:68 _server; opencode/browser.py:66 _call; opencode/mounts.py:89 _rules, :62 _server;
  lib/dataclasses/browser_tools.py:238 __post_init__; lib/registries/browser_tools.py:279 _checked_keys
```
My key collapses same-named functions. A raw run on `lib/dataclasses/browser_tools.py` returns `[(107, '__post_init__', ...), (238, '__post_init__', ...)]`, which makes 12 new. That matches the reviewer's 21 → 33 once same-named functions are counted separately.

**Context.**
- At `origin/main`, `grok/threads.py _call`, `muse/threads.py _call`, `opencode/threads.py _call` and `grok/wire.py read` already carry the same A002 hit. So 4 of the 12 copy their #1036 siblings.
- The other 8 hold real policy whose reason is narrated in prose without the marker. Example: `_rules` explains the fail-closed deny-then-allow order, but has no `@intent` line, while its caller `config` does.

**Severity.** Spec §12.4 requires `@intent` "at each boundary rule", with source A002, and rows 16 and 22–24 cite it. The repo-wide ratchet (574/703) hides the regression, so the per-file delta is the evidence, as the briefing directs. I kept Major. The target is 0 new A002 findings per changed file; a repair agent may keep the 4 sibling-mirroring blocks short.

## 3. Adjudications between reviewers

**A. Grok failed-call evidence (engineering R-E1 vs conformance "considered and rejected").**

The conformance lens rejected the idea because the spec says "listed or called". The engineering lens raised it as Major. Ruling: engineering is right.

- The spec's operative requirement is FR-14's clause "when the vendor's own output shows the mount did not work".
- A-19 and EC-45 promise that a server that never mounts yields `tools_unavailable`, and that "nothing runs silently without the tool".
- "Tool not found" is the vendor's own output that the mount did not work.
- The word "called" in FR-14, D-11 and §9.1 assumed that a call reaches a server. The vendor facts (line 122) show that the model can call `use_tool` by name without the server existing.

So the spec wording must be corrected to "completed a call" together with the code (R-2). This narrows the evidence to what the spec already promises; it is not scope-adding.

**B. Cleanup budget severity (conformance R-C2 Minor, conventions R-V5 Minor, conventions R-V1 Blocker).**

Merged into R-3, because one design choice (a per-removal `asyncio.timeout`) caused both the call chain and the restarted budget, and one edit fixes both. Severity follows the highest member, Blocker. The budget gap alone would have stayed Minor: the typical case is about 1 s, and NFR-4 holds.

**C. Calibration across lenses.**

R-E1 was rated Major by its own lens, while R-V1 and R-V2 (conventions) were rated Blocker. Under the orchestrator's rubric:
- R-V1 and R-V2 are Blockers, because they contradict AGENTS.md and a field-guide lesson.
- R-E1 is a Blocker, because it is a wrong result.

All three are Blockers. Within the tier they are ordered by fix size.

## 4. Severity blind spots checked

1. **A convention fix that breaks a test (found, folded into R-5).** The README edit for R-C1 breaks the byte pin in `test_codex_host_packaging.py:99/:204`.
2. **A convention fix that breaks a lint rule (checked, folded into R-3).** The obvious inlining of `_remove_attempts` under the existing `with suppress` / `async with asyncio.timeout` reaches S024 depth 4. Dropping the timeout without a clock comparison trips S064, which the control run proved at :361. The shared-deadline shape passes both.
3. **One fix creating another finding (folded into R-3 and R-6).** Inlining the loop moves the A002 hit to `_remove`, so `_remove` needs an `@intent` block. New `@intent` blocks and rewrapped comments must stay at 72 columns or less (R-1) and stay within 20 lines of their `def` (A002 window).
4. **The opencode analogue of R-2 (considered, not raised).** `opencode/browser.py:112` counts any mounted-tool call, including failed ones, as evidence. The vendor facts do not record what opencode prints when the model names an MCP tool whose server never connected; opencode is believed to route unknown tool names to its own `invalid` tool, which the reader would skip. With nothing in the vendor facts to anchor it, and with Q-9 having fixed opencode's evidence rule, I did not raise it. A future vendor probe could settle it.
5. **Muse.** `missing` is always `()` by design (Q-17). The required-server failure is the evidence, so the Grok-style hole does not apply.

## 5. Notes for the repair agent

- **R-2** touches comments and the spec in several places that say "listed or called":
  - `grok/browser.py` header ARCHITECTURE NOTE and the `missing` `@intent`;
  - the `grok/wire.py` `connected` `@intent`;
  - spec FR-14, D-11, the §9.1 mount table "Required evidence" row, §9.1 Readers line 643, and AC-12.

  Update them together (AGENTS.md principle 2).
- **R-3** also updates the `hostkit/browser.py` header FUNCTION INVENTORY (it names `_remove_attempts`) and KNOWN EDGE CASES, and spec §17 deviations 4 ("under `asyncio.timeout`") and 13 (it lists `_remove_attempts`).
- **Test-file edits.** R-2 adds a test parameter, and R-5's preferred route changes `README_BULLET`. If the S5 brief forbids test edits, report it rather than skip the fix.
- **Commands to re-check.**
  - R-1: `git diff -U0 origin/main...HEAD -- 'vidbyte/*.py' | awk '...'` (the scan in §2). It must print nothing.
  - R-6: `py -3.11 <scratch>/a002delta.py origin/main HEAD <changed files>`. It must list no NEW entries.
  - R-3: `<scratch>/fixcheck.py` shows the S064/S024 check. Better still, `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S064`, then `--rule S024`, then `--rule A002`, each ending `SDK-LINT: PASS`.

## 6. Commands run (final lines)

- `git diff --stat d00bd8ba HEAD` → `4 files changed, 474 insertions(+), 3 deletions(-)`. All four are docs.
- `git status --short` → empty, before and after.
- `py -3.11 chains.py origin/main|d00bd8ba <32 files>` → `main: 1  pr: 3`, plus the two new chains above.
- R-2 reproduction:
  - shipped code: `2 failed, 1 passed in 19.36s`;
  - with candidate fixes: `3 passed in 77.18s (0:01:17)`.
- Lifecycle file with candidate fixes → `28 passed, 1 skipped in 82.78s (0:01:22)`.
- Mounts file with candidate fixes → `49 passed in 140.32s (0:02:20)`.
- `PYTHONPATH=$W py -3.11 fixcheck.py` → the six result lines quoted in §2 R-3.
- `PYTHONPATH=$W py -3.11 a002delta.py origin/main d00bd8ba <32 files>` → `changed files: 32  A002 at origin/main: 19  at d00bd8ba: 30`.
- The awk scan of added comment lines → the 10 lines quoted in §2 R-1.
- `git merge-base --is-ancestor 6f5a7310 d00bd8ba` and the same against `origin/main` → both true.
- `grep -c Q-19 spec.md` → 0.
- `grep -rn "needs a key at start\|exits at start without TAVILY" tests/ vidbyte/ lint/` → only the two source lines, with no test pin.

**Not run, by instruction:** the full suite, `scripts/run_ci.py`, real vendor CLIs, the paid §4 snippet, and the full `lint/run.py`. The rule analyzers were run directly, and CI on `d00bd8ba` is already green.
