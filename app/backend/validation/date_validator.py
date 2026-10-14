"""
Date extraction, validation, and programmatic due date calculation.
Handles multiple date formats, context-based disambiguation, payment terms arithmetic,
and tracks source (document vs calculated).
Never uses the current system date for calculations or fallbacks.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, Dict, Any


@dataclass
class DateField:
    value: Optional[str] = None          # Normalized ISO: YYYY-MM-DD
    raw: Optional[str] = None            # Exact text from document
    confidence: float = 0.0              # 0.0 to 1.0
    source: str = "not_detected"         # "document" | "calculated" | "not_detected"
    label: Optional[str] = None          # e.g. "Invoice Date", "Due Date"
    date_obj: Optional[date] = None      # Internal python date object

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "value": self.value,
            "raw": self.raw,
            "confidence": round(self.confidence, 2),
            "source": self.source,
        }
        if self.label:
            d["label"] = self.label
        return d


MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_date_string(date_str: str, prefer_us_format: bool = True) -> Tuple[Optional[date], Optional[str], float]:
    """
    Parse a date string in various formats:
    - MM/DD/YYYY or DD/MM/YYYY
    - YYYY-MM-DD or YYYY/MM/DD
    - MM-DD-YYYY or DD-MM-YYYY
    - Month DD, YYYY or DD Month YYYY
    - DD-Mon-YYYY

    Uses contextual disambiguation:
    If a component is > 12 and <= 31, it MUST be the day.
    If year is 2 digits (e.g. 26), maps to 2026.
    Returns: (date_obj, normalized_iso_string, confidence)
    """
    if not date_str or not isinstance(date_str, str):
        return None, None, 0.0

    clean = date_str.strip()
    # Remove ordinal suffixes: 1st, 2nd, 3rd, 14th
    clean_ord = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", clean, flags=re.I)

    # 1. Text Month: "January 14, 2026", "14 January 2026", "Jan 14, 2026", "14-Jan-2026"
    month_regex = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    
    # Month DD, YYYY
    m1 = re.search(rf"\b{month_regex}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", clean_ord, re.I)
    if m1:
        m_name, day, yr = m1.group(1).lower()[:3], int(m1.group(2)), int(m1.group(3))
        m_num = MONTH_NAMES.get(m_name)
        if m_num and 1 <= day <= 31:
            try:
                d = date(yr, m_num, day)
                return d, d.isoformat(), 0.99
            except ValueError:
                pass

    # DD Month YYYY
    m2 = re.search(rf"\b(\d{{1,2}})\s+[-/]?\s*{month_regex}\s+[-/]?\s*(\d{{4}})\b", clean_ord, re.I)
    if m2:
        day, m_name, yr = int(m2.group(1)), m2.group(2).lower()[:3], int(m2.group(3))
        m_num = MONTH_NAMES.get(m_name)
        if m_num and 1 <= day <= 31:
            try:
                d = date(yr, m_num, day)
                return d, d.isoformat(), 0.99
            except ValueError:
                pass

    # 2. ISO Format: YYYY-MM-DD or YYYY/MM/DD
    m_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", clean)
    if m_iso:
        yr, mo, day = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1 <= mo <= 12 and 1 <= day <= 31:
            try:
                d = date(yr, mo, day)
                return d, d.isoformat(), 0.99
            except ValueError:
                pass

    # 3. Numeric formats: MM/DD/YYYY, DD/MM/YYYY, MM-DD-YYYY, DD-MM-YYYY
    m_num = re.search(r"\b(\d{1,2})([/\-\.])(\d{1,2})\2(\d{2,4})\b", clean)
    if m_num:
        p1 = int(m_num.group(1))
        p2 = int(m_num.group(3))
        raw_yr = int(m_num.group(4))
        yr = (2000 + raw_yr) if raw_yr < 100 else raw_yr

        # Disambiguation logic:
        # If p1 > 12 and p2 <= 12: p1 MUST be day, p2 MUST be month (DD/MM/YYYY)
        if p1 > 12 and 1 <= p2 <= 12:
            try:
                d = date(yr, p2, p1)
                return d, d.isoformat(), 0.98
            except ValueError:
                pass

        # If p2 > 12 and p1 <= 12: p2 MUST be day, p1 MUST be month (MM/DD/YYYY)
        if p2 > 12 and 1 <= p1 <= 12:
            try:
                d = date(yr, p1, p2)
                return d, d.isoformat(), 0.98
            except ValueError:
                pass

        # If both <= 12: ambiguous. Use prefer_us_format (MM/DD/YYYY vs DD/MM/YYYY)
        if 1 <= p1 <= 12 and 1 <= p2 <= 12:
            try:
                if prefer_us_format:
                    d = date(yr, p1, p2)
                else:
                    d = date(yr, p2, p1)
                return d, d.isoformat(), 0.85
            except ValueError:
                pass

    return None, None, 0.0


def parse_payment_terms_days(terms_text: str) -> Optional[int]:
    """
    Extract number of days from payment terms string.
    Examples:
    - "DD Net 1 Day" -> 1
    - "DD Net 1" -> 1
    - "Net 30" -> 30
    - "Net 15 Days" -> 15
    - "Net 60" -> 60
    - "1 Day" -> 1
    - "Due in 14 days" -> 14
    - "Due upon receipt" / "Due on receipt" -> 0
    - "Immediate" -> 0
    """
    if not terms_text or not isinstance(terms_text, str):
        return None

    clean = terms_text.strip()

    if re.search(r"\b(due\s+(?:on|upon)\s+receipt|immediate|cash\s+on\s+delivery|cod)\b", clean, re.I):
        return 0

    # Pattern for "DD Net X Day(s)" or "Net X" or "X Days"
    m = re.search(r"(?:net|dd\s+net|terms|due\s+in)?\s*(\d+)\s*(?:days?|d)?\b", clean, re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    return None


def calculate_due_date(
    invoice_date_field: DateField,
    payment_terms: Optional[str],
    explicit_due_date_str: Optional[str] = None
) -> DateField:
    """
    Calculate or resolve the final due date.
    Rules:
    1. If explicit printed due date exists and is valid -> USE PRINTED DUE DATE (source='document', confidence=0.99).
    2. If no explicit due date, but invoice_date and payment_terms exist -> calculate:
       due_date = invoice_date + payment_terms (source='calculated', confidence=0.98).
    3. If neither exists -> due_date = null (source='not_detected').
    Never uses system date.
    """
    # 1. Printed Due Date check
    if explicit_due_date_str:
        # Check if the string is just payment terms rather than an actual calendar date
        terms_days = parse_payment_terms_days(explicit_due_date_str)
        d_obj, iso_str, conf = parse_date_string(explicit_due_date_str)
        if d_obj:
            return DateField(
                value=iso_str,
                raw=explicit_due_date_str.strip(),
                confidence=conf,
                source="document",
                label="Due Date (Printed)",
                date_obj=d_obj
            )

    # 2. Programmatic Calculation from Payment Terms + Invoice Date
    if invoice_date_field.date_obj and payment_terms:
        days = parse_payment_terms_days(payment_terms)
        if days is not None:
            calc_date = invoice_date_field.date_obj + timedelta(days=days)
            return DateField(
                value=calc_date.isoformat(),
                raw=f"{payment_terms} (Calculated from {invoice_date_field.raw or invoice_date_field.value})",
                confidence=0.98,
                source="calculated",
                label="Due Date (Calculated from Terms)",
                date_obj=calc_date
            )

    return DateField(
        value=None,
        raw=None,
        confidence=0.0,
        source="not_detected",
        label="Due Date"
    )
