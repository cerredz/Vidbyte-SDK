<!--- Context Protocol Header --->
<!--
Description:
    Design document for adding 100+ popular preset MCP servers to the Vidbyte SDK.
Purpose:
    Allows developers to attach popular MCP servers (e.g., GitHub, Postgres, web search,
    document converters) to agents in a single line of code without needing to find
    command configurations or manually manage subprocess imports.
Architecture:
    - McpPresetRegistry: Static utility catalog storing preset command templates and documentation.
    - McpAttachableMixin extensions: Ergonomic `attach_preset_mcp_server` and `with_preset_mcp_server` methods.
Relations:
    Related to docs/design/mcp-server-attachment.md, vidbyte/tools/mcp/presets.py,
    vidbyte/agents/mixins.py, and vidbyte/agents/base.py.
-->

# Design Doc: Preset MCP Servers Catalog & One-Line Attachment

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-27  
**Last Updated:** 2026-05-27  

---

## 1. Overview

This feature integrates a curated catalog of over 100 popular Model Context Protocol (MCP) servers directly into the Vidbyte SDK. Developers will be able to attach robust third-party capability servers—such as GitHub integration, PostgreSQL query executors, Puppeteer web browsers, document parsers, and academic reference hubs—in a single line of code. By eliminating the friction of researching node package names, finding binary command syntaxes, and setting up complex stdio shell arguments manually, this enhancement positions Vidbyte as the most integrated and developer-friendly AI agent framework for multi-modal tool environments.

---

## 2. Goals & Non-Goals

### Goals

- **One-Line Attachment Ergonomics:** Enable developers to hook up complex servers via simple keys like `agent.attach_preset_mcp_server("github", env={"GITHUB_PERSONAL_ACCESS_TOKEN": "..."})`.
- **Comprehensive 100+ Preset Catalog:** Deliver a built-in registry of at least 100 popular MCP servers, fully documented with required environment variables and options.
- **Dynamic Parameter Expansion:** Support passing additional arguments (`extra_args`) to preset commands for parameterized presets (e.g., specifying a local directory path for the `local-filesystem` preset).
- **Graceful Error Integration:** Provide specific exceptions when a requested preset does not exist or has missing required environment configurations.
- **Lazy Attachment Parity:** Offer `with_preset_mcp_server` to support lazy builder patterns mirroring `with_mcp_server`.

### Non-Goals

- **Automatic Dependency Installation:** We do not automatically run `npm install` or `pip install` on the user's local operating system; we leverage `npx -y` or `pipx run` to dynamically fetch and execute binaries safely, or assume the host has the required binary in its PATH.
- **Credential Storage/Management:** The SDK does not manage secrets or store credentials; it relies entirely on environment mapping (`env`) provided by the developer at runtime.
- **SSE/Network Server Presets:** Presets are limited to stdio subprocess-backed MCP servers.

---

## 3. Background & Context

Currently, Vidbyte SDK supports raw subprocess attachment using `attach_mcp_server(McpServerConfig(command=["npx", "-y", "@modelcontextprotocol/server-postgres"]))`. While functional, this places a significant research burden on developers. They must:
1. Know the exact NPM package names or binary commands.
2. Search online documentation for required environment variables.
3. Handle platform differences between operating systems.

By embedding a comprehensive, well-documented catalog of popular MCP servers directly into the SDK, we remove this friction entirely. Developers can auto-discover what presets are supported, view their descriptions/requirements, and spawn them instantly.

---

## 4. Requirements

### Functional Requirements

1. **Preset Resolution:** Resolve a string preset identifier (e.g. `"postgres"`) to its corresponding default `McpServerConfig`.
2. **One-Line Async Attachment:** Add `async def attach_preset_mcp_server(self, preset_name: str, ...)` to `McpAttachableMixin`.
3. **One-Line Sync/Lazy Attachment:** Add `def with_preset_mcp_server(self, preset_name: str, ...)` to `McpAttachableMixin`.
4. **Environment Merging:** Merge user-supplied environment mappings with preset defaults (e.g., merging custom database connection ports).
5. **Argument Append / Parameterization:** Support appending `extra_args` to the command line (crucial for filesystem paths, specific databases, etc.).
6. **Detailed Error Raising:** Throw structured `McpPresetNotFoundError` and `McpPresetConfigurationError` (subclasses of `McpAttachmentError`) for invalid configurations.
7. **Preset Catalog Listing:** Provide a public catalog interface to query available presets, descriptions, and required environments.

### Non-Functional Requirements

- **Zero-Impedance Startup:** High-speed lookup using memory registries, introducing zero overhead to the initialization process.
- **Robust Cross-Platform Command Safety:** Ensure node/npx commands are wrapped properly, taking Windows vs. Unix execution details into account.

---

## 5. High-Level Design

We will introduce a new module `vidbyte/tools/mcp/presets.py` containing the `McpPresetRegistry` and its pre-configured preset definitions. We will then extend `McpAttachableMixin` in `vidbyte/agents/mixins.py` to leverage this registry.

```text
┌────────────────────────────────────────────────────────┐
│  BaseAgent / BaseHarness (McpAttachableMixin)          │
│  - attach_preset_mcp_server("github", env=...)        │
│  - with_preset_mcp_server("postgres", env=...)        │
└───────────┬────────────────────────────────────────────┘
            │
            ▼ Resolves preset_name + parameters
┌────────────────────────────────────────────────────────┐
│  McpPresetRegistry (tools/mcp/presets.py)              │
│  - catalog: Dict[str, McpPresetDefinition]             │
│  - create_config(preset, env, extra_args)              │
└───────────┬────────────────────────────────────────────┘
            │
            ▼ Instantiates standard config
┌────────────────────────────────────────────────────────┐
│  McpServerConfig (tools/mcp/types.py)                  │
└───────────┬────────────────────────────────────────────┘
            │
            ▼ Starts stdio process and bridges tools
┌────────────────────────────────────────────────────────┐
│  attach_mcp_server (tools/mcp/attach.py)               │
└────────────────────────────────────────────────────────┘
```

---

## 6. Detailed Design

### 6.1 Preset Definitions & Registry

**File:** `vidbyte/tools/mcp/presets.py`  
**Type:** New file  

#### What it does
Houses the preset catalog metadata, individual server configurations, validation functions, and catalog queries. It defines the `McpPresetDefinition` structure and compiles a list of **at least 100** popular pre-configured servers.

#### Interface / API

```python
from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission

@dataclass(frozen=True, slots=True)
class McpPresetDefinition:
    """Immutable metadata and configuration template for an MCP server preset."""
    name: str
    category: str
    description: str
    command: tuple[str, ...]
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...] = ()
    default_env: Mapping[str, str] | None = None
    docs_url: str | None = None

class McpPresetRegistry:
    """Central registry and query interface for all built-in MCP presets."""
    _presets: dict[str, McpPresetDefinition] = {}

    @classmethod
    def register(cls, definition: McpPresetDefinition) -> None:
        """Register a new preset definition."""
        ...

    @classmethod
    def get(cls, name: str) -> McpPresetDefinition:
        """Retrieve a preset by its identifier name. Raises McpPresetNotFoundError."""
        ...

    @classmethod
    def list_presets(cls, category: str | None = None) -> tuple[McpPresetDefinition, ...]:
        """List all registered presets, optionally filtered by category."""
        ...

    @classmethod
    def build_config(
        cls,
        preset_name: str,
        *,
        env: Mapping[str, str] | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> McpServerConfig:
        """Validates parameters and builds a concrete McpServerConfig for execution.
        
        Raises McpPresetConfigurationError if any required environment variable is missing.
        """
        ...
```

#### The 100+ MCP Servers Preset Catalog

The following is the structured compilation of the **101 preset servers** built into `McpPresetRegistry`:

##### Category: Search & Web Research (10 servers)
1. **`brave-search`**: Executes privacy-focused web searches and crawls clean page text.
   - Command: `("npx", "-y", "@modelcontextprotocol/server-brave-search")`
   - Required Environment: `("BRAVE_API_KEY",)`
2. **`google-search`**: Executes web searches using Google Custom Search engine JSON API.
   - Command: `("npx", "-y", "@modelcontextprotocol/server-google-search")`
   - Required Environment: `("GOOGLE_API_KEY", "GOOGLE_CSE_ID")`
3. **`tavily`**: LLM-optimized agentic web search that delivers ready-to-consume snippets.
   - Command: `("python", "-m", "mcp_server_tavily")`
   - Required Environment: `("TAVILY_API_KEY",)`
4. **`exa`**: Neural search engine utilizing embeddings to find hyper-relevant articles.
   - Command: `("npx", "-y", "@exa-labs/mcp-server")`
   - Required Environment: `("EXA_API_KEY",)`
5. **`duckduckgo`**: Free web search scraping DuckDuckGo results without API key requirements.
   - Command: `("python", "-m", "mcp_server_duckduckgo")`
   - Required Environment: `()`
6. **`puppeteer`**: Headless browser controller to view, screenshot, and scrape complex JavaScript-heavy web applications.
   - Command: `("npx", "-y", "@modelcontextprotocol/server-puppeteer")`
   - Required Environment: `()`
7. **`playwright`**: High-level headless browser scraper using Python's Playwright integration.
   - Command: `("python", "-m", "mcp_server_playwright")`
   - Required Environment: `()`
8. **`searxng`**: Queries self-hosted privacy-respecting meta-search engine instances.
   - Command: `("python", "-m", "mcp_server_searxng")`
   - Required Environment: `("SEARXNG_URL",)`
9. **`firecrawl`**: Converts full, complex web pages into perfectly formatted markdown blocks.
   - Command: `("npx", "-y", "@firecrawl/mcp-server")`
   - Required Environment: `("FIRECRAWL_API_KEY",)`
10. **`jina-reader`**: Jina AI's URL reader converting web layouts into clean markdown representations.
    - Command: `("python", "-m", "mcp_server_jina_reader")`
    - Required Environment: `("JINA_API_KEY",)`

##### Category: Version Control, Development & Task Tracking (12 servers)
11. **`github`**: Complete repository access, including issue tracking, PR management, and code file editing.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-github")`
    - Required Environment: `("GITHUB_PERSONAL_ACCESS_TOKEN",)`
12. **`gitlab`**: Integrates with self-hosted or cloud GitLab projects, branches, and issues.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-gitlab")`
    - Required Environment: `("GITLAB_PERSONAL_ACCESS_TOKEN",)`
13. **`bitbucket`**: Workspace administration, repo checking, and pull requests in Bitbucket.
    - Command: `("python", "-m", "mcp_server_bitbucket")`
    - Required Environment: `("BITBUCKET_USERNAME", "BITBUCKET_APP_PASSWORD")`
14. **`jira`**: Searches, creates, updates, and transitions software engineering sprint issues in Jira.
    - Command: `("npx", "-y", "mcp-server-jira")`
    - Required Environment: `("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")`
15. **`linear`**: Direct connection to modern, lightweight software sprint management backends.
    - Command: `("npx", "-y", "@linear/mcp-server")`
    - Required Environment: `("LINEAR_API_KEY",)`
16. **`sentry`**: Inspects production error dashboards, tracks debug traces, and queries issues.
    - Command: `("npx", "-y", "@sentry/mcp-server")`
    - Required Environment: `("SENTRY_AUTH_TOKEN", "SENTRY_ORG")`
17. **`sonarqube`**: Triggers static analysis and reads Quality Gate status from SonarQube.
    - Command: `("python", "-m", "mcp_server_sonarqube")`
    - Required Environment: `("SONAR_TOKEN", "SONAR_HOST_URL")`
18. **`docker`**: Starts, stops, inspects, and logs standard local Docker container lifecycles.
    - Command: `("python", "-m", "mcp_server_docker")`
    - Required Environment: `()`
19. **`kubernetes`**: Full cluster node, pod, and service diagnostics via standard Kubeconfigs.
    - Command: `("python", "-m", "mcp_server_kubernetes")`
    - Required Environment: `()`
20. **`jenkins`**: Commands Jenkins pipelines, triggers parameters, and tracks job status logs.
    - Command: `("python", "-m", "mcp_server_jenkins")`
    - Required Environment: `("JENKINS_URL", "JENKINS_USER", "JENKINS_TOKEN")`
21. **`circleci`**: Fetches pipeline histories and checks project run states.
    - Command: `("python", "-m", "mcp_server_circleci")`
    - Required Environment: `("CIRCLECI_TOKEN",)`
22. **`vercel`**: Accesses Vercel project deployments, changes domains, and returns log lines.
    - Command: `("npx", "-y", "vercel-mcp-server")`
    - Required Environment: `("VERCEL_TOKEN",)`

##### Category: Databases & Cache (12 servers)
23. **`postgres`**: Executes queries, discovers database schemas, and describes table structures.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-postgres")`
    - Required Environment: `("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE")`
24. **`mysql`**: Performs CRUD queries and checks schemas on standard MySQL servers.
    - Command: `("npx", "-y", "mcp-server-mysql")`
    - Required Environment: `("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")`
25. **`sqlite`**: Inspects tables and manipulates local SQLite database files.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-sqlite")`
    - Required Environment: `()` (Requires database path via `extra_args`)
26. **`mongodb`**: Integrates agent actions with schema-less MongoDB document databases.
    - Command: `("python", "-m", "mcp_server_mongodb")`
    - Required Environment: `("MONGODB_URI",)`
27. **`redis`**: Key-value data interactions and fast transient storage access.
    - Command: `("python", "-m", "mcp_server_redis")`
    - Required Environment: `("REDIS_URI",)`
28. **`supabase`**: Direct access to Supabase serverless database projects and edge instances.
    - Command: `("npx", "-y", "@supabase/mcp-server")`
    - Required Environment: `("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")`
29. **`neon`**: Spins up, branches, and queries serverless relational Neon Postgres engines.
    - Command: `("npx", "-y", "@neondatabase/mcp-server")`
    - Required Environment: `("NEON_API_KEY",)`
30. **`planetscale`**: Schema-safe branch operations on MySQL-compatible PlanetScale clusters.
    - Command: `("python", "-m", "mcp_server_planetscale")`
    - Required Environment: `("PLANETSCALE_SERVICE_TOKEN",)`
31. **`pinecone`**: Queries and updates dense, high-dimensional vector representations.
    - Command: `("python", "-m", "mcp_server_pinecone")`
    - Required Environment: `("PINECONE_API_KEY",)`
32. **`qdrant`**: High-performance semantic vector searches on Qdrant DB.
    - Command: `("python", "-m", "mcp_server_qdrant")`
    - Required Environment: `("QDRANT_URL", "QDRANT_API_KEY")`
33. **`chromadb`**: Local and embedded Chroma vector databases for immediate knowledge storage.
    - Command: `("python", "-m", "mcp_server_chroma")`
    - Required Environment: `("CHROMA_SERVER_HOST",)`
34. **`clickhouse`**: Runs fast analytical columnar queries on mass data logs.
    - Command: `("python", "-m", "mcp_server_clickhouse")`
    - Required Environment: `("CLICKHOUSE_HOST", "CLICKHOUSE_PASSWORD")`

##### Category: Productivity, Office & CRM (12 servers)
35. **`google-calendar`**: Lists, updates, schedules, and edits events on Google Calendars.
    - Command: `("python", "-m", "mcp_server_google_calendar")`
    - Required Environment: `("GOOGLE_CALENDAR_CREDENTIALS",)`
36. **`google-drive`**: Searches, exports, and downloads drive folders and office formats.
    - Command: `("python", "-m", "mcp_server_google_drive")`
    - Required Environment: `("GOOGLE_DRIVE_CREDENTIALS",)`
37. **`google-sheets`**: Appends cells and changes Google Sheet table calculations.
    - Command: `("python", "-m", "mcp_server_google_sheets")`
    - Required Environment: `("GOOGLE_SHEETS_CREDENTIALS",)`
38. **`gmail`**: Searches message histories, drafts auto-replies, and triggers emails.
    - Command: `("python", "-m", "mcp_server_gmail")`
    - Required Environment: `("GMAIL_CREDENTIALS",)`
39. **`notion`**: Queries database schemas, lists pages, and appends block markdown.
    - Command: `("npx", "-y", "@notionhq/mcp-server")`
    - Required Environment: `("NOTION_API_KEY",)`
40. **`coda`**: Edits complex docs and updates operational tables in Coda workspaces.
    - Command: `("npx", "-y", "coda-mcp-server")`
    - Required Environment: `("CODA_API_KEY",)`
41. **`outlook`**: Interacts with Microsoft Office Outlook mailbox folders.
    - Command: `("python", "-m", "mcp_server_outlook")`
    - Required Environment: `("OUTLOOK_OAUTH_TOKEN",)`
42. **`onedrive`**: Explores directories and processes files in Microsoft OneDrive.
    - Command: `("python", "-m", "mcp_server_onedrive")`
    - Required Environment: `("ONEDRIVE_OAUTH_TOKEN",)`
43. **`evernote`**: Handles Evernote accounts, notes, and checklist notebooks.
    - Command: `("python", "-m", "mcp_server_evernote")`
    - Required Environment: `("EVERNOTE_DEVELOPER_TOKEN",)`
44. **`salesforce`**: Explores opportunities, details leads, and appends logs in Salesforce.
    - Command: `("python", "-m", "mcp_server_salesforce")`
    - Required Environment: `("SALESFORCE_CREDENTIALS",)`
45. **`hubspot`**: Tracks marketing pipelines, registers client contacts, and closes deal tickets.
    - Command: `("npx", "-y", "@hubspot/mcp-server")`
    - Required Environment: `("HUBSPOT_ACCESS_TOKEN",)`
46. **`airtable`**: Edits rows, lists fields, and reads relational bases inside Airtable.
    - Command: `("npx", "-y", "airtable-mcp-server")`
    - Required Environment: `("AIRTABLE_API_KEY",)`

##### Category: Document Parsers & Media Utilities (10 servers)
47. **`pandoc`**: Converts documents between filetypes (e.g. HTML to Markdown, DOCX to EPUB).
    - Command: `("python", "-m", "mcp_server_pandoc")`
    - Required Environment: `()`
48. **`pdf-parser`**: Parses and structures metadata, text, and nested tables from PDF files.
    - Command: `("python", "-m", "mcp_server_pdf")`
    - Required Environment: `()`
49. **`ffmpeg`**: Splices, compresses, crops, and processes video and audio media files.
    - Command: `("python", "-m", "mcp_server_ffmpeg")`
    - Required Environment: `()`
50. **`imagemagick`**: Modifies, crops, and optimizes image file resolutions and formats.
    - Command: `("python", "-m", "mcp_server_imagemagick")`
    - Required Environment: `()`
51. **`graphviz`**: Compiles DOT text descriptions into clean SVG or PNG diagram files.
    - Command: `("python", "-m", "mcp_server_graphviz")`
    - Required Environment: `()`
52. **`tesseract-ocr`**: Extracts written or printed text content from scanned image pictures.
    - Command: `("python", "-m", "mcp_server_tesseract")`
    - Required Environment: `()`
53. **`markitdown`**: Microsoft MarkItDown tool converting XLSX, PPTX, PDF, and DOCX to high-fidelity Markdown.
    - Command: `("python", "-m", "mcp_server_markitdown")`
    - Required Environment: `()`
54. **`whisper`**: Generates text translations and subtitles from speech audio files.
    - Command: `("python", "-m", "mcp_server_whisper")`
    - Required Environment: `()`
55. **`xlsx-parser`**: Fast, low-memory extraction of raw spreadsheet sheets.
    - Command: `("python", "-m", "mcp_server_xlsx")`
    - Required Environment: `()`
56. **`epub-reader`**: Parses book chapters and internal indexes from EPUB publications.
    - Command: `("python", "-m", "mcp_server_epub")`
    - Required Environment: `()`

##### Category: Communication & Chat (8 servers)
57. **`slack`**: Posts messages, uploads assets, and reads threads in Slack workspace channels.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-slack")`
    - Required Environment: `("SLACK_BOT_TOKEN",)`
58. **`discord`**: Reads channel announcements, handles roles, and posts embeds to Discord servers.
    - Command: `("python", "-m", "mcp_server_discord")`
    - Required Environment: `("DISCORD_BOT_TOKEN",)`
59. **`telegram`**: Automatically replies to messages and broadcasts updates through Telegram Bots.
    - Command: `("python", "-m", "mcp_server_telegram")`
    - Required Environment: `("TELEGRAM_BOT_TOKEN",)`
60. **`twilio`**: Delivers SMS messages and performs phone number security audits.
    - Command: `("python", "-m", "mcp_server_twilio")`
    - Required Environment: `("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")`
61. **`sendgrid`**: Sends robust promotional or structural system transactional emails.
    - Command: `("python", "-m", "mcp_server_sendgrid")`
    - Required Environment: `("SENDGRID_API_KEY",)`
62. **`teams`**: Posts notifications and cards in Microsoft Teams organization pipelines.
    - Command: `("python", "-m", "mcp_server_teams")`
    - Required Environment: `("TEAMS_OAUTH_TOKEN",)`
63. **`whatsapp`**: Sends templated message scripts via the official WhatsApp Business cloud api.
    - Command: `("python", "-m", "mcp_server_whatsapp")`
    - Required Environment: `("WHATSAPP_ACCESS_TOKEN",)`
64. **`zoom`**: Creates instant Zoom meeting URLs and adds scheduled conference entries.
    - Command: `("python", "-m", "mcp_server_zoom")`
    - Required Environment: `("ZOOM_OAUTH_TOKEN",)`

##### Category: Cloud Platforms, Hosting & Infrastructure (10 servers)
65. **`aws-ec2`**: Lists, boots, and suspends virtual machine servers in Amazon EC2 zones.
    - Command: `("python", "-m", "mcp_server_aws_ec2")`
    - Required Environment: `("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")`
66. **`aws-s3`**: Creates buckets, downloads assets, and uploads files to AWS S3.
    - Command: `("python", "-m", "mcp_server_aws_s3")`
    - Required Environment: `("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")`
67. **`aws-lambda`**: Triggers lambda functions and updates code bundle zip folders.
    - Command: `("python", "-m", "mcp_server_aws_lambda")`
    - Required Environment: `("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")`
68. **`gcp-compute`**: Direct controller to spin up or terminate GCP VM instances.
    - Command: `("python", "-m", "mcp_server_gcp_compute")`
    - Required Environment: `("GOOGLE_APPLICATION_CREDENTIALS",)`
69. **`gcp-storage`**: Lists files and handles buckets inside Google Cloud Storage.
    - Command: `("python", "-m", "mcp_server_gcp_storage")`
    - Required Environment: `("GOOGLE_APPLICATION_CREDENTIALS",)`
70. **`azure-vm`**: Tracks VMs and reviews billing stats inside Microsoft Azure deployments.
    - Command: `("python", "-m", "mcp_server_azure_vm")`
    - Required Environment: `("AZURE_CREDENTIALS",)`
71. **`azure-blob`**: Transfers large media objects into Azure Blob container slots.
    - Command: `("python", "-m", "mcp_server_azure_blob")`
    - Required Environment: `("AZURE_STORAGE_CONNECTION_STRING",)`
72. **`netlify`**: Triggers static workspace builds and configures custom domain mappings.
    - Command: `("python", "-m", "mcp_server_netlify")`
    - Required Environment: `("NETLIFY_AUTH_TOKEN",)`
73. **`cloudflare`**: Updates Cloudflare KV databases, checks DNS records, and deploys Workers.
    - Command: `("python", "-m", "mcp_server_cloudflare")`
    - Required Environment: `("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")`
74. **`heroku`**: Changes configurations, monitors Dynos, and restarts Heroku environments.
    - Command: `("python", "-m", "mcp_server_heroku")`
    - Required Environment: `("HEROKU_API_KEY",)`

##### Category: AI Platforms & Creative APIs (8 servers)
75. **`openai-agent`**: Generates text embeddings, retrieves fine-tuning logs, and controls assistants.
    - Command: `("python", "-m", "mcp_server_openai")`
    - Required Environment: `("OPENAI_API_KEY",)`
76. **`anthropic-agent`**: Manages prompt engineering benchmarks and parses system templates.
    - Command: `("python", "-m", "mcp_server_anthropic")`
    - Required Environment: `("ANTHROPIC_API_KEY",)`
77. **`huggingface`**: Accesses open-source datasets, reviews code repositories, and downloads files.
    - Command: `("python", "-m", "mcp_server_huggingface")`
    - Required Environment: `("HUGGING_FACE_HUB_TOKEN",)`
78. **`replicate`**: Executes arbitrary high-quality image, video, and audio AI models on Replicate.
    - Command: `("npx", "-y", "replicate-mcp-server")`
    - Required Environment: `("REPLICATE_API_TOKEN",)`
79. **`midjourney`**: Starts Midjourney diffusion pipelines and fetches creative graphics assets.
    - Command: `("python", "-m", "mcp_server_midjourney")`
    - Required Environment: `("MIDJOURNEY_API_KEY",)`
80. **`elevenlabs`**: Creates high-fidelity text-to-speech audio files in diverse voices.
    - Command: `("python", "-m", "mcp_server_elevenlabs")`
    - Required Environment: `("ELEVENLABS_API_KEY",)`
81. **`fal-ai`**: Executes fast SDXL or video generation models on the Fal AI cloud compute.
    - Command: `("python", "-m", "mcp_server_fal")`
    - Required Environment: `("FAL_KEY",)`
82. **`groq`**: Ultra-fast LLM text generations powered by Groq LPU execution blocks.
    - Command: `("python", "-m", "mcp_server_groq")`
    - Required Environment: `("GROQ_API_KEY",)`

##### Category: Reference & Academic (8 servers)
83. **`wikipedia`**: Searches Wikipedia database index and returns accurate page snippets.
    - Command: `("python", "-m", "mcp_server_wikipedia")`
    - Required Environment: `()`
84. **`wolfram-alpha`**: Computes mathematical formulas, solves equations, and queries facts.
    - Command: `("python", "-m", "mcp_server_wolfram")`
    - Required Environment: `("WOLFRAM_APP_ID",)`
85. **`stackoverflow`**: Queries active developer questions, code files, and answers.
    - Command: `("python", "-m", "mcp_server_stackoverflow")`
    - Required Environment: `()`
86. **`arxiv`**: Pulls PDF papers, parses abstracts, and searches academic documents.
    - Command: `("python", "-m", "mcp_server_arxiv")`
    - Required Environment: `()`
87. **`mdn`**: Offline lookup tool for standard MDN Web CSS, HTML, and JS configurations.
    - Command: `("python", "-m", "mcp_server_mdn")`
    - Required Environment: `()`
88. **`devdocs`**: Instant keyword search mapping standard language structures in DevDocs.
    - Command: `("python", "-m", "mcp_server_devdocs")`
    - Required Environment: `()`
89. **`pubchem`**: Looks up chemical compound structures, IUPAC names, and lab safety details.
    - Command: `("python", "-m", "mcp_server_pubchem")`
    - Required Environment: `()`
90. **`geonames`**: Resolves latitude/longitude coords into administrative names and timezones.
    - Command: `("python", "-m", "mcp_server_geonames")`
    - Required Environment: `()`

##### Category: Native System & Utilities (11 servers)
91. **`local-filesystem`**: Standard tool for secure reading, editing, and listing files in specific folders.
    - Command: `("npx", "-y", "@modelcontextprotocol/server-filesystem")`
    - Required Environment: `()` (Requires target directory via `extra_args`)
92. **`os-command`**: Runs native terminal commands with strict timeouts and output filtering.
    - Command: `("python", "-m", "mcp_server_os")`
    - Required Environment: `()`
93. **`env-inspector`**: Extracts operating system environment flags, path structures, and user details safely.
    - Command: `("python", "-m", "mcp_server_env")`
    - Required Environment: `()`
94. **`process-manager`**: Monitors active system loops, processes, memory usage, and allows termination.
    - Command: `("python", "-m", "mcp_server_process")`
    - Required Environment: `()`
95. **`system-diagnostics`**: Inspects hard disk allocations, hardware temperatures, and CPU core speeds.
    - Command: `("python", "-m", "mcp_server_diagnostics")`
    - Required Environment: `()`
96. **`markdown-linter`**: Audits document styles, link integrity, and syntax violations.
    - Command: `("python", "-m", "mcp_server_markdown_linter")`
    - Required Environment: `()`
97. **`python-sandbox`**: Runs raw mathematical or file logic inside isolated execution bubbles.
    - Command: `("python", "-m", "mcp_server_py_sandbox")`
    - Required Environment: `()`
98. **`sqlite-sandbox`**: Performs isolated read-only operations on SQL command test tables.
    - Command: `("python", "-m", "mcp_server_sqlite_sandbox")`
    - Required Environment: `()`
99. **`csv-parser`**: Parses massive comma-separated values, performs groupings, and generates statistics.
    - Command: `("python", "-m", "mcp_server_csv")`
    - Required Environment: `()`
100. **`json-validator`**: Checks JSON document formats against schemas.
     - Command: `("python", "-m", "mcp_server_json")`
     - Required Environment: `()`
101. **`sequential-thinking`**: Grants agents the ability to reason step-by-step and break complex issues down logically.
     - Command: `("npx", "-y", "@modelcontextprotocol/server-sequential-thinking")`
     - Required Environment: `()`

---

### 6.2 Agent Mixin Extensions

**File:** `vidbyte/agents/mixins.py`  
**Type:** Modified  

#### What it does
Implements the new preset attachment interface, parsing, dynamic environment variable injection, validation, and standard integration into the existing `BaseAgent` and `BaseHarness` capabilities.

#### Interface / API

```python
# Extended class inside vidbyte/agents/mixins.py:

class McpAttachableMixin:
    # Existing methods ...

    async def attach_preset_mcp_server(
        self,
        preset_name: str,
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> McpAttachableMixin:
        """Start one popular preset MCP server subprocess in a single line.
        
        Discovers tools, bridges, and attaches them directly to the agent.
        
        Returns self to support builder pattern.
        """
        # Multi-line signature is formatted strictly on 1 line for the actual code execution
        from vidbyte.tools.mcp.presets import McpPresetRegistry
        
        config = McpPresetRegistry.build_config(
            preset_name,
            env=env,
            permission=permission,
            timeout=timeout,
            extra_args=extra_args,
        )
        if name:
            config = McpServerConfig(
                command=config.command,
                name=name,
                permission=config.permission,
                env=config.env,
                timeout=config.timeout,
            )
            
        handle = await attach_mcp_server(config)
        self._mcp_handles.append(handle)
        self._attach_tools(handle.bridged_tools)
        return self

    def with_preset_mcp_server(
        self,
        preset_name: str,
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> McpAttachableMixin:
        """Sync builder method that registers an MCP server preset configuration.
        
        The subprocess connection is deferred and connects lazily before the first execution.
        """
        from vidbyte.tools.mcp.presets import McpPresetRegistry
        
        config = McpPresetRegistry.build_config(
            preset_name,
            env=env,
            permission=permission,
            timeout=timeout,
            extra_args=extra_args,
        )
        if name:
            config = McpServerConfig(
                command=config.command,
                name=name,
                permission=config.permission,
                env=config.env,
                timeout=config.timeout,
            )
            
        self._pending_mcp_configs.append(config)
        return self
```

---

## 7. Data Model Changes

N/A - This feature only introduces execution-level configuration objects and preset mappings. No persistent database models or schemas are created, modified, or deleted.

---

## 8. API Changes

N/A - This features affects SDK developer-facing programmatic Python APIs only. No HTTP API endpoints or network routes are added or modified.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/mcp/presets.py` | Contains the catalog of 100+ presets and registry management |
| MODIFY | `vidbyte/agents/mixins.py` | Adds `attach_preset_mcp_server` and `with_preset_mcp_server` |
| MODIFY | `vidbyte/tools/mcp/__init__.py` | Exports preset registries and definitions for public SDK usage |

---

## 10. Testing Plan

A rich, automated validation plan will cover the registry validation, command structure output, error generation, and lazy-loading builders.

### Unit Tests

- `describe('McpPresetRegistry')`
  - `it('should successfully retrieve metadata for registered presets like github or postgres')` [Edge Case]
  - `it('should throw McpPresetNotFoundError if preset is not registered')` [Edge Case]
  - `it('should throw McpPresetConfigurationError if required env variables are missing')` [Hidden Failure]
  - `it('should correctly merge default, platform, and developer environments without leakage')` [Hidden Assumption]
  - `it('should append extra_args correctly to command line configurations')` [Edge Case]
  - `it('should handle None environments without throwing errors')` [Edge Case]

- `describe('McpAttachableMixin Preset Extension')`
  - `it('should lazily configure preset configs without triggering active connections')` [Hidden Assumption]
  - `it('should correctly attach active tools when using lazy connection flows')` [Silent Failure]
  - `it('should throw and clean up properly if preset attachment fails mid-connection')` [Hidden Failure]
  - `it('should respect custom names overriding the preset standard naming')` [Silent Failure]

### Integration Tests

- Full integration test spinning up a lightweight mocked subprocess preset (e.g. `sequential-thinking` or `local-filesystem`) to ensure the entire JSON-RPC initialization handshake completes and discovers tools in 1 line.

### Manual / QA Test Cases

1. Given a python project with a virtual environment:
   - When a developer instantiates an agent:
     ```python
     from vidbyte.agents.base import BaseAgent
     agent = BaseAgent().with_preset_mcp_server("sequential-thinking")
     ```
   - When execution starts (triggering the lazy connection):
     - Confirm the `sequential-thinking` subprocess is spawned.
     - Verify that sequential thinking tools appear in the agent's active registry.
     - Close the agent session and verify no orphan processes remain.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `npx` / Node | Host standard utility | Executes javascript-based MCP servers dynamically | Subprocess execution block if node is missing on the client machine |
| `python` | Host environment standard | Spawns python-based MCP packages | Different command names on Windows (`python`) vs Linux/macOS (`python3`) |

---

## 12. Rollout & Deployment

This feature is completely backwards-compatible and introduces new capabilities without modifying existing method contracts.
- **Breaking Changes:** None.
- **Rollout Path:** Bundled in next minor SDK release.
- **Rollback:** Safe deletion of `vidbyte/tools/mcp/presets.py` and mixin extensions.

---

## 13. Open Questions

- [ ] Should we support a programmatic installer utility (e.g., `McpPresetRegistry.install("postgres")`) in the future that checks host requirements (Node, Python packages) and downloads/installs them if missing?
- [ ] Should we allow developers to register custom presets programmatically at application startup so they can reuse their own command templates under local keys?

---

## 14. Alternatives Considered

### Alternative 1: Downloading all packages locally on SDK install

- **What:** Include npm packages/python files in the SDK wheel or install them during `pip install vidbyte-sdk`.
- **Why rejected:** Exceedingly heavy install package size, complex cross-platform installer dependencies, and frequent version sync mismatches.

### Alternative 2: Storing configs in a YAML config file

- **What:** Placing the preset command structures in an external `presets.yaml` configuration file.
- **Why rejected:** Harder to package inside python package wheels without configuration file path lookup issues, and reduces python programmatic ease-of-use. Storing in native Python dataclasses keeps it compile-safe, high-speed, and extremely transparent.
