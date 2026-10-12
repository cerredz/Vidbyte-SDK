from __future__ import annotations

from enum import Enum


class BudgetPreset(str, Enum):
    """Named budget presets for strategy context construction."""

    TIGHT = "tight"
    BALANCED = "balanced"
    EXPLORATORY = "exploratory"
    UNBOUNDED = "unbounded"


class PermissionPreset(str, Enum):
    """Named permission presets for strategy context construction."""

    SANDBOXED = "sandboxed"
    READ_ONLY = "read_only"
    TOOLS_ONLY = "tools_only"
    TRUSTED = "trusted"


class OperatingSystemFamily(str, Enum):
    """The operating system family an environment runs, which decides its paths, shells, and package managers."""

    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"


class GitHeadState(str, Enum):
    """Where a folder stands in git: outside a repository, on a branch, detached at a commit, or with an unreadable HEAD."""

    NOT_A_REPOSITORY = "not_a_repository"
    BRANCH = "branch"
    DETACHED = "detached"
    UNREADABLE = "unreadable"


class ShellKind(str, Enum):
    """Which shell runs commands, where that changes how a command must be written."""

    BASH = "bash"
    GIT_BASH = "git_bash"
