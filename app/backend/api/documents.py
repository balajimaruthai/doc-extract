"""
Documents API — upload, list, retrieve, delete, view extracted text.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse, Response

from core.config import settings
from database.connection import get_connection
from documents.ingestion import validate_and_ingest, FileValidationError

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
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

    import mimetypes
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    # Check for duplicate
    async with get_connection() as conn:
        existing = await conn.execute(
            """SELECT id, original_filename, processing_status, file_type, file_size, document_type, metadata_json 
               FROM documents WHERE content_hash = ?""",
            (metadata.content_hash,)
        )
        dup = await existing.fetchone()
        if dup:
            if dup["processing_status"] == "completed":
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": dup["id"],
                        "filename": dup["original_filename"],
                        "file_type": dup["file_type"] or metadata.file_type,
                        "file_size": dup["file_size"] or metadata.file_size,
                        "document_type": dup["document_type"],
                        "status": "completed",
                        "cached": True,
                        "message": "Document previously processed. Returning cached result.",
                        "existing_id": dup["id"],
                    }
                )
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

        # Insert document record with SQL BLOB file storage
        await conn.execute(
            """INSERT INTO documents (
                id, original_filename, safe_filename, file_type,
                file_size, content_hash, upload_timestamp, processing_status,
                file_data, mime_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                metadata.id, metadata.original_filename, metadata.safe_filename,
                metadata.file_type, metadata.file_size,
                metadata.content_hash, metadata.upload_timestamp,
                file_data, mime_type,
            )
        )
        await conn.commit()

    # Automatically trigger background processing immediately upon upload
    if background_tasks:
        try:
            from api.processing import _process_single_document
            background_tasks.add_task(_process_single_document, doc_id=metadata.id)
        except Exception:
            pass

    return {
        "id": metadata.id,
        "filename": metadata.original_filename,
        "file_type": metadata.file_type,
        "file_size": metadata.file_size,
        "status": "processing" if background_tasks else "pending",
        "message": "Document uploaded and processing initiated",
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


@router.get("/financial-records")
async def list_financial_records(limit: int = 50, offset: int = 0):
    """List structured financial records stored in the SQL database."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT id, document_id, original_filename, document_type,
                      invoice_number, invoice_date, normalized_invoice_date,
                      due_date, normalized_due_date, payment_terms, po_number,
                      merchant_or_vendor, client_or_customer,
                      subtotal, tax_amount, discount_amount, handling_fee, tip_amount,
                      total_gross, total_fringe, payroll_total, amount_paid, balance_due,
                      total_amount_due, currency, math_verified,
                      line_items_json, validation_report_json, created_at, updated_at
               FROM extracted_financial_records
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        total_cursor = await conn.execute("SELECT COUNT(*) FROM extracted_financial_records")
        total = (await total_cursor.fetchone())[0]

    return {
        "records": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """Get document metadata (excluding heavy binary BLOB)."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT id, original_filename, safe_filename, file_type, file_size,
                      content_hash, upload_timestamp, processing_status,
                      has_native_text, ocr_performed, ocr_confidence, page_count,
                      document_type, classification_confidence, classification_method,
                      error_message, notes, metadata_json, mime_type
               FROM documents WHERE id = ?""",
            (doc_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return dict(row)


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: str):
    """Retrieve the original uploaded file from disk or SQL BLOB storage."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT original_filename, safe_filename, mime_type, file_data FROM documents WHERE id = ?",
            (doc_id,)
        )
        doc = await cursor.fetchone()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    content = None
    file_path = settings.UPLOADS_DIR / doc["safe_filename"]
    if file_path.exists():
        try:
            content = file_path.read_bytes()
        except Exception:
            pass

    if content is None and doc["file_data"]:
        content = doc["file_data"]

    if content is None:
        raise HTTPException(status_code=404, detail="Document file content not found on disk or database")

    mime = doc["mime_type"] or "application/octet-stream"
    filename = doc["original_filename"] or "download"

    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.get("/{doc_id}/financial-record")
async def get_document_financial_record(doc_id: str):
    """Get structured financial extraction record stored in SQL for a document."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT id, document_id, original_filename, document_type,
                      invoice_number, invoice_date, normalized_invoice_date,
                      due_date, normalized_due_date, payment_terms, po_number,
                      merchant_or_vendor, client_or_customer,
                      subtotal, tax_amount, discount_amount, handling_fee, tip_amount,
                      total_gross, total_fringe, payroll_total, amount_paid, balance_due,
                      total_amount_due, currency, math_verified,
                      line_items_json, validation_report_json, raw_extracted_json,
                      created_at, updated_at
               FROM extracted_financial_records WHERE document_id = ?""",
            (doc_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Financial record not found for this document")

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
        for tbl in ["document_pages", "processing_jobs", "profile_documents", "extracted_financial_records"]:
            try:
                await conn.execute(f"DELETE FROM {tbl} WHERE document_id = ?", (doc_id,))
            except Exception:
                pass

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
