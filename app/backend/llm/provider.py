"""
LLM Provider abstraction layer.
Allows switching between llama.cpp (primary) and Ollama (optional)
without changing any extraction code.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when LLM inference fails."""
    pass


class ModelNotFoundError(LLMProviderError):
    """Raised when the required model file is not present."""
    pass


class LocalLLMProvider(ABC):
    """
    Abstract base class for local LLM providers.
    All implementations must run entirely offline.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider and model are ready."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the loaded model name."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Generate text from a prompt. Returns raw string output.
        Runs entirely offline.
        """
        ...

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        json_schema: dict[str, Any],
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """
        Generate structured JSON output constrained to a schema.
        Returns parsed dict. Raises LLMProviderError on failure.
        """
        ...

    @abstractmethod
    def unload(self) -> None:
        """Unload the model and free memory."""
        ...
