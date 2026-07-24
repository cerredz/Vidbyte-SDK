# Static Policy Rules

`typed-mapping-boundary-policy.yml` rejects a function that accepts `object` or
`Any`, checks whether that value is a mapping, and silently returns a fallback
when it is not. In ordinary SDK code, state the required type in the signature
instead; use `Mapping[str, object] | None` when absence is meaningful.

Runtime mapping checks remain legitimate at the audited HTTP, provider, and MCP
wire-format boundaries listed in the rule's path exclusions. Adding an exclusion
requires a documented trust-boundary reason and a fixture example in
`typed-mapping-boundary-policy.py`.

Run locally:

```sh
semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py
semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte
```

Use a narrowly scoped `# nosemgrep: no-untyped-mapping-fallback` only for an
exception that cannot be expressed through the boundary path policy; explain why
next to the suppression.
