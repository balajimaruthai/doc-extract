"""
SQLite database connection and initialization.
Uses aiosqlite for async access. All data stays local.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

_db_path: Path | None = None


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = path


def get_db_path() -> Path:
    if _db_path is None:
        from core.config import settings
        return settings.DB_PATH
    return _db_path


@asynccontextmanager
async def get_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager for a database connection.
    Usage:
        async with get_connection() as conn:
            await conn.execute(...)
    """
    async with aiosqlite.connect(str(get_db_path())) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db() -> None:
    """Initialize database schema. Idempotent — safe to run on every startup."""
    logger.info(f"Initializing database at {get_db_path()}")
    async with aiosqlite.connect(str(get_db_path())) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        await _create_schema(conn)
        # Backfill file_data for any existing documents where file is on disk
        try:
            from core.config import settings
            cur = await conn.execute("SELECT id, safe_filename FROM documents WHERE file_data IS NULL")
            missing_files = await cur.fetchall()
            for r in missing_files:
                doc_id = r[0] if isinstance(r, (tuple, list)) else r["id"]
                s_name = r[1] if isinstance(r, (tuple, list)) else r["safe_filename"]
                p = settings.UPLOADS_DIR / s_name
                if p.exists():
                    try:
                        b = p.read_bytes()
                        await conn.execute("UPDATE documents SET file_data = ? WHERE id = ?", (b, doc_id))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"File backfill notice: {e}")
        await conn.commit()
    logger.info("Database schema ready")


async def _create_schema(conn: aiosqlite.Connection) -> None:
    """Create all tables if they don't exist."""

    # Documents
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            safe_filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            upload_timestamp TEXT NOT NULL,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            has_native_text INTEGER DEFAULT 0,
            ocr_performed INTEGER DEFAULT 0,
            ocr_confidence REAL,
            page_count INTEGER,
            document_type TEXT,
            classification_confidence TEXT,
            classification_method TEXT,
            error_message TEXT,
            notes TEXT,
            metadata_json TEXT,
            file_data BLOB,
            mime_type TEXT,
            UNIQUE(content_hash)
        )
    """)

    # Safe migration for existing documents table
    try:
        cur = await conn.execute("PRAGMA table_info(documents)")
        rows = await cur.fetchall()
        doc_cols = set()
        for r in rows:
            if isinstance(r, (tuple, list)):
                doc_cols.add(r[1])
            else:
                doc_cols.add(r["name"])
        if "file_data" not in doc_cols:
            await conn.execute("ALTER TABLE documents ADD COLUMN file_data BLOB")
        if "mime_type" not in doc_cols:
            await conn.execute("ALTER TABLE documents ADD COLUMN mime_type TEXT")
    except Exception as e:
        logger.warning(f"Documents schema migration notice: {e}")

    # Extracted Structured Financial Records
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS extracted_financial_records (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            original_filename TEXT,
            document_type TEXT,
            invoice_number TEXT,
            invoice_date TEXT,
            normalized_invoice_date TEXT,
            due_date TEXT,
            normalized_due_date TEXT,
            payment_terms TEXT,
            po_number TEXT,
            merchant_or_vendor TEXT,
            client_or_customer TEXT,
            subtotal REAL,
            tax_amount REAL,
            discount_amount REAL,
            handling_fee REAL,
            tip_amount REAL,
            total_gross REAL,
            total_fringe REAL,
            payroll_total REAL,
            amount_paid REAL,
            balance_due REAL,
            total_amount_due REAL,
            currency TEXT DEFAULT 'USD',
            math_verified INTEGER DEFAULT 0,
            line_items_json TEXT,
            raw_extracted_json TEXT,
            validation_report_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(document_id)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_records_doc ON extracted_financial_records(document_id)")

    # Document pages (extracted text per page)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS document_pages (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page_number INTEGER NOT NULL,
            extraction_method TEXT NOT NULL,
            raw_text TEXT,
            cleaned_text TEXT,
            ocr_confidence REAL,
            bounding_boxes TEXT,
            UNIQUE(document_id, page_number)
        )
    """)

    # Processing jobs
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id TEXT PRIMARY KEY,
            document_id TEXT REFERENCES documents(id),
            stage TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            error_reason TEXT,
            ocr_used INTEGER DEFAULT 0,
            llm_used INTEGER DEFAULT 0,
            model_name TEXT,
            duration_ms INTEGER
        )
    """)

    # Profiles
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            date_of_birth TEXT,
            professional_summary TEXT,
            estimated_experience_level TEXT,
            estimated_experience_basis TEXT,
            total_documented_experience_months INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Profile ↔ Document mapping
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_documents (
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            PRIMARY KEY (profile_id, document_id)
        )
    """)

    # Education
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS education (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            degree TEXT,
            specialization TEXT,
            institution TEXT,
            university TEXT,
            start_date TEXT,
            graduation_date TEXT,
            percentage REAL,
            cgpa REAL,
            education_level TEXT,
            source_document_id TEXT REFERENCES documents(id),
            source_page INTEGER,
            confidence_level TEXT,
            extraction_method TEXT DEFAULT 'ai_extracted',
            user_corrected INTEGER DEFAULT 0,
            original_ai_value TEXT
        )
    """)

    # Experience
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS experience (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            company TEXT,
            designation TEXT,
            employment_type TEXT,
            location TEXT,
            start_date TEXT,
            end_date TEXT,
            is_current INTEGER DEFAULT 0,
            responsibilities TEXT,
            duration_months INTEGER,
            source_document_id TEXT REFERENCES documents(id),
            source_page INTEGER,
            confidence_level TEXT,
            extraction_method TEXT DEFAULT 'ai_extracted',
            user_corrected INTEGER DEFAULT 0,
            original_ai_value TEXT
        )
    """)

    # Skills
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            source_document_id TEXT REFERENCES documents(id),
            confidence_level TEXT
        )
    """)

    # Certifications
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS certifications (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            name TEXT,
            issuer TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            credential_id TEXT,
            source_document_id TEXT REFERENCES documents(id),
            source_page INTEGER,
            confidence_level TEXT,
            extraction_method TEXT DEFAULT 'ai_extracted',
            user_corrected INTEGER DEFAULT 0,
            original_ai_value TEXT
        )
    """)

    # Projects
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            name TEXT,
            description TEXT,
            technologies TEXT,
            organization TEXT,
            start_date TEXT,
            end_date TEXT,
            source_document_id TEXT REFERENCES documents(id),
            confidence_level TEXT
        )
    """)

    # Achievements
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            title TEXT,
            organization TEXT,
            date TEXT,
            description TEXT,
            source_document_id TEXT REFERENCES documents(id),
            confidence_level TEXT
        )
    """)

    # Evidence
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            field_value TEXT,
            source_document_id TEXT REFERENCES documents(id),
            source_page INTEGER,
            source_text_snippet TEXT,
            confidence_level TEXT
        )
    """)

    # Conflicts
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS conflicts (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            value_a TEXT,
            source_a_document_id TEXT REFERENCES documents(id),
            source_a_page INTEGER,
            value_b TEXT,
            source_b_document_id TEXT REFERENCES documents(id),
            source_b_page INTEGER,
            resolution TEXT DEFAULT 'unresolved',
            resolved_value TEXT,
            resolved_by TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Create indexes
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_pages_doc ON document_pages(document_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_doc ON processing_jobs(document_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_education_profile ON education(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_experience_profile ON experience(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_profile ON skills(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_certs_profile ON certifications(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_profile ON evidence(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_conflicts_profile ON conflicts(profile_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_conflicts_unresolved ON conflicts(profile_id, resolution)")
