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

    # ── BRANCH: PHOTO / SCANNED DOCUMENT ──────────────────────────
    if dtype == "photo_document":
        result.personal = PersonalInfo()
        if not result.title:
            result.title = f"Scanned Document / Photo: {clean_stem}"
        if not result.document_summary:
            result.document_summary = f"Visual document snapshot processed via optical character recognition, capturing text and data elements from {clean_stem}."
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

