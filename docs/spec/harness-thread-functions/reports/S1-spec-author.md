# S1 spec author — harness-thread-functions r1

Date: 2026-10-15. Branch `feat/native-grok-opencode-meta-hosts`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-functions`. Output: `docs/spec/harness-thread-functions/spec.md` (revision 1).

## 1. What I read

- **Briefing and pipeline:** the S1 launching prompt; `spec-template.md`; `docs/spec/harness-thread-functions/request.md` (§A owner prompts and the four review comments, §B prior work, §C state of the branch, §D weighted words); `context/code-map.md` (§1 commands and lint, §2 PR files, §3 test packs); `context/vendor-facts.md` (all three harnesses, GLM/DeepSeek routes, gaps 1–15). Old spec `docs/spec/native-grok-opencode-meta-hosts/` only by section (request and spec headers), as allowed.
- **Repo rules:** `AGENTS.md` in full; `REPO_MAP.md` entries for `vidbyte/harnesses/native/` and `vidbyte/lib/process/`; `vidbyte/harnesses/README.md` and `vidbyte/lib/README.md` (`native/` and `process/` bullets).
- **Lint rule sources:** C012 (provider/model registry), S052, S054, A001 REQUIRED_FIELDS, and the A007 summary.
- **Field guide** (`field-guide/vidbyte-sdk/`): `review-scope.md`, `cli-backed-source-integrations.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `blocking-lint-invariants.md`, `diagnostic-context.md`, `comment-format.md`, `provider-api-contracts.md`, `prebuilt-agents.md`, `local-ci-verification.md`, `model-facing-tool-contracts.md`.
- **Branch code read for the design:**
  - Grok: `grok/{cli,host,wire}.py`.
  - opencode: `opencode/wire.py` (failure parsing).
  - Muse: `muse/{launcher,wire}.py`.
  - hostkit: `hostkit/{errors,peers}.py`.
  - `backends/__init__.py` (class-bound pattern).
  - lib records, enums, constants and errors: `lib/dataclasses/{process,validation,native_hosts}.py`, `lib/enums/{failure,native_hosts,process}.py`, `lib/constants/native_hosts.py`, `lib/errors/base.py` (`NativeHostError`).
  - lib process: `lib/process/runner.py`.
  - Main precedents:
    - `vidbyte/lib/dataclasses/coding.py` (key field rules);
    - `vidbyte/lib/constants/coding.py` and `vidbyte/agents/coding_context/progress_notes.py` (`.vidbyte/<tool>/.gitignore`);
    - `vidbyte/lib/enums/codex.py` and `vidbyte/lib/constants/codex.py` (wire enums, constants importing enums);
    - `vidbyte/lib/util/credential_keys.py`;
    - `vidbyte/harnesses/serialization.py`.
- **Vendor source:** opencode 1.18.31 `run.ts`, saved to the scratchpad: `resolveRunInput`, `--dir`, the `-s` "Session not found" path, `--fork`, `emit`, and the error events.

## 2. Approaches weighed

- **Chosen (D-1): one bounded headless CLI run per thread operation** through the branch's existing `CliRunner`: `grok --single`, `opencode run`, `muse exec`. Muse continue and fork add one batch `muse serve` exchange. Every vendor already offers run, continue and fork headless with JSON output, so the hosts, stdio peers, HTTP server, turn table and transport extension all go. The result is 24 added Python files versus main, against 56 today.
- **Runner-up: keep the host classes behind thin `<verb>_<h>_thread` wrappers.** Rejected because it keeps about 11.7K lines and live peers, against "simply" and `review-scope.md`.
- **Smaller design rejected (§8.3): only the three named functions, setting only the vendor's key variable.** It fails on any machine with a stored login: Grok's `auth.json` and opencode's `auth.json` both outrank the environment key (vendor-facts Grok Q2, opencode Q2), so the run bills someone else's account. It also drops skills (named in the owner's one signature), continue and Muse.
- **Reading keys from the user's environment:** rejected by KD-2.
- **Skills:** a private `GROK_HOME` with copied skills versus the workspace's `.agents/skills`. The private home was chosen because it is also needed to make the caller's key win, and it keeps the user's repo clean (one ignored `.vidbyte/grok/`).
- **Argv style:** one joined style for every harness was impossible. Muse rejects `--name=value` (probe below), so the builder takes a per-harness `CliOptionStyle`.
- **Failure codes:** keep 53 versus a closed 28 = 9 problems × 3 harnesses + `muse.wsl_unavailable`. Each of the 28 has a reachable path, a written likely cause and a next step.
- **Grok model check before each run:** needs an ACP peer, so it is not built (EC-25, Q-3).

## 3. Probes run (all free: no model call, no valid key, no login written) and side effects

| # | Probe | Result | Used in |
|---|---|---|---|
| 1 | `grok --help` (1.0.52) | flags `-p/--single`, `--output-format`, `--permission-mode` (6 values), `-r/--resume`, `--fork-session`, `-s`, `--cwd`, `-m`, `--reasoning-effort`; `--name=value` accepted | D-12, §9.2 |
| 2 | `grok inspect --json` with a private `GROK_HOME` holding `skills/<n>/SKILL.md` | the skill is listed as source "user"; an empty `GROK_HOME` does not block headless runs | D-7, INV-12 |
| 3 | `grok -p … ` with an invalid `XAI_API_KEY` and a private home | stdout `{"type":"error","message":"Not signed in. …"}`, stderr "Error: Not signed in…", exit 1 | INV-6 key_rejected, EC-9 |
| 4 | `grok --resume=<unknown uuid>` with an invalid key | the same "Not signed in": auth is checked first, so unknown-session text is not observable without a valid key | A-2 |
| 5 | Grok's writes into the private home | README.md, agent_id, config.toml, docs/, installed-plugins/, logs/, sessions/, skills/; Grok does not add skills itself | INV-12, INV-13 |
| 6 | `OPENCODE_CONFIG_CONTENT={"skills":{"paths":["<skill folder itself>"]}}` + `opencode debug skill` | the skill is listed: passing the folder itself works | D-7 |
| 7 | `OPENCODE_CONFIG_CONTENT={"provider":{"zai-coding-plan":{"options":{"apiKey":"dummy"}}}}` with no `ZHIPU_API_KEY`, then `opencode models zai-coding-plan` | the models are listed (without it: "Provider not found"), so a config `apiKey` alone enables a built-in provider | D-6, D-8, FR-8 |
| 8 | Muse 1.0.1 `exec --json --provider echo` in WSL (`MuseUbuntu1`, isolated XDG dirs, `MUSE_NO_AUTO_UPDATE=1`) | JSONL with `stream.id` = session id; success ends `payload_type: run.terminal.completed`, `payload.text`; `task.lifecycle.failed` records appear even on success | D-21, §9.2 (closes vendor-facts gap 10) |
| 9 | `muse exec --session-id <unknown>` | silently creates a new session, exit 0 | D-17, INV-11, EC-19 (closes gap 13; harmful) |
| 10 | Muse with missing credentials, then an invalid `META_API_KEY` | exit 1, "missing meta credentials…" / "failed to fetch model catalog: authentication failed: your API key from META_API_KEY was rejected…" | INV-6 key_rejected |
| 11 | `muse exec --provider=echo` | "unknown option --provider=echo", exit 2: Muse refuses joined options; `-- <prompt>` works for flag-like prompts | D-12, INV-7 |
| 12 | Batch `muse serve` over stdin: `initialize`, `initialized`, `session/read {excludeItems:true}` then EOF | known id → result with `session{…, status:"notLoaded"}`; unknown → error `-32020`, `data.kind:"sessionNotFound"`; exits 0 at EOF; no credentials needed | D-17, §9.2 |
| 13 | Batch `muse serve` `session/fork {commandId, sessionId, excludeItems:true}` | new id at `result.session.sessionId`, `forkedFrom` set; unknown → `-32020` | D-9 |

**Side effects:**
- WSL `/tmp/vbprobe/` in distro `MuseUbuntu1`: isolated Muse config and data, probe outputs, and the echo-provider sessions plus one fork session.
- Scratchpad `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\4ff2472d-322f-4998-ab71-29f9489aa59a\scratchpad\`: `grokhome/`, `grokws/`, `grok_*.txt`, `grok_debug.log`, `grok_resume_out.txt`, `grok_resume_err.txt`, `oc_skill_folder.txt`, `oc_skill_parent.txt`, `run.ts`, `muse_probe2.sh`, `muse_probe3.sh`, `muse_probe4.sh`, `msp_fork_frames.jsonl`, `out2.jsonl`, `out5.jsonl`, `serve_out.jsonl`, `s1_prompt.txt`, `s1tools/depath.py`.
- One stray copy of `msp_fork_frames.jsonl` in `C:\Users\422mi\AppData\Local\Temp\` was deleted.
- Nothing was written to `~/.grok`, `~/.config/opencode`, the user's Muse folders or any repository file other than the spec and this report.
- No installs, no gate runs, no test runs.

## 4. Disagreements with the scout, the request or the rules, with evidence

- **Muse unknown session id (vendor-facts gap 13, "strongly implied"):** confirmed, and it matters more than the scout's note suggests. `exec --session-id <unknown>` silently creates and bills a new thread (probe 9). The spec adds a batch `session/read` pre-check (D-17), and the probe shows it needs no credentials (probe 12).
- **Muse `exec --json` schema (gap 10):** closed by probe 8. One surprise: `task.lifecycle.failed` records appear on successful runs, so the codec decides only from `run.terminal.*`.
- **Comment 3's "for all providers":** one joined `--flag=value` form cannot serve all three, because Muse refuses it (probe 11). The canonical builder takes a style per harness rather than forcing one form.
- **Field guide `review-scope.md` says "start a fresh branch from origin/main"; KD-6 says update PR #1036 in place.** KD-6 wins as the user's decision. The guide's intent is kept: every file of the rejected design is deleted, and the PR body reports the before/after `--stat` (§11 Conflicts, §12.5).
- **Model on the config records:** the PR put `model` on request records, not settings. Lint C012 would flag a `model` field on a `*Config` record unless it is proven against `ProviderModelRegistry`, and vendor-CLI model ids are not in that registry. So `model` stays a per-call argument on `NativeThreadRequest` (D-5), and no lint exemption is requested.
- **`vidbyte/lib/dataclasses/validation.py` header and `NativeHostError.related_docs` point into the old spec folder,** which D-19 deletes. Rows 24 and 26 rewrite them.
- **No disagreement with the request's scope.** Everything in §12.3 traces to request §A–§C, the orchestrator decisions (KD-1…KD-9, removals) or a cited rule. New behavior that is not a control:
  - auto-update off (INV-17, vendor SDK practice);
  - `--user-input-auto-resolve` (D-14, the vendor's own headless switch, so a run cannot hang on a question);
  - the Muse pre-check (EC-19, prevents a silent wrong-thread bill).

  Every candidate control (edit-by-default, sync wrappers, Grok model check, opencode/Muse permission knobs, tools, workspace trust, private-home location) is an optional Q with default no (Q-1…Q-7).

## 5. Least-sure assumptions (ranked)

1. **A-1:** the Grok 1.0.52 JSON success shape (`text`, `sessionId`) comes from the vendor doc and the 1.0.13 research. It was not run with a valid key. If wrong, every Grok success reads as `grok.protocol_mismatch`; the fix is a member-name constant.
2. **A-3 / A-12:** headless approval behavior under the vendor defaults (Grok `default`, Muse `on-request` with the judge). If either blocks, runs end at `timed_out` and Q-1 becomes urgent.
3. **A-2:** Grok's answer to `--resume=<unknown>`. If Grok silently starts a new session, `fork_grok_thread` of an unknown id returns a fresh thread, and a Grok pre-check is needed (D-17 flip).
4. **A-8:** that opencode's final answer is the `text` parts sharing the last `part.messageID`. Not run with a valid key.
5. **A-9:** that opencode accepts `--name=value` for every flag used (yargs). Only Grok's joined form was probed. If wrong, change opencode to `SEPARATE` style, a one-argument change.
6. **A-6 / EC-37:** with a private home, Grok may still load the user's HOME skill folders, and opencode does load its global skills. This is documented as an accepted limitation; no control was added.

## 6. Stage E self-check

- **FR traces:** every FR traces to an INV or an AC. FR-17 traces to AC-20 (added in the self-check).
- **AC traces:** every AC traces to a W row or a §12.3 row.
- **§12.3 coverage:** every row names FR/NFR/W. The 68 non-doc PR files plus the old spec folder each appear in exactly one row (49 rows).
- **Guards:** every EC has an INV or D, or is marked an accepted limitation (EC-25, 26, 27, 28, 34, 36, 37). Every T has a control (T-4 is N/A, with the reason given).
- **Names:** the names in §4 are a subset of §8.5, and each §8.5 symbol has a §12.3 row.
- **Budget:** 24 added Python files versus main and 9 new paths versus the branch head. Both match §8.4 (4 `git mv` + 5 creations).
- **Standards:** every §12.3 row names a governing standard, and §12.4 has an obligation for each kind of file.
- **Weighted words:**
  - "simply": NFR-1.
  - "each": FR-2.
  - "only … definately": INV-1/FR-1.
  - "optimally": D-1/NFR-6.
  - "all of these": INV-15.
  - "much more detail": INV-5/NFR-7.
  - "all providers": INV-14/INV-16.
  - "every single function": FR-10.
- **Commands:** §11 commands are copied from code-map §1.2 and AGENTS.md.
- **No test cases:** §13 holds facts only.
- **Paths:** file paths appear only in §11, §12, §13 (the test files the briefing asks for) and §14 (the worktree); §8 uses module names.
- **Rows by section:** FR 17, NFR 7, INV 23, AC 20, EC 37, D 24, T 5, W 11, A 18, Q 7 (0 blocking).

---

## Addendum — r2 (S1 review round 1, 2026-10-15)

**Input:** `reports/S1-spec-review.md`, verdict SOUND WITH FIXES (1 Blocker, 8 Major, 4 Minor), read in full. All 13 findings were **accepted**. None was rejected, and none reverses a KD. R-7 was carried as a question (Q-8) instead of a silent rename. Each disposition is in spec §16.

### Changes per finding

- **R-1, Blocker.** The Grok private home moves from `<workspace>/.vidbyte/grok` to `~/.vidbyte/grok-homes/<first 16 hex chars of sha256(normcase(resolved workspace))>` (D-24 flipped, INV-13 replaced, Q-7 settled).
  - Why: Grok trusts everything under `GROK_HOME` as user scope without a prompt (its `config.toml` endpoints, hooks, plugins and `auth.json`). A home inside a cloned repo would let the repo steal or redirect the key, or run code.
  - Still holds: KD-2's invariant, since the private home holds no stored login. continue and fork still find the thread, because the key is a stable function of the workspace.
  - No SDK write into the workspace remains, so the `.gitignore` handling is gone.
  - Added T-6 (malicious workspace content) and EC-42 (the workspace contains the user home).
- **R-2.** D-25: the key must match `^[!-z|~]+$`, which is printable ASCII without space, `{` or `}`. This refuses opencode `{env:…}`/`{file:…}` substitution tokens and NUL. EC-1 and AC-5 widened, and EC-38 added. The `{env:VAR}` indirection was not taken, because whether opencode substitutes a second time is unverified.
- **R-3.** Every enum in `native_threads`, and `CliOptionStyle`, is now a `StrEnum`. INV-16 now requires plain `str` argv and environment entries, and row 29 emits `str(member)`.
- **R-4.** AC-12 no longer expects a Muse batch file on PATH to be refused; the batch file is passed through `muse_command`, and the user home is redirected. §13 names `Path.home()` (`USERPROFILE`/`HOME`) as a seam tests must redirect, so no test can reach the real `C:\Users\422mi\.grok\bin\grok.exe`.
- **R-5.** §12.6 now requires that after every phase `python -c "import vidbyte, vidbyte.harnesses.native"` works.
  - P1 removes the `harness_backends` enum import and the `ManagedProcess` export in the same commits that delete those modules.
  - P1 also cuts the five native `__init__` files to empty exports.
  - P2 is a single commit, and row 21 is now in its order. §14 adjusted.
- **R-6.** INV-15 is now two `ast` rules: what the module level may hold, and which constants may appear (docstrings, `__all__` strings, `""`, 0, 1, `None`, `True`, `False`). AC-14 names the scan. The factory takes observations as keyword arguments, and `NATIVE_LINE_SEPARATOR` was added.
- **R-7.** Q-8 (non-blocking): `*_muse_thread` or `*_meta_thread`? The default stays `muse`, with D-3's reasoning written out.
- **R-8.** `NativeSkillFolders.replace` does nothing when the folder already holds the same skills with identical files (`filecmp`, `shallow=False`). EC-27 now states the real failure (a spurious `launch_failed`, or a skill lost mid-run) as an accepted limitation. No locking added.
- **R-9.** A-19 to A-23 added. `MUSE_AUTH_PATH` is now set to a never-created file inside the temp folder (INV-3, D-6, §9.2, §9.3, the enum, row 44). FR-8 is narrowed to API-key providers, plus EC-39.
- **R-10.** D-26: workspace and skill paths are stored as `Path.resolve()`; EC-40 added.
- **R-11.** NFR-2 lets `vidbyte.lib.constants.native_threads` reach 1,000 lines, and the implementer stops BLOCKED beyond that.
- **R-12.** §12.5: this run's `docs/spec/harness-thread-functions/` is KEPT as the design record, because the pipeline reads the spec from the branch at S6–S7. It gets its own line in the PR-body stat.
- **R-13.** INV-5: a failure carries the newest thread id learned (the fork's new id, or the first id in a cut stream). Rows 32, 40 and 44 updated, and AC-21 added.
- **Author addition (not from the review).** opencode merges a workspace `opencode.json` below `OPENCODE_CONFIG_CONTENT`, so a repo-set `baseURL` combines with the SDK's `apiKey`. This is R-1's analogue, but vendor-native: running `opencode run` in that folder yourself has the same exposure. Recorded as T-6(b) and EC-41, with Q-9 (`OPENCODE_DISABLE_PROJECT_CONFIG=1`, default no, scope rule 9).

### New probe (free: echo provider, no credential, no model call)

**Probe 14:** `muse_probe5.sh`, run in WSL `MuseUbuntu1` with `XDG_DATA_HOME=/tmp/vbprobe/data`, `MUSE_NO_AUTO_UPDATE=1` and `META_API_KEY` unset. Each step used a fresh `mktemp -d` config folder.

| Step | Config | Action | Result |
|---|---|---|---|
| 1 | A | `exec --json --provider echo` | session `01a13ed4-f936-7f70-8e10-0a559afb597d`, `run.terminal.completed` |
| 2 | B | `exec --session-id <that id>` | exit 0, same `stream.id`, `run.terminal.completed` |
| 3 | C | batch `muse serve` `session/fork {excludeItems:true}`, no credential | exit 0, new id `01a13ed4-fc64-79a2-8532-b4ee8f27e8ff`, `forkedFrom.sessionId` = source, cut at turn 2 |
| 4 | D | `exec --session-id <new id>` | exit 0, same new `stream.id`, `run.terminal.completed`, `text` "echo: third" |
| 5 | C | `session/read` of the source | `providerId` "echo", `turnCount` 2 |

- No step printed a "refusing"/"identity" line.
- All four config folders were empty afterwards: Muse keeps sessions under `XDG_DATA_HOME`, and wrote nothing to `XDG_CONFIG_HOME`.
- Verbatim terminal record from step 4: `{"schema_version":1,"id":"018f0000-0000-7000-8000-000011e26695","stream":{"kind":"session","id":"01a13ed4-fc64-79a2-8532-b4ee8f27e8ff"},"sequence":36,"recorded_at":1780531700000069,"record_type":"event","durability":"durable","causation_id":"a2ae9853-9402-4fc7-9685-ef5a14d15271","payload_type":"run.terminal.completed","payload_schema_version":1,"payload":{"command_id":"a2ae9853-9402-4fc7-9685-ef5a14d15271","kind":"run_terminal","reason":null,"run_stream":{"id":"a2ae9853-9402-4fc7-9685-ef5a14d15271","kind":"run"},"terminal":"completed","text":"echo: third"}}`

**What it settles:** R-9(b) and R-9(e) are VERIFIED for the echo provider (A-20, A-23). They are still unverified for provider `meta`.

**Side effects:** WSL `/tmp/vbprobe/p5/` (o1, o2, o4 JSONL, s3 serve output, e1–e4 stderr); two new echo sessions and one fork under `/tmp/vbprobe/data`; temp config folders removed. Scratchpad: `muse_probe5.sh` and `s1tools/r2_part1.py`, `r2_part2.py`, `r2_part3.py` (edit scripts).

### Not done, outside S1's write set

The review asks that the probe evidence for R-9(b) and R-9(e) be copied into `context/vendor-facts.md`. S1 may write only the spec and this report, so the evidence is in spec A-20, A-23 and above, and the copy is left to the orchestrator.

### Stage E self-check (r2)

- **IDs:** contiguous, none renumbered. INV 1–23, AC 1–21, EC 1–42, FR 1–17, NFR 1–7, D 1–26, T 1–6, W 1–11, A 1–23, Q 1–9 (0 blocking).
- **Guards:** every new EC is guarded or accepted. EC-38 → INV-4/D-25; EC-39 → accepted (A-22); EC-40 → INV-18/D-26; EC-41 → accepted (T-6, Q-9); EC-42 → accepted (INV-13).
- **Coverage:** the new AC-21 traces to INV-5 and rows 32, 40 and 44. T-6 names its controls.
- **Budget:** no new file, class or enum, so §8.4 is unchanged. The only addition is stdlib `hashlib`/`filecmp`/`os`.
- **Contract:** the §4 and §8.5 public names are unchanged. The `NativeEnvironmentVariable` member `MUSE_AUTH_PATH` was added, and the enums became `StrEnum`.
- **No stale text:** no reference to the r1 in-workspace home remains outside D-24's runner-up, INV-13's revision note, Q-7 and §16.

### Least-sure points after r2

- A-20 and A-23 for provider `meta`.
- A-19: the first Grok run in an empty home after a successful sign-in.
- A-22: opencode providers that sign in through a plugin.
- Whether the owner prefers `meta` (Q-8).
- Whether the owner wants Q-9's opencode project-config switch, given the documented key-exposure risk.

---

## Addendum — r3 (S1 review round 2; approved, 2026-10-15)

**Input:** `reports/S1-spec-review-r2.md` (committed at 1df20485), verdict SOUND WITH FIXES (2 Blocker, 3 Major, 3 Minor), read in full.
- All of R-14 to R-21 were accepted; none was rejected and none reverses a KD.
- The round-1 partials (R-10, R-13) are recorded in §16 as completed through R-14 and R-18.
- Following the coordinator's instruction, the spec is now `status: approved`, revision 3. The review cap of two rounds is reached.

### Changes per finding

- **R-14, Blocker.** §9.1, D-26 and row 28 now run `to_path`, then `require_directory` on the path as given (absolute and existing), then store `Path.resolve()`. Skill paths follow the same order. A relative workspace is refused again, as EC-2 and AC-5 require.
- **R-15, Blocker.**
  - `NATIVE_PROCESS_FLAG_PATTERN = ^-[^\s=]*$`, because the r1 `^-` under `re.fullmatch` accepted only "-".
  - §9.1 now says every pattern is applied with `re.fullmatch`.
  - The prompt and option-value patterns are spelled out as whole-value patterns (`[^\x00]+`, `[^\x00]*`).
  - I re-checked every other §9.1 pattern against full-match; each already describes the whole value.
- **R-16.** Added EC-43 (per-workspace homes grow and are never pruned) as an accepted limitation, with a README sentence. Added A-24, the fresh-home footprint: 976 KB measured from the r1 probe home, with `docs/` 748 KB, `README.md` 112 KB, `logs/` 72 KB and `sessions/` 36 KB. The signed-in footprint is unverified. D-24's runner-up is now one shared home, with its cost (the skills race spans every workspace) and its flip condition. Q-10 covers a bound on growth, default not built (scope rule).
- **R-17.** "Except EC-42" added to INV-12, AC-3 and AC-19. §13 now requires the redirected home and the workspace to be sibling temporary folders.
- **R-18.**
  - INV-5 now says plainly that Grok's id is known only at exit.
  - Row 43 takes the first record whose `stream.kind` is `session`, before the runner checks; this adds the constant `MUSE_SESSION_STREAM_KIND`.
  - AC-21 now covers a timed-out `run_muse_thread`.
  - New D-27 records the rule. Its runner-up is minting Grok ids with the documented `--session-id`, which is unverified together with `--fork-session`.
- **R-19.** AC-16 now proves the no-op by the copied `SKILL.md` keeping its `st_ino`, because `copytree` copies modification times.
- **R-20.** Added EC-44: SDK Grok runs ignore `~/.grok` permission rules, hooks and admin policy files. It is an accepted limitation with a README sentence, and Q-11 offers copying them (default no). EC-14 and row 36 map a `Path.home()` `RuntimeError` to `grok.launch_failed` with a next step; the step-1 launcher fallback is skipped in that case.
- **R-21.** §8.2 and D-11 now say `StrEnum`, and `ProcessLaunchFailure` is re-declared `StrEnum` (row 20, §8.5). Q-9 states its coverage, and A-25 records that `.opencode/` folders may not be covered.
- **Coordinator request.** §15 opens with "Vendor facts this spec settles". It lists vendor-facts gaps 10 and 13, Muse resume and fork across config folders, the `--name=value` refusal and the -32020 answers, each with its probe. A-20 and A-23 say the spec is authoritative over vendor-facts on those points. vendor-facts.md is not edited.

### Probes

No new probe. A-24 uses the measurement of the r1 probe home: `du` of the scratchpad `grokhome/`, a read-only command.

### Stage E self-check (r3)

- **IDs:** contiguous, none renumbered. INV 1–23, AC 1–21, EC 1–44, FR 1–17, NFR 1–7, D 1–27, T 1–6, W 1–11, A 1–25, Q 1–11 (0 blocking).
- **Guards:** the new EC-43 and EC-44 are accepted limitations tied to D-24 and Q-10/Q-11.
- **Coverage:** the new D-27 is cited by INV-5. The new constants (`MUSE_SESSION_STREAM_KIND`, `NATIVE_PROMPT_PATTERN`, `NATIVE_PROCESS_VALUE_PATTERN`, `NATIVE_PROCESS_FLAG_PATTERN`) live in the constants module per row 23 ("the patterns of §9.1").
- **Budget and contract:** no new file, class or enum, so the §8.4 budget and the §4/§8.5 public names are unchanged.
- **No stale text:** no stale `^-`, "never lost" or modification-time proof remains. The remaining `(str, Enum)` mentions are explanatory notes, or refer to main's unchanged `FailureCode`.

### Least-sure points after r3

- A-20 and A-23 for provider `meta`.
- A-19 and A-24: the Grok home after a successful sign-in.
- A-22: opencode providers that sign in through a plugin.
- A-25: whether `OPENCODE_DISABLE_PROJECT_CONFIG` covers `.opencode/`.
- The owner's answers to Q-8 (the Meta name) and Q-9 (the opencode project-config switch).
