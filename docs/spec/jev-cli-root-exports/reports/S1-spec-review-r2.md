VERDICT: SOUND WITH FIXES — The r2 split into permanent and one-time facts, the INV-2 table, and the A → B → draft PR → C order all hold when executed. Three one-time proofs or 6.1.a sentences still fail in states this run will plausibly reach: main has already moved, a header-only fix after commit A, and an attribute sweep. Commit C is also handed off when S3 could make it itself.

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)

- **The split works.** Each 6.1.b invariant maps to exactly one "Proven once" row that names a concrete command and where its output goes (the Proof column or the implementer report): INV-3 → AC-5, INV-6 → AC-6, INV-8 → AC-9, INV-14 → AC-12, INV-15 → AC-13, INV-16 → AC-14, INV-17 → AC-15. A token scan of 6.1.a and the "Tested" table finds no 664, 668, 948, hash, `0.4.0`, `git show` or merge base. The `base_commit` mentions that remain are context, apart from the two sentences in R-3. INV-4 and AC-4 use the superset form and the version-equality form, which survive later root exports such as Q-1's browser names or R3's names.
- **The INV-2 table is exact.** On a scratch copy with row 1 applied, every cell holds for both `is` and `__all__` membership, and every named non-pairing is absent. Exactly the two defining modules the spec names lack an `__all__` entry. A static AST scan of every `__all__` under `vidbyte/**` finds no listing outside the table.
- **The three-commit order is executable and keeps provenance true.** The deriver's `read_paths` are exactly `('pyproject.toml', 'vidbyte/__init__.py')` (`lint/core/public_api_contract.py:431`). A scratch git run of A → generate → B → C printed:
  - at commit A, AC-5's line verbatim (`… is stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode`, with no `removed` line);
  - for row 3, its console line (`wrote … at <A> (vidbyte-sdk 0.4.0, 668 exports)`);
  - after commit C, which touches the release note only, `current at <A> (… 668 exports).`
  
  The `#<n>` never-commit rule closes the placeholder risk.
- **Row 1 is unchanged from r1 and still clean.** It adds 9 lines and removes none (1467 → 1476). ruff I001 reports 0 root lines (223 findings in both trees). S015 shows the same 4 root findings. The edited tree loads the same 948 `vidbyte*` modules as base, with SHA-256 prefix `ff657e9052f220c0`. The four contract names sit after AgentInput, JevDoneResult, ParentPolicy and TextContextItem, as row 3 says. AC-1 prints its four lines verbatim with the keys unset. Row 2's three "before" strings each occur once and are untouched by main's new commits.

FINDINGS (ranked, most severe first, max 15)

R-1 [Major] [L11] §6.1.b INV-3/6/16, §6.2 AC-5/6/9/14/15, NFR-3, §12.6 P4 — main has already moved, and P4 tells S3 to merge it, but the one-time proofs diff against the fixed `b7350ed6`, so AC-6 fails as written on this run
  Evidence:
  - The spec, P4: "If `main` moved, merge it".
  - The spec, AC-6: "`git diff --name-only b7350ed6 HEAD` … lists only the three §12.3 files, the test author's files, and `docs/spec/jev-cli-root-exports/**`".
  - The spec, INV-6: "only the three files in §12.3 differ from `base_commit`". NFR-3 uses `git diff --stat <base_commit>`, and AC-14 archives `b7350ed6`.
  - The repo: `git rev-parse origin/main` and `git ls-remote origin refs/heads/main` both give `0cce5781`. That is `b7350ed6` plus #1184 (`513aa614`) and #1188 (`0cce5781`).
  - `git diff --name-only b7350ed6 origin/main | wc -l` gives 51 files: `tests/features/sdk_provider_keys/*`, `vidbyte/lib/registries/provider_keys.py`, `docs/spec/infinite-memory-prompts/**`, `vidbyte/prompts/prompts/infinite_memory/*`, and others.
  Failure: S3 follows P4 and merges main. AC-6's first command then lists 51 more files, and INV-6, read literally, is false. S3 records a failed P0 proof, or it treats the result as "touching files outside §12.3" (§14 Ask first) and stops BLOCKED. Meanwhile the facts the proofs exist to protect are all still true:
  - `git diff --name-only b7350ed6 origin/main -- vidbyte/__init__.py pyproject.toml contracts docs/design/release-0-4-0.md lint/baseline.json README.md llms.txt` prints nothing.
  - #1184 changes no import line.
  - Main's two changed test packs pass on a `git archive origin/main` copy (383 passed).
  
  So 668, 29, row 2's anchors, the module set and NFR-2's five failures all survive the merge.
  Smallest fix: Measure each one-time diff against the merge base, as S3's own Phase 4 already does (`git diff origin/main...HEAD`).
  - Define `B=$(git merge-base origin/main HEAD)`. It equals `b7350ed6` until main is merged.
  - Use `$B` in AC-5, AC-6, AC-9, AC-15 and NFR-3, and archive `$B` in AC-14.
  - Word INV-3, INV-6, INV-8 and INV-16 as "against the merge base (`b7350ed6` at S1)".
  - Optionally add one line: main's delta since `b7350ed6` (#1184, #1188) touches no gated path, so P4's merge is optional for correctness.

R-2 [Major] [L5/L11] §6.1.b INV-15, §6.2 AC-13, §6.3 EC-6 — Any later commit that edits only non-export text of the root makes AC-13 fail for good, and EC-6's remedy (regenerate) does nothing, by the generator's own design
  Evidence:
  - The spec, INV-15: "commit A's `vidbyte/__init__.py` and `pyproject.toml` are identical to the head's".
  - The spec, AC-13: "`git diff <source.commit> HEAD -- vidbyte/__init__.py pyproject.toml` … the diff prints nothing".
  - The spec, EC-6: "if commit A's inputs change, regenerate in a new commit".
  - The generator, `scripts/generate-sdk-public-api.py:65-67`: when `committed.contract.data == derived.data`, it returns `_restore_canonical` before any dirty check or re-stamp. Its header, KNOWN EDGE CASES: "The file is left untouched when the derived data is unchanged, so source.commit keeps naming the commit whose inputs produced it."
  - Scratch git repo:
    - Commits A → B → C, then A2, which only rewords the new header bullet ("can set" → "can configure").
    - The regeneration prints `… is already current at 4f78b59e…; nothing written.`, and `source.commit` is still A.
    - `git diff <source.commit> HEAD -- vidbyte/__init__.py pyproject.toml | wc -l` gives 13.
  Failure: Several plausible edits change the root without changing `__all__`: a conventions reviewer rewording the AC-11 bullet in S5, or an S3 fix-up for I001 placement after commit A. After any of them, the P0 proof AC-13 cannot pass. The only ways to make it pass are a hand edit of the contract (§14 Never) or amending commit A (rewriting history the draft PR already shows). So the repairer reports a failed proof, or stops BLOCKED, over a contract that is correct.
  Smallest fix: State INV-15 and AC-13 as the repo's own provenance rule:
  - "`--check` exits 0 at the head and reports `current at <source.commit>`, `source.commit` is a commit on the branch, and `git show <source.commit>:vidbyte/__init__.py` lists the four names."
  - Drop "identical to the head's" and the empty-diff clause.
  - Reword EC-6: "if a later commit changes the derived data, regenerate in a new commit; if it changes only other text in an input, the generator correctly keeps `source.commit` and nothing is regenerated."

R-3 [Major] [L10] §6.1.a INV-2, INV-11, §13 "Facts the tests may rely on" — Two sentences in 6.1.a are not permanent properties: INV-2's "and at no other place" is false for attributes, and INV-11's "… are unchanged" is a diff fact that Q-1 would change
  Evidence:
  - The spec, INV-2: "`vidbyte.<name>` is the very object (`is`, not `==`) found at every path in that name's row below, and at no other place", and "Pairings outside the table do not exist".
  - The spec, §13: "the INV-2 table, and only it".
  - My probe on the row-1 scratch copy: the objects are attributes of 16 loaded modules (`AgentLoopSettings`), 19 (`PermissionPolicy`), 15 (`TextModelMode`) and 8 (`JevDynamicComputeOption`). For example:
    - `vidbyte.agents.jev.settings` holds all four.
    - `vidbyte.agents.base` holds three.
    - `vidbyte.tools.executor` and `vidbyte.agents.coding` hold `PermissionPolicy`.
    
    The `__all__` listings match the table exactly, so the table is right and the clause is wrong.
  - The spec, INV-11: "Today's `__getattr__`/`__dir__` block (`vidbyte/__init__.py:1449-1467`) and `_LAZY_NATIVE_THREAD_EXPORTS` (`:1435-1445`) are unchanged".
  - The spec, Q-1: it would add the 11 browser names "lazily through `_LAZY_NATIVE_THREAD_EXPORTS`".
  Failure: The 6.1.a heading says "tests assert these".
  - A blind S2 can test "at no other place" by sweeping `sys.modules` for `getattr(m, name) is obj`. That test can never pass, so S3 stops BLOCKED.
  - S2 can test "unchanged" only by snapshotting the lazy mapping, because comparing against base is forbidden. That test goes red on main the day Q-1 lands.
  Smallest fix:
  - INV-2: replace "and at no other place" and "Pairings outside the table do not exist" with: "No other module lists it in its `__all__` today. This is context, not a test: many modules import these classes for their own use (`vidbyte.agents.jev.settings` holds all four), so no test sweeps attributes or asserts absence."
  - INV-11: keep the behavior sentence. Move the "… are unchanged" sentence to 6.1.b, where INV-3 and INV-6's diff already prove it.
  - §13: change "and only it" to "the positive pairings".

R-4 [Minor] [L8/L11] §12.6 P3, §14 Always, A-1 — Commit C is routed to "the agent that opens the draft PR", and "pending" is the expected outcome. In this pipeline that agent is S3 itself, so commit C can land inside S3, before review
  Evidence:
  - The spec, P3: "If that command finds no PR when P2 is done … reports row 2 as **pending** … The agent that opens the draft PR then applies row 2 as commit C".
  - The spec, A-1: "opened after commit B, at the end of S3".
  - `spec-pipeline/prompts/s3-implementer.md`, Phase 6: `git push -u`, then `gh pr create … --draft`, then "commit `docs(spec): record draft PR for [SLUG]` and push again". Phase 7 commits and pushes again. S3 therefore commits after the PR exists.
  - `s6-pr-author.md`: "without changing a line of source".
  Failure: P2 always ends before S3's Phase 6, so a literal S3 reports row 2 pending and moves on. The three S4 reviewers then review a PR whose release note still says `TextModelMode` is "not the root" and that the contract lists 664 (FR-7 and AC-15 are open). That costs a conformance finding and an S5 round, or it pushes the edit to S6, after review. No placeholder can be committed, because the never-commit `#<n>` rule holds.
  Smallest fix: Add one sentence to P3, §14 Always and A-1: "S3 opens the draft PR in its Phase 6. Right after `gh pr create`, S3 reads the number, applies row 2 alone as commit C, reruns `--check` (expect `current at <commit A>`) and the AC-15 diff, and pushes. Row 2 is pending only if `gh pr create` itself fails."

VERIFIED CLAIMS
- **Round-1 closures.** R-1: closed, except for R-3 above. R-2: closed and executable, apart from the routing in R-4. R-3: closed, and every cell and non-pairing is true. R-5, R-6, VC-1 and VC-2: closed.
- **INV-2 and INV-13 (identity, re-export paths, source lines): HELD.**
  - Every path in the table is the root's object, and each re-export path lists the name in its `__all__`.
  - `loop` and `security` have no `__all__` entry. `text_model` and `jev` do.
  - The named non-pairings are all absent: `vidbyte.lib.config` has no `PermissionPolicy`; `vidbyte.agents.settings` has only `AgentLoopSettings`; `vidbyte.agents.jev`, `vidbyte.lib` and `vidbyte.tools` have none of the four.
  - The INV-13 lines hold: `agents/__init__.py:258-264` and `:323`; `lib/enums/__init__.py:122`, `:204`, `:284` and `:347`; `lib/config/__init__.py:16` and `:34`; `lib/dataclasses/__init__.py:201` and `:413`.
- **Generator inputs: HELD.** `lint/core/public_api_contract.py:431` reads `pyproject.toml` and `vidbyte/__init__.py` only. `_dirty_inputs` is at `:118-121` and `_head_commit` at `:132-135`. `--check` itself runs no git command, but `SourceCatalog` uses `git ls-files`, so any test that runs it needs a git checkout. CI and the source stage have one, and the package stage runs no pytest.
- **EC-4: HELD.** On a dirty root, the generator prints "SDK public-API contract not written: these input files have uncommitted changes:" and writes nothing.
- **S015 `_exports`: HELD.** `s015_public_export_integrity.py:48-53` reads the first literal list only. `public_api_contract.py:5` accepts `+=`, `.extend` and `.append`.
- **INV-16 and AC-14: HELD.** Base and edited trees both load 948 `vidbyte*` modules, with SHA-256 prefix `ff657e9052f220c0`. `vidbyte.harnesses.native` is not loaded.
- **INV-5, INV-7, INV-9, INV-10, INV-11 (behavior part), INV-12 and AC-1/2/3/8: HELD on the edited tree.**
  - The default policy allows `['read', 'safe']`, and `allow_all()` equals `frozenset(ToolPermission)`.
  - The `model_mode` default is `AUTO`, and a string `model_mode` raises the stated `ConfigurationError`.
  - The compute default is `fresh_agent, fork_agent, subagent`, and loop gives `None None None 25 3`.
  - Star import binds all 668 names.
  - Misspelled names raise `AttributeError` or `ImportError`, and native stays unloaded.
  - There is exactly 1 `- Agent setting exports:` bullet, naming all four, and `- Error exports:` contains `ConfigurationError`.
  - INV-7's member lists are already pinned on main (`test_provider_keys_contract.py:43`, `test_jev_compute_situations.py:105`), so a new pin adds no new break.
- **A-2 error text: HELD.** `ConfigurationError: Unsupported model provider: 'notaprovider'`. `settings.py:137` reads `provider: ModelProvider | str`.
- **D-9: HELD.**
  - `git show 64e2bd67` shows the ROLE text ("…by the package root vidbyte/__init__.py, which re-exports SkillLoader as a public name") and the README text ("…for any caller that imports `SkillLoader` from the package root").
  - `security.py:12` names only `vidbyte.tools.security.permissions` as a re-exporter.
- **T-1: HELD.** `security.py:48-56` `check` honors `PermissionCeiling`, and `permission_ceiling.py:27` defaults the ceiling to `None`.
- **Test citations: HELD.**
  - `test_infinite_memory_contract.py:166-169` holds.
  - The native contract read is at `:139-142`, not `:138-141`; the version equality is on `:142`. This is harmless.
  - `test_public_skill_loader_release.py:99-115`, `test_harness_threads_surface.py:227-235` and `:259-261`, `test_public_skill_loader_docs.py:24-41` and `:91`, and `public_skill_loader/FEATURE.md:95` all hold.
- **Prior art: HELD.** `OTHER_EXPORTERS` checks the `__all__` of 5 fixed modules. `fresh_interpreter` sets `PYTHONPATH=REPO_ROOT`. `optional_merge_base`, `merge_base` and `literal_all` exist at `:95`, `:103` and `:110`.
- **Row 2: HELD.** Each of the three "before" strings occurs once. `lists it beside #1099.` ends line 17. 639 + (3+4+17+4+1) = 668. #1184 and #1188 do not touch the file.
- **Baselines: HELD.** `lint/baseline.json` gives C016 0, S015 13, A001 642, S051 259 and S020 1. `--check` on HEAD prints "current at ebd18517… (vidbyte-sdk 0.4.0, 664 exports)".
- **L9 consistency: HELD.**
  - Withdrawn EC rows are referenced only in their struck rows and in §16.
  - §12.1 Serves covers AC-1 to AC-15.
  - The TL;DR and D-8 say three commits.
  - §8.4 is unchanged (0 new files, 3 changed).
  - Row 1's "what changes" text is byte-identical to r1.
- **Stale framing, no effect on code or tests: FALSE in places.** #1184 has merged (`513aa614`), so NG-4, §9.4 and A-3 ("waits on SDK #1184") are stale framing. §11 calls `0e7a8eb0` part of `origin/main`, but it is this branch's first commit.
