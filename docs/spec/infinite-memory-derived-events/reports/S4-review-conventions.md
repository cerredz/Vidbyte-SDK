LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the code meets every AGENTS.md principle, placement rule, §12.4 item and lint rule (no rule count moved against base 181f1992), but one record docstring now describes behavior that is gone and three header and spec texts cite or name the wrong thing.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The lint loop did not move. `python lint/run.py` ends `SDK-LINT: PASS`, and every per-rule count matches base `181f1992`. The `--format json` findings for A001, A002, A007, C002, C006, C008, S008, S016, S017, S019, S020 and S024 are byte-identical between base and head.
  - The touched modules add no A007 literal, no A002 miss, no S024 nesting over 3 and no S008 complexity finding.
  - `_in_flight` is changed outside the shield, and the counters start at `INFINITE_MIN_COUNT`. Both are the cost of holding A007 exactly at its baseline (255), and both are recorded as deviations 1 and 2 in §17 r5. Do not move them back inside `_shielded`.
- Placement and exports follow the rules.
  - The three enums (`InfinitePairPhase`, `InfiniteRefusalRule`, `InfiniteRefusalSource`) live in `vidbyte/lib/enums/infinite.py`. They are in `vidbyte.lib.enums.__all__` and are not in `vidbyte.__all__` (NG-12).
  - The 8 new records are in `vidbyte/lib/dataclasses/infinite.py`. Each is `@dataclass(frozen=True, slots=True)`, has no defaults, and is validated only through `RecordFieldValidator` and `RecordFieldConverter`.
  - Every meaningful literal (levels, scale, throttle, metadata keys, `"rule"`) is in `vidbyte/lib/constants/infinite.py`.
  - The public API contract is current at 678 exports.
- The call shape is flat (AGENTS.md principles 1 and 2).
  - The 22 public `InfiniteEvents` functions are exactly the 22 kind values. Each new one has the same three steps: the `on_event is None` early return, then `_shielded`, then `_deliver`.
  - The helpers `_rule`, `_quota`, `_launcher_role`, `_usage`, `_count` and `_cut` are leaf helpers; `_rule` dispatches with a single `match`.
  - The one added `except BaseException` (`launch.py:313`) announces the abort and then re-raises with a bare `raise`.
  - Every new step in `InfinitePair.run`, `execute`, `arun`, `_after_tool_iteration` and `run_handoff` has a plain-English comment.
  - Each `@intent` sits on the first comment line within 20 lines of its `def`.
- Comments and READMEs follow house style.
  - Every added comment block is at most 72 columns and sits directly above its code. The five 73-column lines in these files predate the PR (blame `2c84049cf`).
  - The stale comments named in §12.3 rows 1, 3–7, 10 and 12 were rewritten.
  - `vidbyte/agents/infinite/README.md` lists all 22 kinds and is A009-clean at 23,230 characters. `vidbyte/agents/README.md:183` matches row 14.

FINDINGS (ranked, most severe first, max 15)
R-V1 [Minor] [stale-docstring] vidbyte/lib/dataclasses/infinite.py:580 — The InfiniteMemoryDroppedDetails docstring still says only "the verifier dropped" an entry, but memory_dropped now also covers the rule and unchecked drops
  Evidence: `sed -n '578,580p' vidbyte/lib/dataclasses/infinite.py`
    `class InfiniteMemoryDroppedDetails:`
    `"""memory_dropped: one staged entry the verifier dropped, with its staged key, a short cut of its text, the reason, and the note."""`
    By contrast, spec FR-1 (spec.md:304) says: "`memory_dropped` is delivered for reason `rule` (in `_commit`, under the verifier) and reason `unchecked` (in `_finish`, under the pair's last started agent)". The enum docstring in the same PR already says so at `vidbyte/lib/enums/infinite.py:98`: "the verifier dropped it, the pair had no verdict, or a rule refused it".
  Failure:
    - Rule: AGENTS.md principle 2 ("update its comments in the same edit so they never describe behavior that is gone") and A001's how_to_fix ("update it when the module's contract changes").
    - This is the record a consumer's sink receives, so `help()` on it now misstates two of its three reasons. The spec's stale-comment list (§12.3 row 4) missed it, so the implementation followed the spec.
    - A reviewer would write: "This docstring says the verifier dropped the entry, but with reason=rule or unchecked no verifier dropped anything."
  Smallest fix: one docstring line: `"""memory_dropped: one staged entry that was not committed (its verifier dropped it, a rule refused it at commit, or the pair had no verdict), with its staged key, a short cut of its text, the reason, and the note."""`
  Spec IDs: FR-1, AC-3, AC-4

R-V2 [Minor] [file-headers] vidbyte/agents/infinite/events.py:9, vidbyte/agents/infinite/launch.py:9 — Edge-case citations in two headers point to the wrong rows: events.py cites "(EC-10)" for two different cases, and launch.py's reworded sentence cites old EC-37, which says the opposite
  Evidence:
    In the `sed -n '9p' vidbyte/agents/infinite/events.py` sentences:
      "One agent run from two threads calls the sink from both, told apart by run_id (EC-10)" (old spec)
      "A sink that raises KeyboardInterrupt on subagent_finished gets subagent_aborted for the same pair, which then leaves in_flight only once (EC-10)" (new spec)
      Also unprefixed: "(EC-4)", "(EC-17)", "(EC-26)", "(EC-28)".
    The line-10 RELATED DOCS lists `docs/spec/infinite-memory-events/spec.md` first. In that spec, EC-4, EC-10, EC-17, EC-26 and EC-28 are all different cases (non-callable `on_event`, two threads, lone surrogate, same name launched twice, read-only `.runs/`).
    `git diff origin/main...c1c3ecc0 -- vidbyte/agents/infinite/launch.py` changes the sentence
      from "...never reaches execute, so it announces nothing (EC-37)"
      to "...so it is announced as batch_rejected with source middleware when the generator replies (EC-37)",
    but old-spec EC-37 (infinite-memory-events/spec.md:304) still reads "no event for the denial".
  Failure:
    - Rule: A001's how_to_fix ("Keep the guidance specific to this module and update it when the module's contract changes").
    - Rule: the house convention, which `agent.py:9` ("(derived-events EC-14)") and `runtime.py:9` ("(derived-events EC-6)") follow, of prefixing citations of the second spec.
    - A reader who follows "(EC-10)" or "(EC-37)" lands on a row that contradicts the sentence.
    - A reviewer would write: "Two different EC-10s in one header, and EC-37 now cites a row that says the denial emits nothing."
  Smallest fix:
    - events.py:9: prefix the five new citations "(derived-events EC-4)", "(derived-events EC-10)", "(derived-events EC-17)", "(derived-events EC-26)", "(derived-events EC-28)". Keep the header to one line.
    - launch.py:9: change "(EC-37)" to "(derived-events FR-15)".
  Spec IDs: FR-15, §12.4 header item (spec.md:897)

R-V3 [Minor] [file-headers] vidbyte/agents/infinite/memory.py:11, workspace.py:11, journal.py:11, agent.py:11, vidbyte/lib/enums/infinite.py:11, vidbyte/lib/dataclasses/infinite.py:11 — Six touched headers do not list the four new test files that cover them in their TESTS field
  Evidence: a loop of `grep -n '^TESTS:' <file> | grep -o derived | wc -l` printed:
    - 0 for memory.py, workspace.py, journal.py, agent.py, `lib/enums/infinite.py` and `lib/dataclasses/infinite.py`;
    - 1 for events.py, launch.py and runtime.py, which were updated.
    For example, `vidbyte/lib/dataclasses/infinite.py:11` reads "TESTS: ...test_infinite_memory_events_records.py, ...test_infinite_memory_delegation.py, ...test_infinite_memory_workspace.py". The records that this PR adds are proven in `test_infinite_memory_derived_records.py`, which the header does not name. The refusal-rule `details` added to memory.py and workspace.py are proven only in `test_infinite_memory_derived_refusals.py`. (The constants module's generic "the rest of tests/features/infinite_memory_agent/" is acceptable.)
  Failure:
    - Rule: A001 lists TESTS as a required header field ("update it when the module's contract changes").
    - Rule: §12.4's header item: "Every touched module's header is updated".
    - An agent editing `InfiniteRefusalRule` or a refusal raise site runs the TESTS command and misses the only tests that pin the change.
    - A reviewer would write: "TESTS still names only the old files; add the derived ones."
  Smallest fix: add the relevant file(s) to each TESTS line, keeping it one line:
    - `lib/enums` and `lib/dataclasses`: `test_infinite_memory_derived_records.py`
    - memory.py and workspace.py: `test_infinite_memory_derived_refusals.py`
    - journal.py: `test_infinite_memory_derived_pairs.py`
    - agent.py: `test_infinite_memory_derived_run.py`
  Spec IDs: §12.4 (spec.md:897), §12.5 bullet 2

R-V4 [Minor] [spec-docs] docs/spec/infinite-memory-derived-events/spec.md:332, :760, :902 — The spec's lint pass line names a banner that this repository never prints
  Evidence: `grep -n 'AGENT-LINT' spec.md` finds 332 (NFR-7: "The agent lint ends `AGENT-LINT: PASS`"), 760 ("Its final line must read `AGENT-LINT: PASS`") and 902 (§12.4). But `lint/core/report.py:58` reads `blocks.append("SDK-LINT: PASS" if self.exit_code() == 0 else "SDK-LINT: FAIL")`. S3's report (`reports/S3-implementer.md:204`) noted the mismatch, but r5 did not correct the spec.
  Failure:
    - Rule: house style for specs, under which acceptance text must be checkable verbatim.
    - Read literally, NFR-7 can never pass.
    - A later stage that greps for the spec's string would report a false failure.
  Smallest fix: replace `AGENT-LINT: PASS` with `SDK-LINT: PASS` at the three lines. This is a docs-only edit.
  Spec IDs: NFR-7

R-V5 [Minor] [scope-adding] vidbyte/lib/dataclasses/infinite.py:760 — InfiniteWorkspaceUsageDetails.level accepts any whole number from 0 to 100, though only 0, 50, 75, 90 and 100 can ever be emitted
  Evidence: `RecordFieldValidator.require_int(self.level, "InfiniteWorkspaceUsageDetails.level", minimum=INFINITE_MIN_COUNT, maximum=INFINITE_EVENT_PERCENT_SCALE)`
    Spec §8.5 (spec.md:590) defines `level` as "count, ≤ INFINITE_EVENT_PERCENT_SCALE", "the highest of INFINITE_EVENT_USAGE_PERCENTS reached ..., else 0".
  Failure: AGENTS.md principle 4 asks each record to check "allowed values". The implementation follows the spec exactly, so this is a spec-level choice and not an implementation defect.
  Smallest fix: `[scope-adding]` In `__post_init__`, also refuse a `level` that is neither `INFINITE_MIN_COUNT` nor in `INFINITE_EVENT_USAGE_PERCENTS`. Raise `ConfigurationError` naming the field, as the validator does. This needs a spec amendment first.
  Spec IDs: n/a

Not flagged, after checking:
- The six §17 r5 deviations are each necessary and recorded:
  - A007 baseline (1, 2);
  - the events.py 660-line cap (3);
  - an I001 regression fixed by `542124fa` (4);
  - the §12.4 header item (5);
  - revision numbering (6).
- Several functions grew: `InfinitePair.run` from 59 to 85 lines, `execute` from 47 to 54, `arun` from 62 to 66, `run_finished` from 15 to 27 and `subagent_finished` from 33 to 40. AGENTS.md sets no length limit, and S008 and S024 are unchanged.
- P2's single commit `611f14e0` (required by §12.6).
- Lines over 72 columns in the new test files. The pack's existing files have them too, and only S2 edits tests.

VERIFIED CLAIMS:
1. Lint did not move. "`python lint/run.py` ends SDK-LINT: PASS, no baseline raised, no suppression added" (S3 report :10): HELD. Head ends `SDK-LINT: PASS`, and per-rule counts equal base `181f1992`, which I linted from an archive in a scratch repository. The 12 per-rule JSON diffs are empty. S064 RATCHETED 4 is the same at base. `git diff origin/main...c1c3ecc0 | grep -c '^+.*noqa\|type: ignore\|pragma'` gives 0.
2. The pack passes. "Infinite-memory pack passes 414 of 414": HELD (`414 passed in 9.04s`).
3. No edit to runtime.py, base.py, middleware or pipelines (NG-7, INV-20). Also none to lint/, scripts/, contracts/, pyproject.toml or `vidbyte/__init__.py`: HELD (`git diff --name-only` over those paths prints 0 lines).
4. Line caps hold at 660, 470 and 870, and headers end at line 12: HELD. events.py has 670 total, 658 after the header; launch.py 467 and 455; lib records 844 and 832.
5. "Public InfiniteEvents functions equal the 22 kind values" (§12.4): HELD. The inspect check printed `22 True`.
6. "No except BaseException except InfinitePair.run's, which re-raises": HELD. The diff adds exactly one, at `launch.py:313`, followed by `launch.events.subagent_aborted(self, exc, phase)` and a bare `raise`.
7. "New enums exported from vidbyte/lib/enums/__init__.py, none added to vidbyte/__init__.py" (NG-12): HELD (`[True, True, True] [False, False, False]`). The public API contract is current at 678 exports.
8. "Every multi-line comment is ≤ 72 columns": HELD for every added source comment. The only 73-column lines in these files predate the PR (blame `2c84049cf`).
9. Commit hygiene: HELD. There are 11 source commits on `origin/main..c1c3ecc0 -- vidbyte`, each with a conventional prefix and cited W-, FR- and AC- IDs, and each with exactly one Co-Authored-By trailer. None contains secrets or generated files. `542124fa` fixes the I001 that `8a9b68fc` introduced, and is recorded as deviation 4.
10. "No other docs need change" (§12.5 last bullet): HELD. `git grep` for the kind names, `InfiniteEventKind` and `on_event` outside docs/, tests/ and the source found only the two READMEs, plus the unrelated `skills/vidbyte-sdk/multi-agent.md:93`.
11. "Tests unchanged since S2 (2cab5070)": HELD. `git diff --stat 2cab5070 c1c3ecc0 -- tests` is empty.
12. "Ruff clean on touched files": HELD ONLY AS "NO NEW FINDINGS". The repository has no ruff config, and under default rules ruff reports 6 findings: BLE001 and UP017 ×4 in `_shielded`, the journal and the workspace, plus RUF022 in `enums/__init__.py`. The base copy has the same 6 rule and location pairs, so all are pre-existing. The repository's gate is S051 in `lint/run.py`, and it is unchanged.
13. "The derived spec is cited in every touched header's RELATED DOCS" (§12.4): HELD in all 10 touched modules. "TESTS updated" did NOT hold in 6 modules (R-V3).

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python lint/run.py | tail -4` → `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS`
- For each of 12 rules, `python lint/run.py --rule <ID> --all --format json` at head and on the base archive (scratch repository, not the worktree), then `diff` → no differences.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider | tail -2` → `414 passed in 9.04s`
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 1332a34e... (vidbyte-sdk 0.4.0, 678 exports).` exit 0
- `python -m ruff check <touched modules> --no-cache --output-format concise`, run at head and at base → `Found 6 errors.` both times, with the same rules and locations.
- `git diff --name-only origin/main...c1c3ecc0 -- lint scripts contracts pyproject.toml vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines vidbyte/__init__.py | wc -l` → `0`
- `wc -l events.py launch.py lib/dataclasses/infinite.py` → `670 / 467 / 844`
- `python -c "inspect InfiniteEvents public functions vs InfiniteEventKind"` → `22 True`
- `git diff origin/main...c1c3ecc0 -- vidbyte | grep '^+.*except BaseException'` → one line, at `launch.py:313`, followed by `raise`
- `git log --format='%h %s' origin/main..c1c3ecc0 -- vidbyte` → 11 commits. The Co-Authored-By count per commit was `11 1`.
- `grep -n '^TESTS:' <10 touched modules>` → derived files named in 3 of 10 (R-V3).
- `sed -n '9p' events.py launch.py | grep -o '(...EC-..)'`, compared with `grep '| EC-' docs/spec/infinite-memory-events/spec.md` → collisions at EC-4, EC-10, EC-17, EC-26 and EC-28, and EC-37 contradicts the sentence (R-V2).
- `grep -n 'AGENT-LINT' spec.md`, then `sed -n '58p' lint/core/report.py` → 332, 760 and 902, against the `SDK-LINT` banner (R-V4).
- `git diff --stat 2cab5070 c1c3ecc0 -- tests` → empty
- HEAD is now `6185889b`. It differs from `c1c3ecc0` only in `docs/spec/infinite-memory-derived-events/pipeline.md`.
