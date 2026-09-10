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

`api_key` is the external provider's key, held in memory and sent as an
Authorization header. Token budgets are approximate character-ratio estimates.
See `docs/design/source-context-tools.md` for the full contract.
