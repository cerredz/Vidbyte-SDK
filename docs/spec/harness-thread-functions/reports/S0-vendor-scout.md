# S0 vendor scout report

Stage: S0 vendor scout, 2026-10-15. Output: `../context/vendor-facts.md`. No commits and no git commands were run. Only these two files were written in the worktree. Scratch work is in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad/` (`probe/`, `scripts/`, `ocskills/`, `musews/`, `musexdg/`, `dl/`).

## What this stage found

Each harness takes a caller key per child process. Grok reads `XAI_API_KEY`, but a stored login beats it, and only an empty private `GROK_HOME` makes the key win. opencode reads one env var per provider (`ZHIPU_API_KEY`, `DEEPSEEK_API_KEY`), but a stored `auth.json` key beats it; an inline config key, `OPENCODE_CONFIG_CONTENT` `provider.<id>.options.apiKey`, beats both. Muse reads `muse exec --api-key-stdin` or `META_API_KEY`, and that env key beats the account login. Per-run skills also work for each harness: Grok through `grok agent --plugin-dir` or ACP `_meta.pluginDirs` (not `grok -p`), opencode through `skills.paths` in `OPENCODE_CONFIG_CONTENT`, and Muse through workspace `.agents/skills` plus `--trust-workspace` or a private `XDG_CONFIG_HOME`.

## Commands run (each with its final lines)

All subprocesses ran with `timeout` and `</dev/null` and with `GIT_TERMINAL_PROMPT=0`.

### Grok
| Command | Final lines |
|---|---|
| `which -a grok; where grok` | `C:\Users\422mi\.grok\bin\grok.exe`, `…\AppData\Roaming\npm\grok(.cmd)` |
| `grok --version` | `grok 1.0.52 (0920c8169e27) [stable]` |
| `grok --help` (saved `probe/grok-help.txt`, 174 lines) | ends with the `wrap` subcommand; no API-key flag |
| `grok agent|login|inspect|setup|sessions|models|usage|plugin --help` (`probe/grok-sub-help.txt`) | `grok agent` has `--plugin-dir <DIR>`, `--always-approve`, `--no-leader`, `--xai-api-base-url` |
| `grok agent stdio|agent headless|sessions list|plugin install|mcp --help` | `agent stdio` takes only `--debug`/`--debug-file` |
| `grep -aoE '(XAI\|GROK)_[A-Z0-9_]+' grok.exe` | `XAI_API_KEY` ×59, `GROK_HOME` ×40, `GROK_CONFIG` ×14, `GROK_DISABLE_API_KEY_AUTH`; no `GROK_API_KEY` |
| `python -I scripts/strings.py grok.exe probe/grok-strings.txt` | 206,213 lines; it contains the embedded user guide |
| `ls ~/.grok`, `ls ~/.grok/docs/user-guide`, `ls ~/.grok/sessions` | no `auth.json` (only `auth.json.lock`); 27 guide files; `session_search.sqlite` |
| `grok --plugin-dir <empty dir> --version` | `error: unexpected argument '--plugin-dir' found` |
| presence checks (`[ -n "${VAR+x}" ]`) | `XAI_API_KEY unset`, `DEEPSEEK_API_KEY set`, `META_API_KEY unset`, `ZHIPU_API_KEY unset`, `OPENCODE_CONFIG* unset` |
| `grep/sed` over `~/.grok/docs/user-guide/{02,05,08,09,11,14,15,17,22,26}-*.md` | the quotes in vendor-facts.md |

### opencode
| Command | Final lines |
|---|---|
| `opencode --version` | `1.18.31` |
| `opencode [run|serve|auth|session|debug|models|export|import|agent] --help` (`probe/opencode-help.txt`) | `run` has `--format json`, `-s`, `-c`, `--fork`, `-m`, `--agent`, `--variant`, `--dir`, `--auto`, `--attach` |
| `opencode debug paths` | `data C:\Users\422mi\.local\share\opencode`, `config C:\Users\422mi\.config\opencode`, … |
| `opencode debug skill` (`probe/oc-skill.txt`) | 151 skills; one `<built-in>` (`customize-opencode`, saved to `probe/oc-customize-skill.md`) |
| `OPENCODE_CONFIG_CONTENT='{"skills":{"paths":["<scratch>/ocskills"]}}' OPENCODE_DISABLE_EXTERNAL_SKILLS=1 opencode debug skill` | 45 skills; last is `vidbyte-probe-skill \| …\scratchpad\ocskills\vidbyte-probe-skill\SKILL.md` |
| `ls ~/.local/share/opencode`, `ls ~/.config/opencode` | `auth.json`, `opencode.db(-shm,-wal)`, `storage/`, `snapshot/`, …; `opencode.jsonc`, `skill/`, `skills/`, … |
| `grep -aoE 'OPENCODE_(AUTH_CONTENT\|…)' opencode.exe` | `OPENCODE_AUTH_CONTENT` ×3, `OPENCODE_CONFIG_CONTENT` ×10, `OPENCODE_PERMISSION` ×5, `OPENCODE_DB` ×7, and the `Auth.all` code that reads `OPENCODE_AUTH_CONTENT` |
| `opencode models zai-coding-plan` / `zai` / `zhipuai-coding-plan` | `Error: Provider not found: …` (no key set) |
| `opencode models deepseek` | `deepseek/deepseek-flash`, `deepseek/deepseek-v4-pro` |
| `ZHIPU_API_KEY=dummy-not-a-key opencode models zai-coding-plan` / `zai` | `zai-coding-plan/glm-4.7 … glm-5.3-highspeed`; `zai/glm-4.5 … zai/glm-4.7-flashx` |
| `gh api repos/sst/opencode` | redirects to `anomalyco/opencode`, default branch `dev`; latest release `v1.19.0` |
| `gh api …/git/trees/v1.18.31?recursive=1` and `…/contents/<path>?ref=v1.18.31` | saved `probe/ocsrc/{run.ts, index.ts (auth), provider.ts, config-src.ts, flag-src.ts}` |
| `curl -s https://models.dev/api.json` (`dl/modelsdev.json`) | `deepseek env=[DEEPSEEK_API_KEY]`, `zai`/`zai-coding-plan`/`zhipuai`/`zhipuai-coding-plan env=[ZHIPU_API_KEY]`, `xai env=[XAI_API_KEY]`, `meta env=[META_MODEL_API_KEY]` |

### Muse
| Command | Final lines |
|---|---|
| `where muse`; `cat ~/.local/bin/muse.cmd` | `wsl.exe -d MuseUbuntu1 -- /usr/local/bin/muse %*` |
| `wsl.exe -l -q` | `Ubuntu`, `MuseUbuntu1` |
| `wsl.exe -d MuseUbuntu1 -e sh -c 'command -v muse; muse --version; …'` | `/usr/local/bin/muse`, `Muse Code 1.0.1 (1.0.1-R2006.1)`, `HOME=/root`, `META_API_KEY unset` |
| `muse --help`, `muse exec|resume|serve|skills|auth|login --help` (`probe/muse-help.txt`, `probe/muse-sub-help.txt`) | `exec --api-key-stdin`, `--session-id <UUID>`, `--json`; `login`: "META_API_KEY always takes priority over the account login." |
| `file /usr/local/bin/muse; head -c 1500 …; grep … launcher; sed -n '101,130p;1029-1135p'` | bash launcher; `exec "$binary" "$@"`; credential path `${MUSE_AUTH_PATH:-$XDG_CONFIG_HOME/muse/auth.json}` |
| `ls -la /usr/local/bin`, `cat .muse-update-checked-at` | `muse-bin-1.0.1-R2006.1`; `.muse-update-checked-at` written at 07:37 by this scout's first `muse --version` |
| `ls ~/.local/share/muse` (WSL) | `local-tracing`, `session-index.db` |
| `python3 -I scripts/strings.py muse-bin-… probe/muse-strings.txt` (inside WSL) | `done`; 8.7 MB |
| `MUSE_NO_AUTO_UPDATE=1 muse skills list --source all --json` (in `/tmp`) | only `bundled:*` skills |
| `muse skills list --source project --workspace <scratch>/musews --json` | `"code": "project-skills-untrusted"` |
| … same with `--trust-workspace` | `"id": "vidbyte-probe-proj", "scope": "project"` |
| `XDG_CONFIG_HOME=<scratch>/musexdg muse skills list --source user --json` | `"id": "vidbyte-probe-user", "path": "$CONFIG_DIR/skills/vidbyte-probe-user/SKILL.md"` |
| `python -I scripts/mspschema.py <earlier run>/muse-1.0.1-msp.schema.json …` | `SessionForkParams` / `SessionForkResult` / `SessionStartParams` / `TurnStartParams` / `ApprovalMode` shapes |

## URLs read
- https://opencode.ai/docs/providers/ (auth.json path, `{env:VAR}`, custom provider; no precedence statement)
- https://opencode.ai/docs/cli/ (run flags, full env var table, serve auth; no JSON event schema)
- https://opencode.ai/docs/permissions/ ("Most permissions default to "allow""; doom_loop and external_directory default to "ask")
- https://opencode.ai/docs/skills/ (discovery paths, frontmatter constraints)
- https://github.com/anomalyco/opencode at tag v1.18.31 (through `gh api`): `packages/opencode/src/cli/cmd/run.ts`, `src/auth/index.ts`, `src/provider/provider.ts`, `src/config/config.ts`, `packages/core/src/flag/flag.ts`
- https://models.dev/api.json
- https://docs.z.ai/devpack/overview, https://docs.z.ai/devpack/tool/others (supported-tool list), https://docs.z.ai/devpack/faq
- https://api-docs.deepseek.com/
- Web search for official Muse Code docs found only third-party pages (withone.ai, codeagentswarm.com, innfactory.ai, developersdigest.tech). None was used as evidence.

## What failed or was not done
- `raw.githubusercontent.com/sst/opencode/dev/…/run.ts` returned 404, because the repo moved to `anomalyco/opencode` and the layout changed on `dev`. The tag `v1.18.31` was fetched through `gh api` instead.
- One heredoc that wrote a markdown draft broke on quoting (a known Git Bash heredoc problem). The file tools were used instead.
- `ctx.py` first failed on cp1252 console encoding; fixed with `sys.stdout.reconfigure`.
- One `sed` call failed (`unknown option -- 2`) because a grep returned an empty line number; it was redone with Python.
- Not run on purpose, because the brief forbids it:
  - any model call;
  - `grok -p`, `opencode run "<prompt>"`, and `muse exec` (including the free `--provider echo` turn that would show the `exec --json` schema);
  - `grok --trust` (writes trust);
  - `grok inspect --json` and `opencode debug config` (they could print secrets from MCP/provider config);
  - reading any `auth.json`.
- **Side effect:** the first `muse --version` ran the launcher without `MUSE_NO_AUTO_UPDATE=1`. The launcher then wrote `/usr/local/bin/.muse-update-checked-at` and may have started a background update check. The installed binary is unchanged (`muse-bin-1.0.1-R2006.1`, `.muse-version` dated Sep 1). Every later muse probe set `MUSE_NO_AUTO_UPDATE=1`.
- opencode starts up by itself even for `debug`/`models` commands: it may refresh its models cache in `~/.cache/opencode` and run its own dependency install in its config dir. No opencode config file was edited.
