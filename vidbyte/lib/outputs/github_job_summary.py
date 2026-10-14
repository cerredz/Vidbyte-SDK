"""FILE: vidbyte/lib/outputs/github_job_summary.py

PURPOSE: Defines GitHubJobSummaryOutput, which appends each finished agent reply to the GitHub Actions job summary of the step it runs in.
ROLE IN CODEBASE: A connector users pass in an agent's outputs; the dispatcher in vidbyte/agents/output/ calls its send.
ARCHITECTURE NOTE: Makes no HTTP request: it appends to the file named by GITHUB_STEP_SUMMARY through LocalFileSystemBackend, on the module's single worker thread.
COMMON MODIFICATION PATTERNS: Keep every write in _append, through LocalFileSystemBackend, and off the event loop.
KNOWN EDGE CASES: A missing directory is not created and any OSError is FAILED file_error; GitHub caps each step's summary at 1 MiB; an append that is cut by the delivery deadline may still land.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
TESTS: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vidbyte.lib.constants.outputs import (
    GITHUB_JOB_SUMMARY_MAX_CHARS,
    GITHUB_JOB_SUMMARY_SEPARATOR,
    GITHUB_JOB_SUMMARY_WRITERS,
    OUTPUT_ERROR_FILE,
    OUTPUT_FILE_ENCODING,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import DeliveryStatus, OutputDestination
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.text import OutputText
from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend

# Appends run here, one at a time, and never on the loop's default
# executor, which asyncio.run waits for with no time limit.
_SUMMARY_EXECUTOR = ThreadPoolExecutor(max_workers=GITHUB_JOB_SUMMARY_WRITERS)


class GitHubJobSummaryOutput(BaseOutput):
    """Appends each reply to the job summary of the GitHub Actions step it runs in."""

    destination = OutputDestination.GITHUB_JOB_SUMMARY

    def __init__(self, *, path: str | None = None, render: Callable[[AgentMessage], OutputContent] | None = None) -> None:
        super().__init__(render=render)
        # The path is resolved like a credential: the argument, then
        # GITHUB_STEP_SUMMARY, which GitHub Actions sets for each step.
        self._path = OutputArguments.credential(self.destination, path, parameter="path")

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Append the chat text and a blank line to the summary file."""
        # @intent job-summary-appends-on-one-worker
        # The file is appended to, never overwritten, on the single
        # worker thread: never on the event loop, where a slow disk
        # would stall every other output, and never two at once, which
        # could interleave two replies. The block, blank line included,
        # stays within GITHUB_JOB_SUMMARY_MAX_CHARS.
        limit = GITHUB_JOB_SUMMARY_MAX_CHARS - len(GITHUB_JOB_SUMMARY_SEPARATOR)
        text = OutputText.truncate(OutputText.chat_text(content), limit) + GITHUB_JOB_SUMMARY_SEPARATOR
        return await asyncio.get_running_loop().run_in_executor(_SUMMARY_EXECUTOR, GitHubJobSummaryOutput._append, self._path, text)

    @staticmethod
    def _append(path: str, text: str) -> DeliveryReceipt:
        # Blocking: runs on _SUMMARY_EXECUTOR. A missing directory is
        # not created, and any file error fails only this output.
        try:
            LocalFileSystemBackend().append_text(Path(path), text, encoding=OUTPUT_FILE_ENCODING, create_parents=False)
        except OSError:
            return DeliveryReceipt(OutputDestination.GITHUB_JOB_SUMMARY, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_FILE)
        return DeliveryReceipt(OutputDestination.GITHUB_JOB_SUMMARY, DeliveryStatus.SENT)


__all__ = ["GitHubJobSummaryOutput"]
