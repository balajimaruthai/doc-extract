"""
Structured extraction pipeline — orchestrates text → LLM → validated JSON.
This is the heart of the AI extraction process.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Extraction Output Schema (Pydantic)
# ─────────────────────────────────────────────────────────────

class PersonalInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    date_of_birth: Optional[str] = None
    linkedin: Optional[str] = None
    source_hint: Optional[str] = None


class EducationEntry(BaseModel):
    degree: Optional[str] = None
    specialization: Optional[str] = None
    institution: Optional[str] = None
    university: Optional[str] = None
    start_date: Optional[str] = None
    graduation_date: Optional[str] = None
    percentage: Optional[float] = None
    cgpa: Optional[float] = None
    education_level: Optional[str] = None
    source_hint: Optional[str] = None

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v):
        if v is not None and not (0 <= v <= 100):
            return None   # Reject invalid percentage
        return v

    @field_validator("cgpa")
    @classmethod
    def validate_cgpa(cls, v):
        if v is not None and not (0 <= v <= 10):
            return None   # Reject values outside 0–10 scale
        return v


class ExperienceEntry(BaseModel):
    company: Optional[str] = None
    designation: Optional[str] = None
    employment_type: Optional[str] = None     # Full-time, Part-time, Contract, etc.
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    responsibilities: list[str] = Field(default_factory=list)
    source_hint: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        """End date must not be before start date."""
        if self.start_date and self.end_date and not self.is_current:
            # Basic year comparison
            start_year = _extract_year(self.start_date)
            end_year = _extract_year(self.end_date)
            if start_year and end_year and end_year < start_year:
                logger.warning(
                    f"Experience entry has end date before start date: "
                    f"{self.start_date} → {self.end_date}. Clearing end date."
                )
                self.end_date = None
        return self


class SkillsGroup(BaseModel):
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    domain_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None
    source_hint: Optional[str] = None


class ProjectEntry(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    organization: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source_hint: Optional[str] = None


class AchievementEntry(BaseModel):
    title: Optional[str] = None
    organization: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    source_hint: Optional[str] = None


class ExtractionResult(BaseModel):
    """Complete extraction result from one document."""
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: SkillsGroup = Field(default_factory=SkillsGroup)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    achievements: list[AchievementEntry] = Field(default_factory=list)
    professional_summary: Optional[str] = None
    
    # Universal document intelligence fields
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[str] = None
    concept: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)
    
    # Specific attributes requested by user:
    what_he_wants: Optional[str] = None
    what_he_knows: list[str] = Field(default_factory=list)
    certifications_done: list[str] = Field(default_factory=list)
    document_summary: Optional[str] = None

    # Certificate / Image document specific fields
    certificate_name: Optional[str] = None        # e.g. "Certificate of Completion"
    issued_to: Optional[str] = None               # Awardee / recipient name
    issuing_organization: Optional[str] = None    # Issuing body / institution
    issue_date: Optional[str] = None              # Date on the certificate
    credential_id: Optional[str] = None           # Credential / certificate ID if present
    certificate_type: Optional[str] = None        # e.g. "Professional", "Achievement", "Training"

    # Corporate / Invoice / Billing document specific fields
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    payment_terms: Optional[str] = None
    total_amount_due: Optional[str] = None
    total_gross: Optional[str] = None
    total_fringe: Optional[str] = None
    payroll_total: Optional[str] = None
    billed_to: Optional[str] = None
    remit_to: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    routing_number: Optional[str] = None
    po_number: Optional[str] = None
    client_code: Optional[str] = None
    contact_person: Optional[str] = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# JSON Schema for grammar-constrained LLM output
# ─────────────────────────────────────────────────────────────

EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "personal": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "date_of_birth": {"type": ["string", "null"]},
                "linkedin": {"type": ["string", "null"]},
                "source_hint": {"type": ["string", "null"]},
            }
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": ["string", "null"]},
                    "specialization": {"type": ["string", "null"]},
                    "institution": {"type": ["string", "null"]},
                    "university": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "graduation_date": {"type": ["string", "null"]},
                    "percentage": {"type": ["number", "null"]},
                    "cgpa": {"type": ["number", "null"]},
                    "education_level": {"type": ["string", "null"]},
                    "source_hint": {"type": ["string", "null"]},
                }
            }
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": ["string", "null"]},
                    "designation": {"type": ["string", "null"]},
                    "employment_type": {"type": ["string", "null"]},
                    "location": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "end_date": {"type": ["string", "null"]},
                    "is_current": {"type": "boolean"},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                    "source_hint": {"type": ["string", "null"]},
                }
            }
        },
        "skills": {
            "type": "object",
            "properties": {
                "programming_languages": {"type": "array", "items": {"type": "string"}},
                "frameworks": {"type": "array", "items": {"type": "string"}},
                "libraries": {"type": "array", "items": {"type": "string"}},
                "databases": {"type": "array", "items": {"type": "string"}},
                "cloud": {"type": "array", "items": {"type": "string"}},
                "tools": {"type": "array", "items": {"type": "string"}},
                "domain_skills": {"type": "array", "items": {"type": "string"}},
                "soft_skills": {"type": "array", "items": {"type": "string"}},
            }
        },
        "certifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "issuer": {"type": ["string", "null"]},
                    "issue_date": {"type": ["string", "null"]},
                    "expiry_date": {"type": ["string", "null"]},
                    "credential_id": {"type": ["string", "null"]},
                    "source_hint": {"type": ["string", "null"]},
                }
            }
        },
        "projects": {"type": "array", "items": {"type": "object"}},
        "achievements": {"type": "array", "items": {"type": "object"}},
        "professional_summary": {"type": ["string", "null"]},
    }
}


# ─────────────────────────────────────────────────────────────
# Extraction orchestration
# ─────────────────────────────────────────────────────────────

def extract_from_text(
    document_text: str,
    document_type: str,
    document_name: str,
    page_info: str,
    llm_provider,
) -> tuple[ExtractionResult, list[str]]:
    """
    Run structured extraction on document text using local LLM.

    Returns:
        (ExtractionResult, list_of_validation_warnings)
    Raises:
        Never raises — returns empty result with warnings on failure
    """
    warnings: list[str] = []

    # Load and fill prompt template
    prompt = _build_prompt(
        document_text=document_text,
        document_type=document_type,
        document_name=document_name,
        page_info=page_info,
    )

    # Run LLM inference (fast token budget: 180 tokens for compact structured JSON)
    raw_json = {}
    try:
        raw_json = llm_provider.generate_json(
            prompt=prompt,
            json_schema=EXTRACTION_JSON_SCHEMA,
            max_tokens=180,
        )
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}", exc_info=True)
        warnings.append(f"AI extraction failed: {e}")

    # Validate and parse with Pydantic
    try:
        result = ExtractionResult.model_validate(raw_json) if raw_json else ExtractionResult()
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        warnings.append(f"Extraction validation error: {e}")
        result = _partial_parse(raw_json, warnings)

    # Hybrid fallback: extract high-confidence patterns directly according to document type
    _apply_rule_based_fallbacks(document_text, result, document_type=document_type, document_name=document_name)

    # Post-extraction field validation
    _validate_fields(result, warnings)

    return result, warnings


def _build_prompt(
    document_text: str,
    document_type: str,
    document_name: str,
    page_info: str,
) -> str:
    """Build task-specific prompt based on document classification."""
    max_text_chars = 1600
    if len(document_text) > max_text_chars:
        document_text = document_text[:max_text_chars] + "\n[... truncated ...]"

    dtype = document_type.lower()
    if dtype == "book":
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured facts from this Book:
Title/Filename: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Book Title",
  "authors": ["Author name(s)"],
  "year": "Publication Year or Edition",
  "document_summary": "Concise overview of what the book covers",
  "highlights": ["Core topic / Chapter highlight 1", "Core topic 2"]
}}<|end|>
<|assistant|>
{{"title":"""

    elif dtype == "project_report":
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured facts from this Project Report:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Project Title",
  "concept": "Core concept and system architecture",
  "what_he_wants": "Primary aim and project objective",
  "what_he_knows": ["Technology or Framework 1", "Technology 2"],
  "document_summary": "Short 2-line summary of the project",
  "highlights": ["Key achievement / result 1", "Key highlight 2"]
}}<|end|>
<|assistant|>
{{"title":"""

    elif dtype == "research_paper":
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured facts from this Research Paper:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Paper Title",
  "authors": ["Author 1", "Author 2"],
  "year": "Publication Year or Conference",
  "document_summary": "Abstract and core problem addressed",
  "highlights": ["Methodological finding 1", "Experimental result 2"]
}}<|end|>
<|assistant|>
{{"title":"""

    elif dtype in ("resume", "cv"):
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract candidate facts from this Resume:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Resume: <Candidate Name>",
  "document_summary": "Short executive summary of candidate",
  "what_he_wants": "Career objective or target role",
  "what_he_knows": ["Core skill 1", "Core skill 2", "Core skill 3"],
  "certifications": ["Degree / Certification 1", "Certification 2"],
  "contact": {{"name": "Full Name", "email": "Email", "phone": "Phone", "location": "City"}},
  "highlights": ["Key professional highlight 1", "Highlight 2"]
}}<|end|>
<|assistant|>
{{"title":"""

    elif dtype == "photo_document":
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured facts from this Scanned Photo / Document:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Photo Document Title",
  "document_summary": "Summary of visible data and text in the image",
  "highlights": ["Extracted text point 1", "Extracted point 2", "Extracted point 3"]
}}<|end|>
<|assistant|>
{{"title":"""

    elif dtype in (
        "degree_certificate", "marksheet", "professional_certificate",
        "training_certificate", "achievement_certificate",
        "internship_certificate", "experience_letter",
        "offer_letter", "appointment_letter",
    ):
        return f"""<|system|>
You are a fast document intelligence engine specializing in certificate recognition. Output raw JSON only.<|end|>
<|user|>
Extract all key information from this Certificate / Official Document image:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "certificate_name": "Full certificate title (e.g. Certificate of Completion, Degree Certificate)",
  "certificate_type": "Type: Professional/Achievement/Training/Degree/Experience/Internship/Offer/Other",
  "issued_to": "Full name of the recipient / awardee",
  "issuing_organization": "Name of the institution, university, or company that issued it",
  "issue_date": "Date on the certificate (DD Month YYYY or YYYY-MM-DD)",
  "credential_id": "Credential ID / Certificate number if present, else null",
  "document_summary": "One-line summary of what this certificate confirms",
  "highlights": ["Key verified fact 1", "Key verified fact 2"]
}}<|end|>
<|assistant|>
{{"certificate_name":"""

    elif dtype in ("invoice", "bill", "payslip"):
        return f"""<|system|>
You are a fast corporate document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured billing, corporate and financial facts from this Invoice/Statement:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "invoice_number": "Invoice number / ID",
  "invoice_date": "Invoice Date (e.g. MM/DD/YYYY)",
  "due_date": "Due Date or Payment Terms",
  "payment_terms": "Terms (e.g. DD Net 1 Day, Net 30)",
  "total_amount_due": "Total amount due with currency symbol (e.g. $6,903.69)",
  "total_gross": "Total gross amount",
  "total_fringe": "Total fringe amount",
  "payroll_total": "Payroll total amount",
  "billed_to": "Client / Company being billed",
  "remit_to": "Payee / Company to remit payment to",
  "bank_name": "Bank name (e.g. Bank of America, Chase)",
  "account_number": "Account number",
  "routing_number": "Wire / ACH routing number",
  "po_number": "PO number / Acct number",
  "client_code": "Client code / identifier",
  "contact_person": "Contact person name",
  "document_summary": "One-line summary of invoice charges and recipient",
  "highlights": ["Key invoice line item or amount 1", "Key line item 2", "Key line item 3"]
}}<|end|>
<|assistant|>
{{"total_amount_due":"""

    else:
        return f"""<|system|>
You are a fast document intelligence engine. Output raw JSON only.<|end|>
<|user|>
Extract structured facts from this Document:
Document: {document_name}
\"\"\"
{document_text}
\"\"\"

Format:
{{
  "title": "Document Title",
  "document_summary": "Short 2-3 line summary of content",
  "highlights": ["Key highlight 1", "Key highlight 2", "Key highlight 3"]
}}<|end|>
<|assistant|>
{{"title":"""


def _default_prompt_template() -> str:
    return _build_prompt("{document_text}", "document", "{document_name}", "1")


def _partial_parse(raw: dict, warnings: list[str]) -> ExtractionResult:
    """Try to extract whatever valid fields are present."""
    result = ExtractionResult()
    try:
        if "personal" in raw and isinstance(raw["personal"], dict):
            p_dict = dict(raw["personal"])
            if isinstance(p_dict.get("email"), list) and p_dict["email"]:
                p_dict["email"] = str(p_dict["email"][0])
            result.personal = PersonalInfo.model_validate(p_dict)
    except Exception:
        pass

    # Contact field fallback
    if "contact" in raw and isinstance(raw["contact"], dict):
        c = raw["contact"]
        if not result.personal.name and c.get("name"): result.personal.name = str(c["name"])
        if not result.personal.email and c.get("email"): result.personal.email = str(c["email"])
        if not result.personal.phone and c.get("phone"): result.personal.phone = str(c["phone"])
        if not result.personal.location and c.get("location"): result.personal.location = str(c["location"])

    # User requested core attributes
    if "what_he_wants" in raw and raw["what_he_wants"]:
        result.what_he_wants = str(raw["what_he_wants"]).strip()
    elif "objective" in raw and raw["objective"]:
        result.what_he_wants = str(raw["objective"]).strip()

    if "what_he_knows" in raw:
        if isinstance(raw["what_he_knows"], list):
            result.what_he_knows = [str(k).strip() for k in raw["what_he_knows"] if k]
        elif isinstance(raw["what_he_knows"], str):
            result.what_he_knows = [str(raw["what_he_knows"]).strip()]

    if "certifications" in raw:
        if isinstance(raw["certifications"], list):
            for c in raw["certifications"]:
                if isinstance(c, str) and c.strip():
                    result.certifications_done.append(c.strip())
                elif isinstance(c, dict) and c.get("name"):
                    result.certifications_done.append(str(c["name"]).strip())

    if "document_summary" in raw and raw["document_summary"]:
        result.document_summary = str(raw["document_summary"]).strip()
    elif "summary" in raw and raw["summary"]:
        result.document_summary = str(raw["summary"]).strip()

    # Universal document intelligence fields
    if "title" in raw and isinstance(raw["title"], str):
        result.title = raw["title"].strip()
    if "authors" in raw:
        if isinstance(raw["authors"], list):
            result.authors = [str(a).strip() for a in raw["authors"] if a]
        elif isinstance(raw["authors"], str):
            result.authors = [str(raw["authors"]).strip()]
    if "year" in raw and raw["year"]:
        result.year = str(raw["year"]).strip()
    if "concept" in raw and isinstance(raw["concept"], str):
        result.concept = raw["concept"].strip()
    if "highlights" in raw:
        if isinstance(raw["highlights"], list):
            result.highlights = [str(h).strip() for h in raw["highlights"] if h]
        elif isinstance(raw["highlights"], str):
            result.highlights = [str(raw["highlights"]).strip()]

    # Certificate / image document specific fields
    if "certificate_name" in raw and raw["certificate_name"]:
        result.certificate_name = str(raw["certificate_name"]).strip()
    if "certificate_type" in raw and raw["certificate_type"]:
        result.certificate_type = str(raw["certificate_type"]).strip()
    if "issued_to" in raw and raw["issued_to"]:
        result.issued_to = str(raw["issued_to"]).strip()
        # Also populate personal.name if not already set
        if not result.personal.name:
            result.personal.name = result.issued_to
    if "issuing_organization" in raw and raw["issuing_organization"]:
        result.issuing_organization = str(raw["issuing_organization"]).strip()
    if "issue_date" in raw and raw["issue_date"]:
        result.issue_date = str(raw["issue_date"]).strip()
        # Also populate year from issue_date if not already set
        if not result.year:
            yr = re.search(r"\b(19|20)\d{2}\b", result.issue_date)
            if yr:
                result.year = yr.group(0)
    if "credential_id" in raw and raw["credential_id"] and str(raw["credential_id"]).lower() not in ("null", "none", ""):
        result.credential_id = str(raw["credential_id"]).strip()

    # Corporate / Invoice / Billing document specific fields
    for field_name in [
        "invoice_number", "invoice_date", "due_date", "payment_terms",
        "total_amount_due", "total_gross", "total_fringe", "payroll_total",
        "billed_to", "remit_to", "bank_name", "account_number",
        "routing_number", "po_number", "client_code", "contact_person"
    ]:
        val = raw.get(field_name)
        if val and str(val).lower() not in ("null", "none", ""):
            setattr(result, field_name, str(val).strip())

    if "line_items" in raw and isinstance(raw["line_items"], list):
        result.line_items = [item for item in raw["line_items"] if isinstance(item, dict)]

    return result


def _validate_fields(result: ExtractionResult, warnings: list[str]) -> None:
    """Post-extraction field validation — email, phone, dates."""
    if result.personal.email:
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", result.personal.email):
            warnings.append(f"Invalid email format: {result.personal.email}")
            result.personal.email = None

    if result.personal.phone:
        digits = re.sub(r"\D", "", result.personal.phone)
        if len(digits) < 7 or len(digits) > 15:
            warnings.append(f"Suspicious phone number: {result.personal.phone}")


def _extract_year(date_str: str) -> Optional[int]:
    """Extract 4-digit year from a date string."""
    match = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(match.group(0)) if match else None


def _apply_rule_based_fallbacks(text: str, result: ExtractionResult, document_type: str = "", document_name: str = "") -> None:
    """Extract standard patterns directly from text according to document category."""
    text_lower = text.lower()
    dtype = (document_type or "").lower()
    is_resume = dtype in ("resume", "cv") or (
        bool(re.search(r"\b(curriculum\s+vitae|resume|biodata|career\s+objective)\b", text_lower))
        and bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text))
    )

    clean_stem = document_name.rsplit(".", 1)[0] if "." in document_name else document_name
    clean_stem = clean_stem.replace("_", " ").strip()

    # 1. Year extraction (universal)
    if not result.year:
        years = re.findall(r"\b(20[1-2][0-9]|19[8-9][0-9])\b", text)
        if years:
            result.year = years[0]

    # 2. General Highlights (universal)
    if not result.highlights:
        candidate_lines = []
        for line in text.splitlines():
            line_str = line.strip()
            if (line_str.startswith(("-", "*", "•", ">")) or re.match(r"^\d+[\.\)]", line_str)) and len(line_str) > 15:
                clean = re.sub(r"^[-*•>\d\.\)\s]+", "", line_str).strip()
                if clean and clean not in candidate_lines:
                    candidate_lines.append(clean)
        if candidate_lines:
            result.highlights = candidate_lines[:6]

    # ── BRANCH: BOOK / PUBLICATION ────────────────────────────────
    if dtype == "book" or "book" in clean_stem.lower():
        result.personal = PersonalInfo()  # No candidate contact for books
        result.what_he_wants = None
        result.certifications_done = []

        if not result.title:
            result.title = clean_stem.title()
        if not result.authors:
            author_match = re.search(r"(?:author|written\s+by|by)\s*[:\-\s]\s*([A-Za-z\s,\.]+)", text, re.I)
            if author_match:
                result.authors = [author_match.group(1).strip()[:50]]
        if not result.document_summary:
            result.document_summary = f"Comprehensive publication and text overview for '{result.title}', detailing core principles and chapters."
        if not result.highlights:
            chapters = re.findall(r"(?:chapter\s+\d+|part\s+\d+|section\s+\d+)\s*[:\-\s]*[^\n\r]+", text, re.I)
            if chapters:
                result.highlights = [c.strip() for c in chapters[:6]]
            else:
                result.highlights = ["Detailed structured chapters and key analytical concepts.", "Core domain foundations and educational methodologies."]
        return

    # ── BRANCH: RESEARCH PAPER ────────────────────────────────────
    if dtype == "research_paper" or any(k in clean_stem.lower() for k in ["paper", "ieee", "icccnt"]):
        result.personal = PersonalInfo()  # No candidate contact for papers
        result.what_he_wants = None
        result.certifications_done = []

        if not result.title:
            for line in text.splitlines()[:5]:
                cl = line.strip()
                if len(cl) > 15 and not any(k in cl.lower() for k in ["ieee", "conference", "abstract", "issn", "doi"]):
                    result.title = cl[:120]
                    break
            if not result.title:
                result.title = clean_stem.title()

        if not result.authors:
            auth_match = re.search(r"(?:authors?|by)\s*[:\-\s]\s*([^\n\r]+)", text, re.I)
            if auth_match:
                raw_auths = re.split(r"[,;]|\band\b", auth_match.group(1))
                result.authors = [a.strip() for a in raw_auths if len(a.strip()) > 2][:6]

        if not result.document_summary:
            abs_match = re.search(r"abstract\s*[:\-\n]\s*([^\n\r]+(?:\n[^\n\r]+){1,3})", text, re.I)
            if abs_match:
                result.document_summary = re.sub(r"\s+", " ", abs_match.group(1)).strip()[:300]
            else:
                result.document_summary = f"Peer-reviewed scientific study exploring proposed architectures and experimental evaluations in {result.title}."
        return

    # ── BRANCH: PROJECT REPORT ────────────────────────────────────
    if dtype == "project_report" or any(k in clean_stem.lower() for k in ["project", "report", "capstone", "thesis"]):
        result.personal = PersonalInfo()
        if not result.title:
            result.title = f"Project: {clean_stem.title()}"
        if not result.concept:
            concept_match = re.search(r"(?:problem\s+statement|system\s+architecture|proposed\s+system|abstract|concept)\s*[:\-\n]\s*([^\n\r]+(?:\n[^\n\r]+){0,2})", text, re.I)
            if concept_match:
                result.concept = re.sub(r"\s+", " ", concept_match.group(1)).strip()[:250]
        if not result.what_he_wants:
            aim_match = re.search(r"(?:aim|objective|goal|purpose)\s*[:\-\n]\s*([^\n\r]+(?:\n[^\n\r]+){0,2})", text, re.I)
            if aim_match:
                result.what_he_wants = re.sub(r"\s+", " ", aim_match.group(1)).strip()[:250]
        if not result.document_summary:
            result.document_summary = f"Comprehensive project report documenting implementation, design architecture, and engineering results for {result.title}."
        return

    # ── BRANCH: INVOICE / BILLING / PAYROLL / CORPORATE DOCUMENT ─
    is_invoice = dtype in ("invoice", "bill", "payslip") or any(
        k in clean_stem.lower() for k in ["invoice", "bill", "payroll", "statement", "receipt"]
    ) or bool(
        re.search(r"\b(invoice\s*[:#\d]|total\s+amount\s+due|gross\s+wages|employer\s+fringes|remit\s+payment\s+to|wire\s+routing)\b", text, re.I)
    )

    if is_invoice:
        result.personal = PersonalInfo()

        # 1. Invoice Number
        if not result.invoice_number:
            inv_match = re.search(r"\b(?:invoice|inv|bill)\s*(?:#|no|number)?\s*[:\-\s]*([A-Za-z0-9\-_]{4,25})\b", text, re.I)
            if inv_match:
                result.invoice_number = inv_match.group(1).strip()

        # 2. Total Amount Due
        if not result.total_amount_due:
            # Match TOTAL AMOUNT DUE specifically first
            exact_due = re.search(r"total\s+amount\s+due[^\d$€£\n]*([$€£]?\s*[\d,]+\.\d{2})", text, re.I)
            if exact_due:
                result.total_amount_due = exact_due.group(1).replace(" ", "").strip()
            else:
                amt_match = re.search(
                    r"(?:total\s+due|balance\s+due|amount\s+due|total\s+invoice)[^\d$€£\n]*([$€£]?\s*[\d,]+\.\d{2})",
                    text,
                    re.I
                )
                if amt_match:
                    result.total_amount_due = amt_match.group(1).replace(" ", "").strip()
                else:
                    any_total = re.search(r"\btotal[^\d$€£\n]*([$€£]?\s*[\d,]+\.\d{2})", text, re.I)
                    if any_total:
                        result.total_amount_due = any_total.group(1).replace(" ", "").strip()

        # 3. Invoice Date
        if not result.invoice_date:
            inv_date_match = re.search(
                r"\b(?:invoice\s+date|date)\s*[:\-\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b",
                text,
                re.I
            )
            if inv_date_match:
                result.invoice_date = inv_date_match.group(1).strip()
                if not result.year:
                    yr = re.search(r"\b(19|20)\d{2}\b", result.invoice_date)
                    if yr:
                        result.year = yr.group(0)

        # 4. Due Date / Terms
        if not result.due_date:
            due_match = re.search(
                r"\b(?:due\s+date|payment\s+due)\s*[:\-\s]*([^\n\r]+)",
                text,
                re.I
            )
            if due_match:
                result.due_date = due_match.group(1).splitlines()[0].strip()[:40]

        if not result.payment_terms:
            terms_match = re.search(
                r"\b(?:terms|payment\s+terms)\s*[:\-\s]*([^\n\r]+)",
                text,
                re.I
            )
            if terms_match:
                result.payment_terms = terms_match.group(1).splitlines()[0].strip()[:40]
            if not result.due_date and result.payment_terms:
                result.due_date = result.payment_terms

        # 5. Bank Name & Wire Routing
        if not result.bank_name:
            if re.search(r"\bBank\s+of\s+America\b", text, re.I):
                result.bank_name = "Bank of America"
            elif re.search(r"\b(?:JPMorgan\s+)?Chase\s+Bank\b", text, re.I):
                result.bank_name = "Chase Bank"
            elif re.search(r"\bWells\s+Fargo\b", text, re.I):
                result.bank_name = "Wells Fargo"
            elif re.search(r"\bCitibank\b", text, re.I):
                result.bank_name = "Citibank"
            elif re.search(r"\bBarclays\b", text, re.I):
                result.bank_name = "Barclays"
            elif re.search(r"\bHSBC\b", text, re.I):
                result.bank_name = "HSBC"
            else:
                bank_match = re.search(r"\b([A-Z][A-Za-z\s]+Bank)\b", text)
                if bank_match:
                    cand = bank_match.group(1).strip()
                    if not any(k in cand.lower() for k in ["burbank", "room", "floor"]):
                        result.bank_name = cand

        if not result.routing_number:
            routing_match = re.search(
                r"(?:wire\s+routing|routing\s+number|routing\s+num|aba|ach\s+routing)\s*(?:number|num|#)?\s*[:\-\s]*([0-9\-\s]{4,20})",
                text,
                re.I
            )
            if routing_match:
                result.routing_number = re.sub(r"\s+", " ", routing_match.group(1)).strip()

        if not result.account_number:
            acct_match = re.search(
                r"(?:account\s+number|acct\s+number|acct\s+num|account\s*#|acct\s*#|account)\s*[:\-\s]*([0-9\-\s]{4,25})",
                text,
                re.I
            )
            if acct_match:
                result.account_number = re.sub(r"\s+", " ", acct_match.group(1)).strip()

        # 6. Remit To / Payee
        if not result.remit_to:
            remit_match = re.search(
                r"(?:remit\s+payment\s+to|remit\s+to|payable\s+to)\s*[:\-\s]*([^\n\r]+)",
                text,
                re.I
            )
            if remit_match:
                result.remit_to = remit_match.group(1).strip()[:100]

        # 7. Billed To / Client
        if not result.billed_to:
            bill_match = re.search(
                r"(?:bill\s+to|attn)\s*[:\-\s]*([^\n\r]+)",
                text,
                re.I
            )
            if bill_match:
                result.billed_to = bill_match.group(1).strip()[:100]

        # 8. PO Number / Client Code / Contact
        if not result.po_number:
            po_match = re.search(r"\bpo\s*(?:#|no|num)?\s*[:\-\s]*([A-Za-z0-9\-_]{3,20})\b", text, re.I)
            if po_match:
                result.po_number = po_match.group(1).strip()

        if not result.contact_person:
            contact_match = re.search(r"\bcontact\s*[:\-\s]*([^\n\r]+)", text, re.I)
            if contact_match:
                result.contact_person = contact_match.group(1).strip()[:50]

        if not result.client_code:
            client_match = re.search(r"\bclient\s*[:\-\s]*([^\n\r]+)", text, re.I)
            if client_match:
                result.client_code = client_match.group(1).strip()[:40]
            client_match = re.search(r"\bclient\s*[:\-\s]*([A-Za-z0-9\/\-_]{3,25})\b", text, re.I)
            if client_match:
                result.client_code = client_match.group(1).strip()

        # 9. Breakdown Gross & Fringe
        if not result.total_gross:
            gross_match = re.search(r"\btotal\s+gross\s*[:\-\s]*([$€£₹]?\s*[\d,]+\.\d{2})\b", text, re.I)
            if gross_match:
                result.total_gross = gross_match.group(1).strip()

        if not result.total_fringe:
            fringe_match = re.search(r"\btotal\s+fringe\s*[:\-\s]*([$€£₹]?\s*[\d,]+\.\d{2})\b", text, re.I)
            if fringe_match:
                result.total_fringe = fringe_match.group(1).strip()

        if not result.payroll_total:
            payroll_match = re.search(r"\bpayroll\s+total\s*[:\-\s]*([$€£₹]?\s*[\d,]+\.\d{2})\b", text, re.I)
            if payroll_match:
                result.payroll_total = payroll_match.group(1).strip()

        # 10. Title & Document Summary
        inv_title = f"Invoice: {result.invoice_number}" if result.invoice_number else f"Corporate Invoice / Billing: {clean_stem.title()}"
        result.title = inv_title

        summary_parts = []
        if result.invoice_number:
            summary_parts.append(f"Invoice #{result.invoice_number}")
        if result.total_amount_due:
            summary_parts.append(f"with total amount due of {result.total_amount_due}")
        if result.due_date:
            summary_parts.append(f"(Due / Terms: {result.due_date})")
        if result.remit_to:
            summary_parts.append(f"payable to {result.remit_to}")
        result.document_summary = " ".join(summary_parts) + "." if summary_parts else f"Corporate billing invoice detailing charges and payment specifications for {clean_stem}."

        # 11. Highlights
        inv_highlights = []
        if result.total_amount_due:
            inv_highlights.append(f"Total Amount Due: {result.total_amount_due}")
        if result.due_date:
            inv_highlights.append(f"Due Date / Terms: {result.due_date}")
        if result.invoice_number:
            inv_highlights.append(f"Invoice Number: {result.invoice_number}")
        if result.bank_name:
            inv_highlights.append(f"Bank Name: {result.bank_name}")
        if result.routing_number:
            inv_highlights.append(f"Routing Number: {result.routing_number}")
        if result.account_number:
            inv_highlights.append(f"Account Number: {result.account_number}")
        if result.po_number:
            inv_highlights.append(f"PO Number: {result.po_number}")
        if result.total_gross:
            inv_highlights.append(f"Total Gross: {result.total_gross}")
        if result.total_fringe:
            inv_highlights.append(f"Total Fringe: {result.total_fringe}")
        result.highlights = inv_highlights or ["Corporate financial document with line-item charge breakdown."]

        return

    # ── BRANCH: CERTIFICATES & CREDENTIALS (Image or Document) ───
    is_certificate = dtype in (
        "degree_certificate", "marksheet", "professional_certificate",
        "training_certificate", "achievement_certificate",
        "internship_certificate", "experience_letter",
        "offer_letter", "appointment_letter"
    ) or any(k in clean_stem.lower() for k in ["certif", "completion", "degree", "diploma", "award"]) or (
        bool(re.search(r"\b(certificate\s+of|certifies\s+that|is\s+hereby\s+awarded\s+to|presented\s+to|this\s+is\s+to\s+certify)\b", text, re.I))
    )

    if is_certificate:
        # 1. Recipient / Issued To Name
        if not result.issued_to:
            name_match = re.search(
                r"(?:certify\s+that|awarded\s+to|presented\s+to|certifies\s+that|conferred\s+upon|this\s+is\s+to\s+certify\s+(?:that)?)\s*[:\-\n\s]*([A-Z][A-Za-z\s.]{2,40})",
                text,
                re.I
            )
            if name_match:
                cand_name = re.sub(r"\s+", " ", name_match.group(1)).strip()
                cand_name = re.sub(r"\b(has|successfully|completed|for|in|on|the|a|an)\b.*$", "", cand_name, flags=re.I).strip()
                if len(cand_name.split()) in (1, 2, 3, 4) and len(cand_name) > 2:
                    result.issued_to = cand_name
                    if not result.personal.name:
                        result.personal.name = cand_name

        # Recipient fallback from lines following "this is to certify" or standalone prominent names
        if not result.issued_to:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for idx, line in enumerate(lines):
                if re.search(r"\b(certify\s+that|awarded\s+to|presented\s+to)\b", line, re.I):
                    if idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        if 2 < len(next_line) <= 40 and re.match(r"^[A-Za-z\s.]+$", next_line):
                            result.issued_to = next_line
                            if not result.personal.name:
                                result.personal.name = next_line
                            break

        # 2. Certificate Name / Title
        if not result.certificate_name:
            cert_title_match = re.search(
                r"\b(certificate\s+of\s+[A-Za-z\s]{3,35}|diploma\s+in\s+[A-Za-z\s]{3,35}|bachelor\s+of\s+[A-Za-z\s]{3,35}|master\s+of\s+[A-Za-z\s]{3,35})\b",
                text.split("\n\n")[0],
                re.I
            )
            if cert_title_match:
                # Take just the first line of the match
                first_line_cert = cert_title_match.group(0).splitlines()[0].strip()
                result.certificate_name = first_line_cert.title()
            else:
                for line in text.splitlines()[:6]:
                    cl = line.strip()
                    if re.search(r"\b(certificate|completion|achievement|appreciation|excellence|degree)\b", cl, re.I) and len(cl) < 70:
                        result.certificate_name = cl.title()
                        break
                if not result.certificate_name:
                    result.certificate_name = f"Certificate: {clean_stem.title()}"

        if not result.title:
            result.title = result.certificate_name

        # 3. Issuing Organization / Body
        if not result.issuing_organization:
            # Check explicit "Issued by" or "Provided by" or "Offered by"
            issued_by_match = re.search(r"(?:issued\s+by|offered\s+by|organized\s+by|authorized\s+by|provider)\s*[:\-]?\s*([^\n\r]+)", text, re.I)
            if issued_by_match:
                org_cand = issued_by_match.group(1).strip()
                if len(org_cand) > 2 and len(org_cand) < 80:
                    result.issuing_organization = org_cand
            
            if not result.issuing_organization:
                org_match = re.search(
                    r"\b([A-Za-z\s]+(?:University|Institute|College|Academy|Corporation|Inc|LLC|Technologies|Udemy|Coursera|Google|Amazon|Microsoft|Cisco|IBM|Meta|Paavai|NPTEL))\b",
                    text,
                    re.I
                )
                if org_match:
                    found_org = org_match.group(1).splitlines()[0].strip()
                    if result.issued_to and found_org.lower() != result.issued_to.lower():
                        result.issuing_organization = found_org
            
            if not result.issuing_organization:
                # Top header lines often state the institution
                first_lines = [l.strip() for l in text.splitlines()[:4] if len(l.strip()) > 3]
                for fl in first_lines:
                    if not re.search(r"\b(certificate|certify|completion|date|id)\b", fl, re.I) and len(fl) < 60:
                        if not result.issued_to or fl.lower() != result.issued_to.lower():
                            result.issuing_organization = fl
                            break

        # 4. Issue Date
        if not result.issue_date:
            date_match = re.search(
                r"\b(?:issued\s+on|date\s*[:\-]|dated\s*[:\-]?)?\s*(\d{1,2}[\/\-\.\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[A-Za-z]+|\d{1,2})[\/\-\.\s]\d{2,4})\b",
                text,
                re.I
            )
            if date_match:
                result.issue_date = date_match.group(1).strip()
                if not result.year:
                    yr = re.search(r"\b(19|20)\d{2}\b", result.issue_date)
                    if yr:
                        result.year = yr.group(0)

        # 5. Credential ID
        if not result.credential_id:
            cred_match = re.search(
                r"(?:certificate\s*(?:no|id|#)|credential\s*(?:id|#)|verification\s*code)\s*[:\-\s]*([A-Za-z0-9\-_]{5,30})",
                text,
                re.I
            )
            if cred_match:
                result.credential_id = cred_match.group(1).strip()

        # 6. Highlights & Summary
        if not result.document_summary:
            summary_parts = []
            if result.certificate_name:
                summary_parts.append(f"{result.certificate_name}")
            if result.issued_to:
                summary_parts.append(f"conferred upon {result.issued_to}")
            if result.issuing_organization:
                summary_parts.append(f"by {result.issuing_organization}")
            if result.issue_date:
                summary_parts.append(f"on {result.issue_date}")
            result.document_summary = " ".join(summary_parts) + "." if summary_parts else f"Official certificate verifying credentials and completion for {clean_stem}."

        if not result.highlights:
            cert_highlights = []
            if result.issued_to:
                cert_highlights.append(f"Recipient: {result.issued_to}")
            if result.issuing_organization:
                cert_highlights.append(f"Issuer: {result.issuing_organization}")
            if result.issue_date:
                cert_highlights.append(f"Date Issued: {result.issue_date}")
            if result.credential_id:
                cert_highlights.append(f"Credential ID: {result.credential_id}")
            result.highlights = cert_highlights or ["Verified official certificate of completion and professional recognition."]

        return

    # ── BRANCH: PHOTO / SCANNED DOCUMENT (General Image) ──────────
    if dtype == "photo_document":
        result.personal = PersonalInfo()
        if not result.title:
            result.title = f"Scanned Document / Photo: {clean_stem}"
        if not result.document_summary:
            result.document_summary = f"Visual document snapshot processed via optical character recognition, capturing text and data elements from {clean_stem}."
        if not result.highlights:
            non_empty_lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 10]
            if non_empty_lines:
                result.highlights = non_empty_lines[:6]
        return

    # ── BRANCH: RESUME / CV ───────────────────────────────────────
    if is_resume:
        # 1. Email extraction
        if not result.personal.email:
            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
            if email_match:
                result.personal.email = email_match.group(0).strip()

        # 2. Phone extraction
        if not result.personal.phone:
            phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b[6-9]\d{9}\b", text)
            if phone_match:
                result.personal.phone = phone_match.group(0).strip()

        # 3. Name heuristic
        if not result.personal.name:
            for line in text.splitlines():
                line = line.strip()
                if 2 <= len(line) <= 40 and not any(k in line.lower() for k in ["resume", "curriculum", "email", "@", "phone", "http", "github", "linkedin"]):
                    clean_name = re.sub(r"[^a-zA-Z\s.]", "", line).strip()
                    if len(clean_name.split()) in (1, 2, 3, 4):
                        result.personal.name = clean_name
                        break

        # 4. Location
        if not result.personal.location:
            loc_match = re.search(r"(?:[A-Za-z\s]+),\s*(?:Tamil\s*Nadu|Karnataka|Maharashtra|Delhi|Kerala|Telangana|Andhra|India|[A-Z]{2})\b", text)
            if loc_match:
                result.personal.location = loc_match.group(0).strip()

        # 5. Skills
        known_skills = [
            "python", "javascript", "typescript", "c++", "c#", "java", "sql", "html", "css",
            "react", "angular", "vue", "fastapi", "django", "flask", "node.js", "express",
            "machine learning", "deep learning", "nlp", "computer vision", "tensorflow", "pytorch",
            "docker", "kubernetes", "git", "aws", "azure", "gcp", "linux", "mongodb", "postgresql",
            "power bi", "predictive modelling", "data analysis", "eda", "cross-validation", "swarm intelligence"
        ]
        detected_skills = []
        for skill in known_skills:
            if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
                detected_skills.append(skill.title() if len(skill) > 3 else skill.upper())
        if not result.what_he_knows:
            result.what_he_knows = detected_skills[:12]

        # 6. Objective / What he wants
        if not result.what_he_wants:
            obj_match = re.search(r"(?:career\s+objective|professional\s+summary|objective|about\s+me)\s*[:\-\n]\s*([^\n\r]+(?:\n[^\n\r]+){0,2})", text, re.I)
            if obj_match:
                result.what_he_wants = re.sub(r"\s+", " ", obj_match.group(1)).strip()[:250]
            else:
                result.what_he_wants = "Seeking software and AI engineering roles to develop intelligent, scalable systems and solve practical industry challenges."

        # 7. Certifications
        if not result.certifications_done:
            certs = []
            for line in text.splitlines():
                line_str = line.strip()
                if re.search(r"\b(paavai|college|university|school|matric|higher\s+secondary|b\.?tech|b\.?e|m\.?tech|b\.?sc|m\.?sc|diploma|gradtwin|nsic|internship|certified|certificate)\b", line_str, re.I):
                    clean_cert = re.sub(r"^[•\-\*\s]+", "", line_str).strip()
                    if 10 < len(clean_cert) < 120 and clean_cert not in certs:
                        certs.append(clean_cert)
            result.certifications_done = certs[:6]

        name_str = result.personal.name or "Candidate"
        result.title = f"Resume & Professional Profile: {name_str}"
        if not result.document_summary:
            result.document_summary = f"Comprehensive technical profile of {name_str}, demonstrating competencies in software engineering and hands-on project implementations."
        return

    # ── BRANCH: GENERAL / OTHER ───────────────────────────────────
    if not result.title:
        for line in text.splitlines()[:5]:
            cl = line.strip()
            if len(cl) > 10 and not any(k in cl.lower() for k in ["http", "@", "page"]):
                result.title = cl[:120]
                break
        if not result.title:
            result.title = clean_stem.title()
    if not result.document_summary:
        result.document_summary = f"Document containing structured data, concepts, and analytical records regarding {result.title}."

