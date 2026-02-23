"""Anthropic LLM provider."""

from __future__ import annotations

import json

from pydantic import BaseModel

from .base import BaseLLM


class AnthropicLLM(BaseLLM):
    """Anthropic Claude provider."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        max_retries: int = 2,
    ):
        import anthropic

        kwargs: dict = {"timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        self._client = anthropic.Anthropic(**kwargs)
        self._model = model
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._timeout_exceptions = self._resolve_timeout_exc()

    @staticmethod
    def _resolve_timeout_exc() -> tuple:
        import anthropic
        return (anthropic.APITimeoutError, anthropic.APIConnectionError)

    def chat(self, messages: list[dict]) -> str:
        system = None
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": chat_messages,
        }
        if system:
            kwargs["system"] = system

        def _call():
            return self._client.messages.create(**kwargs).content[0].text

        return self._retry(_call, self._max_retries, self._timeout_exceptions)

    def structured_output(
        self, messages: list[dict], schema: type[BaseModel]
    ) -> BaseModel:
        schema_json = schema.model_json_schema()
        suffix = (
            f"\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema_json, indent=2)}"
        )

        system = None
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = (m["content"] or "") + suffix
            else:
                chat_messages.append(m)
        if system is None:
            system = suffix.strip()

        def _call():
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=chat_messages,
            )
            raw = response.content[0].text

            # Extract JSON from possible markdown fencing
            if "```" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]

            return schema.model_validate_json(raw)

        return self._retry(_call, self._max_retries, self._timeout_exceptions)
