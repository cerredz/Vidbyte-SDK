"""FILE: vidbyte/lib/process/argv.py

PURPOSE: Defines CliArgv, the canonical builder of a command line: the launcher, the subcommand words, the options in one of two styles, and the operands, returned as a tuple of plain strings.
ROLE IN CODEBASE: Called by every harness thread function under vidbyte/harnesses/native/ (Grok and opencode in the joined style, Muse, its WSL launcher and Claude Code in the separate style) before it hands the argv to CliRunner in vidbyte/lib/process/runner.py.
ARCHITECTURE NOTE: Pure and synchronous: no I/O and no environment reads. Every element it returns is a plain str, so an enum member never reaches argv; str(member) gives the value because every flag enum is a StrEnum. The order is exactly as given.
FUNCTION INVENTORY: CliArgv.build is the narrated main function; _option_elements turns one option into its argv elements for a style.
COMMON MODIFICATION PATTERNS: A new option style adds a CliOptionStyle member (vidbyte/lib/enums/process.py) and its branch in _option_elements.
WHAT NOT TO DO IN THIS FILE: 1. Do not let a separate-style value that starts with a dash through; the vendor would read it as a flag. 2. Do not import from a layer above vidbyte.lib. 3. Do not quote a value in an error; it can be a prompt.
KNOWN EDGE CASES: In the joined style a value that starts with a dash is safe, because it stays inside the --flag=value element. Operands are not checked; a caller that passes a prompt as an operand puts the end-of-options operand before it.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_argv.py
"""

from __future__ import annotations

from vidbyte.lib.constants.native_threads import NATIVE_PROCESS_OPTION_SEPARATOR
from vidbyte.lib.dataclasses.process import CliOption
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError


class CliArgv:
    """Builds one argv tuple of plain strings from a launcher, subcommand words, options and operands."""

    @staticmethod
    def build(launcher: tuple[str, ...], *, command: tuple[str, ...] = (), options: tuple[CliOption, ...] = (), style: CliOptionStyle, operands: tuple[str, ...] = ()) -> tuple[str, ...]:
        # @intent cli-values-never-become-flags
        # Every option goes through _option_elements, which refuses a
        # separate-style value that starts with a dash, so a thread id
        # or a model can never be read by the vendor as another flag.
        elements = [str(part) for part in (*launcher, *command)]

        # Flatten the options in the order given.
        for option in options:
            elements.extend(CliArgv._option_elements(option, style))

        # Operands come last, as plain strings.
        elements.extend(str(operand) for operand in operands)
        return tuple(elements)

    @staticmethod
    def _option_elements(option: CliOption, style: CliOptionStyle) -> tuple[str, ...]:
        # A switch is its flag; a valued option is one --flag=value
        # element in the joined style, or the flag and the value apart.
        flag = str(option.flag)
        if option.value is None:
            return (flag,)
        if style is CliOptionStyle.JOINED:
            return (flag + NATIVE_PROCESS_OPTION_SEPARATOR + str(option.value),)
        if str(option.value).startswith("-"):
            raise ConfigurationError(f"The value of {flag} must not start with a dash, or the program would read it as a flag.", details={"field": flag})
        return (flag, str(option.value))


__all__ = ["CliArgv"]
