"""Context Protocol Header

Description:
    Defines the Vidbyte paradigms namespace client.
Purpose:
    Reserves the public client surface for future paradigm harness factories
    without shipping any concrete paradigm implementations in this scaffolding
    change.
Architecture:
    - ParadigmClient: Namespace marker for future factories such as
      critique-repair or fresh-window decomposition harness constructors.
Relations:
    Instantiated by vidbyte.client.VidbyteSDK and exported through
    vidbyte.paradigms.
"""

from __future__ import annotations


class ParadigmClient:
    """Namespace client for future paradigm harness factories."""


__all__ = ["ParadigmClient"]
