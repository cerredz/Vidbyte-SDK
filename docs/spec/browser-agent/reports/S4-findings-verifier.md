# S4 findings verifier — BrowserAgent

Stage: S4 (second half) · Diff: `origin/main...3f9e63c9` (merge base `08f67e7f`; `git diff --stat 3f9e63c9 HEAD` touches only `docs/spec/browser-agent/`) · Output: `docs/spec/browser-agent/review.md` · No commits.

Verdict: **MERGEABLE AFTER FIXES**. 0 Blockers, 5 confirmed Majors, 17 Minors (2 of them downgraded from Major), 1 refuted.

Environment: every provider key unset (`env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY -u VIDBYTE_API_KEY -u XAI_API_KEY -u GROK_API_KEY -u DEEPSEEK_API_KEY -u OPENAI_API_KEY`), with `PYTHONPATH=$(pwd)` from the worktree root.
- `python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`.
- No paid call was made, no real MCP server was started, and nothing was installed.
- My probes are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d4409101-4281-402b-989c-fb71871586cd/scratchpad/browser-agent/probes-verifier/`.
- `git status --short` in the worktree printed nothing before I wrote the two output files.

## 1. Merge map (original IDs → merged IDs)

There were 22 raw findings: conformance R-C1…R-C6, conventions R-V1…R-V8, engineering R-E1…R-E8. No two shared a root cause, so nothing merged. R-V3 was split in two, because its source part and its test-pack part calibrate differently.

| Original | Proposed | Merged ID | Disposition |
|---|---|---|---|
| R-V3 (base.py part) | Major | R-1 | CONFIRMED Major (source) |
| R-V2 | Major | R-2 | CONFIRMED Major (source) |
| R-C1 | Major | R-3 | CONFIRMED Major (docs) |
| R-E1 | Major | R-4 | CONFIRMED Major (source, plus an optional S2 assertion) |
| R-E2 | Major | R-5 | CONFIRMED Major (tests, S2) |
| R-C6 | Minor | R-6 | Minor, trivial, docs |
| R-C5 | Minor | R-7 | Minor, trivial, docs |
| R-E4 | Minor | R-8 | Minor, trivial, docs (one claim corrected: `patch_goal` does count) |
| R-V4 | Minor | R-9 | Minor, trivial, source |
| R-V7 | Minor | R-10 | Minor, trivial, source |
| R-E5 | Minor | R-11 | Minor, trivial, source |
| R-C4 | Minor | R-12 | Minor, trivial, spec (S1) |
| R-C3 | Minor | R-13 | Minor, follow-up, spec or source |
| R-C2 | Minor | R-14 | Minor, follow-up, source or spec (the spec conflicts with itself) |
| R-V1 | Major | R-15 | DOWNGRADED → Minor, follow-up |
| R-V3 (test-pack part) | Major | R-16 | DOWNGRADED → Minor, follow-up, tests (S2) |
| R-V8 | Minor | R-17 | Minor, follow-up, source |
| R-E6 | Minor | R-18 | Minor, follow-up, source |
| R-E3 | Minor | R-19 | Minor, follow-up, tests (S2) |
| R-E7 | Minor | R-20 | Minor, follow-up, tests (S2) |
| R-V5 | Minor [scope-adding] | R-21 | follow-up, not this PR |
| R-E8 | Minor [scope-adding] | R-22 | follow-up, not this PR |
| R-V6 | Minor | R-23 | REFUTED (spec row 28 directs the placement) |

Possible overlaps I checked and kept apart:
- **R-C4 and R-E6.** Both concern INV-12's "exactly once", but they are different code paths with different fixes: a spec wording change at episode.py:97-101, and moving construction into the `try` at :102-110.
- **R-C5 and R-E4.** Both are README additions, with different content.

## 2. Verification of each proposed Major

### R-V1 → DOWNGRADED (Minor R-15)

- **Claim holds literally.** `vidbyte/lib/outputs/text.py:42-44` is `return " ".join(text.split())[:limit]`. The four inline sites at `goal.py:118,140,225` and `events.py:45` are character-for-character the same expression. My equivalence probe on 5,000 random strings, including unicode whitespace (`\u00a0`, `\u2028`), printed `equivalent on 5000 cases including unicode whitespace`. `None` input raises `AttributeError` in both forms. All four sites receive `str`: an f-string, the pydantic `gap: str`, `list[str]` items, and `detail: str = ""`.
- **Layering and cost.** `vidbyte.lib` is the bottom layer, so the import is allowed. A probe printed `outputs loaded by vidbyte.agents.browser import: True True`, so the import adds no load cost. Note that `vidbyte/lib/outputs/__init__.py` imports all 20 connectors.
- **Why not Major:**
  1. The helper's own header scopes it to connectors. PURPOSE says "the pure string helpers connectors use to fit a title and body into a destination's fields". COMMON MODIFICATION PATTERNS says "Add a helper here only when two or more connectors need the same text transform". `git grep "single_line("` shows its 12 callers are all in `vidbyte/lib/outputs/`.
  2. The repo's grain inlines this idiom. `git grep '" ".join(.*\.split())'` outside the browser package finds 14 hits, including the spec's named templates: `agents/infinite/workspace.py:271-275`, `agents/jev/brief/writer.py:238`, `agents/jev/done/run_state.py:1974,2185`, `lib/dataclasses/jev.py:113,4185,4412`, and `prompts/system_prompt_presets.py:52`.
  3. The reviewer's own fix includes widening `text.py`'s ROLE IN CODEBASE line. That file is outside §12.3, and spec §14 says "Ask first: any change to a file not in §12.3". Without that edit the header becomes false.
  4. No behavior changes.

  AGENTS.md principle 5 targets jobs with policy choices (timeouts, retries, pagination). A one-expression idiom that the sibling agents inline would not draw a review comment. It stays a follow-up: the right fix is a general one-line helper in `vidbyte/lib/util/text.py` beside `TokenEstimate`, or a documented scope change for `OutputText`.

### R-V2 → CONFIRMED Major (R-2)

- **Gate.** `python lint/run.py` → `A002 intent-comments 563 703 IMPROVED` … `SDK-LINT: PASS` (exit 0). `lint/baseline.json:3` holds `"A002": 703`, so the gate is a ratchet and +1 fails nowhere, locally or in Static policy. `vidbyte-gates.md`: "Exit non-zero when a rule REGRESSED (more findings than lint/baseline.json allows)".
- **The new finding.** `python lint/run.py --rule A002 --all --format json` gives 563 findings. Filtered to the PR's changed `vidbyte/*.py` files (from `git diff --name-only 08f67e7f 3f9e63c9`), 14 remain. 12 are in `base.py` and are pre-existing: the PR changed only module-level comment and frozenset lines there, +3/−3, so line numbers are unchanged. One is `lib/dataclasses/agents.py:338 identity`, pre-existing and shifted by the one-line enum addition. The last is the new one: `{'path': 'vidbyte/agents/browser/agent.py', 'line': 91, 'symbol': '_runtime_extension_kwargs', 'extra': {'categories': 'external boundaries'}}`. That gives 562 at the merge base, which agrees with the conventions reviewer's base-lint run.
- **Why A002 flags it.** `POLICY_TOKENS["mcp"]` matches the `mcp` in `self.mcp_servers()`. The window is `lines[lineno-4 : lineno+20]` (`a002_intent_comments.py:79-80`), and the accepted marker is `#\s*@intent\s+\S+` (:23).
- **`_budget_stop` (runtime.py:179).** It contains no policy token, so A002 does not flag it. Its window covers lines 176-199 and holds no marker; the nearest, `runtime.py:165 # @intent the-orchestrator-rebuilds-instead-of-growing`, belongs to `_rebuild_history`.
- **Spec text (spec.md:1029).** "Every function that handles keys, a refusal, a cap, the stall rule, fail-open or fail-closed behavior, the sink swallow, or catalog narrowing has a `# @intent <name>` comment within 20 lines of its `def`. — source: A002". `_budget_stop` returns the stall stop and defers to the loop's caps, so it is covered. Read literally, "within 20 lines of its def" would accept :165, which sits 14 lines above. But the item's source is A002, whose window starts at `def-3`, and the marker belongs to another function. I read the item by its source.
- **Siblings.** Infinite's and Jev's `_runtime_extension_kwargs` have no marker, but neither is flagged, since no `mcp` token appears. Neither runtime overrides `_budget_stop`.
- **Field guide.** `class-bound-helpers.md` ("…`A002 intent-comments` passes, since a new boundary function needs its own `@intent` block") supports the agent.py half.
- **Calibration.** The gate passes and no behavior changes. But the finding is a spec §12.4 obligation that the PR missed, plus new lint debt in a brand-new file that §14 ("run `python lint/run.py --rule … A002 …` on the new paths") should have caught. A reviewer walking the §12.4 checklist would flag it. The fix is two comment lines.

### R-V3 → SPLIT: base.py part CONFIRMED Major (R-1); test-pack part DOWNGRADED (Minor R-16)

- **Count.** Running the exact §12.4 check per touched file (`awk 'length($0) > 72' <file> | grep -cE '^\s*#'`):

  | File | Wide lines |
  |---|---|
  | `browser_agent_fixtures.py` | 16 |
  | `test_browser_agent_episode.py` | 11 |
  | `test_browser_agent_settings.py` | 7 |
  | `test_browser_agent_contract.py` | 6 |
  | `test_browser_agent_goal.py` | 5 |
  | `test_browser_agent_observability.py` | 4 |
  | `test_browser_agent_rebuild.py` | 3 |
  | `test_browser_agent_acceptance.py` | 1 |
  | `test_browser_agent_recheck.py` | 0 |

  That is 53 test lines. The diff-based count of added lines over all `*.py` is 55, which is those 53 plus 2 in `base.py`. The reviewer's "57 (55 test + 2)" overcounts by 2. Every new file under `vidbyte/` prints 0, so the S3 claim holds for the package.
- **base.py.** `git diff 08f67e7f 3f9e63c9 -- vidbyte/agents/base.py` shows lines 81-82 rewritten. Widths:
  - branch: 99 / 95 / 74;
  - merge base: 99 / 99 / 43.

  `comment-format.md`'s "When" is "Writing or editing any `#` comment in SDK code that runs past one line", so the edited block is in scope. The literal §12.4 check on the whole of `base.py` would print 136 lines, almost all pre-existing. That conflicts with the lesson's "leave untouched files alone" and with AGENTS.md ("Do not rewrite untouched code just to make it conform"). The obligation is therefore only the edited block, :80-82.
- **Severity of the base.py part.** The rubric puts "contradicts … a field-guide lesson" at Blocker. I hold it at Major because the width was inherited (line 80 is untouched at 99 columns), the edit made line 81 narrower, and nothing behaves differently. The fix is trivial.
- **Scope of the lesson.** "Not a lint rule: 4,325 of 5,965 existing comment lines are wider". I recounted at `f7a02bae`, the lesson's commit:
  - `vidbyte/`: 4,320 wide of 5,968;
  - `tests/`: 1,487 wide of 2,009.

  The lesson's census is the `vidbyte/` package alone. "SDK code" means the package.
- **Precedent in test packs.** Wide comment lines over total comment lines, with each pack's first commit date:

  | Pack | Created | Wide / total |
  |---|---|---|
  | jev_skills_preload | 2026-10-10 | 198 / 213 |
  | coding_agent | 2026-10-10 | 198 / 287 |
  | jev_bulk_work | 2026-10-10 | 44 / 45 |
  | sdk_managed_text | 2026-10-11 | 112 / 119 |
  | sdk_model_catalog | 2026-10-12 | 2 / 78 |
  | agent_output_connectors | 2026-10-14 | 285 / 313 |
  | harness_threads | 2026-10-15 | 0 / 342 |
  | system_prompt_presets | 2026-10-15 | 14 / 14 |
  | sdk_provider_keys | 2026-10-15 | 205 / 215 |
  | jev_read_only | 2026-10-15 | 55 / 60 |
  | infinite_memory_agent | 2026-10-16 | 65 / 88 |
  | browser_agent | 2026-10-17 | 53 / 60 |

  Merged packs do not follow the rule, so the test part would not draw a review comment. It is S2-owned, and it is a follow-up.

### R-C1 → CONFIRMED Major (R-3)

- `vidbyte/agents/browser/README.md:40`: "No auto-submit: a worker reports `ready_to_submit`, and nothing acts on it."
- I grepped `permission|submit|click|inject|irreversible` across `vidbyte/agents/browser/*.py` and `vidbyte/lib/*/browser.py`. The only hits are wiring (`permission_policy=` at agent.py:64 and episode.py:154), the `ToolPermission.SAFE` imports, and header rules: `episode.py:8` "Do not act on ready_to_submit", `settings.py:8` "Do not add a field whose name contains submit; nothing submits on its own", and `lib/enums/browser.py:9` "READY_TO_SUBMIT is … never acted on by code".
- The `## Browser Agent` section of `vidbyte/agents/README.md` has no hit. Neither do the prompts README or REPO_MAP for "submit".
- **What the spec requires.** EC-29 (spec.md:366): "no code gate exists for a generic click. The developer's `permission_policy` applies to every worker call. | an irreversible action may happen. Documented." T-2 (spec.md:830): "Residual: a generic click cannot be recognized as a submit (EC-29), which is documented." The default is `permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy.allow_all)` (settings.py:144). The weighted phrase in request.md §D is "a worker returns 'ready to submit' and never submits, sends, or pays on its own".
- **Root cause.** Spec row 22's Notes-for-agents list (spec.md:1008) names EC-21, EC-22, EC-24, T-3, EC-31, EC-37, INV-30, EC-36 and more, but not EC-29 or T-2. The implementer followed row 22. EC-29 and T-2 still state the requirement, and the PR's own README overstates the guarantee.
- **Not a Blocker.** The code does not break the weighted phrase beyond the design the user accepted (D-16: prompt rules plus `permission_policy`). The gap is that the residual is undocumented.
- Fix lands in docs. README size is 9,798 characters, well under A009's 40,000.

### R-E1 → CONFIRMED Major (R-4)

- **Code.** runtime.py:132-134 computes `stop_reason`, then `self.events.emit(RUN_FINISHED if stop_reason in _FINISHED else RUN_STOPPED, stop_reason)`, then `return self.response.finished(result, self.usage.settle(), self.events.errors)`.
- **Reproduction.** I read the probe first; it uses only the pack's `ScriptedModel` and `FakeBrowserServers`. Then I ran `python …/probes/probe_unpriced_events.py`:
  ```
  case1: raised UsageAccountingError
  case1 events: ['run_started', 'goal_set', 'goal_rechecked', 'run_finished']
  case1 last event: BrowserEvent(kind=<BrowserEventKind.RUN_FINISHED: 'run_finished'>, sequence=4, episode=0, detail='final_response')
  case1 response.stop_reason: None usage: None output: ''
  ```
- **Spec reading.**
  - INV-20 says "exactly one of `run_finished` or `run_stopped` last, when the loop returns". It is literally met today: the loop returned, then settle raised.
  - INV-21 says "raises `UsageAccountingError` instead of returning". Also met.
  - The failure: the sink's terminal event is semantically wrong. House style principle 1 names exactly this ("partial failure … and the system reports success").
  - The file's own header contradicts the code. KNOWN EDGE CASES (runtime.py:9): "A cancelled or failed run emits no run_finished or run_stopped."
- **Row 16 order.** §12.3 row 16 lists "emits `run_finished` or `run_stopped` and returns `response.finished(result, self.usage.settle(), events.errors)`". That describes the success path and does not require emitting before settle fails, so the fix stays inside the spec.
- **Reachability.** Any model that passes `validate_provider_model_pair` but has no pricebook row reaches this path. That happened for real in this pipeline (spec A-5, §16 "S2 defect 1": `gpt-4.1`).
- **Fix verified by prototype.** `probes-verifier/fix_r_e1.py` is a verbatim copy of `arun`, with `super()` replaced by `AgentRuntime.arun`, changed only at the end:
  ```python
  try:
      usage = self.usage.settle()
  except UsageAccountingError as exc:
      self.events.emit(BrowserEventKind.RUN_STOPPED, type(exc).__name__)
      raise
  self.events.emit(... as now ..., stop_reason)
  return self.response.finished(result, usage, self.events.errors)
  ```
  - `python -m pytest tests/features/browser_agent -q -p no:cacheprovider -p fix_r_e1 -s` → `FIX R-E1 ACTIVE` / `106 passed in 0.70s`.
  - `python …/probes-verifier/run_probe_with_fix.py …/probes/probe_unpriced_events.py` → `case1: raised UsageAccountingError` / `case1 events: ['run_started', 'goal_set', 'goal_rechecked', 'run_stopped']` / `detail='UsageAccountingError'`.
  - INV-20 holds (one terminal event when the loop returns), and INV-21 holds (still raises).
- **Two choices I made, versus the reviewer.**
  1. The detail is `type(exc).__name__` rather than the reviewer's `usage_unaccounted`. It names a real type, as INV-12's error cards do, and invents no pseudo stop reason.
  2. I rejected the even smaller "swap only" variant (settle first, emit nothing on failure). It matches the header but leaves no terminal event after the loop returned, which breaks INV-20's wording.

  Update the runtime.py:9 sentence to match the new behavior.
- **Test half (S2, optional).** In `test_browser_agent_observability.py:170-176`, add an `EventLog`, pass `on_event=log` to `build_agent`, and assert `log.kinds()[-1] == "run_stopped"` and `"run_finished" not in log.kinds()`. AC-19's test asserts only the raise today.

### R-E2 → CONFIRMED Major (R-5)

- **Mutant 1 (wiring).** `PYTHONPATH="$(pwd);…/probes" python -m pytest tests/features/browser_agent -q -p no:cacheprovider -p mutant_keep_one -s` → `MUTANT ACTIVE: keep_recent forced to 1` / `106 passed in 0.71s`. The control run without it gave `106 passed in 1.38s`.
- **Mutant 2 (constant), my own.** `probes-verifier/mutant_default_one.py` sets `vidbyte.lib.constants.browser.BROWSER_DEFAULT_KEEP_OBSERVATIONS = 1` and rewrites the `BrowserAgentSettings.__init__` default to 1. The sanity check printed `default keep_observations now: 1`. The pack then gave `MUTANT ACTIVE: keep_observations default and constant forced to 1` / `106 passed in 0.67s`.
- **Why both pass.** The only window tests use `build_agent(keep_observations=1)` (test_browser_agent_episode.py:238, :266). `test_defaults_are_the_named_constants` (test_browser_agent_settings.py:259) asserts `settings.keep_observations == limits.BROWSER_DEFAULT_KEEP_OBSERVATIONS`, comparing against the constant rather than the settled value. The shared window's own default is `keep_recent: int = 2` (context_compaction.py:173), so a dropped argument would be caught by AC-9. A hard-coded 1, or a constant changed to 1, is not caught.
- **Settled decision.** Spec Q-4 and Q-6 (spec.md:1194, :1196) set "2 observations kept" and "2 per tool". §16 R-6 (spec.md:1211) records that this exact regression happened once at spec time.
- **Fix verified.** `probes-verifier/test_keep_default_probe.py` uses the AC-9 recipe with `build_agent()` and asserts the first snapshot is cut and `snapshots[1:] == ["[second]" + body, "[third]" + body]`:
  - clean: `1 passed`;
  - with `-p mutant_keep_one`: `test_keep_default_probe.py:40: AssertionError` / `1 failed`;
  - with `-p mutant_default_one`: `test_keep_default_probe.py:40: AssertionError` / `1 failed`.

  A parametrized AC-9 with an explicit `keep_observations=2` would catch only mutant 1.
- This is a test-quality gap, not a code defect. The routing is tests, for the S2 author only.

## 3. Disagreements and corrections I adjudicated

- **R-V1 (conventions Major).** Downgraded. See §2: the helper is connector-scoped, the repo's grain inlines the idiom, and the fix crosses §12.3.
- **R-V3 count.** The reviewer reported 57 lines (55 test + 2 base.py). My exact §12.4 check gives 53 test + 2 base.py = 55. I split the finding and confirmed only the base.py part.
- **R-V6 (conventions Minor).** Refuted. Spec row 28 (spec.md:1014) directs placement "after the infinite row (:83-85)", and §17 "Docs placement" (spec.md:1246) records that the implementer followed it. Moving the block reverses a spec instruction. It needs S1 first.
- **R-E4 wording.** The reviewer says "`run_episode` and `patch_goal` never spend" `max_tool_calls`. Only `run_episode` is internal (`metadata={"internal": True}`, episode.py:90). `patch_goal`'s `ToolSpec` (goal.py:187-192) has no `internal` metadata, so it counts. The R-8 fix sentence names `run_episode` only.
- **R-C2.** Kept Minor. The conformance reviewer reads FR-2 and INV-2 correctly, but spec §9.2 step 4 (spec.md:774) prescribes `RecordFieldValidator.require_text` "as `BrowserServerSettings.env[<NAME>]`" and orders it before `build_config` (step 6). The code follows §9.2 exactly, so the spec conflicts with itself. Either fix is acceptable.
- **R-E7 vs the rubric's "a test that cannot fail".** Kept Minor. Only one clause (`repr(agent.tools)`) is vacuous. The test's other clauses can fail, and the property holds by construction today (`Tools` defines no `__repr__`).
- **R-C1 root cause.** The gap traces to spec row 22's list omitting EC-29. I kept the fix in docs and did not route it to S1: EC-29 and T-2 already state the requirement.
- **R-V5 path.** The reviewer and the briefing name `vidbyte/lib/validation.py`. The real file is `vidbyte/lib/dataclasses/validation.py:65` (`require_text_items`).

## 4. Severity blind-spot check (step 6)

I found no new Blocker-class risk between the lenses that I could anchor to a `path:line`, so I added no `[verifier]` finding. These fix interactions matter for the repair agent:

- **R-4 (R-E1) and §12.3 row 16 / INV-20.** The fix changes the order of settle and emit only on the failure path. Use `run_stopped` with the error type name. Do not drop the terminal event (INV-20).
- **R-18 (R-E6).** Moving `worker = self._worker(index)` inside the `try` leaves `worker` unbound in the `except` paths, which call `self._stuck(..., worker)` and in turn `worker.get_usage()`. Guard with `tokens=None`.
- **R-21 (R-V5, follow-up).** `_PatchGoalTool.execute` maps a refusal to `progress_full` only when `exc.details["field"] == "BrowserGoalCard.progress"` (goal.py:205). A validator option that renames that field silently breaks AC-32.
- **R-15 (R-V1, follow-up).** Any reuse of `OutputText.single_line` requires changing `vidbyte/lib/outputs/text.py`'s header (outside §12.3). Do not do it in this PR without an ask.
- **R-1 (base.py).** Rewrap only :80-82. Rewrapping the other 134 wide comment lines in `base.py` would break AGENTS.md's "Do not rewrite untouched code".

## 5. Commands run (final lines)

- `python lint/run.py` → `A002 intent-comments 563 703 IMPROVED` … `S063 IMPROVED 4 -> 3 …` / `S064 RATCHETED: 4 known finding(s) …` / `SDK-LINT: PASS`; exit 0.
- `python lint/run.py --rule A002 --all --format json` → 563 findings; in PR-changed files the only new one is `vidbyte/agents/browser/agent.py:91 _runtime_extension_kwargs`.
- `python -m pytest tests/features/browser_agent -q -p no:cacheprovider` → `106 passed in 1.38s`.
- `… -p mutant_keep_one -s` → `MUTANT ACTIVE: keep_recent forced to 1` / `106 passed in 0.71s`.
- `… -p mutant_default_one -s` → `MUTANT ACTIVE: keep_observations default and constant forced to 1` / `106 passed in 0.67s`.
- `python -m pytest …/probes-verifier/test_keep_default_probe.py` → clean `1 passed`; with either mutant `test_keep_default_probe.py:40: AssertionError` / `1 failed`.
- `python …/probes/probe_unpriced_events.py` → the case1 lines quoted in §2 R-E1.
- `… -p fix_r_e1 -s` → `FIX R-E1 ACTIVE` / `106 passed in 0.70s`.
- `run_probe_with_fix.py` → `case1 events: ['run_started', 'goal_set', 'goal_rechecked', 'run_stopped']`.
- Comment census at `f7a02bae` → `vidbyte: 4320 wide of 5968`, `tests: 1487 wide of 2009`.
- Per-file `awk 'length($0) > 72' <f> | grep -cE '^\s*#'` → counts in §2 R-V3.
- `git grep '" ".join(.*\.split())' -- vidbyte` (excluding browser) → 14 hits. `git grep "single_line(" -- vidbyte` → 12 callers, all in `vidbyte/lib/outputs/`.

Tooling note for later agents: a direct `python script.py` run with `PYTHONPATH="$(pwd);<dir>"` silently loses the worktree entry under Git Bash and imports the global editable `vidbyte`, which has no `vidbyte.agents.browser`. Use `PYTHONPATH="$(pwd -W);<dir>"`. `python -m pytest` is unaffected, because the cwd is on `sys.path`.
