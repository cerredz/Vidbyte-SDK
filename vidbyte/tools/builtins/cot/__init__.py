"""Context Protocol Header

Description:
    Exports the batch-3 deep-family CoT monitoring tools.
Purpose:
    Keeps the context-window, foraging, verification, delegation, and meta
    monitoring builtins importable from one namespace, grouped in their own
    package the way other multi-file builtin categories are.
Architecture:
    - context: context-window awareness tools (4).
    - foraging: information-foraging tools (4).
    - verification: self-verification tools (4).
    - delegation: inter-agent delegation epistemics tools (6).
    - meta: meta-monitoring tools (6).
Relations:
    Re-exported by vidbyte.tools.builtins. Each module reuses CotEventParser
    and _CotEventToolBase from vidbyte.tools.builtins.cot_events, which stays
    outside this package since it also backs the batch-1/2 event tools.
Similar Files:
    - `vidbyte/tools/builtins/fork/__init__.py`
"""

from __future__ import annotations

from vidbyte.tools.builtins.cot.context import (
    AttentionCheckTool,
    ContextLoadTool,
    ForgetDecisionTool,
    RecallTestTool,
)
from vidbyte.tools.builtins.cot.delegation import (
    BlockedOnTool,
    DelegationBriefTool,
    DelegationReceiptTool,
    HandoffCompletenessTool,
    HandoffWhyTool,
    SubagentFailuresTool,
)
from vidbyte.tools.builtins.cot.foraging import (
    EnoughTool,
    SearchPlanTool,
    SearchWhyTool,
    SearchYieldTool,
)
from vidbyte.tools.builtins.cot.meta import (
    CalibrationSelfReportTool,
    DescriptionDriftTool,
    RecordDisputeTool,
    RitualCheckTool,
    SignalHighlightTool,
    TelemetryGapTool,
)
from vidbyte.tools.builtins.cot.verification import (
    IndependentlyDerivedTool,
    ReadBackTool,
    SelfTestTool,
    VerifyTool,
)

__all__ = [
    "AttentionCheckTool",
    "BlockedOnTool",
    "CalibrationSelfReportTool",
    "ContextLoadTool",
    "DelegationBriefTool",
    "DelegationReceiptTool",
    "DescriptionDriftTool",
    "EnoughTool",
    "ForgetDecisionTool",
    "HandoffCompletenessTool",
    "HandoffWhyTool",
    "IndependentlyDerivedTool",
    "ReadBackTool",
    "RecallTestTool",
    "RecordDisputeTool",
    "RitualCheckTool",
    "SearchPlanTool",
    "SearchWhyTool",
    "SearchYieldTool",
    "SelfTestTool",
    "SignalHighlightTool",
    "SubagentFailuresTool",
    "TelemetryGapTool",
    "VerifyTool",
]
