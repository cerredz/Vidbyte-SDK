"""FILE: vidbyte/lib/util/exception_origin.py

PURPOSE: Names where an exception was raised, as "file.py:function:line" of its innermost traceback frame, so a log can point at the root cause without writing the exception's text.
ROLE IN CODEBASE: The one origin helper the CodexHost connection, its server-request router, its turn events and the Codex tools share for their redacted WARNING logs (docs/spec/codex-host-hardening/spec.md D-13, INV-7 to INV-9, X8); re-exported from vidbyte/lib/util/__init__.py.
ARCHITECTURE NOTE: A static-method-only class, like MathHelper in vidbyte/lib/util/math.py. It reads only the traceback's frames and code objects through the standard library, never the exception's message or arguments and never a source line, so the result is safe for any log however private the failure was.
FUNCTION INVENTORY: ExceptionOrigin.describe(exc) -> str: the innermost frame of exc.__traceback__ as basename:function:line, or "" when exc carries no traceback.
COMMON MODIFICATION PATTERNS: Keep the output one token with no spaces, because log lines put it after "origin=". A caller that needs another frame adds its own static method here rather than walking a traceback inline.
WHAT NOT TO DO: Do not include the exception's message, its arguments, a full path or a source line; any of them can carry private values such as prompts, file contents or SDK stderr.
KNOWN EDGE CASES: An exception that was created but never raised has no traceback, so it describes as "". The innermost frame survives a re-raise, including one through concurrent.futures.Future.result(), so the origin still names the code that first raised.
RELATED DOCS: docs/spec/codex-host-hardening/spec.md (D-13 and section 8.5)
TESTS: tests/features/codex_host/test_codex_host_hardening_contract.py (CodexExceptionOriginTests) and the origin checks in tests/features/codex_host/test_codex_host_observability.py
"""

from __future__ import annotations

import os
import traceback


class ExceptionOrigin:
    """Static-method home for naming the code location an exception came from, without its text."""

    @staticmethod
    def describe(exc: BaseException) -> str:
        """The innermost frame of exc's traceback as "file.py:function:line", or "" when exc was never raised."""
        # walk_tb yields each frame with its line without reading any
        # source, and the last one is where the exception was raised.
        steps = list(traceback.walk_tb(exc.__traceback__))
        if not steps:
            return ""
        frame, line = steps[-1]
        return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_code.co_name}:{line}"


__all__ = ["ExceptionOrigin"]
