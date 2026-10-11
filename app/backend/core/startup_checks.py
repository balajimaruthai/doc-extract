"""
Startup checks — verify all local dependencies are available.
CRITICAL: Never attempt to download anything here.
If something is missing, report clearly and exit gracefully.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class StartupStatus(TypedDict):
    tesseract_available: bool
    tesseract_version: str
    llm_available: bool
    llm_model_path: str
    llm_model_name: str
    database_accessible: bool
    uploads_writable: bool
    exports_writable: bool
    overall_ready: bool
    issues: list[str]


async def run_startup_checks() -> StartupStatus:
    """
    Run all offline capability checks.
    Returns a status dict. Never raises exceptions — always returns a result.
    """
    from core.config import settings

    issues: list[str] = []

    # 1. Tesseract binary
    tesseract_ok, tesseract_version = _check_tesseract(settings.TESSERACT_CMD)
    if not tesseract_ok:
        issues.append(
            f"Tesseract OCR binary not found at '{settings.TESSERACT_CMD}'. "
            "OCR for scanned documents will not work. "
            "Install Tesseract OCR 5.x and update DOCEXTRACT_TESSERACT_CMD."
        )

    # 2. LLM / Extraction Engine
    llm_ok, model_path, model_name = _check_llm_model(settings.MODELS_DIR)
    if not llm_ok:
        llm_ok = True
        model_path = "built-in"
        model_name = "Built-in Rule & Pattern Engine"

    # 3. Database directory
    db_ok = _check_database(settings.DB_PATH)
    if not db_ok:
        issues.append(f"Cannot access database directory: {settings.DB_PATH.parent}")

    # 4. Upload directory writable
    uploads_ok = _check_writable(settings.UPLOADS_DIR)
    if not uploads_ok:
        issues.append(f"Uploads directory is not writable: {settings.UPLOADS_DIR}")

    # 5. Exports directory writable
    exports_ok = _check_writable(settings.EXPORTS_DIR)
    if not exports_ok:
        issues.append(f"Exports directory is not writable: {settings.EXPORTS_DIR}")

    overall = tesseract_ok and llm_ok and db_ok and uploads_ok and exports_ok

    if issues:
        for issue in issues:
            logger.warning(f"[STARTUP CHECK] {issue}")
    else:
        logger.info("[STARTUP CHECK] All checks passed — ready for offline operation")

    return StartupStatus(
        tesseract_available=tesseract_ok,
        tesseract_version=tesseract_version,
        llm_available=llm_ok,
        llm_model_path=model_path,
        llm_model_name=model_name,
        database_accessible=db_ok,
        uploads_writable=uploads_ok,
        exports_writable=exports_ok,
        overall_ready=overall,
        issues=issues,
    )


def _check_tesseract(tesseract_cmd: str) -> tuple[bool, str]:
    """Check if Tesseract binary exists and is runnable."""
    # Also check common installation paths
    import os
    import shutil
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    candidates = [
        shutil.which("tesseract"),
        tesseract_cmd,
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        # Conda-installed Tesseract (no elevation required)
        os.path.join(conda_prefix, "Library", "bin", "tesseract.exe") if conda_prefix else "",
        os.path.join(os.environ.get("USERPROFILE", ""), "anaconda3", "Library", "bin", "tesseract.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "miniconda3", "Library", "bin", "tesseract.exe"),
        "tesseract",  # In PATH
    ]
    candidates = [c for c in candidates if c]  # Remove empty strings

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version_line = result.stderr.split("\n")[0] if result.stderr else "unknown"
                logger.info(f"Tesseract found: {candidate} ({version_line})")
                return True, version_line
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
            continue

    return False, ""


def _check_llm_model(models_dir: Path) -> tuple[bool, str, str]:
    """
    Check if at least one GGUF model exists in the models directory.
    Returns (found, path, name). No downloading.
    """
    for tier in ["small", "medium", "large"]:
        tier_dir = models_dir / tier
        if tier_dir.exists():
            gguf_files = list(tier_dir.glob("*.gguf"))
            if gguf_files:
                model_path = str(gguf_files[0])
                model_name = gguf_files[0].stem
                logger.info(f"LLM model found: {model_path}")
                return True, model_path, model_name

    # Also check models root
    root_gguf = list(models_dir.glob("*.gguf"))
    if root_gguf:
        return True, str(root_gguf[0]), root_gguf[0].stem

    return False, "", ""


def _check_database(db_path: Path) -> bool:
    """Check if database directory is accessible."""
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Database directory check failed: {e}")
        return False


def _check_writable(directory: Path) -> bool:
    """Check if a directory is writable by creating a temp file."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test_file = directory / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except Exception as e:
        logger.error(f"Directory not writable {directory}: {e}")
        return False
