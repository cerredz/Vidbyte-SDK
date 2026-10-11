LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, exports, lint, and commit hygiene are sound, but the new `@intent` comment blocks repeat the exact comment shape the owner rejected on PR #690 (field guide `comment-format.md`), and a few small AGENTS.md / spec §12.4 obligations are unmet.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Placement follows AGENTS.md exactly. `TextModelMode` is in the new `vidbyte/lib/enums/text_model.py` with a full A001 header, and it is exported from `vidbyte.lib.enums` and `vidbyte.lib.config`. The 8 constants are in `vidbyte/lib/constants/jev.py` (D-7). `VidbyteGatewayTransport` is in `vidbyte/lib/http/vidbyte_gateway.py` and is NOT re-exported (R-10; `hasattr(vidbyte.lib.http, "VidbyteGatewayTransport")` is False). No new dataclass and no new error class were added, and no production `.py` changed outside `vidbyte/lib/`.
- The C020 change applies the field-guide "two inline copies drift" lesson the honest way. `VIDBYTE_API_KEY_PREFIX` is the only `vb_live_` literal in new code, and `VIDBYTE_API_KEY_PATTERN` is built from it. `DecisionModelConfig` now calls the shared `ProviderModelRegistry.resolve_vidbyte_api_key` with unchanged messages. The C020 baseline moved 4→2, and that is the only `lint/baseline.json` edit.
- The code shaped around lint rules is genuine, not a workaround. The S064 stop is a real event-loop-clock comparison (`loop.time() + retry_wait >= deadline`), and no attempt is shortened. The C017 headers use D-3's `bearer_headers(...)` plus a subscript `Idempotency-Key`. A007 is met through `HTTPStatus` and the existing `JEV_*` constants. `gateway_reason` uses dict dispatch instead of a status ladder. There are no suppressions, no `# type: ignore`, and no baseline raise.
- Every added comment line is at most 72 columns. Each main function (`TextModelRunner.__init__`/`arun`, `VidbyteGatewayTransport.request`, `StreamingTextModelRunner.__init__`) is narrated. Every non-docs commit cites W-/FR-/AC- IDs. The contract is a byte copy (blob `56d4d0b3`, no BOM), and its Provenance row and Change Log line are updated.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Blocker] [field-guide] vidbyte/lib/runners/text.py:33-37, vidbyte/lib/runners/text.py:62-67, vidbyte/lib/http/vidbyte_gateway.py:148-155 — each of the three main functions opens with an `@intent` block that sits away from the code it explains and runs straight into the next step's narration, the comment shape the owner rejected on PR #690
  Evidence: `text.py:33-37`:
  ```
          # Builds the config, checks it, and fixes how calls are sent.
          # @intent managed-runner-is-pinned-at-construction
          # Fixing managed mode, key, cap, and timeout once keeps a
          # managed runner on the gateway after the environment changes;
          # a BYOK config is left as it was, so BYOK does not change.
          config = self._coerce_config(...)
  ```
  That intent is about the pinning `replace(...)` at `text.py:46-54`, 9-17 lines further down, and that code already has its own narration block (`:42-45`).
  - `text.py:62-67`: the routing intent (`managed-calls-route-through-the-gateway-transport`) sits above `call_config = replace(...)` (`:68`) and is fused with "# Add this call's tools, messages, and output format." The code it explains is the transport wrap at `:75-84`.
  - `vidbyte_gateway.py:148-155`: the intent "The adapter's vendor URL and headers are dropped" is fused with "# Mint one key for this call; ..." above `uuid.uuid4()` (`:156`). The code it explains is the header build at `:157-160`.
  - `field-guide/vidbyte-sdk/comment-format.md`: "Put each block directly above the code it explains. A method that does several steps gets one short block per step, not one long block at its top."
  - PR #747 body (`git show 57639080`, now on main): "The `@intent` block that sat at the top of `CodingAgent.__init__` now sits above the permission-policy line it explains."
  Failure: The rule comes from the owner's PR #690 comment r4239871810: "stop writing comments like this, if a comment is a multi line comment, then format it correctly". That comment forced replacement PR #747. The owner would leave the same comment on `TextModelRunner.__init__`, `arun`, and `request`. `docs/spec/coding-agent/reports/S4-review-conventions.md` exists on main, which shows the previous pipeline's conventions review missed this shape, and the owner caught it afterwards.
  Smallest fix: In each of the three functions, move the `# @intent <slug>` line and its rationale lines down so they sit directly above the lines they explain:
  - `text.py`: above `self._managed = config.is_vidbyte_managed()`, merged with the existing pinning narration;
  - `text.py`: above `transport = self._transport`;
  - `vidbyte_gateway.py`: above `gateway_headers = ...`.
  Drop the leading one-line summaries. A002's window is the `def` line −4 to +20, and every moved marker still lands inside it: about 40 of 44 in `__init__`, about 71 of 81 in `arun`, and about 153 of 158 in `request`. Re-run `python lint/run.py --rule A002`.
  Spec IDs: §12.4 (narration item: "comments are updated wherever steps changed"); n/a otherwise

R-V2 [Major] [field-guide] vidbyte/lib/dataclasses/model_configs.py:74, 99, 111, 121, 137, 157; vidbyte/lib/registries/models.py:177, 199; vidbyte/lib/http/vidbyte_gateway.py:64, 75, 95, 150, 194; vidbyte/lib/runners/text.py:34, 63; vidbyte/lib/runners/streaming_text.py:57 — none of the 16 new `@intent` blocks opens with its `# @intent` line, and two edited blocks still start with a comment line wider than 72 columns
  Evidence:
  - An awk scan of the five files for `# @intent` lines preceded by a comment line lists all 16 added markers. Each one follows a summary line, for example `model_configs.py:155-157`: "# Refuses a custom endpoint and any provider the gateway does / # not serve, before a managed call can send the Vidbyte key. / # @intent managed-key-stays-on-the-gateway". Added markers that are first in their block: 0.
  - `comment-format.md`: "Keep `# @intent <name>` on its own first line." In PR #747 every `# @intent` is the first comment line, and the summary lives in the docstring.
  - Edited blocks headed by over-wide lines: `text.py:62` (93 columns, "# Async entry point; awaits the provider's HTTP call without blocking the event loop.") now heads a 6-line block. `model_configs.py:136` (79 columns, "# Resolve explicit keys before provider-specific environment variables.") now heads a block whose first behavior is the managed placeholder return (`:141-142`), so its summary no longer describes what the method does first (AGENTS.md style 2).
  - Unevenly filled block: `model_configs.py:109-110` ("...or when AUTO selects a / # Vidbyte key.").
  Failure: The field-guide entry's check is "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched", and its Do says to keep `@intent` on its own first line. A reviewer applying the entry flags every block. Mitigation: the neighbouring pre-existing `DecisionModelConfig` blocks use the old summary-first shape, which is why this is rated Major rather than Blocker. AGENTS.md "Existing code" still says not to copy pre-rule code as precedent.
  Smallest fix: For each of the 16 blocks, either move the one-line summary into a docstring or drop it, so `# @intent <slug>` opens the block. Re-wrap `text.py:62` and `model_configs.py:136` to 72 columns, and make the `:136` summary cover the managed placeholder branch.
  Spec IDs: n/a (field guide `comment-format.md`; AGENTS.md style 2)

R-V3 [Major] [AGENTS.md] vidbyte/lib/dataclasses/model_configs.py:106 / :141 — new two-level call chain inside `TextModelConfig`: `validate()` → `resolved_api_key()` → `is_vidbyte_managed()`
  Evidence: `validate()` already calls `self.is_vidbyte_managed()` at `:102`. On the BYOK path it then calls `self.resolved_api_key()` at `:106`, which calls `self.is_vidbyte_managed()` again at `:141` before it reaches the registry. That repeats `find_vidbyte_api_key`, including a second environment read. AGENTS.md style 1: "a function may call another of its own functions, but that second function should not call a third." Spec §12.4: "Call chains stay one level deep inside each class."
  Failure: AGENTS.md style 1, the first "General Coding Style Guideline". It applies to "code you change", and both `validate` and `resolved_api_key` were changed. A reviewer would write: "`validate` → `resolved_api_key` → `is_vidbyte_managed` is two hops; lift the call." The base already had a `validate` → `resolved_api_key` → `normalized_provider` chain, but the new hop comes from this PR.
  Smallest fix: In `validate()`'s BYOK tail, replace `self.resolved_api_key()` with `ProviderModelRegistry.resolve_api_key(provider, self.api_key)`. `provider` is already computed at `:96`, and the result is byte-identical to the base BYOK path, so INV-17 holds. `resolved_api_key()` keeps its placeholder branch for adapters.
  Spec IDs: §12.4 (call-chain item), INV-17 (must stay unchanged)

R-V4 [Minor] [agentic] vidbyte/lib/http/vidbyte_gateway.py:129 — `VidbyteGatewayTransport.__init__` has no `@intent` marker, which adds a new A002 finding in a new file, and the S3 report's claim that every new function carries one is false
  Evidence:
  - `python lint/run.py --all --format json`, filtered to changed files: `A002 vidbyte/lib/http/vidbyte_gateway.py 129 __init__`.
  - An IntentAnalyzer run on the changed files reports `e91cf822 43`, `a80f0660 38`, and the only new entry is `vidbyte/lib/http/vidbyte_gateway.py:129:__init__`.
  - S3 report, Completeness pass: "Every new key, request, provider and retry function carries one."
  - Spec §12.4: "Every function that handles keys, requests, providers or retries has a `# @intent <slug>` within 20 lines." `__init__` stores the provider and the bearer key.
  Failure: The gate passes only because A002 is IMPROVED (703 → 653), so this new finding uses up ratchet headroom unseen, and a passing exit hides it. A reviewer who runs `--rule A002 --all` sees a new file with a finding.
  Smallest fix: Add a 2–3 line `# @intent` block (for example, that the key is kept only for the gateway bearer header) as the first lines of `__init__`'s body.
  Spec IDs: §12.4 (A002 item)

R-V5 [Minor] [field-guide] vidbyte/lib/dataclasses/model_configs.py:160 and :127-128 — the managed-mode "no custom endpoint" check and the "api_key must be a string" check are inline copies of `DecisionModelConfig`'s (`:436-437`, `:464-465`)
  Evidence:
  - Text `:160`: `if self.endpoint is not None and (not isinstance(self.endpoint, str) or self.endpoint.strip()):`. Decision `:435-436` is the same predicate.
  - Text `:127`: `if self.api_key is not None and not isinstance(self.api_key, str):`. Decision `:464` is the same.
  - `strict-config-dataclasses.md`: "Two independent inline copies of the same rule drift silently". Spec D-14 cites that lesson to share the key check, but this PR adds new copies of the two sibling checks.
  Failure: The next change to managed-endpoint policy, such as also refusing a Vidbyte origin, has to be made twice. The field guide records that reviewers ask for one owner.
  Smallest fix: Add one shared helper beside `resolve_vidbyte_api_key` (for example `ProviderModelRegistry.require_no_managed_endpoint(endpoint, message)`) and call it from both configs, passing each config's existing message so INV-19's Decision text stays byte-identical. Optional: D-14 explicitly kept Decision's non-string line, so sharing the endpoint check is the part worth doing.
  Spec IDs: D-14 (spirit), INV-19 (must stay unchanged)

R-V6 [Minor] [AGENTS.md] vidbyte/lib/http/vidbyte_gateway.py:41-51 — `_GatewayAnswer` is a mutable record written by hand, and its `raised` field encodes a closed set as exception classes instead of an enum
  Evidence:
  - `class _GatewayAnswer:` has `__slots__ = ("body", "raised", "response")`, and `__init__` assigns three attributes. It is not frozen and not validated, and it is the record passed from `_send` to `request`.
  - `raised: type[Exception] | None` takes exactly three values, `None`, `ProviderRequestError` or `Exception`, and `failure_reason` dispatches on `self.raised is ProviderRequestError` (`:82`).
  - AGENTS.md style 4: "Prefer `@dataclass(frozen=True, slots=True)`... type any field whose value comes from a small, closed set as an enum". Placement: "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py` ... whether it is public or underscore-prefixed."
  Failure: The class is a record in all but name. Writing it by hand keeps it outside both the `AGENTS.md placement` workflow and the frozen-and-validated guarantee, and the exception-class tag is an obscure way to say "transport failure versus other failure". Spec §8.4 budgets "one module-private helper class ... that classifies failures", so the class itself is sanctioned. Its record shape is not.
  Smallest fix: Move the per-attempt data into a `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/` with an enum-typed outcome, and keep `_GatewayAnswer` as the stateless classifier. That is one class over §8.4's budget, so it is a follow-up unless the orchestrator waives the budget. Without a waiver, leave as is.
  Spec IDs: §8.4 (budget tension)

R-V7 [Minor] [agentic] vidbyte/lib/constants/jev.py:6-8 and vidbyte/lib/dataclasses/model_configs.py:13 — header fields went stale for the new managed values
  Evidence:
  - `jev.py` now holds the generative-gateway values, but `COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it...` and `KNOWN EDGE CASES: Vendor limits are the 255 Choice options...` still describe only Jev.
  - `RELATED DOCS` does not name `docs/spec/managed-generative-models/spec.md`, and only PURPOSE, ROLE and TESTS were updated.
  - `model_configs.py:13` still says "resolved_api_key: Resolves provider key by delegating to ProviderModelRegistry", but in managed state it returns `VIDBYTE_MANAGED_KEY_PLACEHOLDER`.
  Failure: Under the agentic file-header obligation, headers must stay accurate against the finished code. An agent editing `VIDBYTE_MANAGED_TEXT_PROVIDERS` or `VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS` gets no header guidance that these must track the backend dispatch table and its 600 s deadline. That coupling is stated only in the inline comments (`:68`, `:78-80`). Spec row 3 required only the PURPOSE and ROLE lines, so this is Minor.
  Smallest fix: Add one clause to COMMON MODIFICATION PATTERNS (the managed generative values change only with the backend generative-gateway contract), add the spec path to RELATED DOCS, and add "(placeholder in Vidbyte-managed state)" to the `model_configs.py:13` inventory line.
  Spec IDs: §12.3 rows 3 and 5 (header upkeep)

VERIFIED CLAIMS:
1. "C020 ratcheted 4→2 through `--update-baseline`; no other baseline touched" — HELD. The `lint/baseline.json` diff is only `-"C020": 4` / `+"C020": 2`, and lint reports C020 2/2.
2. "The only `vb_live_` literal is `VIDBYTE_API_KEY_PREFIX`" — HELD for new code. `git grep vb_live_ -- vidbyte/` shows `jev.py:62` plus the two baselined `providers/typesafe.py:255,271`.
3. "Every new key, request, provider and retry function carries an `@intent`" (S3 Completeness pass) — FAILED. `vidbyte_gateway.py:129 __init__` is a new A002 finding (R-V4).
4. "Every touched file is under 1,000 lines (`jev.py` about 757)" — HELD. `wc -l`: jev.py 757, model_configs.py 507, registries/models.py 402, vidbyte_gateway.py 209.
5. "Contract blob `56d4d0b3`, no BOM" — HELD. `git hash-object` gives `56d4d0b373994f5de6affd675ed4c209e64d589d`, and the first bytes are `{ \n`.
6. "No test file changed after S2" — HELD. `git diff --stat e91cf822..a80f0660 -- tests` is empty.
7. "Production `.py` only under `vidbyte/lib/`" (AC-19) — HELD. No changed `.py` outside `vidbyte/lib/` or `tests/`.
8. "`TextModelMode` exported from enums and config; `VidbyteGatewayTransport` not exported" (§12.5) — HELD. Python prints `True False`.
9. "`repr(TextModelConfig)` hides the key" (FR-10) — HELD. `repr(...).find('vb_live_')` gives -1.
10. "No numeric literals in new code" — HELD. Every A007 finding in a changed file is a pre-existing `timeout_seconds` default (`model_configs.py:68, 201, 250, 312, 363`).
11. "§12.5 Not required: llms.txt, file_index, REPO_MAP, `.env.example`, sdk-public-api.json, lib/http README, lib/http `__init__`" — HELD:
    - `.env.example` does not exist.
    - `vidbyte/__init__.py`, `contracts/` and `vidbyte/lib/http/__init__.py` are untouched.
    - `llms.txt` and `artifacts/file_index.md` never mention `TextModelConfig`, `TextModelRunner` or `VIDBYTE_API_KEY`.
    - REPO_MAP's lib/http and lib/enums entries are folder-level prose with no file list.
12. "Comment lines wrapped at 72" — HELD for added lines (the awk scan of added `#` lines is empty), but see R-V2 for edited blocks.
13. "Semgrep 0 findings" — HELD. "Ran 1 rule on 872 files: 0 findings.", exit 0.
14. "Pack 32 passed" — HELD. `32 passed in 1.04s`.
15. "S051 not worsened" — HELD. Ruff I001/UP0xx findings on the touched files are the same 5 at `e91cf822` and `a80f0660`, and both report "Found 258 errors."
16. Commit hygiene — HELD. Every non-docs commit since origin/main cites `[W-…; FR-…/AC-…]`. No `__pycache__`, `.pyc`, `.env` or log files are in the diff. Test keys are synthetic.

COMMANDS RUN:
- `git diff --stat origin/main...a80f0660` → "31 files changed, 4671 insertions(+), 21 deletions(-)". The merge-base is `00cbd6db`, and origin/main is still `57639080`. Disclosure: an early `git fetch -q origin` ran once. It was a no-op, and origin/main stayed `57639080`.
- awk scan of added `#` lines over 72 columns in `vidbyte/` → (no output). awk scan of the touched files' wide comment lines → `text.py:62: 93`, `model_configs.py:136: 79`, plus untouched pre-existing lines.
- awk scan for `# @intent` preceded by a comment line → 16 of 16 added markers. `git diff ... | grep -c '^+.*# @intent'` → `16`.
- `git show 57639080 | grep -B3 -A4 '^+\s*# @intent'` → every marker in PR #747 is the first comment line, with the summary in the docstring.
- `python lint/run.py` → "S064 retry-overall-deadline 4 4 RATCHETED" … "SDK-LINT: PASS", exit=0 (C017 0, C018 1, C019 0, C020 2; A002 653/703 IMPROVED).
- `python lint/run.py --all --format json`, filtered to the changed files → `A002 vidbyte/lib/http/vidbyte_gateway.py 129 __init__` is the only finding located in a new file.
- `python -I scratchpad/s4conv_scripts/a002_compare.py <worktree>`, which runs IntentAnalyzer over the changed files at both revisions → "e91cf822 43" / "a80f0660 38", with `vidbyte_gateway.py:129:__init__` new.
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045 --no-cache` at the branch and at a `git archive e91cf822` extract in the scratchpad → the same 5 touched-file findings, "Found 258 errors." on both.
- `pysemgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` → "Ran 1 rule on 872 files: 0 findings.", exit=0.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/sdk_managed_text` → "32 passed in 1.04s".
- `PYTHONPATH=$(pwd) python -c "...export and repr checks..."` → worktree `vidbyte/__init__.py`; "True False"; "-1".
- `git hash-object lint/contracts/vidbyte-platform-contract.json` → `56d4d0b373994f5de6affd675ed4c209e64d589d`. `git diff --stat e91cf822..a80f0660 -- tests` → empty. `wc -l` on touched files → max 757.
- Field guide entries read: comment-format, local-ci-verification, blocking-lint-invariants, strict-config-dataclasses, provider-api-contracts, class-bound-helpers, runtime-boundaries, review-scope, declarative-config-resolution, fallback-coordination, diagnostic-context. `comment-format.md` was written at 2026-10-10 22:04, before the first S3 code commit at 22:50.
