# Feature: A reasoning effort for an agent's generative model

## High-Level Feature Description

`reasoning_effort` (a `ReasoningEffort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`) is one provider-neutral setting on `TextModelConfig`, `BaseAgent` and `JevAgentSettings`. On a `TextModelMode.DIRECT` call, each provider adapter sends it in that vendor's documented wire form, deep-merged into the body it already builds. Construction refuses, before any request, an effort the SDK's table has no documented form for, a gateway mode, an effort beside `thinking_config` or an overlapping `extra_body`, and any value outside the six. Unset, nothing changes. The same change root-exports `ReasoningEffort`, `DecisionModelConfig` and `DecisionModelMode`.

## Contract

- `ReasoningEffort` is a `StrEnum` with exactly the six members, in that order, defined in `vidbyte.lib.enums.text_model`, exported from `vidbyte.lib.enums` and from the root (FR-1, INV-12).
- `ReasoningEffortRegistry.supported(provider, model)` returns, for every spec section 9.2 line, exactly that line's "sent" values in enum order, after the `"{provider}/"` prefix strip, the alias and lower-casing; it returns `()` for a "refused (all)" line and for any id with no row (INV-20, AC-18).
- Every "sent" cell puts exactly its section 9.2 fragment into the vendor body, deep-merged, and changes nothing else: not the URL, not the headers, not the key (INV-2, INV-9, AC-2, AC-3, AC-20). Anthropic's `output_config.format` and Gemini's `generationConfig` keys survive (AC-14, AC-15).
- Every refusal is a `ConfigurationError` raised at construction with the section 8.5 text, character for character, and zero HTTP requests (INV-4, INV-11, AC-4, AC-5, AC-7, AC-10, AC-16).
- Every fallback-chain entry is checked, in either order; a capable chain sends each hop's own provider form (INV-6, AC-6).
- The effort survives export and restore, forks, ContinualTrace and Handoff side agents, and reaches the JevAgent main agent, its fresh continuation and its eight children; it never reaches the brief writer, specialists or decision calls (INV-14, INV-15, AC-9, AC-11, AC-12).
- Unset sends nothing and writes no checkpoint key (INV-1, AC-8, NFR-1); billed reasoning tokens reach `UsageRollup` as before (INV-10, AC-17).

## Actors / Callers

SDK developers who construct `Agent`, `BaseAgent`, `TextModelConfig`, `TextModelRunner`, `StreamingTextModelRunner` or `Runner`; vidbyte-cli C5, which maps `--reasoning-effort` onto `JevAgentSettings` and relies on the section 8.5 texts; vidbyte-cli C4, which imports `DecisionModelConfig` and `DecisionModelMode` from the root; a model that drives the fork tool to another model.

## Inputs and Preconditions

A provider, a model id, a mode, an effort value (member, plain string, another enum's member, or a bad value), optionally a fallback chain, `thinking_config`, `extra_body`, `output_schema` and `temperature`. Every test runs offline. The only fake is the network: `HttpTransport.request` (or the transport handed to a runner) is replaced by `Wire`, which answers each vendor in its own response shape; Jev's delegated path also fakes `TypeSafeProvider.run_decision`, as R3's pack does. Provider keys are built at run time from parts and every real `*_API_KEY` variable is removed.

## Observable Outcomes

The recorded request URL, headers and JSON body of every call; the constructor's exception type, `str(error)` and `error.details`; `runner_config.reasoning_effort` and the record fields; `export_state().runtime_config`; the fork tool's `ToolResult`; `agent.get_usage()` output tokens and `cost_usd`; the one line the section 4 snippet prints.

## State Transitions

The value is converted once at the first record that receives it, checked at construction, then immutable. It is copied, never recomputed, into forks, side agents, restored agents and Jev children; each copy's own construction re-checks it against that copy's model.

## Invariants

- For every sent cell, `body(effort) == deep_merge(body(unset), fragment)`, with the URL and headers unchanged (an algebraic identity checked exhaustively over the table, not sampled).
- Refusal order: mode before capability; in `TextModelConfig`, conversion, then mode or capability, then `thinking_config`, then the `extra_body` overlap; R3's spend-cap refusal before the effort guard.
- `attach` never mutates or aliases the module tables (INV-13).
- A later table row never turns this pack red: no test pins the table's size or key set.

## External Dependencies

None at test time. `REASONING_EFFORT_AS_OF`, the pricebook and the provider catalog are read from the SDK at run time, never copied into a test.

## Known Failure Modes

| Spec ID | Input + state | Wrong output without the guard |
|---|---|---|
| AC-1 | the section 4 snippet run as written | the planner's body lacks `reasoning.effort`, the refusal prints differently or after a Gemini call, or `jev`'s Messages body lacks `output_config.effort` |
| AC-2, AC-3, INV-2, FR-4 | any sent cell, through any of the four payload builders | one builder never calls `attach`, so that vendor silently runs at its default |
| AC-3 | a Gemini level | the level is sent lower-case and the vendor answers 400 |
| AC-20, D-4, EC-3 | `medium` on DeepSeek, `xhigh` on grok-4.5 | a remapped or nearest level is sent and billed |
| AC-14, EC-6, D-7 | Anthropic structured output with an effort | a shallow `update` replaces `output_config`, erasing `format` |
| AC-15 | Gemini with `temperature` and a schema | a shallow `update` replaces `generationConfig`, erasing the temperature and schema |
| INV-13, EC-27 | two payloads attached in one process | the table's fragment object is shared and one caller's mutation leaks into every later call |
| AC-4, EC-2, EC-4, INV-20 | each refused cell, on each carrier | a 400 after a paid call, or the no-row text where the capability text belongs |
| AC-4, EC-10, EC-23, EC-24 | an id with no row | a nearest-row guess is sent, or the text omits `REASONING_EFFORT_AS_OF` and the README sources pointer |
| AC-5, EC-1, INV-5 | an effort with the default `AUTO`, explicit `AUTO` or `VIDBYTE_MANAGED` | the gateway answers 422 after admission, or the effort is silently dropped |
| AC-5 | `TextModelConfig` on GLM, Meta or a custom endpoint in a gateway mode | the existing `UnsupportedProviderError` or endpoint refusal is replaced by the effort text |
| AC-6, INV-6, EC-5 | a bad primary before a good fallback, or the reverse | the bad hop pays for a failed call every turn, or a hop is skipped by the guard |
| AC-6 | a capable chain whose first hops fail | a hop's runner is built without the effort, or with the primary's form |
| AC-7, INV-7, EC-7, EC-8 | `thinking_config` (even `{}`) or an overlapping `extra_body` beside an effort | `payload.update` overwrites the fragment, or two thinking controls reach the vendor |
| AC-10, INV-8 | `"max"`, `""`, `"HIGH"`, `3`, `GrokReasoningEffort.MAX` | the value is sent raw, or case-folded |
| AC-10 | `"high"` or `GrokReasoningEffort.HIGH` | the foreign member is stored as is and leaks its type into the wire or the checkpoint |
| AC-16, EC-9 | an effort on an image model's `Runner` | the option is filtered out and dropped silently |
| EC-22 | an effort on an agent with no provider or no model | the effort is accepted and never checked or used |
| EC-21, AC-18 | a slug, an alias, padding or upper case in the model id | support is looked up for the raw id and a supported model is refused, or the message names a rewritten id |
| INV-18 | an effort on an unpriced model under a spend cap | the effort text replaces R3's spend-cap refusal |
| AC-8, NFR-1, INV-1 | any provider and mode with the effort unset or explicitly `None` | a key such as `reasoning: {"effort": null}` is sent, or a checkpoint gains a key |
| INV-17 | `thinking_config` with no effort | the old forwarding stops |
| AC-9, INV-15 | each Jev child on the main model | one child is built without the effort and runs at the vendor default |
| AC-9, INV-15, EC-20 | the brief writer, a specialist, a decision call | Jev's effort leaks into a call that has its own settings or into the TypeSafe gateway |
| AC-11, INV-14, EC-18, EC-29 | export then restore; an old checkpoint; a stored value the table no longer allows | the restored agent runs at the default, an old checkpoint fails, or a stale value is sent |
| AC-12, EC-19, T-2, D-16 | `fork()`, a fork to an incapable model, the fork tool | the child drops the effort, or a model-chosen fork sends an unsupported effort |
| FR-8 | `ContinualTraceAgent` and `HandoffAgent` built from a source agent | the side agent runs at the default effort |
| AC-17, INV-10 | a reply that reports reasoning tokens | reasoning spend misses `UsageRollup` and R3's cap |
| AC-13, INV-12 | the three root names | a copy instead of the defining object, a stale contract, or a second header bullet |

## Historical Regressions

None yet: the pack was written before the feature existed (spec r3, stage S2), from the approved spec alone.

## Test Suite Map

- `test_agent_reasoning_effort_acceptance.py`: AC-1 (the section 4 snippet, run as written).
- `test_agent_reasoning_effort_contract.py`: AC-13, FR-1, FR-3 exports, INV-12, the section 8.5 signatures, `REASONING_EFFORT_AS_OF` and the README sources section the no-row text points to.
- `test_agent_reasoning_effort_registry.py`: INV-20 (table-driven, plus the structural invariant), AC-18, INV-13, the section 8.5 registry texts and their order.
- `test_agent_reasoning_effort_wire.py`: AC-2, AC-3, AC-6 (capable chain), AC-7 (disjoint `extra_body`), AC-14, AC-15, AC-20, EC-21, INV-9, INV-17, streaming and `Runner`.
- `test_agent_reasoning_effort_refusals.py`: AC-4, AC-5, AC-6 (refusals), AC-7, AC-10, AC-16, AC-18, EC-22, INV-18.
- `test_agent_reasoning_effort_copy_paths.py`: AC-11, AC-12, EC-18, EC-19, INV-14, FR-8.
- `test_agent_reasoning_effort_jev.py`: AC-9, INV-15, EC-20.
- `test_agent_reasoning_effort_unset.py`: AC-8, NFR-1, INV-1.
- `test_agent_reasoning_effort_usage.py`: AC-17, INV-10, NFR-5.
- `agent_reasoning_effort_fixtures.py`: the section 9.2 oracle tables, the section 8.5 text builders, `Wire`, `StreamWire` and the agent builders.

Run with `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort`.

## Omitted Testing Strategies

- No live vendor call: the wire forms are the spec's section 9.2 quotes, and a network test would be nondeterministic and need real keys. A-4 (grok-4.5 and grok-4.6 on chat completions) is an assumption the pack does not try to prove.
- No property-based library: Hypothesis is not installed, and the table is finite, so the deep-merge identity and the refusal texts are checked exhaustively over every cell instead of sampled.
- No golden files: every "unchanged" claim compares two builds made in the same test run.
- No test pins the table's size, its key set, `REASONING_EFFORT_AS_OF`'s value, the export count or the package version, so a later sourced row or release keeps the pack green.
- No test that the per-hop effort survives restore (D-6), and none for Q-1 to Q-10: the spec states them as limitations or leaves them unbuilt.
- No test of the pre-existing vendor behaviors the spec accepts as limitations (EC-11 to EC-17, EC-25, EC-26): they need a live vendor.
- The release record (AC-19) lives under `docs/`, which these tests must not read; it is left to review.
- No timing test for NFR-2: zero requests per refusal is asserted instead of a duration.
