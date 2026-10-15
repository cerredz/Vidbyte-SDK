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
