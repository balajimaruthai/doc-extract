"""
Tesseract OCR wrapper — local OCR, no cloud dependency.
Returns structured results with per-word confidence scores.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class OCRWord:
    text: str
    confidence: float      # 0–100 from Tesseract
    left: int
    top: int
    width: int
    height: int
    page_num: int


@dataclass
class OCRResult:
    page_number: int
    full_text: str
    words: list[OCRWord]
    mean_confidence: float
    low_confidence_word_ratio: float   # Fraction of words below threshold
    tesseract_available: bool
    error: Optional[str] = None


_TESSERACT_CONFIGURED = False
_TESSERACT_AVAILABLE = False


def _configure_tesseract() -> bool:
    """Configure pytesseract path. Called once."""
    global _TESSERACT_CONFIGURED, _TESSERACT_AVAILABLE

    if _TESSERACT_CONFIGURED:
        return _TESSERACT_AVAILABLE

    _TESSERACT_CONFIGURED = True

    try:
        import os
        import pytesseract
        from core.config import settings

        conda_prefix = os.environ.get("CONDA_PREFIX", "")
        import shutil
        tess_which = shutil.which("tesseract")
        candidates = [
            tess_which,
            settings.TESSERACT_CMD,
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            # Conda-installed Tesseract (no elevation needed)
            os.path.join(conda_prefix, "Library", "bin", "tesseract.exe") if conda_prefix else "",
            os.path.join(os.environ.get("USERPROFILE", ""), "anaconda3", "Library", "bin", "tesseract.exe"),
            os.path.join(os.environ.get("USERPROFILE", ""), "miniconda3", "Library", "bin", "tesseract.exe"),
        ]
        candidates = [c for c in candidates if c]  # Remove empty strings

        for candidate in candidates:
            if Path(candidate).exists():
                pytesseract.pytesseract.tesseract_cmd = candidate
                # Test it
                try:
                    version = pytesseract.get_tesseract_version()
                    logger.info(f"Tesseract configured: {candidate} v{version}")
                    _TESSERACT_AVAILABLE = True
                    return True
                except Exception:
                    continue

        # Try from PATH
        import subprocess
        result = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            _TESSERACT_AVAILABLE = True
            logger.info("Tesseract found in PATH")
            return True

        logger.warning("Tesseract not found — OCR will not be available")
        return False

    except Exception as e:
        logger.error(f"Tesseract configuration failed: {e}")
        return False


def run_ocr(
    image_array: np.ndarray,
    page_number: int = 1,
    lang: str = "eng",
    confidence_threshold: float = 60.0,
) -> OCRResult:
    """
    Run Tesseract OCR on a preprocessed image array.

    Args:
        image_array: Preprocessed grayscale numpy array
        page_number: Page number for tracking
        lang: Tesseract language code(s) e.g. "eng" or "eng+hin"
        confidence_threshold: Words below this confidence are flagged

    Returns:
        OCRResult with text, word-level confidence, and quality metrics
    """
    if not _configure_tesseract():
        return OCRResult(
            page_number=page_number,
            full_text="",
            words=[],
            mean_confidence=0.0,
            low_confidence_word_ratio=1.0,
            tesseract_available=False,
            error="Tesseract OCR is not available. Install Tesseract OCR 5.x.",
        )

    try:
        import pytesseract

        # Convert numpy array to PIL Image
        pil_image = Image.fromarray(image_array)

        # Get detailed data including confidence
        data = pytesseract.image_to_data(
            pil_image,
            lang=lang,
            output_type=pytesseract.Output.DICT,
            config="--psm 3 --oem 3",   # PSM 3 = auto, OEM 3 = LSTM
        )

        words: list[OCRWord] = []
        word_confidences: list[float] = []

        n_boxes = len(data["text"])
        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])

            # Skip empty words and invalid confidence (-1 = non-word)
            if not text or conf < 0:
                continue

            words.append(OCRWord(
                text=text,
                confidence=conf,
                left=data["left"][i],
                top=data["top"][i],
                width=data["width"][i],
                height=data["height"][i],
                page_num=page_number,
            ))
            word_confidences.append(conf)

        if not words:
            return OCRResult(
                page_number=page_number,
                full_text="",
                words=[],
                mean_confidence=0.0,
                low_confidence_word_ratio=1.0,
                tesseract_available=True,
                error="No text detected on this page",
            )

        # Build full text from words (preserve line structure)
        full_text = pytesseract.image_to_string(
            pil_image,
            lang=lang,
            config="--psm 3 --oem 3",
        )

        mean_conf = float(np.mean(word_confidences))
        low_conf_count = sum(1 for c in word_confidences if c < confidence_threshold)
        low_conf_ratio = low_conf_count / len(word_confidences) if word_confidences else 1.0

        logger.info(
            f"OCR page {page_number}: {len(words)} words | "
            f"mean_conf={mean_conf:.1f}% | "
            f"low_conf_ratio={low_conf_ratio:.2f}"
        )

        return OCRResult(
            page_number=page_number,
            full_text=full_text.strip(),
            words=words,
            mean_confidence=mean_conf,
            low_confidence_word_ratio=low_conf_ratio,
            tesseract_available=True,
        )

    except Exception as e:
        logger.error(f"OCR failed on page {page_number}: {e}", exc_info=True)
        return OCRResult(
            page_number=page_number,
            full_text="",
            words=[],
            mean_confidence=0.0,
            low_confidence_word_ratio=1.0,
            tesseract_available=True,
            error=f"OCR processing error: {e}",
        )


def run_ocr_on_image_file(
    image_path: Path,
    page_number: int = 1,
    lang: str = "eng",
) -> OCRResult:
    """
    Run OCR directly on an image file (JPG, PNG).
    Applies preprocessing automatically.
    """
    from ocr.preprocessor import preprocess_for_ocr

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        return OCRResult(
            page_number=page_number,
            full_text="",
            words=[],
            mean_confidence=0.0,
            low_confidence_word_ratio=1.0,
            tesseract_available=True,
            error=f"Cannot read image file: {e}",
        )

    preprocessed = preprocess_for_ocr(image_bytes)
    return run_ocr(preprocessed.image_array, page_number=page_number, lang=lang)
