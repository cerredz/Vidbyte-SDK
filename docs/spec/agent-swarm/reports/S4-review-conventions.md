LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — the placement, layering, wiring, prompt and lint conventions hold, but the swarm's turn middleware is the only AgentMiddleware subclass in the SDK defined outside `vidbyte/middleware/`, and seven smaller doc, header and style gaps would draw owner comments.

Reviewed: `git diff origin/main...c0b167d3` (local HEAD 038118e2 differs only in `docs/spec/agent-swarm/pipeline.md`). Every changed product file was read in full, beside its sibling in `vidbyte/agents/infinite/`, `vidbyte/lib/*/infinite.py` and `vidbyte/middleware/builtins/`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- Placement and layering hold everywhere:
  - the enums are in `vidbyte/lib/enums/agent_swarm.py` and exported from `vidbyte/lib/enums/__init__.py:41,186-187`;
  - the records are in `vidbyte/lib/dataclasses/agent_swarm.py`, and the constants are in `vidbyte/lib/constants/agent_swarm.py`;
  - `AgentSwarmSettings` uses AGENTS.md exception 1;
  - no lib module imports upward;
  - the registry imports through the package (`vidbyte/lib/registries/runtimes.py:33`, a lazy import inside `resolve`);
  - `member.py` imports `AgentSwarmRuntime` only under `TYPE_CHECKING`;
  - `lint/run.py --all --format json` reports zero findings in any new file.
- The runtime-type wiring is exactly `runtime-boundaries.md:31-36`:
  - the enum member;
  - the registry entry;
  - `_LINEAR_LOOP_RUNTIMES`;
  - `_runtime_extension_kwargs`;
  - the refusal names `AgentSwarm`.
  `AgentSwarm._running` is set and cleared in `try/finally` (`runtime-boundaries.md:38-43`).
- The prompt family satisfies `prompt-families.md:3-8` and `model-facing-tool-contracts.md:3-15`:
  - one `.md` per leaf, and a JSON file with only `{path, source_url}`;
  - headed sections and no digits;
  - 5/4/4-sentence descriptions with no examples;
  - argument names as constants;
  - the enum header count 149/36 matches the catalog.
- Principles 1 and 2, the headers, and the docs are in place:
  - every main function is narrated (`AgentSwarm.arun`, `AgentSwarmRuntime.arun`, `_run_member`, `post_message`, `end_turn`, `AgentSwarmSettings.__post_init__`);
  - no helper calls a helper;
  - every new `#` block is at most 72 columns with `# @intent` first (the awk check prints nothing);
  - the A001 headers are on every module;
  - the package README has a File Index and Notes for agents;
  - the REPO_MAP entry has five general sentences, phrased like the infinite entry (`agents-md-map.md`).

FINDINGS (ranked, most severe first, max 15)

R-V1 [Major] [AGENTS.md placement / field guide] vidbyte/agents/agent_swarm/member.py:73 — AgentSwarmTurnMiddleware is the only AgentMiddleware subclass in the SDK defined outside `vidbyte/middleware/`. Its own inherited pattern, CodingAgent's agent-specific finish-review middleware, lives in `vidbyte/middleware/builtins/`.
  Evidence: `grep -rn "AgentMiddleware)" vidbyte --include=*.py | grep -v "^vidbyte/middleware"` prints only `vidbyte/agents/agent_swarm/member.py:73:class AgentSwarmTurnMiddleware(AgentMiddleware):`.
  The spec's own §8.2 names the pattern it inherits: "Finish-review middleware — `vidbyte/middleware/builtins/verify_command.py:review_finish`". That file's header (`verify_command.py:4`) says "Built by vidbyte/agents/coding.py (CodingAgent.__init__) … Not re-exported from vidbyte.middleware.builtins". InfiniteMemoryAgent's middleware, `DelegationLimitsMiddleware`, is likewise at `vidbyte/middleware/builtins/delegation_limits.py:29`. The bridge pattern for a higher-layer constructor argument is `session_failure_router.py:28-29` (`if TYPE_CHECKING: from vidbyte.sessions.failure.router import FailureRouter`).
  Failure: Field guide `blocking-lint-invariants.md:3-8` records the owner asking for a bridge middleware to live in `vidbyte/middleware/builtins/` "the same as every other built-in policy middleware", with its higher-layer parameter typed under `TYPE_CHECKING` only. `REPO_MAP.md:259-261` makes `vidbyte/middleware/` the layer for deterministic hooks, and AGENTS.md:9 says to "put new code where it says that kind of code belongs". A reviewer would write: "middleware is defined in the middleware layer; move this next to verify_command.py". `AgentSwarmTurnMiddleware` is a run-bound bridge with exactly that shape: it holds the `AgentSwarmRuntime` and forwards `after_tool_call` and `review_finish` to it.
  Smallest fix:
  1. Move the class unchanged to a new `vidbyte/middleware/builtins/agent_swarm_turn.py`. Give it an A001 header and `if TYPE_CHECKING: from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime`. Do not re-export it from `vidbyte.middleware.builtins`, as with `verify_command`.
  2. Import it in `member.py`.
  3. Update the headers of `member.py` and `runtime.py` and the package README's File Index line for `member.py`.

  A006 skips `TYPE_CHECKING` edges, and agents and middleware are one tier, so no lint regression is expected. Re-run `python lint/run.py --rule A006` to confirm. This adds one file, 24 against §8.4's budget of 23. Spec §14 makes exceeding the budget an "ask first", so the orchestrator has to amend §8.4 before the repair.
  Spec IDs: n/a (§8.4, §12.3 row 26; D-3 fixes the hook, not the module).

R-V2 [Minor] [field guide] vidbyte/lib/dataclasses/agent_swarm.py:113-146 — the lib record module grows three private `_check_*` helpers, and one of them hand-rolls a check the canonical validators lack.
  Evidence:
  - `def _check_agent(self)` (:113), `def _check_unlisted_fields(self)` (:119) and `def _check_kind_fields(self)` (:127).
  - :124 `if name not in _KIND_FIELDS[self.kind] and (type(value), value) != (type(defaults[name]), defaults[name]):` is a primitive "must keep its default" check written inline.
  - The sibling `vidbyte/lib/dataclasses/infinite.py` defines only `__post_init__` methods (:53, :94, :117, :135, :157, :183). Its header's COMMON MODIFICATION PATTERNS says: "A check the canonical validators lack becomes a new option or method there, never a helper here."
  Failure: `strict-config-dataclasses.md:61-66` comes from the owner's PR #1084 comment on this exact sibling. Its check is "The record module defines no `_..._field` helpers", and both `_check_unlisted_fields` and `_check_kind_fields` match it literally. A reviewer would write: "no private field helpers in lib records; add the option to RecordFieldValidator". The older `vidbyte/lib/dataclasses/coding.py:110-157` (`_check_*`) predates that lesson, so it is not precedent.
  Smallest fix: The field-guide fix is an option on `RecordFieldValidator`, for example a `require_default(value, field_name, default)`. Spec §14 makes any `validation.py` change an "ask first", so that path needs the user's decision. The no-ask alternative is to fold the three helper bodies into `__post_init__` as the record's own per-kind rule. Run `python lint/run.py --rule S008` and `--rule S024` afterwards, because the inlined body may cross C901's 10-branch limit; if it does, only the validator option remains.
  Spec IDs: n/a (§12.4 row 2 "validates … only through RecordFieldValidator / RecordFieldConverter").

R-V3 [Minor] [agentic-engineering headers] vidbyte/lib/constants/agent_swarm.py:9; vidbyte/agents/agent_swarm/events.py:9; vidbyte/agents/agent_swarm/runtime.py:9 — three file-header sentences are false against the finished code.
  Evidence:
  1. `constants/agent_swarm.py:9` says: "the loop's own isDone is refused by the tool catalog itself." The code at `vidbyte/tools/_internal.py:51-53` is `return tools.add(IsDoneTool(), replace=True)`, which replaces the tool rather than refusing it. A script built `AgentSwarmSettings(..., search_tool=<BaseTool named "isDone">)` and then the member's runtime. It printed `settings accepted isDone search tool` and `runtime built; tools: ['bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone']`. The developer's tool was dropped without an error.
  2. `events.py:9` says: "elapsed_ms is … since this record was built, which AgentSwarm does when the run starts". But `AgentSwarmRuntime.__init__` builds it (`runtime.py:53`), and `events.py:4` itself says "Built by AgentSwarmRuntime".
  3. `runtime.py:9` says: "On TIMEOUT every member task is cancelled, so no member gets AGENT_FAILED". But an agent that failed before the limit keeps the `AGENT_FAILED` that `_fail` recorded at once (`runtime.py:137, 245-250`).
  Failure: The file-header practice (`agentic-engineering/references/file_headers.md`; A001) exists so that the next agent can trust the header instead of the code. Sentence 1 tells a maintainer that `isDone` is already guarded, so nobody adds it to `AGENT_SWARM_RESERVED_TOOL_NAMES`. Meanwhile `settings.py:98-104`, the README ("may not take a swarm tool's name") and INV-21 ("plus the developer's search tool when one is given") all promise otherwise.
  Smallest fix: Reword the three sentences. For 1, say that a search tool named isDone is accepted and silently replaced by the loop's own isDone. Optionally, reserve `"isDone"` in `AGENT_SWARM_RESERVED_TOOL_NAMES` so the EC-33 refusal covers every name INV-21 lists. That is a behavior change; the sibling's `INFINITE_RESERVED_TOOL_NAMES` omits it too, so leave it to the conformance and engineering verdicts.
  Spec IDs: INV-21, EC-33 (sentence 1 only).

R-V4 [Minor] [README accuracy] vidbyte/agents/README.md:205; vidbyte/agents/agent_swarm/README.md:42 — both READMEs say a message reaches a working agent "after its current tool call". In the code it waits for every tool call of the current model response.
  Evidence: `vidbyte/agents/README.md:205` says "A message reaches a working agent after its current tool call and wakes an idle one". The package README:42 says "delivered after its current tool call finishes". In the code, `vidbyte/agents/runtime.py:611` (`for call_index, call in enumerate(tool_calls):`) runs the whole batch, and only then does `:700` call `_after_tool_iteration`, the swarm's only mid-turn seam (`member.py:62-70`). Spec A-1 says "between tool iterations: after all tool calls of one model response have run".
  Failure: AGENTS.md:11 makes a folder README the document a reader trusts "before you change anything inside the folder". A developer who reads these sentences expects delivery between two parallel calls of one response, which never happens. A reviewer would write: "it's per tool iteration, not per call".
  Smallest fix: In both places, say "after the tool calls of its current model response finish (between tool iterations)".
  Spec IDs: A-1, INV-6.

R-V5 [Minor] [comment format] vidbyte/agents/base.py:80-82 — the PR edited this comment block and left it 99/99/95 columns wide.
  Evidence: `sed -n 78,84p vidbyte/agents/base.py | awk '{print length($0)": "$0}'` printed `99: # Runtimes that execute…`, `99: # fallback, and session-failure wiring…` and `95: # INFINITE_MEMORY is InfiniteMemoryAgent's, and AGENT_SWARM_MEMBER is each AgentSwarm member's.` The last line is new in this diff.
  Failure: `comment-format.md:3-8` comes from the owner's comment "stop writing comments like this, if a comment is a multi line comment, then format it correctly". Its check is that awk prints nothing for the files you touched. The rule spares untouched files; this block is touched.
  Smallest fix: Re-wrap the three lines of that one block at 72 columns. This is comment-only, with no other `base.py` change.
  Spec IDs: n/a (§12.3 row 32, §12.4 comment format).

R-V6 [Minor] [field guide] vidbyte/lib/constants/agent_swarm.py:5 — the constants header asserts that the context fits but omits the token-budget sum the field guide asks for.
  Evidence: The header says "the member's own prompt, the swarm prompt, the tool schemas, and the history trimmed to 90,000 tokens fit with room left for the reply". The sibling header, `vidbyte/lib/constants/infinite.py:5`, says: "the role prompt, the tool descriptions, the map, and the trimmed history take about 105,000 tokens, which leaves room for the developer's own prompt and the reply". These are the measured sizes for one member at chars/4:
  - the seven tool schemas: 3,021 chars, about 755 tokens;
  - the swarm system prompt with a one-letter member prompt: 1,399 chars, about 349 tokens;
  - the agentic-loop prompt: 457 chars, about 114 tokens.
  Failure: `strict-config-dataclasses.md:68-73`, from the owner's comments on PR #1084, says: "Write the arithmetic in the constants header", with the check "The constants header states the token budget sum." The member's own `system_prompt` has no cap, so the reader cannot see how much room it has.
  Smallest fix: State the sum in the header: "the swarm prompt (about 350 tokens), the tool schemas (about 750), the agentic-loop prompt (about 110) and the 90,000-token history come to about 91,000 tokens, leaving about 37,000 of a 128,000-token model for the member's own (uncapped) prompt and the reply".
  Spec IDs: n/a (§9.3 last paragraph; §12.3 row 3).

R-V7 [Minor] [typed in and out / unreported deviation] vidbyte/agents/agent_swarm/runtime.py:141 — `post_message` takes `recipient: object, text: object`, not the spec's `str`, and the S3 report does not list the deviation.
  Evidence: `async def post_message(self, sender: str, recipient: object, text: object) -> str:` differs from spec §8.5, `async def post_message(self, sender: str, recipient: str, text: str) -> str`. The S3 report's deviations 1-7 do not mention it. The message tool passes raw `call.arguments.get(...)` values (`member.py:128`). The sibling instead turns model arguments into a validated record at the tool boundary before calling its core method: `InfiniteRememberTool._draft`, `vidbyte/agents/infinite/memory.py:151-170`.
  Failure: AGENTS.md principle 4 says "Invalid data then fails at the boundary where it enters, not deep inside the logic that uses it". The house style asks for "Typed data in and out". `strict-config-dataclasses.md:39-44` checks for `: object` parameters. A reviewer comparing the code with §8.5 sees an undocumented signature drift on the coordinator's core method.
  Smallest fix: In `AgentSwarmMessageTool.execute`, refuse a non-string `to` or `text` with the catalog's `message_unknown_recipient` or `message_blank_text` text, and type `post_message(sender: str, recipient: str, text: str)` as §8.5 states. Alternatively, record the deviation and its reason in spec §17.
  Spec IDs: n/a (§8.5; FR-4 unchanged).

R-V8 [Minor] [scope-adding] [AGENTS.md principle 5] vidbyte/agents/agent_swarm/runtime.py:273-280 — `_failure_text` is the second private copy of the root-cause rendering in `vidbyte/agents/infinite/launch.py:356-361` (`_error_text`).
  Evidence: `cause = error.__cause__ if error.__cause__ is not None else error` duplicates `launch.py:360`, `cause = str(error.__cause__ or "").strip()`. `grep -rn "__cause__" vidbyte/lib` shows no canonical helper. `vidbyte/agents/codex/failures.py:89-90` is a third partial copy.
  Failure: AGENTS.md:41 says: "whenever a canonical helper in `vidbyte/lib/` would save writing the same logic a second time, build it that way". The owner's PR #1084 comment ("per-class helpers become canonical lib classes", `strict-config-dataclasses.md:61-66`) makes a comment likely. Spec Q-11 already decided "No — a private helper", so this is settled for this PR.
  Smallest fix: None in this PR. As a follow-up, add a `vidbyte/lib/errors/` root-cause helper used by the swarm, InfiniteMemoryAgent and Codex together, in its own PR.
  Spec IDs: Q-11.

VERIFIED CLAIMS:
1. Orchestrator: "0d64078a, 28444b65, f97170ec carry no W-/FR-/AC- IDs" — DOES NOT HOLD.
   - The IDs are in the commit bodies, not the subjects. `git log -1 --format=%B`:
     - 0d64078a: "W-1, W-3 to W-11.";
     - 28444b65: "W-3; FR-3, FR-14; AC-13, AC-17.";
     - f97170ec: "W-7, W-8, W-9, W-10, W-11; FR-2 to FR-7, …; INV-17 to INV-19, INV-24, INV-25.".
   - Every product commit carries IDs and the attribution line. Only the docs/spec pipeline commits carry none.
   - Two commits bundle several work items:
     - f97170ec (W-7 to W-11) is forced by the import graph. The package `__init__` imports `runtime.py` and `swarm.py`, the registry imports the package, and §12.6 requires rows 22, 26, 29 and 31 together.
     - d138f5c3 bundles three independent items (W-4, W-5, W-6). That is a pipeline convention only: AGENTS.md has no commit rule, and main is squash-merged (subjects end "(#1095)"), so it is not a finding.
   - No `__pycache__`, `.pyc`, `.env` or secret is in the diff.
2. S3 "SDK-LINT: PASS, no baseline raised" — HOLDS.
   - My run ends in `SDK-LINT: PASS`, every rule is at or below its baseline, and `git diff origin/main...c0b167d3 -- lint/baseline.json` is empty.
   - The JSON run filtered to the branch's changed files shows zero findings in any new file. The only finding that moved is S051 I001 at `vidbyte/lib/registries/runtimes.py:33`, the block's first line (now the new `from vidbyte.agents.agent_swarm import AgentSwarmMemberRuntime`); that block was already unsorted on main (`from vidbyte.agents.runtimes import (LinearAgentRuntime, SearchTreeRuntimeComponent, PointToPointActorRuntime, BroadcastActorRuntime)`).
   - The IMPROVED verdicts (A002, C011, S001, S010, S025, S061, S063) are below baseline, not regressions.
3. Deviation "asyncio.Semaphore, because TID251 bans asyncio.Lock" — HOLDS.
   - `lint/ruff.toml:8` has `"asyncio.Lock" = { msg = "Use the SDK-owned concurrency boundary." }`.
   - No SDK-owned lock helper exists in `vidbyte/lib` (grep).
   - The same substitute is precedent at `vidbyte/agents/codex/agent.py:83-86`.
4. Deviation "ModelProvider(...) for C012" — HOLDS. In `c012_provider_model_registry_validation.py`, `_PROVIDER_PROOF_METHODS` excludes `validate_provider_model_pair`, and `RecordFieldConverter.to_enum` is not a proof. A provider field needs `ModelProvider(f)` or a registry provider method.
5. Deviation "`callable()` for on_event because of S009" — plausible, not re-run. Precedent: `vidbyte/agents/multi/validation.py:91`.
6. Spec §12.5 "llms.txt and artifacts/file_index.md need no entry" — HOLDS. `grep -i "infinite|agents/coding|agents/jev|agents/codex"` finds nothing in either file.
7. Prompt header "149 assets across 36 families" — HOLDS. The `Prompt` enum has 149 members across 36 family prefixes, and there are 36 family JSON files.
8. A009 room — HOLDS:
   - agents README 31,356 chars (AgentSwarm section 1,606);
   - prompts README 33,021 chars (+1,097);
   - package README 7,270 chars;
   - lint A009 0/0 CLEAN.
9. Contract regenerated and current — HOLDS. `generate-sdk-public-api.py --check` reports current at 698f913b, with the 5 root names in the exports.
10. Exports — HOLD:
    - `vidbyte.lib.enums.__all__`;
    - the toolsets `__all__`;
    - the agents `__all__`, with the 6 names;
    - the root `__all__`, with the 5 names, grouped after the Infinite block like the existing feature grouping, which is not alphabetical.
11. No CLI — HOLDS. `git ls-files vidbyte/cli` lists only `README.md`, `__init__.py`, `__main__.py` and `skills.py` (`prebuilt-agents.md:10-15`).
12. Call chains one level deep (AGENTS.md principle 1) — HOLDS:
    - `arun` calls `_build_member` and `_run_member`, and `_run_member` is a main function per §12.4;
    - `_run_member` calls `_failure_text`, `_early_exit_text`, `_fail` and `_end_check`;
    - `end_turn` calls `_drain` and `_end_check`;
    - none of those calls another helper of its own class.
13. `member.py` holding four classes (principle 3) — holds as a file apart from R-V1. It has 166 lines and one subsystem, the same grouping as the sibling's `memory.py` (a state holder plus its tools) and `launch.py` (a tool plus its pipeline). Each class is forced by one SDK base class.
14. `AgentSwarmSettings.timeout_seconds` overlaps `AgentLoopSettings.timeout_seconds` by name (`runtime-boundaries.md:24-29`). It is not a finding: D-8 settles a swarm-wide hard stop, which a per-member loop timeout cannot express.
15. REPO_MAP entry — HOLDS (`agents-md-map.md`). It has 5 sentences, no file names or commands, and the same closing sentence as the infinite entry (`REPO_MAP.md:89`).
16. Feature pack — 161 passed at HEAD.
17. Touched folders' `## Notes for agents` — none exist in `vidbyte/agents`, `vidbyte/lib`, `vidbyte/lib/registries`, `vidbyte/prompts` or `vidbyte/tools`, so there is nothing to obey. The new package README has its own.

COMMANDS RUN:
- `git diff --stat origin/main...c0b167d3` ends `56 files changed, 7653 insertions(+), 8 deletions(-)`.
- `git diff --stat c0b167d3 HEAD` ends `docs/spec/agent-swarm/pipeline.md | 9 ++++++---`.
- `PYTHONPATH=$(pwd) python lint/run.py` ends `S064 RATCHETED: 4 known finding(s)…` then `SDK-LINT: PASS` (exit 0). Its table includes `A009 0 0 CLEAN`, `A006 34 34 RATCHETED`, `S051 259 259 RATCHETED` and `S025 261 263 IMPROVED`.
- `PYTHONPATH=$(pwd) python lint/run.py --all --format json`, filtered to `git diff --name-only origin/main...c0b167d3`, gives 91 findings. All are in pre-existing modified files (`vidbyte/__init__.py`, `vidbyte/agents/__init__.py`, `base.py`, `agent_runtime.py`, `runtimes.py`, `toolsets/__init__.py`). There are 0 in any `agent_swarm` file.
- An awk check for comment lines over 72 columns across the 11 new `.py` files prints nothing. The same check on `base.py:78-84` gives `99`, `99`, `95` for the edited block.
- The `AgentMiddleware)` grep outside `vidbyte/middleware` returns only `vidbyte/agents/agent_swarm/member.py:73`.
- The isDone script ends `settings accepted isDone search tool`, then `runtime built; tools: ['bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone']`.
- The context-size script prints `tool schema chars 3021 tokens~ 755`, `system prompt chars 1399 tokens~ 349` and `457 114` (the agentic-loop prompt).
- The prompt count prints `149 36`, and `find vidbyte/prompts/prompts -name '*.json' | wc -l` gives `36`.
- `wc -c` on the READMEs gives `31356 vidbyte/agents/README.md`, `33021 vidbyte/prompts/README.md` and `7270 vidbyte/agents/agent_swarm/README.md`.
- `python scripts/generate-sdk-public-api.py --check` prints `contracts/sdk-public-api.json is current at 698f913b… (vidbyte-sdk 0.3.0, 649 exports).`
- Semgrep (scratch venv) prints `Ran 1 rule on 994 files: 0 findings.`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` prints `161 passed in 3.14s`.
- `git log -1 --format=%B` on f97170ec, 0d64078a and the other product commits shows the ID lines quoted in claim 1.
- `git ls-tree -r --name-only origin/main docs/spec` shows main keeps `reports/`, `pipeline.md` and `context/` for 8 earlier specs, so the docs files in this PR follow precedent.
