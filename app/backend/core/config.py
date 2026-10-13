"""
Application configuration — reads from environment or .env file.
All paths are local. No remote URLs.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root is three levels up from this file:
# backend/core/config.py → backend → app → project_root
_BACKEND_DIR = Path(__file__).parent.parent
_APP_DIR = _BACKEND_DIR.parent
PROJECT_ROOT = _APP_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="DOCEXTRACT_",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    BACKEND_PORT: int = 37240
    DEV_MODE: bool = False

    # Directories (all local)
    DATA_DIR: Path = PROJECT_ROOT / "data"
    UPLOADS_DIR: Path = PROJECT_ROOT / "data" / "uploads"
    EXPORTS_DIR: Path = PROJECT_ROOT / "data" / "exports"
    MODELS_DIR: Path = PROJECT_ROOT / "models"
    DB_PATH: Path = PROJECT_ROOT / "data" / "docextract.db"
    LOGS_DIR: Path = PROJECT_ROOT / "data" / "logs"

    # OCR
    TESSERACT_CMD: str = "tesseract" if os.name != "nt" else r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    TESSERACT_LANG: str = "eng"
    OCR_DPI: int = 180                     # Optimized for speed and precision (sub-2s target)
    OCR_CONFIDENCE_THRESHOLD: float = 60.0

    # Processing & Performance Optimization
    FAST_PROCESSING: bool = True           # Sub-2-second deterministic extraction SLA
    MAX_VIDEO_SAMPLE_FRAMES: int = 3       # Sample 3 keyframes for fast video OCR

    # LLM
    LLM_PROVIDER: str = "llama_cpp"        # "llama_cpp" or "ollama"
    LLM_MODEL_PATH: str = ""               # Set by model manager
    LLM_N_GPU_LAYERS: int = -1            # -1 = auto-detect
    LLM_N_CTX: int = 2048
    LLM_N_THREADS: int = 8
    LLM_TEMPERATURE: float = 0.0          # Zero temp for extraction (deterministic)
    LLM_MAX_TOKENS: int = 256
    LLM_VERBOSE: bool = False

    # Ollama (optional)
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"  # Localhost only if Ollama used
    OLLAMA_MODEL: str = ""

    # Processing limits
    MAX_FILE_SIZE_MB: int = 100
    MAX_PAGES_PER_DOC: int = 50
    NATIVE_TEXT_MIN_CHARS_PER_PAGE: int = 50  # Below this → use OCR

    # Allowed MIME types (magic-byte validated)
    ALLOWED_EXTENSIONS: list[str] = [
        "pdf", "docx", "doc", "jpg", "jpeg", "png", "webp",
        "wav", "mp3", "mp4", "mov", "avi", "mkv", "webm", "txt"
    ]

    def model_post_init(self, __context) -> None:
        """Ensure all required local directories exist."""
        for directory in [
            self.DATA_DIR,
            self.UPLOADS_DIR,
            self.EXPORTS_DIR,
            self.MODELS_DIR / "small",
            self.MODELS_DIR / "medium",
            self.MODELS_DIR / "large",
            self.LOGS_DIR,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
