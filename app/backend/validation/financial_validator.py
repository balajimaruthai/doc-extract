"""
Financial field extraction, semantic label binding, and mathematical consistency validation.
Ensures document-grounded extraction where:
1. Every field is read from the document OR deterministically calculated.
2. Financial concepts are never conflated (total gross != total amount due).
3. The final payable amount is specifically identified by semantic label and document layout.
4. Mathematical consistency is validated (subtotal+tax+fees-discounts=total, gross+fringe=payroll, payroll+handling=total_due).
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FinancialField:
    value: Optional[float] = None          # Cleaned numeric value
    formatted: Optional[str] = None        # Formatted string with currency e.g. "$6,903.69"
    raw: Optional[str] = None              # Exact text snippet from document
    confidence: float = 0.0                # 0.0 to 1.0
    source: str = "not_detected"           # "document" | "calculated" | "not_detected"
    label: Optional[str] = None            # The label matched in document
    page: int = 1                          # Document page number
    is_verified: bool = False              # Whether validated by mathematical check

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "value": self.value,
            "formatted": self.formatted,
            "raw": self.raw,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "is_verified": self.is_verified,
        }
        if self.label:
            d["label"] = self.label
        if self.page:
            d["page"] = self.page
        return d


@dataclass
class FinancialValidationReport:
    is_valid: bool = True
    confidence: float = 0.95
    verified_calculations: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    math_reconciled: bool = False


def parse_currency_number(val: Any) -> Optional[float]:
    """Parse numeric currency float safely from string or number."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "n/a", "not detected"):
        return None
    if s.endswith("%"):
        return None
    # Handle European or OCR comma-decimal transposition e.g. "1.517,76"
    if re.search(r"^\$?[\d\s]+\.\d{3},\d{2}$", s):
        s = s.replace(" ", "").replace(".", "").replace(",", ".")
    elif "," in s and "." in s and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    cleaned = re.sub(r"[^\d.-]", "", s)
    try:
        if cleaned:
            return round(float(cleaned), 2)
    except Exception:
        pass
    return None


def format_currency(num: Optional[float], currency_symbol: str = "$") -> Optional[str]:
    """Format float into standard currency string with commas."""
    if num is None:
        return None
    return f"{currency_symbol}{num:,.2f}"


def extract_labeled_amount(
    text: str,
    label_patterns: List[str],
    negative_patterns: Optional[List[str]] = None,
    default_label: str = "Amount"
) -> FinancialField:
    """
    Search text for a specific financial label followed closely by its numeric value.
    Supports same line (horizontal), markdown table rows (with |), and stacked (next line) values.
    """
    for pat in label_patterns:
        # Match label, optional parenthetical notes, optional horizontal/vertical separator, optional currency and amount
        full_regex = (
            rf"(?i)\b{pat}\b"
            rf"[^\S\r\n]*(?:\([^\)\n\r]+\))?[^\S\r\n]*"
            rf"(?:[:\-\|]|--+)?[^\S\r\n]*"
            rf"(?:\r?\n[^\S\r\n]*)?"
            rf"(?:[:\-\|]|--+)?[^\S\r\n]*"
            rf"-?([$€£₹]?[^\S\r\n]*[\d,]+(?:\.\d{{1,2}})?)"
            rf"(?![^\S\r\n]*%)"
        )
        matches = list(re.finditer(full_regex, text))
        for m in matches:
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            matched_segment = text[line_start:line_end]

            # Check negative patterns to avoid false matches
            if negative_patterns:
                skip = False
                for neg in negative_patterns:
                    if re.search(neg, matched_segment, re.I):
                        skip = True
                        break
                if skip:
                    continue

            val_str = m.group(1).replace(" ", "").strip()
            num = parse_currency_number(val_str)
            # Avoid single digit non-currency false matches like standalone '2'
            if num is not None and (num >= 1.0 or any(sym in m.group(1) for sym in ["$", "€", "£", "₹"]) or "." in val_str or "," in val_str):
                matched_label = m.group(0)[:m.start(1) - m.start(0)].strip(" :\t-|\r\n")
                curr_symbol = "$"
                if any(sym in m.group(1) for sym in ["€", "£", "₹"]):
                    curr_symbol = [sym for sym in ["€", "£", "₹"] if sym in m.group(1)][0]

                return FinancialField(
                    value=num,
                    formatted=format_currency(num, curr_symbol),
                    raw=m.group(0).strip(),
                    confidence=0.98,
                    source="document",
                    label=matched_label or default_label,
                    page=1,
                    is_verified=False
                )

    return FinancialField(
        value=None,
        formatted=None,
        raw=None,
        confidence=0.0,
        source="not_detected",
        label=default_label,
        page=1,
        is_verified=False
    )


def extract_financial_data(text: str) -> Tuple[Dict[str, FinancialField], FinancialValidationReport]:
    """
    Extract all distinct financial fields with semantic binding:
    - total_amount_due (final payable amount)
    - total_gross
    - total_fringe
    - payroll_total
    - handling_fee
    - subtotal
    - tax_amount
    - discount_amount
    - amount_paid
    - balance_due

    Then performs strict mathematical consistency validation.
    """
    fields: Dict[str, FinancialField] = {}

    # 1. Total Gross (Must NOT be confused with Total Amount Due)
    fields["total_gross"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"total\s+gross",
            r"gross\s+total",
            r"gross\s+amount",
            r"gross\s+wages",
            r"total\s+gross\s+pay",
        ],
        negative_patterns=[r"amount\s+due", r"balance\s+due"],
        default_label="Total Gross"
    )

    # 2. Total Fringe (Employer fringes in payroll billing)
    fields["total_fringe"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"total\s+fringe",
            r"employer\s+fringes?",
            r"fringe\s+benefits?",
            r"fringe\s+total",
        ],
        default_label="Total Fringe"
    )

    # 3. Payroll Total (Gross + Fringe)
    fields["payroll_total"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"payroll\s+total",
            r"total\s+payroll",
            r"payroll\s+charges?",
        ],
        negative_patterns=[r"amount\s+due"],
        default_label="Payroll Total"
    )

    # 4. Handling Fee / Freight / Shipping / Service Charge
    fields["handling"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"freight\s*(?:&|and)?\s*handling",
            r"shipping\s*(?:&|and)?\s*handling",
            r"freight\b",
            r"shipping\b",
            r"handling\s*(?:fee|charges?)?",
            r"service\s+charges?",
            r"processing\s+fees?",
            r"grid\s+access\s+&\s+base\s+fee",
            r"surcharge",
        ],
        default_label="Handling"
    )

    # 5. Final Payable Amount (Total Amount Due / Balance Due / Grand Total)
    fields["total_amount_due"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"total\s+amount\s+due",
            r"balance\s+due",
            r"final\s+total(?:\s*/\s*amount\s+due)?",
            r"final\s+total",
            r"total\s+current\s+charges",
            r"total\s+payable(?:\s+due)?",
            r"total\s+amount\s+payable",
            r"net\s+payable",
            r"amount\s+payable",
            r"total\s+due",
            r"amount\s+due",
            r"invoice\s+total",
            r"grand\s+total",
            r"balance\s+payable",
            r"total\s+paid",
        ],
        negative_patterns=[r"gross", r"fringe", r"subtotal", r"before\s+tax", r"line\s+total"],
        default_label="TOTAL AMOUNT DUE"
    )

    # 6. Subtotal
    fields["subtotal"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"subtotal",
            r"sub-total",
            r"sub\s+total",
            r"food\s+&\s+beverage\s+subtotal",
            r"net\s+amount",
        ],
        negative_patterns=[r"due", r"gross"],
        default_label="Subtotal"
    )

    # 7. Tip / Gratuity
    fields["tip"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"service\s+gratuity(?:\s*/\s*tip)?",
            r"gratuity",
            r"tip\b",
        ],
        default_label="Tip / Gratuity"
    )

    # 7. Tax / VAT / GST
    fields["tax"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"sales\s+tax",
            r"tax\s+amount",
            r"total\s+tax",
            r"tax\b",
            r"vat\b",
            r"gst\b",
            r"tax\s*\(\d+(?:\.\d+)?%\)",
        ],
        default_label="Tax"
    )

    # 8. Discounts
    fields["discount"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"discount",
            r"total\s+discount",
            r"rebate",
            r"savings?",
        ],
        default_label="Discount"
    )

    # 9. Amount Paid
    fields["amount_paid"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"amount\s+paid",
            r"total\s+paid",
            r"payment\s+received",
            r"paid\s+to\s+date",
        ],
        default_label="Amount Paid"
    )

    # 10. Balance Due
    fields["balance_due"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"balance\s+due",
            r"current\s+balance\s+due",
            r"remaining\s+balance",
        ],
        default_label="Balance Due"
    )

    # 11. Current Charges (Utility / Service Statements)
    fields["current_charges"] = extract_labeled_amount(
        text,
        label_patterns=[
            r"total\s+current\s+charges",
            r"current\s+charges",
            r"total\s+new\s+charges",
            r"new\s+charges",
        ],
        default_label="Current Charges"
    )

    # ── Mathematical Reconciliation & Consistency Checks ───────
    report = validate_financial_consistency(fields, text)

    return fields, report


def validate_financial_consistency(
    fields: Dict[str, FinancialField],
    full_text: str = ""
) -> FinancialValidationReport:
    """
    Validate mathematical relationships between extracted financial fields.
    Checks:
    1. Payroll Billing:
       Total Gross + Total Fringe == Payroll Total
       Payroll Total + Handling == TOTAL AMOUNT DUE
    2. Standard Invoice / Receipt:
       Subtotal + Tax + Handling/Freight + Tip - Discounts == Total Due
    3. Current Charges (Utility / Statement):
       Current Charges == Total Amount Due
    4. Balance / Payment:
       Total Due == Amount Paid (Paid in full) OR Total - Amount Paid == Balance Due
    """
    report = FinancialValidationReport()

    gross = fields.get("total_gross", FinancialField()).value
    fringe = fields.get("total_fringe", FinancialField()).value
    payroll = fields.get("payroll_total", FinancialField()).value
    handling = fields.get("handling", FinancialField()).value
    total_due = fields.get("total_amount_due", FinancialField()).value
    subtotal = fields.get("subtotal", FinancialField()).value
    tax = fields.get("tax", FinancialField()).value
    discount = fields.get("discount", FinancialField()).value
    tip = fields.get("tip", FinancialField()).value
    paid = fields.get("amount_paid", FinancialField()).value
    balance = fields.get("balance_due", FinancialField()).value
    curr_charges = fields.get("current_charges", FinancialField()).value

    # --- Check 1: Payroll billing arithmetic ---
    # Total Gross + Fringe = Payroll Total
    if gross is not None and payroll is not None:
        calc_fringe = round(payroll - gross, 2)
        if (fringe is None or abs(round(gross + fringe, 2) - payroll) > 0.05) and calc_fringe > 0:
            # Deterministically calculate / reconcile missing or corrupted fringe
            fields["total_fringe"] = FinancialField(
                value=calc_fringe,
                formatted=format_currency(calc_fringe),
                raw=f"Calculated: Payroll ({payroll}) - Gross ({gross})",
                confidence=0.99,
                source="calculated",
                label="Total Fringe (Reconciled)",
                is_verified=True
            )
            fringe = calc_fringe
            report.verified_calculations.append(f"Reconciled Fringe: Payroll ({payroll}) - Gross ({gross}) = {calc_fringe}")
            fields["total_gross"].is_verified = True
            fields["total_fringe"].is_verified = True
            fields["payroll_total"].is_verified = True
            report.math_reconciled = True
        elif fringe is not None and abs(round(gross + fringe, 2) - payroll) <= 0.05:
            fields["total_gross"].is_verified = True
            fields["total_fringe"].is_verified = True
            fields["payroll_total"].is_verified = True
            report.verified_calculations.append(f"Reconciled: Gross ({gross}) + Fringe ({fringe}) = Payroll Total ({payroll})")
            report.math_reconciled = True

    # Payroll Total + Handling = Total Amount Due
    if payroll is not None:
        calc_total = round(payroll + (handling or 0.0), 2)
        if total_due is not None:
            expected_handling = round(total_due - payroll, 2)
            if (handling is None or abs(calc_total - total_due) > 0.05) and expected_handling > 0:
                # Deterministically reconcile handling fee from total_due - payroll
                fields["handling"] = FinancialField(
                    value=expected_handling,
                    formatted=format_currency(expected_handling),
                    raw=f"Reconciled: Total Due ({total_due}) - Payroll ({payroll})",
                    confidence=0.99,
                    source="calculated",
                    label="Handling Charge (Reconciled)",
                    is_verified=True
                )
                handling = expected_handling
                calc_total = total_due
                fields["total_amount_due"].is_verified = True
                fields["handling"].is_verified = True
                fields["payroll_total"].is_verified = True
                report.verified_calculations.append(
                    f"Reconciled Final Due: Payroll ({payroll}) + Handling ({handling}) = Total Due ({total_due})"
                )
                report.math_reconciled = True
                report.confidence = 0.99
            elif abs(calc_total - total_due) <= 0.05:
                fields["total_amount_due"].is_verified = True
                if fields["handling"].value is not None:
                    fields["handling"].is_verified = True
                fields["payroll_total"].is_verified = True
                report.verified_calculations.append(
                    f"Reconciled Final Due: Payroll ({payroll}) + Handling ({handling or 0.0}) = Total Due ({total_due})"
                )
                report.math_reconciled = True
                report.confidence = 0.99
            else:
                # Conflict detected! Check if total_due was mistakenly set to gross
                if gross is not None and abs(total_due - gross) <= 0.05:
                    report.validation_warnings.append(
                        f"CORRECTED CONFLICT: Total Amount Due was mistakenly set to Total Gross ({gross}). Correcting to {calc_total}."
                    )
                    # Correct to mathematically confirmed final amount due
                    fields["total_amount_due"] = FinancialField(
                        value=calc_total,
                        formatted=format_currency(calc_total),
                        raw=f"Calculated: Payroll ({payroll}) + Handling ({handling or 0.0})",
                        confidence=0.99,
                        source="calculated",
                        label="TOTAL AMOUNT DUE (Reconciled)",
                        is_verified=True
                    )
                    report.math_reconciled = True
                else:
                    report.validation_warnings.append(
                        f"Warning: Payroll ({payroll}) + Handling ({handling or 0.0}) != Total Due ({total_due})"
                    )
                    report.confidence = 0.75
        elif total_due is None and handling is not None:
            # Deterministically calculate verified total amount due
            fields["total_amount_due"] = FinancialField(
                value=calc_total,
                formatted=format_currency(calc_total),
                raw=f"Calculated: Payroll ({payroll}) + Handling ({handling})",
                confidence=0.99,
                source="calculated",
                label="TOTAL AMOUNT DUE (Calculated)",
                is_verified=True
            )
            report.verified_calculations.append(
                f"Calculated Final Due: Payroll ({payroll}) + Handling ({handling}) = {calc_total}"
            )
            report.math_reconciled = True

    # --- Check 2: Standard Invoice / Receipt: Subtotal + Tax + Handling/Freight + Tip - Discount = Total Due ---
    if subtotal is not None and (tax is not None or discount is not None or handling is not None or tip is not None):
        h_val = (handling or 0.0) if payroll is None else 0.0
        calc_std_total = round(subtotal + (tax or 0.0) + h_val + (tip or 0.0) - (discount or 0.0), 2)
        if total_due is not None:
            if abs(calc_std_total - total_due) <= 0.05:
                fields["total_amount_due"].is_verified = True
                fields["subtotal"].is_verified = True
                if tax is not None: fields["tax"].is_verified = True
                if discount is not None: fields["discount"].is_verified = True
                if tip is not None: fields["tip"].is_verified = True
                if h_val > 0: fields["handling"].is_verified = True

                parts = [f"Subtotal ({subtotal})"]
                if discount is not None: parts.append(f"- Discount ({discount})")
                if h_val > 0: parts.append(f"+ Freight/Handling ({h_val})")
                if tax is not None: parts.append(f"+ Tax ({tax})")
                if tip is not None: parts.append(f"+ Tip/Gratuity ({tip})")

                report.verified_calculations.append(
                    f"Reconciled: {' '.join(parts)} = Total ({total_due})"
                )
                report.math_reconciled = True
                report.confidence = 0.99
            elif abs(subtotal - total_due) <= 0.05 and abs(calc_std_total - total_due) > 0.05:
                # Potential mistake where total_due was erroneously set to subtotal when taxes/discounts exist
                report.validation_warnings.append(
                    f"CORRECTED CONFLICT: Total Amount Due was mistakenly set to Subtotal ({subtotal}). Correcting to calculated {calc_std_total}."
                )
                fields["total_amount_due"] = FinancialField(
                    value=calc_std_total,
                    formatted=format_currency(calc_std_total),
                    raw=f"Calculated: Subtotal ({subtotal}) + Adjustments",
                    confidence=0.99,
                    source="calculated",
                    label="TOTAL AMOUNT DUE (Reconciled)",
                    is_verified=True
                )
                report.math_reconciled = True

    # --- Check 3: Current Charges / Utility Statement Matching ---
    if curr_charges is not None and total_due is not None:
        if abs(curr_charges - total_due) <= 0.05:
            fields["total_amount_due"].is_verified = True
            fields["current_charges"].is_verified = True
            report.verified_calculations.append(
                f"Reconciled: Current Charges ({curr_charges}) == Total Due ({total_due})"
            )
            report.math_reconciled = True
            report.confidence = max(report.confidence, 0.99)

    # --- Check 4: Payment Reconciliation / Balance Due ---
    if total_due is not None and paid is not None:
        if abs(total_due - paid) <= 0.05:
            fields["amount_paid"].is_verified = True
            fields["total_amount_due"].is_verified = True
            report.verified_calculations.append(
                f"Reconciled Payment: Total Due ({total_due}) == Amount Paid ({paid}) [Paid in Full]"
            )
            report.math_reconciled = True
            report.confidence = max(report.confidence, 0.99)
        elif balance is not None:
            calc_bal = round(total_due - paid, 2)
            if abs(calc_bal - balance) <= 0.05:
                fields["balance_due"].is_verified = True
                fields["total_amount_due"].is_verified = True
                report.verified_calculations.append(
                    f"Reconciled Balance: Total ({total_due}) - Paid ({paid}) = Balance Due ({balance})"
                )
                report.math_reconciled = True
                report.confidence = max(report.confidence, 0.99)

    # Check 4b: Invoice Total (Subtotal - Discount + Tax) - Amount Paid == Balance Due
    if subtotal is not None and paid is not None and balance is not None:
        calc_tot = round(subtotal + (tax or 0.0) - (discount or 0.0), 2)
        calc_bal = round(calc_tot - paid, 2)
        if abs(calc_bal - balance) <= 0.05:
            fields["balance_due"].is_verified = True
            fields["amount_paid"].is_verified = True
            fields["subtotal"].is_verified = True
            if total_due is not None and abs(total_due - balance) <= 0.05:
                fields["total_amount_due"].is_verified = True
            report.verified_calculations.append(
                f"Reconciled Balance: Invoice Total ({calc_tot}) - Paid ({paid}) = Balance Due ({balance})"
            )
            report.math_reconciled = True
            report.confidence = max(report.confidence, 0.99)

    # Overall validity
    if report.validation_warnings and not report.math_reconciled:
        report.is_valid = False
        report.confidence = min(report.confidence, 0.65)

    return report
