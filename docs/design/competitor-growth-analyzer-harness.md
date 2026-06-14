# Design Doc: Competitor Growth Analyzer Harness

**Status:** Approved (via user review policy)
**Author:** Antigravity
**Created:** 2026-06-14
**Last Updated:** 2026-06-14

---

## 1. Overview

An "in-depth competitor growth" analyzer harness within the Vidbyte SDK that coordinates researching competitors, deduplicating search actions via a local SQLite database, generating structured competitor growth profiles, and writing the final markdown reports to an Obsidian vault.

---

## 2. Goals & Non-Goals

### Goals

- Orchestrate competitor research workflows using `BaseAgent` and tools.
- Deduplicate web searches and URL visits using a persistent SQLite database.
- Format analysis output using a Pydantic output schema.
- Support writing markdown reports to Obsidian using local REST API or direct filesystem write.
- Expose the harness directly on `VidbyteSDK().harnesses`.

### Non-Goals

- Building a hosted web dashboard for this research.
- Implementing real browser execution (scraping) directly inside the harness (users can attach Playwright/Puppeteer MCP servers if needed).

---

## 3. Background & Context

Competitor analysis is crucial for formulating growth strategies for Vidbyte. However, running repeated agentic research runs manually can lead to duplicate web searches (wasting tokens/budgets) and redundant visits. This harness solves the issue by introducing structured output templates and persistent local SQLite-based query/URL tracking.

---

## 4. Requirements

### Functional Requirements

1. Construct and execute a research agent targeting a specific competitor.
2. Maintain a SQLite database to track visited URLs and completed search queries.
3. Expose tools to the agent to check and record search/visit status.
4. Output structured, typed profiles using Pydantic.
5. Export structured reports to an Obsidian vault folder via API or filesystem.

### Non-Functional Requirements

- **Reliability**: Fail-safe fallback to filesystem if Obsidian REST API is unreachable.
- **Safety**: Do not leak secrets or credentials.

---

## 5. High-Level Design

```text
[VidbyteSDK.harnesses] 
      |
      v
[CompetitorGrowthHarness] 
      |---> Loads Competitors
      |---> Instantiates BaseAgent with OpenAI runner
      |---> Registers Custom Tools (Search, Visited URLs)
      |---> Runs Agentic Loop
      |---> Validates Output Schema (CompetitorGrowthAnalysis)
      |---> Passes Output to [ObsidianOutputAdapter]
                  |
                  +---> Writes directly or via HTTPS REST API to Obsidian Vault
```

---

## 6. Detailed Design

### 6.1 `vidbyte/harnesses/competitor_growth.py`
**File(s):** `vidbyte/harnesses/competitor_growth.py`
**Type:** New file

#### What it does
Implements the core harness class, Pydantic schemas, SQLite state memory, and Obsidian output adapter.

#### Interface / API
```python
from pydantic import BaseModel
from typing import Sequence

class CompetitorGrowthAnalysis(BaseModel):
    competitor_name: str
    website: str
    early_wedge: str
    growth_channels: list[str]
    early_playbook_step_by_step: str
    borrowable_ideas_for_vidbyte: list[str]
    sources: list[str]

class CompetitorGrowthHarness:
    def __init__(self, db_path: str = "growth_harness_memory.db", vault_path: str = None, api_key: str = None, port: str = "27124"):
        ...
    async def run_analysis(self, competitor_name: str, runner: object, max_iterations: int = 12) -> CompetitorGrowthAnalysis:
        ...
```

### 6.2 `vidbyte/harnesses/client.py`
**File(s):** `vidbyte/harnesses/client.py`
**Type:** Modified

#### What it does
Exposes the competitor growth analyzer harness constructor.

#### Interface / API
```python
class HarnessClient:
    def competitor_growth(self, **kwargs) -> CompetitorGrowthHarness:
        ...
```

---

## 7. Data Model Changes

### 7.1 SQLite Tables
**Change type:** New

```sql
CREATE TABLE IF NOT EXISTS visited_urls (
    url TEXT PRIMARY KEY,
    competitor_name TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS completed_searches (
    query TEXT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. API Changes
N/A - This is a Python SDK library extension, not a web server.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/harnesses/competitor_growth.py` | Implementation of harness, database, and Obsidian adapter |
| MODIFY | `vidbyte/harnesses/client.py` | Expose competitor growth constructor |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export competitor growth classes |
| CREATE | `tests/test_competitor_growth_harness.py` | Unit and integration tests |
| CREATE | `scripts/test-competitor-growth-analyzer-harness.py` | Executable verification test script |

---

## 10. Testing Plan

### Unit Tests
Written in `tests/test_competitor_growth_harness.py`:
- `test_sqlite_memory_initialization` [Edge Case]: Verifies database and tables are created successfully.
- `test_sqlite_record_and_lookup` [Edge Case]: Verifies URL / query insertion and deduplication checks.
- `test_obsidian_fallback_to_filesystem` [Hidden Failure]: Verifies direct write to folder succeeds if REST API raises connection error.
- `test_agent_tools_called` [Hidden Assumption]: Verifies search and check tools execute and return correct responses.

### Integration Tests
- `test_competitor_growth_harness_run`: Runs `CompetitorGrowthHarness.run_analysis` using a mock runner and asserts it returns correct Pydantic structure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| SQLite3 | Built-in | Deduplication state storage | None |
| Httpx | ^0.24 | Obsidian Local REST API calls | Network failure (mitigated by filesystem fallback) |

---

## 12. Rollout & Deployment
N/A - Exposed as new public methods in SDK namespace.

---

## 13. Open Questions
- None.

---

## 14. Alternatives Considered
N/A
