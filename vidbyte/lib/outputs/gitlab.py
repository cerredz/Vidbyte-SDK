"""FILE: vidbyte/lib/outputs/gitlab.py

PURPOSE: Defines GitLabIssueOutput, which opens one GitLab issue per finished agent reply, or adds it as a note on one merge request.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one REST v4 OutputRequest and hands it to OutputHttp; auth is the PRIVATE-TOKEN header, and the host may be gitlab.com or a self-managed server.
COMMON MODIFICATION PATTERNS: Keep GitLab's paths in GITLAB_* constants in vidbyte/lib/constants/outputs.py and the request shape here.
KNOWN EDGE CASES: A merge request note answer has no web_url, so its receipt has no link; a project path is URL-encoded, so acme/shop becomes acme%2Fshop.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.gitlab.com/api/issues/; https://docs.gitlab.com/api/notes/
TESTS: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from urllib.parse import quote, urlsplit

from vidbyte.lib.constants.outputs import (
    GITLAB_API_PATH,
    GITLAB_AUTH_HEADER,
    GITLAB_DEFAULT_HOST,
    GITLAB_DESCRIPTION_MAX_CHARS,
    GITLAB_HOST_PATTERN,
    GITLAB_NOTE_MAX_CHARS,
    GITLAB_PROJECT_PATH_PATTERN,
    OUTPUT_HTTPS_PREFIX,
    OUTPUT_TITLE_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class GitLabIssueOutput(BaseOutput):
    """Opens one GitLab issue per reply in a fixed project, or adds a note to one fixed merge request."""

    destination = OutputDestination.GITLAB_ISSUE

    def __init__(
        self,
        *,
        project: str | int,
        host: str = GITLAB_DEFAULT_HOST,
        labels: Sequence[str] = (),
        merge_request: int | None = None,
        token: str | None = None,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        # @intent gitlab-host-is-a-bare-host
        # The host is a bare name with an optional port, so the token
        # can never go to a path, a userinfo trick, or another scheme.
        # Reading the port parses it, so one above 65,535 fails here.
        self._host = OutputArguments.matching(host, GITLAB_HOST_PATTERN, parameter="host")
        try:
            _port = urlsplit(OUTPUT_HTTPS_PREFIX + self._host).port
        except ValueError:
            raise ConfigurationError(f"host must have a valid port, got {host!r}.", details={"parameter": "host"}) from None
        # A project is its numeric id or its namespace/name path, which
        # GitLab takes URL-encoded.
        self._project = quote(OutputArguments.reference(project, GITLAB_PROJECT_PATH_PATTERN, parameter="project"), safe="")
        self._labels = OutputArguments.texts(labels, parameter="labels")
        self._merge_request = None if merge_request is None else OutputArguments.number(merge_request, parameter="merge_request")
        # A note lands on a merge request, which keeps its own labels.
        OutputArguments.exclusive({"labels": self._labels, "merge_request": self._merge_request})
        self._token = OutputArguments.credential(self.destination, token, parameter="token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Open one issue with a one-line title, the body, and the labels, or add the reply as a note on the configured merge request."""
        # @intent gitlab-target-is-fixed
        # The host, project, and merge request come only from the
        # constructor, so model output cannot move the reply or the
        # token elsewhere.
        headers = {GITLAB_AUTH_HEADER: self._token}
        project_url = f"https://{self._host}{GITLAB_API_PATH}/projects/{self._project}"
        # A note has no title field, so it carries the chat text;
        # GitLab's answer has no web link, so the receipt has none.
        if self._merge_request is not None:
            note = {"body": OutputText.truncate(OutputText.chat_text(content), GITLAB_NOTE_MAX_CHARS)}
            return await OutputHttp.post(self.destination, OutputRequest(f"{project_url}/merge_requests/{self._merge_request}/notes", headers, note))
        # A new issue gets its labels, comma-separated, only when some
        # were given; the receipt links its web_url.
        issue: dict[str, object] = {"title": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "description": OutputText.truncate(content.body, GITLAB_DESCRIPTION_MAX_CHARS)}
        if self._labels:
            issue["labels"] = ",".join(self._labels)
        return await OutputHttp.post(self.destination, OutputRequest(f"{project_url}/issues", headers, issue, link_path=("web_url",)))


__all__ = ["GitLabIssueOutput"]
