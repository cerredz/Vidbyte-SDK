"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_commands.py

PURPOSE: Prove the commands the /onboard-model-provider skill tells an agent to run are the safe, real ones: preflight and pass-top are read-only up to `git worktree add`, the pass checks run in the FR-3 order, the vintage and member `sed` reads print the right values from the real files, back-pressure and the skip rules query what INV-4 and INV-5 need, every interpreter command is spelled `<py>`, PYTHONPATH only ever prefixes one command, the gate commands and output lines exist in the repository, and the mutation check, research protocol and named paths hold.
ROLE IN CODEBASE: Integration layer of tests/features/onboard_model_provider_skill/ (spec AC-1 static half, AC-5, AC-8; FR-2 to FR-5, FR-9; INV-3, INV-4, INV-5, INV-8, INV-15, INV-17, INV-20; EC-9; NFR-1, NFR-3; D-3, D-15, D-19, D-20, D-27; EC-52; section 8.5 pass-top block; section 12.4 command list; reviews R-3, R-8, R-9, R-10, R-5, R-E3).
ARCHITECTURE NOTE: A command is a logical line of a fenced sh/bash block (continuations joined) or an inline code span. Write detection first blanks quoted strings, comments and <placeholders>, so a jq filter or `<py>` is never read as a redirect. The two sed reads run through SedEmulator over the files the pass reads, so a change to `PRICING_AS_OF: str = "..."` or the enum layout on main fails here before it silently breaks selection.
FUNCTION INVENTORY: test_preflight_and_pass_top_commands_write_nothing_before_the_worktree_add (X1); test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add (X2); test_vintage_and_member_reads_print_the_values_on_main (X3); test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5 (X4); test_preflight_names_every_prerequisite_and_the_permission_setup (X5); test_every_interpreter_command_is_spelled_py_except_the_one_probe_line (X6); test_pythonpath_only_prefixes_one_command_and_never_the_package_stage (X7); test_gate_commands_and_output_lines_are_the_repositorys_real_ones (X8); test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff (X9); test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep (X10); test_every_repository_path_the_skill_names_exists (X11); test_backpressure_counts_the_listed_prs_together_with_this_sessions_prs (X12); test_vintage_stops_the_session_when_mains_pricebook_is_not_before_today (X13).
COMMON MODIFICATION PATTERNS: When the spec adds a pass-top read, add its pattern to REQUIRED_READS; when it allows a new write before the worktree add, change the spec first. Keep each write pattern narrow enough that the spec 8.5 commands pass.
WHAT NOT TO DO IN THIS FILE: 1. Do not execute a command from the skill, git, gh or the network. 2. Do not pin PRICING_AS_OF, the member list or its length: X3 compares the sed output with the values imported from the same tree. 3. Do not compare against base_commit.
KNOWN EDGE CASES: The rules a command serves (the known-red exclusion condition, the A13 two-check exception, the contract-test exclusion, the back-pressure union, the vintage direction) are pinned by their final wording in prose, outside fences, because a token check passes an inverted rule (review R-3, R-8). The same holds for the skip rules, the worktree add and its failure branch, and the network rule (review R-9, R-10): each skip read and the add are compared as whole commands, each rule as its whole sentence, and only the three network-rule lines may name NETWORK_BLOCKED. `2>/dev/null`, `2>&1` and `>&2` are not writes. `git ls-remote --exit-code` exits 2 for an absent branch, which AC-1 accepts. The probe line legitimately names python, python3 and py -3.11; it is the only exempt line. `PYTHONPATH=<dir>` inside a sentence (no `<py>` after it) is prose, not a command.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 6.2 (AC-1, AC-5, AC-8), 7 (FR-2 to FR-5), 8.1 (D-15, D-19, D-20, D-27), 8.5, 12.4.
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_commands.py -q
"""

from __future__ import annotations

import re

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    PROCEDURE_FILE,
    PROCEDURE_REF,
    REPO_ROOT,
    SKILL_FILE,
    SKILL_REF,
    MarkdownDoc,
    SedEmulator,
    first_index,
    read_markdown,
    sed_print_expressions,
)
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.registries.pricing import PRICING_AS_OF

GIT = r"\bgit(?:\s+-C\s+\S+)*\s+"
WORKTREE_ADD = GIT + r"worktree\s+add\b"

# The harness node that fails on every branch applying wiring row A13; its exclusion has its own two-check rule (D-15).
A13_NODE = "tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them"

# The final wording of the selection walk and the worktree add (SKILL.md `## Each pass`, review R-9 and R-10). A skip
# rule that reads live state is pinned as its whole command; a rule that is a sentence is pinned as that sentence.
OPEN_PRS_COMMAND = r'''gh api --paginate "repos/cerredz/Vidbyte-SDK/pulls?state=open&per_page=100" --jq '.[] | select(.head.repo.full_name == "cerredz/Vidbyte-SDK") | select(.head.ref | startswith("feat/provider-")) | "#\(.number)"'; echo "prs exit $?"'''
GH_FAILURE_SENTENCE = "A failed `gh api` call anywhere in a pass stops it with `NETWORK_BLOCKED - api.github.com <status>`; each `gh api` read in a pass prints `prs exit <n>`, and any value but 0 is such a failure, never an empty list."
WALK_SENTENCE = "2. Walk the seed vendors in rank order and select the first one that no skip rule excludes."
LEDGER_SENTENCE = "Skip without a query a vendor that already has an outcome in this session's ledger, or whose slug is a member."
PER_SLUG_COMMAND = r'''gh api "repos/cerredz/Vidbyte-SDK/pulls?state=all&head=cerredz:feat/provider-$SLUG&per_page=100" --jq '.[] | "#\(.number) \(.state) \(.merged_at // "unmerged")"'; echo "prs exit $?"'''
REMOTE_BRANCH_COMMAND = 'git ls-remote --exit-code --heads origin "refs/heads/feat/provider-$SLUG"; echo "remote-branch exit $?"'
LOCAL_BRANCH_COMMAND = 'git show-ref --verify --quiet "refs/heads/feat/provider-$SLUG"; echo "local-branch exit $?"'
PATHS_COMMAND = 'test -e "$WORKTREE" || test -e "$WORKTREE-evidence" || test -e "$WORKTREE-main"; echo "paths exit $?"'
SKIP_DISPOSITION_LINES = {
    "member": "- `member`: the slug is among the `ModelProvider` values on main.",
    "remote-branch": "- `remote-branch`: `ls-remote` exits 0. Exit 2 means the branch is absent; any other exit stops the session with `NETWORK_BLOCKED - github.com <exit>`.",
    "local-branch": "- `local-branch`: the local branch exists (`show-ref` exits 0), or the worktree path, its `-evidence` path or its `-main` twin exists (`paths exit 0`), left by an earlier STOP or an interrupted session. They are never overwritten.",
}
REJECTION_SENTENCE = "A closed unmerged PR is the person's rejection, so that vendor is skipped forever."
NO_CANDIDATE_SENTENCE = "With no vendor left, stop with `NO_CANDIDATE`."
ADD_COMMAND = 'git worktree add -b "feat/provider-$SLUG" "$WORKTREE" origin/main && git -C "$WORKTREE" rev-parse HEAD; echo "add exit $?"'
ADD_STEP_SENTENCE = "This is the pass's first write: a new branch from the fetched `origin/main`, never one that resets or forces an existing branch. The SHA it prints is the pass's `<base>`:"
ADD_FAILURE_SENTENCES = (
    "When `add exit` is not 0, the add failed, usually because another session created that branch or path after this pass's checks.",
    "The SHA, if one printed, is not yours: launch no subagent, record `local-branch` for the vendor, and continue the walk of step 2 with the next vendor.",
)

# The final wording of the network rule (provider-run.md `## 2. Research`, review R-9): only positive evidence of a
# policy refusal, or a failed GitHub check, ends a run NETWORK_BLOCKED; a vendor's own error goes to section 3.
NETWORK_RULE_START = "Network rule. `NETWORK_BLOCKED` needs positive evidence that your session's own policy refused the fetch:"
DENY_HEADER_CHECK = """run `grep -i '^x-deny-reason' "<evidence>/pages/<name>.headers"`."""
DENY_SENTENCE = "A match, or a sandbox or tool permission-denial message for the fetch, ends the run `NETWORK_BLOCKED`; its detail is the host and that header line or message, on one line, because the orchestrator deletes the evidence directory after this outcome."
GITHUB_CHECK = r"`curl -sS --max-time 30 -o /dev/null -w '%{http_code}\n' https://api.github.com`"
OTHER_FAILURE_SENTENCES = (
    "- Any other failure on a vendor host (curl exit not 0 for DNS, connection, TLS or timeout, or an HTTP status of 400 or more without `x-deny-reason`) is first checked against GitHub with " + GITHUB_CHECK + ".",
    "When that does not print a 2xx status, end the run `NETWORK_BLOCKED` with the detail `api.github.com` and what the check printed.",
    "Otherwise the vendor page is unreachable, and section 3 decides whether that is `docs-unreachable`.",
)

# Review R-5 and D-27 (S5 repair 1): the probe prefix, the rule behind it, and why an acceptEdits allowlist fails.
PROBE_PREFIX = "cd <worktree> && PYTHONPATH=<worktree> <py> -c "
CD_RULE = "Every other command that uses a repository-relative path, such as `tests/…` or `scripts/run_ci.py`, starts with `cd <worktree> && `, because each shell call starts in another directory."
ACCEPT_EDITS_SENTENCE = "An allowlist with `acceptEdits` is not enough: allow rules do not match past a leading `PYTHONPATH=` assignment, and edits in a sibling worktree lie outside the working directories, so the run would wait at prompts."

# Spec 8.5 pass-top block and FR-2: the reads a session makes before its first write.
REQUIRED_READS = {
    "git fetch": GIT + r"fetch\b",
    "vintage read": r"PRICING_AS_OF",
    "today": r"\bdate\s+-u\b",
    "open provider PRs": r"state=open",
    "per-slug PRs": r"head=cerredz:feat/provider-",
    "remote branch": r"\bls-remote\b",
    "local branch": r"\bshow-ref\b",
    "push permission": r"permissions\.push",
    "git identity": r"user\.email",
}

# A command that changes a file, a ref, the index, an installed package or anything on GitHub (AC-5, NFR-3, INV-8).
WRITE_PATTERNS = {
    "pip install": r"\bpip3?\s+install\b",
    "HTTP write method": r"(?:-X|--method)\s*(?:POST|PUT|PATCH|DELETE)\b",
    "gh api field": r"\bgh\s+api\b.*\s(?:-f|-F|--field|--raw-field|--input)(?:\s|=|$)",
    "git push": GIT + r"push\b",
    "git write": GIT + r"(?:commit|checkout|switch|reset|clean|merge|rebase|stash|add|rm|mv|tag|cherry-pick|revert|apply|am|restore|init|clone|pull)\b",
    "git branch write": GIT + r"branch\s+(?:-d|-D|-m|-M|-c|-C|-f|--delete|--move|--copy|--force)\b",
    "git worktree write": GIT + r"worktree\s+(?:remove|prune|move|lock|unlock)\b",
    "git config write": GIT + r"config\s+(?!--get\b|--get-all\b|--list\b|-l\b)[\w.-]+\s+(?![|&;>)<]|\d*>)\S",
    "sed in place": r"\bsed\s+(?:-[A-Za-z]*i|--in-place)",
    "file command": r"(?:^|[;&|(]\s*|\bxargs\s+)(?:tee|touch|rm|mv|cp|mkdir|rmdir|truncate|chmod|chown|ln|install|dd)\b",
}

_PLACEHOLDER = re.compile(r"<[A-Za-z][\w .+|-]*>")
_REDIRECT = re.compile(r"\d*>>?\|?\s*(\S+)")
_INTERPRETER_CALL = re.compile(r"(?<![\w<>/.$-])(?:python3?|py\s+-3(?:\.\d+)?)(?=\s+(?:-[A-Za-z]|[\w./-]+\.py\b))")
_PATH_TOKEN = re.compile(r"(?<![\w./-])(?:vidbyte|tests|lint|scripts|\.github)/[A-Za-z0-9_./<>*{}$-]*[A-Za-z0-9_>*}]")
PROBE_MODULES = ("sys", "pytest", "build", "twine", "mypy", "ruff", "yaml", "pydantic", "httpx")


def _neutralize(command: str) -> str:
    # Blank the inside of quoted strings, then drop a trailing comment and every <placeholder>.
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2
                continue
            if char == quote:
                out.append(char)
                quote = ""
        elif char in "'\"":
            out.append(char)
            quote = char
        else:
            out.append(char)
        index += 1
    bare = re.sub(r"(?:^|\s)#.*$", "", "".join(out))
    return _PLACEHOLDER.sub("P", bare)


def _writes(command: str) -> list[str]:
    bare = _neutralize(command)
    found = [name for name, pattern in WRITE_PATTERNS.items() if re.search(pattern, bare, flags=re.IGNORECASE if name == "HTTP write method" else 0)]
    targets = [target for target in _REDIRECT.findall(bare) if not (target.startswith("&") or target == "/dev/null")]
    return found + ([f"redirect to {targets}"] if targets else [])


def _pass_top(skill: MarkdownDoc) -> tuple[list[str], list[str]]:
    # The preflight commands, and the Each pass commands up to (not including) the first worktree add, plus the rest.
    preflight = skill.section("## Prerequisites and preflight").shell_commands()
    each_pass = skill.section("## Each pass").shell_commands()
    cut = first_index(each_pass, WORKTREE_ADD)
    return preflight + (each_pass[:cut] if cut >= 0 else each_pass), each_pass


def test_preflight_and_pass_top_commands_write_nothing_before_the_worktree_add() -> None:
    # X1 · AC-5 / AC-1 static half / NFR-3 / INV-8: a session that stops before any subagent has written nothing;
    # the reads it needs are present, so the scan cannot pass by scanning no commands.
    read_only, _ = _pass_top(read_markdown(SKILL_FILE, SKILL_REF))

    assert [name for name, pattern in REQUIRED_READS.items() if not any(re.search(pattern, command) for command in read_only)] == [], "preflight and pass-top reads must sit in fenced sh/bash blocks"
    assert {command: writes for command in read_only if (writes := _writes(command))} == {}


def test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add() -> None:
    # X2 · FR-3 / FR-4 / FR-5 / D-3 / EC-17: cheapest check first, so a session that must stop makes no worktree;
    # the worktree is a new branch from fresh origin/main and never overwrites a kept branch.
    commands = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass").shell_commands()

    steps = {
        "fetch": first_index(commands, GIT + r"fetch\b.*\borigin\b"),
        "vintage": first_index(commands, r"PRICING_AS_OF"),
        "back-pressure": first_index(commands, r"state=open"),
        "selection": min((index for index in (first_index(commands, pattern) for pattern in (r"model_provider\.py", r"head=cerredz:feat/provider-", r"\bls-remote\b", r"\bshow-ref\b")) if index >= 0), default=-1),
        "worktree add": first_index(commands, WORKTREE_ADD),
    }
    assert [name for name, index in steps.items() if index < 0] == []
    assert list(steps.values()) == sorted(steps.values()), f"## Each pass must run {list(steps)} in that order; found command indexes {steps}"
    add = commands[steps["worktree add"]]
    assert re.search(r"\s-b\s", add) and "feat/provider-" in add and re.search(r"\borigin/main\b", add)
    assert not re.search(r"(?:^|\s)(?:-B|-f|--force)(?:\s|$)", add), "D-3 / EC-17: the worktree add must never reset or force an existing branch"

    # Review R-10: the add is pinned as its whole command, and its failure branch by its sentences, because a session that
    # adopts a worktree another session created runs two subagents on one branch (D-3, EC-52, review R-6).
    prose = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass").prose_lines()
    assert [command for command in commands if re.search(WORKTREE_ADD, command)] == [ADD_COMMAND], "D-3: one worktree add, printing the base SHA and `add exit`"
    assert any(ADD_STEP_SENTENCE in line for line in prose), "D-3: the add is the pass's first write, a new branch from the fetched origin/main"
    failure = [line for line in prose if "`add exit` is not 0" in line]
    assert len(failure) == 1 and [sentence for sentence in ADD_FAILURE_SENTENCES if sentence not in failure[0]] == [], "EC-52 / D-3: a failed add launches no subagent and records local-branch"
    assert not [line for line in prose if re.search(r"launch the subagent on that worktree|SHA that printed is the pass's", line)], "a failed add never adopts the worktree"


def test_vintage_and_member_reads_print_the_values_on_main() -> None:
    # X3 · FR-3 / INV-3 / INV-5a / NFR-1: the pass reads git blobs from origin/main, and its sed scripts, run over the
    # same files in this tree, print exactly PRICING_AS_OF and exactly the ModelProvider values.
    commands = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass").shell_commands()
    sed = SedEmulator()

    vintage = [command for command in commands if re.search(r"\bshow\s+origin/main:vidbyte/lib/registries/pricing\.py\b", command) and sed_print_expressions(command)]
    members = [command for command in commands if re.search(r"\bshow\s+origin/main:vidbyte/lib/enums/model_provider\.py\b", command) and sed_print_expressions(command)]
    assert len(vintage) >= 1 and len(members) >= 1, "## Each pass reads the vintage and the members with `git show origin/main:<path> | sed -n 's/.../p'`"
    pricing = (REPO_ROOT / "vidbyte/lib/registries/pricing.py").read_text(encoding="utf-8")
    providers = (REPO_ROOT / "vidbyte/lib/enums/model_provider.py").read_text(encoding="utf-8")
    for command in vintage:
        assert [line for expression in sed_print_expressions(command) for line in sed.print_lines(expression, pricing)] == [PRICING_AS_OF]
    for command in members:
        printed = [line for expression in sed_print_expressions(command) for line in sed.print_lines(expression, providers)]
        assert len(printed) == len(set(printed)) and set(printed) == {member.value for member in ModelProvider}


def test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5() -> None:
    # X4 · INV-4 / INV-5 a-e / T-4 / EC-10: count every open same-repo provider PR across pages; read every PR state
    # per slug (closed unmerged skips forever); check the remote and local branch and the session ledger.
    each_pass = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass")
    commands = each_pass.shell_commands()

    open_list = [command for command in commands if "state=open" in command]
    assert len(open_list) >= 1
    for command in open_list:
        assert "--paginate" in command and "per_page=100" in command
        assert re.search(r'head\.repo\.full_name\s*==\s*"cerredz/Vidbyte-SDK"', command), "T-4: fork PRs must not count toward back-pressure"
        assert re.search(r'startswith\(\s*"feat/provider-"\s*\)', command)
    per_slug = [command for command in commands if "state=all" in command]
    assert per_slug and all("head=cerredz:feat/provider-" in command and "merged_at" in command for command in per_slug)
    assert [name for name in ("ls-remote", "show-ref") if not any(name in command and "refs/heads/feat/provider-" in command for command in commands)] == []
    text = each_pass.squashed()
    assert [phrase for phrase in ("-evidence", "this session", "BACKPRESSURE", "MAX_OPEN_PROVIDER_PRS") if phrase not in text] == []

    # Review R-9: each skip rule is pinned by its whole command or its whole sentence. After DISQUALIFIED and the D-8
    # cleanup no live state names the vendor, so the ledger sentence alone keeps the walk from selecting it again.
    assert [command for command in (OPEN_PRS_COMMAND, PER_SLUG_COMMAND, REMOTE_BRANCH_COMMAND, LOCAL_BRANCH_COMMAND, PATHS_COMMAND) if commands.count(command) != 1] == [], "INV-4, INV-5 b-d: each read is one exact command"
    prose = each_pass.prose_lines()
    assert any(GH_FAILURE_SENTENCE in line for line in prose), "review R-E3: a failed gh api read stops the pass, never reads as an empty list"
    walk = [line for line in prose if line.startswith(WALK_SENTENCE)]
    assert len(walk) == 1 and LEDGER_SENTENCE in walk[0], "INV-5 e: a vendor with an outcome in this session's ledger is skipped without a query"
    dispositions = {name: [line.strip() for line in prose if line.strip().startswith(f"- `{name}`:")] for name in SKIP_DISPOSITION_LINES}
    assert {name: lines for name, lines in dispositions.items() if lines != [SKIP_DISPOSITION_LINES[name]]} == {}, "INV-5 a, c, d: each skip disposition keeps its final wording"
    assert any(REJECTION_SENTENCE in line for line in prose), "INV-5 b: a closed unmerged PR skips the vendor forever"
    assert any(line.strip() == NO_CANDIDATE_SENTENCE for line in prose)


def test_preflight_names_every_prerequisite_and_the_permission_setup() -> None:
    # X5 · FR-2 / D-27 / section 9.3: the checks the skill can make, and the setup it can only state: the checkout's
    # parent as an added directory, auto or bypassPermissions mode, and why acceptEdits is not enough.
    preflight = read_markdown(SKILL_FILE, SKILL_REF).section("## Prerequisites and preflight").squashed()

    required = {
        "push permission": r"\.permissions\.push",
        "git identity": r"user\.email",
        "origin remote": r"\borigin\b",
        "added directory": r"--add-dir\b",
        "bypassPermissions": r"\bbypassPermissions\b",
        "acceptEdits": r"\bacceptEdits\b",
        "auto mode": r"\bauto mode\b|--permission-mode auto\b",
        "Agent tool": r"\bAgent tool\b",
    }
    assert [name for name, pattern in required.items() if not re.search(pattern, preflight, flags=re.IGNORECASE if name in ("auto mode", "Agent tool") else 0)] == []
    assert ACCEPT_EDITS_SENTENCE in preflight, "D-27: an acceptEdits allowlist is not enough, and the reason is stated"


def test_every_interpreter_command_is_spelled_py_except_the_one_probe_line() -> None:
    # X6 · AC-8 / D-20 / R-7: bare `python` lacks pytest on the user's machine, so every interpreter call is `<py>`; the
    # one exempt line is the preflight probe, which names python, python3 and py -3.11 and imports the dev extras.
    skill = read_markdown(SKILL_FILE, SKILL_REF)
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    probes = [line.text for line in skill.lines if re.search(r"\bpython3\b", line.text)]

    assert len(probes) == 1, f"exactly one SKILL.md line (the D-20 probe) names python3; found {len(probes)}"
    probe = probes[0]
    assert re.search(r"\bpython\b(?!3)", probe) and "py -3.11" in probe
    assert [module for module in PROBE_MODULES if not re.search(rf"\b{module}\b", probe)] == [] and re.search(r"version_info\s*<\s*\(3,\s*11\)", probe)
    assert probe in skill.section("## Prerequisites and preflight").text.splitlines()
    assert [line.text for line in skill.lines if "py -3.11" in line.text] == [probe]
    assert not re.search(r"\bpython3\b|py -3\.11", procedure.text), "provider-run.md uses only <py>"
    bare = [f"{doc.label}:{line.text.strip()}" for doc in (skill, procedure) for line in doc.lines if line.text != probe and _INTERPRETER_CALL.search(line.text)]
    assert bare == [], "every interpreter command must be spelled <py>"
    assert [command for doc in (skill, procedure) for command in doc.shell_commands() if re.search(r"\bpip3?\s+install\b", command)] == [], "the skill never installs; the remedy line is prose or text"


def test_pythonpath_only_prefixes_one_command_and_never_the_package_stage() -> None:
    # X7 · D-15 / AC-8 / AC-12: an exported PYTHONPATH makes the clean install skip the wheel and fail its smoke step,
    # while the source stage in a worktree needs the one-command prefix to import the worktree's vidbyte.
    documents = (read_markdown(SKILL_FILE, SKILL_REF), read_markdown(PROCEDURE_FILE, PROCEDURE_REF))
    commands = [command for doc in documents for command in doc.commands()]

    assert [command for doc in documents for command in doc.shell_commands() if re.search(r"\bexport\s+PYTHONPATH\b", command)] == []
    assert not any(re.search(r"\bexport\s+PYTHONPATH=", doc.text) for doc in documents)
    assert [command for command in commands if "<py>" in command and re.search(r"PYTHONPATH=(?!\S+\s+<py>)", command)] == [], "PYTHONPATH=<dir> must directly prefix one <py> command"
    package = [command for command in commands if "run_ci.py" in command and "--stage package" in command]
    source = [command for command in commands if "run_ci.py" in command and "--stage source" in command]
    assert package and not [command for command in package if "PYTHONPATH" in command], "the package stage runs with no PYTHONPATH"
    assert source and all("PYTHONPATH=" in command for command in source), "the source stage runs with a PYTHONPATH=<worktree> prefix"

    # Review R-5 (S5 repair 1): with `-c`, Python imports from the shell's starting directory before PYTHONPATH, so a
    # probe run from the launcher checkout reads the launcher's files; every probe therefore starts in the worktree.
    probes = [command for command in documents[1].commands() if re.search(r"PYTHONPATH=\S+ <py> -c\b", command)]
    assert len(probes) >= 3 and [command for command in probes if not command.startswith(PROBE_PREFIX)] == [], "R-5: every -c probe runs as `cd <worktree> && PYTHONPATH=<worktree> <py> -c ...`"
    assert any(CD_RULE in line for line in documents[1].prose_lines()), "R-5: a command with a repository-relative path starts with `cd <worktree> && `"


def test_gate_commands_and_output_lines_are_the_repositorys_real_ones() -> None:
    # X8 · section 12.4 / AC-8 / INV-17 / D-15 / FR-11 check (4): the procedure runs the real gate and refresh commands,
    # the output lines it looks for are the ones the repository prints, and the known-red rule keeps its safeguards.
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    text = procedure.squashed()

    required = {
        "source stage": r"PYTHONPATH=\S+ <py> scripts/run_ci\.py --stage source",
        "package stage": r"<py> scripts/run_ci\.py --stage package",
        "provider-keys pack": r"<py> -m pytest tests/features/sdk_provider_keys\b",
        "vintage lock refresh": r"<py> -m lint\.rules\.c010_pricebook_vintage_bump --refresh-lock",
        "lint line": r"SDK-LINT: PASS",
        "smoke line": r"passed smoke checks\.",
        "gate line": r"CI passed\.",
    }
    assert [name for name, pattern in required.items() if not re.search(pattern, text)] == []
    gate = procedure.section("## 8. Gate").squashed()
    safeguards = {
        "base twin": GIT + r"worktree\s+add\s+--detach\b[^`]*-main\b",
        "twin removal": GIT + r"worktree\s+remove\s+--force\b",
        "unchanged file": GIT + r"diff\s+--quiet\b",
        "not found is not failed": r"not found",
        "three reruns": r"\bup to (?:3|three)\b",
    }
    assert [name for name, pattern in safeguards.items() if not re.search(pattern, gate, flags=re.IGNORECASE)] == []
    run_ci = (REPO_ROOT / "scripts/run_ci.py").read_text(encoding="utf-8")
    assert "passed smoke checks." in run_ci and "CI passed." in run_ci
    assert "SDK-LINT: PASS" in (REPO_ROOT / "lint/core/report.py").read_text(encoding="utf-8")
    assert "--refresh-lock" in (REPO_ROOT / "lint/rules/c010_pricebook_vintage_bump.py").read_text(encoding="utf-8")

    # Review R-3: the known-red exclusion is pinned by its condition, so a rule that only logs the diff, or excludes a
    # changed file, fails here; a failing test the branch added must never pass as pre-existing (D-15, review r2-2).
    gate_section = procedure.section("## 8. Gate")
    gate_prose = gate_section.prose_lines()
    unchanged = [line for line in gate_prose if "diff --quiet <base> HEAD -- <file>" in line]
    assert unchanged and all("only when its file is unchanged, meaning `git -C <worktree> diff --quiet <base> HEAD -- <file>` exits 0" in line for line in unchanged), "D-15: exclude a failing node only when its file is unchanged, the scoped diff exiting 0"
    assert not [line for line in unchanged if re.search(r"\bexits 1\b|\bis changed\b|\bchanged file\b", line)]
    # The A13 control-edit exception excludes one node, never its file, and only when both checks hold (S5 R-2 bullet).
    a13 = [line for line in gate_prose if A13_NODE.split("::")[1] in line]
    assert len(a13) == 1, "## 8. Gate names the A13 harness node in one bullet"
    assert [phrase for phrase in ("never its whole file", "only when both checks below hold", "prints exactly one line, `vidbyte/lib/configs/structured_output.py`") if phrase not in a13[0]] == []
    assert any("the same `AssertionError` line as on the branch" in line for line in gate_prose), "the control edit must reproduce the branch's own AssertionError line"
    gate_commands = gate_section.shell_commands()
    assert "git -C <worktree> diff --name-only <base> HEAD -- vidbyte/tools vidbyte/lib/configs" in gate_commands, "the first A13 check is the scoped diff"
    edits = [command for command in gate_commands if "# control edit" in command]
    assert edits and all(">> <worktree>-main/vidbyte/lib/configs/structured_output.py" in command for command in edits), "the control edit goes to the twin, never to the branch worktree"
    assert f"def {A13_NODE.split('::')[1]}(" in (REPO_ROOT / A13_NODE.split("::")[0]).read_text(encoding="utf-8")


def test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff() -> None:
    # X9 · AC-8 / INV-15 / D-15: commit, green run, then per key rule revert, rerun, record the node IDs that newly fail,
    # restore with `git checkout --` and confirm `git diff --quiet`; a test only the table-pinning contract catches is
    # not proof.
    section = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 7. Commit and mutation checks")
    commands = section.commands()

    steps = {
        "commit": first_index(commands, GIT + r"commit\b"),
        "green run": first_index(commands, r"-m pytest tests/features/sdk_provider_keys\b"),
        "restore": first_index(commands, GIT + r"checkout\s+--\s"),
        "clean diff": first_index(commands, GIT + r"diff\s+--quiet\b"),
    }
    assert [name for name, index in steps.items() if index < 0] == []
    assert list(steps.values()) == sorted(steps.values()), f"## 7 must run {list(steps)} in that order; found command indexes {steps}"
    text = section.squashed()
    assert [phrase for phrase in ("mutation-survived", "wire-test", "gate-source") if phrase not in text] == []
    assert re.search(r"\bnode\b", text, flags=re.IGNORECASE), "the mutation record names the node IDs that newly fail"
    assert re.search(r"test_provider_keys_contract|\bC5\b", text), "INV-15: the failing test must be outside the table-pinning contract test"
    # Review R-3: every sentence naming the contract test must exclude it, so "it counts too" fails here.
    naming = [line for line in section.prose_lines() if "test_provider_keys_contract" in line]
    assert naming and all("At least one must be outside `test_provider_keys_contract.py`" in line for line in naming), "AC-8 / INV-15: at least one newly failing node must be outside the contract test"
    assert any("`PROOF_FAILED mutation-survived`" in line for line in naming)
    assert not [line for line in section.prose_lines() if re.search(r"test_provider_keys_contract\.py`? (?:included|counts)|may be `test_provider_keys_contract", line)]


def test_backpressure_counts_the_listed_prs_together_with_this_sessions_prs() -> None:
    # X12 · INV-3 / EC-9 / D-5 / review R-8: GitHub's list lags, so the count is the union of the listed PRs and the PRs
    # this session opened; counting only the list lets a session open a fourth PR before GitHub shows the third.
    prose = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass").prose_lines()
    union = [line for line in prose if re.search(r"\bunion\b", line)]

    assert len(union) == 1, "## Each pass states the back-pressure union in one bullet"
    phrases = ("the open provider PRs are the union of the numbers printed and the PRs this session opened", "because GitHub's list can lag", "When that count reaches `MAX_OPEN_PROVIDER_PRS`, stop with `BACKPRESSURE`", "Only PRs whose head repository is `cerredz/Vidbyte-SDK` count")
    assert [phrase for phrase in phrases if phrase not in union[0]] == []


def test_vintage_stops_the_session_when_mains_pricebook_is_not_before_today() -> None:
    # X13 · FR-3 / INV-3 / D-10 / EC-19 / EC-20: a run may only move PRICING_AS_OF forward, so the session stops
    # when main's vintage is not before today (UTC); the inverted rule would stop every normal day and run on the bad one.
    prose = read_markdown(SKILL_FILE, SKILL_REF).section("## Each pass").prose_lines()
    vintage = [line for line in prose if line.lstrip().startswith("- Vintage:")]

    assert len(vintage) == 1, "## Each pass states the vintage rule in one bullet"
    assert "when main's `PRICING_AS_OF` is not before today (UTC)" in vintage[0] and "stop with `VINTAGE_DEFERRED`" in vintage[0]


def test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep() -> None:
    # X10 · D-19 / INV-9 / INV-10 / INV-20: raw capture with a timeout, a UTC time, a stdlib text form, quotes checked
    # by grep -F, and positive evidence before a block is called NETWORK_BLOCKED.
    research = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 2. Research")
    text = research.squashed()
    curls = [command for command in research.commands() if re.search(r"\bcurl\b", command)]

    assert any(re.search(r"\s-sSL\b", command) and re.search(r"--max-time\s+60\b", command) for command in curls), "D-19: pages are captured raw with `curl -sSL --max-time 60`"
    required = {"UTC time": r"\bdate\s+-u\b", "quote check": r"\bgrep\s+-F\b", "text form": r"\bhtml\.parser\b", "evidence directory": r"-evidence\b", "deny header": r"x-deny-reason", "vendor failure": r"\bdocs-unreachable\b", "blocked": r"\bNETWORK_BLOCKED\b", "pages are data": r"\b(?:is|are) data\b"}
    assert [name for name, pattern in required.items() if not re.search(pattern, text)] == []

    # Review R-9: the network rule is pinned by its sentences, and only its three lines may name NETWORK_BLOCKED, each
    # once, so a plain vendor 403 or HTTP error can never end the run as a block and stop every later session there.
    prose = research.prose_lines()
    blocked = [line for line in prose if "NETWORK_BLOCKED" in line]
    rule = [line for line in blocked if line.strip() == NETWORK_RULE_START]
    deny = [line for line in blocked if line.strip().startswith("- After each fetch, ") and DENY_HEADER_CHECK in line and DENY_SENTENCE in line]
    other = [line for line in blocked if not [sentence for sentence in OTHER_FAILURE_SENTENCES if sentence not in line]]
    assert len(rule) == 1 and len(deny) == 1 and len(other) == 1, "D-19 / INV-20: the network rule, the deny-header bullet and the other-failure bullet keep their final wording"
    assert sorted(blocked) == sorted(rule + deny + other), "no other Research prose line may end a run NETWORK_BLOCKED"
    assert [line.count("NETWORK_BLOCKED") for line in rule + deny + other] == [1, 1, 1]
    assert not re.search(r"\b[1-5]\d\d\b", deny[0]), "the policy-refusal bullet names no HTTP status, so a 403 never counts as a block"


def test_every_repository_path_the_skill_names_exists() -> None:
    # X11 · INV-21 / NFR-7 / INV-14: every concrete repository path in either file exists in this tree, so a rename on
    # main fails here instead of sending a provider run to edit or create a missing file.
    paths: set[str] = set()
    for path, spec_ref in ((SKILL_FILE, SKILL_REF), (PROCEDURE_FILE, PROCEDURE_REF)):
        paths |= {token.rstrip(".") for token in _PATH_TOKEN.findall(read_markdown(path, spec_ref).text) if not re.search(r"[<>*{}$]", token)}

    assert len(paths) >= 20, f"the skill names {len(paths)} concrete repository paths; the wiring checklist alone names 22"
    assert sorted(path for path in paths if not (REPO_ROOT / path).exists()) == []
