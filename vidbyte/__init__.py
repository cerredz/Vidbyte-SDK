# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Root package initializer for the Vidbyte SDK.
# Purpose: Defines top-level exports and initial package-wide setup.
# Architecture & Functions:
#   - Exports VidbyteSDK root client.
# Codebase Relation:
#   - Central entry point when developers import the `vidbyte` package.
# Similar Files:
#   - None (this is the unique root package initializer).
# ==============================================================================

from __future__ import annotations

from vidbyte.client import VidbyteSDK

__all__ = [
    "VidbyteSDK",
]

