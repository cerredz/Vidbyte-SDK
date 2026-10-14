"""FILE: vidbyte/tools/builtins/prebuilt/__init__.py

PURPOSE: Re-exports the 31 <Category>ToolFunctions classes of the prebuilt tool library, one per PrebuiltToolCategory member.
ROLE IN CODEBASE: Imported by vidbyte/tools/toolsets/prebuilt.py, whose PrebuiltTools wraps each class's tool_functions() in FunctionTool objects, and by the feature test pack. This package is deliberately not re-exported from vidbyte.tools.builtins, so that package's export list stays unchanged.
ARCHITECTURE NOTE: The category classes are an internal surface: application code runs a tool through its FunctionTool in a PrebuiltTools catalog, which validates arguments first, while a direct call skips that validation. Importing this package defines classes only and builds no tool.
FUNCTION INVENTORY: No functions; __all__ lists the 31 category classes.
COMMON MODIFICATION PATTERNS: A new category module adds its class import here and its name to __all__, and one entry in the PrebuiltTools dispatch table.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.tools.toolsets; the toolset imports this package, never the reverse. 2. Do not build FunctionTool objects here. 3. Do not export PrebuiltToolSupport; it stays private to the package.
KNOWN EDGE CASES: None; the module only re-exports classes.
RELATED DOCS: vidbyte/tools/builtins/prebuilt/README.md; docs/spec/prebuilt-agent-tools/spec.md (FR-5, D-12)
TESTS: tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py (test_category_class_lists_its_functions_in_row_order)
"""

from __future__ import annotations

from vidbyte.tools.builtins.prebuilt.bits_bytes import BitsBytesToolFunctions
from vidbyte.tools.builtins.prebuilt.code_analysis import CodeAnalysisToolFunctions
from vidbyte.tools.builtins.prebuilt.csv_tables import CsvTablesToolFunctions
from vidbyte.tools.builtins.prebuilt.dates import DatesToolFunctions
from vidbyte.tools.builtins.prebuilt.descriptive_statistics import (
    DescriptiveStatisticsToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.encoding import EncodingToolFunctions
from vidbyte.tools.builtins.prebuilt.exact_arithmetic import (
    ExactArithmeticToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.finance import FinanceToolFunctions
from vidbyte.tools.builtins.prebuilt.geometry import GeometryToolFunctions
from vidbyte.tools.builtins.prebuilt.graphs import GraphsToolFunctions
from vidbyte.tools.builtins.prebuilt.hashing import HashingToolFunctions
from vidbyte.tools.builtins.prebuilt.identifiers import IdentifiersToolFunctions
from vidbyte.tools.builtins.prebuilt.json_data import JsonDataToolFunctions
from vidbyte.tools.builtins.prebuilt.json_records import JsonRecordsToolFunctions
from vidbyte.tools.builtins.prebuilt.lists import ListsToolFunctions
from vidbyte.tools.builtins.prebuilt.markdown_html import MarkdownHtmlToolFunctions
from vidbyte.tools.builtins.prebuilt.network_addresses import (
    NetworkAddressesToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.number_formatting import (
    NumberFormattingToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.number_theory import NumberTheoryToolFunctions
from vidbyte.tools.builtins.prebuilt.probability import ProbabilityToolFunctions
from vidbyte.tools.builtins.prebuilt.regex import RegexToolFunctions
from vidbyte.tools.builtins.prebuilt.scheduling import SchedulingToolFunctions
from vidbyte.tools.builtins.prebuilt.seeded_random import SeededRandomToolFunctions
from vidbyte.tools.builtins.prebuilt.structured_formats import (
    StructuredFormatsToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.text_comparison import TextComparisonToolFunctions
from vidbyte.tools.builtins.prebuilt.text_counting import TextCountingToolFunctions
from vidbyte.tools.builtins.prebuilt.text_extraction import TextExtractionToolFunctions
from vidbyte.tools.builtins.prebuilt.text_transform import TextTransformToolFunctions
from vidbyte.tools.builtins.prebuilt.timestamps_durations import (
    TimestampsDurationsToolFunctions,
)
from vidbyte.tools.builtins.prebuilt.unicode import UnicodeToolFunctions
from vidbyte.tools.builtins.prebuilt.unit_conversion import UnitConversionToolFunctions

__all__ = [
    "BitsBytesToolFunctions",
    "CodeAnalysisToolFunctions",
    "CsvTablesToolFunctions",
    "DatesToolFunctions",
    "DescriptiveStatisticsToolFunctions",
    "EncodingToolFunctions",
    "ExactArithmeticToolFunctions",
    "FinanceToolFunctions",
    "GeometryToolFunctions",
    "GraphsToolFunctions",
    "HashingToolFunctions",
    "IdentifiersToolFunctions",
    "JsonDataToolFunctions",
    "JsonRecordsToolFunctions",
    "ListsToolFunctions",
    "MarkdownHtmlToolFunctions",
    "NetworkAddressesToolFunctions",
    "NumberFormattingToolFunctions",
    "NumberTheoryToolFunctions",
    "ProbabilityToolFunctions",
    "RegexToolFunctions",
    "SchedulingToolFunctions",
    "SeededRandomToolFunctions",
    "StructuredFormatsToolFunctions",
    "TextComparisonToolFunctions",
    "TextCountingToolFunctions",
    "TextExtractionToolFunctions",
    "TextTransformToolFunctions",
    "TimestampsDurationsToolFunctions",
    "UnicodeToolFunctions",
    "UnitConversionToolFunctions",
]
