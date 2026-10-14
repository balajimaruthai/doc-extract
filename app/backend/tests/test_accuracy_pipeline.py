"""
Comprehensive Accuracy and Verification Pipeline Tests.
Validates document understanding, semantic financial field isolation,
deterministic due date calculation, mathematical reconciliation,
and classification.
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

# Ensure backend root is on sys.path
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from validation.date_validator import (
    DateField,
    parse_date_string,
    parse_payment_terms_days,
    calculate_due_date,
)
from validation.financial_validator import (
    FinancialField,
    parse_currency_number,
    format_currency,
    extract_financial_data,
    validate_financial_consistency,
)
from documents.classification import classify_document, DocumentType, ConfidenceLevel
from extraction_pipeline.extractor import ExtractionResult, _apply_rule_based_fallbacks


class TestInvoiceAccuracyCoreCase:
    """Tests specifically targeting the user-reported invoice issue."""

    def test_user_invoice_extraction(self):
        invoice_raw_text = """
        INVOICE
        Invoice Number: 26304921
        Invoice Date: 01/14/2026
        Terms: DD Net 1 Day

        Billed To: ACME Corporation
        Remit To: Enterprise Services LLC

        Line Items:
        Engineering Services           5,332.60
        
        Total Gross:                   5,332.60
        Total Fringe:                  1,517.76
        Payroll Total:                 6,850.36
        Handling:                         53.33

        TOTAL AMOUNT DUE:              6,903.69
        """

        result = ExtractionResult()
        _apply_rule_based_fallbacks(invoice_raw_text, result, "invoice", "invoice_26304921.pdf")

        # 1. Invoice Number
        assert result.invoice_number == "26304921"

        # 2. Total Amount Due must be 6,903.69, NOT 5,332.60 (Total Gross)
        assert result.total_amount_due in ("6,903.69", "$6,903.69")
        assert result.total_gross in ("5,332.60", "$5,332.60")
        assert result.total_amount_due != result.total_gross

        # 3. Intermediate components
        assert "6,850.36" in (result.payroll_total or "")
        assert "53.33" in (result.handling_fee or "")
        assert "1,517.76" in (result.total_fringe or "")

        # 4. Dates
        assert result.normalized_invoice_date == "2026-01-14"
        assert result.payment_terms == "DD Net 1 Day"
        # Due Date calculated programmatically: 2026-01-14 + 1 day = 2026-01-15
        assert result.due_date == "2026-01-15"
        assert result.normalized_due_date == "2026-01-15"

        # 5. Math reconciliation
        assert result.math_verified is True
        assert result.validation_report is not None
        assert result.validation_report.get("math_reconciled") is True

        # 6. Structured schema
        assert result.structured_data is not None
        assert result.structured_data["document_type"] == "invoice"
        assert result.structured_data["total_amount_due"]["value"] == 6903.69
        assert result.structured_data["total_gross"]["value"] == 5332.60
        assert result.structured_data["due_date"]["value"] == "2026-01-15"


class TestDateExtractionAndCalculation:
    """Test date normalization and payment term math."""

    def test_mm_dd_yyyy_disambiguation(self):
        # 14 cannot be a month -> 2026-01-14
        d_obj, iso_str, conf = parse_date_string("01/14/2026")
        assert d_obj == date(2026, 1, 14)
        assert iso_str == "2026-01-14"

    def test_dd_mm_yyyy_disambiguation(self):
        d_obj, iso_str, conf = parse_date_string("14/01/2026")
        assert d_obj == date(2026, 1, 14)
        assert iso_str == "2026-01-14"

    def test_iso_format(self):
        d_obj, iso_str, conf = parse_date_string("2026-01-14")
        assert d_obj == date(2026, 1, 14)
        assert iso_str == "2026-01-14"

    def test_textual_month(self):
        d1, s1, _ = parse_date_string("January 14, 2026")
        d2, s2, _ = parse_date_string("14 Jan 2026")
        assert d1 == date(2026, 1, 14)
        assert d2 == date(2026, 1, 14)

    def test_payment_term_extraction(self):
        assert parse_payment_terms_days("DD Net 1 Day") == 1
        assert parse_payment_terms_days("Net 30 Days") == 30
        assert parse_payment_terms_days("Payment due within 15 days") == 15
        assert parse_payment_terms_days("Due on receipt") == 0
        assert parse_payment_terms_days("Immediate") == 0

    def test_due_date_calculation_from_terms(self):
        inv_field = DateField(value="2026-01-14", date_obj=date(2026, 1, 14), source="document")
        due_field = calculate_due_date(inv_field, payment_terms="DD Net 1 Day")
        assert due_field.value == "2026-01-15"
        assert due_field.source == "calculated"

    def test_explicit_due_date_takes_precedence(self):
        inv_field = DateField(value="2026-01-14", date_obj=date(2026, 1, 14), source="document")
        due_field = calculate_due_date(inv_field, payment_terms="DD Net 1 Day", explicit_due_date_str="2026-01-20")
        assert due_field.value == "2026-01-20"
        assert due_field.source == "document"

    def test_no_date_hallucination_when_missing(self):
        inv_field = DateField()
        due_field = calculate_due_date(inv_field, payment_terms=None)
        assert due_field.value is None
        assert due_field.source == "not_detected"


class TestFinancialReconciliation:
    """Test arithmetic verification and semantic field separation."""

    def test_payroll_and_handling_math(self):
        fields = {
            "total_gross": FinancialField(value=5332.60, label="Total Gross"),
            "total_fringe": FinancialField(value=1517.76, label="Total Fringe"),
            "payroll_total": FinancialField(value=6850.36, label="Payroll Total"),
            "handling": FinancialField(value=53.33, label="Handling"),
            "total_amount_due": FinancialField(value=6903.69, label="TOTAL AMOUNT DUE"),
        }
        report = validate_financial_consistency(fields)
        assert report.is_valid is True
        assert report.math_reconciled is True
        assert len(report.verified_calculations) >= 2

    def test_standard_subtotal_tax_discount_math(self):
        fields = {
            "subtotal": FinancialField(value=100.00, label="Subtotal"),
            "tax": FinancialField(value=8.50, label="Tax"),
            "discount": FinancialField(value=5.00, label="Discount"),
            "total_amount_due": FinancialField(value=103.50, label="Total"),
        }
        report = validate_financial_consistency(fields)
        assert report.is_valid is True
        assert report.math_reconciled is True

    def test_financial_field_semantic_isolation(self):
        text = """
        Subtotal: $400.00
        Tax: $40.00
        Total Gross: $440.00
        Less Discount: $20.00
        TOTAL AMOUNT DUE: $420.00
        """
        fields, report = extract_financial_data(text)
        assert fields["subtotal"].value == 400.00
        assert fields["tax"].value == 40.00
        assert fields["total_gross"].value == 440.00
        assert fields["total_amount_due"].value == 420.00
        assert fields["total_amount_due"].value != fields["total_gross"].value


class TestDocumentClassification:
    """Test classification for multiple document formats."""

    def test_classify_invoice(self):
        res = classify_document("INVOICE #123\nTotal Amount Due: $100\nPayment Terms: Net 30")
        assert res.document_type == DocumentType.INVOICE
        assert res.document_subtype in ("invoice", "commercial_invoice")

    def test_classify_receipt(self):
        res = classify_document("WALMART STORE #1234\nITEMS SOLD\nTOTAL CASH $23.50\nCHANGE $6.50")
        assert res.document_type == DocumentType.RECEIPT

    def test_classify_purchase_order(self):
        res = classify_document("PURCHASE ORDER PO-99881\nVENDOR: Industrial Supplies\nDELIVERY DATE: 2026-02-01")
        assert res.document_type == DocumentType.PURCHASE_ORDER

    def test_classify_contract(self):
        res = classify_document("THIS NON-DISCLOSURE AGREEMENT entered into between Party A and Party B...")
        assert res.document_type == DocumentType.CONTRACT

    def test_classify_salary_slip(self):
        res = classify_document("MONTHLY PAYSLIP / SALARY STATEMENT\nBasic Salary: $4,000\nProvident Fund: $300\nNet Pay: $3,700")
        assert res.document_type == DocumentType.SALARY_SLIP

    def test_classify_unknown_when_low_confidence(self):
        res = classify_document("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
        # Low confidence text falls back to unknown
        assert res.document_type == DocumentType.UNKNOWN or res.confidence == ConfidenceLevel.LOW
