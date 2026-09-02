"""Context Protocol Header

Description:
    Module entry point for running the unified Vidbyte SDK CLI.
Purpose:
    Provides `python -m vidbyte.cli` parity with the installed `vidbyte-sdk` command.
Architecture:
    - Imports vidbyte.cli.main and exits with its returned process status.
Relations:
    Thin bridge for the console script defined in pyproject.toml.
"""

from __future__ import annotations

from vidbyte.cli import main


raise SystemExit(main())
