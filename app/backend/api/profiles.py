"""Profiles API — retrieve, update, view evidence and conflicts."""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database.connection import get_connection

router = APIRouter()


@router.get("/")
async def list_profiles(limit: int = 20, offset: int = 0):
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT id, full_name, email, estimated_experience_level,
                      total_documented_experience_months, created_at
               FROM profiles ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        total_cur = await conn.execute("SELECT COUNT(*) FROM profiles")
        total = (await total_cur.fetchone())[0]
    return {"profiles": [dict(r) for r in rows], "total": total}


@router.get("/{profile_id}")
async def get_profile(profile_id: str):
    async with get_connection() as conn:
        profile_cur = await conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        profile = await profile_cur.fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        edu_cur = await conn.execute("SELECT * FROM education WHERE profile_id = ? ORDER BY graduation_date DESC", (profile_id,))
        exp_cur = await conn.execute("SELECT * FROM experience WHERE profile_id = ? ORDER BY start_date DESC", (profile_id,))
        skills_cur = await conn.execute("SELECT category, skill_name FROM skills WHERE profile_id = ?", (profile_id,))
        cert_cur = await conn.execute("SELECT * FROM certifications WHERE profile_id = ?", (profile_id,))
        proj_cur = await conn.execute("SELECT * FROM projects WHERE profile_id = ?", (profile_id,))
        ach_cur = await conn.execute("SELECT * FROM achievements WHERE profile_id = ?", (profile_id,))
        conflicts_cur = await conn.execute(
            "SELECT * FROM conflicts WHERE profile_id = ? ORDER BY resolution ASC", (profile_id,)
        )
        docs_cur = await conn.execute(
            """SELECT d.id, d.original_filename, d.document_type, d.processing_status
               FROM documents d
               JOIN profile_documents pd ON d.id = pd.document_id
               WHERE pd.profile_id = ?""", (profile_id,)
        )

        education = [dict(r) for r in await edu_cur.fetchall()]
        experience = [dict(r) for r in await exp_cur.fetchall()]
        skills_rows = await skills_cur.fetchall()
        certifications = [dict(r) for r in await cert_cur.fetchall()]
        projects = [dict(r) for r in await proj_cur.fetchall()]
        achievements = [dict(r) for r in await ach_cur.fetchall()]
        conflicts = [dict(r) for r in await conflicts_cur.fetchall()]
        documents = [dict(r) for r in await docs_cur.fetchall()]

    # Group skills by category
    skills: dict = {}
    for row in skills_rows:
        cat = row["category"]
        if cat not in skills:
            skills[cat] = []
        skills[cat].append(row["skill_name"])

    # Parse JSON fields
    for exp in experience:
        try:
            exp["responsibilities"] = json.loads(exp.get("responsibilities") or "[]")
        except Exception:
            exp["responsibilities"] = []

    return {
        **dict(profile),
        "education": education,
        "experience": experience,
        "skills": skills,
        "certifications": certifications,
        "projects": projects,
        "achievements": achievements,
        "conflicts": conflicts,
        "documents": documents,
        "conflict_count": sum(1 for c in conflicts if c["resolution"] == "unresolved"),
    }


@router.get("/{profile_id}/conflicts")
async def get_conflicts(profile_id: str):
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM conflicts WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)
        )
        rows = await cursor.fetchall()
    return {"conflicts": [dict(r) for r in rows]}


class ConflictResolution(BaseModel):
    resolved_value: str
    resolved_by: str = "user"


@router.patch("/{profile_id}/conflicts/{conflict_id}/resolve")
async def resolve_conflict(profile_id: str, conflict_id: str, resolution: ConflictResolution):
    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT id FROM conflicts WHERE id = ? AND profile_id = ?", (conflict_id, profile_id)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conflict not found")

        await conn.execute(
            """UPDATE conflicts SET resolution = 'user_resolved',
               resolved_value = ?, resolved_by = ? WHERE id = ?""",
            (resolution.resolved_value, resolution.resolved_by, conflict_id)
        )
        await conn.commit()
    return {"message": "Conflict resolved", "conflict_id": conflict_id}


class FieldCorrection(BaseModel):
    field: str
    value: str
    section: str   # "personal", "education", "experience", etc.
    record_id: Optional[str] = None


@router.patch("/{profile_id}/correct")
async def correct_field(profile_id: str, correction: FieldCorrection):
    """Allow user to manually correct an extracted field."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    async with get_connection() as conn:
        if correction.section == "personal":
            allowed = ["full_name", "email", "phone", "location", "professional_summary"]
            if correction.field not in allowed:
                raise HTTPException(status_code=400, detail=f"Field not editable: {correction.field}")
            await conn.execute(
                f"UPDATE profiles SET {correction.field} = ?, updated_at = ? WHERE id = ?",
                (correction.value, now, profile_id)
            )

        elif correction.section == "education" and correction.record_id:
            await conn.execute(
                f"UPDATE education SET {correction.field} = ?, user_corrected = 1 WHERE id = ? AND profile_id = ?",
                (correction.value, correction.record_id, profile_id)
            )

        elif correction.section == "experience" and correction.record_id:
            await conn.execute(
                f"UPDATE experience SET {correction.field} = ?, user_corrected = 1 WHERE id = ? AND profile_id = ?",
                (correction.value, correction.record_id, profile_id)
            )

        await conn.commit()

    return {"message": "Field updated", "field": correction.field, "value": correction.value}
