# S1 spec review, round 2 of 2: managed-generative-models (spec r2)

Reviewer: S1 spec reviewer (round 2). Inputs: spec r2 (873 lines), round-1 review, request.md, AGENTS.md, backend spec r3 §9.2 (`a14b37e7e`) and the backend author report's "SDK obligations", the SDK code at `base_commit` c07529316, and the backend repository's branch `feat/generative-model-gateway`. Read-only: no gate that writes files was run, and no file other than this report was written.

VERDICT: SOUND WITH FIXES. r2 resolves all fourteen round-1 findings, and its emitted-keys table matches both the adapters and backend r3 §9.2.4 line by line. One Major issue remains: INV-10's "never gives up" promise is broken on a default path, the 120 s prosecutor/defender/judge stage timeout, and needs rewording plus a README line. Three Minor issues remain: a row-20 lookup command that cannot detect a missing commit, no message or README line for the 2 MB request cap (413), and an ambiguous camelCase clause in AC-26. None blocks implementation.

## WHAT THE SPEC GETS RIGHT

- **The §9.2 "Keys the SDK emits" table is exact.** I checked each row against the payload builders at c07529316, which are identical to the backend's read at 830ad871. The rows checked were `openai._create_text_payload`, `anthropic._create_payload`, `gemini._create_payload` (top level and `generationConfig`) and `compatible._create_payload`, plus the tool shapes in `lib/tools/formatter.py`. Every emitted key is on backend r3's per-dialect list, and so is every "never emitted" key. The `*` fields (`stream`, `background`) are never emitted. There is no Gemini body `model`, because the model goes only in the quoted URL (`gemini.py:26-27`). The only snake_case Gemini key is `function_declarations`. `extra_body` is merged last in all four builders, which is exactly what NG-14/EC-8 assume.
- **The C017 fix is correct.** Moving the endpoint constant into P2, so that rows 15, 6, 11 and 12 land in one commit, keeps every phase green. C017 is CLEAN today and flags a Vidbyte URL literal that no traced request uses. The C020 plan works: delegating `DecisionModelConfig` to `resolve_vidbyte_api_key` removes exactly the literals at `model_configs.py:401,402`, so C020 goes from 4 to 2. Row 5 already says to drop the `os`/`re` imports that the delegation leaves unused. They are used only at `:398` and `:401`, and S001 runs Ruff `F`, so an unused import would regress S001.
- **The D-17 raise shape is correct Python.** Each `except` only records locals, `json.loads` sits in its own narrow try, only `Exception` is caught, and the raise happens after the block. That makes `__cause__` and `__context__` both `None`, avoids B904 (S002 baseline 0), keeps CancelledError propagating, and needs no `from None`. Both outer callers that could re-enter a call while an exception is live use `continue`, so the next call runs outside the `except` and INV-11 holds on every SDK path. They are the agent-runtime retry loop (`agents/runtime.py:660-700`) and the fallback walk (`agents/base.py:1147-1165`).
- **Scope is clean.** Q-8 to Q-10 are optional, labelled and unbuilt. EC-30, EC-31 and T-7 are documentation only. No settled decision is reopened: lib layer, one route, no streaming relay, no SDK retries, BYOK direct, a fresh key per call, a contract copied from the branch with a §15 squash note, and the Jev warning only as a Q.

## FINDINGS

R-1 [Major] [L5] INV-10 / D-9 / EC-14 / AC-18: INV-10 says the SDK "never gives up on a call that the gateway can still complete and bill", but a default code path does exactly that.
  Evidence: (a) Outer timeouts cancel the runner no matter what the 630 s transport floor is. One of them is on by default: `DebateStageSettings.timeout_seconds: float = 120.0` (`context/algorithms/prosecutor_defender_judge.py:67`), enforced through `asyncio.timeout(...)` at `agents/algorithms/prosecutor_defender_judge.py:494`. That limit covers a whole stage of up to 4 model calls. Three more are opt-in, with a default of `None` (`lib/dataclasses/multi_agent.py:127,399,401`):
    - `per_proposer_timeout`, enforced at `agents/aggregation.py:114`;
    - `run_timeout_seconds`, enforced at `agents/multi/runner.py:51`;
    - `worker_timeout_seconds`, enforced at `agents/multi/dispatcher.py:100`, plus bounded retries. Each retry is a new POST with a new key and can bill again.
  (b) The floor's 30 s of headroom must also cover the gateway's own steps before and after the upstream call: gatekeeper, admission, hold and metering (backend A-11). (c) `max(config.timeout_seconds, VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS)` (spec line 450) returns `nan` when `timeout_seconds` is `nan`, and `TextModelConfig._validate_positive_float` (`model_configs.py:112-115`, `value <= 0`) accepts `nan`. I checked: `max(nan, 630.0)` is `nan`, while `max(630.0, nan)` is `630.0`.
  Failure: a prosecutor/defender/judge run in managed mode with default settings cancels any stage that takes longer than 120 s. The gateway still completes the call and bills the wallet, and the developer receives a stage "timeout" instead of an answer. The same happens with the opt-in limits, and dispatcher retries can bill more than once. INV-10, EC-14 and the AC-18 README text say the 630 s floor prevents this. BYOK has the same economics, because the vendor bills an abandoned call too. So this is a gap in documentation and invariants, not in the design. A `nan` timeout reaches httpx unchanged in managed mode.
  Smallest fix:
    - Reword INV-10: "the SDK's own transport never times out before the gateway's 600 s upstream deadline; an outer caller timeout below 630 s can still cancel a call that Vidbyte completes and bills."
    - Add one EC row naming the default 120 s debate-stage timeout and the three opt-in limits.
    - Add one README line under AC-18 and row 14 saying that outer agent timeouts below 630 s may cancel calls that are still billed.
    - Write the floor as `max(VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS, config.timeout_seconds)`, floor first, so that `nan` resolves to 630.0. Optionally, AC-9 can add a `nan` case expecting 630.0.
    - Changing the debate-stage default is outside lib: [scope-adding], optional Q-11, not recommended for this PR.

R-2 [Minor] [L11] §12.5 / §12.6 / §14: the row-20 lookup command never reports a missing commit, and today it returns the commit that is already vendored.
  Evidence: §12.5 (spec line 720) finds the source with `git -C C:/Users/422mi/vidbyte-repos/vidbyte log -1 --format=%H feat/generative-model-gateway -- contracts/vidbyte-platform-contract.json`. Today that prints `bbeef425…` (#648). That commit is a pre-branch main commit, and it is the very content the SDK already vendors (Provenance row). `git log origin/main..feat/generative-model-gateway` contains only docs commits. The command can never print nothing, so "if that commit does not exist, stop" (§12.6 line 749, §14 line 799) cannot be triggered by it. The same thing happens mid-way through the backend implementation: backend P1 row 5 also regenerates the contract, so the command returns the row-5 commit until row 20 lands. Separately, backend main's latest contract commit `6dfc4d20` (agent-run routes) is not on the branch. The branch copy will therefore differ from backend main even after a merge-commit merge.
  Failure: the implementer copies `bbeef425`. Its blob equals the current file, so the blob check at line 721 passes. Then C017 fails on the endpoint constant, which reads as a code defect rather than "backend row 20 not done". The route check (line 723) and the Ask-first trigger (line 799) do catch it, but only after the copy, and with a confusing signal.
  Smallest fix: change the lookup to `git -C C:/Users/422mi/vidbyte-repos/vidbyte log -1 --format=%H origin/main..feat/generative-model-gateway -- contracts/vidbyte-platform-contract.json`, where empty output means STOP (§14). Also add a pre-copy check: `git -C … show <commit>:contracts/vidbyte-platform-contract.json | grep -q '"models.generate"'`, where no match means STOP. Optional, and a risk note only (no reversal): add to §15 that the vendored copy will lack backend-main-only routes such as 6dfc4d20's agent-run routes. Today that is harmless, because the SDK vendors `bbeef425` content and calls none of those routes.

R-3 [Minor] [L5] §9.2 failure row 5 / AC-18: the gateway's 2,000,000-byte request cap (413) has no reason and no README line.
  Evidence: backend r3 §9.2.4 step 5 refuses a forwarded body larger than 2,000,000 bytes with 413 `model_gateway_request_too_large`. It measures `json.dumps` output, so non-ASCII text costs up to 6 bytes per character (backend EC-33). Row 5 lists reasons for 401, 402, 403, 422, 429 and ≥ 500, and 413 falls through to "Vidbyte returned HTTP 413". AC-10 covers 413 only for status and redaction. AC-18 and the row-14 README content do not mention the limit. BYOK has no such limit, so this is a new, gateway-only failure. Long agent contexts can reach it, especially non-ASCII ones, as can 1M-context Gemini or OpenAI models.
  Failure: a context that worked under BYOK fails after switching to managed mode, and nothing tells the developer what to change.
  Smallest fix: add "413: the request exceeds the gateway's 2,000,000-byte limit; shorten the context or use your own provider key" to row 5. Add "requests over 2,000,000 bytes (measured with non-ASCII escaped) are refused" to AC-18 and row 14.

R-4 [Minor] [L10] AC-26: "Gemini keys are camelCase except the `function_declarations` tool key" can be read as a recursive check, which would fail on keys the user supplies.
  Evidence: AC-26 sets "every optional `TextModelConfig` field the adapter maps", including `response_format` and tools. The Gemini builder copies user content into `generationConfig.responseSchema`, where schema property names such as `user_name` are legitimate. It does the same for function parameter schemas inside `function_declarations`, and for the `thinkingConfig` dict as supplied. Backend r3 checks keys only at the top level and directly inside `generationConfig`.
  Failure: a test author who walks the whole body writes a test that fails on correct adapter output, or picks fixture schemas so the test passes.
  Smallest fix: change the wording to "every top-level key and every direct key of `generationConfig` is camelCase, except the `function_declarations` key inside each `tools` entry; nested user-supplied values (schemas, parameter names) are not checked".

## VERIFIED CLAIMS

**Round-1 dispositions**
- R-1 (timeout floor): held. 630.0 appears in INV-10, D-9, §8.5 and §9.3. AC-9 expects 60/30/120/900 → 630/630/630/900. EC-14, EC-20 and AC-18 say "10.5 minutes".
- R-2 (raise shape): held. D-17 is in the decorator docstring (lines 440-444). AC-10, AC-11, AC-12 and AC-25 assert that `__cause__` and `__context__` are `None` and that no body text appears.
- R-3 (C017 phasing): held. P2 is rows 15, 6, 11 and 12 in one commit (§12.6 line 742), and the C020 ratchet is in P1. The source is the backend row-20 branch commit. §15 has the merge-order and squash note. §14 Ask-first triggers on a missing row-20 commit, or a copy that lacks `models.generate` or changes the envelope, the headers or the host status. §12.5 says to use Git Bash rather than PowerShell `>`, and adds the blob-equality check.
- R-4 to R-14: held. The applied changes in the revision table (lines 847-873) match the body text.

**Backend r3 §9.2.4 conformance**
- Per-dialect allowlists: held for all four dialects (see the first "gets right" bullet).
- Gemini `generationConfig` allowlist: held. The adapter emits `temperature`, `topP`, `maxOutputTokens`, `responseMimeType`, `responseSchema` and `thinkingConfig`, and never `stopSequences` (the adapter does not map `stop_sequences`).
- `function_declarations` exception: held (`formatter.py`).
- `*` fields, allowed only as false or null: held. They are never emitted.

**Other backend r3 obligations**
- The cap is always sent (INV-9). Held. The runner fills `max_output_tokens or 8_192`. That maps to `max_output_tokens` for openai (emitted only when set: `openai.py:213-214`), `max_tokens` for anthropic, `generationConfig.maxOutputTokens` for gemini, and `max_tokens` for compatible.
- Client timeout above the 600 s gateway deadline: held for the SDK transport (630 s), with the caveats in R-1.
- No Gemini body `model`: held.
- 402 means the caller's wallet only, and upstream 401/402/403 become 502: held (row 5, EC-10, EC-13, T-5).
- A non-JSON body at any status is a transient edge failure: held (row 3, checked before success).
- `previous_response_id` and `conversation` refused, and no `service_tier` sent: held. The adapters never emit them, and the README lists them.
- Retry behavior: consistent with §9.2.5. The SDK makes no retries (NG-13, INV-16, Q-7) and says "may already have billed". Because every call has a fresh key, 409 and key-reuse 422 cannot happen.

**D-17**
- Failure-table order (1 inner `ProviderRequestError`, 2 other `Exception`, 3 non-object, 4 2xx object, 5 `"error": true`, 6 relayed): held. The 2xx test as `HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES` satisfies A007. Implementer note: do not bind `except … as exc` when the binding is unused, because Ruff F841 runs under S001.

**Constants and placement**
- Budget of 2 new files and 8 constants: held. The names are consistent across §4, §8.5 (lines 391-394), §9.3 (lines 532-539) and §12.3 rows 3 and 15. Row 3 adds 7 in P1 and row 15 adds the endpoint in P2.
- `vidbyte.lib.enums.model_provider` exists, and constants importing an enum follows the `constants/codex.py:16` precedent.
- `jev.py` is 694 lines at the base and 712 on origin/main, so about 738 after the addition, still well under 1,000.
- D-4 host: held. The vendored contract marks `vidbyte-backend.onrender.com` live and `api.vidbyte.pro` planned. C018's baseline of 1 is the Jev constant.

**Lint and paths**
- C016 covers only the root `__all__`; `TextModelConfig` is not a root export. Held.
- S017 scope excludes `lib/http`. Held.
- S020 applies only to README `## File Index` sections, and lib READMEs have none. Held.
- A003 applies only to classes in `lib/errors`; no new error class is added. Held.
- C017: CLEAN today (`python lint/run.py --rule C017`). Its tracer resolves annotated parameters and attributes (A-2). Held.
- Every text path goes through `TextModelRunner`; grep found no direct `run_text` callers. Held.
- EC-18 (YAML `mode` arrives as a string and is refused): held. `_config_options_for` in `runners/utility.py` filters options by `fields()`.
- The streaming refusal location (`streaming_text.py:51-58`, class-level `STREAMING_SUPPORTED_PROVIDERS`): held.

**Tests, README and tooling**
- §13 test seams: held. Checked `test_jev_managed_gateway.py` (lines 39, 120, 154), `test_text_model_runner.py` (12-36), `test_jev_managed_runs.py` (35), `test_streaming_text_runner.py` (175-187), `test_config_validation.py` (12-16, 24-29), the pyproject testpaths, and that there is no conftest.
- README insertion point: held. `## Agents and Runner Inference` is at line 191 and `### JevAgent assumption reconciliation` is at line 214.
- Backend branch `feat/generative-model-gateway`: held. It resolves in the shared checkout `C:/Users/422mi/vidbyte-repos/vidbyte`.
- The vendored contract has no LF/CRLF risk (`.gitattributes` `eol=lf`). `platform_contract.py:175` decodes strict UTF-8, so a BOM would make C017-C020 report ERRORED. The Git Bash rule in §12.5 is therefore needed, and it is present.
- mypy 2.3.1 and Python 3.11.0 are installed, and `lint/mypy.ini` does not enable possibly-undefined, so D-17's record-then-raise locals pass S009.
