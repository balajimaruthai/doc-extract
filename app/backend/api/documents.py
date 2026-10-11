"""
Documents API — upload, list, retrieve, delete, view extracted text.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from core.config import settings
from database.connection import get_connection
from documents.ingestion import validate_and_ingest, FileValidationError

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and ingest a document. Validates file type, checks for duplicates.
    """
    try:
        file_data = await file.read()
        metadata = validate_and_ingest(
            file_data=file_data,
            original_filename=file.filename or "unknown",
            upload_dir=settings.UPLOADS_DIR,
        )
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # Check for duplicate
    async with get_connection() as conn:
        existing = await conn.execute(
            "SELECT id, original_filename FROM documents WHERE content_hash = ?",
            (metadata.content_hash,)
        )
        dup = await existing.fetchone()
        if dup:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "duplicate",
                    "message": (
                        f"This document is identical to an already uploaded file: "
                        f"'{dup['original_filename']}'"
                    ),
                    "existing_id": dup["id"],
                }
            )

        # Insert document record
        await conn.execute(
            """INSERT INTO documents (
                id, original_filename, safe_filename, file_type,
                file_size, content_hash, upload_timestamp, processing_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                metadata.id, metadata.original_filename, metadata.safe_filename,
                metadata.file_type, metadata.file_size,
                metadata.content_hash, metadata.upload_timestamp,
            )
        )
        await conn.commit()

    return {
        "id": metadata.id,
        "filename": metadata.original_filename,
        "file_type": metadata.file_type,
        "file_size": metadata.file_size,
        "status": "pending",
        "message": "Document uploaded successfully",
    }


@router.get("/")
async def list_documents(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List all documents with optional status filter."""
    async with get_connection() as conn:
        if status:
            cursor = await conn.execute(
                """SELECT id, original_filename, file_type, file_size,
                          processing_status, document_type, page_count,
                          ocr_performed, upload_timestamp, error_message,
                          metadata_json
                   FROM documents WHERE processing_status = ?
                   ORDER BY upload_timestamp DESC LIMIT ? OFFSET ?""",
                (status, limit, offset)
            )
        else:
            cursor = await conn.execute(
                """SELECT id, original_filename, file_type, file_size,
                          processing_status, document_type, page_count,
                          ocr_performed, upload_timestamp, error_message,
                          metadata_json
                   FROM documents
                   ORDER BY upload_timestamp DESC LIMIT ? OFFSET ?""",
                (limit, offset)
            )

        rows = await cursor.fetchall()
        total_cursor = await conn.execute("SELECT COUNT(*) FROM documents")
        total = (await total_cursor.fetchone())[0]

    return {
        "documents": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """Get document metadata."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return dict(row)


@router.get("/{doc_id}/text")
async def get_document_text(doc_id: str):
    """Get extracted text pages for a document."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT page_number, extraction_method, cleaned_text, ocr_confidence
               FROM document_pages WHERE document_id = ?
               ORDER BY page_number""",
            (doc_id,)
        )
        pages = await cursor.fetchall()

    return {"pages": [dict(p) for p in pages]}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its stored file."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT safe_filename FROM documents WHERE id = ?", (doc_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        # Remove stored file
        file_path = settings.UPLOADS_DIR / row["safe_filename"]
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

        # Cleanly delete all referencing child rows to satisfy foreign key constraints
        for tbl in ["document_pages", "processing_jobs", "profile_documents"]:
            await conn.execute(f"DELETE FROM {tbl} WHERE document_id = ?", (doc_id,))

        for tbl in ["education", "experience", "skills", "certifications", "projects", "achievements", "evidence"]:
            await conn.execute(f"DELETE FROM {tbl} WHERE source_document_id = ?", (doc_id,))

        await conn.execute(
            "DELETE FROM conflicts WHERE source_a_document_id = ? OR source_b_document_id = ?",
            (doc_id, doc_id)
        )

        await conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await conn.commit()

    return {"message": "Document deleted", "id": doc_id}


@router.get("/stats/summary")
async def document_stats():
    """Return document processing statistics for the dashboard."""
    async with get_connection() as conn:
        total_cur = await conn.execute("SELECT COUNT(*) FROM documents")
        total = (await total_cur.fetchone())[0]

        pending_cur = await conn.execute(
            "SELECT COUNT(*) FROM documents WHERE processing_status = 'pending'"
        )
        pending = (await pending_cur.fetchone())[0]

        completed_cur = await conn.execute(
            "SELECT COUNT(*) FROM documents WHERE processing_status = 'completed'"
        )
        completed = (await completed_cur.fetchone())[0]

        failed_cur = await conn.execute(
            "SELECT COUNT(*) FROM documents WHERE processing_status = 'failed'"
        )
        failed = (await failed_cur.fetchone())[0]

        review_cur = await conn.execute(
            "SELECT COUNT(*) FROM documents WHERE processing_status = 'review'"
        )
        needs_review = (await review_cur.fetchone())[0]

    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "failed": failed,
        "needs_review": needs_review,
    }
