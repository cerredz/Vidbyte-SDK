# S5 repair, iteration 2 of 8: agent-output-connectors

**Branch:** feat/agent-output-connectors
**PR:** https://github.com/cerredz/Vidbyte-SDK/pull/882
**Start HEAD:** d87fcbaf. The remote branch was still at ae6115f4, so 5b484d8f, 4b063c28 and d87fcbaf were unpushed until this iteration's push.
**Code HEAD:** 2334385b

## Outcome

- Caught up with origin/main (8 commits) with a clean merge, d4100704.
- Fixed S6-1 and S6-2, one commit each: 5b437f24 and 2334385b.
- No test, baseline, suppression, CI config, or `vidbyte/agents/base.py` was edited.
- Gate results are in the matrix below.

## Step 0: catch up with main

- Ran `git fetch origin`, then `git merge origin/main`. The merge brought in #890, #885, #889, #767, #888, #887, #746, and #763, with no conflicts.
- The merge commit is d4100704 `chore(merge): catch up with origin/main [gate:mergeability]`. Its parents are d87fcbaf and ab7182d3.
- Two files overlap with this PR, and both keep both sides:
  - `vidbyte/lib/enums/__init__.py` keeps `CodingContextSection`, `TextModelMode`, `DeliveryStatus`, and `OutputDestination`, plus main's new `context.py` enums.
  - `vidbyte/agents/README.md` keeps main's CodingContext text and this PR's `## Output Connectors` section and `output/` line.
- The contract did not conflict. `--check` reports it current at 623 exports, so it was not regenerated.
- The feature pack after the merge gave `1 failed, 340 passed`. The one failure is `[email-empty-to]`, the S6-1 red test.
- **#889 and #887, runtime stop handling.** Main's diff to `runtime.py` changes which messages the end-of-run hooks see after a review STOP, and it does not add or change any `stop_reason`.
  - A review-refused finish still ends through `_unverified_finish_result`, whose stop reason is `AgentStopReason.CONTRACT_UNSATISFIED` (`runtime.py:873-877`).
  - `git diff d87fcbaf d4100704 -- vidbyte/lib/dataclasses/agents.py` is empty, so `AgentStopReason` is unchanged.
  - `OUTPUT_DELIVERABLE_STOP_REASONS` is still `{final_response, is_done}`, which matches INV-9. A review-stopped run is skipped, as it should be.
- **#888, HttpTransport content-type.** The new `_json_request_headers` adds `content-type: application/json` only when no spelling of the header is present, and it never replaces the caller's value.
  - The Slack and Google Chat connectors pass a lowercase `content-type`, so exactly one header goes out.
  - The other connectors pass none, so the transport adds one lowercase header.
  - The lowercase header-key check in `OutputRequest` still behaves and was left alone.
- `lint/baseline.json` differs from d87fcbaf only by main's #763 (`C018` 1 → 0). `git diff d4100704..HEAD -- lint/ .github/ .semgrep/` is empty.
- A002 counts 639, against 638 at b18ac7d1 (whose code equals d87fcbaf). This iteration's fixes add no function A002 inspects, and A002 has no finding in this PR's output files. So the +1 came with the merge; I did not isolate which of main's files carries it.

## Per-finding work and evidence

### S6-1: `EmailOutput(to=[])` named `recipients` instead of `to`

- **Reproduced:** the feature pack failed only `test_invalid_connector_argument_is_rejected_at_construction_naming_the_parameter_and_no_secret[email-empty-to]`, with `AssertionError: recipients must be a non-empty tuple of email addresses, got ().`
- **Root cause:** `OutputArguments.texts` accepts an empty sequence, so `EmailOutput.__init__` handed `()` to `SmtpSettings`, whose `__post_init__` names its own field.
- **Hypotheses, in order:**
  1. Make `texts` reject an empty sequence. Rejected: GitHub's `labels: Sequence[str] = ()` default goes through `texts`, so every `GitHubIssueOutput` without labels would fail.
  2. Raise inline in `EmailOutput.__init__`. Rejected: §12.4 says "Connector constructors contain no `raise` themselves". The briefing asks for the `OutputArguments` pattern, and an inline raise would be a second recorded deviation beside TelegramOutput's.
  3. Add a `minimum=` keyword to `texts`. Rejected: it acts as a flag with one non-default caller, which the function-design rules advise against, and it changes a §8.5 signature and the labels message.
  4. **Chosen:** add a leaf static method, `OutputArguments.non_empty(values: tuple[str, ...], *, parameter: str) -> tuple[str, ...]`. It returns the tuple, or raises `ConfigurationError(f"{parameter} must list at least one value.", details={"parameter": parameter})`.
     - `EmailOutput.__init__` wraps the existing `texts` result with it, so spec row 13's texts → address path is unchanged.
     - The method calls no other `OutputArguments` method, so the call chain stays one level deep.
     - `SmtpSettings` is untouched and still rejects `recipients=()` when built directly.
- **Commit:** 5b437f24 (`base.py` +7 lines, `email.py` 1 line changed).
- **Evidence:**
  - `test_output_connectors_configuration.py` gives `86 passed`, and the feature pack gives `341 passed`.
  - A probe printed:
    - `[] -> to must list at least one value. {'parameter': 'to'}`
    - `() -> the same`
    - `'ops@acme.com' -> ('ops@acme.com',)`
    - `[' ops@acme.com '] -> ('ops@acme.com',)`
    - `github labels=() ()`
    - `record -> recipients must be a non-empty tuple of email addresses, got ().`
- **Spec note for the orchestrator (docs only, not done here):** this is a ninth `OutputArguments` method beyond the §8.5 list. The §17 TelegramOutput bullet says a one-caller check stayed inline "rather than adding a ninth `OutputArguments` method beyond §8.5". So §8.5, §12.3 row 13, and §17 want one line each. The briefing limits my `docs/` writes to review.md, verify-log.md, and this report, so I did not edit spec.md. `OutputArguments` is not a root export, so neither `vidbyte.__all__` nor the C016 contract changes.

### S6-2: the `OutputDeliveryError` resend hint passed receipts to `deliver`

- **Reproduced:** `scratchpad/s5r2/repro_s6_2.py` follows `repair_approaches[2]` literally and gets `[('webhook', 'unexpected:AttributeError')]`. The spec recipe gets `[('webhook', 'sent')]`.
- **Root cause:** the hint called its selection `failed`, which a reader takes to be the `err.failed` property, and that property holds `DeliveryReceipt`s.
- **Fix (2334385b):** one string in `vidbyte/lib/errors/base.py`:
  > Resend only the failed connectors, not err.failed (those are receipts): failed_connectors = [c for c, r in zip(agent.outputs, err.receipts, strict=True) if r.status is DeliveryStatus.FAILED], then await OutputDispatcher.deliver(failed_connectors, err.reply, {}); a failed network output may already have posted, so check its destination first.

  The `deliver` arguments are the real signature `(outputs, reply, metadata)`. R-11's network caution is kept word for word. It matches `vidbyte/agents/output/README.md:86-99`.
- **Hypothesis that failed:** splitting the literal over two lines, copying `errors/base.py:496-497`. Lint S062 (no-implicit-string-concatenation, BLOCKING) failed on it. The diagnostic says to merge the pieces into one literal on one line, and that `+` or `''.join()` will not work. So it is one literal; the `:496` precedent predates S062.
- **Evidence:** `scratchpad/s5r2/verify_s6_2_hint.py` regex-extracts the two expressions from the live hint string and evaluates them exactly as written. It prints `selected: 1 of 2` and `resend receipts: [('webhook', 'sent')]`. The feature pack gives `341 passed`, including the A003 packet test in `test_output_connectors_dispatch.py`.
- `tests/features/agent_output_connectors/FEATURE.md:21` still says `OutputDispatcher.deliver(failed, err.reply, {})`. That is a test-tree file, which this stage may not edit. There it describes the spec's AC-24 variable, which holds connectors, so it is not wrong.

## Gate matrix

All local gates ran in this worktree on the merged tree, code at 2334385b, in CI order.

- **Feature pack** (`PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`): PASS. `341 passed in 3.87s`.
- **Lint** (`python lint/run.py`): PASS. Seven rules IMPROVED and none REGRESSED:

  ```
  S025 IMPROVED 263 -> 261. Lower it with: python lint/run.py --rule S025 --update-baseline
  S051 IMPROVED 259 -> 258. Lower it with: python lint/run.py --rule S051 --update-baseline
  SDK-LINT: PASS
  ```

- **run_ci source** (`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`): PASS, exit 0.

  ```
  tests	est_workflow_agent_forks.py ......                                [100%]

  ====================== 3824 passed, 13 skipped in 32.43s ======================
  CI passed.
  ```

- **run_ci full** (`python scripts/run_ci.py`, PYTHONPATH unset): PASS, exit 0.

  ```
  ====================== 3824 passed, 13 skipped in 33.12s ======================
  No broken requirements found.
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  ```

- **Contract** (`python scripts/generate-sdk-public-api.py --check`): PASS. `contracts/sdk-public-api.json is current at 839e8e33a369743d0643463137f05a6b5eb39282 (vidbyte-sdk 0.2.1, 623 exports).`
- **Semgrep** (1.170.1 in the session venv, put first on PATH through `cygpath -u`): PASS.
  - `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` gave `1/1: ✓ All tests passed` (exit 0).
  - `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` gave `Ran 1 rule on 911 files: 0 findings.` (exit 0).
- **Remote ci.yml** (run 38217488376, headSha 2334385b): PASS.
  - Source / Python 3.11: `3819 passed, 18 skipped in 41.70s` · `CI passed.`
  - Source / Python 3.12: `3819 passed, 18 skipped, 19 warnings in 53.88s` · `CI passed.`
  - Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`
- **Remote static-policy.yml** (run 38217490653, headSha 2334385b): PASS. Static policy gave `1/1: ✓ All tests passed` · `Ran 1 rule on 911 files: 0 findings.`
- **Test tree checks:** `git diff d87fcbaf..HEAD -- tests/features/agent_output_connectors` and `git diff d4100704..HEAD -- tests/` are both empty.

The docs-only commit that records this report is dispatched again after the push. Its run IDs are in the STATUS block.

## Test changes proposed

None. No test contradicts the spec.

## Findings I believe are wrong

None.

## Open items and next hypotheses

None of the defects handed to this iteration is still open, and every gate is green.

There is one docs follow-up for the orchestrator or spec author. It is not a gate and not a finding:
- Record `OutputArguments.non_empty` in spec §8.5, in §12.3 row 13 (the `to` path is now texts → non_empty → address), and in §17. §17's TelegramOutput bullet currently says the earlier iteration avoided "a ninth `OutputArguments` method".
- The PR body's deviations list may want the same line when S6 refreshes it.

If a reviewer rejects the new method, the runner-up is an inline raise in `EmailOutput.__init__`, recorded as a second §17 exception beside TelegramOutput's.

**Watch out:** S062 blocks any implicit string concatenation in `vidbyte/`, so the error-packet strings must stay one literal on one line.
