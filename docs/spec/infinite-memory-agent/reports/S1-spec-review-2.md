VERDICT: SOUND WITH FIXES — All 15 round-1 fixes are in r2, and the new wiring (history trimming, live-catalog extras, the internal launch tool) checks out against the code. Four new Major gaps remain, and each has a local fix that leaves the architecture unchanged:
- A second run on the same agent instance replays every earlier tool output into a system string that trimming cannot reach.
- A malformed bookkeeping line still stops the root one step after R-5's guard saved the cards.
- R-2's fix lets `entries.jsonl` grow past the limits of two preset tools.
- Non-SDK exceptions from a pair's own disk I/O and parsing still escape `gather`, and the running-key guard that would have caught the follow-on is now gone.

WHAT THE SPEC GETS RIGHT (do not "fix" these)
- **D-28 reaches every agent and keeps provider pairing valid.**
  - The path is `BaseAgent(middleware=…)` (base.py:100) → `self.middleware` (237) → `_runtime_middleware()` (1405) → the runtime's `MiddlewarePipeline` (runtime.py:200).
  - Row 20 builds each generator and verifier as a `BaseAgent` with its own instance.
  - The trimmed list reaches the runner as `messages` (runtime.py:1066-1082).
  - After trimming, `ContextCompactionEngine._repair_tool_pairing` (middleware/compaction/engine.py:56-69, 92-114) drops any orphaned call or result. So even a parallel-call turn split across two groups by `_provider_groups` cannot reach the provider broken.
- **R-7's "live catalog at run start" needs no new machinery.**
  - `_generate_reply` awaits `_ensure_mcp_connected` (base.py:866) before both `_runtime()` calls (1226, 1263).
  - Each runtime gets `tools=self.tools` plus `isDone` (runtime.py:192-193).
  - `_tool_name_is_internal(name)` exists (1405-1414).
  - Non-escalation holds: a nested launch tool sees only the extras its card named (INV-7).
- **INV-38 / D-29 match the runtime exactly.** Internal tools skip `tool_timeout_seconds` (runtime.py:1472), tool budgets and `allowed_tools` (1782), and `result_max_chars` truncation (1929). So AC-35 holds as written.
- **r2 did not grow the design beyond what the findings asked for.**
  - Trimming costs one constant and one constructor argument; D-29 costs one metadata flag; `loop` gains one default.
  - Withdrawn IDs (D-19, EC-35, Q-5, the running set, `loop=` in §4) are gone from live text.
  - Every count holds:
    - 18 CREATE + 15 MODIFY rows;
    - 12 new `.py` files;
    - 41 leaves, taking the prompts to 98 + 41 = 139 assets in 34 families;
    - 13 config keys;
    - 8 model-facing tools.

ROUND-1 DISPOSITIONS
- R-1 — resolved for a single run. The wiring is D-28, INV-23, row 20 (`middleware=(…trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS),)`, "a new instance per agent"), row 22, and AC-33. Residual issues: the cross-run replay (R-16), and a task copy that turns out redundant (R-21).
- R-2 — resolved. INV-19 now reads "The three bookkeeping files are bounded only by `max_tokens`", row 17 reads "never `max_file_tokens`, which applies to notes only", and AC-34 was added. This opens a new regression (R-18).
- R-3 — resolved. The §8.5 `loop` default is `partial(AgentLoopSettings, max_iterations=INFINITE_DEFAULT_MAX_ITERATIONS)`, D-9 is restated, EC-47 and AC-39 were added, and §4 drops `loop=`. One imprecision: D-9's "model calls" are really loop iterations, since middleware retries or a fallback can add calls within one iteration.
- R-4 — resolved. INV-38, D-29, the §9.2 Permission column ("internal (`metadata={"internal": True}`)"), row 20, §12.4 and AC-35 all carry it.
- R-5 — partially resolved. INV-29 and row 20 have one guard spanning the pair, row 4 lets `summary`/`review` be empty, and AC-37 was added. But:
  - the root crashes at its next map render (R-17);
  - `OSError` and `ValueError` from the pair's own steps still escape (R-19).
- R-6 — resolved. INV-6 says "ordinary tools are shared by identity", AC-28 checks names only, and §12.4 matches.
- R-7 — resolved. INV-7 and row 21 step (2) say "after `BaseAgent` connected any MCP servers", which the code confirms. Residual: a tool added at run time can collide with a run-bound tool name (R-23).
- R-8 — resolved. §11 Typecheck is `python lint/run.py --rule S009`. The S004 1, S009 350, S041 0 and S047 0 ceilings are listed (they match `lint/baseline.json`), and §12.4 has a "Lint ratchets with no headroom" group.
- R-9 — resolved.
  - §12.4: "In a modified file, update only the header lines that name a fact this change alters."
  - Row 26 edits the base.py header, whose line 13 really reads "(LINEAR and JEV)".
  - The P4 order is now 24 → 20 → … committed as one unit.
- R-10 — resolved. Row 33 edits line 91 of `vidbyte/tools/README.md`, which really is the `toolsets/` bullet.
- R-11 — resolved. The INV-19 heading quotes the user's phrase in full; Q-8, D-26 and NG-4 cite it.
- R-12 — resolved. EC-30 now names lost entries and duplicate ids, EC-46 was added, and both appear in row 30's README notes.
- R-13 — resolved. I tested the new pattern: it matches `**VERDICT: passed**`, ``VERDICT: `passed` ``, `VERDICT: **passed**` and `VERDICT: passed.`. Residual: an upper-case value raises `ValueError` (R-19).
- R-14 — resolved as asked: §8.3 weighs commit-at-once, and the running set is gone. But D-22's premise is broken by EC-41 (R-19).
- R-15 — resolved. There are seven `launch_<field>_description` leaves, 41 leaves in all, and the header says 139.

FINDINGS (ranked, most severe first)

R-16 [Major] [L5/L1] §6.1 INV-23, §12.3 row 21 step (2), §6.3 EC-47 — A second run on the same agent instance carries every earlier run's tool outputs in the system string, where trimming cannot reach them
  Evidence:
  - What the spec promises:
    - INV-23: "So the history never outgrows the cap."
    - TL;DR: "so a long run never outgrows its context."
    - EC-47 tells the developer that "a new `run()` on the same workspace starts from the saved memory."
  - What the code does:
    - After every run, base.py:1274 calls `self._record_tool_contexts(result)`, which appends each model-visible tool result to `self._tool_call_contexts` (1343-1348: "Later runs replay these records to the model").
    - base.py:1232 passes that list as `existing_tool_calls`, and runtime.py:265 folds it into `context.tool_calls`.
    - lib/dataclasses/context.py:237-238 renders it on every model call as `Tool calls:\n<name>: args=… output=…` inside the system string.
    - Only `Session` clears the list (sessions/session.py:237-238, 419-420), and this agent refuses sessions (D-8).
    - The trimming middleware rewrites only `messages` (context_compaction.py:191-203).
  Failure:
  - `agent.run(task1)` ends normally, for example at the EC-47 timeout or after 100 root iterations, and the developer calls `agent.run(task2)` on the same object.
  - Every model call of run 2 now carries run 1's tool outputs in its system string, untrimmed: launch cards (up to ~8,500 tokens per batch), bash output (up to ~12,500 tokens per call), and grep results.
  - A few dozen launches put run 2's system string past 60,000 tokens before it does anything, and a third run overflows the provider.
  - It also breaks the design's premise that the workspace is the only state shared between runs.
  Smallest fix:
  - Row 21 step (2) already replaces the context. Clear the replayed calls in the same call: `context = replace(context, tools=self.tools.specs(), tool_calls=())`.
  - Add one INV: "a run's system string holds no tool output from an earlier run of the same agent".
  - Add one AC: two runs on one agent, where the second run's first `system` has no `Tool calls:` section.

R-17 [Major] [L5/L10] §6.3 EC-24, §6.2 AC-37, §12.3 rows 17 and 21 — A malformed bookkeeping line still stops the unattended run at the root's next map render, one step after R-5's guard saved the cards, and AC-37 cannot be observed
  Evidence:
  - EC-24 (r2): "If the root's own map render hits it, the run stops with that error and no `run_finished`."
  - Row 21: `_after_tool_iteration` "upserts a fresh item: the run's task plus a new map".
  - Row 17: `map_text` reads `files.jsonl` and `entries.jsonl`, and "A malformed bookkeeping line raises `ToolExecutionError`".
  - runtime.py:696 awaits `_after_tool_iteration` with no guard around it, so the error leaves `agent.arun`.
  - AC-37 writes a malformed `files.jsonl` line in the middle of a batch and expects the call to "return normally with two cards".
  - §13 gives the only observable as "tool results as the next prompt's tool messages".
  Failure:
  - Any agent's bash leaves half a line in `files.jsonl`, which is EC-24's own trigger. The pairs return UNCHECKED cards as INV-29 promises.
  - Then the root's map refresh raises, and the whole run stops before the root's model sees any card.
  - `resume()` fails the same way until a human edits the file. That defeats "Unattended" for a recoverable data glitch.
  - For AC-37, the next root call never happens, so a blind test author's end-to-end test gets a `ToolExecutionError` instead of two cards.
  Smallest fix:
  - Make the map never fail on file content:
    - `map_text` takes the live-entry count from the number of non-blank lines in `entries.jsonl`;
    - a file whose `files.jsonl` line cannot be read shows `INFINITE_NO_DESCRIPTION`.
  - The commit-time checks keep raising `ToolExecutionError` inside tools and pairs.
  - Restate EC-24: the map shows no description for that file, and the run continues.
  - Move AC-37's malformed line into `entries.jsonl`, which the commit reads.

R-18 [Major] [L6/L5] §6.1 INV-19, §6.3 EC-48, §8.1 D-3, §12.3 row 14 — R-2's fix lets `entries.jsonl` outgrow two preset tools: `grep` silently skips it past 1,000,000 bytes, and `read_lines` returns it whole, past the 60,000-token trim
  Evidence:
  - What the spec says:
    - INV-19 (r2): "The three bookkeeping files are bounded only by `max_tokens`."
    - §9.3 bounds `max_tokens` only from below ("≥ 1").
    - D-3 flips only once "Live entries pass ~10k lines".
  - What grep does:
    - code_search/base.py:32 defaults `max_file_bytes` to 1,000,000.
    - `is_text_file` (106-113) returns False for any larger file, so grep skips it without a message.
    - Row 14 builds `GrepTool(workspace_root, ignore_patterns=…)` with that default.
  - What read_lines does: its `end` parameter is documented as "Reads to EOF if omitted", with no size cap, and `result_max_chars` is unset by default.
  - EC-48 names only developer and MCP tools as able to exceed the cap ("A bash result … and a full batch of 10 cards … stay well below it").
  Failure:
  - At ~320 characters per line, `entries.jsonl` passes 1,000,000 bytes at about 3,100 entries. That is a third of D-3's 10k-line threshold. It becomes reachable as soon as a developer raises `max_tokens` above the 250,000 default, which a 10M–100M-token task invites. From then on, every `grep` for a remembered fact returns no match, and nothing reports an error.
  - Separately, `read_lines("entries.jsonl")` with no range is the natural "read my memory" call, prompted by the map's token count. It returns up to `max_tokens` tokens. Above 60,000, the trim drops the whole group, so the model never sees the result and tends to call again until `max_iterations`.
  - Before r2, `max_file_tokens` (20,000) capped both files.
  Smallest fix:
  - (1) Size grep's file limit from the workspace cap. `get_tools(root_dir, workspace_root, max_file_bytes)` receives a value derived from `max_tokens` through named constants: characters per token × the UTF-8 worst case of 4 bytes per character. Then no workspace file is ever skipped.
  - (2) Bound every tool result with the existing mechanism. The `loop` default also sets `tool_settings=ToolSettings(result_max_chars=INFINITE_TOOL_RESULT_MAX_CHARS)`, one constant safely under the trim cap (for example 100,000 characters). `launch_subagent` is internal, so it stays exempt.
    - This is a default of an existing field, not a new knob, and request list E names "long bash output capped (existing tool-result compaction)".
    - It also closes EC-48 for developer and MCP tools.
  - Either way, correct EC-48 and D-3's flip condition.

R-19 [Major] [L5] §6.1 INV-29, INV-14, §6.3 EC-41, §8.1 D-22, §12.3 rows 17, 18, 20 — The pair guard catches only `VidbyteSdkError`, but the pair's own disk and parse steps raise `OSError` and `ValueError`; once one escapes, the root can start a second pair under a key that is still running
  Evidence:
  - Unconverted I/O errors:
    - Row 20 says "One `try/except VidbyteSdkError` spans its whole body".
    - Inside that body the pair calls `commit_entry` (row 17: append, temp file + `os.replace`) and `journal.pair_finished` (row 18: append and `os.fsync`). Neither row converts `OSError`.
  - Unconverted parse errors:
    - Row 17 converts only a "malformed bookkeeping line".
    - A line bash writes that is valid JSON but the wrong shape (`{"id": "x"}`, or a list) raises `KeyError` or `TypeError`.
    - Non-UTF-8 bytes raise `UnicodeDecodeError` under the strict `encoding="utf-8"` that row 17 requires.
  - An unconverted verdict value:
    - INV-14 makes the verdict case-insensitive, and I checked that the pattern returns `PASSED` for `Verdict: PASSED`.
    - `InfiniteVerdict("PASSED")` raises `ValueError`, and no row says to lowercase the value.
  - The broken premise:
    - EC-41 calls such an escape "a bug" and accepts that "sibling pairs keep running until they finish".
    - D-22 dropped the running-key check because "no other call in the process can meet a running key". That holds only while a launch call never returns before its pairs finish.
    - pipelines/parallel.py:43 uses `asyncio.gather` without `return_exceptions`.
  Failure:
  - One of these escapes the pair. Examples: on Windows a supersede commit's `os.replace` raises `PermissionError` because another process holds `entries.jsonl` open; or a verifier ends with `VERDICT: PASSED`.
  - `gather` raises, the root gets one `ToolExecutionError`, and every sibling's card is lost while the siblings keep running.
  - The root then relaunches the same names. Finished siblings replay, but a sibling still running has no `pair_finished`, so a second pair starts under the same key.
  - The result is duplicate work, duplicate commits, and two `pair_finished` records for one key.
  Smallest fix:
  - (1) Row 20's guard catches `(VidbyteSdkError, OSError, ValueError)`, which covers the JSON and Unicode decode errors. `CancelledError` still propagates.
  - (2) Row 17: a line that is not JSON, or not in the §9.1 shape, raises `ToolExecutionError` naming the file and line.
  - (3) INV-14: the matched value is lowercased before it maps to `InfiniteVerdict`.
  - (4) Restate EC-41 to include the duplicate-key consequence of relaunching while orphaned pairs still run.

R-20 [Minor] [L9/L10] §12.3 row 20 step (4), §6.2 AC-31 — A batch made only of replays builds an empty `ParallelPipeline`, which raises
  Evidence:
  - Row 20 step (4) says "Run `ParallelPipeline(pairs).run("")`" with no condition.
  - pipelines/parallel.py:37-38: `if not stages: raise PipelineExecutionError("ParallelPipeline requires at least one stage.")`.
  - AC-31 relaunches only `a`.
  Failure: Built exactly as row 20 says, AC-31 returns that pipeline error instead of `a`'s replayed card.
  Smallest fix: Row 20 step (4) runs the pipeline only when at least one new pair exists.

R-21 [Minor] [L2/L10] §6.1 INV-22, INV-23, §8.1 D-28, §6.2 AC-33 — The task copy in the system item duplicates what the runtime already re-sends on every call, and the trim is described as oldest-first when it is not
  Evidence:
  - Why the task cannot be trimmed:
    - The run's message goes to the runner as a separate prompt on every call, placed at `prompt_index` (runtime.py:1563-1570; `vidbyte/lib/util/prompt_placement.py`).
    - With no caller messages the boundary is 0, and runtime.py:1080 keeps a 0 boundary through any rewrite, because `[:0]` always compares equal.
    - So trimming never removes the task. Round 1's premise that "the oldest group, which is the task message, is the first thing trimmed" was false.
  - What the spec says:
    - D-28: "The task joins the map in the system-string item, so trimming never removes it."
    - INV-23: "keeps the newest whole tool call/result groups that fit and drops the oldest".
  - What the trim actually does: strategies.py:609-620 scans from newest to oldest and keeps every group that still fits. A small old group therefore survives when a larger, newer group is skipped.
  Failure:
  - Every call pays for the task twice.
    - For the root this is the developer's whole task text.
    - For a child it is the whole task message: criteria, the pasted context entries, and the finished-child lines.
  - A blind test author who builds AC-33 from results of unequal size (small, large, large) finds the oldest group still present.
  Smallest fix:
  - Keep the item map-only: drop `{task}` from `context_item`, or drop that leaf and use `map_header`. If the author keeps the copy, D-28 should state the real reason.
  - Restate INV-23 in two parts:
    - The task is the run's prompt, which the runtime re-sends ahead of the run's exchange on every call; the map and the rules live in the system string.
    - The trim keeps, from newest to oldest, every whole group that still fits.
  - AC-33 uses tool results of equal size.
  - §13's `system` note follows the change.

R-22 [Minor] [L9] §12.3 row 17, §6.1 INV-20, INV-21, §9.3 `max_file_tokens` — `edit_file`'s path rules are unstated, and the "file" vs "note" wording went stale after R-2
  Evidence:
  - Row 17: "`write_note` enforces INV-19 and INV-20 … `edit_file` enforces a unique match … and the caps".
  - INV-20 is phrased only for "a note path".
  - INV-21 says "Tools never write under `seed/`".
  - §9.3 still describes `max_file_tokens` as "tokens per file", while INV-19 now applies it to notes only.
  Failure:
  - Under FULL, an implementer following row 17 lets `edit_file("entries.jsonl", …)` rewrite memory without the INV-17 rules and the INV-24 id scheme.
  - The same implementation lets `edit_file(".runs/<id>.jsonl", …)` delete or forge a `pair_finished`.
  - A test author who applies INV-21 to `edit_file` gets a failing test.
  Smallest fix:
  - Row 17: "`edit_file` applies INV-20's path rules to an existing file".
  - §9.3 purpose: "tokens per note or seed".

R-23 [Minor] [L5] §12.3 row 21 steps (1)–(2), §6.3 EC-1 — A tool added with `add_tool` or by an MCP server whose name matches a run-bound tool makes the run fail after `run_started` is written
  Evidence:
  - EC-1 and row 16 reject reserved names only in `settings.tools`.
  - R-7's fix made tools added with `add_tool` and MCP tools first-class extras.
  - Row 21 writes `run_started` in step (1), then calls `self.tools.extend(...)` in step (2).
  - `Tools.add`/`extend` raises `ToolRegistrationError("Tool already exists: …")` on a duplicate name (tools/catalog.py:75-89).
  - `bash`, `grep` and `read_lines` already collide inside `add_tool`. But `remember`, `write_note`, `edit_file`, `drop_entry` and `launch_subagent` only enter the catalog in step (2).
  Failure:
  - An MCP memory server that exposes `remember` makes every `run()` leave an unfinished journal and fail with a registry error.
  - `resume(None)` then picks that journal and fails the same way.
  Smallest fix:
  - Row 21 computes the extras and checks them for a reserved name before `InfiniteRunJournal.start`. A collision raises `ConfigurationError` naming the tool and the reserved list.
  - Extend EC-1 to tools added with `add_tool` or by an MCP server.

VERIFIED CLAIMS
- Held: `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_messages=None, max_tokens=None, token_counter=None)` is at context_compaction.py:136-139. Its `before_model_call` rewrites `ctx.provider_messages` (191-203), and it is exported from `vidbyte.middleware` (`__init__.py:46`) and `vidbyte` (`__init__.py:491`).
- Held: the middleware reaches the root and every child. base.py:100 → 237 → `_runtime_middleware` (1405) → runtime.py:200 `MiddlewarePipeline((*middleware, *admission))`. The trimmed list replaces `call_options["messages"]` (1074-1075) and reaches the runner through `_call_with_supported_kwargs` (base.py:1455-1469).
- Held: whole groups are kept, and pairing is repaired afterwards (strategies.py:21-33, 577-620; engine.py:56-69).
- PARTLY FALSE: INV-23 says the trim keeps "the newest … and drops the oldest". The strategy keeps every group that still fits, so an older small group can survive (R-21).
- FALSE (round-1 premise behind R-1's fix (2)): "the task message … is the first thing trimmed". The task is the runner's separate prompt on every call, and the 0 boundary survives any rewrite (runtime.py:1080; prompt_placement.py). The system-item copy is redundant (R-21).
- Held: `_ensure_mcp_connected` (base.py:866) runs before `_runtime()` (1226, 1263, 1330). The runtime holds `user_tools = tools` and `tools = with_internal_agent_tools(tools)` (runtime.py:192-193), so extras = catalog minus reserved names minus `isDone` is implementable (R-7). MCP tools join through `add_tool` (mixins.py:371-382).
- Held: `_tool_name_is_internal` (1405-1414) exempts internal tools from the tool timeout (1472), budgets and `allowed_tools` (1782), and truncation (1929). The precedent is `JevBulkWorkTool.spec` `metadata={"internal": True}` (jev/bulk_work.py:115).
- Held: `_after_tool_iteration` exists (runtime.py:916) and is awaited unguarded at 696, so an exception there ends the run (R-17).
- FALSE (unaccounted): BaseAgent replays every earlier run's tool contexts in the system body (base.py:1232, 1274, 1343-1348; runtime.py:265; context.py:237-238). Only `Session` clears them (R-16).
- Held: `GrepTool` defaults `max_file_bytes` to 1,000,000 and silently skips larger files (code_search/base.py:32, 106-113). `ReadLinesTool` reads to EOF with no cap (R-18).
- FALSE: EC-48's claim that only developer or MCP tools can return more than the cap. `read_lines` on a bookkeeping file can (R-18).
- Held: `ParallelPipeline.run` is `asyncio.gather` without `return_exceptions` (parallel.py:43), and it raises on zero stages (37-38) (R-20).
- FALSE: D-22's premise "no other call in the process can meet a running key". EC-41's accepted escape returns the launch call while its pairs still run (R-19).
- Held: `Tools.add`/`extend` raise on duplicate names (catalog.py:75-89). `Tools.all()` exists, which row 22 uses.
- Held: `AgentLoopSettings` limits default to `None` (settings/loop.py:49-77), and `_budget_stop` checks iterations and the deadline between iterations (runtime.py:1980-2023).
  - A generator stopped this way returns the text "Agent runtime stopped after reaching max_iterations." (1989-1996), so its PARTIAL card's summary is that line.
  - D-9's "model calls" are loop iterations.
- Held: the verdict pattern matches all three AC-38 forms and keeps the last match. An upper-case value returns `PASSED` (R-19). A heading (`## VERDICT: passed`) or list form (`- VERDICT: passed`) does not match, which is acceptable given the preamble.
- Held: base.py:13 reads "the linear-loop runtimes (LINEAR and JEV)" (row 26), and `vidbyte/tools/README.md:91` is the `toolsets/` bullet (row 33). The REPO_MAP toolsets entry (343-345) still says "one such bundle" while the folder holds two, so a third makes row 32's regeneration correct.
- Held: there are 98 `Prompt` members and 33 family JSON files (the header says "98 static prompt assets across 33"), so the change yields 139 assets in 34 families.
- Held: the `lint/baseline.json` ceilings are S004 1, S009 350, S041 0, S047 0, A007 255 and S025 263.
- Held: `BashTool` kills the process group on cancellation on POSIX and documents the Windows limitation (bash.py:5, 9, 139, 197-230), which supports EC-31 and INV-31.
- Held: `ContextManager.items()` returns only unmanaged items (manager.py:264-266), so a child's upserted map item renders once, in the primitives zone, and is never folded into the body.
- Held: no attribute collision on `BaseAgent` or the MCP mixin for `workspace`, `settings`, `resume` or `aresume`.
