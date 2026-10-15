---
slug: harness-thread-functions
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 (local)
flags: none
---

# Request: reshape PR #1036 into harness thread functions (`run_grok_thread`, `fork_grok_thread`, `run_opencode_thread`, …) that run each harness's own CLI with the caller's API key, and resolve the owner's four review comments

This run updates an existing pull request in place: https://github.com/cerredz/Vidbyte-SDK/pull/1036, branch `feat/native-grok-opencode-meta-hosts`. The PR was built by an earlier pipeline run (slug `native-grok-opencode-meta-hosts`). The repository owner (GitHub login `cerredz`) reviewed it, found that it does not match what they wanted, and asked for it to be reshaped.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening message):

````text
for pr #1036, why do we having billing and usage functions, how are they used (vidbyte-sdk): look at this file: vidbyte/harnesses/native/backends/profiles.py
````

**Prompt 2**:

````text
dont the api keys just connect to the user's subscription usage, like  why do we even need usage or  balance checks inside of the pr?
````

**Prompt 3**:

````text
there seems to be some disconnect with the pr and what I wanted the pr to do. i wanted the pr to simply do the following: the user providers their api key, and then we simply  create functions that run the already existing cli/sdk code of open  source harensses (ex: run_grok_thread(api key, skills, prompt, config), run_opencode_thread(params), fork_grok_thread(grok_thread_id), then even complex functions like run_grok_thread_verify_with_opencode(params) etc (dont worry about the complex functions for now). And then each function has the parameters needed for the function and then the api key that the user is providing. Does the pr do this right now?
````

**Prompt 4** (the `/spec-pipeline` invocation; its whole argument string):

````text
I dont literally want the things that I said, but I want you to figure out the general shape of what I said and how to implement optimally (only thing I definately want is the actual function naming the way i said). Can you figure this out,  update the pr, and also resolve the comments that I left
````

**The four review comments the owner left on PR #1036** (all on commit c1fdaef9, all by `cerredz`, 2026-10-15). "Resolve the comments that I left" in Prompt 4 refers to these. Verbatim, with the code each one is anchored to:

1. Comment 4280069037 on `vidbyte/harnesses/native/backends/profiles.py` line 59. The anchored hunk is the block of module-level constants at lines 45–59: `_CLAUDE_MODEL_SLOTS`, `_BASE_URL_VARIABLE`, `_KEY_REJECTED_STEP = "DeepSeek rejected {variable}; set a valid key."`, `_BODY_FIELD = "body"`, `_ERROR_HARNESS = NativeHarness.CLAUDE_CODE`.
   ````text
   wrong file location for all of these, and error messages need to be in much more detail
   ````
2. Comment 4280082885 on `vidbyte/harnesses/native/grok/cli.py` line 36. The anchored hunk is the block of module-level constants at lines 32–42: `_PROGRAM = "grok"`, `_HOME_FOLDERS = (".grok", "bin")`, `_WINDOWS_SUFFIX = ".exe"`, `_BATCH_SUFFIXES = (".cmd", ".bat")`, `_WINDOWS_DROPPED_TAIL = ". "`, `_PEER_PREFIX = ("agent", "--no-leader")`, `_PEER_SUFFIX = ("stdio",)`, `_VERSION_ARGS = ("--version",)`, `_MODELS_ARGS = ("models",)`, `_JSON_OUTPUT = "--output-format=json"`, `_FORK_FLAG = "--fork-session"`.
   ````text
   wrong file location,
   ````
3. Comment 4280090901 on `vidbyte/harnesses/native/grok/cli.py` line 127. The anchored code is `GrokCli._run_flags`, which builds argv with inline string literals: `"--permission-mode=" + …`, `"--cwd=" + …`, `"--allow=" + rule …`, `"--deny=" + rule …`, `"--max-turns=" + …`, `"--model=" + …`, `"--reasoning-effort=" + …`.
   ````text
   feel like this type of code can be cleaner for all providers. Feel like we can define enums for flags/hardcoded strings,  
   ````
4. Comment 4280092326 on `vidbyte/harnesses/native/grok/host.py` line 64. The anchored hunk is the block of module-level constants at lines 55–64: `_ENTER = "__aenter__"`, `_EXIT = "__aexit__"`, `_CONSTRUCT = "GrokHost"`, `_ONE_PAGE = 1`, and four next-step strings such as `_READY_CAPABILITY_NEXT_STEP = "Update Grok Build with grok update; this SDK needs ACP session/list and session/resume."`.
   ````text
   wrong file location
   ````

## B. Handoff block and decision ledger (verbatim, if present)

None in this conversation. The earlier run's request (`docs/spec/native-grok-opencode-meta-hosts/request.md`) holds the original prompts and a decision ledger from an upstream "CodexHost and ClaudeHost" design. That ledger is **superseded** for this PR wherever it conflicts with §A above (for example its "one host class per harness, spawn returns a handle" and "one tool per function" decisions). The original two prompts of the earlier run are quoted in §C "Background" because they still define which harnesses are in scope.

## C. Structured conversation notes

### Background: the earlier run's two prompts (verbatim, from docs/spec/native-grok-opencode-meta-hosts/request.md §A)

````text
Can you view our "herdr-claude 2" claude code sessionsannd view the "CodexHost and ClaudeHost" session, understand what we are talking about implementing in the vidbyte-sdk/, and then come up with a list of 1) other native harnesses to integrate this with (grok, glm, deepseek, meta, opencode, etc), and then 2) an in-depth function list of every function that we can implement with these native harnesses
````

````text
great, can you focus on implementing grok, glm, deepseek, meta, and opencode harnesses for now. Make sure to extensively handle errors for every single function.
````

The earlier run turned the "in-depth function list" into a catalog of about 480 functions, read "great" as accepting the catalog's ★ subset, and built that subset. Prompt 3 above says the result is not what the owner wanted.

### What the conversation established about the PR as it stands (facts checked against branch head c1fdaef9)

- **Public shape today:** three host classes used as async context managers, with handles. `GrokHost(settings)` has 10 methods (`check_grok_ready`, `list_grok_models`, `spawn_grok_session`, `run_grok_once`, `continue_grok_session`, `fork_grok_session`, `list_grok_sessions`, `search_grok_sessions`, `wait_grok_turn`, `interrupt_grok_turn`) plus a module function `run_grok_once(request, *, settings)`. `OpencodeHost(settings)` has 18 (`check_opencode_ready`, `list_opencode_models`, `list_opencode_providers`, `get_opencode_provider_auth`, `spawn_opencode_session`, `continue_opencode_session`, `fork_opencode_session`, `revert_opencode_session`, `unrevert_opencode_session`, `list_opencode_sessions`, `get_opencode_session`, `get_opencode_session_messages`, `get_opencode_message`, `get_opencode_session_diff`, `wait_opencode_turn`, `interrupt_opencode_turn`, `track_opencode_session_usage`, `add_opencode_mcp_server`). `MuseHost(settings)` has 12 (`check_muse_ready`, `list_muse_models`, `spawn_muse_session`, `continue_muse_session`, `fork_muse_session`, `list_muse_sessions`, `read_muse_session`, `page_muse_session`, `steer_muse_turn`, `interrupt_muse_turn`, `wait_muse_turn`, `track_muse_session_usage`). A turn is `spawn_*` (returns a handle at once) then `wait_*_turn(handle)`.
- **Backends:** `vidbyte/harnesses/native/backends/profiles.py` has six functions over two profiles (GLM via Z.ai, DeepSeek): `list_harness_backends`, `build_claude_backend_env`, `check_backend_ready`, `check_backend_compat`, `get_deepseek_balance`, `build_opencode_backend_provider`. `build_claude_backend_env` has no consumer (ClaudeHost is not on main; it is open PR #1044). `check_backend_ready` and `get_deepseek_balance` are called only by three agent tools; no host calls them. `OpencodeHostSettings.backends` copies `GLM_API_KEY` into `ZHIPU_API_KEY` (opencode's built-in `zai-coding-plan` provider) and passes `DEEPSEEK_API_KEY` (built-in `deepseek` provider) into an owned `opencode serve`.
- **No function takes an API key.** Keys come from the machine (old spec D-18, "as if run in the user's terminal"): Grok uses whatever `grok` login the machine has (the code never reads a key); opencode uses its own `auth.json` or the backend env copies above; Muse forwards `META_API_KEY` into WSL when the variable is set. Every vendor child gets `NativeChildEnvironment.build(overlay)` = `{**os.environ, **overlay}` (`vidbyte/harnesses/native/hostkit/peers.py:39`), so a per-call key could travel in the overlay. `NativeErrorFactory.register_secret` redacts any injected secret from error text.
- **No `skills` parameter exists anywhere** in the PR.
- **"config" today:** settings records hold workspace, CLI path, timeouts and live-turn caps; requests hold prompt, model, reasoning effort (Grok one-shot also permission mode, allow/deny rules, max turns; opencode also agent, system prompt, permission rules, title). No harness-native config passthrough.
- **Permission defaults:** the PR answers "no" to every approval request (Grok `allowed_tool_kinds=frozenset()` → `reject_once`; opencode answers every permission and question `reject`; Muse sessions start `approvalMode: denyUnmatched`, every approval `denied`). Whether that blocks ordinary edits depends on each CLI's own defaults, which were not verified.
- **Size:** about 11.7K lines of SDK code and 14K lines of tests; 43 agent tools in 4 toolsets (`GrokTools`, `OpencodeTools`, `MuseTools`, `HarnessBackendTools`); 53 `<host>.<problem>` `FailureCode` members; a `vidbyte.lib.process` package (`CliRunner`, `ManagedProcess`, `ProcessStopper`); an opt-in extension of `McpStdioTransport`; 26 spec docs under `docs/spec/native-grok-opencode-meta-hosts/`.
- **The DeepSeek balance read** exists only because the old catalog listed `check_backend_ready` ("key present plus a one-token test call") and `get_deepseek_balance` as ★, and old spec D-17 swapped the test call for the free `GET /user/balance`. `backend.billing_error` / `backend.usage_limited` are raised only by that balance call (402 / 429), never by a model call. A real turn's 402/429 already surfaces as `opencode.billing_error` / `opencode.usage_limited`.
- **Billing models:** the GLM key is a Coding Plan subscription (quota windows; Z.ai's quota endpoint is undocumented); the DeepSeek key draws a prepaid balance (402 when empty). Both are the user's own accounts (BYOK).

### Key decisions
- **KD-1 Function naming is the one literal requirement.** The owner: "only thing I definately want is the actual function naming the way i said". The names said were `run_grok_thread`, `run_opencode_thread`, `fork_grok_thread`, and (later, not now) `run_grok_thread_verify_with_opencode`. The pattern is `<verb>_<harness>_thread`: a module-level function, verb first, the harness's name, the word `thread` (the owner's word for one conversation with a harness, which the vendor APIs and the current code call a "session"). Every public operation this PR keeps follows that pattern for every harness it keeps.
- **KD-2 The caller supplies the API key to each function.** "the user providers their api key, and then we simply create functions…"; "each function has the parameters needed for the function and then the api key that the user is providing". A function does not depend on a key the machine happens to hold. How the key is passed (a parameter, or a field of the validated input record that AGENTS.md principle 4 asks for) is a design choice for the spec; that a key is supplied by the caller per call is the shape.
- **KD-3 The functions run the harnesses' own existing CLI/SDK code.** "create functions that run the already existing cli/sdk code of open source harensses". The SDK drives the vendor program; it never reimplements an agent loop.
- **KD-4 The literal parameter lists are illustrative, not binding.** "I dont literally want the things that I said, but I want you to figure out the general shape of what I said and how to implement optimally". The examples named an api key, skills, a prompt and a config for `run_grok_thread`, and a thread id for `fork_grok_thread`. The spec decides each function's optimal parameters.
- **KD-5 Composite cross-harness functions are out of scope for now.** "then even complex functions like run_grok_thread_verify_with_opencode(params) etc (dont worry about the complex functions for now)".
- **KD-6 Update PR #1036 in place.** "update the pr": same branch `feat/native-grok-opencode-meta-hosts`, same PR number.
- **KD-7 Resolve the four review comments (§A).** Their content generalizes across the PR ("for all of these", "for all providers"): module-level constants and hardcoded strings do not live in feature files; flags and hardcoded strings become enums; argv building is cleaner and shared across providers; error messages carry much more detail. Each comment thread gets a reply naming the fixing commit.
- **KD-8 Error handling stays thorough.** From the earlier request: "Make sure to extensively handle errors for every single function." Comment 1 adds: "error messages need to be in much more detail".
- **KD-9 Harnesses in scope** come from the earlier request: "grok, glm, deepseek, meta, and opencode". In the current code Grok (Grok Build CLI), opencode and Meta (Muse Code, CLI `muse`) are harnesses with their own programs; GLM and DeepSeek are model providers that a harness is pointed at, not programs of their own.

### Rejected alternatives
- **Keep the PR's current shape** (host classes, spawn/wait handles, 43 tools, readiness/balance/usage/list/search/revert functions): Prompt 3, "there seems to be some disconnect with the pr and what I wanted the pr to do. i wanted the pr to simply do the following".
- **Keys only from the machine's login or environment** (old D-18): conflicts with "the user providers their api key".
- **Copying the example signatures literally**: Prompt 4, "I dont literally want the things that I said".
- **Usage and balance checks as part of the shape**: Prompt 2, "why do we even need usage or balance checks inside of the pr?" (the conversation established nothing calls them and a real turn already reports billing failures).

### Constraints and assumptions
- AGENTS.md binds: dataclasses in `vidbyte/lib/dataclasses/<domain>.py`; enums in `vidbyte/lib/enums/<domain>.py`, exported from `vidbyte/lib/enums/__init__.py`; constants in `vidbyte/lib/constants/<domain>.py`; `vidbyte/lib/` never imports a higher layer; call chains one level deep; narrated main functions; validated frozen dataclasses for core inputs and outputs; files well under 1,000 lines; canonical helpers in `vidbyte/lib/` for shared logic; full local gate `python scripts/run_ci.py` before calling work complete; `docs/` is opaque except named files.
- There is no CLI in the SDK; never add one.
- Scope is the conversation: build what §A–§C ask for plus what a repo rule or gate forces. A risk with no requested control becomes a stated limitation or an optional question (default: not built).
- PR #1044 (ClaudeHost) and PR #1055 (CodexHost) are open, not on main. Do not depend on or edit them.
- The branch was brought up to date with `origin/main` (179d8adc) by a merge commit at S0 (see pipeline.md); later catch-ups are merges, never rebases or force-pushes.
- SDK GitHub Actions auto-triggers are disabled: PR checks appear only after `gh workflow run ci.yml --ref feat/native-grok-opencode-meta-hosts` (and `static-policy.yml`), and results are read through the check-runs API, not `gh pr checks`.

### Clarifications and answers
- Q (assistant, end of the Prompt 3 answer): does the PR do this? A (assistant's finding): no — no function takes an API key or skills; the shape is classes plus handles; it builds much more than asked. The owner then answered with Prompt 4.
- Q (assistant): should GLM and DeepSeek become arguments of `run_opencode_thread` (for example a provider choice with the caller's key) instead of standalone profiles? Not answered; open (see below).
- Q (assistant): how should skills reach each CLI (copy into the workspace's skill folder, a CLI flag, or a config option)? Not answered; open.

### Terminology
- **thread** — one conversation with a harness, which can receive a prompt, be continued, and be forked. Vendor APIs and the current code call it a "session"; public names use "thread" (KD-1).
- **harness** — a vendor coding-agent program the SDK drives: Grok Build (`grok`), opencode (`opencode`), Muse Code (`muse`, Meta's).
- **provider / backend** — a model endpoint a harness is pointed at: GLM through Z.ai, DeepSeek.
- **API key** — the caller's own vendor key, supplied per call (KD-2).
- **skills** — harness skills: folders with a `SKILL.md` that a harness discovers and loads. Each harness has its own discovery rule (not yet researched).

### Implementation hints
- Existing code to reuse or trim (all on the branch): `vidbyte/harnesses/native/{grok,opencode,muse,hostkit,backends}/`; `vidbyte/lib/process/` (`CliRunner`, `ManagedProcess`, `ProcessStopper`); the `McpStdioTransport` extension; dataclasses in `vidbyte/lib/dataclasses/{grok,opencode,muse,native_hosts,harness_backends,process}.py`; enums in `vidbyte/lib/enums/{native_hosts,harness_backends,process}.py` and `FailureCode` in `vidbyte/lib/enums/failure.py`; constants in `vidbyte/lib/constants/native_hosts.py`; `NativeHostError` in `vidbyte/lib/errors/`; tools in `vidbyte/tools/builtins/{grok,opencode,muse,harness_backends}/` and toolsets `vidbyte/tools/toolsets/{grok,opencode,muse,harness_backends}.py`; tests in `tests/features/{grok_host,opencode_host,muse_host,native_backends}/` with fakes `fake_grok_peer.py`, `fake_opencode_serve.py`, `fake_muse_peer.py`.
- Vendor protocol research from the earlier run lives in `docs/spec/native-grok-opencode-meta-hosts/request.md` (ACP variants and error table, `opencode serve` endpoints, MSP 1.0.1 methods, auth: `META_API_KEY` or `muse login`; opencode built-in providers `zai-coding-plan` reading `ZHIPU_API_KEY` and `deepseek` reading `DEEPSEEK_API_KEY`; the GLM Coding Plan tool allowlist) and `.../spec.md` (§8.5 interfaces, §9 data, D-decisions, A-assumptions). These two files are named for reading; they describe the old design, so trust them for vendor facts, not for this run's shape.
- Field-guide entries likely to apply (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): `review-scope.md` (a PR that overengineers a feature should be much smaller), `cli-backed-source-integrations.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `comment-format.md`, `provider-api-contracts.md`, `blocking-lint-invariants.md` (adding a class to `vidbyte/lib/errors/base.py`), `prebuilt-agents.md` (no CLI in the SDK), `local-ci-verification.md`.

### Open questions (the spec resolves each from the code and vendor facts, or carries it as a Q-n with a default)
- How does each harness CLI accept a caller-supplied API key (which environment variable, config option, or flag), per harness and per provider? The PR's research never recorded one for `grok`.
- How does each harness accept skills, and what is the smallest honest way to pass caller skills into one thread?
- Which verbs make up the thread API for each harness (the owner named run and fork; the current code also has continue, interrupt, steer, revert, list, read)? Which survive under the KD-1 naming, and which go?
- The harness name for Meta in function names: `muse` (the CLI's and the current code's name, consistent with naming grok and opencode by their programs) or `meta`?
- Are the thread functions async, sync, or both?
- How are GLM and DeepSeek reached in the new shape (for example a provider choice on the opencode thread functions, with the caller's key)?
- What happens to code the new shape does not need: the 43 agent tools and 4 toolsets, the backend functions, readiness/usage/list/search/revert/diff/MCP functions, the `McpStdioTransport` extension, unused `FailureCode` members, and the old run's 26 docs under `docs/spec/native-grok-opencode-meta-hosts/`?
- What permission default makes a "run a thread" call useful and still safe, given that today every approval is refused?
- Where do the relocated constants, the flag enums and the shared argv builder live (comment 3: "cleaner for all providers")?

## D. Weighted words
- "simply" — Prompt 3: "i wanted the pr to simply do the following: the user providers their api key, and then we simply  create functions that run the already existing cli/sdk code of open  source harensses"
- "each" — Prompt 3: "And then each function has the parameters needed for the function and then the api key that the user is providing."
- "only … definately" — Prompt 4: "only thing I definately want is the actual function naming the way i said"
- "optimally" — Prompt 4: "figure out the general shape of what I said and how to implement optimally"
- "all of these", "much more detail" — Comment 1: "wrong file location for all of these, and error messages need to be in much more detail"
- "all providers" — Comment 3: "feel like this type of code can be cleaner for all providers. Feel like we can define enums for flags/hardcoded strings"
- "every single function" — earlier run, Prompt 2: "Make sure to extensively handle errors for every single function."
