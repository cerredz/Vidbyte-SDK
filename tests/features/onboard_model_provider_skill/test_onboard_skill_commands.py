"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_commands.py

PURPOSE: Prove the commands the /onboard-model-provider skill tells an agent to run are the safe, real ones: preflight and pass-top are read-only up to `git worktree add`, the pass checks run in the FR-3 order, the vintage and member `sed` reads print the right values from the real files, back-pressure and the skip rules query what INV-4 and INV-5 need, every interpreter command is spelled `<py>`, PYTHONPATH only ever prefixes one command, the gate commands and output lines exist in the repository, and the mutation check, research protocol and named paths hold.
ROLE IN CODEBASE: Integration layer of tests/features/onboard_model_provider_skill/ (spec AC-1 static half, AC-5, AC-8; FR-2 to FR-5, FR-9; INV-4, INV-5, INV-8, INV-15, INV-17, INV-20; NFR-1, NFR-3; D-3, D-15, D-19, D-20, D-27; section 8.5 pass-top block; section 12.4 command list).
ARCHITECTURE NOTE: A command is a logical line of a fenced sh/bash block (continuations joined) or an inline code span. Write detection first blanks quoted strings, comments and <placeholders>, so a jq filter or `<py>` is never read as a redirect. The two sed reads run through SedEmulator over the files the pass reads, so a change to `PRICING_AS_OF: str = "..."` or the enum layout on main fails here before it silently breaks selection.
FUNCTION INVENTORY: test_preflight_and_pass_top_commands_write_nothing_before_the_worktree_add (X1); test_each_pass_runs_fetch_vintage_backpressure_and_selection_before_one_safe_worktree_add (X2); test_vintage_and_member_reads_print_the_values_on_main (X3); test_backpressure_and_skip_rule_queries_cover_invariants_4_and_5 (X4); test_preflight_names_every_prerequisite_and_the_permission_setup (X5); test_every_interpreter_command_is_spelled_py_except_the_one_probe_line (X6); test_pythonpath_only_prefixes_one_command_and_never_the_package_stage (X7); test_gate_commands_and_output_lines_are_the_repositorys_real_ones (X8); test_mutation_check_commits_first_restores_by_checkout_and_confirms_a_clean_diff (X9); test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep (X10); test_every_repository_path_the_skill_names_exists (X11).
COMMON MODIFICATION PATTERNS: When the spec adds a pass-top read, add its pattern to REQUIRED_READS; when it allows a new write before the worktree add, change the spec first. Keep each write pattern narrow enough that the spec 8.5 commands pass.
WHAT NOT TO DO IN THIS FILE: 1. Do not execute a command from the skill, git, gh or the network. 2. Do not pin PRICING_AS_OF, the member list or its length: X3 compares the sed output with the values imported from the same tree. 3. Do not compare against base_commit.
KNOWN EDGE CASES: `2>/dev/null`, `2>&1` and `>&2` are not writes. `git ls-remote --exit-code` exits 2 for an absent branch, which AC-1 accepts. The probe line legitimately names python, python3 and py -3.11; it is the only exempt line. `PYTHONPATH=<dir>` inside a sentence (no `<py>` after it) is prose, not a command.
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


def test_research_saves_raw_pages_with_time_and_checks_quotes_with_grep() -> None:
    # X10 · D-19 / INV-9 / INV-10 / INV-20: raw capture with a timeout, a UTC time, a stdlib text form, quotes checked
    # by grep -F, and positive evidence before a block is called NETWORK_BLOCKED.
    research = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 2. Research")
    text = research.squashed()
    curls = [command for command in research.commands() if re.search(r"\bcurl\b", command)]

    assert any(re.search(r"\s-sSL\b", command) and re.search(r"--max-time\s+60\b", command) for command in curls), "D-19: pages are captured raw with `curl -sSL --max-time 60`"
    required = {"UTC time": r"\bdate\s+-u\b", "quote check": r"\bgrep\s+-F\b", "text form": r"\bhtml\.parser\b", "evidence directory": r"-evidence\b", "deny header": r"x-deny-reason", "vendor failure": r"\bdocs-unreachable\b", "blocked": r"\bNETWORK_BLOCKED\b", "pages are data": r"\b(?:is|are) data\b"}
    assert [name for name, pattern in required.items() if not re.search(pattern, text)] == []


def test_every_repository_path_the_skill_names_exists() -> None:
    # X11 · INV-21 / NFR-7 / INV-14: every concrete repository path in either file exists in this tree, so a rename on
    # main fails here instead of sending a provider run to edit or create a missing file.
    paths: set[str] = set()
    for path, spec_ref in ((SKILL_FILE, SKILL_REF), (PROCEDURE_FILE, PROCEDURE_REF)):
        paths |= {token.rstrip(".") for token in _PATH_TOKEN.findall(read_markdown(path, spec_ref).text) if not re.search(r"[<>*{}$]", token)}

    assert len(paths) >= 20, f"the skill names {len(paths)} concrete repository paths; the wiring checklist alone names 22"
    assert sorted(path for path in paths if not (REPO_ROOT / path).exists()) == []
