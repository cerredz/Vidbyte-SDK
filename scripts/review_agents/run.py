"""FILE: scripts/review_agents/run.py

PURPOSE: The review-agents workflow's only entry point: `python scripts/review_agents/run.py <step> ...`.
ROLE IN CODEBASE: Each subcommand is one step of .github/workflows/claude-review-agents.yml: collect, plan, prompt, finalize, report, and check, the last a local validation of every committed prompt. sweep is the one step of .github/workflows/claude-review-sweep.yml.
ARCHITECTURE NOTE: Steps hand data to each other through JSON files and GitHub step outputs, never through a model, so the plan, the prompts, the commits, and the report are the same on every run of the same review. The plan step asks git whether the branch conflicts with its base, and a merge task's finalize goes through MergeFinalizer.
COMMON MODIFICATION PATTERNS: A new step adds one parser in ArgumentParserFactory, one method on ReviewAgentsApp, and one entry in the step table in run().
KNOWN EDGE CASES: Outside GitHub Actions step outputs are printed instead of written; an agent's structured output arrives through an environment variable, never the shell, and a malformed one counts as no result.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: tests/test_review_agents.py runs the check step against the committed prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_agents.finalize import FinalizeRequest, TaskFinalizer
from review_agents.github import GhCli, ReviewFetcher
from review_agents.gitops import CommandRunner, Git
from review_agents.merging import MergeFinalizer
from review_agents.planning import PlanBuilder
from review_agents.prompting import AGENT_SCHEMA, PromptBuilder, compact_schema
from review_agents.readmes import ReadmeLocator
from review_agents.registry import AgentRegistry, PromptContractError
from review_agents.report import ReportWriter
from review_agents.review_data import AgentReport, Scope, TaskResult, TaskStatus, plan_from_json, report_from_json, result_from_json, review_from_json, to_json
from review_agents.sweep import ReviewSweeper


class ActionOutputs:
    """Writes GitHub step outputs, or prints them when run outside Actions."""

    def write(self, name: str, value: str) -> None:
        path = os.environ.get("GITHUB_OUTPUT")
        if not path:
            sys.stdout.write(f"{name}={value}\n")
            return
        # A random delimiter, so no value can end the block early.
        delimiter = f"EOF_{uuid.uuid4().hex}"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


class ArgumentParserFactory:
    """Declares one subcommand per workflow step."""

    @staticmethod
    def build() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Steps of the Claude review-agents workflow.")
        steps = parser.add_subparsers(dest="step", required=True)
        collect = steps.add_parser("collect", help="Fetch the review and its comments.")
        collect.add_argument("--repository", required=True)
        collect.add_argument("--pull", type=int, required=True)
        collect.add_argument("--review", type=int, required=True)
        collect.add_argument("--out", type=Path, required=True)
        plan = steps.add_parser("plan", help="Lay out every agent's tasks.")
        plan.add_argument("--review-file", type=Path, required=True)
        plan.add_argument("--agents-dir", type=Path, required=True)
        plan.add_argument("--out", type=Path, required=True)
        prompt = steps.add_parser("prompt", help="Build one task's prompt.")
        prompt.add_argument("--plan-file", type=Path, required=True)
        prompt.add_argument("--agents-dir", type=Path, required=True)
        prompt.add_argument("--task", required=True)
        final = steps.add_parser("finalize", help="Gate, commit, and push one task's edit.")
        final.add_argument("--plan-file", type=Path, required=True)
        final.add_argument("--agents-dir", type=Path, required=True)
        final.add_argument("--task", required=True)
        final.add_argument("--start-sha", required=True)
        final.add_argument("--agent-outcome", required=True)
        final.add_argument("--report-env", default="AGENT_REPORT")
        final.add_argument("--push-remote-env", default="PUSH_REMOTE")
        final.add_argument("--out", type=Path, required=True)
        report = steps.add_parser("report", help="Render the summary comment.")
        report.add_argument("--plan-file", type=Path, required=True)
        report.add_argument("--agents-dir", type=Path, required=True)
        report.add_argument("--results-dir", type=Path, required=True)
        report.add_argument("--out", type=Path, required=True)
        check = steps.add_parser("check", help="Validate every review prompt.")
        check.add_argument("--agents-dir", type=Path, required=True)
        sweep = steps.add_parser("sweep", help="Start the agents for @claude reviews on conflicting pull requests.")
        sweep.add_argument("--repository", action="append", required=True)
        return parser


class ReviewAgentsApp:
    """Runs one workflow step and returns its process status."""

    def __init__(self) -> None:
        self._outputs = ActionOutputs()

    def run(self, argv: list[str] | None = None) -> int:
        args = ArgumentParserFactory.build().parse_args(argv)
        step = {"collect": self.collect, "plan": self.plan, "prompt": self.prompt, "finalize": self.finalize, "report": self.report, "check": self.check, "sweep": self.sweep}[args.step]
        try:
            return step(args)
        except PromptContractError as error:
            sys.stderr.write(f"Review prompt problem: {error}\n")
            return 2

    def collect(self, args: argparse.Namespace) -> int:
        # Ask GitHub, not a model, which comments this round of review contains.
        review = ReviewFetcher(GhCli()).fetch(args.repository, args.pull, args.review)
        _write_json(args.out, to_json(review))
        self._outputs.write("head_ref", review.head_ref)
        self._outputs.write("base_ref", review.base_ref)
        return 0

    def plan(self, args: argparse.Namespace) -> int:
        # Ask git whether the branch conflicts with its base, which decides if the merge agent runs.
        review = review_from_json(_read_json(args.review_file))
        conflicts = Git(Path.cwd()).merge_preview(f"origin/{review.base_ref}", f"origin/{review.head_ref}").conflicts
        # Load every agent, then lay out its runs over the round's comments and conflicts.
        agents = AgentRegistry(args.agents_dir).load()
        plan = PlanBuilder().build(review, agents, conflicts)
        _write_json(args.out, to_json(plan))
        # The matrix needs each task's ID, a readable job name, and whether to start a merge first.
        matrix = [{"id": task.id, "title": task.title, "merge": task.scope is Scope.MERGE} for task in plan.tasks]
        self._outputs.write("tasks", json.dumps(matrix, ensure_ascii=False))
        self._outputs.write("task_count", str(len(plan.tasks)))
        return 0

    def prompt(self, args: argparse.Namespace) -> int:
        plan = plan_from_json(_read_json(args.plan_file))
        task = plan.task(args.task)
        agent = next(spec for spec in AgentRegistry(args.agents_dir).load() if spec.name == task.agent)
        # Earlier runs' commits come from the branch itself, read through their trailers.
        review = plan.review
        pushed = Git(Path.cwd()).review_commits(f"origin/{review.base_ref}", review.review_id)
        # Each comment's folder README, found on the branch as earlier runs left it.
        readmes = ReadmeLocator(Path.cwd()).for_review(review)
        text = PromptBuilder().agent_prompt(plan, task, agent, pushed, readmes)
        self._outputs.write("text", text)
        self._outputs.write("schema", compact_schema(AGENT_SCHEMA))
        return 0

    def finalize(self, args: argparse.Namespace) -> int:
        plan = plan_from_json(_read_json(args.plan_file))
        task = plan.task(args.task)
        agent = next(spec for spec in AgentRegistry(args.agents_dir).load() if spec.name == task.agent)
        # The agent's structured output arrives through the environment, never the shell.
        request = FinalizeRequest(plan=plan, task=task, agent=agent, report=_agent_report(os.environ.get(args.report_env, "")), agent_succeeded=args.agent_outcome == "success", start_sha=args.start_sha, push_remote=os.environ.get(args.push_remote_env, ""))
        # A merge lands as a two-parent merge commit; every other task as one ordinary commit.
        finalizer = MergeFinalizer if task.scope is Scope.MERGE else TaskFinalizer
        result = finalizer(Git(Path.cwd()), CommandRunner()).finalize(request)
        _write_json(args.out, to_json(result))
        sys.stdout.write(f"{task.id}: {result.status.value}\n{result.detail}\n")
        return 1 if result.status is TaskStatus.FAILED else 0

    def report(self, args: argparse.Namespace) -> int:
        plan = plan_from_json(_read_json(args.plan_file))
        agents = AgentRegistry(args.agents_dir).load()
        results = _read_results(args.results_dir)
        # The merge agent owns no comments, so it gets a line of its own rather than a table column.
        columns = tuple(agent.name for agent in agents if agent.scope is not Scope.MERGE)
        body, ok = ReportWriter().render(plan, columns, results)
        args.out.write_text(body, encoding="utf-8")
        return 0 if ok else 1

    def check(self, args: argparse.Namespace) -> int:
        agents = AgentRegistry(args.agents_dir).load()
        names = ", ".join(f"{agent.order:02d}-{agent.name} ({agent.scope.value})" for agent in agents)
        sys.stdout.write(f"Review prompts are valid: {names}\n")
        return 0

    def sweep(self, args: argparse.Namespace) -> int:
        # One repository failing, such as one the token cannot read, must not stop the others.
        sweeper, failed = ReviewSweeper(GhCli()), 0
        for repository in args.repository:
            try:
                started = sweeper.sweep(repository)
            except (subprocess.CalledProcessError, KeyError, TypeError, ValueError) as error:
                failed += 1
                detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else repr(error)
                sys.stderr.write(f"{repository}: sweep failed: {detail}\n")
                continue
            sys.stdout.write("".join(f"{repository}#{dispatch.pull_number}: started the agents for review {dispatch.review_id}\n" for dispatch in started) or f"{repository}: nothing to start\n")
        return 1 if failed else 0


def _read_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _agent_report(raw: str) -> AgentReport | None:
    # A missing or malformed result is the same as no result: finalize then pushes nothing.
    try:
        return report_from_json(json.loads(raw))
    except (ValueError, KeyError, TypeError):
        return None


def _read_results(directory: Path) -> dict[str, TaskResult]:
    results = (result_from_json(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(directory.rglob("*.json")))
    return {result.task_id: result for result in results}


if __name__ == "__main__":
    raise SystemExit(ReviewAgentsApp().run())
