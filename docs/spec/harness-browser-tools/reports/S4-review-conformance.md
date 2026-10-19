LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The nine functions, every layer, the §8.4 budget and the plain-path byte-identity all match spec r4 and the request, but the spec and the README misstate the Codex position: NG-2 claims #1055 is not on `main` when it is merged into this branch, and no document says that CodexHost has no browser functions.

Reviewed: `git diff origin/main...d00bd8ba` (worktree `vidbyte-sdk-harness-browser-tools`, branch `feat/harness-browser-tools`), measured against spec.md r4, request.md, test-plan.md and AGENTS.md. Local HEAD 2ea367e4 differs from d00bd8ba only by `pipeline.md`.

WHAT THE IMPLEMENTATION GETS RIGHT
- **One call path for all nine functions (INV-1, §5).** Each `<H>BrowserThreads._call` builds `NativeThreadRequest` and `BrowserToolRequest`, then hands a `<H>BrowserHarness` to the single `NativeBrowserRun.execute` (hostkit/browser.py:66-110). That function runs the §5 mermaid order exactly:
  1. register the secrets;
  2. `select`;
  3. `harness.check`;
  4. `prepare`, which checks Node only for stdio tools, Chrome only for `needs_chrome`, then cache `ensure`, then `mkdtemp`;
  5. `harness.run`, then `tool_calls`, then `require(missing)`, then `complete`;
  6. on any failure, a shielded `discard`.
  No harness can skip a layer.
- **AC-1 is real.** `SNIPPET` in test_harness_threads_browser_acceptance.py is byte-identical to spec §4. Only the two workspace literals are replaced. The test passes against the offline fakes and asserts the thread id, the calls, `()` and one artifact path. The nine signatures match INV-2/FR-2: the plain parameters, with `tools: Sequence[str]` keyword-only and required, `tool_keys` defaulting to None, and a return of `BrowserThreadResult`.
- **The plain paths are byte-identical (INV-14).** Every new branch in the three `threads.py`/`wire.py` pairs is gated on `mount is None` and keeps the original value:
  - Grok: `json` output, `GROK_CLI_MAX_OUTPUT_BYTES`, and `env_remove=()`, which is the dataclass default at lib/dataclasses/process.py:60;
  - Muse: `settings=None` and `web_tools_off=False`;
  - opencode: `config_content(request, None)`.
  The plain `_call`s return `.result`. Pre-existing test diffs only re-pin expected values that §13 lists; no assertion was weakened.
- **The budget and the Never list hold.** There are exactly 12 new files and 34 new classes, and no file outside the §12.3 rows: the 25 modified non-test files map to rows 2-4, 6, 8, 9, 11, 12, 14, 15, 17, 18 and 25-37. There are 0 new dependencies, 0 config keys, `lint/baseline.json` is unchanged, and there are no suppressions, no `npx`, no `@latest` and no approve-all. The errors also conform:
  - the four `browser.*` codes each have one cause and one next step (D-29);
  - every factory path routes through `_error`, so `NATIVE_THREAD_RESULT_RECORDS` covers all 18 operations;
  - the D-22 widened texts are present.

FINDINGS (ranked, max 15)

R-C1 [Major] [user's words / honesty] docs/spec/harness-browser-tools/spec.md:79; vidbyte/harnesses/README.md:178 — NG-2 says Codex is not on `main`, and nothing tells a reader that CodexHost has no browser functions
  Evidence:
  - spec.md:79 reads: "NG-2 — Browser functions for Claude Code, Codex or Gemini CLI. — *Why not:* those harnesses are not on `main`: PR #1044 and #1055 are open (KD-2)."
  - `origin/main` 6f5a7310 is "feat(harnesses): add CodexHost … (#1055)". `git merge-base --is-ancestor 6f5a7310 d00bd8ba` succeeds, and `vidbyte/harnesses/native/codex/` is in the tree. (#1044, Claude Code, is indeed not on main.)
  - The spec has no Q-19, although the orchestrator records "Codex is a follow-up (Q-19)" as a decision.
  - README.md:178 opens the `native/` bullet with "`native/codex/` is a host… `CodexHost`". It then says "Each harness also has three browser functions" and lists only grok, opencode and muse. No sentence says that CodexHost has none.
  - Defense: the package docstring (native/__init__.py:3-4) scopes the browser functions to the three thread subpackages. Prosecution wins the tie: the README is the user-facing claim, and the spec's stated reason is false.
  Failure: the request asks for "every harness … so far in the repo". The scope decision (grok/opencode/muse; Codex later) is not relitigated here. But the only written justification for leaving Codex out is a factually wrong statement, and the README sentence a reader sees right after CodexHost implies "each harness" has browser functions. A human reviewer comparing the README to the tree will flag both.
  Smallest fix (docs only, no code):
  1. In spec NG-2, replace the reason for Codex with: "Codex (#1055) merged mid-run as a host-shaped harness (`CodexHost`, an SDK wrapper rather than a vendor-CLI thread function); its browser functions are a follow-up (Q-19)".
  2. Add the Q-19 row.
  3. In README.md:178, add one sentence: "`CodexHost` has no browser functions yet."
  Spec IDs: NG-2, KD-2, G-1, G-5, FR-18, AC-24; request "every harness … so far in the repo".

R-C2 [Minor] [spec conformance / deviation accuracy] vidbyte/harnesses/native/hostkit/browser.py:292-298, 316-317, 353-361 — cleanup can take two to three times `BROWSER_REAP_TIMEOUT_SECONDS`; the code comment and deviation 4 claim one shared budget
  Evidence:
  - `complete` runs `ProcessReaper.reap(..., timeout_seconds=BROWSER_REAP_TIMEOUT_SECONDS)` (line 292), then `_remove(profiles)` (293), then `_remove(folder)` when nothing was saved (298). `discard` runs the reap (316), then `_remove(folder)` (317).
  - Each `_remove` opens its own fresh `asyncio.timeout(BROWSER_REAP_TIMEOUT_SECONDS)` (line 359).
  - So the worst case is 30 s on a successful call with no artifacts, and 20 s on a successful call with artifacts or a failed one.
  - The comment at lines 355-358 says "all within the cleanup budget that also bounds the reap". S3 deviation 4 says the tries "satisfy … FR-15's 10 s".
  - INV-12 says "within `BROWSER_REAP_TIMEOUT_SECONDS`, to kill every process … and to remove the profiles".
  Failure: if a Windows lock is released late or a large profile is removed slowly, the call can block past the documented bound. The comment and the deviation record describe a guarantee the code does not give. NFR-4 (the reap alone within 10 s) still holds.
  Smallest fix: compute one deadline (`loop.time() + BROWSER_REAP_TIMEOUT_SECONDS`) before the reap. Pass the remaining time to the reap and to each `_remove` through `asyncio.timeout_at(deadline)`. Alternatively, correct the comment and deviation 4, and amend INV-12 to "kill within 10 s; each removal within a further 10 s".
  Spec IDs: INV-12, FR-15, NFR-4, EC-22, §17 deviation 4.

R-C3 [Minor] [spec conformance] vidbyte/harnesses/native/hostkit/browser.py:259-266; vidbyte/lib/dataclasses/browser_tools.py:258 — the §9.1 rule "`folder` is absolute and outside the workspace" is not enforced anywhere
  Evidence:
  - §9.1 (spec.md:554) gives `BrowserMount` the invariant "`folder` is absolute and outside the workspace". FR-10 and INV-5 say the same.
  - The record checks only `not servers or not folder.is_absolute() or artifacts != folder / BROWSER_ARTIFACTS_FOLDER`.
  - `prepare` uses `tempfile.mkdtemp` and has an `@intent browser-call-folder-outside-the-workspace` comment, but it never compares the folder with `request.workspace`.
  Failure: when TMPDIR/TEMP points inside the workspace (for example, a CI job that sets `TMPDIR=$PWD/.tmp`), the SDK writes the per-call folder, the Chrome profiles and the kept artifacts into the workspace. That breaks INV-5 ("the SDK writes nothing into the workspace") without any error. The tests always place the temp folder outside the sandbox workspace, so AC-2 cannot catch it.
  Smallest fix: in `prepare`, after `mkdtemp`, check `folder.resolve().is_relative_to(Path(request.workspace).resolve())`. If it is, remove the folder and raise `LAUNCH_FAILED`, with a detail that names the temp folder. Alternatively, drop "outside the workspace" from the §9.1 record rule and note it as accepted under EC-24.
  Spec IDs: INV-5, FR-10, §9.1 `BrowserMount`, AC-2.

VERIFIED CLAIMS:
- HELD: the §8.4 budget (12 files, 34 classes, 0 deps, 0 config keys) and "no file outside §12.3". Checked with `git diff --stat` / `--name-status` and a class count over the added files.
- HELD: INV-2 / FR-2 / AC-3 for all 9 signatures, by `inspect.signature` against the plain functions. Native `__all__` has 28 names; each subpackage `__all__` has 6.
- HELD: INV-1 / §5 mermaid. All nine `_call`s reach `NativeBrowserRun.execute`, and the layer order matches the diagram, including the shielded `discard` and the re-raise.
- HELD: INV-14 (plain paths byte-identical, from the `mount is None` branches) and INV-16 (the plain `expected` values are unchanged through `NATIVE_THREAD_RESULT_RECORDS`).
- HELD: AC-1. The snippet is identical to §4 lines 96-120, and the test passes offline.
- HELD: the weighted words.
  - "pass in strings": `tools` is a `Sequence[str]` of `<tool>[:<capability>,...]`.
  - "programmatically": these are importable async functions.
  - "same": the plain parameters plus `tools` and `tool_keys`.
  - "all layers": one `execute` for every harness.
  - "15-20 popular ones": the registry has 13 rows, which Q-16 accepted (not relitigated).
- HELD: the Muse WSL and Grok limits are stated honestly. The README lists the per-harness mount limits. `BROWSER_MUSE_WSL_DETAIL` names the keyless remote tools, and `BROWSER_GROK_BUDGET_DETAIL` tells the caller to narrow capabilities or mount fewer tools.
- HELD (§17 deviations, 9 of 16 checked):
  - 1: the record refuses non-registry `tool_keys` names by position.
  - 8: the reaper counts only stopped processes (the PowerShell `$count++` sits after `Stop-Process`).
  - 9: `_make_folder` pre-creates `artifacts/` and `profiles/<tool>/`.
  - 11: `OpencodeMounts.check` is a no-op.
  - 13: `GrokMounts.agent_path`, `_install` and `_remove_attempts` exist.
  - 14: an agent-file `OSError` becomes `LAUNCH_FAILED` (grok/browser.py:110-114).
  - 15: the reaper uses `env_remove=(NATIVE_USER_PROFILE_VARIABLE,)` (reaper.py:52).
  - 16: `{} if tool_keys is None else tool_keys` in all three `_call`s.
  - 2: the Grok budget uses an estimated path, with `BROWSER_CALL_FOLDER_ESTIMATE`.
- HELD: D-11 evidence per harness.
  - Grok: mounted servers that are neither listed nor called are missing.
  - opencode: no calls means every server is missing.
  - Muse: `missing` is `()`, and only a `MUSE_RUN_FAILED` carrying "Required MCP server" becomes `TOOLS_UNAVAILABLE`.
- HELD: CI on d00bd8ba is green. Run 39075450892 (Source 3.11, 3.12, Package) and run 39075452414 (Static policy) both succeeded.
- DID NOT HOLD: deviation 4 and the comment at browser.py:355-358 ("within the cleanup budget that also bounds the reap"). See R-C2.
- DID NOT HOLD: NG-2's "PR … #1055 [is] open". See R-C1.
- Considered and rejected:
  - Grok counts a failed `use_tool` call as evidence. This matches the spec's "listed or called".
  - A Muse required-key tool with no key gets `configuration.invalid_argument` before `mount_unsupported`. This follows the §5 order, where `select` runs before `check`.
  - The reaper mixes the literal `0` with `NATIVE_REAP_NONE_COUNT`. That belongs to the conventions lens.

COMMANDS RUN:
- `git diff --stat origin/main...d00bd8ba`; `git diff --name-status origin/main...d00bd8ba`; `git log --oneline origin/main..d00bd8ba`; `git show d00bd8ba:docs/spec/harness-browser-tools/spec.md`
- `git log --oneline origin/main | grep -E "#1044|#1055"`; `git merge-base --is-ancestor 6f5a7310 d00bd8ba` (true)
- `PYTHONPATH=$(pwd) py -3.11 -c "<inspect.signature of the 9 browser + 9 plain functions, native __all__>"`. A first try with `-I` loaded the main clone and failed with `AttributeError`; the rerun without `-I` passed.
- Tests, one file at a time with `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/<file>.py`:

  | File | Result |
  |---|---|
  | `test_harness_threads_browser_acceptance.py` | 1 passed |
  | `test_harness_threads_browser_contract.py` | 22 passed |
  | `test_harness_threads_browser_registry.py` | 40 passed |
  | `test_harness_threads_browser_fakes.py` | 10 passed |
  | `test_harness_threads_browser_mounts.py` | 49 passed in 50.06s |
  | `test_harness_threads_browser_runtime.py` | 26 passed in 15.52s |
  | `test_harness_threads_browser_lifecycle.py` (with `-rs`) | 28 passed, 1 skipped in 40.91s (the POSIX reaper test skips on win32) |
- `gh run view 39075450892`: success. `gh run view 39075452414`: success.
- Read-only greps over vidbyte/harnesses/native/{hostkit,grok,opencode,muse}, vidbyte/lib/{constants,dataclasses,registries,process}, the README files, REPO_MAP.md and skills/failure/vocabulary.md.
- Not run, by instruction: the lint loop (owned by the conventions lens), the real §4 snippet (it makes a paid call), the full suite and `scripts/run_ci.py`.
