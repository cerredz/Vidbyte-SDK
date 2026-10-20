"""FILE: tests/features/harness_compose/test_harness_compose_keys.py

PURPOSE: Key hygiene (AC-15, INV-4, INV-5, INV-6, INV-26, T-3, D-28, EC-28, EC-71, EC-78): with every step bound to its own distinctive key and stand-ins that print keys into answers, plans, proposals, guidance and files, no fragment of any bound key reaches a later step's prompt or argv (COMPOSE_REDACTED_KEY stands in its place), any git argv or environment, the repr of a ThreadStep, StageSpec or EnsembleRoster, a ThreadComposeError's message or any attribute but result and diff (also when git's own text or a changed file's name holds the key), or a ConfigurationError, whether the caller put a key in a bad template or in any caller text that compose refuses (every composite's and alias's prompt, the chain and stage templates, the schema, a thread id, either binder's model) or in one field of a record built without a binder (a ThreadStep built directly or changed with dataclasses.replace, a StageSpec, a ThreadVerdict, a StageAttempt, an EnsembleRole, an EnsembleSelection or a WorkspaceDiff), where neither the refusal nor any exception its context or cause chain keeps quotes the key, nor does the problem compose records when a step answers its key into a verdict's decision, a selection's proposal, a plan role's name or a round's kept list; a WORKTREE_FAILED raised because a reader's worktree keeps a file named after its key (EC-16), a GIT_FAILED raised because compose's temporary folder cannot be made, and a WORKTREE_FAILED raised because a reader's matching folder cannot be made, chain no OS error, so no key reaches their cause, their context or the traceback that logging.exception prints; the records keep the raw text, error.result and error.diff included; each key reaches only its own step's child; os.environ is unchanged.
ROLE IN CODEBASE: Start here when a key shows up anywhere compose produced text.
ARCHITECTURE NOTE: Keys are random placeholders (fresh_key, short_key), and leaks are searched as every 12-character fragment, so a partly scrubbed key is still caught. Prompts and argv are read from the stand-in logs, git children from the CliRunner spy. The stand-in scenarios hold the keys as answer text, the way a model would print them; the stand-in logs credentials only as digests.
FUNCTION INVENTORY: assert_clean fails with the leaked fragments; credential_digests lists the key digests one launch received, opencode's inline config included; short_key makes a placeholder short enough for a refusal to quote; CallerText binds steps to one short key and holds a bad caller text with it; RecordText builds a ThreadStep directly, binds one, or builds a result record, each with one short key; RECORD_SITES maps each record field to the field its refusal names and the call that puts the key there; reachable lists an error and every exception its context and cause chains reach; error_surfaces joins the message, repr, args and attributes of each; AnswerText runs a verify_with or a run_ensemble in which one step answers its own short key into a JSON member; ANSWER_SITES maps each member to the field its problem names, the run and the answer that holds the problem; KeyFileHold keeps the key-named file a reader saved in its worktree from being deleted, and frees it; worktree_root finds the compose worktree that holds a launch's working folder; settle releases the stand-ins and waits for the composite's tasks; traceback_text is what logging.exception prints for an error; FolderRefusal stands in for os.mkdir and refuses one folder name inside a compose worktree; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new spliced value gets a key planted in it here and a clean-prompt assertion on the step that receives it. A new record field whose check can refuse a short str gets a RECORD_SITES row. A new place where compose turns an OSError into a ThreadComposeError gets a row asserting that the error chains nothing.
WHAT NOT TO DO IN THIS FILE: Never use a real key; fresh_key makes a random placeholder in the base key pattern. Do not let a writer save the held key-named file: the writer's diff keeps it raw (EC-71), so error_surfaces would show the key even when compose is right.
KNOWN EDGE CASES: The raw answer and diff texts in the returned records are meant to keep the keys (EC-71); only text compose produces or splices is scrubbed. A refusal quotes a bad value only while its repr fits in 80 characters, so fresh_key's 75-character keys can never show such a leak; the caller-text cases use short_key's 16 characters, so the bad value's repr (33 characters) would still be quoted under a limit cut to less than half, and a value that gets past the template checks (only {previous}) but holds a brace, a space and a NUL, so a later text check is the one that refuses. A record row's bad value ends in a newline, a NUL or a space where the field's pattern needs one to refuse: a bare key passes as a grok or muse model and as a thread id, which validation accepts, so that case is not a refusal and is out of R-33. An answer row checks only the problem compose records: the answer's turns keep the key raw, as the step's own text (EC-71). The round row is a guard: a kept refusal names only the type today, so it passes before R-33 lands too. A held file stops a worktree removal through the operating system's own rules: an open handle on win32, a folder without write permission on POSIX. On POSIX rmtree names only the basename of the entry it cannot unlink, so the held file carries the key in its own name and is alone in its folder; a root process ignores folder permissions, so the held-file rows skip as POSIX root. No operating-system seam refuses the matching folder of a fresh worktree, so its row stands in for os.mkdir, which every Python folder API ends in, and refuses that one folder name with the OS's own PermissionError.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-4, INV-5, INV-26, §6.2 AC-15, §6.3 EC-16, EC-28, EC-71, EC-78, §10 T-3, §14; docs/spec/native-thread-compose/review.md R-3, R-17, R-33, R-34; docs/spec/native-thread-compose/reports/S5-findings-verifier-rr1.md §3.3, §4.2, §8; docs/spec/native-thread-compose/reports/S5-findings-verifier-rr2.md §2.3, §2.4, §5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_keys.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import errno
import inspect
import json
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import IO

import pytest

NUL = "\x00"
# A well-formed thread id: only the model is bad.
THREAD_ID = "0192f0c4-beef-7bee-8f00-000000000005"
# The folder a held reader saves its key-named file in (R-34).
HELD = "held-by-test"
POSIX_ROOT = sys.platform != "win32" and os.geteuid() == 0
ROOT_SKIP = "root ignores folder permissions, so no POSIX seam keeps a worktree folder from removal"


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


class RecordText:
    """Records a caller builds without a binder, with one short key."""

    def __init__(self, api, steps, sandbox, pack, key: str) -> None:
        self.api = api
        self.records = api.records
        self.ensemble = api.ensemble
        self.steps = steps
        self.sandbox = sandbox
        self.pack = pack
        self.key = key

    def direct(self, kind: tuple[str, str], **changes):
        # A ThreadStep built directly (EC-78) around the function of
        # kind, a (harness, verb) pair, and valid apart from the
        # fields the row changes, its harness or verb among them.
        harness, verb = kind
        values = {"function": self.api.functions[kind], "harness": harness, "verb": verb, "api_key": self.key, "workspace": self.sandbox.workspace}
        if harness == "opencode":
            values["model"] = self.pack.OPENCODE_MODEL
        if verb != "run":
            values["thread_id"] = THREAD_ID
        values.update(changes)
        return self.records.ThreadStep(**values)

    def bound(self, harness: str = "grok", verb: str = "run", thread_id: str | None = None):
        return self.steps.bind(harness, verb, thread_id, key=self.key)

    def outcome(self):
        result = self.api.NativeThreadResult(harness=self.api.NativeHarness.GROK, thread_id=THREAD_ID, text="x", text_truncated=False)
        return self.records.StepOutcome(result=result)


# R-33: every record field whose check can refuse a short str, with
# the field its refusal names and the call that puts the key there.
# Each row reaches one check, so a site that quotes fails its rows.
RECORD_SITES = {
    # A ThreadStep built directly (EC-78).
    "ThreadStep() harness": ("ThreadStep.harness", lambda t: t.direct(("grok", "run"), harness=t.key)),
    "ThreadStep() verb": ("ThreadStep.verb", lambda t: t.direct(("grok", "run"), verb=t.key)),
    "ThreadStep() opencode model": ("model", lambda t: t.direct(("opencode", "run"), model=t.key)),
    "ThreadStep() grok model with a newline": ("model", lambda t: t.direct(("grok", "run"), model=t.key + "\n")),
    "ThreadStep() continue thread_id": ("thread_id", lambda t: t.direct(("grok", "continue"), thread_id=t.key + NUL)),
    "ThreadStep() fork thread_id": ("thread_id", lambda t: t.direct(("opencode", "fork"), thread_id=t.key + " x")),
    # A bound step changed with dataclasses.replace (EC-78).
    "replace() harness": ("ThreadStep.harness", lambda t: dataclasses.replace(t.bound(), harness=t.key)),
    "replace() verb": ("ThreadStep.verb", lambda t: dataclasses.replace(t.bound(), verb=t.key)),
    "replace() opencode model": ("model", lambda t: dataclasses.replace(t.bound("opencode"), model=t.key)),
    "replace() continue thread_id": ("thread_id", lambda t: dataclasses.replace(t.bound("grok", "continue", THREAD_ID), thread_id=t.key + NUL)),
    # A StageSpec the caller builds.
    "StageSpec retries": ("StageSpec.retries", lambda t: t.records.StageSpec(t.bound(), "Start.", t.key)),
    "replace() StageSpec retries": ("StageSpec.retries", lambda t: dataclasses.replace(t.records.StageSpec(step=t.bound(), template="Start."), retries=t.key)),
    # Result and answer records, public names a caller can build.
    "ThreadVerdict decision": ("ThreadVerdict.decision", lambda t: t.records.ThreadVerdict(decision=t.key, summary="s")),
    "StageAttempt rung": ("StageAttempt.rung", lambda t: t.records.StageAttempt(rung=t.key, outcome=t.outcome())),
    "StageAttempt decision": ("StageAttempt.decision", lambda t: t.records.StageAttempt(rung=0, outcome=t.outcome(), decision=t.key)),
    "EnsembleSelection proposal": ("EnsembleSelection.proposal", lambda t: t.ensemble.EnsembleSelection(proposal=t.key, approach="a", rationale="r", guidance="g")),
    "EnsembleRole name": ("EnsembleRole.name", lambda t: t.ensemble.EnsembleRole(name=t.key + NUL, identity="i", personality="p", expertise="e", knowledge="k", skills="s", goal="g")),
    "WorkspaceDiff truncated": ("WorkspaceDiff.truncated", lambda t: t.records.WorkspaceDiff(files=(), text="", truncated=t.key)),
}


def reachable(error: BaseException) -> list[BaseException]:
    # The error and every exception its __context__ and __cause__
    # chains reach, so a quoted original kept as context counts too.
    found: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        item = pending.pop()
        if item is None or any(item is seen for seen in found):
            continue
        found.append(item)
        pending.extend((item.__context__, item.__cause__))
    return found


def error_surfaces(error: BaseException) -> str:
    # Every text the error shows, and every exception it reaches:
    # the message, the repr, the args and each attribute's repr.
    return " ".join(" ".join([str(item), repr(item), repr(item.args), *(repr(value) for value in vars(item).values())]) for item in reachable(error))


class AnswerText:
    """Composites in which one step answers its own short key."""

    def __init__(self, api, steps, pack, key: str) -> None:
        self.compose = api.compose
        self.ensemble = api.ensemble
        self.steps = steps
        self.pack = pack
        self.key = key

    def verify(self):
        # A Grok verifier answers its key as the decision every turn.
        writer = self.steps.bind("grok", edits=True, label="writer", fake={"text": "Done.", "write_files": {"feature.txt": "feature\n"}})
        verifier = self.steps.bind("grok", plan=True, label="verifier", key=self.key, fake={"text": self.pack.verdict_json(self.key)})
        return self.compose.verify_with(writer, [verifier], prompt=self.pack.PROMPT)

    def ensemble_run(self, plan: str, selection: str, proposers: int = 1):
        # A planner, Grok fork proposers, a selector and an implementer.
        # One proposer offers the selector block 1 alone (EC-70); ten
        # make it narrow them in a round first. The planner and the
        # selector hold the key.
        planner = self.steps.bind("grok", plan=True, label="planner", key=self.key, fake={"text": plan})
        proposer = self.steps.bind("grok", "fork", plan=True, label="proposer", fake={"text": "PROPOSAL-ONE: lazy imports."})
        selector = self.steps.bind("grok", plan=True, label="selector", key=self.key, fake={"text": selection})
        implementer = self.steps.bind("grok", edits=True, label="implementer")
        roster = self.ensemble.EnsembleRoster(planner=planner, proposers=[proposer] * proposers, selector=selector, implementer=implementer)
        return self.compose.run_ensemble(self.pack.TASK, roster=roster)

    def selection(self):
        # The selector answers its key as the proposal number.
        answer = json.dumps({"proposal": self.key, "approach": "a", "rationale": "r", "guidance": "g"})
        return self.ensemble_run(self.pack.plan_json([("ROLE-ONE", "IDENTITY-ONE")]), answer)

    def plan(self):
        # The planner answers its key and a NUL as its one role's name.
        return self.ensemble_run(self.pack.plan_json([(self.key + NUL, "IDENTITY-ONE")]), self.pack.selection_json(1))

    def narrowing(self):
        # Ten proposals, and the selector answers its key as the one
        # proposal its round keeps.
        roles = [(f"ROLE-{index:02d}", f"IDENTITY-{index:02d}") for index in range(1, 11)]
        answer = json.dumps({"kept": [self.key], "summary": "s"})
        return self.ensemble_run(self.pack.plan_json(roles), answer, proposers=10)


# R-33: every JSON member a step answers whose record can refuse a
# short str, with the field the problem names, the run whose step
# answers its key there, and the answer that keeps the problem.
# Section 3.3 of the R-33 verifier report found the first three; the
# round's kept list already names only its type, and its row keeps
# it that way.
ANSWER_SITES = {
    "verify_with verdict decision": ("ThreadVerdict.decision", lambda t: t.verify(), lambda result: result.verdicts[0]),
    "run_ensemble selection proposal": ("EnsembleSelection.proposal", lambda t: t.selection(), lambda result: result.selection),
    "run_ensemble plan role name": ("EnsembleRole.name", lambda t: t.plan(), lambda result: result.plan),
    "run_ensemble round kept": ("EnsembleRound.kept", lambda t: t.narrowing(), lambda result: result.rounds[0] if result.rounds else None),
}


class KeyFileHold:
    """Keeps the key-named file a reader saved in its worktree."""

    def __init__(self, root: Path, name: str) -> None:
        self.root = root
        self.folder = root / HELD
        self.file = self.folder / name
        self.handle: IO[str] | None = None

    def hold(self) -> None:
        # Windows deletes no file that a process holds open; POSIX
        # unlinks no entry of a folder without write permission. There
        # rmtree names the first entry it cannot unlink, so the folder
        # must hold the key-named file alone.
        assert [item.name for item in self.folder.iterdir()] == [self.file.name], "the held folder holds the key-named file alone"
        if sys.platform == "win32":
            self.handle = self.file.open("a", encoding="utf-8")
        else:
            self.folder.chmod(0o500)

    def free(self) -> None:
        # Undo the hold, then delete what compose had to leave.
        if self.handle is not None:
            self.handle.close()
        if sys.platform != "win32" and self.folder.exists():
            self.folder.chmod(0o700)
        shutil.rmtree(self.root, ignore_errors=True)


def worktree_root(pack, launch: dict) -> Path:
    # The compose worktree that holds a launch's working folder.
    folder = Path(launch["start"]["cwd"])
    return next(item for item in (folder, *folder.parents) if item.name.startswith(pack.WORKTREE_PREFIX))


async def settle(sandbox, before: set, timeout: float) -> None:
    # Release every held stand-in and wait for whatever task the
    # composite left, so nothing outlives the test even when it fails.
    sandbox.release()
    left = asyncio.all_tasks() - before
    if left:
        await asyncio.wait(left, timeout=timeout)


def traceback_text(error: BaseException) -> str:
    # What logging.exception and an uncaught error print: the error
    # and every exception its cause and context chains reach.
    return "".join(traceback.format_exception(error))


class FolderRefusal:
    """Makes the operating system refuse one folder in a worktree."""

    def __init__(self, prefix: str, name: str) -> None:
        self.prefix = prefix
        self.name = name
        self.making = os.mkdir

    def __call__(self, path, *args, **kwargs):
        # Every folder Python makes goes through os.mkdir, whichever
        # API made it; only the named folder inside a compose worktree
        # is refused, with the error the OS gives a folder it may not
        # write in.
        target = Path(os.fsdecode(path))
        if target.name == self.name and self.prefix in str(target):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(target))
        return self.making(path, *args, **kwargs)


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
    # holds no fragment of the key in its message, repr, args or
    # attributes, or in any exception its context or cause chain
    # keeps, and nothing has started. Red until review R-3 lands.
    api = compose_api
    field, call = CALLER_TEXT_SITES[site]
    text = CallerText(api, steps, pack, short_key())
    with pytest.raises(api.ConfigurationError) as refused:
        outcome = call(text)
        if inspect.isawaitable(outcome):
            await outcome
    error = refused.value
    assert error.details.get("field") == field, f"{site}: {error} {error.details}"
    assert pack.leaks(error_surfaces(error), [text.key]) == [], f"INV-4: the {site} refusal quotes the key: {str(error)!r}"
    assert sandbox.launches() == [], "refused before any process starts"


@pytest.mark.parametrize("site", sorted(RECORD_SITES))
def test_a_record_refusal_never_quotes_the_key_it_was_given(compose_api, sandbox, steps, pack, site) -> None:
    # AC-15 / INV-4 / INV-5 / EC-78: a key in one field of a record
    # built without a binder, or changed with dataclasses.replace,
    # is refused by that record. The ConfigurationError names the
    # field, nothing has started, and no fragment of the key is in
    # its message, repr, args or attributes, or in any exception its
    # context or cause chain keeps. Red until review R-33 lands.
    api = compose_api
    field, build = RECORD_SITES[site]
    text = RecordText(api, steps, sandbox, pack, short_key())
    with pytest.raises(api.ConfigurationError) as refused:
        build(text)
    error = refused.value
    assert error.details.get("field") == field, f"{site}: {error} {error.details}"
    assert sandbox.launches() == [], "refused before any process starts"
    assert pack.leaks(error_surfaces(error), [text.key]) == [], f"INV-4: the {site} refusal quotes the key: {str(error)!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(ANSWER_SITES))
async def test_an_answer_member_refusal_never_quotes_the_key_in_its_problem(compose_api, sandbox, steps, pack, site) -> None:
    # AC-15 / INV-4 / EC-28 / EC-71: a step answers its own key into
    # a member whose record refuses it, on every turn. The answer
    # ends with no value after its repair turns, the turns keep the
    # raw text (EC-71), and the problem compose records names the
    # field yet holds no fragment of the key. Red until review R-33
    # lands, except the round row, which guards a refusal that names
    # only the type.
    api = compose_api
    field, run, pick = ANSWER_SITES[site]
    sandbox.make_repo()
    text = AnswerText(api, steps, pack, short_key())
    answer = pick(await run(text))
    assert answer is not None and answer.value is None, f"{site}: the answer was accepted"
    assert len(answer.turns) == 1 + api.constants.COMPOSE_JSON_REPAIR_TURNS, "the first turn and every repair turn ran"
    assert all(text.key in turn.result.text for turn in answer.turns), "the turns keep the raw answer (EC-71)"
    problem = answer.problem or ""
    assert field in problem, f"EC-28: the problem names {field}: {problem!r}"
    assert pack.leaks(problem, [text.key]) == [], f"INV-4: the {site} problem quotes the key: {problem!r}"


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
        assert_clean(pack, traceback_text(error), keys, f"the {error.problem.value} traceback")
    assert sandbox.leftovers() == []


@pytest.mark.asyncio
@pytest.mark.skipif(POSIX_ROOT, reason=ROOT_SKIP)
async def test_a_verifier_worktree_holding_its_key_named_file_chains_no_os_error(compose_api, sandbox, steps, pack, wait_until, check_compose_error) -> None:
    # AC-15 / INV-4 / EC-16 / ledger 3: the opencode verifier saves a
    # file named after its own key in its worktree, and the file is
    # held when compose removes that worktree. WORKTREE_FAILED still
    # names the folder and git worktree prune and keeps the verdict,
    # but neither the error, any exception its cause or context chain
    # reaches, nor its traceback, which logging.exception prints,
    # shows a key. Red until review R-34 lands.
    api = compose_api
    sandbox.make_repo()
    key_w, key_o = pack.fresh_key("writer"), pack.fresh_key("reader")
    keys = (key_w, key_o)
    name = f"{key_o}.txt"
    writer = steps.bind("opencode", label="writer", key=key_w, fake={"write_files": {"feature.txt": "feature\n"}})
    reader = steps.bind("opencode", label="v-held", key=key_o, fake={"mode": "hold", "write_files": {f"{HELD}/{name}": "saved\n"}, "final_parts": [pack.verdict_json("approve")]})
    before = asyncio.all_tasks()
    task = asyncio.ensure_future(api.compose.verify_with(writer, [reader], prompt=pack.PROMPT))
    hold = None
    try:
        # Wait for the verifier to save its key-named file in its own
        # worktree, hold that file, then let the verifier answer.
        assert await wait_until(lambda: bool(sandbox.launches(label="v-held")), pack.WAIT_SECONDS), "the opencode verifier started"
        root = worktree_root(pack, sandbox.only_launch("v-held"))
        assert await wait_until(lambda: (root / HELD / name).is_file(), pack.WAIT_SECONDS), "the verifier saved its key-named file"
        hold = KeyFileHold(root, name)
        hold.hold()
        sandbox.release()
        with pytest.raises(api.ThreadComposeError) as caught:
            await asyncio.wait_for(task, pack.WAIT_SECONDS)
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        if hold is not None:
            hold.free()
        await settle(sandbox, before, pack.WAIT_SECONDS)
    error = caught.value

    # The EC-16 record is what it always was.
    check_compose_error(error, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(root))])
    assert "git worktree prune" in error.next_step
    assert [answer.value.decision.value for answer in error.result.verdicts] == ["approve"]
    assert (registered, leftovers) == (1, [root.name]), "only the held folder is left, and it is no longer registered"

    # No surface of the error, of its chain or of its traceback shows a
    # key: the OS error that names the held file is not kept.
    chain = [type(item).__name__ for item in reachable(error)]
    assert pack.leaks(error_surfaces(error), keys) == [], f"INV-4: the error or its chain {chain} shows a key"
    assert pack.leaks(traceback_text(error), keys) == [], f"ledger 3: the traceback logging.exception prints shows a key; chain {chain}"


@pytest.mark.asyncio
@pytest.mark.skipif(POSIX_ROOT, reason=ROOT_SKIP)
async def test_a_proposer_worktree_holding_its_key_named_file_chains_no_os_error(compose_api, sandbox, steps, pack, wait_until, check_compose_error) -> None:
    # AC-15 / INV-4 / EC-16 / ledger 3: the same through run_ensemble.
    # The Grok fork proposer answers in place; the opencode proposer
    # saves a file named after its own key in its worktree, and the
    # file is held at removal. WORKTREE_FAILED keeps the plan and both
    # proposals, the selector and the implementer never start, and no
    # surface of the error, its chain or its traceback shows a key.
    # Red until review R-34 lands.
    api = compose_api
    sandbox.make_repo()
    key_p, key_f, key_o, key_s, key_i = (pack.fresh_key(label) for label in ("planner", "fork", "proposer", "selector", "implementer"))
    keys = (key_p, key_f, key_o, key_s, key_i)
    name = f"{key_o}.txt"
    proposals = ["PROPOSAL-ONE: lazy imports.", "PROPOSAL-TWO: cache the parser."]
    planner = steps.bind("grok", plan=True, label="planner", key=key_p, fake={"text": pack.plan_json([("ROLE-ONE", "IDENTITY-ONE"), ("ROLE-TWO", "IDENTITY-TWO")])})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", key=key_f, fake={"text": proposals[0]})
    held = steps.bind("opencode", label="p-held", key=key_o, fake={"mode": "hold", "write_files": {f"{HELD}/{name}": "saved\n"}, "final_parts": [proposals[1]]})
    selector = steps.bind("grok", plan=True, label="selector", key=key_s, fake={"text": pack.selection_json(1)})
    implementer = steps.bind("grok", edits=True, label="implementer", key=key_i, fake={"text": "Implemented."})
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork, held], selector=selector, implementer=implementer)
    before = asyncio.all_tasks()
    task = asyncio.ensure_future(api.compose.run_ensemble(pack.TASK, roster=roster))
    hold = None
    try:
        # Wait for the fork proposer to answer and the opencode
        # proposer to save its key-named file, hold that file, then let
        # the proposer answer.
        assert await wait_until(lambda: bool(sandbox.launches(label="p-grok")) and pack.launch_answered(sandbox.only_launch("p-grok")) and bool(sandbox.launches(label="p-held")), pack.WAIT_SECONDS), "the fork proposer answered while the opencode proposer held"
        root = worktree_root(pack, sandbox.only_launch("p-held"))
        assert await wait_until(lambda: (root / HELD / name).is_file(), pack.WAIT_SECONDS), "the proposer saved its key-named file"
        hold = KeyFileHold(root, name)
        hold.hold()
        sandbox.release()
        with pytest.raises(api.ThreadComposeError) as caught:
            await asyncio.wait_for(task, pack.WAIT_SECONDS)
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        if hold is not None:
            hold.free()
        await settle(sandbox, before, pack.WAIT_SECONDS)
    error = caught.value

    # The EC-16 record keeps the plan and both proposals, and nothing
    # after the proposers started.
    check_compose_error(error, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(root))])
    assert "git worktree prune" in error.next_step
    record = error.result
    assert [role.name for role in record.plan.value.roles] == ["ROLE-ONE", "ROLE-TWO"], "the record keeps the plan"
    assert [outcome.text for outcome in record.proposals] == proposals
    assert sandbox.launches(label="selector") == [] and sandbox.launches(label="implementer") == []
    assert (registered, leftovers) == (1, [root.name]), "only the held folder is left, and it is no longer registered"

    # No surface of the error, of its chain or of its traceback shows a
    # key.
    chain = [type(item).__name__ for item in reachable(error)]
    assert pack.leaks(error_surfaces(error), keys) == [], f"INV-4: the error or its chain {chain} shows a key"
    assert pack.leaks(traceback_text(error), keys) == [], f"ledger 3: the traceback logging.exception prints shows a key; chain {chain}"


@pytest.mark.asyncio
async def test_a_temporary_folder_that_cannot_be_made_chains_no_os_error(compose_api, sandbox, steps, pack, monkeypatch) -> None:
    # INV-4 / EC-16 / the R-34 rule: compose's temporary folder cannot
    # be made, because the folder it is made in is a file. GIT_FAILED
    # comes before any launch and is raised after the OS error's
    # handler, so it keeps no __cause__ and no __context__. No key
    # reaches this OS text today; the row keeps the rule at the site
    # that makes compose's temporary folders. Red until review R-34
    # lands.
    api = compose_api
    sandbox.make_repo()
    key_w, key_r = pack.fresh_key("writer"), pack.fresh_key("reader")
    writer = steps.bind("opencode", label="writer", key=key_w)
    reader = steps.bind("grok", plan=True, label="reader", key=key_r)
    blocker = sandbox.root / "temporary-folder-is-a-file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(blocker))
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [reader], prompt=pack.PROMPT)
    error = caught.value
    assert error.problem.value == "git_failed" and sandbox.launches() == []
    assert pack.leaks(error_surfaces(error) + traceback_text(error), (key_w, key_r)) == []
    chain = [type(item).__name__ for item in reachable(error)[1:]]
    assert error.__cause__ is None and error.__context__ is None, f"the R-34 rule: GIT_FAILED chains {chain}"


@pytest.mark.asyncio
async def test_a_matching_folder_that_cannot_be_made_chains_no_os_error(compose_api, sandbox, steps, pack, monkeypatch) -> None:
    # INV-4 / EC-16 / the R-34 rule: the workspace is an empty folder
    # below the repository root, so the reader's worktree has no
    # folder of that name, and the operating system refuses to make
    # it. WORKTREE_FAILED comes before the reader starts and is raised
    # after the OS error's handler, so it keeps no __cause__ and no
    # __context__. Red until review R-34 lands.
    api = compose_api
    sandbox.make_repo()
    sub = sandbox.workspace / "matching-folder"
    sub.mkdir()
    key_w, key_r = pack.fresh_key("writer"), pack.fresh_key("reader")
    writer = steps.bind("opencode", label="writer", key=key_w, workspace=sub)
    reader = steps.bind("opencode", label="reader", key=key_r, workspace=sub, fake={"final_parts": [pack.verdict_json("approve")]})
    monkeypatch.setattr(os, "mkdir", FolderRefusal(pack.WORKTREE_PREFIX, sub.name))
    with pytest.raises(api.ThreadComposeError) as caught:
        await api.compose.verify_with(writer, [reader], prompt=pack.PROMPT)
    error = caught.value
    assert error.problem.value == "worktree_failed" and sandbox.launches(label="reader") == []
    assert sandbox.leftovers() == [], "the worktree that could not be prepared is removed"
    assert pack.leaks(error_surfaces(error) + traceback_text(error), (key_w, key_r)) == []
    chain = [type(item).__name__ for item in reachable(error)[1:]]
    assert error.__cause__ is None and error.__context__ is None, f"the R-34 rule: WORKTREE_FAILED chains {chain}"
