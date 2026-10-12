# Verification log: Agent output connectors

Gate set (from context/code-map.md §1), in CI order:

- **feature pack** (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors`
- **lint** (local, also inside run_ci): `python lint/run.py`, ending `SDK-LINT: PASS`
- **run_ci source** (local): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
- **run_ci full** (local): `python scripts/run_ci.py` with PYTHONPATH unset (source and package stages)
- **public API contract** (local, C016): `python scripts/generate-sdk-public-api.py --check`
- **Semgrep** (local and remote, `static-policy.yml`): `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1 in its own venv)
- **remote ci.yml** (remote only, dispatch-only): Source 3.11, Source 3.12, Package
- **remote static-policy.yml** (remote only, dispatch-only)

## Iteration 1 — 2026-10-12 — agent report: reports/S5-repair-1.md

**Defects in:**
- Confirmed findings: R-1 (Blocker), R-2, R-3, R-4 (Major).
- Trivial Minors: R-6, R-7, R-8, R-9, R-10, R-11, R-12, R-15.
- Failing gate: the feature pack, `16 failed, 324 passed` at 78321115. Every failure is an S4 case for R-1, R-2, R-3, R-12, or R-15.
- Out of scope by orchestrator decision:
  - R-5 was already fixed in spec r6.
  - R-13 is [scope-adding]; it is recorded as Q-11 and not built.
  - R-14 is test-only; its tests are already added and pass.

**Step 0, catch up with main (orchestrator-directed):**
- Ran `git fetch origin`, then `git merge origin/main`, which brought in 25 commits since db3988ff.
- Git merged without conflicts. Three files overlap with this PR:
  - `vidbyte/agents/README.md` keeps both the CodingContext text and the Output Connectors section.
  - `vidbyte/agents/fork.py` keeps `outputs=()` with `# @intent forks-never-deliver` and #884's `ProviderModelRegistry.vidbyte_key_follows_provider` check in `_api_key`.
  - `vidbyte/lib/enums/__init__.py` keeps `CodingContextSection`, `TextModelMode`, `DeliveryStatus`, and `OutputDestination`.
- `contracts/sdk-public-api.json` did not conflict. `--check` reports it current at 623 exports, so it was not regenerated.
- Git wrote its default message, which was reworded on the unpushed commit to `chore(merge): catch up with origin/main [gate:mergeability]` (ba83c953, parents 9db8a702 and e6d42359).
- Results after the merge:
  - feature pack: `16 failed, 324 passed`, the same 16;
  - `SDK-LINT: PASS`;
  - `_generate_reply` still measures 10 / 9 / 50 (C901 / PLR0912 / PLR0915).
- Lint count shift that came from main: S009 is 350/350 at ba83c953. The S3 review recorded 349 before the merge. The S009 finding set at ba83c953 and at the final HEAD is identical (diffed with line numbers stripped), so no S009 finding comes from this iteration.

**Hypotheses and attempts (in order):**
- R-1. Hypothesis: httpx's own `HTTP Request:` INFO line carries the full URL, and nothing scopes or filters it.
  - Tried the spec r6 shape. Module `ContextVar` `_OUTPUT_POST_ACTIVE` ("vidbyte_output_post_active", default False). It is set just before `HttpTransport().request` and reset in a `finally` on the same `try` as the `ProviderRequestError` handler. `OutputHttp._keep_log_record` is added once, at import, with `logging.getLogger("httpx").addFilter`.
  - Worked first time: 6/6 security cases pass, and the caller's own request is still logged.
  - Not tried, and not to try: raising the httpx level, setting `disabled` or `propagate`, or `import httpx`. The test catches the first three, and the NFR-7 layering test catches the import.
- R-2. Hypothesis: a `runtime_checkable` Protocol checks attribute presence only, and `_deliver_one` never checks what `send` returned.
  - Added the destination `isinstance` check in `connectors()` (spec message, with no trailing period).
  - Added a `DeliveryReceipt` check after the `wait_for`, mirroring the render check.
  - Worked first time. `connectors` now measures 8 / 7 / 15 and `_deliver_one` 4 / 3 / 10.
- R-3. Hypothesis: on Python 3.11, `asyncio.run` joins the default executor (`asyncio.to_thread`) with no timeout.
  - Used a module-level `_SMTP_EXECUTOR = ThreadPoolExecutor()` with `loop.run_in_executor`. Worked first time; S006, S046, and S052 stay CLEAN.
  - Updated the `OutputSmtp.send` docstring and the lib README "Deadline" bullet. The bullet also says the interpreter still joins the thread at exit.
- R-4. Added `OUTPUT_EMAIL_ADDRESS_PATTERN` and `OUTPUT_HTTPS_PREFIX` in a new `# Validation` group, as spec row 2 places them.
  - `_is_address` and `OutputArguments.address` both `re.fullmatch` the pattern.
  - `_HTTPS` is removed. The https checks stay different (D-19 versus §9.1 and D-21).
  - `ruff --select I001 --fix` was needed on two PR-created files (`dataclasses/outputs.py`, `outputs/base.py`). C008 is unchanged at 45.
- R-12. Hypothesis: `smtplib.SMTP.__exit__` raises `SMTPResponseException` on a non-221 QUIT, inside the receipt-deciding `try`.
  - Replaced the `with` block with an inner `try` whose `finally` calls `client.quit()` under `contextlib.suppress(smtplib.SMTPException, OSError)`. Nesting depth stays 3 (S024 unchanged).
  - No extra `client.close()` was added. Real `quit()` closes the socket on every path, and an extra close would add a second "close" step in the fake.
  - The verifier's real-smtplib `v_e4_e5.py` now prints `QUIT=250 … receipt sent` and `QUIT=421 … receipt sent`.
- R-15. Hypothesis: neither `urlsplit` nor `.port` was guarded.
  - A bare `parts.port` statement is flagged by ruff B018, so the value is bound (`host, _port = parts.hostname, parts.port`) inside the `try`. `ValueError` becomes `ConfigurationError … from None`.
  - The message is now "must be an https:// URL with a host and a valid port". It is used for both failure paths and never echoes the value.
  - Not fixed, out of scope: verifier `v_blind_urls.py` still shows a URL with a `\x7f` control character passing construction and failing as `unexpected:InvalidURL`. That is the R-13 / Q-11 class (unprintable credential validation), [scope-adding], and not built.
- R-6. Moving `@intent jira-site-is-a-bare-atlassian-host` into `__init__` would leave `JiraIssueOutput.send` with no `@intent`, and A002 flags `send`.
  - So `send` got its own accurate block, `jira-issue-link-is-built-from-the-key`. It replaces the inline "Jira returns only the issue key" comment above the request.
  - `is_deliverable` got `only-accepted-answers-are-delivered` above its return. A002 has no findings in output files.
- R-8. The message comes from the shared `OutputArguments.text`, so it cannot change there.
  - `TelegramOutput.__init__` now uses an if / elif / else: an int passes, a str goes through `OutputArguments.text` (spec row 12), and anything else raises "chat_id must be an int or a non-blank string".
  - The receipt url error is deliberately not changed.
- R-7, R-9, R-10, and R-11 are wording or constants only. Each worked first time. R-11 uses the spec r6 caution sentence (AC-24, EC-42).

**Changes:**
- ba83c953 chore(merge): catch up with origin/main [gate:mergeability]
- 228c0fdc fix(outputs): keep credential URLs out of the httpx request log [R-1]
- b0b403f8 fix(outputs): reject a non-enum destination and a non-receipt send result [R-2]
- e6ae0fa2 fix(outputs): run SMTP on a dedicated executor so run() keeps the deadline [R-3]
- f73ae753 fix(outputs): give the email-address rule one owner in the constants [R-4]
- 50eb32c9 fix(outputs): decide the SMTP receipt before QUIT [R-12]
- fa4a67bb fix(outputs): map a malformed webhook URL port or host to ConfigurationError [R-15]
- 0cb2dbc8 fix(outputs): put each intent block above the rule it explains [R-6]
- e41c535f fix(outputs): name the Jira issue and browse paths as constants [R-9]
- 540b8501 fix(outputs): make the delivery and Jev module headers accurate [R-7]
- a432dcde fix(outputs): say an int or a non-blank string in the Telegram chat_id error [R-8]
- ad96036f docs(outputs): add a Non-Goals section to the agents/output README [R-10]
- a9230d46 docs(outputs): warn before resending a network failure [R-11]

Edits were limited to the following. None of them touches `vidbyte/agents/base.py`, `tests/`, `lint/baseline.json`, or CI config.
- Source: `delivery.py`, `dispatcher.py`, `email.py`, `base.py` (lib/outputs), `constants/outputs.py`, `dataclasses/outputs.py`, `jira.py`, `telegram.py`, and `connector.py`.
- Headers only: the two Jev files.
- Wording only: `errors/base.py` (`repair_approaches`).
- Docs: the two output READMEs.

**Gate matrix out** (code at a9230d46):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` | PASS | `340 passed in 2.14s` |
| lint | `python lint/run.py` | PASS | `A002 IMPROVED 703 -> 638` · `S051 IMPROVED 259 -> 258` · `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3743 passed, 13 skipped in 41.21s` · `CI passed.` |
| run_ci full | `python scripts/run_ci.py` (PYTHONPATH unset) | PASS | `3743 passed, 13 skipped in 32.76s` · `No broken requirements found.` · `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 839e8e33… (vidbyte-sdk 0.2.1, 623 exports).` |
| Semgrep | `semgrep --test …` · `semgrep scan --error …` | PASS | `1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.` (exit 0) |
| remote ci.yml | run 38211640430 on a9230d46 | PASS | success: Source / Python 3.11 (`3738 passed, 18 skipped in 36.26s` · `CI passed.`), Source / Python 3.12 (`CI passed.`), Package (`Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.`) |
| remote static-policy.yml | run 38211642693 on a9230d46 | PASS | success: Static policy (`1/1: ✓ All tests passed` · `Ran 1 rule on 908 files: 0 findings.`) |

The remote runs ran on the code commit a9230d46. The docs-only commit that records this log is dispatched again afterwards; its run IDs and results are in the S5 STATUS block.

**Still open:** none of the findings handed to this iteration. R-5 (spec-only, done in r6), R-13 (Q-11, not built), and R-14 (tests already added) were not this iteration's.

## Iteration 1 addendum (polish) — 2026-10-12

**Defects in:** two trivial Minors from the final re-review (reports/S5-rereview.md, verdict SOUND).
- R-C2: `email.py:32` had one blank line before `class EmailOutput` (E302). The R-3 edit left it.
- R-C1: the R-8 `chat_id` check raises inline in `TelegramOutput.__init__`. That contradicts the §12.4 line "Connector constructors contain no `raise` themselves", and the spec did not record it as a deviation.

**Changes:**
- ad4ed50a style(outputs): restore two blank lines before EmailOutput [rereview R-C2]. `ruff check --no-cache --preview --select E302 vidbyte/lib/outputs/email.py` gives `All checks passed!`.
- 0ca19568 docs(spec): record the TelegramOutput chat_id deviation [rereview R-C1]. It adds one bullet to the §17 "Implementation deviations" list and changes no other spec line. The code is kept as it was.

**Gate matrix out** (at 0ca19568):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| feature pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors` | PASS | `340 passed in 2.93s` |
| lint | `python lint/run.py` | PASS | `SDK-LINT: PASS` |
| run_ci source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `3743 passed, 13 skipped in 38.70s` · `CI passed.` |
| remote ci.yml and static-policy.yml | dispatched on the commit that records this addendum | see the S5 STATUS reply | — |

**Still open:** none. `git diff 7f3bb7ff..HEAD -- tests/` is empty.
