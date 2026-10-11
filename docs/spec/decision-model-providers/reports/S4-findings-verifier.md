# S4 findings verifier — decision-model-providers

Code under review: `origin/main...9784a3f6`. Local HEAD `2082d21a` differs from 9784a3f6 only under `docs/spec/decision-model-providers/`. `git diff --stat 9784a3f6 HEAD -- vidbyte tests lint` prints nothing, and `git status --short` was clean before I wrote my two files.
Inputs read in full: the three S4 reviews, spec r10 (all sections), request.md, the review.md format, and house-style.md. Read in part: test-plan.md (coverage rows for OpenRouter, guards and the M4 area), research §3.4, §3.5 and research-2 §3.3, pricing-proof §3, AGENTS.md, and the field-guide entries provider-api-contracts, class-bound-helpers, jev-capability-layout and review-scope.
My probes are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4869ccb5-b2b0-4bb3-8b31-ca7e2cfe63fb/scratchpad/verifier/`, called `<V>` below. I wrote all of them myself and did not reuse any reviewer script.

## Gates I ran (baseline)
- `python -m pytest tests/features/decision_model_providers -q -p no:cacheprovider` → `87 passed in 1.51s`
- Area suite (the briefing's 10 files) → `406 passed in 3.34s`
- `python lint/run.py` → exit 0 and `SDK-LINT: PASS`. Key lines: `S009 staged-mypy-contracts 349 350 IMPROVED`, `C009 default-model-priced 1 1 RATCHETED`, `C010 pricebook-vintage-bump 0 0 CLEAN`.

## Merge map (original ID → merged ID)
| Original | Lens | Proposed | Merged | Disposition |
|---|---|---|---|---|
| R-C1 | conformance | Blocker | R-1 | CONFIRMED Blocker |
| R-E1 | engineering | Major | R-1 | merged into R-1 (same `systemone.py:85-89` root cause) |
| R-V1 | conventions | Blocker | R-2 | CONFIRMED Blocker (spec amendment needed) |
| R-E3 | engineering | Major | R-3 | CONFIRMED Major (test grant only) |
| R-C2 | conformance | Major | R-4 | CONFIRMED Major |
| R-V2 | conventions | Major | R-4 | merged into R-4 (same file, same rule) |
| R-E5 (M4 half) | engineering | Minor | R-4 guard | folded into R-4 as a protective test grant (fix interaction, see adjudication 5) |
| R-E2 | engineering | Major | R-5 | REFUTED as a defect |
| R-C4 | conformance | Minor [scope-adding] | R-5 | same root cause as R-E2; carried as Minor follow-up R-5 |
| R-C3 | conformance | Minor | R-6 | Minor, trivial |
| R-V3 | conventions | Minor | R-7 | Minor, trivial |
| R-V7 | conventions | Minor | R-8 | Minor, follow-up; the `_TYPESAFE_HOST` half is prescribed by spec row 14 |
| R-V5 | conventions | Minor | R-9 | Minor, follow-up |
| R-V6 | conventions | Minor | R-10 | Minor, follow-up |
| R-C5 | conformance | Minor | R-11 | Minor, follow-up |
| R-V4 | conventions | Minor [scope-adding] | R-12 | Minor, follow-up [scope-adding] |
| R-E4 | engineering | Minor | R-13 | Minor, follow-up (test grant) |
| R-E5 (M12 half) | engineering | Minor | R-14 | Minor, follow-up (test grant) |
| R-E6 | engineering | Minor | R-15 | Minor, follow-up |
| R-V8 | conventions | Minor | R-16 | Minor, follow-up (test author's file) |
| R-V9 | conventions | Minor | R-17 | Minor, follow-up (S6 squash message) |

Totals: confirmed Blockers 2, confirmed Majors 2, refuted 1 (R-5's Major claim), downgraded 0, Minors 13 (R-5 to R-17).

## Verification of every Blocker and Major

### R-1 (R-C1 + R-E1) — CONFIRMED Blocker
- **Code.** `vidbyte/providers/systemone.py:85-86` forces both keys only when `not question.options`. Line 89 otherwise returns `{option.name: option.description ...}` for whatever options exist.
- **Guard check.** `vidbyte/lib/dataclasses/jev.py:294-297` (`_validate_option_set`) accepts any subset of `JEV_NOUL_OPTIONS`. No guard elsewhere stops a one-option noul question.
- **Execution.** I ran `python <V>/v1_openrouter_criteria.py`, which uses a real `JevQuestion`, a real `DecisionModelRunner` and a scripted transport:
  ```
  openrouter  options []                       -> criteria {'true': None, 'false': None}
  openrouter  options [true:'refund owed']     -> criteria {'true': 'refund owed'}
  openrouter  options [false:None]             -> criteria {'false': None}
  openrouter  options [true:'a', false:'b']    -> criteria {'true': 'a', 'false': 'b'}
  perplexity  options []                       -> criteria <omitted>
  perplexity  options [true:'refund owed']     -> criteria {'true': 'refund owed'}
  ```
- **Spec reading.**
  - INV-6: "a host whose `SystemOneHost.noul_criteria_required` is true (OpenRouter) **always** receives `criteria: {"true": <description or null>, "false": <description or null>}` on noul questions".
  - Row 13: "`criteria()` returns `MappingProxyType({JEV_NOUL_TRUE: None, JEV_NOUL_FALSE: None})` (or the option descriptions) for noul when `host.noul_criteria_required`".
  - EC-6 and research §3.5 (`provider-research.md`): "The API reference says noul `criteria` 'must contain both `true` and `false` keys'".
  - So the two partial-option paths break the invariant, and OpenRouter rejects them.
- **Tests.** `test_decision_systemone_wire.py:110-131` covers only `()` and the fully described set, so it cannot fail.
- **Severity.** Blocker. A validated input gets a guaranteed vendor rejection on one host, which is a broken result, against an invariant's "always". I kept the higher of the two proposals; see adjudication 1.

### R-2 (R-V1) — CONFIRMED Blocker, spec amendment needed
- **Code.**
  - `git show origin/main:vidbyte/providers/typesafe.py` lines 138-139: `@dataclass(frozen=True, slots=True)` / `class _TypeSafeHttpCall:`. It is private, a pre-rule legacy record.
  - At 9784a3f6, `vidbyte/providers/decisions.py` is a new file. Lines 37-38 hold `@dataclass(frozen=True, slots=True)` / `class DecisionHttpCall:`, and line 49 holds `async def send(self, transport: HttpTransport) -> HttpResponse:`. The file has no `__post_init__`.
- **Rules.**
  - AGENTS.md Placement Rules, introduced as "binding for all new code": "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py` ... whether it is public or underscore-prefixed". Also: "Behavior that acts on the record lives in the layer that owns that behavior."
  - The "Existing code" clause allows only "Editing one in place (adding a field or a member)". This PR renamed and moved the record into a new module, which is not an in-place edit.
  - Field guide `jev-capability-layout.md:90-92`: "Keep payloads and records in `vidbyte/lib/dataclasses/jev.py`. Records hold validation only ..."; the owner said parsing and schema code "should not be in this dataclass".
  - `class-bound-helpers.md`: "Keep request/result records in `vidbyte/lib/dataclasses/`."
- **Gate check.** `.github/workflows/agents-md-placement.yml` has only a `workflow_dispatch` trigger ("TEMPORARILY DISABLED"), so nothing on the PR catches this. Its prompt (`.github/prompts/agents-md-placement.md` step 3) judges "each new function, class ... inside a changed file", which describes `DecisionHttpCall`.
- **Spec conflict.** FR-6, D-3, §8.4 ("relocated"), §8.5 (`DecisionHttpCall` with `send` in `decisions.py`) and row 12 all prescribe the current placement. AGENTS.md wins over the spec (house-style "the repository wins"), so the fix needs a spec amendment first. The orchestrator routes that to the spec author.
- **Feasibility.**
  - `git grep "from vidbyte.lib.http" -- vidbyte/lib/dataclasses` → none. `vidbyte/lib/http/*.py` imports only `vidbyte.lib.errors` and `vidbyte.lib.http.*`, so even an import would not create a cycle.
  - The record's fields need only `Mapping`, `field` (already imported in `jev.py`) and `JEV_NO_RETRIES` (`constants/jev.py`).
  - Once `send` moves to the providers layer, `vidbyte/lib/` imports no transport type and no provider type.
  - `Mapping[str, object]` fields already exist in `lib/dataclasses` (`jev.py:103`, `codex.py:202`), and the semgrep typed-mapping policy targets fallback conversions, not field types.
  - S015 counts imported names as bound (`lint/rules/s015_public_export_integrity.py` header: "extracts bound/imported/exported names"), so re-exporting from `decisions.py` keeps the test imports working (`test_decision_failures.py:182`, `test_decision_regression_typesafe.py:85`).
  - No test calls `.send`. `git grep "\.send(" -- tests` finds no decision call; the five production call sites are `systemone.py:261`, `openai_decisions.py:253`, `typesafe.py:243`, `:276` and `:302`.

### R-3 (R-E3) — CONFIRMED Major (fix is a test grant only)
- **Code.** `systemone.py:302-303` refuses `VIDBYTE_MANAGED` per call (§17 deviation 1). The URL now comes from `ProviderModelRegistry.resolve_endpoint(self.provider, config.endpoint)` (`:317`), so without this check a managed TypeSafe config would get TypeSafe's direct host and `resolved_api_key()` would return the Vidbyte key.
- **Execution, mutation.** `<V>/vmut.py` re-defines `_config_for` from `inspect.getsource` with exactly the two lines removed, and asserts that the count of removed lines is 2.
  ```
  VMUT=drop_percall_managed PYTHONPATH="<V>;." python -m pytest -p vmut tests/features/decision_model_providers <area suite> -q -p no:cacheprovider -s
  [vmut] applied drop_percall_managed: removed 2 lines from _config_for
  493 passed in 3.29s
  ```
- **Execution, effect.** `python <V>/v3_percall_managed_effect.py`, unmutated and then with `VMUT=drop_percall_managed`:
  ```
  RAISED ProviderConfigurationError | SystemOneProvider sends direct calls only; managed TypeSafe decisions go through TypeSafeProvider. | requests sent: 0
  SENT https://api.typesafe.ai/v1/systemone authorization= Bearer vb_live_aa...
  ```
- **Tests.** `git grep -n "sends direct calls only" -- tests` → no hit. `test_system_one_provider_construction_guards` (`test_decision_failures.py:158-175`) checks only the constructor's managed refusal (`:169`). Test-plan rows 75 and 76 confirm that scope.
- **Severity.** Major, not Blocker. The code is correct today, and the gap is in the test pack, not in a vacuous test. It is still a security guard against a `vb_live_` leak (T-4, INV-3) that any refactor could drop silently, which human review would flag. There is no production change, so the fix is one granted test.

### R-4 (R-C2 + R-V2) — CONFIRMED Major
- **Code**, read at 9784a3f6 (`openai_decisions.py`):
  - `normalize` (:123) → `self._answer` (:137).
  - `_answer` (:160) → `_predicate`, `_score`, `_choice` (:169-172).
  - `_choice` (:182) → `self._entries` (:184) and `self._distribution` (:185).
  - `_score` (:191) → `self._entries` (:194), `self._distribution` and `self._level` (:195).
  - `build` (:63) → `OpenAIDecisionsRequest.question` (:68).
  - `question` (:72) → `OpenAIDecisionsRequest.text` (:77).
  - `encode` (:95) → `option` (:102, :104).
  - `option` (:109) → `text` (:113).
- **Rule.**
  - AGENTS.md coding-style principle 1: "a function may call another of its own functions, but that second function should not call a third ... lift that call up into the main function". It applies "to new code", and the whole file is new.
  - Spec §12.4: "call chains stay one level deep (`run_decision` → builder/encoder/normalizer, never deeper)".
- **Spec check.** Row 15 describes `build` calling `text(request.state)` and `question(q)` side by side. It does not say that `question` calls `text`. §8.5 prescribes `build → question → criteria` for `SystemOneRequest`, which was relocated from main's `_TypeSafePayloadBuilder` (`origin/main typesafe.py:96-121`). That does not cover the new OpenAI builder.
- **Exemption.** `SystemOneAnswers` keeps main's `_TypeSafeAnswerNormalizer` method set (`origin/main typesafe.py:279-361`: `normalize`, `error`, `_answer`, `_choice`, `_score`, `_noul`, `_distribution`, `_keyed`) as row 13 prescribes, so I do not flag it.
- **Severity.** Major. Principle 1 is phrased "should" and appears among the style guidelines, not the binding Placement Rules. Behaviour is correct (11/11 OpenAI wire tests). The spec's own checklist makes it a review-visible gap.

### R-5 (R-E2; R-C4 Minor) — REFUTED as a defect
- **The claim** rests on "Workers AI selects the model from the `/ai/run/<model>` URL". The engineering reviewer could not read `context/provider-research.md`; I can.
- **Research evidence**:
  - `provider-research.md:62`: "Workers AI Clef / Clef-flash `POST /client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clef`, body `model: "clef"` or `"clef-flash"`".
  - `provider-research.md:129` (§3.4, sourced from https://developers.cloudflare.com/workers-ai/models/clef/): "**Boolean call**: `POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clef`, ... body `{"model":"clef-flash","state":"…",...}`".
  - So Cloudflare's own documented sample sends `clef-flash` through the clef route.
- **Spec IDs that decide it**:
  - The §9.1 CLOUDFLARE row: path `CLOUDFLARE_CLEF_PATH` = `/run/@cf/cloudflare/clef`, pricing `clef` 0.24 and `clef-flash` 0.038.
  - AC-7: the URL is `.../ai/run/@cf/cloudflare/clef`.
  - AC-12: Cloudflare `clef-flash` → `cost_usd == 0.038`.
  - D-17: Cloudflare's echo is undocumented, so `model_from_request=True` and the request id is priced.
  - NG-22 excludes only `clef-omni`, because its own sample uses `/ai/run/@cf/cloudflare/clef-omni` (`provider-research-2.md:502`).
- **What remains** is a "re-verify against the live vendor page" item, because vendor fetches are barred in S4. That is R-C4's Minor follow-up, carried as R-5.
- **Side note.** The reviewer's "`clef-omni` prices at 0.24 by prefix" note is pre-existing longest-prefix behaviour; its own verified claim 12 records "with no finding".

## Minors (passed through, de-duplicated, spot-checked)
- **R-6 (R-C3).** `grep -c` on the README gives `PERPLEXITY_API_KEY=1 ... VANSA_KEY=1`, and every other new var is 0. The README is `52002` characters.
- **R-7 (R-V3).** I read `systemone.py:236`, `:242` and `:303`. Spec §17 deviation 3 records `provider="systemone"`.
- **R-8 (R-V7).** `openai_decisions.py:56` is `_LABEL = "OpenAI"`. `typesafe.py:58` is `_TYPESAFE_HOST = SystemOneProvider.HOSTS[ModelProvider.TYPESAFE]`, which spec row 14 prescribes verbatim ("`_TYPESAFE_HOST = SystemOneProvider.HOSTS[ModelProvider.TYPESAFE]`"). That half is spec-conformant.
- **R-9 (R-V5).** I read `decision.py` lines 3, 7, 9, 30, 45 and 59; each still describes TypeSafe-only behaviour.
- **R-10 (R-V6).** `grep` hits at `systemone.py:207` ("spec section 9.1"), `pricing.py:109` ("spec D-12"), README `:599-600` ("research §3.4" and "§3.3"), and `systemone.py:7` (Q-11).
- **R-11 (R-C5).** `skills.py:130` reads `self.decision.model`. `git diff --stat origin/main...9784a3f6 -- vidbyte/agents/jev/alignment/skills.py` is empty, and the last origin/main commit to it is `bfe395fe ... (#698)`.
- **R-16 (R-V8).** `grep -o` finds "Written before the implementation, so every test is red until the spec lands." No r10 or implementation log entry exists (count 0).
- **R-12, R-13, R-14, R-15, R-17.** Passed through as the reviewers wrote them, with tags. R-13 and R-14 need test grants. R-15 is spec-conformant per A-15 (only the README warning is in scope).

## Severity blind spots checked (step 6)
1. **Fix interaction, R-4 against INV-8 (added as a [verifier] guard on R-4).** R-4's refactor rewrites `_choice`, `_score` and `_distribution`. The duplicate-entry check at `openai_decisions.py:213-214` has no test.
   - `VMUT=drop_duplicate_check PYTHONPATH="<V>;." python -m pytest -p vmut tests/features/decision_model_providers -q -s` → `87 passed in 0.44s`.
   - `python <V>/v5_duplicate_probe.py` with a sum-valid duplicate (billing 0.1, logistics 0.2, support 0.1, billing 0.7): unmutated, `RAISED ProviderResponseError | OpenAI `probabilities` for 'team' list an option more than once.`; mutated, `ACCEPTED {'billing': 0.7, 'logistics': 0.2, 'support': 0.1}`.
   - So a convention fix could silently break INV-8 ("a ... duplicate ... answer ... raises ProviderResponseError"). I attached a test grant to R-4 and did not open a separate line.
2. **Fix interaction, R-2 against INV-24.** `tests/test_jev_managed_gateway.py:37,138-140` asserts that the Vidbyte key is absent from `repr(call)`. The moved record must keep `headers: ... = field(repr=False)`, and the new `__post_init__` must never put `headers` in a message (INV-5, T-3).
3. **Fix interaction, R-7 against R-3.** If the repair agent hoists the managed-refusal sentence into a constant (R-7), the text must stay byte-identical, because R-3's granted test asserts it.
4. **Fix interaction, R-1 against INV-23.** The new branch runs only when `host.noul_criteria_required`. TypeSafe and every other host keep today's body, so the TypeSafe regression tests are unaffected.
5. No other Blocker-class gap fell between the lenses. Security (key hygiene, managed refusal), billing (usage on every failure path, luna tier), and catalog ownership were each verified by at least one reviewer with probes, and my baseline gates agree.

## Adjudications between reviewers
1. **R-C1 Blocker vs R-E1 Major.** I chose Blocker. Every input that triggers the bug (one noul option on OpenRouter) gets a vendor rejection, which is a broken result against INV-6's "always". The merge rule keeps the higher severity, and I found no reason to lower it.
2. **R-E2 Major vs R-C4 Minor [scope-adding].** R-E2 is refuted on research §3.4 (a document R-E2's author could not read). R-C4's framing, "unverified; a follow-up for the user", survives as Minor R-5.
3. **R-V2 vs R-C2 scope.** The conformance reviewer called only the normalizer unambiguous, because §8.5 prescribes a two-level builder. The conventions reviewer included the builder. I included both. §8.5's `build → question → criteria` is the relocated System One builder; for the new OpenAI builder, row 15 has `build` call `text` and `question` side by side, so the `question → text` hop is not prescribed and principle 1 applies to it.
4. **R-V1 vs the conformance reviewer's verified claim 15.** The conformance reviewer marked "Every new dataclass lives in jev.py" as HELD for the three records §12.4 names. The conventions reviewer flagged the unnamed fourth record. I side with conventions: the §12.4 list is incomplete, and AGENTS.md is binding over the spec's list.
5. **R-E5.** I split it. The M4 half (the duplicate check) becomes R-4's protective test grant, because R-4's fix edits that code. The M12 half stays Minor R-14.
6. **R-E3 severity.** I kept Major and did not downgrade. Downgrading needs "would not draw a human review comment", and an untested guard against posting a `vb_live_` key is exactly what a security reviewer comments on.

## Commands run (final lines)
- `git diff --stat origin/main...9784a3f6 -- . ':(exclude)docs' | tail` → `33 files changed, 3639 insertions(+), 254 deletions(-)`.
- `git diff --stat 9784a3f6 HEAD -- vidbyte tests lint` → empty.
- `git show origin/main:vidbyte/providers/typesafe.py | grep -n "class \|@dataclass\|def "` → `138:@dataclass(frozen=True, slots=True)`, `139:class _TypeSafeHttpCall:`, `150: async def send`, and `279:class _TypeSafeAnswerNormalizer:` with the eight methods listed above.
- `python <V>/v1_openrouter_criteria.py` → quoted under R-1.
- `python <V>/v3_percall_managed_effect.py`, with and without the mutation → quoted under R-3.
- The mutant pack and area run → `493 passed in 3.29s`. The baseline pack → `87 passed in 1.51s`; the baseline area suite → `406 passed in 3.34s`.
- `VMUT=drop_duplicate_check` pack → `87 passed in 0.44s`. `python <V>/v5_duplicate_probe.py`, both variants → quoted above.
- `python lint/run.py` → `SDK-LINT: PASS`, `exit=0`.
- `git grep -n "sends direct calls only\|SystemOneProvider" -- tests` → only the construction, factory and HOSTS tests; no per-call managed test.
- `git grep -n "from vidbyte.lib.http" -- vidbyte/lib/dataclasses` → none. `git grep -n "from vidbyte" -- vidbyte/lib/http` → only `vidbyte.lib.errors` and `vidbyte.lib.http.*`.
- `sed -n '1,80p' .github/workflows/agents-md-placement.yml` → `on: workflow_dispatch:` ("TEMPORARILY DISABLED").
- `grep -n -i "clef-flash\|run/@cf" context/*.md` → the lines quoted under R-5.
- `git status --short` (before writing) → clean.

No repo files were edited except `review.md` and this report. No commits, no network calls to vendors.
