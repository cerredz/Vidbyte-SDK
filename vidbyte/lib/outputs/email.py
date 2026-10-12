"""FILE: vidbyte/lib/outputs/email.py

PURPOSE: Defines EmailOutput, which mails each finished agent reply over SMTP (Gmail, Microsoft 365, SendGrid, SES, and any SMTP server).
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Validates the SMTP session into SmtpSettings once, then runs the blocking OutputSmtp.send on the module's own _SMTP_EXECUTOR, never the loop's default executor.
COMMON MODIFICATION PATTERNS: Provider-specific setup (host, port, username) belongs in the README, not in a new class.
KNOWN EDGE CASES: A username with no "@" (SendGrid's apikey, Resend's resend) needs an explicit sender to be a valid From address. A session past the delivery deadline keeps running in the background and may still deliver.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.python.org/3/library/smtplib.html
TESTS: tests/features/agent_output_connectors/test_output_connectors_email.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from vidbyte.lib.constants.outputs import OUTPUT_TITLE_MAX_CHARS, SMTP_STARTTLS_PORT
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent, SmtpSettings
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.delivery import OutputSmtp
from vidbyte.lib.outputs.text import OutputText

# SMTP sessions run here, not on the loop's default executor: on Python
# 3.11 asyncio.run waits for that executor with no time limit, so a
# stalled server would hold run() past the delivery deadline.
_SMTP_EXECUTOR = ThreadPoolExecutor()

class EmailOutput(BaseOutput):
    """Mails each reply as a plain-text email over verified TLS."""

    destination = OutputDestination.EMAIL

    def __init__(
        self,
        *,
        to: str | Sequence[str],
        host: str,
        username: str,
        password: str | None = None,
        sender: str | None = None,
        port: int = SMTP_STARTTLS_PORT,
        render: Callable[[AgentMessage], OutputContent] | None = None,
    ) -> None:
        super().__init__(render=render)
        recipients = OutputArguments.texts((to,) if isinstance(to, str) else to, parameter="to")
        login = OutputArguments.text(username, parameter="username")
        self._settings = SmtpSettings(
            host=OutputArguments.text(host, parameter="host"),
            port=port,
            username=login,
            password=OutputArguments.credential(self.destination, password, parameter="password"),
            sender=OutputArguments.address(sender if sender is not None else login, parameter="sender"),
            recipients=tuple(OutputArguments.address(item, parameter="to") for item in recipients),
        )

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Mail the title as the subject and the body as plain text."""
        # @intent email-subject-is-one-line
        # The subject is one line, so a model-written line break cannot
        # add a Bcc header. SMTP blocks, so it runs on its own worker
        # thread, which run() does not wait for past the deadline.
        message = EmailMessage()
        message["From"] = self._settings.sender
        message["To"] = ", ".join(self._settings.recipients)
        message["Subject"] = OutputText.single_line(content.title, OUTPUT_TITLE_MAX_CHARS)
        message.set_content(content.body)
        return await asyncio.get_running_loop().run_in_executor(_SMTP_EXECUTOR, OutputSmtp.send, self._settings, message)


__all__ = ["EmailOutput"]
