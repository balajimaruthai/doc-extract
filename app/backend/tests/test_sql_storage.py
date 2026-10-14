import sys
from pathlib import Path
import pytest
import sqlite3

# Ensure backend root is on sys.path
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from database.connection import init_db, get_connection, set_db_path


@pytest.mark.asyncio
async def test_sql_storage_blob_and_financial_records(tmp_path: Path):
    # Set up temporary database
    db_file = tmp_path / "test_storage.db"
    set_db_path(db_file)
    await init_db()

    async with get_connection() as conn:
        # Verify columns in documents table
        cursor = await conn.execute("PRAGMA table_info(documents)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "file_data" in cols
        assert "mime_type" in cols

        # Insert a test document with raw binary file_data BLOB
        dummy_pdf_bytes = b"%PDF-1.4 sample pdf binary data content"
        doc_id = "test-doc-sql-1"
        await conn.execute(
            """INSERT INTO documents (
                id, original_filename, safe_filename, file_type, file_size,
                content_hash, upload_timestamp, processing_status, file_data, mime_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)""",
            (
                doc_id, "test_invoice.pdf", "test_invoice.pdf", "pdf", len(dummy_pdf_bytes),
                "hash123", "2026-10-14T10:00:00Z", dummy_pdf_bytes, "application/pdf"
            )
        )

        # Insert extracted financial record
        await conn.execute(
            """INSERT INTO extracted_financial_records (
                id, document_id, original_filename, document_type,
                invoice_number, invoice_date, normalized_invoice_date,
                due_date, normalized_due_date, payment_terms, po_number,
                merchant_or_vendor, client_or_customer,
                subtotal, tax_amount, discount_amount, handling_fee, tip_amount,
                total_gross, total_fringe, payroll_total, amount_paid, balance_due,
                total_amount_due, currency, math_verified,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "fin-rec-1", doc_id, "test_invoice.pdf", "invoice",
                "INV-9999", "10/14/2026", "2026-10-14",
                "10/29/2026", "2026-10-29", "Net 15", "PO-100",
                "Acme Corp", "Client XYZ",
                4400.0, 350.63, 150.0, 53.33, 0.0,
                5332.60, 1517.76, 6850.36, 1000.0, 3600.63,
                6903.69, "USD", 1,
                "2026-10-14T10:05:00Z", "2026-10-14T10:05:00Z"
            )
        )
        await conn.commit()

        # Query back documents with BLOB
        doc_cur = await conn.execute("SELECT file_data, mime_type, file_size FROM documents WHERE id = ?", (doc_id,))
        doc_row = await doc_cur.fetchone()
        assert doc_row["file_data"] == dummy_pdf_bytes
        assert doc_row["mime_type"] == "application/pdf"

        # Query back structured financial records
        fin_cur = await conn.execute("SELECT * FROM extracted_financial_records WHERE document_id = ?", (doc_id,))
        fin_row = await fin_cur.fetchone()
        assert fin_row["total_amount_due"] == 6903.69
        assert fin_row["payroll_total"] == 6850.36
        assert fin_row["handling_fee"] == 53.33
        assert fin_row["math_verified"] == 1
        assert fin_row["invoice_number"] == "INV-9999"
        assert fin_row["normalized_invoice_date"] == "2026-10-14"
        assert fin_row["normalized_due_date"] == "2026-10-29"
