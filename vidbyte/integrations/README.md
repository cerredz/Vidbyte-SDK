# `vidbyte.integrations`

`SourceContext` loads one external resource into agent context items.
`SourceTool` builds repository-scoped tools for one external repository.
Both take one plain dictionary (`provider`, `api_key`, `resource`) plus
keyword-only options, and both attach directly to `Agent`:

```python
from vidbyte import Agent, SourceContext, SourceTool

github = {"provider": "github", "api_key": github_token}
context_items = await SourceContext({**github, "resource": "https://github.com/acme/api/pull/41"}, max_tokens=20000).load()
tools = SourceTool({**github, "resource": "https://github.com/acme/api"}, max_output_bytes=50000).build()
agent = Agent(name="reviewer", system_prompt="...", context_items=context_items, tools=tools)
```

`api_key` is the external provider's key, held in memory. GitHub uses the
`gh` CLI through the central `vidbyte.lib.cli.CliRunner` when it is available,
placing the key in `GH_TOKEN`; it falls back to the typed HTTP transport when
the CLI is not installed. Commands and routes are provider-authored and are
never supplied by model input. Token budgets are approximate character-ratio
estimates. See `docs/design/source-context-tools.md` for the full contract.
