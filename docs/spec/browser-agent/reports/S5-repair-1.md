# S5 repair, iteration 1 of 8: BrowserAgent

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent`, branch `feat/browser-agent`, start HEAD `929dcbe6`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1182. Every command ran from the worktree root with every model key unset (`env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY … -u OPENAI_API_KEY`).

## Gate matrix

Local gates ran at the last code commit `57a22077`. The docs-only commits after it change nothing that a gate reads except `docs/`.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| Browser pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider` | PASS | import check prints `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`; `........ [ 66%]` / `..... [100%]` / `109 passed in 1.37s` |
| Lint | `python lint/run.py` | PASS | `A002 intent-comments 562 703 IMPROVED` … `S063 IMPROVED 4 -> 3.` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| Semgrep | `python <scratchpad>/run_semgrep.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Findings: 0 (0 blocking)` / `Rules run: 1` / `Targets scanned: 996` / `Ran 1 rule on 996 files: 0 findings.` |
| Public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 8183aa6f65fa79eb0488c6fea9eb30933239d9fb (vidbyte-sdk 0.3.0, 648 exports).` |
| Source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS apart from the 2 known local-only failures | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `2 failed, 6349 passed, 16 skipped in 101.02s (0:01:41)` |
| Package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Remote | dispatched CI + Static policy | see "Remote checks" | |

Lint detail: every rule is at or below its baseline. A002 is back to 562, the merge-base count. `--all --format json` shows no finding in any browser file this iteration touched. The `base.py` findings (12 A002, S008 on `__init__`, S009 mypy lines) were there before this iteration; only their line numbers moved, by +2, after the R-1 rewrap. S009 (mypy) is still at 350.

The two source-stage failures are the known local-only pair from the briefing and code-map §1.4. (1) The FailureCode surface test gives `assert 148 == 120`; the orchestrator recorded that it also fails at base `08f67e7f`. (2) The root-`__all__` test compares against the merge base's `vidbyte/__init__.py` (`At index 30 diff: 'BrowserAgent' != 'JevAgent'`), which is the PR's intended new export. `optional_merge_base()` returns None on CI, so the test skips there. This iteration changed no file that either test reads (`git diff --name-only 929dcbe6..HEAD` lists no `vidbyte/__init__.py` and no `vidbyte/lib/errors` file). Passed count: 6346 at S3, plus 3 new pack tests from S2 = 6349.

Test-tree rule: `git diff c56f34bc..HEAD -- tests/` is empty (0 lines).

## Per finding

| ID | Commit | What changed | Proof |
|---|---|---|---|
| R-4 | `3f909eb3` | `runtime.py` arun now runs `self.usage.settle()` inside `try` before choosing the terminal event. On `UsageAccountingError` it emits `RUN_STOPPED` with `type(exc).__name__`, then re-raises. Otherwise it emits as before and returns `self.response.finished(result, usage, …)`. `UsageAccountingError` is imported from `vidbyte.lib.errors` (exported there, `__init__.py:69,118`). The step is narrated, and the header edge case now reads: "A run whose usage cannot be priced emits run_stopped, naming UsageAccountingError, and then raises it; a cancelled run, or one whose loop raises, emits no run_finished or run_stopped." | Reproduced red first: `AssertionError … + run_finished` / `1 failed, 108 passed in 1.57s`. After the fix: `109 passed`. S008 and S024 pass; the nesting is `with` → `try`, depth 2. INV-20 holds (exactly one terminal event, and it is last); INV-21 holds (it raises, never returns). |
| R-2 | `e3aacaa7` | Added `# @intent live-servers-reach-only-the-runtime` on `_runtime_extension_kwargs` (`agent.py`), with one sentence of why: the handles are read per run after connect, and their configs hold each server's env. Added `# @intent a-stalled-run-stops-before-its-next-model-call` on `_budget_stop` (`runtime.py`), with its why: a stalled run would only spend more calls. | `python lint/run.py --rule A002` → `A002 IMPROVED 703 -> 562.` / `SDK-LINT: PASS`. No comment line wider than 72 (`awk 'length($0) > 72' … \| grep -E '^\s*#'` prints nothing). |
| R-1 | `b47b90ac` | Rewrapped `base.py:80-82` (99/95/74 columns) as five lines of 54/56/52/53/55 columns, with the same words. A brute-force search over every four-line split found none that fits in 72 columns. No other line of `base.py` changed. | `awk 'NR>=80 && NR<=84 {print NR": "length($0)}'` → `54 56 52 53 55`; `git diff --stat` → `5 insertions(+), 3 deletions(-)`. |
| R-3 | `7a50daea` | README line 40 now reads "…and nothing in code acts on it. The rule itself is in the prompts only; see Notes for agents." New first Notes bullet: the no-submit rule lives only in the worker and orchestrator prompts; code cannot tell a submit from any other click, so an injected page instruction can still lead a worker to submit, send, or pay; `settings.permission_policy` (allow-all by default) applies to every worker and orchestrator tool call and is the code gate the developer controls. `settings.py:8` was softened to the same effect. | Verified the claim in code: `permission_policy=settings.permission_policy` at `agent.py:64` (orchestrator) and `episode.py:154` (every worker). A009, S020, and A001 pass. README is 10,724 characters. |
| R-14 | `6a0bdb94` | `settings.py` env loop: a `ConfigurationError` from `require_text` is re-raised as `BrowserServerSettings.env[<NAME>] for the '<preset>' preset must not be blank; put its value in env, since os.environ is never read.` A command server gets the same message without the preset clause, and `details` is unchanged (`{"field": "BrowserServerSettings.env[<NAME>]"}`). No value is quoted. The intent comment was updated to match. This follows spec r5 §9.2 step 4, and the blank check still runs before `build_config` (step 6). | Probe output: with a preset, `"BrowserServerSettings.env[FIRECRAWL_API_KEY] for the 'firecrawl' preset must not be blank; …"`; with a command, `'BrowserServerSettings.env[FETCH_REGION] must not be blank; …'`; the real `fc-real-123` key in the same env does not appear. Pack: 109 passed. S024, S008, C001, C008, and A002 pass. |
| R-6 | `3db1f624` | `REPO_MAP.md`: the recheck now "sees only the goal, the done criteria, and the progress". | Matches INV-15 and the `goal.py` recheck. |
| R-7 | `179c7c73` | README, under the snippet: a preset runs its registered command (`PlaywrightMCP` runs `python -m mcp_server_playwright`, `vidbyte/lib/config/mcp_presets.py:93`); when that command is not installed, pass `BrowserServerSettings(command=("npx", "@playwright/mcp@latest"))`. | Spec A-3. A009 and S020 pass. |
| R-8 | `6b6e1ef8` | README Limits, orchestrator bullet: `run_episode` is internal, so `loop.max_tool_calls` never counts it; episodes are bounded by `loop.max_iterations` and by how many the model starts in one turn; `patch_goal` is an ordinary tool and does count. No cap was added (scope rule). | Verified: `episode.py` spec `metadata={"internal": True}`; `runtime.py:2073` counts only `_non_internal_tool_contexts`; the `patch_goal` spec has no `internal` metadata. |
| R-9 | `12b1e6c7` | `settings.py` FUNCTION INVENTORY now names `_require_distinct_servers` as the one private helper. `lib/dataclasses/browser.py` ARCHITECTURE NOTE now says the done_when minimum and the progress total are the two hand checks, "because the validators have no minimum-count or total-size option". | `require_text_items` has `max_items` but no minimum (`validation.py:65`). A001 passes. |
| R-10 | `3094ba92` | `goal.py` patch: the if/elif/else ladder became `match chosen:` with one `case` per `BrowserGoalSection` member and no `case _`, as `vidbyte/agents/infinite/journal.py:141` does. `to_enum` returns `BrowserGoalSection`, so the match is exhaustive. No behavior change. | Pack 109 passed; ruff `All checks passed!`; S024, S008, and A002 pass; S009 unchanged at 350. |
| R-11 | `57a22077` | `BrowserServerSettings.command` is now `field(default=None, repr=False)`. | `repr(BrowserServerSettings(command=('fetch-server','--api-key','sk-secret-1')))` → `BrowserServerSettings(preset=None, timeout=30.0)`. Positional `BrowserServerSettings(None, ('x',))` still works. Pack: 109 passed. |

Independent check of R-4: I reran the S4 reviewer's probe, `scratchpad/browser-agent/probes/probe_unpriced_events.py` (fakes only), against the fixed code. Case 1 (unpriced orchestrator model) gives `case1: raised UsageAccountingError` and `['run_started', 'goal_set', 'goal_rechecked', 'run_stopped']`, with last event `detail='UsageAccountingError'`. Case 2 (unpriced worker model) gives `case2: raised UsageAccountingError` and `[… 'episode_finished', 'goal_rechecked', 'run_stopped']`. Before the fix, case 1 ended in `run_finished`. In both cases `agent.response.stop_reason` stays None, as INV-21 intends: the run raises and never returns. R-22, the late reporting of an unpriced worker, stays a follow-up.

"Gets right" list re-checked: the rebuild (`_rebuild_history`), the role split (`tools.py`), the stall rule (`goal.py` `rechecked`/`stalled`), the stuck-card paths, and `BrowserAgentRuntime.__init__` are untouched. Keys are still `repr=False`, and `command` has now joined them. No prompt leaf changed, and the caps are still constants.

## Test changes proposed

None. No test contradicts the spec, and the tree under `tests/` is unchanged since `c56f34bc`.

## Findings I believe are wrong

None. Every finding handed to this iteration reproduced and was fixed as the review described. One refinement: R-14's suggested fix ("name `self.preset.name` when the variable is in `required_env`") was superseded by spec r5 §9.2 step 4, which names the preset for any env value of a preset server. I followed the spec.

## Not done, by instruction

R-15, R-16, R-17, R-18, R-21, and R-22 are follow-ups, and R-23 is refuted. All were left alone. I skipped R-3's optional mirror sentence in `vidbyte/agents/README.md` § Browser Agent: that section claims no submit guarantee, so the smallest change is the folder README.

## Remote checks

Dispatched on `54d23757` (every code commit of this iteration): CI run 39069591066 and Static policy run 39069592426, `headSha` confirmed. `gh run watch --exit-status` gave `CI exit=0` and `Static exit=0`. `gh api …/commits/54d23757f814216ccd6edbaadc9c1ca399f1668d/check-runs`:

```
Package	completed	success
Static policy	completed	success
Source / Python 3.11	completed	success
Source / Python 3.12	completed	success
```

The commit that adds this report is docs-only. I re-dispatched both workflows on that head; the run IDs and results are in the STATUS block.

## What remains open

Nothing handed to this iteration. If a later iteration is needed: the two local-only `harness_threads` failures are not this PR's to fix (FailureCode count fails at base `08f67e7f`; the root-`__all__` test skips on CI). Reproduce them with `PYTHONPATH=$(pwd) python -m pytest tests/features/harness_threads/test_harness_threads_surface.py -q -p no:cacheprovider`.
