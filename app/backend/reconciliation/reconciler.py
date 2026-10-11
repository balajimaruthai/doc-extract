"""
Multi-document reconciliation — merges information from multiple documents,
detects conflicts, calculates experience deterministically.
"""
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConflictRecord:
    id: str
    field_name: str
    value_a: str
    source_a_doc_id: str
    source_a_page: int
    value_b: str
    source_b_doc_id: str
    source_b_page: int


@dataclass
class EmploymentPeriod:
    company: str
    designation: str
    start_date: Optional[date]
    end_date: Optional[date]
    is_current: bool
    source_doc_id: str
    source_page: int


@dataclass
class ReconciliationResult:
    """Output of the reconciliation process."""
    # Winning values (after conflict resolution)
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    date_of_birth: Optional[str] = None
    professional_summary: Optional[str] = None

    # Merged collections
    education: list[dict] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    skills: dict = field(default_factory=dict)
    certifications: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    achievements: list[dict] = field(default_factory=list)

    # Experience calculation
    total_experience_months: int = 0
    experience_breakdown: list[dict] = field(default_factory=list)
    estimated_level: Optional[str] = None
    estimated_level_basis: Optional[str] = None

    # Conflicts detected
    conflicts: list[ConflictRecord] = field(default_factory=list)

    # Evidence map: field → list of (doc_id, page, snippet)
    evidence: dict[str, list[dict]] = field(default_factory=dict)


def reconcile(
    extractions: list[dict],  # List of {doc_id, doc_name, page, result: ExtractionResult}
) -> ReconciliationResult:
    """
    Merge extraction results from multiple documents.

    Strategy:
    - Personal fields: first non-null wins; conflicts recorded
    - Education: deduplicate by (degree, institution), keep all unique
    - Experience: deduplicate by (company, designation, dates)
    - Skills: union of all skill sets
    - Certifications: deduplicate by (name, issuer)
    - Calculate experience deterministically from employment periods
    """
    result = ReconciliationResult()

    if not extractions:
        return result

    # ── Personal Information ──────────────────────────────────
    _merge_personal_fields(extractions, result)

    # ── Education ────────────────────────────────────────────
    _merge_education(extractions, result)

    # ── Experience ───────────────────────────────────────────
    _merge_experience(extractions, result)

    # ── Skills ───────────────────────────────────────────────
    _merge_skills(extractions, result)

    # ── Certifications ───────────────────────────────────────
    _merge_certifications(extractions, result)

    # ── Projects / Achievements ──────────────────────────────
    _merge_projects(extractions, result)
    _merge_achievements(extractions, result)

    # ── Experience Calculation ───────────────────────────────
    _calculate_experience(result)

    logger.info(
        f"Reconciliation complete: "
        f"{len(result.education)} education, "
        f"{len(result.experience)} experience, "
        f"{len(result.conflicts)} conflicts, "
        f"{result.total_experience_months} months experience"
    )

    return result


# ─────────────────────────────────────────────────────────────
# Merge helpers
# ─────────────────────────────────────────────────────────────

def _merge_personal_fields(extractions: list[dict], result: ReconciliationResult) -> None:
    """Merge personal fields — detect conflicts between documents."""
    fields_to_merge = ["name", "email", "phone", "location", "date_of_birth"]
    field_sources: dict[str, dict] = {}   # field → {value, doc_id, page}

    for ex in extractions:
        personal = ex["result"].personal
        doc_id = ex["doc_id"]
        doc_name = ex["doc_name"]
        page = ex.get("page", 1)

        for fname in fields_to_merge:
            val = getattr(personal, fname, None)
            if not val:
                continue

            if fname not in field_sources:
                # First value seen — adopt it
                field_sources[fname] = {
                    "value": val,
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "page": page,
                }
                # Add to evidence
                _add_evidence(result, f"personal.{fname}", val, doc_id, page)
            else:
                # Compare with existing value
                existing = field_sources[fname]["value"]
                if _values_differ(existing, val):
                    # Conflict detected
                    conflict = ConflictRecord(
                        id=str(uuid.uuid4()),
                        field_name=f"personal.{fname}",
                        value_a=existing,
                        source_a_doc_id=field_sources[fname]["doc_id"],
                        source_a_page=field_sources[fname]["page"],
                        value_b=val,
                        source_b_doc_id=doc_id,
                        source_b_page=page,
                    )
                    result.conflicts.append(conflict)
                    logger.warning(
                        f"CONFLICT: {fname} — "
                        f"'{existing}' ({field_sources[fname]['doc_name']}) "
                        f"vs '{val}' ({doc_name})"
                    )
                else:
                    # Same value from different sources — add to evidence
                    _add_evidence(result, f"personal.{fname}", val, doc_id, page)

    # Set final values from first source (conflicts flagged for user)
    result.full_name = field_sources.get("name", {}).get("value")
    result.email = field_sources.get("email", {}).get("value")
    result.phone = field_sources.get("phone", {}).get("value")
    result.location = field_sources.get("location", {}).get("value")
    result.date_of_birth = field_sources.get("date_of_birth", {}).get("value")

    # Professional summary — prefer longest non-null
    summaries = [
        (ex["result"].professional_summary, ex["doc_id"])
        for ex in extractions
        if ex["result"].professional_summary
    ]
    if summaries:
        result.professional_summary = max(summaries, key=lambda s: len(s[0]))[0]


def _merge_education(extractions: list[dict], result: ReconciliationResult) -> None:
    """Merge education entries — deduplicate by (degree, institution)."""
    seen_keys: set[str] = set()

    for ex in extractions:
        doc_id = ex["doc_id"]
        page = ex.get("page", 1)

        for edu in ex["result"].education:
            key = _edu_key(edu)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            entry = edu.model_dump()
            entry["source_document_id"] = doc_id
            entry["source_page"] = page
            result.education.append(entry)

            _add_evidence(
                result,
                f"education.{edu.degree or 'unknown'}",
                f"{edu.degree} from {edu.institution}",
                doc_id, page
            )


def _merge_experience(extractions: list[dict], result: ReconciliationResult) -> None:
    """Merge experience entries — deduplicate by (company, designation, start_date)."""
    seen_keys: set[str] = set()

    for ex in extractions:
        doc_id = ex["doc_id"]
        page = ex.get("page", 1)

        for exp in ex["result"].experience:
            key = _exp_key(exp)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            entry = exp.model_dump()
            entry["source_document_id"] = doc_id
            entry["source_page"] = page
            result.experience.append(entry)


def _merge_skills(extractions: list[dict], result: ReconciliationResult) -> None:
    """Union all skill sets across documents."""
    merged: dict[str, set[str]] = {
        "programming_languages": set(),
        "frameworks": set(),
        "libraries": set(),
        "databases": set(),
        "cloud": set(),
        "tools": set(),
        "domain_skills": set(),
        "soft_skills": set(),
    }

    for ex in extractions:
        skills = ex["result"].skills
        for category in merged:
            items = getattr(skills, category, []) or []
            for item in items:
                if item and len(item.strip()) > 1:
                    merged[category].add(item.strip())

    result.skills = {k: sorted(v) for k, v in merged.items()}


def _merge_certifications(extractions: list[dict], result: ReconciliationResult) -> None:
    """Merge certifications — deduplicate by (name, issuer)."""
    seen_keys: set[str] = set()

    for ex in extractions:
        doc_id = ex["doc_id"]
        page = ex.get("page", 1)

        for cert in ex["result"].certifications:
            key = f"{(cert.name or '').lower()}|{(cert.issuer or '').lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            entry = cert.model_dump()
            entry["source_document_id"] = doc_id
            entry["source_page"] = page
            result.certifications.append(entry)


def _merge_projects(extractions: list[dict], result: ReconciliationResult) -> None:
    seen_names: set[str] = set()
    for ex in extractions:
        doc_id = ex["doc_id"]
        page = ex.get("page", 1)
        for proj in ex["result"].projects:
            key = (proj.name or "").lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            entry = proj.model_dump()
            entry["source_document_id"] = doc_id
            entry["source_page"] = page
            result.projects.append(entry)


def _merge_achievements(extractions: list[dict], result: ReconciliationResult) -> None:
    seen: set[str] = set()
    for ex in extractions:
        doc_id = ex["doc_id"]
        page = ex.get("page", 1)
        for ach in ex["result"].achievements:
            key = (ach.title or "").lower()
            if key in seen:
                continue
            seen.add(key)
            entry = ach.model_dump()
            entry["source_document_id"] = doc_id
            entry["source_page"] = page
            result.achievements.append(entry)


# ─────────────────────────────────────────────────────────────
# Deterministic experience calculation
# ─────────────────────────────────────────────────────────────

def _calculate_experience(result: ReconciliationResult) -> None:
    """
    Calculate total professional experience from employment records.
    Handles overlapping periods correctly (no double-counting).
    Uses actual dates — does NOT ask LLM to estimate experience.
    """
    periods: list[tuple[date, date]] = []
    breakdown: list[dict] = []
    today = date.today()

    for exp in result.experience:
        start = _parse_date_flexible(exp.get("start_date"))
        is_current = exp.get("is_current", False)

        if is_current:
            end = today
        else:
            end = _parse_date_flexible(exp.get("end_date"))

        if start is None:
            continue

        if end is None:
            end = today  # Assume ongoing if no end date

        if end < start:
            logger.warning(f"Experience period end before start — skipping: {exp}")
            continue

        periods.append((start, end))
        duration_months = _months_between(start, end)
        exp["duration_months"] = duration_months

        breakdown.append({
            "company": exp.get("company", "Unknown"),
            "designation": exp.get("designation", ""),
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if not is_current else "Present",
            "duration_months": duration_months,
        })

    # Merge overlapping periods to avoid double-counting
    total_months = _calculate_non_overlapping_months(periods)

    result.total_experience_months = total_months
    result.experience_breakdown = breakdown

    # Estimate level
    result.estimated_level, result.estimated_level_basis = _estimate_level(
        total_months, result
    )

    logger.info(
        f"Experience: {total_months} months total "
        f"({len(periods)} positions, overlap-corrected)"
    )


def _calculate_non_overlapping_months(periods: list[tuple[date, date]]) -> int:
    """
    Calculate total months across employment periods,
    merging overlapping intervals to avoid double-counting.
    """
    if not periods:
        return 0

    # Sort by start date
    sorted_periods = sorted(periods, key=lambda p: p[0])

    # Merge overlapping intervals
    merged: list[tuple[date, date]] = [sorted_periods[0]]

    for start, end in sorted_periods[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Overlapping — extend
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    # Calculate total months
    total = sum(_months_between(s, e) for s, e in merged)
    return total


def _months_between(start: date, end: date) -> int:
    """Calculate number of complete months between two dates."""
    return (end.year - start.year) * 12 + (end.month - start.month)


def _parse_date_flexible(date_str: Optional[str]) -> Optional[date]:
    """
    Parse various date string formats into a date object.
    Supports: YYYY-MM-DD, YYYY-MM, YYYY, "Jan 2022", "January 2022", etc.
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try ISO formats
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.date()
        except ValueError:
            pass

    # Try "Month YYYY" or "MMM YYYY"
    month_patterns = [
        r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})",
        r"(?P<year>\d{4})\s+(?P<month>[A-Za-z]+)",
    ]

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }

    for pattern in month_patterns:
        match = re.search(pattern, date_str)
        if match:
            month_str = match.group("month").lower()
            year_str = match.group("year")
            month_num = month_map.get(month_str)
            if month_num:
                try:
                    return date(int(year_str), month_num, 1)
                except ValueError:
                    pass

    # Try extracting just a year
    year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
    if year_match:
        try:
            return date(int(year_match.group(0)), 1, 1)
        except ValueError:
            pass

    return None


def _estimate_level(months: int, result: ReconciliationResult) -> tuple[str, str]:
    """
    Estimate professional level from documented experience.
    This is an ESTIMATE — presented as such in the UI.
    """
    if months == 0:
        # Check if there's any education to distinguish student vs fresher
        if result.education:
            return "Fresher", "No professional experience found. Has documented education."
        return "Student", "No professional experience or completed education found."

    years = months / 12

    if years < 0.5:
        level = "Fresher"
        basis = f"Less than 6 months of documented experience ({months} months)."
    elif years < 2:
        level = "Entry Level"
        basis = f"Approximately {years:.1f} years of documented professional experience."
    elif years < 4:
        level = "Junior"
        basis = f"Approximately {years:.1f} years of documented professional experience."
    elif years < 7:
        level = "Mid Level"
        basis = f"Approximately {years:.1f} years of documented professional experience."
    elif years < 12:
        level = "Senior"
        basis = f"Approximately {years:.1f} years of documented professional experience."
    else:
        level = "Lead / Manager"
        basis = f"Over {years:.0f} years of documented professional experience."

    return level, basis


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _edu_key(edu) -> str:
    degree = (edu.degree or "").lower().strip()
    institution = (edu.institution or "").lower().strip()
    return f"{degree}|{institution}"


def _exp_key(exp) -> str:
    company = (exp.company or "").lower().strip()
    designation = (exp.designation or "").lower().strip()
    start = (exp.start_date or "").lower().strip()
    return f"{company}|{designation}|{start}"


def _values_differ(a: str, b: str) -> bool:
    """Check if two field values are meaningfully different."""
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    if a_norm == b_norm:
        return False
    # Allow for minor differences (e.g., trailing periods, spaces)
    a_clean = re.sub(r"[^a-z0-9@.]", "", a_norm)
    b_clean = re.sub(r"[^a-z0-9@.]", "", b_norm)
    return a_clean != b_clean


def _add_evidence(
    result: ReconciliationResult,
    field_name: str,
    value: str,
    doc_id: str,
    page: int,
) -> None:
    """Add an evidence entry to the result."""
    if field_name not in result.evidence:
        result.evidence[field_name] = []
    result.evidence[field_name].append({
        "doc_id": doc_id,
        "page": page,
        "value": value,
    })
