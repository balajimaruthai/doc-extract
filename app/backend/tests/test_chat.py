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


def test_offline_chat_medical_records():
    pages = [
        {
            "page_number": 1,
            "cleaned_text": """
            CITY GENERAL HOSPITAL - PATIENT RECORD
            Patient Name: Sarah Connor
            Date of Birth: 1985-04-12
            Attending Physician: Dr. James Marcus
            Diagnosis: Acute Bronchitis with mild wheezing
            Blood Pressure: 120/80 mmHg
            Prescription: Amoxicillin 500mg TID for 7 days
            Follow-up: 2 weeks
            """
        }
    ]
    doc_meta = {"document_type": "medical_record"}

    # Question 1: What is the diagnosis?
    ans, sources, conf = _offline_grounded_answer(
        question="What is the diagnosis?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="Patient_Report_001.pdf"
    )
    assert "Acute Bronchitis" in ans
    assert conf >= 0.90

    # Question 2: Who is the attending physician?
    ans2, _, _ = _offline_grounded_answer(
        question="Who is the attending physician?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="Patient_Report_001.pdf"
    )
    assert "Dr. James Marcus" in ans2


def test_offline_chat_legal_contract():
    pages = [
        {
            "page_number": 1,
            "cleaned_text": """
            NON-DISCLOSURE AGREEMENT
            Effective Date: November 01, 2026
            Disclosing Party: Apex Robotics Inc.
            Receiving Party: Quantum Softworks LLC
            Governing Law: State of Delaware
            Term: 3 years from effective date
            Confidentiality Period: 5 years following termination
            """
        }
    ]
    doc_meta = {"document_type": "contract"}

    # Ask for governing law
    ans, sources, conf = _offline_grounded_answer(
        question="What is the governing law?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="Apex_NDA.pdf"
    )
    assert "State of Delaware" in ans

    # Ask for term
    ans2, _, _ = _offline_grounded_answer(
        question="What is the term of this agreement?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="Apex_NDA.pdf"
    )
    assert "3 years" in ans2


def test_offline_chat_unknown_data_and_logs():
    pages = [
        {
            "page_number": 1,
            "cleaned_text": """
            SYS-LOG-TIMESTAMP 2026-10-14T08:22:15Z
            System Component: Authentication Gateway
            Incident ID: INC-88401
            Error Code: AUTH_TIMEOUT_504
            Root Cause: Redis cluster connection pool exhausted on port 6379
            Mitigation: Increased maximum connection pool size from 50 to 200
            Status: Resolved
            """
        }
    ]
    doc_meta = {"document_type": "unknown"}

    # Ask for incident ID
    ans, _, _ = _offline_grounded_answer(
        question="What is the incident ID and error code?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="system_debug.log"
    )
    assert "INC-88401" in ans
    assert "AUTH_TIMEOUT_504" in ans

    # Ask for root cause
    ans2, _, _ = _offline_grounded_answer(
        question="What was the root cause?",
        doc_meta=doc_meta,
        fin_record=None,
        pages=pages,
        doc_name="system_debug.log"
    )
    assert "Redis cluster" in ans2

