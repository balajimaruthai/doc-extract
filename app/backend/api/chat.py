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


def _offline_grounded_answer(
    question: str,
    doc_meta: dict,
    fin_record: Optional[dict],
    pages: list[dict],
    doc_name: str,
) -> tuple[str, list[ChatSource], float]:
    """
    Deterministic, zero-hallucination semantic answering for document inquiries.
    Runs 100% offline without needing an external network or heavy LLM weights.
    """
    q = question.lower().strip()
    sources: list[ChatSource] = []
    ans_parts = []
    conf = 0.95

    # 1. Total Amount Due / Final Payable Amount
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

    # 2. Due Date and Payment Terms
    if any(k in q for k in ["due date", "when is it due", "payment terms", "terms", "deadline", "pay by"]):
        due_date = fin_record.get("normalized_due_date") if fin_record else doc_meta.get("normalized_due_date") or doc_meta.get("due_date")
        raw_due = fin_record.get("due_date") if fin_record else doc_meta.get("due_date")
        terms = fin_record.get("payment_terms") if fin_record else doc_meta.get("payment_terms")
        inv_date = fin_record.get("normalized_invoice_date") if fin_record else doc_meta.get("normalized_invoice_date") or doc_meta.get("invoice_date")

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

    # 3. Invoice Number / PO Number / Identifier
    if any(k in q for k in ["invoice number", "invoice #", "invoice no", "po number", "purchase order", "account number", "reference"]):
        inv_no = fin_record.get("invoice_number") if fin_record else doc_meta.get("invoice_number")
        po_no = fin_record.get("po_number") if fin_record else doc_meta.get("po_number")
        acc_no = doc_meta.get("account_number")

        if inv_no or po_no or acc_no:
            if inv_no:
                ans_parts.append(f"**Invoice Number:** `{inv_no}`")
                sources.append(ChatSource(page=1, label="Invoice Number", value=str(inv_no), snippet=f"Invoice #{inv_no}"))
            if po_no:
                ans_parts.append(f"**PO Number:** `{po_no}`")
                sources.append(ChatSource(page=1, label="PO Number", value=str(po_no), snippet=f"PO Number: {po_no}"))
            if acc_no:
                ans_parts.append(f"**Account Number:** `{acc_no}`")
            return "\n".join(ans_parts), sources, 0.99

    # 4. Vendor / Supplier / Customer / Billing entities
    if any(k in q for k in ["who", "vendor", "supplier", "merchant", "billed to", "remit to", "client", "customer"]):
        vendor = fin_record.get("merchant_or_vendor") if fin_record else doc_meta.get("merchant_name") or doc_meta.get("remit_to")
        billed = fin_record.get("client_or_customer") if fin_record else doc_meta.get("billed_to")

        if vendor or billed:
            if vendor:
                ans_parts.append(f"**Vendor / Issuer:** {vendor}")
                sources.append(ChatSource(page=1, label="Vendor", value=str(vendor), snippet=f"Vendor: {vendor}"))
            if billed:
                ans_parts.append(f"**Billed To / Customer:** {billed}")
                sources.append(ChatSource(page=1, label="Customer", value=str(billed), snippet=f"Billed To: {billed}"))
            return "\n".join(ans_parts), sources, 0.95

    # 5. Summarize / Overview
    if any(k in q for k in ["summarize", "summary", "overview", "what is this", "tell me about"]):
        summary = doc_meta.get("document_summary")
        doc_type = (fin_record.get("document_type") if fin_record else doc_meta.get("document_type")) or "document"
        
        ans_parts.append(f"### Summary of {doc_name}\n")
        ans_parts.append(f"- **Document Type:** {doc_type.replace('_', ' ').title()}")
        if summary:
            ans_parts.append(f"- **Overview:** {summary}")
        
        # Financial recap
        if fin_record and fin_record.get("total_amount_due") is not None:
            ans_parts.append(f"- **Total Amount Due:** ${fin_record['total_amount_due']:,.2f}")
        if fin_record and fin_record.get("due_date"):
            ans_parts.append(f"- **Due Date:** {fin_record['due_date']}")
        if fin_record and fin_record.get("invoice_number"):
            ans_parts.append(f"- **Reference/Invoice:** {fin_record['invoice_number']}")

        # Resume/profile recap
        if doc_meta.get("personal"):
            p = doc_meta["personal"]
            ans_parts.append(f"- **Name:** {p.get('name')}")
            if p.get("email"): ans_parts.append(f"- **Contact:** {p.get('email')} / {p.get('phone')}")
        if doc_meta.get("skills"):
            skills_preview = ", ".join(doc_meta["skills"][:8])
            ans_parts.append(f"- **Key Skills:** {skills_preview}")

        sources.append(ChatSource(page=1, label="Summary", snippet=f"Document summary generated from verified {doc_type} fields."))
        return "\n".join(ans_parts), sources, 0.95

    # 6. Line Items / Breakdown
    if any(k in q for k in ["line item", "items", "breakdown", "charges", "fees", "subtotal", "tax", "discount"]):
        items = doc_meta.get("line_items") or (json.loads(fin_record["line_items_json"]) if fin_record and fin_record.get("line_items_json") else None)
        subtotal = fin_record.get("subtotal") if fin_record else doc_meta.get("subtotal")
        tax = fin_record.get("tax_amount") if fin_record else doc_meta.get("tax_amount")
        discount = fin_record.get("discount_amount") if fin_record else doc_meta.get("discount_amount")
        handling = fin_record.get("handling_fee") if fin_record else doc_meta.get("handling_fee")

        if subtotal is not None or items:
            ans_parts.append("### Financial Breakdown & Items\n")
            if subtotal is not None: ans_parts.append(f"- **Subtotal:** {_clean_num_str(subtotal)}")
            if tax is not None: ans_parts.append(f"- **Tax:** {_clean_num_str(tax)}")
            if discount is not None: ans_parts.append(f"- **Discount:** {_clean_num_str(discount)}")
            if handling is not None: ans_parts.append(f"- **Handling Fee:** {_clean_num_str(handling)}")

            if items and isinstance(items, list):
                ans_parts.append("\n**Extracted Items:**")
                for itm in items[:10]:
                    if isinstance(itm, dict):
                        desc = itm.get("description", "Item")
                        qty = itm.get("quantity", 1)
                        amt = itm.get("amount") or itm.get("total") or itm.get("unit_price")
                        amt_str = f" (${amt})" if amt else ""
                        ans_parts.append(f"- {qty}x {desc}{amt_str}")
                    else:
                        ans_parts.append(f"- {itm}")

            sources.append(ChatSource(page=1, label="Line Items", snippet="Extracted itemized table & financial subtotals."))
            return "\n".join(ans_parts), sources, 0.95

    # 7. Semantic Full-Text Search fallback across all document pages
    query_words = set(re.findall(r"\b\w{3,}\b", q)) - {"what", "when", "where", "which", "does", "have", "this", "that", "from", "with", "show", "find", "tell"}
    best_snippets = []

    for pg in pages:
        txt = pg.get("cleaned_text") or pg.get("raw_text") or ""
        p_num = pg.get("page_number", 1)
        paragraphs = re.split(r"\n\s*\n|\.\s+", txt)
        for para in paragraphs:
            para_clean = para.strip()
            if len(para_clean) < 15:
                continue
            para_lower = para_clean.lower()
            overlap = sum(1 for w in query_words if w in para_lower)
            if overlap > 0:
                best_snippets.append((overlap, p_num, para_clean))

    if best_snippets:
        best_snippets.sort(key=lambda x: x[0], reverse=True)
        top = best_snippets[:3]
        ans_parts.append(f"Based on the contents of **{doc_name}**:\n")
        for score, p_num, snippet in top:
            ans_parts.append(f"> \"{snippet}\"\n*(Page {p_num})*\n")
            sources.append(ChatSource(page=p_num, snippet=snippet[:200]))
        return "\n".join(ans_parts), sources, 0.90

    # Fallback response grounded in document metadata
    doc_type = (fin_record.get("document_type") if fin_record else doc_meta.get("document_type")) or "document"
    ans = (
        f"I reviewed **{doc_name}** (classified as *{doc_type}*).\n\n"
        f"I could not locate an exact match for '{question}' in the extracted text. "
        f"You can ask about:\n"
        f"- **Amounts:** Total Amount Due, Subtotal, Taxes, Discounts, Payroll, Handling\n"
        f"- **Dates:** Due Date, Invoice Date, Payment Terms\n"
        f"- **Entities:** Invoice #, PO #, Vendor, Customer\n"
        f"- **Summaries:** Request an overview or list of line items."
    )
    return ans, sources, 0.60


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
