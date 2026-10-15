"""FILE: vidbyte/lib/outputs/hubspot.py

PURPOSE: Defines HubSpotTaskOutput, which creates one HubSpot CRM task per finished agent reply.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Builds one CRM v3 tasks OutputRequest and hands it to OutputHttp; auth is a Bearer legacy private-app token.
COMMON MODIFICATION PATTERNS: Keep the endpoint in HUBSPOT_TASKS_URL; the date-versioned tasks endpoint requires associations, which this connector does not send.
KNOWN EDGE CASES: The task has no owner and no association; HubSpot's answer has no web link, so the receipt has none.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developers.hubspot.com/docs/api-reference/crm-tasks-v3/guide
TESTS: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from vidbyte.lib.constants.outputs import (
    HUBSPOT_TASK_BODY_MAX_CHARS,
    HUBSPOT_TASKS_URL,
    OUTPUT_TITLE_MAX_CHARS,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import (
    DeliveryReceipt,
    OutputContent,
    OutputRequest,
)
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputHttp
from vidbyte.lib.outputs.text import OutputText


class HubSpotTaskOutput(BaseOutput):
    """Creates one HubSpot CRM task per reply."""

    destination = OutputDestination.HUBSPOT_TASK

    def __init__(self, *, access_token: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        self._access_token = OutputArguments.credential(self.destination, access_token, parameter="access_token")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Create one task with the reply title as its subject, the body as its notes, and the send time as its due time."""
        # @intent hubspot-task-is-stamped-with-the-send-time
        # HubSpot requires hs_timestamp, so the task is due at the send
        # time, in UTC with milliseconds; no owner or association is
        # set, so the task waits in the portal's task list.
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        properties = {"hs_task_subject": OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS), "hs_task_body": OutputText.truncate(content.body, HUBSPOT_TASK_BODY_MAX_CHARS), "hs_timestamp": stamp}
        request = OutputRequest(HUBSPOT_TASKS_URL, {"authorization": f"Bearer {self._access_token}"}, {"properties": properties})
        return await OutputHttp.post(self.destination, request)


__all__ = ["HubSpotTaskOutput"]
