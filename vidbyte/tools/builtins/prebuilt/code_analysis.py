"""FILE: vidbyte/tools/builtins/prebuilt/code_analysis.py

PURPOSE: Defines CodeAnalysisToolFunctions, the ten prebuilt tools that read source code without running it: a Python syntax check, listings of Python functions, classes, and imports, a line count for common languages, one Python function's signature, Python name usages, a safe Python-literal-to-JSON conversion, and POSIX shell splitting and quoting.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the CODE_ANALYSIS category is chosen. Builds on PrebuiltToolSupport in _support.py for the argument error, the line rule, the nesting level, and the item cap.
ARCHITECTURE NOTE: Python source is only ever handed to ast.parse, and python_literal_to_json alone uses ast.literal_eval, so no analyzed code is compiled into a code object, run, or imported (INV-19, T-5). Definitions are walked with an explicit stack in source order, so qualified names need no recursion, and the two listing tools measure their output while building it (INV-20).
FUNCTION INVENTORY: verify_python_syntax, list_python_functions, list_python_classes, list_python_imports, count_lines_of_code, get_python_function_signature, find_python_name_usages, python_literal_to_json, shell_split_command, and shell_quote_arguments are the tools; _parse_source parses source and maps every parser failure to an error naming source; _definitions walks function and class definitions with their qualified names; _function_entry and _class_entry describe one definition; _line_has_code classifies one line for the line counter; _parameter_entries describes the parameters of a signature; _name_usages and _usage_position find and place name usages; _literal_problem and _sorted_set_items prepare a literal value for JSON; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new code tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.30, and its entry in tool_functions. A new language for count_lines_of_code adds a CodeLanguage member and its PREBUILT_COMMENT_SYNTAX entry, with no change here.
WHAT NOT TO DO IN THIS FILE: 1. Do not hand analyzed code to eval, exec, compile, or an import; ast.parse and ast.literal_eval are the only entry points. 2. Do not build an error message from str(exc); read the SyntaxError attributes msg, lineno, and offset. 3. Do not walk a syntax tree or a literal value with Python recursion; use ast.walk or an explicit stack, because deeply nested input would overflow the interpreter stack.
KNOWN EDGE CASES: ast.parse follows the running Python's grammar, so newer syntax fails on an older version (EC-25). For a null character the parser raises ValueError on 3.11 and SyntaxError later, so the character is refused before parsing; extreme nesting raises MemoryError or RecursionError, which map to a nesting error, and ast.unparse can hit the recursion limit on a long expression chain, which maps to the same error. ast reports columns in UTF-8 bytes, which find_python_name_usages converts to characters. Global and nonlocal declarations, except-clause names, and match-pattern captures are not reported as name usages.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.30, section 9.2 items 6, 12, and 13, INV-19, INV-20); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_code_network.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import ast
import json
import math
import re
import shlex
import sys
from bisect import bisect_right
from collections.abc import Iterator, Mapping
from functools import partial
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_COMMENT_SYNTAX,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_JSON_NESTING,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_REPORTED_NAMES,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_SOURCE_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    CodeLanguage,
    PythonNameUsageKind,
    PythonParameterKind,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_COMPACT_SEPARATORS = (",", ":")
_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_REPORTED_NAME_CHARS = 60
_ENCODED_LINE_BREAK = re.compile(rb"\r\n|\n|\r")
_IDENTIFIER_BEFORE = rb"(?<![0-9A-Za-z_\x80-\xff])"
_IDENTIFIER_AFTER = rb"(?![0-9A-Za-z_\x80-\xff])"
_NAME_CONTEXT_KINDS: MappingProxyType[type[ast.expr_context], PythonNameUsageKind] = MappingProxyType(
    {ast.Load: PythonNameUsageKind.LOAD, ast.Store: PythonNameUsageKind.STORE, ast.Del: PythonNameUsageKind.DELETE}
)
_UNSUPPORTED_LITERAL_PROBLEMS: MappingProxyType[type, str] = MappingProxyType(
    {bytes: "the literal holds bytes, which JSON cannot hold", complex: "the literal holds a complex number, which JSON cannot hold"}
)

_NULL_SOURCE_PROBLEM = "the source contains a null character"
_DEEP_SOURCE_PROBLEM = "the source is nested too deeply for the Python parser"
_ENCODING_SOURCE_PROBLEM = "the source holds characters that cannot be encoded as UTF-8"
_PARSABLE_SOURCE_EXPECTED = "Python source that the running Python version can parse"
_LONG_UNPARSE_PROBLEM = "an expression in the source is nested too deeply to write back as text"
_SHALLOW_SOURCE_EXPECTED = "Python source with less deeply nested expressions"
_LONG_LISTING_PROBLEM = f"the listing would pass {PREBUILT_MAX_TEXT_CHARS} characters of JSON"
_SHORT_LISTING_EXPECTED = f"source whose listing fits in {PREBUILT_MAX_TEXT_CHARS} characters of JSON"
_LITERAL_EXPECTED = f"one Python literal of dicts, lists, tuples, sets, strings, finite numbers, booleans, and None, nested at most {PREBUILT_MAX_JSON_NESTING} levels"

_PYTHON_SOURCE_DESCRIPTION = "The Python source code to analyze, given as plain text. It is only parsed with the standard ast module and is never run or imported. Parsing follows the grammar of the running Python version, and a null character or a syntax error fails with an error naming source. The text may hold at most 200,000 characters."


class CodeAnalysisToolFunctions:
    """The code_analysis category: reading Python and shell code without running it."""

    @staticmethod
    def verify_python_syntax(
        source: Annotated[str, Field(description="The Python source code to check, given as plain text. It is only parsed with the standard ast module and is never run or imported. Parsing follows the grammar of the running Python version, and a syntax error is reported in the result rather than as a failure. The text may hold at most 200,000 characters.", max_length=PREBUILT_MAX_SOURCE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check whether Python source code parses under the running Python version and, when it does not, report the parser's message with the line and column of the problem. Use it to validate generated or edited code before saving or running it, because the code itself is never executed. The column is 1-based, python_version names the major and minor version whose grammar was used, and syntax that only a newer version accepts is invalid on an older one. Source holding a null character, or nested too deeply for the parser, is reported as invalid with a fixed message and a null line and column."""
        error: str | None = None
        line: int | None = None
        column: int | None = None
        # Refuse a null character before parsing: Python 3.11 raises
        # ValueError for it and later versions raise SyntaxError.
        if "\0" in source:
            error = _NULL_SOURCE_PROBLEM
        else:
            # Parse only; the parser's own message and position describe
            # a syntax error; a zero position means it is unknown.
            try:
                ast.parse(source)
            except SyntaxError as exc:
                error = exc.msg or "invalid syntax"
                line = exc.lineno or None
                column = exc.offset or None
            except (RecursionError, MemoryError):
                error = _DEEP_SOURCE_PROBLEM
            except ValueError:
                error = _ENCODING_SOURCE_PROBLEM
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        return {"valid": error is None, "error": error, "line": line, "column": column, "python_version": python_version}

    @staticmethod
    def list_python_functions(source: Annotated[str, Field(description=_PYTHON_SOURCE_DESCRIPTION, max_length=PREBUILT_MAX_SOURCE_CHARS)]) -> PrebuiltToolOutput:
        """List every function and method defined in Python source, in source order, with its qualified name, line range, parameters, decorators, and whether it is async or has a docstring. Use it to get an outline of a module or to find where a function lives before reading or editing it. Qualified names join enclosing classes and functions with dots and add <locals> after a function, parameter names keep their star prefixes, and decorators are written back from the syntax tree. Source that does not parse fails with an error naming source, and so does a listing longer than one million characters of JSON."""
        # Parse the source; nothing in it is run.
        tree = CodeAnalysisToolFunctions._parse_source(source)

        # Describe the functions one at a time in source order, keeping
        # a running size so an oversized listing stops early.
        functions: list[dict[str, object]] = []
        listed_size = 0
        try:
            for qualified, node in CodeAnalysisToolFunctions._definitions(tree):
                if isinstance(node, ast.ClassDef):
                    continue
                entry = CodeAnalysisToolFunctions._function_entry(node, qualified)
                listed_size += len(json.dumps(entry, separators=_COMPACT_SEPARATORS, ensure_ascii=False))
                # @intent prebuilt-code-listing-output-cap
                # Qualified names repeat their enclosing names, so a
                # short source can list megabytes; stop once the JSON
                # passes the output cap instead of building all of it
                # (INV-20).
                if listed_size > PREBUILT_MAX_TEXT_CHARS:
                    raise PrebuiltToolSupport.argument_error("source", _LONG_LISTING_PROBLEM, _SHORT_LISTING_EXPECTED)
                functions.append(entry)
        except RecursionError as exc:
            raise PrebuiltToolSupport.argument_error("source", _LONG_UNPARSE_PROBLEM, _SHALLOW_SOURCE_EXPECTED) from exc
        return {"functions": functions, "count": len(functions)}

    @staticmethod
    def list_python_classes(source: Annotated[str, Field(description=_PYTHON_SOURCE_DESCRIPTION, max_length=PREBUILT_MAX_SOURCE_CHARS)]) -> PrebuiltToolOutput:
        """List every class defined in Python source, in source order, with its qualified name, line range, bases, direct methods, decorators, and whether it has a docstring. Use it to understand the class structure of a module before reading or changing it. Bases and decorators are written back from the syntax tree, so a metaclass keyword appears among the bases, and nested classes carry their enclosing names. Source that does not parse fails with an error naming source, and so does a listing longer than one million characters of JSON."""
        # Parse the source; nothing in it is run.
        tree = CodeAnalysisToolFunctions._parse_source(source)

        # Describe the classes one at a time in source order, keeping a
        # running size so an oversized listing stops early.
        classes: list[dict[str, object]] = []
        listed_size = 0
        try:
            for qualified, node in CodeAnalysisToolFunctions._definitions(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                entry = CodeAnalysisToolFunctions._class_entry(node, qualified)
                listed_size += len(json.dumps(entry, separators=_COMPACT_SEPARATORS, ensure_ascii=False))
                # @intent prebuilt-code-listing-output-cap
                # Qualified names repeat their enclosing names, so a
                # short source can list megabytes; stop once the JSON
                # passes the output cap instead of building all of it
                # (INV-20).
                if listed_size > PREBUILT_MAX_TEXT_CHARS:
                    raise PrebuiltToolSupport.argument_error("source", _LONG_LISTING_PROBLEM, _SHORT_LISTING_EXPECTED)
                classes.append(entry)
        except RecursionError as exc:
            raise PrebuiltToolSupport.argument_error("source", _LONG_UNPARSE_PROBLEM, _SHALLOW_SOURCE_EXPECTED) from exc
        return {"classes": classes, "count": len(classes)}

    @staticmethod
    def list_python_imports(source: Annotated[str, Field(description=_PYTHON_SOURCE_DESCRIPTION, max_length=PREBUILT_MAX_SOURCE_CHARS)]) -> PrebuiltToolOutput:
        """List the import statements in Python source with their module, imported names, line, and relative level, plus the sorted distinct top-level modules imported absolutely. Use it to see what a module depends on or which packages a piece of code needs. Imports anywhere in the source are listed in source order, names keep their as aliases, and a plain import or a relative import without a module name has a null module. Source that does not parse fails with an error naming source."""
        # Parse the source and gather every import statement in source
        # order, including imports inside functions and classes.
        tree = CodeAnalysisToolFunctions._parse_source(source)
        statements = sorted((node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))), key=lambda node: (node.lineno, node.col_offset))

        # Describe each statement, keeping each name as it was written.
        imports = [
            {
                "module": node.module if isinstance(node, ast.ImportFrom) else None,
                "names": [alias.name if alias.asname is None else f"{alias.name} as {alias.asname}" for alias in node.names],
                "line": node.lineno,
                "from_import": isinstance(node, ast.ImportFrom),
                "level": (node.level or 0) if isinstance(node, ast.ImportFrom) else 0,
            }
            for node in statements
        ]

        # Collect the top-level package of every absolute import.
        modules = {alias.name.split(".")[0] for node in statements if isinstance(node, ast.Import) for alias in node.names}
        modules.update(node.module.split(".")[0] for node in statements if isinstance(node, ast.ImportFrom) and node.module and not node.level)
        return {"imports": imports, "modules": sorted(modules)}

    @staticmethod
    def count_lines_of_code(
        source: Annotated[str, Field(description="The source code whose lines are counted, given as plain text in the chosen language. Line breaks may be CRLF, LF, or a lone CR, and a trailing line break does not start an extra line. A line holding only whitespace counts as blank. The text may hold at most 200,000 characters.", max_length=PREBUILT_MAX_SOURCE_CHARS)],
        language: Annotated[CodeLanguage, Field(description="The language whose comment syntax tells comment lines from code lines. Each language has its own fixed line comment markers and block comment delimiters. The default is python. A value outside the listed languages fails validation.")] = CodeLanguage.PYTHON,
    ) -> PrebuiltToolOutput:
        """Count the total, code, comment, and blank lines in source code written in one of the supported languages. Use it to size a file or to see how much of it is code and how much is commentary. Line and block comments follow the chosen language, a line with code and a trailing comment counts as code, and Python docstrings count as code. Strings are not tracked, so a comment marker inside a string literal can be miscounted, and the tool has no failure case beyond its caps."""
        # Build one pattern that finds the next comment marker of the
        # language, trying longer markers first.
        line_markers, block_pairs = PREBUILT_COMMENT_SYNTAX[language]
        openers = dict(block_pairs)
        markers = sorted({*line_markers, *openers}, key=lambda marker: (-len(marker), marker))
        pattern = re.compile("|".join(re.escape(marker) for marker in markers))

        # Classify each line, carrying an open block comment from one
        # line to the next; blank lines leave the open block unchanged.
        lines = PrebuiltToolSupport.split_lines(source)
        blank_lines = 0
        code_lines = 0
        closer: str | None = None
        for line in lines:
            if not line.strip():
                blank_lines += 1
                continue
            has_code, closer = CodeAnalysisToolFunctions._line_has_code(line, closer, line_markers, openers, pattern)
            code_lines += has_code
        return {"total_lines": len(lines), "code_lines": code_lines, "comment_lines": len(lines) - code_lines - blank_lines, "blank_lines": blank_lines}

    @staticmethod
    def get_python_function_signature(
        source: Annotated[str, Field(description=_PYTHON_SOURCE_DESCRIPTION, max_length=PREBUILT_MAX_SOURCE_CHARS)],
        name: Annotated[str, Field(description="The function to describe, given as a qualified name or a bare name. A qualified name joins enclosing classes and functions with dots, so a method's qualified name is its class name, a dot, and its own name. A bare name is used only when no qualified name matches and exactly one function has that name. The name must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
    ) -> PrebuiltToolOutput:
        """Describe one function or method in Python source: its signature line, each parameter with its kind, annotation, and default, its return annotation, its docstring, and its line. Use it to learn how to call a function without reading its whole body. The name is matched against qualified names first and then against bare names, and the signature is written back from the syntax tree with async def for a coroutine. Source that does not parse fails with an error naming source, and a name with no match or with several bare matches fails with an error naming name that lists candidates."""
        # Parse the source and list its functions with qualified names.
        tree = CodeAnalysisToolFunctions._parse_source(source)
        functions = [(qualified, node) for qualified, node in CodeAnalysisToolFunctions._definitions(tree) if not isinstance(node, ast.ClassDef)]

        # Prefer an exact qualified name, and accept a bare name only
        # when exactly one function has it.
        chosen = next((node for qualified, node in functions if qualified == name), None)
        bare = [(qualified, node) for qualified, node in functions if node.name == name]
        if chosen is None and len(bare) != 1:
            candidates = [qualified if len(qualified) <= _REPORTED_NAME_CHARS else qualified[:_REPORTED_NAME_CHARS] + "…" for qualified, _ in (bare or functions)[:PREBUILT_MAX_REPORTED_NAMES]]
            problem = f"the bare name matches {len(bare)} functions" if bare else "no function in the source has that qualified or bare name"
            expected = f"the qualified or bare name of one function, from candidates such as {', '.join(candidates)}" if candidates else "the name of a function, but the source defines none"
            raise PrebuiltToolSupport.argument_error("name", problem, expected)
        node = chosen or bare[0][1]

        # Write the signature and each parameter back from the tree.
        try:
            parameters = CodeAnalysisToolFunctions._parameter_entries(node.args)
            returns = ast.unparse(node.returns) if node.returns else None
            signature = f"{'async def' if isinstance(node, ast.AsyncFunctionDef) else 'def'} {node.name}({ast.unparse(node.args)})"
        except RecursionError as exc:
            raise PrebuiltToolSupport.argument_error("source", _LONG_UNPARSE_PROBLEM, _SHALLOW_SOURCE_EXPECTED) from exc
        if returns is not None:
            signature += f" -> {returns}"
        return {"signature": signature, "parameters": parameters, "returns": returns, "docstring": ast.get_docstring(node), "line": node.lineno}

    @staticmethod
    def find_python_name_usages(
        source: Annotated[str, Field(description=_PYTHON_SOURCE_DESCRIPTION, max_length=PREBUILT_MAX_SOURCE_CHARS)],
        name: Annotated[str, Field(description="The identifier to look for, matched exactly and with case. It is compared with variable, function, class, parameter, attribute, and keyword argument names, and an import matches its alias, its full module path, or any dotted part of that path. A name that never occurs gives an empty list. The name must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find every place where a name is defined, bound as a parameter, imported, read, assigned, deleted, used as an attribute, or used as a keyword argument in Python source. Use it to trace how a variable, function, or attribute is used before renaming or removing it. Matching is purely syntactic with no scope resolution, lines and columns are 1-based with columns counted in characters, and usages are sorted by line and then column. At most 1,000 usages are listed while the count covers all, and source that does not parse fails with an error naming source."""
        # Parse the source; nothing in it is run.
        tree = CodeAnalysisToolFunctions._parse_source(source)

        # Work in UTF-8, the unit ast uses for columns, and note where
        # each line starts and how the name looks as a whole word.
        data = source.encode("utf-8")
        line_starts = [0, *(match.end() for match in _ENCODED_LINE_BREAK.finditer(data))]
        word = re.compile(_IDENTIFIER_BEFORE + re.escape(name.encode("utf-8", "surrogatepass")) + _IDENTIFIER_AFTER)

        # Place every usage at the name itself; definitions and imports
        # start at a keyword, so the name is searched for from there.
        usages = sorted(CodeAnalysisToolFunctions._usage_position(data, line_starts, word, usage) for usage in CodeAnalysisToolFunctions._name_usages(tree, name))

        # List the first usages with columns counted in characters,
        # while the count covers every usage.
        listed, truncated = PrebuiltToolSupport.cap_items(
            {"line": line, "column": len(data[line_starts[line - 1] : line_starts[line - 1] + offset].decode("utf-8", "ignore")) + 1, "context": kind.value} for line, offset, kind in usages
        )
        return {"usages": listed, "count": len(usages), "truncated": truncated}

    @staticmethod
    def python_literal_to_json(
        literal: Annotated[str, Field(description="The Python literal to convert, written as Python source for one value. Only literal syntax is accepted, so names, calls, and operators other than signs and complex number arithmetic are refused. It is evaluated with the standard literal evaluator and is never run. The text may hold at most 200,000 characters.", max_length=PREBUILT_MAX_SOURCE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Convert a Python literal made of dicts, lists, tuples, sets, strings, numbers, booleans, and None into compact JSON text. Use it to turn printed Python data into JSON safely, because the text is only read as a literal and never run. Tuples become arrays, sets become arrays sorted by their JSON text, and number, boolean, and None keys become strings, while object keys keep their source order. Bytes, complex numbers, infinite or NaN floats, tuple keys, nesting deeper than 100 levels, and anything that is not a literal fail with an error naming literal."""
        # Refuse a null character before parsing: Python 3.11 raises
        # ValueError for it and later versions raise SyntaxError.
        if "\0" in literal:
            raise PrebuiltToolSupport.argument_error("literal", "the literal contains a null character", _LITERAL_EXPECTED)

        # Read the text as a literal only; names, calls, and other code
        # are refused by the literal evaluator itself.
        try:
            value = ast.literal_eval(literal)
        except (SyntaxError, ValueError, TypeError) as exc:
            raise PrebuiltToolSupport.argument_error("literal", "the text is not a Python literal of plain data", _LITERAL_EXPECTED) from exc
        except (RecursionError, MemoryError) as exc:
            raise PrebuiltToolSupport.argument_error("literal", "the literal is nested too deeply to read", _LITERAL_EXPECTED) from exc

        # @intent prebuilt-python-literal-nesting-cap
        # A value nested past the cap would make the output serializer
        # recurse too deep after the tool returns, where FunctionTool
        # can no longer turn the failure into a result (INV-19).
        if PrebuiltToolSupport.nesting_level(value) > PREBUILT_MAX_JSON_NESTING:
            raise PrebuiltToolSupport.argument_error("literal", f"the literal is nested deeper than {PREBUILT_MAX_JSON_NESTING} levels", _LITERAL_EXPECTED)

        # Refuse values JSON cannot hold, then write compact JSON with
        # sets turned into sorted arrays.
        problem = CodeAnalysisToolFunctions._literal_problem(value)
        if problem is not None:
            raise PrebuiltToolSupport.argument_error("literal", problem, _LITERAL_EXPECTED)
        return {"json": json.dumps(value, default=CodeAnalysisToolFunctions._sorted_set_items, separators=_COMPACT_SEPARATORS, ensure_ascii=False, allow_nan=False)}

    @staticmethod
    def shell_split_command(
        command: Annotated[str, Field(description="The POSIX shell command line to split, given as plain text. Quotes and backslashes are read the way a POSIX shell reads them, and every other character is kept literally. A hash sign does not start a comment. The text may hold at most 100,000 characters.", max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Split a POSIX shell command line into its arguments the way a POSIX shell would, honoring single quotes, double quotes, and backslash escapes. Use it to see exactly which arguments a command passes, or to take a command apart before changing it. There is no comment handling and no variable or glob expansion, and nothing is ever run. An unbalanced quote or a trailing lone backslash fails with an error naming command."""
        try:
            arguments = shlex.split(command, posix=True)
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("command", "the command has an unbalanced quote or ends with a lone backslash", "a command line whose quotes are closed and whose backslashes each escape a character") from exc
        return {"arguments": arguments, "count": len(arguments)}

    @staticmethod
    def shell_quote_arguments(
        arguments: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description="The arguments to join, in order, one string per argument. Each argument is quoted on its own, so spaces and quotes inside it survive a round trip through a POSIX shell. The list must hold between 1 and 10,000 arguments. Each argument may hold at most 10,000 characters.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Join a list of arguments into one POSIX shell command line, quoting each argument so the shell reads it back unchanged. Use it to build a safe command from values that may hold spaces, quotes, or shell metacharacters. Arguments made only of safe characters stay bare, every other argument is wrapped in single quotes, and an empty argument becomes a pair of quotes. The quoting is for POSIX shells only and does not cover Windows shells, and an empty list fails validation."""
        return {"command": " ".join(shlex.quote(argument) for argument in arguments)}

    @staticmethod
    def _parse_source(source: str) -> ast.Module:
        """Parse Python source without running it, turning every parser failure into an error naming source."""
        # Python 3.11 raises ValueError for a null character and later
        # versions raise SyntaxError, so it is refused before parsing.
        if "\0" in source:
            raise PrebuiltToolSupport.argument_error("source", _NULL_SOURCE_PROBLEM, _PARSABLE_SOURCE_EXPECTED)
        try:
            return ast.parse(source)
        except SyntaxError as exc:
            place = f" at line {exc.lineno}, column {exc.offset}" if exc.lineno and exc.offset else ""
            problem = f"the source does not parse{place}: {(exc.msg or 'invalid syntax').rstrip('.')}"
            raise PrebuiltToolSupport.argument_error("source", problem, _PARSABLE_SOURCE_EXPECTED) from exc
        except (RecursionError, MemoryError) as exc:
            raise PrebuiltToolSupport.argument_error("source", _DEEP_SOURCE_PROBLEM, _SHALLOW_SOURCE_EXPECTED) from exc
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("source", _ENCODING_SOURCE_PROBLEM, _PARSABLE_SOURCE_EXPECTED) from exc

    @staticmethod
    def _definitions(tree: ast.Module) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]]:
        """Yield every function and class definition with its qualified name, in source order, using an explicit stack."""
        pending: list[tuple[ast.AST, str]] = [(tree, "")]
        while pending:
            node, prefix = pending.pop()
            inner_prefix = prefix
            if isinstance(node, _DEFINITION_TYPES):
                qualified = prefix + node.name
                yield qualified, node
                inner_prefix = qualified + ("." if isinstance(node, ast.ClassDef) else ".<locals>.")
            # Children go on the stack last first, so the first child is
            # visited next and the walk keeps source order.
            pending.extend((child, inner_prefix) for child in reversed(list(ast.iter_child_nodes(node))))

    @staticmethod
    def _function_entry(node: ast.FunctionDef | ast.AsyncFunctionDef, qualified: str) -> dict[str, object]:
        """Describe one function for list_python_functions, with star prefixes on the collecting parameters."""
        arguments = node.args
        names = [argument.arg for argument in (*arguments.posonlyargs, *arguments.args)]
        names += [f"*{arguments.vararg.arg}"] if arguments.vararg else []
        names += [argument.arg for argument in arguments.kwonlyargs]
        names += [f"**{arguments.kwarg.arg}"] if arguments.kwarg else []
        return {
            "name": node.name,
            "qualified_name": qualified,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "parameters": names,
            "decorators": [ast.unparse(decorator) for decorator in node.decorator_list],
            "has_docstring": ast.get_docstring(node, clean=False) is not None,
        }

    @staticmethod
    def _class_entry(node: ast.ClassDef, qualified: str) -> dict[str, object]:
        """Describe one class for list_python_classes; keyword arguments of the class line count as bases."""
        return {
            "name": node.name,
            "qualified_name": qualified,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "bases": [ast.unparse(base) for base in (*node.bases, *node.keywords)],
            "methods": [child.name for child in node.body if isinstance(child, _FUNCTION_TYPES)],
            "decorators": [ast.unparse(decorator) for decorator in node.decorator_list],
            "has_docstring": ast.get_docstring(node, clean=False) is not None,
        }

    @staticmethod
    def _line_has_code(line: str, closer: str | None, line_markers: tuple[str, ...], openers: Mapping[str, str], pattern: re.Pattern[str]) -> tuple[bool, str | None]:
        """Say whether a non-blank line holds code outside comments, and return the block comment closer still open after it."""
        has_code = False
        position = 0
        while True:
            # Skip to the end of an open block comment, or give up on
            # the rest of the line when the block does not close on it.
            if closer is not None:
                end = line.find(closer, position)
                if end < 0:
                    return has_code, closer
                position, closer = end + len(closer), None
            # Text before the next marker is code unless it is blank,
            # and a line comment marker ends the line.
            match = pattern.search(line, position)
            has_code = has_code or bool(line[position : match.start() if match else len(line)].strip())
            if match is None or match.group() in line_markers:
                return has_code, None
            closer = openers[match.group()]
            position = match.end()

    @staticmethod
    def _parameter_entries(arguments: ast.arguments) -> list[dict[str, object]]:
        """Describe every parameter of a signature in order, with its kind, annotation, and default as source text."""
        # Defaults belong to the last positional parameters, so the
        # first ones are padded with None.
        positional = [*arguments.posonlyargs, *arguments.args]
        defaults: list[ast.expr | None] = [*([None] * (len(positional) - len(arguments.defaults))), *arguments.defaults]
        slots: list[tuple[ast.arg, PythonParameterKind, ast.expr | None]] = [
            (argument, PythonParameterKind.POSITIONAL_ONLY if index < len(arguments.posonlyargs) else PythonParameterKind.POSITIONAL_OR_KEYWORD, default)
            for index, (argument, default) in enumerate(zip(positional, defaults, strict=True))
        ]
        if arguments.vararg:
            slots.append((arguments.vararg, PythonParameterKind.VAR_POSITIONAL, None))
        slots.extend((argument, PythonParameterKind.KEYWORD_ONLY, default) for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True))
        if arguments.kwarg:
            slots.append((arguments.kwarg, PythonParameterKind.VAR_KEYWORD, None))
        return [
            {
                "name": argument.arg,
                "kind": kind.value,
                "annotation": ast.unparse(argument.annotation) if argument.annotation else None,
                "default": ast.unparse(default) if default else None,
            }
            for argument, kind, default in slots
        ]

    @staticmethod
    def _name_usages(tree: ast.Module, name: str) -> list[tuple[int, int, PythonNameUsageKind, bool]]:
        """Find the nodes that use a name, as (line, UTF-8 column, kind, whether the name must be searched for from there)."""
        usages: list[tuple[int, int, PythonNameUsageKind, bool]] = []
        for node in ast.walk(tree):
            match node:
                case ast.Name(id=identifier) if identifier == name:
                    usages.append((node.lineno, node.col_offset, _NAME_CONTEXT_KINDS.get(type(node.ctx), PythonNameUsageKind.LOAD), False))
                case ast.arg(arg=identifier) if identifier == name:
                    usages.append((node.lineno, node.col_offset, PythonNameUsageKind.PARAMETER, False))
                case ast.keyword(arg=identifier) if identifier == name:
                    usages.append((node.lineno, node.col_offset, PythonNameUsageKind.KEYWORD, False))
                case ast.Attribute(attr=identifier) if identifier == name:
                    # The attribute name ends where the expression ends.
                    end_column = (node.end_col_offset or node.col_offset) - len(identifier.encode("utf-8"))
                    usages.append((node.end_lineno or node.lineno, end_column, PythonNameUsageKind.ATTRIBUTE, False))
                case ast.FunctionDef(name=identifier) | ast.AsyncFunctionDef(name=identifier) | ast.ClassDef(name=identifier) if identifier == name:
                    usages.append((node.lineno, node.col_offset, PythonNameUsageKind.DEFINITION, True))
                case ast.alias(name=identifier, asname=bound) if name in (bound, identifier, *identifier.split(".")):
                    usages.append((node.lineno, node.col_offset, PythonNameUsageKind.IMPORT, True))
        return usages

    @staticmethod
    def _usage_position(data: bytes, line_starts: list[int], word: re.Pattern[bytes], usage: tuple[int, int, PythonNameUsageKind, bool]) -> tuple[int, int, PythonNameUsageKind]:
        """Return a usage's line and UTF-8 column, searching forward for the name when the node starts at a keyword."""
        line, offset, kind, search = usage
        line = min(max(line, 1), len(line_starts))
        found = word.search(data, line_starts[line - 1] + offset) if search else None
        if found is None:
            return line, offset, kind
        index = bisect_right(line_starts, found.start()) - 1
        return index + 1, found.start() - line_starts[index], kind

    @staticmethod
    def _literal_problem(value: object) -> str | None:
        """Walk a literal value with a work stack and describe the first part JSON cannot hold, or return None."""
        pending: list[object] = [value]
        while pending:
            item = pending.pop()
            match item:
                case dict() if any(isinstance(key, tuple) for key in item):
                    return "a dictionary key is a tuple, which JSON cannot use as an object key"
                case dict():
                    pending.extend([*item.keys(), *item.values()])
                case list() | tuple() | set() | frozenset():
                    pending.extend(item)
                case float() if not math.isfinite(item):
                    return "the literal holds an infinite or NaN number, which JSON cannot hold"
                # @intent prebuilt-integer-digit-cap
                # Python cannot write an int of over 4,300 digits as
                # text, and a hexadecimal literal can be far longer, so
                # an integer past the INV-18 digit cap is refused here.
                case int() if abs(item) >= _INTEGER_RESULT_BOUND:
                    return f"the literal holds an integer of more than {PREBUILT_MAX_INTEGER_DIGITS} digits"
                case str() | int() | float() | None:
                    continue
                case _:
                    return _UNSUPPORTED_LITERAL_PROBLEMS.get(type(item), "the literal holds a value that has no JSON form")
        return None

    @staticmethod
    def _sorted_set_items(value: object) -> list[object]:
        """Give json.dumps a set as a list sorted by each item's compact JSON text; json.dumps calls this for every set."""
        if isinstance(value, (set, frozenset)):
            item_text = partial(json.dumps, default=CodeAnalysisToolFunctions._sorted_set_items, separators=_COMPACT_SEPARATORS, ensure_ascii=False, allow_nan=False)
            return sorted(value, key=item_text)
        raise PrebuiltToolSupport.argument_error("literal", "the literal holds a value that has no JSON form", _LITERAL_EXPECTED)

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.verify_python_syntax,
            cls.list_python_functions,
            cls.list_python_classes,
            cls.list_python_imports,
            cls.count_lines_of_code,
            cls.get_python_function_signature,
            cls.find_python_name_usages,
            cls.python_literal_to_json,
            cls.shell_split_command,
            cls.shell_quote_arguments,
        )


__all__ = ["CodeAnalysisToolFunctions"]
