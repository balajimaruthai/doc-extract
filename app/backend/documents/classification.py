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
    BOOK = "book"
    PROJECT_REPORT = "project_report"
    RESEARCH_PAPER = "research_paper"
    PHOTO_DOCUMENT = "photo_document"
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
    (re.compile(r"\bexperience\s+(letter|certificate)\b", re.I), DocumentType.EXPERIENCE_LETTER, 14),
    (re.compile(r"\bto\s+whomsoever?\s+it\s+may\s+concern\b", re.I), DocumentType.EXPERIENCE_LETTER, 8),
    (re.compile(r"\b(worked|employed|served)\s+(with|at|in)\b.{0,200}\b(from|since)\b", re.I | re.S), DocumentType.EXPERIENCE_LETTER, 8),
    (re.compile(r"\brelieving\s+letter\b", re.I), DocumentType.EXPERIENCE_LETTER, 12),

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
    (re.compile(r"\b(award|achievement|recognition|excellence)\b.{0,100}\bcertificate\b", re.I | re.S), DocumentType.ACHIEVEMENT_CERTIFICATE, 10),
]

# Filename hints
FILENAME_HINTS: list[tuple[re.Pattern, DocumentType, int]] = [
    (re.compile(r"\b(resume|cv|biodata)\b", re.I), DocumentType.RESUME, 30),
    (re.compile(r"\b(book|textbook|handbook|manual|guide|ebook|novel)\b", re.I), DocumentType.BOOK, 25),
    (re.compile(r"\b(project|report|capstone|thesis|synopsis)\b", re.I), DocumentType.PROJECT_REPORT, 25),
    (re.compile(r"\b(paper|ieee|icccnt|conference|journal|publication)\b", re.I), DocumentType.RESEARCH_PAPER, 25),
    (re.compile(r"\bdegree\b", re.I), DocumentType.DEGREE_CERTIFICATE, 18),
    (re.compile(r"\bmark.?sheet\b", re.I), DocumentType.MARKSHEET, 18),
    (re.compile(r"\bexperience\b", re.I), DocumentType.EXPERIENCE_LETTER, 18),
    (re.compile(r"\boffer\b", re.I), DocumentType.OFFER_LETTER, 18),
    (re.compile(r"\bappointment\b", re.I), DocumentType.APPOINTMENT_LETTER, 18),
    (re.compile(r"\binternship\b", re.I), DocumentType.INTERNSHIP_CERTIFICATE, 18),
    (re.compile(r"\bcertif\b", re.I), DocumentType.PROFESSIONAL_CERTIFICATE, 18),
    (re.compile(r"\b(scan|photo|screenshot|img|snapshot)\b", re.I), DocumentType.PHOTO_DOCUMENT, 18),
]


def classify_document(
    text: str,
    original_filename: str,
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
    if ext in ("png", "jpg", "jpeg", "webp", "bmp"):
        # If no explicit resume or paper or book signal, classify as photo/scanned document
        if not scores or scores.get(DocumentType.PHOTO_DOCUMENT, 0) > 0 or max(scores.values()) < 15:
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
    elif best_score >= 4:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    logger.info(
        f"Classified '{original_filename}' as {best_type.value} "
        f"(score={best_score}, confidence={confidence.value})"
    )

    return ClassificationResult(
        document_type=best_type,
        confidence=confidence,
        method="rules",
        reasoning=f"Score: {best_score}/{total_score}. Dominant signals matched {best_type.value} pattern.",
    )
