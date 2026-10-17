LENS: conformance
VERDICT: SOUND — the fixes for R-26 and R-27 hold against their review.md evidence, and R-28 holds except for one false sentence. Nothing regressed in the pack (111 passed), AC-1, lint, or the full suite. Two Minors remain, both about documentation or wording: R-C1 is a trivial doc edit, and R-C2 is a follow-up.

Scope of this round: `git diff da338f59..149fea25 -- vidbyte docs/spec/infinite-memory-agent/spec.md` changes three things. They are `vidbyte/agents/infinite/workspace.py` (+20/−4), one bullet in `vidbyte/agents/infinite/README.md`, and spec §17. `274e54d0` changes only `pipeline.md`. Since `11b19a7d`, no file under `tests/` has changed, and `lint/` matches `origin/main`. The follow-up Minors R-14, R-19, R-20, R-22, R-24, R-25 and R-29 are not raised again: none of these fixes made any of them worse.

WHAT THE IMPLEMENTATION GETS RIGHT
- **R-26 restores INV-21's "copied, overwriting" for every construction.** `copy.chmod(copy.stat().st_mode | stat.S_IWRITE)` (`workspace.py:83`) runs after every unconditional copy. The edited-seed case is therefore re-copied, not skipped. The guard that keeps tools out of `seed/` is `_note_path`'s path check (`workspace.py:310-312`), not the file mode. `write_note seed/…`, `write_note Seed/…` and `edit_file seed/…` are all still refused, and the copy's bytes do not change.
- **R-27 closes every encoding route to a half-finished multi-file write.**
  - The check in `_entry_rules` (`:271-272`) covers the only free text in an entry line, `text` and `refs`. Tags are slugs, and the keys, run id and stamp are fixed by their patterns. `commit_entry`'s other lines are read with `errors="replace"`.
  - `write_note` (`:180-181`) encodes every value of `changed`. That includes the `files.jsonl` record, so the path and the description are covered too.
  - `edit_file` writes one file, and `_replace` already makes that write atomic.
  - The journal is ASCII, so it cannot fail on encoding.
  - Every staged entry enters only through `memory.py:88-90`, after `check_entry`. So `_commit`, which catches only `ToolExecutionError`, never meets a `UnicodeEncodeError` (INV-29 is unchanged).
- **The pair case is correct under INV-15, INV-16 and INV-17.** The bad entry is refused when it is staged, with the quota line and no quota spent, so it is never staged and never appears in `dropped`. The verdict stays `passed`, the valid entries commit in order, and staged keys stay contiguous.
- **No scope was added.** The only source edits are the two encode loops, the chmod, one `import stat`, comment and header text, and one README bullet. The scope deviation was reported (INV-20 was left alone and the rule recorded in §17 instead), and it was the narrower choice the briefing granted.

FINDINGS (ranked, most severe first)

R-C1 [Minor] [deviations] docs/spec/infinite-memory-agent/spec.md:1246; vidbyte/agents/infinite/README.md:69 — R-28's record says the catalog check gives `model_name` "the same meaning as `BaseAgent`" and makes it behave "as for the SDK's other agents", but a plain `BaseAgent` runs models these settings refuse. The §17 S5 list also leaves out one rule that S5 added.
  Evidence (the false sentences):
    - §17 says: "…the SDK's declarative `BaseAgentSettings` applies the same check, so §9.3's "same meaning as `BaseAgent`" holds."
    - The README says: "`model_name` must be in `ProviderModelRegistry`'s catalog under `provider`, as for the SDK's other agents".
  Evidence (the probe): `PYTHONPATH=$(pwd) python $W/p2_escape_hatch.py $W/w5` prints, with the default STRICT_MODEL_VALIDATION=True:
      strict=True openai/gpt-4.1-2025-04-14 | infinite: ConfigurationError: InfiniteMemoryAgentSettings.model_name must be a model the SDK can run | BaseAgent: runner TextModelRunner
      strict=True openai/gpt-7 | infinite: ConfigurationError: … | BaseAgent: runner TextModelRunner
      strict=True anthropic/claude-opus-9 | infinite: ConfigurationError: … | BaseAgent: runner TextModelRunner
    With strict=False, every row matches `BaseAgent` exactly, so the escape-hatch sentence is true.
    Round 1's own R-C3 evidence says the same thing: "`BaseAgent(...)` constructs and `_runner_for_model()` returns a `TextModelRunner` for both". The round-1 verifier noted that `JevAgentSettings` does not check the catalog either.
  Evidence (the missing rule): `_note_path` compares the protected names with case ignored (`workspace.py:307-312`, `folded = relative.as_posix().casefold()`; R-2), so `Seed/x.md`, `.Runs/x.md` and `Entries.jsonl` are refused on every disk. INV-20 lists only `seed/`, `.runs/` and the three bookkeeping files. `p3_seed_guard.py` shows `write_note Seed/brief.md: error`. The §17 heading reads "The S5 repairs added these rules, which the sections above do not state", but this rule is not in the list.
  Failure:
    - A developer who reads §9.3 with §17, or the README, expects a dated snapshot that `BaseAgent` runs, such as `gpt-4.1-2025-04-14`, to work. Construction raises `ConfigurationError` instead.
    - S6 would repeat the parity claim in the PR body.
    - A human reviewer would write: "§17 says this matches BaseAgent. It doesn't. Say it matches the declarative settings and is stricter than BaseAgent."
    - On a case-sensitive disk, a note at `Seed/x.md` is refused, and no spec line says so.
  Smallest fix (documentation only, no code):
    - In spec §17 bullet 2, replace "so §9.3's "same meaning as `BaseAgent`" holds" with "so it matches the declarative `BaseAgentSettings` and is stricter than a plain `BaseAgent`, which accepts any name its runner mapping knows, such as `gpt-4.1-2025-04-14`".
    - At README:69, replace "as for the SDK's other agents" with "as the SDK's declarative agent settings require; a plain `BaseAgent` accepts more names".
    - Add one §17 bullet: "Protected names are matched with case ignored, so `SEED/…`, `.Runs/…` and `Entries.jsonl` are refused on every disk (R-2)."
    - `trivial`. Worth doing before S6 so the PR body does not inherit the parity claim.
  Spec IDs: §9.3, §17 (R-28), INV-20.

R-C2 [Minor] [user's words / refusal wording] vidbyte/agents/infinite/workspace.py:271-272, 180-181 — the R-27 refusal passes the raw `UnicodeEncodeError` text to the model. It names no field, and its "position" counts characters in the file being written, not in the argument the model sent.
  Evidence: `PYTHONPATH=$(pwd) python $W/p1_refusals.py $W/w4`. Every case gives `status=error`, `lone surrogate in result: False` and `changed: []`. These are good. The text is:
      description "desc \ud83d"            → "…can't encode character '\ud83d' in position 44: surrogates not allowed Fix it and call the tool again, or move on."
      append text " more \ud83d" to "ok"    → "… in position 8 …"  (counts the existing note's "ok")
      path "notes/\ud83d.md"                → "… in position 16 …" (counts into the files.jsonl JSON line)
      ref "notes/\ud83d.md"                 → "… in position 6 …"  (does not say it is a ref)
    The raw text also runs into the template with no full stop ("…not allowed Fix it…").
    The file header (`workspace.py:7`) says: "A new guardrail is one more check … with an @intent comment and a ToolExecutionError message that says what to fix."
  Failure: INV-32 still holds in substance. The tool returns `ToolResult.error`, nothing is written, the quota line is present, the tool stays usable, and the bad character is named. But a model that sent a 12-character description is told the character sits at position 44. Once `files.jsonl` holds earlier lines, the reported position is the offset into the whole file, often thousands. So "what to fix" is weaker than the file's own pattern promises.
  Smallest fix: in each of the two encode loops, wrap the encode as below. In `_entry_rules`, `_commit` would then also drop such an entry under INV-16 if it ever got there:

      except UnicodeEncodeError as exc:
          raise ToolExecutionError(f"The text holds {exc.object[exc.start:exc.end]!a}, which cannot be saved as UTF-8, often half of an emoji; remove that character and call again.") from exc

    S008 is a function-complexity rule, so one `try/except` adds little risk. The repair declined this for that reason, so filing it as a `follow-up` is also acceptable.
  Spec IDs: INV-32.

VERIFIED CLAIMS (✔ held · ✘ did not hold)
1. ✔ S5-repair-2: "`c1_ro_seed.py` prints `built | copy writable: True | copy == source: True` for the 1st, 2nd and 3rd constructions". Re-run at 274e54d0 gave exactly that, including the 3rd construction after the edit.
2. ✔ S5-repair-2 / the briefing: "Tools still cannot write under `seed/`, because `_note_path` enforces that, not the mode bits." The `p3_seed_guard.py` probe:
   - built the workspace twice over a read-only seed and left the copy writable;
   - `write_note seed/brief.md`, `write_note Seed/brief.md` and `edit_file seed/brief.md` were each refused;
   - the copy's bytes were unchanged (`b'old brief\r\n'`).
   D-24's "read-only through tools" holds. Bash can write there, which D-10 accepts and which was true before R-7.
3. ✔ The R-26 fix still copies every time, so an edited seed propagates. The copy at `workspace.py:82` is unconditional, and `test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches` edits the source before the 3rd build and passes.
4. ✔ S5-repair-2: "`c2_partial.py` steps 2–4 give `changed files: []`, step 5 leaves `['notes/b.md']` with `created counter: 1`, step 6 is refused". Re-run gave exactly that. The `IndexError` at the end of step 6 is the probe indexing an entry that was never staged.
5. ✔ S5-repair-2: "`r1_guard.py` gives `Verdict: passed` for both pairs and `entries.jsonl texts: ['a first fact', 'a third fact', 'b fact']`". Re-run gave pair a `Verdict: passed`, `Entries saved: #1, #2`, `Entries dropped: -`, with `pair_finished per key: {'root/a': 1, 'root/b': 1}`.
6. ✔ The briefing: "no surrogate reaches the tool result". Nine `p1_refusals.py` cases were run: root text, root ref, generator staging, new-note description, new-note text, new-note path, append text, and `edit_file` new_text, plus a valid create in between. Each refusal printed `lone surrogate in result: False` and `changed: []`. The generator's refusal left `staged: [] | accepted: 0`.
7. ✔ "Can any multi-file write still half-complete for an encoding reason?" No.
   - Both two-file paths are pre-checked: `commit_entry` through `_entry_rules`, `write_note` through `changed.values()`.
   - The remaining multi-file risk is the OS refusing the swap, which is R-29 and not an encoding failure.
8. ✔ "`_commit` and the tools' catch tuples are untouched". `git diff --stat da338f59..149fea25 -- vidbyte/agents/infinite/{launch,memory,journal,settings}.py vidbyte/lib` is empty.
9. ✔ §17 S5 bullets 1, 3, 4 and 5 match the code:
   - one-line, no-colon note path at `workspace.py:296-306`;
   - `INFINITE_MIN_CAP` used at `settings.py:83-86, 201` and defined at `constants/infinite.py:28`;
   - `json.dumps(record)`, ASCII by default, at `journal.py:190`;
   - the UTF-8 rule, with "Nothing was saved" and the quota line, as in claim 6.
   ✘ Bullet 2's parity sentence is false, and the list leaves out the case-insensitive match (R-C1).
10. ✔ The README escape hatch, "set `STRICT_MODEL_VALIDATION = False` to use a model released after this SDK version", is true: with it set, `gpt-7` and `claude-opus-9` build and get a `TextModelRunner`. ✘ Its "as for the SDK's other agents" is false (R-C1).
11. ✔ "No comment line passes 72 columns". `awk 'length($0) > 72' workspace.py | grep -E '^\s*#'` prints nothing.
12. ✔ "No test or lint file changed".
   - `git diff 11b19a7d..274e54d0 --stat -- tests/` and `git diff origin/main...274e54d0 --stat -- lint/` are both empty.
   - No `noqa` or `type: ignore` was added since da338f59 (count 0).
   - S2's 11b19a7d only adds tests, and it rewrites header inventory lines. No assertion was removed.
13. ✔ AC-1 and §5.
   - `test_section_4_snippet_prints_the_root_answer_and_leaves_the_documented_workspace` passes through the pack's fake-runner seam (`1 passed`).
   - The §5 call path is unchanged in this round, because none of the three changed files sits on it.
14. ✔ §8.4 budget and §12.3.
   - `origin/main...274e54d0` adds 18 non-doc, non-test files, 12 of them `.py`. This round added none.
   - Every modified file is a §12.3 row.
   - `workspace.py` is 370 lines including its header.
15. ✔ The briefing: "refused at staging; the verdict stays `passed` with the valid entries committed". This matches INV-15, INV-16 and INV-17. `test_an_entry_text_that_cannot_be_written_never_costs_the_pair_its_verdict_or_other_entries` can fail: it was red at 52eaafe8 with `'unchecked'`.
16. ✔ The user's words (request.md §A and §D). This round makes the run "Unattended, resumable" again for read-only seeds: R-26 lets a new process rebuild the agent so it can resume. It strengthens the "deterministic guardrails" (R-27: a refused write changes nothing). It honors "dont overengineer anthing": +24 lines in one file, with no new knob, constant, prompt leaf, or catch widening. No §C decision was reversed.

COMMANDS RUN (W = …/scratchpad/s5-rereview-2, V = …/scratchpad/s5-rrverifier)
- `git log --oneline -12` shows HEAD 274e54d0, then 149fea25, 5c5b7d33, c90b43be, 582b5793, and on down to da338f59.
- `git diff --stat da338f59..274e54d0` shows 16 files. The source files are `workspace.py` (24 lines) and `README.md` (1 line); the spec has 12 lines.
- `git diff --stat 149fea25..274e54d0` shows only `docs/spec/infinite-memory-agent/pipeline.md | 6 +++---`.
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` prints `…\vidbyte-sdk-infinite-memory-agent\vidbyte\__init__.py`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` gives `111 passed in 2.99s`.
- `… -k "section_4_snippet or read_only_seed or cannot_be_written or seed"` gives `11 passed, 100 deselected`. AC-1 alone gives `1 passed in 0.69s`.
- `PYTHONIOENCODING=utf-8 python lint/run.py` ends with `S064 RATCHETED: 4 known finding(s)…` and `SDK-LINT: PASS`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -x -q` (the full suite) exits 0. The progress lines show no F or E, and `-qq` hides the count line. The orchestrator's gate at 149fea25 recorded `5284 passed, 14 skipped`.
- `python $V/c1_ro_seed.py $W/w1` prints `built | copy writable: True | copy == source: True` three times.
- `python $V/c2_partial.py $W/w2` gives `changed files: []` twice, then `['notes/b.md'] | created counter: 1`, then step 6 `ERROR … Nothing was saved`.
- `python $V/rr/r1_guard.py` (run from `$W/w3`) gives pair a `Verdict: passed`, `Entries saved: #1, #2`, and `entries.jsonl texts: ['a first fact', 'a third fact', 'b fact']`.
- `python $V/obs_b_models.py $W/work_b`: settings refuse `gpt-4.1-2025-04-14`, while `BaseAgent` builds a `TextModelRunner` for it.
- `python $W/p1_refusals.py $W/w4` gives 8 refusals, each with `changed: []` and no lone surrogate, and positions 6, 6, 6, 44, 3, 16, 8 and 3.
- `python $W/p2_escape_hatch.py $W/w5`: strict=True, the settings refuse 3 names `BaseAgent` runs; strict=False, the two match exactly.
- `python $W/p3_seed_guard.py $W/w6`: the copy is writable; all 3 seed writes are refused; the bytes are unchanged.
- `awk 'length($0) > 72' vidbyte/agents/infinite/workspace.py | grep -E '^\s*#'` prints nothing.
- `git diff --stat da338f59..149fea25 -- launch.py memory.py journal.py settings.py vidbyte/lib` prints nothing.
- `git diff --name-status origin/main...274e54d0` (non-doc, non-test) shows 18 added files, 12 of them `.py`. The 15 modified files all appear in §12.3.
- `grep -n "STRICT_MODEL_VALIDATION" README.md` gives line 69. `grep -n "same meaning as" spec.md` gives lines 760 and 1246.
