"""Context Protocol Header

Description:
    Implements the Competitor Growth Analyzer Harness including database, schema, and output adapters.
Purpose:
    Enables automatic search, deduplication, structured modeling, and Obsidian publishing for competitor growth playbooks.
Architecture:
    - CompetitorGrowthAnalysis: Structured output representation.
    - SQLiteHarnessMemory: Local SQLite deduplication layer.
    - ObsidianOutputAdapter: Markdown renderer and Obsidian publisher (REST + filesystem).
    - CompetitorGrowthHarness: Main orchestration controller.
Relation to codebase as a whole:
    Belongs under the vidbyte.harnesses namespace and integrates BaseAgent, ContextManager, and Tools.
Similar files:
    - vidbyte/harnesses/client.py: Exposes client methods for the harnesses namespace.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Sequence
from pydantic import BaseModel, Field
import httpx

from vidbyte.agents import BaseAgent
from vidbyte.context import ContextManager, TextContextItem
from vidbyte.tools import tool, ToolCall, ToolResult, ToolStatus


class CompetitorGrowthAnalysis(BaseModel):
    competitor_name: str = Field(..., description="Name of the competitor.")
    website: str = Field(..., description="Main URL or website domain.")
    early_wedge: str = Field(..., description="The 0-to-1 distribution wedge used to get first users.")
    growth_channels: list[str] = Field(..., description="Specific channels used.")
    early_playbook_step_by_step: str = Field(..., description="Step-by-step description of early growth playbook.")
    borrowable_ideas_for_vidbyte: list[str] = Field(..., description="Specific tactics or ideas Vidbyte could borrow.")
    sources: list[str] = Field(..., description="List of source URLs and references discovered.")


class SQLiteHarnessMemory:
    """Persistent local SQLite database for query and URL deduplication."""

    def __init__(self, db_path: str = "growth_harness_memory.db") -> None:
        # Resolves path and initializes local tables.
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        # Creates visited_urls and completed_searches tables if they do not exist.
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS visited_urls (
                    url TEXT PRIMARY KEY,
                    competitor_name TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS completed_searches (
                    query TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def has_visited_url(self, url: str) -> bool:
        # Returns True if the given URL has already been visited.
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM visited_urls WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def record_visit(self, url: str, competitor_name: str) -> None:
        # Records that a URL has been visited for a specific competitor.
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO visited_urls (url, competitor_name) VALUES (?, ?)",
                (url, competitor_name),
            )

    def has_searched(self, query: str) -> bool:
        # Returns True if the given query has already been executed.
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM completed_searches WHERE query = ?", (query,))
        return cursor.fetchone() is not None

    def record_search(self, query: str) -> None:
        # Records that a query has been executed.
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO completed_searches (query) VALUES (?)", (query,))

    def close(self) -> None:
        # Closes the connection to the database.
        self.conn.close()


class ObsidianOutputAdapter:
    """Handles formatting and writing competitor analysis files to Obsidian."""

    def __init__(self, vault_path: str | None = None, api_key: str | None = None, port: str = "27124") -> None:
        # Resolves Obsidian REST API settings and vault directories.
        self.vault_path = vault_path or os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\422mi\knowledge\knowledge")
        self.api_key = api_key or os.getenv("OBSIDIAN_API_KEY", "1e3409ae7c4432c883288e9c6ab1c1d4fd9b35514f4309280c22206886d16bf9")
        self.port = port or os.getenv("OBSIDIAN_API_PORT", "27124")
        self.sub_folder = "Competitors"

    async def save_analysis(self, analysis: CompetitorGrowthAnalysis) -> bool:
        # Saves analysis report to Obsidian using the local REST API, falling back to direct filesystem write.
        filename = f"{analysis.competitor_name.replace(' ', '_')}.md"
        content = self._render_markdown(analysis)

        # Try API
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"https://127.0.0.1:{self.port}/vault/{self.sub_folder}/{filename}"
        try:
            async with httpx.AsyncClient(verify=False) as client:
                res = await client.put(url, headers=headers, content=content, timeout=5.0)
                if res.status_code in (200, 201, 204):
                    return True
        except Exception:
            pass

        # Filesystem fallback
        dest_dir = Path(self.vault_path) / self.sub_folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        filepath = dest_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return True

    def _render_markdown(self, analysis: CompetitorGrowthAnalysis) -> str:
        # Formats the CompetitorGrowthAnalysis model as a clean Markdown string.
        sources_list = "\n".join(f"- [{url}]({url})" for url in analysis.sources)
        ideas_list = "\n".join(f"- {idea}" for idea in analysis.borrowable_ideas_for_vidbyte)
        return f"""# Competitor Growth Analysis: {analysis.competitor_name}
*Website: {analysis.website}*

## Early Wedge (0-to-1)
{analysis.early_wedge}

## Growth Channels
{", ".join(analysis.growth_channels)}

## Step-by-Step Early Playbook
{analysis.early_playbook_step_by_step}

## Borrowable Ideas for Vidbyte
{ideas_list}

## Sources Checked
{sources_list}
"""


class CompetitorGrowthHarness:
    """Manages the full competitor growth analysis execution loop."""

    def __init__(self, db_path: str = "growth_harness_memory.db", vault_path: str | None = None, api_key: str | None = None, port: str = "27124") -> None:
        # Sets up persistent SQLite memory and output destination adapter.
        self.db = SQLiteHarnessMemory(db_path)
        self.adapter = ObsidianOutputAdapter(vault_path=vault_path, api_key=api_key, port=port)

    async def run_analysis(self, competitor_name: str, runner: object, max_iterations: int = 12) -> CompetitorGrowthAnalysis:
        # Creates a BaseAgent with search and deduplication tools to research the competitor and returns structured results.
        tools = self._build_agent_tools(competitor_name)
        agent = BaseAgent(
            name="growth-analyst",
            system_prompt=(
                "You are an expert competitor growth researcher. Your goal is to find the exact "
                "0-to-1 distribution strategies and wedges of competitors. "
                "Use search_web to find credible sources, check if URLs have already been visited to "
                "avoid duplicates, and output a validated Pydantic analysis schema."
            ),
            runner=runner,
            tools=tools,
            output_schema=CompetitorGrowthAnalysis,
            max_iterations=max_iterations,
        )

        context_items = [
            TextContextItem(
                title="Goal",
                content=f"Analyze how {competitor_name} got its first 10,000 users and scaled to 10M+ ARR.",
            )
        ]

        reply = await agent.arun(
            message=f"Research the early growth playbooks and strategies of {competitor_name}.",
            context_items=context_items,
        )

        analysis = reply.metadata.get("structured")
        if not analysis:
            raise ValueError(f"Agent failed to return structured output for {competitor_name}")

        await self.adapter.save_analysis(analysis)
        return analysis

    def _build_agent_tools(self, competitor_name: str) -> list[Any]:
        # Formulates search and check tools bound to the current harness state.
        db = self.db

        @tool
        def has_visited_url(url: str) -> bool:
            """Check if this URL has already been visited or parsed during research."""
            return db.has_visited_url(url)

        @tool
        def record_visited_url(url: str) -> str:
            """Record that a URL has been visited for the current competitor."""
            db.record_visit(url, competitor_name)
            return f"Recorded URL: {url}"

        @tool
        async def search_web(query: str) -> str:
            """Search the web for competitor growth strategies or early playbooks."""
            if db.has_searched(query):
                return f"[MEMORY] Already searched this query: {query}. Skipping."
            db.record_search(query)

            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                return "Error: TAVILY_API_KEY is not configured in the environment."

            async with httpx.AsyncClient() as client:
                try:
                    res = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": api_key, "query": query},
                        timeout=10.0,
                    )
                    res.raise_for_status()
                    data = res.json()
                    results = []
                    for x in data.get("results", []):
                        results.append(f"Title: {x['title']}\nURL: {x['url']}\nSnippet: {x['content']}\n---")
                    return "\n".join(results)
                except Exception as e:
                    return f"Search execution failed: {str(e)}"

        return [has_visited_url, record_visited_url, search_web]

    def close(self) -> None:
        # Closes the internal SQLite memory connection.
        self.db.close()
