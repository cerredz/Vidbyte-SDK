"""Context Protocol Header

Description:
    Prebuilt agent-facing tools for durable sessions.
Purpose:
    Lets a developer hand an agent ready-made tools to checkpoint, fork, rewind,
    and resume its own or another agent's thread, reusing the Session + SessionStore
    + SessionScope primitives from vidbyte.sessions.
Architecture:
    - SessionTool: central combined tool (create_checkpoint / fork_current / list_my_runs / read_run).
    - CheckpointTool / ForkTool / BatchForkTool / RewindTool: granular per-verb tools.
    - ResumeReplaceTool / ResumeAppendTool / ResumeOutputTool: three cross-thread resume modes.
Relations:
    All subclass _SessionBuiltinTool and bind to a Session via bind_session(); the
    Session calls _bind_session_tools() at construction to wire them up.
"""

from __future__ import annotations

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.batch_fork import BatchForkTool
from vidbyte.tools.builtins.sessions.checkpoint import CheckpointTool
from vidbyte.tools.builtins.sessions.fork import ForkTool
from vidbyte.tools.builtins.sessions.resume_append import ResumeAppendTool
from vidbyte.tools.builtins.sessions.resume_output import ResumeOutputTool
from vidbyte.tools.builtins.sessions.resume_replace import ResumeReplaceTool
from vidbyte.tools.builtins.sessions.rewind import RewindTool
from vidbyte.tools.builtins.sessions.session import SessionTool

__all__ = [
    "BatchForkTool",
    "CheckpointTool",
    "ForkTool",
    "ResumeAppendTool",
    "ResumeOutputTool",
    "ResumeReplaceTool",
    "RewindTool",
    "SessionTool",
]
