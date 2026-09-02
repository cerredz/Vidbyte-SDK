"""Context Protocol Header

Description:
    Defines the McpPresetRegistry and wires built-in MCP server presets for one-line attachment.
Purpose:
    Allows developers to look up, validate, and build McpServerConfig instances from
    named presets without knowing command syntax or subprocess details.
Architecture:
    - McpPresetDefinition: Re-exported from vidbyte.lib.config.mcp_presets (canonical source).
    - McpPresetRegistry: Central registry with class-level preset attributes and build helpers.
    - Named preset constants (e.g. BraveSearchMCP) are re-exported for direct import.
Relations:
    Preset data lives in vidbyte.lib.config.mcp_presets.
    Used by vidbyte.agents.mixins.McpAttachableMixin to support one-line attachments.
    Interacts with vidbyte.tools.mcp.types.McpServerConfig.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from vidbyte.lib.errors import McpError
from vidbyte.lib.config.mcp_presets import (
    ALL_PRESETS,
    McpPresetDefinition,
    # Search & Web Research
    BraveSearchMCP, GoogleSearchMCP, TavilyMCP, ExaMCP, DuckduckgoMCP,
    PuppeteerMCP, PlaywrightMCP, SearxngMCP, FirecrawlMCP, JinaReaderMCP,
    # Version Control, Development & Task Tracking
    GithubMCP, GitlabMCP, BitbucketMCP, JiraMCP, LinearMCP, SentryMCP,
    SonarqubeMCP, DockerMCP, KubernetesMCP, JenkinsMCP, CircleciMCP, VercelMCP,
    # Databases & Cache
    PostgresMCP, MysqlMCP, SqliteMCP, MongodbMCP, RedisMCP, SupabaseMCP,
    NeonMCP, PlanetscaleMCP, PineconeMCP, QdrantMCP, ChromadbMCP, ClickhouseMCP,
    # Productivity, Office & CRM
    GoogleCalendarMCP, GoogleDriveMCP, GoogleSheetsMCP, GmailMCP, NotionMCP,
    CodaMCP, OutlookMCP, OnedriveMCP, EvernoteMCP, SalesforceMCP, HubspotMCP,
    AirtableMCP,
    # Document Parsers & Media Utilities
    PandocMCP, PdfParserMCP, FfmpegMCP, ImagemagickMCP, GraphvizMCP,
    TesseractOcrMCP, MarkitdownMCP, WhisperMCP, XlsxParserMCP, EpubReaderMCP,
    # Communication & Chat
    SlackMCP, DiscordMCP, TelegramMCP, TwilioMCP, SendgridMCP, TeamsMCP,
    WhatsappMCP, ZoomMCP,
    # Cloud Platforms, Hosting & Infrastructure
    AwsEc2MCP, AwsS3MCP, AwsLambdaMCP, GcpComputeMCP, GcpStorageMCP,
    AzureVmMCP, AzureBlobMCP, NetlifyMCP, CloudflareMCP, HerokuMCP,
    # AI Platforms & Creative APIs
    OpenaiAgentMCP, AnthropicAgentMCP, HuggingfaceMCP, ReplicateMCP,
    MidjourneyMCP, ElevenlabsMCP, FalAiMCP, GroqMCP,
    # Reference & Academic
    WikipediaMCP, WolframAlphaMCP, StackoverflowMCP, ArxivMCP, MdnMCP,
    DevdocsMCP, PubchemMCP, GeonamesMCP,
    # Native System & Utilities
    LocalFilesystemMCP, OsCommandMCP, EnvInspectorMCP, ProcessManagerMCP,
    SystemDiagnosticsMCP, MarkdownLinterMCP, PythonSandboxMCP, SqliteSandboxMCP,
    CsvParserMCP, JsonValidatorMCP, SequentialThinkingMCP,
    # E-Commerce & Payments
    StripeMCP, ShopifyMCP, WoocommerceMCP, SquareMCP, PaypalMCP,
    # Automation & Workflow
    ZapierMCP, N8nMCP,
    # Search & Web Research (additional)
    PerplexityMCP, SerperMCP, YouSearchMCP, ApifyMCP, BrowserbaseMCP,
    ZenrowsMCP, ScrapingbeeMCP, LinkupMCP,
    # Version Control, Development & Task Tracking (additional)
    AsanaMCP, TrelloMCP, ClickupMCP, PagerdutyMCP, DatadogMCP,
    NewrelicMCP, TerraformMCP, GithubActionsMCP, TravisCiMCP, MondayMCP,
    # Databases & Cache (additional)
    DynamodbMCP, CassandraMCP, ElasticsearchMCP, CockroachdbMCP, FirebaseMCP,
    WeaviateMCP, MilvusMCP, TimescaledbMCP, TursoMCP, FaunadbMCP,
    # Productivity, Office & CRM (additional)
    ObsidianVaultMCP, TodoistMCP, ConfluenceMCP, ZohoCrmMCP, IntercomMCP,
    PipedriveMCP, FreshserviceMCP, ZendeskMCP, SmartsheetMCP, BasecampMCP,
    # Document Parsers & Media Utilities (additional)
    DoclingMCP, UnstructuredMCP, CamelotMCP, PptxParserMCP, DocxParserMCP,
    LibreofficeMCP, VideoTranscriptMCP, ExifToolMCP,
    # Communication & Chat (additional)
    MattermostMCP, RocketchatMCP, MailgunMCP, PostmarkMCP, ResendMCP,
    LineMessagingMCP, PushoverMCP, MandrillMCP,
    # Cloud Platforms, Hosting & Infrastructure (additional)
    AwsRdsMCP, AwsCloudwatchMCP, GcpBigqueryMCP, AzureDevopsMCP, DigitaloceanMCP,
    FlyIoMCP, RailwayMCP, RenderMCP, LinodeMCP, VultrMCP,
    # AI Platforms & Creative APIs (additional)
    StabilityAiMCP, RunwayMCP, CohereSearchMCP, MistralMCP, TogetherAiMCP,
    DeepgramMCP, AssemblyAiMCP, HeygenMCP, SunoMCP, LangsmithMCP,
    # Reference & Academic (additional)
    PubmedMCP, CrossrefMCP, SemanticScholarMCP, OpenLibraryMCP, NpmRegistryMCP,
    PypiMCP, DockerHubMCP, OpenMeteoMCP,
    # Native System & Utilities (additional)
    GitMCP, HttpClientMCP, WebhookSenderMCP, YamlValidatorMCP, XmlParserMCP,
    TomlParserMCP, Base64ToolsMCP, HashingToolsMCP, UuidGeneratorMCP,
    RegexTesterMCP, DateTimeMCP,
)
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class McpPresetNotFoundError(McpError):
    """Raised when the requested MCP server preset is not registered."""


class McpPresetConfigurationError(McpError):
    """Raised when required environment configurations for a preset are missing."""


class McpPresetRegistry:
    """Central registry and query interface for all built-in MCP presets.

    Class attributes provide direct access to each preset definition:
        McpPresetRegistry.BraveSearch  ->  BraveSearchMCP definition
        McpPresetRegistry.Github       ->  GithubMCP definition
        ... (one attribute per preset, named in PascalCase without the MCP suffix)
    """

    _presets: ClassVar[dict[str, McpPresetDefinition]] = {}

    # ── Search & Web Research ────────────────────────────────────────────────
    BraveSearch: ClassVar[McpPresetDefinition] = BraveSearchMCP
    GoogleSearch: ClassVar[McpPresetDefinition] = GoogleSearchMCP
    Tavily: ClassVar[McpPresetDefinition] = TavilyMCP
    Exa: ClassVar[McpPresetDefinition] = ExaMCP
    Duckduckgo: ClassVar[McpPresetDefinition] = DuckduckgoMCP
    Puppeteer: ClassVar[McpPresetDefinition] = PuppeteerMCP
    Playwright: ClassVar[McpPresetDefinition] = PlaywrightMCP
    Searxng: ClassVar[McpPresetDefinition] = SearxngMCP
    Firecrawl: ClassVar[McpPresetDefinition] = FirecrawlMCP
    JinaReader: ClassVar[McpPresetDefinition] = JinaReaderMCP

    # ── Version Control, Development & Task Tracking ────────────────────────
    Github: ClassVar[McpPresetDefinition] = GithubMCP
    Gitlab: ClassVar[McpPresetDefinition] = GitlabMCP
    Bitbucket: ClassVar[McpPresetDefinition] = BitbucketMCP
    Jira: ClassVar[McpPresetDefinition] = JiraMCP
    Linear: ClassVar[McpPresetDefinition] = LinearMCP
    Sentry: ClassVar[McpPresetDefinition] = SentryMCP
    Sonarqube: ClassVar[McpPresetDefinition] = SonarqubeMCP
    Docker: ClassVar[McpPresetDefinition] = DockerMCP
    Kubernetes: ClassVar[McpPresetDefinition] = KubernetesMCP
    Jenkins: ClassVar[McpPresetDefinition] = JenkinsMCP
    Circleci: ClassVar[McpPresetDefinition] = CircleciMCP
    Vercel: ClassVar[McpPresetDefinition] = VercelMCP

    # ── Databases & Cache ────────────────────────────────────────────────────
    Postgres: ClassVar[McpPresetDefinition] = PostgresMCP
    Mysql: ClassVar[McpPresetDefinition] = MysqlMCP
    Sqlite: ClassVar[McpPresetDefinition] = SqliteMCP
    Mongodb: ClassVar[McpPresetDefinition] = MongodbMCP
    Redis: ClassVar[McpPresetDefinition] = RedisMCP
    Supabase: ClassVar[McpPresetDefinition] = SupabaseMCP
    Neon: ClassVar[McpPresetDefinition] = NeonMCP
    Planetscale: ClassVar[McpPresetDefinition] = PlanetscaleMCP
    Pinecone: ClassVar[McpPresetDefinition] = PineconeMCP
    Qdrant: ClassVar[McpPresetDefinition] = QdrantMCP
    Chromadb: ClassVar[McpPresetDefinition] = ChromadbMCP
    Clickhouse: ClassVar[McpPresetDefinition] = ClickhouseMCP

    # ── Productivity, Office & CRM ───────────────────────────────────────────
    GoogleCalendar: ClassVar[McpPresetDefinition] = GoogleCalendarMCP
    GoogleDrive: ClassVar[McpPresetDefinition] = GoogleDriveMCP
    GoogleSheets: ClassVar[McpPresetDefinition] = GoogleSheetsMCP
    Gmail: ClassVar[McpPresetDefinition] = GmailMCP
    Notion: ClassVar[McpPresetDefinition] = NotionMCP
    Coda: ClassVar[McpPresetDefinition] = CodaMCP
    Outlook: ClassVar[McpPresetDefinition] = OutlookMCP
    Onedrive: ClassVar[McpPresetDefinition] = OnedriveMCP
    Evernote: ClassVar[McpPresetDefinition] = EvernoteMCP
    Salesforce: ClassVar[McpPresetDefinition] = SalesforceMCP
    Hubspot: ClassVar[McpPresetDefinition] = HubspotMCP
    Airtable: ClassVar[McpPresetDefinition] = AirtableMCP

    # ── Document Parsers & Media Utilities ───────────────────────────────────
    Pandoc: ClassVar[McpPresetDefinition] = PandocMCP
    PdfParser: ClassVar[McpPresetDefinition] = PdfParserMCP
    Ffmpeg: ClassVar[McpPresetDefinition] = FfmpegMCP
    Imagemagick: ClassVar[McpPresetDefinition] = ImagemagickMCP
    Graphviz: ClassVar[McpPresetDefinition] = GraphvizMCP
    TesseractOcr: ClassVar[McpPresetDefinition] = TesseractOcrMCP
    Markitdown: ClassVar[McpPresetDefinition] = MarkitdownMCP
    Whisper: ClassVar[McpPresetDefinition] = WhisperMCP
    XlsxParser: ClassVar[McpPresetDefinition] = XlsxParserMCP
    EpubReader: ClassVar[McpPresetDefinition] = EpubReaderMCP

    # ── Communication & Chat ─────────────────────────────────────────────────
    Slack: ClassVar[McpPresetDefinition] = SlackMCP
    Discord: ClassVar[McpPresetDefinition] = DiscordMCP
    Telegram: ClassVar[McpPresetDefinition] = TelegramMCP
    Twilio: ClassVar[McpPresetDefinition] = TwilioMCP
    Sendgrid: ClassVar[McpPresetDefinition] = SendgridMCP
    Teams: ClassVar[McpPresetDefinition] = TeamsMCP
    Whatsapp: ClassVar[McpPresetDefinition] = WhatsappMCP
    Zoom: ClassVar[McpPresetDefinition] = ZoomMCP

    # ── Cloud Platforms, Hosting & Infrastructure ────────────────────────────
    AwsEc2: ClassVar[McpPresetDefinition] = AwsEc2MCP
    AwsS3: ClassVar[McpPresetDefinition] = AwsS3MCP
    AwsLambda: ClassVar[McpPresetDefinition] = AwsLambdaMCP
    GcpCompute: ClassVar[McpPresetDefinition] = GcpComputeMCP
    GcpStorage: ClassVar[McpPresetDefinition] = GcpStorageMCP
    AzureVm: ClassVar[McpPresetDefinition] = AzureVmMCP
    AzureBlob: ClassVar[McpPresetDefinition] = AzureBlobMCP
    Netlify: ClassVar[McpPresetDefinition] = NetlifyMCP
    Cloudflare: ClassVar[McpPresetDefinition] = CloudflareMCP
    Heroku: ClassVar[McpPresetDefinition] = HerokuMCP

    # ── AI Platforms & Creative APIs ────────────────────────────────────────
    OpenaiAgent: ClassVar[McpPresetDefinition] = OpenaiAgentMCP
    AnthropicAgent: ClassVar[McpPresetDefinition] = AnthropicAgentMCP
    Huggingface: ClassVar[McpPresetDefinition] = HuggingfaceMCP
    Replicate: ClassVar[McpPresetDefinition] = ReplicateMCP
    Midjourney: ClassVar[McpPresetDefinition] = MidjourneyMCP
    Elevenlabs: ClassVar[McpPresetDefinition] = ElevenlabsMCP
    FalAi: ClassVar[McpPresetDefinition] = FalAiMCP
    Groq: ClassVar[McpPresetDefinition] = GroqMCP

    # ── Reference & Academic ─────────────────────────────────────────────────
    Wikipedia: ClassVar[McpPresetDefinition] = WikipediaMCP
    WolframAlpha: ClassVar[McpPresetDefinition] = WolframAlphaMCP
    Stackoverflow: ClassVar[McpPresetDefinition] = StackoverflowMCP
    Arxiv: ClassVar[McpPresetDefinition] = ArxivMCP
    Mdn: ClassVar[McpPresetDefinition] = MdnMCP
    Devdocs: ClassVar[McpPresetDefinition] = DevdocsMCP
    Pubchem: ClassVar[McpPresetDefinition] = PubchemMCP
    Geonames: ClassVar[McpPresetDefinition] = GeonamesMCP

    # ── Native System & Utilities ─────────────────────────────────────────────
    LocalFilesystem: ClassVar[McpPresetDefinition] = LocalFilesystemMCP
    OsCommand: ClassVar[McpPresetDefinition] = OsCommandMCP
    EnvInspector: ClassVar[McpPresetDefinition] = EnvInspectorMCP
    ProcessManager: ClassVar[McpPresetDefinition] = ProcessManagerMCP
    SystemDiagnostics: ClassVar[McpPresetDefinition] = SystemDiagnosticsMCP
    MarkdownLinter: ClassVar[McpPresetDefinition] = MarkdownLinterMCP
    PythonSandbox: ClassVar[McpPresetDefinition] = PythonSandboxMCP
    SqliteSandbox: ClassVar[McpPresetDefinition] = SqliteSandboxMCP
    CsvParser: ClassVar[McpPresetDefinition] = CsvParserMCP
    JsonValidator: ClassVar[McpPresetDefinition] = JsonValidatorMCP
    SequentialThinking: ClassVar[McpPresetDefinition] = SequentialThinkingMCP

    # ── E-Commerce & Payments ────────────────────────────────────────────────
    Stripe: ClassVar[McpPresetDefinition] = StripeMCP
    Shopify: ClassVar[McpPresetDefinition] = ShopifyMCP
    Woocommerce: ClassVar[McpPresetDefinition] = WoocommerceMCP
    Square: ClassVar[McpPresetDefinition] = SquareMCP
    Paypal: ClassVar[McpPresetDefinition] = PaypalMCP

    # ── Automation & Workflow ─────────────────────────────────────────────────
    Zapier: ClassVar[McpPresetDefinition] = ZapierMCP
    N8n: ClassVar[McpPresetDefinition] = N8nMCP

    # ── Search & Web Research (additional) ───────────────────────────────────
    Perplexity: ClassVar[McpPresetDefinition] = PerplexityMCP
    Serper: ClassVar[McpPresetDefinition] = SerperMCP
    YouSearch: ClassVar[McpPresetDefinition] = YouSearchMCP
    Apify: ClassVar[McpPresetDefinition] = ApifyMCP
    Browserbase: ClassVar[McpPresetDefinition] = BrowserbaseMCP
    Zenrows: ClassVar[McpPresetDefinition] = ZenrowsMCP
    Scrapingbee: ClassVar[McpPresetDefinition] = ScrapingbeeMCP
    Linkup: ClassVar[McpPresetDefinition] = LinkupMCP

    # ── Version Control, Development & Task Tracking (additional) ────────────
    Asana: ClassVar[McpPresetDefinition] = AsanaMCP
    Trello: ClassVar[McpPresetDefinition] = TrelloMCP
    Clickup: ClassVar[McpPresetDefinition] = ClickupMCP
    Pagerduty: ClassVar[McpPresetDefinition] = PagerdutyMCP
    Datadog: ClassVar[McpPresetDefinition] = DatadogMCP
    Newrelic: ClassVar[McpPresetDefinition] = NewrelicMCP
    Terraform: ClassVar[McpPresetDefinition] = TerraformMCP
    GithubActions: ClassVar[McpPresetDefinition] = GithubActionsMCP
    TravisCi: ClassVar[McpPresetDefinition] = TravisCiMCP
    Monday: ClassVar[McpPresetDefinition] = MondayMCP

    # ── Databases & Cache (additional) ───────────────────────────────────────
    Dynamodb: ClassVar[McpPresetDefinition] = DynamodbMCP
    Cassandra: ClassVar[McpPresetDefinition] = CassandraMCP
    Elasticsearch: ClassVar[McpPresetDefinition] = ElasticsearchMCP
    Cockroachdb: ClassVar[McpPresetDefinition] = CockroachdbMCP
    Firebase: ClassVar[McpPresetDefinition] = FirebaseMCP
    Weaviate: ClassVar[McpPresetDefinition] = WeaviateMCP
    Milvus: ClassVar[McpPresetDefinition] = MilvusMCP
    Timescaledb: ClassVar[McpPresetDefinition] = TimescaledbMCP
    Turso: ClassVar[McpPresetDefinition] = TursoMCP
    Faunadb: ClassVar[McpPresetDefinition] = FaunadbMCP

    # ── Productivity, Office & CRM (additional) ──────────────────────────────
    ObsidianVault: ClassVar[McpPresetDefinition] = ObsidianVaultMCP
    Todoist: ClassVar[McpPresetDefinition] = TodoistMCP
    Confluence: ClassVar[McpPresetDefinition] = ConfluenceMCP
    ZohoCrm: ClassVar[McpPresetDefinition] = ZohoCrmMCP
    Intercom: ClassVar[McpPresetDefinition] = IntercomMCP
    Pipedrive: ClassVar[McpPresetDefinition] = PipedriveMCP
    Freshservice: ClassVar[McpPresetDefinition] = FreshserviceMCP
    Zendesk: ClassVar[McpPresetDefinition] = ZendeskMCP
    Smartsheet: ClassVar[McpPresetDefinition] = SmartsheetMCP
    Basecamp: ClassVar[McpPresetDefinition] = BasecampMCP

    # ── Document Parsers & Media Utilities (additional) ──────────────────────
    Docling: ClassVar[McpPresetDefinition] = DoclingMCP
    Unstructured: ClassVar[McpPresetDefinition] = UnstructuredMCP
    Camelot: ClassVar[McpPresetDefinition] = CamelotMCP
    PptxParser: ClassVar[McpPresetDefinition] = PptxParserMCP
    DocxParser: ClassVar[McpPresetDefinition] = DocxParserMCP
    Libreoffice: ClassVar[McpPresetDefinition] = LibreofficeMCP
    VideoTranscript: ClassVar[McpPresetDefinition] = VideoTranscriptMCP
    ExifTool: ClassVar[McpPresetDefinition] = ExifToolMCP

    # ── Communication & Chat (additional) ────────────────────────────────────
    Mattermost: ClassVar[McpPresetDefinition] = MattermostMCP
    Rocketchat: ClassVar[McpPresetDefinition] = RocketchatMCP
    Mailgun: ClassVar[McpPresetDefinition] = MailgunMCP
    Postmark: ClassVar[McpPresetDefinition] = PostmarkMCP
    Resend: ClassVar[McpPresetDefinition] = ResendMCP
    LineMessaging: ClassVar[McpPresetDefinition] = LineMessagingMCP
    Pushover: ClassVar[McpPresetDefinition] = PushoverMCP
    Mandrill: ClassVar[McpPresetDefinition] = MandrillMCP

    # ── Cloud Platforms, Hosting & Infrastructure (additional) ───────────────
    AwsRds: ClassVar[McpPresetDefinition] = AwsRdsMCP
    AwsCloudwatch: ClassVar[McpPresetDefinition] = AwsCloudwatchMCP
    GcpBigquery: ClassVar[McpPresetDefinition] = GcpBigqueryMCP
    AzureDevops: ClassVar[McpPresetDefinition] = AzureDevopsMCP
    Digitalocean: ClassVar[McpPresetDefinition] = DigitaloceanMCP
    FlyIo: ClassVar[McpPresetDefinition] = FlyIoMCP
    Railway: ClassVar[McpPresetDefinition] = RailwayMCP
    Render: ClassVar[McpPresetDefinition] = RenderMCP
    Linode: ClassVar[McpPresetDefinition] = LinodeMCP
    Vultr: ClassVar[McpPresetDefinition] = VultrMCP

    # ── AI Platforms & Creative APIs (additional) ─────────────────────────────
    StabilityAi: ClassVar[McpPresetDefinition] = StabilityAiMCP
    Runway: ClassVar[McpPresetDefinition] = RunwayMCP
    CohereSearch: ClassVar[McpPresetDefinition] = CohereSearchMCP
    Mistral: ClassVar[McpPresetDefinition] = MistralMCP
    TogetherAi: ClassVar[McpPresetDefinition] = TogetherAiMCP
    Deepgram: ClassVar[McpPresetDefinition] = DeepgramMCP
    AssemblyAi: ClassVar[McpPresetDefinition] = AssemblyAiMCP
    Heygen: ClassVar[McpPresetDefinition] = HeygenMCP
    Suno: ClassVar[McpPresetDefinition] = SunoMCP
    Langsmith: ClassVar[McpPresetDefinition] = LangsmithMCP

    # ── Reference & Academic (additional) ────────────────────────────────────
    Pubmed: ClassVar[McpPresetDefinition] = PubmedMCP
    Crossref: ClassVar[McpPresetDefinition] = CrossrefMCP
    SemanticScholar: ClassVar[McpPresetDefinition] = SemanticScholarMCP
    OpenLibrary: ClassVar[McpPresetDefinition] = OpenLibraryMCP
    NpmRegistry: ClassVar[McpPresetDefinition] = NpmRegistryMCP
    Pypi: ClassVar[McpPresetDefinition] = PypiMCP
    DockerHub: ClassVar[McpPresetDefinition] = DockerHubMCP
    OpenMeteo: ClassVar[McpPresetDefinition] = OpenMeteoMCP

    # ── Native System & Utilities (additional) ────────────────────────────────
    Git: ClassVar[McpPresetDefinition] = GitMCP
    HttpClient: ClassVar[McpPresetDefinition] = HttpClientMCP
    WebhookSender: ClassVar[McpPresetDefinition] = WebhookSenderMCP
    YamlValidator: ClassVar[McpPresetDefinition] = YamlValidatorMCP
    XmlParser: ClassVar[McpPresetDefinition] = XmlParserMCP
    TomlParser: ClassVar[McpPresetDefinition] = TomlParserMCP
    Base64Tools: ClassVar[McpPresetDefinition] = Base64ToolsMCP
    HashingTools: ClassVar[McpPresetDefinition] = HashingToolsMCP
    UuidGenerator: ClassVar[McpPresetDefinition] = UuidGeneratorMCP
    RegexTester: ClassVar[McpPresetDefinition] = RegexTesterMCP
    DateTime: ClassVar[McpPresetDefinition] = DateTimeMCP

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
    def build_config(
        cls,
        preset_name: str,
        env: Mapping[str, str] | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> McpServerConfig:
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


# Register every built-in preset from the config catalog.
for _preset in ALL_PRESETS:
    McpPresetRegistry.register(_preset)


__all__ = [
    "McpPresetDefinition",
    "McpPresetNotFoundError",
    "McpPresetConfigurationError",
    "McpPresetRegistry",
    # Named preset constants re-exported for direct import
    # Search & Web Research
    "BraveSearchMCP", "GoogleSearchMCP", "TavilyMCP", "ExaMCP", "DuckduckgoMCP",
    "PuppeteerMCP", "PlaywrightMCP", "SearxngMCP", "FirecrawlMCP", "JinaReaderMCP",
    # Version Control, Development & Task Tracking
    "GithubMCP", "GitlabMCP", "BitbucketMCP", "JiraMCP", "LinearMCP", "SentryMCP",
    "SonarqubeMCP", "DockerMCP", "KubernetesMCP", "JenkinsMCP", "CircleciMCP", "VercelMCP",
    # Databases & Cache
    "PostgresMCP", "MysqlMCP", "SqliteMCP", "MongodbMCP", "RedisMCP", "SupabaseMCP",
    "NeonMCP", "PlanetscaleMCP", "PineconeMCP", "QdrantMCP", "ChromadbMCP", "ClickhouseMCP",
    # Productivity, Office & CRM
    "GoogleCalendarMCP", "GoogleDriveMCP", "GoogleSheetsMCP", "GmailMCP", "NotionMCP",
    "CodaMCP", "OutlookMCP", "OnedriveMCP", "EvernoteMCP", "SalesforceMCP", "HubspotMCP",
    "AirtableMCP",
    # Document Parsers & Media Utilities
    "PandocMCP", "PdfParserMCP", "FfmpegMCP", "ImagemagickMCP", "GraphvizMCP",
    "TesseractOcrMCP", "MarkitdownMCP", "WhisperMCP", "XlsxParserMCP", "EpubReaderMCP",
    # Communication & Chat
    "SlackMCP", "DiscordMCP", "TelegramMCP", "TwilioMCP", "SendgridMCP", "TeamsMCP",
    "WhatsappMCP", "ZoomMCP",
    # Cloud Platforms, Hosting & Infrastructure
    "AwsEc2MCP", "AwsS3MCP", "AwsLambdaMCP", "GcpComputeMCP", "GcpStorageMCP",
    "AzureVmMCP", "AzureBlobMCP", "NetlifyMCP", "CloudflareMCP", "HerokuMCP",
    # AI Platforms & Creative APIs
    "OpenaiAgentMCP", "AnthropicAgentMCP", "HuggingfaceMCP", "ReplicateMCP",
    "MidjourneyMCP", "ElevenlabsMCP", "FalAiMCP", "GroqMCP",
    # Reference & Academic
    "WikipediaMCP", "WolframAlphaMCP", "StackoverflowMCP", "ArxivMCP", "MdnMCP",
    "DevdocsMCP", "PubchemMCP", "GeonamesMCP",
    # Native System & Utilities
    "LocalFilesystemMCP", "OsCommandMCP", "EnvInspectorMCP", "ProcessManagerMCP",
    "SystemDiagnosticsMCP", "MarkdownLinterMCP", "PythonSandboxMCP", "SqliteSandboxMCP",
    "CsvParserMCP", "JsonValidatorMCP", "SequentialThinkingMCP",
    # E-Commerce & Payments
    "StripeMCP", "ShopifyMCP", "WoocommerceMCP", "SquareMCP", "PaypalMCP",
    # Automation & Workflow
    "ZapierMCP", "N8nMCP",
    # Search & Web Research (additional)
    "PerplexityMCP", "SerperMCP", "YouSearchMCP", "ApifyMCP", "BrowserbaseMCP",
    "ZenrowsMCP", "ScrapingbeeMCP", "LinkupMCP",
    # Version Control, Development & Task Tracking (additional)
    "AsanaMCP", "TrelloMCP", "ClickupMCP", "PagerdutyMCP", "DatadogMCP",
    "NewrelicMCP", "TerraformMCP", "GithubActionsMCP", "TravisCiMCP", "MondayMCP",
    # Databases & Cache (additional)
    "DynamodbMCP", "CassandraMCP", "ElasticsearchMCP", "CockroachdbMCP", "FirebaseMCP",
    "WeaviateMCP", "MilvusMCP", "TimescaledbMCP", "TursoMCP", "FaunadbMCP",
    # Productivity, Office & CRM (additional)
    "ObsidianVaultMCP", "TodoistMCP", "ConfluenceMCP", "ZohoCrmMCP", "IntercomMCP",
    "PipedriveMCP", "FreshserviceMCP", "ZendeskMCP", "SmartsheetMCP", "BasecampMCP",
    # Document Parsers & Media Utilities (additional)
    "DoclingMCP", "UnstructuredMCP", "CamelotMCP", "PptxParserMCP", "DocxParserMCP",
    "LibreofficeMCP", "VideoTranscriptMCP", "ExifToolMCP",
    # Communication & Chat (additional)
    "MattermostMCP", "RocketchatMCP", "MailgunMCP", "PostmarkMCP", "ResendMCP",
    "LineMessagingMCP", "PushoverMCP", "MandrillMCP",
    # Cloud Platforms, Hosting & Infrastructure (additional)
    "AwsRdsMCP", "AwsCloudwatchMCP", "GcpBigqueryMCP", "AzureDevopsMCP", "DigitaloceanMCP",
    "FlyIoMCP", "RailwayMCP", "RenderMCP", "LinodeMCP", "VultrMCP",
    # AI Platforms & Creative APIs (additional)
    "StabilityAiMCP", "RunwayMCP", "CohereSearchMCP", "MistralMCP", "TogetherAiMCP",
    "DeepgramMCP", "AssemblyAiMCP", "HeygenMCP", "SunoMCP", "LangsmithMCP",
    # Reference & Academic (additional)
    "PubmedMCP", "CrossrefMCP", "SemanticScholarMCP", "OpenLibraryMCP", "NpmRegistryMCP",
    "PypiMCP", "DockerHubMCP", "OpenMeteoMCP",
    # Native System & Utilities (additional)
    "GitMCP", "HttpClientMCP", "WebhookSenderMCP", "YamlValidatorMCP", "XmlParserMCP",
    "TomlParserMCP", "Base64ToolsMCP", "HashingToolsMCP", "UuidGeneratorMCP",
    "RegexTesterMCP", "DateTimeMCP",
]
