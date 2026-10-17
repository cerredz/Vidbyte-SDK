LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the PR follows the repo's rules, but the procedure it teaches breaks a field-guide lesson: the A13 structured-output row trips a known branch-scoped harness test, and the known-red rule then turns that into a false `PROOF_FAILED` that stops the loop.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Placement and indexing are correct. The skill folder holds only two Markdown files (`git ls-files` shows exactly SKILL.md and references/provider-run.md). No README is needed: 20 of the 21 `skills/*/` folders have none, no lint rule requires one, and C12 pins the two files. `llms.txt` (its exclusion list at line 1198) and the header of `artifacts/file_index.md` exclude both `.claude/` and `tests/`, so REPO_MAP is the only index to update, and it was updated.
- The REPO_MAP `.claude/` entry follows `agents-md-map.md`: five sentences, with no file name, child path or command. It is true to the tree: `ci-settings.json` still denies `Bash(git push)` and `Bash(git push *)`, and `claude.yml:50` still loads it. It also drops the false sentence "Interactive sessions … do not load it".
- The new test pack matches its siblings (`sdk_provider_keys`, `agent_output_connectors`). It has README (Intent / Non-Goals / File Index / Logs) and FEATURE.md with every section the feature-test-pack doctrine names. Every one of the 6 `.py` files carries all 7 A001 fields, plus FUNCTION INVENTORY and WHAT NOT TO DO. A001, S062, A009, S020, A002 and S060 report 0 findings in the pack, and ruff passes. No bytecode is tracked.
- The 33-row wiring table matches spec §12.3 byte for byte, and so does the brief against §8.5. Every row path and symbol exists on current `origin/main` (845a4d9b). Seven rows were spot-checked against the Mistral, Meta and Kimi wiring: A6 lowercase qualified keys, A10 `*_MODEL = "text"`, A11 the one-line subclass plus `__all__`, A12's four touch points, C7 `VENDOR_BASES` and `K_META` built with `+`, C9 `json_body` (the real `HttpTransport.request` kwarg), and C10's tuple shape. All of them match. Every git command in provider-run.md is `git -C`.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Blocker] [field-guide] .claude/skills/onboard-model-provider/references/provider-run.md:300-310 (with row A13 at :167) — The known-red rule turns the field guide's documented branch-scoped failure into a false `PROOF_FAILED gate-source` for every vendor that gets an A13 tier
  Evidence: The field guide `local-ci-verification.md`, entry "Two `harness_threads` surface tests fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports", says: "Do: Classify it as pre-existing. Prove it with a one-line edit to a `vidbyte/tools` file on a clean main worktree … #1036 shipped them as branch-scoped checks that diff `merge-base origin/main HEAD`, so they are green on main (empty diff) and red on every branch with intended changes there."
    - `tests/features/harness_threads/test_harness_threads_surface.py:224-232` reads `scoped = ("vidbyte/tools", "vidbyte/lib/configs", OLD_SPEC_FOLDER)` and `changed = git("diff", "--name-only", base, "--", *scoped)` … `assert changed.stdout.split() == []`. It is present at 72a4ade1 and on origin/main (both at `:224`).
    - Row A13 edits `vidbyte/lib/configs/structured_output.py` (`PROVIDER_SUPPORT`). All six existing compatible vendors carry an entry there (MISTRAL NATIVE_SCHEMA; DEEPSEEK, GLM, KIMI and MINIMAX JSON_MODE; META PROMPT_ONLY at `structured_output.py:40-47`), so A13 is the sibling norm, not an edge case.
    - provider-run.md:302 says a node may be excluded only when "pytest reports that node failed … in at least one of up to 3 runs on a twin worktree built from the base SHA", and :310 says "Anything else ends the run `PROOF_FAILED gate-source`."
    - In the `<worktree>-main` twin, HEAD is the base, so `merge-base origin/main HEAD` is the base and the scoped diff is empty. The test passes 3 of 3 there, while it fails 3 of 3 on the branch.
  Failure: Every provider run that adds an A13 tier, which is any vendor that documents JSON mode or a JSON schema, reaches the one-shot gate and ends `PROOF_FAILED gate-source`. That stops the whole session (FR-9, INV-7). The user asked for a "continuous, 24/7" run, and it would halt on its first realistic vendor because of a trap the field guide already records. Spec §11 says `local-ci-verification.md` was applied, but D-15 and §11 Baseline name only the failure-code test and the MCP flake. A reviewer would write: "The field guide says this test is red on every branch that touches lib/configs; classify it with the control edit, don't stop."
  Smallest fix: In §8.3, add the field guide's method as a second way to prove a failure is pre-existing. A failing node from a test that diffs `merge-base origin/main HEAD` (today `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`) is excluded when two things hold. First, the branch's only changes under that test's scoped paths are checklist rows (A13). Second, the same node fails the same way on the `<worktree>-main` twin after a one-line control edit to a file under `vidbyte/lib/configs`. The twin is already removed with `--force`. Record both outputs. Cite the entry in D-15 and spec §11. (Dropping A13 instead would change the 33-row table that W1 pins, which is a larger change.)
  Spec IDs: FR-9, INV-15, D-15, EC-39, EC-40, §12.3 A13, §11 (field-guide entries applied); request §D "continuous, 24/7"

R-V2 [Major] [field-guide] .claude/skills/onboard-model-provider/references/provider-run.md:40, :84, :203 — The procedure never checks the vendor's response path or usage key names, and its wire test answers with usage keys no chat-completions vendor sends
  Evidence:
    - provider-run.md:40: "A fact is a base URL, chat path, auth scheme, environment variable, model ID, price, price unit, key prefix, tool support or structured-output tier. Nothing else from a page enters code or the PR."
    - provider-run.md:84 (Dialect) checks only Bearer auth, `/chat/completions` and "another request shape".
    - provider-run.md:203: `vendor = ScriptedGateway(provider_answer(ModelProvider.<E>))`. For a member outside `_CHAT_PROVIDERS = frozenset({XAI, DEEPSEEK, KIMI})` (`tests/features/sdk_managed_text/managed_text_fixtures.py:58`), `provider_usage` returns `{"input_tokens": 12, "output_tokens": 2}` (`:115`).
    - Row A2's `ChatCompletionUsage.from_usage_payload` reads `payload.get("prompt_tokens")` and `payload.get("completion_tokens")` (`vidbyte/agents/pricing/compatible.py`). The C9 template asserts only the request.
    - `provider-api-contracts.md` says: "Do: … check every field type …, and response shape against them … Check: A scripted-transport test per documented answer example."
    - `vidbyte/providers/README.md:610-612`, "Adding A Provider" step 1, says: "record … the response path to generated text, and the exact usage key names". Step 4 (`:618`) says: "Guard usage extraction with the `isinstance` pattern above."
    - The AI21 seed row itself says: "Open: the response body shape".
  Failure: Two binding sources ask for a step the taught procedure omits. One is a field-guide lesson. The other is the providers folder README, which AGENTS.md:11 makes binding for edits in that folder. Line 40 even forbids recording those facts. Suppose a vendor reports `input_tokens` or another non-standard usage name. A2 then gives a usage class that parses nothing, and cost goes unrecorded without any error. `operation-pricebook-rates.md` calls this "silent — strictly worse than None". The C9 test still passes, because its canned answer was never the vendor's documented one. Every provider PR would draw the review comment "did you check the response against the vendor's API reference?".
  Smallest fix:
    - (a) Add "response text path and usage key names" to the fact kinds at :40.
    - (b) In §3.2 Dialect, require a first-party quote of a response example that shows `choices[0].message.content` and `usage` with `prompt_tokens` and `completion_tokens`; without it, the vendor is `not-openai-compatible`.
    - (c) In the C9 note, add `ModelProvider.<E>` to `_CHAT_PROVIDERS` in `managed_text_fixtures.py` (a C11 path, so FR-11 check (2) still passes), so the scripted answer carries chat usage keys.
    - Amend D-11 by one line to match.
  Spec IDs: D-11, FR-7, FR-9, INV-9, §12.3 A2/C9/C11, §11 (`provider-api-contracts.md` applied)

R-V3 [Major] [field-guide] .claude/skills/onboard-model-provider/references/provider-run.md:200 — The C9 template that every provider PR copies has a 93-column comment, against `comment-format.md` and against the procedure's own §5 rule
  Evidence: `awk 'length($0) > 72 && $0 ~ /^[[:space:]]*#/'` over provider-run.md prints `provider-run.md: 200: len=93` for `        # The gateway does not serve <s>, so the call is DIRECT, and only the <s> key leaves.` (103 columns once `<s>` is `cerebras`). provider-run.md:148 says: "Comments go above the line they explain, as `#` lines wrapped at 72 columns." `comment-format.md`: "Wrap every comment line at 72 columns, counting the indent … Check: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched." The sibling it is modelled on (`test_provider_keys_modes.py:379`) is also over-wide, so the subagent sees the wrong width twice.
  Failure: Every provider PR pastes a comment that the owner has already rejected ("stop writing comments like this"; PR #690). Spec §12.4 lists the 72-column rule as a standard of this change.
  Smallest fix: Wrap the template comment into two lines, each at most 72 columns with the 8-space indent and a 10-character slug: `# The gateway does not serve <s>, so the call is DIRECT,` and `# and only the <s> key leaves.`
  Spec IDs: §12.4 (72-column bullet), §12.3 C9

R-V4 [Minor] [sibling grain] .claude/skills/onboard-model-provider/references/provider-run.md:186, :213 — Row D1 adds an Endpoint And Auth Matrix row that none of the six compatible siblings has
  Evidence: The D1 Add cell says "one row each (D-24)", and :213 says "One row in each table, shaped like its neighbours". `sed -n '72,84p' vidbyte/providers/README.md | grep -c -i -E "mistral|kimi|meta|deepseek|glm|minimax"` prints `0`. Those vendors are covered by `| Generic | compatible.py | Authorization: Bearer | any OpenAI-compatible endpoint |`, and each has only an Official Provider Documentation row.
  Failure: §5 says "Copy the Mistral entry beside each symbol", but there is no Mistral matrix entry to copy. Each provider PR would then list one compatible vendor in the matrix while its six siblings are absent. A reviewer would ask why. Behavior does not change.
  Smallest fix: Make D1 add an Official Provider Documentation row only, and say that the matrix's Generic row already covers a `compatible.py` subclass. The Symbol cell may keep both headings, because W3 only checks that they exist.
  Spec IDs: D-24, §12.3 D1

R-V5 [Minor] [house format] .claude/skills/onboard-model-provider/SKILL.md:3 — The `description` says what the skill does and how to start it, but not when a person should use it
  Evidence: The description ends with "It never merges. Run it only by typing /onboard-model-provider." (756 characters, within the 1,536 limit). The repo exemplar `skills/jev-continuation/SKILL.md` ends with "Use it before adding or changing any JevDoneCheck …". Claude Code's skill guidance asks the description to say what the skill does and when to use it. With `disable-model-invocation: true`, the description is what a person sees in the `/` menu.
  Failure: This is house-format drift only. A person scanning the menu gets no trigger such as "Use when you want new model vendors researched and proposed as provider PRs without doing the research yourself".
  Smallest fix: Append one "Use it when …" sentence. AC-2 only checks that the description is non-empty and at most 1,536 characters.
  Spec IDs: AC-2, §12.4 (frontmatter bullet)

VERIFIED CLAIMS:
- S3: "All 46 S2 tests pass." HELD (`46 passed in 0.91s`).
- S3 and spec §6.2: "lint prints `SDK-LINT: PASS`". HELD (exit 0). The rules that scan the new files report 0 findings in them: A001 (IMPROVED 642→640, untouched code), S062, A009, S020 (1 known, allowance 1, not in this PR), A002 and S060. No rule count worsened.
- S3: "`## 5. Wiring checklist` holds the 33-row table, byte-identical to spec §12.3." HELD (diff empty apart from the duplicate §8.5 header my extraction caught).
- S3: "the brief, byte-identical to §8.5". HELD.
- S3, AC-10 and INV-24: "Nothing under vidbyte/, lint/, scripts/, .github/ or .claude/ci-settings.json changed." HELD (`git diff --quiet origin/main...32ca7991 -- vidbyte lint scripts .github .claude/ci-settings.json` exit 0).
- S3 drift section: "No wiring-checklist path or symbol changed" on origin/main. HELD (each path and backticked or heading symbol was checked against `origin/main` 845a4d9b; none missing).
- Spec §12.5: "`llms.txt` and `artifacts/file_index.md` exclude `.claude/`". HELD. Both also exclude `tests/`, so the new pack needs no index entry.
- Spec §12.4: "The procedure tells provider runs to read AGENTS.md and each touched folder README to the end". HELD. The README list at provider-run.md:30 names every tracked README of a checklist folder. `vidbyte/lib/enums`, `vidbyte/lib/constants`, `vidbyte/lib/configs` and `tests/` have none.
- Spec §12.4: "multi-line `#` comments … at 72 columns". PARTLY. The rule is stated at :148, but the template at :200 breaks it (R-V3).
- Spec §11: "Field-guide entries applied … `local-ci-verification.md`". DID NOT HOLD for its harness_threads entry (R-V1).
- Spec §11: "`provider-api-contracts.md` — mirror the vendor's own pages; price the exact versioned ID". PARTLY. The versioned-ID half holds, because `OpenAICompatibleProvider` reports `model=config.model` (`compatible.py:45`) and the self-check resolves every catalogued ID. The response-shape half does not hold (R-V2).
- Briefing questions:
  - Description: 756 characters, at most 1,536. Has no when-to-use clause (R-V5).
  - Frontmatter keys: exactly `name`, `description` and `disable-model-invocation` (YAML `True`).
  - Length: SKILL.md 241 lines; provider-run.md 366 lines.
  - Wiring table: the non-silent rows name their governing rule (S014, C009, C010, or the named tests). The 11 silent rows name the consequence of a skip but not the source that requires the row. That is not raised as a finding, because the 5-column grammar is pinned by W1/W2 and §5 says "Apply every row that applies".
  - Commit hygiene: one work item per commit, and IDs cited on every code, test and map commit. The `docs(spec)` pipeline commits cite none, which matches the pipeline's practice. No generated or cache file is tracked, and no key-shaped literal was found in the diff.
  - Local paths: `C:/Users/422mi` appears in the `docs/spec` artifacts, as it does in the `agent-output-connectors` specs already on main, so it is not raised.

COMMANDS RUN:
- `git diff --stat origin/main...32ca7991` → `22 files changed, 4705 insertions(+), 1 deletion(-)`
- `PYTHONPATH=<wt> py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `46 passed in 0.91s`
- `py -3.11 lint/run.py` → `SDK-LINT: PASS`, `lint exit 0`
- `py -3.11 lint/run.py --rule {A001,A009,S020,A002,S060} --all`, grep for the pack and `.claude/` → 0 hits each. `PYTHONIOENCODING=utf-8 py -3.11 lint/run.py --rule S062 --all` → 0 hits. Without UTF-8 output, the `--all` print crashes with `UnicodeEncodeError: 'charmap'`, an environment issue unrelated to this PR.
- `py -3.11 -m ruff check tests/features/onboard_model_provider_skill --config lint/ruff.toml --no-cache` → `All checks passed!`
- `git diff --quiet origin/main...32ca7991 -- vidbyte lint scripts .github .claude/ci-settings.json` → exit 0
- A diff of the spec §12.3 wiring rows and the §8.5 brief against provider-run.md and SKILL.md → identical; `BRIEF IDENTICAL`
- A per-row `git show origin/main:<path>` check of every wiring symbol and heading → `drift check done` (no MISSING lines)
- `git show {72a4ade1,origin/main}:tests/features/harness_threads/test_harness_threads_surface.py | grep -n "def test_branch_leaves_the_tools_and_configs"` → `224:` on both
- `grep -n -A16 "^PROVIDER_SUPPORT" vidbyte/lib/configs/structured_output.py` → 11 entries, including MISTRAL, DEEPSEEK, GLM, KIMI, MINIMAX and META
- `awk 'length($0) > 72 && $0 ~ /^[[:space:]]*#/'` over provider-run.md → `provider-run.md: 200: len=93`
- `grep -n -A14 "def provider_usage"` in `managed_text_fixtures.py` and `grep … ChatCompletionUsage` → the canned usage for a non-`_CHAT_PROVIDERS` member is `input_tokens`/`output_tokens`; the parser reads `prompt_tokens`/`completion_tokens`
- A README-presence loop over the checklist folders and over `skills/*/` → the procedure's list is complete; 20 of 21 skill folders have no README
- A secret grep over the `+` lines of the diff (sk-/ghp_/AKIA/xai-/LLM|/AIza/eyJ/BEGIN) → no lines
- `git status --short` after all runs → 0 lines (HEAD 1144e198)
