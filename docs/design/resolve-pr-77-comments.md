<!-- Context Protocol Header
Description:
    Design document for resolving review comments on PR #77 in the vidbyte-sdk repository.
Purpose:
    Explicate the architecture and strategy to expand and clarify the descriptions of the
    19 built-in memory provider tools, satisfying reviewer feedback before merge.
Architecture:
    Outlines the 19 tool classes across Supermemory, Mem0, Zep, Cognee, and Letta modules.
    Details the specific wording and sentence expansion strategy for model-facing metadata.
Relations:
    Governed by design-doc skill.
    Affects tools in vidbyte/tools/builtins/memory/.
    Complements docs/design/memory-provider-tools.md.
-->

# Design Doc: Resolve PR #77 Review Comments

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-05-28  
**Last Updated:** 2026-05-28  

---

## 1. Overview

This design doc outlines the plan to resolve the review comments on PR #77 in the `vidbyte-sdk` repository. The reviewer requested that all model-facing descriptions for the 19 memory provider tools be made clearer, more descriptive, and follow a specific format: `{Company/Provider Name} is a {description}, use this tool to {description of the core logic/functionality}`. Furthermore, descriptions should be expanded to span at least 4–5 sentences to ensure they provide adequate context for both developers and the language model calling the tools.

---

## 2. Goals & Non-Goals

### Goals

- Rewrite and expand the descriptions of all 19 memory provider tools across Supermemory, Mem0, Zep, Cognee, and Letta.
- Ensure every description follows the format `{Company/Provider Name} is a {description}, use this tool to {core logic/functionality}`.
- Ensure every description spans at least 4 sentences.
- Maintain existing functional logic, parameter schemas, and unit test suites.
- Verify changes using the project's existing tests and the custom verification script.

### Non-Goals

- Adding new memory provider integrations or tools.
- Modifying tool parameter schemas, authentication mechanisms, or URL routes.
- Rewriting the SDK's core execution flow or `BaseMemoryTool` logic.

---

## 3. Background & Context

PR #77 introduces 19 built-in memory tools wrapping five popular managed memory backends. The reviewer noted that the initial descriptions were too brief and vague. Since these descriptions are exposed directly to the LLM agent via `ToolSpec`, detailed and highly informative descriptions are crucial for the model to successfully select and use the correct memory tools. The feedback requires a structured format starting with the provider's definition and expanding on the tool's core actions over 4–5 sentences.

---

## 4. Requirements

### Functional Requirements

1. Every tool's `spec().description` must start with a descriptive sentence about the parent memory provider platform.
2. The description must clearly state what the specific tool does in relation to that platform.
3. Every description must be at least 4 sentences in length.
4. The wording must be professional, informative, and precise.

### Non-Functional Requirements

- **No Breaking Changes**: Modifying descriptions must not impact tool parameters, execution behavior, or API communication.
- **Documentation Integrity**: All files must retain their Context Protocol Headers and inline comments.

---

## 5. High-Level Design

The changes are localized entirely within the `spec()` methods of the 19 tool classes in `vidbyte/tools/builtins/memory/`. No logic or class interfaces are affected. The data flow remains identical: the agent inspects the `ToolSpec` to determine tool capabilities and then calls the tool's `execute()` method.

---

## 6. Detailed Design

### 6.1 Supermemory Tools

**File:** `vidbyte/tools/builtins/memory/supermemory.py`  
**Type:** Modified  

#### What it does
Provides memory tools for the Supermemory v3 platform.

#### Proposed Descriptions

- **SupermemoryAddMemoryTool**:
  "Supermemory is a state-of-the-art managed memory platform that organizes semantic information and temporal context traces. Use this tool to store a new text passage, such as a webpage, conversation snippet, or note, into Supermemory's cloud index. The tool allows optional categorization using container tags to group documents by user or project, and arbitrary metadata key-values for granular filtering. It returns a unique document identifier upon a successful write, which can be stored locally or used for subsequent delete operations." (4 sentences)

- **SupermemorySearchMemoryTool**:
  "Supermemory is a state-of-the-art managed memory platform that organizes semantic information and temporal context traces. Use this tool to perform a semantic search query against the stored documents in the Supermemory index. The search utilizes high-dimensional vector embeddings to retrieve relevant text passages even when exact keyword matches are absent. You can optionally scope the search to a specific container tag, such as a user ID, to restrict the search boundary and control the maximum number of returned excerpts using the limit parameter." (4 sentences)

- **SupermemoryDeleteMemoryTool**:
  "Supermemory is a state-of-the-art managed memory platform that organizes semantic information and temporal context traces. Use this tool to permanently and irreversibly delete a stored document from the Supermemory index using its unique document identifier. Deleting a document immediately removes it from the search index, ensuring future semantic queries will not retrieve its contents or metadata. This tool requires a valid write permission and a non-empty document ID string to execute successfully." (4 sentences)

---

### 6.2 Mem0 Tools

**File:** `vidbyte/tools/builtins/memory/mem0.py`  
**Type:** Modified  

#### What it does
Provides memory tools for the Mem0 platform.

#### Proposed Descriptions

- **Mem0AddMemoryTool**:
  "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. Use this tool to send a list of conversation messages to Mem0 for automatic extraction of key facts, preferences, and long-term context. The extracted facts are dynamically synthesized, resolved against existing memories, and saved under the specified entity scopes such as user ID or agent ID. This allows agents to maintain persistent personalization without manual memory modeling or database management." (4 sentences)

- **Mem0SearchMemoryTool**:
  "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. Use this tool to search for relevant memories using a natural language query under a specific entity scope. The search is executed across the synthesized facts associated with the user, agent, or run, returning ranked matches with similarity scores. This allows the agent to dynamically retrieve relevant personalization context at runtime to guide its responses." (4 sentences)

- **Mem0GetMemoriesTool**:
  "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. Use this tool to retrieve a comprehensive list of all synthesized facts stored for a given user or entity scope. The retrieved memories are returned in a structured list containing their unique identifiers, text values, and timestamp metadata. The tool supports pagination parameters, enabling efficient traversal of large memory histories without overloading the context window." (4 sentences)

- **Mem0DeleteMemoryTool**:
  "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. Use this tool to permanently delete a specific memory entry from the Mem0 platform using its unique memory identifier. Deleting an entry immediately removes that synthesized fact from the entity's profile, preventing it from appearing in subsequent searches or retrievals. This allows agents or users to prune outdated, incorrect, or sensitive facts from their history." (4 sentences)

---

### 6.3 Zep Tools

**File:** `vidbyte/tools/builtins/memory/zep.py`  
**Type:** Modified  

#### What it does
Provides memory tools for the Zep Cloud platform.

#### Proposed Descriptions

- **ZepAddMemoryTool**:
  "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. Use this tool to add new conversation messages to a specific Zep session's memory buffer. The tool automatically handles session creation if the session ID does not already exist on the Zep platform. Added messages are processed asynchronously by Zep to update the session's temporal facts, summary, and memory graph nodes." (4 sentences)

- **ZepGetMemoryTool**:
  "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. Use this tool to retrieve a pre-formatted context string of relevant facts and recent messages for a Zep session. The returned context string is optimized for direct injection into the agent's prompt, providing immediate continuity. You can customize the retrieval by specifying the number of recent messages to include alongside the summarized facts." (4 sentences)

- **ZepSearchMemoryTool**:
  "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. Use this tool to perform a hybrid semantic and graph-based search against a Zep session's memory history. The tool queries the session's memory graph using natural language text, returning ranked excerpts of historical messages and extracted facts. This allows the agent to retrieve precise, long-term context from earlier parts of the conversation." (4 sentences)

- **ZepDeleteSessionTool**:
  "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. Use this tool to permanently and irreversibly delete a Zep session and all of its accumulated conversation history and facts. Deleting a session purges all associated messages, summaries, and graph nodes from Zep's servers, reclaiming storage. Future requests for the same session ID will require a new session creation flow." (4 sentences)

---

### 6.4 Cognee Tools

**File:** `vidbyte/tools/builtins/memory/cognee.py`  
**Type:** Modified  

#### What it does
Provides memory tools for the Cognee knowledge graph platform.

#### Proposed Descriptions

- **CogneeAddTool**:
  "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. Use this tool to ingest unstructured text content into a Cognee dataset to prepare it for knowledge graph construction. The ingested text is staged in Cognee's database under a specific dataset identifier, which defaults to 'default' if not specified. This tool represents the ingestion phase and must be followed by a cognify call to build the graph." (4 sentences)

- **CogneeCognifyTool**:
  "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. Use this tool to trigger the knowledge graph construction process on a previously ingested Cognee dataset. The cognification process extracts entities, complex relationships, and hierarchical facts from the staged raw text, creating a queryable semantic graph. This step is a prerequisite for executing graph-based queries or searches on the ingested data." (4 sentences)

- **CogneeSearchTool**:
  "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. Use this tool to search a Cognee dataset using semantic or graph-completion search modes. The search queries the built knowledge graph, returning structured relationships and facts relevant to the search query. You must ensure that the dataset has been successfully cognified prior to calling this search tool." (4 sentences)

- **CogneeDeleteTool**:
  "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. Use this tool to permanently delete a Cognee dataset and all of its ingested text and generated graph nodes. Deleting the dataset immediately removes all of its associated nodes, edges, and raw chunks from the Cognee server. This is a permanent administrative operation that cannot be undone, reclaiming local or cloud storage." (4 sentences)

---

### 6.5 Letta Tools

**File:** `vidbyte/tools/builtins/memory/letta.py`  
**Type:** Modified  

#### What it does
Provides memory tools for the Letta stateful agent platform.

#### Proposed Descriptions

- **LettaAddArchivalMemoryTool**:
  "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. Use this tool to insert a text passage into a Letta agent's long-term archival memory store. Archival memory acts as an infinite-horizon repository that persists across distinct conversation sessions and agent lifetimes. The stored passage is automatically indexed via vector embeddings, making it discoverable through future semantic search queries." (4 sentences)

- **LettaSearchArchivalMemoryTool**:
  "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. Use this tool to search a Letta agent's archival memory for passages matching a natural language query. The search returns a ranked list of relevant memory passages along with their unique identifiers and text contents. This allows agents to recall precise past facts and interactions on demand during their reasoning loop." (4 sentences)

- **LettaDeleteArchivalMemoryTool**:
  "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. Use this tool to permanently delete a specific archival memory passage from a Letta agent's store using its passage ID. Deleting a passage immediately removes it from the agent's long-term index, ensuring it will not be returned by future search queries. This tool requires both the target agent identifier and the passage identifier to execute." (4 sentences)

- **LettaGetMemoryBlockTool**:
  "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. Use this tool to read the current text value of a named in-context memory block, such as 'persona' or 'human'. In-context blocks represent the active working memory of a Letta agent that is directly appended to the model's system instructions. Reading a block allows the system to inspect the agent's self-concept or known facts about the user." (4 sentences)

---

## 7. Data Model Changes

N/A - No database or schema changes are introduced.

---

## 8. API Changes

N/A - No REST endpoints are modified or introduced.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/resolve-pr-77-comments.md` | This design doc |
| MODIFY | `vidbyte/tools/builtins/memory/supermemory.py` | Refine Supermemory tool descriptions |
| MODIFY | `vidbyte/tools/builtins/memory/mem0.py` | Refine Mem0 tool descriptions |
| MODIFY | `vidbyte/tools/builtins/memory/zep.py` | Refine Zep tool descriptions |
| MODIFY | `vidbyte/tools/builtins/memory/cognee.py` | Refine Cognee tool descriptions |
| MODIFY | `vidbyte/tools/builtins/memory/letta.py` | Refine Letta tool descriptions |

---

## 10. Testing Plan

### Unit Tests
We will verify that the existing unit tests continue to pass successfully. Modifying metadata description strings does not impact tool execution behavior.
- Running `pytest tests/test_memory_tools.py`

### Manual Verification
- Review all descriptions in the code to ensure they perfectly match the detailed format and are at least 4 sentences long.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | N/A | N/A |

---

## 12. Rollout & Deployment

This is a minor additive change resolving PR comments. The changes will be pushed to the PR branch and then reviewed.

---

## 13. Open Questions

- None.

---

## 14. Alternatives Considered

### Alternative 1: Leave descriptions as-is
- Why rejected: Does not resolve the reviewer's explicit feedback and blocks the merge of PR #77.
