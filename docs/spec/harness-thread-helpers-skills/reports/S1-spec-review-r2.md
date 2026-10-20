VERDICT: SOUND WITH FIXES. r2 fixes 13 of the 14 round-1 findings. The one it does not fix, R-10, is replaced by a new design that the installed vendor binary rules out. One Blocker remains: opencode get and lineage (D-26) are built on a list that never contains a child session and never carries `parentID`. There are also four other wrong vendor facts and error texts, and one over-broad refusal, each verified against the vendor's binary or docs.

Method note. The opencode facts below come from reading the strings of the compiled CLI bundle (`C:/Users/422mi/scoop/apps/opencode/1.18.31/opencode.exe`, the version the spec targets). No opencode process was started, and no user session data was read. The Grok facts come from `~/.grok/docs/user-guide/`, `~/.grok/bundled/` and the strings of `~/.grok/bin/grok.exe` (1.0.52). The Muse facts come from `msp.schema.json`.

WHAT THE SPEC GETS RIGHT
- **D-29's minted `--session-id` is correct and documented.**
  - 14-headless-mode.md:364 shows `grok -p "hello" --session-id "$(uuidgen …)" --output-format json`, and the binary checks the value ("--session-id must be a valid UUID (got '…')").
  - If A-25 were false, grok's argument parser would refuse the flag before any model call. That surfaces loudly as `grok.run_failed` and costs nothing.
  - EC-50 now hands back an id the caller can use.
- **D-27's one-id reads and the directories-only scan match the real store.**
  - On this machine `~/.grok/sessions/` holds only `session_search.sqlite` (17-sessions.md:416).
  - A sibling thread's bad `summary.json` can no longer fail a paid run's evidence check (EC-66, EC-68, AC-27, AC-28).
- **D-28 is a sound proof for a skill that leaves no tool trace.**
  - The fragment appears verbatim at `~/.grok/bundled/skills/code-review/SKILL.md:17`.
  - The skill's description (line 3) says only "a deep code quality audit or…", so the fragment cannot come from the skill listing.
  - The function takes no text, the check fails closed, and A-27 has a probe.
- **The Muse shapes and the counts are exact.**
  - `forkedFrom` is `ForkProvenance {commandId, cutCursor, cutExplicit, sessionId}`, all required. `session/list` has a maximum of 200 (default 50), sorts by `updatedAt` descending, and returns `nextCursor`. `-32601` and `-32020` are handled as the spec says.
  - The counts agree: 22 + 25 = 47 functions; 17 + 47 + 4 = 68 exports, split 25/15/16; 20 classes; 10 new files; FailureCode grows from 148 to 152.

ROUND-1 RESOLUTION CHECK
- R-1: resolved. Rows 14, 20 and 26 and the new §12.4 line forbid flow-to-flow calls. One residual leaf rule for `GrokHelperRun.export` is in R-22.
- R-2: resolved. §9.2, row 11, EC-66 and AC-27 now treat only directories as groups and session candidates.
- R-3: resolved. The §9.1 rule, the §12.4 C002 line and row 19's single converter cover it. `require_int` and `require_bool` are at validation.py:85 and :92, and C002 is blocking with a baseline of 9.
- R-4: resolved. FR-12, D-28, A-24, A-27 and AC-30 were added, and 04-slash-commands.md:275-277 and 26-config-reference.md:290 were verified. A residual false-negative path, skill shadowing, is in R-20.
- R-5: resolved in substance (rule 9, D-30, T-8, EC-42, EC-69, EC-70, EC-71). The refusal now reaches too far; see R-19.
- R-6: resolved (INV-29, D-29, AC-29, A-25). One wording residual is in R-23.
- R-7: resolved (D-27, the INV-6 scope bullet, EC-68, AC-28).
- R-8: resolved. Probe (a) now calls the SDK functions themselves, adds a negative control, and A-26 was added.
- R-9: resolved (EC-67, D-31, and the rewritten preamble). Note that A-12, one of the four assumptions the preamble calls silent if wrong, is now verified false (R-15, R-16).
- R-10: **not resolved.** r2 replaces export-per-step with "one `session list` and walk `parentID`". In opencode 1.18.31 that list holds root sessions only, and its rows have no `parentID` field. See R-15.
- R-11: resolved. INV-26 now allows text changes per FR-17 and D-20. R-18 needs one more such exception.
- R-12: resolved. `init_muse_workspace` moved to `MuseThreadHelpers`, and `search_text` is now a tuple.
- R-13: resolved. Row 35 names lines 193 and 195, and §13 and row 37 require `forkedFrom` as an object.
- R-14: resolved (EC-72, row 33, Q-7). For opencode, child sessions never appear in the list at all, because it lists roots only.

FINDINGS

R-15 [Blocker] [L5] §8.1 D-26 / §9.2 opencode get+lineage / AC-31 / A-12 / A-22 — opencode get and lineage read a list that never holds a child session and never carries `parentID`
  Evidence:
  - What the spec says:
    - D-26: "A-12: the list rows already carry `id`, `title`, `created`, `updated`, `directory` and `parentID` … walk `parentID` in memory".
    - AC-31: "on a chain of depth 3 … each call starts exactly one `opencode session list` child and no `export` child".
    - §9.1: "the row's `parentID` if present".
  - The list command in the 1.18.31 bundle:
    - The handler is `E.list({roots:!0,limit:D.maxCount})`.
    - The project lister `gQ` adds `A5(u.parent_id)` (that is, `parent_id IS NULL`) when `roots` is set.
    - The JSON writer is `u9(D){…({id:F.id,title:F.title,updated:F.time.updated,created:F.time.created,projectId:F.projectID,directory:F.directory})}`. It has no `parentID`, which matches the row shape request.md:232 verified.
  - Forks: `Session.fork` creates the new session with `{directory, path, workspaceID, title:NQ(…), metadata}` and no `parentID`. Only `Session.create({parentID})`, which subagent children use, sets one. This also settles A-22: forks record no parent.
  - Export: `opencode export` writes `B={info:C,messages:E}`, where `C` is the full session record including `parentID`. An unknown id prints `Session not found: <id>`.
  Failure:
  - `get_opencode_thread_lineage(<any listed id>)` always returns a 1-element chain, and raises no error.
  - `get_opencode_thread(<subagent child id>)` raises `opencode.thread_not_found` for a session that exists, while `read_opencode_thread` of the same id succeeds.
  - S2 will write AC-6 and AC-31 against a fake whose list rows carry `parentID` and children. The suite then passes while production lineage is meaningless.
  - D-26's own flip condition ("`session list` stops listing child or forked sessions") is already true.
  Smallest fix:
  - Reverse D-26 for get and lineage. Read one session by id from a source that returns non-root sessions together with their `parentID`. Two options are verified:
    - (a) The mechanism the user accepted (request.md:236): `opencode db "<constant SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '<id>'>" --format json`. It runs in-process (`instance:!1`, `C.all(k1.raw(u))`, no sqlite3 binary needed). It is injection-safe, because `NATIVE_THREAD_ID_PATTERN` admits no quote character.
    - (b) r1's `opencode export <id>` `info` block, accepting R-10's cost for very long threads.
  - Rewrite AC-31, the §9.1 opencode `parent_thread_id` mapping, NFR-12 and row 20.
  - Restate A-12 and A-22 as verified facts.
  - Add one README sentence: "opencode lineage shows subagent nesting only; a thread made by `fork_opencode_thread` is its own root."
  - In §13, tell S2 that the fake `session list` lists roots only and emits no `parentID`.

R-16 [Major] [L6] §8.1 D-19 / §9.2 opencode list rows / A-12 — `opencode session list` without `-n` stops at the project's 100 newest root sessions, so lists, windows and searches are silently cut short
  Evidence:
  - D-19: "runs `opencode session list --format=json` with no `--max-count` … A count cap before filtering could hide this workspace's threads". A-12: "lists every session without `--max-count`".
  - In the 1.18.31 bundle, `gQ` does `let Y=$.limit??100;return Q.select().from(u).where(T0(...K)).orderBy(r0(u.time_updated)).limit(Y)`. The filter `K` holds only `project_id`, because the CLI passes no `directory`.
  Failure:
  - In a project with 300 root sessions, `list_opencode_threads(ws, limit=150)` returns at most 100.
  - `list_opencode_threads_since(ws, timedelta(days=30))` silently drops in-window threads that are older than the project's 100th newest.
  - A workspace that is a subfolder, whose threads are all older than that, gets `()`.
  - `search_opencode_threads` misses the same threads.
  - None of this raises an error. It is the silent wrong answer that R-9 removed for Grok.
  Smallest fix:
  - Always pass `--max-count=NATIVE_OPENCODE_SCAN_MAX` (the constant D-19's flip condition already names). Size it so the JSON stays well under `NATIVE_PROCESS_MAX_OUTPUT_BYTES`; for example, 10,000 rows is about 3 MB.
  - Add an EC: when the child returns exactly that many rows, raise a loud error that names the cap (for example `opencode.protocol_mismatch`), never a short list.
  - Restate A-12: roots only, a default of 100, and project-wide.

R-17 [Major] [L1] §15 A-15 / §12.3 row 4 `OPENCODE_COMMAND_NOT_FOUND_TEXT` / D-8 / EC-52 — opencode 1.18.31 does not print the unknown-command text the spec matches, so `opencode.command_not_run` never fires
  Evidence:
  - The spec: row 4 has `OPENCODE_COMMAND_NOT_FOUND_TEXT = 'Command "{command}" not found'`, and A-15 says opencode prints `Command "<unknown>" not found`.
  - The bundle: `SessionPrompt.command` throws `new Ee.Unknown({message:\`Command not found: "${t.command}".${I}\`})`, where `I` is `" Available commands: a, b, …"`. The run handler then emits `Z("error",{error:B.error})` and sets `process.exitCode=1`.
  Failure:
  - `run_opencode_command("no-such", …)` finds no marker, so `OpencodeWire.read` falls through to its generic error-event path and raises `opencode.run_failed`.
  - FR-15, AC-16 and EC-52 fail against the real CLI, while S2's fake, built from the spec's text, passes.
  - A-15's "if wrong" line ("would run as plain text undetected") is also wrong: the failure is loud, just coded wrongly.
  Smallest fix:
  - Set `OPENCODE_COMMAND_NOT_FOUND_TEXT = 'Command not found: "{command}"'` as a prefix match, because the "Available commands" tail varies. Match it in the error event's `data.message` and in stderr.
  - Rewrite A-15 as verified: an `UnknownError` event, then exit 1.
  - Tell S2 in §13 to make the fake print exactly this text.

R-18 [Major] [L5] FR-17 / §12.3 row 4 / §12.4 error texts / D-14 / INV-16 — helpers and streaming runs reuse #1036's run-only texts, so `timed_out` and `output_too_large` advise steps that cannot help
  Evidence:
  - FR-17 and row 4 widen only the `THREAD_NOT_FOUND` texts.
  - The next steps for `GROK_TIMED_OUT`, `OPENCODE_TIMED_OUT` and `MUSE_TIMED_OUT` (`vidbyte/lib/constants/native_threads.py:426`, `:435`, `:444`) say "Raise …ThreadConfig.timeout_seconds …". D-14 says a helper's "`timeout_seconds` and run options are ignored".
  - The likely cause for `GROK_OUTPUT_TOO_LARGE` (`:391`) is "Grok printed more than GROK_CLI_MAX_OUTPUT_BYTES, so its one JSON answer could not be read whole". INV-16 moves Grok command runs and `grok export` to `NATIVE_PROCESS_MAX_OUTPUT_BYTES`.
  - All three `*_OUTPUT_TOO_LARGE` next steps (`:427`, `:436`, `:445`) say "Ask for a shorter answer". A transcript export (EC-22) cannot be made shorter.
  - `NativeErrorFactory` picks these texts per code, not per operation.
  Failure:
  - `read_grok_thread` exceeds 30 s and tells the caller to raise `GrokThreadConfig.timeout_seconds`. The caller does, and the call times out again (D-14).
  - The same happens to the code-review export after a paid run (EC-73).
  - A 70 MiB opencode transcript says "Ask for a shorter answer".
  - So G-3 ("likely cause and next step say what to do") and KD-9 ("error messages need to be in much more detail") are not met.
  Smallest fix:
  - Extend FR-17 and row 4 to widen the `TIMED_OUT` and `OUTPUT_TOO_LARGE` likely cause and next step for all three harnesses. The new texts should cover:
    - helper children, which are bound by the fixed `NATIVE_CONTROL_TIMEOUT_SECONDS` that `config` does not change;
    - a transcript over `NATIVE_PROCESS_MAX_OUTPUT_BYTES`, which cannot be returned whole (the caller can export it with the vendor CLI instead);
    - the Grok stream cap, naming both caps.
  - Keep every text unique within its harness.
  - Name these texts in INV-26's exception and in the §12.4 error-text list. No code path changes.

R-19 [Major] [L1] §9.1 rule 9 / D-30 / INV-9 / EC-70 / AC-12 — the flag-token refusal applies all eight flags to every named wrapper, so ordinary coding requests that mention a CLI flag are refused
  Evidence:
  - Rule 9: "When `named` is `True` (every named wrapper…) … `text` has no whitespace-separated token that equals a `GrokCommandFlag` value". `GrokCommandFlag` holds `--budget`, `--effort`, `--concurrency`, `--dry-run`, `--auto-pr`, `--local`, `--branch` and `--pr`.
  - The bundled argument hints (verified):
    - goal: `<objective> [--budget <tokens>]` (04-slash-commands.md:328);
    - implement: `[--effort N] <description>`;
    - design, resume-claude, resume-codex, resume-cursor and imagine take no options;
    - review and execute-plan take no free text in this API, and `design_doc` may hold no whitespace.
  Failure:
  - Each of these raises `configuration.invalid_argument`, although none of the commands reads those tokens as options:
    - `run_grok_implement("Add a --dry-run flag to scripts/deploy.py")`;
    - `run_grok_design("Design --local and --branch modes for our CLI")`;
    - `run_grok_resume_claude("the session where we fixed --pr parsing")`.
  - Text that names a CLI flag is normal input for a coding agent, and the only way around the refusal is the raw `run_grok_command`.
  Smallest fix:
  - Make the refused set per command: `GROK_TEXT_OPTION_FLAGS: MappingProxyType[GrokCommand, tuple[GrokCommandFlag, ...]]`, with `GOAL → (BUDGET,)`, `IMPLEMENT → (EFFORT,)` and an empty tuple for every other command. Rule 9 checks only that command's set.
  - T-8 keeps its full protection: `--auto-pr`, `--concurrency` and `--dry-run` matter only to execute-plan, and its line carries no caller text.
  - Adjust EC-70 and AC-12's examples to match.

R-20 [Major] [L5] D-4 / §9.2 evidence / EC-63 / §12.4 `grok.command_not_run` texts — a same-named workspace, user or caller skill replaces the bundled one, so a paid run raises `command_not_run` with a cause that blames slash expansion
  Evidence:
  - 08-skills.md:213: "A same-named local, repo, or user skill overrides the bundled copy."
  - 08-skills.md:17-29 lists `./.claude/skills` and `./.claude/commands` (flat `*.md` files become slash commands), `./.grok/…`, `.agents/skills` at each tier, and `~/.claude/skills`.
  - EC-63 says the private home still loads `~/.claude`.
  - #1036 copies the caller's `skills=` folders into the private home's skills folder (`grok/threads.py:_prepare_home` → `NativeSkillFolders.replace`), which is the user tier.
  - Every Grok evidence marker is bundled-only: `shared/personas/*.md`, `shared/resume-session/CORE.md` and `GROK_CODE_REVIEW_FRAGMENT`.
  - The §12.4 cause for `grok.command_not_run` says "-p did not expand the slash command … or the skill left no trace".
  Failure:
  - A workspace with `.claude/commands/review.md`, a common Claude Code setup, makes `run_grok_review` run the user's own `review`. No persona is read, so the call raises `grok.command_not_run` after a paid run. Its message sends the caller to check the Grok release.
  - `skills=[…/design]` does the same to `run_grok_design`.
  Smallest fix:
  - Add an EC for skill shadowing.
  - Extend the `grok.command_not_run` likely cause with: "a same-named skill or command in the workspace (`.grok`, `.claude`, `.agents`, `.cursor`), in `~/.claude` or `~/.grok`, or passed in `skills=` replaced the bundled one". Extend the next step with: "run `grok inspect --json` and look for `collidesWith`".
  - Add one README sentence.
  - Refuse a `skills=` entry whose folder name equals the command's skill name (field `skills[i]`). That closes the SDK's own path to the shadow.
  - Q-n [scope-adding]: run a `grok inspect` pre-flight before each command run? Default: no.

R-21 [Minor] [L9] §5, §9.1, §12.6, §15 — r1 leftovers and gaps in order and scope around the r2 changes
  Evidence and fix, one line each:
  - §12.6 P5 still says "Ships: all 23 command and skill functions"; it should say 25.
  - A-13's "if wrong" line says "the get and lineage helpers raise protocol_mismatch", but in r2 only `read` uses export.
  - §9.1 still maps the opencode parent from "the row's `parentID` if present / `info.parentID`", and list rows never carry it (R-15).
  - In the §5 diagram, node G1 routes every Grok store read through `GrokStore.threads`, but D-27 adds `GrokStore.thread`.
  - A-1 cites `17-sessions.md:20-42` for the `summary.json` members. That range is the layout; the member list is at :420-431, which also documents `info` and says `agent_name` is persisted for "named agents … only".
  - Row 15 depends on rows 11 (`GrokStore.thread`) and 14 (`GrokHelperRun.export`), so Grok's P5 work cannot run in parallel with P4 as "(P4, P5)" says. Add that dependency.
  - `GrokStore.thread` accepts a `NativeThreadRequest` and reads "the groups in scope", but that record has no scope. State that it uses SDK scope: every group of the run's private home.
  Failure: S2 and S3 get instructions that contradict each other or are out of date.

R-22 [Minor] [L4] §12.3 row 14 / §8.5 `GrokHelperRun.export` — `export` is both `read`'s helper and a cross-class entry point, so it must call nothing else in its class, and the spec does not say how it builds its child
  Evidence:
  - Row 14: "`read` calls `GrokStore.thread`, then `export`". `delete` also needs the same keyless child: the environment, `env_remove`, the control timeout and the cap.
  - Row 20 gives opencode a shared private `_child`. Copying that shape here gives `read → export → _child`, the two-deep chain that was a Blocker in round 1 (R-1).
  Failure: The natural refactor breaks AGENTS.md principle 1 again, in a module the §12.4 line does not obviously cover.
  Smallest fix: Row 14 should say that `export` and `delete` each build their `CliInvocation` inline or through a lower class (for example `GrokHome.helper_environment(home)`), and that `export` calls no other `GrokHelperRun` method.

R-23 [Minor] [L5] INV-29 / AC-29 — every post-launch error carries the minted id, even when Grok fails before it creates the session
  Evidence:
  - INV-29: "Every error raised after the child started carries that id".
  - 14-headless-mode.md: "Once the session has started, the error object also carries `cwd`", so some errors come before any session exists.
  - The binary refuses a bad flag value before any session is created, and "Couldn't start session: …" is a documented error.
  Failure: After `grok.key_rejected` or a pre-session `run_failed`, a caller that cleans up with `delete_grok_thread(error.thread_id, ws)` gets `grok.thread_not_found`.
  Smallest fix: INV-29 should say the id is the one the run asked Grok to use. The thread is known to exist only after an `end` or `tool_call` event, or for `command_not_run`, `timed_out` and `output_too_large`. In other cases the error's detail sentence should say "the thread may not exist".

R-24 [Minor] [L4] D-25 / INV-3 — on Windows the built prompt can be refused under the name `prompt`, which no skill function has
  Evidence:
  - D-25 caps the text by characters only: `NATIVE_COMMAND_TEXT_MAX_CHARS` = 24,000 − 1,024.
  - On win32, for Grok and Muse, `NativeThreadRequest.__post_init__` then runs `require_command_line_units(self.prompt, "prompt", max_units=NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS)`, with a limit of 30,000 (`vidbyte/lib/dataclasses/native_threads.py`).
  Failure: Suppose `run_grok_goal(json.dumps(spec))` gets a text of about 20,000 characters, 40 % of them double quotes. It passes D-25, but quoting each `"` as `\"` takes it past 30,000 UTF-16 units. The call then raises `configuration.invalid_argument` naming `prompt`, which breaks INV-3. CI runs only on Linux, so no test catches it.
  Smallest fix: D-25 also runs `require_command_line_units` on the text under its public name, with a units budget reduced by `NATIVE_COMMAND_RESERVED_CHARS`.

R-25 [Minor] [L5] §12.3 row 25 `MuseSessionWire.tool_calls` (outside r2's changes) — in `anchoredSnapshot` mode the items start at a compaction boundary, so the early `read_skill` call is gone
  Evidence:
  - msp.schema.json `SnapshotAnchor`: "The compaction boundary an anchored snapshot is anchored at". `ViewSnapshot.anchor` is "Present exactly when `history.mode` is `anchoredSnapshot`".
  - Row 25 reads `history.snapshot.state.items` in that mode.
  - `muse exec` compacts automatically (code-map §4.5, `--context-compaction-strategy`), and a skill's `read_skill` call comes first in the run.
  Failure: A long `run_muse_scaffold` or `run_muse_browser_app` run that compacted raises `muse.command_not_run`, although the skill was used. The check fails closed, but it fails on exactly the longest, most expensive runs.
  Smallest fix: In `anchoredSnapshot` mode, read the evidence from `muse export --session <id> --out <temp>` instead. That is D-17's existing child, and its output includes tool calls. Alternatively, add an EC and a `muse.command_not_run` cause that names compaction.

VERIFIED CLAIMS
Grok:
- A-25: `--session-id` combines with `-p`/`--single`. **HELD.** 14-headless-mode.md:25, :354 and :364 (`grok -p "hello" --session-id … --output-format json`); the binary says "--session-id must be a valid UUID".
- A-8, streaming-json: `tool_call` carries `toolName` and `rawInput`, `end.sessionId` exists, and `end` is always last. **HELD** (14-headless-mode.md:227-262). Two more facts:
  - `rawInput` is a JSON object, so `NativeToolCall.arguments` must serialize it.
  - The event list is documented as non-exhaustive (`thought`, `usage`, `plan`, `available_commands`, `max_turns_reached`, `auto_compact_*`). Readers must ignore unknown types, as `OpencodeWire` already does.
- `summary.json` members. **HELD**, but they are listed at 17-sessions.md:420-431, not at :20-42 (R-21). That list adds `info` (the session id and working directory) and says `agent_name` is kept only for "named agents".
- The store holds non-session files. **HELD.** `~/.grok/sessions/` here contains only `session_search.sqlite` (17-sessions.md:416).
- `/imagine-video` animates with `image_to_video` (04-slash-commands.md:275-277), and `features.video_gen` exists (26-config-reference.md:290). **HELD.** No default value is documented, which A-24 already says.
- `/goal` takes `<objective> [--budget]` and reserves status, pause, resume and clear (04-slash-commands.md:328). `GROK_WORKFLOWS=0` selects the `update_goal` driver, and `GROK_GOAL` is on by default (05-configuration.md:787-788). **HELD.**
- The code-review fragment is at SKILL.md:17, and the skill has `disable-model-invocation: true`. **HELD.**
- Persona reads: implement and review read `<skill dir>/../shared/personas/<name>.md` with `read_file` in the main agent (implement SKILL.md:51-57, review :17-25). **HELD.** The substring still matches after slash normalization.
- Bundled agents `plan.md` and `explore.md` exist. **HELD.**
- A same-named local, repo or user skill overrides the bundled copy (08-skills.md:213). **NEW**, see R-20.
- The execute-plan argument hint also has `--resume`, `--instructions` and `--no-graphite`. **HELD** that this is harmless: `design_doc` is a single token, so none of them can be injected.

opencode (1.18.31 bundle):
- `session list --format json` rows are exactly `{id, title, updated, created, projectId, directory}`, and the list is roots only. **D-26 and A-12 are FALSE** (R-15).
- `Session.fork` sets no `parentID`. **A-22 is settled: forks record no parent.**
- Without `-n`, `session list` returns at most 100 rows across the project. **A-12 and D-19 are FALSE** (R-16).
- `export` writes `{info: <full session>, messages}`; an unknown id prints `Session not found: <id>`. **A-13 HELD.** `session delete` prints the same not-found text. **A-14 HELD.**
- `db "<sql>" --format json` runs in-process and is not tied to a project. **NEW.** request.md:236's mechanism is viable.
- An unknown `--command` prints `Command not found: "<name>". Available commands: …` and exits 1. **A-15's text is FALSE** (R-17).
- With `--command`, the arguments are the message plus stdin, and an empty stdin is allowed. **HELD** (D-8, AC-16).

Muse (`msp.schema.json`):
- `session/list` takes `cursor`, `limit` (maximum 200, default 50), `updatedAfter` ("after", strict) and `workspaceRoot` (exact match), and returns `{nextCursor, sessions}` ordered by `updatedAt` descending. **HELD.**
- `session/read`: `excludeItems` defaults to true; with `false`, the folded items are returned. **HELD.**
- `Session.forkedFrom` is a `ForkProvenance` object with a required `sessionId`. **HELD** (§9.1, row 37).
- `Item.args` is the model's argument JSON, verbatim, and `ItemKind` includes `toolCall`. **HELD.**
- `HistoryNoneReason` includes `historyBudget`. **HELD** (EC-56).
- `anchoredSnapshot` starts at a compaction boundary. **NEW**, see R-25.

Repository:
- `require_int(value, field, *, minimum, maximum)` and `require_bool` are at `validation.py:85` and `:92`. **HELD.**
- C002 matches only `isinstance(x, bool)` with a bare `bool`, is blocking, and has a baseline of 9; S052 has a baseline of 0. **HELD.**
- `FailureCode` has 148 members ending at `MUSE_WSL_UNAVAILABLE`. Surface test line 193 (`== 120`) and line 195 are stale. `fake_harness.py:562` returns `forkedFrom` as a string. The static policy allows only the literals `""`, `0` and `1`. **All HELD.**
- `lib/enums/__init__.py` has the native import block at lines 111-126 and `__all__` at line 172. `harnesses/README.md` is 10,972 characters, and line 178 is the native bullet. **HELD.**
- `NativeThreadError` exposes `failure_code`, `next_step` and `thread_id`, as the §4 snippet uses. **HELD.**
- The existing `TIMED_OUT` and `OUTPUT_TOO_LARGE` likely-cause and next-step texts are written for #1036's runs only (constants:390-445). **NEW**, see R-18.
- `NativeThreadRequest` checks Windows command-line units under the name `prompt`. **NEW**, see R-24.
- Native `FailureCode` members appear only in `failure.py`, the native constants and the tests, and no vocabulary script requires each code to be documented. **HELD:** rows 3, 4, 35 and 36 cover every place a new code must be registered.
