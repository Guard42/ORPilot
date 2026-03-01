"""Abstract base class for LLM providers."""

import time
from abc import ABC, abstractmethod
from typing import Callable, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseLLM(ABC):
    """Unified interface for LLM providers."""

    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """Send messages and return the assistant's text reply."""
        ...

    @abstractmethod
    def structured_output(
        self, messages: list[dict], schema: type[BaseModel]
    ) -> BaseModel:
        """Send messages and parse the response into a Pydantic model."""
        ...

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        """Strip markdown code fences from a JSON response.

        Some models wrap their JSON in ```json ... ``` even when asked not to.
        Extracts the outermost ``{`` … ``}`` block so Pydantic can parse it.
        """
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return text[start:end]
        return text.strip()

    @staticmethod
    def _sanitize_messages(messages: list[dict]) -> list[dict]:
        """Merge consecutive same-role messages to satisfy API alternation requirements.

        Some APIs (OpenAI, DeepSeek) reject a request if two consecutive messages
        share the same role (most commonly two ``assistant`` messages produced when
        one workflow node ends and the next begins without an intervening user turn).
        Merging them preserves all context while keeping the conversation valid.
        """
        if not messages:
            return messages
        result: list[dict] = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == result[-1]["role"] and msg["role"] != "system":
                # Merge by joining content
                result[-1] = {
                    **result[-1],
                    "content": result[-1]["content"] + "\n\n" + msg["content"],
                }
            else:
                result.append(msg)
        return result

    def _retry(self, fn: Callable[[], T], max_retries: int, timeout_exceptions: tuple) -> T:
        """Call *fn*, retrying up to *max_retries* times on timeout errors.

        Uses exponential backoff (5 s, 10 s, 20 s, …) between attempts.
        All other exceptions are re-raised immediately.
        """
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except timeout_exceptions as exc:
                if attempt == max_retries:
                    raise
                wait = 5 * (2 ** attempt)
                print(f"[ORPilot] API timeout (attempt {attempt + 1}/{max_retries + 1}), "
                      f"retrying in {wait}s…")
                time.sleep(wait)
        raise RuntimeError("unreachable")
