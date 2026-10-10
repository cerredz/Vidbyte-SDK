LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the change follows the house style closely (headers, `@intent`, frozen validated wire records, dated first-party price proof, green lint ratchet), but one new public dataclass sits outside `vidbyte/lib/dataclasses/` against a binding AGENTS.md Placement Rule, and the new OpenAI normalizer breaks the one-level call-chain rule that spec §12.4 names explicitly.

Reviewed: `git diff origin/main...9784a3f6`, file by file (process artifacts under `docs/spec/decision-model-providers/` excluded per briefing). Local HEAD f23da1da differs from 9784a3f6 only in pipeline.md.

WHAT THE IMPLEMENTATION GETS RIGHT
- Lint ratchet holds with no REGRESSED rule: `SDK-LINT: PASS`; S009 349 (baseline 350), A001 643/643 (all three new modules carry the full 7-field header), S015 13/13, A006 34/34 (no `vidbyte.agents` import in any new provider module), A009 0 (providers README 52,002 chars, under the 54,000 budget), C009 only the baselined MISTRAL row, C010 0. `lint/baseline.json` is untouched. Every new policy-token function carries `# @intent` (A002 JSON shows no finding on an added line).
- Placement done right for the records and enum the spec named: `SystemOneHost`, `OpenAIDecisionsWireQuestion`, `OpenAIDecisionsWireRequest` are `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/jev.py` with `__post_init__` validation and `__all__` entries; `DecisionAuthScheme` is in `vidbyte/lib/enums/jev.py` and exported from `vidbyte/lib/enums/__init__.py`; the seven new wire constants are in `vidbyte/lib/constants/jev.py` with URL comments. The `DecisionModelConfig.model: str | None` union exception is documented in the docstring as `strict-config-dataclasses.md` asks.
- Price proof (INV-29) matches `pricing.py`'s existing dated-comment style: every decision block and the `gpt-6-luna` row sit under a contiguous comment with the vendor's own URLs and 2026-10-10; OpenRouter gets its comment-only citation; the C010 lock was refreshed with the tool, in the same commit as the rates (5d1ec7c4, as spec P5 orders).
- `run_decision` in both new adapters keeps the single guarded, narrated `try` with the five typed branches (`provider-api-contracts.md`, NFR-7); every `transport.request` passes `timeout_seconds`; headers stay out of `repr`. Do not "fix" these.

FINDINGS
R-V1 [Blocker] [AGENTS.md placement] vidbyte/providers/decisions.py:37-50 — `DecisionHttpCall` is a newly defined public dataclass outside `vidbyte/lib/dataclasses/`, unvalidated, with transport behaviour on the record
  Evidence: `git show 9784a3f6:vidbyte/providers/decisions.py`:
    `37 @dataclass(frozen=True, slots=True)` / `38 class DecisionHttpCall:` / fields `method: str`, `url: str`, `headers: Mapping[str, str] = field(repr=False)`, `timeout_seconds: float`, ... / `49     async def send(self, transport: HttpTransport) -> HttpResponse:`; `grep -n "post_init"` on the file returns nothing. On main the record was private `_TypeSafeHttpCall` in `vidbyte/providers/typesafe.py:138-151`; this PR deletes that and defines a new public name in a new module. Tests import it from the new path: `test_decision_failures.py:182,197`, `test_decision_regression_typesafe.py:85,89,97` (construction and `repr` only; nothing calls `.send`).
  Failure: AGENTS.md "Placement Rules" (binding; "the AGENTS.md placement workflow enforces it on every pull request by moving misplaced code"): "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py` ... whether it is public or underscore-prefixed"; "Behavior that acts on the record lives in the layer that owns that behavior." The "Existing code" clause allows only editing a legacy record in place (adding a field), not a rename to a new public name in a new module. Coding-style principle 4 also asks every such record to validate in `__post_init__`. Spec §8.4 counted it as "relocated" and FR-6 put it in `providers/decisions.py`, so the defect is in the spec as much as the code. A human reviewer would write: "New public dataclass in providers/ — move it to lib/dataclasses/jev.py; the placement bot will do it for you otherwise, and it will leave no re-export behind for the tests."
  Smallest fix: define `DecisionHttpCall` (same fields, plus a `__post_init__` that rejects a blank `method`/`url`, a non-positive `timeout_seconds`, a negative `retry_count`) in `vidbyte/lib/dataclasses/jev.py` and add it to that `__all__`; turn `send` into a plain function in `vidbyte/providers/decisions.py` (for example `send_decision_call(call, transport)`, keeping its `@intent`) and update the three adapter call sites; import the record into `providers/decisions.py` so the existing test imports keep resolving. Amend FR-6's location sentence to match.
  Spec IDs: FR-6, W-4, §8.4, §12.4 ("Every new dataclass ... lives in `vidbyte/lib/dataclasses/jev.py`")

R-V2 [Major] [AGENTS.md style principle 1 / spec §12.4] vidbyte/providers/openai_decisions.py:123-224, 63-113 — new code nests helper calls two and three levels deep, which §12.4 says must "never" happen
  Evidence: `grep -n "def \|self\._\w*(\|OpenAIDecisions\w*\.\w*("` at 9784a3f6:
    `123 def normalize` → `137 ... self._answer(...)` → `160 def _answer` → `169 return self._predicate(...)` / `171 self._score(...)` / `172 self._choice(...)` → `182 def _choice` → `184 entries = self._entries(...)` / `185 probabilities = self._distribution(...)`; `191 def _score` → `194 self._entries` / `195 self._distribution(... self._level(names, entry) ...)` (normalize → _answer → _score → _entries/_distribution/_level: three levels below the main function).
    `63 def build` → `68 OpenAIDecisionsRequest.question(...)` → `72 def question` → `77 OpenAIDecisionsRequest.text(...)`; `95 def encode` → `102/104 OpenAIDecisionsRequest.option(...)` → `113 OpenAIDecisionsRequest.text(...)`.
  Failure: AGENTS.md coding-style principle 1 ("a function may call another of its own functions, but that second function should not call a third ... lift that call up into the main function"; applies to new code). Spec §12.4: "call chains stay one level deep (`run_decision` → builder/encoder/normalizer, never deeper)". `openai_decisions.py` is wholly new code; the System One normalizer in `systemone.py` has the same shape but was relocated from main's `_TypeSafeAnswerNormalizer`, so it is not flagged. A human reviewer would write: "normalize → _answer → _score → _distribution is four frames to read one answer; lift `_entries`/`_distribution` into `_answer` (or make `_choice`/`_score` return the pairs) and have `build`/`encode` call `text` themselves."
  Smallest fix: make `_choice`/`_score` pure helpers that receive already-extracted entries, and call `_entries`, `_level` and `_distribution` from `_answer`; in `build` and `encode`, resolve the `text(...)` values in the main function and pass strings into `question`/`option`. No name, message, or behaviour changes, so the feature pack is unaffected.
  Spec IDs: §12.4 (narration/call-chain line), FR-9, W-6

R-V3 [Minor] [spec §12.4 / providers README Contract Invariant 4] vidbyte/providers/systemone.py:236 — `ProviderConfigurationError` carries `provider="systemone"`, which is not a `ModelProvider` value; the managed-refusal message is a duplicated literal
  Evidence: `236 raise ProviderConfigurationError("SystemOneProvider requires a DecisionModelConfig: pass decision_config= to the adapter.", provider="systemone")`; lines 242 and 303 repeat the same sentence `"SystemOneProvider sends direct calls only; managed TypeSafe decisions go through TypeSafeProvider."`. `grep -rn '"systemone"' tests/ vidbyte/` hits only line 236, so no test pins it.
  Failure: §12.4: "`ProviderConfigurationError` carries `provider=self.provider.value`"; README "Contract Invariants" 4. No provider is known at that point (the constructor has no config), and `typesafe.py` already uses a non-member `"vidbyte"`, so this is a clarity issue. A reviewer would ask for one constant message and an explicit note on why the provider field is a placeholder.
  Smallest fix: one comment on line 236 saying no provider is known without a config (or reuse the `"vidbyte"` convention); hoist the managed-refusal sentence into a single class-level or `constants/jev.py` string used at 242 and 303.
  Spec IDs: §12.4 (error line), FR-11

R-V4 [Minor] [scope-adding] [AGENTS.md enums] vidbyte/lib/dataclasses/jev.py:464 — `OpenAIDecisionsWireQuestion.type` is a closed three-value set typed as `str`
  Evidence: `464     type: str` with `471 allowed = (OPENAI_DECISIONS_PREDICATE_TYPE, JevQuestionType.CHOICE.value, JevQuestionType.SCORE.value)`; `test_decision_contract.py:313,317,319` construct it with plain strings (`type="choice"`, rejects `"noul"`).
  Failure: AGENTS.md "Enums go in vidbyte/lib/enums/": "Any field ... whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`." Spec §8.5 / FR-12 fixed `type: str`, mirroring main's `TypeSafeWireQuestion.type: str` (jev.py:401), which AGENTS.md says not to copy as precedent. The value is validated, so nothing is wrong at runtime. The fix adds an enum the spec never contained, which goes past the §8.4 class budget ("ask first"); hence Minor.
  Smallest fix: if the orchestrator allows it, add `OpenAIDecisionsQuestionType(str, Enum)` with `PREDICATE`/`CHOICE`/`SCORE` to `vidbyte/lib/enums/jev.py`, export it, and coerce the field in `__post_init__` so string construction (which the tests use) still works. Otherwise record the exception in the field's docstring.
  Spec IDs: FR-12, §8.5

R-V5 [Minor] [header accuracy / AGENTS.md principle 2] vidbyte/lib/runners/decision.py:3,7,9,30,45,59 and vidbyte/agents/pricing/typesafe.py:7,10 — headers and narration still describe a TypeSafe-only runner
  Evidence: `3 PURPOSE: ... and lists the models the account can use.`; `7 KNOWN EDGE CASES: Construction raises ConfigurationError when no API key resolves`; `9 TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, and scripts/test-jev-agent-scaffold.py.`; `30 # Validates the config (including the API key)`; `45 # ... a failed call that TypeSafe still billed`; `59 # Returns the model IDs and aliases (GET /v1/models) this account can pass`. Now 15 of the 16 providers raise from `list_models`, construction also fails for Cloudflare/Foundry with no endpoint (`validate()` resolves the endpoint), and the feature pack is not listed. `agents/pricing/typesafe.py` updated PURPOSE/ROLE but kept `COMMON MODIFICATION PATTERNS: ... extend parsing only when TypeSafe adds usage fields.` and a TESTS line without the feature pack, although it now parses thirteen other hosts.
  Failure: AGENTS.md principle 2 ("update its comments in the same edit so they never describe behavior that is gone"); CONTRIBUTING.md "Update nearby documentation when behavior ... change[s]". Spec §12.5 named only line 6 of the runner header, so the implementer followed the letter. A reviewer would write: "header says this lists the account's models; for 15 providers it raises."
  Smallest fix: edit those six comment lines (TypeSafe-only model listing; key and endpoint checked at construction; any host's billed failure; add `tests/features/decision_model_providers/`), and the two `pricing/typesafe.py` header fields ("when any bound System One host adds usage fields"; add the feature pack to TESTS).
  Spec IDs: FR-16, §12.5 (header bullet)

R-V6 [Minor] [agentic headers / AGENTS.md "docs/ is opaque"] vidbyte/providers/systemone.py:7,207; vidbyte/lib/registries/pricing.py:109; vidbyte/providers/README.md:599-600; RELATED DOCS of decisions.py:8, systemone.py:8, openai_decisions.py:8 — production text cites pipeline-local spec IDs
  Evidence: `systemone.py:7 ... (Nace.AI publishes one, Q-11)`; `systemone.py:207 # One row per System One host (spec section 9.1).`; `pricing.py:109 # this row carries (spec D-12).`; `README.md:599 | Cloudflare | undocumented (research §3.4); ...`, `600 | Microsoft Foundry | undocumented (research §3.3); ...` (no path for "research"); `decisions.py:8 RELATED DOCS: ... docs/spec/decision-model-providers/spec.md`. On main, nothing under `vidbyte/` cites `docs/spec/` (392 files cite `docs/design/`).
  Failure: AGENTS.md tells agents not to read `docs/` unless a human names a document, so a code comment whose reason lives only behind "Q-11" or "D-12" cannot be followed; "research §3.4" leads nowhere. A reviewer would write: "inline the reason, not the ticket number."
  Smallest fix: replace each ID with its reason in a few words (for example "Nace.AI publishes a model list, but the SDK does not call it"); drop "(spec D-12)", since the sentence before it already gives the reason; give the README "research" cites a path or replace them with the vendor doc URL. The RELATED DOCS `docs/spec/...` entries may stay if the team accepts spec links from code; the inline IDs should go.
  Spec IDs: n/a (FR-15 for the README rows)

R-V7 [Minor] [placement / constants] vidbyte/providers/openai_decisions.py:55-56; vidbyte/providers/typesafe.py:58 — new module-level constants in JEV decision modules
  Evidence: `55 # The host name every OpenAI Decisions message carries.` / `56 _LABEL = "OpenAI"`; `typesafe.py:58 _TYPESAFE_HOST = SystemOneProvider.HOSTS[ModelProvider.TYPESAFE]` (next to the pre-existing `_PROVIDER`).
  Failure: AGENTS.md "New JEV code": "a constant in `vidbyte/lib/constants/jev.py`"; field guide `jev-capability-layout.md` ("no module-level constants (underscore-private count too)"). The same lesson applies to `SystemOneProvider.HOSTS` (a 15-row capability table living as a `ClassVar` in an adapter that `TypeSafeProvider` reaches into) under `declarative-config-resolution.md` ("capability declarations live in dependency-light config data"), but spec D-4 chose the in-adapter table, so that is a risk note only.
  Smallest fix: move `_LABEL` to `constants/jev.py` as `OPENAI_DECISIONS_DISPLAY_NAME` (exported); read `_TYPESAFE_HOST` where it is used, or make it a `ClassVar` on `TypeSafeProvider`.
  Spec IDs: §12.4 ("New constants live in `vidbyte/lib/constants/jev.py`"), FR-13

R-V8 [Minor] [folder README discipline] tests/features/decision_model_providers/README.md:5,21-25 — the pack README still says every test is red, and its log stops before the implementation
  Evidence: `5 ... Written before the implementation, so every test is red until the spec lands.`; the Logs list ends with the r8 grant, with no entry for the r10 grant (76b0674d) or the implementation landing; `pytest tests/features/decision_model_providers -q` → `87 passed`.
  Failure: AGENTS.md "Each folder's own README.md documents that folder", and the folder's own Logs convention. The implementer was barred from touching test files, so this falls to the test author or orchestrator.
  Smallest fix: change the sentence to "Written before the implementation; all tests pass at 9784a3f6", and add two log lines (the r10 grant; the implementation landed, 87 passed).
  Spec IDs: n/a

R-V9 [Minor] [commit hygiene] commit 99d4567c — a PR commit subject refers to the out-of-PR cloud experiment
  Evidence: `git log -1 --format=%B 99d4567c` → `docs(spec): log cloud experiment status check`. `git grep -n "claude --cloud\|--teleport\|session_01" 9784a3f6 -- vidbyte tests lint docs/spec/decision-model-providers/spec.md` → no output, so the request §A sentence is not in code, tests, or the spec, and no commit message carries it verbatim. One PR commit (b14b1674, request capture) has no Co-Authored-By trailer; the other 86 do (62 Opus 5.5, 24 Fable 5.1).
  Failure: The briefing says the experiment is outside this PR, so its traces should not ship in PR history. A reviewer would ask for it to be dropped from the squash message.
  Smallest fix: leave it out of the squash-merge message body; no code change.
  Spec IDs: n/a

VERIFIED CLAIMS
1. Lint ratchet holds (NFR-2): HELD. `SDK-LINT: PASS`, exit 0, no REGRESSED rule; S009 349 ≤ 350; S010 0; S014 0; C016 0; C017 0.
2. `lint/baseline.json` never edited: HELD. `git diff origin/main...9784a3f6 -- lint/baseline.json` is empty.
3. Changed non-docs, non-test files are exactly the 21 §12.3 paths plus `lint/pricebook_vintage_lock.json`: HELD.
4. §8.4 budget of 12 new classes and 3 new files: HELD in count. The placement of one of them (`DecisionHttpCall`) is R-V1.
5. Every new module has the 7-field header and an explicit `__all__`: HELD (A001 643/643, S015 13/13).
6. No `vidbyte.agents` import from the new provider modules (NFR-3): HELD (A006 34/34).
7. Every new or moved policy-token function carries `@intent` (§12.4): HELD (A002 `--format json`: 655 findings, none on a line this PR adds).
8. Providers README at or under 54,000 characters: HELD (52,002).
9. C009 flags only the baselined MISTRAL default; Baseten is now priced: HELD (`C009 1 1`, `vidbyte/lib/registries/models.py:70 MISTRAL`).
10. Feature pack passes against the worktree: HELD (87 passed in 1.29s; `vidbyte` resolves to the worktree).
11. Commits cite spec IDs and carry the trailer; 5d1ec7c4 lands rows 1, 6, 7, 8 and the lock together per P5: HELD, except b14b1674 (no trailer; an orchestrator docs commit).
12. The request §A `claude --cloud` sentence is absent from code, tests, the spec, and commit messages: HELD (see R-V9 for the subject that refers to it).
13. §12.4 "`ProviderConfigurationError` carries `provider=self.provider.value`": DID NOT HOLD at systemone.py:236 (R-V3).
14. §12.4 "call chains ... never deeper": DID NOT HOLD in openai_decisions.py (R-V2).
15. §12.4 "Every new dataclass lives in `vidbyte/lib/dataclasses/jev.py`": HELD for the three records the spec names. `DecisionHttpCall` is not named there and is outside (R-V1).
16. Briefing "Each folder's README ends with ## Notes for agents": DID NOT HOLD for the touched folders. None of the providers, registries, enums, runners, pricing, constants, dataclasses, or lib READMEs has that section, so there were no recorded lessons to check against.
17. `DecisionAuthScheme` is placed in `enums/jev.py` and exported (§12.4, D-18): HELD.
18. SKILL.md lines 47, 98, 139 and the REPO_MAP JEV table updated (§12.5): HELD.

COMMANDS RUN
- `python lint/run.py` → `SDK-LINT: PASS` (exit 0)
- `python lint/run.py --rule C009 --format json` → `C009 1 1 RATCHETED`; finding `vidbyte/lib/registries/models.py:70` MISTRAL
- `python lint/run.py --rule S020 --all` → one pre-existing finding, `vidbyte/agents/multi/README.md:26`
- `python lint/run.py --rule A002 --format json` → 655 findings; none on a PR-added line
- `python -m pytest tests/features/decision_model_providers -q -p no:cacheprovider` → `87 passed in 1.29s`
- `git diff origin/main...9784a3f6 -- lint/baseline.json` → (empty)
- `git diff --name-only origin/main...9784a3f6` (non-docs, non-test) → 21 §12.3 paths + `lint/pricebook_vintage_lock.json`
- providers README character count at 9784a3f6 (BOM stripped) → `52002`
- `git show 9784a3f6:vidbyte/providers/decisions.py | grep -n "class \|def \|post_init"` → `38:class DecisionHttpCall:`, `49: async def send`, `57:class DecisionFailures:`; no `__post_init__`
- `git show 9784a3f6:vidbyte/providers/openai_decisions.py | grep -n "def \|self\._\w*(\|OpenAIDecisions\w*\.\w*("` → call graph quoted in R-V2
- `git show 9784a3f6:vidbyte/providers/systemone.py | grep -n 'Q-11\|spec section\|provider="systemone"\|"authorization"'` → lines 7, 207, 236, 315
- `git show 9784a3f6:vidbyte/lib/registries/pricing.py | sed -n 105,110p` → `# this row carries (spec D-12).`
- `git log origin/main..9784a3f6 --no-merges --format='%h|%(trailers:key=Co-Authored-By,valueonly)'` → 62 Opus 5.5, 24 Fable 5.1, 1 empty (b14b1674)
- `git log -1 --format=%B 99d4567c` → `docs(spec): log cloud experiment status check`
- `git grep -n "claude --cloud\|--teleport\|session_01" 9784a3f6 -- vidbyte tests lint docs/spec/decision-model-providers/spec.md` → (no output)
- `grep -rn '"systemone"' tests/ vidbyte/ --include=*.py` → only `vidbyte/providers/systemone.py:236`
