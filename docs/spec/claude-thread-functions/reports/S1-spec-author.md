# S1 · Spec author report — claude-thread-functions r1

Stage: S1 spec author. Date: 2026-10-15. Output: `docs/spec/claude-thread-functions/spec.md` r1 (729 lines, 18 sections), committed as `6d2eaa48`. No production code, no tests, no `claude` run, no key spent, no push, no install.

## What I read

- Pipeline record: `request.md`, `pipeline.md`, `context/code-map.md`, `context/vendor-facts.md`, and `docs/spec/harness-thread-functions/spec.md` (#1036 r4: INV-1–INV-15, D-24, D-27, the row-36 flow and row-47 README text). I did not read `docs/spec/claude-host/`.
- Repo rules: `AGENTS.md` (principles 1–5, Placement Rules, `docs/` opacity, full-gate rule); `vidbyte/harnesses/README.md` (sections and the `native/` bullet); `REPO_MAP.md` lines 157–163; `vidbyte/lib/README.md` line 43.
- Code at `base_commit` `72a4ade1` and HEAD:
  - `vidbyte/harnesses/native/`: `__init__.py`; `grok/__init__.py`, `threads.py`, `wire.py` in full; `hostkit/__init__.py`, `errors.py` (factory API, `wrong_thread`, `listing`, `failure`), `launcher.py`, `skills.py` headers; the stdin and `env_remove` lines of `opencode/` and `muse/`.
  - `vidbyte/lib/`: `dataclasses/native_threads.py` (`NativeThreadRequest`, `GrokThreadConfig`); `dataclasses/process.py`; `dataclasses/validation.py` signatures; `enums/native_threads.py`; `enums/__init__.py` (at `72a4ade1`); `enums/failure.py` (at `72a4ade1`); `constants/native_threads.py` (bounds, tables, headers); `errors/base.py` (`NativeThreadError`); `process/runner.py` (environment, stdin, encoding); `process/argv.py`.
  - Lint: `lint/rules/a002_intent_comments.py`, `s020_readme_file_index_parity.py` header, and the rule list.
- Field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`: `review-scope.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `provider-api-contracts.md`, `comment-format.md`, `cli-backed-source-integrations.md`, `prebuilt-agents.md`, plus the lint and CI entries cited by the code map.
- Tests, for §13 facts only: `test_harness_threads_surface.py` lines 25–60; the conftest, fake harness and pin lines as cited by the code map.

## Approaches weighed

- **Chosen:** mirror #1036's Grok harness. Three modules (`claude/__init__.py`, `threads.py`, `wire.py`) on #1036's `CliRunner`, `CliArgv`, `NativeLauncher`, `NativeSkillFolders` and `NativeErrorFactory`. Each call runs one `claude --print --output-format json --setting-sources user --permission-mode … [--model] [--effort] [--resume id [--fork-session]]`. The prompt goes on stdin. The key goes only in `ANTHROPIC_API_KEY`. `CLAUDE_CONFIG_DIR` is a private per-workspace folder under `~/.vidbyte/claude-configs/`. The child drops every inherited `ANTHROPIC_*`/`CLAUDE*` variable except `CLAUDE_CODE_GIT_BASH_PATH`.
- **Smaller design rejected (§8.3):** set only `ANTHROPIC_API_KEY` and run `claude -p "<prompt>"` with the default config folder. It fails FR-7/INV-4, because a workspace `.claude/settings.json` can redirect, replace or run code with the key in `-p` mode (vendor-facts §8: e1, w1, k1, m1), and an inherited `ANTHROPIC_AUTH_TOKEN` is sent beside the key (a3). It also fails FR-8 (wrong skill set), INV-13 (it writes into `~/.claude`) and INV-5 (24,000-character argv cap).
- **Runner-ups recorded with flip conditions:**
  - one shared config folder instead of one per workspace (D-3);
  - `--setting-sources ""` with `--plugin-dir` per skill (D-4);
  - prompt on argv after `--` (D-5);
  - a fixed name list, or a new `env_remove_prefixes` option on `CliInvocation` (D-6);
  - `--session-id` minting (D-9);
  - `CLAUDE_CODE_MAX_RETRIES=0` (D-11);
  - permission value `manual`, and `--permission-prompts none` (D-12);
  - extra config fields (D-13);
  - lifting the workspace-key expression into hostkit (D-15).
- **Budget:** 3 new files, 7 new classes (3 flow, 1 record, 3 enums), 0 dependencies (−1 extra against HEAD), 0 config keys, 3 public functions.

## Disagreements with the request and the scouts (with evidence)

1. **request.md says #1036 is "still open", and KD-8 retargets #1044 to #1036's branch.** Superseded: `git log origin/main` shows #1036 as `f216fdcf`, and pipeline.md (2026-10-15 18:45) records the fact change. The spec keeps base `main` (D-21, NG-12, A-12). request.md is not edited.
2. **`origin/main` has moved since S0.** It is now `0754e01f` (#1095), not `72a4ade1`. ~~#1095 changed `vidbyte/lib/enums/__init__.py` (3 lines) and `llms.txt` (`git diff --stat 72a4ade1 origin/main`).~~ *Corrected in r2 (reviewer R-3):* that list came from a path-filtered diff. #1095 changed 41 files (`git diff --shortstat 72a4ade1 0754e01f`), among them root `vidbyte/__init__.py` (adds `SystemPromptPreset` to `__all__`), `contracts/sdk-public-api.json`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/README.md`, `README.md`, `llms.txt` and many `vidbyte/agents/**` files. It touches no file under `vidbyte/harnesses/` and none of the native-thread lib modules. Two consequences:
   - `git checkout origin/main -- <files>`, which `review-scope.md` and my own earlier notes suggest, would now pull #1095's enum change into a branch that lacks #1095's modules. ~~The spec says to restore from `72a4ade1` and never from `origin/main` (D-17, rows 1–7, §14).~~ *r2:* the spec restores from the merge base, `git merge-base origin/main HEAD` (`72a4ade1` until the catch-up merge), never from an unmerged `origin/main` tip (D-17, rows 1–7, §14).
   - The pipeline's niche fact "`git diff --stat origin/main HEAD` = 42 files, pure insertions" is true only against `72a4ade1`. Against today's `origin/main` the diff also shows #1095's files reversed.
3. **code-map.md header says HEAD `d8ef24f5` and merge base `77fef0e5`.** Both are stale after the second S0 merge: HEAD was `f6f8d546` (now `6d2eaa48`), and the merge base with main is `72a4ade1`. The code map's line numbers for files #1044 did not touch are still right.
4. **request.md §C constraint: "#1044's probe accepted only a native `claude.exe`".** The code map (note 8) already corrected this: #1044 also accepted `.com`. It does not matter here, because `NativeLauncher` refuses only `.cmd`/`.bat`, as for the other harnesses.
5. **Vendor scout, on `--resume`:** it takes a session id **or title** (p13). That is a hazard nobody flagged as a design input. The spec answers it with the lowercase-UUID `CLAUDE_THREAD_ID_PATTERN` on input and on Claude's answer (D-8, INV-5, EC-6).
6. **Pipeline niche fact "Child env must strip the parent's `CLAUDE_*` vars".** A blanket strip would also drop `CLAUDE_CODE_GIT_BASH_PATH`, which Windows users set when Git Bash is not in the default folder. The spec keeps that one name (`CLAUDE_INHERITED_ENVIRONMENT_KEPT`), under A-6 (from Claude Code's docs; not in vendor-facts).
7. **`pipeline.md` is modified in the working tree by the orchestrator, not by me.** I staged only `spec.md` and this report, by explicit path.

## Least-sure assumptions (in order)

1. **A-2:** the default permission mode denies, rather than waits, in a headless run. Not probed, because the stand-in never returned `tool_use`. If wrong, default-mode runs time out, and the D-12 flip adds `--permission-prompts none`.
2. **D-15:** repeating Grok's one-line workspace-key expression instead of lifting it into hostkit. AGENTS.md principle 5 and the hostkit header ("Plumbing that a second harness needs goes here") point the other way. I chose not to edit #1036's merged Grok module. A reviewer may reasonably flip this.
3. **A-3:** real-API status codes (401/403 → key rejected) are known only from the stand-in.
4. **A-5:** non-ASCII prompts on stdin on Windows. Verified on argv only.
5. **A-4:** session ids are always lowercase UUIDs.
6. **T-2 residual:** the model's own Bash commands see the key in the child's environment. This is accepted as the same exposure as #1036's harnesses; optional Q-7.

## Open items

- Blocking questions: none. Non-blocking: Q-1 (one-record signature for all four harnesses, default no), Q-2 (workspace `CLAUDE.md`), Q-3 (`--session-id` minting), Q-4 (no retries), Q-5 (more config fields), Q-6 (transcript retention), Q-7 (key out of tool subprocesses). All default "no".
- `failure.py`'s header asks for docs for new codes. Following #1036, which added 28 codes without them, the docs are not updated (NG-11, §12.4).
- S2 must also repair the surface pin `len(main_members) == 120` (line 193), which already fails on `base_commit`.

## Revision r2 (review round 1, 2026-10-15)

The spec moved to revision 2 in commit `198eefdf`; `status` stays `draft`. Input: `reports/S1-spec-review.md` (verdict SOUND WITH FIXES: 1 Blocker, 5 Major, 5 Minor). I accepted all eleven findings. §16 of the spec holds the full log.

| ID | Severity | Disposition | Change |
|---|---|---|---|
| R-1 | Blocker | accepted | AC-3 no longer accepts an upper-case continue id. INV-12: a different valid id is `thread_not_found`, and an id outside the pattern (upper case included) is `protocol_mismatch`. AC-13 covers upper case. §13 says the stand-in's `continue_upper_id` mode is Grok-only (`test_harness_threads_threads.py:137-142`) |
| R-2 | Major | accepted | §12.4 has an S008 zero-headroom line with the check `python -m ruff check vidbyte/harnesses/native --isolated --select C901,PLR0912,PLR0915`, and lists the other zero-headroom ratchets. In row 20, both problem choices are conditional expressions, and the exit-0 checks move into the leaf `ClaudeWire._missing_member` |
| R-3 | Major | accepted | Every byte-identity rule (INV-19, INV-20, INV-22, AC-20, NFR-2, rows 1–7, §12.4, §12.6 P1, §14) compares with `git merge-base origin/main HEAD`. D-17 restores from the merge base. §9.4 puts the catch-up merge before the S3 push, as pipeline.md does. The #1095 claim above is corrected |
| R-4 | Major | accepted | New `vidbyte/harnesses/native/hostkit/folders.py` with `NativePrivateFolders.prepare` (row 32), exported from hostkit (row 22, now P3 code). `_prepare_config` is removed. The templates use Grok's fields, so the failure template uses `{home}`. Grok is not switched (NG-13) |
| R-5 | Major | accepted | EC-20, D-12, README row 29 and AC-23 state what each mode allows headless: only `ACCEPT_EDITS` widens anything, and only to file edits and common filesystem commands. A-2 is confirmed by the headless docs. The timeout branch and D-12's flip are dropped |
| R-6 | Major | accepted as a new documented risk | EC-37, D-22, A-14 and optional Q-8 [scope-adding], default no. INV-14 now says it covers skills and workspace files only. §9.1, EC-8, EC-28, NG-10, the T-2/T-3 residuals and the rollback text are updated |
| R-7 | Minor | accepted | INV-21 now uses §8.5 order, INV-13 cites EC-31, and EC-36 drops `true` |
| R-8 | Minor | accepted | Row 33: a header-only change to `vidbyte/lib/dataclasses/validation.py` line 4 |
| R-9 | Minor | accepted | §12.5: the IMPROVED results are pre-existing, and `--update-baseline` is not run. §14 Never lists it |
| R-10 | Minor | accepted | T-6 gets an unverified residual, plus A-15 and optional Q-9 [scope-adding] (`NoDefaultCurrentDirectoryInExePath=1` on win32), default no |
| R-11 | Minor | accepted | Q-1 states readings (a) and (b) with the #690→#747 precedent; the default is unchanged |

**R-6 reasoning (scope rule):** I judged the finding against the settled design, not as a broken invariant.
- Auto memory is not a credential, so INV-3 and INV-4 still hold.
- It is not a skill or a workspace file, so INV-14 still holds once its scope is stated.
- Every thread can already read the workspace's own files, so memory adds persistence, not a new channel.
- Nobody asked for a switch. The memory switch therefore stays an optional Q-8 with default "no", and the behaviour is documented as an accepted limitation (EC-37).

**Probes not run.** The reviewer suggested two stand-in probes: R-6 (seed `MEMORY.md` and inspect the request body) and R-10 (a workspace `git.exe` marker with `claude -p`). Both start `claude`, which this stage forbids. They are recorded as A-14 (docs only) and A-15 (not probed).

**Changed design sections:**
- §8: D-2, D-12, D-15, D-17, D-22, and the §8.4 budget (3 → 4 files, 7 → 8 classes).
- §8.5: `NativePrivateFolders.prepare` and `ClaudeWire._missing_member` added; `ClaudeThreadRun._prepare_config` removed; the `{home}` template.
- §9: §9.1 memory and §9.4 merge timing.
- §10: T-2, T-3, T-4 and T-6.
- §12: new rows 32 and 33, row 22 is now a P3 code change, restores are from the merge base, and the P3/P4 row sets and dependency order changed.

**Not edited (orchestrator files):** pipeline.md, request.md, code-map.md and vendor-facts.md. My r1 note about stale facts in code-map.md and pipeline.md still applies.

## Revision r3 (review round 2, final, 2026-10-15)

The spec moved to revision 3 in commit `66203747`, and `status` is now `approved` (review cap 2/2 reached). Input: `reports/S1-spec-review-r2.md`, committed with the spec (verdict SOUND WITH FIXES: 0 Blocker, 3 Major, 1 Minor). I accepted all four findings. §16 of the spec holds the full log.

| ID | Severity | Disposition | Change |
|---|---|---|---|
| R-12 | Major | accepted (the orchestrator chose to switch Grok) | New row 34 changes Grok's `execute` step 2 to call `NativePrivateFolders.prepare` with Grok's existing constants. The same row deletes `_prepare_home` and the imports only it used (`hashlib`, `os`, `NativeSkillFolders`, `NativeThreadProblem`). NG-13 is withdrawn and struck through. D-15's runner-up (b) is now the decision. INV-20 says Grok's behaviour is unchanged. Rows 22, 25 and 32, §2, §8.2, §9.4, §11, §12.2, §12.6 and the §14 exception were updated. The §8.4 counts stay the same |
| R-13 | Major | accepted | The new leaf `ClaudeWire._text` is added. `read` narrows the answer with `if answer is None`, then one combined `if` that covers `is_error`, `session` and `text`, and the error names the missing member via `_missing_member(answer, session, text) -> str`. `_error_text` lists `errors` only when it is a `list`. Row 20 now states the typing rule, and §12.4 checks S009 (no more than 350). C901 stays at 8 |
| R-14 | Major | accepted (text only) | FR-3 now promises only that the source's transcript is unchanged. EC-37, A-14 and §9.1 now give the memory path as named after the workspace's git repository, and say a fork's notes reach its source. D-6 and EC-37 say the SDK drops an inherited `CLAUDE_CODE_DISABLE_AUTO_MEMORY`. D-22 is qualified. T-4 now names the store shared by every caller of a workspace path. Q-8 is restated with its stakes. README row 29 and AC-23 were updated |
| R-15 | Minor | accepted | Row 23's comment no longer says Claude folds the case of ids. Row 32 now uses absolute imports, and §12.4 has an S040 line |

**R-14 invariant check:** No stated invariant breaks, so Q-8 stays optional with default "no".
- INV-3, INV-4 and INV-14 still hold.
- INV-12 governs only thread ids.
- KD-5, the user's "copy, run, new id", still holds.
- Only FR-3's "the source is unchanged" was too broad. That was my reading of p06, not the user's words, and it is now narrowed.

**Facts carried into the spec:**
- S040 bans relative imports.
- Ruff's C901 counts only `if` statements.
- `NativeErrorFactory.failure(thread_id=None)` falls back to `request.thread_id`.
- `--resume` also accepts a path to a transcript `.jsonl` file. The UUID pattern blocks this (D-8).
- Piped stdin is capped at 10 MB. The 200,000-character cap is at most 800,000 bytes, so it fits (D-5).
- I re-read the Claude Code cli-reference, headless and memory docs on 2026-10-15 to confirm these quotes. I ran no `claude`.

**Changed design sections:**
- §8: D-5, D-6, D-8, D-15 and D-22; NG-13 withdrawn.
- §8.5: `_text` added, and the signature of `_missing_member` changed.
- §9: §9.1 (memory path) and §9.4 (`_prepare_home` removed).
- §10: T-4.
- §12: new row 34, rows 20, 22, 23, 25, 29 and 32, new §12.2 Grok row, §12.4 S009 and S040 lines, and the P3 order.
