# Vendor facts: Claude Code CLI, one headless run per call

Author: S0 vendor scout, 2026-10-15. CLI under test: **Claude Code 2.1.301**, native Windows build.

How to read this file. Every fact carries its evidence: **[probe `name`]** means an offline run of the real `claude.exe` against a local stand-in for the Anthropic Messages API, with outputs saved under `SCRATCH/out/<name>.{stdout,stderr,meta.json}` and the request bodies under `SCRATCH/logs/bodies/`. **[doc URL]** means a quote from the official docs, fetched 2026-10-15. Anything not observed is marked **unverified**.

`SCRATCH` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c726d777-284c-4c17-9776-72f9da8a13f9/scratchpad/claude-vendor-probe/`. The full command list is in `reports/S0-vendor-scout.md`.

Probe harness, in one paragraph. `standin.py` is a threaded HTTP server on 127.0.0.1 that logs method, path, header names, a class for `x-api-key` and `Authorization` (known fake values are named; anything else is logged as `other(len=N)`, never the value), and the JSON body; it answers `POST /v1/messages` with SSE or JSON, and `CONNECT` with 403. `run.py` starts `C:\Users\422mi\.local\bin\claude.exe` with an explicit environment: `ANTHROPIC_API_KEY=sk-ant-probe-0000` (fake), `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`, `CLAUDE_CONFIG_DIR=<fresh scratch dir>`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_AUTOUPDATER=1`, and `HTTPS_PROXY`/`HTTP_PROXY` pointed at the stand-in (so any other outbound HTTPS shows up as a logged, refused `CONNECT`), `NO_PROXY=127.0.0.1,localhost`. Most runs also pointed `USERPROFILE` at a scratch home; the runs marked "real home" did not. It refuses to start if any credential variable is not a known fake. No real key, login or network endpoint was used.

---

## 1. Installation on this machine

| Check | Output (verbatim) |
| :- | :- |
| `command -v claude` (Git Bash) | `/c/users/422mi/.local/bin/claude` |
| `type -a claude` | `claude is /c/users/422mi/.local/bin/claude` (listed four times, because PATH holds `~/.local/bin` under two spellings, twice each) |
| `cmd /c "where claude"` | `C:\Users\422mi\.local\bin\claude.exe` (only match) |
| `cmd /c "where claude.exe"` | `C:\Users\422mi\.local\bin\claude.exe` |
| Python `shutil.which('claude')` | `'C:\\users\\422mi\\.local\\bin\\claude.EXE'` (found through PATHEXT; case follows PATHEXT) |
| `claude --version` | `2.1.301 (Claude Code)`, exit 0 |

- **Native `.exe` only; there is no shim.** `~/.local/bin/claude.exe` (271,840,416 bytes, 2026-10-15 15:34) is a byte copy of `~/.local/share/claude/versions/2.1.301` (`cmp` says identical). That `versions/` folder also holds `2.1.299` and `2.1.300`, and `~/.local/bin/` holds `claude.exe.old.<n>.<pid>` leftovers from the auto-updater. The npm global root `C:\Users\422mi\AppData\Roaming\npm\node_modules` has no `@anthropic-ai` folder, and `%APPDATA%\npm` has no `claude`, `claude.cmd` or `claude.ps1`. So this machine has no `.cmd`, `.bat` or shell shim.
- **The native installer updates itself in place.** It moved 2.1.299 → 2.1.300 → 2.1.301 between 10-13 and 10-15. The CLI version can change between two SDK calls unless `DISABLE_AUTOUPDATER=1` is set (env-vars doc: "Set to `1` to disable automatic background updates"; `DISABLE_UPDATES=1` also blocks a manual `claude update`). https://code.claude.com/docs/en/env-vars
- No managed settings exist. The debug log reports `Broken symlink or missing file encountered for settings.json at path: C:\Program Files\ClaudeCode\managed-settings.json`, and `C:\Program Files\ClaudeCode` and `C:\ProgramData\ClaudeCode` do not exist [probe `p02-base`, `SCRATCH/out/p02-debug.log`].
- On Windows, Claude Code uses Git Bash for hooks and the Bash tool: `Using bash path: "C:\Program Files\Git\bin\bash.exe"` [p02 debug log].
- Checks of the open PR's claims. `CLAUDE_HOME_CLI_PARTS = (".local","bin","claude.exe")` is correct for this machine. `CLAUDE_MIN_CLI_VERSION = "2.1.296"` is satisfied by 2.1.301. The claim that only native `.exe`/`.com` files start without a shell is not something this probe tested, because no shim exists here (**unverified**).

## 2. CLI flags

Full `claude --help` output, verbatim (311 lines, exit 0; captured with a scratch `CLAUDE_CONFIG_DIR`):

```text
Usage: claude [options] [command] [prompt]

Claude Code - starts an interactive session by default, use -p/--print for
non-interactive output

Arguments:
  prompt                                Your prompt

Options:
  --add-dir <directories...>            Additional directories to allow tool
                                        access to
  --agent <agent>                       Agent for the current session. Overrides
                                        the 'agent' setting.
  --agents <json-or-file>               JSON object defining custom agents, or
                                        with --print the path to a file that
                                        holds one (e.g. '{"reviewer":
                                        {"description": "Reviews code",
                                        "prompt": "You are a code reviewer"}}')
  --allow-dangerously-skip-permissions  Enable bypassing all permission checks
                                        as an option, without it being enabled
                                        by default. Recommended only for
                                        sandboxes with no internet access.
  --allowedTools, --allowed-tools <tools...>
      Comma or space-separated list of tool names to allow (e.g. "Bash(git *)
      Edit")
  --append-system-prompt <prompt>       Append a system prompt to the default
                                        system prompt
  --autocompact <auto|tokens>           Auto-compact window size (auto, or
                                        100k–1M tokens)
  --ax-screen-reader                    Render screen-reader friendly output
                                        (flat text, no decorative borders or
                                        animations).
  --bg, --background                    Start the session in the background and
                                        return immediately. Prints the id that
                                        `claude attach`, `logs`, `stop` and `rm`
                                        take; `claude agents` lists them. With
                                        --resume <session-id>, continues that
                                        session in the background under the same
                                        ID, or starts a copy and says so when
                                        the session is already running
  --bare                                Minimal mode: skip hooks (those defined
                                        in settings and by installed plugins;
                                        features built into Claude Code are
                                        unaffected), LSP, plugin sync,
                                        attribution, auto-memory, background
                                        prefetches, keychain reads, and
                                        CLAUDE.md auto-discovery. Sets
                                        CLAUDE_CODE_SIMPLE=1. Anthropic auth is
                                        strictly ANTHROPIC_API_KEY or
                                        apiKeyHelper via --settings (OAuth and
                                        keychain are never read). 3P providers
                                        (Bedrock/Vertex/Foundry) use their own
                                        credentials. Skills still resolve via
                                        /skill-name. Explicitly provide context
                                        via: --system-prompt[-file],
                                        --append-system-prompt[-file], --add-dir
                                        (CLAUDE.md dirs), --mcp-config,
                                        --settings, --agents, --plugin-dir.
  --betas <betas...>                    Beta headers to include in API requests
                                        (API key users only)
  --brief                               Enable SendUserMessage tool for
                                        agent-to-user communication
  --chrome                              Enable Claude in Chrome integration
  --cloud [description|session_id|url]  Create a cloud session with the given
                                        description, or attach to an existing
                                        one by session ID or claude.ai/code URL
  -c, --continue                        Continue the most recent conversation in
                                        the current directory
  --dangerously-skip-permissions        Bypass all permission checks.
                                        Recommended only for sandboxes with no
                                        internet access.
  -d, --debug [filter]                  Enable debug mode with optional category
                                        filtering (e.g., "api,hooks" or
                                        "!1p,!file")
  --debug-file <path>                   Write debug logs to a specific file path
                                        (implicitly enables debug mode)
  --desktop                             Open in the Claude Desktop app instead
                                        of the terminal (with --continue or
                                        --resume <id> to pick the session)
  --disable-slash-commands              Disable all skills
  --disallowedTools, --disallowed-tools <tools...>
      Comma or space-separated list of tool names to deny (e.g. "Bash(git *)
      Edit")
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --environment <environment_id>        Create a new cloud session that runs on
                                        the given self-hosted environment
                                        (ccpool_...).
  --exclude-dynamic-system-prompt-sections
      Move per-machine sections (cwd, env info, memory paths, git status) from
      the system prompt into the first user message. Improves cross-user
      prompt-cache reuse. Only applies with the default system prompt (ignored
      with --system-prompt). (default: false)
  --fallback-model <model>              Enable automatic fallback to specified
                                        model(s) when the default model is
                                        overloaded or not available. Accepts a
                                        comma-separated list to try each in
                                        order. Re-tries the primary at the start
                                        of each user turn.
  --file <specs...>                     File resources to download at startup.
                                        Format: file_id:relative_path (e.g.,
                                        --file file_abc:doc.txt
                                        file_def:img.png)
  --fork-session                        When resuming, create a new session ID
                                        instead of reusing the original (use
                                        with --resume or --continue)
  --forward-subagent-text               Forward subagent text and thinking
                                        blocks as assistant/user messages with
                                        parent_tool_use_id set (only works with
                                        --print and --output-format=stream-json)
  --from-pr [value]                     Resume a session linked to a PR by PR
                                        number/URL, or open interactive picker
                                        with optional search term
  -h, --help                            Display help for command
  --ide                                 Automatically connect to IDE on startup
                                        if exactly one valid IDE is available
  --include-hook-events                 Include all hook lifecycle events in the
                                        output stream (only works with
                                        --output-format=stream-json)
  --include-partial-messages            Include partial message chunks as they
                                        arrive (only works with --print and
                                        --output-format=stream-json)
  --input-format <format>               Input format (only works with --print):
                                        "text" (default), or "stream-json"
                                        (realtime streaming input) (choices:
                                        "text", "stream-json")
  --json-schema <schema>                JSON Schema for structured output
                                        validation. Example:
                                        {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}
  --max-budget-usd <amount>             Maximum dollar amount to spend on API
                                        calls (only works with --print)
  --mcp-config <configs...>             Load MCP servers from JSON files or
                                        strings (space-separated)
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name.
  -n, --name <name>                     Set a display name for this session
                                        (shown in the prompt box, /resume
                                        picker, and terminal title)
  --no-chrome                           Disable Claude in Chrome integration
  --no-session-persistence              Disable session persistence - sessions
                                        will not be saved to disk and cannot be
                                        resumed (only works with --print)
  --output-format <format>              Output format (only works with --print):
                                        "text" (default), "json" (single
                                        result), or "stream-json" (realtime
                                        streaming) (choices: "text", "json",
                                        "stream-json")
  --permission-mode <mode>              Permission mode to use for the session
                                        (choices: "acceptEdits", "auto",
                                        "bypassPermissions", "manual",
                                        "dontAsk", "plan")
  --permission-prompts <target>         Who answers permission prompts with
                                        --print: "host" (the SDK host or
                                        --permission-prompt-tool) or "none"
                                        (nobody: anything that would prompt is
                                        denied automatically; the permission
                                        mode still decides everything else)
                                        (choices: "host", "none", default:
                                        "host")
  --plugin-dir <path>                   Load a plugin from a directory or .zip
                                        for this session only; a folder of
                                        plugins loads each child (repeatable:
                                        --plugin-dir A --plugin-dir B.zip)
                                        (default: [])
  --plugin-url <url>                    Fetch a plugin .zip from a URL for this
                                        session only (repeatable: --plugin-url A
                                        --plugin-url B) (default: [])
  -p, --print                           Print response and exit (useful for
                                        pipes). Note: The workspace trust dialog
                                        is skipped when Claude is run in
                                        non-interactive mode (via -p, or when
                                        stdout is not a TTY, e.g. piped or
                                        redirected output). Only use this in
                                        directories you trust. Settings files
                                        that fail validation are silently
                                        ignored in this mode (no error dialog is
                                        shown).
  --prompt-suggestions [value]          Enable prompt suggestions. In print/SDK
                                        mode, emits a prompt_suggestion message
                                        after each turn with a predicted next
                                        user prompt (choices: "true", "false",
                                        "1", "0", "yes", "no", "on", "off",
                                        preset: "true")
  --remote-control [name]               Start an interactive session with Remote
                                        Control enabled (optionally named)
  --remote-control-session-name-prefix <prefix>
      Prefix for auto-generated Remote Control session names (default: hostname)
  --replay-user-messages                Re-emit user messages from stdin back on
                                        stdout for acknowledgment (only works
                                        with --input-format=stream-json and
                                        --output-format=stream-json)
  --restricted                          Restricted mode: removes the built-in
                                        tools that run commands or code (Bash,
                                        PowerShell and the other code-running
                                        tools) and WebFetch unless --tools names
                                        them, and ignores user, project and
                                        local settings files (managed settings
                                        and --settings still apply; add
                                        --strict-mcp-config to skip MCP servers
                                        too). Also confines the file tools to
                                        the working directories (--add-dir
                                        included), refuses bypassPermissions,
                                        and lets only a person or the configured
                                        permission handler approve writes to
                                        settings, git and tool-configuration
                                        files.
  -r, --resume [value]                  Resume a conversation by session ID, or
                                        open interactive picker with optional
                                        search term
  --safe-mode                           Start with all customizations
                                        (CLAUDE.md, skills, installed plugins,
                                        hooks, MCP servers, custom commands and
                                        agents, output styles, workflows, custom
                                        themes, keybindings, and more) disabled
                                        — useful for troubleshooting a broken
                                        configuration. Admin-managed (policy)
                                        settings still apply. Auth, model
                                        selection, built-in tools and plugins,
                                        and permissions work normally. Sets
                                        CLAUDE_CODE_SAFE_MODE=1.
  --session-id <uuid>                   Use a specific session ID for the
                                        conversation (must be a valid UUID)
  --setting-sources <sources>           Comma-separated list of setting sources
                                        to load (user, project, local).
  --settings <file-or-json>             Path to a settings JSON file or a JSON
                                        string to load additional settings from
  --strict-mcp-config                   Only use MCP servers from --mcp-config,
                                        ignoring all other MCP configurations
  --system-prompt <prompt>              System prompt to use for the session
  --system-prompt-snapshot <on|off>     Record the system prompt once per
                                        conversation and reuse it verbatim on
                                        every request and resume. on (the
                                        default): the prompt is rendered on the
                                        conversation's first request — a
                                        --system-prompt or
                                        --append-system-prompt included — sent,
                                        and recorded; every later request and
                                        resume sends the record as-is, even when
                                        a later launch passes different text,
                                        until the conversation is compacted.
                                        off: never record; the prompt is
                                        rendered fresh every request (for
                                        iterating on prompt text). No effect
                                        where system-prompt recording is not yet
                                        enabled. (choices: "on", "off")
  --teleport [session]                  Resume a teleport session, optionally
                                        specify session ID
  --tmux                                Create a tmux session for the worktree
                                        (requires --worktree). Uses iTerm2
                                        native panes when available; use
                                        --tmux=classic for traditional tmux.
  --tools <tools...>                    Specify the list of available tools from
                                        the built-in set. Use "" to disable all
                                        tools, "default" to use all tools, or
                                        specify tool names (e.g.
                                        "Bash,Edit,Read").
  --verbose                             Override verbose mode setting from
                                        config
  -v, --version                         Output the version number
  -w, --worktree [name]                 Create a new git worktree for this
                                        session (optionally specify a name)

Commands:
  agents [options]                      Manage background agents
  attach <id|name>                      Open a background session in this
                                        terminal. <id> is the short id that
                                        `claude --bg` prints and `claude agents`
                                        lists. Part of the session name works
                                        too
  auth                                  Manage authentication
  auto-mode                             Inspect or reset auto mode classifier
                                        configuration
  doctor                                Check the health of your Claude Code
                                        installation. Reads settings files in
                                        the current directory without a trust
                                        prompt. For a full checkup that can also
                                        fix issues, run /doctor in a session.
  gateway [options]                     Run the enterprise auth/telemetry
                                        gateway
  import [options] [source]             Import config from another AI coding
                                        agent into Claude Code
  install [options] [target]            Install Claude Code native build. Use
                                        [target] to specify version (stable,
                                        latest, or specific version)
  logs <id|name>                        Print a background session's recent
                                        terminal output
  mcp                                   Configure and manage MCP servers
  plugin|plugins                        Manage Claude Code plugins
  purge [options] [path]                Delete all Claude Code state for a
                                        project (transcripts, tasks, file
                                        history, config entry)
  respawn [options] [id]                Restart a background session, or all of
                                        them with --all, so it runs the current
                                        Claude Code version
  rm <id>                               Delete a background session, and its
                                        worktree when that is safe. Works on
                                        sessions that have already exited
  setup-token                           Set up a long-lived authentication token
                                        (requires Claude subscription)
  stop|kill <id>                        Stop a background session. Its
                                        conversation is kept: `claude attach
                                        <id>` opens it again, `claude --resume`
                                        works once it is stopped
  ultrareview [options] [target]        Run a cloud-hosted multi-agent code
                                        review of the current branch (or a PR
                                        number / base branch) and print the
                                        findings
  update|upgrade                        Check for updates and install if
                                        available
```

Flags that matter for a one-shot headless run. "Help" means the flag is listed in `--help`; "hidden" means it is not listed but this version accepts it.

| Flag | In 2.1.301 | Observed behaviour / notes |
| :- | :- | :- |
| `-p`, `--print` | exists (help) | Headless. Help: "The workspace trust dialog is skipped when Claude is run in non-interactive mode ... Settings files that fail validation are silently ignored in this mode". All probes used it. |
| `--output-format text\|json\|stream-json` | exists (help) | `json` prints one JSON object on stdout (§6). `stream-json` without `--verbose` gives exit 1 and stderr `Error: When using --print, --output-format=stream-json requires --verbose` [f9-streamjson-noverbose]. |
| `--input-format text\|stream-json` | exists (help) | Not probed. |
| `-r`, `--resume [value]` | exists (help) | Takes a session id **or a session title** [p13-resume-bad]. See §7. |
| `-c`, `--continue` | exists (help) | Continues the most recent session in the cwd [g4-continue]. With no prior session in the cwd it silently starts a new one, exit 0 [g6-continue-empty-cwd]. |
| `--fork-session` | exists (help) | Works with `--resume`; returns a new id (§7). |
| `--session-id <uuid>` | exists (help) | Chooses the id for a new session, or for the fork (§7). |
| `--model <model>` | exists (help) | The default is `claude-opus-5-5` (request body). `--model sonnet` sends `claude-sonnet-5-5` [f4-model-sonnet]. An unknown name is still sent, after stderr `[claude-code:unrecognized_model] {"model":"claude-made-up-9","query_source":"sdk"}`; with an unknown model the effort sent became `high` [f4b-model-full]. |
| `--permission-mode <mode>` | exists (help) | Help choices: `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`. `default` is **also accepted** (hidden alias) [f2-perm-default]. `manual` is accepted [f2b]. A bad value gives exit 1 and stderr `error: option '--permission-mode <mode>' argument 'bogus' is invalid. Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.` [f2d]. The repo enum `ClaudePermissionMode` has `default` but no `manual`. |
| `--permission-prompts host\|none` | exists (help) | The default is `host`. `none` denies anything that would prompt. Not probed. |
| `--allowedTools` / `--allowed-tools`, `--disallowedTools` / `--disallowed-tools`, `--tools` | exist (help) | Not probed (the stand-in never asked for a tool). |
| `--max-turns <n>` | exists (**hidden**) | Accepted; exit 0 [f1-max-turns]. Documented in cli-reference ("Exits with an error when the limit is reached"). |
| `--max-budget-usd <amount>` | exists (help) | Gives exit 1 with `subtype: "error_max_budget_usd"` after the first call passes the cap (§6) [f7-budget]. |
| `--append-system-prompt <text>` | exists (help) | |
| `--append-system-prompt-file <path>` | exists (**hidden**) | Accepted [f6-sysprompt-file]. |
| `--system-prompt <text>` | exists (help) | Replaces the third system block. The body's system blocks became `[billing header, "You are a Claude agent, built on Anthropic's Claude Agent SDK.", "CUSTOM-SYSTEM-PROMPT"]`. The CLAUDE.md context was still sent as a user-side reminder [f6b-sysprompt]. |
| `--system-prompt-file` | mentioned in the `--bare` help text | Not probed. |
| `--system-prompt-snapshot on\|off` | exists (help) | On by default: the prompt is recorded on the first request and reused on every resume (see §7). |
| `--setting-sources <list>` | exists (help) | Values `user`, `project`, `local`, comma-separated. **An empty string `""` is accepted and loads none** [e4, s9]. This is the flag that blocks workspace settings (§8). |
| `--settings <file-or-json>` | exists (help) | Sits above project settings: its `env` pin beat a workspace `env` value [e10]. |
| `--bare` | exists (help) | Sets `CLAUDE_CODE_SIMPLE=1`. Leaves 3 tools (`Bash`, `Edit`, `Read`), no `Skill` tool and no CLAUDE.md [s2]. **Does not block the workspace `env` block** [e3]. Ignores `CLAUDE_CODE_OAUTH_TOKEN`, a stored login and a project `apiKeyHelper` [a6, k3]. |
| `--plugin-dir <path>` | exists (help) | Repeatable. A folder with or without `.claude-plugin/plugin.json` loads; its skills are listed as `<plugin-name>:<skill>` [s3, s5]. |
| `--add-dir <dirs...>` | exists (help) | Loads `<dir>/.claude/skills` [s6]. |
| `--mcp-config`, `--strict-mcp-config` | exist (help) | `--strict-mcp-config` stopped the workspace `.mcp.json` server from starting [m3]. |
| `--no-session-persistence` | exists (help) | Writes no transcript; a later `--resume` of that id fails [g1, g2]. |
| `--effort low\|medium\|high\|xhigh\|max` | exists (help) | Sent as `output_config.effort` [f3: `{'effort': 'xhigh'}`]. The default sent is `medium` (for `claude-opus-5-5`). |
| `--fallback-model`, `--betas`, `--json-schema`, `--agents`, `--agent` | exist (help) | Not probed. `--betas` is "API key users only". |
| `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions` | exist (help) | Not probed. `--permission-mode bypassPermissions` was accepted [f2c]. |
| `--restricted`, `--safe-mode`, `--disable-slash-commands` | exist (help) | `--restricted` blocked the workspace env [e8]. `--safe-mode` did **not** [e9]. `--disable-slash-commands` removes every skill and the `Skill` tool (21 tools) [s10]. |
| `-d`, `--debug [filter]`, `--debug-file <path>` | exist (help) | `--debug-file` writes a detailed log, including which files and skills were loaded. It is the best diagnostic. |
| Flags that move config or session storage | **absent** | There is no flag for this. Use the env vars `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_PROJECT_DIR_NAME` (docs; §4). |

All 11 values of the repo's `ClaudeCliFlag` (`file`, `restricted`, `autocompact`, `name`, `agent`, `bare`, `safe-mode`, `no-session-persistence`, `worktree`, `plugin-url`, `permission-prompts`) appear in this help text.

## 3. Authentication

### 3.1 Documented precedence
From https://code.claude.com/docs/en/authentication ("Authentication precedence"):

> When multiple credentials are present, Claude Code chooses one in this order:
> 1. Cloud provider credentials, when `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, or `CLAUDE_CODE_USE_FOUNDRY` is set. ...
> 2. `ANTHROPIC_AUTH_TOKEN` environment variable. Sent as the `Authorization: Bearer` header. ...
> 3. `ANTHROPIC_API_KEY` environment variable. Sent as the `X-Api-Key` header. ... In interactive mode, you are prompted once to approve or decline the key, and your choice is remembered. ... **In non-interactive mode (`-p`), the key is always used when present.**
> 4. `apiKeyHelper` script output. ...
> 5. `CLAUDE_CODE_OAUTH_TOKEN` environment variable. ...
> 6. Anthropic profile and federation credentials ... A profile that `ant auth login` wrote ranks here only when you name it in `ANTHROPIC_PROFILE`; otherwise it ranks below `/login`.
> 7. Subscription OAuth credentials from `/login`.

The same page: "A signed-in Claude apps gateway session sits outside this list ... When a gateway session exists, the CLI authenticates with the gateway token ..."; and "If you've set the `CLAUDE_CONFIG_DIR` environment variable, Claude Code keeps the `.credentials.json` file under that directory instead". It also says "On Windows, credentials are stored in `%USERPROFILE%\.claude\.credentials.json`". Profiles live in `%APPDATA%\Anthropic` on Windows, **outside** `CLAUDE_CONFIG_DIR`, and "Claude Code doesn't read profiles or federation variables in bare mode". https://code.claude.com/docs/en/authentication

`apiKeyHelper`: "Claude Code runs the command through the system shell, `/bin/sh` on macOS and Linux and `cmd` on Windows, and sends its output as both the `X-Api-Key` and `Authorization: Bearer` headers. ... In interactive sessions, when the command comes from project or local settings, Claude Code doesn't run it until you accept the workspace trust prompt." https://code.claude.com/docs/en/settings-reference#apikeyhelper

### 3.2 Observed (fake values, stand-in, fresh config dir each run)

| Probe | Credentials given | Header the stand-in saw | Result |
| :- | :- | :- | :- |
| p02-base | `ANTHROPIC_API_KEY` | `x-api-key=probe`, no `authorization` | success |
| a1 | API key + `CLAUDE_CODE_OAUTH_TOKEN` | `x-api-key=probe` only | the API key wins |
| a2 | `CLAUDE_CODE_OAUTH_TOKEN` only | `authorization: Bearer <oauth>`, no `x-api-key` | success |
| a3 | API key + `ANTHROPIC_AUTH_TOKEN` | **both**: `x-api-key=probe` and `Bearer <authtok>` | success; which header the real API honours is **unverified** |
| a4 | fake stored login (`<config>/.credentials.json`) + API key | `x-api-key=probe` only | **the env key beats a stored login in `-p`** |
| a5 | fake stored login only | `Bearer <oauth>`, plus one `CONNECT api.anthropic.com:443` (refused by the proxy trap) | success. The stored-login path calls api.anthropic.com directly, not the base URL. |
| a6 | `CLAUDE_CODE_OAUTH_TOKEN` + `--bare` | none | exit 1, `result: "Not logged in · Please run /login"` |
| k1 | API key + workspace `apiKeyHelper` | **both**: `x-api-key=probe` and `Bearer <helper output>`; the helper ran | success (§8) |
| k2 | workspace `apiKeyHelper` only | `x-api-key=helper`, `Bearer helper` | success |

The other headers on every request, by name only: `accept, accept-encoding, anthropic-beta, anthropic-dangerous-direct-browser-access, anthropic-version (2023-06-01), connection, content-length, content-type, host, user-agent ("claude-cli/2.1.301 (external, sdk-cli)"), x-api-key, x-app ("cli"), x-claude-code-session-id (= the session id), x-stainless-*` [A.log.jsonl #3]. Path: `POST /v1/messages?beta=true`, and **no other endpoint**: across all 103 CLI requests the stand-ins saw no `/v1/models` and no `count_tokens` call [all logs].

**Conclusion for the design.** With `-p`, `ANTHROPIC_API_KEY` in the child env beats a stored `/login` (docs + a4), so a private config dir is **not** needed to make the key win. It is still needed for other reasons: sessions, skills, and keeping the user's `~/.claude` untouched (§4, §5). Three things the child env must **not** carry, because each of them outranks or joins the caller's key: `ANTHROPIC_AUTH_TOKEN` (outranks it, sent alongside), `CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY` (outrank it), and `ANTHROPIC_PROFILE`/federation variables (docs). A workspace can also inject a credential (§8).

## 4. Where state lives

Observed after one `-p` run with a fresh `CLAUDE_CONFIG_DIR=cfg01` and a scratch `USERPROFILE=home01` [p01-nested]:

```text
cfg01/.claude.json                         719 bytes (firstStartTime, machineID, userID, migration flags, pluginUsage; no credentials)
cfg01/backups/.claude.json.backup.<ms>
cfg01/projects/C--Users-422mi-AppData-Local-Temp-claude-C--Users-422mi-vidbyte-repos-c726d777-284c-4c17-9776-72f9da8a13f9-scratchpad-claude-vendor-probe-ws01/<session-id>.jsonl   273,337 bytes
cfg01/projects/<same key>/memory/          (empty)
cfg01/sessions/                            (empty)
home01/                                    (empty: nothing written to the home folder)
ws01/                                      (empty: nothing written to the workspace)
```

- **`CLAUDE_CONFIG_DIR` relocates** the global config file (`<dir>/.claude.json`, not `~/.claude.json`), the transcripts (`<dir>/projects/<key>/<id>.jsonl`), user settings (`<dir>/settings.json`, per the debug log), user skills (`<dir>/skills`), agents, commands, output-styles, plugins, backups and the auto-memory folder [p02 debug log]. The doc says credentials move too (`<dir>/.credentials.json`; a4/a5 confirmed the CLI reads a stored login from there). Docs: "All settings, session history, and plugins are stored under this path" (https://code.claude.com/docs/en/env-vars).
- **Real-home check.** Two runs used the real `USERPROFILE` with a scratch `CLAUDE_CONFIG_DIR` [h1, h2]. Before and after, `~/.claude.json` (mtime 18:28:57.299), `~/.claude/.credentials.json` (17:25:15.810), `~/.claude/settings.json` and `~/.claude/projects/` (7 entries, none for the scratch workspace) were unchanged. Their debug logs contain no path under `C:\Users\422mi\.claude`. **It does not escape:** `CLAUDE_CONFIG_DIR` alone keeps a run out of the user's `~/.claude` and `~/.claude.json` (the one exception is the read-only CLAUDE.md ancestor walk in §5).
- **Session files are keyed by the cwd.** The key is the absolute cwd path with every non-alphanumeric character replaced by `-` (`C:\Users\...\ws01` → `C--Users-...-ws01`), under the config dir. Docs: `CLAUDE_CODE_PROJECT_DIR_NAME` "Set together with `CLAUDE_CONFIG_DIR` to choose the `projects/` directory name ... in place of one derived from the working directory path ... reads it only from the environment ..., never from a settings file `env` block" (https://code.claude.com/docs/en/env-vars; **not probed**).
- **Resume from a different cwd, same config dir: found.** It continues under the same id, appends to the original file under the original cwd key, and records the new cwd on the new lines. The recorded system prompt still says the *original* `Primary working directory` because of the system-prompt snapshot [p07-resume-other-cwd; body A-008]. Docs: "When you pass a session ID, Claude Code searches the current project directory and its git worktrees, then every other project on this machine" (cli-reference).
- **Resume with a different config dir: not found.** Exit 1, stderr `No conversation found with session ID: c3f73f50-...` [p08-resume-other-cfg]. **Continue and fork must reuse the config dir of the run that created the thread.**
- A failed run still writes a transcript and returns a resumable `session_id` (the 401 run wrote `564ebdfc-....jsonl`) [p16].
- Transcript lines carry `type` ∈ {`queue-operation`, `user`, `attachment`, `assistant`, `api-request*`, `last-prompt`, `cost-state`, `mode`, ...}, with `cwd`, `sessionId`, `version` and `entrypoint` on message lines [cfg02 transcript]. Transcripts are plain text. Docs: "If a tool reads a `.env` file or a command prints a credential, that value is written to `projects/<project>/<session>.jsonl`" (https://code.claude.com/docs/en/claude-directory).
- **Retention:** `cleanupPeriodDays` defaults to `30`; "The sweep deletes transcripts without showing a message" (https://code.claude.com/docs/en/settings-reference#cleanupperioddays). A thread id older than 30 days stops resuming unless the private config dir's `settings.json` raises this value.
- Four parallel runs sharing one config dir and one cwd all succeeded, each with its own session [par1–par4]. Two concurrent runs on the **same** session id were not tested (**unverified**).

## 5. Skills

Locations, from https://code.claude.com/docs/en/skills ("Where skills live"): personal `~/.claude/skills/<name>/SKILL.md` (that is, `<CLAUDE_CONFIG_DIR>/skills`), project `.claude/skills/`, nested `<subdir>/.claude/skills/`, `--add-dir` `<dir>/.claude/skills/`, and plugin `<plugin>/skills/<name>/SKILL.md` ("as `/plugin-name:skill-name`"). "Claude Code loads project skills from `.claude/skills/` in the directory where you start it and in every parent directory up to the repository root". "In a session running in a linked git worktree ... when the worktree checkout has no `.claude/skills` directory at its root, Claude Code loads the main checkout's project skills instead." "A `<skill-name>` entry in the enterprise, personal, or project location can be a symlink".

Observed. The debug log line `Loading skills from: managed=..., user=<cfg>\skills, project=[...]` shows the sources, and the request body's skill listing ("The following skills are available for use with the Skill tool: - name: description") shows what the model sees:

| Probe | Setup | Probe skills in the listing | Other things loaded |
| :- | :- | :- | :- |
| s1 | `<cfg>/skills/probe-skill` | `probe-skill` | with a **scratch** home, the ancestor `C:\Users\422mi\.claude\skills` loaded as *project* skills (65 of them) |
| h2 (real home) | default sources | — | `project=[]`: the real home's `~/.claude/skills` is **not** walked into when it is the real home |
| s2 | `--bare` | none (tools = `Bash, Edit, Read`; no `Skill` tool) | — |
| s3 / s5 | `--plugin-dir` with / without manifest | `probe-plugin:plugin-skill` / `bare-plugin:plugin-skill` | the plugin name is the manifest `name`, else the folder name |
| s4, s7 | `--bare` + `--plugin-dir` / `--add-dir` | none listed. The debug log shows them *loaded* ("1 skill dir commands, 1 plugin skills"), but there is no `Skill` tool | a prompt `/adddir-skill do it` **does** expand the skill body [s7c] |
| s6 | `--add-dir <dir>` | `adddir-skill` (unqualified) | — |
| s8 | `--setting-sources user` | `probe-skill` only | no project or ancestor skills, no CLAUDE.md |
| s9 | `--setting-sources ""` | **none** (user skills in `<cfg>` dropped too) | — |
| s10 | `--disable-slash-commands` | none; `Skill` tool removed (21 tools) | CLAUDE.md still loaded |
| s11 | cwd = git repo `gitparent/repo` | `repo-skill`; **not** `ancestor-skill` from above the repo root | the ancestor `~/.claude/CLAUDE.md` still loaded |
| s12 | `--setting-sources user --plugin-dir P` | `probe-skill`, `probe-plugin:plugin-skill` | nothing from the workspace or its ancestors |
| j1 | `<cfg>/skills/junction-skill` = **NTFS junction** to another skill folder, `--setting-sources user` | listed as `junction-skill (ancestor-skill)` | a junction works; the folder name is the command name and the frontmatter `name` is shown in parentheses |
| c1 / c2 | workspace `.claude/skills/probe-skill-ws` + `CLAUDE.md`, default / `--setting-sources user` | present / **absent** | workspace CLAUDE.md present / **absent** |

**CLAUDE.md ancestor walk (finding).** CLAUDE.md files are read from **every ancestor of the cwd, past the git root**, and an ancestor's `.claude/CLAUDE.md` counts. So `C:\Users\422mi\.claude\CLAUDE.md` (the user's personal file) was sent as `Contents of C:\Users\422mi\.claude\CLAUDE.md (project instructions, checked into the codebase)`, even with a scratch `CLAUDE_CONFIG_DIR`. That held with a real home (h2) and inside a git repo (s11). Only `--setting-sources user` (or `""`), `--bare` or `--safe-mode` (docs) stopped it [s8, s2, h1].

**How to show exactly a given set of skill folders for one run, without writing into the workspace (verified).** Use a private `CLAUDE_CONFIG_DIR` whose `skills/` holds the caller's skill folders (copied, or as junctions), plus `--setting-sources user` [s8, j1]. An alternative or addition is `--plugin-dir <folder>` per skill bundle; those skills are listed as `<plugin>:<skill>` [s12]. Do not use `--bare`: the model gets no `Skill` tool, so it can neither see nor invoke the skills [s2, s4, s7]. Do not use `--setting-sources ""`: it drops the config dir's skills [s9].

## 6. Headless output (`-p --output-format json`)

**Success** [p02-base], one line on stdout, exit 0:
```json
{"duration_api_ms":15,"stop_reason":"end_turn","session_id":"c3f73f50-b50c-4f3a-8369-f97267313173","total_cost_usd":0.00014000000000000001,"usage":{"input_tokens":10,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":5,"output_tokens_details":{"thinking_tokens":0},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":0},"inference_geo":"","iterations":[],"speed":"standard","fallback_credit":null},"modelUsage":{"claude-opus-5-5":{"inputTokens":10,"outputTokens":5,"cacheReadInputTokens":0,"cacheCreationInputTokens":0,"webSearchRequests":0,"costUSD":0.00014000000000000001,"contextWindow":1000000,"maxOutputTokens":128000,"thinkingTokens":0,"canonicalModel":"claude-opus-5-5","provider":"firstParty","costBasis":"list"}},"permission_denials":[],"terminal_reason":"completed","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subagent_stats":{...},"safety_stops":0,"is_error":false,"num_turns":1,"subtype":"success","api_error_status":null,"result":"stand-in answer A #4","ttft_ms":...,"type":"result","duration_ms":...,"uuid":"...","ttft_stream_ms":...,"time_to_request_ms":...,"first_content_frame_ms":...,"queued_turn_count":0,"result_index":0}
```
Success keys: `api_error_status, duration_api_ms, duration_ms, fast_mode_disabled_reason, fast_mode_state, first_content_frame_ms, is_error, modelUsage, num_turns, permission_denials, queued_turn_count, result, result_index, safety_stops, session_id, stop_reason, subagent_stats, subtype, terminal_reason, time_to_request_ms, total_cost_usd, ttft_ms, ttft_stream_ms, type, usage, uuid`. `result` is the final answer text; `session_id` is the thread id.

**Errors inside the run.** These give exit 1 and **still** print a JSON object on stdout, with an empty stderr:

| Case | Probe | Key fields |
| :- | :- | :- |
| 401 `authentication_error`, `CLAUDE_CODE_MAX_RETRIES=0` | p16 | `is_error: true`, **`subtype: "success"`**, `api_error_status: 401`, `terminal_reason: "api_error"`, `result: "Invalid API key · Fix external API key"`, `stop_reason: "stop_sequence"`, `num_turns: 1`, `session_id` present, `modelUsage: {}`, `total_cost_usd: 0` |
| 401, default retries | p15 | the same JSON after **184.5 s**: 11 requests (1 + 10 retries) with exponential backoff growing to about 35–40 s between attempts; nothing on stdout or stderr until then. p14 was killed by its 180 s timeout with **empty stdout** |
| no credential (`--bare` with only an OAuth env token or a project helper; `--setting-sources user` with only a project helper) | a6, k3, k4 | `is_error: true`, `subtype: "success"`, `api_error_status: null`, `terminal_reason: "api_error"`, `result: "Not logged in · Please run /login"` |
| `--max-budget-usd` exceeded | f7 | `is_error: true`, `subtype: "error_max_budget_usd"`, `terminal_reason: "budget_exhausted"`, `errors: ["Reached maximum budget ($0.00001)"]`, **no `result` key**, `total_cost_usd: 0.00014` |

So `subtype` is **not** a success signal. Use `is_error`, then `api_error_status` / `terminal_reason` / `errors`. Strings are UTF-8 (the `·` is bytes `c2 b7`).

**Errors before the run.** These give exit 1, **empty stdout**, and plain text on stderr:

| Case | Probe | stderr (verbatim) |
| :- | :- | :- |
| unknown session id (also with `--fork-session`) | p05, g5 | `No conversation found with session ID: 11111111-2222-4333-8444-555555555555` |
| `--resume` with a value that is neither a UUID nor a title | p13 | `Error: --resume requires a valid session ID or session title when used with --print. Usage: claude -p --resume <session-id\|title>. Provided value "not-a-uuid" is not a UUID and does not match any session title.` |
| `--session-id` not a UUID | p12 | `Error: Invalid session ID. Must be a valid UUID.` |
| `--session-id` already used | p10 | `Error: Session ID aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee is already in use.` |
| empty prompt and no stdin | q5 | `Error: Input must be provided either through stdin or as a prompt argument when using --print` |
| prompt starting with `--` | q2 | `error: unknown option '--help me'` / `(Did you mean --help?)` (exit 1 after 0.14 s) |
| bad `--permission-mode` | f2d | see §2 |

**stderr on success is not always empty.** With a non-Anthropic base URL every run printed `We're changing auto mode to no longer charge for classifier requests ... your requests go through 127.0.0.1:62235, which isn't compatible with this update. ...` [p01]. An unknown model adds `[claude-code:unrecognized_model] ...` [f4b]. With an open, silent stdin pipe it adds `Warning: no stdin data received in 3s, proceeding without it. ...` [q8]. Parse stdout only, and treat stderr as diagnostics.

**Passing the prompt.**
- As an argument: newlines, `é`, `✓`, double quotes and backslashes arrived intact through a Python `subprocess` argv list on Windows [q6, body A-052].
- On stdin with no argument: works; a 40,000-character prompt via stdin arrived whole [q1, q7]. The Windows command-line limit (32,767 chars) makes stdin the safe route for long prompts (the limit is general Windows knowledge, not probed with claude).
- **With both an argument and stdin data, the CLI joins them** as `ARG-PART\nSTDIN-PART` [q4]. With stdin an open pipe that never closes, it waits **3 s**, warns, then proceeds [q8]. So pass `stdin=DEVNULL` with an argument prompt, or put the prompt only on stdin.
- A prompt beginning with `--` must come after `--` (end of options): `claude -p --output-format json -- "--help me"` works [q3].
- A prompt beginning with `/name` is treated as a skill or command invocation (s7c). (Git Bash rewrites a leading `/word` argument into `C:/Program Files/Git/word` unless `MSYS_NO_PATHCONV=1` is set; this affects only test scripts run from Git Bash, not a Python `subprocess`.)

## 7. Continue and fork

| Probe | Command (plus `-p ... --output-format json`) | Result |
| :- | :- | :- |
| p02 | new | `session_id` c3f73f50-... |
| p03 | `--resume c3f73f50-...` | **same id**; the request carried the full history (5 messages) |
| p04 | `--resume c3f73f50-... --fork-session` | **new id** 467a3e59-...; the request carried the parent's history plus the new prompt; a separate file `467a3e59-....jsonl` was written |
| p06 | `--resume c3f73f50-...` after the fork | same id; the history does **not** contain the fork's turn (the fork is independent) |
| p09 | `--session-id aaaaaaaa-...` (new) | id = `aaaaaaaa-...` |
| p10 | the same `--session-id` again | exit 1, `Error: Session ID ... is already in use.` |
| p11 | `--resume c3f73f50-... --fork-session --session-id 99999999-...` | the fork gets **the chosen id** `99999999-...` |
| p05, g5 | `--resume <unknown uuid>` (with or without `--fork-session`) | exit 1, empty stdout, stderr `No conversation found with session ID: <id>` |
| g1, g2 | `--no-session-persistence` then `--resume` | no `.jsonl` written; the resume fails with "No conversation found" |
| p07 / p08 | resume from another cwd / another config dir | found / not found (§4) |

The resume header `x-claude-code-session-id` equals the session id on every request [A.log.jsonl]. The system prompt is snapshotted on a conversation's first request and reused on resume, so `--append-system-prompt` / `--system-prompt` text passed on a later resume does not take effect until compaction (cli-reference: "every later request uses that recorded prompt, including after you return to the conversation with `--resume` or `--continue`"). https://code.claude.com/docs/en/cli-reference

## 8. Workspace-supplied configuration (the key-safety risk)

Docs, https://code.claude.com/docs/en/settings-reference#env: "From project and local settings: after you trust the workspace, **or at startup in `-p` mode, which never shows the trust dialog**". The ignore list for project and local `env` covers `CLAUDE_CONFIG_DIR`, `HOME`/`TMP`/`TEMP`, the Windows system variables, OTEL exporter variables and a few others; **`ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` are not on it**. Docs, https://code.claude.com/docs/en/permissions ("What runs before you trust a folder"), for "`claude -p` or the SDK, folder never trusted": hooks, the `env` block and helper commands such as `apiKeyHelper`: "Used"; servers in `.mcp.json`: "Connected without asking, approved or not". The same page lists the mitigations: "Pass `--setting-sources user` ... so Claude Code reads neither the project's settings files nor its `.mcp.json`" and "Start with `--bare` ... **The project's `env` block and helpers such as `awsAuthRefresh` in its settings files still apply**, and Claude Code reads `apiKeyHelper` only from `--settings`".

Observed. The workspaces held `.claude/settings.json` (or `.claude/settings.local.json`) with an `env` block, `hooks` (SessionStart, UserPromptSubmit, Stop → `hook.py`, which records the event and the *class* of `ANTHROPIC_API_KEY` it sees), and/or `apiKeyHelper`. "C" is a second stand-in that only a workspace setting could point to.

| Probe | Workspace content | Flags | Where the caller's key went | Hooks / helper / MCP |
| :- | :- | :- | :- | :- |
| e1 | settings.json: `env.ANTHROPIC_BASE_URL=C`, `VIDBYTE_PROBE_ENV=1`, hooks | — | **to C** (`x-api-key=probe` at C) | hooks ran ×3, **with the caller's key** and `VIDBYTE_PROBE_ENV=1` in their env |
| e6 | the same in **settings.local.json** | — | **to C** | hooks ran ×3 |
| e7 | settings.local.json | `--setting-sources user,project` | A (blocked) | none |
| e2 | settings.json | `--setting-sources user` | A (blocked) | none |
| e4 | settings.json | `--setting-sources ""` | A (blocked) | none |
| e3 | settings.json | `--bare` | **to C** (not blocked) | none |
| e5 | settings.json | `--settings '{"disableAllHooks":true}'` | **to C** | none |
| e9 | settings.json | `--safe-mode` | **to C** | none |
| e8 | settings.json | `--restricted` | A (blocked) | none (`--restricted` also removes code-running tools) |
| e10 | settings.json | `--settings '{"env":{"ANTHROPIC_BASE_URL":"<A>"},"disableAllHooks":true}'` | A (the `--settings` pin wins) | none |
| w1 | settings.json `env.ANTHROPIC_API_KEY=sk-ant-wsenv-3333` | — | **the workspace key replaced the caller's key** (`x-api-key=wsenv`) | hooks saw `wsenv` |
| w2 | the same | `--setting-sources user` | caller's key (`probe`) | none |
| k1 | settings.json `apiKeyHelper` (prints `sk-ant-helper-1111`) | — (caller key set) | `x-api-key=probe` **and** `Authorization: Bearer helper` | **the helper ran** (code execution); hooks ran |
| k2 | the same, no caller key | — | `x-api-key=helper` + `Bearer helper` | helper ran |
| k3 / k4 | the same, no caller key | `--bare` / `--setting-sources user` | none → "Not logged in" | helper **not** run |
| m1 | `.mcp.json` stdio server (writes a marker) | — | — | **the MCP server process started (×2) with the caller's key in its env** |
| m2 / m3 | the same | `--setting-sources user` / `--strict-mcp-config` | — | not started |

**Conclusion.** In `-p` mode an untrusted workspace can, with no prompt: send the caller's key to any URL (`env.ANTHROPIC_BASE_URL`), replace the key (`env.ANTHROPIC_API_KEY`), add its own bearer credential (`apiKeyHelper`), and run code that sees the key (hooks, `apiKeyHelper`, `.mcp.json` stdio servers). **`--setting-sources user`** (with the private config dir as the "user" source) blocked every one of these in the probes, for both `settings.json` and `settings.local.json`. `--setting-sources ""` and `--restricted` also block them. **`--bare`, `--safe-mode` and `--settings '{"disableAllHooks":true}'` do not** block the env redirect. Cost of `--setting-sources user`: the workspace's own `CLAUDE.md`, `.claude/skills`, `.claude/agents`/`commands` and `.mcp.json` are not loaded [c2, s8, m2], so the model does not see the repo's instructions unless the SDK passes them some other way (e.g. `--append-system-prompt`; **not probed**). Pinning individual keys through `--settings` works for the keys pinned [e10], but every unpinned variable (e.g. `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS`, `CLAUDE_CODE_USE_BEDROCK`) remains open, and those were **not probed**.

## 9. Nested-session and environment quirks

- **No nested-session refusal.** `CLAUDECODE=1` + `CLAUDE_CODE_ENTRYPOINT=cli` [p01-nested], `CLAUDE_CODE_CHILD_SESSION=1` + `CLAUDECODE=1` [n1, n1b], and this agent's **whole** environment (except the real key and the messaging pipe variables) [n4-inherit-full-env] all ran normally, persisted the transcript, and resumed. Docs on `CLAUDE_CODE_CHILD_SESSION`: "A nested interactive `claude` TUI started this way is automatically excluded from `--resume`, `--continue` ... **Non-interactive `claude -p` sessions still persist.**" https://code.claude.com/docs/en/env-vars
- Inherited `CLAUDE_CODE_SESSION_ID=<uuid>` did **not** make the child reuse that id (it got a fresh id) [n2]. Inherited `CLAUDE_EFFORT=xhigh` did **not** change the effort sent (`medium`) [n3]. In docs, both are output variables that Claude Code sets for its subprocesses.
- Variables in a Claude Code parent env that the child should drop (none caused a failure, but they belong to the parent): `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_SESSION_ATTENDED`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_PID`, `CLAUDE_EFFORT`, **`CLAUDE_CODE_MESSAGING_SOCKET` + `CLAUDE_CODE_MESSAGING_TOKEN`** (a named pipe and token into the *parent* session; the probes always removed them, so their effect on a child is **unverified**; each child opens its own `\\.\pipe\LOCAL\cc-msg-<hex>` per its debug log), and **`CLAUDE_CONFIG_DIR`** (this agent's own env had `CLAUDE_CONFIG_DIR=C:\Users\422mi\.claude-work`, so a child that inherits it shares the parent's config dir). Also strip `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` from the parent before setting the caller's key (§3). The parent here also carries a real `ANTHROPIC_API_KEY` and a `VIDBYTE_API_KEY`.
- **Set for a clean child:** `DISABLE_AUTOUPDATER=1` (or `DISABLE_UPDATES=1`) so a call never self-updates, and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. With it, the debug log shows `[Bootstrap] Skipped: Nonessential traffic disabled` and `[servedCatalog] off (essential_traffic)`, and across all ~80 probe runs that authenticated with an env key the proxy trap saw **zero** outbound `CONNECT`s (the only one came from the stored-login run a5). Without it, the outbound traffic was **not probed** (doc list: auto-updates, telemetry, error reporting, release notes, feature flags). Consider `CLAUDE_CODE_MAX_RETRIES` (default 10) because of the ~3-minute 401 retry loop (§6).
- **First run in an empty config dir:** no onboarding, login or trust prompt in `-p`. It creates `.claude.json` (several atomic rewrites; the debug log shows one harmless `[ERROR] Failed to save config with lock: ... ENOENT ... .claude.json` before the file exists) and answers in about 1–2 s [p01, p02].
- With a non-first-party base URL the CLI disables ToolSearch (`[ToolSearch:optimistic] disabled: ANTHROPIC_BASE_URL=... is not a first-party Anthropic host`), and claude.ai MCP connectors are off with API-key auth (`[claudeai-mcp] Disabled: API-key auth precedence active`) [p02 debug log].
- Two built-in plugins always load (`cc-plugin-agents-md@builtin`, `cc-plugin-plugin-authoring@builtin`) and register hook modules even under `--setting-sources user`; they are not settings-file hooks [debug logs].
- The default request: `model: claude-opus-5-5`, `max_tokens: 128000`, `thinking: {"type":"adaptive","display":"omitted"}`, `output_config: {"effort":"medium"}`, 22 tools (`Agent, Bash, CronCreate, CronDelete, CronList, Edit, EnterWorktree, ExitWorktree, Glob, Grep, ListAgents, NotebookEdit, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, TaskStop, WebFetch, WebSearch, Workflow, Write`), and a system block `x-anthropic-billing-header: cc_version=2.1.301.<x>; cc_entrypoint=sdk-cli;` [body A-003].

## 10. Gaps

1. **Real Anthropic API behaviour** (all probes used a stand-in): which header wins when both `x-api-key` and `Authorization: Bearer` are sent (a3, k1); real model-not-found, 429/529 and billing errors and their JSON; whether the auto-mode stderr notice appears against api.anthropic.com. *Needs:* one run with a real throwaway key (out of scope for S0).
2. **The real `/login` precedence on this machine** was not run against the user's own stored login (forbidden). It is covered by the docs ("In non-interactive mode (`-p`), the key is always used when present") and by a4 with a *fake* stored login in a scratch config dir.
3. **Outbound traffic without `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`**: skipped so as not to risk real network calls. *Needs:* a run with the proxy trap and that variable unset.
4. **`CLAUDE_CODE_MESSAGING_SOCKET`/`TOKEN` inherited by a child**: always stripped, so their effect is unknown. *Needs:* a run in a throwaway parent session.
5. **Concurrent resume of the same session id** (two calls on one thread at once): not tested. *Needs:* a stand-in that delays its answer, and two simultaneous `--resume` runs.
6. **Windows `.cmd`/npm shim behaviour**: no shim is installed, so untestable here.
7. **`--max-turns` limit reached**: the stand-in never returns tool calls, so the error JSON shape for this case is unknown (docs: "Exits with an error when the limit is reached"). *Needs:* a stand-in mode that answers with `tool_use`.
8. **Untested vectors in a workspace `env` block when the project source is loaded:** `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS`, `CLAUDE_CODE_USE_BEDROCK`. All moot under `--setting-sources user`.
9. **`CLAUDE_CODE_PROJECT_DIR_NAME`, `--system-prompt-file`, `--input-format stream-json`, `--allowedTools`, `--permission-prompts none`, very long cwd paths (MAX_PATH) in the `projects/` key**: docs-only or untested.
10. **The docs disagree with what was observed for `--bare` + `--add-dir`.** The docs say "Skills in a directory you pass with `--add-dir` still load". Observed: loaded internally but not listed and no `Skill` tool, so only a `/name` prompt reaches them [s7, s7b, s7c].
