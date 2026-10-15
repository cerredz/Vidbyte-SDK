LENS: conformance
VERDICT: SOUND — Both S6 fixes hold when run exactly as written, the catch-up merge is clean and leaves every invariant it could touch intact, and the only findings are two Minors: a resend caution that was already narrower than the spec's own edge cases before this round, and a PR body that still calls both fixed defects "not fixed".

Scope of this re-review: the change from ed1dd67b to 81f9cba0. That is the polish pass (ad4ed50a, 0ca19568), the AC-20 test row (4b063c28), the merge d4100704, and the fixes 5b437f24 (S6-1) and 2334385b (S6-2). Each changed source file was read in full. Whole-PR conformance was re-checked only where the merge could reach it: INV-9, INV-22/S008, D-7, AC-1, AC-15, the contract, and #888's header change. The worktree HEAD moved to the docs-only r7 commit 5bd94199 while I worked. `git diff 81f9cba0 HEAD` touches only `docs/spec/agent-output-connectors/`, so every run below exercised 81f9cba0's code.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" it)
- **S6-1 keeps the constructor rule without disturbing the other callers.**
  - `OutputArguments.non_empty` (`vidbyte/lib/outputs/base.py:73-78`) is a leaf that calls no other `OutputArguments` method.
  - `EmailOutput.__init__` (`email.py:50`) composes it at the call site as texts → non_empty → address, which is spec row 13 in r7.
  - `texts` is unchanged, so GitHub's `labels=()` and `labels=[]` still give `()`.
  - `SmtpSettings` is unchanged, so building it directly with `recipients=()` or `[]` still raises with `{'field': 'recipients'}`.
  - No connector constructor gained a `raise`.
- **S6-2 is one literal, and it works when run as written.**
  - Executed verbatim from a live error, the hint selected exactly the two failed connectors out of three. The resend made two requests, only to those hosts, and both came back SENT.
  - R-11's sentence ("a failed network output may already have posted, so check its destination first") is kept word for word.
  - No two string tokens are adjacent anywhere in the PR's hunks, so S062 holds. The adjacent strings at `errors/base.py:486-497` are main's code (aa22f6b29, 2026-08-31).
- **The merge is clean.**
  - `git diff --name-only ab7182d3 d4100704` matches the PR's own 70 paths exactly, so no main file was changed.
  - `git show --cc d4100704` has one hunk: the union of both sides' `__all__` entries in `vidbyte/lib/enums/__init__.py`.
  - `vidbyte/agents/base.py`, `fork.py`, `jev/`, and `AgentStopReason` are untouched by the merge.
  - #889 adds only a `middleware_abort` path and a `CONTRACT_UNSATISFIED` path, and both are already skipped under INV-9.
  - #888 sends exactly one content-type header for all 10 HTTP connectors. Google Chat keeps its own `application/json; charset=UTF-8`.
- **The test discipline held.**
  - The only test change since ed1dd67b is the S2 row `email-empty-to` (+2 lines in 4b063c28).
  - That row bites: with `non_empty` neutralised in-process, the message is "recipients must be a non-empty tuple…", which has no whole-word `to`.
  - `git diff d87fcbaf..81f9cba0 -- tests/features/agent_output_connectors test-plan.md` and `git diff d4100704..81f9cba0 -- tests/` are both empty.

FINDINGS (ranked, most severe first)

R-C1 [Minor] [request fidelity] `vidbyte/lib/errors/base.py:215` — The resend hint warns only about `network` failures, but EC-5 and EC-24 failures may also already have been delivered, so following the hint can post twice
  Evidence:
  - The hint ends: "a failed network output may already have posted, so check its destination first." It says nothing about `http_5xx` or `smtp_recipients_refused`.
  - spec.md EC-5: "GitHub returns 502 after creating the issue. | FAILED `http_502`, not retried. | … At most one issue exists."
  - spec.md EC-24: "SMTP accepts one of two recipients. … FAILED `smtp_recipients_refused` … A retry would send them a duplicate."
  - request.md §C: "Timeouts and 5xx are reported as failures, not retried (the first post may have landed)."
  - Probe (scripted `_send_once`: GitHub stores the issue, then answers 502; the hint's two expressions applied unchanged): `error codes: [('github_issue', 'http_502')]`, `caution covers http_5xx: False | covers smtp_recipients_refused: False`, `issues stored at GitHub: 2`.
  Failure: GitHub answers 502 after creating the issue (or SMTP refuses one of two recipients). The caller follows `repair_approaches[2]`, and the second issue is created (or the accepting recipient gets the email twice). The SDK's "at most one issue exists" guarantee in EC-5 is lost through the SDK's own advice.
  This is not a regression. The same sentence has been in spec §9.2, AC-24, and EC-42 and in both READMEs since r6 (R-11). The repair kept it word for word, as it was told to.
  Smallest fix: wording only, with no new control.
  - Widen the caution to: "a failed network or http_5xx output, or an email with smtp_recipients_refused, may already have been delivered (to some recipients), so check its destination first."
  - Make the change in the hint, which must stay one literal on one line (S062).
  - Make the same change at `vidbyte/agents/output/README.md:98-99` and `vidbyte/lib/outputs/README.md:145-146`.
  - The spec author makes the same change in §9.2, AC-24, and EC-42.
  - The user may also take this as a follow-up.
  Spec IDs: EC-5, EC-24, EC-42, AC-24, §9.2; request.md §C "Retries only where a duplicate is impossible".

R-C2 [Minor] [deviations] `docs/spec/agent-output-connectors/pr-body.md:189`, `:193` — The PR body, which S6 says matches the remote PR description, still lists both fixed defects as "not fixed", and its TelegramOutput rationale no longer holds
  Evidence:
  - pr-body.md:193: "**Small observations from writing this PR, not fixed.** `EmailOutput(to=[])` raises a `ConfigurationError` that names `recipients` instead of `to`. … passing `err.failed` (receipts) instead of connectors gives `unexpected:AttributeError` receipts."
  - pr-body.md:189: "`TelegramOutput.__init__` … because a one-caller check was not worth a new `OutputArguments` method." 5b437f24 has since added the one-caller method `non_empty`, and r7 rewrote the matching §17 bullet for exactly this reason.
  - The probe shows `to=[]` now gives "to must list at least one value." with `{'parameter': 'to'}`.
  Failure: a human reviewer reading PR #882 sees two defects described as open that the branch has closed, and a design rationale the code now contradicts.
  Smallest fix (S6, docs only):
  - Drop the first two sentences of the "Small observations" bullet.
  - Reword the Telegram bullet to match r7 §17.
  - Optionally, add one line under the fixes for S6-1 and S6-2.
  Spec IDs: n/a (PR record; spec §17 r7 is already correct).

No Blocker or Major.

Weighed and rejected as findings:
- **Is a ninth `OutputArguments` method justified? Yes.** The orchestrator asked about this directly.
  - The runner-up, an inline raise in `EmailOutput.__init__`, would break §12.4 ("Connector constructors contain no `raise` themselves") a second time. It would also break the field-guide lesson behind that rule, `strict-config-dataclasses.md` ("Check: `__init__` contains no `raise`"). Under this review's scale, breaking a field-guide lesson is Blocker-class.
  - The house-style smells ("an abstraction with one implementation", "a knob with one caller") are about interfaces and configuration options. `non_empty` is neither: it is a leaf check in the class whose job is constructor-argument checks.
  - It meets AGENTS.md Style 1 (a leaf, composed at the call site, no chain), Style 3 (one job), and Style 5 (it sits in the feature's own `lib/` package).
  - The other repair options were weaker. A `minimum=` flag on `texts` would be a flag with one non-default caller (the function-design rules advise against flags). Making `texts` reject empty input would break GitHub's `labels=()`.
  - r7's §17 wording that separates this from Telegram's inline check is thin, since both checks name their own parameter. That is spec prose, not code, and it is outside what I was asked to flag.
- **The hint fails on a second-round error.** If the resend fails again, applying the hint to that new error zips `agent.outputs` (3) with 2 receipts. That raises `ValueError: zip() argument 2 is shorter than argument 1`, which is loud, and it never mispairs or sends twice. The spec's §9.2 recipe has the same shape. Not a deviation.
- **`tests/features/agent_output_connectors/FEATURE.md:20` still reads `OutputDispatcher.deliver(failed, err.reply, {})`.** It is a consumer list in the test tree, and `failed` there means AC-24's connector tuple. The README recipe at `vidbyte/agents/output/README.md:88-95` defines `failed` as connectors. It is not wrong, and repair may not edit it.
- **`email.py`'s header TESTS line omits `test_output_connectors_configuration.py`.** This predates this round: every earlier email constructor row already lived there. `base.py`'s header, which owns `non_empty`, already lists that file.
- **`email.py:50` is 139 characters.** `lint/ruff.toml` selects only `TID251`, no rule bounds line length, and `lib/outputs/` already has 26 lines over 140.

VERIFIED CLAIMS
1. Feature pack `341 passed`: held, `341 passed in 3.94s`.
2. Full suite `3824 passed, 13 skipped`: held, `3824 passed, 13 skipped in 32.26s` from `pytest tests` (not `run_ci`, by instruction). `git status --short` was empty afterwards.
3. S6-1 probe output (repair report lines 52-58): held, character for character.
   - `[]` and `()` give `to must list at least one value. {'parameter': 'to'}`.
   - `'ops@acme.com'` gives `('ops@acme.com',)`, and `[' ops@acme.com ']` gives `('ops@acme.com',)`.
   - GitHub labels give `()`.
   - The record gives `recipients must be a non-empty tuple of email addresses, got ().`
   - Extra cases also name `to`: `''`, `'  '`, `None`, `set()`, `['']`, `['a@b','']`, an iterator, and a dict.
   - With the secret in `SMTP_PASSWORD` or passed explicitly, no case echoes it in the message, `details`, or the exception chain.
4. "`SmtpSettings` still rejects `recipients=()` when built directly": held, for both `()` and `[]`.
5. "`texts` still accepts GitHub's empty `labels=()` default": held, for both the default and `labels=[]`.
6. S6-2 "run exactly as written, the hint resends only the failed connectors and gets SENT": held. In my 3-connector run, Slack SENT, the webhook got `http_500:boom`, and GitHub got `http_404`.
   - The hint selected `['WebhookOutput', 'GitHubIssueOutput']`.
   - The resend made requests to `['hook.eu1.make.com', 'api.github.com']` only, and both came back `sent`, with GitHub's URL.
   - Passing `err.failed` instead still gives `unexpected:AttributeError`, so the hint's warning is needed.
7. "R-11's network caution is kept word for word": held. The old and new hints end with the same clause. The scope of that caution is R-C1.
8. S062, "one literal": held. A tokenize scan of the three changed files finds no adjacent string tokens in PR code.
9. INV-9 allowlist after #889/#887: held.
   - `OUTPUT_DELIVERABLE_STOP_REASONS = {final_response, is_done}` (`constants/outputs.py:31-33`).
   - `AgentStopReason` is unchanged.
   - The merge diff has no `stop_reason` or `StopReason` change apart from an `__all__` context line.
   - `_unverified_finish_result` still returns `CONTRACT_UNSATISFIED` (`runtime.py:873-877`).
   - #889's new after-iteration abort goes through `_middleware_abort_result`, which is `middleware_abort` and is skipped.
10. INV-22 and S008: held. `_generate_reply` measures C901 10, PLR0912 9, PLR0915 50 (`base.py:826`). `base.py` is untouched since ed1dd67b, and the S008 baseline is still 19.
11. D-7 fork wiring: held. `fork.py:83-84` still has the `# SDK-built forks never post…` comment and `outputs=()`.
12. AC-15 after #885: held.
    - `CodingAgent.__init__` still ends with `**kwargs: Any` (`coding.py:60`).
    - The coding-agent pack plus the pinned contract tests gave `393 passed, 12 skipped`.
13. Contract current: held. `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).`
14. Tests untouched by repair: held. Both diffs from the briefing are empty, and the PR's test tree against the merge base is 13 added files and nothing else.
15. No baseline, lint config, CI, or `pyproject` edits: held.
    - `git diff origin/main...81f9cba0 -- lint/baseline.json` is 0 lines, and so is the same diff over `lint .github .semgrep pyproject.toml scripts`.
    - `d87fcbaf..81f9cba0` shows only main's `C018 1 → 0` (#763).
16. No suppressions: held. The PR diff adds no `noqa`, `type: ignore`, `nosemgrep`, `skip`, or `xfail`.
17. AC-1, the §4 snippet extracted verbatim from spec.md (r7 HEAD): held, `byte-equal: True`. Slack got `{'text': 'Coupon total wrong\n\nTotals ignore coupons.'}`; GitHub got `{title, body, labels:['bug']}`.
18. Round-1 Minors closed:
    - R-C2 (E302): held. `ruff --preview --select E301,E302,E303,E305` gives `All checks passed!` over both packages.
    - R-C1 (Telegram deviation): held. It is recorded in §17.
19. Not verified, because the briefing forbids `lint/run.py`, `run_ci.py`, and network access:
    - `SDK-LINT: PASS`;
    - Semgrep `0 findings`;
    - remote runs 38217869950 and 38217872582.
    Partial evidence:
    - `ruff --config lint/ruff.toml` and mypy (`lint/mypy.ini`, exit 0) pass on the three changed files;
    - S008 was measured;
    - the baseline is unchanged.
    verify-log.md records runs 38217488376 and 38217490653 on 2334385b, which is a different commit from the briefing's 81f9cba0.

COMMANDS RUN
- `git log --oneline --first-parent ed1dd67b..81f9cba0`; `git diff ed1dd67b..d87fcbaf -- vidbyte tests …`; `git diff d4100704..81f9cba0 -- vidbyte` (read in full).
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` → `341 passed in 3.94s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent tests/test_jev_agent.py tests/test_restore_output_schema.py tests/test_agent_fork_isolation.py tests/test_agent_tool.py tests/test_custom_exception_constructors.py tests/test_readme_size_limit.py tests/test_workflow_agent_forks.py` → `393 passed, 12 skipped in 14.77s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests` → `3824 passed, 13 skipped in 32.26s`; `git status --short` was empty.
- `python -m ruff check --no-cache --isolated --select C901,PLR0912,PLR0915 --config "lint.mccabe.max-complexity=1" --config "lint.pylint.max-branches=1" --config "lint.pylint.max-statements=1" vidbyte/agents/base.py` → `826:15 C901 (10 > 1)`, `PLR0912 (9 > 1)`, `PLR0915 (50 > 1)`. With the default limits it reports nothing for `_generate_reply`.
- `python -m ruff check --no-cache --config lint/ruff.toml <3 changed files>` → `All checks passed!`. The same files with `--isolated --select E,W,F,I,B,UP,SIM,…` → `All checks passed!`.
- `python -m ruff check --no-cache --isolated --preview --select E301,E302,E303,E305 vidbyte/lib/outputs/ vidbyte/agents/output/ vidbyte/lib/errors/base.py` → `All checks passed!`
- `python -m mypy --config-file lint/mypy.ini --cache-dir=nul --follow-imports=silent <3 changed files>` → `exit 0`.
- Tokenize scan for adjacent string tokens → `base.py []`, `email.py []`, `errors/base.py [486, 491, 492, 496]` (all main code; `git blame` aa22f6b29).
- `python scripts/generate-sdk-public-api.py --check` → `… current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).`
- Diff checks for tests, baseline, lint, CI, the merge path set, and the combined diff of the merge → as in claims 14-16 and "What the implementation gets right".
- Probes, run as stdin scripts so nothing was written to the repo:
  - S6-1 cases (claim 3);
  - the literal S6-2 hint (claim 6);
  - the second-round hint → `ValueError: zip() argument 2 is shorter than argument 1`;
  - EC-5 with the hint → `issues stored at GitHub: 2` (R-C1);
  - content-type for 10 connectors through `httpx.MockTransport` → one header each;
  - mutation of the `email-empty-to` row → `whole-word 'to' found: False`.
- `python <session scratchpad>/rereview/p_ac1_snippet.py docs/spec/agent-output-connectors/spec.md` → `byte-equal: True`.
- Not run, by instruction: `scripts/run_ci.py`, `lint/run.py`, Semgrep, `gh`.
- One stray file, `$TEMP/x1.txt`, was created by a shell redirect during a path comparison. It sat outside the repo and was deleted at once. The worktree was never written.
