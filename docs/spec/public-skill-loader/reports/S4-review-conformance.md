LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — Every §12.3 row is built, and every FR, INV, and AC holds for the arguments the consumer will actually pass. JevAgent is byte-identical. One promise in §9.2 row 1 and INV-2 ("any iterable except str or bytes is accepted"; "a violation raises ConfigurationError") is false for two kinds of argument. The contract text needs a one-sentence correction before the vidbyte-cli pipeline resumes against §9.2.

Reviewed: `git diff c9d31a7f...c691c176` (15 production files, the S2 pack, and S3's spec edits to the frontmatter and §17). Local HEAD is `88dc6c54`, which adds one docs-only orchestrator note that is not under review.

WHAT THE IMPLEMENTATION GETS RIGHT (do not "fix" these)

- **Public door and contract.** I extracted the §4 snippet verbatim from the spec and ran it from an empty temporary folder. It prints exactly `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']`. The three root names are the defining-module objects (`is`).
  - The contract adds exactly `ConfigurationError`, `SkillLoader`, and `SkillResolution` (639 → 642 exports), removes nothing, and reads `0.3.1`. `--check` reports it current.
  - It was committed alone (`46c074c3`, 1 file), directly on the commit it stamps (`56541481`), and no later commit touches the generator's inputs.
  - Remote CI `38811100780` (source and package stages) and Static policy `38811104841` are both `success` on `46c074c3`.
- **Both doors (INV-18).** I ran a seeded sweep of 6,000 tuples and lists (seed 4242) over all six entry kinds plus `SkillDocument`. Names included the case, space, and Unicode variants `pdf`, `PDF`, `pdf `, `café`, and `cafe\u0301`. It found 0 disagreements between `JevAlignmentSettings(skills=t)` and `SkillLoader(t)` (3,582 accepted, 2,418 rejected, with equal `details["names"]`). The same entry twice gives `{'names': ['pdf']}` from both doors.
- **JevAgent and the boundaries are untouched.**
  - `git diff -- vidbyte/agents/jev/` and `-- lint/` are both empty.
  - The tests tree contains only S2's additions (`A`, one commit `d34a8c3e`), and `467555d9..c691c176 -- tests/` is empty.
  - The Jev area suite passes unedited.
  - All nine INV-16 places read `0.3.1`. `0.3.0` survives outside `docs/` only in a test comment.
  - No suppression was added to production code. The three `# type: ignore[arg-type]` in the diff are in S2's pack, which has precedent in the Jev pack.
- **The AC proofs can fail.** I injected five mutants at runtime through a scratch pytest plugin, with no change to the worktree. Each one turns the pack red:

  | Mutant | Failures |
  |---|---|
  | 1-based positions | 9 |
  | Names checked before elements | 1 |
  | Names case-folded | 2 |
  | No name check | 16 |
  | Memory built from the raw argument | 2 |

FINDINGS (ranked, most severe first)

R-C1 [Major] [spec conformance / §9.2 consumer contract] vidbyte/agents/skills/loader.py:45 — The promise "any iterable except str/bytes is accepted, and a violation raises ConfigurationError" is false. The guard is the `collections.abc.Iterable` type check, so an object that iterates only through `__getitem__` is rejected, and a broken iterable escapes as `TypeError`.
  Evidence:
  - The code, `loader.py:45`: `self.entries = SkillEntries(entries=tuple(entries) if isinstance(entries, Iterable) and not isinstance(entries, (str, bytes)) else entries).entries`.
  - What the spec promises:
    - `spec.md:163` (INV-2): "`SkillLoader(entries)` takes any iterable that is not a `str` or `bytes` … Each of these raises `ConfigurationError` … a `str`, `bytes`, or non-iterable argument".
    - `spec.md:430` (§9.2 row 1): "any iterable except `str` or `bytes` is accepted and turned into a tuple once … A violation raises `ConfigurationError`, whose `details` has exactly one of three shapes".
    - `reports/S1-spec-author.md` "Answers to consumer requirements" item 1 repeats this to the CLI pipeline word for word.
  - My probe (`probe_boundary.py`, run with `PYTHONPATH=<worktree>` from an empty folder) gave, public door versus Jev door:

    | Argument | Public door (`SkillLoader`) | Jev door (`JevAlignmentSettings`) |
    |---|---|---|
    | iterable only through `__getitem__` (`GetItemOnly([inl])`) | `ConfigurationError {'entries_type': 'GetItemOnly'}` | `ACCEPT ('InlineSkill',)` |
    | `__iter__` raises `TypeError` (`IterRaisesType`) | `!! TypeError: iter boom` | `ConfigurationError details={}` |
    | `__iter__` returns a non-iterator (`IterReturnsNonIterator`) | `!! TypeError: iter() returned non-iterator of type 'int'` | `ConfigurationError details={}` |
    | `__iter__` raises `RuntimeError` (`IterRaisesRuntime`) | `!! RuntimeError: iter boom` | `!! RuntimeError: iter boom` |
    | generator that raises partway (`gen_raises`) | `!! ValueError: gen boom` | not tested |

    The Jev door gets its behaviour from `except TypeError` at `vidbyte/agents/jev/settings.py:98-101`.
  Failure:
  - **Iterable rejected.** Python's glossary counts a `__getitem__`-sequence as an iterable, and the pre-PR loader iterated it, as the Jev door still does. The public door now rejects it as `entries_type`, which contradicts "any iterable … is accepted".
  - **Wrong exception.** An argument whose iteration fails with `TypeError` (in practice "not iterable") makes the constructor raise a raw `TypeError`. §9.2 promises `ConfigurationError` with one of three `details` shapes. The same object through the Jev door gives `ConfigurationError`.
  - **Not recorded.** The implementer reinterpreted INV-2 to mean "registered iterables" (S3 report, tricky part 1). That reinterpretation is not recorded in spec §17 or §9.2, so the contract the CLI pipeline will resume from still promises the broader behaviour. The loader header's KNOWN EDGE CASES (`loader.py:9`, "Construction raises ConfigurationError for text, a non-collection, …") and the README's Public-door bullet (`vidbyte/agents/skills/README.md:25`, "and otherwise raises `ConfigurationError`") overstate in the same way.
  - **Impact.** For vidbyte-cli, which passes a `list`, the practical impact is nil. The defect is in the published contract text. I rate it Major because the orchestrator ruled that any gap between §9.2 and the code is Major.
  Smallest fix: change text only. The code matches §8.5 and row 2(b) exactly, and §12.4 forbids any `raise` in `SkillLoader.__init__` beyond the one inline expression.
  1. In INV-2 and §9.2 row 1, say "any `collections.abc.Iterable` except `str` or `bytes`". State that an object iterable only through `__getitem__` is rejected as `entries_type`, and that an exception raised while iterating the caller's own argument propagates unchanged (the same stance as EC-18).
  2. Record this under §17 "Implementation deviations (S3)".
  3. Carry the same sentence into the §9.2 hand-off to the CLI pipeline, and optionally into `loader.py:9` KNOWN EDGE CASES and README:25.

  The alternative code fix, which would keep the broad promise, is to hand the raw value to `SkillEntries` when `tuple(entries)` raises `TypeError`. That needs a spec change to §12.4 first and is not the smaller repair.
  Spec IDs: INV-2, INV-3 ("exactly one of three shapes"), §9.2 row 1, D-14, §5 (node T and "loader (or ConfigurationError)"), AC-3 (scope of "not a collection").

No other finding. I tried each of the following and found nothing:
- the weighted words;
- every ID;
- every §12.3 row;
- the §8.4 budget;
- the §14 Never items;
- the deviations, reported and unreported;
- scope creep;
- reversals of a §C decision.

VERIFIED CLAIMS

Claims from the implementer's report, the test plan, and the briefing:

| # | Claim | Result | Evidence |
|---|---|---|---|
| 1 | AC-1: the §4 snippet prints exactly three lines | HELD | Extracted from `spec.md` §4 by awk and run from an empty scratch folder. The output matches `expected.txt` once Windows stdout CRLF is normalized. The test's `SNIPPET` is byte-equal to the spec block |
| 2 | "Don't miss any" version literal | HELD | `git grep "0\.3\.0" c691c176 -- ':!docs'` finds only `test_public_skill_loader_release.py:34` (a comment). `0\.3\.1` appears at all nine INV-16 places, on the lines §9.2 row 7 cites |
| 3 | "Never edit the contract by hand / never amend" | HELD | `46c074c3` changes only `contracts/sdk-public-api.json` (+5/−2). Its parent `56541481` is the stamped `source.commit`. No later commit touches `vidbyte/__init__.py`, `pyproject.toml`, or `contracts/`. `--check` reports it current at `56541481` (0.3.1, 642 exports), and C016 is CLEAN |
| 4 | "JevAgent must keep its current behavior" | HELD | The `vidbyte/agents/jev/` diff is empty, and `JevAgent` still passes `settings.alignment.skills` (`agent.py:81-88`). The Jev area suite passes unedited (the pack plus the area suite: `493 passed, 1 skipped`) |
| 5 | "No test, fixture, baseline, or file outside §12.3 touched" | HELD | The production diff covers exactly the 15 §12.3 files. Commits after `467555d9` change no test file, and `lint/` is unchanged |
| 6 | Lint and ratchets (NFR-3) | HELD | `python lint/run.py` → `SDK-LINT: PASS`. C016 0, S009 350, S015 13, A001 642, A002 566 (baseline 703), A006 34, A009 0, C011 1 (baseline 2), S012 0, S051 259, S060 32. Each is at or below `lint/baseline.json` |
| 7 | Source stage "5243 passed, 14 skipped" | HELD | Full pytest gives `5243 passed, 14 skipped, 1 warning in 76.89s`. `git status` is still clean |
| 8 | Remote CI "in progress" | HELD, and now finished | `gh run view 38811100780` → `completed` / `success` on `46c074c3` (CI, including `--stage package`, `ci.yml:60`). `38811104841` (Static policy) → `success`. PR #1099 is a draft and open, with head `c691c176` |
| 9 | Deviation 1 (wrapped import) was necessary | HELD | The one-line import is 99 columns. Neither `lint/ruff.toml` nor `pyproject.toml` sets `line-length`, so ruff's default of 88 applies |
| 10 | Deviations 2 and 3 are necessary, minimal, and recorded | HELD | §12.6 allows "source commit or commits". §12.3 row 12(b) does not say where the bullet goes. Both are recorded in spec §17 |
| 11 | "INV-2 'any iterable' means registered iterables, consistent with INV-2" | DID NOT HOLD | See R-C1. Not recorded in the spec |
| 12 | Test plan: "ten single bugs … each caught" | HELD | The five I re-ran were caught (see above) |
| 13 | §12.4: comments ≤ 72 columns; no `raise` in `__init__`; `SkillEntries` only in its module's `__all__` | HELD | The widest new comment is 71 columns. `SkillEntries` is not in `vidbyte`, `vidbyte.lib`, `vidbyte.lib.dataclasses`, `vidbyte.agents`, or `vidbyte.agents.skills`. `vidbyte.agents.skills.__all__ == []` |
| 14 | D-14's purpose: the CLI's `mypy --strict` accepts a list | HELD | `mypy --strict` on a scratch consumer that passes `list[SkillEntry]` to `SkillLoader` reports no `arg-type` error. The only error was in my own probe's narrowing |
| 15 | NFR-1: "validation is one pass over the tuple, O(n)" | HELD in substance | It is O(n), but it makes two passes: the `isinstance` loop, then `Counter`. No behavioural effect, so not a finding |

**ID walk** (prosecution against defense; anything not listed held on concrete evidence):

- **FR:**
  - FR-1, FR-2, FR-3: identity probe True ×3; in `__all__`; in the contract.
  - FR-4: held, except the R-C1 corner.
  - FR-5: `load`, `documents`, and `_pending_groups` are byte-identical (the diff hunk covers only the header, imports, and `__init__`). `iscoroutinefunction(load)` is True, and AC-2, AC-7, and AC-13 pass.
  - FR-6: AC-9 passes. It records construction, changes the environment variables before load, and checks each header against its host.
  - FR-7: constants and enums are untouched, and the README bullet says the caller measures `document.text`.
  - FR-8, FR-9: claims 2 and 3.
  - FR-10: AC-16 passes. A grep for stale phrases finds none in the §12.3 files. The remaining "until the first run" is in Jev's own `alignment/skills.py:74`, which is outside §12.3 and correct for Jev.
  - FR-11: claim 4.
  - FR-12: INV-18 sweep.
- **NFR:**
  - NFR-2: 0 files, 1 class, 0 dependencies, 0 keys, 3 names.
  - NFR-4: AC-6 passes. The probe gives `bytearray`/`memoryview` of a token as `{'position': 0, 'entry_type': 'int'}`, with no value.
  - NFR-5: AC-2 covers all six sources plus a document through root imports, with exact bodies.
  - NFR-6: 3 names added, 0 removed. The public members are `load` and `documents`, and the only signature change is `tuple` → `Sequence`.
  - NFR-7: the loader imports only skills modules and `vidbyte.lib`.
  - NFR-8: held, apart from R-C1's text.
- **INV:**
  - INV-1, INV-3 to INV-17: held (load path unchanged; tests; probes; claims 2–5).
  - INV-2: partial (R-C1).
  - INV-18: the 6,000-case sweep.
- **AC:** all 24 Proof references in §6.2 resolve to existing test functions (0 missing). AC-1 to AC-18 pass inside the 493. AC-1 was also run independently. The contract part of AC-10/AC-11 passes through `--check`/C016.
- **EC:**
  - EC-1 to EC-8 and EC-28: probed or tested. A set, a `deque`, and a dict keyed by entries are accepted. `str`, `bytes`, `None`, `int`, and a single entry give `entries_type`.
  - EC-9 to EC-27: the load path, resolvers, constants, and detail strings are unchanged.
  - EC-29: documentation only.
- **§12.3 rows 1–15:** each was checked against its hunk.
  - Row 1: record placement, check order, and `@intent` text are correct.
  - Row 1(d): TESTS names 4 of S2's 7 modules. These are the ones that exercise the record, so I did not raise it.
  - Row 2(a)–(d): correct. The header keeps WHAT NOT TO DO 1–4.
  - Row 3(a)–(f): import positions and the `__all__` position are exact.
  - Rows 4–10: one line each.
  - Row 11: generated, alone.
  - Rows 12–15: the text matches the prescribed wording. "Notes for agents" is still last.
- **§5 diagram:** it matches the call path. The one divergence is the R-C1 corner, where the constructor can also raise `TypeError`, not only `ConfigurationError`.
- **request.md:**
  - §A: all asks are met. Version 0.3.1 is the settled D-13.
  - §C: no decision is reversed. The existing loader is exposed, not rewritten, and JevAgent is untouched.
  - Scope creep: none. Every addition maps to a §12 row.

COMMANDS RUN

- `git diff --stat c9d31a7f...c691c176` → 36 files, of which 15 are production files, 9 are S2 test files (`A`), and the rest are pipeline docs.
- `git diff --stat c9d31a7f...c691c176 -- vidbyte/agents/jev/` → empty. `-- lint/` → empty. `git diff --stat 467555d9 c691c176 -- tests/` → empty.
- `git grep -n "0\.3\.0" c691c176 -- ':!docs'` → only `tests/.../test_public_skill_loader_release.py:34` (a comment). `git grep -n "0\.3\.1" …` → the nine places plus tests.
- `git show --stat 46c074c3` → `contracts/sdk-public-api.json | 7 +++++--` / `1 file changed`. `git rev-parse 46c074c3^` → `56541481fbb3…`.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 56541481fbb32624aa70ff26b9f4feeb496ea273 (vidbyte-sdk 0.3.1, 642 exports).` exit 0.
- §4 snippet (`awk` extract → `$SCRATCH/s4conf/scripts/snippet.py`, run from `$SCRATCH/s4conf/empty` with `PYTHONPATH=<worktree>`) → exit 0, three lines, `diff` → IDENTICAL.
- `probe_boundary.py` → output shown under R-C1.
- `probe_doors.py` → `INV-1 identity: True True True`; `INV-18 sweep: 6000 cases, 0 mismatches, 3582 accepted, 2418 rejected`; `SkillEntries root: False SkillFetchStep root: False`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader tests/features/jev_skills_preload tests/test_jev_skill_preload.py` → `493 passed, 1 skipped in 5.60s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `5243 passed, 14 skipped, 1 warning in 76.89s`. `git status --short` → clean.
- `python lint/run.py` → `SDK-LINT: PASS` (exit 0), with the per-rule counts as in claim 6.
- Mutants: `S4_MUTANT=<m> PYTHONPATH="<worktree>;$SCRATCH/s4conf/plugin" python -m pytest -q -p s4_mutant tests/features/public_skill_loader` → pos1 `9 failed, 58 passed`; order `1 failed, 66 passed`; casefold `2 failed, 65 passed`; nonames `16 failed, 51 passed`; rawmem `2 failed, 65 passed`.
- `gh run view 38811100780` / `38811104841` → `completed` / `success` on `46c074c38ec4…`. `gh pr view 1099` → `isDraft: true`, `state: OPEN`, head `c691c176`.
- `python -m mypy --strict` on the scratch consumer → no `arg-type` error at the `SkillLoader(list[SkillEntry])` call.

`$SCRATCH` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1d2c8a26-e7b8-4bc3-b449-2665a570335d/scratchpad`. The probe scripts and the mutant plugin are there. Nothing was written to the worktree except this report.
