LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — The layering, placement, D-21 imports, constants, and docs are clean, but one AGENTS.md call-depth violation, a weakened S014, a worsened A002 count under a passing lint exit, list-rejecting public annotations, and a mode ladder need fixing first.

WHAT THE IMPLEMENTATION GETS RIGHT
- Layering and D-21 hold. At module level, `vidbyte/lib/registries/provider_keys.py` imports only `re`, `collections.abc`, `typing`, `lib.constants.jev`, `lib.enums` and `lib.errors`. `ProviderKeys` is imported late inside `match`, under `@intent provider-keys-import-late`, and `lib/dataclasses/agents.py` imports no registries module. Both D-21 import commands succeed, and A006 stays at 34 = 34.
- `ProviderKeyMatcher` is a class-bound static helper (`class-bound-helpers.md`). `match` is narrated step by step (Steps 1–7), and every `_` helper is a leaf `@staticmethod` that calls no other own helper. The new constants live in `lib/constants/jev.py`. The relay header is stored by subscript with the imported constant (`vidbyte_gateway.py:183`, C017 CLEAN). No header literal, `[!-~]+` pattern, or 512 cap appears anywhere else under `vidbyte/`.
- `TextModelConfig.credentials()` dispatches with `match self.mode` and a raising `case _` (`model_configs.py:128-152`), and every key field is `repr=False`. The diff adds no `type: ignore`, `noqa`, or `nosemgrep`. The only baseline change lowers A001 (643 → 641). `base.py` grows by 26 net lines (34/8), within the 30-line limit (NFR-4).
- Every §12.5 action is done:
  - the registries README "Provider Key Format Sources" section, with first-party and secondary labels and exact URLs;
  - the root and agents READMEs, the skills docs, and the `llms.txt:1113` scrub sentence;
  - the `ProviderKeyMatcher` export (`registries/__init__.py:22,32`).
  Commits carry one work item each with W-/FR-/AC- IDs. The diff holds no secrets and no generated or cache files.

FINDINGS

R-V1 [Blocker] [AGENTS.md §1 call depth] vidbyte/lib/dataclasses/model_configs.py:121 — `credentials()` calls two new own helpers, and `validate()` and `resolved_api_key()` call `credentials()`, so the new chains run two levels deep
  Evidence:
  - `:119` (inside `validate()`): `self.credentials()`
  - `:162` (inside `resolved_api_key()`): `provider_api_key = self.credentials().provider_api_key if self.mode is TextModelMode.DIRECT else None`
  - Inside `credentials()`: `:127 provider = self.normalized_provider()`, `:135 self._refuse_missing_provider_key(provider)`, `:149 self._require_relayable_length(provider, provider_key)`. Both of the last two helpers are new in this PR.
  Failure: AGENTS.md §1 says "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function". `validate()` → `credentials()` → `_refuse_missing_provider_key()` and `resolved_api_key()` → `credentials()` → `_require_relayable_length()` are both such chains.
  The §12.4 checklist bounds it too: "`credentials()` calls registry methods plus at most one own helper (`_require_gateway_shape`), and that helper calls no own helper". It calls three own methods.
  A reviewer would write: "validate → credentials → _refuse_missing_provider_key is two levels; inline the raise."
  Smallest fix:
  - Inline the M-8 raise into `case TextModelMode.DIRECT`.
  - Inline the M-21 length check into `case TextModelMode.AUTO`, and move its `@intent relayed-key-fits-the-gateway-header` block with it.
  - Delete `_refuse_missing_provider_key` and `_require_relayable_length`.
  `credentials()` then calls only registry methods and the leaf `normalized_provider()`, which is the one own helper §12.4 allows.
  Spec IDs: FR-3 (§12.4 call-depth bullet; §12.3 row 7)

R-V2 [Major] [lint rule strictness] lint/rules/s014_provider_model_registry_parity.py:46 — S014 counts a deleted, empty, or wrongly aliased `API_KEY_ENV_VARS` as an alias and passes CLEAN where the base rule reported 14 findings; its header claims the reverse
  Evidence:
  - `:46 aliased = set(maps["API_KEY_ENV_VARS"]) == {"__line__"}` and `:47 maps["API_KEY_ENV_VARS"] = constants_map if aliased else maps["API_KEY_ENV_VARS"]`
  - Header `:9`: "An API_KEY_ENV_VARS that is neither a literal nor a resolvable alias reports every provider missing."
  - Mutations, each run on a scratch `git archive 8bd1963d` copy with `python lint/run.py --rule S014 --format json`, edit `vidbyte/lib/registries/models.py:91` (except the control):

    | Mutation | Result |
    |---|---|
    | none | `found 0 CLEAN` |
    | `= {}` | `found 0 CLEAN` |
    | line deleted | `found 0 CLEAN` |
    | `= DEFAULT_TEXT_MODELS` | `found 0 CLEAN` |
    | control: drop the OPENAI row at `jev.py:103` | `found 1 REGRESSED` |
    | base 595a7260, literal replaced by `{}` | `found 14 REGRESSED` |

  Failure: The S014 ruling (pipeline.md at 0d0b484b) let the rule read `jev.py` "when the registry attribute is not a literal", on the condition "Parity stays equally strict". §12.4 says "no rule is weakened" (vidbyte-gates.md). The rule misses that condition in two ways:
  - `{}` is a literal, yet the rule reads it as an alias.
  - Nothing checks that the alias names `PROVIDER_API_KEY_ENV_VARS`.

  S3's mutation proof (S3 report §6) mutated only the `jev.py` side. A deletion would still surface through S009 or an AttributeError, but no lint rule catches an emptied table or a wrong alias.
  A reviewer would write: "This never checks it is actually an alias, and the header says the opposite."
  Smallest fix:
  - Set `aliased` only when the `ProviderModelRegistry` body assigns `API_KEY_ENV_VARS` an `ast.Name` with id `PROVIDER_API_KEY_ENV_VARS`. Otherwise keep the class-dict result, so `{}`, a deletion, or another name reports every provider at `models.py`, as on base.
  - Correct header `:9`.
  - Add the three registry-side mutations above to the S3 proof.
  Spec IDs: NFR-5, W-2 (§12.4 "no rule is weakened"; S014 ruling condition)

R-V3 [Major] [lint A002 / @intent] vidbyte/agents/settings/fallback.py:98 — A002 worsens from 584 to 585 under a passing lint exit: two new business-rule functions have no `@intent`, and two edited ones lost theirs
  Evidence: A per-rule JSON comparison, head against base (`lint/run.py --rule A002 --all --format json`):
  - New findings (4):
    - `settings/fallback.py named_providers` (`:98`, new)
    - `model_configs.py relays` (`:273`, new)
    - `aggregation.py _build_aggregator` (`:341`)
    - `settings/fallback.py _inherited_provider` (`:165`). It lost its cover when `_inherited_api_key` and its `@intent` were deleted.
  - Removed findings (3): aggregation `__init__` and `_build_proposer_agent`, and settings/fallback `to_fallback`.
  - Table rows: base `A002 intent-comments 584 703 IMPROVED`; head `585 703 IMPROVED`.
  Failure: §12.4 requires "Every business rule has an `@intent` within 20 lines of its `def`" (`comment-format.md`, lint A002). The S4 brief adds: "a passing exit with a worsened rule count is still a finding". Both new functions are business rules:
  - `relays` decides whether the developer's provider key goes on the wire to the gateway.
  - `named_providers` decides which providers the root matches keys against.
  A reviewer would write: "`relays` decides whether a secret is sent; where is its `@intent`?"
  Smallest fix: add one `# @intent <slug>` block of at most 72 columns inside each of the four functions, for example `provider-key-relays-only-through-the-gateway` on `relays` and `fallback-providers-join-the-key-matching` on `named_providers`. Rerun `python lint/run.py --rule A002` and expect 581.
  Spec IDs: FR-7, FR-11, AC-32 (§12.4 `@intent` bullet)

R-V4 [Major] [typing / strict-config-dataclasses] vidbyte/lib/dataclasses/model_configs.py:58 — the public `api_keys` annotations reject the documented list form, so mypy or Pyright flags every README example
  Evidence: The annotations:
  - `model_configs.py:58 api_keys: ProviderKeys = field(default_factory=ProviderKeys, repr=False)`
  - `agents/jev/settings.py:132`: the same, on `JevAgentSettings`
  - `agents/jev/settings.py:285 api_keys: tuple[str, ...]` (`JevRunBriefSettings`)
  - `paradigms/context_minimal_fanout/types.py:430 api_keys: tuple[str, ...]` (`AgentRoleSettings`)

  Type-checking the documented calls with `lint/mypy.ini` gives four arg-type errors:
  - `Argument "api_keys" to "TextModelConfig" has incompatible type "list[str | None]"; expected "ProviderKeys"`
  - the same error for `JevAgentSettings`
  - `... "JevRunBriefSettings" has incompatible type "list[str]"; expected "tuple[str, ...]"`
  - the same error for `AgentRoleSettings`

  `Agent(api_keys=[...])` passes, because `base.py:98` is annotated `ProviderKeys | Iterable[str | None] | None`.
  Failure: `strict-config-dataclasses.md` ("Don't cascade…") warns that a hint narrower than what callers legitimately pass "becomes dishonest at every such call site, and a strict CI mypy stage can start flagging previously-valid code". §12.4, NG-19, and D-31 say developers see only the list form, yet these annotations tell their IDE that a list is wrong and advertise `ProviderKeys`. S009 cannot see it, because it checks only `vidbyte/`.
  The implementer followed the spec here: §9.1 (spec.md:699) and §12.3 row 7 prescribe `api_keys: ProviderKeys = field(...)  # accepts a list`.
  A reviewer would write: "My editor underlines the README's own example."
  Smallest fix (needs a ruling, because §9.1 fixes the annotation):
  - Annotate the two tuple fields `Sequence[str | None]`. They are only passed to `match` or `normalize`, so no read site changes.
  - For `TextModelConfig` and `JevAgentSettings`, choose one:
    - widen to `ProviderKeys | Sequence[str | None]` and narrow at the read sites (`model_configs.py:133,147,195,210`; `jev/brief/writer.py:56`); or
    - keep the annotation and record the accepted mismatch in §17.
  Spec IDs: FR-2, NG-19, D-31

R-V5 [Major] [house style: dispatch over ladders] vidbyte/lib/dataclasses/model_configs.py:256 — `TextCredentials.__post_init__` dispatches on mode with an if/elif/else ladder whose `else` quietly gives any other mode AUTO's rule
  Evidence: `:256-261`:
  ```python
  if self.mode is TextModelMode.DIRECT:
      fits = has_provider_key and self.vidbyte_api_key is None
  elif self.mode is TextModelMode.VIDBYTE_MANAGED:
      fits = has_vidbyte_key and self.provider_api_key is None
  else:
      fits = has_vidbyte_key and (self.provider_api_key is None or has_provider_key)
  ```
  Failure: §12.4 says "Mode dispatch uses `match` with an explicit `case _:` that raises", from house style (dispatch over ladders). `credentials()` in the same file follows it (`:128-152`). A fourth `TextModelMode` member would be validated with AUTO's key rule instead of failing loudly.
  A reviewer would write: "Use the same `match` as `credentials()`."
  Smallest fix: `match self.mode:` with the three cases setting `fits`, plus `case _: raise ConfigurationError("TextCredentials.mode must be a TextModelMode value.")`.
  Spec IDs: FR-3 (§9.1 `TextCredentials`; §12.4 match bullet)

R-V6 [Minor] [AGENTS.md §5 / strict-config-dataclasses] vidbyte/lib/dataclasses/agents.py:280 — the Vidbyte-key format check and its message are copied from models.py, and the duplicate-provider message (M-7) is written out twice in provider_keys.py
  Evidence:
  - `agents.py:280-281` and `registries/models.py:208-209` are identical: `if re.fullmatch(VIDBYTE_API_KEY_PATTERN, key) is None: raise ConfigurationError(f"The managed Vidbyte API key must be a live key in the {VIDBYTE_API_KEY_PREFIX} format.", details=details)`. The `models.py` copy predates this PR, and the `agents.py` copy is new.
  - `provider_keys.py:239` and `:275` build the same f-string: "…are both {…} keys; pass one key per provider."
  Failure: AGENTS.md §5 says to write shared logic once. `strict-config-dataclasses.md` says "Two independent inline copies of the same rule drift silently." INV-26 requires the check at construction time, but not a second copy of it.
  Smallest fix:
  - Keep one owner of the check and message. Either `resolve_vidbyte_api_key` validates through `ProviderKeys(vidbyte_api_key=key)`, with a late import like `provider_keys.py` uses, or both sites use one message constant beside `VIDBYTE_API_KEY_PATTERN`.
  - Hoist the M-7 text into one `ProviderKeyMatcher` class constant used at both sites.
  Spec IDs: INV-26, D-17

R-V7 [Minor] [A001 header accuracy] vidbyte/lib/registries/provider_keys.py:4 — three headers misdescribe the finished code
  Evidence:
  - `provider_keys.py:4` ROLE names the `match` callers as "TextModelConfig, BaseAgent and AggregateAgent, JevAgentSettings, BaseAgent.restore". It omits three that also call `match`: `Runner.__init__` (`runners/utility.py:44`), `ModalityDetector._config_options` (`lib/agents/modality_detector.py:226`), and `JevRunBriefWriter` (`agents/jev/brief/writer.py:56`).
  - `runners/text.py:6` says a new mode changes "the uses_gateway branch here". There are two branches on two predicates: `:57 if self._credentials.uses_gateway:` in `__init__`, and `:91 if vidbyte_api_key is not None:` in `arun`.
  - `constants/jev.py:9` TESTS lists `tests/features/sdk_managed_text/` but not `tests/features/sdk_provider_keys/`, even though its own COMMON MODIFICATION PATTERNS (`:6`) names that pack for the new constants.
  Failure: §12.4 says to update the headers of edited files "where they describe the changed behavior" (AGENTS.md §2). The agentic-engineering obligation is "file headers accurate against the finished code".
  Smallest fix:
  - Add the three callers to the `provider_keys.py` ROLE.
  - In `text.py`, either branch `arun` on `self._credentials.uses_gateway` (narrowing the key inside) or name both predicates in the header.
  - Add `tests/features/sdk_provider_keys/` to `jev.py` TESTS.
  Spec IDs: n/a (§12.4 header bullet)

R-V8 [Minor] [comment-format] vidbyte/agents/fork.py:45 — two edited comment lines exceed 72 columns
  Evidence: A width scan of every added comment line in `git diff 595a7260...8bd1963d -- 'vidbyte/*.py'` flags:
  - `fork.py:45` (119 columns): "# Read the vendor the parent really runs on, so the backup check below sees a provider-prefixed model's vendor." This line was edited in this PR.
  - `fork.py:62` (73 columns), inside the new `@intent children-carry-the-matched-keys` block.
  The only other hits are four URL lines in `provider_keys.py`, a reported and accepted deviation.
  Failure: `comment-format.md` and the §12.4 72-column bullet: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` must print nothing for new or edited blocks.
  Smallest fix: wrap `:45` into two lines of at most 72 columns, and rewrap the `:61-64` block.
  Spec IDs: n/a (§12.4 comment bullet)

VERIFIED CLAIMS
- Claim: `provider_keys.py` is under 300 lines (NFR-4, S3). HELD: `wc -l` gives 296. It reached that by joining lines (17 lines over 200 columns). The repo has no line-length limit and already writes one-line messages and signatures, so this is not a finding.
- Claim: S014 is CLEAN and mutation-proven (S3 §6). PARTLY HELD: the rule is CLEAN, and a `jev.py`-side mutation regresses it (reproduced). Registry-side mutations pass unnoticed (R-V2).
- Claim: the D-21 import rules hold (§12.4). HELD: `python -c "import vidbyte"` and `python -c "import vidbyte.lib.registries.provider_keys"` both succeed; `agents.py` imports no registries module; every other importer uses `from vidbyte.lib.registries.provider_keys import ProviderKeyMatcher`.
- Claim: the header is stored by subscript and C017 stays CLEAN, and the header constants are used everywhere (§12.4). HELD: `vidbyte_gateway.py:183`; C017 0/0 at both base and head; `git grep` finds the header name, pattern, and 512 cap only in `constants/jev.py`.
- Claim: no baseline is raised, no suppression is added, and no rule is weakened (§12.4). PARTLY HELD: `lint/baseline.json` changes only `A001 643 → 641`, and the diff adds 0 suppressions. S014 is weakened (R-V2).
- Claim: every business rule has an `@intent` (§12.4). DID NOT HOLD: A002 584 → 585 (R-V3). All 37 added `@intent` lines carry a slug, and the row-4 slugs are present.
- Claim: mode dispatch uses `match` with a raising `case _` (§12.4). PARTLY HELD: true in `credentials()`, false in `TextCredentials.__post_init__` (R-V5).
- Claim: call chains are one level deep (§12.4). PARTLY HELD: the `match` helpers are leaves; `credentials()` is not (R-V1).
- Claim: multi-line comment blocks are at most 72 columns (§12.4). PARTLY HELD: `fork.py:45` and `:62` exceed it (R-V8).
- Claim: `base.py` grows by at most 30 net lines (NFR-4). HELD: numstat 34/8, so +26.
- Claim: the §12.5 non-code actions are done. HELD:
  - The root README, agents README, registries sources section, skills docs, and `llms.txt:1113` are updated. The extra conditional `llms.txt` sentence was correctly skipped, because "Agents and Modalities" lists no agent parameters.
  - The export is present, and the scripts pass `api_keys` (non-text configs keep `api_key`, as designed).
  - The `provider_keys.py` source comments cite only the `openai/plugins` repo root at `:42` and `:58`, where the README gives the exact file paths. That is a clarity nit, not raised.
- Claim: README examples accept the list form (FR-2). HELD at runtime, NOT under static typing (R-V4).
- Commit hygiene. HELD: one work item per commit with IDs; no generated or cache files; the secret grep of the diff's added lines finds only the documented `T3BlbkFJ` mention in docs and test comments, and no key.

COMMANDS RUN
- `env -u DEEPSEEK_API_KEY PYTHONPATH=<wt> PYTHONIOENCODING=utf-8 python lint/run.py` (HEAD 8bd1963d): `SDK-LINT: PASS`
- The same command on a scratch `git archive 595a7260` copy (with `git init` and `git add -A`): `SDK-LINT: PASS`
- `python lint/run.py --rule <R> --all --format json` for A001, A002, A006, C017, C020, S008, S009, S014, S051 and S062, at head and base, compared by `cmp.py`:
  - `== A002: base 584 head 585` (4 added and 3 removed, as listed in R-V3)
  - A001 643 → 641
  - every other rule has equal counts and sets
- S014 mutations on a scratch `git archive 8bd1963d` copy, each with `python lint/run.py --rule S014 --format json`:
  - unmutated: `exit 0 found 0 verdict CLEAN`
  - `= {}`: `exit 0 found 0 verdict CLEAN`
  - deleted: `exit 0 found 0 verdict CLEAN`
  - `= DEFAULT_TEXT_MODELS`: `exit 0 found 0 verdict CLEAN`
  - control (OPENAI row dropped from `jev.py`): `exit 1 found 1 verdict REGRESSED`
  - base with `= {}`: `exit 1 found 14 verdict REGRESSED`
  - The scratch trees were restored afterwards (`git status` shows only the staged adds).
- `python -m mypy --config-file lint/mypy.ini --no-incremental --follow-imports=silent <scratch>/probe/usage_probe.py`: 4 arg-type errors (`TextModelConfig` and `JevAgentSettings` expect "ProviderKeys"; `JevRunBriefSettings` and `AgentRoleSettings` expect "tuple[str, ...]"); the `Agent` line is clean.
- `python -c "import vidbyte"` gave ok, and `python -c "import vidbyte.lib.registries.provider_keys"` gave ok.
- `python -m pytest tests/features/sdk_provider_keys tests/test_readme_size_limit.py tests/features/sdk_managed_text -q`: `158 passed in 2.03s`
- `wc -l vidbyte/lib/registries/provider_keys.py` gave `296`. `git diff --numstat 595a7260...8bd1963d -- vidbyte/agents/base.py` gave `34 8`.
- The added-comment width scan (an awk script over `git diff -U0 … -- 'vidbyte/*.py'`) flagged:
  - `fork.py:45` (119) and `fork.py:62` (73)
  - `provider_keys.py:38` (74), `:43` (85), `:48` (77) and `:63` (85): URL lines
- `git grep -n "must be a live key" 8bd1963d -- vidbyte` finds `agents.py:281` and `models.py:209`. `git show origin/main:vidbyte/lib/registries/models.py` already has the `models.py` copy.
- `git grep` for `X-Vidbyte-Provider-Key`, `[!-~]` and `512` under `vidbyte/` matches only `constants/jev.py`, plus unrelated 512 uses.
- A grep of the diff's added lines for `type: ignore|noqa|nosemgrep|cast(` gave `0`. Generated or cache files in `git diff --name-only`: none.
- `git diff 595a7260...8bd1963d -- lint/baseline.json` gives `-  "A001": 643,` and `+  "A001": 641,`.
- Not run: `run_ci.py --stage package` and semgrep, as the brief instructs.
