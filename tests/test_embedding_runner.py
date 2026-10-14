from __future__ import annotations

import json
import unittest
from typing import Mapping

from vidbyte.lib.config import EmbeddingModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import EmbeddingModelRunner


class FakeTransport:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        return HttpResponse(status_code=200, body=json.dumps(self.responses.pop(0)), headers={})


def _make_openai_embedding_response(vectors: list[list[float]]) -> dict:
    return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)], "usage": {"total_tokens": 10}}


def _make_gemini_embedding_response(vectors: list[list[float]]) -> dict:
    return {"embeddings": [{"values": v} for v in vectors]}


class EmbeddingRunnerTests(unittest.TestCase):
    # --- OpenAI happy path ---

    def test_openai_single_text_embedding(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1, 0.2, 0.3]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        response = runner.run("hello")

        self.assertEqual(len(response.embeddings), 1)
        self.assertAlmostEqual(response.embeddings[0][0], 0.1)
        self.assertAlmostEqual(response.embeddings[0][1], 0.2)
        self.assertAlmostEqual(response.embeddings[0][2], 0.3)

    def test_openai_multi_text_embeddings(self) -> None:
        vectors = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
        transport = FakeTransport([_make_openai_embedding_response(vectors)])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        response = runner.run(["text1", "text2", "text3"])

        self.assertEqual(len(response.embeddings), 3)
        self.assertAlmostEqual(response.embeddings[1][1], 1.0)

    def test_openai_embeddings_sorted_by_index(self) -> None:
        # Response has items out of order; runner must sort by index
        out_of_order = {"data": [{"index": 2, "embedding": [3.0]}, {"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [2.0]}]}
        transport = FakeTransport([out_of_order])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        response = runner.run(["a", "b", "c"])

        self.assertAlmostEqual(response.embeddings[0][0], 1.0)
        self.assertAlmostEqual(response.embeddings[1][0], 2.0)
        self.assertAlmostEqual(response.embeddings[2][0], 3.0)

    def test_openai_malformed_embedding_item_raises_instead_of_dropping(self) -> None:
        # A null or base64-string embedding must fail loudly, never shorten the result.
        malformed_cases = {
            "null": {"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": None}, {"index": 2, "embedding": [3.0]}]},
            "base64": {"data": [{"index": 0, "embedding": "AACAPw=="}, {"index": 1, "embedding": "AAAAQA=="}, {"index": 2, "embedding": "AABAQA=="}]},
        }
        for label, body in malformed_cases.items():
            with self.subTest(case=label):
                runner = EmbeddingModelRunner(
                    EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
                    transport=FakeTransport([body]),
                )

                with self.assertRaisesRegex(ProviderResponseError, "missing embedding list"):
                    runner.run(["a", "b", "c"])

    def test_openai_embedding_sends_correct_url(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        runner.run("test")

        self.assertEqual(transport.requests[0]["url"], "https://api.openai.com/v1/embeddings")

    def test_openai_embedding_sends_input_texts(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1], [0.2]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        runner.run(["foo", "bar"])

        self.assertEqual(transport.requests[0]["json_body"]["input"], ["foo", "bar"])

    def test_openai_embedding_includes_dimensions_when_set(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key", dimensions=512),
            transport=transport,
        )

        runner.run("test")

        self.assertEqual(transport.requests[0]["json_body"]["dimensions"], 512)

    # --- Gemini happy path ---

    def test_gemini_batch_embedding(self) -> None:
        vectors = [[0.1, 0.9], [0.8, 0.2]]
        transport = FakeTransport([_make_gemini_embedding_response(vectors)])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="key"),
            transport=transport,
        )

        response = runner.run(["query", "document"])

        self.assertEqual(len(response.embeddings), 2)
        self.assertAlmostEqual(response.embeddings[0][0], 0.1)
        self.assertAlmostEqual(response.embeddings[1][0], 0.8)

    def test_gemini_embedding_splits_more_than_100_texts_into_capped_batches(self) -> None:
        # Gemini rejects a batchEmbedContents call with more than 100 requests, so 250 texts must go as 100, 100 and 50.
        vectors = [[float(index), 0.5] for index in range(250)]
        transport = FakeTransport([_make_gemini_embedding_response(vectors[:100]), _make_gemini_embedding_response(vectors[100:200]), _make_gemini_embedding_response(vectors[200:])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="key"),
            transport=transport,
        )

        response = runner.run([f"text {index}" for index in range(250)])

        self.assertEqual([len(sent["json_body"]["requests"]) for sent in transport.requests], [100, 100, 50])
        self.assertEqual(response.embeddings, tuple(tuple(vector) for vector in vectors))
        sent_texts = [entry["content"]["parts"][0]["text"] for sent in transport.requests for entry in sent["json_body"]["requests"]]
        self.assertEqual(sent_texts, [f"text {index}" for index in range(250)])
        for sent in transport.requests:
            self.assertTrue(all(entry["taskType"] == "RETRIEVAL_DOCUMENT" and entry["model"] == "models/text-embedding-004" for entry in sent["json_body"]["requests"]))

    def test_gemini_embedding_dimensions_reach_every_capped_batch(self) -> None:
        transport = FakeTransport([_make_gemini_embedding_response([[0.1]] * 100), _make_gemini_embedding_response([[0.2]] * 5)])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="gemini-embedding-001", api_key="key", dimensions=768),
            transport=transport,
        )

        runner.run([f"text {index}" for index in range(105)])

        self.assertEqual([len(sent["json_body"]["requests"]) for sent in transport.requests], [100, 5])
        for sent in transport.requests:
            self.assertTrue(all(entry.get("outputDimensionality") == 768 for entry in sent["json_body"]["requests"]))

    def test_gemini_embedding_sends_to_batch_endpoint(self) -> None:
        transport = FakeTransport([_make_gemini_embedding_response([[0.5]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="key"),
            transport=transport,
        )

        runner.run("hello")

        self.assertIn("batchEmbedContents", transport.requests[0]["url"])

    def test_gemini_embedding_uses_x_goog_api_key_header(self) -> None:
        transport = FakeTransport([_make_gemini_embedding_response([[0.5]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="goog_key"),
            transport=transport,
        )

        runner.run("hello")

        self.assertEqual(transport.requests[0]["headers"].get("x-goog-api-key"), "goog_key")

    def test_gemini_embedding_includes_output_dimensionality_when_set(self) -> None:
        transport = FakeTransport([_make_gemini_embedding_response([[0.1], [0.2]]), _make_gemini_embedding_response([[0.3], [0.4]])])
        sized = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="gemini-embedding-001", api_key="key", dimensions=768),
            transport=transport,
        )
        unsized = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="gemini-embedding-001", api_key="key"),
            transport=transport,
        )

        sized.run(["query", "document"])
        unsized.run(["query", "document"])

        sized_requests = transport.requests[0]["json_body"]["requests"]
        unsized_requests = transport.requests[1]["json_body"]["requests"]
        self.assertEqual(len(sized_requests), 2)
        self.assertTrue(all(entry.get("outputDimensionality") == 768 for entry in sized_requests))
        self.assertEqual(len(unsized_requests), 2)
        self.assertTrue(all("outputDimensionality" not in entry for entry in unsized_requests))

    # --- Edge cases ---

    def test_empty_list_raises_configuration_error(self) -> None:
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=FakeTransport([]),
        )

        with self.assertRaises(ConfigurationError):
            runner.run([])

    def test_string_input_is_normalized_to_single_item_list(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1, 0.2]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        response = runner.run("single string")

        self.assertEqual(len(response.embeddings), 1)
        self.assertEqual(transport.requests[0]["json_body"]["input"], ["single string"])

    def test_missing_provider_and_model_raises_configuration_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            EmbeddingModelRunner(transport=FakeTransport([]))

    def test_model_name_returns_configured_model(self) -> None:
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-large", api_key="key"),
            transport=FakeTransport([]),
        )

        self.assertEqual(runner.model_name(), "text-embedding-3-large")

    def test_kwargs_construction_without_explicit_config(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1]])])
        runner = EmbeddingModelRunner(
            provider=ModelProvider.OPENAI,
            model="text-embedding-3-small",
            api_key="key",
            transport=transport,
        )

        response = runner.run("hello")

        self.assertEqual(len(response.embeddings), 1)

    def test_usage_is_forwarded_from_openai_response(self) -> None:
        transport = FakeTransport([_make_openai_embedding_response([[0.1]])])
        runner = EmbeddingModelRunner(
            EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"),
            transport=transport,
        )

        response = runner.run("hello")

        self.assertIsNotNone(response.usage)
        self.assertEqual(response.usage["total_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
