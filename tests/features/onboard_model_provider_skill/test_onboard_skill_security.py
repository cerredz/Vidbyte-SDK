"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_security.py

PURPOSE: Prove the /onboard-model-provider skill cannot instruct the writes and leaks its threat model rules out: no Windows-only construct, `gh pr`, `gh issue`, `git stash`, force push or `path:line`; GitHub only through `gh api`, with one PR-create POST as the only write; one push of the single provider refspec; no change to VIDBYTE_MANAGED_TEXT_PROVIDERS; the D-29 rule that keeps a provider-prefixed model ID from being catalogued under the wrong vendor; and no literal key shape.
ROLE IN CODEBASE: Security layer of tests/features/onboard_model_provider_skill/ (spec AC-3, AC-15, AC-8 "never git stash"; INV-8, INV-12, INV-14, INV-16, INV-18, INV-19, INV-21; NFR-1, NFR-4; D-12, D-13, D-16, D-29; EC-63; INV-13; threats T-1 to T-4; reviews R-3, R-8, R-10, R-11, R-12).
ARCHITECTURE NOTE: The skill runs with push rights under a person's identity, often in auto or bypassPermissions mode (D-27), so its text is the control. Each scan reads both files whole, prose and fences alike, because an agent follows a prose instruction as readily as a command; each scan also asserts the file is long enough to have been scanned. The D-29 test also checks the runtime behaviour the rule relies on, so a change to Runner's provider derivation fails here. Rules are pinned by their content, not by a token (review R-3): the D-29 condition must read "is None" in prose, every self-check relation must keep its polarity as a statement, and both python fences must compile, so an inverted condition or an assert turned into a bare call fails.
FUNCTION INVENTORY: test_skill_files_hold_no_forbidden_construct (S1); test_github_is_reached_only_through_gh_api_and_the_only_write_is_the_pr_create (S2); test_every_push_is_the_single_unforced_provider_refspec (S3); test_the_managed_text_provider_set_is_only_ever_named_as_untouched (S4); test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it (S5); test_no_literal_key_shape_appears_and_fakes_are_built_by_concatenation (S6); test_format_binding_needs_a_first_party_statement_not_an_example_key (S7); test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt (S8); test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome (S9); _rules_for_the_whole_run reads the bullets before the first H2 of provider-run.md.
COMMON MODIFICATION PATTERNS: When the spec allows a new GitHub write or a new git ref, change the spec first, then the matching pattern here. Keep the forbidden patterns literal enough that a reviewer can read them.
WHAT NOT TO DO IN THIS FILE: 1. Do not call GitHub, git or a vendor. 2. Do not write a real key, or a literal that looks like one, into this file: S6 patterns are built from short pieces. 3. Do not assert that a seed slug is or is not a ModelProvider member.
KNOWN EDGE CASES: `git worktree remove --force` is allowed (not a push). Regex and sed escapes (an escaped pipe, an escaped group parenthesis, a backreference, an escaped dot, a class such as the whitespace class) are not Windows paths. A pytest node ID `file.py::Test` is not a `path:line` reference. A `gh api -X POST` fragment in prose with no endpoint is a mention, not a command. S8 and S9 compare whole lines (the URL rule, the guard paragraph, the proof rule), so an added sentence fails as surely as a deleted one. GUARD_COMMAND is a raw string, so each octal backslash escape stays the four characters the file holds; S9 checks that before comparing. test_onboard_skill_publish_guard.py runs the same line through sh.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 5 (INV-8 to INV-21), 6.2 (AC-3, AC-15), 8.1 (D-12, D-29), 8.5 (self-check), 10 (threat model).
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_security.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    PROCEDURE_FILE,
    PROCEDURE_REF,
    SKILL_FILE,
    SKILL_REF,
    MarkdownDoc,
    read_markdown,
)
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.registries.models import ProviderModelRegistry
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners.utility import Runner
from vidbyte.lib.tools.formatter import ToolsFormatter

GIT = r"\bgit(?:\s+-C\s+\S+)*\s+"
PROVIDER_REFSPEC = "HEAD:refs/heads/feat/provider-"

# AC-3 / INV-21 / INV-19: constructs neither skill file may contain anywhere.
FORBIDDEN = {
    "gh pr or gh issue": re.compile(r"\bgh\s+(?:pr|issue)\b"),
    "git stash": re.compile(GIT + r"stash\b"),
    "push --force": re.compile(r"\bpush\s+--force\b|" + GIT + r"push\b[^;&|`\n]*\s--force\b"),
    "push -f": re.compile(r"\bpush\s+-f\b|" + GIT + r"push\b[^;&|`\n]*\s-f\b"),
    "--force-with-lease": re.compile(r"--force-with-lease"),
    "+ refspec": re.compile(GIT + r"push\b[^;&|`\n]*\s['\"]?\+\S"),
    "powershell": re.compile(r"\bpowershell\b", flags=re.IGNORECASE),
    "pwsh": re.compile(r"\bpwsh\b"),
    "$env:": re.compile(r"\$env:", flags=re.IGNORECASE),
    ".exe": re.compile(r"\.exe\b", flags=re.IGNORECASE),
    "drive-letter path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),
    # INV-21: a backslash between two path-name characters; backreferences, `\.` and regex classes such as `\s+` are escapes.
    "backslash path": re.compile(r"(?<=[A-Za-z0-9_.-])\\(?=[A-Za-z0-9_.-])(?![0-9.]|[nrtsdwbSDWB](?![A-Za-z0-9_]))"),
    "path:line": re.compile(r"\b[\w./-]+\.(?:py|md|json|toml|ya?ml|txt|cfg|ini|sh):\d+\b"),
}

# INV-16: real key shapes of existing vendors; the prefixes are split so this file holds no key-shaped literal either.
_KEY_SHAPE = re.compile("(?:" + "|".join(("s" + "k-(?:ant-|proj-|or-v1-|admin-|svcacct-)?", "x" + "ai-", "g" + "sk_", "c" + "sk-", "AI" + "za", "ey" + "J", "vb_(?:live|test)_")) + r")[A-Za-z0-9_\-]{16,}|LL" + r"M\|\d{6,}\|")
_NEGATION = re.compile(r"\b(?:never|not|no|untouched|unchanged|without|leave|leaves|left)\b|n't\b", flags=re.IGNORECASE)
_PULLS_CREATE = re.compile(r"(?<![\w/])/?repos/(?:cerredz/Vidbyte-SDK|\$REPO|\$\{REPO\})/pulls(?=[\"'\s]|$)")


# Spec 8.5 "Self-check assertions", as the final provider-run.md spells each one: every relation keeps its polarity.
SELF_CHECK_STATEMENTS = (
    "ProviderModelRegistry.validate_provider_model_pair(SLUG, model)",
    "assert ProviderModelRegistry.provider_for_model(model) == SLUG",
    "assert ModalityDetector.detect_modality(model) is ModelModality.TEXT",
    "price = ModelPricingRegistry.default().resolve(ModelProvider(SLUG), model)",
    "assert price is not None and (price.input_per_million, price.output_per_million, price.cache_read_per_million) == (rate_in, rate_out, rate_cache)",
    'assert Runner(provider=SLUG, model_name=model).resolve_runner_type() == "text"',
    'assert ToolsFormatter.provider_from_model(model) == "openai"',
    "assert Runner._normalize_provider_and_model(None, model)[0] is None",
    'assert Runner(provider=SLUG, model_name=None).resolve_runner_type() == "text"',
    'assert ToolsFormatter.provider_from_model(SLUG) == "openai"',
    "assert ModelProvider(SLUG).usage_class() is not None",
)
MANAGED_SET_RULE = "- Never change `VIDBYTE_MANAGED_TEXT_PROVIDERS` or a gateway relay table: the vendor is DIRECT-only."
# INV-13 / review R-10 and R-12: the URL rule of provider-run.md "Rules for the whole run", final wording at 1cac918e.
URL_RULE_SENTENCES = (
    "- Never invent a URL.",
    "Every URL you write into code, a test, a README or the PR body is either the base URL fact from section 3's Endpoint check (or its scheme and host, as row C7 writes it) or the final URL of a line in `<evidence>/fetch-log.txt` with a 2xx status, so it is a page this run opened.",
    "That covers the pricing and key-source comments, the D1 documentation links and every Sources URL.",
    "A URL you did not fetch never enters the PR, even when you know it.",
    "The one exception is the pull-request attribution line your session's instructions give, which section 9 puts last.",
)
URL_RULE = " ".join(URL_RULE_SENTENCES)
ATTRIBUTION_LAST = "and last, the pull-request attribution line your session's instructions give, if any."
# EC-63 / review R-11: the PR-body local-path guard of section 9 step 1, final wording at 8edfdec1. The raw string keeps
# each `\134` as the four characters the file holds; S9 asserts that before comparing.
GUARD_COMMAND = r'''W="<worktree>"; H="${HOME%/}"; H="${H:-$W}"; { sed -E 's#https?://[^[:space:]]*##g' "<evidence>/pr-body.md" || echo 'pr-body.md was not read'; } | grep -n -F -e "$(basename "$W")" -e "$H" -e "/$(basename "$H")/" -e "$(printf '\134%s\134' "$(basename "$H")")" -e 'pr-body.md was not read'; echo "grep exit $?"'''
GUARD_LEAD = "The body writes `<worktree>` and `<evidence>` for those paths, never an absolute local path, a home directory or a user name. Before the push, this must print `grep exit 1`; look as well for the same paths in their other spelling (with a drive letter, or with a leading `/c/`):"
GUARD_SENTENCES = (
    "It first deletes every `http://` and `https://` URL from the body it reads, because a local path never sits inside one, so a Sources URL segment such as `/app/` or `/dev/` cannot block the push.",
    "It then matches three things.",
    "The first is the worktree's last path segment, which ends in `-onboard-<slug>` and which `<evidence>` and the `-main` twin share, so those paths match in any spelling.",
    "The second is your home directory.",
    "The third is the user name, your home directory's last segment, only as a path segment between two slashes or two backslashes, so an ordinary word that equals a short name does not block the push.",
    "When HOME is `/` or empty, as for a container user with no home directory, the worktree path stands in for it.",
    "A body it cannot read becomes the line `pr-body.md was not read`, which it matches, so a check that did not run never prints `grep exit 1`.",
    r"It has no `-i`, because Git for Windows' grep aborts on `-i -F` in the C locale (exit 134), and it spells the backslash as the octal `\134`, because a doubled backslash can reach the shell as one.",
    "When a printed line holds no local path or user name, as when the match sits inside a quote from a vendor page, end the run `PUBLISH_FAILED push local-path-guard` without pushing.",
    "Otherwise replace every local path and name in each printed line of the body with `<worktree>` or `<evidence>`, and run it once more; when that second run does not print `grep exit 1` either, end the run the same way.",
    "Any exit other than 1 means the body is not yet clean or the check did not run: never push until it prints `grep exit 1`.",
)
PROOF_RULE_SENTENCES = (
    "- Sections 1 to 5 are work: repeat a step until it holds, but start section 5 only after section 4's red record exists.",
    "Sections 6 to 9 are proof: each step runs once on the finished wiring, and its first failure ends the run with `PROOF_FAILED <check>`.",
    "The reruns that section 8 allows, and the body check's rerun in section 9 step 1, are the only repeats, and code never changes after a proof step failed.",
)
PROOF_RULE = " ".join(PROOF_RULE_SENTENCES)

_UNQUOTED_PLACEHOLDER = re.compile(r"(?<![\"'\w])<[a-z][^<>\"']*>(?![\"'\w])")


def _documents() -> tuple[MarkdownDoc, MarkdownDoc]:
    return read_markdown(SKILL_FILE, SKILL_REF), read_markdown(PROCEDURE_FILE, PROCEDURE_REF)


def _python_block(section: MarkdownDoc, marker: str) -> str:
    # The one python fence in a section that holds the marker, with bare <placeholders> made literals so it compiles.
    blocks = ["\n".join(body) for info, body in section.fenced_blocks_with_info() if info == "python" and marker in "\n".join(body)]
    assert len(blocks) == 1, f"{section.label}: expected one python fence holding {marker!r}, found {len(blocks)}"
    return _UNQUOTED_PLACEHOLDER.sub("0", blocks[0])


def _gh_method(command: str) -> str:
    # The HTTP method `gh api` will use: an explicit -X/--method, else POST when fields are sent, else GET.
    explicit = re.search(r"(?:-X|--method)[\s=]*['\"]?([A-Za-z]+)", command)
    if explicit:
        return explicit.group(1).upper()
    return "POST" if re.search(r"\s(?:-f|-F|--field|--raw-field|--input)(?:\s|=)", command) else "GET"


@pytest.mark.parametrize(("path", "spec_ref"), [(SKILL_FILE, SKILL_REF), (PROCEDURE_FILE, PROCEDURE_REF)], ids=["SKILL.md", "provider-run.md"])
def test_skill_files_hold_no_forbidden_construct(path: Path, spec_ref: str) -> None:
    # S1 · AC-3 / AC-8 / INV-21 / INV-19 / D-21: GraphQL-backed gh commands, stash, force pushes, Windows-only constructs
    # and line-number references are absent from every line, prose and fences alike.
    document = read_markdown(path, spec_ref)
    lines = [line.text for line in document.lines if line.text.strip()]

    assert len(lines) >= 50, f"{document.label} has {len(lines)} non-blank lines; the scan needs the real file"
    found = [f"{name}: {line.strip()}" for line in lines for name, pattern in FORBIDDEN.items() if pattern.search(line)]
    assert found == []


def test_github_is_reached_only_through_gh_api_and_the_only_write_is_the_pr_create() -> None:
    # S2 · INV-18 / INV-19 / AC-15 / NG-3 / T-3: no other gh command, no GraphQL, no merge; the orchestrator writes nothing
    # to GitHub; the provider run's one write is POST repos/cerredz/Vidbyte-SDK/pulls with base main and a provider head.
    skill, procedure = _documents()
    every = [(doc.label, command) for doc in (skill, procedure) for command in doc.commands()]

    assert [command for _, command in every if re.search(r"\bgh\s+(?!api\b)[a-z]", command)] == [], "INV-19: GitHub only through `gh api`"
    assert [command for _, command in every if re.search(r"graphql", command, flags=re.IGNORECASE)] == []
    assert [command for _, command in every if re.search(GIT + r"merge(?![\w-])|/merge(?![\w-])|state=closed", command)] == [], "AC-15: never merge or close"
    writes = [(label, command) for label, command in every if re.search(r"\bgh\s+api\b", command) and "repos/" in command and _gh_method(command) != "GET"]
    assert [command for label, command in writes if label == skill.label] == [], "the orchestrator makes no GitHub write"
    bad = [command for _, command in writes if not (_gh_method(command) == "POST" and _PULLS_CREATE.search(command) and re.search(r"\bbase=main\b", command) and re.search(r"\bhead=(?:cerredz:)?feat/provider-", command))]
    assert bad == [], "the only GitHub write is the PR create against main"
    assert any(label == procedure.label for label, _ in writes), "## 9. Publish must create the PR with `gh api -X POST repos/cerredz/Vidbyte-SDK/pulls`"


def test_every_push_is_the_single_unforced_provider_refspec() -> None:
    # S3 · INV-18 / NFR-4 / AC-15 / T-3: every push names HEAD:refs/heads/feat/provider-<slug> and nothing that forces,
    # deletes, mirrors or reaches main; at least one such push sits in Publish.
    skill, procedure = _documents()
    pushes = [command for doc in (skill, procedure) for command in doc.commands() if re.search(GIT + r"push\b", command)]

    bad = [command for command in pushes if PROVIDER_REFSPEC not in command or re.search(r"(?:^|\s)(?:\+\S|-f\b|--force\S*|--delete\b|-d\b|--mirror\b|--all\b|--tags\b|--prune\b)|\bmain\b", command)]
    assert bad == []
    assert [command for command in procedure.section("## 9. Publish").commands() if re.search(GIT + r"push\b", command)], "## 9. Publish pushes the provider refspec once"


def test_the_managed_text_provider_set_is_only_ever_named_as_untouched() -> None:
    # S4 · INV-14 / D-12 / AC-15: adding a vendor to VIDBYTE_MANAGED_TEXT_PROVIDERS makes AUTO route it to a gateway that
    # does not serve it; the skill names the set only to forbid changing it, and the PR states DIRECT mode.
    skill, procedure = _documents()
    mentions = [line.text for doc in (skill, procedure) for line in doc.lines if "VIDBYTE_MANAGED_TEXT_PROVIDERS" in line.text]

    assert any("VIDBYTE_MANAGED_TEXT_PROVIDERS" in line.text for line in procedure.lines), "provider-run.md must forbid changing the managed set"
    assert [line.strip() for line in mentions if not _NEGATION.search(line)] == []
    assert "TextModelMode.DIRECT" in procedure.text, "D-12: the PR says the vendor works only with mode=TextModelMode.DIRECT"

    # Re-review round 1 (R-3 class): a line can hold a negation and still tell the run to add the vendor ("Add the
    # vendor to VIDBYTE_MANAGED_TEXT_PROVIDERS, never to a relay table"), so the instruction is forbidden as such and the
    # rule is compared whole.
    assert [line.strip() for line in mentions if re.search(r"\b(?:add|adds|put|append|include|register|insert)\b[^.;:]*VIDBYTE_MANAGED_TEXT_PROVIDERS", line, flags=re.IGNORECASE)] == [], "D-12: no line tells the run to add the vendor to the managed set"
    assert MANAGED_SET_RULE in _rules_for_the_whole_run(procedure), "D-12: the procedure's rule keeps its final wording"


def test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it() -> None:
    # S5 · D-29 / D-14 / INV-12 / R-1 (review r2): a one-slash ID whose first segment is a ModelProvider value is routed
    # to that provider when provider= is omitted, so Qualify refuses it and the self-check asserts the rule holds.
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    fragments = ("ProviderModelRegistry.validate_provider_model_pair(", "ProviderModelRegistry.provider_for_model(", "ModalityDetector.detect_modality(", "ModelPricingRegistry.default().resolve(", "resolve_runner_type()", "model_name=None", "ToolsFormatter.provider_from_model(", "usage_class()", "Runner._normalize_provider_and_model(None")

    assert "_normalize_provider_and_model" in procedure.section("## 3. Qualify").text
    assert [fragment for fragment in fragments if fragment not in procedure.section("## 6. Self-check").text] == []
    assert all(callable(getattr(owner, name, None)) for owner, name in ((ProviderModelRegistry, "validate_provider_model_pair"), (ProviderModelRegistry, "provider_for_model"), (ModalityDetector, "detect_modality"), (ModelPricingRegistry, "default"), (Runner, "resolve_runner_type"), (ToolsFormatter, "provider_from_model"), (ModelProvider, "usage_class")))
    derived = {f"{case}/example-model-1": Runner._normalize_provider_and_model(None, f"{case}/example-model-1")[0] for member in ModelProvider for case in (member.value, member.value.upper())}
    assert derived and [model for model, provider in derived.items() if provider is None] == [], "D-29 relies on a provider-prefixed ID deriving its provider"
    assert Runner._normalize_provider_and_model(None, "example-labs/example-model-1")[0] is None

    # Review R-3: the rule is pinned by its content, so an inverted condition or a bare call fails, not only a deletion.
    qualify = procedure.section("## 3. Qualify")
    qualify_prose = qualify.prose_lines()
    assert any(re.search(r"`Runner\._normalize_provider_and_model\(None, <id>\)\[0\]` is None\b", line) and "Otherwise `no-usable-model-id`" in line for line in qualify_prose), "D-29: Qualify's prose makes eligibility require the derived provider to be None"
    assert not [line for line in qualify_prose if re.search(r"_normalize_provider_and_model\([^)]*\)\[0\]`? is not None", line)], "D-29 inverted: a derived provider must make an ID ineligible"
    eligible = [line for line in qualify_prose if "An ID is eligible when its line reads" in line]
    assert len(eligible) == 1 and "derived provider None" in eligible[0], "the probe's eligibility reading requires `derived provider None`"
    probe = [line.text for line in qualify.lines if line.kind == "code"]
    assert any("derived provider {Runner._normalize_provider_and_model(None, model)[0]}" in line for line in probe), "the Qualify probe prints the derived provider it judges"
    compile(_python_block(qualify, "_normalize_provider_and_model"), "qualify_ids.py", "exec")
    self_check = procedure.section("## 6. Self-check")
    script = [line.text.strip() for line in self_check.lines if line.kind == "code"]
    assert [statement for statement in SELF_CHECK_STATEMENTS if sum(line.startswith(statement) for line in script) != 1] == [], "each section 8.5 self-check relation is one statement with its polarity, never a bare call"
    compile(_python_block(self_check, "self-check passed"), "self_check.py", "exec")


def test_format_binding_needs_a_first_party_statement_not_an_example_key() -> None:
    # S7 · D-13 / EC-33 / review R-8: a vendor joins FORMAT_BOUND_PROVIDERS only on a quoted first-party statement that its
    # keys begin with P; bound on an example key alone, it refuses its own unprefixed key and elimination hands that key
    # to another vendor, the cross-vendor leak the swap tests exist for.
    qualify_prose = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 3. Qualify").prose_lines()
    bound = [line for line in qualify_prose if "FORMAT_BOUND_PROVIDERS" in line]

    assert any("Add the vendor to `FORMAT_BOUND_PROVIDERS` (row C2) only with a quoted first-party statement that its keys begin with P." in line and "An example key alone is not enough" in line for line in bound), "D-13: format binding needs a quoted first-party statement, and an example key alone is not enough"
    assert not [line for line in qualify_prose if re.search(r"example key (?:alone )?is enough|whenever an example key", line, flags=re.IGNORECASE)], "D-13 inverted: an example key must never be enough to bind the format"


def _rules_for_the_whole_run(procedure: MarkdownDoc) -> list[str]:
    # The bullets under "Rules for the whole run:", which sits before the first H2 of provider-run.md.
    starts = [index for index, line in enumerate(procedure.lines) if line.kind == "prose" and line.text.strip() == "Rules for the whole run:"]
    assert len(starts) == 1, "provider-run.md holds one 'Rules for the whole run:' block"
    end = next(index for index in range(starts[0], len(procedure.lines)) if procedure.lines[index].kind == "prose" and procedure.lines[index].text.startswith("## "))
    return [line.text.strip() for line in procedure.lines[starts[0] + 1 : end] if line.kind == "prose" and line.text.startswith("- ")]


def test_every_url_a_run_writes_was_fetched_and_only_the_attribution_line_is_exempt() -> None:
    # S8 · INV-13 / request section D ("Never invent a URL") / review R-10 and R-12: the URL rule is one rules bullet,
    # word for word, so deleting it, inverting it to "may enter the PR", or widening its one exception fails here.
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    rules = _rules_for_the_whole_run(procedure)

    assert [rule for rule in rules if "invent a URL" in rule] == [URL_RULE], "INV-13: the URL rule keeps its final wording, its one exception included"
    assert not [line for line in procedure.prose_lines() if re.search(r"\b(?:may|can|might) enter the PR\b|\bmay invent\b|\bunless you (?:did not fetch|know)\b", line)], "INV-13 inverted: an unfetched URL never enters the PR"
    publish = procedure.section("## 9. Publish").prose_lines()
    assert len([line for line in publish if ATTRIBUTION_LAST in line]) == 1, "R-12: section 9 puts the attribution line last, as the exception says"


def test_the_pr_body_guard_is_the_exact_command_and_ends_in_a_named_outcome() -> None:
    # S9 · NFR-1 / D-16 / EC-63 / FR-10 / review R-11: the local-path guard is one exact command, its paragraph is
    # pinned whole (URL strip, worktree name, HOME fallback, unreadable body, one bounded rerun, the outcome), and the
    # one-shot proof rule allows exactly that rerun, so a guard that keeps matching ends the run instead of looping.
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    publish = procedure.section("## 9. Publish")

    assert GUARD_COMMAND.count("\\134") == 2 and "\\\\" not in GUARD_COMMAND, "the pinned guard spells each backslash as the octal escape, as the file does"
    assert [command for command in publish.shell_commands() if "pr-body.md" in command and "grep" in command] == [GUARD_COMMAND], "EC-63: section 9 step 1 runs the guard exactly as pinned"
    prose = [line.strip() for line in publish.prose_lines()]
    assert [line for line in prose if line.startswith("The body writes `<worktree>`")] == [GUARD_LEAD], "the body names no local path, and the guard must print grep exit 1 before the push"
    assert [line for line in prose if line.startswith("It first deletes every")] == [" ".join(GUARD_SENTENCES)], "EC-63: the guard paragraph keeps its final wording, outcome and one bounded rerun included"
    assert procedure.text.count("local-path-guard") == procedure.text.count("`PUBLISH_FAILED push local-path-guard`") >= 1, "EC-63: the guard's only outcome is PUBLISH_FAILED push local-path-guard"
    assert not [line for line in procedure.prose_lines() if re.search(r"\brun it (?:again|until)\b|\brepeat (?:it|the check) until\b", line)], "the guard reruns once, never until it passes"
    assert [rule for rule in _rules_for_the_whole_run(procedure) if rule.startswith("- Sections 1 to 5 are work")] == [PROOF_RULE], "the one-shot proof rule allows only section 8's reruns and the body check's one rerun"


def test_no_literal_key_shape_appears_and_fakes_are_built_by_concatenation() -> None:
    # S6 · INV-16 / S062 / section 12.4: no key-shaped literal in the skill (push protection, leaked-key scanners), and the
    # procedure tells provider runs to build fakes by `+` concatenation.
    skill, procedure = _documents()

    assert [match.group(0)[:6] for doc in (skill, procedure) for match in _KEY_SHAPE.finditer(doc.text)] == []
    assert re.search(r"concatenat", procedure.text, flags=re.IGNORECASE)
