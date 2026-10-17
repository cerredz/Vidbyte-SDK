# S6 · PR author report: browser-agent

Stage: S6 PR author · Date: 2026-10-17 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent` · Branch: `feat/browser-agent` · Start HEAD `010e3eee` · Final HEAD `03abae95` · PR: https://github.com/cerredz/Vidbyte-SDK/pull/1182 (draft)

Produced: `docs/spec/browser-agent/pr-body.md` (title on line 1); spec r5 frontmatter `status: pr-open` (`updated: 2026-10-17` and `pr:` kept), §5 flow chart redrawn from the code, §17 row `r5 | 2026-10-17 | S6 PR | finalized for review` and a "PR finalization (S6)" note. One commit, `03abae95 docs(spec): finalize browser-agent for PR`, pushed. No file outside `docs/spec/browser-agent/` changed. This report is not committed (it records the checks on the commit above).

## 1. What the code does (written before opening the spec)

The full pre-spec note is in the scratchpad (`.../scratchpad/browser-agent/s6/understanding-before-spec.md`); its substance:

- **Construction.** `BrowserServerSettings` takes a registered preset (stored as the registered `McpPresetDefinition`) or a `command` argv, a read-only `env`, and a `timeout` of at most 600 s. It refuses a blank env value (naming the variable and, for a preset, the preset, never the value) and runs the preset's own `McpPresetRegistry.build_config` against `env` only, never `os.environ`. `command` and `env` are `repr=False`. `BrowserAgentSettings` checks the text fields, converts the provider, proves `model_name`, `episode_model_name`, and `recheck_model_name` against it, requires an action server, refuses a preset or command repeated across roles, caps `done_when` (20 one-line items of 500 chars), matches the model keys, refuses extra tools named `run_episode`/`patch_goal`, requires every cap to be an int of at least 1, and refuses an async `on_event`.
- **Facade.** `BrowserAgent.__init__` type-checks the settings, builds the role map, the response writer, and the event emitter, calls `BaseAgent.__init__` with `runtime=AgentRuntimeType.BROWSER` and the developer prompt plus the orchestrator rules, then queues each server as `browser-<role>-<n>` through `with_preset_mcp_server` / `with_mcp_server` with only its own env. `_runtime_extension_kwargs` hands settings, role map, `self.mcp_servers()`, response, and events to each run-local runtime. Sessions are refused.
- **Run.** `BrowserAgentRuntime.arun`, inside the agent's usage ledger scope: refuses a reserved name on any live tool, splits live tools by role (by `handle.name`), refuses a run with no ACTION tools, starts the record and events (`run_started`), derives `done_when` with one structured call when empty (fail closed), builds the goal card (`goal_set`), swaps the ACTION tools for `run_episode` and `patch_goal`, clears history, drops a per-run `tools` option, pins the card at `TOP_OF_CONTEXT` on a copied context manager, and runs `super().arun`. Hooks: `_after_tool_iteration` rebuilds the stored history past 60,000 tokens (shared `ContextCompactionEngine`, `TRIM_WITH_PROVIDER_BOUNDARIES`, `max_messages=1`; counted only when something was removed), runs the periodic recheck when due, and re-pins the card; `_continue_finish_attempt` rechecks every finish in a fresh agent, accepts on `done` or an unavailable recheck, otherwise rebuilds, re-pins, and appends the `continue_prompt` gap message; `_budget_stop` ends the run with `goal_stalled` (the card as output) once `max_stalls` stalls accrue, else defers to the loop's budgets. After the loop it settles usage first (on `UsageAccountingError`: `run_stopped` naming the error, re-raise), then emits `run_finished` (final_response / is_done) or `run_stopped`, and `BrowserResponse.finished` writes output, stop reason, usage, and sink errors and returns the result with the settled rollup.
- **Episode.** `run_episode` validates `task`/`done_when` (error result, nothing recorded, when blank), numbers the episode, builds a fresh plain `BaseAgent` worker holding only the ACTION tool objects (same bridged objects, so one server process and one browser), with `max_tool_calls=max_actions`, `max_iterations=max_actions+4`, `max_calls_per_tool` for every tool whose name contains "screenshot", the per-tool sliding window (`keep_observations`, older cut to 400 chars) and a 32,000-token provider-boundary trim, and `output_schema=BrowserEpisodePayload`. A valid card is cut to its caps; a cap stop or schema miss (`OutputSchemaViolationError`) gives a stuck card from `worker.last_reply` (exact action count, newest successful observation's first 400 chars as evidence); any other `VidbyteSdkError`/`OSError`/`ValueError` gives a stuck card with `actions=None`; cancellation propagates. The recipe is the successful calls of a `done` card. The orchestrator gets only the result-card text capped at 800 tokens.
- **Goal card.** Frozen record; `patch_goal` changes plan (replace), blockers (replace), or progress (append one item per non-blank line) and refuses anything else, with `progress_full` when the 96,000-char total is passed and `patch_refused` otherwise. Stall rule: `stalled`, or `continue` with progress unchanged since the previous recheck, adds one; anything else resets; an unavailable recheck neither counts nor resets but restarts the cadence. Rechecks are fresh `BaseAgent`s with no presets, two iterations, and only the goal, criteria, and progress; a `VidbyteSdkError` or off-schema answer is "unavailable" (fail open).
- **Events / usage / response.** Events numbered from 1, details one line of at most 500 chars, sink `Exception` recorded by type name, `BaseException` propagates. Usage fails closed through `JevUsageAccount.failures`. The response record is replaced at each run start.

## 2. The §4 snippet, run through the fakes

Script: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d4409101-4281-402b-989c-fb71871586cd/scratchpad/browser-agent/s6/run_snippet.py` (the AC-1 script; reuses `browser_agent_fixtures.py`). Run from the worktree root with `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY -u FIRECRAWL_API_KEY -u VIDBYTE_API_KEY PYTHONPATH="$(pwd -W);$(pwd -W)/tests/features/browser_agent" python run_snippet.py` → exit 0. The snippet runs as written; no deviation for AC-1.

```text
# vidbyte imported from: C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py
# ---- snippet output ----
run_started 
goal_set 1
episode_started 
episode_finished done
recipe_recorded 1
goal_patched progress
goal_rechecked done
run_finished final_response
FINAL-ANSWER: Seedcamp accepts applications until 30 November at https://seedcamp.com/apply.
final_response 1
Seedcamp - https://seedcamp.com/apply - closes 30 November
# ---- what the fakes saw ----
# model calls by agent: ['vc-scout', 'vc-scout-episode-1', 'vc-scout-episode-1', 'vc-scout', 'vc-scout', 'vc-scout-recheck']
# ACTION server calls: [('browser_navigate', {'url': 'https://seedcamp.com/apply'})]
# server processes started: 2, all closed: True
# key reached SEARCH server only: True
# episode 1: outcome=done actions=1 recipe_steps=1 stop_reason=final_response
# rechecks: [('done', True)]
# usage rollup: model_call_count=6 input_tokens=18 output_tokens=12 cost_complete=True; equals get_usage(): True
# settings repr hides the key: True
```

## 3. Deviations found (spec r5 vs code at `57a22077`)

1. §12.3 row 16 — terminal event then `response.finished(result, self.usage.settle(), …)`; code settles first and, on `UsageAccountingError`, emits `run_stopped` (detail `UsageAccountingError`) and re-raises (`vidbyte/agents/browser/runtime.py:133-137`). R-4 repair. (R-C2)
2. §17 "Event details" — `run_finished`/`run_stopped` carry the stop reason; on the path above the detail is the error type name. (R-C2)
3. §8.5 — `command: tuple[str, ...] | None = None`; code `field(default=None, repr=False)` (`vidbyte/agents/browser/settings.py:69`). R-11 repair. (R-C2)
4. INV-20 — sink error type names reach `agent.response.event_errors`; on the `UsageAccountingError` path `BrowserResponse.finished` never runs, so the list stays `[]` (`runtime.py:135-137`, `response.py:65`). (R-C3)
5. §5 — the r1 flow chart omitted the settings checks, run-start refusals, periodic recheck, stall stop, and the settle-before-terminal-event step. Fixed in this commit (§5 redrawn, noted in §17); not a code deviation.
6. INV-12 "exactly once" — not true if `_worker(index)` or the prompt lookup raises, because both sit outside the `try` after the counter and `episode_started` advanced (`vidbyte/agents/browser/episode.py:102-110`). Triaged as R-18 follow-up; listed in the PR under Follow-ups, as the briefing directs.
7. The S3 deviations already recorded in spec §17 (two counting constants, the extra `validate_provider` call for C012, `_require_distinct_servers`, text normalization, event details, rebuild measure with `default=str`, docs placement) are referenced in one line in the PR body, not repeated.

No other place where §4, §5, §8, or §12 differs from the code: names, paths, the module count (10), the 19 leaves, and every `§8.5` signature match. All 37 AC proof test names in spec §6.2 exist on the branch (checked against `pytest --collect-only`, 109 items).

## 4. PR state after the update

`gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1182 --json title,isDraft,baseRefName,headRefOid,url`:

```text
{"baseRefName":"main","headRefOid":"03abae95b5a8d70b5f4cd38e3fed2df64fe53fbd","isDraft":true,"title":"feat(agents): add BrowserAgent for long browser tasks over the developer's own MCP servers","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1182"}
```

Mergeable state before the push: `MERGEABLE` against `main` (`6f5a7310`).

## 5. Checks on the final SHA `03abae95`

Dispatched after the final push: `gh workflow run CI --ref feat/browser-agent` → run 39077935821; `gh workflow run "Static policy" --ref feat/browser-agent` → run 39077937123. `gh run list` showed both with `headSha` `03abae95b5a8d70b5f4cd38e3fed2df64fe53fbd` before watching. `gh run watch … --exit-status` → `Static exit=0`, `CI exit=0`.

`gh api repos/cerredz/Vidbyte-SDK/commits/03abae95b5a8d70b5f4cd38e3fed2df64fe53fbd/check-runs --jq '.check_runs[] | "\(.name) \(.status) \(.conclusion)"'`:

```text
Package completed success
Static policy completed success
Source / Python 3.12 completed success
Source / Python 3.11 completed success
```

4/4 green on `03abae95`. `gh pr view … --json mergeable,statusCheckRollup` → `MERGEABLE`, rollup length 0 (expected for dispatched runs).

**PR body vs the committed file.** After the checks finished, I edited the PR description once more with `gh pr edit --body-file`. The only change from `pr-body.md` line 2 onward is the "Remote checks" cell: the committed file says the head is re-dispatched after the push, and the PR page names `03abae95` with its two run IDs and the four `completed success` results. A new commit would have moved the head again, which is why the file was left as it is. The live body was read back with `gh pr view --json body` and diffed against the edited file: they are identical apart from one trailing newline. The body ends with the Claude Code line, holds no `[WIP]`, and the PR is still a draft.

## 6. Verification of this stage's own claims

- Both mermaid blocks in `pr-body.md` and in spec §5 parse with mermaid 10.9.1's own parser under jsdom (`check_mermaid.mjs`, scratchpad); a deliberately broken control block fails with a parse error, so the check can fail.
- Re-ran at `010e3eee`: browser pack `109 passed in 1.47s`; `python lint/run.py` → `A002 intent-comments 562 703 IMPROVED` … `SDK-LINT: PASS`; `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 8183aa6f65fa79eb0488c6fea9eb30933239d9fb (vidbyte-sdk 0.3.0, 648 exports).`
- The source, package, and semgrep gate lines in the PR body are the orchestrator's re-run at `7c6d0e65` and verify-log iteration 1; I did not re-run them, because every commit after `57a22077` touches only `docs/spec/browser-agent/`, and the remote CI on `03abae95` runs the full source and package stages again.
- Every Major in the review table was checked against `review.md`'s Status column; the Minor count (11 fixed: R-6 to R-14, R-19, R-20; 6 open: R-15 to R-18, R-21, R-22) was counted from the same column.

## 7. Candidate field-guide lessons (not written to the field guide)

Shape follows `field-guide/vidbyte-sdk/comment-format.md` (rule heading; When / Do / Because / Check / Evidence). All are candidates only: no human review has accepted them yet.

### L-1 (runtime-boundaries) A fail-closed usage settle runs before the run's terminal event
- **When:** An agent runtime both emits a terminal success event to a developer sink (`run_finished`) and fails closed on usage (`JevUsageAccount.failures` → `UsageAccountingError`).
- **Do:** Call `settle()` first. On `UsageAccountingError` emit the stop event naming the error type and re-raise; only after a clean settle choose `run_finished` or `run_stopped`.
- **Because:** Emitting first told the sink the run succeeded while the caller received an exception, and `agent.response.stop_reason` and `.usage` stayed None.
- **Check:** A test with an unpriced model and a recording sink asserts the last event is the stop event and the success event never appears.
- **Evidence:** PR #1182, R-4; fix `3f909eb3`, test `6dae8247`.

### L-2 (model-facing / safety docs) A rule that lives only in prompts is documented as prompt-only, with the code gate named
- **When:** A README or header states a safety behavior (no submit, no payment) that only prompt leaves enforce, because MCP browser tools are generic.
- **Do:** Say plainly that the rule is prompt-level only and that `permission_policy` (allow-all by default) is the code gate the developer controls.
- **Because:** "Nothing acts on `ready_to_submit`" read as a guarantee; an injected page instruction can still lead a worker to click submit.
- **Check:** `grep -n "permission_policy" <package>/README.md` finds the caveat next to the no-submit claim.
- **Evidence:** PR #1182, R-3; fix `7a50daea`.

### L-3 (strict-config-dataclasses) An MCP server's `command` is hidden from `repr` like its `env`
- **When:** A settings record holds an MCP server `command` argv next to its `env`.
- **Do:** Declare `command` with `field(default=None, repr=False)`; keep equality comparing it, and name only the program (argv[0]) in error messages.
- **Because:** Later argv entries can carry a key (`--api-key …`), so a logged settings repr would leak it even though `env` is hidden.
- **Check:** A test builds a server with `command=("srv", "--api-key", SECRET)` and asserts `SECRET not in repr(settings)`.
- **Evidence:** PR #1182, R-11; fix `57a22077` (the test is still missing: R-C1).

### L-4 (strict-config-dataclasses / tests) A settled default is pinned by behavior with default settings, not by comparing the field to its constant
- **When:** A spec settles a default value (for example `keep_observations=2`) that lives in a `BROWSER_*`-style constant.
- **Do:** Add one behavior test that builds the agent with default settings and observes the default's effect (two observations whole, the third older one cut).
- **Because:** `field == CONSTANT` passes when both drift together; two mutants (wiring forced to 1, constant and default set to 1) both left the pack green.
- **Check:** Mutate the constant to the old value; at least one test fails.
- **Evidence:** PR #1182, R-5; test `4f73cf31`.

### L-5 (tests / MCP) Assert on `repr(agent.tools)` only while the MCP servers are attached
- **When:** A test checks that no key reaches the agent's tool catalog.
- **Do:** Read every tool's `repr` and spec after `arun` and before `close_mcp_servers()`, and first assert the bridged tools are present.
- **Because:** `Tools` has no `__repr__`, and a sync `run()` releases the bridged tools, so the post-run assertion cannot fail.
- **Check:** The test fails when a key is planted in a bridged tool's spec metadata.
- **Evidence:** PR #1182, R-20; test `169f548c`.

### L-6 (blocking-lint-invariants / A002) Any function that touches MCP handles needs an `@intent` within 20 lines of its `def`
- **When:** A new function's body reads MCP server handles or configs (for example `self.mcp_servers()`), or implements a stop rule.
- **Do:** Put `# @intent <name>` on the first line of its comment block, saying why the handles go where they go.
- **Because:** A002 classifies functions by body tokens (`mcp` counts as an external boundary); `_runtime_extension_kwargs` raised A002 from 562 to 563 although the ratcheted gate still passed.
- **Check:** `python lint/run.py --rule A002` reports no increase over the merge base.
- **Evidence:** PR #1182, R-2; fix `e3aacaa7`.

### L-7 (comment-format, reinforcement) Rewrapping applies to an existing comment block you edit in a shared file
- **When:** A change adds a clause to an existing multi-line comment in shared SDK code (here `_LINEAR_LOOP_RUNTIMES` in `vidbyte/agents/base.py`).
- **Do:** Rewrap only that block to 72 columns with the same words; leave the rest of the file alone.
- **Because:** The existing entry says "Writing or editing"; inherited width is not an exemption, and the verifier rated the miss Major.
- **Check:** `awk 'NR>=<start> && NR<=<end> {print length($0)}' <file>` prints values ≤ 72.
- **Evidence:** PR #1182, R-1; fix `b47b90ac`. Evidence for the existing `comment-format.md` entry, not a new entry.

### L-8 (agentic-engineering headers) Re-read a module's A001 header after splitting out a helper
- **When:** A module gains a private helper or a hand-written check after its header was written.
- **Do:** Update FUNCTION INVENTORY and ARCHITECTURE NOTE in the same commit, naming the helper and every hand check.
- **Because:** Two headers said "no private helpers" and "only the progress total is checked by hand" while a helper and a second hand check existed.
- **Check:** Every `def _…` in the module appears in FUNCTION INVENTORY.
- **Evidence:** PR #1182, R-9; fix `12b1e6c7`.

Also observed, not proposed: R-10 (`match` on a closed enum instead of an if/elif with a bare `else`) is already house style; R-15 shows `OutputText.single_line` is documented as connector-only, so inlining the collapse idiom is the repo grain today; R-8 is a useful fact for the runtime-boundaries entry: a tool with `metadata={"internal": True}` is never counted by `loop.max_tool_calls`.

## 8. Anything that looked wrong while reading (no source changed)

- `vidbyte/agents/browser/episode.py:102-110` — R-18 (known): the counter and `episode_started` advance before `_worker()` and the prompt lookup, both outside the `try`.
- `vidbyte/agents/browser/runtime.py:135-137` with `vidbyte/agents/browser/response.py:65` — R-C3 (known): `event_errors` not copied on the raising path.
- `vidbyte/agents/browser/runtime.py:104-108` — a run whose `done_when` derivation fails has already emitted `run_started` and then emits nothing more (no `run_stopped`), so a sink sees an unterminated run. This matches EC-19 and INV-20's "when the loop returns", so it is not a deviation, but it is worth one line in the README notes in a later PR.
- `vidbyte/agents/browser/runtime.py:118-119` — a caller's per-run `tools=` option is dropped silently (`run_options.pop("tools", None)`). Spec §8.2 records this as the Infinite pattern; the README does not mention it.
- Test gap: no test asserts `BrowserEpisodeResult.tokens` (`grep -n "\.tokens\b\|total_tokens" tests/features/browser_agent/*.py` finds nothing). The fakes report usage without `total_tokens`, so the rollup's `total_tokens` is None in the fakes (observed in the first snippet run) and every card's `tokens` is None in every test; spec G-6 names per-episode tokens. Real OpenAI usage carries `total_tokens`, and the Anthropic and Gemini parsers derive it, so this is a test gap, not a code bug.
- Test gap (known): R-C1 — no regression test for R-14 (preset named in a blank-key error) or R-11 (`command` hidden from `repr`).
