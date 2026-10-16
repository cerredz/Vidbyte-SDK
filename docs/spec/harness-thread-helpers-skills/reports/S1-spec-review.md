VERDICT: SOUND WITH FIXES — The architecture, surface and evidence design are right and fit #1036. Before building, fix one AGENTS.md call-depth violation, a Grok store scan that breaks on files Grok itself keeps in the store, a C002 gate risk, slash-line argument injection, and an exclusion (NG-5) that rests on false vendor facts.

WHAT THE SPEC GETS RIGHT
- The evidence fails closed and comes from the run's own record (D-4, INV-8). `command_not_run` carries the new thread id. A-7's failure is loud (EC-41), and `GROK_WORKFLOWS=0` is the documented in-turn `/goal` driver (Grok docs 05-configuration.md:358 and :788). Keep this design.
- The Muse helpers match `msp.schema.json` exactly:
  - `session/list` takes `cursor`, `limit` and `updatedAfter`; its maximum of 200 equals `NATIVE_LIST_MAX_LIMIT`, and results come back newest `updatedAt` first;
  - lineage reads `forkedFrom.sessionId`;
  - `-32020` means not found and `-32601` means the version lacks the method;
  - there is no delete method (NG-6 is correct).
  `read_muse_thread` exports with `--out` into an empty temp cwd (D-17). `NativeHelperRequest` keeps keys and dummy prompts out of the helpers (INV-2, the §8.5 rejected alternative).
- D-10 moves the shared code into `GrokHome` and `MuseChildren` instead of copying it, and INV-26 keeps the moved behavior byte-identical. The stale `== 120` pin is assigned to S2 alone (row 35), and §14 forbids other test edits. The surface arithmetic agrees: 17 + 45 + 4 = 66 exports, split 23/15/16. The budget of 10 files matches §12.3.
- Read paths never create a home (D-11, EC-1, EC-18). Each file's size is checked with `os.fstat` before parsing (EC-10, A007). A query never reaches argv (D-3). KD-7 is resolved correctly: get returns a summary, and plan and to-do are excluded (NG-13, Q-3).

FINDINGS
R-1 [Blocker] [L4] §12.3 row 20 — opencode lineage loops `get`, which calls `_child`: a two-deep same-class call chain
  Evidence: Row 20 says "`OpencodeHelperRun`: narrated flows with one private `_child(request, config, errors, *, command, operands)` … lineage loops `get` with `NativeThreadListing.check_step`". AGENTS.md principle 1 says "a function may call another of its own functions, but that second function should not call a third". #1036's review raised this exact shape as Blocker R-3 (docs/spec/harness-thread-functions/review.md).
  Failure: A fresh implementer writes `lineage → self.get → self._child`. That breaks principle 1 and will draw the same Blocker comment in review. Muse (row 26) and Grok (row 14) do not say whether `lineage`/`read` call `get` either.
  Smallest fix: In row 20 (and rows 14 and 26), state that `lineage` calls the lower-layer step directly: `_child` or the wire for opencode, `MuseChildren` for Muse, `GrokStore` for Grok, followed by `check_step`. No flow may call another flow that calls a helper. Add a §12.4 line: "no flow calls a sibling flow that calls a private helper".

R-2 [Major] [L5] §9.2 Grok store scan / row 11 — the scan does not exclude the files Grok keeps beside the session folders
  Evidence:
  - §9.2 says "read `home/sessions/*/<id>/summary.json` … SDK reads all groups … USER reads the groups whose `urllib.parse.unquote(name)` (or the stripped `.cwd` file…)".
  - On this machine, `ls ~/.grok/sessions/` returns only `session_search.sqlite` (1.5 MB, the FTS5 index, 17-sessions.md:416).
  - Each group folder also holds `permission.toml` and `permission_<client>.toml` (22-permissions-and-safety.md:426) and possibly `.cwd`.
  - Row 11 steers toward `path.iterdir()` (the S061 note).
  Failure: An implementer iterates `sessions/` and treats every entry as a group. Then `session_search.sqlite/<…>` or `session_search.sqlite/.cwd` raises `NotADirectoryError` (an OSError), and by EC-13 every SDK-scope list on a real store raises `grok.store_unreadable`. Inside a group, `permission.toml` becomes a session candidate whose name fails `NATIVE_THREAD_ID_PATTERN`, so the scan raises `protocol_mismatch` or skips it, inconsistently. Fakes with a clean layout never show this.
  Smallest fix: State in §9.2 and row 11 that only directories are groups and only directories inside a group are session candidates, and that files at both levels (`session_search.sqlite`, `permission*.toml`, `.cwd`) are ignored. Add an EC with exactly those names, and have S2's real-layout fake store include them.

R-3 [Major] [L4] §9.1 / §12.4 — the int and bool checks invite inline `isinstance(x, bool)` guards that trip the blocking C002 ratchet
  Evidence:
  - `lint/baseline.json:11` sets `"C002": 9`. C002 is blocking: `lint/rules/c002_duplicate_inline_bool_guard_validation.py`, with `severity = "blocking"`, flags any non-generic name guarded by `isinstance(x, bool)` in two functions.
  - Guards already exist for `limit` (`vidbyte/lib/dataclasses/coding.py:143`), `concurrency` (`vidbyte/evals/runner.py:45`) and `status` (`vidbyte/harnesses/native/opencode/wire.py:124`).
  - The spec says "`limit` … is an `int` (not a `bool`)" (§9.1 rule 5) and "`concurrency` … Every int check refuses `bool`" (rules 6 and 8).
  - Row 19 says the epoch-ms conversion runs in `sessions` and `info`, "refusing bool and float".
  - §12.4 has a C006 line (1077) but no C002 line.
  Failure: `if isinstance(self.limit, bool) …` in `NativeHelperRequest` takes C002 from 9 to 11, and `python scripts/run_ci.py` fails. Two inline epoch guards in `OpencodeHelperWire` do the same.
  Smallest fix: §9.1 should say that every int and bool field goes through `RecordFieldValidator.require_int` / `require_bool` (validation.py:85/:92). For `pr`, check `isinstance(pr, str)` first, then `require_int`. The opencode epoch-ms conversion should be one private converter called by both readers. Add a §12.4 line: "`python lint/run.py --rule C002` stays at 9".

R-4 [Major] [L1] §2 NG-5 — the exclusion of `run_grok_imagine_video` and `run_grok_code_review` rests on false facts
  Evidence:
  - The spec says "no video tool is documented". In fact 04-slash-commands.md:275-277 documents `/imagine-video <description>` ("…animates them with `image_to_video`"), and 26-config-reference.md:290 documents `features.video_gen` ("Enable video tools / `/imagine-video`").
  - The spec says code-review's "SKILL.md tells the model to read no file and call no tool". `~/.grok/bundled/skills/code-review/SKILL.md` (192 lines) contains no such instruction. It is a maintainability-audit rubric.
  - request.md:269 lists `run_grok_imagine_video(desc)` in the accepted §E.2 catalog, which is the settled scope.
  Failure: A requested function is dropped on a reason that the vendor's own docs contradict. A reviewer who checks the docs reopens the scope.
  Smallest fix:
  - Add `run_grok_imagine_video(description, …)` with `GrokCommand.IMAGINE_VIDEO = "imagine-video"`, the line `/imagine-video <t>`, and evidence "a `tool_call` named `image_to_video`".
  - Add an A-item saying `features.video_gen` is on by default for a key-authenticated headless run (if wrong, the call fails with `command_not_run`), and a probe item.
  - Update the counts: 67 exports, grok 24.
  - Restate the code-review reason as "no distinctive tool trace to verify", and keep Q-2 (default no) for code-review only.

R-5 [Major] [L7] §9.2 Grok lines / §9.1 GrokCommandArguments — INV-9 protects argv, but not the slash-command line that Grok tokenizes
  Evidence:
  - The lines are `/goal <t>[ --budget <b>]` and `/execute-plan <d>[ --effort <e>]…[ --auto-pr]`.
  - Rule 3 requires only that `design_doc` is "an absolute path to an existing file", with no whitespace rule.
  - INV-9 covers only "inside `--single=`".
  - The execute-plan SKILL.md:5 argument hint quotes `--instructions "..."`, so its arguments are split on whitespace.
  - `/goal` reserves `status|pause|resume|clear` (04-slash-commands.md:328).
  Failure:
  - (1) `run_grok_execute_plan(r"C:\Users\Jane Doe\plan.md")`: the skill receives `C:\Users\Jane` and the paid run fails.
  - (2) A design doc named `x --auto-pr.md`, or goal text ending in `--budget 99999999`, is read as a flag. That gives `auto_pr` without the opt-in that T-7 promises, or a budget above `GROK_GOAL_MAX_BUDGET_TOKENS`.
  - (3) `run_grok_goal("clear")` clears the goal and then raises `command_not_run` after a paid run.
  Smallest fix: In GrokCommandArguments, refuse a `design_doc` that contains whitespace (field `design_doc`). In the named wrappers, refuse text with a whitespace-separated token equal to a `GrokCommandFlag` value (field = the public parameter). Refuse goal text whose stripped, casefolded value is a reserved `/goal` subcommand. Add three ECs. `run_grok_command`'s raw `arguments` stays the caller's own.

R-6 [Major] [L5] EC-50 / §9.2 Grok runs — a timed-out or capped command run loses its thread id, although Grok can take a pre-minted one
  Evidence:
  - EC-50 says "The id is unknown, because `sessionId` arrives only in `end`" → `grok.timed_out` with `thread_id=None`.
  - Grok headless supports `-s, --session-id <ID>`: "Create a new session with this UUID" (14-headless-mode.md:25 and :354).
  - `CliRunner._drain` keeps the first `max_output_bytes` bytes and keeps reading, so an over-cap stream loses its final `end` too (runner.py:335).
  - The default timeout is 1800 s (`NATIVE_THREAD_DEFAULT_SECONDS`).
  Failure: `run_grok_goal`, `run_grok_implement` or `run_grok_execute_plan` runs past 30 minutes. The caller paid for the run but gets `thread_id=None`, so it cannot continue, read or delete the thread except by guessing from a list.
  Smallest fix: `GrokCommandRun` passes `GrokFlag.SESSION_ID` (`--session-id=<uuid4>`, JOINED) and uses that id in every post-launch error. It checks that `end.sessionId` equals the id (a mismatch is `protocol_mismatch`). EC-50 then reports the id. Add an A-item (`--session-id` combines with `--single`) and a probe item. No public parameter is added, and #1036's `run_grok_thread` stays unchanged (INV-26).

R-7 [Major] [L5] §9.2 / row 11 / INV-6 — an operation on one id inherits the whole-store strict parse, so another thread's file breaks it
  Evidence:
  - §9.2 routes `get_grok_thread` and `get_grok_thread_lineage` through `GrokStore.threads`, and row 11 makes that one entry point (also "the agent lookup used by plan and explore").
  - INV-6 says the store is "never silently skipped, never yields a partial result".
  - EC-62 accepts an "intermittent `grok.protocol_mismatch`" while any run rewrites its `summary.json`.
  Failure: While a long goal run (thread B) rewrites its summary, or after B's file is corrupt or over 1 MiB, every one of these raises `protocol_mismatch` that names B's file:
  - `get_grok_thread(A)`
  - `delete_grok_thread(A)` (no delete starts)
  - `read_grok_thread(A)`
  - the post-run evidence check of an already-paid `run_grok_plan`
  Smallest fix: In §9.2 and row 11, have operations on one id read only `sessions/*/<id>/summary.json` (and, for lineage, each parent's file). Whole-store strictness (INV-6) then applies to list, recent, since and search only. Add one EC: "a corrupt sibling does not affect get/delete/plan evidence".

R-8 [Major] [L10] §12.5 probe (a) / §15 A-7 — the probe as worded does not exercise the SDK's own path, and the availability of bundled skills under a private home is unstated
  Evidence:
  - §12.5(a) says "(a) that `grok --single "/goal …"` expands". The user runs it "in their own shell", which uses `~/.grok`, the default workflows (host driver, no `update_goal`) and the default output format.
  - The SDK runs under a private `GROK_HOME` (`~/.vidbyte/grok-homes/<key>`, which does not exist on this machine), with `GROK_WORKFLOWS=0`, `--single=` and `--output-format=streaming-json`.
  - Bundled skills are "distribute[d] … separately … cached under `~/.grok/bundled/skills/`" (08-skills.md:213). No A-item says they resolve under a fresh `GROK_HOME`.
  Failure: The bare probe passes, but the SDK path fails: 9 of the 11 Grok command functions raise `command_not_run` on every paid call. Or the probe fails for workflow-driver reasons that do not apply to the SDK. Either way, A-7 is not settled.
  Smallest fix:
  - Have probe (a) and (c) call `run_grok_goal`, `run_grok_implement` and `run_grok_imagine` themselves and print `thread_id`, the tool names seen, and `error.code` on failure.
  - Add a negative control: send the goal text without the leading `/` and confirm that no `update_goal` call appears, so the evidence is shown to discriminate.
  - Add A-22: "bundled skills resolve under the private GROK_HOME". If that is wrong, the PR body names it.

R-9 [Major] [L9] §15 preamble — "being wrong produces a loud error, never a silent wrong answer" is false for four assumptions
  Evidence: Line 1209 makes the claim, yet:
  - A-1 says "If wrong: every Grok list returns `()`";
  - A-4 says "USER scope misses threads";
  - A-12 says "or an empty list";
  - A-21 says "the Muse helpers miss the SDK's threads".
  EC-11 skips any session folder that has no `summary.json`.
  Failure: Grok renames or nests `summary.json`. EC-11 then skips every folder, and every Grok list returns `()` with no error. Tests on synthetic fixtures still pass.
  Smallest fix:
  - Bound EC-11: if a scanned home has at least one session folder and none of them has a `summary.json`, raise `grok.protocol_mismatch` naming the expected layout.
  - Rewrite the preamble to name A-4, A-12 and A-21 as silent-if-wrong, each settled by a §12.5 item (b, f, g).

R-10 [Major] [L1] §9.2 opencode get/lineage — a metadata call moves whole transcripts, and the request's mechanism was dropped with no D- entry
  Evidence:
  - §9.2 says "`get_opencode_thread` … `get_opencode_thread_lineage` | `opencode export <id>` … Lineage calls export once per step".
  - request.md:236 says "The `session.parent_id` database column, read with `opencode db "<sql>"`".
  - A-12 says the `session list` rows already carry `id`, `title`, `created`, `updated`, `directory` and `parentID`.
  - D-19 already lists every session in one call.
  Failure: `get_opencode_thread` on a long session whose export exceeds 64 MiB raises `opencode.output_too_large` for a summary request. Lineage at depth d runs d full exports, each under the 30 s control timeout, and raises `timed_out` on large threads.
  Smallest fix: `get` and `lineage` read the one `session list` call and walk `parentID` in memory. An id that is absent raises `thread_not_found`. Only `read` uses `export`. Record the change from `opencode db` as a D- entry.

R-11 [Minor] [L9] §5 INV-26 vs FR-17 / D-20 — the "unchanged" promise contradicts two planned text changes
  Evidence: INV-26 says `run_/continue_/fork_<harness>_thread` "keep #1036 behavior exactly: … codes and messages", yet FR-17 says "Today's `thread_not_found` texts are widened", and D-20 changes `NativeThreadError.expected` for all operations (§9.4 lines 865–866).
  Failure: A reviewer reads INV-26 literally and flags the continue/fork message changes as regressions.
  Smallest fix: Amend INV-26 to say: "codes and behavior unchanged; message texts change only per FR-17 and D-20".

R-12 [Minor] [L9] §12.3 row 27 / §9.1 — two internal contracts disagree
  Evidence:
  - Row 27 gives `MuseCommands` a second guarded `_call` for `init_muse_workspace`, while §12.4 says "Every public class has exactly one guarded `_call`".
  - `GrokThreadFile.search_text: str` (line 635) feeds `NativeThreadListing.matches(texts: Sequence[str | None], …)` (line 643).
  Failure: The implementer either breaks §12.4 or guesses, and either passes a str as a Sequence (matching character by character) or changes a signature.
  Smallest fix: Move `init_muse_workspace` to `MuseThreadHelpers` (it is keyless and takes a `NativeHelperRequest`) and update the counts in row 26 and row 27. Make `search_text: tuple[str | None, ...]`.

R-13 [Minor] [L10] §12.3 row 35 / §13 — S2's instruction misses a second stale assertion and a fake shape drift
  Evidence:
  - `tests/features/harness_threads/test_harness_threads_surface.py:195` reads `assert len(members) == len(main_members) + len(NEW_FAILURE_CODES)`. With merge base 72a4ade1 at 148 members (verified with the test's own ast logic) and row 35's `NEW_FAILURE_CODES` (32), that is 152 ≠ 180.
  - `fake_harness.py:562` returns `"forkedFrom": source` as a string, while the MSP `Session.forkedFrom` is an object `{sessionId, …}`, which the spec reads as `forkedFrom.sessionId`.
  Failure: S2 fixes only line 193 and the gate still fails at line 195. A Muse lineage fixture copied from the fork fake gives a string, so the reader raises `protocol_mismatch`, or a lenient reader is written to pass it.
  Smallest fix: Row 35 names line 195 too (for example, `len(members) == len(main_members) + 4`). §13 tells S2 to model `forkedFrom` as an object in new Muse fixtures.

R-14 [Minor] [L6] §7 edge cases — subagent child threads are listed as ordinary threads, with no EC or README line
  Evidence:
  - Grok's layout says "the child sessions live in the normal sessions tree" (17-sessions.md:22-36).
  - `parent_session_id` is documented only "for forked or restored sessions" (:42).
  - execute-plan launches an implementer and a reviewer subagent per PR (execute-plan SKILL.md:486, :585).
  - Muse items carry `childSessionId`.
  Failure: After one `run_grok_execute_plan`, `list_recent_grok_threads(ws)` (limit 10) can be mostly subagent children. The caller's own threads drop out, and a child's lineage may stop at itself.
  Smallest fix: Add an EC and a README sentence saying that subagent child threads appear as ordinary threads. Optional Q-4 [scope-adding], default no: filter children out of lists.

VERIFIED CLAIMS:
- `grok/threads.py:GrokThreadRun._prepare_home`: the sha16 home key is at lines 141–143, and `_fallback`, `_environment` and `_argv` (JOINED, `--single=` last) are as the spec says. HELD (row 11 and row 12 extraction are feasible).
- `hostkit/errors.py`: `failure(...)` and `from_launch_failure(..., request: NativeThreadRequest)` (required), and `hostkit/launcher.py:NativeLauncher.resolve`, read only `.workspace`/`.thread_id`. HELD (the widening in rows 8–10 is safe).
- `vidbyte/lib/process/argv.py:9` says "Operands are not checked", and a separate-style value starting with a dash is refused (:50). HELD (D-3 and the INV-9 rationale).
- `CliRunner`: stdin is DEVNULL when `stdin_text` is None; the environment is `os.environ` minus `env_remove` plus the overlay; the output cap keeps the first N bytes and keeps draining without killing the child. HELD. The new consequence is R-6: `end` is lost when the stream goes over the cap.
- `NativeThreadResult` has no text cap. HELD (INV-21 is feasible).
- `test_harness_threads_static_policy.py`: the allowed literals are "", 0 and 1, and bool and None are allowed. HELD (INV-15).
- Surface test line 193 `== 120` is stale, since the merge base 72a4ade1 has 148 members ending in `MUSE_WSL_UNAVAILABLE`. HELD. Line 195 is also stale (NEW).
- `test_harness_threads_errors.py:193-204`: the key set is 28 codes + 2, with texts unique per harness. HELD (row 36).
- `fake_harness.py:548-550`: serve refuses frames without `excludeItems is True` (-32602). HELD. `:562` `forkedFrom` is a string (NEW, R-13).
- C002 is blocking with a baseline of 9. Existing guards cover `limit`, `concurrency` and `status`, and `RecordFieldValidator.require_int`/`require_bool` exist at validation.py:85/:92. HELD (R-3).
- `vidbyte/harnesses/README.md:178` holds the EC-44 sentence. `llms.txt` and `artifacts/file_index.md` have no native entries, and there is no CHANGELOG. HELD (rows 33–34 and 38 are sufficient).
- `msp.schema.json`, all HELD:
  - 31 methods, none of which deletes;
  - `session/list` takes `{cursor, limit ≤ 200 (default 50), updatedAfter, workspaceRoot}` and returns `{nextCursor, sessions}` ordered by `updatedAt` descending;
  - `Session` has `createdAt`, `updatedAt`, `modelId`, and `forkedFrom` (an object with `sessionId`, or null);
  - the `SessionHistory` modes and the `noneReason` values;
  - `Item` has `tool`, `args` (a string) and `childSessionId`;
  - `-32020` means sessionNotFound.
- `muse-skills.json` has the ids `bundled:plan`, `bundled:import`, `bundled:greenfield-project-scaffolding` and `bundled:browser-app-delivery`, all on, with descriptions that say "call read_skill for bundled:<id>". HELD. `create_goal` does not appear there, so A-17's second half stays unverified, as the spec says.
- Grok layout and `summary.json` members (17-sessions.md:20-42) and the streaming `tool_call.toolName`/`rawInput` and `end.sessionId` fields: HELD. The timestamp format is undocumented, which A-2 correctly marks as an assumption.
- Grok persona files `shared/personas/{implementer,reviewer,design-doc-writer}.md` and `shared/resume-session/CORE.md` exist. The skills read them with `read_file` "at the start of the run" (execute-plan SKILL.md:84, before the Dry-Run Exit at :393). HELD (A-9; the evidence also holds for `dry_run=True`).
- `/goal <objective> [--budget <tokens>]`, plus the reserved `status|pause|resume|clear`, and `GROK_WORKFLOWS=0` selects `update_goal`. HELD. The reserved words are NEW (R-5).
- NG-5's claims that "no video tool is documented" and that code-review means "read no file and call no tool": FALSE (R-4).
- D-3's claim that it "mixes in results from xAI's servers": HELD (17-sessions.md:272, "combines a local SQLite index with remote results").
- D-4's claim that `chat_history.jsonl`/`updates.jsonl` member names are undocumented: HELD (the files are listed, but their schema is not).
- Grok `--session-id <UUID>` creates a new headless session (14-headless-mode.md:25). NEW (R-6).
- The Grok store holds files that are not sessions (`sessions/session_search.sqlite` on this machine, and `<group>/permission*.toml`). NEW (R-2).
- request.md:236 put opencode lineage on `session.parent_id` via `opencode db`. HELD; the spec drops it without a D- entry (R-10).
- `origin/main` is now 0f69f7b7 (#1095, #1103) and touches `vidbyte/lib/enums/__init__.py` but no native files and not `failure.py`. Merge note only: row 2 will need a trivial rebase.
