# -*- coding: utf-8 -*-
#
# Context Protocol Header:
# - DESCRIPTION: Package entry point for time-based harnesses under vidbyte.harnesses.time.
# - PURPOSE: To provide clean, explicit exports for the time harness abstractions, built-in date/compaction contracts, and configurations.
# - ARCHITECTURE: Standard Python package initialization exposing types, configurations, exceptions, and implementations.
# - KEY FUNCTIONS: N/A (export package only).
# - RELATION TO CODEBASE: Serves as the public interface for the harnesses/time submodule. It aggregates types from types.py and the harness class from minimum_time.py.
# - SIMILAR FILES: vidbyte/harnesses/__init__.py, vidbyte/tools/__init__.py

from __future__ import annotations

from vidbyte.harnesses.time.minimum_time import MinimumTimeHarness
from vidbyte.harnesses.time.types import (
    BaseCompactionTool,
    BaseDateTool,
    ConfigurationError,
    HarnessExecutionError,
    MinimumTimeHarnessConfig,
    SystemDateTool,
    TimeHarnessIterationResult,
    TimeHarnessState,
    TimeHarnessStatus,
    ValidationError,
)

__all__ = [
    "MinimumTimeHarness",
    "MinimumTimeHarnessConfig",
    "BaseDateTool",
    "SystemDateTool",
    "BaseCompactionTool",
    "TimeHarnessIterationResult",
    "TimeHarnessState",
    "TimeHarnessStatus",
    "ConfigurationError",
    "ValidationError",
    "HarnessExecutionError",
]
