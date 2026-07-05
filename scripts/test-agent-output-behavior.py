"""Verification script for agent output behavior.

Runs the test cases from Section 10 of docs/design/agent-output-behavior.md.
Prints PASS/FAIL per test case and exits non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput
from vidbyte.evals import Behavior, ContainsGrader, EvalCase, EvalRunner, EvalSuite, PredicateGrader, RunProbe
from vidbyte.evals.behavior.output import OutputBehavior
from vidbyte.evals.behavior.tool import ToolBehavior
from vidbyte.lib.dataclasses.agents import AgentMessage


class StructuredPayload(BaseModel):
    """Pydantic payload used to verify model_dump structured traversal."""

    answer: str
    items: list[dict[str, Any]]


class StubAgent:
    """Minimal stub mimicking BaseAgent post-run fields for RunProbe tests."""

    def __init__(self, reply: AgentMessage | None = None) -> None:
        # Stores the reply and minimal post-run fields expected by RunProbe.
        self.last_reply = reply
        self.last_handoff = None
        self.handoffs = []
        self.last_trace = None


class MockAgent(BaseAgent):
    """BaseAgent subclass returning scripted replies with output metadata."""

    def __init__(self, reply_metadata: dict[str, Any] | None = None, reply_content: str = "processed") -> None:
        # Initializes a scriptable mock agent for EvalRunner and behavior integration tests.
        super().__init__(name="mock", system_prompt="test", runner=object())
        self._reply_metadata = reply_metadata or {}
        self._reply_content = reply_content

    def fork(self, **kwargs: Any) -> MockAgent:
        # Returns self to keep tests deterministic while still exercising EvalRunner's agent path.
        return self

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Simulates BaseAgent.generate_reply cache invalidation and reply recording.
        self._behavior_view = None
        reply = AgentMessage(sender="mock", recipient="orchestrator", content=self._reply_content, metadata=dict(self._reply_metadata))
        self.last_reply = reply
        return reply


class TestRunner:
    """Collects test results and prints a simple PASS/FAIL report."""

    def __init__(self) -> None:
        # Initializes an empty result list for this script run.
        self._results: list[tuple[str, bool, str]] = []

    def run(self, name: str, test_fn: Any) -> None:
        # Runs a synchronous test function and records a PASS/FAIL result.
        try:
            test_fn()
            self._results.append((name, True, ""))
            print(f"PASS: {name}")
        except AssertionError as exc:
            self._results.append((name, False, str(exc)))
            print(f"FAIL: {name} - {exc}")
        except Exception as exc:
            self._results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL: {name} - {type(exc).__name__}: {exc}")

    async def run_async(self, name: str, test_fn: Any) -> None:
        # Runs an asynchronous test function and records a PASS/FAIL result.
        try:
            await test_fn()
            self._results.append((name, True, ""))
            print(f"PASS: {name}")
        except AssertionError as exc:
            self._results.append((name, False, str(exc)))
            print(f"FAIL: {name} - {exc}")
        except Exception as exc:
            self._results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL: {name} - {type(exc).__name__}: {exc}")

    def summary(self) -> int:
        # Prints the final pass count and returns the intended process exit code.
        passed = sum(1 for _, ok, _ in self._results if ok)
        total = len(self._results)
        print(f"\n{passed}/{total} tests passed")
        return 0 if passed == total else 1


def make_reply(content: str = "reply", metadata: dict[str, Any] | None = None) -> AgentMessage:
    # Builds an AgentMessage with the given content and metadata.
    return AgentMessage(sender="agent", recipient="orchestrator", content=content, metadata=metadata or {})


def behavior_from_probe(probe: RunProbe) -> Behavior:
    # Builds a Behavior facade backed by a pre-built probe.
    b = Behavior.__new__(Behavior)
    b._agent = None
    b._probe = probe
    b._output = OutputBehavior.__new__(OutputBehavior)
    b._output._behavior = b
    b._tool = ToolBehavior.__new__(ToolBehavior)
    b._tool._behavior = b
    return b


def output_behavior(text: str = "", structured: Any = None) -> OutputBehavior:
    # Builds an OutputBehavior backed by a RunProbe with the provided text and structured data.
    return behavior_from_probe(RunProbe(output=text, structured=structured)).output


def expect(condition: bool) -> None:
    # Raises AssertionError when condition is false so lambdas can act as test cases.
    if not condition:
        raise AssertionError("condition was false")


def expect_raises(exc_type: type[BaseException], fn: Any) -> None:
    # Raises AssertionError unless fn raises the expected exception type.
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_probe_from_agent_structured() -> None:
    # [Hidden Assumption] from_agent copies metadata["structured"] into probe.structured.
    structured = {"answer": "yes"}
    probe = RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"structured": structured})))
    assert probe.structured is structured


def test_probe_from_reply_structured() -> None:
    # [Hidden Assumption] from_reply copies metadata["structured"] without an agent.
    structured = {"answer": "yes"}
    probe = RunProbe.from_reply(make_reply(metadata={"structured": structured}))
    assert probe.structured is structured


def test_probe_missing_structured_defaults_none() -> None:
    # [Edge Case] missing structured metadata leaves probe.structured as None.
    assert RunProbe.from_reply(make_reply()).structured is None


def test_output_empty_and_whitespace() -> None:
    # [Edge Case / Silent Failure] output emptiness handles empty and whitespace strings.
    assert behavior_from_probe(RunProbe(output="")).output.is_empty() is True
    assert behavior_from_probe(RunProbe(output="   ")).output.is_empty(strip=True) is True
    assert behavior_from_probe(RunProbe(output="   ")).output.is_empty(strip=False) is False
    assert behavior_from_probe(RunProbe(output="x")).output.is_not_empty(strip=True) is True


def test_output_length_line_word_counts() -> None:
    # [Edge Case / Silent Failure] output count predicates use inclusive bounds and token counts.
    out = behavior_from_probe(RunProbe(output="one, two three"))
    assert behavior_from_probe(RunProbe(output="")).output.length(at_least=0, at_most=0) is True
    assert behavior_from_probe(RunProbe(output="abcd")).output.length(at_least=2, at_most=4) is True
    assert behavior_from_probe(RunProbe(output="abcde")).output.length(at_most=4) is False
    assert behavior_from_probe(RunProbe(output="")).output.line_count(at_least=0, at_most=0) is True
    assert behavior_from_probe(RunProbe(output="a\nb")).output.line_count(at_least=2, at_most=2) is True
    assert out.output.word_count(at_least=3, at_most=3) is True


def test_output_json_validity() -> None:
    # [Edge Case / Hidden Failure / Silent Failure] JSON validity is boolean and non-throwing.
    assert behavior_from_probe(RunProbe(output="")).output.is_valid_json() is False
    assert behavior_from_probe(RunProbe(output="{bad")).output.is_valid_json() is False
    assert behavior_from_probe(RunProbe(output='{"a": 1}')).output.is_valid_json() is True
    assert behavior_from_probe(RunProbe(output="[1, 2]")).output.is_valid_json() is True


def test_output_code_blocks() -> None:
    # [Edge Case / Hidden Failure / Silent Failure] code block predicates detect closed fences and language.
    output = "Before\n```Python\nprint('x')\n```\n~~~js\nconsole.log(1)\n~~~"
    b = behavior_from_probe(RunProbe(output=output))
    assert b.output.contains_code_block() is True
    assert b.output.contains_code_block("python") is True
    assert b.output.code_block_count() == 2
    assert b.output.code_block_count("python") == 1
    assert b.output.code_block_count("python", at_least=1, at_most=1) is True
    assert behavior_from_probe(RunProbe(output="```python\nx")).output.contains_code_block() is False
    assert behavior_from_probe(RunProbe(output="plain")).output.code_block_count(at_least=0, at_most=0) is True


def test_output_urls_and_citations() -> None:
    # [Edge Case / Silent Failure / Hidden Failure] URL and citation predicates cover all styles.
    assert behavior_from_probe(RunProbe(output="no link")).output.contains_url() is False
    links = behavior_from_probe(RunProbe(output="https://a.test http://b.test www.c.test"))
    assert links.output.contains_url() is True
    assert links.output.url_count(at_least=3, at_most=3) is True
    assert behavior_from_probe(RunProbe(output="no citations")).output.contains_citation() is False
    cited = behavior_from_probe(RunProbe(output="See [source](https://example.com), [1], and [^note]."))
    assert cited.output.contains_citation("markdown") is True
    assert cited.output.contains_citation("bracket") is True
    assert cited.output.contains_citation("footnote") is True
    assert cited.output.contains_citation("url") is True
    assert cited.output.citation_count("any", at_least=4) is True
    try:
        cited.output.contains_citation("apa")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown citation style should raise ValueError")


def test_output_refusal_hedging_prefix_suffix() -> None:
    # [Silent Failure / Edge Case] stance and boundary predicates normalize as expected.
    assert behavior_from_probe(RunProbe(output="I can't help with that.")).output.refused() is True
    assert behavior_from_probe(RunProbe(output="I cannot comply.")).output.refused() is True
    assert behavior_from_probe(RunProbe(output="I'm unable to do that.")).output.refused() is True
    assert behavior_from_probe(RunProbe(output="I can help with that.")).output.refused() is False
    assert behavior_from_probe(RunProbe(output="Maybe this is likely correct.")).output.contains_hedging() is True
    assert behavior_from_probe(RunProbe(output="This is correct.")).output.contains_hedging() is False
    b = behavior_from_probe(RunProbe(output=" Result: done. \n"))
    assert b.output.starts_with("result:", case_sensitive=False, strip=True) is True
    assert b.output.ends_with(".", strip=True) is True
    assert b.output.starts_with("") is True
    assert b.output.ends_with("") is True


def test_structured_fields() -> None:
    # [Edge Case / Silent Failure / Hidden Failure] structured path predicates handle nested and falsey values.
    assert behavior_from_probe(RunProbe(structured=None)).output.structured_valid() is False
    assert behavior_from_probe(RunProbe(structured={})).output.structured_valid() is True
    b = behavior_from_probe(RunProbe(structured={"answer": "", "items": [{"title": "First"}], "count": 0, "a": 0, "b": False}))
    assert b.output.structured_field_exists("answer") is True
    assert b.output.structured_field_exists("items.0.title") is True
    assert b.output.structured_field_exists("missing") is False
    assert b.output.structured_field_exists("items.x.title") is False
    assert b.output.structured_field_exists("items.99.title") is False
    assert b.output.structured_field_equals("count", 0) is True
    assert b.output.structured_field_matches("count", lambda v: v == 0) is True
    assert b.output.structured_field_matches("missing", lambda v: True) is False
    assert b.output.structured_field_type("items", list) is True
    assert b.output.structured_contains_keys(["a", "b"]) is True
    assert b.output.structured_contains_keys(["a", "c"]) is False
    try:
        b.output.structured_field_matches("count", lambda v: (_ for _ in ()).throw(ValueError("boom")))
    except ValueError:
        pass
    else:
        raise AssertionError("predicate errors should propagate")


def test_structured_pydantic_model_dump() -> None:
    # [Hidden Assumption] Pydantic structured objects are supported through model_dump().
    payload = StructuredPayload(answer="yes", items=[{"title": "First"}])
    b = behavior_from_probe(RunProbe(structured=payload))
    assert b.output.structured_field_equals("answer", "yes") is True
    assert b.output.structured_field_exists("items.0.title") is True


def test_behavior_facade_output() -> None:
    # [Edge Case / Silent Failure / Hidden Assumption] facade exposes a cached output category using the same probe.
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    assert isinstance(agent.behavior.output, OutputBehavior)
    assert agent.behavior.output is agent.behavior.output
    b = behavior_from_probe(RunProbe(output="x"))
    assert b.output._behavior.probe is b.tool._behavior.probe


async def test_integration_agent_output_behavior() -> None:
    # [Hidden Assumption / Silent Failure] agent behavior sees structured metadata and code block output.
    agent = MockAgent(reply_metadata={"structured": {"answer": "yes"}}, reply_content='{"answer": "yes"}')
    await agent.arun("answer")
    assert agent.behavior.output.structured_field_equals("answer", "yes") is True
    assert agent.behavior.output.is_valid_json() is True
    code_agent = MockAgent(reply_content="```python\nprint('x')\n```")
    await code_agent.arun("code")
    assert code_agent.behavior.output.contains_code_block("python") is True


async def test_integration_eval_runner_output_behavior() -> None:
    # [Hidden Failure] EvalRunner passes structured output to PredicateGrader and leaves standard graders unchanged.
    agent = MockAgent(reply_metadata={"structured": {"answer": "yes"}}, reply_content='{"answer": "yes"}')
    suite = EvalSuite("s", [EvalCase(prompt="t", grader=PredicateGrader(lambda p: p.structured is not None and p.output != ""))])
    result = await EvalRunner(agent, default_grader=PredicateGrader(lambda p: False)).arun(suite)
    assert result.results[0].grader_result.passed is True
    standard = await EvalRunner(MockAgent(reply_content="processed"), default_grader=ContainsGrader()).arun(
        EvalSuite("s", [EvalCase(prompt="t", expected="processed", grader=ContainsGrader())])
    )
    assert standard.results[0].grader_result.passed is True


async def test_integration_output_cache_invalidation() -> None:
    # [Silent Failure] a second run invalidates cached output behavior probe.
    agent = MockAgent(reply_content="first output")
    await agent.arun("first")
    assert agent.behavior.output.starts_with("first") is True
    agent._reply_content = "second output"
    await agent.arun("second")
    assert agent.behavior.output.starts_with("first") is False
    assert agent.behavior.output.starts_with("second") is True


async def run_async_tests(tr: TestRunner) -> None:
    # Runs every asynchronous integration test in sequence.
    await tr.run_async("integration_agent_output_behavior [Hidden Assumption/Silent Failure]", test_integration_agent_output_behavior)
    await tr.run_async("integration_eval_runner_output_behavior [Hidden Failure]", test_integration_eval_runner_output_behavior)
    await tr.run_async("integration_output_cache_invalidation [Silent Failure]", test_integration_output_cache_invalidation)


def main() -> int:
    # Runs every Section 10 test case and returns a process exit code.
    tr = TestRunner()
    structured = {"answer": "yes"}
    tr.run("RunProbe.from_agent structured [Hidden Assumption]", lambda: expect(RunProbe.from_agent(StubAgent(reply=make_reply(metadata={"structured": structured}))).structured is structured))
    tr.run("RunProbe.from_reply structured [Hidden Assumption]", lambda: expect(RunProbe.from_reply(make_reply(metadata={"structured": structured})).structured is structured))
    tr.run("RunProbe missing structured [Edge Case]", lambda: expect(RunProbe.from_reply(make_reply()).structured is None))

    tr.run("output empty string [Edge Case]", lambda: expect(output_behavior("").is_empty() is True))
    tr.run("output whitespace empty with strip [Edge Case]", lambda: expect(output_behavior("   ").is_empty(strip=True) is True))
    tr.run("output whitespace not empty without strip [Silent Failure]", lambda: expect(output_behavior("   ").is_empty(strip=False) is False))
    tr.run("output is_not_empty negates empty [Silent Failure]", lambda: expect(output_behavior("text").is_not_empty(strip=True) is True))
    tr.run("output length zero bounds [Edge Case]", lambda: expect(output_behavior("").length(at_least=0, at_most=0) is True))
    tr.run("output length inclusive bounds [Silent Failure]", lambda: expect(output_behavior("abcd").length(at_least=2, at_most=4) is True))
    tr.run("output line_count empty [Edge Case]", lambda: expect(output_behavior("").line_count(at_least=0, at_most=0) is True))
    tr.run("output line_count splitlines [Silent Failure]", lambda: expect(output_behavior("a\nb").line_count(at_least=2, at_most=2) is True))
    tr.run("output word_count tokens [Silent Failure]", lambda: expect(output_behavior("one, two three").word_count(at_least=3, at_most=3) is True))

    tr.run("output valid_json empty false [Edge Case]", lambda: expect(output_behavior("").is_valid_json() is False))
    tr.run("output valid_json malformed false [Hidden Failure]", lambda: expect(output_behavior("{bad").is_valid_json() is False))
    tr.run("output valid_json object true [Silent Failure]", lambda: expect(output_behavior('{"a": 1}').is_valid_json() is True))
    tr.run("output valid_json array true [Silent Failure]", lambda: expect(output_behavior("[1, 2]").is_valid_json() is True))
    code = "Before\n```Python\nprint('x')\n```\n~~~js\nconsole.log(1)\n~~~"
    tr.run("output code_block absent false [Edge Case]", lambda: expect(output_behavior("plain").contains_code_block() is False))
    tr.run("output code_block unclosed false [Hidden Failure]", lambda: expect(output_behavior("```python\nx").contains_code_block() is False))
    tr.run("output code_block language case-insensitive [Silent Failure]", lambda: expect(output_behavior(code).contains_code_block("python") is True))
    tr.run("output code_block_count language only [Silent Failure]", lambda: expect(output_behavior(code).code_block_count("python") == 1))
    tr.run("output code_block_count zero bounds [Edge Case]", lambda: expect(output_behavior("plain").code_block_count(at_least=0, at_most=0) is True))

    urls = "https://a.test http://b.test www.c.test"
    citations = "See [source](https://example.com), [1], and [^note]."
    tr.run("output contains_url absent false [Edge Case]", lambda: expect(output_behavior("no link").contains_url() is False))
    tr.run("output contains_url detects forms [Silent Failure]", lambda: expect(output_behavior(urls).url_count(at_least=3, at_most=3) is True))
    tr.run("output url_count two urls [Silent Failure]", lambda: expect(output_behavior("https://a.test http://b.test").url_count(at_least=2, at_most=2) is True))
    tr.run("output contains_citation absent false [Edge Case]", lambda: expect(output_behavior("no citations").contains_citation() is False))
    tr.run("output citation markdown [Silent Failure]", lambda: expect(output_behavior(citations).contains_citation("markdown") is True))
    tr.run("output citation bracket [Silent Failure]", lambda: expect(output_behavior(citations).contains_citation("bracket") is True))
    tr.run("output citation footnote [Silent Failure]", lambda: expect(output_behavior(citations).contains_citation("footnote") is True))
    tr.run("output citation url [Silent Failure]", lambda: expect(output_behavior(citations).contains_citation("url") is True))
    tr.run("output citation unknown raises [Hidden Failure]", lambda: expect_raises(ValueError, lambda: output_behavior(citations).contains_citation("apa")))

    tr.run("output refused detects cant [Silent Failure]", lambda: expect(output_behavior("I can't help with that.").refused() is True))
    tr.run("output refused detects cannot [Silent Failure]", lambda: expect(output_behavior("I cannot comply.").refused() is True))
    tr.run("output refused detects unable [Silent Failure]", lambda: expect(output_behavior("I'm unable to do that.").refused() is True))
    tr.run("output refused ordinary false [Edge Case]", lambda: expect(output_behavior("I can help with that.").refused() is False))
    tr.run("output hedging detects terms [Silent Failure]", lambda: expect(output_behavior("Maybe this is likely correct.").contains_hedging() is True))
    tr.run("output hedging decisive false [Edge Case]", lambda: expect(output_behavior("This is correct.").contains_hedging() is False))
    tr.run("output starts_with casefold [Silent Failure]", lambda: expect(output_behavior(" Result: done. \n").starts_with("result:", case_sensitive=False, strip=True) is True))
    tr.run("output ends_with strip [Silent Failure]", lambda: expect(output_behavior(" Result: done. \n").ends_with(".", strip=True) is True))
    tr.run("output empty prefix suffix true [Edge Case]", lambda: expect(output_behavior("x").starts_with("") is True and output_behavior("x").ends_with("") is True))

    data = {"answer": "", "items": [{"title": "First"}], "count": 0, "score": 0.9, "a": 0, "b": False}
    tr.run("structured_valid none false [Edge Case]", lambda: expect(output_behavior(structured=None).structured_valid() is False))
    tr.run("structured_valid empty dict true [Edge Case]", lambda: expect(output_behavior(structured={}).structured_valid() is True))
    tr.run("structured_field_exists falsey [Silent Failure]", lambda: expect(output_behavior(structured=data).structured_field_exists("answer") is True))
    tr.run("structured_field_exists missing false [Hidden Failure]", lambda: expect(output_behavior(structured=data).structured_field_exists("missing") is False))
    tr.run("structured_field_exists nested list [Silent Failure]", lambda: expect(output_behavior(structured=data).structured_field_exists("items.0.title") is True))
    tr.run("structured_field_exists noninteger index false [Hidden Failure]", lambda: expect(output_behavior(structured=data).structured_field_exists("items.x.title") is False))
    tr.run("structured_field_exists out-of-range false [Hidden Failure]", lambda: expect(output_behavior(structured=data).structured_field_exists("items.99.title") is False))
    tr.run("structured_field_equals falsey [Silent Failure]", lambda: expect(output_behavior(structured=data).structured_field_equals("count", 0) is True))
    tr.run("structured_field_matches predicate [Hidden Assumption]", lambda: expect(output_behavior(structured=data).structured_field_matches("score", lambda v: v > 0.8) is True))
    tr.run("structured_field_matches exception propagates [Hidden Failure]", lambda: expect_raises(ValueError, lambda: output_behavior(structured=data).structured_field_matches("score", lambda v: (_ for _ in ()).throw(ValueError("boom")))))
    tr.run("structured_field_type list [Silent Failure]", lambda: expect(output_behavior(structured=data).structured_field_type("items", list) is True))
    tr.run("structured_contains_keys all required [Silent Failure]", lambda: expect(output_behavior(structured=data).structured_contains_keys(["a", "b"]) is True))
    tr.run("structured pydantic model_dump [Hidden Assumption]", lambda: expect(output_behavior(structured=StructuredPayload(answer="yes", items=[{"title": "First"}])).structured_field_exists("items.0.title") is True))

    tr.run("behavior output property [Edge Case]", lambda: expect(isinstance(BaseAgent(name="t", system_prompt="t", runner=object()).behavior.output, OutputBehavior)))
    agent = BaseAgent(name="t", system_prompt="t", runner=object())
    tr.run("behavior output cached category [Silent Failure]", lambda: expect(agent.behavior.output is agent.behavior.output))
    b = behavior_from_probe(RunProbe(output="x"))
    tr.run("behavior output shared probe [Hidden Assumption]", lambda: expect(b.output._behavior.probe is b.tool._behavior.probe))

    asyncio.run(run_async_tests(tr))
    return tr.summary()


if __name__ == "__main__":
    sys.exit(main())
