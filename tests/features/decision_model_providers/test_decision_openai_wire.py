"""FILE: tests/features/decision_model_providers/test_decision_openai_wire.py

PURPOSE: Pins the OpenAI Decisions wire: the exact request body in question order, answers matched by name in any order, JSON-text serialization of structured content, refusal of noul option descriptions before any call, refusal answers, drifted answers, score label fallback, the request id as response.model, and the Vercel endpoint-override recipe.
ROLE IN CODEBASE: Covers spec INV-7, INV-8, INV-9, INV-27, AC-5, AC-6, AC-17, EC-7, EC-8, EC-10, EC-11 and D-8, D-11 of docs/spec/decision-model-providers/spec.md.
ARCHITECTURE NOTE: DecisionModelRunner over a ScriptedTransport; the recorded json_body is compared as a whole Python object so list order (questions, choices, levels) is part of the assertion.
COMMON MODIFICATION PATTERNS: A new OpenAI answer shape gets one normalization test and one drift test; keep literal bodies in sync with provider-research.md section 3.1.
KNOWN EDGE CASES: OpenAI's response-level model echo is undocumented, so response.model is always the request id; predicate questions carry no choices or levels key at all.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 6.2, 8.1 (D-8, D-11), 9.1; docs/spec/decision-model-providers/context/provider-research.md section 3.1; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_openai_wire.py
"""

from __future__ import annotations

import json
import unittest

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.lib.constants.jev import JEV_MAX_RESPONSE_BYTES, JEV_RETRY_BACKOFF_SECONDS, JEV_RETRY_STATUS_CODES
from vidbyte.lib.dataclasses.jev import JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError

THREE_QUESTIONS = (fx.noul_question(), fx.choice_question(), fx.score_question())
THREE_ANSWERS = [fx.openai_predicate("refund", 0.8), fx.openai_choice(), fx.openai_score()]
EXPECTED_BODY = {
    "model": "gpt-6-luna",
    "input": fx.STATE,
    "questions": [
        {"type": "predicate", "name": "refund", "instructions": "Should this customer receive a refund?"},
        {"type": "choice", "name": "team", "instructions": "Which team owns the next step?", "choices": [{"value": "billing"}, {"value": "logistics"}, {"value": "support"}]},
        {"type": "score", "name": "frustration", "instructions": "How frustrated is the customer?", "levels": [{"label": "calm"}, {"label": "frustrated"}, {"label": "angry"}]},
    ],
}


class OpenAIRequestTests(unittest.IsolatedAsyncioTestCase):
    """Pins the request body, URL, headers, and the pre-call refusal."""

    async def test_body_is_the_documented_decisions_request_in_question_order(self) -> None:
        # [Silent Failure] INV-7/AC-5: the whole body, including list order, is compared against the documented shape.
        runner, transport = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(THREE_ANSWERS)))
        response = await runner.arun(fx.customer_request(*THREE_QUESTIONS))
        self.assertEqual(len(transport.requests), 1)
        sent = transport.requests[0]
        self.assertEqual((sent["method"], sent["url"]), ("POST", "https://api.openai.com/v1/decisions"))
        self.assertEqual(sent["headers"]["authorization"], f"Bearer {fx.KEY}")
        self.assertEqual(sent["json_body"], EXPECTED_BODY)
        json.dumps(sent["json_body"])
        self.assertEqual(set(response.answers), {"refund", "team", "frustration"})

    async def test_structured_content_becomes_json_text_and_descriptions_are_sent(self) -> None:
        # [Silent Failure] EC-8/D-11: input and instructions are strings on this wire; descriptions ride on choices and levels.
        state = {"chat": ["hi", "hélp"]}
        instructions = ["step one", "step two"]
        choice = JevQuestion(name="team", question_type=JevQuestionType.CHOICE, instructions=instructions, options=(JevOption("billing", description="Billing team"), JevOption("support")))
        score = JevQuestion(name="frustration", question_type=JevQuestionType.SCORE, instructions="How frustrated?", options=(JevOption("calm"), JevOption("angry", description={"signals": ["caps"]})))
        answers = [fx.openai_choice(choice="billing", probabilities=[{"value": "billing", "probability": 0.9}, {"value": "support", "probability": 0.1}]), fx.openai_score(probabilities=[{"value": 0, "label": "calm", "probability": 0.4}, {"value": 1, "label": "angry", "probability": 0.6}])]
        answers[1]["score"] = 0.6
        runner, transport = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(answers)))
        await runner.arun(fx.customer_request(choice, score, state=state))
        body = transport.requests[0]["json_body"]
        self.assertEqual(body["input"], json.dumps(state, ensure_ascii=False))
        self.assertIn("hélp", body["input"])
        self.assertEqual(body["questions"][0]["instructions"], json.dumps(instructions, ensure_ascii=False))
        self.assertEqual(body["questions"][0]["choices"], [{"value": "billing", "description": "Billing team"}, {"value": "support"}])
        self.assertEqual(body["questions"][1]["levels"], [{"label": "calm"}, {"label": "angry", "description": json.dumps({"signals": ["caps"]}, ensure_ascii=False)}])

    async def test_noul_option_descriptions_are_refused_before_any_call(self) -> None:
        # [Hidden Failure] AC-17/EC-7/D-11: predicate questions have no criteria slot, and criteria are never silently dropped.
        described = fx.noul_question(options=(JevOption("true", description="refund now"), JevOption("false", description="no refund")))
        runner, transport = fx.scripted_runner("OPENAI")
        with self.assertRaises(ConfigurationError) as caught:
            await runner.arun(fx.customer_request(described))
        self.assertEqual(caught.exception.message, "OpenAI predicate questions take instructions only; question 'refund' carries true/false criteria — move them into its instructions.")
        self.assertEqual(transport.requests, [])
        bare_options = fx.noul_question(options=(JevOption("true"), JevOption("false")))
        runner, transport = fx.scripted_runner("OPENAI", fx.response(fx.openai_body([fx.openai_predicate("refund", 0.2)])))
        await runner.arun(fx.customer_request(bare_options))
        predicate = transport.requests[0]["json_body"]["questions"][0]
        self.assertEqual(predicate, {"type": "predicate", "name": "refund", "instructions": "Should this customer receive a refund?"})

    async def test_transport_kwargs_and_a_fresh_idempotency_key_on_openai(self) -> None:
        # [Hidden Assumption] AC-11/INV-14/INV-15: the OpenAI adapter passes the same bounds and a fresh 32-hex key per call.
        body = fx.openai_body([fx.openai_predicate("refund", 0.8), fx.openai_choice()])
        runner, transport = fx.scripted_runner("OPENAI", fx.response(body), fx.response(body), retry_count=2, timeout_seconds=30.0)
        await runner.arun(fx.customer_request())
        await runner.arun(fx.customer_request())
        first, second = transport.requests
        self.assertEqual((first["timeout_seconds"], first["retry_count"]), (30.0, 2))
        self.assertEqual(first["backoff_seconds"], JEV_RETRY_BACKOFF_SECONDS)
        self.assertEqual(tuple(first["retry_status_codes"]), tuple(JEV_RETRY_STATUS_CODES))
        self.assertEqual(first["max_response_bytes"], JEV_MAX_RESPONSE_BYTES)
        self.assertRegex(first["idempotency_key"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertNotIn("Idempotency-Key", first["headers"])
        no_retry, no_retry_transport = fx.scripted_runner("OPENAI", fx.response(body), retry_count=0)
        await no_retry.arun(fx.customer_request())
        self.assertIsNone(no_retry_transport.requests[0]["idempotency_key"])

    async def test_vercel_recipe_uses_the_endpoint_override_and_the_caller_model(self) -> None:
        # [Hidden Assumption] D-8/T-1: Vercel is reached through this adapter by endpoint override with an explicit key and model.
        runner, transport = fx.scripted_runner("OPENAI", fx.response(fx.openai_body([fx.openai_predicate("refund", 0.8)], model="openai/gpt-6-luna-decisions")), endpoint="https://ai-gateway.vercel.sh/v1", model="openai/gpt-6-luna-decisions")
        response = await runner.arun(fx.customer_request(fx.noul_question()))
        sent = transport.requests[0]
        self.assertEqual(sent["url"], "https://ai-gateway.vercel.sh/v1/decisions")
        self.assertEqual(sent["json_body"]["model"], "openai/gpt-6-luna-decisions")
        self.assertEqual(response.model, "openai/gpt-6-luna-decisions")


class OpenAIAnswerTests(unittest.IsolatedAsyncioTestCase):
    """Pins answer normalization, drift handling, and the response model rule."""

    async def test_answers_array_in_any_order_normalizes_by_name(self) -> None:
        # [Silent Failure] AC-5/INV-8/INV-9: array order is irrelevant; each kind becomes the same JevAnswer System One produces.
        runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(list(reversed(THREE_ANSWERS)))))
        response = await runner.arun(fx.customer_request(*THREE_QUESTIONS))
        self.assertIs(response.provider, fx.provider_member("OPENAI"))
        self.assertEqual(response.model, "gpt-6-luna")
        self.assertEqual(response.usage, fx.USAGE)
        refund = response.answer("refund")
        self.assertEqual((refund.noul, refund.choice, refund.confidence, refund.score), (0.8, "true", None, None))
        self.assertAlmostEqual(refund.probabilities["false"], 0.2)
        self.assertEqual(set(refund.probabilities), {"true", "false"})
        team = response.answer("team")
        self.assertEqual((team.choice, team.confidence), ("billing", 0.7))
        self.assertEqual(dict(team.probabilities), {"billing": 0.7, "logistics": 0.2, "support": 0.1})
        frustration = response.answer("frustration")
        self.assertEqual((frustration.choice, frustration.score, frustration.confidence), ("frustrated", 1.05, 0.92))
        self.assertEqual(dict(frustration.probabilities), {"calm": 0.0, "frustrated": 0.95, "angry": 0.05})

    async def test_refusal_answer_raises_a_billed_error_naming_the_question(self) -> None:
        # [Hidden Failure] AC-6/EC-10: a refusal is a typed error carrying the usage OpenAI billed, never a half-answered response.
        answers = [{"type": "refusal", "name": "refund", "refusal": "I cannot decide this."}, fx.openai_choice()]
        runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(answers)))
        with self.assertRaises(ProviderResponseError) as caught:
            await runner.arun(fx.customer_request())
        self.assertEqual(caught.exception.message, "OpenAI refused question 'refund'.")
        self.assertEqual(caught.exception.details["usage"], fx.USAGE)
        self.assertEqual(caught.exception.provider, "openai")

    async def test_missing_extra_duplicate_or_mistyped_answers_raise_with_usage(self) -> None:
        # [Hidden Failure] INV-8/EC-9: every drift from the documented array is a ProviderResponseError with the billed usage.
        drifts = {
            "missing": [fx.openai_predicate("refund", 0.8)],
            "extra": [*THREE_ANSWERS[:2], fx.openai_predicate("extra", 0.1)],
            "duplicate": [fx.openai_predicate("refund", 0.8), fx.openai_predicate("refund", 0.2), fx.openai_choice()],
            "mistyped": [{**fx.openai_choice(name="refund"), "type": "choice"}, fx.openai_choice()],
            "wrong labels": [fx.openai_predicate("refund", 0.8), fx.openai_choice(probabilities=[{"value": "billing", "probability": 0.7}, {"value": "logistics", "probability": 0.2}, {"value": "z", "probability": 0.1}])],
            "bad probability": [fx.openai_predicate("refund", 1.5), fx.openai_choice()],
            "not a list": {"refund": fx.openai_predicate("refund", 0.8)},
        }
        for label, answers in drifts.items():
            with self.subTest(drift=label), self.assertRaises(ProviderResponseError) as caught:
                runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(answers)))  # type: ignore[arg-type]
                await runner.arun(fx.customer_request())
            self.assertEqual(caught.exception.details["usage"], fx.USAGE)
            self.assertEqual(caught.exception.provider, "openai")

    async def test_score_entries_without_labels_fall_back_to_the_value_index(self) -> None:
        # [Edge Case] EC-11/A-8: value indexes the question's levels when label is absent; neither present is a typed error.
        by_value = [{"value": 0, "probability": 0.0}, {"value": 1, "probability": 0.95}, {"value": 2, "probability": 0.05}]
        runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body([fx.openai_score(probabilities=by_value)])))
        answer = (await runner.arun(fx.customer_request(fx.score_question()))).answer("frustration")
        self.assertEqual(dict(answer.probabilities), {"calm": 0.0, "frustrated": 0.95, "angry": 0.05})
        self.assertEqual(answer.choice, "frustrated")
        neither = [{"probability": 0.0}, {"probability": 0.95}, {"probability": 0.05}]
        runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body([fx.openai_score(probabilities=neither)])))
        with self.assertRaises(ProviderResponseError) as caught:
            await runner.arun(fx.customer_request(fx.score_question()))
        self.assertEqual(caught.exception.details["usage"], fx.USAGE)

    async def test_response_model_is_the_request_id_regardless_of_the_echo(self) -> None:
        # [Silent Failure] INV-27: the pricebook key is what the caller sent; an undocumented echo must not replace it.
        for echo in ("decisions-2026-10-01", fx.OMIT_MODEL, None):
            with self.subTest(echo=echo):
                runner, _ = fx.scripted_runner("OPENAI", fx.response(fx.openai_body([fx.openai_predicate("refund", 0.8)], model=echo)))
                response = await runner.arun(fx.customer_request(fx.noul_question()))
                self.assertEqual(response.model, "gpt-6-luna")
                self.assertEqual(response.raw.get("model"), None if echo is fx.OMIT_MODEL else echo)

    async def test_sixty_four_predicate_questions_keep_request_order(self) -> None:
        # [Hidden Assumption] INV-7/INV-8: many questions keep their order on the wire and come back keyed in request order.
        names = [f"q{index:02d}" for index in range(64)]
        questions = tuple(fx.noul_question(name=name, instructions=f"Is {name} true?") for name in names)
        answers = [fx.openai_predicate(name, index / 100) for index, name in enumerate(names)]
        runner, transport = fx.scripted_runner("OPENAI", fx.response(fx.openai_body(list(reversed(answers)))))
        response = await runner.arun(fx.customer_request(*questions))
        self.assertEqual([question["name"] for question in transport.requests[0]["json_body"]["questions"]], names)
        self.assertEqual(sorted(response.answers), names)
        for index, name in enumerate(names):
            self.assertEqual(response.answer(name).noul, index / 100)


if __name__ == "__main__":
    unittest.main()
