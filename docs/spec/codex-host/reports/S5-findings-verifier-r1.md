# S5 findings verifier, round 1: codex-host

Scope: the findings verifier after the S5 conformance re-review, round 1 of 2. Code under review: `feat/codex-host` at bbaa5a8b. Local HEAD a9daa401 adds only docs: `git diff --stat bbaa5a8b HEAD -- vidbyte tests lint pyproject.toml` prints nothing. There is one input, reports/S5-rereview.md (R-C1..R-C4); the other two review slots are `n/a` for this scoped round. Output: review.md rows R-26..R-29, with an updated verdict and a round line. Rows R-1..R-25 are byte-identical; an md5 of each `| R-n |` line matches HEAD for n = 1..25.

Verdict: MERGEABLE AFTER FIXES. Confirmed: 0 Blocker, 2 Major (R-26, R-27), 2 Minor (R-28, R-29). Refuted: 0. Downgraded: 0. Sub-claims trimmed: 3.

All probes live in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/codex-verifier-r1/` ($S below):
- `probe_rc1.py`
- `probe_rc2.py`
- `rc2_fixed.py`
- `pack_with_variant.py`

Every fix candidate was compiled from the module's own source text into the real module namespace, in memory, and undone afterwards. `git status --short` was empty after every run.

## Merge map

| Original | Merged | Severity (proposed → final) | Notes |
|---|---|---|---|
| R-C2 | R-26 | Major → Major | Ordered first in the tier because its fix is one line. |
| R-C1 | R-27 | Major → Major | Its fix touches one attribute, one method and two call sites. |
| R-C3 | R-28 | Minor → Minor | trivial |
| R-C4 | R-29 | Minor → Minor | trivial, spec-change |

There were no merges. The four findings sit on four different lines and have four different failures.

## Verifications

### R-C1 → R-27 (CONFIRMED, Major)

**Code at bbaa5a8b.**
- host.py:407 reads `if turn.snapshot is not None or turn.stop_sent: return`, and host.py:409 sets `turn.stop_sent = True` before the await at :410.
- `stop_sent` is set at turns.py:87 (`False`), :173 (`stop()`) and host.py:409. It is never reset.
- It also gates `over_cap()` (turns.py:133) and `stop()` (turns.py:171).
- R-16's commit 7d4c21fa changed exactly that guard line, from `if turn.snapshot is not None:`.

**Spec reading.**
- §9.2 row (spec.md:876): "Nothing is sent when the turn has already finished."
- AC-16 (spec.md:387): given "A running turn", "One `turn/interrupt` is sent".
- EC-25 (spec.md:438): the no-op applies to "interrupt on a finished turn".
- EC-27 (spec.md:440): a failed timeout interrupt "is not retried, and the turn continues".
- D-7 (spec.md:585): "failed interrupts are not retried".

None of these lets the host drop the caller's own interrupt of a running turn after an earlier stop ended. R-16's own row covers only a stop that "is still in flight". So the finding reads the spec correctly.

**Existing guard?** None. No other path resets `stop_sent` or sends an interrupt for a running turn. The timeout timer fires once, and `over_cap()` returns False once `stop_sent` is set.

**Own probe.** `$S/probe_rc1.py` is a HostTestCase with `CODEX_HOST_WORKER_THREADS=1`, over the fake. Command:

```
VARIANT=<v> PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$W;$S" $PY -P -m unittest probe_rc1
```

Output for `current`, the code under review:
```
[current] A: first user interrupt raised codex.api_error; next_step='Retry with backoff, and check the service status if it persists.'
[current] A: turn/interrupt sent after first call: 1
[current] A: retry returned None; turn/interrupt sent after retry: 1; turn: inProgress problem=None
[current] B: timeout interrupts sent: 1; turn: inProgress problem=None
[current] B: user interrupt returned None; turn/interrupt sent: 1; turn: inProgress problem=None
[current] C: cap interrupts sent (after a 2nd crossing): 1; turn: inProgress problem=None
[current] C: user interrupt returned None; turn/interrupt sent: 1; turn: inProgress problem=None
[current] D: while the timeout interrupt is held: user call done=True; turn/interrupt sent: 1
[current] D: user call returned None; turn/interrupt sent in all: 1; turn: interrupted problem=codex.turn_timed_out
[current] E: second call done while first held=True; turn/interrupt sent: 1
[current] E: second returned None; turn/interrupt sent in all: 1; turn: interrupted problem=None
[current] F: AC-16: interrupts=1 status=interrupted problem=None; finished-turn interrupt sent nothing more: True
```

Output for `revert`, with host.py:407 set to `if turn.snapshot is not None:` in memory:
```
[revert] A: retry returned None; turn/interrupt sent after retry: 2; turn: interrupted problem=None
[revert] B: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.turn_timed_out
[revert] C: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.budget_exhausted
[revert] D: while the timeout interrupt is held: user call done=False; turn/interrupt sent: 1
[revert] D: user call returned None; turn/interrupt sent in all: 2; turn: interrupted problem=codex.turn_timed_out
[revert] E: second returned None; turn/interrupt sent in all: 2; turn: interrupted problem=None
[revert] F: AC-16: interrupts=1 status=interrupted problem=None; finished-turn interrupt sent nothing more: True
```

Output for `pending`, the re-reviewer's `stop_pending` fix as R-27 specifies it, in memory:
```
[pending] A: retry returned None; turn/interrupt sent after retry: 2; turn: interrupted problem=None
[pending] B: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.turn_timed_out
[pending] C: user interrupt returned None; turn/interrupt sent: 2; turn: interrupted problem=codex.budget_exhausted
[pending] D: while the timeout interrupt is held: user call done=True; turn/interrupt sent: 1
[pending] D: user call returned None; turn/interrupt sent in all: 1; turn: interrupted problem=codex.turn_timed_out
[pending] E: second call done while first held=True; turn/interrupt sent: 1
[pending] E: second returned None; turn/interrupt sent in all: 1; turn: interrupted problem=None
[pending] F: AC-16: interrupts=1 status=interrupted problem=None; finished-turn interrupt sent nothing more: True
```

**Pack under each fix, in memory** (`$PY -P $S/pack_with_variant.py $W`, with `RC2FIX=1` as well):
```
111 passed in 6.18s   VARIANT=current RC2FIX=1 pytest exit=0
111 passed in 6.28s   VARIANT=revert  RC2FIX=1 pytest exit=0
111 passed in 6.28s   VARIANT=pending RC2FIX=1 pytest exit=0
```
No existing test pins R-16's in-flight behaviour: the revert passes, so nothing would catch a regression of D or E.

**Calibration.** Major, not Blocker. The trigger needs an earlier interrupt to have failed, which is rare. The effect, a paid turn that keeps running with no working stop short of close, matches S4's R-6, which was rated Major. No AGENTS.md rule, field-guide lesson or weighted word is broken; see the trimmed INV-8 cite below.

### R-C2 → R-26 (CONFIRMED, Major)

**Code at bbaa5a8b.** wire.py:262 reads `raise ConfigurationError(f"{UNUSABLE_SCHEMA_MESSAGE} {exc}") from exc`. It came in with R-2 at 6856645b.

**Spec reading.**
- INV-9 (spec.md:246-248): "Messages carry only Codex's own error message, the method, the JSON-RPC code, or an exception's type name."
- §12.3 row 10 (spec.md:1255): "No message includes … any `str(exc)`, `repr(exc)` or `f"{exc}"` … Every caller raises the mapped error `from None`, never `from exc`".
- §12.4 (spec.md:1330): "**No exception text in harness errors.** … S017's scan covers `vidbyte/tools/` but not `vidbyte/harnesses/`, so review holds this rule there."
- The lint rule confirms the gap. `lint/rules/s017_no_raw_exception_disclosure.py:22` has `SCOPED_PREFIXES = ("vidbyte/providers/", "vidbyte/tools/", "vidbyte/mcp_server/", "vidbyte/lib/runners/")`.

**Consistency.** I ran `git grep -n "from exc\|from None\|{exc\|str(exc\|repr(exc\|type(exc)" bbaa5a8b -- vidbyte/harnesses/native/codex …`.
- Every other raise in the package is `from None` (connection.py:163, :188, :242; host.py:158, :453).
- errors.py:117 builds `f"{method} failed with {type(exc).__name__}."`.
- wire.py:262 is the only `{exc}` and the only `from exc`.

**Own probe.** `$S/probe_rc2.py`, run with `PYTHONPATH="$W;$S" $PY -P -m unittest probe_rc2`:
```
[object() value] ConfigurationError message="output_schema must be a Pydantic model type or a mapping that serializes to JSON. Unable to serialize unknown type: <class 'object'>"
[object() value] __cause__=PydanticSerializationError suppress_context=True requests_sent=[]
[cyclic mapping] ConfigurationError message='output_schema must be a Pydantic model type or a mapping that serializes to JSON. Circular reference detected (id repeated)'
[cyclic mapping] __cause__=ValueError suppress_context=True requests_sent=[]
[dataclass type] ConfigurationError message="output_schema must be a Pydantic BaseModel subclass or a dict, got 'type'."
[dataclass type] __cause__=None suppress_context=False requests_sent=[]
[model with no JSON schema] ConfigurationError message="output_schema must be a Pydantic model type or a mapping that serializes to JSON. Cannot generate a JsonSchema for core_schema.IsInstanceSchema (<class 'probe_rc2._Opaque'>)\n\nFor further information visit https://errors.pydantic.dev/2.14/u/invalid-for-json-schema"
[model with no JSON schema] __cause__=PydanticInvalidForJsonSchema suppress_context=True requests_sent=[]
[tool] status=ToolStatus.ERROR output="configuration.invalid_argument: output_schema must be a Pydantic model type or a mapping that serializes to JSON. Unable to serialize unknown type: <class 'object'> Next step: Fix the argument or setup named in the message, then call again."
```

The dataclass type never reaches wire.py:262. `OutputSchemaFormatter.resolve_schema` (providers/output_schema.py:62) raises its own fixed-text `ConfigurationError`, which the `except (PydanticUserError, TypeError, ValueError)` clause does not catch. Only mappings and Pydantic models with no JSON schema break the rule.

**Fix, in memory.** `$S/rc2_fixed.py` swaps in `… Got {type(exc).__name__}.") from None`:
```
[object() value] … message='output_schema must be a Pydantic model type or a mapping that serializes to JSON. Got PydanticSerializationError.'  __cause__=None
[cyclic mapping] … 'Got ValueError.'  __cause__=None
[model with no JSON schema] … 'Got PydanticInvalidForJsonSchema.'  __cause__=None
[tool] … 'configuration.invalid_argument: output_schema must be … JSON. Got PydanticSerializationError. Next step: …'
```
The pack passes 111/111 with it, as shown under R-27. The existing R-2 test asserts only `assertIn("output_schema", str(caught.exception))` (test_codex_host_review_gaps.py:93), so it passes before and after. Its `UNUSABLE_SCHEMAS` mapping case (`{"properties": {"summary": object()}}`) does reach wire.py:262. So `assertIsNone(caught.exception.__cause__)` fails today and passes after the fix, which makes it a real regression test.

**Calibration.** Major. INV-9 and the §12.4 review-held rule are spec invariants, and a human reviewer who knows S017 would comment on this. No field guide forbids it (I grepped `field-guide/vidbyte-sdk/*.md` for exception text and `from None`), and INV-9 is not among the weighted words, so it is not a Blocker.

### R-C3 → R-28 (CONFIRMED, Minor, trivial)

The texts at bbaa5a8b are descriptions.py:60 and :61. Probe output:
```
ConfigurationError Codex review target baseBranch needs branch; got empty [] and unused ['title'].
ConfigurationError Codex review target commit needs sha; got empty [] and unused ['instructions'].
ConfigurationError Codex review target uncommittedChanges needs no fields; got empty [] and unused ['title'].
ok {'kind': <CodexReviewTargetKind.COMMIT: 'commit'>, 'sha': 'abc', 'title': 't'}
```

The tool really hits this. `StartCodexReviewTool` passes `title=self._resolve_text(call, "title")` and `instructions=…` straight into `CodexReviewTarget` (delegation.py:116-121), so a title sent with a base-branch review returns `configuration.invalid_argument`.

The fix keeps S025 satisfied. `SentenceCounter` reports `title now 4 after 4` and `instructions now 4 after 4`, and S025's `MINIMUM_SENTENCES = 4`. `grep -rn "used only when\|TITLE_DESCRIPTION\|INSTRUCTIONS_DESCRIPTION" tests/` finds nothing, so no test pins the old text.

### R-C4 → R-29 (CONFIRMED, Minor, trivial, spec-change)

Each of the 11 names occurs 0 times in spec.md (`grep -c`). `CODEX_THREAD_START_METHOD` also occurs 0 times, but it is on main and is not new. §9.3 (spec.md:1039) lists only the 5 raw-method names. Row 4(b) is at spec.md:1249.

Line correction: at bbaa5a8b the constants are at constants/codex.py:446-457, with their comment at :443-445. The re-reviewer cited :441-455. The code needs no change.

## Adjudications

1. **The fix for R-27.**
   - The briefing offered three options: `stop_pending`, the revert, or something smaller.
   - Nothing smaller than the revert fixes cases B and C. D-7 needs `stop_sent` to stay True after a failed Vidbyte stop: probe C shows that a second cap crossing must send nothing. So the interrupt guard has to tell "in flight" from "ended". That needs either new state or no guard at all.
   - The revert is smaller, but it re-opens R-16. D and E then send 2, and R-16's immutable row still says "fixed @7d4c21fa".
   - I made `stop_pending` the recommended fix. It is the smallest fix that closes R-C1 without regressing a confirmed finding, and I checked it on all six probe cases and the full pack.
   - I kept the revert as the stated smaller alternative, with what it costs.
   - `stop()` is synchronous and spawns its interrupt, so a `finally` that clears the flag needs an async method. Without one, case B stays broken. Hence one method, and no closure (AGENTS.md principle 1 forbids nested functions).
2. **Order inside the Major tier.** Smaller fix first: R-26 (one line), then R-27.
3. **Three sub-claims trimmed** (review.md refuted table):
   - R-C1's INV-8 and weighted-word cite: INV-8 holds, because no foreign exception escapes.
   - R-C1's "nothing else can stop the turn": this is D-7 and EC-27 as written, not a second defect.
   - R-C2's INV-8 and EC-82 cites: both hold. The probe shows `requests_sent=[]` and an error message that names `output_schema`.
4. **The case B label is spec-literal.** After a failed timeout interrupt, a later successful user interrupt ends the turn `interrupted` with `codex.turn_timed_out`. That holds under both fixes. EC-27 says "no `turn_timed_out` label unless the turn ended interrupted", and D-7 says the first stop reason wins. This is not a finding. A regression test must assert this label, not `None`.

## Blind-spot pass over the 18 repair commits (2f098372..08d498d8)

I read each fix diff with `git show <sha> -- vidbyte`, plus the current code around it. No new Blocker or Major was found, so no `[verifier]` row was added.

| Commit | Row | What I checked | Result |
|---|---|---|---|
| 2f098372 + 846ce849 | R-1 | `_accept_review` (host.py:662-698): the `except BaseException` arm watches, stops, then re-raises. `suppress(CodexAgentError)` now wraps `require_thread`, so a failed read finds nothing stored, as before. | holds |
| 6856645b | R-2 | Refusal before preflight in spawn (host.py:254), continue (:277) and launch (:438). The tool continue path inherits `spawn_defaults.output_schema` through `_continue_defaults`, so R-26's fix covers it too. | R-26 |
| 8f6975e8 | R-3 | Enum conversions at turns.py:229 and connection.py:212. openai-codex is pinned `>=0.162.1,<0.163.0` (pyproject.toml:43), and the SDK validates the status as its own enum first, so `CodexGoalStatus(...)` cannot meet an unknown value under the pin. | holds |
| 846ce849 | R-4 | `stop` sits on `CodexLiveTurn`. R-27's recommended `send_stop` keeps the chain at stop → send_stop → connection.interrupt (another class), one level. | holds; constrains R-27 |
| 08d498d8 | R-5 | comments only (re-reviewer's count: 0 of 729 over 72) | holds |
| 4d597f91 | R-6 | `except BaseException` re-raises every non-`CodexAgentError`, so cancellation propagates. Field guide provider-api-contracts.md:12 ("Never catch BaseException, so cancellation propagates") targets provider adapters, and its intent is kept here. The launch message says "were interrupted" even when a quiet interrupt fails; that is EC-52's wording from before the repair. | holds; not raised |
| 52e9e313 | R-7 | `finally` closes the goal streams and the client. The connection's own `finally` shuts the executor down. | holds |
| f2e9db7e | R-8 | `_reject_small_int` and `_reject_bad_seconds` return on `None` (codex_host.py:60, :69), so `limit=None` and `timeout_seconds=None` still pass. | holds |
| fad8c55f | R-9 | `# @intent` added only | holds |
| 874bd5a3 | R-10 | `_starting` is added only when `future.cancel()` is False and is discarded in `_land` on the loop. If the loop is already closed, the post is suppressed and the thread stays marked, but the host is closed by then. | holds |
| 528e5ef6 | R-11 | constants only; spec record → R-29 | R-29 |
| 4a9ecc49 | R-12 | description and docstring text (re-reviewer's claim 14) | holds |
| d894d87a, 168282f4 | R-13, R-14 | tests only, granted file | holds |
| 1169ad68 | R-15 | two of four descriptions; the other two → R-28 | R-28 |
| 7d4c21fa | R-16 | the guard over-reaches | R-27 |
| 9dee1619 | R-17 | `finally` runs `finish()` and `unregister_goal_operation` | holds |
| 4e222e3c | R-18 | keyword arguments and `if`/`elif` | holds |

**Considered and not raised.**
- **A failed user interrupt turns off the timeout and the cap.** It leaves `stop_sent=True`, so the timeout and the cap stay off for that turn. Two reasons this is not a finding:
  - This predates R-16. At 099fac83, host.py also set `stop_sent = True` before the await.
  - It is consistent with D-7 ("first stop wins") and D-35. With either R-27 fix, the caller can retry, so the turn is never left unstoppable.
- **A user interrupt still raises while a stop is in flight.** Under the recommended fix, if the user's own interrupt is in flight and its caller is cancelled, `finally` clears `stop_pending` while the request may still be running on the worker. A new user call would then send a second interrupt. The window is narrow, and the outcome is the pre-R-16 behaviour, so this is not a finding.

## Notes for repair iteration 2

- **R-26.** Change one line at wire.py:262. Add `self.assertIsNone(caught.exception.__cause__)` inside the existing `with self.subTest(...)` block of `CodexHostOutputSchemaRefusalTests`. Reproduce with `$S/probe_rc2.py`.
- **R-27, recommended fix.**
  - Touch turns.py:87 (the attribute), turns.py:165-175 (`stop()` spawns `self.send_stop(...)`), a new `async def send_stop` on `CodexLiveTurn`, and host.py:400-410.
  - `send_stop` contains "send", so A002 requires an `# @intent <name>` line within 20 lines of the `def` (spec §12.4, "A002 `# @intent` lines").
  - Wrap comments at 72 columns, counting the indent (field guide comment-format.md).
  - Update host.py's narration at :401-403, which says "or one already sent its one stop, gets nothing".
  - Do not touch `over_cap()` or `stop()`'s `stop_sent` check.
- **Regression tests for R-27, in test_codex_host_review_gaps.py:**
  - A, with `server.fail("turn/interrupt", FakeRpcError(-32603, …), times=1)` on a plain spawn: the first call gives `codex.api_error`, the retry sends a 2nd `turn/interrupt`, and the turn ends INTERRUPTED with problem None.
  - B, with `timeout_seconds=0.2` and the interrupt failing once, then a user interrupt: 2 interrupts, ending INTERRUPTED with `codex.turn_timed_out`.
  - D, with `server.hold("turn/interrupt")` on the timeout's interrupt and a user interrupt while it is held: 1 interrupt in all.
  - Use the pack's one-worker barrier (`patch_connection("CODEX_HOST_WORKER_THREADS", 1)`, then `read_codex_thread`) before counting.
- **Shared line.** R-24, the open M5 test gap, sits on the same `interrupt_codex_turn` lines. Keep `turn.stop_sent = True` on the user path.
- **R-28** is two string edits. **R-29** goes to the spec author: one §9.3 row.

## Commands run

- `git log --oneline -5`; `git status --short` (clean throughout); `git diff --stat bbaa5a8b HEAD -- vidbyte tests lint pyproject.toml` (empty).
- `git show bbaa5a8b:<path>` for host.py, turns.py, connection.py, wire.py, descriptions.py and constants/codex.py; `git show <sha> -- vidbyte` for 4d597f91, 874bd5a3, 52e9e313, 2f098372, 9dee1619, 6856645b, f2e9db7e, 7d4c21fa and 1169ad68.
- `git grep -n "from exc\|from None\|{exc\|str(exc\|repr(exc\|type(exc)" bbaa5a8b -- vidbyte/harnesses/native/codex vidbyte/tools/builtins/codex vidbyte/lib/dataclasses/codex_host.py vidbyte/agents/codex`
- The pack at HEAD: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `111 passed in 7.09s`
- `VARIANT={current,revert,pending} … -m unittest probe_rc1` → the output quoted under R-27
- `VARIANT={current,revert,pending} RC2FIX=1 $PY -P $S/pack_with_variant.py $W` → `111 passed` ×3
- `… -m unittest probe_rc2` and `$PY -P $S/rc2_fixed.py` → the output quoted under R-26
- `CodexReviewTarget` probe and `SentenceCounter` check via `$PY -P -c` → the output quoted under R-28
- `grep -c <name> docs/spec/codex-host/spec.md` for the 12 method constants → all 0

Here `W=C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host` and `PY=C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python.exe` (openai-codex 0.162.1).
