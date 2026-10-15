# S5 repair, iteration 3 of 8: InfiniteMemory agent

Branch `feat/infinite-memory-agent`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1084 (draft). Start HEAD dee01423. Fix commit 6932c936.

This iteration is a docs-only cleanup. Re-review round 2 (reports/S5-rereview-2.md) returned SOUND with two Minors. R-30 (`trivial`) is fixed. R-31 (`follow-up`) is recorded and left open by instruction. No code, test, or lint file changed.

## Gate matrix (at 6932c936)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `.......................................  [100%]` / `111 passed in 3.03s` |
| Lint | `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | `Found 223 errors.` / `[*] 223 fixable with the --fix option.` (223 = origin/main) |
| Semgrep | `python scratchpad/s5-1/semgrep_launch.py scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 946 files: 0 findings.` / exit 0 |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `tests\test_workflow_agent_forks.py ......  [100%]` / `5284 passed, 14 skipped in 49.13s` / `CI passed.` / exit 0 |
| Full local gate, package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit 0 |
| Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084` | none (workflows are disabled repo-wide, so nothing was dispatched) | `no checks reported on the 'feat/infinite-memory-agent' branch` (PR head 6932c936) |

Lint rule counts that matter here are unchanged from iteration 2: A009 0 (CLEAN), C012 23, S008 19, S061 5 and S062 889. The README is 9.4k characters, far under A009's 40,000. `git diff 11b19a7d..HEAD -- tests/` and `git diff origin/main...HEAD -- lint/` are both empty.

## Per finding

### R-30 (Minor, `trivial`): fixed @6932c936

**Reproduced.** `PYTHONPATH=$(pwd) python $W/p2_escape_hatch.py $W/w5` gave these results, with `$W` = `…/scratchpad/s5-rereview-2`:
- With strict mode on, the settings refuse `openai/gpt-4.1-2025-04-14`, `openai/gpt-7` and `anthropic/claude-opus-9`, and a plain `BaseAgent` gets a `TextModelRunner` for each.
- With strict mode off, every row matches `BaseAgent`. That includes the shared `No runner mapping` refusal of `o9-mini` and `my-finetune-xyz`.

**Code checked before writing.**
- `InfiniteMemoryAgentSettings._validate_model` (`settings.py:206-213`) calls `ProviderModelRegistry.validate_provider_model_pair`.
- That function (`vidbyte/lib/registries/models.py:357-375`) first calls `validate_model`, which refuses an empty name and then, when strict, a name missing from the catalog. When strict, it next applies the OpenRouter-slug check and the owner check. When not strict, only the empty-name check runs.
- A direct call shows the refusal text for the three names: `Unrecognized model '<name>'. The SDK has no registered runner for it.`
- `BaseAgentSettings._validated_model` (`vidbyte/lib/dataclasses/config.py:505-517`) makes the same registry call. So "like `BaseAgentSettings`, unlike a plain `BaseAgent`" is exact.

**Changes.**
1. Spec §17 "Implementation deviations (S5)", the model bullet. It now says:
   - the settings check the provider/model pair with `validate_provider_model_pair`, because C012 requires a catalog check;
   - the declarative `BaseAgentSettings` applies the same check, but a plain `BaseAgent` runs any name its runner mapping knows, so the three names above run there and are refused here;
   - §9.3's "same meaning as `BaseAgent`" therefore covers what the fields mean, not which names are accepted;
   - an unlisted name is refused unless `STRICT_MODEL_VALIDATION = False`, which skips the catalog and provider checks, after which the agent accepts and refuses the same names a plain `BaseAgent` does.
   - The bullet ends with "(Corrected per R-30: …)", matching the S3 list's "(Corrected in S5 per R-5 and R-28: …)" style.
2. Spec §17, a new bullet placed directly after the note-path bullet, since both extend INV-20. It says `_note_path` casefolds the path before comparing it with `seed/`, `.runs/` and the three bookkeeping files, so `SEED/brief.md`, `.Runs/x.md` and `Entries.jsonl` are refused on every disk (R-2). I checked this on a real workspace:
   - `SEED/brief.md`, `Seed/new.md`, `.Runs/x.md`, `Entries.jsonl` and `FILES.jsonl` are each refused;
   - `notes/ok.md` is allowed.
3. `vidbyte/agents/infinite/README.md:69` now says the name must be in the catalog "as the SDK's declarative `BaseAgentSettings` require". It adds that a plain `BaseAgent` accepts more names, such as `gpt-4.1-2025-04-14`, which these settings refuse. It ends: set `STRICT_MODEL_VALIDATION = False` to accept the names a plain `BaseAgent` accepts, such as a model released after this SDK version.
4. `review.md` gains the section "Re-review round 2 (final) — Minors" with rows R-30 and R-31. R-30 is set to `fixed @6932c936` in the verify-log commit, because a commit cannot name its own SHA (iteration 2 did the same).

**Not edited:** §9.3's table row (`spec.md:760`, "same meaning as `BaseAgent`"), which is outside the grant. The §17 bullet qualifies it, and §17 already serves as the record of deviations. A grep for the parity wording over `vidbyte/agents/infinite/`, the spec and `REPO_MAP.md` found it at README:69 and spec:1246 only, plus §9.3.

### R-31 (Minor, `follow-up`): open by instruction

It is recorded in `review.md` with its repro (`PYTHONPATH=$(pwd) python $W/p1_refusals.py $W/w4`) and the round-2 smallest fix. No code was changed.

## Test changes proposed

None.

## Findings I believe are wrong

None. Re-review round 2's R-C1 evidence reproduced exactly.

## Still open, and what I would try next

- **R-31.** In each of the two encode loops (`workspace.py:180-181` in `write_note` and `:271-272` in `_entry_rules`), catch `UnicodeEncodeError`. Re-raise it as a `ToolExecutionError` that quotes `exc.object[exc.start:exc.end]` with `!a` and says to remove that character.
  - Re-run `python lint/run.py` and watch S008 for both functions. Iteration 1 pushed `__post_init__` over C901 with one added try/except.
  - If S008 moves, put the encode check in one small helper that the two sites call. Both callers sit one level below their main functions, so watch the call-chain rule (AGENTS.md principle 1).
  - Re-run `p1_refusals.py`. It must still show `changed: []` and no surrogate in the result.
- **The earlier follow-ups** are unchanged: R-14, R-19, R-20, R-22, R-24, R-25 and R-29.
- **For S6:** the PR body must not repeat the old parity claim. Use the §17 wording: the settings check the model like `BaseAgentSettings` and are stricter than a plain `BaseAgent`.
