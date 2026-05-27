"""Context Protocol Header

Description:
    Defines built-in Model Context Protocol (MCP) server presets and the registry.
Purpose:
    Allows developers to fetch popular pre-configured MCP servers (e.g. GitHub, Postgres, Brave Search)
    in a single line of code without manual command specification.
Architecture:
    - McpPresetDefinition: Dataclass capturing metadata and templates for a preset server.
    - McpPresetRegistry: Central registry to lookup presets, validate parameters, and construct McpServerConfig instances.
Relations:
    Used by vidbyte.agents.mixins.McpAttachableMixin to support one-line attachments.
    Interacts with vidbyte.tools.mcp.types.McpServerConfig.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vidbyte.lib.errors import McpError
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class McpPresetNotFoundError(McpError):
    """Raised when the requested MCP server preset is not registered."""


class McpPresetConfigurationError(McpError):
    """Raised when required environment configurations for a preset are missing."""


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
        # Registers a new preset definition in the global preset registry.
        cls._presets[definition.name] = definition

    @classmethod
    def get(cls, name: str) -> McpPresetDefinition:
        # Retrieves a preset definition by its name, raising an error if it does not exist.
        if name not in cls._presets:
            raise McpPresetNotFoundError(f"Preset MCP server '{name}' is not found in the catalog.")
        return cls._presets[name]

    @classmethod
    def list_presets(cls, category: str | None = None) -> tuple[McpPresetDefinition, ...]:
        # Returns all registered presets, optionally filtered by category.
        if category:
            return tuple(p for p in cls._presets.values() if p.category == category)
        return tuple(cls._presets.values())

    @classmethod
    def build_config(cls, preset_name: str, env: Mapping[str, str] | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, timeout: float = 30.0, extra_args: Sequence[str] | None = None) -> McpServerConfig:
        # Validates user arguments and constructs a concrete McpServerConfig for execution.
        preset = cls.get(preset_name)
        merged_env: dict[str, str] = {}
        if preset.default_env:
            merged_env.update(preset.default_env)
        if env:
            merged_env.update(env)

        missing_vars = [var for var in preset.required_env if var not in merged_env]
        if missing_vars:
            raise McpPresetConfigurationError(
                f"Preset '{preset_name}' requires the following environment variables: {', '.join(missing_vars)}"
            )

        cmd = list(preset.command)
        if extra_args:
            cmd.extend(extra_args)

        return McpServerConfig(
            command=tuple(cmd),
            name=preset.name,
            permission=permission,
            env=merged_env if merged_env else None,
            timeout=timeout,
        )


# ==========================================
# Popular MCP Presets Database Definitions
# ==========================================

_POPULAR_PRESETS: list[McpPresetDefinition] = [
    # Category: Search & Web Research
    McpPresetDefinition(
        name="brave-search",
        category="Search & Web Research",
        description="Executes privacy-focused web searches and crawls clean page text.",
        command=("npx", "-y", "@modelcontextprotocol/server-brave-search"),
        required_env=("BRAVE_API_KEY",),
    ),
    McpPresetDefinition(
        name="google-search",
        category="Search & Web Research",
        description="Executes web searches using Google Custom Search engine JSON API.",
        command=("npx", "-y", "@modelcontextprotocol/server-google-search"),
        required_env=("GOOGLE_API_KEY", "GOOGLE_CSE_ID"),
    ),
    McpPresetDefinition(
        name="tavily",
        category="Search & Web Research",
        description="LLM-optimized agentic web search that delivers ready-to-consume snippets.",
        command=("python", "-m", "mcp_server_tavily"),
        required_env=("TAVILY_API_KEY",),
    ),
    McpPresetDefinition(
        name="exa",
        category="Search & Web Research",
        description="Neural search engine utilizing embeddings to find hyper-relevant articles.",
        command=("npx", "-y", "@exa-labs/mcp-server"),
        required_env=("EXA_API_KEY",),
    ),
    McpPresetDefinition(
        name="duckduckgo",
        category="Search & Web Research",
        description="Free web search scraping DuckDuckGo results without API key requirements.",
        command=("python", "-m", "mcp_server_duckduckgo"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="puppeteer",
        category="Search & Web Research",
        description="Headless browser controller to view, screenshot, and scrape JavaScript-heavy pages.",
        command=("npx", "-y", "@modelcontextprotocol/server-puppeteer"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="playwright",
        category="Search & Web Research",
        description="High-level headless browser scraper using Python's Playwright integration.",
        command=("python", "-m", "mcp_server_playwright"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="searxng",
        category="Search & Web Research",
        description="Queries self-hosted privacy-respecting meta-search engine instances.",
        command=("python", "-m", "mcp_server_searxng"),
        required_env=("SEARXNG_URL",),
    ),
    McpPresetDefinition(
        name="firecrawl",
        category="Search & Web Research",
        description="Converts full, complex web pages into perfectly formatted markdown blocks.",
        command=("npx", "-y", "@firecrawl/mcp-server"),
        required_env=("FIRECRAWL_API_KEY",),
    ),
    McpPresetDefinition(
        name="jina-reader",
        category="Search & Web Research",
        description="Jina AI's URL reader converting web layouts into clean markdown representations.",
        command=("python", "-m", "mcp_server_jina_reader"),
        required_env=("JINA_API_KEY",),
    ),

    # Category: Version Control, Development & Task Tracking
    McpPresetDefinition(
        name="github",
        category="Version Control, Development & Task Tracking",
        description="Complete repository access, including issue tracking, PR management, and code file editing.",
        command=("npx", "-y", "@modelcontextprotocol/server-github"),
        required_env=("GITHUB_PERSONAL_ACCESS_TOKEN",),
    ),
    McpPresetDefinition(
        name="gitlab",
        category="Version Control, Development & Task Tracking",
        description="Integrates with self-hosted or cloud GitLab projects, branches, and issues.",
        command=("npx", "-y", "@modelcontextprotocol/server-gitlab"),
        required_env=("GITLAB_PERSONAL_ACCESS_TOKEN",),
    ),
    McpPresetDefinition(
        name="bitbucket",
        category="Version Control, Development & Task Tracking",
        description="Workspace administration, repo checking, and pull requests in Bitbucket.",
        command=("python", "-m", "mcp_server_bitbucket"),
        required_env=("BITBUCKET_USERNAME", "BITBUCKET_APP_PASSWORD"),
    ),
    McpPresetDefinition(
        name="jira",
        category="Version Control, Development & Task Tracking",
        description="Searches, creates, updates, and transitions software engineering sprint issues in Jira.",
        command=("npx", "-y", "mcp-server-jira"),
        required_env=("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"),
    ),
    McpPresetDefinition(
        name="linear",
        category="Version Control, Development & Task Tracking",
        description="Direct connection to modern, lightweight software sprint management backends.",
        command=("npx", "-y", "@linear/mcp-server"),
        required_env=("LINEAR_API_KEY",),
    ),
    McpPresetDefinition(
        name="sentry",
        category="Version Control, Development & Task Tracking",
        description="Inspects production error dashboards, tracks debug traces, and queries issues.",
        command=("npx", "-y", "@sentry/mcp-server"),
        required_env=("SENTRY_AUTH_TOKEN", "SENTRY_ORG"),
    ),
    McpPresetDefinition(
        name="sonarqube",
        category="Version Control, Development & Task Tracking",
        description="Triggers static analysis and reads Quality Gate status from SonarQube.",
        command=("python", "-m", "mcp_server_sonarqube"),
        required_env=("SONAR_TOKEN", "SONAR_HOST_URL"),
    ),
    McpPresetDefinition(
        name="docker",
        category="Version Control, Development & Task Tracking",
        description="Starts, stops, inspects, and logs standard local Docker container lifecycles.",
        command=("python", "-m", "mcp_server_docker"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="kubernetes",
        category="Version Control, Development & Task Tracking",
        description="Full cluster node, pod, and service diagnostics via standard Kubeconfigs.",
        command=("python", "-m", "mcp_server_kubernetes"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="jenkins",
        category="Version Control, Development & Task Tracking",
        description="Commands Jenkins pipelines, triggers parameters, and tracks job status logs.",
        command=("python", "-m", "mcp_server_jenkins"),
        required_env=("JENKINS_URL", "JENKINS_USER", "JENKINS_TOKEN"),
    ),
    McpPresetDefinition(
        name="circleci",
        category="Version Control, Development & Task Tracking",
        description="Fetches pipeline histories and checks project run states.",
        command=("python", "-m", "mcp_server_circleci"),
        required_env=("CIRCLECI_TOKEN",),
    ),
    McpPresetDefinition(
        name="vercel",
        category="Version Control, Development & Task Tracking",
        description="Accesses Vercel project deployments, changes domains, and returns log lines.",
        command=("npx", "-y", "vercel-mcp-server"),
        required_env=("VERCEL_TOKEN",),
    ),

    # Category: Databases & Cache
    McpPresetDefinition(
        name="postgres",
        category="Databases & Cache",
        description="Executes queries, discovers database schemas, and describes table structures.",
        command=("npx", "-y", "@modelcontextprotocol/server-postgres"),
        required_env=("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE"),
    ),
    McpPresetDefinition(
        name="mysql",
        category="Databases & Cache",
        description="Performs CRUD queries and checks schemas on standard MySQL servers.",
        command=("npx", "-y", "mcp-server-mysql"),
        required_env=("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"),
    ),
    McpPresetDefinition(
        name="sqlite",
        category="Databases & Cache",
        description="Inspects tables and manipulates local SQLite database files.",
        command=("npx", "-y", "@modelcontextprotocol/server-sqlite"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="mongodb",
        category="Databases & Cache",
        description="Integrates agent actions with schema-less MongoDB document databases.",
        command=("python", "-m", "mcp_server_mongodb"),
        required_env=("MONGODB_URI",),
    ),
    McpPresetDefinition(
        name="redis",
        category="Databases & Cache",
        description="Key-value data interactions and fast transient storage access.",
        command=("python", "-m", "mcp_server_redis"),
        required_env=("REDIS_URI",),
    ),
    McpPresetDefinition(
        name="supabase",
        category="Databases & Cache",
        description="Direct access to Supabase serverless database projects and edge instances.",
        command=("npx", "-y", "@supabase/mcp-server"),
        required_env=("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    ),
    McpPresetDefinition(
        name="neon",
        category="Databases & Cache",
        description="Spins up, branches, and queries serverless relational Neon Postgres engines.",
        command=("npx", "-y", "@neondatabase/mcp-server"),
        required_env=("NEON_API_KEY",),
    ),
    McpPresetDefinition(
        name="planetscale",
        category="Databases & Cache",
        description="Schema-safe branch operations on MySQL-compatible PlanetScale clusters.",
        command=("python", "-m", "mcp_server_planetscale"),
        required_env=("PLANETSCALE_SERVICE_TOKEN",),
    ),
    McpPresetDefinition(
        name="pinecone",
        category="Databases & Cache",
        description="Queries and updates dense, high-dimensional vector representations.",
        command=("python", "-m", "mcp_server_pinecone"),
        required_env=("PINECONE_API_KEY",),
    ),
    McpPresetDefinition(
        name="qdrant",
        category="Databases & Cache",
        description="High-performance semantic vector searches on Qdrant DB.",
        command=("python", "-m", "mcp_server_qdrant"),
        required_env=("QDRANT_URL", "QDRANT_API_KEY"),
    ),
    McpPresetDefinition(
        name="chromadb",
        category="Databases & Cache",
        description="Local and embedded Chroma vector databases for immediate knowledge storage.",
        command=("python", "-m", "mcp_server_chroma"),
        required_env=("CHROMA_SERVER_HOST",),
    ),
    McpPresetDefinition(
        name="clickhouse",
        category="Databases & Cache",
        description="Runs fast analytical columnar queries on mass data logs.",
        command=("python", "-m", "mcp_server_clickhouse"),
        required_env=("CLICKHOUSE_HOST", "CLICKHOUSE_PASSWORD"),
    ),

    # Category: Productivity, Office & CRM
    McpPresetDefinition(
        name="google-calendar",
        category="Productivity, Office & CRM",
        description="Lists, updates, schedules, and edits events on Google Calendars.",
        command=("python", "-m", "mcp_server_google_calendar"),
        required_env=("GOOGLE_CALENDAR_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="google-drive",
        category="Productivity, Office & CRM",
        description="Searches, exports, and downloads drive folders and office formats.",
        command=("python", "-m", "mcp_server_google_drive"),
        required_env=("GOOGLE_DRIVE_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="google-sheets",
        category="Productivity, Office & CRM",
        description="Appends cells and changes Google Sheet table calculations.",
        command=("python", "-m", "mcp_server_google_sheets"),
        required_env=("GOOGLE_SHEETS_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="gmail",
        category="Productivity, Office & CRM",
        description="Searches message histories, drafts auto-replies, and triggers emails.",
        command=("python", "-m", "mcp_server_gmail"),
        required_env=("GMAIL_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="notion",
        category="Productivity, Office & CRM",
        description="Queries database schemas, lists pages, and appends block markdown.",
        command=("npx", "-y", "@notionhq/mcp-server"),
        required_env=("NOTION_API_KEY",),
    ),
    McpPresetDefinition(
        name="coda",
        category="Productivity, Office & CRM",
        description="Edits complex docs and updates operational tables in Coda workspaces.",
        command=("npx", "-y", "coda-mcp-server"),
        required_env=("CODA_API_KEY",),
    ),
    McpPresetDefinition(
        name="outlook",
        category="Productivity, Office & CRM",
        description="Interacts with Microsoft Office Outlook mailbox folders.",
        command=("python", "-m", "mcp_server_outlook"),
        required_env=("OUTLOOK_OAUTH_TOKEN",),
    ),
    McpPresetDefinition(
        name="onedrive",
        category="Productivity, Office & CRM",
        description="Explores directories and processes files in Microsoft OneDrive.",
        command=("python", "-m", "mcp_server_onedrive"),
        required_env=("ONEDRIVE_OAUTH_TOKEN",),
    ),
    McpPresetDefinition(
        name="evernote",
        category="Productivity, Office & CRM",
        description="Handles Evernote accounts, notes, and checklist notebooks.",
        command=("python", "-m", "mcp_server_evernote"),
        required_env=("EVERNOTE_DEVELOPER_TOKEN",),
    ),
    McpPresetDefinition(
        name="salesforce",
        category="Productivity, Office & CRM",
        description="Explores opportunities, details leads, and appends logs in Salesforce.",
        command=("python", "-m", "mcp_server_salesforce"),
        required_env=("SALESFORCE_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="hubspot",
        category="Productivity, Office & CRM",
        description="Tracks marketing pipelines, registers client contacts, and closes deal tickets.",
        command=("npx", "-y", "@hubspot/mcp-server"),
        required_env=("HUBSPOT_ACCESS_TOKEN",),
    ),
    McpPresetDefinition(
        name="airtable",
        category="Productivity, Office & CRM",
        description="Edits rows, lists fields, and reads relational bases inside Airtable.",
        command=("npx", "-y", "airtable-mcp-server"),
        required_env=("AIRTABLE_API_KEY",),
    ),

    # Category: Document Parsers & Media Utilities
    McpPresetDefinition(
        name="pandoc",
        category="Document Parsers & Media Utilities",
        description="Converts documents between filetypes (e.g. HTML to Markdown, DOCX to EPUB).",
        command=("python", "-m", "mcp_server_pandoc"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="pdf-parser",
        category="Document Parsers & Media Utilities",
        description="Parses and structures metadata, text, and nested tables from PDF files.",
        command=("python", "-m", "mcp_server_pdf"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="ffmpeg",
        category="Document Parsers & Media Utilities",
        description="Splices, compresses, crops, and processes video and audio media files.",
        command=("python", "-m", "mcp_server_ffmpeg"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="imagemagick",
        category="Document Parsers & Media Utilities",
        description="Modifies, crops, and optimizes image file resolutions and formats.",
        command=("python", "-m", "mcp_server_imagemagick"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="graphviz",
        category="Document Parsers & Media Utilities",
        description="Compiles DOT text descriptions into clean SVG or PNG diagram files.",
        command=("python", "-m", "mcp_server_graphviz"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="tesseract-ocr",
        category="Document Parsers & Media Utilities",
        description="Extracts written or printed text content from scanned image pictures.",
        command=("python", "-m", "mcp_server_tesseract"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="markitdown",
        category="Document Parsers & Media Utilities",
        description="Microsoft MarkItDown tool converting XLSX, PPTX, PDF, and DOCX to high-fidelity Markdown.",
        command=("python", "-m", "mcp_server_markitdown"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="whisper",
        category="Document Parsers & Media Utilities",
        description="Generates text translations and subtitles from speech audio files.",
        command=("python", "-m", "mcp_server_whisper"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="xlsx-parser",
        category="Document Parsers & Media Utilities",
        description="Fast, low-memory extraction of raw spreadsheet sheets.",
        command=("python", "-m", "mcp_server_xlsx"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="epub-reader",
        category="Document Parsers & Media Utilities",
        description="Parses book chapters and internal indexes from EPUB publications.",
        command=("python", "-m", "mcp_server_epub"),
        required_env=(),
    ),

    # Category: Communication & Chat
    McpPresetDefinition(
        name="slack",
        category="Communication & Chat",
        description="Posts messages, uploads assets, and reads threads in Slack channels.",
        command=("npx", "-y", "@modelcontextprotocol/server-slack"),
        required_env=("SLACK_BOT_TOKEN",),
    ),
    McpPresetDefinition(
        name="discord",
        category="Communication & Chat",
        description="Reads announcements, handles roles, and posts embeds to Discord servers.",
        command=("python", "-m", "mcp_server_discord"),
        required_env=("DISCORD_BOT_TOKEN",),
    ),
    McpPresetDefinition(
        name="telegram",
        category="Communication & Chat",
        description="Automatically replies to messages and broadcasts updates through Telegram Bots.",
        command=("python", "-m", "mcp_server_telegram"),
        required_env=("TELEGRAM_BOT_TOKEN",),
    ),
    McpPresetDefinition(
        name="twilio",
        category="Communication & Chat",
        description="Delivers SMS messages and performs phone number security audits.",
        command=("python", "-m", "mcp_server_twilio"),
        required_env=("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"),
    ),
    McpPresetDefinition(
        name="sendgrid",
        category="Communication & Chat",
        description="Sends robust promotional or structural system transactional emails.",
        command=("python", "-m", "mcp_server_sendgrid"),
        required_env=("SENDGRID_API_KEY",),
    ),
    McpPresetDefinition(
        name="teams",
        category="Communication & Chat",
        description="Posts notifications and cards in Microsoft Teams organization pipelines.",
        command=("python", "-m", "mcp_server_teams"),
        required_env=("TEAMS_OAUTH_TOKEN",),
    ),
    McpPresetDefinition(
        name="whatsapp",
        category="Communication & Chat",
        description="Sends templated message scripts via the WhatsApp Business cloud API.",
        command=("python", "-m", "mcp_server_whatsapp"),
        required_env=("WHATSAPP_ACCESS_TOKEN",),
    ),
    McpPresetDefinition(
        name="zoom",
        category="Communication & Chat",
        description="Creates instant Zoom meeting URLs and adds scheduled conference entries.",
        command=("python", "-m", "mcp_server_zoom"),
        required_env=("ZOOM_OAUTH_TOKEN",),
    ),

    # Category: Cloud Platforms, Hosting & Infrastructure
    McpPresetDefinition(
        name="aws-ec2",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Lists, boots, and suspends virtual machine servers in Amazon EC2 zones.",
        command=("python", "-m", "mcp_server_aws_ec2"),
        required_env=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    ),
    McpPresetDefinition(
        name="aws-s3",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Creates buckets, downloads assets, and uploads files to AWS S3.",
        command=("python", "-m", "mcp_server_aws_s3"),
        required_env=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    ),
    McpPresetDefinition(
        name="aws-lambda",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Triggers lambda functions and updates code bundle zip folders.",
        command=("python", "-m", "mcp_server_aws_lambda"),
        required_env=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    ),
    McpPresetDefinition(
        name="gcp-compute",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Direct controller to spin up or terminate GCP VM instances.",
        command=("python", "-m", "mcp_server_gcp_compute"),
        required_env=("GOOGLE_APPLICATION_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="gcp-storage",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Lists files and handles buckets inside Google Cloud Storage.",
        command=("python", "-m", "mcp_server_gcp_storage"),
        required_env=("GOOGLE_APPLICATION_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="azure-vm",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Tracks VMs and reviews billing stats inside Microsoft Azure deployments.",
        command=("python", "-m", "mcp_server_azure_vm"),
        required_env=("AZURE_CREDENTIALS",),
    ),
    McpPresetDefinition(
        name="azure-blob",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Transfers large media objects into Azure Blob container slots.",
        command=("python", "-m", "mcp_server_azure_blob"),
        required_env=("AZURE_STORAGE_CONNECTION_STRING",),
    ),
    McpPresetDefinition(
        name="netlify",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Triggers static workspace builds and configures custom domain mappings.",
        command=("python", "-m", "mcp_server_netlify"),
        required_env=("NETLIFY_AUTH_TOKEN",),
    ),
    McpPresetDefinition(
        name="cloudflare",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Updates Cloudflare KV databases, checks DNS records, and deploys Workers.",
        command=("python", "-m", "mcp_server_cloudflare"),
        required_env=("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"),
    ),
    McpPresetDefinition(
        name="heroku",
        category="Cloud Platforms, Hosting & Infrastructure",
        description="Changes configurations, monitors Dynos, and restarts Heroku environments.",
        command=("python", "-m", "mcp_server_heroku"),
        required_env=("HEROKU_API_KEY",),
    ),

    # Category: AI Platforms & Creative APIs
    McpPresetDefinition(
        name="openai-agent",
        category="AI Platforms & Creative APIs",
        description="Generates text embeddings, retrieves fine-tuning logs, and controls assistants.",
        command=("python", "-m", "mcp_server_openai"),
        required_env=("OPENAI_API_KEY",),
    ),
    McpPresetDefinition(
        name="anthropic-agent",
        category="AI Platforms & Creative APIs",
        description="Manages prompt engineering benchmarks and parses Claude system templates.",
        command=("python", "-m", "mcp_server_anthropic"),
        required_env=("ANTHROPIC_API_KEY",),
    ),
    McpPresetDefinition(
        name="huggingface",
        category="AI Platforms & Creative APIs",
        description="Accesses open-source datasets, reviews code repositories, and downloads files.",
        command=("python", "-m", "mcp_server_huggingface"),
        required_env=("HUGGING_FACE_HUB_TOKEN",),
    ),
    McpPresetDefinition(
        name="replicate",
        category="AI Platforms & Creative APIs",
        description="Executes arbitrary high-quality image, video, and audio AI models on Replicate.",
        command=("npx", "-y", "replicate-mcp-server"),
        required_env=("REPLICATE_API_TOKEN",),
    ),
    McpPresetDefinition(
        name="midjourney",
        category="AI Platforms & Creative APIs",
        description="Starts Midjourney diffusion pipelines and fetches creative graphics assets.",
        command=("python", "-m", "mcp_server_midjourney"),
        required_env=("MIDJOURNEY_API_KEY",),
    ),
    McpPresetDefinition(
        name="elevenlabs",
        category="AI Platforms & Creative APIs",
        description="Creates high-fidelity text-to-speech audio files in diverse voices.",
        command=("python", "-m", "mcp_server_elevenlabs"),
        required_env=("ELEVENLABS_API_KEY",),
    ),
    McpPresetDefinition(
        name="fal-ai",
        category="AI Platforms & Creative APIs",
        description="Executes fast SDXL or video generation models on the Fal AI cloud compute.",
        command=("python", "-m", "mcp_server_fal"),
        required_env=("FAL_KEY",),
    ),
    McpPresetDefinition(
        name="groq",
        category="AI Platforms & Creative APIs",
        description="Ultra-fast LLM text generations powered by Groq LPU execution blocks.",
        command=("python", "-m", "mcp_server_groq"),
        required_env=("GROQ_API_KEY",),
    ),

    # Category: Reference & Academic
    McpPresetDefinition(
        name="wikipedia",
        category="Reference & Academic",
        description="Searches Wikipedia database index and returns accurate page snippets.",
        command=("python", "-m", "mcp_server_wikipedia"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="wolfram-alpha",
        category="Reference & Academic",
        description="Computes mathematical formulas, solves equations, and queries facts.",
        command=("python", "-m", "mcp_server_wolfram"),
        required_env=("WOLFRAM_APP_ID",),
    ),
    McpPresetDefinition(
        name="stackoverflow",
        category="Reference & Academic",
        description="Queries active developer questions, code files, and answers.",
        command=("python", "-m", "mcp_server_stackoverflow"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="arxiv",
        category="Reference & Academic",
        description="Pulls PDF papers, parses abstracts, and searches academic documents.",
        command=("python", "-m", "mcp_server_arxiv"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="mdn",
        category="Reference & Academic",
        description="Offline lookup tool for standard MDN Web CSS, HTML, and JS configurations.",
        command=("python", "-m", "mcp_server_mdn"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="devdocs",
        category="Reference & Academic",
        description="Instant keyword search mapping standard language structures in DevDocs.",
        command=("python", "-m", "mcp_server_devdocs"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="pubchem",
        category="Reference & Academic",
        description="Looks up chemical compound structures, IUPAC names, and lab safety details.",
        command=("python", "-m", "mcp_server_pubchem"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="geonames",
        category="Reference & Academic",
        description="Resolves latitude/longitude coords into administrative names and timezones.",
        command=("python", "-m", "mcp_server_geonames"),
        required_env=(),
    ),

    # Category: Native System & Utilities
    McpPresetDefinition(
        name="local-filesystem",
        category="Native System & Utilities",
        description="Standard tool for secure reading, editing, and listing files in specific folders.",
        command=("npx", "-y", "@modelcontextprotocol/server-filesystem"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="os-command",
        category="Native System & Utilities",
        description="Runs native terminal commands with strict timeouts and output filtering.",
        command=("python", "-m", "mcp_server_os"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="env-inspector",
        category="Native System & Utilities",
        description="Extracts operating system environment flags, path structures, and user details safely.",
        command=("python", "-m", "mcp_server_env"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="process-manager",
        category="Native System & Utilities",
        description="Monitors active system loops, processes, memory usage, and allows termination.",
        command=("python", "-m", "mcp_server_process"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="system-diagnostics",
        category="Native System & Utilities",
        description="Inspects hard disk allocations, hardware temperatures, and CPU core speeds.",
        command=("python", "-m", "mcp_server_diagnostics"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="markdown-linter",
        category="Native System & Utilities",
        description="Audits document styles, link integrity, and syntax violations.",
        command=("python", "-m", "mcp_server_markdown_linter"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="python-sandbox",
        category="Native System & Utilities",
        description="Runs raw mathematical or file logic inside isolated execution bubbles.",
        command=("python", "-m", "mcp_server_py_sandbox"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="sqlite-sandbox",
        category="Native System & Utilities",
        description="Performs isolated read-only operations on SQL command test tables.",
        command=("python", "-m", "mcp_server_sqlite_sandbox"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="csv-parser",
        category="Native System & Utilities",
        description="Parses massive comma-separated values, performs groupings, and generates statistics.",
        command=("python", "-m", "mcp_server_csv"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="json-validator",
        category="Native System & Utilities",
        description="Checks JSON document formats against schemas.",
        command=("python", "-m", "mcp_server_json"),
        required_env=(),
    ),
    McpPresetDefinition(
        name="sequential-thinking",
        category="Native System & Utilities",
        description="Grants agents the ability to reason step-by-step and break complex issues down logically.",
        command=("npx", "-y", "@modelcontextprotocol/server-sequential-thinking"),
        required_env=(),
    ),
]

for _preset in _POPULAR_PRESETS:
    McpPresetRegistry.register(_preset)
