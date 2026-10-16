# S0 scout report: infinite-memory-prompts

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts`, branch `feat/infinite-memory-prompts`. HEAD moved from `7efceb55` to `73c13236` during the scout (the orchestrator committed `docs/spec/infinite-memory-prompts/{request,pipeline}.md`; `git diff --stat` between the two shows only those two files, so every code fact below holds at both). The scout made no commits and left only two new files: `context/code-map.md` and this report.

## Planned reading list

1. `AGENTS.md`, `REPO_MAP.md` (prompts and agents entries), gates reference, field guide index and linked topics.
2. This run's `request.md`; base spec `spec.md` §1, §6.1, §9.2; base `request.md` §A, §C, §D; `pr-body.md`.
3. `vidbyte/prompts/catalog.py`, `vidbyte/lib/enums/prompts.py` (INFINITE_MEMORY block), the family JSON and all 40 `.md` assets.
4. Consumers: `vidbyte/agents/infinite/{agent,runtime,launch,memory,workspace,journal,settings,__init__}.py` and `README.md`; `vidbyte/lib/{constants,enums,registries,dataclasses}/infinite.py`; `vidbyte/lib/util/text.py` (TokenEstimate); `vidbyte/tools/toolsets/infinite.py`; `vidbyte/middleware/builtins/delegation_limits.py`; the compaction middleware's trim constructor.
5. Lint: S025 in full, A009, S020, S010, `lint/README.md` head, baseline entries.
6. Tests: the whole `tests/features/infinite_memory_agent/` pack (7 test files, fixtures, FEATURE.md, README.md); tests outside the pack that mention the family; `scripts/test-prompt-templates.py` header; pytest config.
7. Style references named by the request: `vidbyte/prompts/prompts/jev_bulk_work/` and "the coding-agent prompt family"; `vidbyte/agents/coding.py` header.
8. Measurement of all 40 leaves (chars, bytes, chars÷4, tiktoken cl100k_base, placeholders, trailing newline) with a scratchpad script run under `python -I`.

## Files actually read

All of the above, with these specifics:

- `docs/`: only the four named documents — this run's `request.md`; `docs/spec/infinite-memory-agent/spec.md` §1 (from line 33), §6.1 (from line 189), §9.2 (lines 735-795); `docs/spec/infinite-memory-agent/request.md` (§A verbatim prompts skimmed, §C key decisions through terminology and hints, §D in full); `docs/spec/infinite-memory-agent/pr-body.md` (headings, prompt-related lines, Verification, Deviations, Follow-ups). `pipeline.md` was not read.
- Field guide: `init.md`, `prompt-families.md`, `model-facing-tool-contracts.md`, `comment-format.md`, `local-ci-verification.md`, `review-scope.md`, `runtime-boundaries.md`.
- Code: everything in item 4 of the plan; `scripts/run_ci.py:55-110` and `:211`; `vidbyte/middleware/compaction/context_compaction.py:137-160`; `lint/rules/a009_*` key lines; `pyproject.toml` pytest block; `vidbyte/agents/coding.py` header; listing of `vidbyte/agents/coding_context/` and `vidbyte/prompts/prompts/`; sizes of every `.md` prompt asset in the repo.
- Tests: the pack in full; `grep prompt_text(` and `Prompt.INFINITE_MEMORY_` across the pack for the definitive per-leaf list; headers of the five outside tests that mention the feature.
- Measurement script: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad/s0/measure.py`, run once with `python -I`; tiktoken 0.12.0 imported.

Not read (recorded as unverified in the code map §4.18): `agentic_engineering/system_prompt.md` (candidate style reference), the body of `MessageHistoryCompactionMiddleware` beyond the constructor's one-line comment, S062's full rule.

## What the briefing, request, and gates reference got wrong or stale

1. **Root prompt formatting.** The request's Terminology and hints say `root_system_prompt.md` is "formatted with `{max_parallel}` and `{max_depth}`". At HEAD `agent.py:72-75` uses it raw, the file holds no braces, and PR #1113 removed that formatting (field guide `runtime-boundaries.md` check: `grep "format(max_"` empty). The intent comment at `agent.py:68-71` documents the rule.
2. **The 1k floor is already met by three of the seven assets.** Root 1,829 / generator 1,277 / verifier 1,059 tiktoken tokens (2,129 / 1,503 / 1,246 by `TokenEstimate.count`). The root exceeds the request's 1,100-1,500 band by both measures. Only task_prompt, verifier_task_prompt, resume_prompt, and launch_tool_description are below 1,000. The orchestrator's baseline figures are confirmed except that its chars÷4 values were floors (1502, 1245, 285, 272, 494) where `TokenEstimate.count` rounds up (1503, 1246, 286, 273, 495).
3. **S025 is misdescribed.** It is a four-sentence minimum on statically resolvable `ToolSpec`/`ToolParameter` description literals and exempts `prompts.get(...)`; it never reads `.md` assets. A prompt-only change cannot move it.
4. **"The coding-agent prompt family" does not exist.** CodingAgent has no default system prompt and no family; its model-facing sections are context items from `vidbyte/agents/coding_context/`.
5. **`vidbyte/prompts/prompts/infinite_memory/` has no README** (the request asked to check). The two READMEs that describe the family are `vidbyte/agents/infinite/README.md` and `vidbyte/prompts/README.md`; the one sentence that becomes false under a size change is `vidbyte/agents/infinite/README.md:68` ("about 2,100 tokens … about 5,000 … near 105,000"), echoed by the Python header `vidbyte/lib/constants/infinite.py:5`.
6. **Gates reference says semgrep is part of `run_ci.py`.** It is not: `run_source()` runs the bytecode check, `lint/run.py`, `compileall`, three `scripts/check_*.py`, and `pytest`; semgrep is a separate command (field guide `local-ci-verification.md`). The package stage's smoke test does read every prompt asset (`assert Prompts().keys()`).
7. **PR body is stale on leaf storage**: it says "their four `.md` files"; after PR #1113 all 40 leaves are `.md` and the family JSON holds only `{path, source_url}`. The enum header now says 139 assets across 35 families (the PR body said 138/34).
8. **Spec §9.3 defaults differ from code** (10/10/200 caps, 100 iterations, 60-token entries, quota 5 in the spec; 20/20/1,000, 500, 150, 25 in `constants/infinite.py`). Prompts carry no numbers, so this only matters if the spec author copies numbers from §9.3.
9. **No test pins the text of 29 leaves** beyond the two all-leaf contract tests (40-leaf non-blank set and the coding-word ban); 11 leaves are regex-pinned through `template_regex(prompt_text(...))`, which tracks rewrites automatically as long as the literal text survives formatting; the seven `launch_<field>_description` leaves are `fullmatch`ed against the schema. S2's new tests are the only guard on the seven behavior-shaping assets' content.

## Facts the next stage should not miss

- 13 leaves are `str.format`ted and must hold no literal braces and keep each placeholder exactly once; the other 27 are raw. Formatted leaves end without a trailing newline, raw leaves with one.
- No numeric limit may appear in any leaf (field guide, README:75/114); refusals name limits from code strings listed in code map §2.2.
- Banned words in every leaf: `git`, `repo(s|sitory|sitories)`, `worktree(s)`, `pull request(s)`, `single writer`, `one writer`.
- `result_card` must not contain `" … [cut]"`; `quota_line` must render its integers as standalone tokens; `memory_rejected_prompt` must not be relied on for the EC-18 "note/pointer" advice.
- Any new test file S2 adds must be listed in the pack README's `## File Index` (S020) and dated in `## Logs`.
- Index line endings are LF; measure tokens through `Prompts().get(...)`.
