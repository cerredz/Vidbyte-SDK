"""FILE: tests/features/harness_compose/test_harness_compose_validation.py

PURPOSE: Validate first (AC-14, INV-3, INV-5, INV-9, INV-10, INV-18, INV-24, INV-36, D-3, EC-35, EC-39 to EC-48, EC-62, EC-76, EC-77, EC-79): every invalid input is refused with ConfigurationError whose details["field"] names the argument path and whose message never quotes a key, and after the refusal no git process or vendor launcher has started, no temporary folder or Grok home exists and the workspace is untouched; a chain or later-stage template that renders blank once every spliced value is empty is refused the same way, naming the template and the step that could be sent a blank prompt, while a chain template that holds {prompt} is never refused as blank and runs; an alias given a missing or misspelled step keyword raises TypeError when awaited, and a positional step fails at the call itself; the new RecordFieldValidator.command_line_units counts one argument as CreateProcess does, and require_command_line_units keeps its result and its exact error at that count.
ROLE IN CODEBASE: Start here when a composite starts git or a step before refusing an input, or names the wrong argument.
ARCHITECTURE NOTE: The workspace is a repository with one commit, so a composite that ran its git checks before validating would show git children in the CliRunner spy; the stand-in log folder shows any vendor launch. Record-level refusals (StageSpec, EnsembleRoster) happen when the record is built, so their field is the `<Record>.<field>` name of spec §9.1.
FUNCTION INVENTORY: unrelated_async is a callable that is not one of the nine; Inputs builds the valid and invalid steps a case needs; CASES maps each case to the call that must be refused; BLANK_CASES maps each blank template to its call, its field and the step its refusal names; nothing_started checks that a refusal left no child, launch, folder, Grok home or workspace change; UNIT_CASES pairs a value with its hand-counted command-line units; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new refusal is one CASES entry and one parametrize row naming the expected field.
WHAT NOT TO DO IN THIS FILE: Do not make the workspace a non-repository here; the git-free proof depends on git being reachable.
KNOWN EDGE CASES: A 24,000-character caller prompt fits a Grok writer exactly, so the too-long prompt cases put it in front of a Grok reader or a later Grok step, where the fixed prompt files add to it.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-3, INV-5, INV-18, INV-24, INV-36, §6.2 AC-14, §6.3 EC-35, EC-39 to EC-48, EC-62, EC-76, EC-77, EC-79, §9.1; docs/spec/native-thread-compose/review.md R-13, R-32
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_validation.py
"""

from __future__ import annotations

import functools
import inspect

import pytest

THREAD_ID = "0192f0c4-beef-7bee-8f00-000000000002"
LONG_PROMPT = "x" * 24_000
LONG_STAGE_TEMPLATE = "y" * 23_990 + " {previous}"
UNIT_CASES = (
    pytest.param("", 2, id="empty argument becomes two quotes"),
    pytest.param("abc", 3, id="plain ascii"),
    pytest.param("a b", 5, id="space wraps the argument in quotes"),
    pytest.param("tab\there", 10, id="tab wraps the argument in quotes"),
    pytest.param('say "hi"', 12, id="each quote is escaped inside the wrapping quotes"),
    pytest.param("é", 1, id="one BMP letter is one unit"),
    pytest.param("\U0001f600", 2, id="one astral character is two units"),
)


async def unrelated_async(prompt: str, *, api_key: str, workspace: str) -> None:
    return None


class Inputs:
    """The valid steps a case builds on, and the invalid values it swaps in."""

    def __init__(self, api, steps, sandbox, pack) -> None:
        self.api, self.steps, self.sandbox, self.pack = api, steps, sandbox, pack
        self.compose = api.compose
        self.records = api.records
        self.other = sandbox.root / "ws2"
        self.other.mkdir(exist_ok=True)

    def grok(self, **fields):
        return self.steps.bind("grok", **fields)

    def plan(self, **fields):
        return self.steps.bind("grok", plan=True, **fields)

    def opencode(self, **fields):
        return self.steps.bind("opencode", **fields)

    def muse(self, **fields):
        return self.steps.bind("muse", **fields)

    def fork(self, harness: str = "grok", **fields):
        return self.steps.bind(harness, "fork", **fields)

    def raw(self, function, harness: str, verb: str = "run"):
        api = self.api
        return self.records.ThreadStep(function=function, harness=api.NativeHarness(harness), verb=api.NativeThreadVerb(verb), api_key=self.pack.API_KEY, workspace=self.sandbox.workspace, config=self.steps.config(harness, label="raw"))

    def stage(self, step, template: str = "Review: {previous}", **fields):
        return self.records.StageSpec(step=step, template=template, **fields)

    def roster(self, **roles):
        values = {"planner": self.plan(label="planner"), "proposers": [self.plan(label="proposer")], "selector": self.plan(label="selector"), "implementer": self.grok(edits=True, label="implementer")}
        values.update(roles)
        return self.api.ensemble.EnsembleRoster(**values)

    def chain(self, steps, template=None, prompt=None):
        return self.compose.chain_threads(steps, template, prompt=prompt or self.pack.PROMPT)

    def verify(self, writer, verifiers, prompt=None):
        return self.compose.verify_with(writer, verifiers, prompt=prompt or self.pack.PROMPT)


def _template(inputs: Inputs, template: str):
    return inputs.chain([inputs.grok(), inputs.grok()], template)


CASES = {
    # INV-3: anything that is not a checked step, wherever a step goes.
    "harness name in steps": lambda i: i.chain([i.grok(), "grok"]),
    "key string in steps": lambda i: i.chain([i.grok(), i.pack.API_KEY]),
    "bare function in steps": lambda i: i.chain([i.grok(), i.api.functions[("grok", "run")]]),
    "partial in steps": lambda i: i.chain([i.grok(), functools.partial(i.api.functions[("grok", "run")], api_key=i.pack.API_KEY)]),
    "step of an unknown function": lambda i: i.chain([i.grok(), i.raw(unrelated_async, "grok")]),
    "step whose harness differs from its function": lambda i: i.chain([i.grok(), i.raw(i.api.functions[("opencode", "run")], "grok")]),
    "step whose verb differs from its function": lambda i: i.chain([i.grok(), i.raw(i.api.functions[("grok", "run")], "grok", "fork")]),
    "unanchored fork in a chain": lambda i: i.chain([i.fork(), i.grok()]),
    "one chain step": lambda i: i.chain([i.grok()]),
    "26 chain steps": lambda i: i.chain([i.grok()] * 26),
    # INV-5 / EC-39 / EC-40: templates.
    "unknown template field": lambda i: _template(i, "{previous} {nope}"),
    "positional template field": lambda i: _template(i, "{previous} {}"),
    "attribute template field": lambda i: _template(i, "{previous} {prompt.upper}"),
    "indexed template field": lambda i: _template(i, "{previous} {prompt[0]}"),
    "template conversion": lambda i: _template(i, "{previous!r}"),
    "template format spec": lambda i: _template(i, "{previous:>5}"),
    "unmatched opening brace": lambda i: _template(i, "{previous} {"),
    "unmatched closing brace": lambda i: _template(i, "{previous} }"),
    "chain template without previous": lambda i: _template(i, "Do this: {prompt}"),
    # INV-5 / EC-41 / INV-21: stages.
    "first stage uses previous": lambda i: i.compose.run_staged_threads([i.stage(i.grok(), "Start from {previous}")]),
    "stage template with another field": lambda i: i.stage(i.grok(), "Start from {prompt}"),
    "stage step of an unknown function": lambda i: i.compose.run_staged_threads([i.stage(i.grok(), "Start."), i.stage(i.grok()), i.stage(i.raw(unrelated_async, "grok"))]),
    "no stages": lambda i: i.compose.run_staged_threads([]),
    "26 stages": lambda i: i.compose.run_staged_threads([i.stage(i.grok(), "Start.")] + [i.stage(i.grok())] * 25),
    "four retries": lambda i: i.stage(i.grok(), "Start.", retries=4),
    "ladder config of another harness": lambda i: i.stage(i.grok(), "Start.", ladder=(i.api.configs["opencode"](),)),
    "five ladder configs": lambda i: i.stage(i.grok(), "Start.", ladder=tuple(i.api.configs["grok"]() for _rung in range(5))),
    "stage template too long for grok": lambda i: i.compose.run_staged_threads([i.stage(i.opencode(), "Start."), i.stage(i.grok(), LONG_STAGE_TEMPLATE)]),
    # INV-9 / INV-10 / EC-44 / EC-46 / EC-47 / EC-48: verifiers.
    "unanchored fork verifier": lambda i: i.verify(i.opencode(), [i.fork()]),
    "grok verifier with accept edits": lambda i: i.verify(i.opencode(), [i.grok(edits=True)]),
    "grok verifier with dont ask": lambda i: i.verify(i.opencode(), [i.grok(permission_mode=i.api.GrokPermissionMode.DONT_ASK)]),
    "opencode continue verifier": lambda i: i.verify(i.grok(edits=True), [i.steps.bind("opencode", "continue", THREAD_ID)]),
    "muse anchored fork verifier": lambda i: i.verify(i.grok(edits=True), [i.steps.bind("muse", "fork", THREAD_ID)]),
    "verifier on another workspace": lambda i: i.verify(i.opencode(), [i.plan(workspace=i.other)]),
    "no verifiers": lambda i: i.verify(i.opencode(), []),
    "11 verifiers": lambda i: i.verify(i.opencode(), [i.plan()] * 11),
    "writer that is not a step": lambda i: i.verify("opencode", [i.plan()]),
    # INV-18 / EC-35: a caller prompt the
    # fixed prompt files leave no room for.
    "prompt too long for a grok verifier": lambda i: i.verify(i.opencode(), [i.plan()], prompt=LONG_PROMPT),
    "prompt too long for a later grok step": lambda i: i.chain([i.opencode(), i.grok()], prompt=LONG_PROMPT),
    "prompt too long for a grok planner": lambda i: i.compose.run_ensemble(LONG_PROMPT, i.roster()),
    # INV-24 / EC-42: aliases check each step's harness.
    "pair alias step on the wrong harness": lambda i: i.compose.run_opencode_then_grok(i.pack.PROMPT, opencode=i.grok(), grok=i.grok()),
    "trio alias writer on the wrong harness": lambda i: i.compose.run_grok_verify_with_opencode_and_muse(i.pack.PROMPT, writer=i.opencode(), opencode=i.opencode(), muse=i.muse()),
    "trio alias reader on the wrong harness": lambda i: i.compose.run_grok_verify_with_opencode_and_muse(i.pack.PROMPT, writer=i.grok(edits=True), opencode=i.opencode(), muse=i.plan()),
    # INV-2 / EC-43: binders.
    "bind_thread of a continue function": lambda i: i.compose.bind_thread(i.api.functions[("grok", "continue")], api_key=i.pack.API_KEY, workspace=i.sandbox.workspace),
    # INV-5 / EC-44 / EC-76: handoff.
    "run step as from_thread": lambda i: i.compose.handoff_thread(i.grok(), i.opencode()),
    "unanchored fork as from_thread": lambda i: i.compose.handoff_thread(i.fork(), i.opencode()),
    "unanchored fork as to_step": lambda i: i.compose.handoff_thread(i.steps.bind("grok", "continue", THREAD_ID), i.fork()),
    # D-3 / EC-44 / EC-45 / INV-10 / EC-48: ensemble roles.
    "no proposers": lambda i: i.roster(proposers=[]),
    "11 proposers": lambda i: i.roster(proposers=[i.plan()] * 11),
    "unanchored fork planner": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(planner=i.fork(plan=True))),
    "opencode fork proposer": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(proposers=[i.fork("opencode")])),
    "grok fork proposer under an opencode planner": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(planner=i.opencode(), proposers=[i.fork(plan=True)])),
    "grok proposer with accept edits": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(proposers=[i.grok(edits=True)])),
    "proposer on another workspace": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(proposers=[i.plan(workspace=i.other)])),
    "selector with accept edits": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(selector=i.grok(edits=True))),
    "unanchored fork implementer under an opencode planner": lambda i: i.compose.run_ensemble(i.pack.TASK, i.roster(planner=i.opencode(), proposers=[i.opencode()], implementer=i.fork(edits=True))),
    # INV-3 / §9.2: parse_json_answer
    # takes any step but an unanchored fork.
    "unanchored fork to parse_json_answer": lambda i: i.compose.parse_json_answer(i.fork(), i.pack.PROMPT, schema="{}", parse=dict),
    "string to parse_json_answer": lambda i: i.compose.parse_json_answer("grok", i.pack.PROMPT, schema="{}", parse=dict),
}

FIELDS = {
    "harness name in steps": "steps[1]", "key string in steps": "steps[1]", "bare function in steps": "steps[1]", "partial in steps": "steps[1]",
    "step of an unknown function": "steps[1]", "step whose harness differs from its function": "steps[1]", "step whose verb differs from its function": "steps[1]",
    "unanchored fork in a chain": "steps[0]", "one chain step": "steps", "26 chain steps": "steps",
    "unknown template field": "template", "positional template field": "template", "attribute template field": "template", "indexed template field": "template",
    "template conversion": "template", "template format spec": "template", "unmatched opening brace": "template", "unmatched closing brace": "template",
    "chain template without previous": "template",
    "first stage uses previous": "stages[0].template", "stage template with another field": "StageSpec.template", "stage step of an unknown function": "stages[2].step",
    "no stages": "stages", "26 stages": "stages", "four retries": "StageSpec.retries", "ladder config of another harness": "StageSpec.ladder", "five ladder configs": "StageSpec.ladder",
    "stage template too long for grok": "stages[1].template",
    "unanchored fork verifier": "verifiers[0]", "grok verifier with accept edits": "verifiers[0]", "grok verifier with dont ask": "verifiers[0]",
    "opencode continue verifier": "verifiers[0]", "muse anchored fork verifier": "verifiers[0]", "verifier on another workspace": "verifiers[0]",
    "no verifiers": "verifiers", "11 verifiers": "verifiers", "writer that is not a step": "writer",
    "prompt too long for a grok verifier": "prompt", "prompt too long for a later grok step": "prompt", "prompt too long for a grok planner": "prompt",
    "pair alias step on the wrong harness": "opencode", "trio alias writer on the wrong harness": "writer", "trio alias reader on the wrong harness": "muse",
    "bind_thread of a continue function": "function",
    "run step as from_thread": "from_thread", "unanchored fork as from_thread": "from_thread", "unanchored fork as to_step": "to_step",
    "no proposers": "EnsembleRoster.proposers", "11 proposers": "EnsembleRoster.proposers", "unanchored fork planner": "roster.planner",
    "opencode fork proposer": "roster.proposers[0]", "grok fork proposer under an opencode planner": "roster.proposers[0]", "grok proposer with accept edits": "roster.proposers[0]",
    "proposer on another workspace": "roster.proposers[0]", "selector with accept edits": "roster.selector",
    "unanchored fork implementer under an opencode planner": "roster.implementer",
    "unanchored fork to parse_json_answer": "step", "string to parse_json_answer": "step",
}


# EC-79: each case is (the call, the refused field, the step the
# message names as the one a blank prompt could reach).
BLANK_CASES = {
    "previous alone": (lambda i: _template(i, "{previous}"), "template", "steps[1]"),
    "previous with whitespace around it": (lambda i: _template(i, "  {previous} \n\t"), "template", "steps[1]"),
    "previous and diff": (lambda i: _template(i, "{previous}{diff}"), "template", "steps[1]"),
    "previous alone in the second stage": (lambda i: i.compose.run_staged_threads([i.stage(i.grok(), "Start."), i.stage(i.grok(), "{previous}")]), "stages[1].template", "stages[1].step"),
    "previous with whitespace in the third stage": (lambda i: i.compose.run_staged_threads([i.stage(i.grok(), "Start."), i.stage(i.grok()), i.stage(i.grok(), " \n{previous}\n ")]), "stages[2].template", "stages[2].step"),
}
# EC-79 / R-32: templates that hold {prompt}, each with the text
# between the caller's prompt and the previous answer.
PROMPT_TEMPLATES = {
    "prompt then previous": ("{prompt}{previous}", ""),
    "prompt and previous on two lines": ("{prompt}\n{previous}", "\n"),
}


def nothing_started(sandbox, runs, before: tuple) -> None:
    # After a refusal: no child process, no launch, no temporary
    # folder, no Grok home and no change to the workspace.
    assert runs.invocations == [], f"a child started before the refusal: {[item.argv for item in runs.invocations]}"
    assert sandbox.launches() == []
    assert sandbox.leftovers() == []
    assert not (sandbox.home / ".vidbyte").exists()
    assert (sandbox.status(), sandbox.files(), sandbox.refs(), sandbox.worktrees()) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(CASES))
async def test_invalid_input_is_refused_before_any_git_launch_or_folder(compose_api, sandbox, steps, runs, pack, case) -> None:
    # AC-14 / INV-5: ConfigurationError naming the argument path, no key
    # in its message or details, and nothing started or created.
    api = compose_api
    assert set(CASES) == set(FIELDS), "every case names its expected field"
    sandbox.make_repo()
    before = (sandbox.status(), sandbox.files(), sandbox.refs(), sandbox.worktrees())
    inputs = Inputs(api, steps, sandbox, pack)
    with pytest.raises(api.ConfigurationError) as caught:
        outcome = CASES[case](inputs)
        if inspect.isawaitable(outcome):
            await outcome
    error = caught.value
    assert error.details.get("field") == FIELDS[case], f"{case}: {error} {error.details}"
    assert pack.API_KEY not in str(error) and pack.API_KEY not in repr(error.details)
    assert runs.invocations == [], f"{case}: a child started before the refusal: {[item.argv for item in runs.invocations]}"
    assert sandbox.launches() == []
    assert sandbox.leftovers() == []
    assert not (sandbox.home / ".vidbyte").exists()
    assert (sandbox.status(), sandbox.files(), sandbox.refs(), sandbox.worktrees()) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(BLANK_CASES))
async def test_a_template_blank_without_its_spliced_values_is_refused_before_any_io(compose_api, sandbox, steps, runs, pack, case) -> None:
    # EC-79 / INV-18 / INV-5: rendered with every spliced value
    # empty, the template is blank, so a blank answer would give the
    # next step a blank prompt. ConfigurationError names the
    # template and the step at risk before any git command or step.
    # Red until review R-13 lands: such a chain ran its steps.
    api = compose_api
    call, field, step_name = BLANK_CASES[case]
    sandbox.make_repo()
    before = (sandbox.status(), sandbox.files(), sandbox.refs(), sandbox.worktrees())
    with pytest.raises(api.ConfigurationError) as caught:
        await call(Inputs(api, steps, sandbox, pack))
    error = caught.value
    assert error.details.get("field") == field, f"{case}: {error} {error.details}"
    assert step_name in str(error), f"the refusal names {step_name}, the step a blank prompt could reach: {error}"
    nothing_started(sandbox, runs, before)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(PROMPT_TEMPLATES))
async def test_a_chain_template_that_holds_prompt_is_never_refused_as_blank(compose_api, sandbox, steps, pack, case) -> None:
    # EC-79 / INV-18: the blank check renders {prompt} as the
    # caller's prompt, which is never blank, so a template that holds
    # it is accepted and the chain runs: the second step gets the
    # caller's prompt and the first answer. Red at HEAD until review
    # R-32 lands: the check refuses these templates as blank.
    api = compose_api
    template, joiner = PROMPT_TEMPLATES[case]
    first = steps.bind("opencode", label="first", fake={"final_parts": ["FIRST-ANSWER-5c1e"]})
    second = steps.bind("grok", label="second")
    result = await api.compose.chain_threads([first, second], template, prompt=pack.PROMPT)
    assert result.failed_step is None and len(result.outcomes) == 2
    assert pack.launch_prompt(sandbox.only_launch("second")) == pack.PROMPT + joiner + "FIRST-ANSWER-5c1e"


@pytest.mark.asyncio
async def test_alias_keyword_mistakes_raise_type_error_before_anything_runs(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-77 / INV-24: Signature.bind runs first inside the coroutine, so
    # a misspelled or missing keyword is a TypeError on await naming it;
    # a positional step fails at the call itself.
    api = compose_api
    sandbox.make_repo()
    writer, grok, muse = steps.bind("opencode"), steps.bind("grok", plan=True), steps.bind("muse")
    alias = api.compose.run_opencode_verify_with_grok_and_muse
    misspelled = alias(pack.PROMPT, writer=writer, grok=grok, muze=muse)
    with pytest.raises(TypeError) as caught:
        await misspelled
    assert "muze" in str(caught.value)
    missing = alias(pack.PROMPT, writer=writer, grok=grok)
    with pytest.raises(TypeError) as caught:
        await missing
    assert "muse" in str(caught.value)
    with pytest.raises(TypeError):
        alias(pack.PROMPT, writer, grok, muse)
    pair = api.compose.run_grok_then_muse(pack.PROMPT, grok=grok, opencode=writer)
    with pytest.raises(TypeError) as caught:
        await pair
    assert "opencode" in str(caught.value) or "muse" in str(caught.value)
    assert runs.invocations == [] and sandbox.launches() == [] and sandbox.leftovers() == []


@pytest.mark.parametrize(("value", "units"), UNIT_CASES)
def test_command_line_units_is_the_count_require_command_line_units_enforces(compose_api, value, units) -> None:
    # INV-36 / §8.5: the new helper counts one argument
    # as CreateProcess does (quoted as subprocess quotes
    # it, in UTF-16 code units; the expected counts are
    # worked out by hand), and the existing check keeps
    # its result and its exact error at that boundary.
    validator = compose_api.RecordFieldValidator
    assert validator.command_line_units(value) == units
    assert validator.require_command_line_units(value, "prompt", max_units=units) is value
    with pytest.raises(compose_api.ConfigurationError) as caught:
        validator.require_command_line_units(value, "prompt", max_units=units - 1)
    assert str(caught.value) == f"prompt must take at most {units - 1} UTF-16 code units once quoted for the Windows command line; got {units}."
    assert caught.value.details == {"field": "prompt"}
