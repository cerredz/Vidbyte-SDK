# S2 test author: harness-thread-helpers-skills

STATUS: DONE · Spec r3 (approved) · Branch `feat/harness-thread-helpers-skills` · HEAD `a2053e68`

## Commits
| SHA | Message | Paths |
|---|---|---|
| `b502b6f2` | `test(harnesses): add failing tests for harness-thread-helpers-skills [AC-1..AC-34]` | `tests/features/harness_threads/` (21 files) + `docs/spec/harness-thread-helpers-skills/test-plan.md` |
| `a2053e68` | `docs(spec): record test proof for harness-thread-helpers-skills` | `docs/spec/harness-thread-helpers-skills/spec.md` (only the §6.2 Proof column, 34 cells) |

`pipeline.md` shows as modified in the worktree (2 insertions). I did not make that change and did not stage it. No file under `vidbyte/` was touched.

## Produced
- **12 new test files, 563 tests** in `tests/features/harness_threads/`:
  - `test_harness_threads_helper_surface.py` (37), `test_harness_threads_grok_helpers.py` (28), `test_harness_threads_opencode_helpers.py` (19), `test_harness_threads_muse_helpers.py` (23)
  - `test_harness_threads_grok_commands.py` (58), `test_harness_threads_opencode_commands.py` (10), `test_harness_threads_muse_commands.py` (18)
  - `test_harness_threads_helper_arguments.py` (274), `test_harness_threads_helper_credentials.py` (11), `test_harness_threads_helper_bounds.py` (33)
  - `test_harness_threads_acceptance_helpers.py` (4), `test_harness_threads_listing_properties.py` (48)
- **Stand-in vendor.** `fake_harness.py` was extended (722 lines, under the 1,000 cap). The new sibling `fake_harness_helpers.py` (591 lines) holds the helper paths: the Grok export and delete, the opencode list, db, export and delete with a real SQLite `session` table, and Muse serve, export and init. It imports only the standard library and never calls a network, a real CLI or the real `wsl.exe`.
- **conftest.py** (584 lines): `helper`, `skill`, `stores` (Grok real layout, opencode SQLite, Muse MSP sessions with exact export bytes) and `shapes`; `raw_config` hands over `None` or another record unchanged.
- **§12.3 rows 35–38 only:**
  - `test_harness_threads_surface.py`: 68 exports, enum members, 32 codes, constants.
  - `test_harness_threads_errors.py`: the stale line-193 pin becomes the 4 new code texts.
  - `test_harness_threads_static_policy.py`: the 10 new modules.
  - `FEATURE.md` and `README.md`: File Index, test map, Logs.
  - No other existing assertion was weakened, skipped or deleted.
- **`test-plan.md`** in the report-formats layout. The coverage map uses 98 test names; every one was checked against `pytest --collect-only`.
- **Spec §6.2 Proof column.** AC-1..AC-34 each name `file::test`. AC-21 cites the 431 unedited #1036 tests, AC-22 is the gate (S3/S4) and AC-26 is "review (S4)". A script checked that each named test exists and that only the last cell of each row changed.

## Red run
Bootstrap: pre-created venv, no install (`.venvs/harness-thread-helpers-skills`; pytest 8.3.5, pytest-asyncio 1.3.0, Python 3.11.0, win32).

`$PY -m pytest tests/features/harness_threads -q -p no:cacheprovider -rf` on the committed tree:
```
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_vocabularies_are_str_enums_carrying_the_vendor_values
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_contract_constants_hold_the_spec_values
568 failed, 430 passed, 3 skipped in 54.97s
```
- **Baseline before S2:** `1 failed, 435 passed, 2 skipped`. The one failure was the stale `errors.py` pin at line 193.
- **The 431 unedited #1036 tests:** 0 failed, 429 passed, 2 skipped (same skips as the baseline). They ran against the extended conftest and stand-in.
- **The 7 edited pins from §12.3 rows 35–38:** all 7 fail.
- **The 563 new tests:** 561 fail, 1 passes and 1 is skipped:
  - the pass is `test_root_export_lists_are_untouched`, the INV-1 guard. It is green by design and fails only if root `__all__` grows;
  - the skip is `test_muse_helpers_outside_windows_look_muse_up_on_path`, which is POSIX-only.
- **Every failure is a missing spec name.** The 568 break down as:
  - 547 `AttributeError` for a §8.5 function or record, or a §9.3 constant, that is missing from `vidbyte.harnesses.native` or `vidbyte.lib.constants.native_threads`;
  - 12 `RecordFieldConverter.to_utc_datetime` missing;
  - 3 `ValueError: 'grok.command_not_run' is not a valid FailureCode`;
  - 2 static-policy "§12.3 names these modules ... missing";
  - 3 surface list or enum mismatches;
  - 1 AC-1 subprocess whose stderr shows `ImportError: cannot import name 'get_grok_thread_lineage'`.

  No failure comes from a fixture, the stand-in, a timeout or collection.
- **Stand-in checked independently.** The scratch smoke driver runs the stand-ins with the exact argv, env and frames the tests send and checks their answers. It ends with `FAILS: []` (47/47 ok).

## Lint
After staging, `python lint/run.py` ended:
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
Two issues came up on the way and both are fixed:
- **S020** reported 14 findings while the new files were untracked. Staging them brought it back to its 1 known finding.
- **S062** caught one adjacent-literal SQL string in `fake_harness_helpers.py`. It is now a single literal.

A001, A002, S025, S061 and S063 report IMPROVED. I did not lower their baselines.

## Spec gaps found (tests chose the least-committal reading)
1. `MUSE_GOAL_PROMPT_TEMPLATE` has no value in the spec. The tests read the constant and require only that it contains `{prompt}`.
2. EC-74 and §12.4 disagree on which config location `features.video_gen` belongs in. The test accepts either.
3. The order of the parts in EC-67's detail is unspecified. The test checks content, not order.
4. The `limit` the SDK sends in Muse `session/list` is unspecified. The tests accept anything from the caller's limit up to 200 and keep ties away from the cut.
5. A Muse or opencode protocol-mismatch detail may name the vendor member (`updatedAt`) or the record field (`updated_at`). The tests accept either.

## Tests deliberately not written
- **EC-12 and EC-62:** races that could only be made deterministic by mocking the SDK's own filesystem calls.
- **EC-24:** the behaviour belongs to the vendor.
- **EC-64:** a scale requirement, not a correctness one.
- **EC-43, EC-47, EC-63 and EC-72:** vendor-side effects.
- **AC-22:** this is the gate itself.
- **AC-26:** proven by review.
- **Live probes:** these need a real CLI or key.
- **Hypothesis:** it is not installed, so seeded `random.Random` stores take its place.

## Notes for the implementer (full list in test-plan.md)
- **Grok argv:** exact order `--output-format=streaming-json`, `--session-id=<uuid4>`, `--cwd`, `--permission-mode`, `[--model] [--reasoning-effort] [--agent]`, `--single=<line>`.
- **Grok env:** `GROK_WORKFLOWS=0` is set only for goal.
- **opencode `run`:** the command goes in `--command=<c>` and the arguments go on stdin. An empty stdin means no arguments.
- **Control timeout:** read `NATIVE_CONTROL_TIMEOUT_SECONDS` from the constants module at call time. Tests monkeypatch it and pass `timeout_seconds=600` to prove it is ignored.
- **Helper children (INV-2):** they must also drop an inherited `OPENCODE_CONFIG_CONTENT`.
- **Muse helpers:** each call gets a fresh private `XDG_CONFIG_HOME`.
- **Muse lineage:** `forkedFrom` is an object.
- **Order:** Muse returns ties id-ascending, and the SDK must reorder them.
- **Pre-existing, outside this area:** the MCP stdio flake noted on pristine main. It did not come up, because only `tests/features/harness_threads` was run.

## Open items
- **For S1 (or for S3 to settle as an implementation choice):** gaps 1 and 2 above.
- **For S3:** `pipeline.md` has an uncommitted 2-line change made by someone else. It is left as found.
