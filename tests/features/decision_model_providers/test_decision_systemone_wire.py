"""FILE: tests/features/decision_model_providers/test_decision_systemone_wire.py

PURPOSE: Pins the System One wire for the eight hosts SystemOneProvider.HOSTS lists: URL, authorization scheme, byte-identical TypeSafe body, OpenRouter's always-present noul criteria, transport kwargs with a fresh idempotency key, noul/score/choice normalization, the model echo rule (INV-27), and host-named mismatch messages with billed usage.
ROLE IN CODEBASE: Covers spec INV-5, INV-6, INV-8, INV-9, INV-14, INV-15, INV-27, AC-2, AC-3, AC-4, AC-7, AC-11, AC-18, EC-6, EC-9, EC-19, EC-24, EC-27 and NFR-4 of docs/spec/decision-model-providers/spec.md.
ARCHITECTURE NOTE: Each test drives DecisionModelRunner over a ScriptedTransport; the transport's recorded kwargs are the observable wire, the returned DecisionModelResponse and the raised errors are the observable results.
COMMON MODIFICATION PATTERNS: A new System One host adds a HOST_ROWS entry in decision_fixtures.py and is covered by every per-host loop here; a new answer kind gets its own normalization test.
KNOWN EDGE CASES: TypeSafe is in the loops so a drift between its body and another host's body is caught in the same assertion; Cloudflare and Foundry use the tenant endpoints from the fixtures.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 6.2, 9.1; docs/spec/decision-model-providers/context/provider-research.md section 3; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_systemone_wire.py
"""

from __future__ import annotations

import json
import os
import re
import unittest
from unittest.mock import patch

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MAX_RESPONSE_BYTES, JEV_RETRY_BACKOFF_SECONDS, JEV_RETRY_STATUS_CODES
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.runners.decision import DecisionModelRunner

SYSTEM_ONE_HOSTS = ("TYPESAFE", *fx.SYSTEM_ONE_DIRECT)
HEX_32 = re.compile(r"^[0-9a-f]{32}$")


def _answers(p_yes: float = 0.8) -> dict[str, object]:
    # The System One answers map for the section 4 request.
    return {"refund": fx.systemone_noul(p_yes), "team": fx.systemone_choice()}


class SystemOneRequestTests(unittest.IsolatedAsyncioTestCase):
    """Pins URL, authorization, and body per host."""

    async def test_each_host_posts_the_typesafe_body_to_its_documented_url(self) -> None:
        # [Silent Failure] INV-5/INV-6/AC-3/AC-7: the same body reaches each host at its own URL with its own auth scheme.
        for name in SYSTEM_ONE_HOSTS:
            row = fx.HOST_ROWS[name]
            with self.subTest(provider=name):
                runner, transport = fx.scripted_runner(name, fx.response(fx.systemone_body(_answers(), model=row.default_model)))
                response = await runner.arun(fx.customer_request())
                self.assertEqual(len(transport.requests), 1)
                sent = transport.requests[0]
                self.assertEqual((sent["method"], sent["url"]), ("POST", fx.expected_url(name)))
                self.assertEqual(sent["headers"]["authorization"], f"{row.auth_scheme} {fx.KEY}")
                self.assertEqual(sent["headers"]["content-type"], "application/json")
                body = sent["json_body"]
                self.assertEqual((body["model"], body["state"]), (row.default_model, fx.STATE))
                self.assertEqual(list(body["questions"]), ["refund", "team"])
                self.assertEqual(body["questions"]["team"], {"type": "choice", "instructions": "Which team owns the next step?", "criteria": {"billing": None, "logistics": None, "support": None}})
                self.assertEqual(body["questions"]["refund"]["type"], "noul")
                if row.noul_criteria_required:
                    self.assertEqual(body["questions"]["refund"]["criteria"], {"true": None, "false": None})
                else:
                    self.assertNotIn("criteria", body["questions"]["refund"])
                self.assertIs(response.provider, fx.provider_member(name))
                self.assertEqual(set(response.answers), {"refund", "team"})

    async def test_perplexity_body_is_byte_equal_to_the_typesafe_body(self) -> None:
        # [Silent Failure] AC-2: with the key from PERPLEXITY_API_KEY, the Perplexity body is the TypeSafe body for the same request.
        body = fx.systemone_body(_answers(), model="pplx-decider-v1.1-27b")
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": fx.KEY}, clear=False):
            perplexity_transport = fx.ScriptedTransport(fx.response(body))
            perplexity = DecisionModelRunner(DecisionModelConfig(provider=fx.provider_member("PERPLEXITY")), transport=perplexity_transport)
            response = await perplexity.arun(fx.customer_request())
        typesafe_transport = fx.ScriptedTransport(fx.response(fx.systemone_body(_answers(), model="jev-1.13.0")))
        typesafe = DecisionModelRunner(DecisionModelConfig(api_key=fx.KEY, model="pplx-decider-v1.1-27b"), transport=typesafe_transport)
        await typesafe.arun(fx.customer_request())
        sent = perplexity_transport.requests[0]
        self.assertEqual((sent["method"], sent["url"]), ("POST", "https://api.perplexity.ai/v1/decisions"))
        self.assertEqual(sent["headers"]["authorization"], f"Bearer {fx.KEY}")
        self.assertEqual(json.dumps(sent["json_body"]), json.dumps(typesafe_transport.requests[0]["json_body"]))
        self.assertEqual(sent["json_body"]["model"], "pplx-decider-v1.1-27b")
        self.assertIs(response.provider, fx.provider_member("PERPLEXITY"))
        self.assertEqual(response.model, "pplx-decider-v1.1-27b")
        self.assertEqual([answer.question_name for answer in response.answers.values()], ["refund", "team"])

    async def test_openrouter_always_sends_noul_criteria_while_other_hosts_keep_typesafe_behaviour(self) -> None:
        # [Hidden Failure] INV-6/EC-6/AC-4: OpenRouter rejects a noul without criteria, so nulls are sent; descriptions pass through everywhere.
        described = fx.noul_question(options=(JevOption("true", description="refund now"), JevOption("false", description="no refund")))
        cases = (
            ("OPENROUTER", fx.noul_question(), {"true": None, "false": None}),
            ("OPENROUTER", described, {"true": "refund now", "false": "no refund"}),
            ("PERPLEXITY", described, {"true": "refund now", "false": "no refund"}),
            ("PERPLEXITY", fx.noul_question(), None),
        )
        for name, question, criteria in cases:
            with self.subTest(provider=name, criteria=criteria):
                runner, transport = fx.scripted_runner(name, fx.response(fx.systemone_body({"refund": fx.systemone_noul(0.8)}, model=fx.HOST_ROWS[name].default_model)))
                await runner.arun(fx.customer_request(question))
                wire_question = transport.requests[0]["json_body"]["questions"]["refund"]
                if criteria is None:
                    self.assertNotIn("criteria", wire_question)
                else:
                    self.assertEqual(wire_question["criteria"], criteria)
                if name == "OPENROUTER":
                    self.assertEqual(transport.requests[0]["url"], "https://openrouter.ai/api/v1/systemone")
                    self.assertEqual(transport.requests[0]["json_body"]["model"], "typesafe/jev-1.13")

    async def test_structured_state_and_criteria_pass_through_as_plain_json_on_every_host(self) -> None:
        # [Silent Failure] INV-6: frozen content thaws back to the JSON TypeSafe receives today; score criteria stay an ordered array.
        angry = JevOption("angry", description={"signals": ["caps", "threats"]})
        structured = JevQuestion(name="frustration", question_type=JevQuestionType.SCORE, instructions="How frustrated is the customer?", options=(JevOption("calm"), JevOption("frustrated"), angry))
        for name in ("PERPLEXITY", "LIQUID", "FOUNDRY"):
            with self.subTest(provider=name):
                runner, transport = fx.scripted_runner(name, fx.response(fx.systemone_body({"frustration": fx.systemone_score()}, model=fx.HOST_ROWS[name].default_model)))
                await runner.arun(fx.customer_request(structured, state={"chat": ["hi", "help"]}))
                body = transport.requests[0]["json_body"]
                json.dumps(body)
                self.assertEqual(body["state"], {"chat": ["hi", "help"]})
                self.assertEqual(body["questions"]["frustration"]["criteria"], ["calm", "frustrated", {"signals": ["caps", "threats"]}])

    async def test_transport_kwargs_and_a_fresh_idempotency_key_on_every_host(self) -> None:
        # [Hidden Assumption] AC-11/INV-14/INV-15/NFR-4: one request per decision with the documented bounds and a fresh 32-hex key.
        for name in SYSTEM_ONE_HOSTS:
            with self.subTest(provider=name):
                body = fx.systemone_body(_answers(), model=fx.HOST_ROWS[name].default_model)
                runner, transport = fx.scripted_runner(name, fx.response(body), fx.response(body), retry_count=2, timeout_seconds=30.0)
                await runner.arun(fx.customer_request())
                await runner.arun(fx.customer_request())
                self.assertEqual(len(transport.requests), 2)
                first, second = transport.requests
                self.assertEqual((first["timeout_seconds"], first["retry_count"]), (30.0, 2))
                self.assertEqual(first["backoff_seconds"], JEV_RETRY_BACKOFF_SECONDS)
                self.assertEqual(tuple(first["retry_status_codes"]), tuple(JEV_RETRY_STATUS_CODES))
                self.assertEqual(first["max_response_bytes"], JEV_MAX_RESPONSE_BYTES)
                self.assertRegex(first["idempotency_key"], HEX_32)
                self.assertRegex(second["idempotency_key"], HEX_32)
                self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])
                self.assertNotIn("Idempotency-Key", first["headers"])
                no_retry, no_retry_transport = fx.scripted_runner(name, fx.response(body), retry_count=0)
                await no_retry.arun(fx.customer_request())
                self.assertIsNone(no_retry_transport.requests[0]["idempotency_key"])
                self.assertEqual(no_retry_transport.requests[0]["retry_count"], 0)


class SystemOneAnswerTests(unittest.IsolatedAsyncioTestCase):
    """Pins answer normalization, the model echo rule, and mismatch messages across hosts."""

    async def test_noul_answers_normalize_identically_on_every_wire(self) -> None:
        # [Silent Failure] INV-9: P(yes) expands to a true/false distribution with the 0.5 threshold and no confidence or score.
        for name in ("PERPLEXITY", "LIQUID", "CLOUDFLARE"):
            for p_yes in (0.0, 0.49, 0.5, 1.0):
                with self.subTest(provider=name, p_yes=p_yes):
                    runner, _ = fx.scripted_runner(name, fx.response(fx.systemone_body({"refund": fx.systemone_noul(p_yes)}, model=fx.HOST_ROWS[name].default_model)))
                    answer = (await runner.arun(fx.customer_request(fx.noul_question()))).answer("refund")
                    self.assertEqual(answer.noul, p_yes)
                    self.assertEqual(answer.probabilities["true"], p_yes)
                    self.assertAlmostEqual(answer.probabilities["false"], 1.0 - p_yes)
                    self.assertEqual(answer.choice, "true" if p_yes >= 0.5 else "false")
                    self.assertIsNone(answer.confidence)
                    self.assertIsNone(answer.score)

    async def test_score_and_choice_answers_normalize_on_a_non_typesafe_host(self) -> None:
        # [Silent Failure] section 9.1 matrix: index-keyed score probabilities map onto labels; choice keeps its distribution.
        body = fx.systemone_body({"team": fx.systemone_choice(), "frustration": fx.systemone_score()}, model="d1")
        runner, _ = fx.scripted_runner("LIQUID", fx.response(body))
        response = await runner.arun(fx.customer_request(fx.choice_question(), fx.score_question()))
        frustration = response.answer("frustration")
        self.assertEqual((frustration.choice, frustration.score, frustration.confidence), ("frustrated", 1.05, 0.92))
        self.assertEqual(dict(frustration.probabilities), {"calm": 0.0, "frustrated": 0.95, "angry": 0.05})
        team = response.answer("team")
        self.assertEqual((team.choice, team.confidence), ("billing", 0.7))
        self.assertEqual(dict(team.probabilities), {"billing": 0.7, "logistics": 0.2, "support": 0.1})
        self.assertEqual(response.model, "d1")

    async def test_documented_echo_hosts_report_the_echo_and_require_it(self) -> None:
        # [Hidden Failure] INV-27/EC-19: TypeSafe and Perplexity trust the echo; a missing echo is a billed error naming the host.
        cases = (("TYPESAFE", "jev-1.13.0"), ("PERPLEXITY", "pplx-decider-v1.1-27b"), ("PERPLEXITY", "pplx-decider-v1-27b"))
        for name, echo in cases:
            with self.subTest(provider=name, echo=echo):
                runner, _ = fx.scripted_runner(name, fx.response(fx.systemone_body(_answers(), model=echo)))
                self.assertEqual((await runner.arun(fx.customer_request())).model, echo)
        for name, missing in (("PERPLEXITY", fx.OMIT_MODEL), ("PERPLEXITY", None), ("PERPLEXITY", " ")):
            with self.subTest(provider=name, model=missing), self.assertRaises(ProviderResponseError) as caught:
                runner, _ = fx.scripted_runner(name, fx.response(fx.systemone_body(_answers(), model=missing)))
                await runner.arun(fx.customer_request())
            self.assertEqual(caught.exception.details["usage"], fx.USAGE)
            self.assertEqual(caught.exception.provider, "perplexity")
            self.assertTrue(caught.exception.message.startswith("Perplexity response has no `model` string naming the version that answered; received "))
        with self.assertRaises(ProviderResponseError) as caught:
            runner, _ = fx.scripted_runner("PERPLEXITY", fx.response(fx.systemone_body(_answers(), model=fx.OMIT_MODEL)))
            await runner.arun(fx.customer_request())
        self.assertEqual(caught.exception.message, "Perplexity response has no `model` string naming the version that answered; received NoneType None.")

    async def test_request_model_hosts_report_the_request_id_and_ignore_the_echo(self) -> None:
        # [Silent Failure] INV-27/EC-27/EC-19: pricing keys off response.model, so an undocumented echo must never replace the request id.
        cases = (
            ("OPENROUTER", None, fx.OMIT_MODEL, "typesafe/jev-1.13"),
            ("LIQUID", None, "d1-2026-09-01", "d1"),
            ("BASETEN", None, "mercury-decide-v2", "inception/mercury-decide"),
            ("MERAGPT", None, None, "sd-1"),
            ("CLOUDFLARE", None, "@cf/cloudflare/clef", "clef"),
            ("CLOUDFLARE", "clef-flash", "@cf/cloudflare/clef", "clef-flash"),
            ("FOUNDRY", None, fx.OMIT_MODEL, "microsoft-decision-1"),
            ("FOUNDRY", "my-deployment", "some-deployment-echo", "my-deployment"),
        )
        for name, requested, echo, expected in cases:
            with self.subTest(provider=name, echo=echo):
                overrides = {} if requested is None else {"model": requested}
                runner, transport = fx.scripted_runner(name, fx.response(fx.systemone_body(_answers(), model=echo)), **overrides)
                response = await runner.arun(fx.customer_request())
                self.assertEqual(response.model, expected)
                self.assertEqual(transport.requests[0]["json_body"]["model"], expected)
                self.assertEqual(response.usage, fx.USAGE)

    async def test_answer_mismatch_names_the_host_and_keeps_the_billed_usage(self) -> None:
        # [Hidden Failure] INV-8/AC-18/EC-9: partial or mislabeled answers are a typed error with usage, worded for the host that answered.
        request = fx.customer_request(fx.noul_question(), fx.choice_question(), fx.score_question())
        partial = {"refund": fx.systemone_noul(0.8), "team": fx.systemone_choice(), "extra": fx.systemone_noul(0.1)}
        with self.assertRaises(ProviderResponseError) as caught:
            runner, _ = fx.scripted_runner("BASETEN", fx.response(fx.systemone_body(partial, model=fx.OMIT_MODEL)))
            await runner.arun(request)
        self.assertEqual(caught.exception.message, "Baseten answers do not match the questions sent: missing ['frustration'], unexpected ['extra'].")
        self.assertEqual(caught.exception.details["usage"], fx.USAGE)
        self.assertEqual(caught.exception.provider, "baseten")
        self.assertNotIn("TypeSafe", caught.exception.message)
        with self.assertRaises(ProviderResponseError) as typesafe:
            runner, _ = fx.scripted_runner("TYPESAFE", fx.response(fx.systemone_body(partial, model="jev-1.13.0")))
            await runner.arun(request)
        self.assertEqual(typesafe.exception.message.replace("TypeSafe", "Baseten"), caught.exception.message)
        wrong_type = {"refund": fx.systemone_noul(0.8), "team": {**fx.systemone_choice(), "type": "score"}}
        with self.assertRaises(ProviderResponseError) as mistyped:
            runner, _ = fx.scripted_runner("LIQUID", fx.response(fx.systemone_body(wrong_type, model="d1")))
            await runner.arun(fx.customer_request())
        self.assertEqual(mistyped.exception.message, "Liquid AI answer for 'team' has type 'score', but the question was 'choice'.")
        self.assertEqual(mistyped.exception.details["usage"], fx.USAGE)
        wrong_labels = {"refund": fx.systemone_noul(0.8), "team": fx.systemone_choice(probabilities={"billing": 0.7, "logistics": 0.2, "z": 0.1})}
        with self.assertRaises(ProviderResponseError) as mislabeled:
            runner, _ = fx.scripted_runner("MERAGPT", fx.response(fx.systemone_body(wrong_labels, model=fx.OMIT_MODEL)))
            await runner.arun(fx.customer_request())
        self.assertEqual(mislabeled.exception.message, "meraGPT `probabilities` for 'team' do not match its options: missing ['support'], unexpected ['z'].")
        self.assertEqual(mislabeled.exception.provider, "meragpt")


if __name__ == "__main__":
    unittest.main()
