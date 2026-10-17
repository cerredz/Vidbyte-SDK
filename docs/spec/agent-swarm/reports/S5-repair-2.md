# S5 repair, iteration 2 of 8: AgentSwarm

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm`, branch `feat/agent-swarm`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1174 (draft). Start HEAD `c66a1ffe` (local; origin at `87df4fc9`). Scratch evidence is in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/`: `s5r2-source.log`, `s5r2-package.log`, `s5r2-lint-before.txt` and `s5r2-lint-after.txt`.

## Defects in

- **R-16** (Minor, spec text). Resolved by spec r5 at `c66a1ffe` before this iteration started, so there is nothing to change in code or tests. Recorded in review.md as `resolved in spec r5 @c66a1ffe`.
- **R-17** (Minor, docs against fixed behaviour). Fixed at `4a993f98`.
- No gate was failing. origin/main had not moved (`git log HEAD..origin/main` is empty), so no merge was needed.

## Per finding

### R-17: three doc sentences

1. **`vidbyte/agents/agent_swarm/swarm.py:38`.** The `AgentSwarm.arun` docstring is now "Run the swarm on the goal until no agent is working, or the time limit is reached." Checked against the code:
   - `_end_check` (`runtime.py:279-290`) decides the end only when `self._working` is empty, and it picks FAILED, MAX_TURNS or QUIET by INV-10.
   - The only other end is `asyncio.timeout`, at `runtime.py:97-104`.
   - A spent budget only refuses wakes (`runtime.py:183`, `:209`), as INV-9 and EC-9 say, and `test_agent_swarm_acceptance.py:107` (EC-9) pins it.
   - "Every agent failed" is one case of "no agent is working", so the old list was wrong and also redundant.
   - The wording matches the package README line 3, `REPO_MAP.md:77` and the `runtime.py` PURPOSE line.
   - `help()` now prints the new line: `python -c "from vidbyte import AgentSwarm; print(AgentSwarm.arun.__doc__)"`.
2. **`vidbyte/agents/agent_swarm/README.md:58`.** The row now ends "may not take a swarm tool's name or `isDone`". Checked against the code:
   - The refusal is at `settings.py:105-107`. `probe_verify.py p3` prints `ConfigurationError: AgentSwarmSettings.search_tool must not take a swarm tool's name; got 'isDone'. Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.`
   - The row agrees with EC-33 and the §9.3 `search_tool` row.
3. **`vidbyte/agents/agent_swarm/events.py:9`.** I reworded the header and kept the placeholder. The new sentence: "AgentSwarmRuntime builds one record with the runtime and replaces it with a fresh one when arun starts, before the first event, so elapsed_ms counts from the start of the run, not from when the runtime was built." Checked against the code:
   - `runtime.py:53` builds the placeholder.
   - `:79` replaces it right after `_ran = True`.
   - The first `record` call is at `:89`.
   - Spec r5 §17 describes the same thing: "the event record is rebuilt right after the run is marked as run".
   - `test_event_time_counts_from_arun_not_from_building_the_runtime` still passes.

#### Why the reword, and not deleting the placeholder

The other option was to delete `runtime.py:53` and let `arun` be the only place that builds the record, which would make the old header true. Grep shows that every read of `self._events` is inside a method that runs during `arun`, and no test touches it earlier, so mypy would accept the deletion.

But `post_message`, `collect_messages`, `end_turn` and `record_tool_call` are public methods of `AgentSwarmRuntime`, which is exported from `vidbyte` and `vidbyte.agents`. Called before `arun`, each one now records into the placeholder, and `post_message` also flushes to `on_event`. Without the placeholder each would raise `AttributeError`. That changes behaviour on a misuse path, and the briefing (rule 6) forbids any behaviour change.

The reword changes no code. The lint table stayed byte-identical.

The deletion becomes the right fix if a later PR is allowed to change behaviour and the owner wants those four methods to refuse calls before `arun`. In that case, guard them with an explicit `ConfigurationError` rather than leaving the `AttributeError`.

### Same-class sweep

I grepped all 37 product files this branch changes for "budget is spent", "turn budget", "work left", "swarm tool's name" and "when the runtime". No other sentence is false:

- `swarm.py:27` (the class docstring) and `vidbyte/agents/README.md:419` say the agents stop when "none has work left". This is a summary, not a list of end conditions. I left both alone, because rewording them was not in the request (rule 11).
- The `MAX_TURNS` enum comment "the turn budget refused a wake" is accurate.
- `runtime.py:9` already says MAX_TURNS needs a waiting message.

## Gate matrix (local, on `4a993f98`)

| Gate | Result | Final lines |
|---|---|---|
| `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` | PASS | `171 passed in 5.69s` |
| `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 698f913b594f9cbeac6513d4883c0e4f0f1f4175 (vidbyte-sdk 0.3.0, 649 exports).` |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: lint | PASS | `S063 IMPROVED 4 -> 3. Lower it with: ...` / `S064 RATCHETED: 4 known finding(s). ...` / `SDK-LINT: PASS`. 0 REGRESSED. All 133 rule lines are identical to iteration 1's run on `dc4710f9` (`diff` exit 0). |
| same run: pytest | FAIL, 3 inherited | `FAILED .../test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `=========== 3 failed, 6414 passed, 16 skipped in 145.31s (0:02:25) ============` / `CI failed: Command failed with exit code 1: ...python.exe -m pytest ...` |
| `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1) | PASS | `Scan was limited to files tracked by git` / `Ran 1 rule on 995 files: 0 findings.` |

The three pytest failures are the same `harness_threads` surface tests that iteration 1 showed are inherited:
- one fails on main itself, because it expects 120 `FailureCode` members and main has 148;
- two diff `git merge-base origin/main HEAD`, so they fail on any branch that changes `vidbyte/tools` or the root exports.

CI skips all three in its shallow clone.

## Remote checks (dispatched on `4a993f98`)

| Run | Result | Final lines |
|---|---|---|
| CI 39008866234 | success: Source / Python 3.11, Source / Python 3.12 and Package | `SDK-LINT: PASS` / `6376 passed, 57 skipped in 116.32s` / `CI passed.` (3.12: `6376 passed, 57 skipped, 19 warnings in 123.72s`). Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Static policy 39008871160 | success | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.` |

`gh pr checks` stays empty for dispatched runs, so I read both runs with `gh run view`.

## Test changes proposed

None. `git diff 87df4fc9..HEAD -- tests/` is empty.

## Findings disputed

None.

## Still open

No finding is open. R-15 remains a follow-up for a separate PR, which S4 decided.
