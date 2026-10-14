"""
Test 100% Offline Document Chat & Q&A.
"""
import sys
from pathlib import Path
import pytest

backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from api.chat import _offline_grounded_answer


def test_offline_chat_amount_due_disambiguation():
    # Test invoice metadata with 6903.69 total amount due and 5332.60 gross
    doc_meta = {
        "invoice_number": "26304921",
        "total_gross": "$5,332.60",
        "payroll_total": "$6,850.36",
        "handling_fee": "$53.33",
        "total_amount_due": "$6,903.69",
        "payment_terms": "DD Net 1 Day",
        "due_date": "2026-01-15",
    }
    fin_record = {
        "invoice_number": "26304921",
        "total_amount_due": 6903.69,
        "total_gross": 5332.60,
        "payroll_total": 6850.36,
        "handling_fee": 53.33,
        "payment_terms": "DD Net 1 Day",
        "normalized_due_date": "2026-01-15",
        "math_verified": 1,
    }
    pages = [
        {"page_number": 1, "cleaned_text": "INVOICE 26304921 TOTAL GROSS $5,332.60 PAYROLL $6,850.36 HANDLING $53.33 TOTAL AMOUNT DUE $6,903.69"}
    ]

    # Ask for total amount due
    ans, sources, conf = _offline_grounded_answer(
        question="What is the total amount due?",
        doc_meta=doc_meta,
        fin_record=fin_record,
        pages=pages,
        doc_name="AP_Invoice.pdf",
    )
    assert "$6,903.69" in ans
    assert "$5,332.60" in ans  # Mentions Total Gross as distinct from Total Amount Due
    assert conf >= 0.95
    assert any(s.label == "TOTAL AMOUNT DUE" for s in sources)


def test_offline_chat_due_date_and_terms():
    doc_meta = {
        "payment_terms": "DD Net 1 Day",
        "due_date": "01/15/2026",
        "normalized_due_date": "2026-01-15",
    }
    fin_record = {
        "payment_terms": "DD Net 1 Day",
        "due_date": "01/15/2026",
        "normalized_due_date": "2026-01-15",
        "normalized_invoice_date": "2026-01-14",
    }
    pages = []

    ans, sources, conf = _offline_grounded_answer(
        question="When is this due and what are the payment terms?",
        doc_meta=doc_meta,
        fin_record=fin_record,
        pages=pages,
        doc_name="AP_Invoice.pdf",
    )
    assert "2026-01-15" in ans
    assert "DD Net 1 Day" in ans
    assert conf >= 0.95


def test_offline_chat_summarize():
    doc_meta = {
        "document_type": "invoice",
        "document_summary": "Invoice #26304921 has a total due of $6,903.69.",
        "invoice_number": "26304921",
    }
    fin_record = {
        "document_type": "invoice",
        "invoice_number": "26304921",
        "total_amount_due": 6903.69,
    }
    pages = []

    ans, sources, conf = _offline_grounded_answer(
        question="Summarize this document",
        doc_meta=doc_meta,
        fin_record=fin_record,
        pages=pages,
        doc_name="AP_Invoice.pdf",
    )
    assert "Summary of AP_Invoice.pdf" in ans
    assert "$6,903.69" in ans
