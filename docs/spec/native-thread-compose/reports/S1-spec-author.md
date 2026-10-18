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

## 10. Addendum: revision r2 (review round 1, commit 25358062)

**Input.** The S1 reviewer's R-1 to R-11 (0 Blocker, 8 Major, 3 Minor), the orchestrator's two adjudications (R-3 adopts D-25's runner-up and is not a Q; R-2's optional marker becomes Q-11), and the list of repo facts the reviewer verified. All eleven findings were accepted. None was rejected, and the only scope-adding part (R-2's shortened-input marker) became Q-11, default not built.

**Dispositions, one line each** (the full log is spec §16):
- R-1: §9.2 gains per-file port rules. Each ported file loses its own output contract, `json_answer` with a schema is the only JSON contract, proposers answer in prose, `implementer_turn` is rewritten around its six fields, and sandbox wording goes. AC-21 now checks six forbidden texts. I applied the rule to `planner_system` too, although its contract matched the plan schema, so one rule covers all ten files and AC-21 needs no exemption.
- R-2: the up-front check counts each spliced value as its longest truncation note (omitted count `sys.maxsize`, which no string length exceeds), one proposal block per proposer and numbers at their largest. Send time searches the largest fair share by bisection, in characters and on win32 in units. The blank last resort and `COMPOSE_FIT_ROUNDS` are gone. A value no longer than its own note is never cut, which keeps the share search monotonic.
- R-3: `chain_threads(steps, template=None, *, prompt)` and `verify_with(writer, verifiers, *, prompt)`; the aliases keep `(prompt, *, …)`. Checked with `inspect.signature(...).bind`: the ledger's positional forms now bind.
- R-4: EC-13 corrected, EC-73 added, two constants give `GIT_FAILED` from `add` its own likely cause and next step, and D-6 and Q-10 name what the tree mechanism refuses.
- R-5: D-2 quotes the Placement Rule and argues the forward is record plumbing (the `RunnerHandle.invoke` shape). The agreed fallback, in D-2 and row 7, keeps `await step(prompt)`: the verb order and the guard move to `ThreadBinder.invoke`, and the record forwards to that injected invoker.
- R-6: after the fill, compose creates the matching folder; a verifier's worktree index is set to S0 (a new git row and `ComposeGit.set_index`); EC-74 and EC-75 added.
- R-7: INV-5 requires `from_thread` to be a `CONTINUE` step or an anchored fork; EC-76 added. I left INV-3 unchanged because it covers what a step is, not which verb a role needs.
- R-8: compose names `HEAD`, never `HEAD^{tree}`; EC-65, T-8, D-24 and Q-9 state the remaining temporary-path limit.
- R-9: the `details` shape now follows `NativeThreadError` (the A003 fields in `details`, the rest in `safe_runtime_details`); the §11 layout line is relabelled; row 28 adds a docstring-only edit of `vidbyte/harnesses/native/__init__.py`, so nine files are modified.
- R-10: §13 and §12.2 now credit C015 and forbid a README in `compose/prompts/`.
- R-11: INV-4 narrowed; T-3 records the reader-reads-a-saved-key residual as accepted.

**Repo facts from the orchestrator, and where each landed:** the Python 3.11.0 subscript `TypeError` (§8.5 comment, row 16, §13); `iscoroutinefunction` on alias instances (§13); the env order in `CliRunner` (§9.3); NUL in `NativeThreadResult.text` (§13, already handled by INV-18); C015 and the README rule (§12.2, §13); the empty mkdtemp folder for `worktree add` (§15 fact 11); the planner contract already matching (R-1 disposition). The 438-test count and the 15 local env variables were already in r1.

**r2 probes** (scratch folder `scratchpad/r2probe/`, no checkout touched): `add -A` exits 128 on an untracked repository with no commit and 1 with `--ignore-errors`; `rev-parse --verify --quiet HEAD` exits 1 when unborn and 0 with a commit; `read-tree HEAD` and `read-tree HEAD^{tree}` give the same tree id; after `read-tree -u --reset S1`, `read-tree S0` makes `git diff` show the writer's change to existing files and `git status` show its new files as untracked; `worktree add --detach --no-checkout` works into an existing empty folder; `cmd.exe` prints `HEAD{tree}` for `HEAD^{tree}`; on Python 3.11.0 `Box[int](...)` raises `TypeError` for a frozen slotted generic dataclass and 3.13.1 accepts it; `inspect.iscoroutinefunction` is `False` for an instance with `async __call__`.

**Self-check after r2:** 18 `## §` headings, identical heading set; §0.1 still equals request.md lines 21–31; 20 tables, 0 malformed rows; every ID reference resolves (INV 36, AC 23, EC 76, FR 18, NFR 11, D 28, T 8, W 13, NG 13, A 11, Q 11); §12.3 has 28 rows from `| 1 |`, with 40 new files and 9 modified; 42 public names and 49 classes, unchanged; no test-case text. The committed blob is LF-only.

**Least sure after r2:** that the bisection's monotonicity holds on win32 at the boundary where a value's trailing backslashes meet a quote in the fixed text. A one-unit wobble there could make the search settle on a slightly smaller share than the true largest, but every share it returns is checked to fit, so it can cut more than needed and can never overflow. Also, whether review accepts D-2's argument; the fallback is ready if not.

## 11. Addendum: revision r3 (review round 2, the last round)

**Input.** The round-2 reviewer's R-12 to R-17 (1 Blocker, 2 Major, 3 Minor); the orchestrator's adjudication for R-13 (build the injected-invoker form now, the reviewer's first option); and its instruction to set `status: approved`, because two review rounds are the cap. All six findings were accepted. None was disputed, so no new Q-n was needed.

**Dispositions, one line each** (the full log is spec §16, rows r2-12 to r2-17):
- R-12 (Blocker): INV-4 now lists only text compose itself produces: git argv and environment, `ThreadStep` reprs, the error's message and every attribute but `result` and `diff`, `ConfigurationError`, files compose writes, and spliced values. It also says step output stays raw, `error.result` and `.diff` included. AC-15 matches, and it also checks that the raw texts keep the echoed key, so a build that scrubs too much fails as surely as one that scrubs too little. EC-71, T-3 (a second residual), §12.4 and §14 follow.
- R-13: one design remains. `ThreadStep.invoker` is `field(default=None, repr=False, compare=False)`, and the binders set it to `ThreadBinder.invoke`. `__call__` only awaits it, and raises `ConfigurationError` naming `ThreadStep.invoker` when it is `None`. Composites call `ThreadBinder.invoke(step, prompt)` directly. D-2 (the r2 forward is now its runner-up), INV-2, INV-3, §5, §8.2, §8.5, §9.1, rows 7, 11 and 12, §13 and r1-5 follow. EC-78 records the two cases the reviewer raised: a step built without a binder, and one whose invoker was replaced.
- R-14: in INV-24, D-18 and rows 19 and 20, `__call__` first binds with `self.__signature__.bind(prompt, **steps)`, so a missing or unknown keyword raises `TypeError` on await, before any check (EC-77). The §9.2 boundary paragraph now says that a signature mismatch is Python's `TypeError`, for the aliases as for the general composites.
- R-15: INV-26 defers to the §9.2 cwd column (§15 fact 13).
- R-16: only an `add` that exited non-zero gets the two `add` texts, which now name both causes; a timeout keeps the generic texts. EC-73's trigger now includes the unreadable file (§15 fact 14).
- R-17: the `role_system` port rule quotes both CLI sentences, and AC-21 also forbids "cannot write" and "will fail".

**r3 probes** (scratch folder `scratchpad/r3probe/`, no checkout touched):
- git 2.49.0.windows.1, `diff.relative=true`: a tree-to-tree `diff --name-only` run from `sub` printed `b.txt` and `new_by_writer.txt` and dropped `c.txt`. Run from the root, it printed `c.txt`, `sub/b.txt` and `sub/new_by_writer.txt`. The real index was untouched. This reproduces the reviewer's result independently.
- A file opened from PowerShell with `FileShare.None` made `add -A` into a temporary index exit 128 (`Permission denied`, `unable to index file`, `adding files failed`). Once the handle was closed, the same command exited 0.
- Python 3.11.0, injected invoker: a frozen, slotted record with `invoker = field(default=None, repr=False, compare=False)` leaves it out of `repr`, `==` and `hash`, and `dataclasses.replace` keeps it. A replaced invoker runs on a direct await but not through the composite path. With no invoker, `__call__` raises before anything runs.
- Python 3.11.0, aliases: for an alias instance with `async __call__`, `Signature.bind` raised "missing a required argument: 'grok'" and "got an unexpected keyword argument 'muze'" on await, and a step passed positionally failed at the call itself.
- CLI read-only check (abd31b4): `role_system.md:37–38` holds both sentences. A grep of the ten ported CLI prompts for sandbox, read-only, write-access and will-fail claims found only three outside the dropped `<examples>` blocks (`implementer_system.md:84–546`, `planner_system.md:112–728`): that pair, `fork_turn.md:7` and `implementer_system.md:58`. The port rules already cover the last two.

**Self-check after r3:**
- headings: 18 `## §` headings, the same set as r2; §0.1 still equals request.md lines 21–31;
- tables: 20, with 0 malformed rows;
- references: every ID resolves (INV 36, AC 23, EC 78, FR 18, NFR 11, D 28, T 8, W 13, NG 13, A 11, Q 11); every EC has a guard and every T a control;
- work breakdown: §12.3 still has 28 rows, 40 new files and 9 modified, and every row names a W; 42 public names and 49 classes, unchanged;
- text: no test-case text; `git diff --check` is clean.

**Decisions in the approved spec that depart from request §B,** listed for the owner:
- Ledger 2 (D-25): `chain_threads` and `verify_with` add a required keyword-only `prompt`; the ledger's positional order still binds.
- Ledger 2 (NG-7, Q-1, Q-3): only the six distinct-harness pairs and the three trios become aliases, and there are no default roster helpers.
- Ledger 2, "any set of verifiers" (INV-5, INV-9, INV-10, D-3): every step works in one workspace, opencode and Muse readers must be `RUN` steps, Grok readers must use `PLAN` or `DEFAULT`, and fork roles exist only on Grok.
- Ledger 3 (D-2, INV-3): `ThreadStep` is a validated record awaited through an injected invoker, not a bare `Callable` alias, and composites refuse other callables.
- Ledger 3, key rule (INV-4, EC-71, T-3): compose scrubs only text it produces. Answers and diffs stay raw in records, and a reader can open a key file that a writer saved.
- Ledger 5 (D-6, Q-10): snapshots are git trees built through a temporary index, not the literal `status --porcelain` and `diff` texts, and an untracked repository with no commit fails the snapshot (EC-73).
- Ledger 7 (D-26): a compose-owned failure (git, worktree, backstop) raises `ThreadComposeError` carrying the partial record.
- Ledger 8 (D-22): each git child has its own `COMPOSE_GIT_TIMEOUT_SECONDS`, which `CliInvocation` requires. That is not a step timeout.
- Ledger 10 (D-10, D-12, D-13): the ported prompts drop their `<examples>` and their own output contracts, and `{{x}}` becomes `{x}`.

**Least sure after r3:** A-1, A-4, A-5 and A-8 stand as after r2. A-1 (Grok `PLAN` run headless) has the widest blast radius, and the backstop contains it. Also, a caller who logs `repr` of a record can show a key that a model printed. That follows from R-12 and is stated in T-3 and in the README bullet that row 26 requires, but it may surprise callers. Finally, the win32 bisection boundary noted after r2 is still unproven by test.

**Git state:** one commit for r3 holds the spec and this addendum.

## 12. Addendum: revision r4 (S2 test-author findings, not a review round)

**Input.** The orchestrator relayed S2's defect S2-1, a Blocker for AC-23. It also asked me to check the test plan's "Interpretations the tests encode" against the spec. I read only the test plan's "Notes for the implementer" section, not the test code or the S2 report. The review cap stays at 2 of 2. The spec moves from `approved` to `tests-written`, revision 4. Worktree HEAD before the edit was b0f0a531, and the tree was clean.

**S2-1: which primitive.**
- The ban. `lint/ruff.toml:8` bans `asyncio.Lock` (TID251, "Use the SDK-owned concurrency boundary."), and `lint/baseline.json:66` holds S039 at 5. `py -3.11 -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` finds exactly five uses today: `vidbyte/harnesses/stores/memory.py:41`, `vidbyte/middleware/builtins/circuit_breaker.py:63`, and `vidbyte/tools/mcp/transport.py:139`, `:140` and `:144`. A sixth use fails `python lint/run.py`, and AC-23 forbids raising the baseline. The rule's repair text (`lint/rules/s039_banned_api_policy.py:35–39`) says to use the approved SDK abstraction, or to add the behavior to the boundary that owns it.
- No such boundary exists. Outside `docs/`, the phrase appears only in `lint/ruff.toml`, and `vidbyte/` has no lock, mutex or keyed-lock class. `vidbyte/agents/skills/loader.py:5` also records the ban.
- The SDK's own answer is a one-slot `Semaphore` sized by a named constant: `vidbyte/agents/codex/agent.py:82–86` ("A Semaphore rather than a Lock because the SDK bans asyncio.Lock …"), with `CODEX_MAX_CONCURRENT_TURNS = 1` (`vidbyte/lib/constants/codex.py:226`). `asyncio.Semaphore` also bounds concurrency in three other places: `vidbyte/agents/aggregation.py:87`, `vidbyte/evals/runner.py:60` and `vidbyte/paradigms/context_minimal_fanout/paradigm.py:113`.
- Chosen: `asyncio.Semaphore(native_compose.COMPOSE_GROK_MAX_CONCURRENT_CALLS)`, with the new constant set to 1. There is one semaphore per running loop and normcased resolved workspace, kept in the class-level `WeakValueDictionary` as before. What stays unchanged:
  - the behavior;
  - the class name `GrokWorkspaceLocks`;
  - every public name;
  - the general term "Grok lock", which INV-13 now defines.
- r4 probes (scratch folder `scratchpad/r4probe/`):
  - `semprobe.py` on Python 3.11.0. Two calls on one workspace did not overlap: "a" ended before "b" started. A call on a second workspace ran beside them. After a holder and a waiter were cancelled, the next call on that workspace took the semaphore at once (0.0 s).
  - `lockprobe.py`, checked with `--config lint/ruff.toml --select TID251,RUF012`. TID251 flags `asyncio.Lock()` but not `asyncio.Semaphore(1)`. RUF012 (lint S005) flags a class-level `{}` but not a class-level `WeakValueDictionary`.
- Spec edits:
  - D-5: the decision, the reason with this evidence, runner-up 3 and the flips-if;
  - row 12: the semaphore, `async with` around one step call, and the lint and precedent citations;
  - INV-13 and the §5 node label;
  - §8.2: a new pattern bullet;
  - §8.5: the class line and the constant;
  - §11: the lint files, under "Rules read";
  - §12.4: a new checklist line;
  - T-4.

**S2-2: the eleven readings.**

| # | Reading in the test plan | Spec before r4 | Disposition |
|---|---|---|---|
| 1 | The omitted count is measured after NUL removal | INV-18 removed NULs and keys first, but did not say what the count measures | Clarified in INV-18: the value's length after NUL removal and key replacement, minus the kept prefix's length |
| 2 | A cut is `text[:cap]` and `files[:cap]` | INV-8 gave the caps, not which part is kept | Clarified in INV-8: the start is kept, and no marker is added |
| 3 | `WorkspaceDiff.text` is git's raw output | INV-4 and EC-71 kept it unscrubbed, but nothing was said about stripping | Clarified in INV-8: the stdout `CliRunner` returns, unchanged apart from the cut |
| 4 | The problem constants follow their names, and the problem for an extra member names it | §8.5 listed the constants without saying when each applies; EC-27 already names the member | Clarified in INV-19: one clause per constant |
| 5 | An unanchored fork passed as `to_step` is refused naming `to_step` | EC-44 said "naming `thread_id`, or the argument" | Clarified in EC-44: `thread_id` from a direct call, the argument from a composite |
| 6 | The overlay is a subset of `{GIT_INDEX_FILE}`, and `rev-parse` runs in the workspace | The §9.2 cwd column already said "workspace", and §9.3 listed only `GIT_INDEX_FILE` as set | Clarified in INV-26: no other variable is set. The cwd was already explicit |
| 7a | `likely_cause` and `next_step` are their constants verbatim | INV-6 said "from constants" | Clarified in INV-6: verbatim |
| 7b | "The `add` failure appends both cause texts" | INV-6: "gets the two `add` texts instead" | Not adopted, and reported as an open item |
| 8 | `findings` and `kept` are tuples | §8.5 typed them as tuples, but never said how a JSON list becomes one | Clarified in §9.1: stored by `RecordFieldConverter.to_tuple`, which accepts a list (`EnsemblePlan.roles` too) |
| 9 | The problem text contains `str(ValueError)` from `JsonText.decode` | INV-20 said "error messages from `JsonText`" | Clarified in INV-19, with reading 4 |
| 10 | The selection runs before the backstop, and no snapshot follows the implementer | INV-23 already put select before backstop; NG-13 rules out a diff of the implementer's work | Clarified in INV-23 step 5: no snapshot after the implementer. The order was already explicit |
| 11 | The refusal names `StepOutcome.result` or `StepOutcome.error` | §9.1 said refusals name `<Record>.<field>`, but this rule covers two fields | Clarified in §9.1: both set, or neither, is refused naming `StepOutcome.result`, which is one of the two names the tests accept |

**Open item: reading 7b.**
- The test plan says: "`likely_cause` and `next_step` are their constants verbatim. The `add` failure appends both cause texts."
- INV-6 says: "when the snapshot's `add` exits non-zero, its `GIT_FAILED` gets the two `add` texts instead". EC-73 agrees: "the likely cause and next step name both causes".
- The reading agrees with the spec if the test asserts `likely_cause == THREAD_COMPOSE_ADD_LIKELY_CAUSE` and `next_step == THREAD_COMPOSE_ADD_NEXT_STEP`, each naming both causes, with the message ending in them.
- It contradicts INV-6 if the test expects the generic `GIT_FAILED` texts with the `add` texts appended.
- I could not read the test, so this part of the spec is unchanged.

The section's other notes agree with the spec and need no change. They cover the seams, constants read at call time, the `tempfile` folders with the `index` file name, and prompt rendering, and match §8.5, §9.2, §9.3, §13, INV-17 and INV-18.

**Self-check after r4:**
- headings: 18 `## §` headings, the same set as r3, and §0.1 still matches request.md lines 21–31;
- tables: 20, with 0 malformed rows;
- references: every ID resolves (INV 36, AC 23, EC 78, FR 18, NFR 11, D 28, T 8, W 13, NG 13, A 11, Q 11);
- work breakdown: 28 rows, 40 new and 9 modified files, 42 public names and 49 classes, all unchanged;
- the AC table, including the Proof column S2 filled, is byte-identical (0 AC lines in the diff). Nothing under `tests/` is touched;
- `git diff --check` is clean, the CRLF working copy is kept, and no backslash was added.

**Git state:** one commit for r4 holds the spec and this addendum.

## 13. Addendum: revision r5 (as-built corrections after S5 repair 1, not a review round)

**Input.** The orchestrator asked me to correct, as built, the passages that S5 iteration 1 made stale and that `reports/S5-repair-1.md` §6 lists, together with anything that depends on them. It also asked me to sweep for `gather`, `counted`, `add_worktree`, `shielded`, `(text, spliced)`, `(text, bool)`, `40 new files`, and the record and class counts.
- Worktree HEAD before the edit was a4092e7c, and the tree was clean.
- The code there is the code S5 left at 3a21352b: `git diff --stat 3a21352b a4092e7c -- vidbyte tests pyproject.toml REPO_MAP.md` is empty.
- `status:` is left as the orchestrator set it, and the revision is now 5.

**Method.**
- I checked each statement against the code at HEAD, not against the repair report. I read:
  - `ComposeCalls.fan_out` and `settle` (`calls.py:71–113`);
  - `DisposableWorktree.__aenter__`, `__aexit__` and `_settled` (`workspace.py:115–179`);
  - the `ComposeGit` worktree methods (`git.py:152–183`);
  - `ComposeTexts.render` and `fixed`, and `PromptFitter.check`, `_scrub` and `_encodable` (`texts.py:50–197`);
  - `ThreadBinder._derived` and `_withheld` (`steps.py:143–167`);
  - the `kept` lists and `_kept` in `verify.py:73–171` and `ensemble.py:85–248`, and the selector's handler (`selection.py:95–101`);
  - `PromptSegment` (`native_compose.py:139–152`) and `SecretText` (`secret_text.py:55–67`);
  - the two keywords (`validation.py:42` and `:177`).
- I diffed the class and `def` names between e1bf20d8 (the S3 report commit) and HEAD. The result is exactly the §6 list:
  - added: `PromptSegment`, `SecretText`, `replace_all`, `settle`, `fixed`, `worktree_folder`, `fill_worktree`, `_settled`, `_derived`, `_withheld`, `_encodable` and `_kept`;
  - removed: `counted` and `_replace`.
- No call to `asyncio.gather(`, `asyncio.shield(` or `TaskGroup(` is left in compose.
- Probe `scratchpad/r5probe/cancel_probe.py` (Python 3.11.0). A child's cleanup takes 0.2 s, and its waiter is cancelled twice. This is the evidence behind D-17's new reason:
  - `gather`: `['cleanup-cut', 'outer-ended child_done=True']`, so the second cancel reaches the child;
  - `shield`: `['outer-ended child_done=False', 'cleanup-finished']`, so the waiter stops while the child runs on;
  - `asyncio.wait` in a loop, as `settle` does: `['cleanup-finished', 'outer-ended child_done=True']`.

**Passages changed.**

| Section | Before | After | Checked against |
|---|---|---|---|
| D-17 | Tasks with `gather` plus explicit cancellation. S006, S019 and S063 "fit the gather shape" | One task per child and `asyncio.wait(FIRST_EXCEPTION)`. Then whatever still runs is cancelled, and `ComposeCalls.settle` waits for every child. One exception propagates: the first failure in child order, or the cancel. No gather and no `TaskGroup`. The reason cites the probe. Gather is added as the r1 to r4 runner-up. The intent (one raise, the rest cancelled) is unchanged | `calls.py:71–113` |
| §8.2 | "Shielded cleanup" after `muse/threads.py:109–116`; "Fan-out with gather" after `aggregation.py:89` | The muse intent without its shield, with git steps settled. No gather precedent applies | `workspace.py:173–179`, `calls.py:71–113` |
| EC-17 | The removal runs as a shielded task | An add that has started runs to its end, then the removal runs. Each is a settled task, with git bounded by `COMPOSE_GIT_TIMEOUT_SECONDS` | `workspace.py:122–142` |
| INV-30 | "shielded cleanups" | "settled cleanups" (one word) | `calls.py:94–113` |
| §8.5 | `ComposeGit` listed `add_worktree`, and `ComposeCalls` listed `call` and `fan_out`. There was no `PromptSegment` and no `SecretText` | `worktree_folder() -> Path`, `add_worktree(folder) -> None` and `fill_worktree(folder, tree) -> None`. `ComposeCalls` gains `settle(tasks)`. A `PromptSegment` record and a `SecretText` block are added | `git.py:152–167`, `calls.py:94`, `native_compose.py:139–152`, `secret_text.py:55–67` |
| §8.4 | "51 classes in 19 modules" | "51 classes: 50 in the 19 new modules, and `ThreadComposeError` in `base.py`". The same imprecision was there in r1 to r4 | AST count over the 19 added modules |
| §9.1, §9.4 | No `PromptSegment` row. `JsonText` was the only `vidbyte.lib.util` export, and the keywords were missing | A `PromptSegment` row (types only), `SecretText`, and the two grant (c) keywords | `native_compose.py:146–152`, `util/__init__.py:64`, `validation.py:42` and `:177` |
| §11 | The muse shield was the template and the aggregation gather a reusable piece. The util layout had no `secret_text.py` | Each of the two lines now says that compose does not copy it (D-17). The layout lists `secret_text.py [NEW]` | as for D-17 |
| §12.3 | Rows 12, 14 and 15 named gather, `add_worktree` and shielded removal. Rows 4, 6, 7 and 13 did not mention the grants. The table had 28 rows, with 5 lib modules and 40 new files | Rows 12, 14 and 15 describe the code as built. Rows 4, 6, 7 and 13 name the grants. New row 29 is `secret_text.py`. The count is 6 lib modules and 41 new files | the PR diff (see the self-check) |
| §12.4, §12.6, §14 | Gather results "checked against `BaseException`". P1 was rows 1–10. "More than 40 new files" | No gather and no shield, only `settle`. Row 29 joins P1. The limit is 41 | `calls.py` header, WHAT NOT TO DO item 5 |
| §17 | Rendering used `(text, spliced)`. The helpers list had `StepRoles.counted`. Fan-out was wait, then gather. Several readers gave the record from before their stage | Rendering uses `PromptSegment` records. `counted` is removed, and the S5 helpers are added with their S4 review IDs. Fan-out is as in D-17, with the planner and the selector as one-child fan-outs. The record holds every verdict or every proposal once every verifier or every proposer has answered, and otherwise the writer or the plan alone. An r5 row is added | `verify.py:163–171`, `ensemble.py:240–248`, `ensemble.py:92` and `:106` |

**Sweep: left as they are.**
- INV-1 "18 records": these are the records compose exports. `PromptSegment` is not exported, so the 42 names still hold.
- EC-19 "A plain `gather` would leave siblings running": this describes a rejected alternative and is still true.
- The S5 grant sub-bullets in §17 that mention `(text, spliced)` tuples and `StepRoles.counted`: they record what the grants replaced.
- INV-17 says templates are "rendered with `str.format_map`". The code splits them with the parser that `format_map` uses, so the text is the same. §17 Rendering records this, and row 13 now says it too.
- §0 and §4 are byte-identical, and the AC table is unchanged.

**r4 open item 7b is resolved.** `tests/features/harness_compose/conftest.py:659–661` checks `likely_cause` and `next_step` against `THREAD_COMPOSE_ADD_LIKELY_CAUSE` and `THREAD_COMPOSE_ADD_NEXT_STEP` when the add texts apply. So the add texts replace the generic ones, as INV-6's "instead" says. The spec needs no change.

**Open items (requirement level; the spec is unchanged).**
1. INV-1 and AC-22 name `JsonText` as the `vidbyte.lib.util` export but not `SecretText`. Neither says "only", so the code passes both, and §8.4 and §9.4 count `SecretText`. The owner decides whether INV-1 should name it.
2. R-13. Before any I/O, `PromptFitter.check` refuses a prompt whose fixed text is blank (`COMPOSE_BLANK_PROMPT`, naming `template` or `stages[i].template`). INV-18 requires that no prompt is sent blank, but it describes the up-front check only as a longest-form fit. No INV, EC or AC row names this refusal.
3. R-12. At send time, compose rejoins surrogate halves that were split apart in a spliced value and turns a lone half into U+FFFD. This happens after NUL removal and before the key scrub. It refuses fixed text that holds a lone surrogate up front (`COMPOSE_UNENCODABLE_TEXT`). INV-18 lists only NUL removal and key replacement at send time, and no EC covers surrogates.
4. EC-17 now says that an add that has started runs to its end before the removal (S4 review R-14). The expected result is unchanged. If the orchestrator wants only the one-word change, the Behavior cell becomes "The removal runs as a settled task, then `CancelledError` propagates".

**Note.** When two children fail before the cancel lands, `fan_out` raises the one that comes first in child order (`calls.py:87–90`). D-17 now says so, and INV-14's "that one exception" can be read this way.

**Self-check after r5:**
- headings: 18 `## §` headings, the same set as at HEAD;
- tables: 20, with 0 malformed rows;
- references: every ID resolves (INV 36, AC 23, EC 78, FR 18, NFR 11, D 28, T 8, W 13, NG 13, A 11, Q 11);
- work breakdown: 29 rows, with 41 new and 9 modified files. Every row matches `git diff --name-status origin/feat/native-grok-opencode-meta-hosts...HEAD -- vidbyte pyproject.toml REPO_MAP.md`, which lists 50 files, 22 of them prompts. `--stat` gives the same 50 files changed;
- every name added to §8.5 or §17 has a `def` or `class` at HEAD (`git grep -n` for `def <name>` or `class <name>`);
- §4's sha256 and the AC rows are unchanged, `git diff --check` is clean, the CRLF working copy is kept (1,620 CRLF, no lone LF or CR), and no backslash was added.

**Git state:** one commit for r5 holds the spec and this addendum. It is not pushed.
