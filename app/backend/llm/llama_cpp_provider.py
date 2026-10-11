"""
llama-cpp-python provider — primary local LLM backend.
Uses GGUF models. CUDA-accelerated on NVIDIA GPU.
Runs entirely offline. No network calls.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from llm.provider import LocalLLMProvider, LLMProviderError, ModelNotFoundError

logger = logging.getLogger(__name__)


class LlamaCppProvider(LocalLLMProvider):
    """
    Local LLM using llama-cpp-python with GGUF models.
    Supports CPU-only and CUDA-accelerated inference.
    """

    def __init__(
        self,
        model_path: str | Path,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        n_threads: int = 8,
        verbose: bool = False,
    ):
        """
        Args:
            model_path: Path to the GGUF model file (must exist locally)
            n_gpu_layers: Number of layers to offload to GPU.
                         -1 = auto-detect, 0 = CPU only
            n_ctx: Context window size (tokens)
            n_threads: CPU threads to use
            verbose: Enable llama.cpp verbose output
        """
        self._model_path = Path(model_path)
        self._n_gpu_layers = n_gpu_layers
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._verbose = verbose
        self._llm = None
        self._model_name = self._model_path.stem

    def _load_model(self) -> None:
        """Load the GGUF model into memory. Called lazily on first use."""
        if self._llm is not None:
            return

        if not self._model_path.exists():
            raise ModelNotFoundError(
                f"Model file not found: {self._model_path}\n"
                "Please install a GGUF model before running the application.\n"
                "See docs/MODEL_SETUP.md for instructions."
            )

        logger.info(f"Loading model: {self._model_path.name}")
        logger.info(f"  n_gpu_layers={self._n_gpu_layers}, n_ctx={self._n_ctx}, n_threads={self._n_threads}")

        try:
            from llama_cpp import Llama

            # Determine GPU layers
            gpu_layers = self._n_gpu_layers
            if gpu_layers == -1:
                gpu_layers = self._auto_detect_gpu_layers()

            self._llm = Llama(
                model_path=str(self._model_path),
                n_gpu_layers=gpu_layers,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                verbose=self._verbose,
                use_mmap=True,      # Memory-mapped for efficiency
                use_mlock=False,    # Don't lock memory (important for 8 GB system)
            )
            logger.info(
                f"Model loaded: {self._model_name} "
                f"(GPU layers: {gpu_layers})"
            )

        except Exception as e:
            self._llm = None
            raise LLMProviderError(f"Failed to load model: {e}") from e

    def _auto_detect_gpu_layers(self) -> int:
        """Determine GPU layers based on available hardware."""
        try:
            from hardware.detector import get_hardware_info
            hw = get_hardware_info()
            if hw.gpu and hw.gpu.cuda_available:
                layers = hw.gpu.recommended_n_gpu_layers
                logger.info(f"Auto-detected GPU layers: {layers}")
                return layers
        except Exception as e:
            logger.debug(f"GPU detection failed, defaulting to CPU: {e}")
        return 0

    def is_available(self) -> bool:
        try:
            return self._model_path.exists()
        except Exception:
            return False

    def get_model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Run inference and return raw string output."""
        self._load_model()
        try:
            response = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or [],
                echo=False,
            )
            return response["choices"][0]["text"].strip()
        except Exception as e:
            raise LLMProviderError(f"Inference failed: {e}") from e

    def generate_json(
        self,
        prompt: str,
        json_schema: dict[str, Any] = None,
        max_tokens: int = 256,
    ) -> dict[str, Any]:
        """
        Generate structured JSON output with support for assistant turn prefilling
        and automatic syntax repair for incomplete model outputs.
        """
        self._load_model()
        return self._generate_json_fallback(prompt, max_tokens)

    def _generate_json_fallback(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        """
        Generate text and extract valid JSON with auto-repair.
        """
        raw = self.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            stop=["<|end|>", "<|user|>", "<|system|>"],
        )

        # Detect pre-fill from prompt
        p_strip = prompt.rstrip()
        if p_strip.endswith('{"title":'):
            clean_raw = '{"title":' + raw.strip()
        elif p_strip.endswith('{'):
            clean_raw = '{' + raw.strip()
        else:
            clean_raw = raw.strip()

        # Remove markdown code fences if present
        clean_raw = re.sub(r"^```(?:json)?\s*", "", clean_raw, flags=re.MULTILINE)
        clean_raw = re.sub(r"\s*```$", "", clean_raw, flags=re.MULTILINE).strip()

        # Auto repair and parse JSON
        repaired = self._repair_and_parse_json(clean_raw)
        if repaired:
            return repaired

        logger.warning(f"Could not parse valid JSON from LLM output. Raw: {raw[:200]}")
        return {}

    def _repair_and_parse_json(self, s: str) -> dict[str, Any]:
        """Robustly parse JSON, repairing missing quotes, commas, brackets, or braces."""
        s = s.strip()
        if not s:
            return {}

        # 1. Direct parse
        try:
            return json.loads(s)
        except Exception:
            pass

        # 2. Extract from outermost '{'
        start = s.find('{')
        if start != -1:
            s = s[start:]

        # Clean trailing commas before closing brackets
        s = re.sub(r',\s*([\]}])', r'\1', s)

        # Try parsing
        try:
            return json.loads(s)
        except Exception:
            pass

        # 3. Auto-balance quotes, brackets, and braces
        candidate = s
        if candidate.count('"') % 2 != 0:
            candidate += '"'
        open_sq = candidate.count('[') - candidate.count(']')
        if open_sq > 0:
            candidate += ']' * open_sq
        open_cu = candidate.count('{') - candidate.count('}')
        if open_cu > 0:
            candidate += '}' * open_cu

        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 4. Backtrack to previous comma and close
        for end_idx in [s.rfind(','), s.rfind('}'), s.rfind(']')]:
            if end_idx != -1:
                sub = s[:end_idx].rstrip()
                if sub.count('"') % 2 != 0:
                    sub += '"'
                op_sq = sub.count('[') - sub.count(']')
                if op_sq > 0: sub += ']' * op_sq
                op_cu = sub.count('{') - sub.count('}')
                if op_cu > 0: sub += '}' * op_cu
                try:
                    return json.loads(sub)
                except Exception:
                    continue

        return {}

    def unload(self) -> None:
        """Unload model and free memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            logger.info(f"Model unloaded: {self._model_name}")
