"""
OCR image preprocessor using OpenCV and Pillow.
Applies targeted transformations to improve Tesseract accuracy.
Does NOT over-process high-quality images.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

TARGET_DPI = 180
TARGET_SHORT_EDGE_PX = 900    # Minimum short-edge pixels for good OCR
MAX_LONG_EDGE_PX = 3400       # Cap oversized images while preserving 300 DPI text details


@dataclass
class PreprocessResult:
    image_array: np.ndarray    # OpenCV BGR or grayscale array
    was_resized: bool
    was_denoised: bool
    was_deskewed: bool
    was_thresholded: bool
    skew_angle: float


def preprocess_for_ocr(
    image_input: bytes | np.ndarray | Image.Image,
    aggressive: bool = False,
) -> PreprocessResult:
    """
    Preprocess an image for Tesseract OCR.

    Pipeline (applied selectively based on image quality):
    1. Convert to grayscale
    2. Normalize resolution (scale down if > 3400px, scale up if < 900px)
    3. Denoise (fast Gaussian if aggressive)
    4. Deskew (if aggressive)
    5. Adaptive threshold (for poor contrast)

    Args:
        image_input: Raw image bytes, numpy array, or PIL Image
        aggressive: Apply stronger transformations for very low-quality images
    """
    # Convert input to numpy array
    img = _to_numpy(image_input)

    was_resized = False
    was_denoised = False
    was_deskewed = False
    was_thresholded = False
    skew_angle = 0.0

    # Step 1: Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Step 2: Normalize dimensions for fast high-accuracy OCR
    h, w = gray.shape[:2]
    long_edge = max(h, w)
    short_edge = min(h, w)

    if long_edge > MAX_LONG_EDGE_PX:
        scale = MAX_LONG_EDGE_PX / long_edge
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
        was_resized = True
        logger.debug(f"Downscaled oversized image from {w}x{h} to {new_w}x{new_h}")
    elif short_edge < TARGET_SHORT_EDGE_PX:
        scale = TARGET_SHORT_EDGE_PX / short_edge
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        was_resized = True
        logger.debug(f"Resized from {w}x{h} to {new_w}x{new_h}")

    # Step 3: Fast smoothing (Gaussian blur instead of slow non-local means)
    if aggressive:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        was_denoised = True

    # Step 4: Fast Deskew (only run Hough transform when aggressive=True)
    if aggressive:
        skew_angle = _estimate_skew(gray)
        if abs(skew_angle) > 1.0:
            gray = _deskew(gray, skew_angle)
            was_deskewed = True

    # Step 5: Adaptive thresholding for poor contrast / dark backgrounds
    mean_val = float(np.mean(gray))
    contrast = _estimate_contrast(gray)
    if aggressive or (contrast < 25 and mean_val < 160):
        gray = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=25,
            C=10
        )
        was_thresholded = True

    return PreprocessResult(
        image_array=gray,
        was_resized=was_resized,
        was_denoised=was_denoised,
        was_deskewed=was_deskewed,
        was_thresholded=was_thresholded,
        skew_angle=skew_angle,
    )


def _to_numpy(image_input: bytes | np.ndarray | Image.Image) -> np.ndarray:
    """Convert various image formats to OpenCV numpy array."""
    if isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image bytes")
        return img
    elif isinstance(image_input, Image.Image):
        return cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
    elif isinstance(image_input, np.ndarray):
        return image_input.copy()
    else:
        raise TypeError(f"Unsupported image type: {type(image_input)}")


def _estimate_noise(gray: np.ndarray) -> float:
    """Estimate image noise using Laplacian variance."""
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.std(lap))


def _estimate_contrast(gray: np.ndarray) -> float:
    """Estimate image contrast as standard deviation of pixel values."""
    return float(np.std(gray))


def _estimate_skew(gray: np.ndarray) -> float:
    """
    Estimate document skew angle using Hough line transform.
    Returns angle in degrees. Returns 0.0 on failure.
    """
    try:
        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Hough lines
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        if lines is None:
            return 0.0

        angles = []
        for line in lines[:50]:  # Sample first 50 lines
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            if -45 < angle < 45:  # Only near-horizontal lines
                angles.append(angle)

        if not angles:
            return 0.0

        return float(np.median(angles))
    except Exception:
        return 0.0


def _deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image to correct skew."""
    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        gray, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated
