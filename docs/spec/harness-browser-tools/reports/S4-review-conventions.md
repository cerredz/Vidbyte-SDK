LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the layering, placement, import direction and lint ratchets hold, but one new three-level call chain and ten over-wide comment lines contradict AGENTS.md principle 1 and the comment-format field guide; both are mechanical fixes that change no behavior.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets)
- Placement is correct. The 7 StrEnums are in `lib/enums/browser_tools.py`, the 9 frozen slots records are in `lib/dataclasses/browser_tools.py`, the constants, the registry and the reaper are under `lib/`, and every enum plus `NativeThreadResultRecord` is exported from `lib/enums/__init__.py`.
- D-27 import direction holds. `hostkit/browser.py` imports `hostkit.errors` and `hostkit.skills` from their concrete modules, never from the façade. Each `mounts.py` imports nothing from its own subpackage. A006 stays at 34/34.
- KD-6 holds: `BrowserToolRequest` validates with `accepts_text` and constant messages, and never quotes caller text.
- The lint loop gives `SDK-LINT: PASS` with no rule above baseline (S009 346/350, S061 5/6, S041/S047/S052 at 0). The largest new file is 400 lines. `NativeBrowserRun.execute`, `BrowserToolRegistry.select` and the stream readers are narrated with `@intent` blocks. All 29 implementation commits use conventional titles carrying W/FR/AC IDs, and no generated file is tracked.

FINDINGS (ranked, max 15)

R-V1 [Blocker] [principle-1 call depth] vidbyte/harnesses/native/hostkit/browser.py:353 — `complete`/`discard` → `_remove` → `_remove_attempts` is a three-level call chain inside one class
  Evidence: `complete` (:293, :298) and `discard` (:317) call `NativeBrowserTools._remove`. At :361, `_remove` calls `NativeBrowserTools._remove_attempts`, which is the loop at :364-372. I parsed the AST of every changed `vidbyte/*.py` at `origin/main` and at `d00bd8ba` and kept only chains new in this PR. This is the only new chain: `NativeBrowserTools.complete -> _remove -> _remove_attempts` and `NativeBrowserTools.discard -> _remove -> _remove_attempts`. The split came from commit c9edd485 ("split the cache install out of ensure and bound folder removal by the cleanup budget").
  Failure: AGENTS.md principle 1 says a helper "should not call a third"; lift the call into the main function. Spec §12.4 has the checkbox "Call chains are one level deep" for harness modules (rows 16, 19–30), and that checkbox is not met.
  Smallest fix: merge the loop into `_remove` and bound it with a clock deadline instead of a nested function. Set `deadline = asyncio.get_running_loop().time() + browser_tools.BROWSER_REAP_TIMEOUT_SECONDS`. Then loop `for _attempt in range(BROWSER_REMOVE_ATTEMPTS)`, using `if not await asyncio.to_thread(folder.exists) or loop.time() >= deadline: return` before the sleep. S064 accepts an ordered comparison with a clock-derived value (header of `lint/rules/s064_retry_overall_deadline.py`). The nesting depth stays at 2.
  Do not simply move the loop inside the existing `with suppress(TimeoutError): async with asyncio.timeout(...)` block. That reaches S024 depth 4 (with → async with → for → with), and `MAX_NESTING_DEPTH = 3`.
  If the spec's "under `asyncio.timeout`" wording (§ line 1164) must stay, the alternative is to move the bounded attempt loop into a canonical `vidbyte/lib/` helper. That follows principle 5, and calls to another class do not count toward the depth limit.
  Spec IDs: §12.4 (harness modules), row 16, NFR-7, D-27 n/a

R-V2 [Blocker] [field-guide comment-format] vidbyte/lib/constants/native_threads.py:112 — ten added comment lines run past 72 columns
  Evidence: I scanned only the added lines in `git diff -U0 origin/main...d00bd8ba` for `#` lines longer than 72 columns:
  - grok/mounts.py:76 (73)
  - grok/wire.py:134 (73)
  - hostkit/browser.py:91 (73)
  - constants/browser_tools.py:36 (75), :130 (73), :234 (73), :310 (73)
  - constants/native_threads.py:112 (77)
  - registries/browser_tools.py:65 (74), :303 (74)
  Failure: `field-guide/vidbyte-sdk/comment-format.md` says "Wrap every comment line at 72 columns, counting the indent". Its Check is `awk 'length($0) > 72' <file> | grep -E '^\s*#'` and it "prints nothing for the files you touched". For the PR's own added lines it prints these 10. Spec §12.4 cites this guide as a source, and the owner rejected wide comment blocks in review (PR #690).
  Smallest fix: rewrap those 10 comment blocks. Keep each `# @intent` line first and within 20 lines of its `def` so A002 still matches. Then rerun the awk scan over the added lines.
  Spec IDs: §12.4 (harness modules; `comment-format.md`), NFR-7

R-V3 [Major] [A002 / spec §12.4] vidbyte/harnesses/native/hostkit/browser.py:364 — twelve new boundary functions lack an `@intent` block, hidden under A002 slack
  Evidence: I ran `IntentAnalyzer` on every changed file at `origin/main` and at `d00bd8ba`. In those files A002 findings go from 21 to 33, so +12 are new:
  - grok/browser.py:71 `_call`
  - grok/wire.py:92 `read_stream`
  - hostkit/browser.py:203 `_install`, :364 `_remove_attempts`
  - muse/browser.py:69 `_call`
  - muse/mounts.py:68 `_server`
  - opencode/browser.py:66 `_call`
  - opencode/mounts.py:62 `_server`, :89 `_rules`
  - lib/dataclasses/browser_tools.py:107 and :238 `__post_init__`
  - lib/registries/browser_tools.py:279 `_checked_keys`
  The repository total still reads 574/703, so the ratchet hides the regression.
  Failure: spec §12.4 says "`# @intent <name>` goes on its own line at each boundary rule". Rows 16 and 22–24 cite "A002 (`@intent` on boundaries)". `class-bound-helpers.md` says "a new boundary function needs its own `@intent` block". The lint gate passes only because A002 has 129 findings of slack.
  Smallest fix: add one `# @intent <name>` block to each of the 12 functions. If R-V1 merges `_remove_attempts` into `_remove`, the block goes on `_remove` instead. Then rerun the per-file A002 delta; it should be 0 new.
  Spec IDs: §12.4, rows 16, 19–24, NFR-7

R-V4 [Major] [README/source accuracy] vidbyte/lib/registries/browser_tools.py:104 — the tavily source comment states a false vendor fact, and the registries README rule contradicts the tavily row
  Evidence: the row comment at :103-104 says tavily "exits at start without TAVILY_API_KEY (spec A-10)". The sources say otherwise:
  - vendor-facts.md:274 gives tavily "needs key to start? no".
  - vendor-facts.md:436 says "Firecrawl, Exa, Tavily and SearXNG start without keys".
  - Spec A-10 says tavily "needs a key to answer calls (it starts without one)".
  `vidbyte/lib/registries/README.md:128-129` says "A tool that needs a key at start is `REQUIRED`; one that starts without a key but takes one is `OPTIONAL`". I dumped the key rules of all 13 rows. Tavily is `required` and is the only row that breaks the README rule.
  Failure: the README describes code that does not exist, and the comment invents a fact to make the row fit that rule. A maintainer who follows the README will set the next tool like tavily to `OPTIONAL`, or will "fix" tavily to `OPTIONAL`, and its calls will then fail without a key. This breaks the claim that the rows 12/15/35–37 docs say what the code does.
  Smallest fix:
  - Comment: change it to "it starts without TAVILY_API_KEY but answers no call without one (spec A-10)".
  - README: change the rule to "A tool that cannot answer a call without a key is `REQUIRED`; one that works without a key but takes one is `OPTIONAL`".
  Spec IDs: A-10, row 10, row 12 (registries README), FR-5

R-V5 [Minor] [narration accuracy] vidbyte/harnesses/native/hostkit/browser.py:354 — the cleanup comments say removal shares the reap's budget, but every step gets a fresh budget
  Evidence:
  - `_remove` (:354-358) says removal runs "all within the cleanup budget that also bounds the reap".
  - `constants/browser_tools.py:58-60` repeats "within the cleanup budget BROWSER_REAP_TIMEOUT_SECONDS that also bounds the reap".
  - In the code, `ProcessReaper.reap(..., timeout_seconds=BROWSER_REAP_TIMEOUT_SECONDS)` (:292, :316) gets its own budget, and each `_remove` call opens a new `asyncio.timeout(BROWSER_REAP_TIMEOUT_SECONDS)` (:360).
  - `complete` can run reap, then `_remove`, then `_remove`, which is up to 3 × 10 s.
  Failure: AGENTS.md principle 2 requires comments that never describe behavior that is not there. The comments promise a single bound that the code does not enforce. Spec line 169 and NFR-4 call for one bound. The behavioral side of this belongs to the engineering lens.
  Smallest fix: reword both comments to "each removal gets its own BROWSER_REAP_TIMEOUT_SECONDS budget". Alternatively, share one deadline across reap and removals, which is a behavioral change that engineering should decide.
  Spec IDs: line 169 (§5 cleanup), NFR-4, AC-13

R-V6 [Minor] [principle-4 validation] vidbyte/lib/dataclasses/browser_tools.py:113 — `BrowserToolDefinition` accepts a key rule that cannot be honoured
  Evidence: my probe ran `dataclasses.replace(BrowserToolRegistry.definition(BrowserTool.TAVILY), key_variable=None)`. It printed "REQUIRED stdio row with key_variable=None ACCEPTED: required None".
  `_checked_remote` (:154) rejects a remote row with package, version, entry, key variable or Chrome. It does not reject `arguments`, `profile_option`, `output_option`, `caps_option` or `environment`, which `_command` ignores silently for a remote row at :341-342.
  (Environment values that are not strings are rejected; that check held.)
  Failure: AGENTS.md principle 4 says a record checks its required fields and allowed values. A future REQUIRED or OPTIONAL stdio row with no variable would validate, and the caller's key would never reach the server. No current row triggers this.
  Smallest fix:
  - In `__post_init__`: for a stdio row, require `(key_rule is NONE) == (key_variable is None)`.
  - In `_checked_remote`: add `self.arguments or self.profile_option or self.output_option or self.caps_option or self.environment` to the rejection, keeping the constant message.
  Spec IDs: row 5 (records), FR-4, KD-6 (messages stay constant)

R-V7 [Minor] [literals/constants consistency] vidbyte/lib/process/reaper.py:94 — named constants exist, but literals are used beside them
  Evidence:
  - `reaper.py:94-95` and `:103-104` use `exit_code != 0` / `return 0`, and `:41`/`:103` use `sys.platform == "win32"`. In the same file, `reap` returns `native_threads.NATIVE_REAP_NONE_COUNT` (:48, :62, :77), and `NATIVE_WINDOWS_PLATFORM = "win32"` exists (`constants/native_threads.py:91`). Commit c665afdb is titled "…name its zero count" but left both helpers on the literal.
  - `hostkit/browser.py:132` uses `outcome.exit_code == 0`, while :218 uses `native_threads.NATIVE_SUCCESS_EXIT_CODE`. The module's own header (:5) says "The module holds no literals of its own (spec INV-15)".
  Failure: this breaks the brief's claim of "no literals or magic numbers outside constants". The static policy allows `0`, so it is a consistency gap rather than a lint failure. The A001 header claim is not true.
  Smallest fix: use `NATIVE_SUCCESS_EXIT_CODE` at `browser.py:132`, `reaper.py:94` and `:103`, `NATIVE_REAP_NONE_COUNT` at `reaper.py:95`, `:97` and `:104`, and `NATIVE_WINDOWS_PLATFORM` at `reaper.py:41` and `:103`. (`lib/process/runner.py` uses `"win32"` 7 times on main, so leave that file alone.)
  Spec IDs: INV-15, §12.4 A007 row

R-V8 [Minor] [principle-5 duplication] vidbyte/harnesses/native/grok/mounts.py:111 — `env_remove` is byte-identical to `OpencodeMounts.env_remove`
  Evidence: `grok/mounts.py:111-116` and `opencode/mounts.py:54-59` have the same comment and the same two lines: `selections = [...]` and `return tuple(selection.definition.key_variable.value for ... if ... key_variable is not None and selection.key is None)`.
  Failure: AGENTS.md principle 5 says to write shared logic once. D-20's rule ("a mounted tool's unpassed key variable goes into `env_remove`") now lives in two places, which can drift.
  Smallest fix: put it once, as `NativeBrowserTools.unkeyed_variables(mount)` in hostkit or as a read-only property on `BrowserMount`. Both mounts then call it (spec line 339 still lists `env_remove` per harness, so keep the name as the call site).
  Spec IDs: D-20, rows 19–20, INV-13

R-V9 [Minor] [A001 headers] vidbyte/harnesses/native/grok/wire.py:11 — the TESTS lines of all six changed `threads.py`/`wire.py` headers omit the browser test files that now cover them
  Evidence: in grok, opencode and muse, `threads.py` and `wire.py` each list only `test_harness_threads_errors/threads/acceptance.py` (`grep -c '^TESTS:.*browser'` = 0 in all six). Meanwhile `test_harness_threads_browser_{acceptance,contract,lifecycle,mounts,runtime}.py` exercise `tool_calls`, `read_stream` and `execute(mount=…)`. The FUNCTION INVENTORY lines were updated; the TESTS lines were not.
  Failure: the A001 header misdirects the next editor about which tests to run after changing a reader.
  Smallest fix: add the browser test files that touch each module to its TESTS line.
  Spec IDs: rows 25–30, §12.4 A001

R-V10 [Minor] [scope-adding] [class-bound-helpers] vidbyte/harnesses/native/opencode/mounts.py:31 — `OpencodeMounts.check` is a no-op reached through a pass-through seam
  Evidence: `OpencodeBrowserHarness.check` (`opencode/browser.py:95-97`) only calls `OpencodeMounts.check`, whose body is `return None` (`mounts.py:37`).
  Failure: `class-bound-helpers.md` says "do not wrap a call that needs no transformation in a pass-through alias". Two methods carry one decision, which is "accept everything".
  Smallest fix: keep the `@intent opencode-carries-every-selection` block on `OpencodeBrowserHarness.check`, return there, and drop `OpencodeMounts.check`. This reverses spec rows 19/22, which name the delegation, so it counts as scope-adding.
  Spec IDs: rows 19, 22

VERIFIED CLAIMS:
- HELD: "`SDK-LINT: PASS` with no rule worse than baseline". The full `lint/run.py` exited 0 with A006 34/34, A007 255/255, S009 346/350, S061 5/6, S020 1/1, S054 3/3, S064 4/4, S041/S047/S052 0, A009 0 and A002 574/703. In substance, A002 regressed by +12 in the changed files under slack (R-V3).
- BROKEN once: "call chains one level deep in `hostkit/browser.py` and the three `browser.py`/`mounts.py`". The AST diff of all changed files against main found exactly one new chain (R-V1). `ensure` → `_install` and the registry `select` helpers are flat.
- BROKEN: comments are at most 72 columns. There are 10 added lines over the limit (R-V2).
- HELD: every new file is under 1,000 lines. The largest is `constants/browser_tools.py` at 400.
- HELD: the A001 FUNCTION INVENTORY of `hostkit/browser.py` matches its classes and methods. The inventories of the harness threads and wire modules name the new members.
- BROKEN: the A001 TESTS lines are stale (R-V9), and the header claim "no literals of its own" is false (R-V7).
- HELD: D-27 concrete hostkit imports, and `mounts` modules import nothing from their subpackage.
- HELD: the 7 enums and `NativeThreadResultRecord` are exported from `lib/enums/__init__.py`; `ProcessReaper` and `BrowserToolRegistry` are exported from their package inits.
- HELD: KD-6. No validation message in `lib/dataclasses/browser_tools.py` interpolates a caller value.
- PARTLY BROKEN: "no dataclass validation that skips a field". A non-string environment value is rejected, but a REQUIRED stdio row with no key variable is accepted (probe output, R-V6).
- HELD/BROKEN: the REPO_MAP native and `lib/process` paragraphs match the code. The registries README key rule contradicts the tavily row, the only one of 13 rows to do so (R-V4).
- HELD: `tests/features/harness_threads/test_harness_threads_static_policy.py` passes 3 tests. CI run 39075450892 (Source 3.11, Source 3.12 and Package) and run 39075452414 (Static policy) are both green.
- HELD: commit hygiene. The diff carries no `.pyc`, `__pycache__` or `egg-info`, and every implementation commit has a conventional title with IDs.

COMMANDS RUN:
- `git diff origin/main...d00bd8ba -- <file>` per changed file; `git diff --name-only/--stat origin/main...d00bd8ba`; `git show origin/main:<f>` and `git show d00bd8ba:<f>`; `git log --format='%h %s' origin/main..d00bd8ba`; `git diff --name-only ... | grep -E "pyc|egg-info|__pycache__"` (no match).
- `PYTHONPATH=$(pwd) py -3.11 lint/run.py` (exit 0, `SDK-LINT: PASS`).
- Inline `py -3.11` script running `lint.rules.a002_intent_comments.IntentAnalyzer` on main and PR blobs of every changed file (21 → 33).
- `awk` scan of added `#` lines over 72 columns on `git diff -U0` (10 hits).
- `py -3.11 scratchpad/s4conv_depth.py <changed files>`: an AST three-level call-chain diff against main (one new chain).
- `PYTHONPATH=$(pwd) py -3.11 scratchpad/s4conv_probe.py`: validation probe on `BrowserToolDefinition`. Also a `py -3.11 -c` dump of `key_rule` for all 13 registry rows.
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_static_policy.py` (3 passed).
- `gh run view 39075452414` and `gh run view 39075450892` (both green).
- `sed`/`grep` over `lint/rules/{s064,s024,a002}*.py` headers, `field-guide/vidbyte-sdk/{comment-format,class-bound-helpers}.md`, spec §12.4 and lines 169/339/1164, and vendor-facts lines 274/436.
