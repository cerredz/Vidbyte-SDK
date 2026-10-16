# S5 re-review round 1: findings verifier report (public-skill-loader)

Date: 2026-10-15 to 16 · Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader` · HEAD `a8a13f64` (last code-bearing commit `778b094a`; PR head on GitHub `eed6308e`) · merge-base with `origin/main` `0754e01f` · Input: `reports/S5-rereview.md` (conformance only; conventions and engineering n/a)

Output: a section appended to `review.md`, "## S5 re-review round 1 (scoped verification)", with 30 lines added and 0 removed. The S4 content and the R-1 to R-7 rows are untouched (`git diff --stat` shows `30 insertions(+)`, with no `-` lines).

**Verdict: MERGEABLE AFTER FIXES.**
- Confirmed: 0 Blockers, 1 Major (R-C11), 2 Minors (R-C12 trivial; R-C13 follow-up).
- Refuted: 1 (R-C10, as a PR defect). Downgraded: 0.

No commit, fetch, checkout, stash, install, or PR-state change was made. Every probe ran from a scratch folder or against a `git archive` copy, with `PYTHONDONTWRITEBYTECODE=1`. The tree is clean apart from the two files I own.

---

## 1. Merge

There are four findings, and no two of them share a root cause.
- R-C11 (what 0.3.1 carries) and R-C12 (stale line numbers) both come from the merge `fc0175da`, but they fail in different ways: one is a false fact, the other a wrong citation. I kept them separate.
- My blind-spot additions joined the finding with the same root cause:
  - the `TextModelMode` root gap, #1104, and §9.4 "additive only" went into R-C11;
  - three more stale `settings.py` citations went into R-C12;
  - FEATURE.md `:25` went into R-C13.

## 2. R-C10 [Blocker, request fidelity]: refuted as a PR defect; reclassified as external state, already escalated

**The claim:** PR #1099 is not a draft, and nothing records an authorization, so the PR breaks request.md:80 ("The PR stays a draft").

### What holds (my own probes, read-only)
```
$ gh pr view 1099 --json isDraft,state,title,mergeStateStatus,mergeable,headRefOid,baseRefName,reviewDecision
{"baseRefName":"main","headRefOid":"eed6308e…","isDraft":false,"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE","reviewDecision":"","state":"OPEN","title":"[WIP] feat: Public skill loader: …"}
$ gh api repos/cerredz/Vidbyte-SDK/issues/1099/timeline --paginate --jq '.[] | select(.event != "committed") | {event, actor: .actor.login, created_at}'
{"actor":"cerredz","created_at":"2026-10-15T22:28:02Z","event":"ready_for_review"}
```

### Who did it (my own scan, independent of the orchestrator's)
- I wrote `scratchpad/scan_transcripts.py`. It parses every `tool_use` input in the Claude Code transcripts under `~/.claude/projects` changed since 2026-10-15T00:00Z (67 files).
- It matches `gh pr ready`, `markPullRequestReadyForReview`, `convertPullRequestToDraft`, `draft: false` / `draft=false`, `-f draft`, `pr edit … draft`, a PATCH on `pulls/1099`, and `update_pull_request`.
- Result: 62 matches. None is a draft change on #1099 between the S3 PR creation and 2026-10-16T00:35Z. The matches are:
  - Agent or SendMessage prompts from 10-08 to 10-12 that mention "draft", for other PRs;
  - S6 `gh pr edit` title and body calls for other slugs at 01:02Z and 15:14Z on 10-15;
  - from 00:35Z on 10-16, the orchestrator's and the reviewer's own searches, and mine.
- Every `tool_use` from 22:26:00Z to 22:29:00Z (21 calls) is one of:
  - a scratch analysis in session `316f126c`;
  - read-only `sed` and `grep` on `tree_72a4`, plus a `pr_wait2.sh 1103` started at 22:26:14Z, in session `47250a2c` (the main-merge session). I read `pr_wait2.sh`: it only calls `gh pr view`, `gh run list`, `gh run watch`, and `gh run view`. No `.sh` file in that scratchpad mentions draft or ready;
  - the S5 repair agent's log wait (22:26:29Z), its egg-info cleanup (22:28:35Z), and its `git push` (22:28:41Z), all after the event.
- `gh run list --created "2026-10-15T22:20:00Z..2026-10-15T22:35:00Z"` shows only workflow_dispatch runs: on `fix/trace-keep-last-user-tool-results` at 22:21Z and 22:26Z, then on this branch at 22:28:48Z and 22:28:51Z. So no workflow ran in the 22:20Z to 22:28:02Z window.
- The `on:` blocks have no automatic trigger that could change draft state:
  - `ci.yml` and `agents-md-placement.yml` are dispatch-only ("TEMPORARILY DISABLED");
  - `claude.yml` fires only on a `@claude` review or comment, and the timeline has none.
- `gh api repos/cerredz/Vidbyte-SDK/collaborators` returns `cerredz admin`, the only collaborator, which is the user's account. The local `gh` token is also `cerredz`, so the actor's name alone proves nothing. The transcript scan rules out the agents.

### The harm the finding names
- "Anyone with write access can merge a non-draft PR from the GitHub UI" is overstated.
- `gh api …/branches/main/protection` gives:
  - `required_status_checks.strict: true`;
  - contexts `Source / Python 3.11`, `Source / Python 3.12`, `Package`;
  - `enforce_admins: false`.
- The PR is `BEHIND`, and `gh pr view 1099 --json statusCheckRollup` gives `[]`.
- GraphQL gives `viewerCanMergeAsAdmin: true`. Only an admin bypass can merge, and the only admin is the user.
- NG-2 already makes merging "the user's call after review", and §14 Never bars every agent. A 10-08 transcript also records that `gh pr merge --admin` is denied by the harness permission system.

### Classification
- No code, test, doc, or spec change in this PR can restore draft state, and the pipeline did not cause it.
- The constraint belongs to the user, the event came from the user's account, and the question has already been put to the user (`pipeline.md:82`).
- So it is not a defect for the repair loop: **REFUTED as a PR defect**. It stays as an external-state item for the user.
- No agent should change draft state. S6 must describe the PR as open and not a draft.

## 3. R-C11 [Major, consumer contract]: CONFIRMED Major

### 3a. What a 0.3.1 cut from this branch carries beyond PyPI 0.3.0
```
$ git rev-parse v0.3.0  -> a7ed9cdeff1f… (= tag; git ls-remote --tags origin 'v0.3*' shows only v0.3.0)
$ git log --first-parent --format='%h %ad %s' --date=format:'%H:%M' v0.3.0..0754e01f
0754e01f 18:58 feat: opt-in Working Principles system-prompt preset … (#1095)
72a4ade1 18:20 feat(lib,agents): agents take vidbyte_api_key and a list of api_keys, and text calls relay your provider key through the Vidbyte gateway (#1027)
f216fdcf 18:09 feat(harnesses): run, continue and fork Grok, opencode and Muse threads with the caller's API key (#1036)
77fef0e5 #1102 · cb4e702a #1101 · a89422ee #1097 · 5a9c9463 #1100 · 6ef534f8 #1098 · 4816e1d6 #1096 · 6724417a #1094 · 3b879c67 #1093 · 95990c78 #1092 · a496ba73 #1091 · 9aaf662a #1090 · 716a98b9 #1089 · c9d31a7f #1088 · 2b2e6fd9 #1087 · 3656b31e #1086
```

The 18 PRs, classified by commit message and by the root-signature diff in 3b:

| PR | Class | Root-API effect (vs v0.3.0) |
|---|---|---|
| #1027 `72a4ade1` | **breaking, and a default behavior change** | `api_key=` removed (see 3b). It adds `api_keys=` and `vidbyte_api_key=`, and `model_mode=TextModelMode.AUTO` on 5 classes. AUTO sends every text call through the Vidbyte gateway and needs a Vidbyte key (see 3c) |
| #1095 `0754e01f` | additive (opt-in) | root `SystemPromptPreset`; `system_prompt_presets=` on `Agent`, `BaseAgent`, and `JevAgentSettings`; `RunState.system_prompt_presets`; `Prompt.WORKING_PRINCIPLES_SYSTEM_PROMPT` |
| #1036 `f216fdcf` | additive | 28 new `FailureCode` members (grok, opencode, muse); harness threads. No root name added |
| #1093 `3b879c67` | additive (bug fix) | `algorithm=` on `restore`, `Session.resume`, and `Session.fork_from` |
| #1086–#1092, #1094, #1096–#1098, #1100–#1102 | bug fix (behavior) | no root signature change |
| this PR | additive | `ConfigurationError`, `SkillLoader`, and `SkillResolution` become root exports; the `McpStudioServer` default `version` becomes `'0.3.1'` |

How each change was attributed: `git log --first-parent -S` finds `system_prompt_presets` and `WORKING_PRINCIPLES_SYSTEM_PROMPT` only in `0754e01f`, `GROK_KEY_REJECTED` only in `f216fdcf`, and `vidbyte_api_key: str | None = None` only in `72a4ade1`. `-G "algorithm: ContextWindowAlgorithm | str | None = None"` finds `72a4ade1` and `3b879c67`.

**After the merge-base** (on `origin/main` `0105b5b7`, not in this branch), two more PRs exist:
- #1103 `0f69f7b7`, a compaction fix;
- #1104 `0105b5b7`, "child runners carry the agent's api_keys and model_mode", which fixes a gap left by #1027.

A 0.3.1 published from `main` after this PR merges would carry both. A cut from this branch alone would not.

### 3b. Root-export signature diff, v0.3.0 vs HEAD (the release manager's check)
I wrote two scripts:
- `scratchpad/api_dump.py` dumps, for every name in `vidbyte.__all__`: its kind, its constructor or function signature, the signatures of its public methods, its dataclass fields with defaults, and its enum members.
- `scratchpad/param_diff.py` diffs two dumps by parameter name.

I ran the dump against `git archive v0.3.0 | tar -x -C scratchpad/v030tree`, and against the worktree:

```
v0.3.0: 639 names, 3898 lines · HEAD: 643 names, 3914 lines
Agent class:            REMOVED api_key: 'str | None' = None · ADDED api_keys, model_mode = <TextModelMode.AUTO>, system_prompt_presets, vidbyte_api_key
Agent.restore:          REMOVED api_key · ADDED algorithm, api_keys, vidbyte_api_key
AgentRoleSettings:      REMOVED api_key · ADDED api_keys: Sequence[str | None] = (), vidbyte_api_key
AgentRunnerConfig:      REMOVED api_key (was the FIRST positional field) · ADDED api_keys: ProviderKeys = <factory> (now first), model_mode = AUTO
AggregateAgent:         REMOVED api_key · ADDED api_keys, model_mode = AUTO, vidbyte_api_key
BaseAgent class:        REMOVED api_key · ADDED api_keys, model_mode = AUTO, system_prompt_presets, vidbyte_api_key
BaseAgent.restore:      REMOVED api_key · ADDED algorithm, api_keys, vidbyte_api_key
JevAgentSettings:       REMOVED api_key · ADDED api_keys = <factory>, model_mode = AUTO, system_prompt_presets, vidbyte_api_key
JevRunBriefSettings:    REMOVED api_key · ADDED api_keys: Sequence[str | None] = ()
Session.fork_from / Session.resume: REMOVED api_key · ADDED algorithm, api_keys, vidbyte_api_key
FailureCode enum: removed [] ; added 28 (GROK_*, MUSE_*, OPENCODE_*)
Prompt enum: removed [] ; added WORKING_PRINCIPLES_SYSTEM_PROMPT
RunState: ADDED system_prompt_presets
McpStudioServer: CHANGED version '0.3.0' -> '0.3.1'
only-old: []   only-new: ConfigurationError, SkillLoader (+load, documents), SkillResolution (+fields, transient), SystemPromptPreset
```

**Summary:** `api_key=` is removed from 11 signatures on 8 root exports, and nothing else is removed.

The contract file gives the same picture (`git show <ref>:contracts/sdk-public-api.json`):
```
v0.3.0: 0.3.0 639 | merge-base 0754e01f: 0.3.0 640 | HEAD: 0.3.1 643 (source.commit fc0175da…)
HEAD vs v0.3.0 added: ['ConfigurationError', 'SkillLoader', 'SkillResolution', 'SystemPromptPreset'] removed: []
HEAD vs merge-base added: ['ConfigurationError', 'SkillLoader', 'SkillResolution'] removed: []
$ python scripts/generate-sdk-public-api.py --check -> current at fc0175da… (vidbyte-sdk 0.3.1, 643 exports)
```
The contract records names only, so it cannot show a parameter removal. That is why the release looks additive from the contract alone.

`git show v0.3.0:vidbyte/agents/base.py | grep -n "api_key: str | None = None"` gives `101:` (the constructor) and `555:` (`restore`). At HEAD, `base.py:105-107` read `api_keys…`, `vidbyte_api_key…`, and `model_mode: TextModelMode = TextModelMode.AUTO`.

### 3c. Behavior probe: where a default `Agent` text call goes
- The script is `scratchpad/route_probe.py`.
- `httpx.AsyncClient.send` and `httpx.Client.send` are replaced. They record the URL and which auth headers are present, never the values, then stop.
- Setup: `OPENAI_API_KEY=sk-proj-FFF…` (fake), with `VIDBYTE_API_KEY` unset.
- The call: `vidbyte.Agent(name="probe", system_prompt="x", provider="openai", model_name="gpt-4o").run("hello")`.

```
=== v0.3.0 env-only      -> requests attempted: 1   POST https://api.openai.com/v1/responses headers=['authorization']
=== v0.3.0 api_key-kw    -> requests attempted: 1   POST https://api.openai.com/v1/responses headers=['authorization']
=== HEAD env-only        -> AgentExecutionError: Agent 'probe' failed to generate a reply.
                              caused by ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT to call the provider with your own key and no Vidbyte fee.
                              requests attempted: 0
=== HEAD env+vidbyte     -> requests attempted: 1   POST https://vidbyte-backend.onrender.com/api/v1/models/generate headers=['authorization', 'x-vidbyte-provider-key']
=== HEAD api_key-kw      -> TypeError: BaseAgent.__init__() got an unexpected keyword argument 'api_key'   requests attempted: 0
```

**The code behind it** (`vidbyte/lib/dataclasses/model_configs.py:152-169`, `credentials()`): `case TextModelMode.AUTO` always calls `resolve_vidbyte_api_key(...)` (`registries/models.py:204-208`, which raises "Missing Vidbyte API key" when the key is empty), then relays the provider key. The enum header (`vidbyte/lib/enums/text_model.py:7`) says: "AUTO always uses the gateway and needs a Vidbyte key, even when a provider key is held".

**A root-only consumer cannot opt out:**
```
TextModelMode in vidbyte.__all__: False | hasattr(vidbyte, "TextModelMode"): False
TextModelMode in vidbyte.lib.enums.__all__: True
Agent(..., model_mode="direct") -> ConfigurationError AgentRunnerConfig.model_mode must be a TextModelMode value.
```

### 3d. CLI impact (read-only; `C:/Users/422mi/vidbyte-repos/vidbyte-cli`, `origin/main` = `64b04b3`, 2026-10-15 15:48 -0400, #166, no fetch)

**The pin** (`git -C <cli> show origin/main:pyproject.toml`):
- `:42-45` is the comment: "The SDK is alpha and may change APIs between minor versions, so stay within 0.3.x until a newer minor is verified against this CLI."
- `:46` and `:53` read `"vidbyte-sdk[codex]>=0.3.0,<0.4"`.

**What the CLI binds to.** Every SDK symbol is resolved dynamically in five adapters, `src/vidbyte_cli/services/{bug_finder,ensemble,mcp,outputs,suggestions}/sdk.py`:
- `_REQUIRED` tuples from the root:
  - Codex settings and enums: `CodexAgentSettings`, `CodexApprovalMode`, `CodexClientSettings`, `CodexForkSettings`, `CodexHarnessAgentSettings`, `CodexReasoningEffort`, `CodexRunInput`, `CodexSandbox`, `CodexThreadSettings`, `CodexTurnSettings`;
  - `AgentMessage`;
  - outputs: `GitHubIssueOutput`, `LinearIssueOutput`, `OutputDeliveryError`, `OutputDispatcher`, `SlackOutput`;
  - `ContextManager`.
- Deep modules used by the MCP adapter:
  - `vidbyte.lib.runners.decision.DecisionModelRunner`;
  - `vidbyte.lib.dataclasses.model_configs.DecisionModelConfig`;
  - the Jev records `JevDecisionRequest`, `JevBrief`, `JevQuestion`, `JevOption`, and `JevCriterion`;
  - `JevQuestionType`, `JEV_NOUL_TRUE`/`JEV_NOUL_FALSE`, `ProviderRequestError`, and `VidbyteSdkError`;
  - plus `vidbyte.agents.codex.CodexHarnessAgent`.

**Signature check.** `scratchpad/cli_bound_dump.py` ran at v0.3.0 and at HEAD. `diff cli_v030.txt cli_head.txt` differs only on line 1 (`version 0.3.0` → `0.3.1`), so all 30 bindings are identical, and all 17 root names are still root.

**Body check.** An AST comparison of the class bodies, v0.3.0 vs HEAD: `DecisionModelConfig identical: True`, `DecisionModelRunner identical: True`.

**Packages behind those bindings:**
- `git diff --stat v0.3.0 HEAD -- vidbyte/lib/outputs/ vidbyte/agents/codex/ vidbyte/lib/dataclasses/codex.py vidbyte/lib/enums/codex.py vidbyte/lib/runners/decision.py vidbyte/context/manager.py` touches only `vidbyte/agents/codex/fallback.py`, with 8 lines of comment text.
- `class CodexHarnessAgent:` at `vidbyte/agents/codex/agent.py:55` is not a `BaseAgent`, and no file under `vidbyte/agents/codex/` mentions `TextModelRunner`, `TextModelConfig`, or `model_mode`.

**CLI usage of the changed APIs:**
- `git -C <cli> grep -E "TextModelMode|model_mode|api_keys|vidbyte_api_key|BaseAgent|JevAgent(Settings)?|AggregateAgent|AgentRunnerConfig|AgentRoleSettings|JevRunBriefSettings|RunState|fork_from|\.restore\(|TextModelRunner|TextModelConfig" origin/main -- src` finds only the CLI's own `RunState` enum (`types/runs.py:42`).
- Its only SDK `api_key=` calls are `services/mcp/sdk.py:110` (`DecisionModelConfig`) and `services/outputs/sdk.py:75` (`LinearIssueOutput`), and both are unchanged.

**Conclusion:** CLI main is not broken by #1027. R-C11 is a false contract premise and a false decision basis, not a demonstrated CLI break.

### 3e. Spec statements now false or misleading (exact lines)
- `spec.md:436` (§9.2 row 7) and `reports/S1-spec-author.md:195`: "0.3.1 differs from a 0.2.2 cut from `179d8adc` only by #1086 to #1088 (plus this PR), as built from this branch … (#1089 to #1093 so far)." **False.** As built from this branch it carries all 18 PRs in 3a. Those PRs are already in the branch through `fc0175da`; they are not a later addition from `main`.
- `spec.md:436` and `S1-spec-author.md:192`: "So 0.3.1 needs only a floor raise to `>=0.3.1,<0.4`, with no minor crossing." **Literally true for CLI main**, which binds no changed API (3d). It misleads because it omits that the patch carries a breaking change, and the CLI's pin comment relies on patch-level stability.
- `spec.md:745` (Q-8): the same "only by #1086 to #1088" sentence. **False.** The options also omit 0.4.0.
- `spec.md:323` (D-13): its reasoning is still valid as numbering ("the first release that can carry the loader is the next patch"). Its flip column lacks the breaking-change input.
- `pipeline.md:57` (D-13 reason 2): "the user's choice of a patch bump for an additive export is preserved". **False premise** after the merge.
- `spec.md:455` (§9.4): "Public contract change: additive only … nothing is removed or renamed." **True for the names-only contract compared with `main`.** It reads as a release-level claim, and the release removes `api_key=` (3b).
- Still true: "0.3.0 (#1085) changed only version literals, and its root export list equals main's at `179d8adc` (639 names)" (v0.3.0 dump: 639 names). EC-29 is still true.

### 3f. Calibration
**Not Blocker:**
- No code in this PR is wrong, and CLI main is unaffected (3d).
- Publishing is out of scope (NG-2), and the version is the user's Q-8 call with a default applied.
- AGENTS.md:5 ("APIs may change between minor versions") is permissive about minors. It does not forbid a patch from breaking, so the PR does not contradict it.

**Not Minor:** the false sentences sit exactly where the user decides Q-8 and where the paused CLI pipeline resumes. A release reviewer would flag them.

**So: Major, CONFIRMED.** The reviewer's smallest fix is right in kind. I refined it in the review.md row with the corrected 18-PR list, the 8-root-export / 11-signature count, the Vidbyte-key requirement, the DIRECT root gap, and the note that the proposed D-13 flip condition is already met.

### 3g. Corrections to the reviewer's own wording
- "#1089–#1102" includes #1099 (this PR) and #1095. The exact `main` list is #1086–#1094, #1096–#1098, and #1100–#1102 (fixes), plus #1036, #1027, and #1095.
- "`api_key=` becomes `api_keys=`/`vidbyte_api_key=` on `Agent`, `BaseAgent`, and `JevAgentSettings`" is incomplete. The full list is 8 root exports and 11 signatures (3b).
- "the default `TextModelMode.AUTO` routes text calls through the gateway" understates the change. Under AUTO every text call **requires a Vidbyte key**: without one it fails before any request. It also sends the caller's provider key to `vidbyte-backend.onrender.com` in `X-Vidbyte-Provider-Key`, and DIRECT cannot be selected from the root.

## 4. R-C12 [Minor]: confirmed; trivial

`scratchpad/cite_check.py` compares every `path:line` citation in spec.md and in S1's answers section, at `c9d31a7f` and at HEAD. I confirmed each shift by hand:
```
text.py: HEAD "def run(" at 108, get_running_loop at 111, asyncio.run at 115      -> :93-100 becomes :108-115 (reviewer correct)
base.py: c9d31a7f 1053 def … 1060 raise; HEAD 1106 def … 1113 raise              -> :1053-1060 becomes :1106-1113 (reviewer wrote :1106-1112; off by one)
settings.py: c9d31a7f 89 def _normalized_skills … 122 return; HEAD 95 … 128     -> :89-122 becomes :95-128 (reviewer correct); uniform +6 shift
settings.py:96-101 (str/bytes guard + tuple()) -> :102-107   [verifier: spec.md:247 EC-6, :324 D-14]
settings.py:113-121 (append … duplicate raise)  -> :119-127   [verifier: spec.md:555 §11 Conflicts]
settings.py:89-122 at spec.md:314 (D-4)         -> :95-128    [verifier]
errors/base.py: c9d31a7f "284:class ConfigurationError", HEAD "287:" -> :287 (reviewer correct; review.md:30 is S4 history, left verbatim)
```

**Row 7's places still hold.** `git grep -n "0\.3\.1" HEAD -- <the eight files>` gives `pyproject.toml:7`, `vidbyte/__init__.py:40`, `vidbyte/cli/__init__.py:58`, `core.py:79`, `client.py:46`, `README.md:86`, `llms.txt:17`, and `bug_report.yml:19`. These are the same numbers row 7 cites, and the contract has `"version": "0.3.1"` at line 5.

**Optional:** `vidbyte/lib/dataclasses/skills.py` citations (`spec.md:45` `:39`, `:265` `:190-191`, `:526` `:233-254`) moved +2 because of this PR's own S3 edits, not the merge.

## 5. R-C13 [Minor]: confirmed; follow-up (test-pack file), test-plan part trivial

- `FEATURE.md:10`: "takes any iterable except `str` and `bytes` … for text or a non-collection".
- `FEATURE.md:25`: "or other non-text iterable" [verifier].
- `FEATURE.md:15`: "Every version-bearing place reads `0.3.1`".
- `test-plan.md:29`: "compared with 0.3.1".

The probe at HEAD:
```
GetItemOnly -> {'entries_type': 'GetItemOnly'}
raw TypeError propagates: boom
```

The test itself is `release.py:114-115`: `assert read(monkeypatch) == pyproject_version(monkeypatch)`, then the tuple must be `>= FIRST_LOADER_RELEASE` (`:36`, `(0, 3, 1)`). FEATURE.md is a test-pack file, so §14 puts it under Ask first.

## 6. Blind spots the merge brought in that the reviewer did not cover
- [verifier, folded into R-C11] `TextModelMode` is not a root export and a string `model_mode` is rejected, so no root-only consumer can select DIRECT (3c).
- [verifier, folded into R-C11] #1104 on `main` fixes a #1027 gap (child runners). It is in a 0.3.1 published from `main` after merge, and missing from a cut of this branch.
- [verifier, folded into R-C11] §9.4 "additive only" (`spec.md:455`) is true only for the names-only contract.
- [verifier, folded into R-C12] three more stale `settings.py` citations, and the off-by-one in `base.py`.
- [verifier, folded into R-C13] FEATURE.md `:25`.

Checked and clean:
- The loader's credential path. An AST comparison at `c9d31a7f` and HEAD gives `resolve_api_key`, `get_default_endpoint`, and `get_api_key_env_var` `identical: True`, the only three `ProviderModelRegistry` methods `vendor.py` calls. `VIDBYTE_API_KEY_PREFIX` has no diff since v0.3.0, and `github.py:107` and `vendor.py:124` still guard with it.
- The skill entries keep `api_key=` and `token=` (`AnthropicSkill`, `OpenAISkill`, and `GitHubSkill` are absent from the root diff). Only the agent and config parameters were renamed.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader tests/features/jev_skills_preload tests/test_jev_skill_preload.py` gives `493 passed, 1 skipped in 5.38s`. `git status --short` is empty, apart from my two files.

## 7. Exact corrected facts for the spec author (r5) and for Q-8
1. **Releases and tags.** PyPI's latest is 0.3.0, tag `v0.3.0` = `a7ed9cde`. No `v0.3.1` tag exists (`git ls-remote --tags origin 'v0.3*'`).
2. **What 0.3.1 carries.** A 0.3.1 cut from this branch = v0.3.0 + 18 `main` PRs (#1086–#1094, #1096–#1098, #1100–#1102, #1036, #1027, #1095) + this PR. Proof: `git log --first-parent --oneline v0.3.0..0754e01f`.
3. **The breaking change.** #1027 (`72a4ade1`, 18:20) removes `api_key=` from `Agent`, `BaseAgent`, `AggregateAgent`, `AgentRoleSettings`, `AgentRunnerConfig` (its first positional field), `JevAgentSettings`, `JevRunBriefSettings`, `Agent.restore`/`BaseAgent.restore`, `Session.resume`, and `Session.fork_from`. Their replacements are `api_keys=` and `vidbyte_api_key=`. Proof: 3b.
4. **The default behavior change.** Under the default `model_mode=TextModelMode.AUTO`, every `Agent` text call needs a Vidbyte key (`VIDBYTE_API_KEY` or `vidbyte_api_key=`), otherwise `ConfigurationError` before any request. With a key, the call goes to the Vidbyte gateway and relays the provider key in `X-Vidbyte-Provider-Key`. At v0.3.0 the same code called `api.openai.com` directly. Proof: 3c.
5. **No root opt-out.** `TextModelMode` is not in `vidbyte.__all__` or the contract, and `model_mode="direct"` is rejected.
6. **Additive changes.** #1095 adds `SystemPromptPreset` and `system_prompt_presets=`; #1036 adds 28 `FailureCode` members; #1093 adds `algorithm=`. Root names compared with v0.3.0: +4, −0 (639 → 643).
7. **CLI main is unaffected.** CLI `origin/main` `64b04b3` binds no changed API (3d), so for its current code a floor raise to `>=0.3.1,<0.4` is enough. A consumer that builds `Agent`/`BaseAgent`, or the other classes in item 3, must verify 0.3.1 as it would verify a new minor (AGENTS.md:5; CLI `pyproject.toml:42-45`).
8. **Q-8 options, as facts.**
   - 0.3.1 (default; ships #1027 as a patch).
   - 0.4.0 (signals the break; outside CLI main's `<0.4`, so the CLI would cross it deliberately after verifying).
   - 0.2.2 on `release/0.2.x` from `179d8adc` (additive-only, but below CLI main's `>=0.3.0` floor; NG-17).

   The reviewer's proposed D-13 flip condition ("main gains a breaking change before release") is already true at HEAD, so record it as a Q-8 input. #1103 and #1104 are on `main` after the merge-base and would be in any 0.3.1 published from `main` after merge.

## 8. Scratch artifacts (not committed)
All are under `C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\1d2c8a26-e7b8-4bc3-b449-2665a570335d\scratchpad\`:
- scripts: `scan_transcripts.py`, `api_dump.py`, `param_diff.py`, `route_probe.py`, `cli_bound_dump.py`, `cite_check.py`;
- the extracted `v030tree/`;
- `apidiff/` (`v030.txt`, `head.txt`, `api.diff`, `cli_v030.txt`, `cli_head.txt`).
