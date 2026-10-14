"""FILE: vidbyte/tools/toolsets/prebuilt.py

PURPOSE: Defines PrebuiltTools, the catalog that turns a choice of PrebuiltToolCategory members into fresh FunctionTool objects for the deterministic prebuilt utility tools.
ROLE IN CODEBASE: Exported by vidbyte/tools/toolsets/__init__.py and handed by developers to Agent(tools=...). Builds on vidbyte/tools/catalog.py (Tools), vidbyte/tools/function_tool.py (FunctionTool), the category classes in vidbyte/tools/builtins/prebuilt/, and PrebuiltToolCategory from vidbyte/lib/enums/prebuilt_tools.py.
ARCHITECTURE NOTE: PrebuiltTools is a Tools subclass whose narrated __init__ calls two static helpers as sibling steps, the shape of CodingAgentTools in coding.py. _CATEGORY_FUNCTIONS maps every category to its class's tool_functions, so the category list lives in the enum and the dispatch lives here, below which nothing names tool classes. Tools are built on every construction and never cached, so two catalogs never share a tool object and importing this module builds nothing.
FUNCTION INVENTORY: PrebuiltTools.__init__ is the narrated main function; select_categories checks the categories and returns the distinct members in catalogue order; get_tools wraps every function of the chosen categories in a new FunctionTool.
COMMON MODIFICATION PATTERNS: A new category adds its enum member, its category module and class, and one entry in _CATEGORY_FUNCTIONS. Single tools are picked with the inherited Tools.subset, so no selection method belongs here.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a default that attaches the whole library; a model chooses tools worse as their number grows. 2. Do not accept plain strings for categories; a category is an enum member. 3. Do not cache built tools or build them at import time.
KNOWN EDGE CASES: A PrebuiltToolCategory member is also a str, so a bare member is checked before a bare string, and a bare string is reported whole instead of being iterated character by character. Building the whole library takes a fraction of a second, so a hot loop should build once and reuse the catalog.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 8.5, D-2, D-11); vidbyte/tools/builtins/prebuilt/README.md; vidbyte/tools/README.md (Prebuilt Tools)
TESTS: tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py and tests/features/prebuilt_tools/test_prebuilt_acceptance.py
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.enums.prebuilt_tools import PrebuiltToolCategory
from vidbyte.lib.errors import ToolRegistryError
from vidbyte.tools.builtins.prebuilt import (
    BitsBytesToolFunctions,
    CodeAnalysisToolFunctions,
    CsvTablesToolFunctions,
    DatesToolFunctions,
    DescriptiveStatisticsToolFunctions,
    EncodingToolFunctions,
    ExactArithmeticToolFunctions,
    FinanceToolFunctions,
    GeometryToolFunctions,
    GraphsToolFunctions,
    HashingToolFunctions,
    IdentifiersToolFunctions,
    JsonDataToolFunctions,
    JsonRecordsToolFunctions,
    ListsToolFunctions,
    MarkdownHtmlToolFunctions,
    NetworkAddressesToolFunctions,
    NumberFormattingToolFunctions,
    NumberTheoryToolFunctions,
    ProbabilityToolFunctions,
    RegexToolFunctions,
    SchedulingToolFunctions,
    SeededRandomToolFunctions,
    StructuredFormatsToolFunctions,
    TextComparisonToolFunctions,
    TextCountingToolFunctions,
    TextExtractionToolFunctions,
    TextTransformToolFunctions,
    TimestampsDurationsToolFunctions,
    UnicodeToolFunctions,
    UnitConversionToolFunctions,
)
from vidbyte.tools.builtins.prebuilt._support import PrebuiltToolFunction
from vidbyte.tools.catalog import Tools
from vidbyte.tools.function_tool import FunctionTool

_CATEGORY_FUNCTIONS: Mapping[PrebuiltToolCategory, Callable[[], tuple[PrebuiltToolFunction, ...]]] = MappingProxyType(
    {
        PrebuiltToolCategory.EXACT_ARITHMETIC: ExactArithmeticToolFunctions.tool_functions,
        PrebuiltToolCategory.NUMBER_THEORY: NumberTheoryToolFunctions.tool_functions,
        PrebuiltToolCategory.NUMBER_FORMATTING: NumberFormattingToolFunctions.tool_functions,
        PrebuiltToolCategory.DESCRIPTIVE_STATISTICS: DescriptiveStatisticsToolFunctions.tool_functions,
        PrebuiltToolCategory.PROBABILITY: ProbabilityToolFunctions.tool_functions,
        PrebuiltToolCategory.SEEDED_RANDOM: SeededRandomToolFunctions.tool_functions,
        PrebuiltToolCategory.FINANCE: FinanceToolFunctions.tool_functions,
        PrebuiltToolCategory.UNIT_CONVERSION: UnitConversionToolFunctions.tool_functions,
        PrebuiltToolCategory.DATES: DatesToolFunctions.tool_functions,
        PrebuiltToolCategory.SCHEDULING: SchedulingToolFunctions.tool_functions,
        PrebuiltToolCategory.TIMESTAMPS_DURATIONS: TimestampsDurationsToolFunctions.tool_functions,
        PrebuiltToolCategory.TEXT_COUNTING: TextCountingToolFunctions.tool_functions,
        PrebuiltToolCategory.TEXT_TRANSFORM: TextTransformToolFunctions.tool_functions,
        PrebuiltToolCategory.UNICODE: UnicodeToolFunctions.tool_functions,
        PrebuiltToolCategory.REGEX: RegexToolFunctions.tool_functions,
        PrebuiltToolCategory.TEXT_COMPARISON: TextComparisonToolFunctions.tool_functions,
        PrebuiltToolCategory.JSON_DATA: JsonDataToolFunctions.tool_functions,
        PrebuiltToolCategory.JSON_RECORDS: JsonRecordsToolFunctions.tool_functions,
        PrebuiltToolCategory.CSV_TABLES: CsvTablesToolFunctions.tool_functions,
        PrebuiltToolCategory.STRUCTURED_FORMATS: StructuredFormatsToolFunctions.tool_functions,
        PrebuiltToolCategory.ENCODING: EncodingToolFunctions.tool_functions,
        PrebuiltToolCategory.HASHING: HashingToolFunctions.tool_functions,
        PrebuiltToolCategory.IDENTIFIERS: IdentifiersToolFunctions.tool_functions,
        PrebuiltToolCategory.LISTS: ListsToolFunctions.tool_functions,
        PrebuiltToolCategory.GRAPHS: GraphsToolFunctions.tool_functions,
        PrebuiltToolCategory.GEOMETRY: GeometryToolFunctions.tool_functions,
        PrebuiltToolCategory.BITS_BYTES: BitsBytesToolFunctions.tool_functions,
        PrebuiltToolCategory.MARKDOWN_HTML: MarkdownHtmlToolFunctions.tool_functions,
        PrebuiltToolCategory.TEXT_EXTRACTION: TextExtractionToolFunctions.tool_functions,
        PrebuiltToolCategory.CODE_ANALYSIS: CodeAnalysisToolFunctions.tool_functions,
        PrebuiltToolCategory.NETWORK_ADDRESSES: NetworkAddressesToolFunctions.tool_functions,
    }
)


class PrebuiltTools(Tools):
    """Catalog of the deterministic prebuilt utility tools of the chosen categories, in catalogue order."""

    def __init__(self, categories: Iterable[PrebuiltToolCategory] | PrebuiltToolCategory) -> None:
        # Check every category before building anything, and keep each
        # one once, in the order the library lists them.
        chosen = self.select_categories(categories)

        # Wrap every function of those categories in a fresh tool and
        # hand them to the catalog, which refuses duplicate names.
        super().__init__(self.get_tools(chosen))

    @staticmethod
    def select_categories(categories: Iterable[PrebuiltToolCategory] | PrebuiltToolCategory) -> tuple[PrebuiltToolCategory, ...]:
        """Return the distinct categories in declaration order, raising ToolRegistryError naming every value that is not a member."""
        # A member is also a str, so a bare member or a bare string is
        # one value and is never read character by character.
        is_single = isinstance(categories, str) or not isinstance(categories, Iterable)
        listed: list[object] = [categories] if is_single else list(categories)
        unknown = [item for item in listed if not isinstance(item, PrebuiltToolCategory)]
        if unknown:
            bad_values = ", ".join(repr(item) for item in unknown)
            raise ToolRegistryError(f"Unknown prebuilt tool categories: {bad_values}. Pass PrebuiltToolCategory members; valid values are: {', '.join(PrebuiltToolCategory.values())}.")
        return tuple(member for member in PrebuiltToolCategory if member in listed)

    @staticmethod
    def get_tools(categories: tuple[PrebuiltToolCategory, ...]) -> tuple[FunctionTool, ...]:
        """Return a new FunctionTool for every function of the given categories, in catalogue order."""
        return tuple(FunctionTool(function) for category in categories for function in _CATEGORY_FUNCTIONS[category]())


__all__ = ["PrebuiltTools"]
