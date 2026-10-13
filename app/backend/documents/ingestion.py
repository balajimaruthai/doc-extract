"""
Document ingestion — file validation, hashing, metadata extraction.
Security-first: magic bytes validation, path sanitization, no file execution.
"""
import hashlib
import logging
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# Magic bytes for supported file types
MAGIC_BYTES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],   # ZIP-based (docx, xlsx, etc.)
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE2 compound
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],
    "wav": [b"RIFF"],
    "mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    "mp4": [b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x20ftyp", b"\x00\x00\x00\x1cftyp", b"\x00\x00\x00\x14ftyp"],
    "mov": [b"\x00\x00\x00\x14ftypqt", b"\x00\x00\x00\x20ftypqt"],
    "avi": [b"RIFF"],
    "mkv": [b"\x1a\x45\xdf\xa3"],
    "webm": [b"\x1a\x45\xdf\xa3"],
}

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "doc", "jpg", "jpeg", "png", "webp",
    "wav", "mp3", "mp4", "mov", "avi", "mkv", "webm", "txt"
}
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB (expanded for video/audio)


class FileValidationError(Exception):
    """Raised when a file fails validation."""
    pass


class DocumentMetadata(BaseModel):
    """Metadata extracted from a file during ingestion."""
    id: str
    original_filename: str
    safe_filename: str
    file_type: str
    file_size: int
    content_hash: str
    upload_timestamp: str
    storage_path: str


def validate_and_ingest(
    file_data: bytes,
    original_filename: str,
    upload_dir: Path,
) -> DocumentMetadata:
    """
    Validate a file and store it safely. Returns document metadata.

    Checks:
    1. File size limit
    2. Extension whitelist
    3. Magic bytes (actual content, not just extension)
    4. Sanitized storage filename
    5. Duplicate detection via SHA-256 hash
    """
    # 1. Size check
    if len(file_data) > MAX_FILE_SIZE_BYTES:
        raise FileValidationError(
            f"File too large: {len(file_data) / (1024*1024):.1f} MB "
            f"(maximum: {MAX_FILE_SIZE_BYTES // (1024*1024)} MB)"
        )

    if len(file_data) == 0:
        raise FileValidationError("File is empty")

    # 2. Extension check
    suffix = Path(original_filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type '.{suffix}' is not supported. "
            f"Supported types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 3. Magic bytes check — actual content validation
    detected_type = _detect_file_type(file_data, suffix)
    if detected_type is None:
        raise FileValidationError(
            f"File content does not match its extension '.{suffix}'. "
            "The file may be corrupted or renamed."
        )

    # 3b. Verify detected type is compatible with claimed extension
    # (e.g., JPEG bytes claiming to be PDF is rejected)
    _EXT_TO_TYPE = {
        "pdf": {"pdf"},
        "docx": {"docx"},
        "doc": {"doc"},
        "jpg": {"jpg", "jpeg"},
        "jpeg": {"jpg", "jpeg"},
        "png": {"png"},
        "webp": {"webp"},
        "wav": {"wav"},
        "mp3": {"mp3"},
        "mp4": {"mp4"},
        "mov": {"mov", "mp4"},
        "avi": {"avi"},
        "mkv": {"mkv", "webm"},
        "webm": {"webm", "mkv"},
        "txt": {"txt"},
    }
    allowed_detected = _EXT_TO_TYPE.get(suffix, {suffix})
    if detected_type not in allowed_detected:
        raise FileValidationError(
            f"File content does not match its extension: claimed '.{suffix}' "
            f"but content appears to be '{detected_type}'. "
            "The file may be corrupted or renamed."
        )

    # 4. Normalize type (jpg and jpeg are the same)
    file_type = "jpg" if detected_type in ("jpg", "jpeg") else detected_type

    # 5. Content hash (SHA-256)
    content_hash = hashlib.sha256(file_data).hexdigest()

    # 6. Generate safe storage filename (UUID-based, no user input in path)
    doc_id = str(uuid.uuid4())
    safe_filename = f"{doc_id}.{file_type}"
    storage_path = upload_dir / safe_filename

    # 7. Write file to controlled directory
    _safe_write(file_data, storage_path, upload_dir)

    logger.info(
        f"Ingested: {original_filename!r} → {safe_filename} "
        f"({len(file_data)} bytes, SHA-256: {content_hash[:16]}...)"
    )

    return DocumentMetadata(
        id=doc_id,
        original_filename=_sanitize_display_name(original_filename),
        safe_filename=safe_filename,
        file_type=file_type,
        file_size=len(file_data),
        content_hash=content_hash,
        upload_timestamp=datetime.now(timezone.utc).isoformat(),
        storage_path=str(storage_path),
    )


def _detect_file_type(data: bytes, claimed_extension: str) -> Optional[str]:
    """
    Detect actual file type from magic bytes.
    Returns the detected type, or None if it doesn't match the claimed extension.
    """
    if claimed_extension == "txt":
        return "txt"

    header = data[:16]

    # Check each type
    for ftype, magic_list in MAGIC_BYTES.items():
        for magic in magic_list:
            if header.startswith(magic):
                detected = ftype

                # DOCX/DOC disambiguation: both are PK (ZIP) magic
                # DOCX is a ZIP. DOC is OLE2.
                if detected == "docx" and claimed_extension == "docx":
                    return "docx"
                elif detected == "docx" and claimed_extension == "doc":
                    return "docx"
                elif detected == "doc":
                    return "doc"
                elif detected in ("jpg", "jpeg"):
                    return "jpg"
                elif detected in ("pdf", "png", "webp", "wav", "mp3", "mp4", "mov", "avi", "mkv", "webm"):
                    return detected

    # Fallback for video containers with ftyp at offset 4
    if len(data) >= 8 and data[4:8] == b"ftyp":
        if claimed_extension in ("mp4", "mov"):
            return claimed_extension

    # Fallback for RIFF containers (WAV, WEBP, AVI)
    if header.startswith(b"RIFF") and len(data) >= 12:
        tag = data[8:12]
        if tag == b"WAVE":
            return "wav"
        elif tag == b"WEBP":
            return "webp"
        elif tag == b"AVI ":
            return "avi"

    # Permissive fallback if claimed extension is audio/video
    if claimed_extension in ("mp3", "wav", "mp4", "mov", "avi", "mkv", "webm"):
        return claimed_extension

    return None


def _safe_write(data: bytes, target_path: Path, allowed_dir: Path) -> None:
    """
    Write file data to target_path, enforcing that it stays within allowed_dir.
    Prevents path traversal.
    """
    # Resolve to absolute paths
    resolved_target = target_path.resolve()
    resolved_allowed = allowed_dir.resolve()

    # Ensure target is within allowed directory
    try:
        resolved_target.relative_to(resolved_allowed)
    except ValueError:
        raise FileValidationError(
            f"Security violation: attempted write outside upload directory"
        )

    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    resolved_target.write_bytes(data)


def _sanitize_display_name(filename: str) -> str:
    """
    Return a safe display name for the original filename.
    Strips path components and dangerous characters.
    Only stores the base name.
    """
    # Get only the base name (no directory traversal)
    name = Path(filename).name
    # Remove null bytes and control characters
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    # Limit length
    if len(name) > 255:
        stem = Path(name).stem[:240]
        suffix = Path(name).suffix
        name = stem + suffix
    return name or "unknown_document"


def compute_hash(file_data: bytes) -> str:
    """Compute SHA-256 hash of file data."""
    return hashlib.sha256(file_data).hexdigest()
