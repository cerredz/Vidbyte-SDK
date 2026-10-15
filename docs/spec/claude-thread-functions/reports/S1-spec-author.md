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
2. **`origin/main` has moved since S0.** It is now `0754e01f` (#1095), not `72a4ade1`. #1095 changed `vidbyte/lib/enums/__init__.py` (3 lines) and `llms.txt` (`git diff --stat 72a4ade1 origin/main`). Two consequences:
   - `git checkout origin/main -- <files>`, which `review-scope.md` and my own earlier notes suggest, would now pull #1095's enum change into a branch that lacks #1095's modules. The spec says to restore from `72a4ade1` and never from `origin/main` (D-17, rows 1–7, §14).
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
