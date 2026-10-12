# S4 findings verifier — managed-generative-models

**Stage:** S4 verification. **Diff:** `git diff origin/main...a80f0660` (merge-base `00cbd6db`). HEAD is `cad3cf59`, which adds only docs after `a80f0660`. **Output:** `docs/spec/managed-generative-models/review.md`.

**Verdict:** MERGEABLE AFTER FIXES. There are 1 Blocker, 5 Majors (one of them `[verifier]`) and 14 Minors. No finding was refuted. Six fix proposals or claims were refuted, re-rated or superseded.

## Inputs read
- **Reviews.** The three current reports (`reports/S4-review-{conformance,conventions,engineering}.md`), in full. Also their `39a2b101` versions, in full for engineering and conventions, and the headers for conformance, which is identical.
- **Specs and rules.** `spec.md` r5 (all 917 lines), `test-plan.md` and `request.md` §A–§D. From the S3 implementer report, only its deadline lines. `AGENTS.md`, the house style, the report formats, and the field-guide `init.md` and `comment-format.md`.
- **Code.** The diff for every changed production file. `vidbyte_gateway.py`, `text.py` and the changed parts of `model_configs.py`, `registries/models.py` and `streaming_text.py`, read whole. Also the #747 precedent (`git show 57639080:vidbyte/agents/coding.py`) and the shape #690 rejected (`git show 4daed535:vidbyte/agents/coding.py`).

## Merge map
| Original ID (run) | Proposed severity | Merged ID | Final | Disposition |
|---|---|---|---|---|
| conventions R-V1 (current) | Blocker | R-1 | Blocker | CONFIRMED |
| conventions R-V1 (39a2b101) | Blocker | R-1 | Blocker | same finding |
| conventions R-V4 (current) | Minor | R-2 | Major | CONFIRMED and re-rated (merge keeps the highest severity, and the finding is verified) |
| conventions R-V3 (39a2b101) | Major | R-2 | Major | same finding |
| — (verifier) | — | R-3 | Major | `[verifier]`: the R-6 fix trips S020 |
| engineering R-E2 (current only) | Major | R-4 | Major | CONFIRMED |
| conventions R-V2 (current and 39a2b101) | Major | R-5 | Major | CONFIRMED (39a2b101's wide-line sub-point is now under R-1) |
| conformance R-C1 (current = 39a2b101) | Major | R-6 | Major | CONFIRMED |
| engineering R-E1 (current and 39a2b101) | Major | R-6 | Major | same root cause |
| engineering R-E3 (current), re-send-count part (`resends_off_by_one`) | Minor | R-6 | Major | same root cause: the r5 message count is untested |
| engineering R-E3 (current), remainder (`mut_first`, `auto_shape_unchecked`) | Minor | M-9 | Minor | passed through · trivial (rides on R-6) |
| conformance R-C2 | Minor | M-1 | Minor | passed through · trivial |
| conformance R-C3 | Minor | M-2 | Minor | passed through · trivial |
| conformance R-C4 | Minor | M-3 | Minor | passed through · trivial / follow-up |
| conformance R-C5 | Minor | M-4 | Minor | passed through · trivial |
| conventions R-V3 (current) / R-V4 (39a2b101) | Minor | M-5 | Minor | confirmed by my own A002 run · trivial |
| conventions R-V5 (current) / R-V6 (39a2b101) | Minor | M-6 | Minor | follow-up (needs a §8.4 budget change) |
| conventions R-V6 (current) / R-V7 (39a2b101) | Minor | M-7 | Minor | trivial |
| conventions R-V7 (current) / R-V5 (39a2b101) | Minor | M-8 | Minor | follow-up (budget). 39a2b101 also flagged the `api_key` non-string check; D-14 keeps Decision's line, so only the endpoint copy counts. |
| engineering R-E4 (current) | Minor | M-10 | Minor | follow-up (the fix edits an S2 assertion) |
| engineering R-E5 (current) | Minor [scope-adding] | M-11 | Minor | follow-up |
| engineering R-E6 (current) / R-E2 (39a2b101) | Minor [scope-adding] | M-12 | Minor | follow-up (current numbers supersede the "10.5 minutes") |
| engineering R-E7 (current) / R-E3 (39a2b101) | Minor [scope-adding] | M-13 | Minor | follow-up |
| — (verifier) | — | M-14 | Minor | FEATURE.md contract predates r5 (an S2 file) |

Nothing found only in `39a2b101` was dropped. Every finding there maps to a row above.

## Verifications (Blocker and Major), with my own evidence

### R-1 — `@intent` blocks placed away from the code they explain (Blocker, CONFIRMED)
- **The rule.** `field-guide/vidbyte-sdk/comment-format.md` says: "Put each block directly above the code it explains. A method that does several steps gets one short block per step, not one long block at its top. Keep `# @intent <name>` on its own first line."
- **The precedent.** The #747 body (`git log -1 57639080`), comment 1, says: "The `@intent` block that sat at the top of `CodingAgent.__init__` now sits above the permission-policy line it explains." The rejected shape (`4daed535`) was a 110-column `@intent` block at the top of `__init__`, far from `super().__init__(permission_policy=…)`. The accepted shape (`57639080`) puts the block directly above `policy = PermissionPolicy.allow_all() if …`.
- **The code** (read at `a80f0660`):
  - `text.py:33-37` is a summary line, then `# @intent managed-runner-is-pinned-at-construction`, then 3 rationale lines, all above `config = self._coerce_config(...)`. The pinning it explains is `:46-54`. Between them are the validate narration (`:39-40`), `config.validate()` (`:41`) and the pinning narration (`:42-45`).
  - `text.py:62-67` is the pre-existing 93-column summary, the routing intent with 3 lines, and then `# Add this call's tools, messages, and output format.`, all above `call_config = replace(` (`:68`). The routing is at `:77-84`.
  - `vidbyte_gateway.py:148-155` is a 2-line summary, the header/URL intent with 2 lines, and then the 3-line key-mint narration: one 8-line block above `idempotency_key = uuid.uuid4().hex` (`:156`). The header build is at `:159-160`.
  - In `model_configs.py:136-143`, the pre-existing 79-column "Resolve explicit keys before provider-specific environment variables." now heads the block over the managed short-circuit (`:141-142`). The BYOK return it describes is at `:143`. The `@intent` itself is correctly placed here; the displaced narration and its width are the defect.
- **Is the fix safe for A002?** I applied the moves listed in R-1 to scratch copies (`scratchpad/s4ver/rv1/`) and ran `lint.rules.a002_intent_comments.IntentAnalyzer` on the before and after text:
  ```
  text.py: A002 before=[(109, '_coerce_config')] after=[(106, '_coerce_config')]
  vidbyte_gateway.py: A002 before=[(129, '__init__')] after=[]
  model_configs.py: A002 before=[...16 pre-existing Image/Video/Audio/Embedding sites...] after=[same 16, shifted +1]
    text.py:24 def __init__ / text.py:38 # @intent managed-runner-is-pinned-at-construction
    text.py:59 async def arun / text.py:69 # @intent managed-calls-route-through-the-gateway-transport
    vidbyte_gateway.py:129 def __init__ / :130 # @intent one-gateway-transport-per-call-holds-the-bearer
    vidbyte_gateway.py:140 async def request / :155 # @intent managed-request-reaches-only-the-gateway
  ```
  A002's window is `lines[def-4 : def+20]`, which is lines def−3 to def+20 (`a002_intent_comments.py:79-81`). Every moved marker stays inside its window. The simulation includes M-5's new `__init__` block.
- **Wide lines.** The PR added no `#` line over 72 columns. Of the 158 pre-existing wide comment lines in the touched files (model_configs 34, registries 32, text 2, streaming_text 4, jev 86), only `text.py:62` and `model_configs.py:136` head blocks this PR edited. The field guide's literal "Check" (awk prints nothing for touched files) conflicts with AGENTS.md "Do not rewrite untouched code just to make it conform". The repository rule wins, so the fix rewraps only the edited blocks.
- **Severity.** Blocker per the rubric: it contradicts a field-guide lesson and repeats the exact owner-rejected case that #747 fixed.

### R-2 — two-level own-class call chain (Major, CONFIRMED and re-rated from the current Minor)
- **Code.** `validate()` calls `is_vidbyte_managed()` at `:102`, and on the BYOK tail calls `self.resolved_api_key()` at `:106`. That method now calls `self.is_vidbyte_managed()` again at `:141`. At base, `resolved_api_key` called only `normalized_provider`.
- **Probe** (`fixplug_rv4.py` swaps in the fixed `validate`):
  ```
  branch  : one BYOK validate(): {'is_vidbyte_managed': 2, 'find_vidbyte_api_key': 2, 'resolved_api_key': 1} | missing-key message: Missing API key for provider mistral. Pass api_key or set MISTRAL_API_KEY.
  rv4 fix : one BYOK validate(): {'is_vidbyte_managed': 1, 'find_vidbyte_api_key': 1, 'resolved_api_key': 0} | missing-key message: Missing API key for provider mistral. Pass api_key or set MISTRAL_API_KEY.
  ```
- **Full suite with the fix**, `env -u DEEPSEEK_API_KEY -u VIDBYTE_API_KEY … python -m pytest -q -p no:cacheprovider -p fixplug_rv4 -p vnetblock --tb=line`:
  ```
  [fixplug_rv4] applied
  3004 passed, 1 skipped in 21.40s
  []
  ```
- **Adjudication.**
  - The current conventions run rated this Minor, because base already had `validate` → `resolved_api_key` → `normalized_provider`. The 39a2b101 run rated it Major.
  - The merge rule keeps the highest severity, so it enters verification as Major. Verification confirms it: the new hop is in changed code, and AGENTS.md style 1 and spec §12.4 both forbid it.
  - It does not meet the downgrade test: both runs predicted a reviewer comment ("lift the call").
  - I did not raise it to Blocker: the two-level shape through this method predates the PR, and results are unchanged.

### R-3 — `[verifier]` the R-6 test file trips S020 (Major, new)
- **The rule.** `lint/rules/s020_readme_file_index_parity.py` applies to every tracked `README.md` that declares `## File Index` (`check` → `catalog.readmes()`). It reports any tracked direct child with an indexed suffix that the index does not list (`:42-44`). The pack README (`tests/features/sdk_managed_text/README.md:7`) declares one, listing the four test files, the fixtures, FEATURE.md and README.md.
- **Simulation:**
  ```
  pack README now      : []
  with one new test file: [('test_managed_text_deadline.py', 'tracked direct child missing from File Index')]
  existing S020 findings: [('vidbyte/agents/multi/README.md', ('multi_agent.py', 'File Index entry is stale or not a direct tracked child'))]
  ```
- **The gate.** `python lint/run.py --rule S020` prints `S020   readme-file-index-parity                    1      1 RATCHETED`, so one more finding regresses the gate.
- **Why no reviewer saw it.** The orchestrator's constraint ("ADD tests in ONE new file in that folder", "may not edit any S2 file") was set after the reviews. The conformance and engineering fixes did not consider the README index. A001 (643/643) and S062 (889/889) are also exactly at baseline, so the new file needs a full A001 header and no implicit string concatenation. Those two are niche facts, not findings.
- **The fix needs an orchestrator grant.** Either allow one bullet in the pack README's File Index, or accept a red gate. Placing the file elsewhere contradicts the orchestrator's decision that tests live in `tests/features/sdk_managed_text/`.

### R-4 — live billable POST from the repo's own suite (Major, CONFIRMED)
- **Plugin.** I wrote my own: `scratchpad/s4ver/vnetblock.py`. It blocks `httpx.AsyncClient.send`, `httpx.Client.send`, `urllib.request.urlopen`, and `socket.getaddrinfo`, `socket.socket.connect` and `socket.socket.connect_ex` for non-loopback targets. It records the test id, layer and target only. Every run stripped the real `DEEPSEEK_API_KEY` present in this shell (`env -u DEEPSEEK_API_KEY`) and used the fake key `vb_live_` + `z`×32.
- **Branch, single test, fake key:** `1 passed in 1.14s`, with one attempt: `httpx.AsyncClient.send https://vidbyte-backend.onrender.com/api/v1/models/generate`.
- **Branch, single test, no key:** `1 passed in 0.89s`, `[]`.
- **Merge base `00cbd6db`** (`git archive 00cbd6db vidbyte tests pyproject.toml | tar -x -C scratchpad/s4ver/base`; `import vidbyte` resolved to the extract), fake key: `1 passed in 0.83s`, `[]`. So this PR introduced it.
- **Branch, full suite, fake key:**
  ```
  3004 passed, 1 skipped in 47.82s
  1
  httpx.AsyncClient.send https://vidbyte-backend.onrender.com/api/v1/models/generate tests/test_jev_run_state_relation.py::JevRunStateRelationRuntimeTests::test_legacy_mode_keeps_per_run_begin_semantics (call)
  ```
  No other layer recorded anything, so there are no other DNS or socket attempts.
- **Spec check.**
  - §13 says "No test touches the network". NFR-6 says "no network in tests".
  - §13's environment note expected only changed outcomes, not I/O.
  - AC-24 requires agents with only `VIDBYTE_API_KEY` to go managed, so a code-side guard would contradict the spec. The fix belongs in the test.
- **Fix verification** (scratch copies under `scratchpad/s4ver/r_e2/`):
  - Decorator form `@patch.dict(os.environ, {"VIDBYTE_API_KEY": ""})`: `1 passed`, `[]`, but the warnings show `RuntimeWarning: coroutine '…test_legacy_mode_keeps_per_run_begin_semantics' was never awaited` and `DeprecationWarning: It is deprecated to return a value!=None from a test case`. The body never ran, so the pass is vacuous (Python 3.11.0). **Rejected.**
  - Context-manager form (body indented under `with patch.dict(os.environ, {"VIDBYTE_API_KEY": ""}):`, plus `import os`): `1 passed in 0.94s`, `[]`.
  - The same copy with `self.fail("body ran")` after the last assertion gives `AssertionError: body ran` / `1 failed`. The body runs and every original assertion passes.
- **Adjudication of the fix proposals.**
  - Engineering's first option, binding a `ScriptedGenerativeRunner`, changes what the test exercises and is outside the pre-grant ("only to isolate it from `VIDBYTE_API_KEY`").
  - The `clear=True` option clears every variable, which is broader than needed.
  - The context-manager blanking is the smallest fix inside the grant.
- **Side note for the orchestrator.** The 39a2b101 engineering run reported "full suite HELD with a valid-format `VIDBYTE_API_KEY` set" without any network block. That run therefore most likely sent one request with a fake key to the live host. It caused no harm, but it shows how easily R-4 fires.

### R-5 — `@intent` blocks open with a summary line (Major, CONFIRMED)
- **My awk scan** (`/^[ \t]*# @intent/` with the previous line a comment) flags these lines:
  ```
  model_configs.py:74 99 111 121 137 157 [new] … 424 447 461 468 474 492 [pre-existing Decision markers]
  registries/models.py:177 199; vidbyte_gateway.py:64 75 95 150 194; text.py:34 63; streaming_text.py:57
  ```
- **Counts.** `git diff -U0 origin/main...a80f0660 -- vidbyte/ | grep -c '^+.*# @intent'` gives `16`, so every new marker follows a summary.
- **#747 files**, as file, total `@intent`, preceded by a comment: `vidbyte/agents/coding.py 1 0`, `vidbyte/lib/dataclasses/coding.py 2 0`, `vidbyte/tools/builtins/bash.py 4 0`, `vidbyte/tools/toolsets/coding.py 2 0`.
- **Docstring safety.** No lint rule constrains method docstrings: `grep -l docstring lint/rules/*.py` finds only A001 (module headers), C018 and C020 (both skip docstrings), S025 (tool descriptions) and S060. `lint/ruff.toml` selects only `TID251`.
- **Severity.** Major, not Blocker. The reason: spec §11 named the summary-first `DecisionModelConfig` exemplar, and the owner's quoted ruling (#690 r4239871810) concerns width and placement. "On its own first line" is the entry's distillation of #747's practice. A reviewer applying the entry would still flag every block.

### R-6 — the r5 deadline and re-send count are untested (Major, CONFIRMED)
- **Grep:** `grep -n "deadline\|loop.time\|did not re-send\|re-sends in this call" tests/features/sdk_managed_text/*.py` prints nothing. `test-plan.md:3` reads "spec.md r4", and `test-plan.md:20` lists EC-38.
- **Mutation sweep** (the engineering reviewer's `mutplug.py`, which I re-ran; Windows `PYTHONPATH` uses `;` and `C:/` paths):
  ```
  no_deadline              32 passed in 0.48s
  deadline_gt              32 passed in 0.44s
  deadline_after_first     32 passed in 0.38s
  shorten_attempt          32 passed in 0.43s
  resends_off_by_one       32 passed in 0.37s
  auto_shape_unchecked     32 passed in 0.41s
  retry_503                2 failed, 30 passed in 0.64s
  error_truthy             1 failed, 31 passed in 0.53s
  fresh_key_per_attempt    4 failed, 28 passed in 0.56s
  mut_first                32 passed in 0.36s
  ```
- **The proposed fix, built as a scratch test** (`scratchpad/s4ver/test_deadline_probe.py`): a fake loop clock; steps 0, 600 and 629.5; per-attempt timeout and key checks; plus 502 → 422.
  - Baseline: `4 passed`.
  - `no_deadline`: 2 failed (the 600 and 629.5 cases).
  - `deadline_gt`: 1 failed (629.5: `AssertionError: 2 != 1`).
  - `deadline_after_first`: 2 failed (600 and 629.5).
  - `shorten_attempt`: 2 failed (the timeout checks at 0 and 600).
  - `resends_off_by_one`: 1 failed (`'re-sends in this call: 2' not found in "… (re-sends in this call: 1)."`).
  - `mut_first`: 1 failed (`502 != 422`).
- **Adjudication of the two proposed tests:**
  - Conformance's real-clock variant (timeouts 0.4/0.6 s, sleep stubbed): `no_deadline` gives 2 failed; `deadline_gt`, `deadline_after_first`, `shorten_attempt` and `resends_off_by_one` each give `2 passed`. It kills one mutant of five.
  - Engineering's fake-clock steps 629.4/629.6: `deadline_gt` gives `2 passed`, so it survives; `deadline_after_first` gives 1 failed; `no_deadline` gives 2 failed.
  - Exactly 629.5 is needed for `>=` against `>`: 629.5 + 0.5 == 630.0 exactly in binary floating point. Step 600 is the one case where `deadline_after_first` gives a third POST.
  - R-6 merges both proposals with these corrected values.
- **Seam note.** Patch the module attribute (`patch.object(vidbyte.lib.http.vidbyte_gateway, "asyncio", SimpleNamespace(...))`), not `asyncio.get_running_loop` globally, because the test itself calls the real `asyncio.run`.

## Minor pass-through notes
- The Minors are de-duplicated and tagged in `review.md` but not re-verified, except two:
  - M-5: confirmed by `python lint/run.py --rule A002 --all --format json`, which lists `vidbyte/lib/http/vidbyte_gateway.py 129 __init__`. The base/head analyzer diff shows it is the only new name in the touched files (`streaming_text.py base 4 head 4`, `text.py 3→1`, `registries/models.py 17→16`, `model_configs.py 19→16`).
  - M-9's `mut_first` part: confirmed with the probe.
- **M-4.** No test pins "never billed twice". The phrase appears only in `README.md:286` and spec AC-18.
- **M-10.** `test_managed_text_failures.py:180` is `self.assertNotIn("TypeError", message)`, an S2 file, hence follow-up.

## Blind-spot checks run (step 6)
- **A convention fix breaking a conformance gate.** R-1's moves were simulated against A002 (above): no regression. R-5's docstring swap was checked against every rule that mentions docstrings: none constrains them.
- **A conformance/engineering fix breaking a convention gate.** R-6's new file against S020: a regression, now R-3. Against A001 and S062: both at baseline, recorded as niche facts.
- **An R-4 fix that cannot fail.** The decorator form is vacuous on Python 3.11.0, as shown above. The fix names the context-manager form.
- **Docs that will contradict the new test.** FEATURE.md's contract predates r5 (M-14). `test-plan.md:3`/`:20` are part of R-6's doc step.

## Commands run (final lines quoted)
- `git log --oneline -5` shows HEAD at `cad3cf59`. `git diff --stat a80f0660 HEAD` touches only 4 docs files. The merge-base is `00cbd6dbd12e3a8d7c92ec7ffbe2ed04e8273ec5`. `origin/main` has moved to `5058737a`, but the merge-base and the diff are unchanged.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` gives `32 passed in 1.31s`. `import vidbyte` resolved to this worktree.
- The mutation sweep, probes, `vnetblock` runs and `fixplug_rv4` full suite are quoted in the sections above.
- `python lint/run.py --rule A001` gives `A001 agent-readable-file-headers 643 643 RATCHETED`. `--rule S062` gives `889 889 RATCHETED`. `--rule S020` gives `1 1 RATCHETED`. `--rule S064` gives `4 4 RATCHETED`. `--rule A002` gives `A002 intent-comments 653 703 IMPROVED` / `SDK-LINT: PASS`.
- I did not run the full `python lint/run.py` or `scripts/run_ci.py`, which the briefing forbids. The orchestrator and the conformance reviewer quote `SDK-LINT: PASS`.

## Files
- **Written in the worktree:** `docs/spec/managed-generative-models/review.md` and this report. No source edits, no commits, no stash, checkout, reset or merge. `git status --short` showed nothing before these two files.
- **Scratch** (outside the worktree): `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/89243902-3a54-44fb-81e0-5240b0f89dfc/scratchpad/s4ver/`:
  - `vnetblock.py`, `fixplug_rv4.py`, `test_deadline_probe.py`, `test_reviewer_steps.py`, `test_realclock_probe.py`;
  - `rv1/` (simulated comment moves), `r_e2/` (test-fix copies), `base/` (merge-base extract) and the JSON attempt logs.
- **Re-used** (re-run, not modified): `…/scratchpad/s4eng/mutplug.py` and `mut_first.py`.
- **Network:** no live call left the machine. Every pytest run that could reach the gateway had `vnetblock` loaded and a fake key. No real key was printed or used.
