"""
Document classification — determines document type from content and filename.
Uses a hybrid approach: deterministic rules first, then LLM if uncertain.
Never blindly trusts filename.
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    RESUME = "resume"
    CV = "cv"
    DEGREE_CERTIFICATE = "degree_certificate"
    MARKSHEET = "marksheet"
    EXPERIENCE_LETTER = "experience_letter"
    OFFER_LETTER = "offer_letter"
    APPOINTMENT_LETTER = "appointment_letter"
    INTERNSHIP_CERTIFICATE = "internship_certificate"
    PROFESSIONAL_CERTIFICATE = "professional_certificate"
    TRAINING_CERTIFICATE = "training_certificate"
    ACHIEVEMENT_CERTIFICATE = "achievement_certificate"
    PAYSLIP = "payslip"
    SALARY_SLIP = "salary_slip"
    INVOICE = "invoice"
    BILL = "bill"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    QUOTATION = "quotation"
    ESTIMATE = "estimate"
    DELIVERY_NOTE = "delivery_note"
    CONTRACT = "contract"
    LETTER = "letter"
    FORM = "form"
    FINANCIAL_STATEMENT = "financial_statement"
    BANK_STATEMENT = "bank_statement"
    SPREADSHEET = "spreadsheet"
    BOOK = "book"
    PROJECT_REPORT = "project_report"
    RESEARCH_PAPER = "research_paper"
    PHOTO_DOCUMENT = "photo_document"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"
    OTHER = "other"
    NEEDS_REVIEW = "needs_review"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ClassificationResult:
    document_type: DocumentType
    confidence: ConfidenceLevel
    method: str           # "rules", "llm", "hybrid"
    reasoning: str        # Human-readable explanation
    document_subtype: Optional[str] = None
    confidence_score: float = 0.95


# ─────────────────────────────────────────────────────────────
# Rule-based patterns (deterministic, no AI required)
# ─────────────────────────────────────────────────────────────

# (pattern, document_type, weight)
TEXT_PATTERNS: list[tuple[re.Pattern, DocumentType, int]] = [
    # Resume / CV (Strictly candidate-oriented, no generic 'project' match)
    (re.compile(r"\b(curriculum\s+vitae|CV)\b", re.I), DocumentType.CV, 20),
    (re.compile(r"\b(resume|r[eé]sum[eé]|biodata)\b", re.I), DocumentType.RESUME, 20),
    (re.compile(r"\b(career\s+objective|professional\s+summary|technical\s+skills?|employment\s+history|work\s+experience)\b", re.I), DocumentType.RESUME, 12),
    (re.compile(r"\bObjective\b.{0,100}\b(career|position|employment)\b", re.I | re.S), DocumentType.RESUME, 10),
    (re.compile(r"\bWork\s+Experience\b.{0,200}\bEducation\b", re.I | re.S), DocumentType.RESUME, 15),
    (re.compile(r"\bSkills?\b.{0,200}\bExperience\b.{0,200}\bEducation\b", re.I | re.S), DocumentType.RESUME, 15),

    # Book / Publication / Manual
    (re.compile(r"\b(isbn\s*[:-]?\s*\d|table\s+of\s+contents|published\s+by|publisher|edition|copyright\s+\d{4})\b", re.I), DocumentType.BOOK, 22),
    (re.compile(r"\b(chapter\s+\d+|preface|prologue|epilogue|foreword|acknowledgments)\b", re.I), DocumentType.BOOK, 18),
    (re.compile(r"\b(textbook|handbook|reference\s+guide|user\s+manual|novel)\b", re.I), DocumentType.BOOK, 16),

    # Project Report
    (re.compile(r"\b(project\s+report|final\s+year\s+project|capstone\s+project|problem\s+statement|system\s+architecture)\b", re.I), DocumentType.PROJECT_REPORT, 22),
    (re.compile(r"\b(submitted\s+in\s+partial\s+fulfillment|bachelor\s+of\s+engineering\s+in|guided\s+by|project\s+guide|synopsis)\b", re.I), DocumentType.PROJECT_REPORT, 18),
    (re.compile(r"\b(project\s+objective|scope\s+of\s+the\s+project|hardware\s+requirements|software\s+requirements|system\s+design|implementation\s+details)\b", re.I), DocumentType.PROJECT_REPORT, 16),
    (re.compile(r"\b(project\s+overview|project\s+work|mini\s+project|major\s+project)\b", re.I), DocumentType.PROJECT_REPORT, 12),

    # Research Paper / Conference Paper
    (re.compile(r"\b(abstract|ieee|springer|easychair|acm|elsevier|proceedings|conference|journal|doi:\s*10\.)\b", re.I), DocumentType.RESEARCH_PAPER, 22),
    (re.compile(r"\b(keywords|introduction|related\s+work|methodology|proposed\s+system|experimental\s+results|conclusion|references)\b", re.I), DocumentType.RESEARCH_PAPER, 16),

    # Degree Certificate
    (re.compile(r"\b(bachelor|master|doctor|b\.?tech|m\.?tech|b\.?e|m\.?e|b\.?sc|m\.?sc|ph\.?d|m\.?b\.?a)\b", re.I), DocumentType.DEGREE_CERTIFICATE, 6),
    (re.compile(r"\bdegree\b.{0,100}\b(awarded|conferred|granted|bestowed)\b", re.I | re.S), DocumentType.DEGREE_CERTIFICATE, 16),
    (re.compile(r"\bthis\s+is\s+to\s+certify\b.{0,200}\bdegree\b", re.I | re.S), DocumentType.DEGREE_CERTIFICATE, 14),
    (re.compile(r"\buniversity\b.{0,100}\b(diploma|degree|certificate)\b", re.I | re.S), DocumentType.DEGREE_CERTIFICATE, 8),

    # Marksheet / Transcript
    (re.compile(r"\b(mark\s*sheet|grade\s*sheet|transcript|result\s*sheet)\b", re.I), DocumentType.MARKSHEET, 16),
    (re.compile(r"\b(semester|subject|marks?\s+obtained|grade\s+point)\b.{0,200}\b(total|aggregate|percentage)\b", re.I | re.S), DocumentType.MARKSHEET, 10),
    (re.compile(r"\b(mark\s*sheet|transcript)\b.{0,100}\bCGPA\b", re.I | re.S), DocumentType.MARKSHEET, 8),
    (re.compile(r"\bSGPA\b", re.I), DocumentType.MARKSHEET, 6),

    # Experience Letter
    (re.compile(r"\bexperience\s+(letter|certificate)\b", re.I), DocumentType.EXPERIENCE_LETTER, 28),
    (re.compile(r"\bto\s+whomsoever?\s+it\s+may\s+concern\b", re.I), DocumentType.EXPERIENCE_LETTER, 18),
    (re.compile(r"\b(worked|employed|served)\s+(with|at|in)\b.{0,200}\b(from|since)\b", re.I | re.S), DocumentType.EXPERIENCE_LETTER, 18),
    (re.compile(r"\brelieving\s+letter\b", re.I), DocumentType.EXPERIENCE_LETTER, 24),

    # Purchase Orders
    (re.compile(r"\b(purchase\s+order|p\.?o\.?\s*#|buyer\s*name|po\s+date|deliver\s+to|vendor\s+code)\b", re.I), DocumentType.PURCHASE_ORDER, 26),

    # Quotations & Estimates
    (re.compile(r"\b(quotation|proforma\s+invoice|price\s+quote|estimate\s*#|valid\s+until|validity\s+period)\b", re.I), DocumentType.QUOTATION, 25),

    # Delivery Notes & Shipping Documents
    (re.compile(r"\b(delivery\s+note|packing\s+slip|bill\s+of\s+lading|consignee|waybill|shipping\s+manifest)\b", re.I), DocumentType.DELIVERY_NOTE, 25),

    # Contracts & Agreements
    (re.compile(r"\b(contract|agreement|terms\s+and\s+conditions|hereby\s+agree|parties\s+hereto|effective\s+date|governing\s+law)\b", re.I), DocumentType.CONTRACT, 26),

    # Salary Slips & Payslips
    (re.compile(r"\b(salary\s+slip|payslip|pay\s+stub|earnings\s+statement|net\s+pay|basic\s+pay|provident\s+fund)\b", re.I), DocumentType.SALARY_SLIP, 26),

    # Forms & Applications
    (re.compile(r"\b(application\s+form|registration\s+form|enrollment\s+form|declaration|applicant\s+signature)\b", re.I), DocumentType.FORM, 24),

    # General Business / Professional Letters
    (re.compile(r"\b(dear\s+(?:mr|ms|dr|sir|madam)|to\s+whom\s+it\s+may\s+concern|sincerely|yours\s+faithfully)\b", re.I), DocumentType.LETTER, 14),

    # Corporate Invoice / Billing / Payroll Statement
    (re.compile(r"\b(invoice|tax\s+invoice|bill\s+to|invoice\s*#|invoice\s+no|remit\s+payment\s+to)\b", re.I), DocumentType.INVOICE, 25),
    (re.compile(r"\b(total\s+amount\s+due|amount\s+due|balance\s+due|gross\s+wages|total\s+gross|wire\s+routing|routing\s+number)\b", re.I), DocumentType.INVOICE, 25),
    (re.compile(r"\b(terms\s*:\s*dd\s+net|net\s+\d+\s+days?|due\s+date|payment\s+terms)\b", re.I), DocumentType.INVOICE, 20),
    (re.compile(r"\b(payroll\s+charges|employer\s+fringes|total\s+fringe|payroll\s+total)\b", re.I), DocumentType.INVOICE, 22),

    # Receipts & Point of Sale (POS)
    (re.compile(r"\b(receipt|sales\s+receipt|pos\s+receipt|terminal\s*#|merchant|cashier|subtotal|sales\s+tax|tip\s*[$€£₹\d]|gratuity)\b", re.I), DocumentType.RECEIPT, 25),
    (re.compile(r"\b(store\s*#|register\s*#|item\s+count|order\s*#|customer\s+receipt|visa\s+ending|mastercard\s+ending|amex\s+ending)\b", re.I), DocumentType.RECEIPT, 20),

    # Financial Statements / Bank Statements / Monthly Transactions
    (re.compile(r"\b(bank\s+statement|account\s+statement|monthly\s+statement|statement\s+period|period\s+covered)\b", re.I), DocumentType.FINANCIAL_STATEMENT, 26),
    (re.compile(r"\b(opening\s+balance|closing\s+balance|beginning\s+balance|ending\s+balance|previous\s+balance|new\s+balance)\b", re.I), DocumentType.FINANCIAL_STATEMENT, 25),
    (re.compile(r"\b(total\s+deposits|total\s+withdrawals|total\s+credits|total\s+debits|checks\s+paid|daily\s+ledger)\b", re.I), DocumentType.FINANCIAL_STATEMENT, 22),

    # Spreadsheets / Excel Models
    (re.compile(r"\b(sheet\s*:\s*|calculated\s+totals|csv_data|total\s+debits?|total\s+credits?|grand\s+total)\b", re.I), DocumentType.SPREADSHEET, 24),

    # Offer Letter
    (re.compile(r"\boffer\s+letter\b", re.I), DocumentType.OFFER_LETTER, 14),
    (re.compile(r"\bwe\s+(are\s+pleased|take\s+pleasure)\s+to\s+offer\b", re.I), DocumentType.OFFER_LETTER, 12),
    (re.compile(r"\bjoining\s+(date|bonus)\b", re.I), DocumentType.OFFER_LETTER, 8),
    (re.compile(r"\bcompensation\s+package\b", re.I), DocumentType.OFFER_LETTER, 8),

    # Appointment Letter
    (re.compile(r"\bappointment\s+letter\b", re.I), DocumentType.APPOINTMENT_LETTER, 14),
    (re.compile(r"\bappointed\s+(as|to\s+the\s+post)\b", re.I), DocumentType.APPOINTMENT_LETTER, 10),

    # Internship Certificate
    (re.compile(r"\binternship\s+(certificate|letter|completion)\b", re.I), DocumentType.INTERNSHIP_CERTIFICATE, 14),
    (re.compile(r"\binternal\s+trainee\b", re.I), DocumentType.INTERNSHIP_CERTIFICATE, 8),
    (re.compile(r"\bintern\b.{0,100}\b(successfully\s+completed|worked)\b", re.I | re.S), DocumentType.INTERNSHIP_CERTIFICATE, 10),

    # Professional / Training / Achievement Certificates
    (re.compile(r"\b(certified|certification)\b.{0,100}\b(professional|associate|expert)\b", re.I | re.S), DocumentType.PROFESSIONAL_CERTIFICATE, 10),
    (re.compile(r"\baws\s+certified|microsoft\s+certified|google\s+cloud\s+certified|cisco\s+certified\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 12),
    (re.compile(r"\btraining\s+(certificate|program|completion)\b", re.I), DocumentType.TRAINING_CERTIFICATE, 10),
    # Universal Certificate patterns (require specific non-work certificate context)
    (re.compile(r"\b(certificate\s+of\s+(completion|achievement|appreciation|participation|excellence|merit|attendance|recognition))\b", re.I), DocumentType.ACHIEVEMENT_CERTIFICATE, 25),
    (re.compile(r"\b(is\s+hereby\s+awarded\s+to|presented\s+to|certifies\s+that)\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 20),
    (re.compile(r"\bthis\s+is\s+to\s+certify\s+that\b(?!.*worked)", re.I | re.S), DocumentType.PROFESSIONAL_CERTIFICATE, 15),
    (re.compile(r"\b(successfully\s+completed\s+(the\s+course|training|internship|program))\b", re.I), DocumentType.TRAINING_CERTIFICATE, 20),
    (re.compile(r"\b(certificate\s+id|credential\s+id|verification\s+code|certificate\s+no|cert\s*#)\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 15),
    (re.compile(r"\b(udemy|coursera|edx|linkedin\s+learning|nptel|scaler|great\s+learning|simplilearn)\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 18),
]

# Filename hints
FILENAME_HINTS: list[tuple[re.Pattern, DocumentType, int]] = [
    (re.compile(r"\b(resume|cv|biodata)\b", re.I), DocumentType.RESUME, 30),
    (re.compile(r"\b(invoice|bill|statement|payroll)\b", re.I), DocumentType.INVOICE, 30),
    (re.compile(r"\b(receipt|sales_receipt|pos_slip|expense_receipt)\b", re.I), DocumentType.RECEIPT, 30),
    (re.compile(r"\b(bank_stmt|bank_statement|account_stmt|monthly_txn|ledger)\b", re.I), DocumentType.FINANCIAL_STATEMENT, 30),
    (re.compile(r"\.(xlsx|xls|csv)$", re.I), DocumentType.SPREADSHEET, 35),
    (re.compile(r"\b(book|textbook|handbook|manual|guide|ebook|novel)\b", re.I), DocumentType.BOOK, 25),
    (re.compile(r"\b(project|report|capstone|thesis|synopsis)\b", re.I), DocumentType.PROJECT_REPORT, 25),
    (re.compile(r"\b(paper|ieee|icccnt|conference|journal|publication)\b", re.I), DocumentType.RESEARCH_PAPER, 25),
    (re.compile(r"\bdegree\b", re.I), DocumentType.DEGREE_CERTIFICATE, 18),
    (re.compile(r"\bmark.?sheet\b", re.I), DocumentType.MARKSHEET, 18),
    (re.compile(r"\bexperience\b", re.I), DocumentType.EXPERIENCE_LETTER, 18),
    (re.compile(r"\boffer\b", re.I), DocumentType.OFFER_LETTER, 18),
    (re.compile(r"\bappointment\b", re.I), DocumentType.APPOINTMENT_LETTER, 18),
    (re.compile(r"\binternship\b", re.I), DocumentType.INTERNSHIP_CERTIFICATE, 18),
    (re.compile(r"\b(certif|course_complete|completion|award|credential)\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 25),
    (re.compile(r"\b(scan|photo|screenshot|img|snapshot)\b", re.I), DocumentType.PHOTO_DOCUMENT, 18),
]


def classify_document(
    text: str,
    original_filename: str = "",
    use_llm: bool = False,
) -> ClassificationResult:
    """
    Classify a document using rule-based analysis.
    Falls back to NEEDS_REVIEW if insufficient signal.

    Args:
        text: Extracted text from the document
        original_filename: Original filename (used as weak hint only)
        use_llm: Whether to use LLM for uncertain cases (Phase 8)
    """
    scores: dict[DocumentType, int] = {}

    # Score from text patterns
    for pattern, doc_type, weight in TEXT_PATTERNS:
        if pattern.search(text):
            scores[doc_type] = scores.get(doc_type, 0) + weight

    # Score from filename hints (weaker signal)
    stem = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
    for pattern, doc_type, weight in FILENAME_HINTS:
        if pattern.search(stem):
            scores[doc_type] = scores.get(doc_type, 0) + weight

    ext = original_filename.lower().rsplit(".", 1)[-1] if "." in original_filename else ""
    if ext in ("mp3", "wav", "m4a", "aac", "ogg"):
        return ClassificationResult(
            document_type=DocumentType.AUDIO,
            confidence=ConfidenceLevel.HIGH,
            method="rules",
            reasoning=f"Audio media container (.{ext}).",
        )
    if ext in ("mp4", "mov", "avi", "mkv", "webm"):
        return ClassificationResult(
            document_type=DocumentType.VIDEO,
            confidence=ConfidenceLevel.HIGH,
            method="rules",
            reasoning=f"Video media container (.{ext}).",
        )

    if ext in ("png", "jpg", "jpeg", "webp", "bmp"):
        # Check if there are strong signals for specific types (like certificate, marksheet, resume)
        certificate_types = {
            DocumentType.DEGREE_CERTIFICATE,
            DocumentType.PROFESSIONAL_CERTIFICATE,
            DocumentType.TRAINING_CERTIFICATE,
            DocumentType.ACHIEVEMENT_CERTIFICATE,
            DocumentType.INTERNSHIP_CERTIFICATE,
            DocumentType.MARKSHEET,
            DocumentType.EXPERIENCE_LETTER,
            DocumentType.RESUME,
            DocumentType.CV,
        }
        has_specific_signal = any(scores.get(t, 0) >= 12 for t in certificate_types)

        if not has_specific_signal:
            # If no strong certificate/resume signal, classify as photo/scanned document
            if not scores or scores.get(DocumentType.PHOTO_DOCUMENT, 0) > 0 or max(scores.values()) < 12:
                return ClassificationResult(
                    document_type=DocumentType.PHOTO_DOCUMENT,
                    confidence=ConfidenceLevel.HIGH if scores else ConfidenceLevel.MEDIUM,
                    method="rules",
                    reasoning="Classified as photo/scanned document based on visual image container.",
                )

    if not scores:
        return ClassificationResult(
            document_type=DocumentType.NEEDS_REVIEW,
            confidence=ConfidenceLevel.LOW,
            method="rules",
            reasoning="No classification signals found in text or filename.",
        )

    # Get top candidate
    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]
    total_score = sum(scores.values())

    # Determine confidence
    dominance = best_score / total_score if total_score > 0 else 0

    if best_score >= 10 and dominance >= 0.5:
        confidence = ConfidenceLevel.HIGH
        conf_score = 0.95
    elif best_score >= 4:
        confidence = ConfidenceLevel.MEDIUM
        conf_score = 0.80
    else:
        confidence = ConfidenceLevel.LOW
        conf_score = 0.50

    # Determine document subtype
    text_lower = text.lower()
    subtype: Optional[str] = None
    if best_type == DocumentType.INVOICE:
        if any(k in text_lower for k in ["payroll", "fringe", "gross wages", "total gross"]):
            subtype = "payroll_billing"
        elif any(k in text_lower for k in ["tax invoice", "gst", "vat"]):
            subtype = "tax_invoice"
        else:
            subtype = "commercial_invoice"
    elif best_type == DocumentType.RECEIPT:
        subtype = "pos_receipt" if "terminal" in text_lower or "cashier" in text_lower else "sales_receipt"
    elif best_type in (DocumentType.FINANCIAL_STATEMENT, DocumentType.BANK_STATEMENT):
        subtype = "bank_account_statement"
    elif best_type == DocumentType.PURCHASE_ORDER:
        subtype = "standard_purchase_order"
    elif best_type == DocumentType.CONTRACT:
        subtype = "legal_agreement"
    elif best_type in (DocumentType.RESUME, DocumentType.CV):
        subtype = "curriculum_vitae" if "curriculum vitae" in text_lower or "cv" in text_lower else "professional_resume"
    elif best_type == DocumentType.DEGREE_CERTIFICATE:
        subtype = "academic_degree"
    elif best_type in (DocumentType.PROFESSIONAL_CERTIFICATE, DocumentType.TRAINING_CERTIFICATE):
        subtype = "course_completion_credential"
    elif best_type == DocumentType.RESEARCH_PAPER:
        subtype = "conference_or_journal_paper"
    elif best_type == DocumentType.PROJECT_REPORT:
        subtype = "academic_or_engineering_report"

    # If confidence is low, do not force an incorrect category (Requirement 3)
    final_type = best_type
    if confidence == ConfidenceLevel.LOW:
        if not text.strip():
            final_type = DocumentType.NEEDS_REVIEW
        else:
            final_type = DocumentType.UNKNOWN

    logger.info(
        f"Classified '{original_filename}' as {final_type.value} "
        f"(subtype={subtype}, score={best_score}, confidence={confidence.value})"
    )

    return ClassificationResult(
        document_type=final_type,
        confidence=confidence,
        method="rules",
        reasoning=f"Score: {best_score}/{total_score}. Dominant signals matched {best_type.value} pattern.",
        document_subtype=subtype,
        confidence_score=conf_score,
    )
