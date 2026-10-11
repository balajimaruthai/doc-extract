"""Export API — JSON, CSV, and PDF export (all local, no external services)."""
import csv
import io
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, JSONResponse
from database.connection import get_connection
from core.config import settings

router = APIRouter()


@router.get("/{profile_id}/json")
async def export_json(profile_id: str):
    """Export profile as structured JSON."""
    profile = await _get_full_profile(profile_id)
    return JSONResponse(content=profile, headers={
        "Content-Disposition": f'attachment; filename="profile_{profile_id[:8]}.json"'
    })


@router.get("/{profile_id}/csv")
async def export_csv(profile_id: str):
    """Export key profile fields as CSV."""
    profile = await _get_full_profile(profile_id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Field", "Value", "Source"])
    writer.writerow(["Name", profile.get("full_name", ""), "profile"])
    writer.writerow(["Email", profile.get("email", ""), "profile"])
    writer.writerow(["Phone", profile.get("phone", ""), "profile"])
    writer.writerow(["Location", profile.get("location", ""), "profile"])
    writer.writerow(["Experience Level", profile.get("estimated_experience_level", ""), "calculated"])
    writer.writerow(["Total Experience (months)", profile.get("total_documented_experience_months", 0), "calculated"])
    writer.writerow([])

    writer.writerow(["EDUCATION"])
    writer.writerow(["Degree", "Specialization", "Institution", "Graduation"])
    for edu in profile.get("education", []):
        writer.writerow([edu.get("degree", ""), edu.get("specialization", ""),
                         edu.get("institution", ""), edu.get("graduation_date", "")])
    writer.writerow([])

    writer.writerow(["EXPERIENCE"])
    writer.writerow(["Company", "Designation", "Start", "End", "Duration (months)"])
    for exp in profile.get("experience", []):
        writer.writerow([exp.get("company", ""), exp.get("designation", ""),
                         exp.get("start_date", ""), exp.get("end_date", "Present" if exp.get("is_current") else ""),
                         exp.get("duration_months", "")])

    csv_content = output.getvalue()
    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="profile_{profile_id[:8]}.csv"'}
    )


@router.get("/{profile_id}/pdf")
async def export_pdf(profile_id: str):
    """Export profile as a formatted PDF using ReportLab (offline only)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        raise HTTPException(status_code=500, detail="ReportLab not installed. Run: pip install reportlab")

    profile = await _get_full_profile(profile_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceAfter=4, spaceBefore=12)
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=9, textColor=colors.grey)

    story = []

    # Header
    name = profile.get("full_name") or "Unknown Candidate"
    story.append(Paragraph(name, h1))

    contact_parts = [p for p in [profile.get("email"), profile.get("phone"), profile.get("location")] if p]
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), small))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 0.3*cm))

    # Privacy notice
    story.append(Paragraph(
        "<i>Generated locally. No data was transmitted to any external service.</i>",
        small
    ))
    story.append(Spacer(1, 0.3*cm))

    # Summary
    if profile.get("professional_summary"):
        story.append(Paragraph("Professional Summary", h2))
        story.append(Paragraph(profile["professional_summary"], normal))

    # Experience level
    if profile.get("estimated_experience_level"):
        story.append(Paragraph("Experience Level", h2))
        months = profile.get("total_documented_experience_months", 0)
        years = months // 12
        rem_months = months % 12
        duration_str = f"{years}y {rem_months}m" if years > 0 else f"{rem_months} months"
        story.append(Paragraph(
            f"<b>Estimated Level:</b> {profile['estimated_experience_level']} "
            f"| <b>Documented Experience:</b> {duration_str}",
            normal
        ))
        if profile.get("estimated_experience_basis"):
            story.append(Paragraph(f"<i>{profile['estimated_experience_basis']}</i>", small))

    # Education
    if profile.get("education"):
        story.append(Paragraph("Education", h2))
        for edu in profile["education"]:
            parts = [p for p in [edu.get("degree"), edu.get("specialization")] if p]
            story.append(Paragraph(f"<b>{' — '.join(parts)}</b>", normal))
            inst_parts = [p for p in [edu.get("institution"), edu.get("university")] if p]
            if inst_parts:
                story.append(Paragraph(", ".join(inst_parts), normal))
            date_parts = []
            if edu.get("graduation_date"):
                date_parts.append(f"Graduated: {edu['graduation_date']}")
            if edu.get("cgpa"):
                date_parts.append(f"CGPA: {edu['cgpa']}")
            elif edu.get("percentage"):
                date_parts.append(f"Percentage: {edu['percentage']}%")
            if date_parts:
                story.append(Paragraph(" | ".join(date_parts), small))
            story.append(Spacer(1, 0.2*cm))

    # Experience
    if profile.get("experience"):
        story.append(Paragraph("Professional Experience", h2))
        for exp in profile["experience"]:
            end = "Present" if exp.get("is_current") else (exp.get("end_date") or "")
            story.append(Paragraph(
                f"<b>{exp.get('designation', 'Role Unknown')}</b> — {exp.get('company', 'Company Unknown')}",
                normal
            ))
            story.append(Paragraph(
                f"{exp.get('start_date', '')} — {end}" +
                (f" ({exp.get('duration_months', 0)} months)" if exp.get("duration_months") else ""),
                small
            ))
            story.append(Spacer(1, 0.2*cm))

    # Skills
    skills = profile.get("skills", {})
    if any(skills.values()):
        story.append(Paragraph("Skills", h2))
        for cat, skill_list in skills.items():
            if skill_list:
                cat_display = cat.replace("_", " ").title()
                story.append(Paragraph(f"<b>{cat_display}:</b> {', '.join(skill_list)}", normal))

    # Certifications
    if profile.get("certifications"):
        story.append(Paragraph("Certifications", h2))
        for cert in profile["certifications"]:
            story.append(Paragraph(
                f"<b>{cert.get('name', '')}</b> — {cert.get('issuer', '')} ({cert.get('issue_date', '')})",
                normal
            ))

    # Conflicts notice
    conflict_count = profile.get("conflict_count", 0)
    if conflict_count > 0:
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.red))
        story.append(Paragraph(
            f"⚠ {conflict_count} data conflict(s) detected between documents. "
            "Review conflicts in the application before relying on this report.",
            ParagraphStyle("Warning", parent=normal, textColor=colors.red)
        ))

    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        "All processing performed locally.",
        small
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="profile_{profile_id[:8]}.pdf"'}
    )


async def _get_full_profile(profile_id: str) -> dict:
    """Shared helper to build full profile dict for export."""
    from api.profiles import get_profile
    class FakeRequest:
        pass
    try:
        return await get_profile(profile_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
