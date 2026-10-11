LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the transport, key selection and failure mapping do what spec r5 says on every path I drove, including under a fake clock, but the r5 retry deadline has no test (three deadline mutations survive), and on a machine with `VIDBYTE_API_KEY` set, the repo's own suite now sends a real, billable gateway POST.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- `VidbyteGatewayTransport.request` (`vidbyte/lib/http/vidbyte_gateway.py:156-190`) mints one uuid4 key per call. The headers dict and the envelope are built once and reused on every attempt. The deadline is taken once from `loop.time()` before the first POST. Each attempt passes the full `timeout_seconds` with no `retry_count`, and the error is raised after every `except` block has ended. In a fake-clock run every case behaved as INV-10, INV-16 and EC-38 require: 0 s attempts gave 3 POSTs, 629.4 s attempts gave 2 POSTs over 1259.3 s, and 629.6 s gave 1 POST with "did not re-send". All attempts used one key.
- Credential safety holds. `_send` keeps only the exception class, never the instance (`:198-206`). `_json_object` decodes in its own narrow `try`. Messages are built from the status and the shape only. Pack tests scan `str()`, `details` and the formatted traceback for a planted canary and key-shaped strings. The row-1/row-2 split, the truthiness check on `"error"`, the inner retry and a per-attempt fresh key were each mutated, and tests caught every one.
- Key selection fails closed. `find_vidbyte_api_key` (`vidbyte/lib/registries/models.py:173-193`) only reports managed state for a key with the prefix, and fills in `VIDBYTE_API_KEY` only for the six managed providers. `resolved_api_key()` returns the placeholder in managed state (`model_configs.py:137-143`). Explicit managed mode never reads the provider env var. A Vidbyte key reached no vendor host in any path I tried, including direct adapter use and an unpinned BYOK runner after an env change.
- BYOK stays isolated. The runner pins only managed configs (`vidbyte/lib/runners/text.py:46-54`). Each call builds its own decorator, so concurrent calls share no state (`:77-84`). `resolve_api_key` is untouched. The production `.py` diff is lib-only (AC-19), and the SDK holds no markup, fee or price constant (INV-15).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [test quality] vidbyte/lib/http/vidbyte_gateway.py:168-184 (and tests/features/sdk_managed_text/test_managed_text_failures.py:94-110) — No test drives the event-loop clock, so the r5 cumulative deadline (INV-10, INV-16, EC-38, lint S064) can be deleted, inverted or moved without any test failing.
  Evidence: I re-executed mutated copies of the module through a scratch pytest plugin (`-p mutplug`). Worktree files were not edited.
    `MUT=no_deadline` (`if not answer.retryable():`, deadline check removed) → `32 passed in 0.34s`
    `MUT=deadline_gt` (`>=` → `>`) → `32 passed in 0.31s`
    `MUT=deadline_after_first` (deadline re-taken after the first attempt, which allows about 3× the timeout) → `32 passed in 0.31s`
    `MUT=shorten_attempt` (retry attempt gets `deadline - loop.time()` instead of the full timeout, which INV-10 forbids) → `32 passed in 0.33s`
    The equality at `test_managed_text_failures.py:110` (`request["timeout_seconds"] == 630.0`) catches a shortened attempt only when the clock moves between attempts. Here, `python -c "import time;print(time.get_clock_info('monotonic'))"` prints `resolution=0.015625`, so on Windows the shortened retry still reads exactly 630.0.
    The branch that writes "the SDK did not re-send it, because the call's … s timeout left no time for another attempt" (`vidbyte_gateway.py:80-81`) is never executed by any test. Even so, test-plan.md:20 lists EC-38 as covered by `test_gateway_errors_raise_credential_safe_errors_after_one_post_or_three_for_a_502`.
  Failure: Suppose a later edit drops `or loop.time() + retry_wait >= deadline`, or recomputes `deadline` after attempt 1, or gives each retry only the time left. A slow 502 at the gateway's 600 s deadline then gets two re-sends instead of at most one, and the worst case grows from about 21 to about 32 minutes. A shortened attempt could also time out while the gateway is still finishing a call it bills. All 32 tests stay green either way, and only S064, which is a static pattern check, would notice a missing comparison.
  Smallest fix: Add one test to `test_managed_text_failures.py`. Patch `vidbyte.lib.http.vidbyte_gateway.asyncio` with a namespace whose `get_running_loop()` returns a fake clock and whose `sleep(d)` advances it. Use an inner transport that advances the clock by `step` on each attempt and answers 502. Then assert:
    - step 0: 3 POSTs and waits `[0.5, 1.0]`;
    - step 629.4: 2 POSTs, and the message says "re-sends in this call: 1";
    - step 629.6: 1 POST, and the message says "did not re-send";
    - every attempt records `timeout_seconds == 630.0` while the fake clock has moved.
  My scratch script `fake_clock.py` already does this and shows the current code passes it. Update the test-plan AC-10 row so it stops claiming EC-38.
  Spec IDs: INV-10, INV-16, EC-38, D-10 (r5), §9.2 Retries; AC-27

R-E2 [Major] [test hygiene / money path] tests/test_jev_run_state_relation.py:496-508 — With `VIDBYTE_API_KEY` set in the shell, which is true for every JevAgent developer (EC-27), running the repo's own suite now sends a live, billable POST to the production gateway with the developer's real key. At base, the same code path raised "Missing API key" and sent nothing.
  Evidence: I wrote a scratch plugin, `-p netblock`, that blocks `httpx.AsyncClient.send`, `httpx.Client.send` and `urlopen`, and records each attempted URL.
    `VIDBYTE_API_KEY=vb_live_zzz… python -m pytest -q -p netblock` → `3004 passed, 1 skipped in 17.74s`, with one attempt recorded: `https://vidbyte-backend.onrender.com/api/v1/models/generate  tests/test_jev_run_state_relation.py::JevRunStateRelationRuntimeTests::test_legacy_mode_keeps_per_run_begin_semantics`
    The same test with no key → `1 passed`, and the attempt list is `[]`.
    Captured stack: `agents/base.py:1176 _run_direct → agents/runtime.py:662 → lib/runners/text.py:86 arun → providers/openai.py:30 → lib/http/vidbyte_gateway.py:174 → lib/http/transport.py:70`. So an agent model turn in that test has no scripted runner bound to it.
  Failure: (developer shell has `VIDBYTE_API_KEY=<real key>`, `pytest` runs) → the managed call goes out. It is billed at provider cost plus 2%, with a default 8,192-token cap, on every suite run. This breaks NFR-6 ("no network in tests"). Spec §13's environment-sensitivity note expected only changed outcomes for missing-key assertions, not network I/O. CI is safe only because it sets no key.
  Smallest fix: Bind a `ScriptedGenerativeRunner` to the unbound agent in that test's legacy-mode setup. Alternatively, run the test under `patch.dict(os.environ, {}, clear=True)`, or pop `VIDBYTE_API_KEY`. Spec §14 says "Never modify a test file … stop and report", so the orchestrator must approve this edit. Re-run the `netblock` command and expect `[]`.
  Spec IDs: NFR-6, EC-27, §13 (environment sensitivity)

R-E3 [Minor] [test quality] vidbyte/lib/http/vidbyte_gateway.py:182-190 — Two things in the retry loop are never asserted: that the last attempt's outcome decides the error, and that the message reports the right number of re-sends.
  Evidence: `-p mut_first`, which raises the first attempt's failure and status instead of the last → `32 passed in 0.35s`. `MUT=resends_off_by_one` (`resends = JEV_DEFAULT_RETRY_COUNT - 1`) → `32 passed in 0.32s`. Every mixed script in the pack ends in a 200 (`test_managed_text_failures.py:207+`), and the messages are only checked against `re-?sent|retr` (`:137`, `:200`). Also, `MUT=auto_shape_unchecked`, which deletes the AUTO-state endpoint and provider check in `TextModelConfig.validate()`, → `32 passed`, because the runner's `replace()` → `__post_init__` re-check masks it. A direct `config.validate()` caller has no coverage.
  Failure: Take a 502 followed by a 402. A bug that reports the first answer gives "gateway unavailable (HTTP 502)" instead of the wallet remedy. Or the count goes off by one, and the message says "re-sends in this call: 1" after two re-sends. Callers use that count to decide whether sending a new request risks paying twice (§9.2 row 5, the 409 case).
  Smallest fix: Add these scripts:
    - 502 → 422: expect `status_code == 422`, the 422 remedy and 2 POSTs;
    - 502 → raised `ProviderRequestError(provider="http")`: expect `status_code is None` and the no-response message;
    - 502 three times: expect `re-sends in this call: 2` in the message.
  Also add one direct `TextModelConfig(..., endpoint=…).validate()` assertion under `VIDBYTE_API_KEY`.
  Spec IDs: §9.2 Retries ("the last outcome is raised per its row"), §9.2 rows 3, 5 and 6 ("how many times"), AC-27, EC-7

R-E4 [Minor] [error handling / observability] vidbyte/lib/http/vidbyte_gateway.py:204-205, :84-85 — Row 2 throws away even the exception class. A local programming error, raised before any byte leaves the process, is therefore reported as a possible billing event with nothing to diagnose it.
  Evidence: `except Exception: raised = Exception`. The resulting reason is "the request failed before an answer arrived, and if it reached Vidbyte it may have been billed", with `status_code=None`. `json.dumps(envelope)` runs inside `HttpTransport._send_once` (`vidbyte/lib/http/transport.py:59-62`), so a `bytes`, `datetime` or `Decimal` in `extra_body`, `metadata` or a tool schema raises `TypeError` locally. In BYOK that `TypeError` reaches the developer unchanged. The pack enforces the opaque form: `test_managed_text_failures.py:180` `self.assertNotIn("TypeError", message)`. That goes further than AC-25(a), which forbids the exception's text, not its class name.
  Failure: Example: `extra_body={"metadata": {"t": datetime.now()}}` in managed mode → a provider-shaped error with no status and no type, suggesting a network or billing problem. The developer and the operator cannot tell it apart from a dropped connection.
  Smallest fix: Bind `except Exception as exc` and keep only `type(exc).__name__`, which holds no body text. Put it in the row-2 reason, for example "(TypeError raised before an answer arrived)". Relax the assertion at line 180 to forbid only the exception's message. Confirm that S017 accepts `type(exc).__name__`.
  Spec IDs: AC-25(a), EC-33, §9.2 row 2

R-E5 [Minor] [security / key-crossing] [scope-adding] vidbyte/lib/registries/models.py:162-171 — The spec blesses one configuration for text that still leaks the Vidbyte key from every other modality in the same process.
  Evidence: `OPENAI_API_KEY=vb_live_aaa… python -c "…"` printed:
    `text managed: True adapter key: vidbyte-managed`
    `embedding key is vb_live: True endpoint: https://api.openai.com/v1`
    `image key is vb_live: True endpoint: https://api.openai.com/v1`
  Failure: A developer follows EC-5 and puts their Vidbyte key in `OPENAI_API_KEY`. Text calls are protected, but any embedding, image, video or audio call sends the `vb_live_` key to api.openai.com, a non-Vidbyte host. That is a shorter route to a leaked key than T-3 traces. This PR does not cause it: before the PR, text calls leaked the key too.
  Smallest fix: This is a follow-up for the user. INV-18 deliberately keeps `resolve_api_key` unchanged, so the repair loop does not build it. One option is for `resolve_api_key` to refuse a key that starts with `VIDBYTE_API_KEY_PREFIX` for non-text configs, raising a `ConfigurationError` that names the key-crossing.
  Spec IDs: T-3, INV-6 (text-scoped), INV-18, EC-5

R-E6 [Minor] [failure modes] [scope-adding] vidbyte/lib/http/vidbyte_gateway.py:201 → vidbyte/lib/http/transport.py:46 — The 630 s floor also becomes the TCP connect and pool timeout. An unreachable gateway host can therefore stall a managed call far longer than BYOK's 60 s, although nothing can have been billed before a connection exists.
  Evidence: `transport.py:46` runs `httpx.AsyncClient(timeout=timeout_seconds, …)`. `python -c "import httpx;t=httpx.Timeout(630.0);print(t.connect,t.read,t.write,t.pool)"` prints `630.0 630.0 630.0 630.0`.
  Failure: (gateway host black-holed, or Render down at the TCP level) → each managed call waits until the OS gives up on the connection. That is roughly 21 s on Windows and roughly 127 s with Linux's default SYN retries, so the 630 s ceiling is not the usual bound. The call then raises row 1, "Vidbyte may already have billed the call", which is wrong here, because no request was sent. This partly corrects the earlier committed version of this report, which said 10.5 minutes.
  Smallest fix: This is a follow-up and outside §12.3. One option is for the decorator to pass a split timeout, with a short connect phase and 630 s for read, through a new `HttpTransport` option.
  Spec IDs: INV-10 (per-attempt floor), EC-26

R-E7 [Minor] [observability] [scope-adding] vidbyte/lib/http/vidbyte_gateway.py:174-190 — Same-key re-sends of a call that may already be billed leave nothing an operator can use. A success after retries looks identical to a first-try success, and a failure carries no `Idempotency-Key` to match against the backend's replay and claim rows.
  Evidence: the method returns `answer.response` unchanged and writes no log line. The raised message includes only the re-send count, and `idempotency_key` is local to `request`.
  Failure: (a support ticket reports "billed but got an error") → no SDK-side identifier links the client error to the gateway's claim and replay records, which are keyed by (user, API key, key value).
  Smallest fix: This is a follow-up. One option is to add the per-call `Idempotency-Key` to the managed error's `details`. It is an owner-scoped random token, not a credential.
  Spec IDs: INV-11, T-4

VERIFIED CLAIMS
- Orchestrator/S3 "pack 32 passed": held. `32 passed in 0.94s`.
- Orchestrator/S3 "full suite 3004 passed, 1 skipped": held. Also held with `VIDBYTE_API_KEY` set and the network blocked: `3004 passed, 1 skipped in 17.74s`. That run is what exposed R-E2.
- S3 lint figures (C017 0, C018 1, C019 0, C020 2, S064 4, `SDK-LINT: PASS`): held. I re-ran them, and S002 0, S008 19 and S009 345 ≤ 350 also held.
- AC-19, production `.py` only under `vidbyte/lib/`: held. `git diff --name-only origin/main...a80f0660` lists 9 production files, all under `vidbyte/lib/`.
- S3 "option A as built": the cumulative deadline, a worst case of about 2× the timeout, a slow 502 re-sent at most once, and "did not re-send" at 629.6 s. Held in my own fake-clock run, with the same numbers as the S3 scratch check.
- §9.2 "inner retry_count left at 0": held. No `retry_count` is passed, `HttpTransport.request` defaults to 0, and the `inner_retry` mutation fails 6 tests.
- INV-16 "one key and one envelope per call": held. The fake clock showed `keys=1` across 3 POSTs, and the `fresh_key_per_attempt` mutation fails 4 tests.
- INV-10 NaN → 630, floor first: held. The `nan_floor_order` mutation fails 1 test.
- INV-15, no markup constant in the SDK: held. Grepping the code diff for markup, basis points, bps, 0.02, fee, price or cost finds only the 422 message text.
- Test plan "AC-10 row covers EC-38": did not hold (R-E1).
- Spec NFR-6 "no network in tests", and the §13 note that only outcomes change when a key is set: did not hold on a machine with `VIDBYTE_API_KEY` set (R-E2).
- Test plan, implicitly "every plausible bug is caught by some test": 6 of 21 mutations survived (`no_deadline`, `deadline_gt`, `deadline_after_first`, `shorten_attempt` on Windows, `resends_off_by_one`, `mut_first`; also `auto_shape_unchecked` and `follow_redirects`). These were caught: `retry_503`, `retry_network`, `error_truthy`, `inner_retry`, `fresh_key_per_attempt`, `succeeded_ignores_body`, `row1_as_row2`, `no_placeholder`, `nan_floor_order`, `runner_key_placeholder`, `fallthrough_any_provider`, `env_vb_not_managed`, `no_429_remedy_split`. Note on `follow_redirects`: httpx drops `Authorization` on cross-origin redirects, so that surviving mutation is not reported.

COMMANDS RUN
- `git diff --stat origin/main...a80f0660` → `31 files changed, 4671 insertions(+), 21 deletions(-)`
- `git diff --name-only origin/main...a80f0660 | grep "\.py$"` → 5 test files and 9 `vidbyte/lib/**` files
- `PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` → `32 passed in 0.94s`
- `PYTHONPATH=$(pwd) timeout 580 python lint/run.py` → `C017 0 0 CLEAN`, `C018 1 1 RATCHETED`, `C020 2 2 RATCHETED`, `S064 4 4 RATCHETED`, `S002 0 0 CLEAN`, `SDK-LINT: PASS` (`git status --short` empty before and after)
- `MUT=<id> PYTHONPATH="$(pwd);<scratch>" python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider -p mutplug`, for 19 mutation ids → survivors: `no_deadline`, `deadline_gt`, `deadline_after_first`, `resends_off_by_one`, `shorten_attempt`, `auto_shape_unchecked` and `follow_redirects` (each `32 passed`). Every other id gave 1 to 8 failures.
- `PYTHONPATH="$(pwd);<scratch>" python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider -p mut_first` → `32 passed in 0.35s`
- `PYTHONPATH=$(pwd) python <scratch>/fake_clock.py` → `step=0.0 POSTs=3 elapsed=1.5 keys=1 … (re-sends in this call: 2)`; `step=629.4 POSTs=2 elapsed=1259.3 … (re-sends in this call: 1)`; `step=629.6 POSTs=1 … did not re-send it, because the call's 630 s timeout left no time for another attempt`; `502→422: POSTs=2 … the 422 remedy`
- `python -c "import time;print(time.get_clock_info('monotonic'))"` → `resolution=0.015625`
- `NETBLOCK_OUT=… VIDBYTE_API_KEY=vb_live_z… PYTHONPATH="$(pwd);<scratch>" python -m pytest -q -p no:cacheprovider -p netblock --tb=no -rf` → `3004 passed, 1 skipped in 17.74s`; one blocked attempt: `…/api/v1/models/generate tests/test_jev_run_state_relation.py::…::test_legacy_mode_keeps_per_run_begin_semantics`
- The same test without the key, `-p netblock` → `1 passed in 0.89s`, attempts `[]`. With the key and `-p netstack`, the stack ends `text.py:86 → openai.py:30 → vidbyte_gateway.py:174 → transport.py:70`.
- `OPENAI_API_KEY=vb_live_a… PYTHONPATH=$(pwd) python -c "…EmbeddingModelConfig/ImageModelConfig…"` → `embedding key is vb_live: True endpoint: https://api.openai.com/v1`

All scratch files (`mutplug.py`, `mut_first.py`, `fake_clock.py`, `netblock.py`, `netstack.py`) are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/89243902-3a54-44fb-81e0-5240b0f89dfc/scratchpad/s4eng/`, outside the worktree. No worktree file other than this report was written.
