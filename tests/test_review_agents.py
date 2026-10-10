"""FILE: tests/test_review_agents.py

PURPOSE: Prove the @claude review-agents workflow's helpers in scripts/review_agents/ collect each round, plan, prompt, gate, commit, merge, verify, report, and sweep the way the workflow relies on, and that lint rule A009 bounds the folder READMEs its notes writer edits.
ROLE IN CODEBASE: The offline spec for .github/workflows/claude-review-agents.yml and claude-review-sweep.yml; it loads the committed prompts in .github/prompts/review-agents/ and pins what the reviewer asked of each one.
ARCHITECTURE NOTE: GitHub is a fake reader, no model runs, and the finalize and merge cases commit and push to a bare repository under tmp_path, never to a real remote; scripts/ is put on sys.path because the workflow runs these tools without installing the SDK.
COMMON MODIFICATION PATTERNS: A new prompt or scope adds a case here next to the registry ones; a new finalize refusal gets a case that also proves nothing reached the remote.
KNOWN EDGE CASES: Test commits need a git identity, so the finalize fixture sets one through monkeypatch; the workflow's own commits set theirs explicitly.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from lint.core.discovery import SourceCatalog
from lint.rules.a009_readme_size_limit import RULE as README_SIZE_RULE

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from review_agents.finalize import FinalizeRequest, TaskFinalizer
from review_agents.github import ROUND_MARKER, ReviewFetcher
from review_agents.gitops import CommandRunner, Git
from review_agents.merging import MergeFinalizer
from review_agents.planning import PlanBuilder
from review_agents.prompting import AGENT_SCHEMA, PromptBuilder, compact_schema
from review_agents.readmes import ReadmeLocator
from review_agents.registry import AgentRegistry, PromptContractError
from review_agents.report import ReportWriter
from review_agents.review_data import AgentReport, AgentSpec, BiteVerdict, Review, ReviewComment, Scope, TaskResult, TaskStatus, plan_from_json, to_json
from review_agents.sweep import RUN_NAME, ReviewSweeper

_AGENTS_DIR = _ROOT / ".github" / "prompts" / "review-agents"
_WORKFLOWS = _ROOT / ".github" / "workflows"
_SHA = "a" * 40
_THROUGH = "2026-10-10T06:26:37Z"
_PASS = (sys.executable, "-c", "raise SystemExit(0)")
_FAIL = (sys.executable, "-c", "raise SystemExit(1)")


def _comment(comment_id: int, body: str = "Fix this.", path: str | None = "app.txt") -> ReviewComment:
    return ReviewComment(comment_id, body, path, 1 if path else None, "", "@@ -1 +1 @@", None)


def _review(*comments: ReviewComment, sha: str = _SHA) -> Review:
    return Review("o/r", 1, 77, sha, "feat", "main", "", comments, "", _THROUGH)


def _agent(name: str, order: int, scope: Scope, guard: bool = False) -> AgentSpec:
    return AgentSpec(name, order, scope, guard, f"{order:02d}-{name}.md", f"# {name}\n")


# The committed prompts


def test_real_prompts_run_resolver_then_preventer_per_comment_then_notes_writer() -> None:
    agents = AgentRegistry(_AGENTS_DIR).load()
    assert [(spec.name, spec.scope, spec.guard) for spec in agents] == [("merge-conflicts", Scope.MERGE, False), ("resolver", Scope.REVIEW, False), ("preventer", Scope.COMMENT, True), ("readme-notes", Scope.REVIEW, False)]
    plan = PlanBuilder().build(_review(_comment(1), _comment(2)), agents, ())
    # Without conflicts no merge runs; the resolver owns every comment first and the notes writer every comment last.
    assert [(task.id, task.comment_ids) for task in plan.tasks] == [("10-resolver-review", (1, 2)), ("20-preventer-c1", (1,)), ("20-preventer-c2", (2,)), ("30-readme-notes-review", (1, 2))]
    assert all("scope:" not in spec.body for spec in agents)


def test_a_conflicting_branch_is_merged_before_any_comment_is_handled() -> None:
    agents = AgentRegistry(_AGENTS_DIR).load()
    plan = PlanBuilder().build(_review(_comment(1)), agents, ("app.txt",))
    assert [(task.id, task.scope, task.comment_ids) for task in plan.tasks][:2] == [("05-merge-conflicts-merge", Scope.MERGE, ()), ("10-resolver-review", Scope.REVIEW, (1,))]
    # A conflicted branch is merged even when the round holds no comments.
    assert [task.id for task in PlanBuilder().build(_review(), agents, ("app.txt",)).tasks] == ["05-merge-conflicts-merge"]
    # The merge prompt lists the conflicted files and leaves the comments to the runs after it.
    merge = PromptBuilder().agent_prompt(plan, plan.tasks[0], agents[0], (), {})
    assert merge.startswith("# Merge Conflict Resolver")
    assert "- `app.txt`" in merge
    assert "- 1 at app.txt:1: Fix this." in merge
    assert "#### Comment 1" not in merge


def test_merge_resolver_settles_both_sides_and_never_commits() -> None:
    merge = _bodies()["merge-conflicts"]
    assert "combining both sides' intent" in merge
    assert "do not commit or push" in merge
    assert "python scripts/run_ci.py" in merge


def test_resolver_groups_comments_checks_its_fixes_and_runs_the_gate() -> None:
    resolver = _bodies()["resolver"]
    assert "Group the comments before you edit anything" in resolver
    assert "Check that every fix is accurate" in resolver
    assert "Check that every fix meets this repository's standards" in resolver
    commands = ("python lint/run.py", "python -m compileall -q vidbyte", "semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte", "python -m pytest", "python scripts/run_ci.py")
    assert [command for command in commands if command not in resolver] == []


def test_preventer_catalogs_every_kind_of_test_and_the_other_guards() -> None:
    preventer = _bodies()["preventer"]
    assert "## Prevention mechanisms" in preventer
    rungs = ("### Rung (a)", "### Rung (b)", "### Rung (c)", "### Rung (d)")
    assert [rung for rung in rungs if rung not in preventer] == []
    kinds = ("Unit test", "Integration test", "End-to-end test", "Acceptance test", "Regression test", "Property-based test", "Mutation test", "Packaging and install test")
    assert [kind for kind in kinds if f"**{kind}.**" not in preventer] == []


def test_notes_writer_notes_carry_no_links() -> None:
    notes = _bodies()["readme-notes"]
    assert "http" not in notes
    assert "no links" in notes


def test_agents_can_never_push() -> None:
    settings = json.loads((_ROOT / ".claude" / "ci-settings.json").read_text(encoding="utf-8"))
    assert {"Bash(git push)", "Bash(git push *)"} <= set(settings["permissions"]["deny"])


def _bodies() -> dict[str, str]:
    return {spec.name: spec.body for spec in AgentRegistry(_AGENTS_DIR).load()}


# The prompt contract


def _valid_prompt(first_step: str = "Read `AGENTS.md` first.") -> str:
    filler = " ".join(["This sentence gives the section the depth the contract asks for."] * 8)
    steps = "\n".join(f"{number}. {first_step if number == 1 else filler}" for number in range(1, 5))
    sections = "\n\n".join(f"## {title}\n\n{steps if title == 'Instructions' else filler}" for title in ("Goal", "Objective", "Instructions", "Constraints", "Output"))
    return f"# Title\n\n{sections}\n"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        pytest.param("10-a.md", _valid_prompt().replace("## Output", "## Result"), id="missing-section"),
        pytest.param("10-a.md", "---\nscope: file\n---\n" + _valid_prompt(), id="unknown-scope"),
        pytest.param("10-a.md", "---\nscope: group\n---\n" + _valid_prompt(), id="retired-group-scope"),
        pytest.param("10-a.md", "---\nmodel: x\n---\n" + _valid_prompt(), id="unknown-frontmatter-field"),
        pytest.param("10-a.md", _valid_prompt("Start working."), id="first-step-skips-agents-md"),
        pytest.param("resolver.md", _valid_prompt(), id="not-named-nn-name"),
    ],
)
def test_registry_rejects_a_broken_prompt(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")
    with pytest.raises(PromptContractError):
        AgentRegistry(tmp_path).load()


def test_registry_rejects_two_agents_with_one_number(tmp_path: Path) -> None:
    for name in ("10-a.md", "10-b.md"):
        (tmp_path / name).write_text(_valid_prompt(), encoding="utf-8")
    with pytest.raises(PromptContractError):
        AgentRegistry(tmp_path).load()


def test_a_new_agent_needs_only_its_file_and_defaults_to_one_run_per_review(tmp_path: Path) -> None:
    (tmp_path / "30-docs.md").write_text("---\nscope: review\n---\n" + _valid_prompt(), encoding="utf-8")
    (tmp_path / "40-plain.md").write_text(_valid_prompt(), encoding="utf-8")
    loaded = AgentRegistry(tmp_path).load()
    assert [(spec.name, spec.order, spec.scope) for spec in loaded] == [("docs", 30, Scope.REVIEW), ("plain", 40, Scope.REVIEW)]


# Planning


def test_tasks_follow_agent_order_then_units_and_survive_json() -> None:
    agents = (_agent("preventer", 20, Scope.COMMENT, guard=True), _agent("resolver", 10, Scope.REVIEW), _agent("docs", 30, Scope.REVIEW), _agent("merge", 5, Scope.MERGE))
    plan = PlanBuilder().build(_review(_comment(1), _comment(2)), agents, ("a.py",))
    assert [task.id for task in plan.tasks] == ["05-merge-merge", "10-resolver-review", "20-preventer-c1", "20-preventer-c2", "30-docs-review"]
    # The plan crosses from the plan job to every agent leg as JSON.
    assert plan_from_json(json.loads(json.dumps(to_json(plan)))) == plan
    assert PlanBuilder().build(_review(), agents, ()).tasks == ()


# Reading GitHub


@dataclass(frozen=True)
class _FakeReader:
    responses: dict[str, Any]

    def get(self, path: str) -> dict[str, Any]:
        result: dict[str, Any] = self.responses[path]
        return result

    def list(self, path: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self.responses[path]
        return result


def _raw_review(review_id: int, at: str, body: str = "", association: str = "OWNER", kind: str = "User") -> dict[str, Any]:
    return {"id": review_id, "body": body, "commit_id": _SHA, "html_url": f"u{review_id}", "submitted_at": at, "author_association": association, "user": {"login": "someone", "type": kind}}


def _github(trigger_body: str, comments: list[dict[str, Any]], reviews: tuple[dict[str, Any], ...] = (), issue_comments: tuple[dict[str, Any], ...] = (), association: str = "OWNER") -> _FakeReader:
    base = "repos/o/r/pulls/4"
    trigger = _raw_review(77, _THROUGH, trigger_body, association)
    return _FakeReader({base: {"head": {"ref": "feat"}, "base": {"ref": "main"}}, f"{base}/reviews/77": trigger, f"{base}/reviews": [*reviews, trigger], f"{base}/comments": comments, "repos/o/r/issues/4/comments": list(issue_comments)})


def _marker(through: str, login: str = "github-actions[bot]") -> dict[str, Any]:
    return {"body": "## Claude review agents\n\n" + ROUND_MARKER.format(through=through), "user": {"login": login}}


def test_a_round_holds_every_single_comment_review_since_the_last_clean_round() -> None:
    # "Add single comment" makes each comment its own review, and the @claude review holds none.
    reviews = (_raw_review(60, "2026-10-10T05:00:00Z"), _raw_review(61, "2026-10-10T06:22:57Z"), _raw_review(62, "2026-10-10T06:25:15Z", "Also log it."))
    raw = [
        {"id": 5, "body": "Old thread.", "pull_request_review_id": 60, "path": "a.py", "line": 3},
        {"id": 6, "body": "Still wrong.", "pull_request_review_id": 61, "path": "a.py", "line": None, "original_line": 3, "in_reply_to_id": 5, "diff_hunk": "@@"},
        {"id": 7, "body": "Rename it.", "pull_request_review_id": 62, "path": "b.py", "line": 9},
    ]
    fetched = ReviewFetcher(_github("@claude please", raw, reviews, (_marker("2026-10-10T05:30:00Z"),))).fetch("o/r", 4, 77)
    # Comment 5 belongs to the round that already finished; a summary on another review is a request of its own.
    assert [comment.id for comment in fetched.comments] == [6, 7, 62]
    assert fetched.comments[-1].body == "Also log it."
    assert (fetched.summary, fetched.since, fetched.through) == ("please", "2026-10-10T05:30:00Z", _THROUGH)
    # A reply carries the comment it answers, and an outdated one keeps its original line.
    assert fetched.comments[0].parent_body == "Old thread."
    assert fetched.comments[0].line == 3


def test_a_round_ignores_bots_people_without_write_access_and_forged_markers() -> None:
    reviews = (_raw_review(60, "2026-10-10T06:00:00Z", association="NONE"), _raw_review(61, "2026-10-10T06:01:00Z", kind="Bot"), _raw_review(62, "2026-10-10T06:02:00Z"))
    raw = [{"id": number, "body": "Do it.", "pull_request_review_id": review, "path": "a.py", "line": 1} for number, review in ((5, 60), (6, 61), (7, 62))]
    # Only the workflow's own comment can end a round, so a forged marker moves nothing.
    fetched = ReviewFetcher(_github("@claude", raw, reviews, (_marker("2026-10-10T06:10:00Z", login="mallory"),))).fetch("o/r", 4, 77)
    assert [comment.id for comment in fetched.comments] == [7]
    with pytest.raises(ValueError, match="write access"):
        ReviewFetcher(_github("@claude", [], association="CONTRIBUTOR")).fetch("o/r", 4, 77)


def test_a_summary_only_round_becomes_one_comment() -> None:
    fetched = ReviewFetcher(_github("@CLAUDE rename x", [])).fetch("o/r", 4, 77)
    assert [(comment.id, comment.body, comment.path) for comment in fetched.comments] == [(77, "rename x", None)]
    # A review that a clean round already covered starts an empty round, not a repeat.
    again = ReviewFetcher(_github("@claude rename x", [], issue_comments=(_marker(_THROUGH),))).fetch("o/r", 4, 77)
    assert again.comments == ()


# Building prompts


def test_the_resolver_prompt_holds_every_comment_to_group_itself() -> None:
    agents = AgentRegistry(_AGENTS_DIR).load()
    plan = PlanBuilder().build(_review(_comment(1, "Use a logger."), _comment(2, "Rename this.", "b.py")), agents, ())
    specs = {spec.name: spec for spec in agents}
    text = PromptBuilder().agent_prompt(plan, plan.tasks[0], specs["resolver"], (), {1: "pkg/README.md"})
    assert text.startswith("# Review Comment Resolver")
    assert "Folder README: `pkg/README.md`" in text
    assert _SHA in text
    assert "#### Comment 1 at app.txt:1" in text
    assert "#### Comment 2 at b.py:1" in text
    assert "handled by other runs\n\nNone." in text


def test_a_per_comment_prompt_lists_the_other_comments_out_of_scope() -> None:
    agents = AgentRegistry(_AGENTS_DIR).load()
    plan = PlanBuilder().build(_review(_comment(1, "Use a logger."), _comment(2, "Rename this.", "b.py")), agents, ())
    specs = {spec.name: spec for spec in agents}
    text = PromptBuilder().agent_prompt(plan, plan.tasks[1], specs["preventer"], (), {})
    assert "#### Comment 1 at app.txt:1" in text
    assert "- 2 at b.py:1: Rename this." in text
    assert "#### Comment 2" not in text


def test_a_comment_without_a_file_says_why_it_has_no_readme() -> None:
    agents = AgentRegistry(_AGENTS_DIR).load()
    plan = PlanBuilder().build(_review(_comment(5, path=None)), agents, ())
    notes_task = plan.tasks[-1]
    spec = next(agent for agent in agents if agent.name == notes_task.agent)
    text = PromptBuilder().agent_prompt(plan, notes_task, spec, (), {})
    assert "Folder README: none, because this comment is not on a file." in text


def test_the_agent_schema_survives_single_quotes_in_claude_args() -> None:
    schema = compact_schema(AGENT_SCHEMA)
    assert "'" not in schema
    assert json.loads(schema) == AGENT_SCHEMA


# Folder READMEs


def test_readme_locator_walks_up_but_never_returns_the_root_readme(tmp_path: Path) -> None:
    (tmp_path / "pkg" / "deep" / "deeper").mkdir(parents=True)
    (tmp_path / "bare").mkdir()
    for readme in ("README.md", "pkg/README.md", "pkg/deep/README.md"):
        (tmp_path / readme).write_text("# Folder\n", encoding="utf-8")
    locator = ReadmeLocator(tmp_path)
    assert locator.nearest("pkg/deep/a.py") == "pkg/deep/README.md"
    assert locator.nearest("pkg/deep/deeper/b.py") == "pkg/deep/README.md"
    # The root README is the package's PyPI page, which the notes writer never edits.
    assert locator.nearest("bare/c.py") is None
    assert locator.nearest("top.py") is None
    found = locator.for_review(_review(_comment(1, path="pkg/x.py"), _comment(2, path="top.py"), _comment(3, path=None)))
    assert found == {1: "pkg/README.md"}


# Finalize, against real git repositories


@dataclass(frozen=True)
class _Fixture:
    root: Path
    work: Path
    remote: Path
    review: Review


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {arguments} failed: {result.stderr}")
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Fixture:
    # A bare remote, a main branch, and a feature branch that introduces the reviewed defect.
    for key, value in (("GIT_AUTHOR_NAME", "spec"), ("GIT_COMMITTER_NAME", "spec"), ("GIT_AUTHOR_EMAIL", "spec@example.invalid"), ("GIT_COMMITTER_EMAIL", "spec@example.invalid")):
        monkeypatch.setenv(key, value)
    remote, seed, work = tmp_path / "remote.git", tmp_path / "seed", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    (seed / "app.txt").write_text("ok\n", encoding="utf-8")
    (seed / ".claude").mkdir()
    (seed / ".claude" / "ci-settings.json").write_text("{}\n", encoding="utf-8")
    (seed / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "base")
    _git(seed, "push", "-q", str(remote), "main")
    (seed / "app.txt").write_text("BUG\n", encoding="utf-8")
    _git(seed, "commit", "-q", "-am", "feature with a bug")
    _git(seed, "push", "-q", str(remote), "HEAD:refs/heads/feat")
    _git(tmp_path, "clone", "-q", str(remote), str(work))
    _git(work, "checkout", "-q", "-B", "feat", "origin/feat")
    reviewed = _git(work, "rev-parse", "HEAD")
    return _Fixture(tmp_path, work, remote, _review(_comment(1001, "No BUG here."), sha=reviewed))


def _finalize(repo: _Fixture, task_index: int, report: AgentReport | None, gate: tuple[str, ...] = _PASS, succeeded: bool = True, start: str | None = None) -> TaskResult:
    agents = (_agent("resolver", 10, Scope.REVIEW), _agent("preventer", 20, Scope.COMMENT, True))
    plan = PlanBuilder().build(repo.review, agents, ())
    task = plan.tasks[task_index]
    spec = next(agent for agent in agents if agent.name == task.agent)
    request = FinalizeRequest(plan=plan, task=task, agent=spec, report=report, agent_succeeded=succeeded, start_sha=start or _git(repo.work, "rev-parse", "HEAD"), push_remote=str(repo.remote), gate=gate)
    return TaskFinalizer(Git(repo.work), CommandRunner()).finalize(request)


def _changed(summary: str, check: str = "") -> AgentReport:
    return AgentReport(TaskStatus.CHANGED, "fix(app): remove the bug", summary, check)


def _remote_head(repo: _Fixture) -> str:
    return _git(repo.work, "--git-dir", str(repo.remote), "rev-parse", "refs/heads/feat")


def _resolve(repo: _Fixture) -> TaskResult:
    (repo.work / "app.txt").write_text("ok\n", encoding="utf-8")
    return _finalize(repo, 0, _changed("Removed the bug."))


def test_a_passing_fix_is_committed_with_trailers_and_pushed(repo: _Fixture) -> None:
    # The agent also leaves edits to config the action restored from the base branch.
    (repo.work / "CLAUDE.md").write_text("tampered\n", encoding="utf-8")
    (repo.work / ".claude-pr").mkdir()
    (repo.work / ".claude-pr" / "copy.md").write_text("x\n", encoding="utf-8")
    result = _resolve(repo)
    assert result.status is TaskStatus.CHANGED, result.detail
    assert _remote_head(repo) == result.commit_sha
    message = _git(repo.work, "log", "-1", "--format=%B")
    assert "Claude-Review: 77" in message
    assert "Claude-Review-Comments: 1001" in message
    # Restored config is never committed, and is put back in the working tree.
    assert _git(repo.work, "show", "--name-only", "--format=", "HEAD").splitlines() == ["app.txt"]
    assert (repo.work / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"
    assert not (repo.work / ".claude-pr").exists()


def test_a_guard_that_fails_with_the_fix_reverted_is_verified_and_kept(repo: _Fixture) -> None:
    _resolve(repo)
    detector = "import pathlib, sys; sys.exit('BUG' in pathlib.Path('app.txt').read_text())"
    (repo.work / "guard.py").write_text(detector + "\n", encoding="utf-8")
    verified = _finalize(repo, 1, _changed("Added a guard.", f'"{sys.executable}" guard.py'))
    assert verified.status is TaskStatus.CHANGED, verified.detail
    assert verified.bite is BiteVerdict.VERIFIED
    assert (repo.work / "guard.py").exists()


def test_a_guard_that_misses_the_original_problem_is_never_pushed(repo: _Fixture) -> None:
    _resolve(repo)
    start = _git(repo.work, "rev-parse", "HEAD")
    (repo.work / "weak.py").write_text("pass\n", encoding="utf-8")
    weak = _finalize(repo, 1, _changed("Weak.", f'"{sys.executable}" weak.py'))
    assert weak.status is TaskStatus.FAILED, weak.detail
    assert weak.bite is BiteVerdict.NOT_CAUGHT
    assert _remote_head(repo) == start


def test_a_guard_that_fails_on_fixed_code_is_rejected(repo: _Fixture) -> None:
    _resolve(repo)
    (repo.work / "noisy.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    noisy = _finalize(repo, 1, _changed("Noisy.", f'"{sys.executable}" noisy.py'))
    assert noisy.bite is BiteVerdict.ALWAYS_FAILS


def test_finalize_refuses_empty_red_crashed_and_workflow_edits(repo: _Fixture) -> None:
    start = _git(repo.work, "rev-parse", "HEAD")
    # No edits means no commit, even when the agent claims a change.
    nothing = _finalize(repo, 0, _changed("Thought about it."))
    assert nothing.status is TaskStatus.NO_CHANGE
    assert nothing.detail != ""
    (repo.work / "app.txt").write_text("broken\n", encoding="utf-8")
    red = _finalize(repo, 0, _changed("Broke it."), gate=_FAIL)
    assert red.status is TaskStatus.FAILED
    assert "gate" in red.detail
    _git(repo.work, "reset", "-q", "--hard", start)
    (repo.work / "app.txt").write_text("edited\n", encoding="utf-8")
    crashed = _finalize(repo, 0, None, succeeded=False)
    assert crashed.status is TaskStatus.FAILED
    _git(repo.work, "reset", "-q", "--hard", start)
    (repo.work / ".github" / "workflows").mkdir(parents=True)
    (repo.work / ".github" / "workflows" / "x.yml").write_text("on: push\n", encoding="utf-8")
    workflow = _finalize(repo, 0, _changed("Edited CI."))
    assert workflow.status is TaskStatus.FAILED, workflow.detail
    assert _remote_head(repo) == start


def test_an_agents_own_commits_are_folded_into_one(repo: _Fixture) -> None:
    start = _git(repo.work, "rev-parse", "HEAD")
    for name in ("one.txt", "two.txt"):
        (repo.work / name).write_text(name, encoding="utf-8")
        _git(repo.work, "add", name)
        _git(repo.work, "commit", "-q", "-m", f"agent {name}")
    folded = _finalize(repo, 0, _changed("Two files."), start=start)
    assert folded.status is TaskStatus.CHANGED, folded.detail
    assert _git(repo.work, "rev-parse", "HEAD~1") == start


def test_a_push_race_is_resolved_by_replaying_on_top(repo: _Fixture) -> None:
    # Someone pushes to the branch while the agent runs.
    other = repo.root / "other"
    _git(repo.root, "clone", "-q", "-b", "feat", str(repo.remote), str(other))
    (other / "theirs.txt").write_text("theirs\n", encoding="utf-8")
    _git(other, "add", "theirs.txt")
    _git(other, "commit", "-q", "-m", "a human push")
    _git(other, "push", "-q", "origin", "feat")
    (repo.work / "mine.txt").write_text("mine\n", encoding="utf-8")
    rebased = _finalize(repo, 0, _changed("Mine."))
    assert rebased.status is TaskStatus.CHANGED, rebased.detail
    remote_files = _git(repo.work, "--git-dir", str(repo.remote), "ls-tree", "--name-only", "refs/heads/feat").split()
    assert "theirs.txt" in remote_files
    assert "mine.txt" in remote_files


# Merging the base branch, against real git repositories


def _diverge(repo: _Fixture) -> str:
    # The base branch changes the line the feature changed, adds a file, and changes restored config.
    other = repo.root / "main-side"
    _git(repo.root, "clone", "-q", "-b", "main", str(repo.remote), str(other))
    (other / "app.txt").write_text("main\n", encoding="utf-8")
    (other / "lib.txt").write_text("from main\n", encoding="utf-8")
    (other / ".claude" / "ci-settings.json").write_text('{"from": "main"}\n', encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "main moves on")
    _git(other, "push", "-q", "origin", "main")
    _git(repo.work, "fetch", "-q", "origin")
    return _git(repo.work, "rev-parse", "origin/main")


def _start_merge(repo: _Fixture) -> str:
    # What the workflow's "Start merging the base branch" step does before the agent runs.
    start = _git(repo.work, "rev-parse", "HEAD")
    subprocess.run(["git", "merge", "--no-commit", "--no-ff", "origin/main"], cwd=repo.work, capture_output=True, check=False)
    return start


def _finalize_merge(repo: _Fixture, start: str, report: AgentReport | None) -> TaskResult:
    agent = _agent("merge-conflicts", 5, Scope.MERGE)
    plan = PlanBuilder().build(_review(sha=start), (agent,), ("app.txt",))
    request = FinalizeRequest(plan=plan, task=plan.tasks[0], agent=agent, report=report, agent_succeeded=True, start_sha=start, push_remote=str(repo.remote), gate=_PASS)
    return MergeFinalizer(Git(repo.work), CommandRunner()).finalize(request)


def _merged(summary: str) -> AgentReport:
    return AgentReport(TaskStatus.CHANGED, "chore(merge): merge main into feat", summary, "")


def test_git_previews_the_conflicts_without_touching_the_checkout(repo: _Fixture) -> None:
    _diverge(repo)
    preview = Git(repo.work).merge_preview("origin/main", "HEAD")
    assert preview.conflicts == ("app.txt",)
    assert _git(repo.work, "status", "--porcelain") == ""
    assert Git(repo.work).merge_preview("origin/main", "origin/main").conflicts == ()


def test_a_settled_merge_is_pushed_as_a_two_parent_merge_commit(repo: _Fixture) -> None:
    base = _diverge(repo)
    start = _start_merge(repo)
    # The agent settles the conflict, and the action had swapped restored config for other copies.
    (repo.work / "app.txt").write_text("main and ok\n", encoding="utf-8")
    (repo.work / "CLAUDE.md").write_text("tampered\n", encoding="utf-8")
    (repo.work / ".claude" / "ci-settings.json").write_text("tampered\n", encoding="utf-8")
    result = _finalize_merge(repo, start, _merged("Kept both sides."))
    assert result.status is TaskStatus.CHANGED, result.detail
    assert _remote_head(repo) == result.commit_sha
    assert _git(repo.work, "rev-parse", "HEAD^1", "HEAD^2").split() == [start, base]
    assert _git(repo.work, "show", "HEAD:app.txt") == "main and ok"
    assert _git(repo.work, "show", "HEAD:lib.txt") == "from main"
    # Restored config comes back as the clean merge holds it, keeping the base branch's change.
    assert _git(repo.work, "show", "HEAD:CLAUDE.md") == "@AGENTS.md"
    assert _git(repo.work, "show", "HEAD:.claude/ci-settings.json") == '{"from": "main"}'
    assert "Claude-Review-Agent: merge-conflicts" in _git(repo.work, "log", "-1", "--format=%B")


def test_a_merge_the_agent_committed_itself_still_keeps_both_parents(repo: _Fixture) -> None:
    base = _diverge(repo)
    start = _start_merge(repo)
    (repo.work / "app.txt").write_text("settled\n", encoding="utf-8")
    _git(repo.work, "commit", "-q", "-am", "agent merge")
    result = _finalize_merge(repo, start, _merged("Settled."))
    assert result.status is TaskStatus.CHANGED, result.detail
    assert _git(repo.work, "rev-parse", "HEAD^1", "HEAD^2").split() == [start, base]


def test_a_merge_with_markers_left_or_a_moved_branch_is_never_pushed(repo: _Fixture) -> None:
    _diverge(repo)
    start = _start_merge(repo)
    # The agent claims success but leaves git's conflict markers in place.
    unsettled = _finalize_merge(repo, start, _merged("Done."))
    assert unsettled.status is TaskStatus.FAILED
    assert "Conflict markers remain in app.txt" in unsettled.detail
    assert _remote_head(repo) == start
    # Someone pushes while the agent works: a merge is never replayed, because that would flatten it.
    other = repo.root / "other"
    _git(repo.root, "clone", "-q", "-b", "feat", str(repo.remote), str(other))
    (other / "theirs.txt").write_text("theirs\n", encoding="utf-8")
    _git(other, "add", "theirs.txt")
    _git(other, "commit", "-q", "-m", "a human push")
    _git(other, "push", "-q", "origin", "feat")
    (repo.work / "app.txt").write_text("settled\n", encoding="utf-8")
    raced = _finalize_merge(repo, start, _merged("Settled."))
    assert raced.status is TaskStatus.FAILED
    assert "rejected" in raced.detail
    assert _remote_head(repo) == _git(other, "rev-parse", "HEAD")


def test_a_merge_may_not_edit_workflow_files_the_base_branch_left_alone(repo: _Fixture) -> None:
    _diverge(repo)
    start = _start_merge(repo)
    (repo.work / "app.txt").write_text("settled\n", encoding="utf-8")
    (repo.work / ".github" / "workflows").mkdir(parents=True)
    (repo.work / ".github" / "workflows" / "x.yml").write_text("on: push\n", encoding="utf-8")
    refused = _finalize_merge(repo, start, _merged("Also edited CI."))
    assert refused.status is TaskStatus.FAILED
    assert ".github/workflows/x.yml" in refused.detail
    assert _remote_head(repo) == start


# The summary comment


def test_the_report_shows_one_row_per_comment_and_fails_on_missing_results() -> None:
    agents = (_agent("resolver", 10, Scope.REVIEW), _agent("preventer", 20, Scope.COMMENT, True))
    plan = PlanBuilder().build(_review(_comment(1), _comment(2)), agents, ())
    done = {
        "10-resolver-review": TaskResult("10-resolver-review", TaskStatus.CHANGED, "Fixed.", "b" * 40, BiteVerdict.NOT_APPLICABLE, ""),
        "20-preventer-c1": TaskResult("20-preventer-c1", TaskStatus.CHANGED, "Guarded.", "c" * 40, BiteVerdict.VERIFIED, ""),
    }
    body, ok = ReportWriter().render(plan, ("resolver", "preventer"), done)
    assert "on commit `aaaaaaaaaaaa`: 2 comment(s) left since the pull request opened." in body
    assert "| Comment | resolver | preventer |" in body
    assert "guard verified" in body
    # A task that never reported is shown as failed and fails the report.
    assert body.count("did not report") >= 2
    assert not ok
    # A round that failed leaves no marker, so the next @claude review covers its comments again.
    assert "claude-review-agents through=" not in body


def test_a_clean_round_with_a_merge_reports_it_first_and_ends_with_the_marker() -> None:
    agents = (_agent("merge-conflicts", 5, Scope.MERGE), _agent("resolver", 10, Scope.REVIEW))
    plan = PlanBuilder().build(_review(_comment(1)), agents, ("app.txt", "b.py"))
    done = {
        "05-merge-conflicts-merge": TaskResult("05-merge-conflicts-merge", TaskStatus.CHANGED, "Merged.", "d" * 40, BiteVerdict.NOT_APPLICABLE, ""),
        "10-resolver-review": TaskResult("10-resolver-review", TaskStatus.CHANGED, "Fixed.", "b" * 40, BiteVerdict.NOT_APPLICABLE, ""),
    }
    body, ok = ReportWriter().render(plan, ("resolver",), done)
    assert ok
    assert "Merge of `main`, 2 conflicted file(s): ✅ changed `ddddddd`" in body
    assert body.index("Merge of `main`") < body.index("| Comment | resolver |")
    assert body.rstrip().endswith(ROUND_MARKER.format(through=_THROUGH))


def test_an_empty_review_reports_that_and_passes() -> None:
    agents = (_agent("resolver", 10, Scope.REVIEW),)
    body, ok = ReportWriter().render(PlanBuilder().build(_review(), agents, ()), (), {})
    assert "no new comments" in body
    assert ok


# The sweep for reviews on conflicting pull requests


@dataclass
class _FakeSweepGitHub:
    pulls: list[dict[str, Any]]
    run_titles: list[str]
    posted: list[tuple[str, dict[str, Any]]]

    def get(self, path: str) -> dict[str, Any]:
        assert path == "repos/o/r/actions/workflows/claude-review-agents.yml/runs?per_page=100"
        return {"workflow_runs": [{"display_title": title} for title in self.run_titles]}

    def graphql(self, query: str, variables: dict[str, str]) -> dict[str, Any]:
        assert variables == {"owner": "o", "name": "r"}
        return {"repository": {"defaultBranchRef": {"name": "main"}, "pullRequests": {"nodes": self.pulls}}}

    def post(self, path: str, payload: dict[str, Any]) -> None:
        self.posted.append((path, payload))


def _pull(number: int, mergeable: str, reviews: list[tuple[int, str, str, str]], marker: str = "") -> dict[str, Any]:
    nodes = [{"databaseId": review_id, "body": body, "submittedAt": at, "authorAssociation": association, "author": {"__typename": "User", "login": "someone"}} for review_id, body, at, association in reviews]
    comments = [{"body": ROUND_MARKER.format(through=marker), "author": {"login": "github-actions"}}] if marker else []
    return {"number": number, "mergeable": mergeable, "isCrossRepository": False, "reviews": {"nodes": nodes}, "comments": {"nodes": comments}}


def test_the_sweep_starts_the_newest_unhandled_claude_review_on_conflicting_pull_requests_only() -> None:
    pulls = [
        _pull(1, "CONFLICTING", [(10, "@claude", "2026-10-10T06:00:00Z", "OWNER"), (11, "nit", "2026-10-10T06:05:00Z", "OWNER"), (12, "@claude again", "2026-10-10T06:10:00Z", "OWNER")]),
        # A mergeable pull request gets its own review event, so the sweep never races it.
        _pull(2, "MERGEABLE", [(20, "@claude", "2026-10-10T06:00:00Z", "OWNER")]),
        # Nobody without write access can start the agents.
        _pull(3, "CONFLICTING", [(30, "@claude", "2026-10-10T06:00:00Z", "NONE")]),
        # A clean round already covered this review.
        _pull(4, "CONFLICTING", [(40, "@claude", "2026-10-10T06:00:00Z", "OWNER")], marker="2026-10-10T06:00:00Z"),
        # An earlier sweep or event already started this one.
        _pull(5, "CONFLICTING", [(50, "@claude", "2026-10-10T06:00:00Z", "MEMBER")]),
    ]
    github = _FakeSweepGitHub(pulls, [RUN_NAME.format(pull=5, review=50)], [])
    started = ReviewSweeper(github).sweep("o/r")
    assert [(dispatch.pull_number, dispatch.review_id) for dispatch in started] == [(1, 12)]
    assert github.posted == [("repos/o/r/actions/workflows/claude-review-agents.yml/dispatches", {"ref": "main", "inputs": {"pr": "1", "review": "12"}})]


def test_the_agents_workflow_names_its_runs_the_way_the_sweep_looks_for_them() -> None:
    workflow = (_WORKFLOWS / "claude-review-agents.yml").read_text(encoding="utf-8")
    expected = RUN_NAME.format(pull="${{ github.event.pull_request.number || inputs.pr }}", review="${{ github.event.review.id || inputs.review }}")
    assert f'run-name: "{expected}"' in workflow
    # Only people who can push may start the agents from a review.
    assert """contains(fromJSON('["OWNER", "MEMBER", "COLLABORATOR"]'), github.event.review.author_association)""" in workflow
    sweep = (_WORKFLOWS / "claude-review-sweep.yml").read_text(encoding="utf-8")
    assert "run.py sweep" in sweep
    assert "secrets.CLAUDE_REVIEW_SWEEP_TOKEN" in sweep


def test_run_py_check_accepts_the_committed_prompts() -> None:
    command = (sys.executable, str(_ROOT / "scripts" / "review_agents" / "run.py"), "check", "--agents-dir", str(_AGENTS_DIR))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


# Lint rule A009, the folder README ceiling


def _readme_repository(root: Path, readmes: dict[str, int]) -> SourceCatalog:
    # Each README is a tracked file of exactly the given number of characters.
    _git(root, "init", "-q")
    for rel, size in readmes.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Folder\n\n## Notes for agents\n\n" + "x" * (size - 31), encoding="utf-8", newline="\n")
    _git(root, "add", "-A")
    return SourceCatalog(root)


def test_a009_reports_a_folder_readme_over_its_ceiling_at_the_notes(tmp_path: Path) -> None:
    catalog = _readme_repository(tmp_path, {"pkg/README.md": 40_001, "fits/README.md": 40_000})
    findings = README_SIZE_RULE.check(catalog)
    assert [(finding.rel_path, finding.line) for finding in findings] == [("pkg/README.md", 3)]
    assert findings[0].extra == {"characters": "40001", "ceiling": "40000", "target": "30000"}
    assert "30,000" in README_SIZE_RULE.explain(findings[0]).what_happened


def test_a009_exempts_the_root_readme_and_keeps_legacy_ceilings(tmp_path: Path) -> None:
    catalog = _readme_repository(tmp_path, {"README.md": 90_000, "vidbyte/providers/README.md": 50_000, "vidbyte/agents/codex/README.md": 65_001})
    findings = README_SIZE_RULE.check(catalog)
    assert [(finding.rel_path, finding.extra["target"]) for finding in findings] == [("vidbyte/agents/codex/README.md", "55000")]
