"""FILE: tests/features/harness_compose/test_harness_compose_keys.py

PURPOSE: Key hygiene (AC-15, INV-4, INV-5, INV-6, INV-26, T-3, D-28, EC-71): with every step bound to its own distinctive key and stand-ins that print keys into answers, plans, proposals, guidance and files, no fragment of any bound key reaches a later step's prompt or argv (COMPOSE_REDACTED_KEY stands in its place), any git argv or environment, the repr of a ThreadStep, StageSpec or EnsembleRoster, a ThreadComposeError's message or any attribute but result and diff (also when git's own text or a changed file's name holds the key), or a ConfigurationError, whether the caller put a key in a bad template or in any caller text that compose refuses (every composite's and alias's prompt, the chain and stage templates, the schema, a thread id, either binder's model); the records keep the raw text, error.result and error.diff included; each key reaches only its own step's child; os.environ is unchanged.
ROLE IN CODEBASE: Start here when a key shows up anywhere compose produced text.
ARCHITECTURE NOTE: Keys are random placeholders (fresh_key, short_key), and leaks are searched as every 12-character fragment, so a partly scrubbed key is still caught. Prompts and argv are read from the stand-in logs, git children from the CliRunner spy. The stand-in scenarios hold the keys as answer text, the way a model would print them; the stand-in logs credentials only as digests.
FUNCTION INVENTORY: assert_clean fails with the leaked fragments; credential_digests lists the key digests one launch received, opencode's inline config included; short_key makes a placeholder short enough for a refusal to quote; CallerText binds steps to one short key and holds a bad caller text with it; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new spliced value gets a key planted in it here and a clean-prompt assertion on the step that receives it.
WHAT NOT TO DO IN THIS FILE: Never use a real key; fresh_key makes a random placeholder in the base key pattern.
KNOWN EDGE CASES: The raw answer and diff texts in the returned records are meant to keep the keys (EC-71); only text compose produces or splices is scrubbed. A refusal quotes a bad value only while its repr fits in 80 characters, so fresh_key's 75-character keys can never show such a leak; the caller-text cases use short_key's 16 characters, so the bad value's repr (33 characters) would still be quoted under a limit cut to less than half, and a value that gets past the template checks (only {previous}) but holds a brace, a space and a NUL, so a later text check is the one that refuses.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-4, INV-5, INV-26, §6.2 AC-15, §6.3 EC-71, §10 T-3; docs/spec/native-thread-compose/review.md R-3, R-17
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

import inspect
import os
import uuid

import pytest

NUL = "\x00"
# A well-formed thread id: only the model is bad.
THREAD_ID = "0192f0c4-beef-7bee-8f00-000000000005"


def assert_clean(pack, text: str, keys, where: str) -> None:
    found = pack.leaks(text, keys)
    assert found == [], f"{where} holds key fragments {found[:3]}"


def short_key() -> str:
    # A random placeholder of 16 characters in the base key pattern.
    # A bad value holding it and a NUL has a 33-character repr, well
    # inside the 80 characters a refusal quotes, so even a limit cut
    # by half could not hide the leak (review R-3, R-17).
    return f"vbk-{uuid.uuid4().hex[:12]}"


class CallerText:
    """Steps bound to one short key, and a bad caller text holding it."""

    def __init__(self, api, steps, pack, key: str) -> None:
        self.api = api
        self.compose = api.compose
        self.steps = steps
        self.pack = pack
        self.key = key
        # Gets past the template checks, which allow {previous}, and
        # fails the text checks after them: the brace, the space or
        # the NUL breaks each one's pattern.
        self.bad = "{previous} " + key + NUL

    def grok(self, **fields):
        return self.steps.bind("grok", key=self.key, **fields)

    def opencode(self, **fields):
        return self.steps.bind("opencode", key=self.key, **fields)

    def muse(self, **fields):
        return self.steps.bind("muse", key=self.key, **fields)

    def roster(self):
        return self.api.ensemble.EnsembleRoster(planner=self.grok(plan=True), proposers=[self.grok(plan=True)], selector=self.grok(plan=True), implementer=self.opencode())

    def stages(self, *templates: str):
        return [self.api.records.StageSpec(step=self.grok(), template=template) for template in templates]


# site: (the field its refusal names,
# the call that puts the bad text there)
CALLER_TEXT_SITES = {
    "chain_threads prompt": ("prompt", lambda t: t.compose.chain_threads([t.grok(), t.opencode()], prompt=t.bad)),
    "chain_threads template": ("template", lambda t: t.compose.chain_threads([t.grok(), t.opencode()], t.bad, prompt=t.pack.PROMPT)),
    "verify_with prompt": ("prompt", lambda t: t.compose.verify_with(t.opencode(), [t.grok(plan=True)], prompt=t.bad)),
    "run_ensemble prompt": ("prompt", lambda t: t.compose.run_ensemble(t.bad, t.roster())),
    "later StageSpec.template": ("stages[1].template", lambda t: t.compose.run_staged_threads(t.stages("Start.", t.bad))),
    "first StageSpec.template": ("stages[0].template", lambda t: t.compose.run_staged_threads(t.stages(t.key + NUL))),
    "parse_json_answer prompt": ("prompt", lambda t: t.compose.parse_json_answer(t.grok(), t.bad, schema="{}", parse=dict)),
    "parse_json_answer schema": ("schema", lambda t: t.compose.parse_json_answer(t.grok(), t.pack.PROMPT, schema=t.bad, parse=dict)),
    "bind_continue thread_id of a continue function": ("thread_id", lambda t: t.steps.bind("grok", "continue", t.bad, key=t.key)),
    "bind_continue thread_id of a fork function": ("thread_id", lambda t: t.steps.bind("opencode", "fork", t.bad, key=t.key)),
    "bind_thread model": ("model", lambda t: t.steps.bind("grok", key=t.key, model=t.bad)),
    "bind_continue model": ("model", lambda t: t.steps.bind("grok", "continue", THREAD_ID, key=t.key, model=t.bad)),
    "run_grok_then_opencode prompt": ("prompt", lambda t: t.compose.run_grok_then_opencode(t.bad, grok=t.grok(), opencode=t.opencode())),
    "run_grok_then_muse prompt": ("prompt", lambda t: t.compose.run_grok_then_muse(t.bad, grok=t.grok(), muse=t.muse())),
    "run_opencode_then_grok prompt": ("prompt", lambda t: t.compose.run_opencode_then_grok(t.bad, opencode=t.opencode(), grok=t.grok())),
    "run_opencode_then_muse prompt": ("prompt", lambda t: t.compose.run_opencode_then_muse(t.bad, opencode=t.opencode(), muse=t.muse())),
    "run_muse_then_grok prompt": ("prompt", lambda t: t.compose.run_muse_then_grok(t.bad, muse=t.muse(), grok=t.grok())),
    "run_muse_then_opencode prompt": ("prompt", lambda t: t.compose.run_muse_then_opencode(t.bad, muse=t.muse(), opencode=t.opencode())),
    "run_grok_verify_with_opencode_and_muse prompt": ("prompt", lambda t: t.compose.run_grok_verify_with_opencode_and_muse(t.bad, writer=t.grok(edits=True), opencode=t.opencode(), muse=t.muse())),
    "run_opencode_verify_with_grok_and_muse prompt": ("prompt", lambda t: t.compose.run_opencode_verify_with_grok_and_muse(t.bad, writer=t.opencode(), grok=t.grok(plan=True), muse=t.muse())),
    "run_muse_verify_with_grok_and_opencode prompt": ("prompt", lambda t: t.compose.run_muse_verify_with_grok_and_opencode(t.bad, writer=t.muse(), grok=t.grok(plan=True), opencode=t.opencode())),
}


def credential_digests(launch) -> list[dict]:
    # The key digests one launch received: its credential variables,
    # and every apiKey inside opencode's inline config.
    found = [value for name, value in launch["start"]["credentials"].items() if value is not None and name != "OPENCODE_CONFIG_CONTENT"]
    pending = [launch["start"].get("opencode_config")]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            found.extend(value for key, value in node.items() if key == "apiKey" and isinstance(value, dict))
            pending.extend(value for key, value in node.items() if key != "apiKey")
        elif isinstance(node, list):
            pending.extend(node)
    return found


@pytest.mark.asyncio
async def test_chain_splices_answers_and_diffs_with_every_key_redacted(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-15 / INV-4 / D-28: A prints all three keys and saves them in a
    # file; B prints two; later prompts carry [redacted], records keep
    # the raw text, git never sees a key, os.environ is unchanged.
    api = compose_api
    sandbox.make_repo()
    key_a, key_b, key_c = pack.fresh_key("chain-a"), pack.fresh_key("chain-b"), pack.fresh_key("chain-c")
    keys = (key_a, key_b, key_c)
    a_text = f"A-ANSWER {key_a} {key_b} {key_c}"
    b_text = f"B-ANSWER {key_c} and {key_a}"
    a = steps.bind("opencode", label="a", key=key_a, fake={"final_parts": [a_text], "write_files": {"leak.txt": f"{key_a}\n{key_b}\n{key_c}\n"}})
    b = steps.bind("grok", label="b", key=key_b, fake={"text": b_text})
    c = steps.bind("muse", label="c", key=key_c)
    environment = dict(os.environ)
    result = await api.compose.chain_threads([a, b, c], prompt=pack.PROMPT)
    assert dict(os.environ) == environment
    assert result.failed_step is None

    b_prompt, c_prompt = pack.launch_prompt(sandbox.only_launch("b")), pack.launch_prompt(sandbox.only_launch("c"))
    assert "A-ANSWER" in b_prompt and "leak.txt" in b_prompt and pack.REDACTED in b_prompt
    assert "B-ANSWER" in c_prompt and pack.REDACTED in c_prompt
    assert_clean(pack, b_prompt, keys, "step b's prompt")
    assert_clean(pack, c_prompt, keys, "step c's prompt")
    for launch in sandbox.launches():
        assert_clean(pack, " ".join(launch["start"]["argv"]) + (launch["start"].get("stdin_text") or ""), keys, f"{launch['label']}'s argv or stdin")
    assert sandbox.only_launch("b")["start"]["credentials"]["XAI_API_KEY"] == pack.key_digest(key_b), "each key reaches only its own step"
    assert sandbox.only_launch("c")["start"]["credentials"]["META_API_KEY"] == pack.key_digest(key_c)
    assert pack.key_digest(key_a) in credential_digests(sandbox.only_launch("a"))
    assert all(pack.key_digest(other) not in credential_digests(sandbox.only_launch(label)) for label, own in (("a", key_a), ("b", key_b), ("c", key_c)) for other in keys if other != own)
    for _index, item in runs.git_calls():
        assert_clean(pack, " ".join(item.argv) + repr(dict(item.env_overlay)), keys, "a git child")

    assert result.outcomes[0].text == a_text and result.outcomes[1].text == b_text
    assert all(key in result.outcomes[0].diff.text for key in keys), "records keep the raw diff (EC-71)"


@pytest.mark.asyncio
async def test_ensemble_splices_roles_proposals_and_guidance_with_every_key_redacted(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-15 / INV-4: keys in the plan's role fields and analysis, in the
    # proposals and in the selection's guidance never reach the next
    # stage's prompt.
    api = compose_api
    sandbox.make_repo()
    key_p, key_f, key_o, key_s, key_i = (pack.fresh_key(label) for label in ("planner", "fork", "opencode", "selector", "implementer"))
    keys = (key_p, key_f, key_o, key_s, key_i)
    plan = pack.plan_json([("ROLE-ONE", f"IDENTITY-ONE {key_i}"), ("ROLE-TWO", f"IDENTITY-TWO {key_s}")], analysis=f"ANALYSIS {key_p}")
    planner = steps.bind("grok", plan=True, label="planner", key=key_p, fake={"text": plan})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", key=key_f, fake={"text": f"PROPOSAL-ONE {key_o}"})
    opencode = steps.bind("opencode", label="p-oc", key=key_o, fake={"final_parts": [f"PROPOSAL-TWO {key_f}"]})
    selector = steps.bind("grok", plan=True, label="selector", key=key_s, fake={"text": pack.selection_json(2, guidance=f"GUIDANCE {key_p}")})
    implementer = steps.bind("grok", edits=True, label="implementer", key=key_i)
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork, opencode], selector=selector, implementer=implementer)
    result = await api.compose.run_ensemble(pack.TASK, roster=roster)
    assert result.failed_stage is None
    expected = {"p-grok": ("IDENTITY-ONE", "ANALYSIS"), "p-oc": ("IDENTITY-TWO", "ANALYSIS"), "selector": ("PROPOSAL-ONE", "PROPOSAL-TWO"), "implementer": ("PROPOSAL-TWO", "GUIDANCE")}
    for label, texts in expected.items():
        prompt = pack.launch_prompt(sandbox.only_launch(label))
        assert all(text in prompt for text in texts) and pack.REDACTED in prompt, f"{label} did not get its spliced values"
        assert_clean(pack, prompt, keys, f"{label}'s prompt")
    assert key_i in result.plan.text and key_o in result.proposals[0].text, "records keep the raw text"
    for _index, item in runs.git_calls():
        assert_clean(pack, " ".join(item.argv) + repr(dict(item.env_overlay)), keys, "a git child")


@pytest.mark.asyncio
async def test_errors_and_reprs_never_show_a_key_while_result_and_diff_stay_raw(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-15 / INV-4 / EC-71 / T-3: a Grok reader that saves keys into a
    # file trips the backstop; the error's text and attributes are
    # clean except result and diff; reprs of records holding steps are
    # clean; a ConfigurationError never quotes a key a caller put in a
    # bad template.
    api = compose_api
    sandbox.make_repo()
    key_w, key_r = pack.fresh_key("writer"), pack.fresh_key("reader")
    keys = (key_w, key_r)
    writer = steps.bind("opencode", label="writer", key=key_w, fake={"final_parts": [f"WRITER {key_w} {key_r}"], "write_files": {"writer-leak.txt": f"{key_w}\n"}})
    reader = steps.bind("grok", plan=True, label="reader", key=key_r, fake={"text": pack.verdict_json("approve", summary=f"Saw {key_w}."), "write_files": {"reader-leak.txt": f"{key_r} {key_w}\n"}})
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [reader], prompt=pack.PROMPT)
    error = caught.value
    assert error.problem.value == "reader_changed_workspace"
    assert_clean(pack, str(error), keys, "the error message")
    assert_clean(pack, repr(error.args), keys, "the error args")
    for name, value in vars(error).items():
        if name not in ("result", "diff"):
            assert_clean(pack, repr(value), keys, f"error.{name}")
    assert_clean(pack, repr(error.details), keys, "error.details")
    assert key_r in error.diff.text and key_w in error.diff.text, "error.diff keeps the raw text"
    assert key_w in error.result.writer.text, "error.result keeps the raw answer"
    assert_clean(pack, pack.launch_prompt(sandbox.only_launch("reader")), keys, "the verifier's prompt")
    assert pack.REDACTED in pack.launch_prompt(sandbox.only_launch("reader"))

    stage = api.records.StageSpec(step=writer, template="Start.")
    roster = api.ensemble.EnsembleRoster(planner=reader, proposers=[reader], selector=reader, implementer=writer)
    for record in (writer, reader, stage, roster):
        assert_clean(pack, repr(record), keys, f"repr of {type(record).__name__}")
    with pytest.raises(api.ConfigurationError) as refused:
        await api.compose.chain_threads([writer, reader], f"Use {key_w} then {{nope}} and {{previous}}", prompt=pack.PROMPT)
    assert refused.value.details.get("field") == "template"
    assert_clean(pack, str(refused.value) + repr(refused.value.details), keys, "the ConfigurationError")


@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(CALLER_TEXT_SITES))
async def test_a_refusal_of_caller_text_never_quotes_the_key_it_holds(compose_api, sandbox, steps, pack, site) -> None:
    # AC-15 / INV-4 / INV-5 / T-3: a caller text that holds a key bound
    # to the call's steps gets past any template check and fails the
    # text check after it. The ConfigurationError names the argument,
    # holds no fragment of the key in its message, args or any
    # attribute, and nothing has started. Red until review R-3 lands.
    api = compose_api
    field, call = CALLER_TEXT_SITES[site]
    text = CallerText(api, steps, pack, short_key())
    with pytest.raises(api.ConfigurationError) as refused:
        outcome = call(text)
        if inspect.isawaitable(outcome):
            await outcome
    error = refused.value
    assert error.details.get("field") == field, f"{site}: {error} {error.details}"
    shown = " ".join([str(error), repr(error.args), *(repr(value) for value in vars(error).values())])
    assert pack.leaks(shown, [text.key]) == [], f"INV-4: the {site} refusal quotes the key: {str(error)!r}"
    assert sandbox.launches() == [], "refused before any process starts"


@pytest.mark.asyncio
async def test_git_text_and_file_names_that_hold_a_key_are_scrubbed_from_errors(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-15 / T-3 / INV-6: a writer that leaves an untracked repository
    # named after its key makes add fail with git's text naming that
    # folder; a reader that writes a file named after its key trips the
    # backstop, whose message lists changed files. Neither error shows
    # a key outside result and diff, yet git's text and the file stay.
    api = compose_api
    sandbox.make_repo()
    key_w, key_r = pack.fresh_key("writer"), pack.fresh_key("reader")
    keys = (key_w, key_r)
    nested = {f"{key_w}/.git/HEAD": "ref: refs/heads/main\n", f"{key_w}/.git/objects/.keep": "", f"{key_w}/.git/refs/heads/.keep": "", f"{key_w}/inner.txt": "inner\n"}
    writer = steps.bind("opencode", label="writer", key=key_w, fake={"write_files": nested})
    never = steps.bind("grok", plan=True, label="never", key=key_r)
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [never], prompt=pack.PROMPT)
    failed = caught.value
    assert failed.problem.value == "git_failed" and "does not have a commit checked out" in failed.git_message
    assert sandbox.launches(label="never") == []

    second = sandbox.make_repo(sandbox.root / "second")
    calm = steps.bind("opencode", label="calm-writer", key=key_w, workspace=second, fake={"write_files": {"feature.txt": "feature\n"}})
    reader = steps.bind("grok", plan=True, label="reader", key=key_r, workspace=second, fake={"text": pack.verdict_json("approve"), "write_files": {f"{key_r}.txt": "named after the key\n"}})
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(calm, [reader], prompt=pack.PROMPT)
    changed = caught.value
    assert changed.problem.value == "reader_changed_workspace" and changed.diff.files == (f"{key_r}.txt",), "error.diff keeps the raw file name"

    for error in (failed, changed):
        assert_clean(pack, str(error), keys, f"the {error.problem.value} message")
        assert_clean(pack, repr(error.args), keys, f"the {error.problem.value} args")
        for name, value in vars(error).items():
            if name not in ("result", "diff"):
                assert_clean(pack, repr(value), keys, f"{error.problem.value} error.{name}")
        assert_clean(pack, repr(error.details), keys, f"the {error.problem.value} details")
    assert sandbox.leftovers() == []
