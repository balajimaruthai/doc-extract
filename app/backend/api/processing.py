"""
Processing API — trigger document processing, status tracking.
Runs the full pipeline: text extraction → OCR → LLM → validation → profile.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from core.config import settings
from database.connection import get_connection

router = APIRouter()
logger = logging.getLogger(__name__)

# Singleton LLM provider (loaded lazily)
_llm_provider = None


def get_llm_provider():
    """Get or initialize the LLM provider singleton."""
    global _llm_provider
    if _llm_provider is None:
        from llm.model_manager import get_best_model
        from llm.llama_cpp_provider import LlamaCppProvider

        best_model = get_best_model(settings.MODELS_DIR)
        if best_model is None:
            return None

        hw_info = None
        try:
            from hardware.detector import get_hardware_info
            hw_info = get_hardware_info()
        except Exception:
            pass

        n_gpu = hw_info.gpu.recommended_n_gpu_layers if (hw_info and hw_info.gpu) else 0

        _llm_provider = LlamaCppProvider(
            model_path=best_model.path,
            n_gpu_layers=n_gpu,
            n_ctx=settings.LLM_N_CTX,
            n_threads=settings.LLM_N_THREADS,
            verbose=settings.LLM_VERBOSE,
        )
    return _llm_provider


class ProcessRequest(BaseModel):
    document_ids: list[str]
    create_profile: bool = True


class ProcessSingleRequest(BaseModel):
    create_profile: bool = True


@router.post("/start")
async def start_processing(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
):
    """Start processing one or more documents."""
    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    # Validate documents exist
    async with get_connection() as conn:
        for doc_id in request.document_ids:
            cursor = await conn.execute(
                "SELECT id, processing_status FROM documents WHERE id = ?", (doc_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Queue processing in background
    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _process_documents,
        job_id=job_id,
        document_ids=request.document_ids,
        create_profile=request.create_profile,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "document_count": len(request.document_ids),
        "message": "Processing started in background",
    }


@router.get("/status/{doc_id}")
async def get_processing_status(doc_id: str):
    """Get processing status for a document."""
    async with get_connection() as conn:
        doc_cursor = await conn.execute(
            "SELECT processing_status, error_message, document_type, page_count FROM documents WHERE id = ?",
            (doc_id,)
        )
        doc = await doc_cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        jobs_cursor = await conn.execute(
            """SELECT stage, status, started_at, completed_at, duration_ms, error_reason
               FROM processing_jobs WHERE document_id = ?
               ORDER BY started_at DESC LIMIT 10""",
            (doc_id,)
        )
        jobs = await jobs_cursor.fetchall()

    return {
        "document_id": doc_id,
        "status": doc["processing_status"],
        "document_type": doc["document_type"],
        "page_count": doc["page_count"],
        "error_message": doc["error_message"],
        "processing_stages": [dict(j) for j in jobs],
    }


async def _process_documents(
    job_id: str,
    document_ids: list[str],
    create_profile: bool,
):
    """
    Full processing pipeline — runs in background.
    Extracts text → OCR → LLM → validates → reconciles → saves profile.
    """
    logger.info(f"Processing job {job_id}: {len(document_ids)} documents")
    extractions = []

    for doc_id in document_ids:
        try:
            result = await _process_single_document(doc_id)
            if result:
                extractions.append(result)
        except Exception as e:
            logger.error(f"Failed to process document {doc_id}: {e}", exc_info=True)

    # Create consolidated profile if requested, but ONLY from profile-relevant documents
    profile_extractions = [
        ex for ex in extractions
        if ex.get("document_type") in (
            "resume", "cv", "degree_certificate", "marksheet",
            "experience_letter", "offer_letter", "appointment_letter",
            "internship_certificate", "professional_certificate"
        )
    ]
    if create_profile and profile_extractions:
        try:
            await _create_profile(profile_extractions)
        except Exception as e:
            logger.error(f"Profile creation failed: {e}", exc_info=True)


async def _process_single_document(doc_id: str) -> Optional[dict]:
    """Process a single document through the full pipeline."""
    from pathlib import Path
    import time

    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        )
        doc = await cursor.fetchone()
        if not doc:
            return None

        # Mark as processing
        await conn.execute(
            "UPDATE documents SET processing_status = 'processing' WHERE id = ?",
            (doc_id,)
        )
        await conn.commit()

    file_path = settings.UPLOADS_DIR / doc["safe_filename"]
    file_type = doc["file_type"]
    pages_text = []

    try:
        # ── PHASE 1: Text Extraction ──────────────────────────
        await _log_job(doc_id, "text_extraction", "running")
        t0 = time.time()

        if file_type == "pdf":
            from extraction.pdf_extractor import extract_pdf
            pdf_result = extract_pdf(file_path)

            if pdf_result.is_password_protected:
                await _mark_failed(doc_id, "PDF is password-protected")
                return None

            if pdf_result.error:
                await _mark_failed(doc_id, pdf_result.error)
                return None

            # Process each page
            for page in pdf_result.pages:
                if page.needs_ocr and page.image_data:
                    # ── PHASE 2: OCR ──────────────────────────
                    from ocr.preprocessor import preprocess_for_ocr
                    from ocr.tesseract_ocr import run_ocr

                    prepped = preprocess_for_ocr(page.image_data)
                    ocr_result = run_ocr(prepped.image_array, page_number=page.page_number)

                    page_text = ocr_result.full_text
                    ocr_conf = ocr_result.mean_confidence
                    method = "ocr"
                    ocr_used = True
                else:
                    page_text = page.text
                    ocr_conf = None
                    method = "native"
                    ocr_used = False

                pages_text.append({
                    "page_number": page.page_number,
                    "text": page_text,
                    "method": method,
                    "ocr_confidence": ocr_conf,
                })

            has_native = pdf_result.has_native_text
            page_count = pdf_result.total_pages

        elif file_type in ("docx", "doc"):
            from extraction.docx_extractor import extract_docx
            docx_result = extract_docx(file_path)
            pages_text = [{"page_number": 1, "text": docx_result.full_text, "method": "native", "ocr_confidence": None}]
            has_native = True
            page_count = 1
            ocr_used = False

        elif file_type in ("jpg", "jpeg", "png"):
            from ocr.preprocessor import preprocess_for_ocr
            from ocr.tesseract_ocr import run_ocr_on_image_file
            ocr_result = run_ocr_on_image_file(file_path, page_number=1)
            pages_text = [{"page_number": 1, "text": ocr_result.full_text, "method": "ocr", "ocr_confidence": ocr_result.mean_confidence}]
            has_native = False
            page_count = 1
            ocr_used = True
        else:
            await _mark_failed(doc_id, f"Unsupported file type: {file_type}")
            return None

        extraction_ms = int((time.time() - t0) * 1000)
        await _log_job(doc_id, "text_extraction", "success", duration_ms=extraction_ms, ocr_used=ocr_used)

        # Save pages to DB
        async with get_connection() as conn:
            for pg in pages_text:
                pid = str(uuid.uuid4())
                import re
                cleaned = re.sub(r"\s+", " ", pg["text"]).strip()
                await conn.execute(
                    """INSERT OR REPLACE INTO document_pages
                       (id, document_id, page_number, extraction_method, raw_text, cleaned_text, ocr_confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (pid, doc_id, pg["page_number"], pg["method"], pg["text"], cleaned, pg["ocr_confidence"])
                )
            await conn.commit()

        # ── PHASE 3: Classification ──────────────────────────
        full_text = "\n\n".join(p["text"] for p in pages_text if p["text"])
        from documents.classification import classify_document
        classification = classify_document(full_text, doc["original_filename"])

        # ── PHASE 4: LLM Extraction ──────────────────────────
        await _log_job(doc_id, "llm_extraction", "running")
        t1 = time.time()

        llm = get_llm_provider()
        extraction_result = None

        if llm and llm.is_available():
            from extraction_pipeline.extractor import extract_from_text
            page_info = f"1-{page_count}" if page_count > 1 else "1"
            extraction_result, warnings = extract_from_text(
                document_text=full_text[:2000],
                document_type=classification.document_type.value,
                document_name=doc["original_filename"],
                page_info=page_info,
                llm_provider=llm,
            )
            llm_ms = int((time.time() - t1) * 1000)
            await _log_job(doc_id, "llm_extraction", "success", duration_ms=llm_ms, llm_used=True, model_name=llm.get_model_name())
        else:
            await _log_job(doc_id, "llm_extraction", "skipped")
            logger.warning(f"LLM not available — skipping extraction for {doc_id}")

        # ── Update document record ──────────────────────────
        import json
        doc_meta = {}
        if extraction_result:
            if extraction_result.title: doc_meta["title"] = extraction_result.title
            if extraction_result.authors: doc_meta["authors"] = extraction_result.authors
            if extraction_result.year: doc_meta["year"] = extraction_result.year
            if extraction_result.concept:
                if isinstance(extraction_result.concept, list):
                    doc_meta["concept"] = [str(c).strip() for c in extraction_result.concept if str(c).strip()]
                elif isinstance(extraction_result.concept, str):
                    import re
                    lines = [s.strip().lstrip("-*• ") for s in re.split(r'(?<=[.?!])\s+|\n+|•', extraction_result.concept) if len(s.strip()) > 5]
                    doc_meta["concept"] = lines or [extraction_result.concept.strip()]
            if extraction_result.highlights:
                doc_meta["highlights"] = [str(h).strip().lstrip("-*• ") for h in extraction_result.highlights if str(h).strip()]
            if extraction_result.document_summary: doc_meta["document_summary"] = extraction_result.document_summary
            if extraction_result.what_he_wants: doc_meta["what_he_wants"] = extraction_result.what_he_wants
            if extraction_result.what_he_knows: doc_meta["what_he_knows"] = extraction_result.what_he_knows
            if extraction_result.certifications_done: doc_meta["certifications"] = extraction_result.certifications_done

            p = extraction_result.personal
            personal_dict = {}
            if p.name: personal_dict["name"] = p.name
            if p.email: personal_dict["email"] = p.email
            if p.phone: personal_dict["phone"] = p.phone
            if p.location: personal_dict["location"] = p.location
            if personal_dict: doc_meta["personal"] = personal_dict

            s = extraction_result.skills
            all_skills = list(dict.fromkeys(s.programming_languages + s.frameworks + s.tools + s.databases + s.cloud + s.domain_skills))
            if all_skills and not doc_meta.get("what_he_knows"):
                doc_meta["what_he_knows"] = all_skills
            if all_skills: doc_meta["skills"] = all_skills

            edu_lines = [
                f"{e.degree or 'Degree'}{(' - ' + e.institution) if e.institution else ''}{(' (' + e.graduation_date + ')') if e.graduation_date else ''}"
                for e in extraction_result.education if (e.degree or e.institution)
            ]
            if edu_lines: doc_meta["education"] = edu_lines

            exp_lines = [
                f"{exp.designation or 'Role'}{(' at ' + exp.company) if exp.company else ''}{(' (' + (exp.start_date or '') + ' - ' + (exp.end_date or 'Present') + ')') if (exp.start_date or exp.end_date) else ''}"
                for exp in extraction_result.experience if (exp.company or exp.designation)
            ]
            if exp_lines: doc_meta["experience"] = exp_lines

        async with get_connection() as conn:
            await conn.execute(
                """UPDATE documents SET
                    processing_status = 'completed',
                    document_type = ?,
                    classification_confidence = ?,
                    classification_method = ?,
                    page_count = ?,
                    has_native_text = ?,
                    ocr_performed = ?,
                    metadata_json = ?
                   WHERE id = ?""",
                (
                    classification.document_type.value,
                    classification.confidence.value,
                    classification.method,
                    page_count,
                    1 if has_native else 0,
                    1 if ocr_used else 0,
                    json.dumps(doc_meta) if doc_meta else None,
                    doc_id,
                )
            )
            await conn.commit()

        logger.info(f"Document {doc_id} processed successfully")

        return {
            "doc_id": doc_id,
            "doc_name": doc["original_filename"],
            "page": 1,
            "result": extraction_result,
            "document_type": classification.document_type.value,
        } if extraction_result else None

    except Exception as e:
        logger.error(f"Processing error for {doc_id}: {e}", exc_info=True)
        await _mark_failed(doc_id, str(e))
        return None


async def _create_profile(extractions: list[dict]) -> None:
    """Create a consolidated profile from multiple document extractions."""
    from reconciliation.reconciler import reconcile

    reconciled = reconcile(extractions)

    profile_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_connection() as conn:
        import json

        await conn.execute(
            """INSERT INTO profiles (
                id, full_name, email, phone, location, date_of_birth,
                professional_summary, estimated_experience_level,
                estimated_experience_basis, total_documented_experience_months,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id,
                reconciled.full_name,
                reconciled.email,
                reconciled.phone,
                reconciled.location,
                reconciled.date_of_birth,
                reconciled.professional_summary,
                reconciled.estimated_level,
                reconciled.estimated_level_basis,
                reconciled.total_experience_months,
                now, now,
            )
        )

        # Link documents to profile
        for ex in extractions:
            await conn.execute(
                "INSERT OR IGNORE INTO profile_documents (profile_id, document_id) VALUES (?, ?)",
                (profile_id, ex["doc_id"])
            )

        # Save education
        for edu in reconciled.education:
            eid = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO education (id, profile_id, degree, specialization,
                   institution, university, start_date, graduation_date,
                   percentage, cgpa, education_level, source_document_id, source_page, confidence_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, profile_id, edu.get("degree"), edu.get("specialization"),
                 edu.get("institution"), edu.get("university"), edu.get("start_date"),
                 edu.get("graduation_date"), edu.get("percentage"), edu.get("cgpa"),
                 edu.get("education_level"), edu.get("source_document_id"),
                 edu.get("source_page"), "medium")
            )

        # Save experience
        for exp in reconciled.experience:
            xid = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO experience (id, profile_id, company, designation,
                   employment_type, location, start_date, end_date, is_current,
                   responsibilities, duration_months, source_document_id, source_page, confidence_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (xid, profile_id, exp.get("company"), exp.get("designation"),
                 exp.get("employment_type"), exp.get("location"),
                 exp.get("start_date"), exp.get("end_date"),
                 1 if exp.get("is_current") else 0,
                 json.dumps(exp.get("responsibilities", [])),
                 exp.get("duration_months"), exp.get("source_document_id"),
                 exp.get("source_page"), "medium")
            )

        # Save skills
        for category, skill_list in reconciled.skills.items():
            for skill in skill_list:
                sid = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO skills (id, profile_id, category, skill_name, confidence_level) VALUES (?, ?, ?, ?, ?)",
                    (sid, profile_id, category, skill, "medium")
                )

        # Save certifications
        for cert in reconciled.certifications:
            cid = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO certifications (id, profile_id, name, issuer,
                   issue_date, expiry_date, credential_id, source_document_id, source_page, confidence_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, profile_id, cert.get("name"), cert.get("issuer"),
                 cert.get("issue_date"), cert.get("expiry_date"),
                 cert.get("credential_id"), cert.get("source_document_id"),
                 cert.get("source_page"), "medium")
            )

        # Save conflicts
        for conflict in reconciled.conflicts:
            await conn.execute(
                """INSERT INTO conflicts (id, profile_id, field_name, value_a,
                   source_a_document_id, source_a_page, value_b,
                   source_b_document_id, source_b_page, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conflict.id, profile_id, conflict.field_name,
                 conflict.value_a, conflict.source_a_doc_id, conflict.source_a_page,
                 conflict.value_b, conflict.source_b_doc_id, conflict.source_b_page,
                 now)
            )

        await conn.commit()

    logger.info(f"Profile created: {profile_id} for {len(extractions)} documents")


async def _log_job(
    doc_id: str,
    stage: str,
    status: str,
    duration_ms: int = 0,
    ocr_used: bool = False,
    llm_used: bool = False,
    model_name: str = "",
    error_reason: str = "",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())
    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO processing_jobs (id, document_id, stage, started_at,
               completed_at, status, error_reason, ocr_used, llm_used, model_name, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, doc_id, stage, now, now if status != "running" else None,
             status, error_reason, 1 if ocr_used else 0,
             1 if llm_used else 0, model_name, duration_ms)
        )
        await conn.commit()


async def _mark_failed(doc_id: str, error: str) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE documents SET processing_status = 'failed', error_message = ? WHERE id = ?",
            (error[:500], doc_id)
        )
        await conn.commit()


import uuid  # already imported above but explicit at module level
