# S5 repair, iteration 1 of 8: agent-output-connectors

**Branch:** feat/agent-output-connectors
**PR:** https://github.com/cerredz/Vidbyte-SDK/pull/882
**Start HEAD:** 9db8a702 (78321115 plus the orchestrator's pipeline.md commit)
**Code HEAD:** a9230d46

## Outcome

- Merged origin/main as orchestrator Step 0.
- Fixed all twelve findings handed to this iteration, one commit each: R-1, R-2, R-3, R-4, R-6, R-7, R-8, R-9, R-10, R-11, R-12, and R-15.
- Every local gate is green on the merged tree, and both dispatched remote workflows are green on a9230d46.
- No test was edited. No baseline, suppression, or CI config was touched, and `vidbyte/agents/base.py` was not edited.

## Step 0: catch up with main

- Ran `git fetch origin`, then `git merge origin/main`, which brought in 25 commits since db3988ff.
- Git merged with no conflicts. I checked each overlapping file by hand:
  - `vidbyte/agents/fork.py` keeps `outputs=()` with `# @intent forks-never-deliver` (lines 82–84) and #884's `ProviderModelRegistry.vidbyte_key_follows_provider` check in `_api_key` (lines 113–121).
  - `vidbyte/lib/enums/__init__.py` keeps main's `CodingContextSection` and `TextModelMode`, and this PR's `DeliveryStatus` and `OutputDestination`, both in the imports and in `__all__`.
  - `vidbyte/agents/README.md` keeps main's CodingContext paragraph and `coding_context/` Key Modules line, and this PR's `## Output Connectors` section and `output/` line.
- Git's default merge message was reworded on the unpushed commit. The commit is ba83c953 `chore(merge): catch up with origin/main [gate:mergeability]`, with parents 9db8a702 and e6d42359.
- The contract did not conflict, and `--check` reports it current (623 exports), so it was not regenerated.
- Checks after the merge:
  - The feature pack gave `16 failed, 324 passed`, the same 16 S4 cases.
  - Lint gave `SDK-LINT: PASS`.
  - `_generate_reply` measures `C901 … (10 > 1)`, `PLR0912 Too many branches (9 > 1)`, and `PLR0915 Too many statements (50 > 1)`, so it is unchanged at 10 / 9 / 50.
- Lint count moved by main: S009 reads 350/350 at ba83c953, while the S4 review recorded 349 for the pre-merge branch.
  - I ran `lint/run.py --rule S009 --all` in a temporary worktree at ba83c953 and at the final tree.
  - The finding sets, with line numbers stripped, are identical.
  - So the +1 came in with main, and this iteration adds no S009 finding.

## Per-finding work and evidence

| ID | Commit | What changed | Reproducer, before → after |
|---|---|---|---|
| R-1 Blocker | 228c0fdc | `delivery.py`: module `ContextVar` `_OUTPUT_POST_ACTIVE`. It is set before `HttpTransport().request` and reset in a `finally` on the same `try`. Static `OutputHttp._keep_log_record` (with `@intent output-request-log-hides-the-url`) is registered once at import with `logging.getLogger("httpx").addFilter`. There is no `import httpx` and no level change, and `transport.py` is untouched. | `test_url_credential_never_reaches_the_httpx_request_log_*` went from 6 failed (`'HTTP Request: POST https://hook.eu1.make.com/S3CRETwebhook …'` in caplog) to `31 passed` for `test_output_connectors_security.py`. |
| R-2 Major | b0b403f8 | `dispatcher.py`: `connectors()` rejects a non-`OutputDestination` destination with `f"outputs[{index}].destination must be an OutputDestination, got {type(item.destination).__name__}"` (the spec row 22 text). `_deliver_one` raises `ConfigurationError` unless `send` returned a `DeliveryReceipt`. The header's edge-case line is updated. | `[destination-not-an-enum]` and `[none]` / `[str]` went from failing to passing. S008 measures: `connectors` 8 / 7 / 15 and `_deliver_one` 4 / 3 / 10. |
| R-3 Major | e6ae0fa2 | `email.py`: `_SMTP_EXECUTOR = ThreadPoolExecutor()` and `await asyncio.get_running_loop().run_in_executor(_SMTP_EXECUTOR, OutputSmtp.send, …)`. The header and the `@intent` text are updated, as are the `OutputSmtp.send` docstring and the lib README "Deadline" footgun. | `test_sync_run_returns_at_the_delivery_deadline_*` went from failed (10 s backstop) to passing. S006, S046, and S052 stay CLEAN. |
| R-4 Major | f73ae753 | `constants/outputs.py` gains a `# Validation` group with `OUTPUT_EMAIL_ADDRESS_PATTERN = r"[^\s,]*@[^\s,]*"` and `OUTPUT_HTTPS_PREFIX`, both in `__all__`. `_is_address` and `OutputArguments.address` both `re.fullmatch` the pattern and keep their own messages. `_HTTPS` is removed. The prefix constant is used in the records, `https_url`, and `_link`, and the checks stay different. | No test is red for R-4. The AC-16 and AC-20 address cases still pass: `334 passed` (the 6 failing are R-12 and R-15). C008 is unchanged at 45. |
| R-12 Minor | 50eb32c9 | `OutputSmtp.send`: the `with` block becomes an inner `try` whose `finally` calls `client.quit()` under `contextlib.suppress(smtplib.SMTPException, OSError)`. The header edge case is updated. | `test_quit_reply_after_*` [quit-answers-250], [quit-answers-421], and [partial-refusal-then-quit-421] went from failed to passing. The verifier's real-smtplib `v_e4_e5.py` prints `R-E4 QUIT=421: server accepted mail=True -> receipt sent None`. |
| R-15 Minor | fa4a67bb | `OutputArguments.https_url` reads `urlsplit(value)` and `.port` in a `try` and raises `ConfigurationError(message) from None`. The message, "`<parameter>` must be an https:// URL with a host and a valid port.", never contains the value. | The 3 `slack-*` configuration cases went from failed to passing. The verifier's `v_blind_urls.py` now reports `ConfigurationError; secret in message: False` for the port and IPv6 cases. |
| R-6 Minor | 0cb2dbc8 | The `jira-site-is-a-bare-atlassian-host` block moves onto `self._site = OutputArguments.matching(…)` in `__init__`. `send` gets `jira-issue-link-is-built-from-the-key` above the request, replacing the inline comment, because A002 would otherwise flag `send`. `is_deliverable` gets `only-accepted-answers-are-delivered` above its return. | `lint/run.py --rule A002 --all` lists no output files. |
| R-9 Minor | e41c535f | `JIRA_ISSUE_PATH = "/rest/api/3/issue"` and `JIRA_BROWSE_PATH = "/browse/"` are added, and `jira.py` uses them. | Feature pack `340 passed`, including the Jira wire contract. |
| R-7 Minor | 540b8501 | The `delivery.py` ARCHITECTURE NOTE no longer claims to be "the only place" and drops the INV-11 citation. Both Jev headers list `test_output_connectors_agent_wiring.py`. | Header text only. |
| R-8 Minor | a432dcde | `TelegramOutput.__init__`: an int passes, a str goes through `OutputArguments.text` (spec row 12), and anything else raises "chat_id must be an int or a non-blank string, got …". The receipt url error is not changed, as the verifier advised. | `chat_id=1.5` and `True` now give "must be an int or a non-blank string"; `'   '` still gives "must be a non-blank string". |
| R-10 Minor | ad96036f | A `## Non-Goals` section in `vidbyte/agents/output/README.md` restates the settled exclusions in plain terms, with no Q-IDs, since `docs/` is opaque to agents. | A009 is CLEAN. |
| R-11 Minor | a9230d46 | The spec r6 caution sentence is added in the agents/output README after the resend recipe, in the lib/outputs README "Deadline" footgun, and in `OutputDeliveryError.repair_approaches[2]`. | `test_output_connectors_dispatch.py` packet checks still pass (`340 passed`). |

## Gate matrix (code at a9230d46)

- **Feature pack** (`PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`): PASS. `340 passed in 2.14s`.
- **Lint** (`python lint/run.py`): PASS. `S025 IMPROVED 263 -> 261` · `S051 IMPROVED 259 -> 258` · `SDK-LINT: PASS`. A002 is at 638 against a baseline of 703.
- **run_ci source** (`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`): PASS.

  ```
  tests\test_workflow_agent_forks.py ......                                [100%]

  ====================== 3743 passed, 13 skipped in 41.21s ======================
  CI passed.
  ```

- **run_ci full** (`python scripts/run_ci.py`, with PYTHONPATH unset): PASS.

  ```
  No broken requirements found.
  …
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  ```

- **Contract** (`python scripts/generate-sdk-public-api.py --check`): PASS. `contracts/sdk-public-api.json is current at 839e8e33a369743d0643463137f05a6b5eb39282 (vidbyte-sdk 0.2.1, 623 exports).`
- **Semgrep** (1.170.1, own venv): PASS. `1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.` · exit 0.
- **Remote static-policy.yml** (run 38211642693, head a9230d46): PASS. success: Static policy (`1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.`).
- **Remote ci.yml** (run 38211640430, head a9230d46): PASS. success: Source / Python 3.11 (`3738 passed, 18 skipped in 36.26s` · `CI passed.`), Source / Python 3.12 (`CI passed.`), Package (`Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`).

The full suite grew from 3527 to 3743 passing because of main's 25 commits.

## Test changes proposed

None. No test contradicts the spec.

## Findings I believe are wrong

None.

## Out of scope, observed

The verifier's `v_blind_urls.py` still shows `https://hooks.slack.com/services/T/B/VSEC\x7fctrl` passing construction and failing at delivery as `unexpected:InvalidURL`.
- No secret leaks: the formatted traceback and `repr(cause)` are both clean.
- This is the R-13 / Q-11 class, unprintable or non-ASCII credential validation. It is [scope-adding], recorded as not built, and was not changed here.

## Not fixed by direction

- R-5 is a spec wording fix, already made in r6.
- R-13 is [scope-adding] and recorded as Q-11, not built.
- R-14 is test-only; its tests were added at 45ba29cc and pass.

Their review.md statuses are left for the orchestrator.

## Hypotheses for a next iteration

None are needed for these findings. If the re-reviewer questions a choice, these are the alternatives already considered:
- **R-1:** redact `record.args` to scheme and host instead of dropping the line. The review accepted it as an equal alternative; the spec chose the drop.
- **R-12:** add an explicit `client.close()` after the suppressed `quit()`. Rejected because real `quit()` closes the socket on every path, and the fake would record "close" twice.
- **R-8:** a new `OutputArguments` method. Rejected as a one-caller helper outside the §8.5 method list.
