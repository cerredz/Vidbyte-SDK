# Refresh SDK Provider Documentation Links

## 1. Overview

The SDK already contains external-contract prose for model, MCP, and tracing
boundaries, but several providers are named without a direct first-party
documentation link. Web-operation clients and durable session stores also have
no colocated external reference surface. This documentation-only change adds
current, first-party links at those boundaries and indexes the new surfaces for
agent-facing repository discovery.

## 2. Goals & Non-Goals

### Goals

- Add a direct official documentation link for every registered model provider.
- Add official protocol and provider links to the existing MCP and trace
  contract READMEs.
- Add colocated external-reference READMEs for web-operation clients and
  session-store providers.
- Record retrieval dates and keep descriptions limited to the external contract
  each directory actually depends on.
- Make the new documentation discoverable from the SDK's agent-facing index.

### Non-Goals

- No runtime, registry, endpoint, pricing, dependency, or configuration change.
- No vendor documentation is copied into the repository.
- No claim that a documentation link verifies live credentials or provider
  behavior.
- No new test files.

## 3. Background & Context

The SDK uses raw HTTP adapters for model and web providers, a protocol client
for MCP, translator objects for tracing backends, and lazy imports for optional
session-store drivers. These seams are defined by vendor or protocol contracts
that change independently of SDK releases. The existing READMEs explain many
of the contracts in the SDK's own words, but link coverage is uneven: provider
names are often cited only as domains, and two provider families have no local
reference file.

## 4. Requirements

1. Use first-party documentation hosts for every link.
2. Keep links adjacent to the provider contract they support.
3. Include all 13 model-provider enum values, all six web-operation clients,
   all four session-store implementations, and all three trace backends.
4. Include the MCP specification and official SDK/reference pages used by the
   client contract.
5. Stamp the retrieval date in each external-reference section.
6. Use project-internal paths only in the agent-facing index and design record;
   external-reference READMEs must remain provider-focused.
7. Preserve existing contract prose and do not change executable files.

## 5. High-Level Design

The change has three documentation layers:

1. Extend the model-provider, MCP, and trace-provider READMEs with direct
   first-party links.
2. Add one external-only README beside the web-operation clients and one beside
   the session-store providers, each with a compact provider matrix.
3. Add an index entry to `llms.txt` so an agent can find each boundary's live
   references before inspecting implementation details.

Each link is paired with a narrow purpose such as API overview, endpoint
reference, authentication, or protocol specification. The link is not treated
   as a vendored copy or as proof that the runtime contract is currently valid.

## 6. Detailed Design

### Model providers

Add first-party links for OpenAI, Anthropic, Gemini, xAI, DeepSeek, GLM/Z.AI,
MiniMax, Kimi/Moonshot, Meta Llama, Mistral, OpenRouter, ElevenLabs, and
PlayAI. Keep the existing endpoint/auth/usage matrix as the local summary and
place the link matrix immediately after it.

### MCP

Add links for the specification, tools capability, transports, and Python SDK
reference. Keep the existing stdio-focused contract and explicitly identify
the areas that remain outside this SDK's implementation scope.

### Trace providers

Add direct links for LangSmith, Langfuse, and Phoenix. Keep the distinction
between the LangSmith `run_type` translator and generic pass-through backends.

### Web-operation clients

Create a README covering Brave Search, Browserbase, Exa, Firecrawl, Parallel,
and Tavily. Link to each provider's API overview and the endpoint documentation
corresponding to the client boundary. Include a note that endpoint/version
compatibility remains a runtime verification concern.

### Session stores

Create a README covering MongoDB, PostgreSQL, SQLite, and Supabase. Link to the
official driver or SQL/reference documentation needed to understand connection,
index, transaction, or table behavior. SQLite is included as the stdlib-backed
provider so the store family is complete.

## 7. Data Model Changes

None. This is a Markdown-only change.

## 8. API Changes

None. No public Python signatures, HTTP routes, protocol messages, or
configuration keys change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/refresh-provider-documentation-links.md` | Design record for the link-only SDK update |
| MODIFY | `vidbyte/providers/README.md` | Add direct links for all registered model providers |
| MODIFY | `vidbyte/tools/mcp/README.md` | Add first-party MCP specification and SDK references |
| MODIFY | `vidbyte/trace/providers/README.md` | Add direct links for trace backends |
| CREATE | `vidbyte/tools/builtins/operations/clients/README.md` | Document web-operation provider references beside the clients |
| CREATE | `vidbyte/lib/providers/README.md` | Document session-store provider references beside the stores |
| MODIFY | `llms.txt` | Index the colocated provider reference surfaces for agents |

No executable files are created, modified, or deleted.

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Model provider APIs | First-party developer/API documentation | Model request, response, modality, and auth contracts | Provider pages and model catalogs change frequently |
| Model Context Protocol | Current specification and Python SDK documentation | MCP tools and stdio protocol contract | Specification revisions can supersede the retrieved revision |
| LangSmith, Langfuse, Phoenix | First-party observability documentation | Trace type and attribute contract | Product docs may split between guides and API references |
| Brave, Browserbase, Exa, Firecrawl, Parallel, Tavily | First-party API documentation | Search, browser, extract, and fetch operation contracts | API versions and beta paths can change |
| MongoDB, PostgreSQL, SQLite, Supabase | First-party database/driver documentation | Session-store connection and persistence contract | Driver and SQL behavior is version-sensitive |

## 11. Rollout & Deployment

- **Feature flags:** None.
- **Breaking change:** No. Runtime behavior is unchanged.
- **Deployment order:** Merge the design record first, then the README/index
  update commit.
- **Verification:** Run `git diff --check`, verify every added URL has a first-
  party host, and run the existing SDK source, package, and full CI stages.
- **Rollback:** Revert the documentation commit; no runtime or data rollback is
  required.

## 12. Open Questions

- [ ] Should a future scheduled link checker validate canonical redirects and
  report stale provider pages?
- [ ] Should provider-specific model catalogs be refreshed in a separate change
  from this link-only update?
- [ ] Should the operation-client README later record verified endpoint versions
  after live funded-provider checks are available?

## 13. Alternatives Considered

### Alternative 1: Add all links only to `llms.txt`

- **What:** Create one central list of provider URLs.
- **Why rejected:** Agents and maintainers inspect provider boundaries in their
  colocated directories; a central list would separate the link from the
  contract it explains.

### Alternative 2: Add one new README for every vendor

- **What:** Create a separate document for every model, web, trace, and store
  provider.
- **Why rejected:** It would multiply maintenance surfaces and duplicate shared
  contract prose. Provider-family READMEs keep the references complete without
  scattering them across dozens of files.

### Alternative 3: Copy vendor documentation into the SDK

- **What:** Vendor or mirror external API pages locally.
- **Why rejected:** It creates licensing and staleness problems. First-party
  links with retrieval dates provide a smaller, auditable boundary reference.

---

END OF DESIGN DOC
