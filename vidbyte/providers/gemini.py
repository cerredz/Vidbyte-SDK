from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from vidbyte.lib.config import EmbeddingModelConfig, TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.registries.structured_output import StructuredOutputRegistry
from vidbyte.lib.runners.types import EmbeddingResponse, TextModelResponse
from vidbyte.lib.tools.formatter import ToolsFormatter

# Gemini refuses a larger batchEmbedContents call with 400 "at most 100 requests can be in one batch".
_GEMINI_EMBEDDING_BATCH_LIMIT = 100


class GeminiProvider:
    provider = ModelProvider.GEMINI

    def __init__(self, *, text_config: TextModelConfig | None = None, embedding_config: EmbeddingModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._embedding_config = embedding_config
        self._parser = response_parser or HttpResponseParser()

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute Gemini generateContent with contents, tools, safety, and cache options.
        config = self._config(config)
        model = quote(config.model, safe="")
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/models/{model}:generateContent", headers=self._create_headers(config), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        usage = parsed.get("usageMetadata") if isinstance(parsed.get("usageMetadata"), dict) else None
        try:
            text = self._extract_text(parsed)
        except ProviderResponseError as exc:
            # A billed 200 with no usable text keeps its usage on the error so the caller can still bill it.
            if usage is not None:
                exc.details["usage"] = dict(usage)
            raise
        return TextModelResponse(provider=self.provider, model=config.model, text=text, raw=parsed, usage=usage)

    def _config(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError("GeminiProvider requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Prefer the x-goog-api-key header so the key is not embedded in URLs.
        return {"x-goog-api-key": config.resolved_api_key(), "content-type": "application/json"}

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build the Gemini request body around its contents array contract.
        payload: dict[str, Any] = {"contents": self._create_contents(config, prompt)}
        # Decide once whether the output schema travels as instructions, so both steps below agree.
        schema_as_text = self._schema_as_text(config)
        self._attach_instructions(payload, config, system, schema_as_text)
        self._attach_generation_config(payload, config, schema_as_text)
        self._attach_tools(payload, config)
        self._attach_safety(payload, config)
        self._attach_cache(payload, config)
        self._attach_extra_body(payload, config, metadata)
        return payload

    def _create_contents(self, config: TextModelConfig, prompt: str) -> list[Mapping[str, Any]]:
        # Gemini supports alternating user/model turns through the contents array.
        history = [self._gemini_turn(message) for message in config.messages]
        history.insert(self._prompt_index(history, config.prompt_index), {"role": "user", "parts": [{"text": prompt}]})
        # A model note followed by a model call is one model step, so they travel as one model turn.
        history = self._merge_model_turns(history)
        # Answers to one parallel function-call turn must travel together in a single user turn.
        return self._merge_function_responses(history)

    def _prompt_index(self, history: list[Mapping[str, Any]], boundary: int | None = None) -> int:
        # @intent prompt-sits-at-the-run-boundary
        # The runtime's run boundary wins as it does in PromptPlacement, unless the history opens with a model turn.
        if boundary is not None and boundary <= len(history) and not (history and history[0].get("role") == "model"):
            return boundary
        # The runtime appends this run's tool exchange to whatever history it was handed, but
        # the prompt that provoked that exchange arrives separately and would otherwise land
        # after it, leaving the functionCall turn with nothing in front of it. Gemini rejects
        # that outright: "function call turn comes immediately after a user turn or after a
        # function response turn". Slot the prompt in as that missing opening turn. A model turn
        # at the very start, text or call, has nothing in front of it either and gets the same
        # treatment. A call right after a user turn (a function response is one too) belongs to
        # an exchange that is already introduced, such as a replayed one or a later round, so
        # scanning goes on past it; with no unintroduced model turn the prompt simply appends.
        # @intent gemini-prompt-opens-a-model-led-history
        # A rejected plain-text draft now opens this run's exchange, and Gemini refuses contents that start with a model turn.
        for index, turn in enumerate(history):
            if not (self._has_part(turn, "functionCall") or (index == 0 and turn.get("role") == "model")):
                continue
            if index and history[index - 1].get("role") == "user":
                continue
            return index
        return len(history)

    def _merge_model_turns(self, history: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        # A context note pinned to the conversation arrives as its own assistant turn, so a
        # functionCall turn can land right behind another model turn. Gemini rejects that: "function
        # call turn comes immediately after a user turn or after a function response turn". Fold
        # back-to-back model turns into one, keeping every part verbatim and in order.
        # @intent gemini-one-model-turn-per-step
        # Gemini expects one model turn per step, and a split step leaves its call without a user turn in front.
        merged: list[Mapping[str, Any]] = []
        for turn in history:
            if merged and turn.get("role") == "model" and merged[-1].get("role") == "model":
                merged[-1] = {**merged[-1], "parts": [*(merged[-1].get("parts") or ()), *(turn.get("parts") or ())]}
                continue
            merged.append(turn)
        return merged

    def _merge_function_responses(self, history: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        # @intent boundary: the runtime formats each tool result as its own user turn, but when
        # the model makes several calls in one turn Gemini demands every answer in the single
        # content that follows it: "the number of function response parts is equal to the number
        # of function call parts of the function call turn". Fold back-to-back response-only
        # user turns into one, keeping call order. User text turns are never merged.
        merged: list[Mapping[str, Any]] = []
        for turn in history:
            if merged and self._is_function_response_turn(turn) and self._is_function_response_turn(merged[-1]):
                merged[-1] = {**merged[-1], "parts": [*merged[-1]["parts"], *turn["parts"]]}
                continue
            merged.append(turn)
        return merged

    @staticmethod
    def _is_function_response_turn(turn: Mapping[str, Any]) -> bool:
        # A user turn made only of functionResponse parts, the shape ToolsFormatter emits.
        parts = turn.get("parts") or ()
        return turn.get("role") == "user" and bool(parts) and all(isinstance(part, Mapping) and "functionResponse" in part for part in parts)

    @staticmethod
    def _has_part(turn: Mapping[str, Any], key: str) -> bool:
        # Reports whether a turn carries a given Gemini part kind.
        parts = turn.get("parts") or ()
        return any(key in part for part in parts if isinstance(part, Mapping))

    @staticmethod
    def _gemini_turn(message: Mapping[str, Any]) -> dict[str, Any]:
        # History reaches providers in the OpenAI {role, content} shape, which Gemini cannot
        # read: it wants {role, parts} and calls the assistant role 'model'. Tool turns are
        # already built in Gemini's shape by ToolsFormatter and pass through untouched.
        turn = dict(message)
        role = turn.get("role")
        if role == "assistant":
            turn["role"] = "model"
        elif role == "system":
            turn["role"] = "user"
        if "parts" not in turn and "content" in turn:
            content = turn.pop("content")
            turn["parts"] = [{"text": content if isinstance(content, str) else str(content)}]
        return turn

    def _schema_as_text(self, config: TextModelConfig) -> bool:
        # @intent gemini-2-schema-cannot-ride-with-function-calls
        # The registry declares which models reject a JSON response type beside function declarations.
        if config.response_format is None or not config.tools:
            return False
        return not StructuredOutputRegistry.native_schema_with_tools(self.provider, config.model)

    def _attach_instructions(self, payload: dict[str, Any], config: TextModelConfig, system: str | None, schema_as_text: bool) -> None:
        # Gemini uses systemInstruction for developer-provided instructions.
        instructions = system or config.system or ""
        # @intent below-native-the-fields-only-reach-the-model-as-text
        # When native schema cannot be sent, its fields reach the model through the instructions instead.
        if schema_as_text and config.response_format is not None:
            instructions = (instructions + StructuredOutputRegistry.describe(self.provider, config.model).schema_instruction(dict(config.response_format))).strip()
        if instructions:
            payload["systemInstruction"] = {"parts": [{"text": instructions}]}

    def _attach_generation_config(self, payload: dict[str, Any], config: TextModelConfig, schema_as_text: bool) -> None:
        # Collect Gemini generation options under generationConfig.
        generation_config: dict[str, Any] = {}
        if config.temperature is not None:
            generation_config["temperature"] = config.temperature
        if config.top_p is not None:
            generation_config["topP"] = config.top_p
        if config.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = config.max_output_tokens
        if config.response_format is not None and not schema_as_text:
            generation_config["responseMimeType"] = "application/json"
            # @intent response-schema-speaks-gemini-openapi-subset
            # responseSchema is Gemini's OpenAPI subset, so $defs/$ref from any nested model or Enum
            # fail the whole request; reuse the reducer tool declarations already go through.
            generation_config["responseSchema"] = ToolsFormatter._gemini_schema(config.response_format)
        if config.thinking_config is not None:
            generation_config["thinkingConfig"] = dict(config.thinking_config)
        if generation_config:
            payload["generationConfig"] = generation_config

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Gemini supports function tools, code execution, and toolConfig.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_config is not None:
            payload["toolConfig"] = dict(config.tool_config)

    def _attach_safety(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Safety settings override Gemini defaults per harm category.
        if config.safety_settings:
            payload["safetySettings"] = [dict(setting) for setting in config.safety_settings]

    def _attach_cache(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # cachedContent lets callers reuse long context already cached with Gemini.
        if config.cached_content:
            payload["cachedContent"] = config.cached_content

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Preserve forward compatibility for new Gemini fields and caller metadata.
        if metadata:
            payload.setdefault("labels", {}).update({str(key): str(value) for key, value in metadata.items()})
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def run_embedding(self, *, texts: list[str], transport: HttpTransport, config: EmbeddingModelConfig | None = None) -> EmbeddingResponse:
        # POST to batchEmbedContents and return one float vector per input text.
        config = self._embedding_config_for(config)
        model = quote(config.model, safe="")
        url = f"{config.resolved_endpoint()}/models/{model}:batchEmbedContents"
        # @intent gemini-embedding-batches-stay-under-the-cap
        # Gemini answers more than 100 requests in one batch with 400 "BatchEmbedContentsRequest.requests: at most
        # 100 requests can be in one batch", so the texts go out in consecutive slices of at most that many.
        embeddings: list[tuple[float, ...]] = []
        bodies: list[Mapping[str, Any]] = []
        for batch in self._embedding_batches(texts):
            # Each slice is one ordinary batch call, built exactly as a single call always was.
            payload = self._create_embedding_payload(config, model, batch)
            response = transport.request(method="POST", url=url, headers=self._create_embedding_headers(config), json_body=payload, timeout_seconds=config.timeout_seconds)
            parsed = self._parser.parse_json_response(response, provider=self.provider.value)
            # Check each slice against its own size, then keep its vectors in input order.
            embeddings.extend(self._extract_batch_embeddings(parsed, expected_count=len(batch)))
            bodies.append(parsed)
        # One slice keeps its body as raw, as before; several are listed in order, since no single body covers them all.
        raw = bodies[0] if len(bodies) == 1 else {"batches": bodies}
        return EmbeddingResponse(provider=self.provider, model=config.model, embeddings=tuple(embeddings), raw=raw)

    @staticmethod
    def _embedding_batches(texts: list[str]) -> list[list[str]]:
        # Consecutive slices of at most the vendor cap; an empty input stays one empty call, as before.
        return [texts[start : start + _GEMINI_EMBEDDING_BATCH_LIMIT] for start in range(len(texts))[::_GEMINI_EMBEDDING_BATCH_LIMIT]] or [texts]

    @staticmethod
    def _create_embedding_payload(config: EmbeddingModelConfig, model: str, texts: list[str]) -> dict[str, Any]:
        # One batchEmbedContents body whose requests carry the model path and task type for each text.
        task_type = config.input_type or "RETRIEVAL_DOCUMENT"
        payload: dict[str, Any] = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}, "taskType": task_type} for t in texts]}
        # @intent embedding-dimensions-reach-every-provider
        # The shared dimensions setting becomes Gemini's per-request outputDimensionality, the way input_type becomes taskType.
        if config.dimensions is not None:
            for request in payload["requests"]:
                request["outputDimensionality"] = config.dimensions
        return payload

    def _embedding_config_for(self, config: EmbeddingModelConfig | None) -> EmbeddingModelConfig:
        # Resolve embedding config from call argument or stored instance config.
        resolved = config or self._embedding_config
        if resolved is None:
            raise ProviderConfigurationError("GeminiProvider requires an EmbeddingModelConfig.", provider=self.provider.value)
        return resolved

    def _create_embedding_headers(self, config: EmbeddingModelConfig) -> dict[str, str]:
        # Gemini uses x-goog-api-key for embedding requests the same as text.
        return {"x-goog-api-key": config.resolved_api_key(), "content-type": "application/json"}

    def _extract_batch_embeddings(self, parsed: Mapping[str, Any], *, expected_count: int) -> tuple[tuple[float, ...], ...]:
        # Extract the values list from each embedding in the ordered batch response.
        items = parsed.get("embeddings")
        if not isinstance(items, list):
            raise ProviderResponseError("Gemini embeddings response missing embeddings list.", provider=self.provider.value, response_excerpt=str(parsed))
        if len(items) != expected_count:
            raise ProviderResponseError(f"Gemini returned {len(items)} embeddings but {expected_count} were requested.", provider=self.provider.value, response_excerpt=str(parsed))
        result: list[tuple[float, ...]] = []
        for item in items:
            values = item.get("values") if isinstance(item, dict) else None
            if not isinstance(values, list):
                raise ProviderResponseError("Gemini embedding item missing values list.", provider=self.provider.value, response_excerpt=str(item))
            result.append(tuple(float(v) for v in values))
        return tuple(result)

    def _extract_text(self, parsed: Mapping[str, Any]) -> str:
        # Normalize text parts from the first Gemini candidate.
        candidates = parsed.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderResponseError("Gemini response did not include candidates.", provider=self.provider.value, response_excerpt=str(parsed))
        first = candidates[0]
        content = first.get("content") if isinstance(first, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise ProviderResponseError("Gemini response did not include text parts.", provider=self.provider.value, response_excerpt=str(parsed))
        # @intent thought-parts-are-not-the-answer
        # With thinkingConfig.includeThoughts, Gemini sends thought summaries as parts marked "thought": true
        # ahead of the answer; the answer is the other text parts, never the thinking.
        chunks = [part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str) and part.get("thought") is not True]
        if not chunks:
            if any(isinstance(part, dict) and ("functionCall" in part or "function_call" in part) for part in parts):
                return ""
            raise ProviderResponseError("Gemini response did not include text.", provider=self.provider.value, response_excerpt=str(parsed))
        return "\n".join(chunks)


__all__ = [
    "GeminiProvider",
]
