# S1 spec author — report

Spec: `docs/spec/infinite-memory-prompts/spec.md` r1, committed as `f70e65a2` ("docs(spec): add infinite-memory-prompts spec r1") on `feat/infinite-memory-prompts` over `68227a58`. This report is left uncommitted for the orchestrator's pipeline commit, as S0's was.

## What I read

- Run inputs: `request.md` (in full, twice — once before the usage-limit stop, once after), `context/code-map.md` (171 lines), `pipeline.md`, `reports/S0-scout.md`; the pipeline references `spec-template.md`, `house-style.md`, `vidbyte-gates.md`; `AGENTS.md`; field guide `prompt-families.md`, `model-facing-tool-contracts.md`, `runtime-boundaries.md`, `comment-format.md`, `review-scope.md`, `local-ci-verification.md`.
- Base-branch design record (the only `docs/` files allowed): `docs/spec/infinite-memory-agent/request.md` §A + §D, `spec.md` §1, §3, §6.1 (INV-1…INV-39), §9.2, `pr-body.md`.
- Code: all 40 `.md` assets and `infinite_memory.json`; `catalog.py` (`_resolve_prompt_text`, `_validate_enum_sync`); `agents/infinite/{agent,launch,memory,workspace,runtime,journal,settings}.py`; `middleware/builtins/delegation_limits.py`; `lib/constants/infinite.py`; `lib/util/text.py`; `lib/enums/prompts.py`; `agents/infinite/README.md`; `prompts/README.md` (`:55-75`, `:220-260`); `prompts/prompts/jev_bulk_work/`; `scripts/run_ci.py` (`:72-91`, `:211`); `pyproject.toml`; the feature pack (`infinite_memory_fixtures.py`, the contract/delegation/verification/workspace/resume modules at the pinned lines, pack `README.md`, `FEATURE.md`).
- Measured, not assumed: every leaf's chars / `TokenEstimate.count` / tiktoken cl100k_base through `Prompts().get`, placeholder sets via `string.Formatter().parse`, brace counts, trailing newline, digits, banned words (script `scratchpad/s1/measure_leaves.py`); the §4 snippet (`scratchpad/s1/snippet.py`) run from the worktree; a Stage E self-check of the spec against the family on disk (`scratchpad/s1/selfcheck.py`, `idcheck.py`): section order, ID contiguity, all 40 names in §8.5 and §12.3, placeholder sets, baselines, and that every phrase marked *kept* is present at `base_commit` and every phrase marked *new* is absent.

## Approaches weighed (§8.1 D-1, §8.3)

1. **Layered distribution by stage (chosen).** Standing per-role rules in the three system prompts (existing heading sets kept), the moment-of-use checklist in the three briefing templates, why/when + cross-field card rules in `launch_tool_description`, one nudge per compact description, at most one per reply, none in the three shape leaves. Meets G-1 (every stage) and G-3 (nothing that rides along on every call grows).
2. **Repeat the full rule set at every point of use.** Rejected: multiplies per-call cost (24 descriptions are in every schema), contradicts D-C and P1.
3. **Redistribute text out of the system prompts into the four sub-floor assets without adding rules (smallest).** Rejected: the system prompts would shrink below their baselines (orchestrator's ruling: no asset ends shorter), and the user said "expand".
4. **Concentrate all new rules in the three system prompts.** Rejected: four of the seven stay under the floor and the moment-of-use stages get no checklist.

## Disagreements with the request / scout, with evidence

- **The request's `{max_parallel}`/`{max_depth}` sentence is stale.** `agent.py:72-75` consumes the root system prompt raw (`f"{settings.system_prompt}\n\n{rules}"`); `grep -rn "format(max_" vidbyte/agents/infinite` is empty. Spec INV-22 / A-6 record the code's truth; the scout had already flagged this.
- **No "coding-agent prompt family" exists** as a second style reference (request §C D-F). Only `jev_bulk_work` is used (A-4); the orchestrator already ruled the same.
- **The #1113 text already carries most of the principle language.** My Stage E check found that 21 of the 23 compact-description nudges and 6 of the 7 reply anchors I chose exist verbatim at `base_commit`, and so do about half of the system-prompt/briefing phrases. I therefore split every §8.5 phrase into *kept* (must survive) and *new* (must be added; absent today), so S2's phrase test is red-before-green on the new ones and the four sub-floor assets, and §12.3 says rows 8–30 are "keep, check against code truth, tighten within bound", not a rewrite for its own sake. The request's framing ("the other 33 leaves are rewritten compactly") overstates how much changes there.
- **The 24-description sum is 4,950 by `TokenEstimate.count`, not 4,926** (scout): `TokenEstimate.count` is `ceil(len/4)` per leaf; the scout's figure sums `len//4`. Same cause for the pipeline.md baseline table (generator 1502 vs 1503, verifier 1245 vs 1246, task 285 vs 286, resume 272 vs 273, launch 494 vs 495). The spec carries the `TokenEstimate.count` values, which are what AC-1 prints.
- **README figures are chars/4, not tiktoken.** `agents/infinite/README.md:70` says "Tokens are estimated as characters divided by four everywhere", so row 42 / INV-20 / AC-11 update line 68 with `TokenEstimate.count` figures; "about 5,000" (4,950 today) may stay true.
- **Digits exist today only as ordered-list markers** (`1. **Orient.**` etc. in the three system prompts), so the "no numbers" rule is stated precisely as "no digit except `^\d+\. `" (INV-13) rather than "no digits".
- **The pack has seven test modules + fixtures, not eight modules** (request §C "eight files" counts the fixtures module).
- **mypy is not in the local gate** (`pyproject.toml:47` lists it; `run_ci.py` and `lint/run.py` never invoke it) — §11 says so instead of inventing a typecheck command.
- **An interrupted pair is relaunched under the same name** (current `resume_prompt`: "the same name runs a pair from scratch"); my first draft said "under a new name" and the self-check against the leaf caught it — fixed in outline 6.

## Least-sure assumptions

- **A-3** — the system-prompt ceilings (root 2,600 / generator 1,900 / verifier 1,600 tiktoken) and the compact bounds (0.8–1.25 × baseline, 23-sum ≤ 4,500, replies ≤ 80) are my margins; the user set no ceiling. They exist so G-3 is testable; flip freely.
- **A-2** — tiktoken is importable here but not a declared dependency; the floor test must skip (with a message) where it is missing, so the binding measure is weaker in such an environment (EC-12; mitigated by the 1,100 margin and the ratio ≈ 0.85 recorded).
- **A-7** — expansion by repetition (EC-11) is review-only; I found no mechanical check that distinguishes a repeated rule from a new one.
- The phrase set itself: 3–6 per behavior-shaping asset, chosen to state rules in plain English with no digits and no banned words; any reviewer who prefers a different sentence for a rule should change the phrase in §8.5 before S2 writes against it, since the phrases are the test contract (D-4).

## Open questions carried

- Q-1 floor on all 40 leaves — default no (A-1). Q-3 "content is data, not instructions" rule — default no (D-13; the code holds the controls, §10 T-2). Q-2 resolved by the orchestrator (README yes, Python header no).
