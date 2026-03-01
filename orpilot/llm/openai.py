"""OpenAI LLM provider."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from .base import BaseLLM

# Matches <think>...</think> blocks emitted by reasoning models (e.g. deepseek-reasoner)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Model name prefixes that are reasoning models
_REASONING_MODEL_PREFIXES = ("deepseek-r", "o1", "o3")

# Minimum max_tokens for reasoning models (thinking tokens compete with output tokens)
_REASONING_MIN_TOKENS = 16384


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning model output."""
    return _THINK_RE.sub("", text).strip()


def _is_reasoning_model(model: str) -> bool:
    model_lower = model.lower()
    return any(model_lower.startswith(p) for p in _REASONING_MODEL_PREFIXES)


class OpenAILLM(BaseLLM):
    """OpenAI chat completion provider."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        max_retries: int = 2,
        temperature: float = 0.0,
    ):
        import openai

        kwargs: dict = {"timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = model
        # Reasoning models need more tokens since thinking competes with output tokens
        if _is_reasoning_model(model):
            self._max_tokens = max(max_tokens, _REASONING_MIN_TOKENS)
        else:
            self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._is_reasoning = _is_reasoning_model(model)
        # Reasoning models don't support temperature — they use fixed sampling.
        self._temperature = None if self._is_reasoning else temperature
        # Newer OpenAI models require max_completion_tokens instead of max_tokens.
        # Third-party compatible APIs (e.g. DeepSeek) always set a base_url and
        # still expect max_tokens, so only switch when using the real OpenAI endpoint.
        self._max_tokens_param = "max_tokens" if base_url else "max_completion_tokens"
        self._timeout_exceptions = self._resolve_timeout_exc()

    @staticmethod
    def _resolve_timeout_exc() -> tuple:
        import openai
        return (openai.APITimeoutError, openai.APIConnectionError)

    def chat(self, messages: list[dict]) -> str:
        messages = self._sanitize_messages(messages)

        def _call():
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                self._max_tokens_param: self._max_tokens,
            }
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return _strip_thinking(content) if self._is_reasoning else content

        return self._retry(_call, self._max_retries, self._timeout_exceptions)

    def structured_output(
        self, messages: list[dict], schema: type[BaseModel]
    ) -> BaseModel:
        schema_json = schema.model_json_schema()
        system_suffix = (
            f"\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}"
        )

        augmented = list(messages)
        if augmented and augmented[0]["role"] == "system":
            augmented[0] = {
                **augmented[0],
                "content": augmented[0]["content"] + system_suffix,
            }
        else:
            augmented.insert(0, {"role": "system", "content": system_suffix.strip()})

        def _call():
            kwargs: dict = {
                "model": self._model,
                "messages": augmented,
                self._max_tokens_param: self._max_tokens,
            }
            # response_format=json_object is not supported by reasoning model endpoints
            if not self._is_reasoning:
                kwargs["response_format"] = {"type": "json_object"}
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            response = self._client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content or "{}"
            if self._is_reasoning:
                raw = _strip_thinking(raw)
            return schema.model_validate_json(self._strip_json_fences(raw))

        return self._retry(_call, self._max_retries, self._timeout_exceptions)
