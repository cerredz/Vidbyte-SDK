VERDICT: SOUND WITH FIXES — The architecture is right-sized and well grounded, but as written a long unattended run either overflows the root's context or stops writing memory after about 250 entries. Several spec-level contradictions would also produce broken tests or gate failures. Every fix is a local edit; none changes the architecture.

WHAT THE SPEC GETS RIGHT (do not "fix" these)
- The smallest mechanism is used and matches the repo's grain. `InfiniteMemoryRuntime` only does per-run setup, following the JevAgent pattern. Children are plain `BaseAgent`s run as `BasePipeline` stages under `ParallelPipeline`, each catching `VidbyteSdkError`, as `JevBulkWorker` does. `base.py` is touched by one frozenset member. Verified against the repo:
  - `_LINEAR_LOOP_RUNTIMES` at base.py:78;
  - the facade import at registries/runtimes.py:33;
  - the refusal at jev/runtime.py:59-74.
- The map is compaction-proof through `ContextManager.upsert(..., TOP_OF_CONTEXT)`, which `_build_system_string` renders on every model call (runtime.py:1615; manager.py:208-217 renders `### [id] title`). D-27 honestly records the `setdefault("system")` hole at runtime.py:1561.
- Repo constraints are read correctly and the deferrals follow from them:
  - There is no live tree-wide ledger (base.py:838-842), hence D-9.
  - `Session` restore rebuilds a plain `BaseAgent`, hence the feature's own journal plus `session_persistence_supported = False` (session.py:102).
  - `GrepTool` has a fixed name and `Tools.add` raises on duplicates, hence D-15.
  - `BashTool` needs EXECUTE, hence the `allow_all()` default.
  - The pair-key replay is an idempotency key, and the journal is a write-ahead log that tolerates a torn final line.
- Placement and gate grounding is careful:
  - enums, records and constants are in their `lib` homes;
  - tool text goes through `Prompts().get` (S025);
  - prompt enum↔asset parity uses correct counts (98→131 assets, 33→34 families);
  - C016 is regenerated only after committing row 28, which is correct because the generator refuses dirty inputs;
  - toolsets never import `vidbyte.agents`.

FINDINGS (ranked, most severe first)

R-1 [Blocker] [L1/L5] §8.1 D-19, §6.1 INV-23, §6.3 EC-35 — No history compaction is wired and the task is not in the compaction-proof zone, so a long unattended root overflows and dies instead of surviving "few/10s of compactions"
  Evidence:
  - What the spec says:
    - D-19: "No compaction is wired by default and there is no middleware field … The SDK's compaction middleware is opt-in, and adding a field adds a knob (Q-1)".
    - EC-35: "accepted limitation: the provider error ends the run with no `run_finished`".
    - INV-23 names only "the map and each role's rules" as living in the system string. The task is the root's first user message (row 21, step 4) and the child's task card is its first message (row 20).
  - What the user asked:
    - Prompt 2: "just important memories after few/10s of compactions".
    - Prompt 5: "treating the main agent's context window as somethingg that is VERY limitied … useful for long-term runs".
    - Round 2: "Unattended".
    - The §C architecture: "system prompt: rules + task + workspace map + budgets (rebuilt every turn, so compaction can't remove it)".
    - List E: "existing compaction middleware on by default".
  - What the repo already has:
    - `BaseAgent.__init__(…, middleware=…)` at base.py:100.
    - `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=…)` at middleware/compaction/context_compaction.py:137, exported from `vidbyte.middleware` and `vidbyte`. It keeps whole call/result groups and system groups (strategies.py:578-620).
    - The default `ContextWindowAlgorithm` admits raw tool output (context/presets.py:32-35).
    - Precedent for a prebuilt agent wiring middleware by default: CodingAgent appends `VerifyCommandMiddleware` (agents/README.md:114).
  Failure:
  - At the scale the request names (10M–100M tokens), the root gains up to ~800 tokens of card text per pair plus raw bash and grep results (bash returns up to 50,000 bytes per call).
  - After roughly 100 pairs, or a few large bash outputs, the provider rejects the call. The result is an `AgentExecutionError` with no `run_finished`, and the "unattended" run waits for a human to call `resume()`.
  - INV-23 is vacuous by default, because nothing ever rewrites the conversation.
  - Once compaction is added (Q-1), the oldest group, which is the task message, is the first thing trimmed. The root then forgets its task.
  - The same applies to any generator that delegates deeply.
  Smallest fix:
  - (1) Pass `middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS),)` to the root's `BaseAgent.__init__` and to every child built in `InfinitePair`. This needs one constant and no settings field; Q-1 stays for developer extras.
  - (2) Put the task in the compaction-proof item. The runtime adds the root's task (from `run_started`), and `InfinitePair` adds the task card, to the same TOP_OF_CONTEXT item as the map.
  - (3) Restate INV-23 as "task + map + rules".
  - (4) Replace EC-35 with "history beyond the cap is trimmed; the run continues", and add one AC: past the cap, the root still sees its task and the map, and the oldest tool groups are gone.
  - (5) Have the resume prompt list finished cards by name, status and entry ids rather than pasting every full card.
  - This adds no new mechanism and keeps every FR and INV.

R-2 [Major] [L6/L9] §6.1 INV-19, §9.1 — The per-file cap also applies to `entries.jsonl` and `superseded.jsonl`, so memory becomes permanently read-only after about 250 entries, not the ~3,000 that §9.1 promises
  Evidence:
  - INV-19: "No tool write may leave … any file above `max_file_tokens` tokens".
  - Row 17: "`commit_entry` runs `check_entry`, then the caps".
  - §9.1: "At ~80 tokens per line, the 250,000-token default allows about 3,000 lines".
  - D-7 sets `max_file_tokens` = 20,000.
  Failure:
  - 20,000 / ~80 ≈ 250 live entries. Beyond that, every root `remember` returns a cap error and every pair commit drops all its entries with a cap reason.
  - After about 250 supersessions, `superseded.jsonl` is over the cap, so every `supersedes=` write is refused.
  - The workspace persists across runs (D-6), so this lasts until a human edits the files.
  - A 100-pair run, at up to 10 entries per pair, hits the limit around pair 25.
  Smallest fix:
  - Apply `max_file_tokens` to notes only; `max_tokens` alone bounds the three bookkeeping files.
  - Fix the §9.1 volume line.
  - Add one AC: an entry commits when `entries.jsonl` alone is above `max_file_tokens` but the workspace is under `max_tokens`.

R-3 [Major] [L1/L5] §8.1 D-9, §9.3 `loop`, §15 Q-5, §4 — The defaults never bound an agent, and one shared `loop` makes the root's clock include its children's time, so "runs until … budget caps are hit" does not hold
  Evidence:
  - D-9: "Spend is bounded by `max_agents` × the per-agent `loop` settings".
  - §9.3: the `loop` default is "`AgentLoopSettings()` (unbounded…)", and Q-5 defaults to No.
  - Every limit in `AgentLoopSettings.__init__` defaults to None (agents/settings/loop.py:50-66).
  - The option the user picked: "One command runs until done criteria or budget caps are hit".
  - §4 passes `loop=AgentLoopSettings(max_iterations=60, timeout_seconds=1800)`, which §9.3 applies to "every agent in the tree".
  Failure:
  - (a) Under the defaults, a generator that keeps retrying a failing bash command never calls `isDone`. Its pair never returns, so the root's `launch_subagent` never returns. The run neither finishes nor hits a cap, and spend is unbounded, because `max_agents` caps agent count, not iterations.
  - (b) Under the §4 settings, the root's 30-minute clock keeps running while it waits on pairs, and one pair alone can take 30 + 30 minutes. The root stops with `timeout`, `run_finished` is written, and `resume()` then refuses the run as finished. The root also gets only 60 iterations for a 10M-token task.
  Smallest fix:
  - Give `loop` a bounded default from named constants (`INFINITE_DEFAULT_MAX_ITERATIONS`; per-agent iteration limits are in the conversation's list F).
  - Correct D-9 to "spend ≤ `max_agents` × `max_iterations` model calls".
  - State in §9.3 and the README that a parent's `timeout_seconds` includes its children's time.
  - Remove `timeout_seconds` from the §4 snippet (AC-1).
  - Optional [scope-adding] Q-n: "Separate loop settings for the root and for children?" Default: not built.

R-4 [Major] [L4/L5] §9.2 `launch_subagent` row, §12.3 row 20 — `launch_subagent` is not marked internal, so tool limits in the shared `loop` time out or truncate whole pair batches
  Evidence:
  - §9.2 gives `launch_subagent` only "SAFE".
  - Precedent: `JevBulkWorkTool.spec()` sets `metadata={"internal": True}` (agents/jev/bulk_work.py).
  - The runtime exempts only internal tools from:
    - `tool_timeout_seconds` (runtime.py:1469-1476, `timeout = None if tool_is_internal …`);
    - `result_max_chars` truncation (runtime.py:1926-1931);
    - tool budgets and `allowed_tools` (runtime.py:1780-1783).
  - `settings.loop` applies to every agent.
  Failure:
  - A developer bounds bash with `ToolSettings(tool_timeout_seconds=300, result_max_chars=4000)`.
  - A batch that takes more than 300 s is cancelled by `asyncio.wait_for`. Every running pair dies, the journal keeps `pair_started` with no finish, and the root sees "timed out".
  - A 5-card result of about 16,000 characters is cut to 4,000, so the root never sees most of its cards.
  - `max_calls_per_tool` and `max_tool_calls` also count launches.
  Smallest fix:
  - The launch tool's `ToolSpec` carries `metadata={"internal": True}`, as `JevBulkWorkTool` does.
  - Add one INV: tool timeouts and result caps never apply to `launch_subagent`.
  - Add one AC for that INV.

R-5 [Major] [L5] §6.1 INV-29, §12.3 rows 4 and 20 — Only each agent's `arun` is guarded, so a failure while building the verifier, committing, or building the card escapes `ParallelPipeline` and loses every sibling's card
  Evidence:
  - Row 20: "Each agent's `arun` is wrapped in `try/except VidbyteSdkError`".
  - Row 17: "A malformed bookkeeping line raises `ToolExecutionError`". The verifier is built with a fresh map, so `map_text()` and `commit_entry` both read those files.
  - EC-24 already expects bash to leave malformed lines behind.
  - Row 4 validates "non-blank strings" without saying that `InfiniteResultCard.summary` and `review` may be empty, yet a FAILED pair (INV-29) has both empty.
  - `ParallelPipeline.run` is `asyncio.gather` without `return_exceptions` (pipelines/parallel.py:43).
  - The runtime turns the escaped exception into one `ToolResult.error` (`_run_tool_call`, `except Exception`).
  Failure:
  - Bash leaves half a line in `files.jsonl`. Pair `a`'s generator returns, and building its verifier calls `map_text()`, which raises `ToolExecutionError`. The error leaves `InfinitePair.run` and `gather` raises.
  - The root gets one error instead of N cards, which breaks INV-29 ("every sibling's card is still returned … does not raise").
  - The siblings keep running as orphan tasks whose cards nobody reads. When `asyncio.run` exits it cancels them, leaving `pair_started` with no `pair_finished`.
  - The same happens when `InfiniteResultCard` rejects a FAILED pair's blank summary.
  Smallest fix:
  - In row 20, one `try/except VidbyteSdkError` spans the whole stage after the generator returns (verifier build, commit, card build).
  - On error, the card is FAILED or UNCHECKED, carries the error text as its review, and lists the remaining staged entries in `dropped`.
  - In row 4, `summary` and `review` may be empty.

R-6 [Major] [L10/L9] §6.1 INV-6, §6.2 AC-28, §12.4 — AC-28 requires each child's extras to be a different object, but the chosen `AgentForker._clone_tool` returns ordinary tools unchanged
  Evidence:
  - AC-28: "both pair agents hold a `web_fetch` tool that is not the root's object".
  - INV-6 says "clones"; §12.4 says "never the root's objects".
  - The repo:
    - `_clone_tool` is documented as "preserving custom tools by identity". It returns `tool` unless the tool is a `_ToolWrapper`, has `clone_for_agent` or `clone_for_fork`, or rebinds a context manager (agents/fork.py:199-216).
    - `BaseTool.rebind_context_manager` returns `self` when `old is None` (tools/base.py:44-52).
  Failure:
  - The blind test author writes AC-28 with an ordinary `BaseTool`. The implementer follows row 20 exactly and the test fails.
  - Making it pass needs a deep copy that §12 does not contain, which is BLOCKED under §14.
  Smallest fix:
  - INV-6, AC-28 and §12.4 say: agent-bound SDK tools are cloned by `_clone_tool`; ordinary tools are shared by identity, as `JevBulkWorker` does.
  - AC-28 then asserts that both pair agents hold `web_fetch` and neither holds `calc`.

R-7 [Major] [L1] §8.1 D-20, §12.3 row 21, INV-7 — MCP servers the developer attaches never reach a subagent, even by name, against "you can add … any MCP server, or skills"
  Evidence:
  - Round 2: "Apart from these you can add any tool that they want, or any MCP server, or skills that they want". This is a settled decision.
  - Row 21: "extras = the developer tools in `settings.tools`".
  - INV-7 checks a card's tools against those extras.
  - `with_mcp_server(...)` bridges MCP tools into the agent's `self.tools` (agents/mixins.py:147; `_attach_tools` at 371-382), never into `settings.tools`, and the settings have no MCP field.
  Failure:
  - The developer attaches a browser MCP server; the root holds `browser_navigate`.
  - A card with `"tools": ["browser_navigate"]` rejects the whole batch (EC-6), because that name is not in the extras.
  - So no subagent can ever use an MCP server, and the closed settings surface offers no other route. The spec also never says how a skill reaches the tree.
  Smallest fix:
  - Build the launch tool's extras from the launching agent's live catalog, minus `INFINITE_RESERVED_TOOL_NAMES` and `isDone`. For the root that is the runtime's `user_tools`, read after `_ensure_mcp_connected`. MCP-bridged tools then become nameable exactly like `settings.tools`.
  - State in D-20 and the README that a skill reaches every agent as text in `system_prompt`, which every child inherits (row 20), or as a developer tool.
  - Remove "MCP" from Q-4.

R-8 [Major] [L8/L11] §11 Commands and Baseline, §12.4 — §11 says no type-check step exists, and it omits the lint ratchets that the journal and workspace code will hit
  Evidence:
  - §11: "Typecheck: N/A — no separate type-check step exists". The ceiling list omits S009, S041, S004 and S047.
  - The repo does run a type check inside lint:
    - lint/README.md:14: "Run pinned mypy once and ratchet every package type-contract error".
    - lint/README.md:90: "S009 … Package type errors may only decrease".
    - lint/mypy.ini sets `disallow_any_generics = True` and `check_untyped_defs = True`.
  - `lint/baseline.json` ceilings:

    | Rule | Ceiling | What it catches |
    |---|---|---|
    | S009 | 350 | mypy type errors |
    | S041 | 0 | PLW1514: `open` without `encoding` |
    | S004 | 1 | DTZ: naive `datetime` |
    | S047 | 0 | ASYNC230: `open` inside `async def` |

  Failure:
  - The journal and workspace code is new file I/O and timestamp code. Each of these breaks a ratchet with no headroom:
    - `open(path, "a")` with no encoding;
    - `datetime.now()` for run ids and `at` stamps;
    - a bare `list` annotation;
    - an `open` inside `async def execute`.
  - The gate fails with `AGENT-LINT: FAIL`. §12.4, which claims to list the rules that will fire, names none of these.
  Smallest fix:
  - §11 Typecheck becomes `python lint/run.py --rule S009` (pinned mypy, ceiling 350).
  - Add S009 = 350, S041 = 0, S004 = 1 and S047 = 0 to the ceiling list.
  - Add §12.4 lines:
    - every `open` passes `encoding="utf-8"`;
    - timestamps use `datetime.now(timezone.utc)`;
    - no `open()` directly in an `async def`; file I/O stays in the sync workspace and journal methods;
    - no bare generic annotations.

R-9 [Minor] [L8/L9/L11] §12.4 headers, §12.3 row 26, §12.6 P4 — The A001 checklist line forces six legacy headers to be rewritten, the base.py header goes stale, and P4 orders row 22 before the enum member it uses
  Evidence:
  - §12.4 says every "new or modified .py" carries all A001 fields, but row 26 says "Nothing else in the file changes".
  - Six modified files use legacy headers, by grep:
    - `base.py`, `registries/runtimes.py`, `toolsets/__init__.py`, `agents/__init__.py` and `vidbyte/__init__.py` have 0 of the 7 fields;
    - `agent_runtime.py` has 3 of 7.
  - base.py:12-14 says the trackers go to "the linear-loop runtimes (LINEAR and JEV)".
  - §12.6 orders "rows 20 → 21 → 22 → 23, then 24 – 26", but row 22 uses `AgentRuntimeType.INFINITE_MEMORY`, which row 24 adds.
  Failure:
  - Following §12.4 means rewriting six legacy headers, including base.py's (a 1,767-line file), which AGENTS.md calls out of scope ("Do not rewrite untouched code"). Not doing it fails the checklist.
  - The base.py header stays wrong.
  - A per-row commit of P4 imports a missing enum member.
  Smallest fix:
  - Apply the A001 line to new files only. In modified files, update just the lines that name changed facts; row 26 also edits base.py:12-14 to add INFINITE_MEMORY.
  - Move row 24 ahead of row 22.

R-10 [Minor] [L8] §12.5, §14 — `vidbyte/tools/README.md` documents the toolsets folder but is not in §12.3, and §14 bars touching it
  Evidence:
  - vidbyte/tools/README.md:91: "`toolsets/`: pre-assembled tool catalogs, including `CodingAgentTools` …". The toolsets folder has no README of its own.
  - §14: "touching any file not in §12.3" is ask-first.
  Failure: a reviewer asks for the new catalog to be named there, and the implementer is BLOCKED.
  Smallest fix: add a §12.3 MODIFY row that adds one clause naming `InfiniteMemoryAgentTools` on line 91.

R-11 [Minor] [L1] §6.1 INV-19, §8.1 D-26 — The user's own "compaction for file policy" is cut from the weighted-word quote and deferred by a D- instead of a Q-
  Evidence:
  - The §D weighted word: "impose file limits (total files, max file length, compaction for file policy)".
  - INV-19 quotes it as "(total files, max file length, …)".
  - D-26 defers it citing request §C, but the phrase is the user's own (Prompt 4), not an assistant suggestion.
  Failure: a user-named item is silently decided against, and the elided quote reads as if it were covered.
  Smallest fix:
  - Quote the weighted word in full.
  - Add Q-8: "Add a compaction-for-file policy (e.g. consolidate a note nearing `max_file_tokens`)?" Default: not built.

R-12 [Minor] [L5] §6.3 EC-26, EC-30 — Two edge cases understate the damage: a second process loses entries, and a crash after commit re-commits a pair's memories
  Evidence:
  - EC-30 says only "pairs may run twice and journal lines interleave".
  - §9.1: a supersede rewrites `entries.jsonl` atomically (temp file + `os.replace`).
  - INV-24: the next id is max + 1 under an in-process lock only.
  - Row 20 commits first, then writes `pair_finished`.
  Failure:
  - Process B appends entry #40 while process A rewrites `entries.jsonl`; A's `os.replace` silently erases #40.
  - Two processes can mint the same id, so `supersedes=40` becomes ambiguous.
  - A crash between commit and `pair_finished` re-runs the pair on resume. Only exact duplicates are rejected, so it commits near-duplicate entries and re-appends its notes.
  Smallest fix:
  - Restate EC-30 as lost entries and duplicate ids.
  - Add an EC for the window between commit and `pair_finished`.
  - Put both in the README's Notes for agents. Q-7 stays.

R-13 [Minor] [L5] §12.3 row 3 `INFINITE_VERDICT_PATTERN`, INV-14 — The verdict pattern rejects common Markdown, so a correct verifier loses all its memories
  Evidence:
  - `INFINITE_VERDICT_PATTERN = r"(?im)^\s*VERDICT:\s*(passed|fixed|failed)\s*$"`.
  - INV-15 drops every staged entry on UNCHECKED.
  Failure: a verifier ending in `**VERDICT: passed**`, `VERDICT: **passed**` or `VERDICT: passed.` matches nothing, the verdict becomes UNCHECKED, and every verified entry is discarded.
  Smallest fix:
  - Allow `*`, `_` and backticks around the keyword and value, plus a trailing period, e.g. ``(?im)^[\s*_`]*VERDICT[\s*_`]*:[\s*_`]*(passed|fixed|failed)[\s*_`.]*$``.
  - Add the bold form to EC-13.

R-14 [Minor] [L2] §8.3, D-4, INV-26 and EC-5 — The smaller memory-write design is never weighed, and the "running key" guard is unreachable
  Evidence:
  - §8.3 rejects only the bulk-work clone. D-4's runner-up is the larger "journal staged entries" design.
  - Request §C's open question "Staged commits vs writing entries flagged 'unverified'?" was never answered by the user.
  - INV-26 and EC-5 reject a key "currently running … from another call in the same model turn". But:
    - one agent's tool calls run sequentially (runtime.py:607-608, `for … in enumerate(tool_calls): … await self._process_tool_call`);
    - keys are prefixed by the launching agent's key, so no in-process call can meet a running key.
  Failure:
  - Staging costs `InfiniteStagedEntry`, `drop_entry` (plus 2 prompt leaves), the commit re-check, `dropped`, INV-15/16 and AC-9–11.
  - "Commit at once, and the verifier corrects with `remember(supersedes=…)`" would meet every user-required item with less code, and the spec never says why it lost.
  - The `running` set and EC-5's second clause are code and tests for a state that cannot occur.
  Smallest fix:
  - Add the commit-at-once design to §8.3 with the concrete reason staging wins (siblings see unverified entries; FAILED or UNCHECKED work is kept), or adopt it.
  - Drop the `running` set and EC-5's second clause; D-23 already covers the cross-process case.

R-15 [Minor] [L4] §9.2 prompt leaves — The seven task-card fields carry no model-facing descriptions
  Evidence:
  - §9.2 has only `launch_tool_description` and `launch_tasks_description`. The item fields get no descriptions: `name`, `goal`, `done_criteria`, `generator_prompt`, `verifier_prompt`, `context`, `tools`.
  - Field guide `model-facing-tool-contracts.md`: "give the tool and every parameter a consistent 4–5 sentence general description".
  Failure: the fields that decide what each pair does (checkable criteria, what the verifier must check, `#N` context ids) are undocumented in the schema the model fills, and a reviewer applying the field guide flags it.
  Smallest fix:
  - Add seven `launch_<field>_description` leaves and use them as the item property descriptions. That makes 40 leaves, and the header becomes 138 assets.
  - Alternatively, state that the `.md` tool description covers each field.

VERIFIED CLAIMS
- Held: `_LINEAR_LOOP_RUNTIMES = frozenset({LINEAR, JEV})` at vidbyte/agents/base.py:78.
- Held: `JevRuntime.__init__` refuses with "The 'jev' runtime is only available through JevAgent…" (jev/runtime.py:59-74). `_offer_bulk_work` (171-180) uses `self.tools.add`, `run_options.pop("tools")` and `replace(context, tools=…)`.
- Held: `RuntimeRegistry.resolve` lazily imports `from vidbyte.agents.jev import JevRuntime` through the facade (registries/runtimes.py:33).
- Held: `_after_tool_iteration` is defined at runtime.py:916 and called at 696. `_adopt_agent_catalog` keeps runtime-added tools.
- Held: `call_options.setdefault("system", system)` at runtime.py:1561. `_build_system_string` renders the primitives zone on every call.
- Held: `ContextManager.copy()` and `upsert(item, placement=…)` mutate and return self. `TextContextItem(title, content, primitive_id=…)` exists.
- Held: `generate_reply` (base.py:814-845) merges nested usage into the parent once, in `finally`.
- Held: `_runtime()` builds a fresh runtime on each call. It is called from both `_build_context` (1226) and `_run_direct` (1263), so run-bound tools cannot leak across runs.
- Held: `Session.__init__` refuses agents with `session_persistence_supported=False` (session.py:102). The Codex and multi agents opt out.
- Held: 98 `Prompt` members and 33 family JSON files, so 131 assets and 34 families after the change.
- Held: the `text.py` header says "Add another general text helper as a @staticmethod here". Three chars/4 copies exist (runtime.py:2106, strategies.py:52, trace_render.py:149).
- Held: `GrepTool` has the fixed name "grep" and `ignore_patterns` match path parts. `ReadLinesTool(FileSystemToolConfig)` exists. `IS_DONE_TOOL_NAME = "isDone"`, the only internal tool added.
- Held: the `_runner_for_model` patch seam at test_jev_bulk_work.py:186-193. `tests/test_jev_compute_situations.py:255` `_call` and `tests/test_jev_agent.py:441-450` exist.
- Held: `generate-sdk-public-api.py` refuses to write while its inputs differ from HEAD. The root package exports enums explicitly, so P1 cannot trip C016.
- Held: the README sizes (agents 22,296 chars; prompts 27,678 chars). `llms.txt` and `artifacts/file_index.md` do not list JevAgent or CodingAgent. The REPO_MAP toolsets entry drifts ("currently holds one such bundle").
- Held: the §12.3 counts match §8.4 (18 CREATE, 14 MODIFY).
- Held: the listed `lint/baseline.json` ceilings.
- FALSE: "Typecheck: N/A". Lint S009 runs pinned mypy with a ceiling of 350. The ceiling list also omits S041 = 0, S004 = 1 and S047 = 0 (R-8).
- FALSE: INV-6/AC-28 say `_clone_tool(tool, None, None)` clones extras. It returns ordinary tools by identity (R-6).
- PARTLY FALSE: D-19 "adding [compaction] adds a knob". `BaseAgent(middleware=…)` plus the exported `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries` can be wired by default with no settings field (R-1).
- Undermines D-9: `AgentLoopSettings()` defaults every limit to None (R-3).
- Missing from the spec: an `internal` tool's `metadata` exempts it from tool timeouts, result truncation and budgets (runtime.py:1405-1414, 1469-1476, 1780-1783, 1926-1931). The spec never sets it (R-4).
- Makes EC-5 unreachable: one agent's tool calls run sequentially (runtime.py:607-608), see R-14.
