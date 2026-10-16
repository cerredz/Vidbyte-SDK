# S1 spec author report: codex-host-thread-helpers

- **Stage:** S1 spec author, revision r1
- **Spec:** `docs/spec/codex-host-thread-helpers/spec.md`, committed as `5a1c754c`
- **Worktree base:** `c181be65`, which merged origin/main and #1036 into `feat/codex-host`

## What I read

**Pipeline inputs**
- `request.md`: all six prompts, §C notes, §D weighted words, §E accepted catalog.
- `context/code-map.md`.
- `reports/S0-scout.md` and `reports/S0-merge-main.md`.
- `pipeline.md`.
- `docs/spec/codex-host/{request.md, spec.md, pr-body.md}`. These are the PR #1055 catalog and spec, cited throughout as "codex-host X-n".

No other file under `docs/` was read. The sibling worktree was not read.

**Rules**
- AGENTS.md, all of it.
- Lint rules A001, A002, A006, S012, S054, S062 and C002.
- Field-guide entries: comment-format, model-facing-tool-contracts, strict-config-dataclasses, blocking-lint-invariants, local-ci-verification, class-bound-helpers, provider-api-contracts and review-scope.

**Production code**
- All of `vidbyte/harnesses/native/codex/`: host, connection, wire, preflight, errors and turns.
- `vidbyte/agents/codex/result.py`.
- `vidbyte/lib/{enums/codex.py, enums/failure.py, enums/__init__.py, constants/codex.py, dataclasses/codex_host.py}`, plus the input records of `dataclasses/codex.py`.
- `vidbyte/tools/builtins/codex/*`, `vidbyte/tools/builtins/__init__.py` and `vidbyte/tools/toolsets/codex.py`.

**Tests**
- The codex_host pack's support module, fakes, and the tools, records, packaging, lifecycle, threads and sdk-contract files.
- #1036's surface and static-policy tests.
- `tests/test_codex_output_contracts.py:322`.

**Vendor**
- openai-codex 0.162.1: generated `v2_all.py`, plus `api.py` and `client.py` for compact, the goal operation and `SkillUserInput`.
- The five bundled system SKILL.md files and their agent configs, for the headless verdicts.

**Live probe**
- `codex app-server` 0.162.1 on 2026-10-15, non-spending methods only: `skills/list`, `thread/list`, and the five new methods against a random UUID and a malformed id.
- No write method touched a real thread.
- No real id, title, path or skill content was recorded beyond the five bundled skill names.

## Approaches weighed

1. **Pure reuse (rejected; spec §8.3).**
   - Search would be `list_codex_threads(search=)`, the transcript `read_codex_thread(include_turns=True)` and the goal wrapper `spawn_codex_thread(goal=)`.
   - It fails four requirements:
     - Visibility: the default `sourceKinds` hides every thread the SDK started. The probe's default listing returned only cli and vscode threads.
     - No `limit`.
     - No readback: there is no proof that a goal took (request §E).
     - No transcript: `read_codex_thread` drops items.
2. **Everything inline in `host.py` (runner-up, rejected).**
   - Size: it pushes `host.py` from 771 to about 1,050 lines.
   - Call depth: `run_codex_goal`, then `self.spawn_codex_thread`, then `_open_thread` is three levels, which breaks AGENTS principle 1.
3. **Chosen: two collaborators built in `_open()`, as `CodexPreflight` is.**
   - `CodexThreadHelpers` holds the connection, translators, preflight and registry.
   - `CodexSkillFunctions` holds the host itself under TYPE_CHECKING, and composes the public spawn, list, get and interrupt methods. Calls into another class do not count toward call depth, and A006 skips TYPE_CHECKING edges.
   - Every host method is guard plus one delegation.
4. **Error mapping: existence read versus `_rpc_code` overrides.**
   - The probe showed all five new methods return -32600 for unknown ids, with differing messages. Without help they would map to `api_error`.
   - I chose one `thread/read` precheck, which `_rpc_code` already maps to `session_not_found`, over method-specific overrides. Overrides would mislabel busy or invalid refusals as not-found.
   - As a result, `errors.py` is unchanged and only three codes are new.

## Disagreements with the scout or request, with evidence

- **Five bundled skills, not four.** `skills/list` reports five system skills: openai-docs, imagegen, review-agent, skill-creator and skill-installer. Only openai-docs passes the headless rule. The spec has one wrapper; the rest are ✗ with reasons (§9.2).
- **The scout's idea of renaming `CodexResultSerializer._item` is blocked.** `tests/test_codex_output_contracts.py:322` calls `_item`. The spec adds a public `items()` classmethod instead and leaves `_item` untouched (INV-32).
- **Line drift in the scout's anchors.** `StubCodexHost` is at `codex_host_support.py:345`, not 420. The `FailureCode` dot check is at `tests/test_session_failures.py:143`. The spec uses the verified lines.
- **"Empty since-window" was listed as an error case.** The spec returns `()` (D-9), because an empty list is not a failure for any other listing. Raising instead is optional Q-11.
- **"Delete of a loaded thread".** The spec refuses a thread that is running here or that Codex reports `active` (INV-8). It deletes an idle loaded thread (D-14), because refusing would break the common flow of spawn, wait, then clean up. Q-14 covers the stricter reading.
- **INV-9 of codex-host ("no private data").** I read it as "nothing the host reads itself from the Codex home". `list_codex_skills` returns what `skills/list` answers, including `path` and `description`, the same class of data as the `cwd` and preview that `list_codex_threads` already returns. Error messages carry names only, never paths (D-24, T-3).
- **Skill item order changed from my Stage C note.** The spec sends the text item first, then the skill item (INV-25). Nothing in the vendor package fixes the order. My recollection is that Codex's TUI sends text, then skills. That is unverified, and A-7 says so.

## Self-check (Stage E)

**Traceability, checked by script.**
- IDs are contiguous: INV-1 to INV-32, AC-1 to AC-37, EC-1 to EC-40, FR-1 to FR-17, NFR-1 to NFR-9, D-1 to D-24, T-1 to T-5, A-1 to A-15, Q-1 to Q-15, W-1 to W-12, NG-1 to NG-16 and G-1 to G-5.
- Every reference resolves locally. The only exceptions are explicitly labelled citations of the codex-host spec.

**Coverage.**
- Every FR cites an INV or an AC.
- Every AC is in a W row, or in the cross-cutting note under §12.1 for AC-1, AC-34 and AC-35.
- Every §12.3 row cites an FR or a W and names its standard.
- Every EC names an INV or D guard, or is marked accepted (EC-19, EC-20, EC-33).
- Every T names a control.

**Consistency.**
- Names agree across §4, §8.5 and §12.3.
- There are 4 new files (rows 9, 10, 14 and 15), which matches the §8.4 budget.
- The sections are in template order. I fixed §4 and §5, which I had first written after §10.

**File-path rule.**
- §8 now speaks in modules and symbols, except §8.2, which the template allows `path:symbol`. Its exact anchors moved to a new §11 "Evidence anchors" list.
- File paths remain in §1 evidence, §3 reasons, §6 must-not-regress invariants and §13, where the template asks for them.

**Privacy.**
- §9.2 had the real home-folder path and verbatim SKILL.md quotes. Both were replaced with `$CODEX_HOME` and paraphrased reasons.

**Commands.**
- Every gate script exists.
- The venv has ruff 0.16.4.
- **Semgrep is not installed** in the venv or on PATH, and S1 installs nothing. §11 marks the semgrep command unverified and gives the `uvx` form and the `static-policy.yml` dispatch as alternatives.

**Other.**
- No test cases appear anywhere.

## Assumptions I am least sure of

1. **A-4 and A-5: which new methods need a loaded thread.**
   - The probe's different unknown-id messages suggest `thread/compact/start` and `thread/goal/get` look the thread up among loaded threads ("thread not found"). `thread/turns/list` reads persisted history.
   - The spec therefore resumes before compact and goal-get, but not before turns/list.
   - Live QA should check both directions. D-12, D-13 and D-15 each name their flip.
2. **A-2: sort order across cursor pages.** The `since` cut-off assumes `updated_at desc` stays ordered across cursor pages. Only one page was observed.
3. **A-7: skill items.** Codex is assumed to honour a skill item in any position, and to actually load the SKILL.md. Without a paid turn this cannot be shown. D-17's flip adds a readback.
4. **A-8: goal readback precision.** The goal readback compares the objective byte for byte. If Codex normalizes whitespace, `run_codex_goal` would falsely report `command_not_run`.
5. **A-14: delete retries.** The raw path retries `thread/delete` on overload. The spec assumes overload is rejected before work, so no double delete.

## Open items for the next stages

- **Blocking questions:** none.
- **Optional Q-1 to Q-15:** all default to no.
- **S2 must extend the fake before most ACs are observable.** §13 lists:
  - handlers for the five new methods;
  - per-thread `updatedAt`, `source` and parent fields, and a `notLoaded` status;
  - a parameter-honouring `thread/list` whose pages end;
  - stored turns with items;
  - a skills registry;
  - recorded `turn/start` input.
- **S2 updates only the pins** that §13 names.
- **Inherited failure:** `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` still fails, `assert 148 == 120`. It is not this PR's to fix.

## Addendum r2: review round 1 (spec commit deeba11e)

**Input:** `reports/S1-spec-review.md`, verdict SOUND WITH FIXES, 15 findings (2 Blocker, 7 Major, 6 Minor). The orchestrator decided R-3, R-5 and R-6. All 15 are accepted, and each has a row in spec §16. No ID was renumbered. No user reply arrived, so §0.2 is unchanged.

### R-3 probe (read-only, codex app-server 0.162.1)

`probe_r3.py` ran only these calls: `initialize`, then `thread/list` (limit 3), which returned 3 threads, all `notLoaded`. On ONE of them, with its id masked in all output, it ran `thread/read` (includeTurns false), `thread/goal/get`, `thread/read`, `thread/turns/list` (limit 1, itemsView full, sortDirection desc), `thread/read` and `thread/list`. It sent no resume, compact, delete, goal-set or turn-start.

| Call | Result |
|---|---|
| `thread/read` | ok, status `notLoaded` |
| `thread/goal/get` | ok, `{goal: null}`; the thread stays `notLoaded` |
| `thread/turns/list` | ok. Keys: backwardsCursor, data, nextCursor. One turn, nextCursor non-null. Turn keys: completedAt, durationMs, error, id, items, itemsView, rootTurnId, startedAt, status. `completed`, 89 items, the first a `userMessage` (keys clientId, content, id, type; content entries text, text_elements, type `text`) |
| `thread/read`, `thread/list` afterwards | the thread is still `notLoaded` |

**Consequences**
- **A-5 is verified.**
- **A-4 is disproved for `thread/goal/get`**, so D-15 flipped and `get_codex_goal` never resumes (INV-20, new INV-33: no READ function loads a thread).
- **A-4 is unverified for `thread/compact/start`**, because a write is not probeable. Compact therefore keeps its resume, behind a goal check: on a `notLoaded` thread it first runs `thread/goal/get`, and any goal not `complete` raises the new `codex.goal_unfinished` before any resume (INV-18, D-13, AC-38, EC-42).

### Residual risks recorded

- **A-16 / EC-44:** `thread/goal/get` on a `notLoaded` thread reads stored goals. Only `null` was observed.
- **A-17 / EC-43:** resuming a thread with no goal, or a `complete` one, starts no turn. This is unverifiable without a write.
- **A-19:** the `userMessage` is recorded within 5 s of `turn/start`. If wrong, there are loud false `command_not_run` failures, never a silent pass.
- **A-20:** the skill entry persists in `userMessage.content`. The schema allows it (`v2_all.py:9968-9975, 6509-6519`). It has not been observed live.
- **A-18:** `NativeThreadSummary` field types are assumed. The request gives names only.

### Triage summary

| ID | Disposition | Change |
|---|---|---|
| R-1 | Accepted | `thread_list(limit: int \| None = None)`, plus the A007 checklist line |
| R-2 | Accepted | `_valid_arguments` and `_valid_kwargs` added to the §13 authorized pins |
| R-3 | Accepted (orchestrator) | Probe, INV-33, D-15 flipped, compact goal gate, `codex.goal_unfinished` |
| R-4 | Accepted | EC-41, a sentence in INV-18, docstring, tool description and `COMPACT_STARTED_TEXT`; Q-16 `[scope-adding]` |
| R-5 | Accepted (orchestrator) | Skill read-back: INV-34, INV-35, D-17, AC-30, AC-39, AC-40, EC-45, EC-46, 3 messages, 4 constants |
| R-6 | Accepted (orchestrator) | §6.3 §C table; D-9, D-14 and FR-15 marked "Deviates from request §C"; Q-11 and Q-14 repointed |
| R-7 | Accepted | `CodexSkillHost` Protocol; no host import |
| R-8 | Accepted | §12.4 A007, C008, S024 and S008 lines |
| R-9 | Accepted | `CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT` (D-25, AC-41, EC-47) |
| R-10 | Accepted | `from_sdk` unchanged byte for byte |
| R-11 | Accepted | `vidbyte/agents/codex/README.md` read and recorded; no edit, legacy A009 ceiling 65,000 |
| R-12 | Accepted | §4 and AC-1 say 0.162.1 |
| R-13 | Accepted | A-18; D-10 flip |
| R-14 | Accepted (acknowledged) | NG-14 drift note; Q-18 |
| R-15 | Accepted | INV-16 reworded |

### Self-check (Stage E, re-run on r2)

- **IDs:** every new ID is defined and referenced at least once: INV-33..35, AC-38..41, EC-41..47, D-25, A-16..20, Q-16..18. No dangling local reference. D-26 is codex-host's own and carries that prefix. The two codex-host `INV-32 to INV-34` ranges now prefix each ID, because local INV-33..35 exist.
- **Tables:** every table row has its header's column count.
- **Coverage:** every AC is in §12.1 or §12.3. Every FR names an INV or AC. FR-16 is traced through the §9.2 catalog table, noted under §12.1.
- **Counts updated:** 4 codes, 19 classes, 19 host failure codes in the pinned slice, TL;DR, §2 and G-2/G-3/G-5.
- **No tests or production code were written.**
