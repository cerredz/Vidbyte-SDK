# S2 test author report: agent-reasoning-effort

Spec: `docs/spec/agent-reasoning-effort/spec.md` r3 · Base: `92e13da8` · Plan: `docs/spec/agent-reasoning-effort/test-plan.md`

## 1. What was produced

- **The pack** `tests/features/agent_reasoning_effort/`:
  - `FEATURE.md`, `README.md` (its File Index matches the folder, S020), and `agent_reasoning_effort_fixtures.py`;
  - nine test files: `acceptance`, `contract`, `registry`, `wire`, `refusals`, `copy_paths`, `jev`, `unset`, `usage` (each is `test_agent_reasoning_effort_<aspect>.py`);
  - no `__init__.py`;
  - A001 headers on every `.py` file.
- **Size.** 61 test functions, which give 655 collected cases. Most of the cases come from sweeping the §9.2 table: 198 sent cells, 120 refused cells and 35 no-row cases. These sweeps replace Hypothesis, which is not installed, and cover the table exhaustively.
- **The three layout-pin appends §13 assigns**, and no other edit to an existing test:
  - `tests/features/sdk_managed_text/test_managed_text_selection.py:57`;
  - `tests/features/sdk_provider_keys/test_provider_keys_contract.py:130` (`AgentRunnerConfig`) and `:132` (`JevAgentSettings`).
- **Records:** `test-plan.md`, the Proof cells in spec §6.2 (one per AC; AC-19 reads "not tested", with the reason), and this report.

## 2. Inventory: input + state → the wrong output if unguarded

The spec IDs come first, then my additions. Each entry names the test that holds it; the coverage map in test-plan.md gives the level and the reason it cannot pass vacuously.

**Wire (INV-2, INV-9, AC-2, AC-3, AC-14, AC-15, AC-20, FR-4).**
- Any sent cell gives a body that differs from `deep_merge(unset, fragment)`. Causes: a builder that skips the attach, a shallow `update` that erases `output_config.format` or `generationConfig.temperature`, a case-folded Gemini level, a remapped DeepSeek `medium`, or another provider's field.
- The effort moves the URL, the headers or the key.
- The tests: `wire` sweep, the agent path for 7 providers, AC-14 (Anthropic schema), AC-15 (Gemini temperature and schema), streams, Runner xAI, and normalized ids.

**Refusals (INV-3 to INV-8, INV-11, INV-20, AC-4 to AC-7, AC-10, AC-16, EC-1 to EC-5, EC-9, EC-10, EC-22 to EC-24).**
- A refused cell or a no-row id constructs, sends a request, or gives a text other than §8.5.
- A gateway mode (the default AUTO, explicit AUTO, or VIDBYTE_MANAGED) carries the effort.
- A chain entry anywhere in the chain is not checked.
- `thinking_config` or an overlapping `extra_body` is accepted.
- `"max"`, `""`, `"HIGH"`, `3` or `GrokReasoningEffort.MAX` is accepted.
- An image Runner drops the effort.
- An agent with no provider or no model keeps an effort it can never use.

**Copy paths (FR-8, INV-14, AC-11, AC-12, EC-18, EC-19).**
- A checkpoint loses the effort, or stores a member that breaks JSON.
- An old checkpoint raises.
- A stale stored value is restored silently.
- A plain fork drops the effort; a switched fork to an incapable model builds anyway.
- The fork tool raises, or sends a request.
- A ContinualTrace or Handoff side agent drops the effort.

**Jev (INV-15, AC-9, EC-20).**
- Any one of the 10 agents on Jev's model omits the effort. They are: main, fresh continuation, run state, run-state relation, done handoff, reviewer, clarification, bulk worker, clone, swarm.
- The brief writer, a decision call or a specialist inherits the effort.

**Unset (INV-1, AC-8, NFR-1, INV-17).**
- Explicit `None` differs from the omitted argument, on 7 DIRECT providers and on the gateway modes for gateway providers.
- An effort field appears with nothing set.
- The checkpoint gets a `reasoning_effort` key.
- `dataclasses.replace(config, reasoning_effort=None)` differs from a never-set config.
- An explicitly unset JevAgent differs from the default one.
- `thinking_config` forwarding changes when no effort is set.

**Usage (INV-10, AC-17, NFR-5).** With the effort, `output_tokens` or `cost_usd` differ from the same reply without it, across 7 usage shapes.

**Contract (INV-12, INV-19, AC-13, FR-1, FR-3, NFR-4).**
- A root name is a copy, not the same object.
- An import works only after other imports.
- The contract is stale.
- The root header has two bullets.
- A carrier parameter is positional or has a non-None default.
- The guard's signature differs from the spec.
- The registry re-exports copies of the tables.
- `REASONING_EFFORT_AS_OF` is not an ISO date, or the README sources heading is missing.

**Ordering (INV-18, my additions).**
- The guard runs before the spend cap.
- The capability reason comes before the mode reason.
- A conversion or capability error comes after the thinking error.
- A repeated bad hop is listed twice.

**My additions beyond the spec's IDs:**
- **Boundaries:** the empty string and a blank-only model id (`ConfigurationError`); a padded upper-case id `" GPT-5.5 "` on all three carriers; a non-string value `3`; a foreign enum's member, accepted when its value is one of the six (Grok `HIGH`) and refused when it is not (Grok `MAX`).
- **Duplicates and order:** a repeated bad hop gives its reason once; two bad hops are reported in chain order.
- **Concurrency (EC-27):** two payloads share no dict object, and writing to one leaves the table equal to a deepcopy taken before.
- **Partial failure:** each fallback hop is driven by a real HTTP 500, so each hop's own request is observed.
- **Hostile input:** a model-chosen fork, and the fork tool's schema offering no effort (T-2); keys never in a message or a body (T-3).
- **Unset path:** see Unset above.
- **The §4 snippet, run literally:** AC-1.

## 3. Pruned, and why

The table "Tests deliberately NOT written" in test-plan.md has the full list. The items cut while writing were these:
- an enum-order test that re-proved the contract test;
- a README path-string assertion (brittle; the no-row template already holds the pointer text);
- a "payload unchanged after an attach refusal" assertion (§8.5 does not promise it).

The unset key check was narrowed from a sweep of every nested key to the fragment locations: top-level `reasoning`, `reasoning_effort` and `thinking`, `output_config.effort`, and `generationConfig.thinkingConfig`, in the body or in the gateway's `body["body"]`. A whole-body sweep would turn red on unrelated keys with the same names nested inside tool schemas.

Not written at all:
- AC-19 (it lives under `docs/`);
- INV-16 (already pinned by an existing test that must pass unedited);
- byte equality with `base_commit` (needs `git show`);
- the table size or key set (forbidden);
- NFR-3, NFR-4 and NFR-7 (lint or review facts);
- EC-11 to EC-17 and EC-29 (vendor behavior, or an older SDK);
- D-6 per-hop restore, Q-1 to Q-10 and A-4 (excluded by the prompt).

## 4. Red run (exact)

```
$ cd C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-reasoning-effort
$ PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort
655 errors in 4.19s
  365 × ImportError: cannot import name 'REASONING_EFFORT_AS_OF' from 'vidbyte.lib.configs'
  263 × ImportError: cannot import name 'ReasoningEffort' from 'vidbyte.lib.enums'
   15 × ImportError: cannot import name 'ReasoningEffort' from 'vidbyte'
   12 × ImportError: cannot import name 'GEMINI_THINKING_BUDGET_OFF' from 'vidbyte.lib.configs'
```
Per file: acceptance 1, contract 12, copy_paths 10, jev 14, refusals 214, registry 151, unset 21, usage 7, wire 225. Every error is a setup error: a module-level guard holds the `ImportError`, and an autouse fixture raises it. The pack still collects, and so does the whole tree (`8360 tests collected`).

Area suite (sdk_managed_text, sdk_provider_keys, loop_spend_cap, jev_cli_root_exports, and the Gemini, compatible, DeepSeek, pricing and Jev agent tests): `2 failed, 418 passed in 5.53s`. Both failures are the pins, red only because of `'reasoning_effort'`.

Lint, run read-only on the staged pack:
- `lint/run.py` (all rules): `SDK-LINT: PASS`;
- `ruff check` and `ruff format --check`: clean.

The first full lint run showed S062 REGRESSED (891 against an allowance of 889). Two adjacent-literal strings in my files caused it, and I merged each into one literal.

## 5. Satisfiability and mutant check (scratch only, never in the worktree)

To make sure the pack can turn green and kills the S4 mutants, I built a throwaway prototype of §12 in a scratch copy of the repository: `…/scratchpad/r2proto`, a separate git repository that is never pushed. It holds the three new modules and the call-site edits for every §12 row. Against it:
- the pack ran `655 passed in 2.50s`;
- the area suite plus the pins ran `420 passed`.

Each of 35 seeded mutants failed at least one test. All counts are failing test cases:

| Mutant | Failing cases |
|---|---|
| drop attach in the OpenAI, Anthropic, Gemini or compatible builder | 82, 67, 33, 59 |
| shallow merge | 10 |
| alias the table | 11 |
| remap DeepSeek `medium` to `high` | 8 |
| guard skips the primary hop | 2 |
| guard skips the last hop | 4 |
| no dedup of reasons | 2 |
| guard runs before the spend cap | 1 |
| guard removed | 194 |
| capability checked before mode | 141 |
| Runner drops the option | 32 |
| Runner does not refuse a non-text runner | 1 |
| primary runner drops the effort | 31 |
| a fallback hop drops it | 1 |
| no export | 1 |
| `None` exported when unset | 2 |
| no restore | 2 |
| fork, continual trace or handoff side agent drops it | 5, 1, 1 |
| thinking_config refused only when truthy | 2 |
| no overlap check | 6 |
| each of the 9 Jev child skips | 1 or 2 each |
| brief writer inherits the effort | 1 |

The prototype encodes my reading of the spec. Its passing does not prove that the spec texts are right. It proves only that the pack is satisfiable and that its oracles are not vacuous.

## 6. Fixtures added (`agent_reasoning_effort_fixtures.py`)

- **The oracle tables, from §9.2 text and never from production:**
  - `SENT`, which gives each line's sent values in enum order;
  - `ALIASES` (`gpt-5.6` maps to `gpt-5.6-sol`);
  - `NO_ROW`, the ids with no row:
    - "refused (all)" lines such as `o3` and `gemini-2.5-pro`;
    - snapshot and dated ids: `gpt-5.5-2026-04-23`, `claude-opus-4-7`, `gemini-3.5-flash-001`;
    - `deepseek-chat`, `deepseek-reasoner` and `claude-mythos-preview`;
    - `kimi`, and an `openrouter` slug;
    - older xAI and GLM ids;
  - `REPRESENTATIVE`, `GATEWAY_PROVIDERS`;
  - `fragment(provider, value)`;
  - `sent_cells()` and `refused_cells()`.
- **The §8.5 text builders:** `capability_reason`, `no_row_reason` (its date is passed in from `REASONING_EFFORT_AS_OF`), `mode_reason`, `guard_text`, `identity_text` and `bad_value_text`.
- **Oracle helpers:** `deep_merge`, the test's own merge rule, and `nested_keys`.
- **`Wire`:** it stands in for `HttpTransport.request`, records each request as `{method, url, headers, json_body}`, and answers each vendor in its own reply shape with a usage block. Per-provider failure statuses drive fallback hops and single-request Jev children. TypeSafe decision URLs get 500, and Jev's gates fail open. `StreamWire` is the streaming version.
- **Keys:** `provider_key` builds a provider-shaped key from parts at run time (the repo has GH013 push protection), and `clear_provider_environment` unsets every `*_API_KEY` and `VIDBYTE_API_KEY`.
- **Builders:** `direct_agent` (`planner`, DIRECT), `run_agent` and `first_request`.
- **Nothing existing was extended.** The pack reuses `tests.test_jev_usage_ledger._answer` for the specialist delegation path.

## 7. Spec defects and hard spots (for the orchestrator)

1. **The §8.5 Runner text has a grammar slip.**
   - `"… resolves to a {runner_type} runner …"` renders as `resolves to a image runner`.
   - The test pins it character for character, as NFR-6 requires.
   - If S1 changes the template to "an", S2 must update `test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it`. The implementer must not change it alone.
2. **The `model` value in the TextModelConfig refusal details is not defined.**
   - §8.5 lists the `model` key but does not say whether it holds the raw id or the stripped one.
   - AC-18 says the message names the model "as given, stripped", so the pack compares `details["model"]` with the stripped id.
   - S1 should confirm this. If the raw id is intended, one helper (`_assert_carrier_texts`) changes.
3. **AC-18 and EC-21 differ for a slug at the agent level.**
   - With `provider=None` and `model_name="anthropic/claude-sonnet-5"`, D-5 makes the guard use `Runner._normalize_provider_and_model`. That gives the pair `anthropic:claude-sonnet-5`, the normalized id.
   - AC-18 says the message names the model "as given".
   - The pack checks only the `anthropic:` prefix and the supported list at the end of that message, so it stays neutral.
   - At the registry level (`provider="anthropic"`, `model="anthropic/claude-sonnet-5"`), the pack expects the given id, `anthropic:anthropic/claude-sonnet-5`.
   - S1 should state which form the agent-level text uses.
4. **INV-20 against the prompt's rule.**
   - INV-20 says the table holds "exactly" the §9.2 ids, but the prompt forbids freezing the key set.
   - The pack proves every §9.2 line through `supported()`, plus structural rules over all rows. Each row must be lower case, a catalog text id, and a non-empty tuple in enum order, and every value must have a form.
   - So an extra, unsourced row that satisfies those rules would not be caught. That is a review check under NFR-4.
5. **AC-8 says "equal base_commit's"**, but a test cannot read `base_commit`, because `git show` and merge-base are forbidden. The pack proves the same fact another way: explicit `None` gives the same request as an omitted argument, and no fragment field appears.
6. **Not a defect, but a tooling quirk for S3: ruff I001 and S051.**
   - Ruff classifies a not-yet-existing first-party submodule (for example `vidbyte.lib.configs.reasoning_effort`) as third-party, so a guarded import of it adds an I001 finding. S051 has zero slack.
   - The pack therefore imports from existing packages (`vidbyte.lib.configs`, `vidbyte.lib.registries`, `vidbyte.lib.enums`, `vidbyte`) and loads the new modules with `importlib.import_module` inside the tests.
   - S3 must export the names from those package `__init__` files.
7. **Not a defect: S062 counts tests too.** The implicit string concatenation ratchet is global (allowance 889), so S3 must not add adjacent string literals anywhere.
8. **The pin in `test_provider_keys_contract.py` checks `AgentRunnerConfig` before `JevAgentSettings`.** The `:132` append shows red only after the `AgentRunnerConfig` field lands. The prototype run shows that both pass once both fields are appended last.

## 8. Not touched

- No production code.
- The inherited reds in `tests/features/harness_threads/test_harness_threads_surface.py` (`:309`, `:270-278`) are neither relied on nor edited.
- No install, no `run_ci.py`, no network, no sleeps, no push.
