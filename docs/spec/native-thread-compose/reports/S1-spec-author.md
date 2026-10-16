# S1 spec author report: native-thread-compose r1

- **Produced:** `docs/spec/native-thread-compose/spec.md`, committed alone as `7df09460` ("docs(spec): add native-thread-compose spec r1") on `feat/native-thread-compose`, on top of `5a8ece05`. The file has 1,479 lines.
- **Structure:**
  - its `##`/`###` headings are identical to the template's (checked by diff);
  - `grep -c "^## §"` gives 18;
  - the first §12.3 row starts `| 1 |`;
  - §0.1 equals `request.md` lines 21–31 (checked by diff, CR stripped);
  - the committed blob is LF-only (autocrlf normalized it).
- **This report is not committed.** The scratch parts stay in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/spec-parts/`.

## 1. What I read

- **`docs/`** (the allowed list only):
  - `docs/spec/native-thread-compose/request.md`;
  - `docs/spec/native-thread-compose/context/code-map.md`;
  - `docs/spec/harness-thread-functions/spec.md`, `test-plan.md`, `context/vendor-facts.md` and `context/code-map.md`.

  Not read: `pipeline.md`, `reports/S0-scout.md`, and every other file under `docs/`.
- **Repo rules:**
  - `AGENTS.md` (all 81 lines) and `CLAUDE.md`;
  - `REPO_MAP.md` (157–162, 197, 215);
  - `CONTRIBUTING.md` (33–36, 38–49, 51–76, 84–86) and `.github/pull_request_template.md`;
  - `lint/README.md`;
  - `vidbyte/harnesses/README.md` (headings; native bullet at 178; 10,771 characters at `base_commit`) and `vidbyte/lib/README.md`.
- **SDK code at `5c08c35e`:**
  - the harness modules: `vidbyte/harnesses/native/` (`__init__`; the `grok`/`opencode`/`muse` `threads.py`, `wire.py` and `launcher.py`; `hostkit`) and `vidbyte/harnesses/serialization.py`;
  - process: `vidbyte/lib/process/runner.py`, `argv.py`;
  - records and validators: `vidbyte/lib/dataclasses/{native_threads,process,validation}.py`;
  - constants and enums: `vidbyte/lib/constants/native_threads.py`, `vidbyte/lib/enums/{native_threads,__init__}.py`;
  - errors: `vidbyte/lib/errors/{base,__init__}.py`;
  - util: `vidbyte/lib/util/__init__.py` and the `__all__` of its modules;
  - existing template and fan-out sites: `vidbyte/agents/aggregation.py` (89, 192), `vidbyte/context/algorithms/independent_critic.py` (248);
  - the paradigm precedent: `vidbyte/paradigms/context_minimal_fanout/prompts/__init__.py`, `types.py`;
  - `pyproject.toml` (7, 10, 48–49, 55–81).
- **Tests:**
  - `tests/features/harness_threads/`: `conftest.py` (all), `fake_harness.py` (header, hold, log, Grok, opencode and Muse branches), `FEATURE.md`, `README.md`;
  - the surface and static-policy tests where they pin exports;
  - which packs carry `FEATURE.md`/`README.md`;
  - pins on lib `__all__` lists (none are exact).
- **Field guide:**
  - `vidbyte-sdk/`: `comment-format`, `blocking-lint-invariants`, `local-ci-verification`, `class-bound-helpers`, `strict-config-dataclasses`, `fallback-coordination`, `review-scope`, `agents-md-map`, `cli-backed-source-integrations`, `runtime-boundaries`, `prompt-families`, `diagnostic-context`, `init`;
  - `vidbyte-cli/`: `agent-stage-prompts`, `runtime-execution`.
- **CLI (read-only, never imported or modified):**
  - `src/vidbyte_cli/lib/runtime_primitives/stages.py` (151–191), `stage_failures.py`;
  - `src/vidbyte_cli/types/runtime.py`, `types/ensemble.py` (22–23);
  - `src/vidbyte_cli/services/ensemble/service.py` (47, 193–217), `settings.py`, `sdk.py`, `prompts/*.md`, `prompts/library.py` (138);
  - `skills/harnesses/runtime-primitives/SKILL.md` (62–66).

## 2. Approaches weighed and the choice

**Chosen:**
- General composites over a validated, frozen `ThreadStep` lib record with `async __call__`, which the caller builds with `bind_thread`/`bind_continue`.
- A single writer, enforced by mechanism:
  - Grok readers run in place, only in `PLAN`/`DEFAULT`, serialized per event loop and workspace (orchestrator ruling);
  - opencode and Muse readers run only in disposable worktrees, filled from a temporary-index snapshot that includes uncommitted and untracked files;
  - a snapshot backstop around every read-only phase turns any change into `READER_CHANGED_WORKSPACE` before the writer runs.
- Tree-to-tree diffs.
- 22 local Markdown prompts loaded with `importlib.resources`.
- JSON answers through a canonical `JsonText` decoder, a caller-supplied `parse`, and at most two repair turns on the same thread.
- Nine aliases generated as callable class attributes.
- Budget: 40 new files (18 `.py` and 22 `.md`), 49 classes, 8 modified files.

**Smaller designs rejected** (§8.3):
- *Five hand-written functions*: they take keys and harness names, tell reviewers "do not edit" in the prompt, use one `json.loads`, and diff with `git diff` text. This fails FR-1/INV-3 (ledger 3), FR-3/INV-24 (ledger 2), FR-12/INV-9–11 (ledger 4), FR-16/INV-20 and base INV-15 (ledger 10), FR-11/INV-19 (ledger 6), INV-8/AC-17 (new files are missed and earlier edits leak in), and FR-18/AC-19 (a long answer breaks a Grok step).
- *Detection-only readers in place*: this fails ledger 4's worktree preference. A detected write has already corrupted the workspace the writer produced, and concurrent opencode readers race on the same files.

**Other alternatives, each recorded as a D- runner-up:**
- a worktree per Grok step (D-5): a new Grok home per path that is never removed, and threads reachable only from that path;
- C-17's prepared-skill pattern (D-5, runner-up only, per the orchestrator);
- catalog prompts (D-9);
- `asyncio.TaskGroup` (D-17), which raises an `ExceptionGroup`;
- the literal status and diff texts (D-6);
- a `vidbyte/lib/git` helper (D-7);
- `functools.partial` steps (D-2), which leak the key in their `repr`.

## 3. Disagreements, with evidence

1. **Ledger 5's literal `git status --porcelain` plus `git diff` (D-6).**
   - Problem: an already-edited file keeps the same status line, two diff texts cannot be subtracted, and `git diff` never shows untracked files.
   - Evidence: probe facts 1–2 (§15).
   - What the spec keeps of ledger 5: `CliRunner`, snapshots before and after, the changed files and a bounded unified diff, all through tree objects.
   - Open item: Q-10, default no.
2. **Ledger 2's `chain_threads(steps, template)` order (D-25).** That shape has no place for the caller's prompt, and the acceptance list calls aliases as `(prompt, …)`, so the spec puts the prompt first.
3. **Ledger 7, "only an empty result aborts" (D-26).** The spec reads it as: raise only before any I/O or for a compose-owned failure, and then always carrying the record so far.
4. **Ledger 4, "exactly one writer per composite" (D-27).** The spec scopes it to `verify_with` and `run_ensemble`. Chain, handoff and stages are sequential pipelines in which each step may write, because Prompt 2 says Grok "continues the work".
5. **The request hint's "eleven `.md` files" (C-14).** The CLI has ten, and ledger 10 lists ten, so the spec ports ten.
6. **Ledger 3's `ThreadStep = Callable[...]` alias.** It breaks base INV-15 (C-3), so `ThreadStep` is a lib record with `async __call__` (D-2).
   - Risk: review could rule against `__call__` on a lib record. Fallback: a compose-side caller class; the public names stay.
7. **D-28 added beyond the ledger.** The base does not scrub keys from successful answers, so splicing could carry a key into another vendor's argv. Compose replaces every bound key in spliced values with `COMPOSE_REDACTED_KEY`, by exact text; `HarnessRedactor` would rewrite `token = …` lines inside diffs.
8. **The CLI's approach band, 5–10 per role (`types/ensemble.py:22–23`).** The spec uses 2–5 (A-11), because Grok and Muse selectors read free-text proposals inside 24,000 characters, which leaves about 1,200 characters per proposal for ten proposals (EC-23).
9. **`runtime-boundaries.md`'s last entry**, which says prompts carry no numbers.
   - Every count a model is asked for (roles, the round target, the offered numbers) is a placeholder filled from the same constant or count that the decoders check, so prompt and code cannot drift.
   - The approach range is unchecked guidance, as in the CLI.
   - Recorded in §11 and §12.4.
10. **Caps derived from base constants.** `COMPOSE_ANSWER_TEXT_MAX_CHARS` and `COMPOSE_DIFF_MAX_CHARS` equal `NATIVE_RESULT_TEXT_MAX_CHARS`, and `ENSEMBLE_ROLE_NAME_MAX_CHARS` equals `NATIVE_NAME_MAX_CHARS`, following `strict-config-dataclasses.md`.
11. **Corrected count.** The base pack collects 438 tests at `base_commit` (`pytest --collect-only`). INV-35 now says 438; an earlier draft said 397.
12. **Placement judgement.** AGENTS.md says "Add to the existing domain module when there is one".
    - The spec puts the compose records, enums and constants in new `native_compose` modules, plus `native_ensemble` for the ensemble records, not in the `native_threads` modules.
    - Reasons: compose is its own subsystem, and merging would push `constants/native_threads.py` (452 lines now) and `dataclasses/native_threads.py` (228 lines plus 18 records) past the base 500-line cap (base NFR-2). No test pins those modules' `__all__`.
    - If a reviewer prefers `native_threads.py`, only file names change.

## 4. Assumptions I am least sure of

- **A-1.** Grok `PLAN`/`DEFAULT` run headless never edit. This is unverified at the vendor. If it is wrong, the backstop makes it loud, and verify and ensemble runs with Grok readers fail.
- **A-4.** Muse in WSL mode works inside a Windows worktree folder. Whether WSL git follows the worktree's `gitdir:` is unverified.
- **A-5.** Repeated sequential forks of one Grok session each get a fresh thread. Not probed.
- **A-8.** The ported prompts still work without their `<examples>` blocks. This cannot be measured offline.
- **D-2 placement.** `ThreadStep.__call__` lives in a lib record. See item 6 above.

## 5. Code-map items and where the spec disposes of them

| ID | Topic | Disposition |
|---|---|---|
| C-1 | Not every failure code is a harness code | INV-21: reverse lookup through `NATIVE_THREAD_FAILURE_CODES`; an unmatched code gets `STAGE_UNCLASSIFIED_DECISION` = ABORT. Also EC-54 and the §9.2 `STAGE_DECISIONS` table |
| C-2 | `native.__all__` is pinned | D-1 (ruling (a)), INV-1, INV-27, NG-2 |
| C-3 | INV-15 binds compose | INV-32, NFR-5; D-2 (a record, not an alias); D-9 (names from `ComposePrompt`); D-18 (aliases as class attributes); the §12.4 INV-15 line |
| C-4 | No new codes or enum members | D-15 (`ThreadComposeError`), D-16, INV-33 |
| C-5 | The base spec excludes diffs | Ruling (b), INV-34, D-7 |
| C-6 | Git needs its own timeout | D-22, INV-22, NG-4, Q-7 |
| C-7 | Grok PLAN is undocumented | INV-10, INV-11 (backstop), D-4, A-1 |
| C-8 | opencode and Muse have no read-only mode | D-4, INV-9, NG-6, Q-6 |
| C-9 | Forking conflicts with the roster and with worktrees | D-3, INV-23 step 2, EC-44, EC-45, Q-5 |
| C-10 | A repair turn needs continue | D-2 (the record carries harness, verb, workspace and config); `ThreadBinder.anchor` (§9.2); INV-19; INV-9 (repairs run inside the worktree) |
| C-11 | Spliced prompts can exceed the cap | INV-18, D-19, D-11, D-12, NFR-11, EC-23, EC-34 to EC-37 |
| C-12 | `{{x}}` breaks under `str.format` | D-10; §12.3 rows 4 and 17 |
| C-13 | No host-enforced schema | D-8, D-13, INV-19, A-7 |
| C-14 | Ten prompts, not eleven | §9.2 (10 P rows), §12.3 row 17, FR-16 |
| C-15 | The PR is stacked | D-23, §11 conflicts, §9.4 |
| C-16 | No effort ladder to port | D-14, INV-21, Q-4, Q-7 |
| C-17 | A third safe Grok pattern | D-5 runner-up 2 (orchestrator ruling: serialize per workspace) |
| G-1 | A `partial` shows the key in its `repr` | D-2, INV-4 (`field(repr=False)`), AC-15 |
| G-2 | A worktree per Grok step is costly | D-5, INV-10, INV-31 |
| G-3 | Muse needs a drive path | EC-56 (accepted limitation), EC-55, A-4 |
| G-4 | Tests cannot show a vendor refusing a write | AC-8 (backstop detection plus the argv), INV-11; §13 fact 4 (the stand-in has no write mode) |
| G-5 | Fail-then-succeed needs a stand-in change | §13 fact 1 (a per-scenario launch counter) |
| G-6 | git is unreachable in the sandbox | §13 "Git in the sandbox", `PATH` |
| G-7 | Records see more than `NativeThreadError` | INV-15, D-26, INV-6 (no `OSError` escapes; a step failure never becomes a compose error) |
| G-8 | Gather rules | D-17, INV-14; §12.4 S063, S006, S019 |
| G-9 | Cost of each prompt route | D-9, NG-8 |
| G-10 | No canonical JSON helper | D-8, §12.3 row 5, NG-5 |
| G-11 | opencode sessions belong to a project | D-3, EC-57, A-3, Q-5; §13 fact 5 |
| G-12 | A Grok writer needs ACCEPT_EDITS | EC-38 (accepted), D-21; the §4 snippet binds ACCEPT_EDITS |
| G-13 | Prompts must be NUL-free and non-blank | INV-18, EC-37, D-19 |

The code-map's §4.3 "unverified" items go here:
- Grok modes → A-1.
- An opencode read-only agent → NG-6, Q-6.
- Concurrent Grok forks → serialized by INV-13; sequential forks → A-5.
- WSL git in a worktree → A-4, EC-55.
- Git identity and autocrlf under the redirected home → verified by probe, recorded as §13 facts.
- S045 and `timeout_seconds` → moot: compose has no timeout parameter (NFR-2).
- `pip install -e` → §11 Install: none.

## 6. §D weighted words → INV / NFR / AC

| Weighted words (request §D) | Where they became a rule |
|---|---|
| fresh thread per stage, retry budget, classifier keyed on `NativeThreadProblem` (retry / raise effort / abort) | INV-21, AC-5, AC-12 |
| each result spliced into the next prompt, as stages.py does | INV-17, AC-2, AC-5 |
| Grok (PLAN) and Muse (worktree) independently review the diff and answer a structured verdict; both verdicts plus an agreement flag | INV-9, INV-10, INV-14, INV-19, INV-25, AC-3 |
| planner roster, N PLAN forks proposing weighed approaches, a selector narrowing to one, one ACCEPT_EDITS writer | INV-23, D-3, AC-6, AC-20 |
| the user defines the threads and providers | INV-2, INV-3, INV-23 ("no role is tied to a harness"), AC-6, AC-14 |
| every base rule still holds for the composites (ledger 1) | INV-27 to INV-36, AC-23 |
| generate variations, never hand-write nine functions | INV-24, AC-2, AC-22 |
| any writer, any verifiers, one structured verdict each, all verdicts plus agreement | INV-5 (1 to 10 verifiers), INV-25, AC-3, AC-11 |
| the caller supplies every role's step; no role hard-wired | INV-23, AC-6 |
| steps only, never harness names or raw keys; the key never reaches argv, files, `os.environ`, errors or logs | INV-3, INV-4, AC-14, AC-15 |
| exactly one writer, enforced by mechanism, not prompt | INV-9 to INV-12, AC-8 |
| fail loudly if a reviewer changed files | INV-11, AC-8 |
| verifiers receive the diff, not a prose claim; non-git workspace is a closed failure | INV-6, INV-8, AC-3 (prompts contain the diff, not the writer's text), AC-13 |
| every verdict, roster and selection through one parser; `text_truncated` fails the parse | INV-19, AC-9 |
| every result or error, thread id and failed step recorded; only an empty result aborts | INV-15, D-26, AC-7 |
| gather cancels siblings unless all-results; each step's own `timeout_seconds`; no second timeout system | INV-14, INV-22, AC-10 |
| lib never imports harnesses; no root export; no new dependencies | INV-32, INV-27, NFR-1, NFR-3, AC-22 |
| every sentence to a model in `prompts/*.md` | INV-20, FR-16, AC-21 |
| serialize Grok per workspace or isolate it | INV-13, AC-11 |
| async only; no sync wrappers, tools, payment or admission | NFR-2, AC-22 (exact surface), NG-3 |
| tests never need a real vendor CLI or key | NFR-6 |
| neither verifier able to change the workspace | INV-9 to INV-11, AC-3, AC-8 |
| one entry per stage, retried per budget, decision recorded per attempt | INV-21, AC-5, AC-12 |
| roster text, every proposal, the selection and the implementation returned | INV-23, FR-8, AC-6 |
| every function covered by tests against the fake harness | NFR-6; AC-7 to AC-12 cover the six named cases |

## 7. Stage E self-check (run on the assembled file with scripts in `scratchpad/tools/`)

- **IDs.** These families are contiguous and every reference resolves: INV 36, AC 23, EC 72, FR 18, NFR 11, D 28, T 8, W 13, NG 13, A 11, Q 10, G 6.
- **FR → INV/AC.** Every FR cites an INV, and every FR appears in §12.1 next to its AC.
- **AC → W/§12.3.** All 23 ACs appear in §12.1.
- **§12.3 row → FR/NFR/W.** All 27 rows name a W-, and most also name an FR or INV.
- **EC guards.** Every EC row has a guard: an INV, a D, or an accepted limitation, and §12.3 row 26 lists all the accepted limitations.
- **T controls.** Every T row names a control. T-4 now names `GrokWorkspaceLocks`.
- **Names.** The §4 imports, the 42 public names, the 22 internal classes and their methods, the 18 records, the 7 enums, `ThreadComposeError` and `JsonText` match across §4, §8.4, §8.5 and §12.3. The class total is 49, as §8.4 says.
- **File count.** §12.3 creates 40 files and modifies 8, matching §8.4.
- **§12.4** has an obligation for each kind of file: enum, constants, validator, helper, record, error, export list, plumbing and composite services, prompt assets, `pyproject`, package init, the README and `REPO_MAP`.
- **Weighted words.** Every §D weighted word maps to an INV, NFR or AC (table above).
- **Commands.** The §11 commands come from code-map §1.3, AGENTS.md or the briefing.
- **No test cases.** No `def test_`, `assert` or `pytest.raises` anywhere; §13 states facts only.
- **Tables.** All 20 tables are well-formed (cell counts match their headers).

Small fixes made during the check:
- added handoff to INV-16;
- FR-6 now cites INV-17 and INV-16;
- the T-4 control;
- row 26 now lists every accepted limitation;
- rows 5, 7 and 8 gained a literal `__all__`, following their siblings;
- rows 6 and 10 now follow their headers' modification patterns;
- row 9 cites the `TYPE_CHECKING` precedent (`base.py:61–64`);
- added the §12.4 REPO_MAP and prompt-number lines;
- W-11 gained AC-15;
- the §11 baseline label now matches the template.

## 8. Probes and environment disclosure

- **Git probe.** `scratchpad/git-probe/probe.sh` is a throwaway script that creates scratch repositories under `scratchpad/git-probe/` only. It was first run during grounding and re-run on 2026-10-16 with git 2.49.0.windows.1. One-line follow-ups covered:
  - `worktree add` on an unborn `HEAD` (exit 128, "invalid reference: HEAD");
  - `rev-parse --local-env-vars` (exactly 15 names);
  - a `post-checkout` hook: it does not run for `--no-checkout` plus `read-tree -u --reset`, and it does run for a normal `worktree add` (positive control);
  - safecrlf warnings: present without `-c core.safecrlf=false`, absent with it;
  - `core.autocrlf=true` comes from `C:/Program Files/Git/etc/gitconfig`.

  The results are §15 facts 1–8. No real checkout was touched; the scratch worktrees were removed.
- **Read-only checks in this worktree:**
  - `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest --collect-only -q -p no:cacheprovider tests/features/harness_threads` collected 438 tests and left the tree clean;
  - `shutil.which("git")` returned the Git Bash path.
- **Nothing installed.** `scratchpad/semgrep-venv` and `scratchpad/base-5c08c35e` were created by the orchestrator, not by me.
- **Scratch tools:** `scratchpad/tools/*.py` (exact-replacement edits, assembly and the check scripts). One stray temporary file, `/tmp/s01.txt`, was written during verification and deleted at once.
- **Git state changes:** exactly one commit, `7df09460`. No push, no PR, and no other ref touched.

## 9. The larger move this opens

- **First fix the stand-in, before any compose test.** The test author has to extend `fake_harness.py` with per-launch answer sequences, a write-into-workspace mode and a key-echo-into-answer mode (§13 facts 1 and 4). Every scenario-driven AC depends on them.
- **Lift the git machinery into lib when a second feature needs it.** `DiffCapture`, `DisposableWorktree` and the temporary-index snapshot are the SDK's first general "read-only by mechanism" primitive. When a second feature needs snapshots or worktrees, D-7 flips and these move into a `vidbyte/lib/` helper. That would be its own PR.
- **Probe Grok PLAN headless behavior once with a real key.** A-1 is the assumption with the largest blast radius. One owner-run probe of `grok --permission-mode=plan` attempting an edit would settle it and turn the backstop from a likely path into a pure safety net.
