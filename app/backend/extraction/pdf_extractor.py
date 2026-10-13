"""
PDF text extraction using PyMuPDF (fitz).
Strategy: native text first, OCR only if text is insufficient.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = 50  # Below this threshold → page likely needs OCR


@dataclass
class PageText:
    page_number: int          # 1-indexed
    text: str
    char_count: int
    extraction_method: str    # "native" or "ocr_needed"
    needs_ocr: bool
    image_data: Optional[bytes] = None   # PNG bytes if OCR needed


@dataclass
class PDFExtractionResult:
    document_path: str
    total_pages: int
    pages: list[PageText]
    has_native_text: bool      # True if at least some pages have native text
    needs_ocr: bool            # True if at least some pages need OCR
    is_password_protected: bool
    error: Optional[str] = None


def extract_pdf(file_path: Path, ocr_dpi: int = 180) -> PDFExtractionResult:
    """
    Extract text from a PDF file.
    For pages with sufficient native text: return text directly.
    For pages with insufficient text (scanned): render to image for OCR.

    Args:
        file_path: Path to the PDF file
        ocr_dpi: DPI for rendering pages that need OCR (default 180 for sub-2s speed)
    """
    pages: list[PageText] = []
    is_password_protected = False
    error = None

    try:
        doc = fitz.open(str(file_path))
    except fitz.FileDataError as e:
        logger.error(f"PDF damaged or unreadable: {file_path}: {e}")
        return PDFExtractionResult(
            document_path=str(file_path),
            total_pages=0,
            pages=[],
            has_native_text=False,
            needs_ocr=False,
            is_password_protected=False,
            error=f"PDF is damaged or unreadable: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to open PDF {file_path}: {e}")
        return PDFExtractionResult(
            document_path=str(file_path),
            total_pages=0,
            pages=[],
            has_native_text=False,
            needs_ocr=False,
            is_password_protected=False,
            error=str(e),
        )

    # Check for password protection
    if doc.is_encrypted:
        # Try empty password (some PDFs have nominal encryption)
        if not doc.authenticate(""):
            doc.close()
            logger.warning(f"PDF is password-protected: {file_path}")
            return PDFExtractionResult(
                document_path=str(file_path),
                total_pages=0,
                pages=[],
                has_native_text=False,
                needs_ocr=False,
                is_password_protected=True,
                error="PDF is password-protected and cannot be processed.",
            )

    total_pages = doc.page_count
    logger.info(f"Processing PDF: {file_path.name} ({total_pages} pages)")

    for page_num in range(total_pages):
        page = doc[page_num]

        # Extract native text
        raw_text = page.get_text("text")
        cleaned = _clean_native_text(raw_text)
        char_count = len(cleaned.strip())

        if char_count >= MIN_CHARS_PER_PAGE:
            # Sufficient native text — no OCR needed
            pages.append(PageText(
                page_number=page_num + 1,
                text=cleaned,
                char_count=char_count,
                extraction_method="native",
                needs_ocr=False,
            ))
        else:
            # Insufficient text — render page for OCR
            logger.debug(
                f"Page {page_num + 1}: only {char_count} chars — "
                "rendering for OCR"
            )
            image_bytes = _render_page_to_image(page, dpi=ocr_dpi)
            pages.append(PageText(
                page_number=page_num + 1,
                text=cleaned,  # Store whatever little native text exists
                char_count=char_count,
                extraction_method="ocr_needed",
                needs_ocr=True,
                image_data=image_bytes,
            ))

    doc.close()

    has_native_text = any(p.extraction_method == "native" for p in pages)
    needs_ocr = any(p.needs_ocr for p in pages)

    logger.info(
        f"PDF extraction complete: {file_path.name} | "
        f"{total_pages} pages | native={has_native_text} | needs_ocr={needs_ocr}"
    )

    return PDFExtractionResult(
        document_path=str(file_path),
        total_pages=total_pages,
        pages=pages,
        has_native_text=has_native_text,
        needs_ocr=needs_ocr,
        is_password_protected=False,
    )


def _clean_native_text(text: str) -> str:
    """Clean extracted native text — normalize whitespace, remove nulls."""
    import re
    # Remove null bytes
    text = text.replace("\x00", "")
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive blank lines (keep max 2)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse excessive spaces (but preserve indentation signals)
    text = re.sub(r"[ \t]{3,}", "  ", text)
    return text.strip()


def _render_page_to_image(page: fitz.Page, dpi: int = 180) -> bytes:
    """
    Render a PDF page to PNG bytes at the specified DPI (default 180 for sub-2s speed).
    Used when native text extraction yields insufficient content.
    """
    zoom = dpi / 72.0  # 72 DPI is the base PDF unit
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY)
    return pixmap.tobytes("png")
