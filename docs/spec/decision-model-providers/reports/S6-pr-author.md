# S6 PR author report: decision-model-providers

Stage: S6 (PR author) · Date: 2026-10-11 · Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-decision-model-providers` · Branch: `feat/decision-model-providers`

**Result**

- Draft PR https://github.com/cerredz/Vidbyte-SDK/pull/697 now has the title `feat(providers): add 15 decision-model providers beside TypeSafe Jev, priced from each vendor's own API docs`.
- It has the new body from `docs/spec/decision-model-providers/pr-body.md`, with 2 mermaid blocks and the attribution line as its last line.
- It is still a draft.
- The branch is pushed at `dd833cd5`, and the tree is clean.
- No source or test file changed.

**Commits added**

| Commit | Content |
|---|---|
| `c4fa6629` | `docs(spec): finalize decision-model-providers for PR` (`spec.md` frontmatter, the §17 row, and `pr-body.md`) |
| `dd833cd5` | `docs(spec): state the PR merge state precisely in the PR body` (one sentence of `pr-body.md`; see the note under "Final PR state") |

Both commits were staged by path only and carry the Co-Authored-By trailer.

## 1. What the code does (written from the diff, before opening the spec)

The entry point is `DecisionModelRunner(DecisionModelConfig(provider=X, ...))`.

1. **Config checks.** `DecisionModelConfig.__post_init__` (`vidbyte/lib/dataclasses/model_configs.py`) runs first.
   - The provider must be a key of `ProviderModelRegistry.DECISION_DEFAULT_MODELS`. There are 16 keys: TYPESAFE, PERPLEXITY, OPENROUTER, LIQUID, BASETEN, MERAGPT, CLOUDFLARE, FOUNDRY, CELERIS, NACE, UPSTAGE, INCEPTION, HANZO, VANSA, ZOODATA, and OPENAI. Any other provider raises `UnsupportedProviderError`, whose message lists the values sorted.
   - `VIDBYTE_MANAGED` with a provider other than TypeSafe raises `ConfigurationError`.
   - `model` now defaults to `None` and is filled from the provider's decision default.
   - `validate()` resolves the key and then the endpoint. Cloudflare and Foundry have `""` as their default endpoint, so they fail when the runner is built unless `endpoint` is passed.
   - `resolved_model()` is the typed reader. The runner uses it for `model_name()` and for the billed-failure ledger entry.
2. **Routing.** `ModelProviders.decision` (`vidbyte/providers/__init__.py`) dispatches with a dict: TYPESAFE goes to `TypeSafeProvider`, OPENAI to `OpenAIDecisionsProvider`, and the other 14 to `SystemOneProvider`.
3. **`SystemOneProvider`** (`vidbyte/providers/systemone.py`).
   - **Construction.** The constructor binds the `HOSTS` row for the config's provider. It refuses a missing config, a provider without a row, and a managed config.
   - **Config check.** `run_decision` first runs `_config_for`, which requires the same provider and refuses managed mode.
   - **Building the call.** `_call` builds a `DecisionHttpCall`:
     - the URL is `ProviderModelRegistry.resolve_endpoint(provider, config.endpoint)` plus the host path;
     - the authorization header is `"<scheme> <key>"`, and Baseten's scheme is `Api-Key`;
     - an idempotency key is created only when `retry_count > 0`, and it is never sent as a header.
   - **Sending and normalizing.** `DecisionTransport.send` applies the shared transport policy. The adapter parses the JSON and reads the usage first. `SystemOneAnswers.normalize` then requires an exact name match and a matching type tag, and maps score index keys onto level labels. The model is either the echo (on documented hosts) or the requested id (on `model_from_request` hosts).
   - **Errors.** A `ProviderResponseError` keeps the usage. A `ProviderRequestError` is rewritten with the host label, plus the env var on a 401. Anything else becomes a `ProviderResponseError`.
   - **OpenRouter.** Its row always sends noul criteria `{true, false}`, each with its description or null.
   - **Other operations.** `list_models` and `close_run` raise without a network call.
4. **`OpenAIDecisionsProvider`** (`vidbyte/providers/openai_decisions.py`).
   - It posts `{model, input, questions[]}` to `{endpoint}/decisions`. Noul becomes `predicate`, choice carries `choices[{value, description?}]`, and score carries `levels[{label, description?}]`.
   - Structured content is sent as JSON text.
   - A noul question whose options carry descriptions is refused before the call.
   - Answers are matched by `name`. A refusal, a duplicate, a missing or extra answer, a wrong type, or a malformed distribution raises an error that keeps the usage.
   - The response model is always the requested id.
5. **`TypeSafeProvider`** (`vidbyte/providers/typesafe.py`) is rebuilt on `SystemOneRequest`, `SystemOneAnswers`, the TypeSafe `HOSTS` row, `DecisionTransport`, and `DecisionFailures`. It keeps the managed headers, the managed run context, `/models`, run close, and the credential-safe managed wording.
6. **Pricing** (`vidbyte/lib/registries/pricing.py`).
   - `PRICING_AS_OF` moves from 2026-07-30 to 2026-10-10.
   - 13 decision blocks and the `gpt-6-luna` row (0.10, and 0.20 over 272K) are added. Each has first-party URLs and 2026-10-10 in its comment.
   - OpenRouter has no row, only a comment citation, because `usage.cost` is authoritative.
   - The C010 lock is refreshed.
7. **Usage.** The 13 new members are bound to `JevUsage`. `OpenRouterUsage` also parses `input_tokens` and `output_tokens`.
8. **Catalog and records.**
   - The catalog gains 13 members, registry rows, and runner-catalog rows. Inception's key comes after Baseten's, so `mercury-decide` resolves to Inception and `inception/mercury-decide` to Baseten.
   - Seven wire constants are added, plus the `DecisionAuthScheme` enum.
   - `SystemOneHost`, the OpenAI wire records, and `DecisionHttpCall` (validated) live in `vidbyte/lib/dataclasses/jev.py`.
9. **Docs and tests.** The providers README, REPO_MAP, and the jev-agent SKILL are updated. The pack has 9 Python files plus FEATURE.md and README.md, and 91 tests.

## 2. Snippet (spec §4) — real output on this branch

The snippet uses top-level `await`, so I ran it two ways without editing its text. The scripts are in my scratchpad: `section4_snippet.py` is extracted by `awk` from spec §4, and the harness scripts are `run_as_written.py`, `prelude.py`, and `postlude.py`.

**Run A: as written, no keys, no transport injected.** I compiled it with `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT` and ran it:

```
vidbyte.lib.errors.base.ConfigurationError: Missing API key for provider perplexity. Pass api_key or set PERPLEXITY_API_KEY.
```

**Run B: prelude, then the verbatim snippet, then the postlude, piped into `python -m asyncio`.** The prelude sets test keys and wraps `DecisionModelRunner` to inject a `decision_fixtures.ScriptedTransport`. This is the AC-1 setup.

```
0.8
'billing'
(<ModelProvider.PERPLEXITY: 'perplexity'>, 'pplx-decider-v1.1-27b')
mappingproxy({'true': 0.8, 'false': 0.19999999999999996})
[('perplexity', 'POST', 'https://api.perplexity.ai/v1/decisions', 'pplx-decider-v1.1-27b'), ('openai', 'POST', 'https://api.openai.com/v1/decisions', 'gpt-6-luna')]
'https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/cloudflare/clef'
```

AC-1 holds. The snippet runs as written in an async context; it is not a deviation. The PR body says to wrap it in `asyncio.run(...)` for a plain script.

## 3. Deviations (spec vs code)

The code matches spec §8.5 names and signatures, §9.1 rows, §12, and the §5 flow, so §5 was not changed.

**Recorded in spec §17 "Implementation deviations", all confirmed in the code:**

1. **C017 URL building.** Both direct adapters use `ProviderModelRegistry.resolve_endpoint(...)` (`systemone.py:326`, `openai_decisions.py:315`). `SystemOneProvider._config_for` also refuses managed mode per call (`systemone.py:311-312`). Commit `d07c328b`.
2. **OpenRouter usage.** `OpenRouterUsage._decision_usage` derives the total and is also read when the chat parse found only a total (`vidbyte/agents/pricing/openrouter.py`).
3. **Config-less construction.** `provider="systemone"` is used on config-less construction (`systemone.py:245`, with a comment at :244).
4. **Private helpers.** Both adapters have extra private helpers. `OpenAIDecisionsRequest.text` turns a `RecursionError` into a `ConfigurationError` (`openai_decisions.py:93-96`).
5. **TypeSafe label.** It comes from the host row (`typesafe.py:62`, `:137`, `:251`).
6. **SKILL.md line drift.** The edit is at line 46, not 47.
7. Superseded: the branch was merged, not rebased. The PR body leaves this out.
8. **One commit for three rows.** Rows 1, 6, and 7 share commit `8a140ba2`, because of S014 parity.

**Found myself.** INV-2 says every production reader uses `resolved_model()`. But `vidbyte/agents/jev/alignment/skills.py:130` reads `self.decision.model` directly. That line came from main (#698), and this is review R-11. It has no runtime effect, so it is a spec-wording issue only. The PR body lists it as deviation 8.

## 4. Final `gh pr view` and `gh pr checks`

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/697 --json title,isDraft,baseRefName,url,headRefOid,mergeStateStatus,mergeable
{"baseRefName":"main","headRefOid":"dd833cd575ce04ebe6fcf27bcbcf60402a2510a5","isDraft":true,"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE","title":"feat(providers): add 15 decision-model providers beside TypeSafe Jev, priced from each vendor's own API docs","url":"https://github.com/cerredz/Vidbyte-SDK/pull/697"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/697
no checks reported on the 'feat/decision-model-providers' branch
```

**Merge state.** `BEHIND` is new since the briefing. origin/main moved to `5058737a` ("fix(evals,tools): close MCP servers of internally created forks after their run (#760)") after the third integration merge.

- That commit touches `tests/test_fork_tool.py`, `vidbyte/evals/runner.py`, `vidbyte/tools/agent_tool.py`, and `vidbyte/tools/builtins/fork/fork.py`, plus 2 more files. None of them overlaps this branch (checked with `git diff --name-only`).
- I did not merge it. A merge brings source changes into the branch, and that is outside S6.
- The PR body says so, and also says that `BLOCKED` (draft plus required checks) remains even when the branch is current. That sentence is why the second commit `dd833cd5` exists.
- The remote body matches `pr-body.md` line 2 onward (checked with `diff`; the only difference is a trailing newline that jq adds).

**Gates I re-ran at `6cc53e39`, whose code is identical to `6149d9b9`:**

| Gate | Result |
|---|---|
| `python -m pytest tests/features/decision_model_providers -q` | `91 passed in 1.67s` |
| Area suite (verify-log command) | `406 passed in 3.52s` |
| `python scripts/run_ci.py` | exit 0, `3162 passed, 12 skipped in 25.90s` / `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Lint, inside `run_ci` | `SDK-LINT: PASS`, 0 REGRESSED: A006 34/34, A009 0, C002 9/9, C009 1/1, C010 0, C016 0, C017 0, S009 346/350, S014 0, S015 13/13, S051 258/259 |
| Test-contract diffs (`git diff 3943089c HEAD -- tests/features/decision_model_providers/`; other tests against merge base `57639080`) and the `lint/baseline.json` diff | 0 bytes each |

## 5. Candidate field-guide lessons (report only; not written to the field guide)

Each lesson comes from a confirmed `review.md` finding: the conventions lens, or a conformance or engineering finding that encodes a repo rule. All link to https://github.com/cerredz/Vidbyte-SDK/pull/697.

1. **New dataclass outside `vidbyte/lib/dataclasses/`** (R-2, Blocker).
   - Trigger: adding a `@dataclass` in `vidbyte/providers/` or any other layer, including renaming a legacy private record into a new module.
   - Preferred action: define it in `vidbyte/lib/dataclasses/<domain>.py` with `__post_init__` validation, keep behaviour in the owning layer as a static helper (here `DecisionTransport.send`), and re-export it from the provider module if callers import it there.
   - Project-specific reason: the AGENTS.md Placement Rules are binding, but the `agents-md-placement` workflow is `workflow_dispatch`-only, so no gate catches a misplaced record.
   - Quick check: `git diff origin/main -- vidbyte | grep -n "^+@dataclass"`; every hit sits in a file under `vidbyte/lib/dataclasses/`.
2. **Helper chains deeper than one level in a new module** (R-4).
   - Trigger: a normalizer or encoder class whose private helpers call other private helpers.
   - Preferred action: have the main function call every helper and pass resolved values (text, entries, distributions) into the next helper. An error factory that calls nothing further is allowed.
   - Project-specific reason: AGENTS.md principle 1, enforced in review for new modules. Relocated legacy code prescribed by a spec is exempt.
   - Quick check: in each `_helper` body, grep for `self._` or `ClassName.` calls to siblings.
3. **Closed set typed as `str`** (R-12).
   - Trigger: a record field validated against a fixed tuple, such as `type in ("predicate", "choice", "score")`.
   - Preferred action: an enum in `vidbyte/lib/enums/<domain>.py`, exported from `vidbyte/lib/enums/__init__.py`.
   - Project-specific reason: AGENTS.md says any field from a small closed set is an enum.
   - Quick check: grep new dataclass `str` fields whose `__post_init__` checks `not in (`.
4. **Module-level literal in a provider** (R-8).
   - Trigger: `_LABEL = "OpenAI"` or similar constants in a JEV provider module.
   - Preferred action: put the constant in `vidbyte/lib/constants/jev.py`.
   - Project-specific reason: AGENTS.md "New JEV code" says a constant goes in `constants/jev.py`.
   - Quick check: `grep -nE '^_[A-Z_]+ *(: *str)? *= *"' vidbyte/providers/<module>.py`.
5. **Error `provider=` value and duplicated refusal text** (R-7).
   - Trigger: raising `ProviderConfigurationError` before a provider is known, or repeating a refusal sentence in two guards.
   - Preferred action: comment any non-`ModelProvider` value, and hoist the sentence into one `ClassVar` so a single test pins it.
   - Project-specific reason: callers branch on `error.provider`, and tests pin exact messages.
   - Quick check: `grep -n 'provider="' vidbyte/providers/*.py`.
6. **Generalizing a single-provider module** (R-9).
   - Trigger: a module that served only TypeSafe now serves many providers.
   - Preferred action: rewrite the header's PURPOSE, ROLE, and TESTS lines and the main-function narration in the same commit.
   - Project-specific reason: A001 checks only that the header fields exist, and agents read headers first.
   - Quick check: grep the touched headers and comments for the old single-provider wording.
7. **Pipeline IDs in production comments** (R-10).
   - Trigger: writing code comments while a spec exists under `docs/spec/`.
   - Preferred action: state the reason inline, without `D-12`, `Q-11`, "spec section 9.1", or "research §3.4".
   - Project-specific reason: AGENTS.md makes `docs/` opaque to agents, so such an ID is a dead end.
   - Quick check: `git diff origin/main -- vidbyte | grep -nE '^\+.*(\b(D|Q|INV|AC|EC)-[0-9]+\b|research §|spec section)'`.
8. **Bool guards for `timeout_seconds` and `retry_count`** (R-18, plus the C002 trap recorded in review.md).
   - Trigger: validating a numeric parameter that already has `isinstance(x, bool)` guards elsewhere.
   - Preferred action: reuse `JevCount.require` for counts. For timeouts, write `type(x) is bool or not isinstance(x, (int, float))`, never `type(x) not in (int, float)`, which refuses subclasses that `DecisionModelConfig` accepts.
   - Project-specific reason: C002 groups inline bool guards by parameter name across files (baseline 9). The exact-type spelling broke INV-23 for subclass timeouts.
   - Quick check: `python lint/run.py --rule C002`, plus a probe with `class Seconds(float)`.
9. **A credential guard needs a test that fails when the guard is deleted** (R-3).
   - Trigger: a guard that stops a key from reaching the wrong host, such as a per-call managed-config refusal.
   - Preferred action: a test that asserts the exact refusal and `transport.requests == []`.
   - Project-specific reason: a mutation run showed `SystemOneProvider`'s per-call refusal was unguarded, and deleting it posted a `vb_live_` key to `api.typesafe.ai`.
   - Quick check: delete the guard locally; the pack must go red.
10. **Every new env var is named in the folder README** (R-6).
    - Trigger: adding entries to `ProviderModelRegistry.API_KEY_ENV_VARS`.
    - Preferred action: list each variable in `vidbyte/providers/README.md` "Decision Providers" (or the matching section) within A009's size ceiling.
    - Project-specific reason: the README is the documented contract index for providers.
    - Quick check: grep the README for each new variable name.

## 6. Things that looked wrong while reading (no code changed)

- **Coverage narrower than its name.** `tests/features/decision_model_providers/test_decision_acceptance.py:84-90`: `test_changing_the_provider_changes_nothing_else` loops over `fx.HOST_ROWS`, which has 9 providers (TYPESAFE, PERPLEXITY, OPENROUTER, LIQUID, BASETEN, MERAGPT, CLOUDFLARE, FOUNDRY, OPENAI). It does not cover the seven r8 hosts, and its comment says "all nine providers". This is not vacuous: the r8 hosts are covered by `test_each_host_posts_the_typesafe_body_to_its_documented_url` (AC-20). But the §4 "change provider and nothing else" property is pinned for 9 of the 16 providers only. A follow-up test grant could iterate `fx.ALL_HOST_ROWS`.
- **Inaccurate shared message.** `vidbyte/providers/systemone.py:293`: Nace.AI's `alist_models()` message says the host "publishes no model-list endpoint", which is untrue for Nace. This is spec Q-11 and a known limitation, not a new bug.
- No other bug, dead code, or vacuous test found in the files read.

## 7. Notes on the briefing

- **Minor count.** The briefing says "15 Minors", but `review.md` lists 14 (R-5 to R-17 and R-19): 4 fixed (R-6, R-7, R-16, R-19) and 10 follow-ups. The PR body uses 14.
- **Unverified pricing claim.** The `gpt-5.6-sol` claim ("differs from OpenAI's current page") comes from the briefing. I did not verify it, because `context/pricing-proof.md` is not on my read list. The PR body attributes it to "this PR's price research". The `clef-omni` $0.150 figure is backed by spec Q-12.
- **Body file location.** I wrote the temporary `pr-body.md.body` file to my scratchpad instead of the worktree, so the tree stayed clean. The content is the same as the briefing's script.
