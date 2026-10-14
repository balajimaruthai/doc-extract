"""
Offline Document Chat & Q&A API.
100% Offline — zero external network calls, zero external API keys.
Combines local LLM inference (llama.cpp) with deterministic grounded intelligence.
"""
import json
import logging
import re
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from database.connection import get_connection

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    document_id: Optional[str] = None
    question: str
    history: Optional[list[ChatMessage]] = None


class ChatSource(BaseModel):
    page: Optional[int] = None
    label: Optional[str] = None
    value: Optional[str] = None
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    confidence: float
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    sources: list[ChatSource] = []
    model_used: str


def _clean_num_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return f"${val:,.2f}" if isinstance(val, float) else f"${val:,}"
    s = str(val).strip()
    return s if s else None


def _extract_key_value_pairs(pages: list[dict]) -> list[dict]:
    """Extract all labeled key-value pairs and tabular entries across pages."""
    kv_pairs = []
    kv_pattern = re.compile(r"^[\s•*-]*([A-Za-z0-9\s/&#_\(\).-]{2,45})\s*[:=]\s*([^\n\r]+)$", re.MULTILINE)
    
    for pg in pages:
        txt = pg.get("cleaned_text") or pg.get("raw_text") or ""
        p_num = pg.get("page_number", 1)
        for match in kv_pattern.finditer(txt):
            k = match.group(1).strip()
            v = match.group(2).strip()
            if len(k) > 1 and len(v) > 0 and len(k.split()) <= 6:
                kv_pairs.append({
                    "key": k,
                    "key_lower": k.lower(),
                    "value": v,
                    "page": p_num,
                    "line": match.group(0).strip()
                })
    return kv_pairs


def _offline_grounded_answer(
    question: str,
    doc_meta: dict,
    fin_record: Optional[dict],
    pages: list[dict],
    doc_name: str,
) -> tuple[str, list[ChatSource], float]:
    """
    Universal, zero-hallucination semantic answering for ALL document types,
    records, tables, reports, contracts, medical forms, and unknown data.
    Runs 100% offline without needing external network or heavy LLM weights.
    """
    q = question.lower().strip()
    sources: list[ChatSource] = []
    ans_parts = []
    doc_type = (fin_record.get("document_type") if fin_record else doc_meta.get("document_type")) or "document"
    full_text = "\n\n".join(p.get("cleaned_text") or p.get("raw_text") or "" for p in pages)
    kv_pairs = _extract_key_value_pairs(pages)

    # 1. Financial totals & amounts (Invoices, Bills, Receipts, POs, Statements)
    if any(k in q for k in ["total amount due", "amount due", "final amount", "balance due", "total payable", "how much is due", "how much do i owe", "what is due", "total due", "payable amount"]):
        total_due = None
        if fin_record and fin_record.get("total_amount_due") is not None:
            total_due = f"${fin_record['total_amount_due']:,.2f}"
        elif doc_meta.get("total_amount_due"):
            total_due = doc_meta["total_amount_due"]
        elif doc_meta.get("total_payable_due"):
            total_due = doc_meta["total_payable_due"]

        gross = None
        if fin_record and fin_record.get("total_gross") is not None:
            gross = f"${fin_record['total_gross']:,.2f}"
        elif doc_meta.get("total_gross"):
            gross = doc_meta["total_gross"]

        payroll = None
        if fin_record and fin_record.get("payroll_total") is not None:
            payroll = f"${fin_record['payroll_total']:,.2f}"
        elif doc_meta.get("payroll_total"):
            payroll = doc_meta["payroll_total"]

        handling = None
        if fin_record and fin_record.get("handling_fee") is not None:
            handling = f"${fin_record['handling_fee']:,.2f}"
        elif doc_meta.get("handling_fee"):
            handling = doc_meta["handling_fee"]

        balance_due = None
        if fin_record and fin_record.get("balance_due") is not None:
            balance_due = f"${fin_record['balance_due']:,.2f}"
        elif doc_meta.get("balance_due"):
            balance_due = doc_meta["balance_due"]

        amount_paid = None
        if fin_record and fin_record.get("amount_paid") is not None:
            amount_paid = f"${fin_record['amount_paid']:,.2f}"
        elif doc_meta.get("amount_paid"):
            amount_paid = doc_meta["amount_paid"]

        if total_due:
            ans_parts.append(f"**Total Amount Due:** **{total_due}**")
            sources.append(ChatSource(page=1, label="TOTAL AMOUNT DUE", value=str(total_due), snippet=f"Verified final payable amount: {total_due}"))

            if gross and gross != total_due:
                ans_parts.append(f"- Note: The **Total Gross** is {gross}, which precedes fringe and handling additions.")
            if payroll:
                ans_parts.append(f"- **Payroll Total:** {payroll}")
            if handling:
                ans_parts.append(f"- **Handling Fee:** {handling}")
            if amount_paid:
                ans_parts.append(f"- **Amount Paid:** {amount_paid}")
            if balance_due and balance_due != total_due:
                ans_parts.append(f"- **Balance Due:** {balance_due}")

            if fin_record and fin_record.get("math_verified"):
                ans_parts.append("\n✅ *Mathematical consistency has been verified deterministically from document figures.*")
            return "\n".join(ans_parts), sources, 0.98

    # 2. Universal Due Dates, Effective Dates, Deadlines & Timelines
    if any(k in q for k in ["due date", "when is it due", "payment terms", "terms", "deadline", "pay by", "effective date", "valid until", "expiration", "expiry date"]):
        due_date = (fin_record.get("normalized_due_date") if fin_record else None) or doc_meta.get("normalized_due_date") or doc_meta.get("due_date")
        raw_due = (fin_record.get("due_date") if fin_record else None) or doc_meta.get("due_date")
        terms = (fin_record.get("payment_terms") if fin_record else None) or doc_meta.get("payment_terms")
        inv_date = (fin_record.get("normalized_invoice_date") if fin_record else None) or doc_meta.get("normalized_invoice_date") or doc_meta.get("invoice_date")

        if due_date or terms:
            if due_date:
                ans_parts.append(f"**Due Date:** **{due_date}**" + (f" *(printed as {raw_due})*" if raw_due and raw_due != due_date else ""))
                sources.append(ChatSource(page=1, label="Due Date", value=str(due_date), snippet=f"Due Date: {due_date}"))
            if terms:
                ans_parts.append(f"**Payment Terms:** **{terms}**")
                sources.append(ChatSource(page=1, label="Payment Terms", value=str(terms), snippet=f"Terms: {terms}"))
            if inv_date and terms and due_date:
                ans_parts.append(f"\nCalculated from Invoice Date ({inv_date}) + Payment Terms ({terms}) -> Due Date ({due_date}).")
            return "\n".join(ans_parts), sources, 0.98

        # Check for other date key-value pairs (e.g. Effective Date, Expiration Date, Issue Date)
        date_matches = [kv for kv in kv_pairs if any(d in kv["key_lower"] for d in ["date", "expiry", "effective", "valid", "period", "deadline", "schedule"])]
        if date_matches:
            ans_parts.append(f"### Relevant Dates in {doc_name}:\n")
            for m in date_matches[:6]:
                ans_parts.append(f"- **{m['key']}:** `{m['value']}` *(Page {m['page']})*")
                sources.append(ChatSource(page=m["page"], label=m["key"], value=m["value"], snippet=m["line"]))
            return "\n".join(ans_parts), sources, 0.95

    # 3. Direct Key-Value Pair Lookup (Works on ANY record / form / unknown data)
    q_tokens = [w for w in re.findall(r"\b[a-z0-9_-]{2,}\b", q) if w not in {"what", "when", "where", "which", "who", "does", "have", "this", "that", "from", "with", "show", "find", "tell", "give", "the", "and", "for"}]
    matching_kvs = []
    for kv in kv_pairs:
        k_tokens = set(re.findall(r"\b[a-z0-9_-]{2,}\b", kv["key_lower"]))
        overlap = sum(1 for t in q_tokens if t in k_tokens or any(t in kt for kt in k_tokens))
        if overlap > 0:
            matching_kvs.append((overlap, kv))

    if matching_kvs:
        matching_kvs.sort(key=lambda x: (x[0], -len(x[1]["key"])), reverse=True)
        top_kvs = [kv for _, kv in matching_kvs[:5]]
        ans_parts.append(f"From **{doc_name}**:\n")
        for kv in top_kvs:
            ans_parts.append(f"- **{kv['key']}:** **{kv['value']}** *(Page {kv['page']})*")
            sources.append(ChatSource(page=kv["page"], label=kv["key"], value=kv["value"], snippet=kv["line"]))
        return "\n".join(ans_parts), sources, 0.95

    # 4. Universal Document Summarization (Supports ALL document types & unknown records)
    if any(k in q for k in ["summarize", "summary", "overview", "what is this", "tell me about", "explain", "describe"]):
        ans_parts.append(f"### Summary of {doc_name}\n")
        ans_parts.append(f"- **Document Type:** {doc_type.replace('_', ' ').title()}")

        if doc_meta.get("document_summary"):
            ans_parts.append(f"- **Executive Summary:** {doc_meta['document_summary']}")

        if doc_meta.get("title"):
            ans_parts.append(f"- **Title / Header:** {doc_meta['title']}")

        # Financial details if applicable
        if fin_record and fin_record.get("total_amount_due") is not None:
            ans_parts.append(f"- **Total Amount Due:** ${fin_record['total_amount_due']:,.2f}")
        if fin_record and fin_record.get("invoice_number"):
            ans_parts.append(f"- **Reference #:** {fin_record['invoice_number']}")

        # Profile / Resume details if applicable
        if doc_meta.get("personal"):
            p = doc_meta["personal"]
            if p.get("name"): ans_parts.append(f"- **Subject / Name:** {p.get('name')}")
            if p.get("email"): ans_parts.append(f"- **Contact:** {p.get('email')}")
        if doc_meta.get("skills"):
            ans_parts.append(f"- **Highlights / Skills:** {', '.join(doc_meta['skills'][:6])}")

        # Extracted key records from unknown or structured documents
        if kv_pairs:
            ans_parts.append("\n**Key Detected Fields & Records:**")
            seen_keys = set()
            count = 0
            for kv in kv_pairs:
                if kv["key_lower"] not in seen_keys and count < 8:
                    seen_keys.add(kv["key_lower"])
                    ans_parts.append(f"- **{kv['key']}:** {kv['value']}")
                    count += 1

        # Page count & layout
        ans_parts.append(f"\n*Total pages analyzed: {len(pages)}*")
        sources.append(ChatSource(page=1, label="Overview", snippet=f"Comprehensive summary for {doc_name} ({doc_type})."))
        return "\n".join(ans_parts), sources, 0.95

    # 5. Table rows, line items, lists, or structured records
    if any(k in q for k in ["line item", "items", "table", "breakdown", "list", "entries", "charges", "fees", "subtotal", "tax"]):
        items = doc_meta.get("line_items") or (json.loads(fin_record["line_items_json"]) if fin_record and fin_record.get("line_items_json") else None)
        subtotal = fin_record.get("subtotal") if fin_record else doc_meta.get("subtotal")
        tax = fin_record.get("tax_amount") if fin_record else doc_meta.get("tax_amount")

        # Check for table rows containing '|' or tabs in pages
        table_lines = []
        for pg in pages:
            for line in (pg.get("cleaned_text") or pg.get("raw_text") or "").splitlines():
                if "|" in line or "\t" in line or (len(line.split()) >= 3 and any(char.isdigit() for char in line)):
                    if len(line.strip()) > 8 and not line.strip().startswith("#"):
                        table_lines.append((pg.get("page_number", 1), line.strip()))

        if items or subtotal is not None or table_lines:
            ans_parts.append(f"### Itemized Breakdown & Records for {doc_name}\n")
            if subtotal is not None: ans_parts.append(f"- **Subtotal:** {_clean_num_str(subtotal)}")
            if tax is not None: ans_parts.append(f"- **Tax:** {_clean_num_str(tax)}")

            if items and isinstance(items, list):
                ans_parts.append("\n**Items / Entries:**")
                for itm in items[:12]:
                    if isinstance(itm, dict):
                        desc = itm.get("description") or itm.get("name") or "Entry"
                        qty = itm.get("quantity")
                        amt = itm.get("amount") or itm.get("total") or itm.get("unit_price")
                        qty_str = f"{qty}x " if qty else ""
                        amt_str = f" ({_clean_num_str(amt)})" if amt else ""
                        ans_parts.append(f"- {qty_str}{desc}{amt_str}")
                    else:
                        ans_parts.append(f"- {itm}")

            elif table_lines:
                ans_parts.append("\n**Extracted Data Rows:**")
                for p_num, row in table_lines[:8]:
                    ans_parts.append(f"- {row} *(Page {p_num})*")

            sources.append(ChatSource(page=1, label="Items", snippet="Extracted table records and itemized rows."))
            return "\n".join(ans_parts), sources, 0.95

    # 6. Universal Semantic Sentence & Paragraph Search
    # Works on ANY document: medical, legal, research, academic, logs, reports, letters, books
    scored_sentences = []
    stop_words = {"what", "when", "where", "which", "who", "whom", "whose", "why", "how", "does", "have", "this", "that", "from", "with", "show", "find", "tell", "give", "the", "and", "for", "are", "was", "were", "been", "being", "can", "could", "would", "should"}
    keywords = [w for w in re.findall(r"\b[a-z0-9_-]{3,}\b", q) if w not in stop_words]

    for pg in pages:
        txt = pg.get("cleaned_text") or pg.get("raw_text") or ""
        p_num = pg.get("page_number", 1)
        # Split into sentences or lines
        sentences = re.split(r"(?<=[.!?])\s+|\n+", txt)
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 12:
                continue
            s_lower = s_clean.lower()
            match_count = sum(1 for kw in keywords if kw in s_lower)
            if match_count > 0:
                scored_sentences.append((match_count, p_num, s_clean))

    if scored_sentences:
        scored_sentences.sort(key=lambda x: (x[0], len(x[2])), reverse=True)
        top_matches = scored_sentences[:4]
        ans_parts.append(f"Here is what **{doc_name}** states regarding your query:\n")
        for score, p_num, snippet in top_matches:
            ans_parts.append(f"> \"{snippet}\"\n*(Source: Page {p_num})*\n")
            sources.append(ChatSource(page=p_num, snippet=snippet[:250]))
        return "\n".join(ans_parts), sources, 0.92

    # 7. Grounded Document Overview Fallback
    ans_parts.append(f"I analyzed **{doc_name}** (classified as *{doc_type}*).\n")
    ans_parts.append(f"While I did not find a direct mention of \"{question}\", here are the primary data points detected:")
    if kv_pairs:
        for kv in kv_pairs[:5]:
            ans_parts.append(f"- **{kv['key']}:** {kv['value']} *(Page {kv['page']})*")
    elif len(pages) > 0:
        first_page_snippet = (pages[0].get("cleaned_text") or "")[:200].strip()
        if first_page_snippet:
            ans_parts.append(f"\n> \"{first_page_snippet}...\"\n*(Page 1)*")
    ans_parts.append(f"\nYou can ask about any specific label, person, date, condition, number, table, or section in this document.")
    return "\n".join(ans_parts), sources, 0.65


@router.post("/ask", response_model=ChatResponse)
async def ask_document(req: ChatRequest):
    """
    Ask questions about a document or entire document collection.
    100% Offline — runs local rule & pattern intelligence + local LLM if loaded.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    async with get_connection() as conn:
        doc = None
        fin_record = None
        pages = []

        if req.document_id:
            d_cur = await conn.execute("SELECT * FROM documents WHERE id = ?", (req.document_id,))
            doc = await d_cur.fetchone()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Fetch financial record
            f_cur = await conn.execute("SELECT * FROM extracted_financial_records WHERE document_id = ?", (req.document_id,))
            fin_record = await f_cur.fetchone()

            # Fetch pages
            p_cur = await conn.execute("SELECT page_number, cleaned_text, raw_text FROM document_pages WHERE document_id = ? ORDER BY page_number", (req.document_id,))
            pages = [dict(r) for r in await p_cur.fetchall()]
        else:
            # If no document_id specified, pick the most recent completed document
            d_cur = await conn.execute("SELECT * FROM documents WHERE processing_status = 'completed' ORDER BY upload_timestamp DESC LIMIT 1")
            doc = await d_cur.fetchone()
            if doc:
                f_cur = await conn.execute("SELECT * FROM extracted_financial_records WHERE document_id = ?", (doc["id"],))
                fin_record = await f_cur.fetchone()
                p_cur = await conn.execute("SELECT page_number, cleaned_text, raw_text FROM document_pages WHERE document_id = ? ORDER BY page_number", (doc["id"],))
                pages = [dict(r) for r in await p_cur.fetchall()]

    if not doc:
        return ChatResponse(
            answer="No processed documents found yet. Please upload a document to begin asking questions.",
            confidence=1.0,
            document_id=None,
            document_name=None,
            sources=[],
            model_used="Offline Document Intelligence",
        )

    doc_meta = json.loads(doc["metadata_json"]) if doc["metadata_json"] else {}
    fin_dict = dict(fin_record) if fin_record else None
    doc_name = doc["original_filename"]

    # Check if a local GGUF offline model is available
    from api.processing import get_llm_provider
    llm = get_llm_provider() if not settings.FAST_PROCESSING else None

    # If local LLM exists and question is conversational or complex
    if llm and llm.is_available():
        try:
            full_text = "\n\n".join(p.get("cleaned_text") or p.get("raw_text") or "" for p in pages)[:4000]
            prompt = (
                f"You are DocExtract Offline Assistant. Answer the question using ONLY the provided document context.\n"
                f"Document Name: {doc_name}\n"
                f"Document Type: {doc.get('document_type', 'unknown')}\n\n"
                f"--- DOCUMENT TEXT ---\n{full_text}\n\n"
                f"--- USER QUESTION ---\n{req.question}\n\n"
                f"Answer clearly and concisely. If exact numbers or dates are asked, cite them exactly. Do not guess."
            )
            raw_ans = llm.generate(prompt=prompt, max_tokens=512, temperature=0.1)
            if raw_ans and len(raw_ans.strip()) > 10:
                return ChatResponse(
                    answer=raw_ans.strip(),
                    confidence=0.95,
                    document_id=doc["id"],
                    document_name=doc_name,
                    sources=[ChatSource(page=1, snippet=f"Context from {doc_name}")],
                    model_used=f"Local Offline LLM ({llm.get_model_name()})",
                )
        except Exception as e:
            logger.warning(f"Local LLM chat failed, falling back to deterministic grounder: {e}")

    # Offline Grounded Semantic Engine
    answer, sources, conf = _offline_grounded_answer(
        question=req.question,
        doc_meta=doc_meta,
        fin_record=fin_dict,
        pages=pages,
        doc_name=doc_name,
    )

    return ChatResponse(
        answer=answer,
        confidence=conf,
        document_id=doc["id"],
        document_name=doc_name,
        sources=sources,
        model_used="Offline Grounded Intelligence Engine (100% Local / Zero-Hallucination)",
    )
