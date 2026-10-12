LENS: conformance
VERDICT: SOUND — All twelve repairs hold against their original evidence. The merge of origin/main broke nothing this PR depends on, the tests and baseline were not touched, and only two Minors remain: one unrecorded spec deviation and one blank line.

Scope of this re-review: the full PR diff `origin/main...ed1dd67b`, with every hunk changed since 9463c348 read in its whole file. That covers the 12 repair commits, the merge ba83c953, and the three doc commits. The 5 commits main gained after the merge (#767, #888, #887, #746, #763) were checked for semantic interplay with this PR.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" it)
- **The R-1 log guard is scoped correctly.**
  - `delivery.py:64` sets the flag just before the `try`, and `:81-82` resets it in `finally`. A concurrent task, an exception, a timeout, and a cancellation all leave the flag `False`.
  - The user's own httpx requests still log, both during and after an output send. The filter is registered exactly once.
  - At root DEBUG, no logger prints the token on the 429-retry, 302, network-error, or oversize paths. `HttpTransport` has no logger of its own.
- **R-3 keeps the deadline without breaking interpreter exit.**
  - Sync `run()` raises FAILED `network` at 0.22 s against a 0.2 s deadline.
  - The SMTP worker finishes later (accepted at 2.02 s), and the interpreter joins it and exits cleanly, as INV-19 says.
  - The pool is bounded at the default size (`_max_workers` = 12 on this machine).
  - A real `send_message` failure (smtp_554, smtp_553, all recipients refused) still gives FAILED, because the exception passes through the inner `finally` to the outer `except` (`delivery.py:145-164`).
- **R-2 and R-15 match spec row 22 and row 5 word for word, and stay inside the S008 limits.**
  - `connectors()` uses the exact message from row 22 (`dispatcher.py:47-48`). `_deliver_one` names the connector class and the returned type (`:97-98`).
  - Measured complexity: `connectors` 8/7/15, `_deliver_one` 4/3/10, and `_generate_reply` still 10/9/50.
  - `https_url` re-raises as `ConfigurationError ... from None` and never echoes the value (`base.py:47-57`).
- **The merge is clean.**
  - `fork.py:81-83` keeps `outputs=()` with its `@intent`, and `:110-121` keeps #884's `vidbyte_key_follows_provider`.
  - The enums `__init__` and the agents README keep both sides.
  - The merged main code adds no new `AgentStopReason`. `FinishReview.stop` now ends with `CONTRACT_UNSATISFIED`, which is already in INV-9's skip set.
  - Of the 5 commits main gained since the merge, #888 (one content-type header) is neutral for every connector, because all of them send lowercase header keys. #887 changes only a review-refused plain finish inside `runtime.py`, not any stop reason.
  - The §4 snippet, extracted verbatim from spec.md, still prints byte-equal output.

FINDINGS (ranked, most severe first)

R-C1 [Minor] [deviations] `vidbyte/lib/outputs/telegram.py:43` — The R-8 repair adds a `raise` inside a connector constructor, which the spec forbids, and records the deviation nowhere
  Evidence:
  - The code: `else: raise ConfigurationError(f"chat_id must be an int or a non-blank string, got {chat_id!r}.", details={"parameter": "chat_id"})`.
  - spec.md:1130 (§12.4): "Connector constructors contain no `raise` themselves. Every check lives in `OutputArguments` or in a record's `__post_init__`." Its source is the field guide's `strict-config-dataclasses.md` ("Check: `__init__` contains no `raise`").
  - spec.md:1079 (§12.3 row 12): "`chat_id` is an `int` (not `bool`), or is validated with `OutputArguments.text`." The code instead routes only a `str` to `text` and rejects everything else inline.
  - spec.md:1394 (r6): "R-6, R-7, R-8, R-10, and R-14 need no spec change."
  - Neither the §17 "Implementation deviations" list nor `reports/S5-repair-1.md` (which records only the rejected alternative, at line 106) records the change.
  - `grep -n raise vidbyte/lib/outputs/*.py` shows this is the only `raise` in any of the 11 connector modules.
  - Behaviour: `TelegramOutput(chat_id=1.5)` gives "chat_id must be an int or a non-blank string, got 1.5." (correct for R-8).
  Failure: Behaviour is correct, so nothing breaks at runtime. But a reader or a later agent who checks §12.4 or row 12 finds code that contradicts both, with no record explaining why. This is the kind of drift §17's deviation list exists to prevent.
  Smallest fix: Docs only, which honours the orchestrator's decision to keep the check inline:
  - Amend row 12 to "an `int` (not `bool`), a `str` validated with `OutputArguments.text`, or else `ConfigurationError` naming `chat_id` raised in `__init__`".
  - Add one bullet to the §17 "Implementation deviations" list, saying that `TelegramOutput.__init__` is the single exception to the §12.4 no-`raise` rule and why (R-8; a one-caller `OutputArguments` method was rejected).
  No code change.
  Spec IDs: §12.3 row 12, §12.4 (Records, typing, and validation), §17; S4 R-8.

R-C2 [Minor] [boundaries] `vidbyte/lib/outputs/email.py:30-32` — The R-3 repair left one blank line between `_SMTP_EXECUTOR` and `class EmailOutput`
  Evidence:
  - `git show e6ae0fa2 -- vidbyte/lib/outputs/email.py` shows `+_SMTP_EXECUTOR = ThreadPoolExecutor()` followed by one blank line and then `class EmailOutput(BaseOutput):`. Before the commit, the class had two blank lines above it.
  - `python -m ruff check --no-cache --preview --select E302,E305 vidbyte/lib/outputs/ vidbyte/agents/output/` reports `Found 1 error` (E302 at `email.py:32`). It is the only such finding in either new package.
  - The repo's `lint/ruff.toml` selects only `TID251`, so no gate catches it.
  Failure: No behaviour change. It is a PEP 8 inconsistency introduced by a repair, in the one new module that defines a module-level object above a class.
  Smallest fix: Add one blank line before `class EmailOutput` at `email.py:32`.
  Spec IDs: n/a (house consistency; NFR-3 "clean").

No Blocker or Major.

Weighed and rejected as findings:
- **Style 5 (canonical helper), credential resolution.** `OutputArguments.credential` (`base.py:36-42`) follows the same order as `ProviderModelRegistry.resolve_api_key` (`registries/models.py:163-172`).
  - It is not a Style 5 violation: it is a lib helper with 11 callers. The only lib sibling is bound to the `ModelProvider` env-var table and cannot serve an `OutputDestination` without changing untouched model-registry code. AGENTS.md: "Do not rewrite untouched code just to make it conform". §14 also puts files outside §12.3 behind "ask first".
  - `langfuse.py:40-41` and `langsmith.py:38` already resolve credentials inline on main.
  - D-11 records the sibling explicitly.
  - Possible follow-up for the user, not for repair: a shared `resolve_credential(explicit, env_var)` in `vidbyte/lib/` used by models, outputs, and the tracing providers.
- **Style 5, the httpx log guard.** No other `HttpTransport` caller puts a secret in its URL (a grep for `key=`, `token=`, and `api_key=` URL building outside `lib/outputs` finds nothing). So it is single-feature logic, which Style 5 allows to stay with its feature. It already sits in `vidbyte/lib/`.
- **v_c1 case C still raises a bare `ConfigurationError`.** That case calls `OutputDispatcher.deliver` directly with a connector that never passed `connectors()`. Only the construction path is in INV-21's scope, and the resend path (AC-24) passes already-validated `agent.outputs`. Not a regression.
- **v_e2 probe 3 now shows `unexpected:AttributeError`.** The probe monkeypatches `email.asyncio.to_thread`, which the fix removed, so the probe is obsolete. Probes 1 and 2 show the fixed behaviour.

VERIFIED CLAIMS
1. **R-1 fixed (Blocker).** Held.
   - `v_e1_logs.py`: `root=INFO ... leaked=[]` and `root=DEBUG ... leaked=[]` (was 6 connectors leaking).
   - Own probe `p_r1_concurrency.py`: `1 concurrent: receipt sent | own request logged: True | secret logged: False`. The flag is `False` after the concurrent, exception (`failed network`), timeout, and cancellation paths. `filters on httpx logger: 1`.
   - `p_r1_paths.py` (DEBUG): 429→200, 302, network, and oversize all give `leaked=[]`.
2. **R-2 fixed (Major).** Held.
   - `v_c1_destination.py` A/B: `construction raised ConfigurationError outputs[1].destination must be an OutputDestination, got str`.
   - D: `('webhook','failed','unexpected:ConfigurationError') | cause: ConfigurationError`, with `'deliveries' on last_reply: True`.
3. **R-3 fixed (Major).** Held.
   - `v_e2_deadline.py`: `1 sync run(): ... after 0.22s`, `2 arun(): ... asyncio.run returned after 0.20s` (were 3.03 s and 3.00 s).
   - `p_r3_exit.py`: `run() raised [('failed', 'network')] at 0.22`, `worker: accepted at 2.02`, then a clean exit. `executor max_workers: 12`.
4. **R-12 fixed.** Held.
   - `v_e4_e5.py`: `QUIT=250 ... -> receipt sent None`, `QUIT=421 ... -> receipt sent None`.
   - The `smtp_554`, `smtp_553`, and recipients-refused cases still give FAILED (email pack passes).
5. **R-15 fixed.** Held. `v_blind_urls.py`: `:99999`, `:abc`, and `[::1` give `construction raised ConfigurationError; secret in message: False`.
6. **R-4 and R-8 behaviour.** Held. `_is_address` and `OutputArguments.address` agree on 7 probe strings, including `"a@b\n"` and `" "`. Telegram `1.5`, `True`, and `None` give "an int or a non-blank string", and `'   '` gives "non-blank string". R-8's spec conformance did not hold: see R-C1.
7. **Feature pack `340 passed`.** Held: `340 passed in 2.34s`.
8. **Source suite `3743 passed, 13 skipped`.** Held: the full `pytest tests` gave `3743 passed, 13 skipped in 46.98s`.
9. **`_generate_reply` stays at 10/9/50 for S008.** Held: `base.py:826 C901 (10) PLR0912 (9) PLR0915 (50)`.
10. **The contract is current, with 17 root exports and 18 in `vidbyte.agents.output`.** Held.
    - `generate-sdk-public-api.py --check` gives "current at 839e8e33... 623 exports".
    - The diff adds exactly the 17 §9.2 names.
    - `vidbyte.agents.output.__all__` has 18 names; the only one not exported at the root is `OutputDispatcher`.
11. **Tests were untouched by repair, and the other test-file differences come only from main.** Held. `git diff 7f3bb7ff..ed1dd67b -- tests/features/agent_output_connectors docs/.../test-plan.md` is empty, and the non-feature `tests/` diff against the merge base is empty.
12. **No baseline, lint config, CI, or `pyproject.toml` edits.** Held: `git diff --stat origin/main...ed1dd67b -- lint/` is empty, and so is the diff against the merge base for `lint/`, `pyproject.toml`, `.semgrep`, `.github`, and `scripts`.
13. **The §8.4 budget holds and every touched file is in §12.3.** Held: 23 new files, no new classes from repair, and all non-doc and non-test paths map to §12.3 rows 1–36.
14. **AC-1, the §4 snippet extracted verbatim from spec.md.** Held: `byte-equal: True`. Slack got `{'text': 'Coupon total wrong\n\nTotals ignore coupons.'}`; GitHub got `{title, body, labels:['bug']}`.
15. **R-6, R-7, R-9, R-10, and R-11 text.** Held.
    - The `@intent` blocks sit above the rules they describe.
    - No spec IDs are cited in source (a grep for `INV-|AC-|EC-|FR-|D-|Q-|R-` over PR source is empty).
    - The constants are in `__all__`.
    - The two READMEs together restate every settled exclusion (unsigned webhooks, SES 2465, personal mentions, Q-4, Q-5, Q-7, and Q-8).
16. **No new comment lines over 72 columns in PR-owned code.** Held. The only over-72 lines in touched files are main's own comments in `fork.py`; this PR's `fork.py:81-82` lines are short.
17. **ruff with the repo config and mypy on the 9 repaired modules.** Held: `All checks passed!` and mypy exit 0.

COMMANDS RUN
- `git log --oneline -25`, `git diff --stat origin/main...ed1dd67b` → 67 files, `9594 insertions(+), 9 deletions(-)`.
- `git diff 9463c348 ed1dd67b -- <PR source paths>` (read in full).
- `PYTHONPATH=$(pwd) python <verifier>/{v_e1_logs,v_c1_destination,v_e2_deadline,v_e4_e5,v_blind_urls}.py` → outputs as in claims 1–5.
- `PYTHONPATH=$(pwd) python <scratchpad>/rereview/p_r1_concurrency.py` → `any secret ever logged: False`.
- `PYTHONPATH=$(pwd) python <scratchpad>/rereview/p_r1_paths.py` → four lines, all `leaked=[]`.
- `PYTHONPATH=$(pwd) python <scratchpad>/rereview/p_r3_exit.py` → `run() raised ... at 0.22`, `worker: accepted at 2.02`.
- `PYTHONPATH=$(pwd) python <scratchpad>/rereview/p_ac1_snippet.py docs/spec/agent-output-connectors/spec.md` → `byte-equal: True`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/agent_output_connectors` → `340 passed in 2.34s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent/test_coding_agent_contract.py tests/test_jev_agent.py tests/test_restore_output_schema.py tests/test_agent_fork_isolation.py tests/test_agent_tool.py tests/test_custom_exception_constructors.py tests/test_readme_size_limit.py tests/test_workflow_agent_forks.py` → `142 passed in 1.16s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests` → `3743 passed, 13 skipped in 46.98s`.
- `python -m ruff check vidbyte/agents/base.py --select C901,PLR0912,PLR0915 --config <limits=1> --output-format concise` → `826:15 C901 (10 > 1)`, `PLR0912 (9 > 1)`, `PLR0915 (50 > 1)`.
- `python -m ruff check --config lint/ruff.toml --no-cache <9 repaired modules>` → `All checks passed!`
- `python -m mypy --config-file lint/mypy.ini --cache-dir <scratchpad> --follow-imports=silent <9 modules>` → `exit 0`.
- `python -m ruff check --no-cache --preview --select E302,E305 vidbyte/lib/outputs/ vidbyte/agents/output/` → `Found 1 error.` (`email.py:32`).
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 839e8e33... (vidbyte-sdk 0.2.1, 623 exports).`
- `git diff --stat 7f3bb7ff..ed1dd67b -- tests/features/agent_output_connectors docs/spec/agent-output-connectors/test-plan.md` → empty.
- `git diff --name-only $(git merge-base origin/main HEAD) HEAD -- tests/ | grep -v agent_output_connectors` → empty.
- `git diff --stat origin/main...ed1dd67b -- lint/` → empty.
- `git show 31c7cbfe -- vidbyte/lib/http/transport.py` (#888) and `git show 2b71f1c2` (#887) → read for interplay; neutral for this PR.
- `git diff 9463c348 <merge-base> -- vidbyte/lib/dataclasses/agents.py vidbyte/agents/runtime.py vidbyte/sessions/*.py` → no new stop reason and no `outputs` in session rebuilds.
- Not run, by orchestrator instruction: `scripts/run_ci.py`, `lint/run.py`, Semgrep.
