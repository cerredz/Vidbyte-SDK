"""FILE: tests/features/agent_output_connectors/test_output_connectors_contract.py

PURPOSE: Pin the public and structural contract of agent output connectors: the exported names and where they live, the enum values, the connector Protocol and base class, record validation, the operational constants the requirements name, the import layering between vidbyte/lib and vidbyte/agents, and the documentation the feature ships with.
ROLE IN CODEBASE: Contract tests over vidbyte/__init__.py, vidbyte/agents/output/, vidbyte/lib/outputs/, vidbyte/lib/{enums,constants,dataclasses}/outputs.py, vidbyte/lib/errors, and the READMEs and REPO_MAP.md entries the spec requires.
ARCHITECTURE NOTE: The layering check parses source with ast instead of importing it, so a function-level import of a higher layer is caught too; imports under `if TYPE_CHECKING:` are allowed, as the spec permits.
FUNCTION INVENTORY: test_public_names_* (FR-18, D-16); test_destination_and_status_values_* (§8.5); test_every_connector_* (FR-5, FR-6); test_base_output_* (FR-5); test_records_* (§9.1); test_operational_constants_* (FR-11, FR-12, INV-9, INV-11, INV-14, INV-15, §9.3); test_lib_output_modules_never_import_* and test_agent_side_* (NFR-7, §12.2); test_docs_* (AC-26, FR-19, FR-20).
COMMON MODIFICATION PATTERNS: When a public name is added, add it to ROOT_NAMES and to the spec's §9.2 list in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not loosen the layering check to module-level imports only; NFR-7 forbids function-level imports too. 2. Do not compare README text beyond the facts AC-26 requires.
KNOWN EDGE CASES: OutputShaping, BaseOutput, and the lib helpers are deliberately not root exports. Relative imports are resolved against the file's package before the layering check.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§7 FR-18, NFR-7; §8.5; §9.1; §9.2; §12.2; §12.3 rows 2, 19-23, 33-36)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_contract.py
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import re
import sys
from pathlib import Path

import pytest

import vidbyte
from tests.features.agent_output_connectors.factories import (
    CONNECTOR_CASES,
    OUTPUT_ENV_VARS,
    SLACK_URL,
    ScriptedConnector,
)
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT_NAMES = (
    "OutputConnector",
    "OutputContent",
    "DeliveryReceipt",
    "DeliveryStatus",
    "OutputDestination",
    "TypefullyPlatform",
    "OutputDeliveryError",
    "OutputDispatcher",
    "SlackOutput",
    "DiscordOutput",
    "TeamsOutput",
    "GoogleChatOutput",
    "TelegramOutput",
    "EmailOutput",
    "GitHubIssueOutput",
    "LinearIssueOutput",
    "JiraIssueOutput",
    "NotionPageOutput",
    "WebhookOutput",
    "GitLabIssueOutput",
    "GitHubJobSummaryOutput",
    "ConfluencePageOutput",
    "TypefullyDraftOutput",
    "HubSpotTaskOutput",
)
CONNECTOR_NAMES = ROOT_NAMES[8:]
NOT_ROOT_NAMES = ("OutputShaping", "BaseOutput", "OutputArguments", "OutputText", "OutputHttp", "OutputSmtp", "OutputRequest", "SmtpSettings")
LIB_OUTPUT_MODULES = ("__init__", "base", "text", "delivery", "slack", "discord", "teams", "google_chat", "telegram", "email", "github", "linear", "jira", "notion", "webhook", "adf", "github_api", "gitlab", "github_job_summary", "confluence", "typefully", "hubspot")
AGENT_OUTPUT_MODULES = ("__init__", "connector", "dispatcher")


def _names(pattern: str, message: str) -> bool:
    return re.search(rf"\b{re.escape(pattern)}\b", message) is not None


def test_public_names_are_exported_from_the_agent_output_package_and_the_root(output_api) -> None:
    # FR-18 / D-16 / §9.2: 24 root names (follow-ups FR-29), OutputDispatcher included, the same objects in vidbyte.agents.output.
    assert sorted(output_api.__all__) == sorted(ROOT_NAMES)
    assert len(output_api.__all__) == 24
    assert "OutputShaping" not in output_api.__all__
    for name in ROOT_NAMES:
        assert name in vidbyte.__all__, name
        assert getattr(vidbyte, name) is getattr(output_api, name), name
    assert [name for name in NOT_ROOT_NAMES if name in vidbyte.__all__] == []


def test_public_names_live_in_their_placement_modules(output_api) -> None:
    # D-2 / AGENTS.md placement rules: enums, records, the error, the provider classes, and the agent-side contract each have one home.
    enums = importlib.import_module("vidbyte.lib.enums")
    errors = importlib.import_module("vidbyte.lib.errors")
    records = importlib.import_module("vidbyte.lib.dataclasses.outputs")
    lib_outputs = importlib.import_module("vidbyte.lib.outputs")
    assert {"DeliveryStatus", "OutputDestination"} <= set(enums.__all__)
    assert enums.OutputDestination is output_api.OutputDestination and enums.DeliveryStatus is output_api.DeliveryStatus
    assert output_api.OutputDestination.__module__ == "vidbyte.lib.enums.outputs"
    assert "OutputDeliveryError" in errors.__all__ and errors.OutputDeliveryError is output_api.OutputDeliveryError
    assert issubclass(output_api.OutputDeliveryError, AgentExecutionError)
    assert records.OutputContent is output_api.OutputContent and records.DeliveryReceipt is output_api.DeliveryReceipt
    assert {"BaseOutput", "OutputArguments", "OutputText", "OutputHttp", "OutputSmtp", *CONNECTOR_NAMES} <= set(lib_outputs.__all__)
    assert all(getattr(lib_outputs, name) is getattr(output_api, name) for name in CONNECTOR_NAMES)
    assert output_api.OutputConnector.__module__ == "vidbyte.agents.output.connector"
    assert output_api.OutputDispatcher.__module__ == "vidbyte.agents.output.dispatcher"
    assert importlib.import_module("vidbyte.agents.output.connector").OutputShaping.__module__ == "vidbyte.agents.output.connector"


def test_destination_and_status_values_are_the_documented_strings(output_api) -> None:
    # §8.5: these values appear in receipts, error messages, and the missing-credential message.
    assert issubclass(output_api.OutputDestination, str) and issubclass(output_api.DeliveryStatus, str)
    assert [member.value for member in output_api.OutputDestination] == ["slack", "discord", "teams", "google_chat", "telegram", "email", "github_issue", "linear_issue", "jira_issue", "notion_page", "webhook", "gitlab_issue", "github_job_summary", "confluence_page", "typefully_draft", "hubspot_task"]
    assert [member.value for member in output_api.DeliveryStatus] == ["sent", "failed", "skipped"]


def test_every_connector_is_a_base_output_that_satisfies_the_protocol_and_masks_its_repr(output_api, any_case) -> None:
    # FR-5 / FR-6 / D-11: one class per destination, structurally an OutputConnector, with a masked repr.
    from vidbyte.lib.outputs import BaseOutput

    cls = getattr(output_api, any_case.class_name)
    connector = any_case.build(output_api)
    assert issubclass(cls, BaseOutput)
    assert cls.destination is output_api.OutputDestination(any_case.key)
    assert connector.destination is output_api.OutputDestination(any_case.key)
    assert isinstance(connector, output_api.OutputConnector)
    assert repr(connector) == f"{any_case.class_name}(credential='***')"
    assert connector.render is None


def test_base_output_is_abstract_and_render_is_a_read_only_property(output_api) -> None:
    # FR-5: BaseOutput stores render and declares send; it cannot be built on its own.
    from vidbyte.lib.outputs import BaseOutput

    def render(reply):
        return output_api.OutputContent("X", "Y")

    with pytest.raises(TypeError):
        BaseOutput()
    connector = output_api.SlackOutput(webhook_url=SLACK_URL, render=render)
    assert connector.render is render
    with pytest.raises(AttributeError):
        connector.render = None


def test_protocol_accepts_a_caller_written_connector_and_rejects_a_plain_object(output_api) -> None:
    # FR-5: OutputConnector is runtime-checkable and structural.
    assert isinstance(ScriptedConnector(output_api.OutputDestination.WEBHOOK), output_api.OutputConnector)
    assert not isinstance(object(), output_api.OutputConnector)


def _receipt_cases(api):
    destination, status = api.OutputDestination, api.DeliveryStatus
    return [
        ("failed-without-code", {"destination": destination.SLACK, "status": status.FAILED}, "error_code"),
        ("failed-with-blank-code", {"destination": destination.SLACK, "status": status.FAILED, "error_code": "  "}, "error_code"),
        ("sent-with-code", {"destination": destination.SLACK, "status": status.SENT, "error_code": "http_500"}, "error_code"),
        ("failed-with-url", {"destination": destination.GITHUB_ISSUE, "status": status.FAILED, "url": "https://github.com/acme/shop/issues/1", "error_code": "network"}, "url"),
        ("skipped-with-url", {"destination": destination.GITHUB_ISSUE, "status": status.SKIPPED, "url": "https://github.com/acme/shop/issues/1"}, "url"),
        ("sent-with-plain-http-url", {"destination": destination.GITHUB_ISSUE, "status": status.SENT, "url": "http://github.com/acme/shop/issues/1"}, "url"),
        ("destination-as-text", {"destination": "slack", "status": status.SENT}, "destination"),
        ("status-as-text", {"destination": destination.SLACK, "status": "sent"}, "status"),
    ]


@pytest.mark.parametrize("case", ["failed-without-code", "failed-with-blank-code", "sent-with-code", "failed-with-url", "skipped-with-url", "sent-with-plain-http-url", "destination-as-text", "status-as-text"])
def test_records_reject_an_invalid_receipt_naming_the_field(output_api, case) -> None:
    # §9.1: error_code exactly when FAILED; url only when SENT and https; enum-typed destination and status.
    [(_, arguments, field)] = [row for row in _receipt_cases(output_api) if row[0] == case]

    with pytest.raises(ConfigurationError) as info:
        output_api.DeliveryReceipt(**arguments)

    assert _names(field, str(info.value)), str(info.value)


def test_records_accept_valid_receipts_and_content_and_are_frozen(output_api) -> None:
    # §9.1 / AGENTS.md Style 4: frozen, slotted records.
    destination, status = output_api.OutputDestination, output_api.DeliveryStatus
    sent = output_api.DeliveryReceipt(destination=destination.GITHUB_ISSUE, status=status.SENT, url="https://github.com/acme/shop/issues/412")
    output_api.DeliveryReceipt(destination=destination.SLACK, status=status.FAILED, error_code="network")
    output_api.DeliveryReceipt(destination=destination.SLACK, status=status.SKIPPED)
    content = output_api.OutputContent("Checkout bug", "SAVE10 is ignored.")
    for record in (sent, content):
        assert dataclasses.is_dataclass(record)
        assert type(record).__dataclass_params__.frozen
        assert hasattr(type(record), "__slots__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        content.title = "Changed"


@pytest.mark.parametrize(("title", "body", "field"), [(" ", "body", "title"), ("title", "", "body"), (7, "body", "title"), ("title", None, "body")])
def test_records_reject_blank_or_non_text_content_naming_the_field(output_api, title, body, field) -> None:
    # §9.1: both title and body are non-blank str.
    with pytest.raises(ConfigurationError) as info:
        output_api.OutputContent(title, body)

    assert _names(field, str(info.value)), str(info.value)


SMTP_BASE = {"host": "smtp.gmail.com", "port": 587, "username": "bot@acme.com", "password": "S3CRETsmtp", "sender": "bot@acme.com", "recipients": ("ops@acme.com",)}


@pytest.mark.parametrize(
    ("record", "arguments", "field"),
    [
        ("OutputRequest", {"url": "http://hooks.slack.com/services/T/B/X", "headers": {}, "json_body": {}}, "url"),
        ("OutputRequest", {"url": SLACK_URL, "headers": {"authorization": 7}, "json_body": {}}, "headers"),
        ("OutputRequest", {"url": SLACK_URL, "headers": {}, "json_body": {}, "link_path": ("",)}, "link_path"),
        ("SmtpSettings", {**SMTP_BASE, "port": 0}, "port"),
        ("SmtpSettings", {**SMTP_BASE, "port": 65_536}, "port"),
        ("SmtpSettings", {**SMTP_BASE, "port": True}, "port"),
        ("SmtpSettings", {**SMTP_BASE, "host": "smtp gmail.com"}, "host"),
        ("SmtpSettings", {**SMTP_BASE, "password": " "}, "password"),
        ("SmtpSettings", {**SMTP_BASE, "sender": "bot acme.com"}, "sender"),
        ("SmtpSettings", {**SMTP_BASE, "recipients": ()}, "recipients"),
        ("SmtpSettings", {**SMTP_BASE, "recipients": ("ops@acme.com", "ops,cfo@acme.com")}, "recipients"),
    ],
)
def test_records_reject_invalid_requests_and_smtp_settings_naming_the_field(record, arguments, field) -> None:
    # §9.1: the records validate themselves, so an invalid request or SMTP session cannot be built.
    records = importlib.import_module("vidbyte.lib.dataclasses.outputs")

    with pytest.raises(ConfigurationError) as info:
        getattr(records, record)(**arguments)

    assert _names(field, str(info.value)), str(info.value)
    assert "S3CRET" not in str(info.value)


def test_operational_constants_hold_the_values_the_requirements_name(output_api, output_constants) -> None:
    # FR-11 / FR-12 / INV-9 / INV-11 / INV-14 / INV-15 / NFR-2 / §9.3: the named bounds the behavior tests rely on.
    c = output_constants
    assert (c.OUTPUT_TIMEOUT_SECONDS, c.OUTPUT_RATE_LIMIT_RETRIES, c.OUTPUT_RETRY_STATUS_CODES) == (10.0, 2, (429,))
    assert (c.OUTPUT_MAX_RESPONSE_BYTES, c.OUTPUT_DELIVERY_DEADLINE_SECONDS) == (1_000_000, 35.0)
    assert c.OUTPUT_DELIVERABLE_STOP_REASONS == frozenset({"final_response", "is_done"})
    assert (c.OUTPUT_DELIVERIES_METADATA_KEY, c.OUTPUT_TRUNCATION_MARKER, c.OUTPUT_TITLE_MAX_CHARS) == ("deliveries", "\n\n[truncated]", 250)
    assert c.OUTPUT_ERROR_TOKEN_PATTERN == r"[a-z][a-z0-9_]{0,63}"
    assert {destination.value: name for destination, name in c.OUTPUT_CREDENTIAL_ENV_VARS.items()} == {key: CONNECTOR_CASES[key].env_var for key in CONNECTOR_CASES}
    assert sorted(c.OUTPUT_CREDENTIAL_ENV_VARS.values()) == sorted(OUTPUT_ENV_VARS)
    with pytest.raises(TypeError):
        c.OUTPUT_CREDENTIAL_ENV_VARS[output_api.OutputDestination.SLACK] = "OTHER"
    assert {"OUTPUT_TIMEOUT_SECONDS", "OUTPUT_DELIVERY_DEADLINE_SECONDS", "OUTPUT_CREDENTIAL_ENV_VARS"} <= set(c.__all__)


class _RuntimeImports(ast.NodeVisitor):
    """Collects absolute module names a file imports at runtime, skipping `if TYPE_CHECKING:` bodies."""

    def __init__(self, package: str) -> None:
        self.package = package.split(".")
        self.modules: list[tuple[int, str]] = []

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
        for child in node.orelse if is_type_checking else [*node.body, *node.orelse]:
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        self.modules.extend((node.lineno, alias.name) for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = ".".join(self.package[: len(self.package) - node.level + 1]) if node.level else ""
        module = ".".join(part for part in (base, node.module or "") if part)
        if node.module is None:
            self.modules.extend((node.lineno, f"{module}.{alias.name}") for alias in node.names)
        else:
            self.modules.append((node.lineno, module))


def _runtime_imports(path: Path) -> list[tuple[int, str]]:
    package = ".".join(path.relative_to(REPO_ROOT).with_suffix("").parts[:-1])
    collector = _RuntimeImports(package)
    collector.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return collector.modules


def _lib_output_files() -> list[Path]:
    folder = REPO_ROOT / "vidbyte" / "lib" / "outputs"
    missing = [name for name in LIB_OUTPUT_MODULES if not (folder / f"{name}.py").is_file()]
    assert missing == [], f"spec 12.3 rows 4-18 modules missing from vidbyte/lib/outputs: {missing}"
    placement = [REPO_ROOT / "vidbyte" / "lib" / kind / "outputs.py" for kind in ("enums", "constants", "dataclasses")]
    return [*sorted(folder.glob("*.py")), *placement]


def test_lib_output_modules_never_import_a_higher_layer_or_raw_http() -> None:
    # NFR-7 / AGENTS.md Style 3 / §12.4: lib is the bottom layer, even inside a function; HTTP goes through HttpTransport only.
    violations = []
    for path in _lib_output_files():
        for line, module in _runtime_imports(path):
            top = module.split(".")
            if top[0] == "vidbyte" and (len(top) == 1 or top[1] != "lib"):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line} imports {module}")
            if top[0] in ("httpx", "requests", "aiohttp") or module in ("http.client", "urllib.request"):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line} imports {module}")

    assert violations == []


def test_agent_side_output_modules_import_only_the_standard_library_and_vidbyte_lib() -> None:
    # NFR-7 / §12.2: base.py imports vidbyte.agents.output, so anything else from vidbyte.agents would be a cycle.
    folder = REPO_ROOT / "vidbyte" / "agents" / "output"
    missing = [name for name in AGENT_OUTPUT_MODULES if not (folder / f"{name}.py").is_file()]
    assert missing == []
    violations = []
    for path in sorted(folder.glob("*.py")):
        for line, module in _runtime_imports(path):
            top = module.split(".")[0]
            allowed = top in sys.stdlib_module_names or top == "__future__" or module in ("vidbyte.lib", "vidbyte.agents.output") or module.startswith(("vidbyte.lib.", "vidbyte.agents.output."))
            if not allowed:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line} imports {module}")

    assert violations == []


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")


def test_docs_provider_reference_has_one_dated_row_with_an_official_link_per_destination() -> None:
    # AC-26 / FR-19 / NFR-8: one row per destination, found by its credential variable, with a link and the retrieval date.
    text = _read("vidbyte/lib/outputs/README.md")
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    undocumented = [name for name in OUTPUT_ENV_VARS if not any(name in row and "https://" in row and ("2026-10-11" in row or "2026-10-14" in row) for row in rows)]
    assert undocumented == []
    assert "Retrieved" in text


def test_docs_describe_outputs_in_the_agent_readme_and_both_folders_in_the_repo_map() -> None:
    # AC-26 / FR-20 / §12.3 rows 23, 33, 36: users find outputs= where they read about agents; agents find both folders in the map.
    assert "outputs=" in _read("vidbyte/agents/README.md")
    _read("vidbyte/agents/output/README.md")
    repo_map = _read("REPO_MAP.md")
    for folder in ("vidbyte/agents/output/", "vidbyte/lib/outputs/"):
        assert re.search(rf"^#+ `{re.escape(folder)}`\s*$", repo_map, flags=re.MULTILINE), folder


@pytest.mark.parametrize("relative", ["vidbyte/lib/outputs/README.md", "vidbyte/agents/output/README.md"])
def test_docs_new_folder_readmes_stay_within_40000_characters(relative) -> None:
    # AC-26 / A009: the edited existing READMEs are already held to the ceiling by tests/test_readme_size_limit.py.
    assert len(_read(relative)) <= 40_000
