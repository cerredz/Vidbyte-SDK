"""Context Protocol Header

Description:
    Exports MCP bridge client, transport, configuration, state handles, presets, and named preset constants.
Purpose:
    Provides a stable public surface for connecting external MCP tools and configuring
    automatic lifecycle attachments in the Vidbyte SDK.
Architecture:
    - McpClient: JSON-RPC operations.
    - McpStdioTransport: Subprocess stdio transport.
    - McpBridgedTool and McpToolBridge: Native wrappers for remote tools.
    - McpServerConfig: Immutable server configuration.
    - McpServerHandle: Live process connection wrapper.
    - McpToolPermission: Remote execution permissions.
    - McpPresetRegistry: Preset catalog and resolution builder.
    - Named preset constants (e.g. BraveSearchMCP): Direct import handles for each built-in preset.
Relations:
    Related to vidbyte.tools.registry, vidbyte.tools.executor, and agent mixins.
"""

from __future__ import annotations

from vidbyte.tools.mcp.bridge import McpBridgedTool, McpToolBridge
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.presets import (
    McpPresetConfigurationError,
    McpPresetDefinition,
    McpPresetNotFoundError,
    McpPresetRegistry,
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
)
from vidbyte.tools.mcp.transport import McpStdioTransport, McpTransport
from vidbyte.tools.mcp.types import (
    McpServerConfig,
    McpServerHandle,
    McpToolDefinition,
    McpToolPermission,
)

__all__ = [
    "McpBridgedTool",
    "McpClient",
    "McpPresetConfigurationError",
    "McpPresetDefinition",
    "McpPresetNotFoundError",
    "McpPresetRegistry",
    "McpServerConfig",
    "McpServerHandle",
    "McpStdioTransport",
    "McpToolBridge",
    "McpToolDefinition",
    "McpToolPermission",
    "McpTransport",
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
]
