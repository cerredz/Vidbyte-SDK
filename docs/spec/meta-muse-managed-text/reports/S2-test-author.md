# S2 test author report: meta-muse-managed-text

- **Stage:** S2 test author, against spec r3.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`, branch `feat/meta-muse-managed-text`.
- **Commits:**
  - `856e3c0a test(gateway): add failing tests for meta-muse-managed-text [AC-1..AC-14]`: the 16 pack files and `test-plan.md`.
  - `882556ea docs(spec): record test proof for meta-muse-managed-text`: only the §6.2 Proof cells of `spec.md` (15 lines; a script checked that no other byte changed).
  - This report is committed separately, on top of `882556ea`.
- **Not touched:** `vidbyte/`, `README.md`, `lint/`, `scripts/`, the main checkouts, `pipeline.md`. No install (bootstrap is `PYTHONPATH`), no `git stash`, no push. Scratch plugins and scripts stay in the session scratchpad and are not committed.

## Bootstrap ("install")

```
$ PYTHONPATH=$(pwd) py -3.11 -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-meta-muse-managed-text\vidbyte\__init__.py
```

## Inventory

**Read:** spec r3 in full (§4 snippet, §6, §7, §12, §13), `request.md`, `context/code-map.md`, `context/wire-contract.md` (§9.2 error rows and the missing-key copy), `pipeline.md` (the grant); every module of both packs, both fixture modules, both `FEATURE.md`/`README.md` files; the production readers of the set (`model_configs.py:193-209`, `provider_keys.py:303-309`), `text.py:57-62`, `vidbyte_gateway.py` wording, `streaming_text.py`, the grader's metadata shape; `lint/pricebook_vintage_lock.json:51` (C010 lock entry for `META/muse-spark-1.1`).

**Probed before writing** (scratch `s2_probe.py`, base vs. the set widened in memory): M-12 text; meta + endpoint (M-13 first, both ways); streaming refusal text and `details`; agent fallback (base: `AgentExecutionError`, inner `UnsupportedProviderError`, 0 requests); M-18 on both roots; the `DIRECT` golden (identical base and widened); the grader (base: candidates `{anthropic}`, 1 run; widened: `{anthropic, meta}`, 2 runs, the meta request relays `META_API_KEY`).

**Written:** 15 new test methods (1 in `sdk_managed_text`, 14 in `sdk_provider_keys`) and 10 existing tests extended through the per-provider tables. Full map in `test-plan.md`.

| Module | New tests | Extended existing tests |
|---|---|---|
| `mt/test_managed_text_acceptance.py` | AC-13 README bullets | per-provider end to end (meta subtest) |
| `mt/test_managed_text_wire_contract.py` | — | cap per dialect, emitted keys (meta subtests) |
| `mt/test_managed_text_selection.py` | — | unserved providers refused (meta moved out; M-12 must list meta) |
| `mt/test_managed_text_deadline.py` | — | M-12 lists every served provider |
| `pk/test_provider_keys_acceptance.py` | AC-1 snippet; AC-4; AC-6 + AC-12 golden | — |
| `pk/test_provider_keys_wire_contract.py` | relay sources (AC-2, INV-4, T-1); paid headers (AC-3) | own-key relay, envelope = DIRECT + cap, relay cap (meta subtests) |
| `pk/test_provider_keys_modes.py` | INV-1 build, INV-12 endpoint, INV-14 streaming | `GatewayShapeTests` (meta row out, `SERVED` + meta) |
| `pk/test_provider_keys_matching.py` | EC-6 M-18 for a meta primary | — |
| `pk/test_provider_keys_failures.py` | AC-7 422, AC-8 502, AC-9/EC-13 401 and 429 | every failure test's leak list (+`K_META`) |
| `pk/test_provider_keys_security.py` | AC-14 leak scenarios | — |
| `pk/test_provider_keys_agents.py` | AC-11 fallback, EC-11 fork, EC-16 grader | — |

## Pruned

- **"Building a meta config reads no `*_API_KEY`"** (planned inside the INV-1 test): pruned. It mirrors the unserved-refusal check, but for a served provider it is not a spec claim, and it would bind an unspecified implementation detail.
- **A `muse-spark-1.1` price pin (INV-15):** it would pass at HEAD (rule 6). INV-15 is guarded by lint C010's lock entry and the NFR-2 diff check.
- **A Meta-specific branch in `relayed_provider_error`:** not needed. Meta's relayed body is OpenAI-style (§13), which the default branch already emits. Only a comment was added.
- **The EC-2 "(re-sends in this call: 2)" text, the NaN floor, concurrency, and `extra_body` passthrough for meta:** provider-generic and already pinned for other providers; listed under "Tests deliberately NOT written".
- **Separate EC-13 and AC-9 tests:** merged into one test with a 401 and a 429 subtest.
- **The other EC-16 compositions and EC-11's handoff:** the same `TextModelRunner` mechanism. The grader and the fork stand for it.

## Red output (exact)

At HEAD `82a3bd8e` (code = `base_commit`), before the commits:

```
$ env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) py -3.11 -m pytest tests/features/sdk_managed_text tests/features/sdk_provider_keys -q -p no:cacheprovider --tb=no
FAILED tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py::MetaRelayTests::test_a_meta_call_without_a_meta_key_sends_exactly_the_three_vidbyte_paid_headers
FAILED tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py::RelayCapAndFloorTests::test_a_relay_body_carries_the_default_cap_or_the_callers_exact_value
24 failed, 159 passed in 2.13s
```

**Reason audit.** Each failing test was re-run under `unittest`, which reports every failing subtest. Of 53 subtest-level failures:

| Count | Failure |
|---|---|
| 33 | `UnsupportedProviderError` M-12 at construction |
| 6 | `'meta' not found` in the M-12 message |
| 5 | `UnsupportedProviderError ... is not an instance of ProviderRequestError` |
| 4 | `AgentExecutionError` with `details["error_type"] == "UnsupportedProviderError"` and 0 requests |
| 2 | sets missing `meta` (consequences of M-12) |
| 1 | M-18 without "Vidbyte's own meta account" |
| 2 | README facts missing |

There were no `KeyError`, import, collection, or typo failures, and no non-meta subtest failed.

**Green proof (scratch plugins only).**

| Run | Result |
|---|---|
| `-p s1_widen` (set widened in `jev`, `model_configs`, `provider_keys`) | `1 failed, 182 passed in 1.44s` (only the README test) |
| `-p s1_widen -p s1_readme` (README copy with §12.3 row 2 (a)-(c)) | `183 passed in 1.41s` |

Baselines before any edit: `168 passed in 2.04s` unwidened, and `2 failed, 166 passed in 1.86s` widened (the two by-design failures §13 names).

**Mutation check (scratch `s2_mutants.py`).** All 4 mutants were killed:

| Mutant | Result |
|---|---|
| README with the Providers bullet only | 1 failed |
| README with Providers and cap, no `LLM\|` | 1 failed |
| Set widened only for `TextModelConfig` | M-18 test failed |
| Gateway default cap 16,384 | 15 failed |

## Fixtures added or extended

All are within the grant; every before and after is recorded in `test-plan.md`.

| File | Changes |
|---|---|
| `managed_text_fixtures.py` | `MANAGED_MODELS` + META (`muse-spark-1.1`); `UNMANAGED_TEXT_PROVIDERS` − META; `_CHAT_PROVIDERS` + META (so `provider_answer(META)` carries chat usage, matching `MetaProvider`); "six" → "seven" comment; Meta note on `relayed_provider_error` |
| `provider_keys_fixtures.py` | new `K_META_2` (concatenated; exported); `chat_done` comment |
| Per-module tables | `ORACLE_KEYS` ×2, `CAP_FIELD` ×2, `EMITTED_KEYS`, `FULL_CONFIG`, `MANAGED_PROVIDERS`, `RELAY_KEYS`, `SERVED`, `PROVIDER_KEYS` + meta; `GatewayShapeTests` meta row removed; the false comment at `test_provider_keys_modes.py:379` corrected |
| `GatewayCall` (failures module) | gains optional `model=` and `mode=`; existing callers are unchanged |
| Pack docs | both packs' `FEATURE.md` and `README.md` ("six" prose, meta failure modes, suite map, log lines) |

## Spec defects and observations

**No blocking defect.** Every name the spec commits to exists and was bound as written.

1. **INV-15 has no pytest pin for `muse-spark-1.1` (observation, not a defect).** `test_catalog_pricing_contract.py:64-99` pins the 1.2, 1.3, and contributor rows only. The 1.1 row is guarded by lint C010 (`pricebook_vintage_lock.json:51`) and NFR-2's diff check, so S4 should verify NFR-2 by diff and the full gate.
2. **AC-1's wording (clarity).** "answers each gateway POST with a Meta chat completion" needs, for the agent's POST, a chat completion that ends the loop. The test uses an `isDone` tool-call completion (`chat_done`). The `VIDBYTE_MANAGED` call gets a plain chat completion.
3. **§13 "Usage shape" (resolved by the grant).** Adding META to `_CHAT_PROVIDERS` makes the per-provider acceptance test compare chat usage.

## Environment notes

- The session scratchpad is shared with other running agents. Writing `fill_proof.py` at the scratchpad root overwrote an existing file of that name: the Write tool reported "updated", and its origin is unknown. My later scratch files went under `scratchpad/meta-s2/`. If another agent relied on the root `fill_proof.py`, it now holds this run's Proof-filling script.
- `DEEPSEEK_API_KEY` is set in this shell. Every pytest command here ran under `env -u DEEPSEEK_API_KEY`.
- The full suite was not run (memory is tight, and no module outside the two packs imports their fixtures; checked by grep). The area command covers every changed file.

## r4 delta

- **Stage:** S2 test author (r4 delta), against spec r4. The production code under test is HEAD `121911df`, which holds the r3 implementation and no r4 change.
- **Commits (not pushed):**
  - `23c4e9c4 test(provider-keys): add failing tests for meta-muse-managed-text r4 [AC-1, AC-16..AC-18]`
  - `4af4d8e0 test(sdk-packs): wrap S2 comments at 72 columns and tidy pack headers [R-2, R-6, R-7]`
  - `docs(spec): record r4 test proof for meta-muse-managed-text`: `test-plan.md` `## r4 delta`, the four §6.2 Proof cells (AC-1, AC-16, AC-17, AC-18; a script checked that only those 4 lines changed), and this section.
- **Not touched:** `vidbyte/` (including `provider_keys.py`), `vidbyte/lib/registries/README.md`, the root `README.md`, `lint/`, `scripts/`, `pipeline.md`, and the main checkouts. No install, no `git stash`, no push, and no `scripts/run_ci.py`.

### What was built

- **Fixture:** `K_META_DOC = "LLM" + "_" + "1" * 16 + "_" + "m" * 32` (`provider_keys_fixtures.py`, in `__all__`). `LLM_` was added to the reserved-prefix list in the header.
- **Tests:** 9 new test methods and 7 extended existing tests, about 290 new subtests. No new file. The coverage map, the failure inventory (F1 to F19) and the before/after of every edit are in `test-plan.md` `## r4 delta`.
- **AC-17 (i) closes S4 R-3.** The agent test kills `meta_key_to_keyless` in both shapes (4 of 4 subtests). It does so at HEAD's rows too, where only the `LLM_` subtests are red without the mutant.

### Results

- **Red (HEAD):** area `15 failed, 177 passed`. There are 139 failing subtests, all on the `LLM_` shape, the §8.5 row or the r4 source text, and no `LLM|` subtest fails. The 177 are every r3 test that was not extended.
- **Green-ability:** `192 passed`. The scratch plugin `s2b_r4.py` sets the exact §8.5 row and serves the row 4(b) and row 5 text from scratch copies.
- **Mutants:** 13 of 13 killed. They are m1 to m9 on the row, `meta_key_to_keyless`, and three source-text mutants. Each row mutant is also killed by a behavior test, not only by the §8.5 pin.
- **R-2:** the recount prints nothing (0 lines). R-6 and R-7 are done. `ruff` E301/E302/E303/E305 and F/E9 report `All checks passed!`, and `python lint/run.py` reports `SDK-LINT: PASS`.

### Spec defects and observations (r4)

**No blocking defect.** Every name in §4, §8.5 and §12.3 that the r4 delta binds exists and is bound as written: `ProviderKeyMatcher.KEY_FORMATS`, `provider_of`, `accepts_unproven`, `match`, `FORMAT_BOUND_PROVIDERS`, `RESERVED_PREFIXES`, `OPENAI_KEY_PREFIX`, `OPENAI_JWT_PREFIX`, the §8.5 row, the M-6, M-7 and M-18 details keys, and the registries README `| meta |` row.

1. **Open item: AC-13's r4 text is unbound.** AC-13 and FR-7 now require the root README Prefixes bullet to read "`LLM_` or `LLM|` (Meta)". The existing AC-13 test checks only `` `LLM|` (Meta) ``, which that text still contains. The grant says "AC-13 stays as is" and grants new tests only for AC-16 to AC-18, INV-16, INV-17 and EC-17 to EC-19. So no test fails if the implementer leaves `LLM_` out of the root README. The S5 review must check it, or a later grant can add one `assertIn`.
2. **AC-18's "says that today's page no longer shows that form" is a paraphrase** (row 5(b) gives no fixed wording), so it is left to the S5 review. Every fixed string is bound: both pattern spans in order, the URL, the date, the quoted sentence, the error page, and #1027's kept 2026-10-15 text.
3. **Observation.** The comment above the Meta row at HEAD already breaks the 72-column rule (its first line is 74 columns), so the AC-18 comment test is red for that reason as well as for the missing `LLM_` and date. Row 4(b)'s example block passes at 72 columns or fewer.
4. **Observation (fail-closed path).** Keys with non-ASCII digits or letters never reach `provider_of` through a root. The printable-ASCII check (M-6b) refuses them first. The `\d`/`\w` guard therefore lives in the `provider_of` table, which is the only seam where those mutants are visible.

### Environment notes (r4)

- In Git Bash, `PYTHONPATH="$(pwd);<dir>"` turns the first entry into `C:\c\Users\...`, an invalid path. `vidbyte` still resolved to the worktree through `sys.path[0]`, because `-m` adds the cwd (checked with `vidbyte.__file__`). The final green and mutant runs used the explicit Windows path instead.
- A `sed -i` rewrite turned one CRLF file into LF. It was converted back before commit. All later scripted edits keep line endings.
- Scratch files are prefixed `s2b_` in `<scratchpad>/plugins/` so they cannot collide with other agents' plugins. Only `s4e_mutants.py`, from another stage, was loaded, and it was not edited.
