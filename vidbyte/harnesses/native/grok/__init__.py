"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: The Grok Build subpackage of the harness thread functions; exports run_grok_thread, continue_grok_thread and fork_grok_thread, the eight keyless Grok thread helpers (list, list recent, list since, get, read, lineage, search and delete), and the fourteen Grok command functions (run_grok_command and its thirteen named wrappers).
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py, which re-exports every function bound here. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only binds each public function to its class attribute, GrokThreads (grok/threads.py), GrokThreadHelpers (grok/helpers.py) or GrokCommands (grok/commands.py), so callers get plain module functions while the code stays in its class.
FUNCTION INVENTORY: No functions of its own. run_grok_thread, continue_grok_thread and fork_grok_thread are bound from GrokThreads; list_grok_threads, list_recent_grok_threads, list_grok_threads_since, get_grok_thread, read_grok_thread, get_grok_thread_lineage, search_grok_threads and delete_grok_thread from GrokThreadHelpers; run_grok_command, run_grok_goal, run_grok_implement, run_grok_design, run_grok_execute_plan, run_grok_review, run_grok_code_review, run_grok_resume_claude, run_grok_resume_codex, run_grok_resume_cursor, run_grok_imagine, run_grok_imagine_video, run_grok_plan and run_grok_explore from GrokCommands.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable. 2. Do not export GrokThreadRun, GrokHelperRun, GrokCommandRun, GrokHome, GrokStore or the wire readers; they are internal.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok.commands import GrokCommands
from vidbyte.harnesses.native.grok.helpers import GrokThreadHelpers
from vidbyte.harnesses.native.grok.threads import GrokThreads

run_grok_thread = GrokThreads.run_grok_thread
continue_grok_thread = GrokThreads.continue_grok_thread
fork_grok_thread = GrokThreads.fork_grok_thread
list_grok_threads = GrokThreadHelpers.list_grok_threads
list_recent_grok_threads = GrokThreadHelpers.list_recent_grok_threads
list_grok_threads_since = GrokThreadHelpers.list_grok_threads_since
get_grok_thread = GrokThreadHelpers.get_grok_thread
read_grok_thread = GrokThreadHelpers.read_grok_thread
get_grok_thread_lineage = GrokThreadHelpers.get_grok_thread_lineage
search_grok_threads = GrokThreadHelpers.search_grok_threads
delete_grok_thread = GrokThreadHelpers.delete_grok_thread
run_grok_command = GrokCommands.run_grok_command
run_grok_goal = GrokCommands.run_grok_goal
run_grok_implement = GrokCommands.run_grok_implement
run_grok_design = GrokCommands.run_grok_design
run_grok_execute_plan = GrokCommands.run_grok_execute_plan
run_grok_review = GrokCommands.run_grok_review
run_grok_code_review = GrokCommands.run_grok_code_review
run_grok_resume_claude = GrokCommands.run_grok_resume_claude
run_grok_resume_codex = GrokCommands.run_grok_resume_codex
run_grok_resume_cursor = GrokCommands.run_grok_resume_cursor
run_grok_imagine = GrokCommands.run_grok_imagine
run_grok_imagine_video = GrokCommands.run_grok_imagine_video
run_grok_plan = GrokCommands.run_grok_plan
run_grok_explore = GrokCommands.run_grok_explore

__all__ = [
    "continue_grok_thread",
    "delete_grok_thread",
    "fork_grok_thread",
    "get_grok_thread",
    "get_grok_thread_lineage",
    "list_grok_threads",
    "list_grok_threads_since",
    "list_recent_grok_threads",
    "read_grok_thread",
    "run_grok_code_review",
    "run_grok_command",
    "run_grok_design",
    "run_grok_execute_plan",
    "run_grok_explore",
    "run_grok_goal",
    "run_grok_imagine",
    "run_grok_imagine_video",
    "run_grok_implement",
    "run_grok_plan",
    "run_grok_resume_claude",
    "run_grok_resume_codex",
    "run_grok_resume_cursor",
    "run_grok_review",
    "run_grok_thread",
    "search_grok_threads",
]
