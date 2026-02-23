"""OpenAI LLM provider."""

from __future__ import annotations

import json

from pydantic import BaseModel

from .base import BaseLLM


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
    ):
        import openai

        kwargs: dict = {"timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = model
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._timeout_exceptions = self._resolve_timeout_exc()

    @staticmethod
    def _resolve_timeout_exc() -> tuple:
        import openai
        return (openai.APITimeoutError, openai.APIConnectionError)

    def chat(self, messages: list[dict]) -> str:
        def _call():
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
            )
            return response.choices[0].message.content or ""

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
            response = self._client.chat.completions.create(
                model=self._model,
                messages=augmented,
                max_tokens=self._max_tokens,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return schema.model_validate_json(raw)

        return self._retry(_call, self._max_retries, self._timeout_exceptions)
