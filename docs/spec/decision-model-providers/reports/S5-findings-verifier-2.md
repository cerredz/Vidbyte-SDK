# S5 findings verifier (after re-review round 1): decision-model-providers

Scope: the scoped run after S5 repair iteration 1. One review this round, `reports/S5-rereview.md` (conformance lens). The other two review slots are "none this round". Code reviewed: `7ee8ebbd`. Local HEAD moved to `44dc3faf` while I worked (the spec author's R-C2 commit). `git diff 7ee8ebbd HEAD --stat -- vidbyte tests lint REPO_MAP.md` is empty, so the code under review is unchanged. Comparison base: origin/main `097eba9b`. `git diff 7be96284 origin/main` (the merge base) is empty for `vidbyte/providers/typesafe.py`, `vidbyte/lib/dataclasses/model_configs.py` and `vidbyte/lib/runners/decision.py`, so the comparison holds against both.

Result: R-C1 is **CONFIRMED (Major)** and becomes R-18. R-C2 passes through as Minor R-19 (`trivial`, spec-only). Refuted: 0. Downgraded: 0. Rows R-1 to R-17 and the refuted R-5 row are unchanged.

## Merge map

| Original | Lens | Proposed severity | Merged ID | Disposition |
|---|---|---|---|---|
| R-C1 (S5-rereview) | conformance | Major | R-18 | CONFIRMED, Major kept |
| R-C2 (S5-rereview) | conformance (deviations) | Minor | R-19 | passed through, tagged `trivial`; status "spec-only; spec author" |

There were no duplicates to group, because only one review ran. No existing row was renumbered or re-verified.

## R-C1 → R-18: verification

**Claim.** At `vidbyte/lib/dataclasses/jev.py:525`, `DecisionHttpCall.__post_init__` refuses `int` and `float` subclass timeouts. Spec row 5 admits them. TypeSafe decisions with such a timeout worked on origin/main and now fail (INV-23).

**1. The code (read at 7ee8ebbd, lines 524-526).**
```
        # An exact int or float type keeps True (a bool, which is an int subclass) out of the timeout.
        if type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= JEV_TIMEOUT_FLOOR_SECONDS:
            raise JevValidation.error("decision call timeout_seconds", "a finite number of seconds greater than 0", self.timeout_seconds)
```
`type(x) not in (int, float)` is True for any subclass instance, so the check refuses every subclass. This is the only exact-type check in the diff: `git diff origin/main...7ee8ebbd -- vidbyte | grep -nE '^\+.*\btype\([^)]*\) *(is|not in|in|==|!=)'` returns only this line.

**2. The spec reading.** Spec r11 §12.3 row 5, rule (3): "`timeout_seconds` that is a `bool`, is not an `int` or `float`, is not finite (`math.isfinite`), or is `<= JEV_TIMEOUT_FLOOR_SECONDS` (0.0)". I read "is not an `int` or `float`" as `isinstance` does, for three reasons:
- Rule 3 gives `bool` its own clause. That clause is needed only under `isinstance` semantics. Under exact-type semantics `bool` is already "not an `int` or `float`".
- Rule (5) in the same row uses the same words ("a `bool`, is not an `int`, or is `< JEV_NO_RETRIES`"). It is implemented by `JevCount.require` (`jev.py:4164`: `isinstance(value, bool) or not isinstance(value, int) or value < minimum`), which admits `int` subclasses. Rules 1, 2 and 6 ("not a non-blank `str`") are implemented with `isinstance(..., str)` (`jev.py:520,522,530`), which admits `str` subclasses.
- The repo does the same elsewhere. In the same module, `JevProbability.require` (`jev.py:221`) uses `isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)`. `JevAgentSettings._validate_timeout` (`vidbyte/agents/jev/settings.py:193`) uses `isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0`.

Spec §17 "Implementation deviations" (items 1-8, spec.md:914-923) has no entry for subclass refusal. The briefing's decisions sanction refusing `bool`, `inf` and `nan`, but not subclasses. request.md §C declines nothing relevant here.

**3. Is there an upstream guard?** No.
- `DecisionModelConfig.__post_init__` (`vidbyte/lib/dataclasses/model_configs.py:387`) runs `if not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= JEV_TIMEOUT_FLOOR_SECONDS`. That admits subclasses, and it neither coerces nor replaces the value. The same line is at :371 on origin/main.
- The value reaches the record unchanged at `typesafe.py:111,115,122`, `systemone.py:327` and `openai_decisions.py:316` (`timeout_seconds=config.timeout_seconds`).
- The JevAgent path passes the user's `DecisionModelConfig` through. `JevAgentSettings.timeout_seconds` is the generative-model timeout (`agent.py:67,98`), not the decision timeout.
- `HttpTransport.request` (`vidbyte/lib/http/transport.py:46`) hands the timeout to `httpx.AsyncClient(timeout=...)` without a type check.

**4. Execution: my own probe.** I wrote `rc1_probe.py` in the scratchpad, with `class Seconds(float)` and `class WholeSeconds(int)`. I ran it with `PYTHONPATH` set to each tree: the worktree (7ee8ebbd code), `git archive origin/main vidbyte` extracted to the scratchpad, and a patched copy (step 6). Each run printed the `vidbyte.__file__` it imported, to show which tree it used.
```
=== NEW (7ee8ebbd code) ===
-- builder: _TypeSafeCallBuilder(HttpResponseParser()).decision(cfg, req)
   float 30.0             -> call built; timeout 30.0 (float)
   int 30                 -> call built; timeout 30 (int)
   Seconds(30.0)          -> ConfigurationError: Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received Seconds 30.0.
   WholeSeconds(30)       -> ConfigurationError: Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received WholeSeconds 30.
   numpy.float64(30.0)    -> ConfigurationError: Invalid Jev decision call timeout_seconds: expected a finite number of seconds greater than 0; received float64 np.float64(30.0).
-- runner: DecisionModelRunner(cfg, transport=scripted).arun(req)
   typesafe direct    Seconds(30.0)      -> ConfigurationError: ... received Seconds 30.0. | requests sent: 0
   typesafe direct    WholeSeconds(30)   -> ConfigurationError: ... received WholeSeconds 30. | requests sent: 0
   perplexity direct  Seconds(30.0)      -> ConfigurationError: ... | requests sent: 0
   openai direct      Seconds(30.0)      -> ConfigurationError: ... | requests sent: 0
=== ORIGIN/MAIN 097eba9b ===
   Seconds(30.0)          -> call built; timeout 30.0 (Seconds)
   WholeSeconds(30)       -> call built; timeout 30 (WholeSeconds)
   numpy.float64(30.0)    -> call built; timeout np.float64(30.0) (float64)
   typesafe direct    Seconds(30.0)      -> ok; sent 1 request(s), timeout passed 30.0
   typesafe direct    WholeSeconds(30)   -> ok; sent 1 request(s), timeout passed 30
```
A managed-mode probe (`rc1_managed.py`, timeout `Seconds(30.0)`; the `VIDBYTE_MANAGED` key is `vb_live_` plus 32 characters):
```
[new]  typesafe         arun          -> ConfigurationError: ... received Seconds 30.0. | requests sent 0
[new]  typesafe         alist_models  -> ConfigurationError: ... | requests sent 0
[new]  vidbyte_managed  arun          -> ConfigurationError: ... | requests sent 0
[new]  vidbyte_managed  alist_models  -> ConfigurationError: ... | requests sent 0
[main] typesafe         arun          -> ok; requests sent 1
[main] vidbyte_managed  arun          -> ok; requests sent 1
[main] typesafe / vidbyte_managed alist_models -> requests sent 1 (then ProviderResponseError from my
       scripted models body's shape; the same on main and on the fixed copy, so it does not bear on the finding)
```
INV-23 (spec.md:200) requires the TypeSafe transport kwargs and behaviour to stay byte-identical. The output above shows a TypeSafe call that was sent on origin/main and is not sent at 7ee8ebbd. The control rows (`float 30.0`, `int 30`) are unchanged, and `bool`, `inf` and `nan` are rejected as row 5 sanctions.

**5. Classification: CONFIRMED, Major.** Real and reproduced. It breaks INV-23 on one input class and goes beyond row 5. It is not recorded as a deviation. A reviewer would flag it, because `type(x) not in (...)` where `isinstance` is meant is a standard review comment. It is not a Blocker for three reasons. The failure is loud. It happens before any request, so there is no charge and no silent wrong result. And it needs an uncommon input type: a float or int subclass such as `numpy.float64`.

**6. Checking the smallest fix.** I copied `vidbyte/`, `tests/`, `lint/` and `pyproject.toml` to the scratchpad (`fixed_tree`). I applied the re-reviewer's fix to `jev.py:524-525` with CRLF kept; `diff` shows exactly those 2 lines.
- The probe on the fixed copy: `Seconds(30.0)`, `WholeSeconds(30)` and `numpy.float64(30.0)` give `call built`. All 6 runner rows (TypeSafe, Perplexity and OpenAI, each with `Seconds` and `WholeSeconds`) give `ok; sent 1 request(s)`. `bool True`, `float inf` and `float nan` still give the exact AC-23 messages, for example `... received bool True.`.
- `python -m pytest -p no:cacheprovider tests/features/decision_model_providers <10 area files> -q` on the fixed copy gives `496 passed in 3.08s` (90 + 406).
- Lint, in process: `lint_patched.py` monkeypatches `SourceCatalog._build` so that it returns the patched `jev.py` text in memory. Nothing is written to the worktree. Then it calls `lint.run.main([])` against the worktree.
  - Spelling `type(self.timeout_seconds) is bool or not isinstance(self.timeout_seconds, (int, float))` gives `C002 duplicate-inline-bool-guard-validation 9 9 RATCHETED`, `SDK-LINT: PASS` and exit 0.
  - Spelling `isinstance(self.timeout_seconds, bool) or not isinstance(...)` gives `C002 10 9 REGRESSED` and exit 1: "vidbyte/lib/dataclasses/jev.py:525 validates 'timeout_seconds' with isinstance(..., bool), and the same meaningful identity is guarded elsewhere: vidbyte/workflows/contracts.py:149 (__post_init__), vidbyte/workflows/contracts.py:176 (__post_init__), vidbyte/workflows/validation.py:172 (__init__)."
- I checked the test-grant assertion directly on both trees (`DecisionHttpCall(method="POST", url=..., headers=..., timeout_seconds=...)`). A `type("Seconds", (float,), {})(30.0)` timeout and a `type("WholeSeconds", (int,), {})(30)` timeout raise at HEAD and construct on the fixed copy with `timeout_seconds == 30: True`. `True` and `0` raise on both trees with the same message. So the granted test fails at 7ee8ebbd and passes with the fix.

No spec change is needed after the fix: row 5 already admits subclasses. The fix needs no §17 deviation entry either.

## Adjudication: the repair report against the re-review, on C002

`reports/S5-repair-1.md` (R-2, second bullet) says the exact-type spelling was "forced by lint rule C002" and that refusing subclasses was "acceptable", because "only adapters build this record, from `DecisionModelConfig.timeout_seconds`". The re-review says C002 does not force this. Both are partly right:
- C002 does forbid the obvious idiom. `_bool_guard_identity` (`lint/rules/c002_duplicate_inline_bool_guard_validation.py:86-95`) keys on `isinstance(<name or attr>, bool)` with the bare name `bool`. A fourth `timeout_seconds` site takes the count to 10/9, which I reproduced. The field guide says the same in `blocking-lint-invariants.md` (C002 section): "Never add a second `isinstance(x, bool)` guard for a field name that is already guarded."
- C002 does not force subclass refusal. `type(x) is bool or not isinstance(x, (int, float))` keeps C002 at 9/9 and matches row 5. The repair's "acceptable" reason fails on its own premise. Adapters build the record from `DecisionModelConfig.timeout_seconds`, and that config admits subclasses (`model_configs.py:387`). So the refusal reaches users, as shown in step 4.

Verdict: the re-review is right. R-18 stands.

## R-C2 → R-19 (Minor, passed through)

At 7ee8ebbd, `git show 7ee8ebbd:docs/spec/decision-model-providers/spec.md | sed -n 919p` lists "`OpenAIDecisionsAnswers._by_name`/`_answer`/`_predicate`/...". Also at 7ee8ebbd, `grep -n "def _require_type\|def _answer" vidbyte/providers/openai_decisions.py` returns only `185: def _require_type(...)`. The claim is accurate, and it affects the spec only. While I worked, spec commit `44dc3faf` ("docs(spec): r11 — deviation 4 names the renamed OpenAI helper (R-C2)", which touches only spec.md) replaced `_answer` with `_require_type`. As the briefing directs, R-19 keeps the status "spec-only; spec author". The orchestrator can close it against `44dc3faf`.

## Severity blind spots checked (nothing new raised)

- **Other exact-type checks in the diff:** none. See step 1.
- **New `isinstance(..., bool)` guards in the diff:** one, `isinstance(value, int) and not isinstance(value, bool)` in `openai_decisions.py`. `value` is a C002 generic identity, so C002 does not count it.
- **`DecisionModelConfig` admits `True`, `inf` and `nan`** (`model_configs.py:387` has neither a bool check nor a finite check). Such a config now fails at the first call ("Invalid Jev decision call timeout_seconds") rather than at construction. Row 5 sanctions that refusal, and the briefing records it as decided. Tightening `DecisionModelConfig` is outside the R-2 design and §12.3 for this round. Not raised.
- **Interaction with the planned origin/main merge (28 commits).** origin/main touches `vidbyte/lib/dataclasses/jev.py`, with hunks at :22 (one import line), :3694, :3843 and :4634. After the merge, the R-18 line moves from :525 to about :526, so anchor on the text and not on the line number. On origin/main, `lint/baseline.json` is unchanged and the `timeout_seconds` C002 group is still the same three sites, so the fix stays C002-neutral after the merge.
- **Retry count:** rule 5 goes through `JevCount.require` with `isinstance` semantics, which matches the spec. Leave it alone.

## Commands run (all read-only for the worktree)

- `git log --oneline -8`, `git status --short` (0 lines before my edits), `git diff 7ee8ebbd HEAD --stat` (docs only), `git merge-base origin/main 7ee8ebbd` → `7be96284`.
- `git archive origin/main vidbyte | tar -x -C <scratchpad>/main_tree`. The same for the merge base, into `base_tree`.
- `PYTHONPATH=<tree> python rc1_probe.py {new,main}` and `rc1_managed.py {new,main,fixed}` (scratchpad scripts). Output is quoted above.
- `python lint/run.py` at HEAD → exit 0, `C002 9 9 RATCHETED`, `SDK-LINT: PASS`, and the tree still clean.
- `python lint_patched.py <worktree> type_is_bool` → `C002 9 9 RATCHETED`, `SDK-LINT: PASS`, exit 0. `... isinstance_bool` → `C002 10 9 REGRESSED`, exit 1.
- `python -m pytest -p no:cacheprovider tests/features/decision_model_providers -q` at HEAD → `90 passed in 1.08s`.
- On the fixed copy, the pack plus the 10 area files → `496 passed in 3.08s`.
- `git grep` for `isinstance(...timeout_seconds, bool)` on HEAD and origin/main: 3 sites each, all under `vidbyte/workflows/`.
- `git diff 7be96284 origin/main -- lint/baseline.json` → no changed lines.

I ran no `git add`, commit, checkout, stash, merge or push, no pip install, no `scripts/run_ci.py`, and made no network call. The only worktree files I changed are `review.md` and this report.
