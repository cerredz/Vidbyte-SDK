# S1 spec author report: harness-thread-helpers-skills

- **Stage:** S1 spec author
- **Spec:** `docs/spec/harness-thread-helpers-skills/spec.md`, r1 (1,271 lines), committed as `7910f151` on `feat/harness-thread-helpers-skills`
- **Base:** `72a4ade1`
- **Result:** DONE. 0 blocking questions.

## 1. What I read

Rawest material first: code and vendor CLIs, then the docs.

- **Source code, PR #1036, as merged at `72a4ade1`:**
  - `vidbyte/harnesses/native/__init__.py`, plus `grok/`, `opencode/` and `muse/`, each with `__init__.py`, `threads.py` and `wire.py`. Muse also has `launcher.py`.
  - `hostkit/__init__.py`, `hostkit/errors.py` and `hostkit/launcher.py`.
  - The lib layer: `lib/enums/native_threads.py`, `lib/enums/failure.py`, `lib/constants/native_threads.py`, `lib/dataclasses/native_threads.py`, `lib/dataclasses/process.py` (`CliInvocation`), `lib/dataclasses/validation.py` and `lib/errors/base.py`.
  - The exemplar I copied is `GrokThreads._call`: the guarded except-order, the narrated `GrokThreadRun.execute`, and the `NativeErrorFactory` table.
- **Repo rules:**
  - AGENTS.md: principles, Placement Rules and Repository Map.
  - `lint/rules/*` for A001, A002, A007, S052, S061, S015, C016, C006, S060/S039, S012, S008/S024, S020 and A009, plus `lint/baseline.json`.
  - `.semgrep/typed-mapping-boundary-policy.yml`. Its rule `no-untyped-mapping-fallback` runs only in `static-policy.yml`.
  - `REPO_MAP.md` and `vidbyte/harnesses/README.md`, which holds the false EC-44 sentence.
  - The field-guide entries the briefing allowed, `house-style.md` and `spec-template.md`.
- **Tests:**
  - `tests/features/harness_threads/*`: surface, errors, static policy, `fake_harness.py`, `conftest.py` and `FEATURE.md`.
  - My baseline run in the worktree venv gave `1 failed, 435 passed, 2 skipped`. The failure is `test_harness_threads_surface.py` line 193, `assert 148 == 120`. It is a stale #1036 pin that is already red on main. The gate forces its rewrite, and that is S2's job (§12.3 row 35).
- **Vendors, keyless only:**
  - `grok --help`, `grok sessions --help`, `grok export --help` and `grok inspect`. `grok inspect` is what proved #1036 EC-44 false.
  - `opencode session list|delete --help` and `opencode export --help`.
  - `muse --help`, `muse exec --help`, `muse init --help` and `muse export --help`.
  - The allowed captures `msp.schema.json` (MSP 1.0.1) and `muse-skills.json`. I did NOT open `oc-export.json`, `oc-config.json` or `inspect*.json`.
- **Docs:**
  - The request: `request.md` (Prompts 1–6, KD-1 to KD-10, §C, §E.1, §E.2), `context/code-map.md` and `reports/S0-scout.md`.
  - From the #1036 spec folder: `request.md`, `spec.md` (read in chunks), `review.md` and `pr-body.md`.

## 2. Approaches weighed

- **Chosen design:** 45 functions under the owner's naming.
  - **22 helpers.** They are keyless, use a new `NativeHelperRequest`, and return one shared `NativeThreadSummary`.
  - **23 skill functions.** They use the per-harness building blocks `run_grok_command` / `run_opencode_command` / `run_muse_skill`, plus 3–5 line named wrappers. They return #1036's `NativeThreadResult` only when that run's own record proves the command ran. Otherwise they raise `<harness>.command_not_run` with the new thread id.
  - **10 new source files, 0 dependencies.**
  - **Refactor scope:** shared plumbing is extracted only where three callers need it: `GrokHome`, `MuseChildren`, `NativeThreadListing` and `NativeCommandEvidence`.
- **Rejected: prefix-only wrappers (§8.3).** These are 23 one-liners that prepend `/goal` and so on. They are the smallest option, but they fail INV-8. On Muse, `muse exec "/goal …"` was verified to run an ordinary thread and report success (KD-6). request.md itself lists "bare slash-command prefixing without verification" as rejected.
- **Rejected: helpers on `NativeThreadRequest` with a dummy prompt and key.** That would put a key on keyless calls (INV-2). It would also make refusals name `prompt` (INV-3).
- **Rejected: parsing `grok sessions list` text.** The text has no created time, parent or model, and no member names to check strictly (FR-4, INV-6). I read `summary.json` instead. This reverses #1036 D-17 and is recorded as a D- item; the file's shape is A-1 to A-4.
- **Evidence source per harness:**
  - **Grok:** `--output-format=streaming-json` tool calls (`update_goal`, `read_file` of the persona or resume CORE path, `image_gen` / `image_edit`). For `--agent`, evidence is `summary.json` `agent_name`. Rejected: post-hoc export parsing, which is Markdown and lossy.
  - **opencode:** its own `Command "<name>" not found` dispatch error. opencode resolves `--command` itself, so no transcript check is needed.
  - **Muse:** MSP `session/read {excludeItems:false}` `toolCall` items (`read_skill` + skill id, or `create_goal`). History mode `none` fails closed.

## 3. Where I disagreed with the scout or the request (with evidence)

- **Muse compaction.** The scout suggested "Muse list/compact reuse", but compaction is excluded (NG-3). `/compact` is a TUI/turn command, and no headless path was verified for any of the three harnesses. That leaves Q-1, default no.
- **Grok search.** It runs locally over `summary.json` (title, summary, last-turn summary), not through `grok sessions search`. That command's output is human text, with the same problem as `sessions list` (INV-6).
- **opencode lineage.** It uses `opencode export` `info.parentID`, not `opencode db`. `opencode db` is an internal SQLite surface with no stability promise.
- **Excluded functions.** `run_grok_skill`, `run_opencode_skill`, `run_muse_command` (NG-7, Q-6), `run_grok_code_review` and `run_grok_imagine_video` (NG-5, Q-2) are excluded. None of them has a verifiable evidence rule offline, and an unverifiable wrapper is exactly the rejected design.
- **`get_*_thread` returns only the summary record.** KD-7 fixes the record, so the plan, to-do list and goal state are left out (Q-3).
- **The briefing's venv note was followed.** No global `pip install`.
- **The scout was right that main moved to `72a4ade1`.** This was confirmed, and `base_commit` uses it.
- **#1036 EC-44 is false.** SDK Grok runs still load `~/.claude` hooks, skills and MCP servers (`grok inspect`). Per the orchestrator, this is a limitation (EC-63, T-6, NG-9), and the README sentence is replaced (AC-26). It is not fixed in this PR.

## 4. Assumptions I am least sure of

All of these are unverifiable offline. The manual QA probe in the PR body (§12.5) covers each one.

- **A-7:** `grok --single "/goal …"` expands a leading slash command.
  - If wrong, every Grok command except plan and explore raises `grok.command_not_run`. That is fail-closed, so it is safe but not useful.
  - This is the biggest risk to G-2.
- **A-2:** the `summary.json` member types (times, `parent_session_id`, `agent_name`, model).
- **A-8, A-9 and A-11:** the streaming-json event fields, the evidence markers (persona and CORE paths), and the "final text = text after last tool event" rule.
- **A-15:** opencode's exact unknown-command text and its exit code.
- **A-16 and A-17:** a batch `muse serve` answers `session/read` with inline `toolCall` items, and `read_skill` args carry the skill id.

## 5. Stage E self-check

- **Template:** all sections from §0 to §17 are present, in template order.
- **IDs:**
  - Defined: G 4, NG 15, INV 28, AC 26, EC 65, FR 20, NFR 12, D 25, W 12, T 7, A 23, Q 6.
  - Every referenced ID is defined. KD-n refers to request.md.
- **Names:**
  - §4, §8.5, FR, §9.2 and §12.3 name the same 45 functions.
  - Every stray name is an NG exclusion or an existing #1036 function.
  - Export math: 17 existing + 45 + 4 = 66 in the root, and the subpackages hold 23, 15 and 16. I checked this against the live `__all__` in the venv.
- **File budget:** 10 CREATE rows = the §8.4 budget of 10.
- **EC guards:** every EC row has a guard cell. EC-24 is marked as a vendor limitation. I added INV-5 to EC-58.
- **Threats:** every T- row names a control and where it sits.
- **No tests:** §13 has facts only, with no `def test_` and no `assert`.
- **One fix made during the self-check:** FR-20 (docs) had no acceptance criterion. I added **AC-26** (P1, proven by review) and linked it from W-11.

## Addendum: r2 (S1 review round 1)

- **Spec r2:** committed as `7a0d170f`. HEAD before it was `39eaa7f4`, after the rebase onto origin/main `0f69f7b7`.
- **Review read:** `reports/S1-spec-review.md`. Verdict SOUND WITH FIXES, with 1 Blocker, 9 Major and 4 Minor findings.
- **Disposition:** all 14 accepted. None rejected, none deferred. §16 records each one.

### Evidence I re-checked before accepting

I did not take the review on trust. I checked each claim against the raw source:

- **R-2:** `~/.grok/sessions/` on this machine holds only `session_search.sqlite`.
- **R-3:** `lint/baseline.json:11` has `"C002": 9`, and the rule is `severity = "blocking"`. `RecordFieldValidator.require_int` / `require_bool` are at `validation.py:85` / `:92`.
- **R-4, the user guide:**
  - `04-slash-commands.md:275-277` documents `/imagine-video` with `image_to_video`.
  - `26-config-reference.md:290` documents `features.video_gen`.
- **R-4, the code-review skill:**
  - `code-review/SKILL.md` is a 192-line rubric.
  - It has no persona file and no distinctive tool, and it does not say "call no tool".
- **R-5:** the `/goal` reserved words are at `04-slash-commands.md:328`, and the execute-plan argument hint splits on whitespace.
- **R-6:** `14-headless-mode.md:25` and `:354` document `-s, --session-id`: "Create a **new** session with this **UUID**". `GrokFlag` has no `SESSION_ID` today.
- **R-13:**
  - Surface test line 195 is stale as well as line 193.
  - `fake_harness.py:562` returns `forkedFrom` as a string.
  - FailureCode has 148 members at both `72a4ade1` and `0f69f7b7`, by the test's own `ast` logic.
- **Rebase effects:**
  - The `vidbyte/lib/enums/__init__.py` native import block is still at lines 111–126, and `__all__` is at lines 172–290.
  - `contracts/sdk-public-api.json` has 0 `harnesses.native` entries.
- **Baseline re-run:** on `39eaa7f4`, `1 failed, 435 passed, 2 skipped in 61.86 s`. The single failure is the same stale line-193 pin.

### Where I went beyond the reviewer's smallest fix

- **R-4: both functions are restored, not only imagine-video.** The orchestrator ruled both in scope (request.md:267/:269). code-review leaves no tool trace, so its evidence is the run's own `grok export` transcript containing a sentence of the skill's Core Prompt (D-28). This matches the owner's own proof rule ("goal state in `summary.json` or `export`"). The caller cannot spoof it, because the function takes no text. If the expansion is not in the transcript, the function fails closed (A-27).
- **R-9: the layout bound has a grace period.** The reviewer's rule raises when no session folder has a `summary.json`. That would make a fresh home's first run raise `protocol_mismatch` on any list during startup. I added `GROK_SUMMARY_GRACE_SECONDS` (60), measured on the newest folder's mtime (D-31, EC-67).
- **R-5: the token check also refuses `<flag>=`,** for example `--effort=5`, not only exact tokens.
- **R-8: renumbered.** The reviewer's proposed "A-22" was already taken, so the item is A-26. IDs stay stable.

### Assumptions I am now least sure of

All of these are new or still unverified, and each is a probe item:

- **A-25:** `--session-id` combines with `--single`. If it does not, every Grok command run fails, which is loud, and D-29 flips back to r1.
- **A-26:** bundled skills resolve under a fresh private `GROK_HOME`. If they do not, 11 of the 13 named Grok wrappers always raise `command_not_run` (all but plan and explore).
- **A-27:** the code-review expansion appears in the export transcript.
- **A-24:** `features.video_gen` is on by default.
- **A-7:** `-p` slash expansion is still the largest single risk.

### Self-check results (r2)

- **Defined IDs:** G 4, NG 15 (NG-5 withdrawn), INV 29, AC 31, EC 74, FR 20, NFR 12, D 31, W 12, T 8, A 27, Q 7 (Q-2 closed).
- **References:** every referenced ID is defined.
- **Names:** §8.5 = FR = 47 functions, and every §4 name is in §8.5. Exports: 17 + 47 + 4 = 68, with subpackages at 25, 15 and 16.
- **Tables:** every table row has a uniform column count. I checked this by script, and it caught a misplaced T-8 row, which I fixed before the commit.
- **Budget:** 10 new source files, as before. The new methods (`GrokStore.thread`, `GrokHelperRun.export`, `NativeCommandEvidence.require_text`) live in files already counted. `OpencodeHelperWire.info` was removed.
- **No tests:** the spec still contains no test code.

## Addendum: r3 (S1 review round 2, final; status approved)

- **Spec r3:** committed as `e6b2cdbd`, on top of `a428f686`.
- **Review read:** `reports/S1-spec-review-r2.md`. Verdict SOUND WITH FIXES, with 1 Blocker, 5 Major and 5 Minor findings, and R-10 marked unresolved.
- **Disposition:**
  - R-15 to R-25 accepted, all 11.
  - R-10 re-disposed: R-15 resolves it.
  - Nothing rejected. Nothing is still disputed, so no dispute-Q was needed.

### Evidence I re-checked myself

All of this comes from the strings of the opencode 1.18.31 binary. I started no opencode process and read no session data.

- **`session list`:**
  - It lists root sessions only: `E.list({roots:!0,limit:D.maxCount})`.
  - With no limit given, it stops at 100 rows: `let Y=$.limit??100`.
- **The unknown-command text** is `Command not found: "${t.command}".${I}`.
- **`opencode db`:**
  - It is `command:"db"` with `instance:!1`.
  - Its default subcommand is `$0 [query]`, with `--format json|tsv`.
  - The handler runs `C.all(k1.raw(u))` and prints `JSON.stringify(rows)`.
- **The `session` table** has the columns `id`, `parent_id`, `directory`, `title`, `time_created` and `time_updated`.
- **Not-found text:** `Session not found: ${id}`.
- **Repo:** `NATIVE_THREAD_ID_PATTERN` is `^[A-Za-z0-9][A-Za-z0-9_-]*$`, so no quote, space or semicolon can reach the SQL. `require_command_line_units` is at `validation.py:64`, and `NativeThreadRequest` calls it under the name `prompt` at `native_threads.py:102`.

### Decisions in r3 and why

- **R-15 (and R-10):** get and lineage use `opencode db --format=json "<constant SELECT … WHERE id = '<id>'>"`.
  - This is the request's own mechanism (request.md:236) and the orchestrator's preference.
  - It reads `parent_id` for non-root sessions without moving a transcript.
  - It is injection-safe through the id pattern (T-9).
  - Lineage runs one query per step. A recursive CTE would need one child in all, but it is harder to verify, and lineage depth is small.
  - The flip condition in D-26 falls back to `export` `info`.
  - Forks record no parent (`Session.fork`), so this is now a documented limitation (EC-76, plus a README sentence).
- **R-16:** lists pass `--max-count=10000`. Exactly the cap raises `opencode.protocol_mismatch` with a detail naming the cap, never a short list.
  - I chose `protocol_mismatch` over `output_too_large` because the shared `OUTPUT_TOO_LARGE` observation speaks of a byte cap.
  - The fix stays internal: an error, not a parameter.
- **R-20:** the in-scope fix is a refusal plus error texts. A `skills=` folder named like the command is refused (D-32). The text changes cover the workspace and user shadows. The `grok inspect` pre-flight is Q-8 [scope-adding], default no.
- **R-25:** in `anchoredSnapshot` mode the evidence comes from the run's own `muse export` (D-33). It fails closed, with a compaction cause, if A-28 is false.
- **Unasked correction:** I reworded D-24's reason. The 1.18.31 session record may carry a model, but the decision `model=None` stands.

### Least-sure assumptions now

- **A-7:** `-p` slash expansion.
- **A-26:** bundled skills resolve under a private `GROK_HOME`.
- **A-27:** the code-review expansion appears in the export transcript.
- **A-28:** `muse export` keeps tool calls from before compaction.
- **A-24:** `features.video_gen` defaults on.

All five fail closed and have probe items.

### Self-check results (r3)

- **Defined IDs:** G 4, NG 15, INV 29, AC 34, EC 81, FR 20, NFR 12, D 33, W 12, T 9, A 29, Q 8.
- **References:** every referenced ID is defined.
- **Names:** §8.5 = FR = 47 functions.
- **Tables:** 0 malformed rows.
- **Budget:** still 10 new source files and 20 classes. Exports: 68, with subpackages at 25, 15 and 16.
- **No tests:** the spec contains no test code.

## Addendum r4

r4 amends the contract for the S4 code review (`review.md`, `reports/S4-findings-verifier.md`), before S5 fixes the code. The spec commit is `d6792f3d`. The S4 IDs R-1 to R-23 collide with the spec-review IDs R-1 to R-25 already in §16, so the spec cites them as "S4 R-n", and their §16 rows have Round "S4".

### What I read

- `review.md`, `reports/S4-findings-verifier.md` and the `reports/S4-review-*.md` files.
- The code behind each accepted finding:
  - `muse/commands.py:134-153`: the old anchored rule is two `require_text` calls over the export.
  - `hostkit/evidence.py:36`: the substring match.
  - `hostkit/errors.py`: the `thread_id` fallbacks in `failure`, `from_configuration_error`, `from_unexpected` and `from_launch_failure`.
  - `grok/commands.py:230-243`.
  - `muse/wire.py`: `tool_calls` at 300-338 and `exited` at 272-281.
  - `GrokHelperWire._checked` and `OpencodeHelperWire._checked`.
  - The `MUSE_*` constants, with the old scan-cap next step at line 817.
  - The test pin at `test_harness_threads_helper_surface.py:258`.
- **Why R-2 is a real Blocker.** `MUSE_GOAL_PROMPT_TEMPLATE` names `create_goal`, and `MUSE_SKILL_PROMPT_TEMPLATE` names the skill. Both are in the export, so the r3 text search always passed.

### What changed and why

- **R-2 (D-33, INV-8, AC-34, EC-83, EC-84, A-28; rows 4, 25, 26, 27).**
  - Muse evidence is always a `toolCall` item, and message text never counts.
  - In `anchoredSnapshot` mode the items are the top-level `items` list of the run's own `muse export` JSON.
  - The new pure `MuseSessionWire.item_calls(holder)` reads both sources. `tool_calls` hands it the history or the snapshot state.
  - One `NativeCommandEvidence.require` call checks both sources.
  - An export that is not JSON, not an object, or has no `items` list fails closed with `MUSE_EXPORT_ITEMS_DETAIL`.
  - **Where the export is parsed.** I put the parse in `MuseCommandRun.execute` (a `ValueError` from `json.loads` counts as no document), not in `MuseHelperRun.transcript`. Two reasons: `transcript` keeps its `-> str` signature, and the briefing allows only one new wire static.
- **R-23 (AC-17, EC-82, A-17, §9.2, §9.3, row 30).** `require` gains one keyword, `member`.
  - With `member` set, a call counts only when its `args` parse as a JSON object whose `member` value equals `fragment` exactly, with no folding.
  - Muse passes `member=MUSE_READ_SKILL_ID_MEMBER` (`"id"`). Grok keeps the substring rule after folding.
  - I chose a keyword on `require` so that inline and anchored items stay "the same `require`", as the briefing asks for R-2.
- **R-5 (D-34, AC-35, EC-85; rows 8, 15, 27).** `NativeErrorFactory.remember_thread(thread_id: str) -> None` follows the `register_secret` precedent (per-call state).
  - The fallback order is: the explicit `thread_id`, then the remembered id, then `request.thread_id`.
  - There are exactly two call sites: right after `GrokStreamWire.read` and right after `MuseThreadRun.execute`.
  - A launch failure before the child started stays without an id (INV-26).
  - INV-29 and EC-61 keep their wording.
- **R-6 (D-35; rows 8, 13, 19, 25).** `NativeErrorFactory.child_problem(outcome: CliOutcome, *, marker: str | None = None, texts: tuple[str, ...] = ()) -> NativeThreadProblem | None` is a pure static, following the `wrong_thread` precedent (`efae78a5`).
  - The order is: timed out, then stdout cut, then non-zero exit with the marker, then other non-zero exit, else `None`.
  - Each site passes its own marker: Grok checks stderr and stdout, opencode checks stderr, and Muse passes no marker.
  - The marker and texts are data arguments, not a boolean flag (`function_design.md`).
  - Main's four copies stay ("do not rewrite untouched code"). The §8.4 budget is unchanged, and §8.4 says so.
- **R-7.** AC-22, NFR-5 and §11 say `SDK-LINT: PASS`.
- **R-8.** INV-18, NFR-4 and §12.4 use #1036's wording and exempt boundary-record validation (#1036 D-26).
- **R-16.** §12.4 holds the verbatim next step. Row 4 stores it, and §13 notes that the pin at `:258` moves with it.
- **Propagation.**
  - TL;DR, §5 and the §12.4 `muse.command_not_run` cause now name items, not "transcript lacks the call".
  - W-12 now covers AC-35.
  - The proof cells of amended ACs say "r4 amendment: proof pending (S2, S5)".
  - §12.4 checks that no `require_text` call remains in `muse/commands.py` and that `remember_thread` has exactly two call sites.
- **Recorded, not changed.**
  - Code fixes: R-1, R-3, R-10, R-11, R-15, R-17 and R-21.
  - R-4 is a test-fixture fix only. No `NativeEnvironmentVariable` members are added, and README line 179 stays.
  - Deferred to follow-up (S4): R-9, R-12, R-13, R-14, R-18, R-19, R-20 and R-22.
  - The verifier's refutations: no spec change.
- **Not changed.** The frontmatter `base_commit` still says `0f69f7b7`. §17 records that the merge base is now `239c408a`, through S3's merge `4206cee2`.

### Least-sure assumptions now

- **A-17, the `id` member name.** The member name is unverified on a real Muse. If it is wrong, every Muse skill call fails closed. The failure is loud but total, and probe g prints the real `args`.
- **A-28, the export's top-level `items` shape.** This shape is unverified. The default export file is named `trajectory-<timestamp>.json`, which hints at a different format. If the shape is wrong, the run fails closed with `MUSE_EXPORT_ITEMS_DETAIL`, and probe g prints the real top-level keys.
- **`member` on `require`.** This adds a keyword to an existing §8.5 signature. It is not a new name. If the orchestrator reads "no change to any name in §8.5" strictly, the fallback is an equality check inside `MuseCommandRun`. That would split the evidence rule into two places, and the briefing asks for one.

### Self-check results (r4)

- **Defined IDs:** G 4, NG 15, INV 29, AC 35, EC 85, FR 20, NFR 12, D 35, W 12, T 9, A 29, Q 8. No number is skipped and none is reused.
- **References:** every referenced ID is defined. The KD-n IDs are the request's key decisions.
- **Coverage:** every AC is reached by a W- item, by a range or directly, and AC-35 by W-2, W-7, W-9 and W-12. Every EC row has a guard. The FR-to-AC mapping goes through the W- items, as in r3.
- **Tables:** 0 malformed rows, checked by column count per table, with code spans and escaped pipes handled.
- **Names:** `remember_thread`, `child_problem`, `item_calls`, `member`, `MUSE_READ_SKILL_ID_MEMBER` and `MUSE_EXPORT_ITEMS_DETAIL` have the same signatures in §8.5, §12.3 and §16.
- **Remnants:**
  - `AGENT-LINT` is left only in the S4 R-7 row and the historical r3 §17 row.
  - `require_text` is left only for Grok code-review (D-28) and in "no `require_text` call remains".
  - `list_opencode_threads_since` is not left in any next-step text.
- **Budget:** still 47 functions, 68 exports, 10 new source files and 20 harness classes.
- **No tests:** the spec contains no test code.

## Addendum r5

r5 revises D-33, A-28 and everything that depends on them, after the orchestrator's probe of a real Muse. The spec commit is `b701550e`.

### The evidence

- **The orchestrator's probe.** It ran `muse exec --provider echo` and then `muse export --redacted` in a throwaway store. The export has the top-level members `diagnostics`, `events`, `export_schema_version`, `exporter_version`, `redaction`, `session_build`, `session_terminated_abnormally` and `sessions`, and no `items`. I re-read the file: 58 `events`, each `{kind, derived, envelope{stream, payload{kind, event}}}`. So under r4, every compacted Muse skill or goal run would fail closed with `MUSE_EXPORT_ITEMS_DETAIL`.
- **The MSP schema** (`scratchpad/msp.schema.json`, `msp-view-defs.json`):
  - `SnapshotState` says "the anchored rung serves the full folded state".
  - `SnapshotState.items` is "Every item, in first-opened order, each at its latest revision at the snapshot cursor".
  - `ItemKind` includes `compaction`.
  - `session/read` takes no `history` preference; the server picks the mode.
  - `view/page` has error arms `-32040 viewTruncated` and `-32042 boundaryPruned`.
  - Nothing in the schema says an anchored snapshot drops items from before the boundary. That premise (review R-25 in r2, and the comment in `wire.py` "An anchored snapshot starts at a compaction boundary") came from the word "anchored".
- **The stand-in** (`fake_harness_helpers.py:454-473`) models that premise: its anchored mode keeps a `compaction` item and only the `list_dir` calls.

### My probes (echo only, no key, throwaway store, removed afterwards)

The scripts are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/muse-probe/`: `probe_history.py`, `probe_autocompact.py` and `probe_prefixcompact.py`. Their logs and raw answers are in `out/` (`probe.log`, `probe2.log`, `probe3.log`, `read*.json`, `page*.json`, `p2_*.json`, `p3_*.json`). Each script:
- runs under `env -i PATH=/usr/bin:/bin`;
- makes its own `tempfile.mkdtemp` root with `HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` inside it, and asserts that no `*KEY*` or `*TOKEN*` variable is set;
- removes the root in `finally`. Every log ends `exists_after False`, and `initialize` reported `museHome` inside the root.

1. **History before and after a manual compact.** Command: `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -e env -i PATH=/usr/bin:/bin /usr/bin/python3 -I <scratchpad>/muse-probe/probe_history.py <scratchpad>/muse-probe/out`. The script ran three `muse exec --provider echo --session-id <uuid7> --json -- "<prompt>"` turns. One `muse serve` then sent `initialize`, `initialized`, `session/read {excludeItems:false}`, `view/page {limit:1000, direction:forward}`, `session/resume {history:auto}`, `session/compact`, then `session/read` and `view/page` again. After that it ran a fourth exec turn, and a second serve sent `session/read` and `view/page`. Output:
   - `read1_before mode inline ... inline items 15` (3 `userMessage`, 3 `agentMessage`, 9 `reminderChild`);
   - `page1_before events 24 nextCursor None`, with 15 `item/completed`, 3 `turn/started`, 3 `turn/completed` and 3 `session/tokenUsage`;
   - `item/completed` params are `['item', 'sessionId', 'sourceRange', 'viewCursor']`, and `item` is the full `Item` (`itemId`, `kind`, `revision`, `status`, `text`, `turnId`, ...);
   - `compact {"error": {"code": -32030, "data": {"kind": "commandRejected", "reason": "compaction_unavailable", "retryable": false}}}`;
   - after the compact, the mode is still `inline` with 15 items; after turn four, `inline` with 20 items and 32 page events.
2. **Auto-compaction.** `probe_autocompact.py` ran four exec turns per strategy, with `--context-compaction-soft-threshold 0.001 --context-compaction-hard-threshold 0.002` and long prompts, then a batch serve `session/read` plus `view/page`.
   - `summary-preserved-suffix/v1`: mode `inline`, no `compaction` item.
   - Both prefix strategies: exit 2, "context compaction strategy `prefix-extension-summary/v1` is experimental; set MUSE_EXPERIMENTAL_PREFIX_COMPACTION=on".
3. **The same with the experimental flag.** `probe_prefixcompact.py` repeated the prefix strategies with `MUSE_EXPERIMENTAL_PREFIX_COMPACTION=on`. Result: exit 0, mode `inline`, no `compaction` item, for both strategies.

**Conclusion:** the echo provider cannot compact, so the anchored fold cannot be observed without a paid run. Per the briefing, the unverified part stays as a sharper A-28 tied to manual probe g. The `view/page` event shape (needed by the runner-up) is verified on 1.0.1.

### The decision (D-33)

- **Chosen: (a).** In `anchoredSnapshot` mode, read `history.snapshot.state.items` with the same loop as `snapshot` mode, through the same single `require(..., member=MUSE_READ_SKILL_ID_MEMBER)` call. The reasons:
  - It is the smallest rule: it deletes the export path, adds nothing, and leaves r4's own `item_calls` with no reason to exist.
  - It is sound in every case: an item in the server's fold is a call the model made, and text never counts.
  - It is complete under the schema's own words ("full folded state", "every item"), because the evidence call opens the run, before any boundary (`no_compactable_history` means a compaction needs earlier history).
- **Runner-up: (b),** paging `view/page` forward from the start through the same loop. It is correct by the view's contract, and its shape is verified. But it needs a new `MuseMethod` member, a page reader, a page cap and one serve child per page, because the batch serve exchange cannot carry a cursor into the next request. It also has its own truncation arms.
- **Rejected: (c),** parsing the export's `events`. Its tool-call event shape is unobserved, and the export is a debugging artifact, not an MSP contract.
- **Flip condition:** probe g shows an anchored `state.items` that lacks the run's early call. Then switch to (b).

### What changed in the spec

- **D-33** is rewritten.
- **A-28** is rewritten: the schema basis, what stays unverified (a pruned fold; a snapshot folded at the boundary), and that it fails closed.
- **INV-8, the TL;DR, §5 and §9.2** read the anchored state like a snapshot, with no export.
- **AC-34** now uses an MSP-shaped anchored stand-in, and asserts that no export child starts.
- **EC rows.** EC-79 and EC-83 are amended. EC-84 is rewritten for the A-28-false world. EC-85 and AC-35 lose the export-folder example.
- **§8.4** gets an r5 note: nothing is added, and the budget is unchanged.
- **§8.5:**
  - `MuseSessionWire.tool_calls -> tuple[NativeToolCall, ...]`, never `None`.
  - `MuseHelperRun.tool_calls` is listed with the same return type.
  - `item_calls` and `transcript` are removed.
- **§12.3 rows:**
  - Row 4: `MUSE_EXPORT_ITEMS_DETAIL` is withdrawn, and the exact new `MUSE_COMMAND_NOT_RUN` likely cause comes from §12.4.
  - Row 25: the anchored branch reads `state.items`; the new `@intent muse-anchored-snapshot-holds-every-item`; header updates.
  - Row 26: remove the `transcript` flow.
  - Row 27: four narrated steps, with no transcript and no JSON parse.
- **§12.4:**
  - The exact cause: "muse exec sends slash commands as plain text and the model did not call read_skill or create_goal, the thread's history could not be read back, or the run compacted and the history Muse served after the compaction lacks the call."
  - The no-export check.
  - The intent list.
- **§12.5 probe g** checks the anchored fold and prints the mode, the cursors and the item kinds.
- **§13** says what the stand-in must model, both for the anchored snapshot and for the real export's top-level members, and records the probe facts.
- **§16:** rows orch-1 (the rule), orch-2 (R-23's `member` kept, as the orchestrator accepted) and orch-3 (`base_commit`).
- **§17:** the r5 row.
- **Frontmatter:** `revision: 5`, `base_commit: 239c408a...` (verified with `git merge-base HEAD origin/main`; `git diff --stat 239c408a origin/main -- vidbyte/harnesses/native` is empty).
- **Unchanged:** R-5, R-6, R-7, R-8, R-16 and R-23.

### Least-sure assumptions now

- **A-28.** The real anchored fold keeps the items from before the boundary, and the evidence call sits at or before the snapshot cursor. This is unverifiable offline. If it is wrong, the run fails closed (EC-84) and D-33 flips to `view/page`.
- **A-17.** The `read_skill` argument is named `id`. This is unchanged; if it is wrong, every skill call fails closed.
- **The `view/page` shape for `toolCall`.** If the flip happens, (b) relies on a `toolCall` arriving as `item/*` with `params.item` in the shared `Item` schema. That is observed only for message items so far.

### Self-check results (r5)

- **Defined IDs:** G 4, NG 15, INV 29, AC 35, EC 85, FR 20, NFR 12, D 35, W 12, T 9, A 29, Q 8. No ID is new, renumbered or reused.
- **Tables:** 0 malformed rows. No ID is dangling; the KD-n IDs are the request's.
- **No tests:** the spec contains no test code.
- **Withdrawn names:** every mention of `item_calls`, `MUSE_EXPORT_ITEMS_DETAIL` and `transcript` outside §16/§17 is a withdrawal note. §8.5 lists none of them.
- **Budget:** still 47 functions, 68 exports, 10 new source files and 20 harness classes.
