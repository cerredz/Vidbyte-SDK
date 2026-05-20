# -*- coding: utf-8 -*-
#
# Context Protocol Header:
# - DESCRIPTION: Entry point for the harnesses module in the Vidbyte SDK.
# - PURPOSE: Exposes namespace clients and base contracts for constructing evaluation and execution harnesses.
# - ARCHITECTURE: Standard Python package aggregating general harnesses (BaseHarness, HarnessClient).
# - KEY FUNCTIONS: N/A (export package only).
# - RELATION TO CODEBASE: Provides the high-level API access to evaluation, execution, and timing harnesses.
# - SIMILAR FILES: vidbyte/tools/__init__.py, vidbyte/providers/__init__.py

from __future__ import annotations

from vidbyte.harnesses.base import BaseHarness
from vidbyte.harnesses.client import HarnessClient

__all__ = [
    "BaseHarness",
    "HarnessClient",
]

