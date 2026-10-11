"""
Structured logging configuration.
IMPORTANT: Never log document content, extracted text, or PII.
"""
import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure structured local logging."""
    from core.config import settings

    log_dir = log_dir or settings.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Rotating file handler — keeps last 5 × 10 MB logs
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "docextract.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
