---
spec: jev-cli-root-exports
title: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs
status: tests-written    # draft | approved | tests-written | implemented | reviewed | verified | pr-open | abandoned
revision: 3              # r3.1: INV-7 wording only, per the S2 note
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports
branch: feat/jev-cli-root-exports
base_commit: b7350ed6423642c9c178361eef87f3d9cda5589b
created: 2026-10-19
updated: 2026-10-19
pr:                      # filled at S3 (draft) and finalized at S6
---

# Spec: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs

> **TL;DR** — Four classes that already exist, `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption`, become top-level `vidbyte` exports, and `contracts/sdk-public-api.json` is regenerated from 664 to 668 names. vidbyte-cli may import only root names that this contract lists, so after this change it can set JevAgent's loop limits, allow write and execute tools, choose the text-model mode, and name compute options by enum. The decision that matters most: the root binds the existing class objects eagerly from modules that `import vidbyte` already loads. There are no copies, no lazy hooks, and no change to any definition, default, sub-package export list, or version literal. The work lands in three commits. The source comes first, because the contract generator refuses to stamp a commit whose inputs are uncommitted. The generated contract comes second. The release-note entry comes last, once the draft PR exists, because it must cite the PR's real number.

## §0 User prompts

_The verbatim record of what the user asked lives in `docs/spec/jev-cli-root-exports/request.md` (every prompt in order, the handoff block if one exists, and the structured conversation notes). This block reproduces only the prompt that invoked the pipeline, plus the two answers that define this PR's slice._

### 0.1 Invoking request (verbatim)

Prompt 2, which invoked the pipeline:

```
/spec-pipeline I like this and I agree with the setup, can you start building it into the vidbyte-cli/.
```

The answers in Prompt 3 that create this SDK slice (request.md §A, mapped to the questions in §C.1), verbatim:

```
2) you can create a new seperate pr in the vidbyte-sdk/ that you can just auto merge that applies this change and updates the version. 3) I dont want writes to be denied.
```

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

The program "JevAgent in vidbyte-cli" (request.md §C.2 D-P1) needs the CLI to turn flags into the two frozen settings objects `JevAgent` accepts. The CLI may import only top-level `vidbyte` names that its vendored copy of `contracts/sdk-public-api.json` lists (CLI lint C028, request.md §C "Why"). On `base_commit`, none of the four names below is a root name. `hasattr(vidbyte, name)` is False for each one, and none is in `vidbyte.__all__` (verified in this session with `PYTHONPATH=<worktree> py -3.11`). The settings objects will not accept a substitute:

- `JevAgentSettings.loop` must be an `AgentLoopSettings` instance (`vidbyte/agents/jev/settings.py:181-182`). Without the class, the agreed `--max-iterations`, `--max-tokens`, `--max-tool-calls` and `--loop-timeout` flags (request.md §C.0 flag map, row `.loop`) have nothing to build.
- `JevAgentSettings.permission_policy` must be a `PermissionPolicy` instance (`settings.py:179-180`). Its default allows only `SAFE` and `READ` (`vidbyte/lib/dataclasses/security.py:36-38`). Without the class, every write and execute tool call is denied, and the user said "I dont want writes to be denied" (Prompt 3, answer 3; D-P3).
- `JevAgentSettings.model_mode` must be a `TextModelMode` member (`settings.py:169-170`). Reproduced: `model_mode="direct"` raises `ConfigurationError: JevAgentSettings.model_mode must be a TextModelMode value.` `TextModelMode.DIRECT` is the only mode that calls the provider with the caller's own key and needs no Vidbyte key (`vidbyte/lib/enums/text_model.py`, KNOWN EDGE CASES). The CLI's own-key-only rule (D-P5) points at that mode.
- `JevComputeSettings.dynamic_compute` accepts strings, so building the settings does not strictly need `JevDynamicComputeOption`. It is in scope because request.md §C names it. The harm the request states is that without it the CLI "must pass compute options as bare strings" (request.md §C "Why"). The same string-acceptance argument leaves `ModelProvider` out of this PR (NG-2, A-2, Q-3).

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | vidbyte-cli can build every JevAgent setting in the agreed flag map from top-level `vidbyte` names alone: loop limits, write and execute permissions, text-model mode, and compute options by enum | The §4 snippet runs with only `from vidbyte import …`, and the regenerated contract lists all four names | request.md §C "This run's scope" and "Why"; §C.0 flag map rows `.permission_policy` and `.loop`; Prompt 3 answers 2 and 3 |
| G-2 | The record of the unreleased 0.4.0 release still describes exactly what 0.4.0 ships | `docs/design/release-0-4-0.md` names the four exports, states 668 exports, and no longer says `TextModelMode` is "not the root" | request.md §C "Version (D-P2)" ("add them there") |
| G-3 | No existing SDK user sees any change | Every existing import path, default, and validation behaves exactly as on `base_commit`, and `import vidbyte` loads the same modules | request.md §C "Not in this run: … any behavior change to the four classes" |

## §2 Objective

When this PR merges, `vidbyte/__init__.py` binds `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption` from the modules they already come from, and lists each name exactly once in `vidbyte.__all__`. The root header gains one bullet that names the four. `contracts/sdk-public-api.json` is regenerated by `scripts/generate-sdk-public-api.py` to 668 exports at version `0.4.0`, and `docs/design/release-0-4-0.md` records the four exports in the release they ship in. Nothing else changes: no class definition, no default, no sub-package `__all__`, no version literal, and no other root name. This is PR **R1** of the 8-PR program (request.md §C.2 D-P1). Later slices, all out of scope here: R3 (a USD spend cap on `AgentLoopSettings`), R2 (reasoning effort), and C1 to C5 (vidbyte-cli, including the refresh of the CLI's vendored contract and its pin move to `>=0.4.0,<0.5`).

## §3 Non-goals

- **NG-1** — Root-export the 11 native browser names that #1183 added to `vidbyte.harnesses.native.__all__` (`BrowserThreadResult`, `BrowserToolCall`, `{run,continue,fork}_{grok,opencode,muse}_with_browser`). Their absence makes 3 tests in `tests/features/root_native_thread_exports/` fail on pristine `base_commit`. — *Why not:* request.md §C fixes exactly four names. Those 3 failures are inherited (§11 baseline) and belong to a separate PR (Q-1).
- **NG-2** — Root-export any other type that is not a root name today (`ModelProvider`, `ProviderKeys`, `ToolErrorPolicy`, `OutputContract`, `DecisionModelConfig`, `JevUsageReport`, `PermissionDecision`, `PermissionCeiling`). — *Why not:* this is not in the request. `provider` and `api_keys` accept strings. The others are not in the agreed flag map, or are never exposed (`.decision`). A response record such as `JevUsageReport` can be read through its attributes without importing its type (A-2). `ModelProvider` is the one closed vocabulary in the agreed flag map that stays non-root (`--provider`, `--brief-provider`). A later SDK PR could export it (Q-3, default not built).
- **NG-3** — Clear the four pre-existing S015 root findings: `ContinualTraceAgentDescriptor`, `FunctionTool`, `HandoffAgentDescriptor` and `ToolMixin` are imported by the root but missing from `__all__`, and they count in S015's baseline of 13. — *Why not:* clearing them adds four public exports that nobody asked for (hard rule: scope is the conversation).
- **NG-4** — Change the version, tag, or publish. — *Why not:* D-P2 (request.md §C.2). 0.4.0 is unpublished, and these exports ship in it. Tagging and publishing are a separate release step. The release note's own precondition, the Meta key fix #1184, is now met: it merged as `513aa614` on 2026-10-19. The note's "Do not tag until … #1184 …" sentence is therefore stale, and it is left for the release PR (§12.5). The user's "updates the version" is met by these exports shipping in the unreleased 0.4.0 (D-7).
- **NG-5** — Change any behavior or default of the four classes, or move the legacy enums `PermissionDecision` (`vidbyte/lib/dataclasses/security.py:25`) and `ToolPermission` (`vidbyte/lib/dataclasses/tools.py:47`) to `vidbyte/lib/enums/`. — *Why not:* request.md §C "Not in this run". AGENTS.md Placement Rules / Existing code: "Moving it to `vidbyte/lib/` is a change of its own and belongs in its own pull request."
- **NG-6** — Split `vidbyte/__init__.py`, which is 1,467 lines, against General Coding Style 3 ("Keep files well below 1,000 lines"). — *Why not:* AGENTS.md General Coding Style preamble: "Do not rewrite untouched code just to make it conform; that belongs in its own pull request." The precedent PRs #1179 and #1099 grew the file without splitting it. No lint rule enforces the limit (code-map §2.4).
- **NG-7** — Rewrite the examples in README.md, llms.txt or `skills/**` to import from the root, or fix the unrelated `PermissionPolicy(allowed=..., denied=...)` mistake at `skills/usage/create_agent_with_tools.md:164`. `PermissionPolicy` has no `denied` field. — *Why not:* the sub-package paths those examples use keep working (INV-13), no rule ties those files to `__all__` (code-map §2.7), and the `denied=` mistake is a separate documentation bug.
- **NG-8** — Edit the headers of the defining modules, or any file under `vidbyte/tools/**` or `vidbyte/lib/configs/**`. — *Why not:* nothing in those headers becomes false (D-9). An edit under `vidbyte/tools/**` turns `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` red (`tests/features/harness_threads/test_harness_threads_surface.py:227-235`).
- **NG-9** — Make lazy root exports for the four names. — *Why not:* `import vidbyte` already loads all four defining modules (verified), so laziness saves nothing and adds a mapping and a `__getattr__` branch (D-1).
- **NG-10** — Convert the root's legacy "Context Protocol Header" to the A001 field format. — *Why not:* this is untouched code (the AGENTS.md style preamble), and the file is already counted in A001's baseline of 642.
- **NG-11** — Any vidbyte-cli change: refreshing `lint/contracts/sdk-public-api.json`, moving the pin to `>=0.4.0,<0.5`, or adding flags. — *Why not:* that is CLI PR C4 (request.md §C.2 D-P1, D-P2).
- **NG-12** — The weighted words that belong to other PRs of the program, each traced: "one of the 7 provider keys", "use a key outside of this", "a helper class that runs before the core logic runs", and "raise an error with a message explaining that they need 1 of these 7 api providers" belong to C1. "make "max_spend" a universal command" and "every agent to be tracking usage" belong to R3 and C3. "if there are clarifying questions the JevAgent will stop …" belongs to C4. "JevAgent should have a reasoning effort" belongs to R2 and C5. "just run the jev agent with no parameters … whatever these defaults are they will run" belongs to C4, and this PR keeps every SDK default unchanged so that C4 inherits them (INV-7). "Can you give me a checklist of all the basic/required commands" was answered in the conversation (request.md §C.0). "all the setting/things that are possible to be tweaked/customized through the jevAgent" is served here by G-1 and AC-1 for the four field types it needs, and by the CLI PRs for the commands themselves. "updates the version" is handled by D-7 and NG-4. "I dont want writes to be denied" is served here by FR-2 and AC-2.
- **NG-13** — Tests that compare against `base_commit` or the merge base, or that pin an export count, a module hash, or a version literal. — *Why not:* such tests go red on `main` after the merge, or at the next export (R-1). These facts are proven once by the implementer instead (§6.1.b, the second table in §6.2).

## §4 Developer usage

This is how vidbyte-cli's `services/jev/sdk.py` adapter, or any SDK user, builds JevAgent settings once this PR merges. It uses root names only, as CLI lint C028 requires. No provider key or Vidbyte key is needed, because nothing runs.

```python
import vidbyte
from vidbyte import AgentLoopSettings, JevAgent, JevAgentSettings, JevComputeSettings
from vidbyte import JevDynamicComputeOption, JevRuntimeSettings, PermissionPolicy, TextModelMode

settings = JevAgentSettings(
    name="jev",
    system_prompt="You are a careful coding agent.",
    provider="openai",
    model_name="gpt-5-mini",
    permission_policy=PermissionPolicy.allow_all(),
    loop=AgentLoopSettings(max_iterations=40, max_tool_calls=200, timeout_seconds=900),
    model_mode=TextModelMode.DIRECT,
)
compute = JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.CLONE, JevDynamicComputeOption.FRESH_AGENT))
agent = JevAgent(settings, JevRuntimeSettings(compute=compute))

print(sorted(level.value for level in settings.permission_policy.allowed))
print(settings.loop.max_iterations, settings.model_mode.value)
print([option.value for option in compute.dynamic_compute])
print({"AgentLoopSettings", "PermissionPolicy", "TextModelMode", "JevDynamicComputeOption"} <= set(vidbyte.__all__))
```

Exact stdout:

```
['execute', 'read', 'safe', 'write']
40 direct
['fresh_agent', 'clone']
True
```

The third line shows existing behavior that this PR does not change: `JevComputeSettings` puts the options in tie-break order (`vidbyte/lib/enums/jev.py:278`), whatever order they were given in. The same script, with the four names imported from their sub-packages, prints these lines on `base_commit`, except that the last line is `False` (verified with `OPENAI_API_KEY` and `VIDBYTE_API_KEY` unset). The CLI no longer needs a deep import, which C028 forbids, or bare strings to reach these four settings.

## §5 Flow diagram

```mermaid
flowchart TD
  A["caller: from vidbyte import PermissionPolicy (CLI services/jev/sdk.py)"] -->|root attribute lookup| B["vidbyte/__init__.py root import binding"]
  B -->|the same class object| C["defining module: agents.settings.loop / lib.dataclasses.security / lib.enums.text_model / lib.enums.jev"]
  B -->|literal __all__, read with ast| D["scripts/generate-sdk-public-api.py"]
  D -->|668 sorted names, version 0.4.0, source.commit| E["contracts/sdk-public-api.json"]
  E -->|vendored byte for byte in CLI PR C4| F["vidbyte-cli C028 admits the name"]
  B -->|lint/run.py| G["S015: bound and listed once; S051: import order"]
  E -->|lint/run.py| H["C016: committed contract equals the derived contract"]
```

A caller's `from vidbyte import X` resolves to a binding the root module makes at import time. That binding is the class object from the defining module, not a wrapper, so `isinstance` checks and JevAgentSettings' validators see one class. The generator never imports `vidbyte`: it reads the literal `__all__` and `pyproject.toml` with `ast` and `tomllib`. It writes the sorted names, the version and the HEAD commit, and it refuses to write while either input file is uncommitted. Validation happens in the lint gate. S015 rejects an unbound or unlisted root name, S051 rejects import-order drift, and C016 rejects a committed contract that differs from what the source derives. The only state change is the committed JSON file. The CLI-side step F happens in a different repository, in a later PR.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

### 6.1 Invariants

This section holds two kinds of statement:

- **6.1.a — Permanent properties of the root surface.** They hold at this PR's head and must keep holding after later PRs merge, so the test author tests them.
- **6.1.b — One-time diff facts about this PR, measured against the merge base `$MB`.** The implementer proves each one once, with the command output named in §6.2's second table. No test asserts them.

`MB=$(git merge-base origin/main HEAD)`. It equals `b7350ed6` (`base_commit`) until `main` is merged into the branch. After such a merge it moves to the merged `main` commit, so every diff against `$MB` still shows only this PR's own changes. The variable is named `MB`, not `B`, because "commit B" already names the contract commit (§12.6). `origin/main` has already moved to `0cce5781` (#1184, #1188), and that delta changes none of these facts (§12.6 P4).

The reason no test may assert a 6.1.b fact: a test that compares against `base_commit` or the merge base, or that pins an export count, a module hash, or a version literal, goes red on `main` after the merge, or at the next export or version bump. The field guide `local-ci-verification.md` records this happening twice: "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself", and "Two `harness_threads` surface tests fail locally on any branch that touches … root exports".

#### 6.1.a Permanent properties (tests assert these)

- **INV-1** — Each of `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption` is an attribute of the root `vidbyte` module bound at import time, and appears **exactly once** in `vidbyte.__all__`.
- **INV-2** — `vidbyte.<name>` is the very object (`is`, not `==`) found at every path in that name's row below.

  | Name | Defining module (attribute) | Existing re-export paths (attribute, and listed in that module's `__all__`) |
  |---|---|---|
  | `AgentLoopSettings` | `vidbyte.agents.settings.loop` | `vidbyte.agents.settings`, `vidbyte.agents` |
  | `PermissionPolicy` | `vidbyte.lib.dataclasses.security` | `vidbyte.lib.dataclasses`, `vidbyte.tools.security`, `vidbyte.tools.security.permissions` |
  | `TextModelMode` | `vidbyte.lib.enums.text_model` | `vidbyte.lib.enums`, `vidbyte.lib.config` |
  | `JevDynamicComputeOption` | `vidbyte.lib.enums.jev` | `vidbyte.lib.enums` |

  Every cell was verified on `base_commit`. No other module lists any of the four in its `__all__` today. For example, `vidbyte.lib.config` does not export `PermissionPolicy`, `vidbyte.agents.settings` exports none of the other three, and `vidbyte.agents.jev`, `vidbyte.lib` and `vidbyte.tools` export none of the four. This is context, not a test. Many modules import these classes for their own use (`vidbyte.agents.jev.settings` holds all four as attributes), so no test sweeps module attributes or asserts absence anywhere. Two defining modules have no `__all__` entry for their name: `vidbyte.agents.settings.loop` and `vidbyte.lib.dataclasses.security`. Check those two by attribute only.
- **INV-4** — `contracts/sdk-public-api.json` is the generator's canonical output for the current source, so `scripts/generate-sdk-public-api.py --check` exits 0 and C016 is CLEAN. Its `exports` include the four names. This is a superset check, the form `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:166-169` and `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py:139-142` use. Its `version` equals `pyproject.toml`'s `[project].version` and `vidbyte.__version__`. That is an equality among the three, never a literal.
- **INV-5** — A fresh `import vidbyte` starts no process, and leaves `vidbyte.harnesses.native` unloaded until a thread function is named (harness thread spec INV-23). The "no new module" half of the import-cost claim is the one-time fact INV-16.
- **INV-7** — Defaults and validation keep these values, which are the values on `base_commit`:
  - `PermissionPolicy().allowed == frozenset({ToolPermission.SAFE, ToolPermission.READ})`.
  - `PermissionPolicy.allow_all().allowed == frozenset(ToolPermission)`.
  - The `model_mode` default of `JevAgentSettings` is `TextModelMode.AUTO`.
  - `JevComputeSettings().dynamic_compute == (FRESH_AGENT, FORK_AGENT, SUBAGENT)`.
  - `AgentLoopSettings()` has no iteration, token, or tool-call limit, with `max_queued_prompts == 25` and `max_contract_rejections == 3`.
  - A string `model_mode` is still rejected with `ConfigurationError`.
  - The existing members of `TextModelMode` (`auto`, `vidbyte_managed`, `direct`) and of `JevDynamicComputeOption` (`fresh_agent`, `fork_agent`, `subagent`, `clone`, `swarm`) keep their values and relative order; a later PR may add members. Adding a compute option is a normal change (AGENTS.md "New JEV code": "A new dynamic-compute option adds its enum member …"), so no test pins the full member list (r3.1, S2 note).

  At this PR, INV-7 follows from INV-2 (the same objects) and INV-6 (byte-identical definitions). Existing tests already pin parts of it (`tests/test_jev_compute_clone.py:70`, `tests/features/sdk_loop_settings/test_contract.py`, `tests/test_restore_permission_policy.py:103`).
- **INV-9** — `from vidbyte import *` binds every name in `vidbyte.__all__`, including the four. The names it binds are the root's own objects.
- **INV-10** — The root header has exactly one Architecture bullet starting `- Agent setting exports:`, and it names all four. The release-note half of the old INV-10 is now INV-17.

**Must not regress:**
- **INV-11** — A misspelled root name, such as `vidbyte.PermissionPolicies` or `from vidbyte import TextModelModes`, still raises `AttributeError` or `ImportError` and does not load `vidbyte.harnesses.native`. (The sentence that said the lazy block is unchanged is a one-time diff fact, and moved to INV-6 in r3.)
- **INV-12** — The root header's `- Error exports:` bullet still contains `ConfigurationError` (`tests/features/public_skill_loader/test_public_skill_loader_docs.py:91`).
- **INV-13** — Every existing import path in the INV-2 table keeps working and returns the root's object. The source lines are `vidbyte/agents/__init__.py:258-264` and `:323`, `vidbyte/agents/settings/__init__.py`, `vidbyte/lib/enums/__init__.py` (`:122`, `:204`, `:284`, `:347`), `vidbyte/tools/security/__init__.py`, `vidbyte/tools/security/permissions.py`, `vidbyte/lib/dataclasses/__init__.py` (`:201`, `:413`), and `vidbyte/lib/config/__init__.py` (`:16`, `:34`).

#### 6.1.b One-time diff facts (the implementer proves these once with command output; no test asserts them)

- **INV-3** — `set(vidbyte.__all__)` at the head equals the `__all__` at the merge base `$MB` (`b7350ed6` at S1) plus exactly the four names. No name is removed and no other name is added. Every entry that already exists keeps its relative order.
- **INV-6** — The definitions and every sub-package export list are byte-identical to the merge base `$MB` (`b7350ed6` at S1). So are the root's `__getattr__`/`__dir__` block (`vidbyte/__init__.py:1449-1467` at S1) and `_LAZY_NATIVE_THREAD_EXPORTS` (`:1435-1445` at S1), which moved here from INV-11 in r3. Outside `docs/spec/jev-cli-root-exports/` and the test author's files under `tests/`, only the three files in §12.3 differ from `$MB`.
- **INV-8** — This PR changes no version literal. The nine places, all reading `0.4.0` at the merge base `$MB` (`b7350ed6` at S1, and unchanged on `origin/main` `0cce5781`), are: `pyproject.toml:7`, `vidbyte/__init__.py` `__version__`, `vidbyte/cli/__init__.py:58`, `vidbyte/mcp_server/server/core.py:79`, `vidbyte/tools/mcp/client.py:46`, `README.md:86`, `llms.txt:17`, `.github/ISSUE_TEMPLATE/bug_report.yml:19`, and the contract's `version`. They are kept equal to each other permanently by `tests/features/public_skill_loader/test_public_skill_loader_release.py:99-115` and by INV-4.
- **INV-14** — No lint rule gains a finding. C016 stays at 0, S015 at 13, A001 at 642, and S051 at or below 259, with no I001 finding on `vidbyte/__init__.py`.
- **INV-15** — The contract's provenance follows the repo's own rule. At the head, `scripts/generate-sdk-public-api.py --check` exits 0 and reports `current at <source.commit> (vidbyte-sdk 0.4.0, 668 exports)`. `source.commit` is a commit on the branch, and `git show <source.commit>:vidbyte/__init__.py` lists the four names. `source.commit` is commit A (§12.6), unless a later commit changed the derived data and the generator re-stamped it. The generator keeps `source.commit` whenever the derived data is unchanged (`scripts/generate-sdk-public-api.py:65-67`, and its KNOWN EDGE CASES). So a later commit that changes only other text in an input, or no input at all, leaves `source.commit` alone, and that is correct. Commit C is such a commit: the generator's only inputs are `pyproject.toml` and `vidbyte/__init__.py` (`lint/core/public_api_contract.py:431`). The count is 668 unless a merged `main` adds root exports (EC-7).
- **INV-16** — A fresh `import vidbyte` loads exactly the same set of modules at the head as at the merge base `$MB` (`b7350ed6` at S1). For the one-off probe only: on `b7350ed6`, and also on `origin/main` `0cce5781` (re-measured at r3), it loads 948 modules named `vidbyte` or `vidbyte.*`, and their sorted names, joined with `\n`, hash to a SHA-256 beginning `ff657e9052f220c0`. **Never pin these numbers in a test.**
- **INV-17** — `docs/design/release-0-4-0.md` carries the three edits of §12.3 row 2. It no longer says `TextModelMode` is exported "not the root". It states 668 exports and 29 added since `v0.3.0`, four of them from this PR, cited by its real number. No placeholder such as `#<n>` is ever committed.

### 6.2 Acceptance criteria

**Tested.** These are permanent; the test author writes the tests.

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch at the PR head, on `PYTHONPATH`, with no provider or Vidbyte key in the environment | the §4 snippet runs | it prints exactly the four lines shown in §4 and raises nothing | P0 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py::test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key` (fresh interpreter, every `*API_KEY*` variable removed, exact stdout) |
| AC-2 | the root package is imported | each of the four names is read as `vidbyte.<name>`, and through `from vidbyte import <name>` | each resolves; `vidbyte.__all__.count(name) == 1`; each is the object at every path in its INV-2 row; `vidbyte.PermissionPolicy.allow_all().allowed` holds all four `ToolPermission` levels | P0 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py::` `test_each_setting_name_is_listed_exactly_once_in_the_root_all`, `test_root_name_is_the_same_object_at_every_path_in_its_inv2_row` (12 cases, one per INV-2 positive pairing), `test_from_vidbyte_import_binds_the_defining_objects`, `test_root_permission_policy_keeps_its_default_and_allow_all_permits_every_level` |
| AC-3 | a fresh interpreter with `PYTHONPATH` set to the checkout | `from vidbyte import *` runs | the namespace holds the four names, each identical to the root's attribute | P1 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_star_import_binds_every_root_name_and_the_four_as_the_root_objects` |
| AC-4 | the PR head, after commit B | `contracts/sdk-public-api.json` and `pyproject.toml` are read | `exports` includes the four names (a superset check, never a count); `version` equals `pyproject.toml`'s version and `vidbyte.__version__` (equality, never a literal). This is red between commit A and commit B, by design | P0 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py::test_public_api_contract_lists_the_four_names_at_the_package_version` |
| AC-7 | a fresh interpreter | `import vidbyte` runs | `vidbyte.harnesses.native` is not in `sys.modules`, and no subprocess starts | P0 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process` (also asserts INV-1's eager binding: the four are in `vars(vidbyte)` right after import; process starts are seen through a `sys.addaudithook` hook) |
| AC-8 | the root names | `PermissionPolicy()` is built, and `JevAgentSettings(..., model_mode="direct")` is built, through the root names | the first allows exactly `SAFE` and `READ`; the second raises `ConfigurationError`. The rest of INV-7 is implied by INV-2 and INV-6, so at most one smoke test is needed here | P2 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py::` `test_root_permission_policy_keeps_its_default_and_allow_all_permits_every_level`, `test_jev_settings_take_the_root_text_model_mode_and_still_reject_a_string` |
| AC-10 | the PR head | `vidbyte.PermissionPolicies` is read, and `from vidbyte import TextModelModes` runs | `AttributeError` and `ImportError` respectively. The existing `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_a_misspelled_root_name_is_still_an_attribute_or_import_error` already covers this, because it exercises the same unchanged `__getattr__`. No new test is required | P2 | existing `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_a_misspelled_root_name_is_still_an_attribute_or_import_error`; the two names given here are also probed, with the native package still unloaded afterwards, in `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py::test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process` |
| AC-11 | the PR head | the root header in `vidbyte/__init__.py` is read | it has exactly one `- Agent setting exports:` bullet, and that bullet names all four; `- Error exports:` still contains `ConfigurationError` | P1 | `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py::test_root_header_has_one_agent_setting_exports_bullet_naming_the_four`; the `- Error exports:` half is the existing `tests/features/public_skill_loader/test_public_skill_loader_docs.py::test_docs_describe_the_public_door[root header error exports]` |

**Proven once by the implementer.** These are one-time diff facts. The implementer pastes the command and its output into the Proof column, or into the implementer report. Never write a test for them. Each command first sets `MB=$(git merge-base origin/main HEAD)` (§6.1).

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-5 | commit A, before commit B | `py -3.11 scripts/generate-sdk-public-api.py --check` runs | it prints `contracts/sdk-public-api.json is stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` and **no** `exports removed` line (INV-3; negative: none of the 11 native browser names, nor any other name, joins). `git diff $MB -- vidbyte/__init__.py` adds exactly the 9 lines of §12.3 row 1 and removes none, so the `__getattr__`/`__dir__` block and `_LAZY_NATIVE_THREAD_EXPORTS` are unchanged (INV-6) | P0 | |
| AC-6 | the PR head | `git diff --name-only $MB HEAD` and `git diff --name-only $MB HEAD -- vidbyte/tools vidbyte/lib/configs vidbyte/agents/settings vidbyte/lib/dataclasses vidbyte/lib/enums vidbyte/lib/config vidbyte/agents/__init__.py vidbyte/agents/jev` run | the first lists only the three §12.3 files, the test author's files, and `docs/spec/jev-cli-root-exports/**`; the second prints nothing (INV-6) | P0 | |
| AC-9 | the PR head | `git diff $MB HEAD -- pyproject.toml vidbyte/cli/__init__.py vidbyte/mcp_server/server/core.py vidbyte/tools/mcp/client.py README.md llms.txt .github/ISSUE_TEMPLATE/bug_report.yml` runs, and the `vidbyte/__init__.py` diff is read | the first prints nothing; the root diff has no `__version__` line (INV-8) | P0 | |
| AC-12 | the PR head | `PYTHONPATH=$(pwd) py -3.11 lint/run.py` runs, and `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` runs | the lint's last line is `SDK-LINT: PASS`, with C016 0, S015 13, A001 642, S051 ≤ 259; ruff reports no `vidbyte\__init__.py` line (INV-14) | P0 | |
| AC-13 | the PR head | `py -3.11 scripts/generate-sdk-public-api.py --check` runs, then `git merge-base --is-ancestor <source.commit> HEAD`, then `git show <source.commit>:vidbyte/__init__.py` | the check exits 0 and prints `… is current at <source.commit> (vidbyte-sdk 0.4.0, 668 exports).` (`<source.commit>` is commit A unless the derived data changed later); the ancestor check exits 0; the shown `__all__` lists the four names (INV-15). No diff between `source.commit` and HEAD is required to be empty | P0 | |
| AC-14 | a scratch copy of `$MB` (`git archive $MB vidbyte pyproject.toml` extracted into the session scratchpad) and the head | a fresh `py -3.11` interpreter prints the sorted `vidbyte*` keys of `sys.modules` after `import vidbyte`, once with `PYTHONPATH` set to each tree | the two lists are identical. At S1 and at r3, both `b7350ed6` and `0cce5781` give 948 names with SHA-256 prefix `ff657e9052f220c0` (INV-16, NFR-1) | P0 | |
| AC-15 | the PR head after commit C | `git diff $MB HEAD -- docs/design/release-0-4-0.md` runs | it shows exactly the three edits of §12.3 row 2, with this PR's real number and no `#<n>` (INV-17) | P1 | |

### 6.3 Edge cases and failure modes

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| EC-1 | `"PermissionPolicy"` is added to `__all__` but the import is forgotten | `from vidbyte import *` raises `AttributeError: module 'vidbyte' has no attribute 'PermissionPolicy'` through `__getattr__`; S015 reports "`__all__` entry is not bound/imported/lazily declared" | every star-import user breaks; the lint gate is red | INV-1, INV-9, S015 |
| EC-2 | the import is added but the `__all__` entry is forgotten | `from vidbyte import PermissionPolicy` works, but the generator omits the name, so the CLI's C028 rejects the import; S015 reports "root public import is missing from `__all__`" | the CLI cannot use the name, although the SDK seems to export it | INV-1, INV-4, S015 |
| EC-3 | a name is listed twice, for example both beside its sibling and in a cluster at the end | S015 reports "duplicate `__all__` entry"; the contract silently collapses duplicates (`lint/core/public_api_contract.py` KNOWN EDGE CASES) | the lint gate is red | INV-1, S015 |
| EC-4 | the generator runs before the root change is committed | it prints `SDK public-API contract not written: these input files have uncommitted changes:` and exits 1; nothing is written | the implementer must commit first | D-8 |
| EC-5 | the four names are typed into the JSON by hand, and `source.commit` stays `ebd18517…` | C016 compares only the data and the canonical bytes, so it can pass, while `source.commit` names a commit whose root file has 664 names | the provenance is false; a CLI owner who audits `source.commit` finds no such export there | INV-15, D-8 |
| EC-6 | commit A is amended or rebased after the contract commit | `source.commit` names a commit that is no longer on the branch; the data stays correct and C016 stays green | nothing at run time; after the squash merge the SHA is not on `main` anyway, which is the normal state today (`ebd18517` is not an ancestor of `main`, code-map §2.1) | accepted limitation; INV-15. If a later commit changes the derived data, regenerate in a new commit. If it changes only other text in an input, the generator correctly keeps `source.commit`, and nothing is regenerated |
| EC-7 | `main` merges another root export, for example the browser names, before this PR merges | `contracts/sdk-public-api.json` conflicts, or C016 reports `exports-stale` after the merge | the gate is red after the merge | field guide "Main can break a long-lived feature branch …": merge `main`, run the generator, commit, then `--check` |
| ~~EC-8~~ to ~~EC-12~~ | (withdrawn r2, R-5) Implementer-process mistakes: importing `PermissionPolicy` from another path, editing a `vidbyte/tools/security/` header, adding the 11 browser names, bumping the version, or writing the header bullet as a continuation line | — | — | each is now an obligation in §12.4 or a line in §14 |
| EC-13 | a root import goes through a module that `import vidbyte` did not already load | import time grows for every SDK user | slower `import vidbyte` | INV-16, D-1, D-3 (every chosen path is already loaded) |
| EC-14 | a consumer does `from vidbyte import *` after defining its own `PermissionPolicy` or `TextModelMode` | the root's object shadows the consumer's | a changed name binding after the upgrade | accepted limitation: an additive export always does this to star importers, and the root already exports 664 names |
| EC-15 | a misspelled near name, such as `vidbyte.TextModelModes` | the unchanged `__getattr__` raises `AttributeError` without importing the native package | the same error as today | INV-11 |
| ~~EC-16~~ to ~~EC-21~~ | (withdrawn r2, R-5) Implementer-process mistakes: saving the contract with CRLF, stopping after commit A, committing a placeholder PR number, editing an inherited red test, running a gate without `PYTHONPATH`, or running `pip install -e` from the worktree | — | — | each is now an obligation in §12.4, §12.6 or §14 |
| EC-22 | concurrency, retries, empty or first-run state, timeouts, scale | N/A: the module import is serialized by Python's import lock, there is no I/O or stored state, and both the generator and S015 are O(names), with 668 names | — | — |

**Rollback of the user action:** `git revert` the squash commit on `main`. The revert restores `vidbyte/__init__.py`, the release note, and the 664-name contract together, so C016 stays green and `source.commit` returns to `ebd18517…`. Before 0.4.0 is published, no released consumer depends on the four root names. After publication, removing a root name is a breaking change for vidbyte-cli, and `contracts/README.md` ("tell the vidbyte-cli owners") applies.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-1 | `AgentLoopSettings` is a root export: bound in `vidbyte/__init__.py` from `vidbyte.agents`, and listed once in `__all__`; it is `vidbyte.agents.settings.loop.AgentLoopSettings` | P0 | request.md §C "Build exactly this"; G-1 |
| FR-2 | `PermissionPolicy` is a root export: bound from `vidbyte.lib.dataclasses.security`, and listed once; `vidbyte.PermissionPolicy.allow_all()` permits all four `ToolPermission` levels ("I dont want writes to be denied") | P0 | request.md §C; Prompt 3 answer 3; G-1 |
| FR-3 | `TextModelMode` is a root export: bound from `vidbyte.lib.enums`, and listed once; it is `vidbyte.lib.enums.text_model.TextModelMode` | P0 | request.md §C; G-1 |
| FR-4 | `JevDynamicComputeOption` is a root export: bound from `vidbyte.lib.enums`, and listed once; it is `vidbyte.lib.enums.jev.JevDynamicComputeOption` | P0 | request.md §C; G-1 |
| FR-5 | `contracts/sdk-public-api.json` is regenerated by `scripts/generate-sdk-public-api.py` (never by hand) to 668 exports at `0.4.0`, in a commit after the root change | P0 | request.md §C ("regenerate … with the repo's generator"); contracts/README.md; C016 |
| FR-6 | The root header documents the four names in one new Architecture bullet; every other header line is unchanged | P1 | CONTRIBUTING.md "Making a Change" step 3; precedents 64e2bd67, 82b46c85; G-1 |
| FR-7 | `docs/design/release-0-4-0.md` records the four exports and the new counts, and drops the claim that `TextModelMode` is not a root export | P1 | request.md §C "Version (D-P2)" ("add them there"); G-2 |
| FR-8 | No other export path changes: no sub-package `__all__`, no definition, and no other root name | P0 | request.md §C "any behavior change" out of scope; G-3 |
| FR-9 | No version literal changes | P0 | request.md §C.2 D-P2; G-2 |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | Import cost: the change adds no import-time work | P0 | the set of `sys.modules` keys after a fresh `import vidbyte` is identical to `base_commit`'s; `vidbyte.harnesses.native` is absent |
| NFR-2 | Gate: the full local gate is green apart from the named inherited failures | P0 | The source stage's pytest shows exactly 5 failures: the 4 inherited ones of §11, plus `test_import_vidbyte_starts_no_process…`, which is red by design and only locally. Every test the test author added passes. Lint ends `SDK-LINT: PASS`. The package stage passes |
| NFR-3 | Smallest diff: the implementer changes only three files | P0 | `git diff --stat $MB HEAD` (`MB=$(git merge-base origin/main HEAD)`, §6.1) lists `vidbyte/__init__.py` (+9 lines, −0), `contracts/sdk-public-api.json` (+4 names and a new `source.commit`), and `docs/design/release-0-4-0.md` (three sentences), plus the test author's files and the spec folder |
| NFR-4 | The change is purely additive: every existing import and behavior keeps working ("always") | P0 | the full existing suite passes, except the inherited failures; INV-13 |

---

## Part C — Design

## §8 Architecture and decisions

### 8.1 Decisions
| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | Bind the four names **eagerly**, as ordinary imports in the root initializer | All four defining modules are already in `sys.modules` after a plain `import vidbyte` (verified), so an eager import costs nothing and keeps the name visible to type checkers and S015 with no hook | A lazy entry in a `_LAZY_*_EXPORTS` mapping, served by `__getattr__` | a later refactor stops `import vidbyte` from loading one of these modules, and that change measurably affects import time |
| D-2 | Import `PermissionPolicy` from its defining module: `from vidbyte.lib.dataclasses.security import PermissionPolicy` | AGENTS.md Placement Rules: "Import it from its domain module, `vidbyte.lib.dataclasses.<domain>`". This matches the root's precedent for a lib dataclass, `from vidbyte.lib.dataclasses.skills import SkillResolution` (`vidbyte/__init__.py:480`, added by #1099). The `vidbyte.lib.dataclasses` package re-exports it the same way (`vidbyte/lib/dataclasses/__init__.py:201`) | `from vidbyte.tools.security import PermissionPolicy`, the path `JevAgentSettings` uses (`vidbyte/agents/jev/settings.py:68`) and the one README.md shows | a repo rule or a reviewer requires root imports to go through package façades. Either path yields the same object, so the flip costs one line |
| D-3 | Add `AgentLoopSettings` to the existing `from vidbyte.agents import (…)` block, and both enums to the existing `from vidbyte.lib.enums import (…)` block | Three of the four names need no new import statement. The sibling `ToolSettings` already comes from the `vidbyte.agents` block, and the enum block is how the root imports enums. Both paths are already loaded | Import from `vidbyte.agents.settings` or `vidbyte.lib.enums.text_model` directly | none expected; the objects are identical on every path |
| D-4 | Place each name in `__all__` beside its domain sibling: `JevDynamicComputeOption` after `"JevComputeSettings"`, then `AgentLoopSettings` and `TextModelMode` after `"AgentStopReason"` (the agent-configuration run that ends with `"ToolSettings"`), and `PermissionPolicy` after `"ToolPermission"` | Root `__all__` is grouped by domain, not sorted (code-map §2.1). A reader looking for compute options or permission types finds them next to the related names. No test pins the order | One cluster of four, appended together, as #1099 did with `SkillLoader`, `SkillResolution` and `ConfigurationError` | a reviewer prefers the single-cluster form. Order is not part of any contract (the contract sorts), so the flip is free |
| D-5 | Document the four in **one new** header bullet, `- Agent setting exports:`, inserted after `- Agent exports:` | One line states what the four are for and who needs them, without rewriting the existing bullets. The precedent #1179 added a bullet of its own ("Native harness thread exports") | Append the names to the existing Agent and Tool bullets | a reviewer prefers the names inline. That is also a one-line change |
| D-6 | The release record is `docs/design/release-0-4-0.md`. Edit three sentences: the `TextModelMode.DIRECT` claim, the "Later changes on `main`" bullet, and the contract-count sentence | It is the only record of the unreleased 0.4.0. It enumerates every root export the release adds, with counts (664 = 639 + 25), and it states that `TextModelMode.DIRECT` is "exported from `vidbyte.lib.enums` and not the root". After this PR, both statements are false unless edited. Putting the PR in "Later changes" keeps the list's stated range (`v0.3.0..82b46c85` plus #1099) true | A bullet of its own in the release list | the release note is rewritten or replaced before this PR merges. Then the same three facts go into whatever replaced it |
| D-7 | No version change (user decision, request.md §C.2 D-P2) | 0.4.0 is unpublished, and these exports ship in it; "updates the version" is met by that | Bump to 0.4.1 | the user says otherwise during the run |
| D-8 | Three commits, in this order. **Commit A** holds only the root change (§12.3 row 1). **Commit B** holds only the regenerated contract, written by the generator (row 3). The draft PR is opened next. **Commit C** holds only the release-note edits (row 2), citing the PR number read from `gh pr view feat/jev-cli-root-exports --json number -q .number` | The generator refuses to write while `vidbyte/__init__.py` or `pyproject.toml` differs from HEAD, and it records HEAD as `source.commit` (`scripts/generate-sdk-public-api.py:69-72`, `:118-130`). Hand edits falsify provenance (EC-5). Row 2 needs a PR number that does not exist until the draft PR is open, and GitHub numbers issues and PRs from one shared sequence, so a guess is unsafe (R-2). The release note is not a generator input: the inputs are `pyproject.toml` plus the resolved root module (`lint/core/public_api_contract.py:431`). So commit C leaves `source.commit` true, C016 CLEAN, and nothing to regenerate (INV-15) | Two commits, with the release note in commit A. That needs the PR number before the PR exists | the generator starts reading `docs/`, or the PR is opened before implementation starts. Then row 2 can join commit A |
| D-9 | Leave the headers of the defining modules unchanged | Nothing in them becomes false. #1099 is the precedent for the runner-up: it added "and by the package root vidbyte/__init__.py, which re-exports SkillLoader as a public name" to the ROLE of `vidbyte/agents/skills/__init__.py`, and "for any caller that imports `SkillLoader` from the package root" to `vidbyte/agents/README.md`. Those texts named the skill package's consumers as if the list were complete, so leaving them alone would have made them stale. The four headers here make no such claim. They already omit most of their re-exporters: for example, `vidbyte/lib/dataclasses/security.py:12` does not name `vidbyte.lib.dataclasses`, which re-exports `PermissionPolicy` at `vidbyte/lib/dataclasses/__init__.py:201`. Leaving them alone keeps INV-6 simple and keeps the 3-file budget (§8.4). The `vidbyte/tools/**` headers cannot change anyway (NG-8) | Add "re-exported from the root" to `loop.py`, `security.py`, `text_model.py` and `jev.py`, as #1099 did for `SkillLoader` | a reviewer asks for it (Q-2, default No). Then only the four files outside `vidbyte/tools/` change, and §8.4 grows by four |

### 8.2 Patterns inherited
- **Façade re-export: one public import surface over layered packages.** The root initializer re-exports lower-layer objects without redefining them. It fits because the CLI's C028 admits only root names. The repo uses it in `vidbyte/__init__.py` (for example, `SkillResolution` at `:480` and `ToolSettings` through `from vidbyte.agents import …`). A006 explicitly exempts every `__init__.py` from the layering graph (`lint/rules/a006_directed_dependency_graph.py:67`).
- **Generated contract with provenance and a freshness lint (generate, then check).** The contract file is derived from source by one script that stamps the commit it read, and a lint rule fails when the committed copy drifts. The repo uses it in `scripts/generate-sdk-public-api.py`, `lint/core/public_api_contract.py`, and `lint/rules/c016_public_api_contract_current.py`.
- **Expand-only API change.** An additive public name needs no deprecation path and no migration. Removing it later would be the breaking "contract" step (`contracts/README.md`: "When an export is removed or renamed, tell the vidbyte-cli owners").

### 8.3 Smaller design rejected
- **Root imports and `__all__` only, with no contract regeneration and no doc edits.** This fails FR-5 and INV-4. C016 reports `exports-stale` (baseline 0, blocking), and the CLI's vendored copy would never list the names, so G-1 is not met. It also fails FR-7 and INV-17: the release note would keep saying `TextModelMode` is "not the root" and that the contract lists 664.
- **Export only the three names the CLI cannot replace with a string** (`AgentLoopSettings`, `PermissionPolicy`, `TextModelMode`). This fails FR-4. The request names `JevDynamicComputeOption` explicitly (request.md §C "Build exactly this", and R1 in §C.2 D-P1).

### 8.4 Complexity budget
| Item | Count | Justification for each |
|---|---|---|
| New files | 0 | The implementer creates no file. The test author's pack files are written at S2 and do not count against this budget; they must meet the §12.4 test-file obligations |
| New classes/modules | 0 | All four classes exist; only bindings are added |
| New dependencies | 0 | — |
| New config keys | 0 | — |
| New collections/tables | 0 | — |
| New public endpoints/commands | 4 root export names | `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode`, `JevDynamicComputeOption`, each required by request.md §C |
| Files changed (implementer) | 3 | `vidbyte/__init__.py` (source), `docs/design/release-0-4-0.md` (release record, D-6), `contracts/sdk-public-api.json` (generated, D-8) |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

These names are the contract that the test author imports and that the implementer must provide. Each is an existing object, with its signature unchanged:

```python
# vidbyte (root package): the four new root names and where each binding comes from.
from vidbyte.agents import AgentLoopSettings                     # defined in vidbyte.agents.settings.loop
from vidbyte.lib.dataclasses.security import PermissionPolicy    # defined there
from vidbyte.lib.enums import JevDynamicComputeOption            # defined in vidbyte.lib.enums.jev
from vidbyte.lib.enums import TextModelMode                      # defined in vidbyte.lib.enums.text_model

class AgentLoopSettings:  # plain validated class; raises ConfigurationError on bad input
    def __init__(self, *, max_iterations: int | None = None, max_tokens: int | None = None,
                 max_tool_calls: int | None = None, max_queued_prompts: int = 25,
                 max_parallel_tool_calls: int | None = None, max_retries: int | None = None,
                 timeout_seconds: float | None = None, context_window_budget: int | None = None,
                 compaction_trigger_tokens: int | None = None, compaction_target_tokens: int | None = None,
                 allowed_tools: tuple[str, ...] | None = None, tool_error_policy: ToolErrorPolicy | None = None,
                 tool_settings: ToolSettings | None = None, output_contracts: Sequence[OutputContract] = (),
                 max_contract_rejections: int = 3) -> None: ...

@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    allowed: frozenset[ToolPermission] = frozenset({ToolPermission.SAFE, ToolPermission.READ})  # strings are converted
    def check(self, spec: ToolSpec, call: ToolCall) -> PermissionDecision: ...  # also honors PermissionCeiling
    @classmethod
    def allow_all(cls) -> "PermissionPolicy": ...  # every ToolPermission

class TextModelMode(str, Enum):
    AUTO = "auto"; VIDBYTE_MANAGED = "vidbyte_managed"; DIRECT = "direct"

class JevDynamicComputeOption(str, Enum):  # members in tie-break order
    FRESH_AGENT = "fresh_agent"; FORK_AGENT = "fork_agent"; SUBAGENT = "subagent"; CLONE = "clone"; SWARM = "swarm"
```

Contract file shape (schema unchanged, `schema_version` 1):

```json
{
  "schema_version": 1,
  "source": {"repository": "cerredz/Vidbyte-SDK", "commit": "<full SHA of commit A>", "generator": "scripts/generate-sdk-public-api.py"},
  "distribution": "vidbyte-sdk",
  "version": "0.4.0",
  "exports": ["ActionTrace", "…668 names, sorted with Python's sorted()…", "vidbyte_tool"]
}
```

## §9 Data, API, configuration, migration

### 9.1 Data model
N/A — no entity, record, field, or stored data is added or changed; the four classes are byte-identical.

### 9.2 API and interface surface
Four public Python names are added to the root package: `vidbyte.AgentLoopSettings`, `vidbyte.PermissionPolicy`, `vidbyte.TextModelMode`, and `vidbyte.JevDynamicComputeOption`. Their constructors, members, validation, and error types are unchanged. Validation stays at the existing boundaries: `AgentLoopSettings.__init__` and `JevAgentSettings.__post_init__` raise `ConfigurationError`, and `PermissionPolicy.__post_init__` raises `ValueError` for a single string. No auth applies, because this is an in-process library. The cross-repository contract `contracts/sdk-public-api.json` grows from 664 to 668 `exports` with no schema change.

### 9.3 Configuration and flags
N/A — no environment variable, setting, or flag is added; the CLI flags that will use these names are CLI PRs C2 and C4.

### 9.4 Migrations and compatibility
Additive only. Every existing import path keeps working (INV-13), so no caller has to migrate and nothing is deprecated. The public contract changes by addition. vidbyte-cli picks up the new names when its PR C4 vendors the regenerated contract and moves its pin to `>=0.4.0,<0.5` (request.md §C.2 D-P2). Until 0.4.0 is published, the CLI tests against a locally built wheel (A-3). Publishing is a separate release step, and its last named precondition, SDK #1184, merged as `513aa614` on 2026-10-19.

## §10 Security and tenancy
| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | Imports `PermissionPolicy` from the root and passes `allow_all()` as a blanket default to an agent with coding tools, so the model can write files and run shell commands | The SDK default stays `SAFE` and `READ` (INV-7). `allow_all()` is an explicit opt-in call; for the CLI it is the user's own decision (D-P3). `allow_all()` was already reachable through `vidbyte.tools.security` on `base_commit`, so the root export changes the SDK's security posture in no way: it only shortens the import path. `PermissionPolicy.check` also honors the run's `PermissionCeiling` (`vidbyte/lib/dataclasses/security.py:48-56`), but the ceiling defaults to `None` (`vidbyte/lib/permission_ceiling.py:27`). It caps nothing unless Jev's `read_only` preset, or another scope, opens one, so it is not a control on this path | inside the SDK, in the caller's process; this change has no server |
| T-2 | Hostile user | N/A — the change adds no input surface (no parser, no I/O, no new argument) | The four classes validate hostile values exactly as before | the existing constructors |
| T-3 | Compromised teammate / leaked credential | Slips an extra internal name into root `__all__` and the contract in this auto-merged PR, which makes it a public commitment | INV-3 and AC-5 (exactly four added, checked against `base_commit`). `generate-sdk-public-api.py --check` prints "exports added: …" for any drift. The contract diff is reviewed at S4 | CI and the lint gate, plus review |
| T-4 | Another tenant | N/A — an in-process library with no tenancy and no stored data | — | — |

No secret is involved: none of the four classes holds a key, and their `repr` is unchanged. The repo's secret conventions (`repr=False` on key fields, as in `JevAgentSettings.api_keys` and `vidbyte_api_key`) are untouched.

## §11 Codebase grounding

- **Rules read:** AGENTS.md in full. The rules that bind this change:
  - Repository Map: the full local gate `python scripts/run_ci.py`; `docs/` is opaque, except a document a human names.
  - General Coding Style 3: the layering rule (it does not bind the root initializer); "keep files well below 1,000 lines" (see NG-6).
  - Placement Rules, Dataclasses: "Import it from its domain module … the definition stays in `vidbyte/lib/dataclasses/`".
  - Placement Rules, Enums: "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`". Both enums already are, at `:284` and `:347`.
  - Placement Rules, Existing code.
  - `CONTRIBUTING.md:38-45` ("Keep public API changes explicit … Update nearby documentation when … imports … change") and `:52-75`.
  - `contracts/README.md` (37 lines): never hand-edit; regenerate after committing the source.
  - `.github/pull_request_template.md`.
  - `vidbyte/` has no folder README.
- **Field-guide entries applied** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`):
  - `local-ci-verification.md`, "Run the source stage with `PYTHONPATH=<worktree>` and the package stage without it": source stage and tests use the worktree on `PYTHONPATH`; the package stage runs without it.
  - `local-ci-verification.md`, "Check S051 import sorting with ruff over the whole `vidbyte` tree": run ruff I001 over `vidbyte`, not over one file.
  - `local-ci-verification.md`, "Two `harness_threads` surface tests fail locally …": `test_import_vidbyte_starts_no_process…` turns red because root `__all__` changes; classify it as pre-existing and do not edit it.
  - `local-ci-verification.md`, "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself": inherited, so name it in the PR body.
  - `local-ci-verification.md`, "Main can break a long-lived feature branch …": after any merge of `main`, rerun `generate-sdk-public-api.py --check`.
  - `local-ci-verification.md`, "Semgrep only scans git-tracked files": `git add` first.
  - `local-ci-verification.md`, "Dispatched checks never unblock the merge": merge with `--admin --match-head-commit`.
  - `review-scope.md`: keep the PR to its minimal surface.
- **Stack (from manifests):** Python `>=3.11` (`pyproject.toml:10`; local `py -3.11` is 3.11.0; CI matrix 3.11 and 3.12). setuptools build. Dev tools pinned in `pyproject.toml:45-50`: `pytest==8.3.5`, `pytest-asyncio==1.3.0`, `mypy==2.3.1`, `ruff==0.16.4`. `semgrep==1.170.1` (`.github/workflows/static-policy.yml:24`). No database.
- **Commands** (exact, from code-map.md §1.2/§3.1 and AGENTS.md; on this machine use `py -3.11` in place of `python`, prefix `PYTHONPATH=$(pwd)` for source-side commands run from the worktree root, and never `export` it):
  - Install: none for this worktree. The shared editable install (`python -m pip install -e ".[dev]"`, `CONTRIBUTING.md:35`) already exists and resolves to the canonical checkout. Do not reinstall from the worktree (§14 Never).
  - Lint: `PYTHONPATH=$(pwd) py -3.11 lint/run.py` (last line `SDK-LINT: PASS`). Focused: `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule C016`, `--rule S015`, `--rule S051`, `--rule A001`.
  - Import order (S051/I001): `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`. Filter the output to `vidbyte\__init__.py`; there are 0 lines on `base_commit`.
  - Contract: `py -3.11 scripts/generate-sdk-public-api.py --check`; regenerate with `py -3.11 scripts/generate-sdk-public-api.py`, only after commit A.
  - Typecheck: mypy runs inside lint as S009: `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S009`.
  - Test (focused): `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/<pack>`, or one file by its path.
  - Test (full): `PYTHONPATH=$(pwd) py -3.11 -m pytest`.
  - Full local gate: AGENTS.md's `python scripts/run_ci.py`, run on this machine as `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`, then `py -3.11 scripts/run_ci.py --stage package` with no `PYTHONPATH`.
  - Static policy: `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
  - Remote-only checks: `.github/workflows/ci.yml` and `static-policy.yml` run only on `workflow_dispatch`; their automatic triggers are removed ("TEMPORARILY DISABLED"). Dispatched runs do not attach to the PR's check rollup, so the merge is `gh pr merge <n> --squash --admin --match-head-commit <sha>` (field guide; request.md §C).
- **Baseline at `base_commit`**. `b7350ed6` was `origin/main` at S1. The baseline adds `0e7a8eb0`, which is this branch's first commit (docs-only, not part of `origin/main`). It was run in this session. `origin/main` has since moved to `0cce5781` (#1184, #1188), and that delta touches no gated path (§12.6 P4):
  - `PYTHONPATH=$(pwd) py -3.11 -m pytest` gives `4 failed, 6715 passed, 17 skipped`. The 4 failures:
    - `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`; inherited, per the field guide).
    - `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_every_native_export_is_listed_in_the_root_all`, `::test_each_root_name_is_the_native_object_itself`, and `::test_the_public_api_contract_lists_every_root_native_name_at_the_package_version`. These are inherited from #1183: the 11 browser names have no root export (NG-1).
  - After this change, `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` also fails locally, by design, because it compares root `__all__` with the merge base (field guide "Two `harness_threads` surface tests fail locally …"). CI skips it. Do not edit it (§14).
  - CI-only: `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is a known 3.11 flake.
  - The package stage was not run at S1 (A-6).
  - Lint on HEAD: `PYTHONPATH=$(pwd) py -3.11 lint/run.py` exits 0 with `SDK-LINT: PASS`.
    - C016 is `CLEAN` (0).
    - These rules are `RATCHETED` at their baselines: S015 at 13 (4 of them on the root, as listed in NG-3), A001 at 642, S051 at 259, and S020 at 1.
    - Seven rules already report `IMPROVED` on `main`, all from earlier PRs: A002 (703 → 566), S001 (59 → 56), S009 (350 → 346), S010 (5 → 0), S025 (263 → 261), S061 (6 → 5), and S063 (4 → 3).
    - `generate-sdk-public-api.py --check` prints "current at ebd18517… (vidbyte-sdk 0.4.0, 664 exports)".
    - ruff I001 has 0 findings on `vidbyte/__init__.py`.
- **Directory layout relevant to this change:**
  ```
  vidbyte/__init__.py                 root façade: header :1-37, __version__ :41, imports :45-760, __all__ :762-1427, lazy natives :1435-1467
  vidbyte/agents/settings/loop.py     AgentLoopSettings :46 (read only)
  vidbyte/lib/dataclasses/security.py PermissionPolicy :32-61 (read only)
  vidbyte/lib/enums/text_model.py     TextModelMode :17 (read only)
  vidbyte/lib/enums/jev.py            JevDynamicComputeOption :278 (read only)
  contracts/sdk-public-api.json       generated, LF (contracts/.gitattributes)
  scripts/generate-sdk-public-api.py  the only writer of the contract
  docs/design/release-0-4-0.md        0.4.0 release record (19 lines; the one docs/ file this PR edits)
  ```
- **Nearest sibling feature (the template to copy):** commit `64e2bd67` (#1099, public skill loader), which touches `vidbyte/__init__.py`, `contracts/sdk-public-api.json` and `docs/design/release-0-4-0.md`. Copy four things from it: a lib dataclass imported from its domain module (`from vidbyte.lib.dataclasses.skills import SkillResolution`), new names placed in a thematic `__all__` spot, a header line edit, and the release-note entry with counts. A second sibling is commit `82b46c85` (#1179, native thread root exports): copy its own header bullet and its order of a source commit before a contract commit. This PR adds a third commit for the release note (D-8).
- **Reusable pieces:**
  - `scripts/generate-sdk-public-api.py:PublicApiContractGenerator.run`: writes the contract (this PR's row 3).
  - `lint/core/public_api_contract.py:PublicApiDeriver.derive`: the static derivation that both C016 and the generator use.
  - `lint/rules/s015_public_export_integrity.py:ExportIntegrityAnalyzer`: checks root binding and listing.
  - The existing re-export blocks `vidbyte/__init__.py:45-280` (`vidbyte.agents`) and `:481-491` (`vidbyte.lib.enums`), which receive three of the four names.
- **Code-style exemplar** (`vidbyte/__init__.py:477-491`, verbatim):
  ```python
      ProsecutorDefenderJudgeReport,
      ProsecutorReportPayload,
  )
  from vidbyte.lib.dataclasses.skills import SkillResolution
  from vidbyte.lib.enums import (
      BudgetPreset,
      GrokPermissionMode,
      GrokReasoningEffort,
      InfiniteMemoryPreset,
      MuseReasoningEffort,
      PermissionPreset,
      Prompt,
      StructuredOutputSupport,
      SystemPromptPreset,
  )
  ```
- **Domain glossary:**
  - root export: a name bound in `vidbyte/__init__.py` and listed in its `__all__`.
  - the contract: `contracts/sdk-public-api.json`, `sorted(set(vidbyte.__all__))` plus the distribution, version and provenance.
  - C028: vidbyte-cli's lint rule that admits only contract-listed root names.
  - C016: the SDK lint rule that keeps the contract current.
  - S015: the SDK lint rule for export integrity.
  - text-model mode: how text calls are routed (gateway relayed, gateway Vidbyte-paid, or direct).
  - dynamic compute option: a kind of extra agent that Jev's mid-run checkpoint may launch.
- **Prior specs / design docs / ADRs that constrain this:** `docs/design/release-0-4-0.md` (named by the orchestrator; read in full). request.md §C.2 D-P1 to D-P3. No other.
- **Conflicts between house style and AGENTS.md:** none that bind. House style's "small functions" and "narrate the main function" have no target here, because no function is written. AGENTS.md's file-length rule is noted in NG-6.

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list
| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1 | `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode` and `JevDynamicComputeOption` importable from top-level `vidbyte` as the defining objects, each listed once in `__all__` | FR-1 to FR-4, FR-8, NFR-1, NFR-4, AC-1 to AC-3, AC-5 to AC-8, AC-10, AC-12, AC-14 | developer (vidbyte-cli, SDK users) |
| W-2 | The public-API contract lists the four names at 0.4.0 with true provenance | FR-5, FR-9, NFR-2, AC-4, AC-9, AC-12, AC-13 | vidbyte-cli (C028), operator |
| W-3 | The root header and the 0.4.0 release record describe the new surface | FR-6, FR-7, AC-11, AC-15 | maintainer, release operator |

### 12.2 Folder and module map
| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/` (root initializer only) | public façade above every layer; A006 excludes it (`a006_directed_dependency_graph.py:67`) | no | no folder README exists. The file keeps its legacy "Context Protocol Header"; add one Architecture bullet (D-5) | any sub-package; chosen paths per D-2 and D-3 |
| `contracts/` | generated machine-readable contracts | no | `contracts/README.md` File Index already lists `sdk-public-api.json`; no change (its Change Log records creation only, and no precedent adds a line per regeneration) | n/a (generated) |
| `docs/design/` | design and release records (opaque to agents unless named) | no | none | n/a |

### 12.3 File-by-file actions
| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard (AGENTS.md § / placement rule / field-guide file / lint rule ID) | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | MODIFY | `vidbyte/__init__.py` | package initializer (public façade) | **(a)** In `from vidbyte.agents import (…)` (`:45-280`), insert `    AgentLoopSettings,` between `    AgentInput,` (`:52`) and `    AgentMessage,` (`:53`). **(b)** Insert the new statement `from vidbyte.lib.dataclasses.security import PermissionPolicy` on its own line, between the closing `)` of the `vidbyte.lib.dataclasses.prosecutor_defender_judge` block (`:479`) and `from vidbyte.lib.dataclasses.skills import SkillResolution` (`:480`). **(c)** In `from vidbyte.lib.enums import (…)` (`:481-491`), insert `    JevDynamicComputeOption,` between `    InfiniteMemoryPreset,` (`:485`) and `    MuseReasoningEffort,` (`:486`), and insert `    TextModelMode,` after `    SystemPromptPreset,` (`:490`). Positions (a) to (c) were checked with ruff I001 on a scratch probe. **(d)** In `__all__`: insert `    "JevDynamicComputeOption",` immediately after `    "JevComputeSettings",` (`:824`); insert `    "AgentLoopSettings",` then `    "TextModelMode",` immediately after `    "AgentStopReason",` (`:1053`), before `    "ToolSettings",`; insert `    "PermissionPolicy",` immediately after `    "ToolPermission",` (`:1373`). **(e)** Header: insert this line, verbatim, directly after the `    - Agent exports: …` line (`:12`): `    - Agent setting exports: AgentLoopSettings (loop limits), PermissionPolicy (which ToolPermission levels tools may use) and TextModelMode (gateway or direct text calls), which BaseAgent and JevAgentSettings take, plus JevDynamicComputeOption, the values of JevComputeSettings.dynamic_compute, so a caller limited to root names, such as vidbyte-cli, can set JevAgent's loop, permission, text-mode and compute options.` Nothing else in the file changes: not `__version__`, the `TYPE_CHECKING` block, `_LAZY_NATIVE_THREAD_EXPORTS`, `__getattr__`/`__dir__`, any other import, or any other `__all__` entry or its order. Net change: +9 lines | S015 (bound and listed once; `s015_public_export_integrity.py:38-45`); S051/I001 (field guide "Check S051 …"); `__all__` stays one literal list (S015's `_exports` reads only the first literal `__all__` list, `s015_public_export_integrity.py:48-53`; the C016 deriver would also accept `+=` or `.extend`, `lint/core/public_api_contract.py:5`, but S015 would then miss the new names); AGENTS.md Placement Rules / Dataclasses ("Import it from its domain module") for (b); the docs test `test_public_skill_loader_docs.py:91` (keep `- Error exports:` intact); AGENTS.md style preamble (do not rewrite untouched code: the header style stays legacy, A001 stays 642); CONTRIBUTING.md step 3 for (e) | FR-1 to FR-4, FR-6, FR-8, W-1, W-3 | P1 |
| 2 | MODIFY | `docs/design/release-0-4-0.md` | doc (release record) | Three edits, everything else byte-identical. Made as commit C, after the draft PR exists. `<n>` is this PR's real number, read from `gh pr view feat/jev-cli-root-exports --json number -q .number`. It is never guessed, and `#<n>` is never committed (A-1, INV-17). This file is not a generator input, so commit C needs no regeneration (D-8, INV-15). **(a)** Replace `` `TextModelMode.DIRECT`, exported from `vidbyte.lib.enums` and not the root, calls the provider directly with the caller's own key. `` with `` `TextModelMode.DIRECT`, exported from the root and from `vidbyte.lib.enums`, calls the provider directly with the caller's own key. ``. **(b)** At the end of the `- **Later changes on `main`.**` bullet, after `` lists it beside #1099. ``, append: `` Among them, #<n> makes `AgentLoopSettings`, `PermissionPolicy`, `TextModelMode`, and `JevDynamicComputeOption` root exports, 4 names, so vidbyte-cli can set `JevAgent`'s loop limits, allow write and execute tools, choose the text-model mode, and name compute options without a deep import; the four classes and their defaults are unchanged. ``. **(c)** Replace `` The contract now lists 664 exports, against 639 at `v0.3.0`: 25 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, and `SystemPromptPreset` from #1095. `` with `` The contract now lists 668 exports, against 639 at `v0.3.0`: 29 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, 4 from #<n>, and `SystemPromptPreset` from #1095. `` (639 was verified from `git show v0.3.0:contracts/sdk-public-api.json`). Keep UTF-8, and keep the one non-ASCII `…` in the "Breaking default" bullet | request.md §C "Version (D-P2)" ("add them there"); D-6; AGENTS.md Repository Map: `docs/` is opaque, and this file is the one named document, so read and edit only this file | FR-7, W-3, AC-15 | P3 |
| 3 | REGENERATE | `contracts/sdk-public-api.json` | generated contract | After commit A, run `py -3.11 scripts/generate-sdk-public-api.py`. The expected console line is `wrote contracts/sdk-public-api.json at <SHA of commit A> (vidbyte-sdk 0.4.0, 668 exports)`. The result: four `exports` lines (`"AgentLoopSettings"` after `"AgentInput"`, `"JevDynamicComputeOption"` after `"JevDoneResult"`, `"PermissionPolicy"` after `"ParentPolicy"`, `"TextModelMode"` after `"TextContextItem"`) and a new `source.commit`. Commit it alone as commit B. Never edit it by hand | `contracts/README.md` ("Never edit a contract by hand"); generator header WHAT NOT TO DO 1-2; C016 (baseline 0); `contracts/.gitattributes` (LF) | FR-5, FR-9, W-2, AC-4, AC-13 | P2 |

### 12.4 Standards checklist for this change
- [ ] Each of the four names is imported exactly once and listed exactly once in root `__all__`. S015 stays at 13 findings, and none of them is a new root finding. — *source:* `lint/rules/s015_public_export_integrity.py`, `lint/baseline.json` (`"S015": 13`)
- [ ] The import positions follow ruff isort exactly as in row 1 (a) to (c). `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` prints no `vidbyte\__init__.py` line, and S051 does not regress. — *source:* field guide `local-ci-verification.md` "Check S051 …"; `lint/baseline.json` (`"S051": 259`)
- [ ] `__all__` stays one literal list of string constants; no existing entry is moved, removed, or reordered, and no `+=`, `.extend` or `.append` is added. — *source:* `lint/rules/s015_public_export_integrity.py:48-53` (`_exports` reads only the first literal `__all__` list, so names added any other way escape S015, although the deriver at `lint/core/public_api_contract.py:5` would accept them); INV-3
- [ ] `PermissionPolicy` is imported from `vidbyte.lib.dataclasses.security`; the definitions stay where they are. — *source:* AGENTS.md Placement Rules / Dataclasses (D-2)
- [ ] Both enums are already in `vidbyte/lib/enums/__init__.py`'s `__all__` (`:284`, `:347`), so that file is not edited. — *source:* AGENTS.md Placement Rules / Enums
- [ ] The new header line starts with `    - ` (four spaces, a dash, a space), sits on its own line directly after `- Agent exports:`, and does not wrap. `- Error exports:` still contains `ConfigurationError`. — *source:* `tests/features/public_skill_loader/test_public_skill_loader_docs.py:24,91` (its `PART_BREAK` reads a bullet up to the next `- ` line)
- [ ] The header keeps its legacy "Context Protocol Header" format; no A001 field is added or removed, and A001 stays at 642. — *source:* AGENTS.md style preamble; `lint/baseline.json` (`"A001": 642`)
- [ ] The contract is written only by the generator, after commit A. Commit B contains only `contracts/sdk-public-api.json`, LF-only. C016 is `CLEAN`, and `--check` exits 0 at the head. — *source:* `contracts/README.md`; `scripts/generate-sdk-public-api.py` (D-8); `lint/baseline.json` (`"C016": 0`)
- [ ] Commit C contains only `docs/design/release-0-4-0.md`, with this PR's real number in both places of row 2, read from `gh pr view`. It changes no generator input, so `--check` still reports `current at <commit A>` after it. — *source:* D-8; `lint/core/public_api_contract.py:431`; INV-15, INV-17
- [ ] No file under `vidbyte/tools/**` or `vidbyte/lib/configs/**`, and no defining module or sub-package `__init__.py`, changes. — *source:* `tests/features/harness_threads/test_harness_threads_surface.py:227-235`; INV-6
- [ ] No version literal changes (INV-8). — *source:* request.md §C.2 D-P2; `tests/features/public_skill_loader/test_public_skill_loader_release.py`
- [ ] Under `docs/`, read and edit only `docs/design/release-0-4-0.md` and this spec folder. — *source:* AGENTS.md Repository Map
- [ ] No tracked bytecode. Run Python with `PYTHONDONTWRITEBYTECODE=1`; the source stage checks this. — *source:* `scripts/run_ci.py:_assert_no_tracked_bytecode`; CONTRIBUTING.md step 4
- [ ] Every gate runs from the worktree root, with `PYTHONPATH=$(pwd)` for source-side commands and none for the package stage. The final verdict comes from both stages. — *source:* AGENTS.md Repository Map; field guide `local-ci-verification.md`
- [ ] New test files (the test author's, at S2) carry all seven A001 fields (`PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, `TESTS:`). A pack `README.md` with `## File Index` lists every direct child (S020). Test basenames stay unique across `tests/`. — *source:* `lint/rules/a001_agent_readable_file_headers.py:24-32`; `lint/rules/s020_readme_file_index_parity.py`
- [ ] Commit messages cite spec IDs (for example `W-1`, `FR-1..FR-4`) and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; subjects follow `feat(<scope>): …`. — *source:* `git log` style (code-map §1.4); attribution instruction
- [ ] N/A for this change, with the reason: main-function narration, `@intent` comments, validated dataclasses, and structured error packets all need a new function, rule, record, or raise, and this PR writes none. — *source:* AGENTS.md General Coding Style 2 and 4; house style

### 12.5 Non-code actions
- Release-record entry for the unreleased 0.4.0: `docs/design/release-0-4-0.md` (row 2, commit C, after the draft PR exists). — *source:* request.md §C "Version (D-P2)"
- Regenerate the public-API contract: `contracts/sdk-public-api.json` (row 3). — *source:* request.md §C; C016
- README.md, llms.txt, REPO_MAP.md, and `artifacts/file_index.md` root-export listings: **none found**. None of those files lists root exports or `__all__`. This was checked with `git grep -n -i "root export\|__all__\|public api\|public surface\|sdk-public-api"` over the four files, and no test ties them to `__all__` (code-map §2.7). No action. — *source:* request.md §C ("the spec author finds and cites each")
- `contracts/README.md` Change Log: no entry. It records the folder's creation only, and neither #1099 nor #1179 added a line when regenerating. — *source:* `contracts/README.md:35-37`
- Lint-baseline ratchet: none. The seven rules that report `IMPROVED` on `main` (§11 baseline) improved in earlier PRs, not this one, so lowering their baselines is not this PR's change (hard rule 9). Leave `lint/baseline.json` untouched. Report any rule whose count this PR itself changes. — *source:* vidbyte-gates "ratchet … only after a genuine source improvement"; house style
- `.env.example`, registrations, folder READMEs: N/A. There is no configuration, no registry, and no new folder.
- PR body (S6): name the inherited failures, each with proof on pristine `main`. These are the 3 in `root_native_thread_exports`, the `assert 167 == 120` test, and the local-only `test_import_vidbyte_starts_no_process…`. List the follow-ups: Q-1, Q-3 (`ModelProvider` stays non-root; the CLI's provider parity check goes through `JevAgentSettings(provider=…)` until a later SDK PR exports it), the `denied=` doc bug from NG-7, the stale "#1184 gate" sentence in the release note (next bullet), and the CLI refresh of the vendored contract (C4).
- Follow-up, not done here: the release note's "#1184 gate" sentence has been stale since `513aa614`. That sentence is "Do not tag until the Meta key fix, #1184, is on `main`: on 2026-10-18, `main`'s Meta key rule still matched only the legacy `LLM|` shape …", in `docs/design/release-0-4-0.md:19`, the same line as row 2 (c). #1184 merged as `513aa614`, and the META row of `KEY_FORMATS` on `main` now accepts both shapes, `("LLM|", "LLM_")` (`vidbyte/lib/registries/provider_keys.py:59` on `0cce5781`). This PR does not edit that sentence; row 2 (c) replaces only the count sentence beside it. Correcting it is release-gate wording, and it is left for the release PR. — *source:* coordinator r3 note; review round 2 stale-fact list — *source:* field guide `local-ci-verification.md`; `.github/pull_request_template.md`

### 12.6 Phases and dependency order

**P1 — Source commit (commit A)** (ships: the four names are importable from `vidbyte`; C016 is red with `exports-stale`, and any test that reads the contract JSON is red, by design until P2): row 1 only. Run the focused tests and `lint/run.py --rule S015`, `--rule S051`, and ruff I001 before committing. Capture the AC-5 `--check` output right after committing.

**P2 — Contract commit (commit B)** (ships: C016 is CLEAN, and the CLI-facing contract lists 668 names): row 3. P2 must run. The PR is incomplete after P1 alone.

**P3 — Release-note commit (commit C)** (ships: the 0.4.0 record names the four exports): row 2, only once the draft PR exists. S3 opens the draft PR in its Phase 6. Right after `gh pr create`, S3 does four things:
1. It reads the number with `gh pr view feat/jev-cli-root-exports --json number -q .number`.
2. It applies row 2 alone as commit C.
3. It reruns `--check`, expecting `current at <commit A>`, and the AC-15 diff.
4. It pushes.

Row 2 is pending only if `gh pr create` itself fails. S3 then reports row 2 as **pending (needs PR number)**, not BLOCKED, and never commits a placeholder (A-1).

**P4 — Verify** (ships: nothing new): the full local gate (§11), `--check`, the S015/S051/C016 counts, and the one-time proofs of §6.2's second table, each measured against `$MB` (§6.1).

`main` has moved since S1. `origin/main` is `0cce5781`, which is `b7350ed6` plus #1184 (`513aa614`) and #1188 (`0cce5781`), with 51 files changed. That delta touches no gated path:
- `git diff --name-only b7350ed6 origin/main -- vidbyte/__init__.py pyproject.toml contracts docs/design/release-0-4-0.md lint/baseline.json README.md llms.txt` prints nothing.
- No version literal of INV-8 changes.
- Under `vidbyte/` it changes only `vidbyte/lib/registries/provider_keys.py` and Markdown files, and adds no module. A fresh `import vidbyte` on `0cce5781` loads the same 948 modules, with the same hash as `b7350ed6` (re-measured at r3).
- The reviewer ran main's changed test packs on a `git archive origin/main` copy, and 383 passed.

So merging `main` is optional for correctness. If S3 merges it, `$MB` moves with it, and every one-time proof still holds. After any merge, regenerate in a new commit only if the derived data changed, and run `--check` again.

**Dependency order:** row 1 → commit A → row 3 → commit B → draft PR opened → row 2 → commit C. P4 runs after commit B, and its `--check` and AC-15 parts run again after commit C. **Independent:** none. Row 3 depends on row 1 being committed, and row 2 depends on the PR number. Commit C must not touch `vidbyte/__init__.py` or `pyproject.toml`, so it never forces a regeneration.

## §13 Test seams (facts for the test author — no tests here)

- **Framework:** pytest 8.3.5 (`pyproject.toml:78-81`: `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`); some older files use `unittest.TestCase`; `pytest-asyncio==1.3.0` is installed.
- **Layout and naming:**
  - A feature pack is `tests/features/<pack>/`. It holds a `FEATURE.md` (the agentic-engineering feature-test-pack format), an optional `README.md` with `## File Index` and `## Logs`, and files named `test_<pack>_<aspect>.py`.
  - Packs and `tests/features/` have no `__init__.py`; `tests/__init__.py` exists. Test basenames are unique across the tree today, and must stay unique.
  - Every new `.py` file needs the seven A001 header fields. A README with a File Index is checked by S020.
- **Prior art to copy:**
  - `tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py`, the closest pack: root `__all__` membership; identity with `getattr(vidbyte, n) is getattr(source, n)` and through `from vidbyte import …`; a fresh-interpreter probe `fresh_interpreter()` with `PYTHONPATH=REPO_ROOT`; star import; misspelled-name errors; contract JSON plus the version check.
  - `tests/features/public_skill_loader/test_public_skill_loader_contract.py`: the `FEATURE_MISSING` try/except-`ImportError` guard with an autouse fixture that re-raises it, so tests written before the code collect and fail at setup; `root.__all__.count(name) == 1`; identity against the defining module; `OTHER_EXPORTERS` ("exported nowhere else new").
  - **Do not copy for this feature:** `tests/features/harness_threads/test_harness_threads_surface.py`'s `optional_merge_base()` and `literal_all(git show <base>:vidbyte/__init__.py)`. Those helpers compare against `main`, and such a test is the failure mode that NG-13 forbids: it is the reason `test_import_vidbyte_starts_no_process…` goes red locally on any branch that changes root exports.
- **What no test may do** (NG-13, §6.1 intro): compare against `base_commit`, `origin/main` or the merge base; pin an export count (664, 668), a module count or hash, or a version literal (`0.4.0`); or read a file's git history. Every such fact is in §6.1.b and is proven once by the implementer. The reason is in the field guide `local-ci-verification.md`: "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself", and "Two `harness_threads` surface tests fail locally on any branch that touches … root exports".
- **Fixtures / factories:** none shared. The packs use module-level helpers, `importlib`, `subprocess` probes, and `monkeypatch`. No conftest is needed for import-only checks.
- **Real seams (do not mock):**
  - Import the real root package and the real defining modules.
  - Run import-time checks (`sys.modules` contents, star import) in a fresh interpreter, because the test process has usually imported `vidbyte.harnesses.native` already.
  - `JevAgentSettings`, `JevRuntimeSettings`, `JevComputeSettings` and `JevAgent` construct offline with no key in the environment (verified), so the §4 snippet runs as a test with no network.
  - `scripts/generate-sdk-public-api.py --check` is static and git-backed, and can run as a subprocess.
- **Facts the tests may rely on:**
  - All four defining modules are in `sys.modules` after a plain `import vidbyte`, and `vidbyte.harnesses.native` is not (INV-5). The module count and hash are a one-off probe for the implementer only (INV-16, AC-14), never a test value.
  - On `base_commit`, all four names are absent from the root. That is context, not something to assert.
  - Which name lives at which existing path: the positive pairings in the INV-2 table. A name × path cross-product test cannot pass (for example, `vidbyte.lib.config` has no `PermissionPolicy`). Neither can a sweep of `sys.modules` attributes, because many modules import these classes for their own use (`vidbyte.agents.jev.settings` holds all four). Assert presence at the table's paths, never absence elsewhere. INV-13 names the source lines behind each cell.
  - `JevComputeRegistry.validate` reorders `dynamic_compute` into tie-break order and accepts strings.
  - `PermissionPolicy.__post_init__` converts string members and rejects a single string with `ValueError`.
  - `JevAgentSettings` rejects a string `model_mode` with `ConfigurationError`.
- **The contract JSON in pytest: two precedents conflict.**
  - `public_skill_loader` deliberately does not read it (`FEATURE.md:95`), because such a test is red between commit A and commit B.
  - `root_native_thread_exports` (`test_root_native_thread_exports_contract.py:139-142`) and `infinite_memory_agent` (`test_infinite_memory_contract.py:166-169`) do read it. Both check membership as a superset (`names <= set(contract["exports"])`), never a count. The first also checks `contract["version"] == project_version == vidbyte.__version__`, an equality and never a literal. A test that reads it here follows that form (INV-4, AC-4).
  - Either choice is green at the PR head. C016 and `--check` already enforce freshness.
- **Inherited red, which tests must neither depend on nor fix:**
  - The 3 tests in `root_native_thread_exports` (NG-1).
  - `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.
  - `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`, red locally once root `__all__` changes; CI skips it.
  - Any test that edits `vidbyte/tools/**` turns `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` red.
- **`docs/` is off limits to tests:** `test_public_skill_loader_docs.py` WHAT NOT TO DO 2 says "Do not read anything under docs/", per the AGENTS.md opacity rule. The release note is proven by the implementer's diff (AC-15), not by a test. The root header is under `vidbyte/` and may be read. That docs test's `part()` helper and `PART_BREAK` regex (`:24-41`) show how a header bullet is isolated.
- **Per-area config:** none. The root `pyproject.toml` pytest settings apply.
- **Run one file:** `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/<pack>/<file>.py` · **Run all:** `PYTHONPATH=$(pwd) py -3.11 -m pytest` (the source stage of `scripts/run_ci.py` runs the same suite after lint)

## §14 Agent boundaries
- **Always:**
  - Work only inside `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports`.
  - Use `py -3.11`, with `PYTHONPATH=$(pwd)` inline for source-side commands, and `PYTHONDONTWRITEBYTECODE=1`.
  - Commit the source (commit A) before running the generator, then commit the contract alone (commit B).
  - Make the release-note edits (row 2) as commit C, alone, only after the draft PR exists. S3 opens the draft PR in its Phase 6. Right after `gh pr create`, S3 reads the number with `gh pr view feat/jev-cli-root-exports --json number -q .number`, applies row 2 alone as commit C, reruns `--check` (expecting `current at <commit A>`) and the AC-15 diff, and pushes. Row 2 is pending only if `gh pr create` itself fails. S3 then reports it as pending, which is not BLOCKED (§12.6 P3).
  - Measure every one-time proof against `MB=$(git merge-base origin/main HEAD)`, never against a fixed SHA (§6.1).
  - Prove each one-time fact in §6.2's second table with the named command, and paste its output.
  - Run the new tests, `lint/run.py --rule S015`, `--rule C016`, and ruff I001 after each phase.
  - Run both gate stages before reporting done, and quote the final lines.
  - Cite spec IDs in commit messages.
- **Ask first (stop and report BLOCKED):**
  - Modifying any test file, including the test author's new files and the inherited red tests.
  - Touching any file outside §12.3.
  - Exceeding the §8.4 budget.
  - Adding any root name beyond the four.
  - Changing a definition, a default, or a sub-package `__all__`.
  - A lint rule that reports REGRESSED for a reason this spec does not name.
  - The generator writing anything other than the 4-line addition plus a new `source.commit`.
  - ~~The PR number still being unknown when row 2 is applied (A-1).~~ (withdrawn r2, R-2: row 2 waits for the PR and is reported pending, §12.6 P3)
- **Never:**
  - Hand-edit `contracts/sdk-public-api.json`.
  - Edit anything under `vidbyte/tools/**` or `vidbyte/lib/configs/**`.
  - Change a version literal.
  - Guess a PR number, or commit a placeholder such as `#<n>`.
  - Write a test that compares against `base_commit` or the merge base, or that pins an export count, a module hash, or a version literal (NG-13).
  - Add the 11 native browser names.
  - Read or edit any `docs/` file except `docs/design/release-0-4-0.md` and this spec folder.
  - Run `pip install -e` from the worktree.
  - Delete, skip, xfail, or weaken a test, or raise a number in `lint/baseline.json`, or add a suppression.
  - Commit secrets or bytecode.
  - Push to `main`, tag, or publish.

## §15 Assumptions and open questions
**Assumptions** (stand unless the user corrects them):
- **A-1** — S3 opens the draft PR for `feat/jev-cli-root-exports` in its Phase 6, after commit B.
  - Right after `gh pr create`, S3 reads the number with `gh pr view feat/jev-cli-root-exports --json number -q .number` and applies row 2 alone as commit C, with that number for `#<n>` (§12.6 P3).
  - S3 then reruns `--check`, expecting `current at <commit A>`, and the AC-15 diff, and pushes.
  - Commit C changes no generator input, so `source.commit` stays commit A (INV-15).
  - Row 2 is pending only if `gh pr create` itself fails.

  — *If wrong:* if `gh pr create` fails, S3 reports row 2 as pending, not BLOCKED. The orchestrator then applies commit C as soon as the PR exists, before the S4 review. A placeholder is never committed (INV-17, §14 Never).
- **A-2** — After R1, every field type in the agreed flag map (request.md §C.0) is a root name or accepts a string. That covers `provider`, `api_keys`, `preflight`, `checks`, `gate` and `dynamic_compute`, and `ToolPermission` is already a root name. So the CLI's C2 and C4 can build every setting without a further SDK export. One closed vocabulary in the flag map stays non-root: `ModelProvider`, behind `JevAgentSettings.provider: ModelProvider | str` (`vidbyte/agents/jev/settings.py:137`), used by `--provider` and `--brief-provider`. The CLI's `click.Choice` parity check for providers can still go through root names: `JevAgentSettings(provider=<value>, …)` accepts every member and rejects anything else with `ConfigurationError: Unsupported model provider: '<value>'` (verified). — *If wrong:* a follow-up SDK PR adds the missing name (Q-3 for `ModelProvider`). This PR does not grow (NG-2).
- **A-3** — Merging R1 does not make the names installable from PyPI. Publishing 0.4.0 is a separate release step after R1 merges. The release note's precondition, SDK #1184, merged as `513aa614` on 2026-10-19. The CLI tests against a locally built 0.4.0 wheel until 0.4.0 is published. — *If wrong:* nothing in this PR changes; only the CLI's verification route does.
- **A-4** — No other PR adds root exports to `main` before this one merges. — *If wrong:* merge `main`, rerun the generator in a new commit, and recompute the counts in row 2 (c) (EC-7).
- **A-5** — D-P2 is right that "updates the version" means "ship in the unreleased 0.4.0", not "bump the number". The briefing records this as the user-approved program decision, and the spec author agrees: a bump would leave 0.4.0, which already carries #1027's breaking changes, unpublished in favor of a number no release note describes. — *If wrong:* a user reply changes D-7, which then touches the nine places of INV-8 and the release note.
- **A-6** — `py -3.11 scripts/run_ci.py --stage package` passes on `base_commit`. It was not run at S1. It builds a wheel and installs it, with its dependencies, into a fresh virtual environment. — *If wrong:* the implementer proves the same failure on a clean `origin/main` worktree and names it as inherited. This PR adds no package asset, so it cannot cause a package-stage failure of its own.

**Open questions** (max 5 blocking):
| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | Root-export the 11 native browser names from #1183 (`BrowserThreadResult`, `BrowserToolCall`, `{run,continue,fork}_{grok,opencode,muse}_with_browser`), lazily through `_LAZY_NATIVE_THREAD_EXPORTS`, to turn `root_native_thread_exports` green? | non-blocking | **No**: not built here; it is a separate PR for the orchestrator to schedule |
| Q-2 | Add "also exported from the root" to the headers of `loop.py`, `security.py`, `text_model.py` and `jev.py`? | non-blocking | **No** (D-9) |
| Q-3 | Root-export `ModelProvider` in a later SDK PR, so the CLI's provider `click.Choice` mirror can be parity-checked against the enum itself (R-4)? | non-blocking | **No**: not built here, and `ModelProvider` is not added by this PR. The CLI validates providers through `JevAgentSettings(provider=…)` (A-2) until the orchestrator schedules such a PR |

## §16 Review log
| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| 1 | R-1 | Blocker | §6.1, §6.2, §13 | Facts true only at this commit (diff against base, 668, 948/hash, version literals, provenance) were written as testable invariants, so permanent tests would go red after merge | accepted | §6.1 split into 6.1.a (permanent, tested: INV-1, 2, 4, 5, 7, 9, 10 to 13) and 6.1.b (one-time, implementer-proven: INV-3, 6, 8, 14, and new INV-15, 16, 17). INV-4 is now a superset plus version equality. §6.2 split into "Tested" and "Proven once by the implementer"; AC-5, 6, 9, 12 moved there, new AC-13, 14, 15 added. NG-13, §13 "What no test may do", and a §14 Never line forbid such tests; §13 drops the 948/hash/1,343 facts |
| 1 | R-2 | Major | §12.6, A-1, D-8, §14, §12.3 row 2 | Row 2 needed the PR number inside commit A, before the PR exists | accepted | Three commits: A (row 1), B (contract), then the draft PR, then C (row 2, number from `gh pr view`). Commit C changes no generator input (`lint/core/public_api_contract.py:431`), so INV-15 holds. Updated TL;DR, D-8, row 2 (Phase P3), §12.4, §12.5, §12.6 (P3 commit C, P4 verify), §14, A-1; the "Ask first" PR-number line is struck; no PR at P2 end means "pending", not BLOCKED |
| 1 | R-3 | Major | §6.1 INV-2, INV-13 | The export-path list did not say which name lives where, and `vidbyte.lib.config` has no `PermissionPolicy` | accepted | INV-2 is now a four-row name → path table, re-verified on `base_commit`, with the non-pairings and the two defining modules that lack an `__all__` entry named. INV-13 and §13 point at the table |
| 1 | R-4 | Minor (scope-adding) | §1, NG-2, A-2 | The parity-test argument for `JevDynamicComputeOption` applies equally to `ModelProvider` | accepted as text fixes; scope not added | §1 and §8.3 rest `JevDynamicComputeOption` on request.md §C naming it. NG-2 and A-2 name `ModelProvider` as the one closed vocabulary left non-root, with the root-only check `JevAgentSettings(provider=…)` (verified error text). New optional Q-3, default No, not built; named in §12.5 follow-ups. `ModelProvider` is not added |
| 1 | R-5 | Minor | §6.2, §6.3 | AC-8, AC-10 and 11 process EC rows were ceremony | accepted | AC-8 marked implied by INV-2 + INV-6, at most one smoke test; AC-10 points to the existing misspelled-name test; AC-9 moved to the implementer table; EC-8 to EC-12 and EC-16 to EC-21 struck through as withdrawn, their content kept in §12.4, §12.6 and §14 |
| 1 | R-6 | Minor | §11, D-9 | The spec told the implementer to copy #1099 without saying why it departs from #1099's header and README edits | accepted | D-9 cites #1099's ROLE and README edits as the runner-up's precedent, and gives the difference: those texts listed consumers as if complete; these four headers already omit most re-exporters (`security.py:12` omits `vidbyte.lib.dataclasses`, which imports it at `vidbyte/lib/dataclasses/__init__.py:201`). Q-2 default stays No |
| 1 | VC-1 | note | §12.3 row 1, §12.4 | "Computed `__all__` fails closed" cited the wrong source | accepted | The citation is now S015's `_exports` (`s015_public_export_integrity.py:48-53`), which reads only the first literal list; the deriver accepts `+`, `+=`, `.extend` and `.append` (`public_api_contract.py:5`). The obligation is unchanged |
| 1 | VC-2 | note | §10 T-1 | T-1 overstated `PermissionCeiling` as a control | accepted | T-1 now says the ceiling defaults to `None` (`vidbyte/lib/permission_ceiling.py:27`) and caps nothing unless a scope opens it, and that `allow_all()` was already reachable via `vidbyte.tools.security`, so the security posture is unchanged |
| 2 | R-1 | Major | §6.1.b, §6.2 AC-5/6/9/14/15, NFR-3, §12.6 P4 | `origin/main` moved to `0cce5781` (#1184, #1188; 51 files), so one-time diffs against the fixed `b7350ed6` fail once P4 merges `main` | accepted | Every one-time proof now uses `MB=$(git merge-base origin/main HEAD)`. AC-5, 6, 9 and 15 and NFR-3 diff against `$MB`, and AC-14 archives `$MB`. INV-3, 6, 8 and 16 read "against the merge base (`b7350ed6` at S1)". The variable is named `MB`, not `B`, because "commit B" already names the contract commit. I added the optional line to P4 and re-verified it at r3: the gated-path diff is empty, the version literals are unchanged, and `0cce5781` loads the same 948 modules with the same hash. Merging `main` is optional for correctness |
| 2 | R-2 | Major | §6.1.b INV-15, §6.2 AC-13, §6.3 EC-6 | After a commit that changes only non-export root text, the generator keeps `source.commit` = A (`generate-sdk-public-api.py:65-67`), so AC-13's empty-diff clause could never pass | accepted | INV-15 and AC-13 now state the repo's provenance rule. `--check` exits 0 and reports `current at <source.commit>`, `source.commit` is on the branch (`git merge-base --is-ancestor`), and `git show <source.commit>:vidbyte/__init__.py` lists the four. "Identical to the head's" and the empty-diff clause are dropped. EC-6 is reworded per the fix |
| 2 | R-3 | Major | §6.1.a INV-2, INV-11, §13 | INV-2's "at no other place" is false for attributes (8 to 19 modules hold each object), and INV-11's "unchanged" sentence is a diff fact that Q-1 would turn red | accepted | INV-2 now says no other module lists the names in `__all__` today, marked as context and not a test, with no attribute sweep and no absence assertion. The "unchanged" sentence moved from INV-11 to INV-6 (6.1.b), and AC-5 proves it (9 added lines, 0 removed). §13 now says "the positive pairings" |
| 2 | R-4 | Minor | §12.6 P3, §14 Always, A-1 | Commit C was routed to "the agent that opens the draft PR", with "pending" as the expected outcome, but S3 itself opens the PR in its Phase 6 | accepted | P3, §14 Always and A-1 now say: S3 opens the draft PR in Phase 6, reads the number right after `gh pr create`, applies row 2 alone as commit C, reruns `--check` and AC-15, and pushes. Row 2 is pending only if `gh pr create` fails |
| 2 | SF-1 | note | NG-4, §9.4, A-3, §11, INV-4, §13 | Stale facts: #1184 has merged; `0e7a8eb0` is this branch's first commit, not part of `origin/main`; the native contract check is at `:139-142` | accepted | NG-4, §9.4 and A-3 now say #1184 merged as `513aa614` (2026-10-19) and that publishing is a separate release step. The §11 baseline names `0e7a8eb0` as the branch's first commit. Both citations now read `:139-142` |
| 2 | SF-2 | note (coordinator) | §12.5, NG-4 | The release note's "Do not tag until the Meta key fix, #1184, is on `main` …" sentence (line 19) is stale since `513aa614`; on `main`, META accepts `("LLM|", "LLM_")` | accepted as a follow-up only | One §12.5 bullet and one item in the S6 PR-body follow-ups record it, verified on `0cce5781`. Row 2's edits are unchanged, and the sentence is left for the release PR |

## §17 Revision history
| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-19 | S1 spec | Initial spec |
| r2 | 2026-10-19 | S1 spec (review round 1) | Applied R-1 to R-6 and two verified-claim notes: permanent vs one-time facts split in §6.1/§6.2 (new INV-15 to INV-17, AC-13 to AC-15, NG-13); three commits with the release note last (D-8, §12.6); INV-2 name → path table; `ModelProvider` recorded as optional Q-3, not built; process ECs withdrawn; D-9 precedent; T-1 and the S015 citation corrected. Version unchanged (D-P2) |
| r3 | 2026-10-19 | S1 spec (review round 2, final) | Applied R-1 to R-4 and the stale-fact notes. One-time proofs are measured against `MB=$(git merge-base origin/main HEAD)`, and main's 0cce5781 delta was re-verified as touching no gated path. INV-15 and AC-13 follow the generator's provenance rule. INV-2 has no absence claim, and the lazy-block sentence moved from INV-11 to INV-6. S3 makes commit C right after `gh pr create`. #1184 is recorded as merged. A follow-up records the release note's stale "#1184 gate" sentence. Status: approved. Scope and version unchanged |
| r3.1 | 2026-10-19 | S2 note (not a review round) | r3.1 — INV-7 wording per S2 note: the existing members of `TextModelMode` and `JevDynamicComputeOption` keep their values and relative order, and a later PR may add members (AGENTS.md treats a new compute option as a normal change). The rest of INV-7 is unchanged. Status: tests-written (S2 baseline dc5108e6) |
