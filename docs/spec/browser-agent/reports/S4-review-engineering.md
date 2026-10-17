LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the loop, caps, rebuild and stuck-card paths hold under probing. Two Majors remain. First, a run that fails closed on usage tells the event sink `run_finished`. Second, the settled `keep_observations` default of 2 has no test that would catch a regression to 1. Both fixes are small.

WHAT THE IMPLEMENTATION GETS RIGHT (do not "fix" these)
- Per-run state lives on the per-run runtime and on the episode tool it builds:
  - the episode counter, the goal, the usage scope and the events;
  - `BrowserAgentRuntime.__init__` has no side effects, so BaseAgent can build `_runtime()` twice (base.py:1280, :1319) without harm;
  - AC-23 covers the counter reset across runs.
- `_rebuild_history` uses the shared provider-aware engine (runtime.py:164-177). The probe ran the same call on Anthropic, Gemini and OpenAI histories built with `ToolsFormatter`. It keeps whole call/result groups for every provider, including the "bulk call + refused isDone" turn, so nothing is orphaned.
- The stuck-card path is correct in both branches (episode.py:118-124):
  - `OutputSchemaViolationError` is caught first and the card is built from `worker.last_reply`, which is set before the raise (base.py:1009 before :1022). The card has the exact actions and the newest successful observation.
  - Other SDK/OS/value errors give an error card.
  - `CancelledError` propagates.
  - Every error BaseAgent re-raises unwrapped (`UsageAccountingError`, `FailureRaisedError`, `AllModelsFailedError`) is a `VidbyteSdkError` (lib/errors/base.py:134,168,410,506), so none escapes an episode.
- Keys are handled correctly:
  - they live only in `BrowserServerSettings.env` and the model-key fields, all `repr=False` (settings.py:70, :136-137);
  - an `os.environ`-only key or a blank key is refused;
  - the duplicate-server error names only the program (settings.py:243-252).

FINDINGS (ranked, most severe first)

R-E1 [Major] [error handling & observability] vidbyte/agents/browser/runtime.py:133-134 — A run that raises `UsageAccountingError` has already told the sink `run_finished final_response`, and `agent.response` keeps no stop reason or usage
  Evidence: the event is emitted on line 133, and `settle()`, which can raise, runs on line 134:
    `self.events.emit(BrowserEventKind.RUN_FINISHED if stop_reason in _FINISHED else BrowserEventKind.RUN_STOPPED, stop_reason)`
    `return self.response.finished(result, self.usage.settle(), self.events.errors)`
    probe_unpriced_events.py (the unpriced setup from AC-19, plus an EventLog) printed:
      `case1: raised UsageAccountingError`
      `case1 events: ['run_started', 'goal_set', 'goal_rechecked', 'run_finished']`
      `case1 last event: BrowserEvent(kind=<BrowserEventKind.RUN_FINISHED: 'run_finished'>, sequence=4, episode=0, detail='final_response')`
      `case1 response.stop_reason: None usage: None output: ''`
  Failure: a model reply reports a model with no pricebook row (or a call goes unaccounted). The caller gets `UsageAccountingError` (INV-21: "raises … instead of returning"), but any dashboard or log built on `on_event` records a successful finish. Its last event is `run_finished` with `final_response`, the opposite of what the caller saw. `agent.response.stop_reason` and `.usage` stay None, so the response cannot explain the stop either. The AC-19 test (test_browser_agent_observability.py:170-176) asserts only the raise, so this ordering is untested.
  Smallest fix: run `settle()` before choosing the terminal event. On `UsageAccountingError`, emit `RUN_STOPPED` (detail such as `usage_unaccounted`) and re-raise. Otherwise emit as now and return `finished(...)`. INV-20 still holds: exactly one terminal event, at loop return. Add `log.kinds()[-1] == "run_stopped"` to the AC-19 test.
  Spec IDs: INV-20, INV-21, AC-19

R-E2 [Major] [test quality] tests/features/browser_agent/test_browser_agent_episode.py:238,266 (window built at vidbyte/agents/browser/episode.py:148) — No test can tell `keep_observations` apart from a hard-coded 1, so the default of 2 settled in Q-4/Q-6 has no regression guard
  Evidence: the only runs that exercise the window both use `build_agent(keep_observations=1)` (lines 238 and 266, AC-9 and AC-31). The settings tests check only the stored value (test_browser_agent_settings.py:259).
    Mutation probe `mutant_keep_one.py`: a pytest plugin forcing `tool_output_sliding_window(keep_recent=1)` for every worker.
      `MUTANT ACTIVE: keep_recent forced to 1`
      `106 passed in 0.86s`
  Failure: a refactor that drops the argument, or passes `BROWSER_MIN_CAP`, sends each worker 1 full observation per tool instead of the settled 2, and the whole pack stays green. This is the exact regression spec §16 R-6 (Major) already caught once in review ("the settled '2 observations kept' became '1 per tool'"). The opposite mistake goes undetected too: a build that ignores the setting and uses the default constant passes every run except AC-9/AC-31 only by luck of which value they chose.
  Smallest fix: parametrize AC-9 over `keep_observations` in {1, 2} (or add one default-settings case). With 2, the 4th worker call carries the first snapshot cut to 400 characters and the second and third whole.
  Spec IDs: INV-11, FR-7, D-10, AC-9, Q-6

R-E3 [Minor] [test quality] vidbyte/agents/browser/episode.py:160, vidbyte/agents/browser/goal.py:230 — No run test checks that `episode_model_name` and `recheck_model_name` reach the worker and the recheck
  Evidence: `grep -rn "episode_model_name\|recheck_model_name" tests/features/browser_agent/` finds only settings-validation rows (test_browser_agent_settings.py:170-171, :266).
    The fixture seam receives the agent but drops its model (browser_agent_fixtures.py:247-248): `def runner_for(agent: BaseAgent) -> tuple[object, str]: return _ScriptedRunner(model, agent.name), RUNNER_TYPE_TEXT`.
  Failure: a mutant where `model_name=settings.model_name` ignores the override, at either site, passes all 106 tests. In production every worker then runs on the orchestrator model, which is the cost the override exists to cut, and nothing reports it.
  Smallest fix: record `agent.model_name` on `ModelCall` in `runner_for`. Add one run with both overrides set, asserting that worker calls and recheck calls carry their own models.
  Spec IDs: D-13, §9.3 settings row (`episode_model_name` / `recheck_model_name`)

R-E4 [Minor] [data and scale] vidbyte/agents/browser/episode.py:90 + vidbyte/agents/runtime.py:1836-1837, :1866-1868 — `loop.max_tool_calls` never counts `run_episode`, so the only bound on episodes is `loop.max_iterations`, and the README does not say so
  Evidence: the episode spec is `metadata={"internal": True}` (episode.py:90). `_enforce_tool_settings` returns early for internal calls (`if tool_is_internal: return None`), and the budget counts only `_non_internal_tool_contexts` ("@intent internal-tools-never-spend-the-tool-budget"). README.md:58 says only "Orchestrator: 1,000 iterations and tool results cut at 20,000 characters, unless you pass another `loop`".
  Failure: a developer passes `loop=AgentLoopSettings(max_tool_calls=40, ...)` expecting a spend ceiling for an eight-hour run. `run_episode` and `patch_goal` never spend it, so the run can still make one or more episodes per iteration. At defaults that is 1,000 × (30 browser actions + up to 34 worker model calls), and more when the model emits several `run_episode` calls in one turn.
  Smallest fix: one README "Limits" sentence: `max_tool_calls` counts only search/fetch/developer tools; episodes are bounded by `loop.max_iterations` × calls per turn. A `max_episodes` cap would be [scope-adding] (Q-4/Q-10 settled the caps) and is a follow-up only.
  Spec IDs: n/a (documentation of D-9/Q-4 behavior)

R-E5 [Minor] [security] vidbyte/agents/browser/settings.py:69 — `command` shows in `repr(settings)` although the module says its arguments may carry a key
  Evidence: `command: tuple[str, ...] | None = None` has no `repr=False`. The header says "A duplicate command is reported by its program name only, since later arguments may carry a key" (settings.py:9). `_require_distinct_servers` names only `command[0]` for that reason (:243-252). Because `BrowserAgentSettings` is a dataclass, `repr(settings)` includes each server's full `command`.
  Failure: `BrowserServerSettings(command=("npx", "some-mcp", "--api-key", "sk-…"))` is accepted, and logging `settings`, or a traceback that prints it, shows the key. The code guards the error message against this case but not the repr.
  Smallest fix: `command: tuple[str, ...] | None = field(default=None, repr=False)`, or a `__repr__` that shows the program name only.
  Spec IDs: INV-3 ("repr(settings)"), T-1

R-E6 [Minor] [error handling] vidbyte/agents/browser/episode.py:102-110 — The counter advances and `episode_started` is emitted before worker construction and prompt formatting, which sit outside the try
  Evidence: lines 102-104 run `self._episodes += 1 … emit(EPISODE_STARTED)`, then lines 109-110 run `worker = self._worker(index)` / `prompt = Prompts().get(...).format(...)`, and only then does `try:` open at line 118.
  Failure: if `BaseAgent(...)` or the prompt lookup raises (for example a packaging miss of the worker leaf), the call yields no card, no `episode_finished` event and no `response.episode`. The episode index is still spent. That breaks "exactly once" for a call that was not cancelled, and leaves the sink with an unmatched `episode_started`.
  Smallest fix: move lines 109-110 inside the `try`. The existing `except (VidbyteSdkError, OSError, ValueError)` then gives an error card, with `worker` built first, or `tokens=None` when it is unbound.
  Spec IDs: INV-12

R-E7 [Minor] [test quality] tests/features/browser_agent/test_browser_agent_observability.py:197 — The `repr(agent.tools)` clause of AC-3 cannot fail
  Evidence: `exposed = [repr(agent.tools), …]`. Probe output:
    `<vidbyte.tools.catalog.Tools object at 0x0000021C74153D90>`
    `[]`
    `Tools.__repr__ is object.__repr__: True`
    `Tools` has no `__repr__`, and after a sync run the bridged tools are released anyway.
  Failure: if a later change gives `Tools` or `McpBridgedTool` a repr that prints server config, this clause stays green, because it reads an empty catalog's address. The guarantee holds today only by accident.
  Smallest fix: read `repr(agent.tools)` while the servers are attached, either inside a scripted step via `observe(...)` or after `arun` and before `close_mcp_servers()`.
  Spec IDs: AC-3, INV-3, T-3

R-E8 [Minor] [scope-adding] [data and scale] vidbyte/agents/browser/usage.py:9, :40-52 — An unpriced worker or recheck model is reported only after the whole run has spent its budget
  Evidence: the usage.py header says "settle runs once, after the loop returns, so a run spends its whole budget before an unpriced call is reported". probe_unpriced_events.py case 2 gave worker 1's card an unpriced model:
    `case2: raised UsageAccountingError`
    `case2 events: ['run_started', 'goal_set', 'episode_started', 'episode_finished', 'episode_started', 'episode_finished', 'goal_rechecked', 'run_finished']`
    `case2 calls by agent: {'vc-scout': 3, 'vc-scout-episode-1': 1, 'vc-scout-episode-2': 1, 'vc-scout-recheck': 1}`
  Failure: an `episode_model_name` that passes `validate_provider_model_pair` but has no pricebook row (the spec's own S2 defect with `gpt-4.1`) runs all ~1,000 iterations of an eight-hour job, then withholds the result. This is documented and matches INV-21, so it is not a defect in this PR.
  Smallest fix (follow-up): check `model_name`, `episode_model_name` and `recheck_model_name` against the pricebook in `BrowserAgentSettings.__post_init__`. This adds a control the spec does not contain.
  Spec IDs: INV-21 (as designed), A-5

VERIFIED CLAIMS
1. The browser pack passes at the reviewed code — held (106 passed). HEAD 51e573a0 differs from 3f9e63c9 only in `docs/spec/browser-agent/pipeline.md`, so S3's "HEAD code = 3f9e63c9" claim held.
2. "A rebuild keeps exactly the newest whole call/result group" (D-11, INV-30) — held for OpenAI, Anthropic and Gemini stored shapes, including multi-result turns. The probe printed `anthropic bulk+isDone refusal: removed=4 kept=3` (the assistant turn and both tool_result messages) and `gemini bulk+isDone refusal: removed=4 kept=3`.
3. "`messages` in the hooks is the stored history" — held: runtime.py:314-317 passes `state.messages`, so `messages[:] = list(kept)` rewrites the stored list.
4. "A refused finish skips `_after_tool_iteration`, so the rebuild must also run in `_continue_finish_attempt`" — held (runtime.py:680-688). Both call sites exist (runtime.py:136-145, :147-162), and AC-33 covers the refused-finish site.
5. "Tool calls in one turn run sequentially, so episodes never overlap" (D-22) — held (runtime.py:611-612 awaits each call in a for loop).
6. "The worker's `last_reply` is set before the schema raise" (EC-11/EC-12) — held: base.py:1007-1009 runs before :1022.
7. "The action cap stops before the next model call; iterations are checked before tool calls" — held (runtime.py:2055-2080). AC-7 asserts `max_tool_calls`; a mutant with `max_iterations` lacking the reply turns would fail it.
8. "The recheck is fresh" (D-13) — held: test_browser_agent_recheck.py:79 `assert call.messages == []` and :110 for the second recheck.
9. "No change under `vidbyte/tools` or `vidbyte/middleware`" — held (diff stat over the reviewed range).
10. "Internal tools never spend the tool budget" — held (runtime.py:1836-1837, :1866-1868). It is the source of R-E4.
11. "Every error BaseAgent re-raises unwrapped is caught by the episode and recheck handlers" — held (all subclass `VidbyteSdkError`).
12. Test-quality mutation reasoning. Each line is a plausible bug and the test that catches it:
   - Episode caps:
     - worker `max_iterations` without reply turns → AC-7 (stop_reason);
     - a non-screenshot tool capped → the INV-10 test;
     - no card token cap → the oversize-card test;
     - window hard-coded to 1 → **not caught** (R-E2).
   - Rebuild:
     - `max_messages=2` → AC-22 (asserts 2 kept messages);
     - rebuild after the gap message → AC-33;
     - event on `removed_count == 0` → EC-35 test.
   - Recheck/stall:
     - `recheck_every` ignored → AC-14;
     - `>` for `>=` in stalled → AC-15;
     - recheck inherits the conversation → recheck test :79.
   - Settings/security:
     - permission policy not passed to workers → the T-2 test;
     - model overrides ignored → **not caught** (R-E3);
     - key leaked via `repr(agent.tools)` → **not catchable** (R-E7).
   - Usage/events:
     - unpriced call returns instead of raising → AC-19;
     - terminal event wrong on a raise → **not caught** (R-E1).

COMMANDS RUN (keys unset with `env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY -u VIDBYTE_API_KEY -u XAI_API_KEY -u GROK_API_KEY -u DEEPSEEK_API_KEY -u OPENAI_API_KEY`, `PYTHONPATH=$(pwd)` from the worktree root)
- `python -m pytest tests/features/browser_agent -q -p no:cacheprovider` → `106 passed in 1.48s`
- `python -c "import vidbyte,inspect; print(inspect.getfile(vidbyte))"` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`
- `git diff --stat 3f9e63c9 HEAD` → only `docs/spec/browser-agent/pipeline.md`; `git rev-parse --short HEAD` → `51e573a0`
- `python <scratchpad>/probes/probe_engine_shapes.py` → `anthropic single-call turns: removed=4 kept=2` / `anthropic bulk+isDone refusal: removed=4 kept=3` / `gemini single-call turns: removed=4 kept=2` / `gemini bulk+isDone refusal: removed=4 kept=3` / `openai final-text refused (gap then answer): removed=3 kept=1`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(pwd);<scratchpad>/probes" python -m pytest tests/features/browser_agent -q -p no:cacheprovider -p mutant_keep_one -s` → `MUTANT ACTIVE: keep_recent forced to 1` / `106 passed in 0.86s`
- `python <scratchpad>/probes/probe_unpriced_events.py` → the case1/case2 lines quoted in R-E1 and R-E8
- `python -c "...build_agent(); print(repr(a.tools)) ..."` → `<vidbyte.tools.catalog.Tools object at 0x…>` / `[]` / `Tools.__repr__ is object.__repr__: True`
- `grep -rn "episode_model_name\|recheck_model_name" tests/features/browser_agent/` → settings rows only (test_browser_agent_settings.py:170, :171, :266)
- `git status --porcelain` → empty (no worktree changes besides this report; `__pycache__` is git-ignored)
- Probes live in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d4409101-4281-402b-989c-fb71871586cd/scratchpad/browser-agent/probes/` (`probe_engine_shapes.py`, `mutant_keep_one.py`, `probe_unpriced_events.py`).
