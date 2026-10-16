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
