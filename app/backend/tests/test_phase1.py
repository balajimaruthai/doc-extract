"""
Phase 1 verification tests — verify all backend components are functional.
Run from: D:/Projects/offline document extraction/app/backend
Command: python -m pytest tests/ -v
"""
import asyncio
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Core Config ─────────────────────────────────────────────
class TestConfig:
    def test_settings_loads(self):
        from core.config import settings
        # Backend port is 37240
        assert settings.BACKEND_PORT == 37240
        assert settings.DB_PATH.name == "docextract.db"

    def test_models_dir_configured(self):
        from core.config import settings
        assert "models" in str(settings.MODELS_DIR).lower()

    def test_uploads_dir_configured(self):
        from core.config import settings
        assert "uploads" in str(settings.UPLOADS_DIR).lower()


# ─── Hardware Detection ───────────────────────────────────────
class TestHardwareDetector:
    def test_hardware_detection_runs(self):
        from hardware.detector import get_hardware_info
        hw = get_hardware_info()
        assert hw is not None

    def test_cpu_detected(self):
        from hardware.detector import get_hardware_info
        hw = get_hardware_info()
        assert hw.cpu_cores > 0
        assert hw.ram_total_gb > 0

    def test_profile_assigned(self):
        from hardware.detector import get_hardware_info
        hw = get_hardware_info()
        assert hw.profile is not None
        assert hw.recommended_model_tier in ("small", "medium", "large")


# ─── Document Ingestion ───────────────────────────────────────
class TestIngestion:
    def test_pdf_magic_bytes_validation(self, tmp_path):
        from documents.ingestion import validate_and_ingest, FileValidationError
        # Valid PDF magic
        pdf_data = b"%PDF-1.4\n%EOF"
        result = validate_and_ingest(pdf_data, "test.pdf", tmp_path)
        assert result.file_type == "pdf"
        assert result.content_hash == hashlib.sha256(pdf_data).hexdigest()

    def test_rejects_wrong_extension(self, tmp_path):
        from documents.ingestion import validate_and_ingest, FileValidationError
        with pytest.raises(FileValidationError, match="not supported"):
            validate_and_ingest(b"data", "test.exe", tmp_path)

    def test_rejects_empty_file(self, tmp_path):
        from documents.ingestion import validate_and_ingest, FileValidationError
        with pytest.raises(FileValidationError, match="empty"):
            validate_and_ingest(b"", "test.pdf", tmp_path)

    def test_rejects_mismatched_content(self, tmp_path):
        from documents.ingestion import validate_and_ingest, FileValidationError
        # Claim PDF but provide JPEG bytes
        jpeg_data = b"\xff\xd8\xff" + b"\x00" * 100
        with pytest.raises(FileValidationError, match="content does not match"):
            validate_and_ingest(jpeg_data, "test.pdf", tmp_path)

    def test_path_traversal_prevention(self, tmp_path):
        from documents.ingestion import _sanitize_display_name
        result = _sanitize_display_name("../../etc/passwd")
        assert ".." not in result
        assert result == "passwd"

    def test_png_accepted(self, tmp_path):
        from documents.ingestion import validate_and_ingest
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = validate_and_ingest(png_data, "photo.png", tmp_path)
        assert result.file_type == "png"

    def test_sha256_hash(self):
        from documents.ingestion import compute_hash
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_hash(data) == expected


# ─── Document Classification ──────────────────────────────────
class TestClassification:
    def test_resume_classified(self):
        from documents.classification import classify_document, DocumentType
        text = "RESUME\nWork Experience\nSkills\nEducation\nObjective: To work as a software engineer"
        result = classify_document(text, "resume.pdf")
        assert result.document_type == DocumentType.RESUME

    def test_degree_certificate_classified(self):
        from documents.classification import classify_document, DocumentType
        text = "This is to certify that the degree of Bachelor of Technology has been awarded to"
        result = classify_document(text, "degree.pdf")
        assert result.document_type == DocumentType.DEGREE_CERTIFICATE

    def test_experience_letter_classified(self):
        from documents.classification import classify_document, DocumentType
        text = "To Whomsoever It May Concern. This is to certify that the employee worked with our organization from January 2020"
        result = classify_document(text, "exp.pdf")
        assert result.document_type == DocumentType.EXPERIENCE_LETTER

    def test_marksheet_classified(self):
        from documents.classification import classify_document, DocumentType
        text = "Mark Sheet - Semester 5\nSubject Marks Obtained\nTotal: 450\nAggregate Percentage: 75%\nCGPA: 8.5"
        result = classify_document(text, "marksheet.pdf")
        assert result.document_type == DocumentType.MARKSHEET

    def test_empty_text_returns_needs_review(self):
        from documents.classification import classify_document, DocumentType
        result = classify_document("", "unknown.pdf")
        assert result.document_type == DocumentType.NEEDS_REVIEW


# ─── Experience Calculation ───────────────────────────────────
class TestExperienceCalculation:
    def test_simple_experience(self):
        from reconciliation.reconciler import _calculate_non_overlapping_months, _parse_date_flexible
        from datetime import date
        periods = [
            (date(2020, 1, 1), date(2022, 1, 1)),  # 24 months
        ]
        total = _calculate_non_overlapping_months(periods)
        assert total == 24

    def test_overlapping_experience_not_double_counted(self):
        from reconciliation.reconciler import _calculate_non_overlapping_months
        from datetime import date
        periods = [
            (date(2020, 1, 1), date(2022, 1, 1)),   # 24 months
            (date(2021, 1, 1), date(2023, 1, 1)),   # overlaps by 12 months
        ]
        total = _calculate_non_overlapping_months(periods)
        # Should be 36 months (Jan 2020 - Jan 2023), not 48
        assert total == 36

    def test_date_parsing_iso(self):
        from reconciliation.reconciler import _parse_date_flexible
        from datetime import date
        result = _parse_date_flexible("2022-06-01")
        assert result == date(2022, 6, 1)

    def test_date_parsing_month_year(self):
        from reconciliation.reconciler import _parse_date_flexible
        from datetime import date
        result = _parse_date_flexible("June 2022")
        assert result == date(2022, 6, 1)

    def test_date_parsing_year_only(self):
        from reconciliation.reconciler import _parse_date_flexible
        from datetime import date
        result = _parse_date_flexible("2022")
        assert result == date(2022, 1, 1)

    def test_date_parsing_invalid_returns_none(self):
        from reconciliation.reconciler import _parse_date_flexible
        result = _parse_date_flexible("N/A")
        assert result is None


# ─── Extraction Schema ────────────────────────────────────────
class TestExtractionSchema:
    def test_valid_data_parses(self):
        from extraction_pipeline.extractor import ExtractionResult
        data = {
            "personal": {"name": "John Doe", "email": "john@example.com"},
            "education": [{"degree": "B.Tech", "institution": "MIT"}],
            "experience": [{"company": "Google", "designation": "SWE", "is_current": False}],
            "skills": {"programming_languages": ["Python", "Java"]},
            "certifications": [],
            "projects": [],
            "achievements": [],
        }
        result = ExtractionResult.model_validate(data)
        assert result.personal.name == "John Doe"
        assert len(result.education) == 1
        assert result.education[0].degree == "B.Tech"

    def test_invalid_cgpa_rejected(self):
        from extraction_pipeline.extractor import EducationEntry
        edu = EducationEntry(degree="B.Tech", cgpa=15.0)  # Invalid > 10
        assert edu.cgpa is None

    def test_invalid_percentage_rejected(self):
        from extraction_pipeline.extractor import EducationEntry
        edu = EducationEntry(degree="B.Tech", percentage=150.0)  # Invalid > 100
        assert edu.percentage is None

    def test_null_fields_allowed(self):
        from extraction_pipeline.extractor import ExtractionResult
        result = ExtractionResult()
        assert result.personal.name is None
        assert result.education == []


# ─── Database ─────────────────────────────────────────────────
class TestDatabase:
    @pytest.mark.asyncio
    async def test_init_db_runs(self, tmp_path):
        from database.connection import set_db_path, init_db
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        await init_db()
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_tables_created(self, tmp_path):
        from database.connection import set_db_path, init_db, get_connection
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        await init_db()

        async with get_connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in await cursor.fetchall()]

        expected = [
            "achievements", "certifications", "conflicts", "documents",
            "document_pages", "education", "evidence", "experience",
            "processing_jobs", "profile_documents", "profiles", "projects",
            "skills"
        ]
        for table in expected:
            assert table in tables, f"Missing table: {table}"

    @pytest.mark.asyncio
    async def test_insert_and_query_document(self, tmp_path):
        from database.connection import set_db_path, init_db, get_connection
        import uuid
        from datetime import datetime, timezone

        db_path = tmp_path / "test2.db"
        set_db_path(db_path)
        await init_db()

        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO documents (id, original_filename, safe_filename, file_type,
                   file_size, content_hash, upload_timestamp, processing_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, "test.pdf", f"{doc_id}.pdf", "pdf", 1000, "abc123", now, "pending")
            )
            await conn.commit()

            cursor = await conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            row = await cursor.fetchone()
            assert row is not None
            assert row["original_filename"] == "test.pdf"
            assert row["processing_status"] == "pending"


# ─── OCR Preprocessor ────────────────────────────────────────
class TestOCRPreprocessor:
    def test_preprocessor_handles_numpy_array(self):
        import numpy as np
        from ocr.preprocessor import preprocess_for_ocr

        # Create a synthetic grayscale image (600x800)
        img = np.full((600, 800), 128, dtype=np.uint8)
        result = preprocess_for_ocr(img)
        assert result.image_array is not None
        # Output is always 2D (grayscale)
        assert len(result.image_array.shape) == 2
        # Small image gets resized up
        assert result.was_resized is True

    def test_preprocessor_resizes_small_image(self):
        import numpy as np
        from ocr.preprocessor import preprocess_for_ocr, TARGET_SHORT_EDGE_PX

        # Create a small image (200x300)
        img = np.full((200, 300), 200, dtype=np.uint8)
        result = preprocess_for_ocr(img)
        h, w = result.image_array.shape[:2]
        assert min(h, w) >= TARGET_SHORT_EDGE_PX or result.was_resized


# ─── Security ─────────────────────────────────────────────────
class TestSecurity:
    def test_sanitize_path_traversal(self):
        from documents.ingestion import _sanitize_display_name
        names = [
            ("../../etc/passwd", "passwd"),
            ("C:\\Windows\\system32\\evil.exe", "evil.exe"),
            ("../../../root/.bashrc", ".bashrc"),
            ("normal_file.pdf", "normal_file.pdf"),
        ]
        for input_name, expected_stem in names:
            result = _sanitize_display_name(input_name)
            assert ".." not in result
            assert "\\" not in result

    def test_content_hash_uniqueness(self):
        from documents.ingestion import compute_hash
        h1 = compute_hash(b"document A content")
        h2 = compute_hash(b"document B content")
        assert h1 != h2
        assert len(h1) == 64  # SHA-256 hex = 64 chars


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
