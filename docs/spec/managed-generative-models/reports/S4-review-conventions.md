LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, exports, lint shapes, headers and §12.5 actions are all correct, but the new `@intent` and narration blocks repeat the comment shape the owner rejected on PR #690 (field guide `comment-format.md`), and one new A002 finding is hidden by ratchet headroom.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Placement and exports match AGENTS.md and the spec. `TextModelMode` is in `vidbyte/lib/enums/text_model.py`, exported from `vidbyte.lib.enums` and re-exported from `vidbyte.lib.config`. `VidbyteGatewayTransport` stays unexported (R-10), and the eight constants are in `vidbyte/lib/constants/jev.py`. No dataclass or error class was added, and no production `.py` changed outside `vidbyte/lib/` (`git diff --name-only e91cf822..a80f0660 -- '*.py'` lists 9 files, all under `vidbyte/lib/`).
- The lint-driven shapes are honest fixes, not workarounds:
  - S064 compares the real `loop.time() + retry_wait >= deadline`, which does bound re-sends.
  - C017 traces the headers from `bearer_headers(...)` plus a subscript.
  - C020 drops 4→2 because Decision really does delegate to the shared resolver.
  - A007 is satisfied by reusing constants, with no numeric literal in code statements.
  - There are no suppressions, and no baseline was raised. Against the pre-implementation commit `e91cf822`, no rule count rose (A002 658→653, C012 24→23, C020 4→2, everything else equal).
- Every added `#` comment line is at most 72 columns wide. Both new modules carry complete A001 headers. The "Key Functions" inventories in `model_configs.py` and `registries/models.py` were updated. The contract was re-vendored byte-exact (blob `56d4d0b3…`, starts with `{\n`, so no BOM), with its Provenance row and Change Log line.
- Commit hygiene is good. Each §12.3 row (or the spec-mandated P2 bundle of rows 15, 6, 11 and 12) has its own commit, and every commit cites its IDs. The C020 ratchet is its own `chore(lint)` commit. No secrets and no generated or cache files are committed, and `tests/` is unchanged since `e91cf822`.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Blocker] [field guide comment-format.md; AGENTS.md style 2] vidbyte/lib/runners/text.py:33-37 — The `@intent` blocks of the three main functions sit at the top of the method, fused into the next step's narration, away from the code they explain. This is the exact shape the owner rejected on PR #690.
  Evidence: four blocks show the problem.
  - `text.py:33-38`: `# Builds the config, checks it, and fixes how calls are sent.` / `# @intent managed-runner-is-pinned-at-construction` / `# Fixing managed mode, key, cap, and timeout once keeps a` … The block sits directly above `config = self._coerce_config(...)`, but the pinning it explains is `text.py:46-54` (`self._managed = config.is_vidbyte_managed()` / `config = replace(...)`), which has its own narration at `:42-45`.
  - `text.py:62-68`: the pre-existing 93-column line `# Async entry point; awaits the provider's HTTP call without blocking the event loop.` is now the first line of one 6-line block. That block also holds `# @intent managed-calls-route-through-the-gateway-transport`, three rationale lines, and the next step's narration `# Add this call's tools, messages, and output format.`, all above `call_config = replace(...)`. The routing the intent explains is `text.py:75-84`.
  - `vidbyte_gateway.py:148-156`: one 8-line block (a summary, `# @intent managed-request-reaches-only-the-gateway`, two rationale lines, then `# Mint one key for this call; …`) sits above `idempotency_key = uuid.uuid4().hex`. The header building it explains is at `:159-160`.
  - `model_configs.py:136-141`: the pre-existing 79-column line `# Resolve explicit keys before provider-specific environment variables.` now heads a 5-line block above the managed short-circuit `if self.is_vidbyte_managed():`. The BYOK line it describes is `:143`.
  - Command: `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` on the touched files prints `text.py:62: 93` and `model_configs.py:136: 79`. Both lines head blocks this PR edited.
  - Owner-accepted precedent on main (`git show 57639080:vidbyte/agents/coding.py`, lines 42-49): the `@intent` block sits directly above `policy = PermissionPolicy.allow_all() if …`, the line it explains, and each later step gets its own short block.
  Failure: `comment-format.md` says: "Put each block directly above the code it explains. A method that does several steps gets one short block per step, not one long block at its top. … A single-line comment that would pass 72 columns becomes a wrapped block too." Its evidence is #690 comment r4239871810 ("stop writing comments like this, if a comment is a multi line comment, then format it correctly"). The #747 fix reads: "The `@intent` block that sat at the top of `CodingAgent.__init__` now sits above the permission-policy line it explains." AGENTS.md style 2 also says: "Each comment translates the next step." The block at `text.py:33` describes a later step. A human reviewer would leave the #690 comment again.
  Smallest fix: move each of the four blocks.
  - Move the `text.py` init intent so it sits directly above `self._managed = …`, merged with the pinning narration and opening with `# @intent`.
  - Move the `arun` intent directly above `transport = self._transport`.
  - Move the `request` intent directly above `gateway_headers = …`.
  - Give `_coerce_config`, `call_config` and the idempotency-key mint each a short block of their own.
  - Wrap `text.py:62` to 72 columns. In `resolved_api_key`, put "Resolve explicit keys…" directly above the BYOK `return` at `:143`.
  - All new positions stay inside A002's window (lines def−3 to def+20): about `text.py:37` (limit 44), `text.py:71` (limit 81) and `vidbyte_gateway.py:154` (limit 158). Re-run `python lint/run.py --rule A002`.
  Spec IDs: §12.4 (narration; `@intent` within 20 lines), AGENTS.md style 2, FR-5, FR-4 (sites only).

R-V2 [Major] [field guide comment-format.md; agentic intent_based_commenting.md] vidbyte/lib/dataclasses/model_configs.py:74 — In all 16 new `@intent` blocks, the `# @intent` line comes after a summary comment line. It is never the first line of its block.
  Evidence:
  - Command: `awk '/# @intent/ { if (p ~ /^[ \t]*#/) print FILENAME":"NR } {p=$0}'` flags every new marker:
    - `model_configs.py:74, 99, 111, 121, 137, 157`;
    - `registries/models.py:177, 199`;
    - `vidbyte_gateway.py:64, 75, 95, 150, 194`;
    - `text.py:34, 63`;
    - `streaming_text.py:57`.
  - The same check on the owner-accepted #747 production files (`git show 57639080:<file>` for `agents/coding.py`, `lib/dataclasses/coding.py`, `tools/builtins/bash.py`, `tools/toolsets/coding.py`) gives `@intent=9, preceded-by-comment=0`, and #747 has no comment line over 72 columns.
  - One block is also unevenly filled, which the entry forbids ("fill the lines evenly"): `model_configs.py:109-110` reads `# True in explicit managed mode, or when AUTO selects a` / `# Vidbyte key.`.
  Failure: `comment-format.md` says: "Keep `# @intent <name>` on its own first line." The agentic deep-dive says: "The first sentence after `@intent` should make the intent clear." The PR copied the older summary-first idiom from `DecisionModelConfig`, which spec §11 names as the code-style exemplar. The owner's newer ruling, recorded in the field guide at 22:04 before the first S3 commit at 22:50, replaces that idiom. The owner would ask for these blocks to be reformatted.
  Smallest fix: give each method its one-line summary as a docstring (as #747 does) or delete the summary, so each block opens with `# @intent <slug>`. The A002 positions do not change.
  Spec IDs: §12.4 (`@intent`).

R-V3 [Minor] [lint A002; §12.4] vidbyte/lib/http/vidbyte_gateway.py:129 — `VidbyteGatewayTransport.__init__` is a new A002 finding that ratchet headroom hides, so the implementer's "every … provider … function carries one" claim is false.
  Evidence:
  - I compared `python lint/run.py --all --format json` at `a80f0660` with the same run in a scratch clone at `e91cf822`, filtered to the changed files. The only added finding is `> A002 vidbyte/lib/http/vidbyte_gateway.py __init__ | def __init__(self, inner: HttpTransport, *, provider: ModelProvider, model: str, api_key: str) -> None:`.
  - The net A002 count fell 658→653 (baseline 703) because six old sites were fixed, which masks the new finding.
  - A002 scans lines def−3 to def+20, which is lines 126-149 for this method. The `request` marker at `:150` is one line outside that window.
  Failure: §12.4 says: "Every function that handles keys, requests, providers or retries has a `# @intent <slug>` within 20 lines." The S3 report says: "Every new key, request, provider and retry function carries one." The `__init__` stores the bearer key and the provider, and it has no marker.
  Smallest fix: give `__init__` its own `@intent` block. One option is to say why one transport is built per call: it keeps one key per call and holds the bearer that only the gateway receives. Confirm with `python lint/run.py --rule A002 --all | grep vidbyte_gateway` printing nothing.
  Spec IDs: §12.4.

R-V4 [Minor] [AGENTS.md style 1] vidbyte/lib/dataclasses/model_configs.py:106 — `validate()` → `resolved_api_key()` → `is_vidbyte_managed()` is a new own-class chain two levels deep, and it runs the environment fall-through a second time.
  Evidence: `:102 if self.is_vidbyte_managed():` … `:106 self.resolved_api_key()`, then `:135 def resolved_api_key` → `:141 if self.is_vidbyte_managed():`. At `origin/main`, `resolved_api_key` did not call `is_vidbyte_managed`.
  Failure: AGENTS.md style 1 says: "a function may call another of its own functions, but that second function should not call a third", and it applies to "code you change". A reviewer would ask for the second check to be removed, because `validate()` already knows the config is BYOK on that line.
  Smallest fix: replace `:106` with `ProviderModelRegistry.resolve_api_key(provider, self.api_key)`. `provider` is already computed at `:96`, and the BYOK behavior and its error message stay the same.
  Spec IDs: §12.4 (call chains one level deep).

R-V5 [Minor] [AGENTS.md style 4 and Placement] vidbyte/lib/http/vidbyte_gateway.py:41-51 — `_GatewayAnswer` is a mutable, unvalidated per-attempt record, written as a plain `__slots__` class beside its only user. It tags its outcome with exception classes (`raised: type[Exception] | None`), where AGENTS.md wants a closed set typed as an enum.
  Evidence: `__slots__ = ("body", "raised", "response")`; `__init__` assigns three public, mutable attributes. `_send` returns it (`:192`, `-> _GatewayAnswer`), and `failure_reason` branches on `self.raised is ProviderRequestError` (`:82`).
  Failure: AGENTS.md style 4 says "Prefer `@dataclass(frozen=True, slots=True)` … type any field whose value comes from a small, closed set as an enum." Placement would then require any such dataclass to live in `vidbyte/lib/dataclasses/`. The owner's #432 comment, cited in `strict-config-dataclasses.md`, asked that "all function inputs should be dataclass in vidbyte/lib with strict input validation". Spec §8.4 allows one module-private helper class "that classifies failures", but not one that holds per-attempt state. The class also mixes a record with the status-to-remedy table (style 3: describing it "needs the word 'and'").
  Smallest fix: this is a follow-up, because a frozen `GatewayAttempt` record in `vidbyte/lib/dataclasses/` with an enum outcome would be a fourth new class, which exceeds §8.4. It needs the user or orchestrator to approve a budget change. Within the current budget, state the exemption in the class docstring: it is a module-private, single-use attempt record, and the type tags stand for "no answer: transport failure" and "no answer: other exception".
  Spec IDs: §8.4 (budget tension), D-17 (classification recorded in locals).

R-V6 [Minor] [agentic file headers; §12.3 rows 3 and 5] vidbyte/lib/constants/jev.py:6 — The header's COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES and RELATED DOCS still describe only TypeSafe. The new generative-gateway values follow Vidbyte's backend contract, one comment cites "backend 9.2.8" without saying where that document is, and the `model_configs.py` inventory misdescribes `resolved_api_key`.
  Evidence:
  - `model_configs.py:13` still reads `- resolved_api_key: Resolves provider key by delegating to ProviderModelRegistry.`, but in managed state the method now returns `VIDBYTE_MANAGED_KEY_PLACEHOLDER` (`:141-142`).
  - `:6 COMMON MODIFICATION PATTERNS: Change a vendor limit only after TypeSafe documents it; local sanity caps stay generous because the API enforces the real (token) limits itself.`
  - `:9 RELATED DOCS:` lists only Jev design docs and docs.typesafe.ai URLs.
  - `:68 # The six providers the generative gateway dispatches (backend 9.2.8).`
  - In fact, `VIDBYTE_API_KEY_PREFIX` must equal the vendored contract's `api_key_prefix`, `VIDBYTE_GATEWAY_TIMEOUT_FLOOR_SECONDS` tracks the backend's 600 s deadline, and `VIDBYTE_MANAGED_TEXT_PROVIDERS` tracks the backend dispatch table.
  Failure: the agentic-engineering obligation is "file headers accurate against the finished code". An agent that follows `:6` would treat 630.0 or the provider set as TypeSafe vendor limits. PURPOSE and ROLE were updated (row 3) but these three fields were not.
  Smallest fix: add one clause to each field.
  - Modification pattern: "change the managed generative values only with the backend gateway contract (`lint/contracts/vidbyte-platform-contract.json`; `docs/spec/managed-generative-models/spec.md` §9.2)".
  - RELATED DOCS: add that spec.
  - Comment at `:68`: replace "backend 9.2.8" with that resolvable reference.
  - `model_configs.py:13`: append "(the placeholder in Vidbyte-managed state)".
  Spec IDs: §12.3 rows 3 and 5, §12.4 (A001 header text).

R-V7 [Minor] [field guide strict-config-dataclasses.md] vidbyte/lib/dataclasses/model_configs.py:160 — The managed "no custom endpoint" predicate is a new inline copy of `DecisionModelConfig`'s, so the rule that keeps the Vidbyte bearer off a caller URL now has two owners.
  Evidence: Text `:160` is `if self.endpoint is not None and (not isinstance(self.endpoint, str) or self.endpoint.strip()):`. Decision `:435-436` is `if self.mode is DecisionModelMode.VIDBYTE_MANAGED and self.endpoint is not None:` / `if not isinstance(self.endpoint, str) or self.endpoint.strip():`, the same predicate with a different message. The non-string `api_key` check (`:127` vs `:464`) is a second copy, but D-14 keeps Decision's line on purpose, so only the endpoint copy counts here.
  Failure: `strict-config-dataclasses.md` says: "Two independent inline copies of the same rule drift silently". Spec D-14 cites that lesson for the key check. The next change to managed-endpoint policy, such as also refusing a Vidbyte origin passed as an endpoint, would have to be made in two places.
  Smallest fix: this is a follow-up, not something for the repair loop. One shared owner, such as a helper that takes each config's existing message so INV-19's Decision text stays byte-identical, adds public surface (spec §8.4: "2 registry classmethods") or a new file (C008's `validation.py`). Either needs a budget waiver from the user or orchestrator.
  Spec IDs: D-14 (spirit), INV-19 (must stay unchanged), §8.4.

VERIFIED CLAIMS:
1. **Does not hold.** S3: "Every new key, request, provider and retry function carries [an `@intent`]". `VidbyteGatewayTransport.__init__` is a new A002 finding (R-V3).
2. **Holds.** S3: "There are no numeric literals in the new code." A grep of added non-comment lines in `lib/http`, `lib/runners`, `lib/dataclasses` and `lib/registries` finds digits only in the module docstring and in message text. A007 is 254 at both `e91cf822` and `a80f0660`.
3. **Holds for new code.** S3: "The only `vb_live_` literal is `VIDBYTE_API_KEY_PREFIX`." `git grep vb_live_ -- vidbyte/` finds `constants/jev.py:62` plus the two pre-existing `providers/typesafe.py:255,271` sites, which are the 2 that C020 still counts.
4. **Holds.** S3 and §12.5: contract blob `56d4d0b373994f5de6affd675ed4c209e64d589d` with no BOM. `git hash-object` prints that blob, and `od -c` shows `{ \n`.
5. **Holds.** S3 and AC-17 lint: `SDK-LINT: PASS` with C017 0, C018 1, C019 0, C020 2 and S064 4. No rule count rose against `e91cf822`.
6. **Holds.** S3: semgrep reports 0 findings ("Ran 1 rule on 872 files: 0 findings.").
7. **Holds.** S3: the pack has 32 passing tests (`32 passed in 0.87s`, with `PYTHONPATH` resolving `vidbyte` to this worktree).
8. **Holds.** S3: "`git diff e91cf822..HEAD -- tests` is empty." The `--stat` output is empty.
9. **Holds.** AC-19 and NFR-4: production `.py` files change only under `vidbyte/lib/` (9 files).
10. **Holds.** §12.5 "Not required" items:
    - `.env.example` does not exist.
    - `llms.txt` has no `TextModelConfig`, `TextModelRunner`, `DecisionModelMode` or `VIDBYTE_API_KEY` content.
    - `vidbyte/lib/http/__init__.py` has an empty diff.
    - The root `__all__` is unchanged (C016 CLEAN).
    - No rule reads `llms.txt` or `artifacts/file_index.md` for parity. S020 is opt-in by a "File Index" heading and stays at 1.
11. **Holds.** S3: "`jev.py` is about 757." `wc -l` prints 757. Every touched file is under 1,000 lines.
12. **Holds.** §12.4: no suppressions. The added lines contain no `type: ignore`, `noqa` or `pragma`.
13. **Holds in content but not in placement.** S3: "These main functions are narrated." The narration exists, but its placement fails the comment-format entry (R-V1, R-V2).

COMMANDS RUN:
- `git log --oneline -20`; `git status --short` → HEAD `a80f0660`, clean. The only untracked file was the parallel `S4-review-conformance.md`.
- `git fetch -q origin` (run once by mistake). It changed nothing: `git rev-parse origin/main` still prints `576390804c1fb89367c4524a37c492eb8076ece4`, and the merge-base is still `00cbd6db`.
- `git diff --stat origin/main...a80f0660` → `31 files changed, 4671 insertions(+), 21 deletions(-)`.
- `git diff origin/main...a80f0660 -- <each code path>`; read every changed production file whole.
- Added-comment width check: `git diff -U0 … | grep '^+' | awk 'length($0) > 72' | grep -E '^\s*#'` → no output.
- Per-file wide-comment check: `awk 'length($0) > 72 && $0 ~ /^[ \t]*#/'` → `text.py:62: 93`, `model_configs.py:136: 79` in edited blocks. The rest are pre-existing lines in untouched blocks.
- `@intent`-first-line check (awk) → 16 new markers preceded by a comment line. The same check on `git show 57639080:<#747 files>` → `@intent=9, preceded-by-comment=0`, `wide comment lines: 0`.
- `python lint/run.py` → `S064 retry-overall-deadline 4 4 RATCHETED` … `SDK-LINT: PASS`, `exit=0`.
- `python lint/run.py --all --format json`, run in the worktree and in a scratch clone at `e91cf822` (`git clone --shared --no-checkout` into the scratchpad, then `checkout e91cf822` inside the clone only). Counts that differ: `A002 base 658 branch 653`, `C012 base 24 branch 23`, `C020 base 4 branch 2`. Filtered diff of changed-file findings: the only addition is `A002 vidbyte/lib/http/vidbyte_gateway.py __init__`.
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → worktree path. Then `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/sdk_managed_text` → `32 passed in 0.87s`.
- `pysemgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` → `Ran 1 rule on 872 files: 0 findings.`
- `git hash-object lint/contracts/vidbyte-platform-contract.json` → `56d4d0b373994f5de6affd675ed4c209e64d589d`.
- `git grep -n vb_live_ -- vidbyte/` → `constants/jev.py:62`, `providers/typesafe.py:255`, `:271`. `git grep model_gateway_ -- vidbyte/` → none.
- `git diff --stat e91cf822..a80f0660 -- tests` → empty. `git diff --name-only e91cf822..a80f0660 -- '*.py'` → 9 files under `vidbyte/lib/`.
- `PYTHONPATH=$(pwd) python -c "import <module>"` for `constants.jev`, `enums`, `http.vidbyte_gateway`, `runners.text` and `registries.models` → all "fresh import ok", so no import cycle from the new `constants.jev` → `enums.model_provider` edge.
- `PYTHONPATH=$(pwd) python -c` over `vidbyte.lib.constants.jev.__all__`. The 8 new constants are not in `__all__`, consistent with the module's 5 pre-existing `VIDBYTE_*` constants, so this is not a finding.
- Not run, per the briefing: `scripts/run_ci.py` (S3 quoted "CI passed." for both stages) and any `--update-baseline`.
- `git log --oneline -3` at the end of the run → HEAD moved during this review to `39a2b101` ("docs(spec): record managed-generative-models S4 reviews …"). It touches only the three S4 report files, so the code reviewed (`a80f0660`) is unchanged. That commit already held an earlier `S4-review-conventions.md`. This report overwrote it in the working tree (`git status` → ` M …/S4-review-conventions.md`), and the earlier text is still at `git show 39a2b101:docs/spec/managed-generative-models/reports/S4-review-conventions.md`. Its seven findings match these. This version includes its uneven-fill and `model_configs.py:13` points and its endpoint-copy finding (now R-V7, rated as a budget follow-up). The call-chain finding is rated Minor here, because the base already had `validate` → `resolved_api_key` → `normalized_provider`; the earlier version rated it Major.
