"""Context Protocol Header

Description:
    Exports Vidbyte's built-in tool categories.
Purpose:
    Provides convenient imports for safe built-in tools without auto-registering
    environment-specific instances.
Architecture:
    - Code search tools from builtins.code_search.
    - Patch/edit tools from builtins.editing.
    - Context compaction tools from builtins.context.
    - Web tools: web_search, web_fetch.
    - Execution tools: shell, http_client, verification.
    - Data tools: sql, pdf.
    - VCS tools: git (11 tools), github (8 tools).
    - Agent tools: todo, plan, memory, monitor, lsp, image_gen.
    - Browser tools: 12 browser automation tools.
Relations:
    Related to vidbyte.tools.client and vidbyte.tools.registry.
"""

from __future__ import annotations

from vidbyte.tools.builtins.browser import (
    browser_act,
    browser_click,
    browser_close_tab,
    browser_extract,
    browser_get_content,
    browser_list_tabs,
    browser_navigate,
    browser_new_tab,
    browser_press_key,
    browser_screenshot,
    browser_scroll,
    browser_switch_tab,
    browser_type,
)
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool, SemanticSearchTool
from vidbyte.tools.builtins.context import (
    CompactionMode,
    ContextCompactionTool,
    ContextMessage,
    ProgressLog,
)
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.builtins.git import (
    git_add,
    git_branch_create,
    git_branch_list,
    git_checkout,
    git_clone,
    git_commit,
    git_diff,
    git_log,
    git_push,
    git_remote_list,
    git_status,
)
from vidbyte.tools.builtins.github import (
    github_add_pr_comment,
    github_create_issue,
    github_create_pr,
    github_get_issue,
    github_get_pr,
    github_get_pr_diff,
    github_list_issues,
    github_list_prs,
)
from vidbyte.tools.builtins.http_client import http_delete, http_get, http_post, http_put
from vidbyte.tools.builtins.image_gen import generate_image
from vidbyte.tools.builtins.lsp import (
    lsp_call_hierarchy,
    lsp_definition,
    lsp_diagnostics,
    lsp_format,
    lsp_hover,
    lsp_references,
    lsp_symbols,
    lsp_type_definition,
)
from vidbyte.tools.builtins.memory import (
    memory_delete,
    memory_list,
    memory_load,
    memory_save,
    memory_search,
)
from vidbyte.tools.builtins.monitor import (
    monitor_list,
    monitor_read,
    monitor_start,
    monitor_stop,
)
from vidbyte.tools.builtins.pdf import pdf_metadata, pdf_read, pdf_read_tables
from vidbyte.tools.builtins.plan import enter_plan_mode, exit_plan_mode
from vidbyte.tools.builtins.shell import ShellTool
from vidbyte.tools.builtins.sql import sql_describe_table, sql_list_tables, sql_query
from vidbyte.tools.builtins.todo import (
    todo_add_dependency,
    todo_create,
    todo_list,
    todo_update,
    todo_visualize,
)
from vidbyte.tools.builtins.verification import verify_run_lint, verify_run_tests
from vidbyte.tools.builtins.web_fetch import web_fetch
from vidbyte.tools.builtins.web_search import web_search

__all__ = [
    "CalculatorTool",
    "CodeExecutionTool",
    "CompactionMode",
    "ContextCompactionTool",
    "ContextMessage",
    "DocumentRetrievalTool",
    "GlobTool",
    "GrepTool",
    "PatchTool",
    "ProgressLog",
    "SemanticSearchTool",
    "ShellTool",
    "browser_act",
    "browser_click",
    "browser_close_tab",
    "browser_extract",
    "browser_get_content",
    "browser_list_tabs",
    "browser_navigate",
    "browser_new_tab",
    "browser_press_key",
    "browser_screenshot",
    "browser_scroll",
    "browser_switch_tab",
    "browser_type",
    "enter_plan_mode",
    "exit_plan_mode",
    "generate_image",
    "git_add",
    "git_branch_create",
    "git_branch_list",
    "git_checkout",
    "git_clone",
    "git_commit",
    "git_diff",
    "git_log",
    "git_push",
    "git_remote_list",
    "git_status",
    "github_add_pr_comment",
    "github_create_issue",
    "github_create_pr",
    "github_get_issue",
    "github_get_pr",
    "github_get_pr_diff",
    "github_list_issues",
    "github_list_prs",
    "http_delete",
    "http_get",
    "http_post",
    "http_put",
    "lsp_call_hierarchy",
    "lsp_definition",
    "lsp_diagnostics",
    "lsp_format",
    "lsp_hover",
    "lsp_references",
    "lsp_symbols",
    "lsp_type_definition",
    "memory_delete",
    "memory_list",
    "memory_load",
    "memory_save",
    "memory_search",
    "monitor_list",
    "monitor_read",
    "monitor_start",
    "monitor_stop",
    "pdf_metadata",
    "pdf_read",
    "pdf_read_tables",
    "sql_describe_table",
    "sql_list_tables",
    "sql_query",
    "todo_add_dependency",
    "todo_create",
    "todo_list",
    "todo_update",
    "todo_visualize",
    "verify_run_lint",
    "verify_run_tests",
    "web_fetch",
    "web_search",
]
