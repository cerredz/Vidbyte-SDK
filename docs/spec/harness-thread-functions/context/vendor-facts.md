# Vendor facts: how grok, opencode and muse take a caller key, skills, per-run config, and thread operations

Written by the S0 vendor scout on 2026-10-15. Each answer is tagged **VERIFIED** (with the quoted evidence) or **UNVERIFIED** (with what was tried). No model was called. No login or credential file was opened, and no config was changed. One side effect: the first `muse --version` probe let Muse's launcher write its update-check timestamp (Muse Q1). Commands and URLs are in `../reports/S0-vendor-scout.md`.

## Grok Build

Sources: `grok --help` and subcommand `--help` on the installed 1.0.52, and the vendor's own user guide. Grok extracts that guide on launch to `~/.grok/docs/user-guide/NN-*.md`, cited below as `user-guide/<file>`; the same text is embedded in the binary. The public web copy was not fetched (see Gaps).

1. **Installed: VERIFIED.** `grok --version` prints `grok 1.0.52 (0920c8169e27) [stable]`. The path is `C:\Users\422mi\.grok\bin\grok.exe`, first on PATH. A second shim exists at `C:\Users\422mi\AppData\Roaming\npm\grok` / `grok.cmd` (not probed). `~/.grok` holds `config.toml`, `sessions/`, `skills/`, `docs/` and `trusted_folders.toml`. The directory listing shows `auth.json.lock` but **no `auth.json`** today (listed only, not opened), so this machine has no stored Grok login right now.

2. **API key: VERIFIED (env var and precedence), with a trap.**
   - Env var: `XAI_API_KEY`. user-guide/14-headless-mode.md, "Environment Variables for Headless": "`XAI_API_KEY` | API key for authentication (required when no browser login)". Legacy alias, from user-guide/11-custom-models.md "Credential Resolution": "The `XAI_API_KEY` environment variable (global fallback; Grok also accepts `GROK_CODE_XAI_API_KEY` for backward compatibility)".
   - **Trap: a stored login beats the env key.** user-guide/02-authentication.md "Auth Precedence": "1. **Per-model `api_key` or `env_key`** -- set under `[model.<name>]` in `config.toml`. Wins whenever present. 2. **Active session token** -- obtained through browser, OIDC/OAuth2, or external-provider login and stored in `~/.grok/auth.json`. 3. **`XAI_API_KEY`** -- fallback when no session token is active." The binary also carries this message: "You have an API key set (XAI_API_KEY). Your cached OAuth session is being used instead. To use your API key, run `grok logout`".
   - There is no `--api-key` flag. Neither `grok --help` nor `grok agent --help` lists one (VERIFIED by reading both).
   - Setting `auth.preferred_method = "api_key"` would force the key ("Pin automatic auth to one method with no fallthrough", user-guide/26-config-reference.md, `auth` table). But it is a config-file key, and the `GROK_CONFIG` overlay **cannot** set auth. user-guide/05-configuration.md: "The overlay is confined, fail-closed, to an **allowlist** of soft settings (`models`, `features`, a narrowed `toolset`, and a `shell_environment_policy` limited to its filter fields …); every other table is dropped at the choke point, so the overlay cannot spawn commands, set auth policy, redirect network traffic, elevate trust, or add a discovery source."
   - Per child only: Grok reads `XAI_API_KEY` from its process environment (precedence tier 2, "Environment variables"), so setting it in the child's environment alone writes no global state. Without editing user files, the only way to guarantee that the caller's key wins over a stored login is to also point **`GROK_HOME`** at a directory that has no `auth.json`. user-guide/14-headless-mode.md: "`GROK_HOME` | Override config directory (default: `~/.grok`)". The side effect, VERIFIED from the File Locations table in the same file: `GROK_HOME` also moves `config.toml`, `auth.json`, `sessions/`, `memory/`, `skills/`, plugins, logs and the folder-trust store. A thread created under one `GROK_HOME` can therefore be continued or forked only under the same `GROK_HOME`. Whether a fresh `GROK_HOME` also skips the `~/.claude/skills` scan is UNVERIFIED.

3. **Skills: VERIFIED (doc, plus one parse probe).**
   - user-guide/08-skills.md "Skill Locations" lists these folders: `./.grok/skills/` and `./.grok/commands/` (current directory, highest priority), `<repo_root>/.grok/skills/`, `~/.grok/skills/` (user), `~/.claude/skills/` and `./.claude/skills/` (Claude compatibility), `~/.cursor/skills/` and `./.cursor/skills/`. The same page adds: "Grok also scans `.agents/skills/` (and `commands/`) at each tier (alongside `.grok/`) and walks every directory between your working directory and the repo root."
   - Extra folders: `[skills] paths = [...]` in `~/.grok/config.toml`. The `GROK_CONFIG` overlay cannot set it (see the allowlist in Q2).
   - Format: a directory holding `SKILL.md` with YAML frontmatter. Core fields are `name` (lowercase letters, digits and hyphens, at most 64 characters; defaults to the directory name) and `description` (defaults to the first paragraph). Optional fields are `when-to-use`, `allowed-tools`, `argument-hint`, `user-invocable`, `disable-model-invocation`, `model`, `effort`, `license`, `compatibility` and `metadata`.
   - **Per-run injection without touching user files works through plugins.** user-guide/09-plugins.md says a plugin is a directory that can hold "**Skills**: a `skills/` directory of SKILL.md files", plus optional `commands/`, `agents/`, `hooks/hooks.json` and `.mcp.json`. Its locations table includes "`_meta.pluginDirs` (`session/new`, and `session/load` on the shell route) | Session, that session only | Trusted automatically" and "`--plugin-dir` (the `grok agent … stdio` flag) | Process, that agent process only | Trusted automatically". The same page says `--plugin-dir` is "repeatable (`grok agent --no-leader --plugin-dir A --plugin-dir B stdio`), and ignored in leader mode". `grok agent --help`: "--plugin-dir <DIR>  Load a plugin from this directory for this process only (repeatable). Highest-priority plugin scope; always trusted … Used by the Agent SDKs to inject per-connection plugins".
   - **Headless `grok -p` does NOT accept `--plugin-dir`** (VERIFIED: `grok --plugin-dir <dir> --version` prints `error: unexpected argument '--plugin-dir' found`). Per-run skills for a one-shot `grok -p` run therefore need project skill folders inside the workspace, or a private `GROK_HOME/skills/`.
   - Trust trap. user-guide/22-permissions-and-safety.md: "Folder trust gates project permission rules in `.grok/config.toml` and `.claude/settings.json`, plus startup loading of project instructions and skills. Headless startup with these sources requires `--trust` or a prior grant." Trust grants are stored in `~/.grok/trusted_folders.toml`. `--trust` is not in `grok --help` (it is a hidden flag). It was not probed, because it writes trust state.

4. **Per-run config: VERIFIED (doc).**
   - Overlay: `GROK_CONFIG` (inline JSON) or `GROK_CONFIG_PATH` (an extra JSON or TOML file), deep-merged above `config.toml` and limited to the allowlist quoted in Q2. Example from user-guide/05-configuration.md: `GROK_CONFIG='{"models": {"default_reasoning_effort": "high"}}' grok agent stdio`.
   - Headless settings are flags, all listed in `grok --help`:
     - model and reasoning: `-m/--model`, `--reasoning-effort`/`--effort` (levels `none, minimal, low, medium, high, xhigh, max`, per 14-headless-mode.md);
     - permissions: `--permission-mode`, `--always-approve` (alias `--yolo`), `--allow <RULE>`, `--deny <RULE>`;
     - run limits and workspace: `--max-turns <N>` (headless only), `--cwd <CWD>`;
     - prompt and agent: `--rules <RULES>`, `--system-prompt-override`, `--agent`, `--agents <JSON>`;
     - tools and sandbox: `--tools`, `--disallowed-tools`, `--no-subagents`, `--disable-web-search`, `--sandbox` (env `GROK_SANDBOX`).
   - Other environment variables: `GROK_MEMORY=0` turns off cross-session memory, and `GROK_DISABLE_AUTOUPDATER=1` turns off update checks ("The agent SDKs inject `GROK_DISABLE_AUTOUPDATER=1` for the non-leader agents they spawn").
   - ACP live options (user-guide/15-agent-mode.md, 09-plugins.md): `session/set_config_option` with `configId` `model` or `reasoning_effort`. The `session/new` `_meta` fields are `rules`, `systemPromptOverride`, `agentProfile`, `yoloMode`, `autoMode` and `pluginDirs`.

5. **Thread operations, headless: VERIFIED (help and doc; output shape from the doc, not from a live run).**
   - New thread: `grok -p "<prompt>" --output-format json [--cwd <dir>] [-m <model>] …`. The prompt can also come from `--prompt-file <path>` or `--prompt-json <json>`; "Headless mode does not read piped stdin into the prompt". The optional `-s/--session-id <uuid>` names the new thread ("must be a valid UUID and must not already exist under the target session directory").
   - Continue: `grok -p "<prompt>" --resume <session-id> --output-format json`. It "errors if the session does not exist". `-c/--continue` resumes the most recent session in the working directory.
   - Fork: `grok -p "<prompt>" --resume <session-id> --fork-session [--session-id <new-uuid>] --output-format json`. Help: "When resuming (`--resume` / `--continue`), create a new session ID instead of reusing the original (optionally set via `--session-id`)". Headless mode always needs a prompt, so a fork without a new prompt has no headless form. ACP has `x.ai/session/fork` (extension table in user-guide/15-agent-mode.md), but its params are UNVERIFIED. `--fork-session` is "Not combinable with" `--worktree`.
   - JSON output of `--output-format json` (user-guide/14-headless-mode.md) is one object: `{"text", "stopReason", "sessionId", "requestId", "cwd", "num_turns", "usage": {input_tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens, reasoning_tokens, total_tokens}, "modelUsage": {<model>: {inputTokens, outputTokens, cacheReadInputTokens, modelCalls, costUSD}}, "total_cost_usd", "total_cost_usd_ticks"}`.
     - `thought` is added when reasoning is present.
     - The flags `cost_is_partial` and `usage_is_incomplete` can appear.
     - Spend fields are left out when the prompt never reached the model, and "Cost is stamped for API-key traffic today".
     - A failure prints `{"type":"error","message":"Couldn't start session: ..."}` and exits non-zero, adding `cwd` once the session has started.
     - Exit codes: 0 success; 1 error ("Authentication failure, network error, or runtime error"); 130 SIGINT; 143 SIGTERM.
     - The earlier research recorded only `{text, stopReason, sessionId, requestId}` on 1.0.13. The 1.0.52 docs add the other fields.
   - ACP (live turns): `grok agent --no-leader [--plugin-dir D] [-m M] [--reasoning-effort E] [--always-approve] stdio`. Methods: `initialize`; `session/new` (`cwd`, `mcpServers`, `_meta`); `session/load`; `session/prompt`; `session/set_config_option`. Progress arrives as `session/update` with `agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update` and `plan`.

6. **Permissions: PARTLY VERIFIED.**
   - Modes, from user-guide/22-permissions-and-safety.md:
     - "`default` (**ask**) | Read-only tools and built-in read-only shell commands";
     - `acceptEdits`: "File edits without a prompt";
     - `dontAsk`: "Only pre-approved tools and built-in read-only handling | Strict CI allowlists";
     - `bypassPermissions` (always-approve): "Tool calls in general (`deny` rules, hooks, and some shell `ask` rules still apply)".
   - The recommended setting for SDKs is "Scripts, SDKs, CI, agent servers | Always-approve; add deny rules or hooks for hard limits". Under `dontAsk`, a call that no rule allows is denied ("a denial under `dontAsk`").
   - **UNVERIFIED: what `default` mode does in headless `-p` when a call needs approval (block, fail, or auto-deny).** No doc sentence says it, and testing it needs a model call. The earlier spec's A-5 assumed "refused".
   - The `streaming-messages-json` docs say: "Grok omits the schema's always-empty `permission_denials`, because it does not collect permission denials."
   - `GROK_DEFAULT_SELECTED_PERMISSION` only chooses which TUI approval row starts highlighted. It is not a headless permission policy.

7. **Thread storage: VERIFIED (doc), partly by listing.**
   - Path: `~/.grok/sessions/<encoded-cwd>/<session-id>/`. It holds `updates.jsonl` (the source of truth), `summary.json` (`info`, `parent_session_id`, `current_model_id`, …), `chat_history.jsonl`, `plan.json` and `signals.json` (user-guide/17-sessions.md "Session Storage Details").
   - `grok sessions search` keeps a SQLite full-text index, `~/.grok/sessions/session_search.sqlite` (seen in the listing).
   - Sessions are stored per working directory: `-s` says "must not already exist under the target session directory", and `-r` title matching is "for the current directory". A continue or fork must therefore run with the same `--cwd` and the same `GROK_HOME`. Whether `--resume <uuid>` finds a session created under a different cwd is UNVERIFIED.

## opencode

Sources:
- `--help` on the installed 1.18.31, and two read-only diagnostics, `opencode debug paths` and `opencode debug skill`.
- `opencode models <provider>`, which lists models from the catalog and makes no model call.
- The vendor docs https://opencode.ai/docs/cli/, /docs/providers/, /docs/permissions/ and /docs/skills/.
- The built-in `customize-opencode` skill text, printed by `opencode debug skill`.
- The vendor source at tag `v1.18.31` of `github.com/anomalyco/opencode` (the repo `sst/opencode` now redirects there): `packages/opencode/src/cli/cmd/run.ts`, `src/auth/index.ts`, `src/provider/provider.ts`, `src/config/config.ts` and `packages/core/src/flag/flag.ts`, cited as `run.ts:<line>` and so on.
- The models.dev catalog, https://models.dev/api.json, which is where opencode's built-in providers come from.

1. **Installed: VERIFIED.** `opencode --version` prints `1.18.31`. The scoop shim is `C:\Users\422mi\scoop\shims\opencode.exe`, and the real binary is `C:\Users\422mi\scoop\apps\opencode\current\opencode.exe`. The latest release on GitHub is `v1.19.0`. `opencode debug paths` prints `data C:\Users\422mi\.local\share\opencode`, `config C:\Users\422mi\.config\opencode`, `cache C:\Users\422mi\.cache\opencode` and `state C:\Users\422mi\.local\state\opencode`.

2. **API key: VERIFIED (source, binary and probe).**
   - **Env var per provider.** Each built-in provider reads the env var(s) named in its models.dev `env` list (provider.ts:1582-1593, "// load env"). The relevant ones:
     - `deepseek`: `DEEPSEEK_API_KEY`;
     - `zai-coding-plan`, `zai`, `zhipuai-coding-plan` and `zhipuai`: **all four read `ZHIPU_API_KEY`**;
     - `xai`: `XAI_API_KEY`;
     - `meta`: `META_MODEL_API_KEY` (Muse Spark models at `https://api.meta.ai/v1`);
     - `llama`: `LLAMA_API_KEY`.
   - Probe: without a key, `opencode models zai-coding-plan` prints `Error: Provider not found: zai-coding-plan`. With `ZHIPU_API_KEY=dummy-not-a-key` set for that one child, the same command lists `zai-coding-plan/glm-4.7 … glm-5.3, glm-5.3-flash, glm-5.3-highspeed`. A key given to one child process therefore enables the provider, and no global state is written.
   - **Stored login: `~/.local/share/opencode/auth.json`.** It exists on this machine; it was listed, not opened. Docs: "When you add a provider's API keys with the `/connect` command, they are stored in `~/.local/share/opencode/auth.json`."
   - **Precedence (resolves the earlier A-4): config `apiKey` > `auth.json` > env var.**
     - provider.ts:1582-1606 merges the env key first ("// load env"), then deep-merges every `auth.json` entry of `type: "api"` over it ("// load apikeys"). A stored key therefore **replaces** the env key for the same provider.
     - provider.ts:1781: `if (options["apiKey"] === undefined && provider.key) options["apiKey"] = provider.key`. A config `provider.<id>.options.apiKey` therefore beats both.
     - So an env-only key does NOT win when the user has run `/connect` for that provider.
   - **Per-process overrides that beat a stored login without touching user files:**
     - (a) `OPENCODE_CONFIG_CONTENT='{"provider":{"<id>":{"options":{"apiKey":"{env:SOME_VAR}"}}}}'`. Inline config gets `{env:VAR}` substitution, because `loadConfig` runs `ConfigVariable.substitute` on it (config.ts:227-240, 482-490); the docs show `"apiKey": "{env:ANTHROPIC_API_KEY}"`.
     - (b) **`OPENCODE_AUTH_CONTENT`** (undocumented). auth/index.ts: `if (process.env.OPENCODE_AUTH_CONTENT) { try { return JSON.parse(process.env.OPENCODE_AUTH_CONTENT) } catch (err) {} }`. When set, it replaces the whole `auth.json` read for that process, in the shape `{"<providerId>": {"type": "api", "key": "<key>"}}`. The string is present in the installed 1.18.31 binary (grep found the same code). opencode's own workspace feature uses it to pass auth to children. It is undocumented, so treat it as unstable.
   - There is no `--api-key` flag in `opencode --help` or `opencode run --help`.

3. **Skills: VERIFIED (docs, source and probe).**
   - Discovery, from https://opencode.ai/docs/skills/:
     - project-local, searched "from the current directory up to the git worktree": `.opencode/skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md`, `.agents/skills/<name>/SKILL.md`;
     - global: `~/.config/opencode/skills/<name>/SKILL.md`, `~/.claude/skills/…`, `~/.agents/skills/…`;
     - the singular `skill/` folder also loads (the built-in skill says `.opencode/skill(s)/`, and `debug skill` listed `~/.config/opencode/skill/*`).
   - Format: frontmatter `name` is required: "1–64 characters, lowercase alphanumeric with single hyphen separators", and it must "Match the directory name that contains `SKILL.md`". `description` is required, "must be 1-1024 characters", and "skills without one are filtered out". Optional fields are `license`, `compatibility` and `metadata` (recognized keys `opencode/slash` and `opencode/autoinvoke`). The model loads a skill through the `skill` tool, and the permission key is `permission.skill`.
   - Extra folders per run: `skills.paths` and `skills.urls` in config. The built-in skill says: "Register skills from non-default locations via `skills.paths` (scanned recursively for `**/SKILL.md`) and `skills.urls` (each URL serves a list of skills)". It is "an object with `paths` and/or `urls`, not an array".
   - **Probe (VERIFIED):** `OPENCODE_CONFIG_CONTENT='{"skills":{"paths":["<scratch>/ocskills"]}}' OPENCODE_DISABLE_EXTERNAL_SKILLS=1 opencode debug skill` listed `vidbyte-probe-skill | …\scratchpad\ocskills\vidbyte-probe-skill\SKILL.md`, next to the user's global skills.
   - Turning off the user's skill scans per run:
     - `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` dropped the `~/.claude/skills` and `~/.agents/skills` entries (151 skills became 45);
     - `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` and `OPENCODE_DISABLE_CLAUDE_CODE=1` are documented in the /docs/cli env table;
     - the global `~/.config/opencode/skill(s)` folders still load unless the config dir is redirected (`OPENCODE_CONFIG_DIR`; its effect on the global folder is UNVERIFIED).

4. **Per-run config: VERIFIED (docs and source).**
   - Env vars, from the /docs/cli env table: `OPENCODE_CONFIG` ("Path to config file"), `OPENCODE_CONFIG_DIR` ("Path to config directory"), `OPENCODE_CONFIG_CONTENT` ("Inline json config content"), `OPENCODE_PERMISSION` ("Inlined json permissions config"), `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_PROJECT_CONFIG` (built-in skill: "skip the project's local `opencode.json`"), `OPENCODE_PURE=1` / `--pure` ("run without external plugins") and `OPENCODE_DB` (database path; see Q7).
   - Merge order, lowest to highest (config.ts:405-563):
     1. remote well-known config;
     2. global `~/.config/opencode/opencode.json(c)`;
     3. `OPENCODE_CONFIG` file;
     4. project `opencode.json(c)` (skipped by `OPENCODE_DISABLE_PROJECT_CONFIG`);
     5. `.opencode/` directories and `OPENCODE_CONFIG_DIR`;
     6. **`OPENCODE_CONFIG_CONTENT`** ("final local-scope merge");
     7. account/org config;
     8. **`OPENCODE_PERMISSION`**, deep-merged into `permission` last.
   - Unknown top-level keys fail startup ("Unknown top-level keys in `opencode.json` are rejected with `ConfigInvalidError`").
   - Headless settings, as `opencode run` flags: `-m/--model provider/model`, `--variant` ("provider-specific reasoning effort, e.g., high, max, minimal"), `--agent`, `--dir` (working directory), `--auto` (permissions), `--title`, `-f/--file`.
   - Config keys: `model`, `small_model`, `permission`, `agent.<name>.{model, prompt, permission, steps, temperature, …}`, `provider`, `skills`, `mcp`, `enabled_providers`, `disabled_providers`.
   - There is no max-turns flag. Per-agent `steps` in config limits agent steps (listed among the agent fields in the built-in skill; exact semantics UNVERIFIED).

5. **Thread operations, headless: VERIFIED (help and source).**
   - **`opencode run` supports everything asked:** `--format json` ("raw JSON events"), `-s/--session` ("session id to continue"), `-c/--continue`, `--fork` ("fork the session before continuing (requires --continue or --session)"), `-m/--model`, `--agent`, `--variant`, `--dir`, `--auto`, `--title`, `--attach <url>` (use a running `opencode serve`), and `--port`.
   - New thread: `opencode run --format json [-m p/m] [--agent a] [--variant v] [--dir D] "<prompt>"`. run.ts:556-570 calls `session.create` with `permission` rules that deny `question`, `plan_enter` and `plan_exit` in non-interactive mode (run.ts:430-447).
   - Continue: `opencode run --format json -s <sessionID> "<prompt>"`. An unknown id prints `Session not found` and exits 1 (run.ts:455-466). `-c` takes the first root session (`!item.parentID`) from `session.list()`.
   - Fork: `opencode run --format json -s <sessionID> --fork "<prompt>"` calls `sdk.session.fork({sessionID})`, then prompts the **new** id (run.ts:469-490). A prompt is required: "You must provide a message or a command" exits 1 (run.ts:419-422). A fork with no prompt therefore needs the server route `POST /session/{id}/fork` (earlier research).
   - **JSON events** (run.ts:678-692) are one JSON object per line: `{"type": <t>, "timestamp": <ms>, "sessionID": <id>, ...data}`.
     - Types: `step_start` `{part}`, `step_finish` `{part}`, `text` `{part}` (emitted only when `part.time.end` is set, i.e. the finished text), `tool_use` `{part}` (tool parts that are `completed` or `error`), `reasoning` `{part}` (only with `--thinking`), and `error` `{error}`.
     - **Every line carries `sessionID`**: this is how a caller learns the new thread's id, including a fork's new id. The final answer is the `part.text` of the `text` events. The earlier research recorded that `step_finish` carries cost and tokens.
     - The process ends when `session.status` turns `idle` (run.ts:793-799). Exit code is 1 if a `session.error` occurred.
   - **Stdin trap:** run.ts:416 runs `const piped = process.stdin.isTTY ? undefined : await Bun.stdin.text()` and appends piped stdin to the message. The child must get a closed stdin (`DEVNULL`), or it waits for EOF.
   - Server alternative (current PR): `opencode serve --hostname 127.0.0.1 --port 0` with `POST /session`, `POST /session/{id}/prompt_async`, `POST /session/{id}/fork`, and basic auth via `OPENCODE_SERVER_PASSWORD` / `OPENCODE_SERVER_USERNAME` (docs: "Set `OPENCODE_SERVER_PASSWORD` to enable HTTP basic auth (username defaults to `opencode`)").

6. **Permissions: VERIFIED (source for run mode, docs for defaults).**
   - Defaults (https://opencode.ai/docs/permissions/): "Most permissions default to "allow"" and "doom_loop and external_directory default to "ask""; `read` is allowed but `.env` files are denied. So edits and bash are allowed by default unless the user's config says otherwise.
   - **An "ask" under `opencode run` is auto-rejected, not blocked** (run.ts:801-822). On `permission.asked`, if `--auto` is set it replies `once`; otherwise it prints `permission requested: <perm> (<patterns>); auto-rejecting` and replies `reject`. Hidden aliases of `--auto` are `--yolo` and `--dangerously-skip-permissions` (run.ts:247-256, 274).
   - Non-interactive `run` also denies `question`, `plan_enter` and `plan_exit` on sessions it **creates**. A session reached with `-s` keeps its own rules.
   - Allow or deny per run with `OPENCODE_PERMISSION='{"edit":"deny","bash":{"*":"ask","git *":"allow"}}'` or a `permission` block in `OPENCODE_CONFIG_CONTENT`. Actions are `allow`, `ask` and `deny`, and "the last matching rule" wins.

7. **Thread storage: VERIFIED (listing and binary).**
   - Sessions live in the SQLite database `~/.local/share/opencode/opencode.db` (with `-wal` and `-shm`), plus `storage/` and `snapshot/` in the same data dir; seen in the listing.
   - `OPENCODE_DB` overrides the database file. In the binary, `:memory:` or an absolute path is used as is; any other value is joined to the data dir. Any later `run -s`/`--fork` must use the same `OPENCODE_DB`.
   - Sessions belong to a project (the git worktree of `--dir`/cwd); `-c` searches `session.list()` for the current project. Whether `-s <id>` finds a session created from a different project directory is UNVERIFIED.

## Muse Code

Sources:
- `muse --help`, `muse exec|resume|serve|skills|auth|login --help` on the installed 1.0.1, run inside WSL.
- The launcher script `/usr/local/bin/muse`.
- Read-only `muse skills list --json` probes.
- Vendor text embedded in the binary `/usr/local/bin/muse-bin-1.0.1-R2006.1`: bundled skills and help strings, extracted with a strings pass.
- The MSP 1.0.1 JSON Schema the earlier run exported (`muse schema generate-json-schema`), saved at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/2526e8d1-a2d5-407e-9242-3458f24f4f3a/scratchpad/research/muse-1.0.1-msp.schema.json`.
- No official Meta Muse Code doc page was found by web search; only third-party guides came up (see Gaps).

1. **Installed: VERIFIED.**
   - Windows has no native `muse`. `where muse` finds `C:\Users\422mi\.local\bin\muse.cmd`, whose content is `wsl.exe -d MuseUbuntu1 -- /usr/local/bin/muse %*`.
   - `wsl.exe -l -q` lists the distros `Ubuntu` and `MuseUbuntu1`.
   - `wsl.exe -d MuseUbuntu1 -e sh -c 'command -v muse; muse --version'` prints `/usr/local/bin/muse` and `Muse Code 1.0.1 (1.0.1-R2006.1)`.
   - `/usr/local/bin/muse` is a 33 KB **bash launcher** that ends in `exec "$binary" "$@"`. The real binary is `/usr/local/bin/muse-bin-1.0.1-R2006.1`, chosen through `/usr/local/bin/.muse-version`.
   - **Launcher trap:** unless `MUSE_NO_AUTO_UPDATE=1` is set, every launch may start a background self-update, at most once per `MUSE_UPDATE_INTERVAL_SECONDS` (default 3600). Launcher: `elif [[ "${MUSE_NO_AUTO_UPDATE:-0}" != 1 ]] && should_check_for_update …`. This scout's own `muse --version` probe wrote `/usr/local/bin/.muse-update-checked-at`; the binary was not replaced.
   - WSL runs as root here: `HOME=/root`, and `/root/.config` does not exist, so there is no Muse login or saved key.

2. **API key: VERIFIED (help, launcher, binary text).**
   - Env var `META_API_KEY`. `muse login --help`: "META_API_KEY always takes priority over the account login." Binary text: "note: META_API_KEY overrides your Meta account login; unset it to use the account login, or run `muse logout` to remove the login." So, **unlike Grok and opencode, the env key wins over a stored login.**
   - **Per-run flag `muse exec --api-key-stdin`**: "Read the provider API key from stdin". Passing the secret as a flag is refused; binary text: "--api-key … use --api-key-stdin instead of passing secrets as flag values".
     - This avoids env plumbing across WSL entirely: stdin passes through `wsl.exe`.
     - It also means the prompt cannot come from stdin; use the positional `[PROMPT]` or `--prompt-file <PATH>`.
     - `muse serve` has **no** `--api-key-stdin` (`muse serve --help` lists only the sandbox flags and `--no-session-log`). A served MSP host gets its key only from `META_API_KEY` or saved credentials, and MSP 1.0.1 has no auth method (earlier spec A-10).
   - Env across WSL: a Windows-side `META_API_KEY` reaches the distro only when `WSLENV` names it (`META_API_KEY/u`), which is the earlier PR's design. `wsl.exe -e sh -c '…'` probes confirmed `META_API_KEY unset` inside the distro.
   - Saved credentials:
     - `muse auth set [--provider <PROVIDER>] --api-key-stdin` ("Which provider the credential is for. Defaults to `meta`") and `muse login` (device-code browser login).
     - The launcher's credential path is `${MUSE_AUTH_PATH:-$XDG_CONFIG_HOME/muse/auth.json, else $HOME/.config/muse/auth.json}`.
     - Precedence between `--api-key-stdin` and `META_API_KEY` is UNVERIFIED. The binary has the source labels "API key (unsaved)", "META_API_KEY (environment)" and "Meta account".
   - Per child only: both `--api-key-stdin` and a child-only `META_API_KEY` (+ `WSLENV`) leave no global state.

3. **Skills: VERIFIED (vendor text and probes).**
   - Scopes, from the bundled `create-skill` skill text:
     - "Project scope (the default): the skill lives in the current workspace at `.agents/skills/<skill-id>/`";
     - "Personal scope … the managed personal root `$CONFIG_DIR/skills/<skill-id>` (`$XDG_CONFIG_HOME/muse`, else `$HOME/.config/muse`)";
     - `~/.codex/skills`, `~/.claude/skills` and `$HOME/.agents/skills` are read as "import-only sources, never write targets";
     - bundled skills live at `bundled://muse-core/skills/<name>/SKILL.md` (`muse skills list --json`).
   - Format: `SKILL.md` with frontmatter `name` (the skill id: "ASCII lowercase letters, digits, hyphen, or underscore", must not start with `-`, no Windows reserved stems) and `description`. `muse skills validate <path> --json` validates a skill.
   - **Trust gate (VERIFIED by probe).** `muse skills list --source project --workspace <ws> --json` on a workspace holding `.agents/skills/vidbyte-probe-proj/SKILL.md` returned the diagnostic `"code": "project-skills-untrusted", "message": "project skills skipped because workspace is untrusted"`. Adding `--trust-workspace` listed `"id": "vidbyte-probe-proj", "path": ".agents/skills/vidbyte-probe-proj/SKILL.md", "scope": "project"`.
     - `--trust-workspace` is per run: "Trust this workspace for this run (load its skills and rules); does not save trust".
     - It exists on `muse`, `muse exec` and `muse serve` ("Load each session workspace's skills and rules").
     - `--yolo` also trusts the workspace.
   - **Per-run personal root (VERIFIED by probe).** `XDG_CONFIG_HOME=<scratch>/musexdg muse skills list --source user --json` listed `"id": "vidbyte-probe-user", "path": "$CONFIG_DIR/skills/vidbyte-probe-user/SKILL.md", "scope": "user"`. Side effect: `XDG_CONFIG_HOME` also moves `settings.json` and the saved credentials (`$XDG_CONFIG_HOME/muse/auth.json`).
   - `muse exec --no-foreign-personal-context` will "Exclude foreign personal rules and skills from this run".
   - No `--skills-dir` flag exists on `muse`, `exec` or `serve` (VERIFIED by reading the help). MSP 1.0.1 has no `skill/*` methods; the earlier research says they arrive in Muse 1.4.

4. **Per-run config: VERIFIED (help); file layout from binary strings.**
   - `muse exec` flags:
     - model: `--model <ID>`, `--reasoning-effort none|minimal|low|medium|high|xhigh|ultra` (default `high`);
     - provider: `--provider echo|meta`, `--base-url <URL>`;
     - workspace: `--workspace <PATH>`;
     - limits: `--max-model-steps <N>`, `--max-tool-output-bytes <N>`;
     - permissions: `--approval-mode untrusted|on-request|never` (default `on-request`), `--approval-judge off|on` (default `on`; an LLM decides prompt-bound calls), `--permission-profile <ID>`;
     - safety: `--disable-write`, `--disable-shell`, `--disable-sandbox`, `--sandbox-network restricted|enabled|proxy-only`, `--yolo`, `--trust-workspace`;
     - misc: `--disable-web-tools`, `--no-session-log`, `--user-input-auto-resolve` ("Offer request_user_input and auto-cancel prompts (headless)"), and the root `--agents <JSON>` ("Supply one ephemeral agent-definition overlay").
   - Env names seen in the binary: `MUSE_MODEL`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `MUSE_DISABLE_APPROVAL_JUDGE`, `MUSE_CUSTOM_HEADERS`. Launcher env: `MUSE_NO_AUTO_UPDATE`, `MUSE_AUTH_PATH`.
   - The user settings file is `$HOME/.config/muse/settings.json` (binary string). No inline-config env var (an equivalent of `OPENCODE_CONFIG_CONTENT`) was found.
   - Windows paths must be translated to `/mnt/c/...` for `--workspace` and `--prompt-file` (VERIFIED: the probes used `/mnt/c/...` paths).

5. **Thread operations: PARTLY VERIFIED.**
   - New thread: `muse exec --json [--session-id <UUID>] [--model M] [--reasoning-effort E] [--workspace P] "<prompt>"` (or `--prompt-file`).
     - `--session-id <UUID>`: "Use a specific session id". The caller can mint the UUID, so it knows the thread id without parsing output.
     - Binary text: "--session-id requires session logging", so it cannot be combined with `--no-session-log`.
     - Another binary string: "refusing to resume because provider identity cannot be verified; start a new --session-id to switch providers".
   - Continue: `muse exec --session-id <existing-id> "<follow-up>"`. Vendor text from the bundled session-recovery skill: "`muse exec --session-id <session-id> "<follow-up>"` — headless continuation, only on explicit request". `muse resume <session-uuid>` / `--last` is the interactive form.
   - Fork: **no headless CLI fork** (`muse exec --help` has no fork flag). Fork exists only on MSP over `muse serve`.
     - `session/fork` params: `{commandId (UUIDv7, required), sessionId (required), cutPoint?, excludeItems?}`. `cutPoint` means "Copy history through a completed turn, inclusive. Omitted means "all completed turns"".
     - Result: `{session (the new fork session, carrying `forkedFrom` provenance), history, pendingRequests, viewCursor}`. No prompt is needed; a following `turn/start {commandId, sessionId, input[], reasoningEffort?, ifBusy?}` adds one.
     - MSP `session/start` takes `{commandId, sessionId? ("Exact identity for this new root session. When omitted the server mints a UUIDv7"), modelId?, providerId?, approvalMode?, workspaceRoot?}`.
     - `ApprovalMode` enum: `allowAll | promptUnmatched | onRequest | denyUnmatched`.
   - **`muse exec --json` event shapes: UNVERIFIED.** Help says only "Emit machine-readable JSONL events on stdout", and no doc text with event names was found in the binary or on the web. They could be checked offline with `muse exec --provider echo --json …` (the echo provider makes no model call), but this scout did not run it because the brief forbids muse turns.

6. **Permissions: PARTLY VERIFIED.**
   - Help: "Safety (approval and the sandbox are ON by default)". The default `--approval-mode` is `on-request`, and `--approval-judge` defaults to `on` (an LLM approval judge, which may itself use model quota).
   - Opt-outs per run: `--disable-approval`, `--approval-mode never`, `--yolo` ("Disable approval and sandbox and trust this workspace (this run)"). Restrictions: `--disable-write`, `--disable-shell`.
   - `muse serve`: "Approval mode is … selected on the wire, so there is no approval flag here". The earlier PR used `approvalMode: denyUnmatched`.
   - UNVERIFIED: what `muse exec` does when a call needs a human approval and none can be given. The binary contains "unsandboxed execution requires human approval, but approval prompts are disabled", which suggests refusal, not blocking, but no doc sentence says so.

7. **Thread storage: VERIFIED (vendor text and listing).**
   - From the bundled skill text: `MUSE_SESSIONS="${XDG_DATA_HOME:-$HOME/.local/share}/muse/sessions"`; "the store is sharded by local date" (`$MUSE_SESSIONS/*/*/*/*/` holds `<session-id>` directories with a `session.jsonl` log).
   - A session index lives at `~/.local/share/muse/session-index.db` (seen in the listing at `/root/.local/share/muse/`).
   - A later continue or fork must use the same `XDG_DATA_HOME` and run in the same WSL distro (and as the same Linux user).

## GLM and DeepSeek routes

| Harness | GLM Coding Plan | GLM plain API | DeepSeek |
|---|---|---|---|
| opencode | **Built-in provider `zai-coding-plan`** (models.dev `env: ["ZHIPU_API_KEY"]`, `api: https://api.z.ai/api/coding/paas/v4`, models `glm-4.7, glm-5-turbo, glm-5.2, glm-5.2-highspeed, glm-5.3, glm-5.3-flash, glm-5.3-highspeed`). VERIFIED by probe: `ZHIPU_API_KEY=dummy opencode models zai-coding-plan` lists them; model id `zai-coding-plan/glm-5.3`. | **Built-in provider `zai`** (`env: ["ZHIPU_API_KEY"]`, `api: https://api.z.ai/api/paas/v4`). VERIFIED by the same probe (`zai/glm-4.5 … zai/glm-4.7-flashx`). China endpoints: `zhipuai` and `zhipuai-coding-plan` (`open.bigmodel.cn`). | **Built-in provider `deepseek`** (`env: ["DEEPSEEK_API_KEY"]`, npm `@ai-sdk/openai-compatible`, `api: https://api.deepseek.com`). VERIFIED: `opencode models deepseek` lists `deepseek/deepseek-flash`, `deepseek/deepseek-v4-pro` (models.dev also lists `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp`). |
| Grok Build | Technically possible through a custom model `[model.<id>]` with `base_url = "https://api.z.ai/api/coding/paas/v4"`, `api_backend = "chat_completions"`, `env_key = "<VAR>"` (user-guide/11-custom-models.md). But this must be in a `config.toml`: the `GROK_CONFIG` overlay allowlist excludes the `model` table, so it needs a private `GROK_HOME/config.toml`. **Not allowed by Z.ai: Grok is not on the Coding Plan tool list.** | Same custom-model route, with `base_url = "https://api.z.ai/api/paas/v4"` (UNVERIFIED end to end). | Same custom-model route, with `base_url = "https://api.deepseek.com"` (chat completions) or `https://api.deepseek.com/anthropic` with `api_backend = "messages"` (UNVERIFIED end to end). |
| Muse Code | **No.** `--provider <MODE>  Startup provider: echo or meta`. `--base-url` overrides only "the Meta provider base URL"; pointing it at Z.ai is UNVERIFIED and unlikely to work. Also not on the Coding Plan tool list. | No CLI route (same reason). | No CLI route (same reason). |

- **Z.ai Coding Plan tool list (VERIFIED).** https://docs.z.ai/devpack/tool/others: "The GLM Coding Plan is limited to use within the following officially supported tools and product environments;" … "users may not use their subscription benefits for tools or scenarios outside of this scope."
  - Coding Agent Tools listed: "ZCode, Claude Code, Claude for IDE, Codex, OpenCode, Pi, Cursor, Cline, TRAE, Qoder, Droid, Kilo Code, Roo Code, Crush, Goose, Eigent". General-purpose agents listed: "AutoClaw, OpenClaw, Hermes Agent, SillyTavern".
  - **OpenCode is listed; Grok/Grok Build and Muse Code/Meta are not.**
  - FAQ (https://docs.z.ai/devpack/faq): "Users subscribed to the Coding Plan can only make calls via the plan's quota in supported tools." and "API calls outside the plan are not available." Also: "API endpoint for Claude Code and Goose is：`https://api.z.ai/api/anthropic`" and "API endpoint for other tools is: `https://api.z.ai/api/coding/paas/v4`". A plan key used outside its conditions returns "1113 Insufficient Balance".
- **DeepSeek (VERIFIED, https://api-docs.deepseek.com/).** OpenAI-compatible base `https://api.deepseek.com`; Anthropic-compatible `https://api.deepseek.com/anthropic`. Key is sent as `Authorization: Bearer ${DEEPSEEK_API_KEY}`. Models: "Use `deepseek-flash` as the model name" and `deepseek-v4-pro`; legacy `deepseek-v4-flash` is "served by the DeepSeek-V4.1-Flash model". The page names OpenCode as a supported backend and has an Agent Integrations page for it (`/quick_start/agent_integrations/opencode`, not fetched).
- Trap: the four Z.ai/Zhipu providers in opencode share **one** env var, `ZHIPU_API_KEY`. The model id prefix (`zai-coding-plan/` vs `zai/`) is the only thing that picks the Coding Plan endpoint versus the metered API. A Coding Plan key sent to `zai/…` (the plain endpoint) bills the account balance or fails.
- Note: models.dev also has opencode providers `xai` (`XAI_API_KEY`) and `meta` (`META_MODEL_API_KEY`, `https://api.meta.ai/v1`, Muse Spark models), so opencode can drive Grok and Meta **models** with a caller key. That is not the Grok Build or Muse Code **harness**.

## Gaps

These are still UNVERIFIED and must be carried as assumptions in the spec.

1. **Grok headless `default`-mode approval behavior.** Unknown whether an approval-needing tool call in `grok -p` (no `--always-approve`) is auto-denied, fails the run, or blocks; no doc sentence found, and testing needs a model call. `dontAsk` is documented to deny; `bypassPermissions`/`--always-approve` is the vendor's recommended SDK mode.
2. **Grok ACP `x.ai/session/fork` params and result.** Only the method name is documented. A fork without a new prompt is otherwise unavailable headless.
3. **Grok session lookup across cwd.** Whether `--resume <uuid>` finds a session created under a different `--cwd` is unknown, because storage is per encoded cwd.
4. **Grok with a fresh `GROK_HOME`.** Whether it still scans `~/.claude/skills` and `~/.cursor/skills` (HOME-based) is unknown. Also unknown: whether the first run in an empty `GROK_HOME` triggers any interactive step (onboarding, trust) that blocks headless runs.
5. **Grok project skills in headless runs need folder trust** ("requires `--trust` or a prior grant"). `--trust` is hidden; its exact effect in `-p` mode (per-run or saved) was not probed, because it writes `trusted_folders.toml`.
6. **Grok JSON output on 1.0.52** is taken from the vendor doc, not a live run. The 1.0.13 research saw only `{text, stopReason, sessionId, requestId}`.
7. **opencode `OPENCODE_AUTH_CONTENT`** is undocumented (source and binary only) and may change. `OPENCODE_CONFIG_CONTENT` with `provider.<id>.options.apiKey` is the documented way to beat a stored `auth.json` key.
8. **opencode `-s <id>` across project directories**, and whether `OPENCODE_CONFIG_DIR` replaces or only adds to the global `~/.config/opencode` (skills, agents).
9. **opencode `run` with `-s` on a session it did not create** keeps that session's permission rules; `run` adds its deny-`question`/`plan_*` rules only on `session.create`.
10. **Muse `exec --json` event schema**: names, field holding the final text, field holding the session id. A free offline check exists (`--provider echo`), but it was not run because the brief forbids muse turns.
11. **Muse key precedence** between `--api-key-stdin`, `META_API_KEY` and a saved `muse auth set` key. Env beats the account login (VERIFIED); the stdin key's rank is unknown.
12. **Muse headless approval behavior** under the default `on-request` with the LLM judge on: whether an unresolved approval is denied, fails, or waits.
13. **Muse `exec --session-id <new-uuid>`**: whether it creates a new session when the id is unknown (strongly implied by the "start a new --session-id to switch providers" text, but not stated).
14. **No official Muse Code docs were found online.** All Muse facts come from local help, the launcher, binary text and probes.
15. **Grok or Muse routed to GLM/DeepSeek**: never run. Grok's custom-model route is documented generically; Muse has no route.
