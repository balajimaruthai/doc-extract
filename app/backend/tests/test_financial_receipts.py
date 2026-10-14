"""
Unit tests for diverse receipt and invoice document formats.
Verifies correct field isolation, semantic separation, and mathematical reconciliation.
"""
import pytest
from documents.classification import classify_document, DocumentType
from validation.financial_validator import extract_financial_data
from extraction_pipeline.extractor import extract_from_text, ExtractionResult, _apply_rule_based_fallbacks


def test_pos_retail_receipt():
    text = """
    WHOLE FOODS MARKET #1042
    123 Main Street, Austin, TX 78701
    Date: 02/18/2026 14:32
    Cashier: Alex M.

    Organic Bananas               $2.49
    Almond Milk 64oz              $3.99
    Wild Salmon Fillet           $18.50
    Olive Oil Extra Virgin       $14.99
    Artisan Sourdough             $5.50

    SUBTOTAL                     $45.47
    DISCOUNT (Store Promo)        $5.00
    SALES TAX (8.25%)             $3.34
    TOTAL AMOUNT DUE             $43.81

    PAYMENT METHOD: VISA **** 4821
    AMOUNT PAID:                 $43.81
    CHANGE DUE:                   $0.00
    """
    res = ExtractionResult()
    _apply_rule_based_fallbacks(text, res, "receipt", "whole_foods_receipt.txt")
    
    assert res.subtotal == "$45.47"
    assert res.discount_amount == "$5.00"
    assert res.tax_amount == "$3.34"
    assert res.total_amount_due == "$43.81"
    assert res.invoice_date == "02/18/2026"
    assert res.normalized_invoice_date == "2026-02-18"
    assert res.math_verified is True


def test_restaurant_dining_receipt_with_gratuity():
    text = """
    THE RUSTIC BISTRO
    Table: 14 | Guests: 2
    Date: 03/01/2026  8:15 PM
    Server: Michael R.

    2x Ribeye Steak 12oz         $76.00
    1x Cabernet Sauvignon        $28.00
    1x Truffle Fries             $12.00
    1x Tiramisu Dessert           $9.00

    Food & Beverage Subtotal:   $125.00
    State & Local Tax (8%):      $10.00
    Service Gratuity / Tip:      $25.00
    FINAL TOTAL / AMOUNT DUE:   $160.00

    Paid via MasterCard ending in 9012
    """
    res = ExtractionResult()
    _apply_rule_based_fallbacks(text, res, "receipt", "restaurant_bistro.txt")

    assert res.subtotal == "$125.00"
    assert res.tax_amount == "$10.00"
    assert res.tip_amount == "$25.00"
    assert res.total_amount_due == "$160.00"
    assert res.invoice_date == "03/01/2026"
    assert res.normalized_invoice_date == "2026-03-01"
    assert res.math_verified is True


def test_commercial_invoice_with_freight_and_discount():
    text = """
    TECHSUPPLY SOLUTIONS LLC
    100 Enterprise Way, Suite 400
    San Jose, CA 95110

    INVOICE
    Invoice Number: TS-2026-8841
    Invoice Date: 02/10/2026
    Payment Terms: Net 30 Days

    Bill To: Global Analytics Corp
    Ship To: Global Analytics Corp - Data Center 2

    Item Description        Qty    Unit Price    Total
    Rackmount Server 2U       2     $2,500.00   $5,000.00
    10GbE Switch 24-Port      1     $1,200.00   $1,200.00
    Fiber Patch Cables 5m    10        $15.00     $150.00

    Subtotal:                                  $6,350.00
    Enterprise Discount (5%):                   -$317.50
    Freight & Handling:                          $120.00
    Applicable Sales Tax (7.25%):                $437.36
    TOTAL AMOUNT DUE:                          $6,589.86

    Remit To: TechSupply Solutions LLC, Account # 482910492
    Wire Routing: 121000358
    """
    cls = classify_document(text, "commercial_invoice.pdf")
    assert cls.document_type == DocumentType.INVOICE
    assert cls.document_subtype == "commercial_invoice"

    res = ExtractionResult()
    _apply_rule_based_fallbacks(text, res, "invoice", "commercial_invoice.pdf")

    assert res.invoice_number == "TS-2026-8841"
    assert res.normalized_invoice_date == "2026-02-10"
    assert res.payment_terms == "Net 30 Days"
    assert res.normalized_due_date == "2026-03-12"
    assert res.subtotal == "$6,350.00"
    assert res.discount_amount == "$317.50"
    assert res.handling_fee == "$120.00"
    assert res.tax_amount == "$437.36"
    assert res.total_amount_due == "$6,589.86"
    assert res.math_verified is True


def test_utility_service_bill():
    text = """
    METRO POWER & UTILITIES
    Customer Account: 9821-4472-01
    Statement Date: 01/20/2026
    Due Date: 02/15/2026

    Summary of Account Activity:
    Previous Balance:                           $145.20
    Payments Received (Thank you):             -$145.20
    Balance Forward:                              $0.00

    New Charges (01/01/2026 - 01/20/2026):
    Electric Usage 840 kWh:                      $92.40
    Grid Access & Base Fee:                      $15.00
    State Environmental Surcharge:                $3.25
    Municipal Utility Tax:                        $4.15
    TOTAL CURRENT CHARGES:                      $114.80

    TOTAL AMOUNT DUE:                           $114.80
    Due Date: 02/15/2026
    """
    res = ExtractionResult()
    _apply_rule_based_fallbacks(text, res, "invoice", "metro_power_bill.pdf")

    assert res.normalized_invoice_date == "2026-01-20"
    assert res.normalized_due_date == "2026-02-15"
    assert res.total_amount_due == "$114.80"
    assert res.math_verified is True
