# S1 spec review 3 — decision-model-providers r7

Scope: r6 → r7 diff and the briefing's ID list. Read-only review; repo state at `e885f9c8` (worktree), `c090d219` (r7 spec commit), merge base `6b7ba7c3`, `origin/main` `868ff97f` as fetched locally (not re-fetched).

VERDICT: SOUND WITH FIXES — r7's catalog, pricing, INV-30 ordering and the P5/C010 plan hold against the code, but the new echo-host list reached INV-27/D-17/§9.1 and not EC-19, §13 or A-13, several header and comment edits are under-specified, and one price-proof URL was never read by the research.

## WHAT THE SPEC GETS RIGHT

- INV-30 matches the code exactly. `ProviderModelRegistry.provider_for_model` walks `MODEL_PROVIDER_RUNNER_TYPE_MAP` in insertion order and matches on the model part after the first `/` or on the whole key. `baseten/inception/mercury-decide` is at `runners.py:178`, so a later `inception/mercury-decide` key gives `"baseten"` for the qualified id and `"inception"` for `mercury-decide`. EC-34's refusal of `(INCEPTION, "inception/mercury-decide")` follows from `validate_provider_model_pair`'s owner check.
- The pricebook plan passes lint:
  - Every r7 default resolves under C009's `PricingLookup` (exact or `normalize_model`), so the baseline stays MISTRAL only.
  - The `gpt-6-luna` long-context tier works with `output_over_threshold_per_million=0.0`, because `effective_rates` tests `is not None` and uses a strict `>` (`vidbyte/agents/pricing/base.py:124-149`).
  - One C010 `--refresh-lock` in P5 is enough: the lock is at vintage 2026-07-30 with no decision entries, and comment lines change no digest.
- The seven new HOSTS rows match research-2 §3.1.1–§3.1.7 cell by cell: endpoint, path, Bearer auth, env var (including `VANSA_KEY`), default model, rate and echo flag. The §8.4 counts also add up: 16 providers, 15 HOSTS rows, 13 env vars, 13 pricing blocks, 3 adapters.
- Scope stays tight:
  - D-19 adds no adapter, `SystemOneHost` field, constant, file or dependency.
  - NG-17…NG-24 and Q-11…Q-16 default to "not built".
  - `test_decision_contract.py:61-69` checks `WIRE_CONSTANTS` with `assertIn` on `__all__`, so the r7 design breaks no S2 constant test.

## FINDINGS

R-15 [Major] [L9] §6.3 EC-19, §13, §15 A-13 — r7 changed which hosts must echo `model`, but three sections that S2 builds tests from still say "TypeSafe and Perplexity only"
  Evidence:
  - INV-27 (spec line 192), D-17 (line 335) and the §9.1 rows (lines 534-541) set Celeris, Nace.AI, Inception, Hanzo and Vansa to `model_from_request=False`. For those hosts the echo is reported, and a missing echo raises `ProviderResponseError`.
  - EC-19 (line 254) still says "TypeSafe and Perplexity (`model_from_request=False`): `ProviderResponseError` …; every other host and OpenAI: the echo is ignored".
  - §13 "Observable facts" (line 796) says "the echo for TypeSafe/Perplexity, the request id elsewhere".
  - A-13 (line 821) says "No other host's echo is relied on (INV-27, D-17)", and its "If wrong" clause covers only Perplexity.
  Failure:
  - An S2 test written from EC-19 or §13 sends a Celeris, Nace, Inception, Hanzo or Vansa response with no `model` and expects `response.model == config.resolved_model()`. S3 builds from INV-27 and the HOSTS rows, so it raises `ProviderResponseError` instead.
  - Resolving that in the test's favour (flipping those rows to True) breaks pricing for alias callers. For example, `drex-latest` or `vansa` would be recorded as `response.model`. Neither is a prefix-match for the `drex-v1.5` or `vansa-3.4` row, so the call records `cost_usd=None`.
  - The five new echo assumptions also have no stated fallback.
  Smallest fix:
  - EC-19 → "the seven `model_from_request=False` hosts (TypeSafe, Perplexity, Celeris, Nace.AI, Inception, Hanzo, Vansa): `ProviderResponseError` with usage; the eight True hosts and OpenAI: echo ignored, `response.model = config.resolved_model()`".
  - §13 → "the echo for §9.1's seven `model_from_request=False` hosts, the request id elsewhere".
  - A-13 → extend the assumption to the five r7 hosts, citing research-2 §3.1.1, §3.1.2, §3.1.4, §3.1.5 and §3.1.6, with the same "If wrong" fix: flip that host's one HOSTS cell.

R-16 [Major] [L8] §12.3 rows 11, 13, 18 — the r7 edit lists leave header and comment lines that r7 itself makes false
  Evidence:
  - `vidbyte/providers/systemone.py`: row 13's r7 text changes only the ROLE line and then says "Nothing else changes". r7 makes four more lines false:
    - line 3 (PURPOSE) still names only the seven r6 hosts;
    - line 8 (RELATED DOCS) lists only r6 vendor URLs;
    - line 6 (COMMON MODIFICATION PATTERNS) says a new host needs "a path constant in `vidbyte/lib/constants/jev.py`", but r7 adds none (D-19);
    - the comment above HOSTS at line 208, "TypeSafe and Perplexity document the `model` they echo, so every other row prices the requested id", becomes false once five more rows are False.
  - `vidbyte/agents/pricing/typesafe.py`: row 11's r7 text names only "header lines 13-14". Line 4 (PURPOSE) also lists "(Perplexity, Cloudflare, Foundry, Liquid, Baseten, meraGPT)", and line 5 (ROLE) says "the six other System One hosts".
  - `vidbyte/providers/README.md:586`: r7's A-2 (line 810) now verifies `total_tokens`, but this row still reads "OpenAI (Decisions) | `usage` | `input_tokens` | `output_tokens` | — (spec A-2)", and row 18 does not touch it.
  Failure: S3 follows the row text literally. It ships headers whose PURPOSE and ROLE lines disagree, and a HOSTS comment that contradicts the rows beneath it. This breaks A001 header accuracy and AGENTS.md principle 2 ("update its comments in the same edit").
  Smallest fix:
  - Row 13 r7: replace "Nothing else changes" with "PURPOSE (line 3) names the fourteen direct hosts; RELATED DOCS (line 8) adds the seven research-2 §3.1 doc URLs; COMMON MODIFICATION PATTERNS (line 6) reads 'a path constant (reuse one when the path already exists)'; the comment above HOSTS (line 208) names the seven False hosts. Messages, `list_models` and the ladder stay as built."
  - Row 11 r7: "header lines 4, 5 ('six other' → 'thirteen other') and 13-14".
  - Row 18 r7: the last cell of the OpenAI (Decisions) Usage Key Divergence row becomes `total_tokens`.

R-17 [Major] [L1] §9.1 HANZO cell (INV-29, AC-21) — the Hanzo price-proof URL `https://docs.hanzo.ai/docs/models/kai` was never read by the research
  Evidence:
  - §9.1 (line 540) cites "(https://hanzo.ai/pricing, https://docs.hanzo.ai/docs/models/kai)".
  - research-2 §6 (line 649) lists the pages actually read for Hanzo: "Hanzo (raw): https://docs.hanzo.ai/docs/decisions, https://hanzo.ai/pricing".
  - Line 671 records `docs/decisions.md` as a 404.
  - research-2's ship table (line 550) gives `https://hanzo.ai/pricing` as the only price source.
  - `docs/models/kai` appears only in §3.1.5's "Docs." line (line 291), as a page that exists.
  Failure: INV-29 says "Each URL is the vendor's own page … so the row's rate is the price that vendor serves". AC-21 requires that URL, verbatim, in the comment above the HANZO block. The code would carry a "proof" link that nobody checked against 0.021, which defeats ruling (e). S5's pricing recheck would then have to explain a proof link that may not state the rate.
  Smallest fix: change the §9.1 HANZO pricing cell to "(https://hanzo.ai/pricing, https://docs.hanzo.ai/docs/decisions)". Research-2 §6 read both raw. If `docs/models/kai` is wanted, list it as an overview link in row 18's README documentation table, not as price proof.

R-18 [Minor] [L1] §15 A-18 (D-19) — Vansa's ship evidence cites a quote about keys, not the null values the SDK sends; the stronger quote and the known risk go unnamed
  Evidence:
  - Ruling (c2) ships Vansa "only if research §3.1 shows it accepts the body the SDK sends today".
  - A-18 (line 826) says Vansa accepts "`null` descriptions inside choice and noul criteria". Its only citation is "optional object with `true` and/or `false` string keys" (research-2 line 317), which describes the keys, not the values.
  - research-2 §5 item 4 (line 583) names exactly this as a risk: "Noul criteria with `null` values may be rejected … Vansa takes 'string keys'. The SDK sends `null`".
  - `SystemOneRequest.criteria()` sends `{option.name: option.description}`, and `JevOption.description` defaults to None, so §4's own choice snippet sends nulls.
  - The stronger evidence is research-2 line 308: "Jev-compatible: the same `state` + `questions` format as TypeSafe's Jev `/v1/systemone`" (from a helper's fetch). A-18 does not cite it.
  - No EC covers a Vansa 4xx caused by null criteria.
  Failure: the spec rests the (c2) gate on a quote that does not establish it. The risk the research flagged is invisible, so S2 writes no test for it, and the row 18 Vansa note gives callers no warning.
  Smallest fix: A-18 cites the "Jev-compatible" quote as the (c2) evidence and states research-2 §5 item 4 as the remaining risk. Row 18's Vansa bullet adds "describe every option; `null` descriptions are unverified on Vansa". Vansa stays shipped, and (c2) is not reopened.

R-19 [Minor] [L4] §7 FR-13, §12.3 row 4 — Inception and Hanzo reuse `PERPLEXITY_DECISIONS_PATH`, whose doc-URL comment names only Perplexity
  Evidence:
  - FR-13's r7 text (line 293) routes Inception and Hanzo through `PERPLEXITY_DECISIONS_PATH`.
  - `vidbyte/lib/constants/jev.py:23` has only `# https://docs.perplexity.ai/api-reference/decisions-post` above that constant.
  - The r6 Baseten precedent (lines 25-26) gave the same `"/decisions"` value its own constant and vendor URL.
  - Row 4 has no r7 note.
  Failure: someone checking why Hanzo calls `/decisions` finds only a Perplexity link. If Perplexity moves its path, the obvious one-line edit silently re-routes two other vendors.
  Smallest fix: add an r7 note to row 4 that extends the comment above `PERPLEXITY_DECISIONS_PATH` with "also the System One body path of Inception (https://docs.inceptionlabs.ai/capabilities/decisions.md) and Hanzo (https://docs.hanzo.ai/docs/decisions)". This is a comment-only change: D-19's "no new constant" still holds, and no digest or test changes.

R-20 [Minor] [L9] §7 NFR-6, §6.1 INV-18 — the proof wording claims more than INV-29 and ruling (a) allow
  Evidence:
  - NFR-6 (line 306) says "Every pricing row and README documentation row carries its first-party URL and the retrieval date `2026-10-10`".
  - INV-29 (line 194) says "Untouched text-model rows are out of scope", and the text rows in `pricing.py` carry no such date.
  - INV-18 (line 189) says "guessed, copied, or third-party rates never appear", then two sentences later prices Baseten at Inception's rate (ruling (a)).
  Failure: a literal NFR-6 check over `PROVIDER_PRICING` fails on every untouched text row, and INV-18 contradicts itself on Baseten.
  Smallest fix:
  - NFR-6 → "Every decision pricing row (INV-29) and every README documentation row r7 adds carries …".
  - INV-18 → "… never appear, except Baseten's row, which carries Inception's published rate for the same model by ruling (a)."

R-21 [Minor] [L1] §12.3 row 18, §12.3 row 7, §12.6 P1, §13 — two repo figures the r7 text relies on are stale
  Evidence:
  - Row 18 says the providers README is "49,420 at `c090d219`". `vidbyte/providers/README.md` is 48,690 characters at `c090d219` and at `e885f9c8`, measured with utf-8-sig as A009 reads it.
  - Rows 7, P1 and §13 (lines 714, 780, 793) cite `tests/test_agent_settings_validation.py:104-110`. After the main merge, the test is at lines 125-131 (`def test_accepts_every_text_provider_default_model` at line 125).
  Failure: the budget is unaffected (48,690 + 4,500 = 53,190, under the 54,000 target and the 55,000 ceiling). But the next reviser measures headroom from a false figure, and S2 opens the wrong lines.
  Smallest fix: "48,690 at `c090d219`", and change ":104-110" to ":125-131" (or cite the test by name only).

## VERIFIED CLAIMS

1. INV-30 / EC-34 (provider_for_model insertion order; baseten key at `runners.py:178`; pair refusal after r7) — HELD.
2. INV-1 sorted list of 16 members; §8.4 counts (16 providers, 15 HOSTS rows, 13 env vars, 13 pricing blocks, 3 adapters); W-5 "fourteen hosts" (15 rows minus TypeSafe) — HELD.
3. INV-18 / §12.5: every r7 default resolves in C009's `PricingLookup`; `_PRICED_PER_RESPONSE` is OPENROUTER only; the baseline stays 1 (MISTRAL) — HELD.
4. D-12 / EC-33: the `gpt-6-luna` tier switches only above 272,000 (strict `>`, `threshold_inclusive=False`) and accepts the 0.0 over-threshold output rate (`is not None`, `base.py:124-149`); AC-12 arithmetic — HELD.
5. §12.5 C010: `lint/pricebook_vintage_lock.json` is at vintage 2026-07-30 with no decision entries; comment-only edits change no digest; one `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock` covers r6 plus r7. `origin/main` `pricing.py:54` is still `PRICING_AS_OF = "2026-07-30"` — HELD.
6. Row 16 targets: `REPO_MAP.md:390` "seven-host `SystemOneProvider`", `REPO_MAP.md:394` "six System One hosts", `skills/jev-agent/SKILL.md:142` host list — HELD.
7. Row 13 "header ROLE line ('seven direct System One hosts')" — HELD for line 4, but lines 3, 6, 8 and 208 are also stale (R-16).
8. Row 11 "header lines 13-14" of `agents/pricing/typesafe.py` — HELD for lines 13-14, but lines 4-5 also list the hosts (R-16).
9. FR-13 / D-19 "the r7 hosts reuse existing constants": `JEV_SYSTEMONE_PATH == "/systemone"` and `PERPLEXITY_DECISIONS_PATH == "/decisions"` (`constants/jev.py:20,24`); the `WIRE_CONSTANTS` check is `assertIn` (`test_decision_contract.py:61-69`) — HELD (comment gap in R-19).
10. INV-30 / S014 parity: each r7 default has a `<provider>/<model>` qualified key and a bare key; `mercury-decide` is already in the bare and prefix maps (`runners.py:320,388`); modality detection gives AUTO for every r7 id, with no text-prefix collision — HELD.
11. `gpt-6-luna` is absent from every text catalog, on the branch and on `origin/main` — HELD.
12. §9.1 HANZO price proof `https://docs.hanzo.ai/docs/models/kai` was read by research-2 — NOT HELD (§6 line 649 lists only docs/decisions and hanzo.ai/pricing; R-17).
13. A-18 "Vansa accepts null criteria values" per the quoted "string keys" — NOT ESTABLISHED by that quote; research-2 §5 item 4 flags it as a risk (R-18).
14. Row 18 "49,420 at `c090d219`" — NOT HELD (48,690; R-21). Row 7 / P1 / §13 `test_agent_settings_validation.py:104-110` — DRIFTED to 125-131 (R-21).
15. Research-2 §3.1.1–§3.1.7 against §9.1 (endpoints, env vars, defaults, rates, echo flags; Upstage and ZooData True, Hanzo False with research noting "True is safer" — still prices correctly because `kai` is the row key) — HELD.
