"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_security.py

PURPOSE: Prove the /onboard-model-provider skill cannot instruct the writes and leaks its threat model rules out: no Windows-only construct, `gh pr`, `gh issue`, `git stash`, force push or `path:line`; GitHub only through `gh api`, with one PR-create POST as the only write; one push of the single provider refspec; no change to VIDBYTE_MANAGED_TEXT_PROVIDERS; the D-29 rule that keeps a provider-prefixed model ID from being catalogued under the wrong vendor; and no literal key shape.
ROLE IN CODEBASE: Security layer of tests/features/onboard_model_provider_skill/ (spec AC-3, AC-15, AC-8 "never git stash"; INV-8, INV-12, INV-14, INV-16, INV-18, INV-19, INV-21; NFR-4; D-12, D-29; threats T-1 to T-4).
ARCHITECTURE NOTE: The skill runs with push rights under a person's identity, often in auto or bypassPermissions mode (D-27), so its text is the control. Each scan reads both files whole, prose and fences alike, because an agent follows a prose instruction as readily as a command; each scan also asserts the file is long enough to have been scanned. The D-29 test also checks the runtime behaviour the rule relies on, so a change to Runner's provider derivation fails here. Rules are pinned by their content, not by a token (review R-3): the D-29 condition must read "is None" in prose, every self-check relation must keep its polarity as a statement, and both python fences must compile, so an inverted condition or an assert turned into a bare call fails.
FUNCTION INVENTORY: test_skill_files_hold_no_forbidden_construct (S1); test_github_is_reached_only_through_gh_api_and_the_only_write_is_the_pr_create (S2); test_every_push_is_the_single_unforced_provider_refspec (S3); test_the_managed_text_provider_set_is_only_ever_named_as_untouched (S4); test_qualify_rejects_provider_prefixed_ids_and_the_self_check_proves_it (S5); test_no_literal_key_shape_appears_and_fakes_are_built_by_concatenation (S6); test_format_binding_needs_a_first_party_statement_not_an_example_key (S7).
COMMON MODIFICATION PATTERNS: When the spec allows a new GitHub write or a new git ref, change the spec first, then the matching pattern here. Keep the forbidden patterns literal enough that a reviewer can read them.
WHAT NOT TO DO IN THIS FILE: 1. Do not call GitHub, git or a vendor. 2. Do not write a real key, or a literal that looks like one, into this file: S6 patterns are built from short pieces. 3. Do not assert that a seed slug is or is not a ModelProvider member.
KNOWN EDGE CASES: `git worktree remove --force` is allowed (not a push). Regex and sed escapes (an escaped pipe, an escaped group parenthesis, a backreference, an escaped dot, a class such as the whitespace class) are not Windows paths. A pytest node ID `file.py::Test` is not a `path:line` reference. A `gh api -X POST` fragment in prose with no endpoint is a mention, not a command.
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


def test_no_literal_key_shape_appears_and_fakes_are_built_by_concatenation() -> None:
    # S6 · INV-16 / S062 / section 12.4: no key-shaped literal in the skill (push protection, leaked-key scanners), and the
    # procedure tells provider runs to build fakes by `+` concatenation.
    skill, procedure = _documents()

    assert [match.group(0)[:6] for doc in (skill, procedure) for match in _KEY_SHAPE.finditer(doc.text)] == []
    assert re.search(r"concatenat", procedure.text, flags=re.IGNORECASE)
