"""FILE: vidbyte/cli/coding.py

PURPOSE: Adds `vidbyte-sdk coding run`, which builds a CodingAgent over one folder from command-line flags, runs one task through it, and prints the agent's final reply.
ROLE IN CODEBASE: Registered by vidbyte/cli/__init__.py (VidbyteCli._register_subcommand_groups); a thin adapter over vidbyte/agents/coding.py (CodingAgent), whose CodingAgentSettings owns every check of the folder and the keys.
ARCHITECTURE NOTE: CodingAgent is imported inside build_agent, so `vidbyte-sdk --help` and `vidbyte-sdk coding --help` never load the agents layer. A fetch key is never a flag value, because flag values land in shell history and process lists; each --<provider>-key-env flag names the environment variable that holds the key. A ConfigurationError from CodingAgent reaches VidbyteCli.main, which prints it and returns 1.
FUNCTION INVENTORY: CodingCommandGroup.register attaches `coding run` and its flags; run_task is the narrated main function; _fetch_keys reads the named environment variables; build_agent turns the parsed flags and keys into a CodingAgent. register is the module hook the root CLI calls.
COMMON MODIFICATION PATTERNS: A new CodingAgent keyword gets one flag in register and one keyword in build_agent; a new keyed fetch provider gets one row in FETCH_KEY_FLAGS.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept a key value as a flag. 2. Do not check the root folder or the keys here; CodingAgentSettings owns those checks. 3. Do not import vidbyte.agents at module level.
KNOWN EDGE CASES: A named environment variable that is unset fails with an error naming the variable, never a value. The agent runs with CodingAgent's default allow-all policy, so it may run any bash command, and bash is not confined to the folder.
RELATED DOCS: vidbyte/cli/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_cli.py
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.coding import CodingAgent

CODING_RUN_DEFAULT_NAME = "coding-agent"
CODING_RUN_DEFAULT_SYSTEM_PROMPT = "You are a careful software engineer. Make the smallest change that completes the task, and check that it works before you finish."

# Each row is (flag, argparse destination, CodingAgent key parameter).
FETCH_KEY_FLAGS = (
    ("--firecrawl-key-env", "firecrawl_key_env", "firecrawl_api_key"),
    ("--browserbase-key-env", "browserbase_key_env", "browserbase_api_key"),
    ("--parallel-key-env", "parallel_key_env", "parallel_api_key"),
    ("--tavily-key-env", "tavily_key_env", "tavily_api_key"),
)


class CodingCommandGroup:
    """Registers and handles the vidbyte-sdk coding subcommand group."""

    def register(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Attaches `coding run` with its task, folder, model, and
        # fetch-key flags.
        coding_parser = subparsers.add_parser("coding", help="Run a CodingAgent over a folder from the terminal.")
        action_parsers = coding_parser.add_subparsers(dest="coding_command", required=True)
        parser = action_parsers.add_parser("run", help="Run one task with a CodingAgent and print its final reply.")
        parser.add_argument("task", help="The task for the agent, in plain words.")
        parser.add_argument("--root-dir", default=".", help="The folder the agent works in; every file tool and bash command starts here (default: the current folder).")
        parser.add_argument("--provider", help="The model provider, for example openai.")
        parser.add_argument("--model", dest="model_name", help="The model name, for example gpt-4.1.")
        parser.add_argument("--name", default=CODING_RUN_DEFAULT_NAME, help=f"The agent's name (default: {CODING_RUN_DEFAULT_NAME}).")
        parser.add_argument("--system-prompt", default=CODING_RUN_DEFAULT_SYSTEM_PROMPT, help="The agent's system prompt (default: a short careful-engineer prompt).")
        fetch = parser.add_argument_group("web fetch", "Name at most one environment variable that holds a fetch provider's API key; with none, the agent fetches pages over plain HTTP.")
        for flag, dest, parameter in FETCH_KEY_FLAGS:
            fetch.add_argument(flag, dest=dest, metavar="ENV_VAR", help=f"Environment variable holding the key passed as {parameter}.")
        parser.set_defaults(handler=self.run_task)

    def run_task(self, args: argparse.Namespace) -> int:
        # Read each fetch key from the environment variable its flag
        # names, so no key ever appears on the command line.
        keys = self._fetch_keys(args)

        # Build the agent; CodingAgent checks the folder and the keys
        # and raises a clear error when one of them is wrong.
        agent = self.build_agent(args, keys)

        # Run the one task through the agent's tool loop until the
        # model reports that it is done.
        reply = agent.run(args.task)

        # Print only the final reply, so the output can be piped.
        print(reply.content)
        return 0

    def _fetch_keys(self, args: argparse.Namespace) -> dict[str, str]:
        # Maps each CodingAgent key parameter whose flag was given to
        # the value of the environment variable that flag names.
        keys: dict[str, str] = {}
        for flag, dest, parameter in FETCH_KEY_FLAGS:
            variable = getattr(args, dest)
            if variable is None:
                continue
            value = os.environ.get(variable)
            if value is None:
                raise ConfigurationError(f"{flag} names the environment variable {variable}, but it is not set.", details={"flag": flag, "variable": variable})
            keys[parameter] = value
        return keys

    def build_agent(self, args: argparse.Namespace, keys: dict[str, str]) -> CodingAgent:
        # Imports CodingAgent only when a task runs, so help output
        # stays fast and never loads the agents layer.
        from vidbyte.agents.coding import CodingAgent

        return CodingAgent(name=args.name, system_prompt=args.system_prompt, root_dir=args.root_dir, provider=args.provider, model_name=args.model_name, **keys)


def register(subparsers: argparse._SubParsersAction[Any]) -> None:
    # Registers the coding command group with the root vidbyte-sdk
    # parser.
    CodingCommandGroup().register(subparsers)


__all__ = [
    "CodingCommandGroup",
    "register",
]
