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
