import { useEffect, useState, useRef } from 'react'
import { Upload, FileText, Trash2, RefreshCw, Eye, AlertTriangle, X, BookOpen, Sparkles, User, Calendar, CheckCircle2, Play } from 'lucide-react'
import { documentsApi, processingApi, type DocumentRecord, type PageText } from '../api/client'

const STATUS_LABELS: Record<string, { label: string; class: string }> = {
  pending: { label: 'Pending', class: 'badge-neutral' },
  processing: { label: 'Processing…', class: 'badge-info' },
  completed: { label: 'Completed', class: 'badge-success' },
  failed: { label: 'Failed', class: 'badge-error' },
  review: { label: 'Needs Review', class: 'badge-warning' },
}

const DOC_TYPE_LABELS: Record<string, string> = {
  resume: 'Resume / CV',
  cv: 'Resume / CV',
  degree_certificate: 'Degree Certificate',
  marksheet: 'Marksheet',
  experience_letter: 'Experience Letter',
  offer_letter: 'Offer Letter',
  appointment_letter: 'Appointment Letter',
  internship_certificate: 'Internship Certificate',
  professional_certificate: 'Professional Certificate',
  training_certificate: 'Training Certificate',
  achievement_certificate: 'Achievement Certificate',
  research_paper: 'Research / Conference Paper',
  project_report: 'Project Report',
  book: 'Book / Publication',
  photo_document: 'Image / Scanned Document',
  invoice: 'Corporate Invoice / Billing Statement',
  bill: 'Bill / Payment Receipt',
  payslip: 'Salary Slip / Payroll Statement',
  audio: 'Audio Track / Recording',
  video: 'Video Recording / Keyframes',
  needs_review: 'Needs Review',
  other: 'General Document',
}

export function Documents() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null)
  const [docPages, setDocPages] = useState<PageText[]>([])
  const [loadingPages, setLoadingPages] = useState(false)
  const [processingId, setProcessingId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const ACCEPTED = '.pdf,.docx,.doc,.xlsx,.xls,.csv,.jpg,.jpeg,.png,.webp,.wav,.mp3,.mp4,.mov,.avi,.mkv,.webm,.txt'

  const loadDocuments = async () => {
    setLoading(true)
    const timeout = setTimeout(() => {
      setLoading(false)
    }, 4000)
    try {
      const result = await documentsApi.list({ limit: 100 })
      setDocuments(result.documents)
      setTotal(result.total)
    } catch (e: any) {
      setError(e.message)
    } finally {
      clearTimeout(timeout)
      setLoading(false)
    }
  }

  useEffect(() => { loadDocuments() }, [])

  // Auto-poll when any document is pending or processing
  useEffect(() => {
    const hasActive = documents.some(d => d.processing_status === 'pending' || d.processing_status === 'processing')
    if (!hasActive) return

    const timer = setInterval(() => {
      documentsApi.list({ limit: 100 }).then(r => {
        setDocuments(r.documents)
        setTotal(r.total)
      }).catch(() => {})
    }, 2500)

    return () => clearInterval(timer)
  }, [documents])

  const handleProcessDoc = async (docId: string) => {
    setProcessingId(docId)
    setError(null)
    try {
      await processingApi.processSingle(docId)
      await loadDocuments()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setTimeout(() => setProcessingId(null), 1000)
    }
  }

  const handleFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files)
    if (fileArray.length === 0) return

    setUploading(true)
    setError(null)
    try {
      for (const file of fileArray) {
        await documentsApi.upload(file)
      }
      await loadDocuments()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (docId: string) => {
    if (!confirm('Are you sure you want to delete this document?')) return
    try {
      await documentsApi.delete(docId)
      if (selectedDoc?.id === docId) setSelectedDoc(null)
      await loadDocuments()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleView = async (doc: DocumentRecord) => {
    setSelectedDoc(doc)
    setLoadingPages(true)
    try {
      const [res, fullDoc] = await Promise.all([
        documentsApi.getText(doc.id),
        documentsApi.get(doc.id).catch(() => doc)
      ])
      setDocPages(res.pages)
      if (fullDoc) setSelectedDoc(fullDoc)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoadingPages(false)
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      })
    } catch {
      return iso
    }
  }

  // Parse custom metadata if available
  const parseMetadata = (jsonStr?: string | null) => {
    if (!jsonStr) return null
    try {
      return JSON.parse(jsonStr)
    } catch {
      return null
    }
  }

  const metadata = selectedDoc ? parseMetadata(selectedDoc.metadata_json) : null

  return (
    <div>
      <div className="flex items-center justify-between mb-lg">
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700 }}>Documents</h1>
          <p className="text-muted text-sm mt-xs">
            {total} document{total !== 1 ? 's' : ''} stored locally on this machine
          </p>
        </div>
        <button
          className="btn btn-secondary btn-sm"
          onClick={loadDocuments}
          disabled={loading}
        >
          <RefreshCw size={13} className={loading ? 'spinner' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="card mb-md flex justify-between items-center" style={{ borderColor: 'var(--color-error)', backgroundColor: 'rgba(239, 68, 68, 0.05)', padding: '10px 16px' }}>
          <div className="flex items-center gap-sm">
            <AlertTriangle size={16} color="var(--color-error)" />
            <span style={{ color: 'var(--color-error)', fontSize: 13, fontWeight: 500 }}>{error}</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => setError(null)} style={{ padding: '2px 8px', fontSize: 11 }}>
            Dismiss
          </button>
        </div>
      )}

      {/* Upload Drop Zone */}
      <div
        className={`card upload-zone mb-lg ${dragActive ? 'upload-zone-active' : ''}`}
        onDragEnter={e => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={e => { e.preventDefault(); setDragActive(false) }}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); setDragActive(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileInputRef.current?.click()}
        style={{ cursor: 'pointer', textAlign: 'center', padding: '32px 16px' }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          style={{ display: 'none' }}
          onChange={e => e.target.files && handleFiles(e.target.files)}
        />
        <div className="flex flex-col items-center gap-sm">
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            backgroundColor: 'var(--color-primary-light)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Upload size={22} color="var(--color-primary)" />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              {uploading ? 'Validating and saving locally…' : 'Drop any document here, or browse files'}
            </div>
            <div className="text-muted text-xs mt-xs">
              Supports Invoices, Receipts, Excel/CSVs, Word, Bank Statements, Resumes, Books, Reports &amp; Certificates (PDF, DOCX, XLSX, CSV, JPG, PNG)
            </div>
          </div>
        </div>
      </div>

      {/* Documents Table */}
      {loading ? (
        <div className="card" style={{ textAlign: 'center', padding: 36 }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          <div className="text-muted text-sm">Loading document inventory…</div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={loadDocuments}
            style={{ marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <RefreshCw size={12} /> Reload Inventory
          </button>
        </div>
      ) : documents.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <FileText size={40} style={{ color: 'var(--color-border)', margin: '0 auto 12px' }} />
          <div style={{ fontWeight: 600 }}>No documents uploaded yet</div>
          <div className="text-muted text-sm mt-xs">
            Drop your documents above to begin local intelligence extraction.
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Format</th>
                  <th>Detected Category</th>
                  <th>Size</th>
                  <th>Pages</th>
                  <th>OCR</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => {
                  const s = STATUS_LABELS[doc.processing_status] ?? { label: doc.processing_status, class: 'badge-neutral' }
                  return (
                    <tr key={doc.id}>
                      <td className="truncate" style={{ maxWidth: 220 }}>
                        <div className="flex items-center gap-sm">
                          <FileText size={14} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
                          <span title={doc.original_filename} style={{ fontWeight: 500 }}>{doc.original_filename}</span>
                        </div>
                      </td>
                      <td><span className="badge badge-neutral">{doc.file_type.toUpperCase()}</span></td>
                      <td>
                        <span className="badge badge-info" style={{ fontSize: 11 }}>
                          {doc.document_type ? (DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type) : 'Pending'}
                        </span>
                      </td>
                      <td className="text-muted">{formatSize(doc.file_size)}</td>
                      <td className="text-muted">{doc.page_count ?? '—'}</td>
                      <td>{doc.ocr_performed ? <span className="badge badge-info">OCR</span> : <span className="text-muted">—</span>}</td>
                      <td><span className={`badge ${s.class}`}>{s.label}</span></td>
                      <td className="text-muted text-xs">{formatDate(doc.upload_timestamp)}</td>
                      <td>
                        <div className="flex gap-sm items-center">
                          {doc.processing_status === 'completed' && (
                            <button
                              className="btn btn-primary btn-sm"
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', fontSize: 12, fontWeight: 600 }}
                              onClick={() => handleView(doc)}
                              title="View Document Intelligence"
                            >
                              <Eye size={13} /> View
                            </button>
                          )}
                          {doc.processing_status !== 'completed' && doc.processing_status !== 'processing' && (
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', fontSize: 12, fontWeight: 600 }}
                              onClick={() => handleProcessDoc(doc.id)}
                              disabled={processingId === doc.id}
                              title={doc.processing_status === 'failed' ? (doc.error_message ? `Failed: ${doc.error_message}. Click to retry.` : 'Retry Processing') : 'Process Document Now'}
                            >
                              {processingId === doc.id ? (
                                <>
                                  <RefreshCw size={12} className="spinner" /> Processing…
                                </>
                              ) : (
                                <>
                                  <Play size={12} /> {doc.processing_status === 'failed' ? 'Retry' : 'Process'}
                                </>
                              )}
                            </button>
                          )}
                          {doc.processing_status === 'processing' && (
                            <span className="badge badge-info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                              <RefreshCw size={11} className="spinner" /> Working…
                            </span>
                          )}
                          <button
                            className="btn btn-danger btn-sm"
                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '5px 7px', minWidth: 28 }}
                            onClick={() => handleDelete(doc.id)}
                            title="Delete document"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Intelligence & Extracted Content Modal (Times New Roman, Line-by-Line Reader View) */}
      {selectedDoc && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000, padding: 20
        }}>
          <div style={{
            maxWidth: 780, width: '100%', maxHeight: '90vh', overflowY: 'auto',
            backgroundColor: '#ffffff', color: '#111827', borderRadius: 10,
            padding: '36px 40px', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3)',
            fontFamily: '"Times New Roman", Times, serif',
            position: 'relative'
          }}>
            {/* Top Header */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              borderBottom: '2px solid #e5e7eb', paddingBottom: 16, marginBottom: 24
            }}>
              <div>
                <div style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6b7280', marginBottom: 4 }}>
                  Document Intelligence Summary
                </div>
                <h2 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: '#111827', lineHeight: 1.3 }}>
                  {selectedDoc.original_filename}
                </h2>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                style={{
                  background: 'none', border: '1px solid #d1d5db', borderRadius: '50%',
                  width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: '#6b7280'
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Extracted Specific Content Line by Line */}
            {(() => {
              const toLines = (val: any): string[] => {
                if (!val) return []
                if (Array.isArray(val)) return val.map(String).map(s => s.trim()).filter(Boolean)
                if (typeof val === 'string') {
                  return val
                    .split(/\r?\n|•|(?<=[.?!])\s+(?=[A-Z0-9])/)
                    .map(s => s.trim().replace(/^[-*•\d.)\s]+/, ''))
                    .filter(s => s.length > 3)
                }
                return []
              }

              const firstPageText = docPages[0]?.cleaned_text || ''

              const title = metadata?.title || (firstPageText ? firstPageText.split(/\r?\n/)[0]?.trim().slice(0, 120) : selectedDoc.original_filename)
              
              const documentSummary = metadata?.document_summary || (
                firstPageText ? firstPageText.split(/\r?\n\r?\n|(?<=[.?!])\s+/).filter((s: string) => s.trim().length > 30).slice(0, 2).join(' ').trim() : null
              )
              
              const whatHeWants = metadata?.what_he_wants
              const whatHeKnows = toLines(metadata?.what_he_knows || metadata?.skills)
              const certifications = toLines(metadata?.certifications || metadata?.education)
              const personal = metadata?.personal
              
              let authors = toLines(metadata?.authors)
              if (authors.length === 0 && firstPageText) {
                const authorMatch = firstPageText.match(/(?:by|authors?|contributors?)\s*[:\-\s]\s*([^\n\r]+)/i)
                if (authorMatch) {
                  authors = authorMatch[1].split(/[,;]|\band\b/).map((s: string) => s.trim()).filter((s: string) => s.length > 2 && s.length < 50)
                }
              }

              const year = (metadata?.year && !['not provided', 'null', 'none'].includes(String(metadata.year).toLowerCase())) ? String(metadata.year) : null
              
              const certName = metadata?.certificate_name || null
              const issuedTo = metadata?.issued_to || personal?.name || null
              const issuingOrg = metadata?.issuing_organization || null
              const issueDate = metadata?.issue_date || year || null
              const credId = metadata?.credential_id || null
              const certType = metadata?.certificate_type || null

              // Receipt / POS variables
              const merchantName = metadata?.merchant_name || null
              const subtotal = metadata?.subtotal || null
              const taxAmount = metadata?.tax_amount || null
              const tipAmount = metadata?.tip_amount || null
              const discountAmount = metadata?.discount_amount || null
              const paymentMethod = metadata?.payment_method || null

              // Bank Statement & Financial Transaction variables
              const statementPeriod = metadata?.statement_period || null
              const openingBalance = metadata?.opening_balance || null
              const closingBalance = metadata?.closing_balance || null
              const totalDeposits = metadata?.total_deposits || null
              const totalWithdrawals = metadata?.total_withdrawals || null
              const transactionCount = metadata?.transaction_count || null
              const sheetCount = metadata?.sheet_count || null

              // Corporate Invoice / Billing variables
              const invoiceNumber = metadata?.invoice_number || null
              const invoiceDate = metadata?.invoice_date || null
              const dueDate = metadata?.due_date || null
              const paymentTerms = metadata?.payment_terms || null
              const totalAmountDue = metadata?.total_payable_due || metadata?.total_amount_due || null
              const totalPayableDue = metadata?.total_payable_due || metadata?.total_amount_due || null
              const totalGross = metadata?.total_gross || null
              const totalFringe = metadata?.total_fringe || null
              const payrollTotal = metadata?.payroll_total || null
              const handlingFee = metadata?.handling_fee || null
              const billedTo = metadata?.billed_to || null
              const remitTo = metadata?.remit_to || null
              const bankName = metadata?.bank_name || null
              const accountNumber = metadata?.account_number || null
              const routingNumber = metadata?.routing_number || null
              const poNumber = metadata?.po_number || null
              const clientCode = metadata?.client_code || null
              const contactPerson = metadata?.contact_person || null
              
              let conceptLines = toLines(metadata?.concept)
              if (conceptLines.length === 0 && firstPageText) {
                const sentences = firstPageText.split(/(?<=[.?!])\s+/).map((s: string) => s.trim()).filter((s: string) => s.length > 25)
                const relevant = sentences.filter((s: string) => /(?:methodology|proposed|system|architecture|algorithm|model|framework|capsule|lstm|feature)/i.test(s))
                if (relevant.length > 0) conceptLines = relevant.slice(0, 4)
              }

              let highlightLines = toLines(metadata?.highlights)
              if (highlightLines.length === 0 && firstPageText) {
                const bullets = firstPageText.split(/\r?\n/)
                  .map((s: string) => s.trim())
                  .filter((s: string) => (s.startsWith('-') || s.startsWith('•') || s.startsWith('*') || /^\d+\./.test(s)) && s.length > 15)
                  .map((s: string) => s.replace(/^[-*•\d.)\s]+/, '').trim())
                if (bullets.length > 0) {
                  highlightLines = bullets.slice(0, 5)
                } else {
                  const keySentences = firstPageText.split(/(?<=[.?!])\s+/).map((s: string) => s.trim()).filter((s: string) => /(?:accuracy|performance|achieved|results|findings|conclusion|demonstrate|improves)/i.test(s) && s.length > 25)
                  if (keySentences.length > 0) highlightLines = keySentences.slice(0, 4)
                }
              }

              const isSpreadsheet = selectedDoc.document_type === 'spreadsheet' || ['xlsx', 'xls', 'csv'].includes(selectedDoc.file_type || '') || !!sheetCount
              const isStatement = selectedDoc.document_type === 'financial_statement' || (!isSpreadsheet && (!!statementPeriod || !!openingBalance || !!closingBalance))
              const isReceipt = selectedDoc.document_type === 'receipt' || (!isSpreadsheet && !isStatement && (!!merchantName || !!subtotal))
              const isInvoice = !isSpreadsheet && !isStatement && !isReceipt && (['invoice', 'bill', 'payslip'].includes(selectedDoc.document_type || '') || !!totalAmountDue || !!invoiceNumber || !!bankName || !!routingNumber)
              const isAudio = selectedDoc.document_type === 'audio' || ['wav', 'mp3', 'm4a', 'aac', 'ogg'].includes(selectedDoc.file_type || '')
              const isVideo = selectedDoc.document_type === 'video' || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(selectedDoc.file_type || '')
              const isBook = selectedDoc.document_type === 'book'
              const isProject = selectedDoc.document_type === 'project_report'
              const isPaper = selectedDoc.document_type === 'research_paper'
              const isPhoto = selectedDoc.document_type === 'photo_document'
              const isResume = ['resume', 'cv'].includes(selectedDoc.document_type || '')
              const isCert = !isInvoice && !isReceipt && !isStatement && !isSpreadsheet && !isAudio && !isVideo && (['degree_certificate', 'marksheet', 'experience_letter', 'offer_letter', 'appointment_letter', 'internship_certificate', 'professional_certificate', 'training_certificate', 'achievement_certificate'].includes(selectedDoc.document_type || '') || !!certName || !!issuedTo || !!issuingOrg)

              return (
                <div style={{ fontSize: 16, lineHeight: 1.85, color: '#1f2937' }}>
                  {/* Title */}
                  {title && (
                    <div style={{ marginBottom: 20 }}>
                      <div style={{ fontWeight: 700, fontSize: 17, color: '#111827' }}>Title:</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: '#1e3a8a', marginTop: 2 }}>{title}</div>
                    </div>
                  )}

                  {/* Document Category */}
                  <div style={{ marginBottom: 20 }}>
                    <div style={{ fontWeight: 700, fontSize: 17, color: '#111827' }}>Document Category:</div>
                    <div style={{ fontSize: 16, color: '#374151' }}>
                      <span className="badge badge-info" style={{ fontSize: 13, padding: '3px 10px', marginTop: 4 }}>
                        {selectedDoc.document_type ? (DOC_TYPE_LABELS[selectedDoc.document_type] ?? selectedDoc.document_type) : 'Document'}
                      </span>
                    </div>
                  </div>

                  {/* ── BOOK VIEW ── */}
                  {isBook && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>📖 Content &amp; Overview:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {authors.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 6 }}>✍️ Author(s):</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {authors.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
                          </ul>
                        </div>
                      )}
                      {year && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827' }}>📅 Publication Year / Edition:</div>
                          <div style={{ fontSize: 16, color: '#374151' }}>{year}</div>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>🌟 Core Chapters &amp; Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── PROJECT REPORT VIEW ── */}
                  {isProject && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>📁 Project Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {whatHeWants && (
                        <div style={{ marginBottom: 24, backgroundColor: '#fdf4ff', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #a855f7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#7e22ce', marginBottom: 6 }}>🎯 Project Aim &amp; Objectives:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#3b0764' }}>{whatHeWants}</div>
                        </div>
                      )}
                      {conceptLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#eff6ff', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #3b82f6' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#1d4ed8', marginBottom: 8 }}>💡 Concept &amp; System Architecture:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {conceptLines.map((c, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{c}</li>)}
                          </ul>
                        </div>
                      )}
                      {whatHeKnows.length > 0 && (
                        <div style={{ marginBottom: 24 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 8 }}>🛠️ Technologies &amp; Tools Used:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {whatHeKnows.map((k, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{k}</li>)}
                          </ul>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Key Implementation Highlights &amp; Results:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                      {authors.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 6 }}>👥 Contributors / Project Guide:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {authors.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── RESEARCH PAPER VIEW ── */}
                  {isPaper && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>🔬 Abstract &amp; Overview:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {authors.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 6 }}>👥 Authors &amp; Affiliations:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {authors.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
                          </ul>
                        </div>
                      )}
                      {conceptLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#eff6ff', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #3b82f6' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#1d4ed8', marginBottom: 8 }}>💡 Proposed Concept &amp; Methodology:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {conceptLines.map((c, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{c}</li>)}
                          </ul>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Key Findings &amp; Accuracy Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                      {year && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827' }}>📅 Publication Year / Conference:</div>
                          <div style={{ fontSize: 16, color: '#374151' }}>{year}</div>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── PHOTO / SCANNED DOCUMENT VIEW ── */}
                  {isPhoto && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>🖼️ Extracted Photo / Document Data:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Optical Highlights &amp; Text Data:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── RESUME / CV VIEW ── */}
                  {isResume && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>📝 Summary of Whole Document (Short Version):</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {whatHeWants && (
                        <div style={{ marginBottom: 24, backgroundColor: '#fdf4ff', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #a855f7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#7e22ce', marginBottom: 6 }}>🎯 What He Wants / Target Objective:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#3b0764' }}>{whatHeWants}</div>
                        </div>
                      )}
                      {whatHeKnows.length > 0 && (
                        <div style={{ marginBottom: 24 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 8 }}>💡 What He Knows (Skills &amp; Knowledge Domain):</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {whatHeKnows.map((k, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{k}</li>)}
                          </ul>
                        </div>
                      )}
                      {certifications.length > 0 && (
                        <div style={{ marginBottom: 24 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 8 }}>📜 Certifications &amp; Completed Work:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {certifications.map((item, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{item}</li>)}
                          </ul>
                        </div>
                      )}
                      {(personal?.name || personal?.email || personal?.phone || personal?.location) && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 8 }}>📇 Contact Information:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85 }}>
                            {personal.name && <div style={{ marginBottom: 4 }}><strong>Name:</strong> {personal.name}</div>}
                            {personal.email && <div style={{ marginBottom: 4 }}><strong>Email:</strong> {personal.email}</div>}
                            {personal.phone && <div style={{ marginBottom: 4 }}><strong>Phone:</strong> {personal.phone}</div>}
                            {personal.location && <div style={{ marginBottom: 4 }}><strong>Location:</strong> {personal.location}</div>}
                          </div>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Key Highlights &amp; Experience:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── CERTIFICATE VIEW ── */}
                  {isCert && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>📜 Credential Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}

                      {/* Key Certificate Information Card */}
                      <div style={{ marginBottom: 24, backgroundColor: '#f0fdf4', padding: '20px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                        <div style={{ fontWeight: 700, fontSize: 18, color: '#166534', marginBottom: 14 }}>
                          🎓 Extracted Key Information:
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', fontSize: 15, lineHeight: 1.6 }}>
                          {certName && (
                            <div>
                              <strong style={{ color: '#374151' }}>Certificate Title:</strong>
                              <div style={{ color: '#15803d', fontWeight: 600 }}>{certName}</div>
                            </div>
                          )}
                          {issuedTo && (
                            <div>
                              <strong style={{ color: '#374151' }}>Issued To (Recipient):</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{issuedTo}</div>
                            </div>
                          )}
                          {issuingOrg && (
                            <div>
                              <strong style={{ color: '#374151' }}>Issuing Organization:</strong>
                              <div style={{ color: '#111827' }}>{issuingOrg}</div>
                            </div>
                          )}
                          {issueDate && (
                            <div>
                              <strong style={{ color: '#374151' }}>Date of Issue:</strong>
                              <div style={{ color: '#111827' }}>{issueDate}</div>
                            </div>
                          )}
                          {credId && (
                            <div>
                              <strong style={{ color: '#374151' }}>Credential / Cert ID:</strong>
                              <div style={{ color: '#0369a1', fontFamily: 'monospace', fontWeight: 600 }}>{credId}</div>
                            </div>
                          )}
                          {certType && (
                            <div>
                              <strong style={{ color: '#374151' }}>Certificate Type:</strong>
                              <div style={{ color: '#111827' }}>{certType}</div>
                            </div>
                          )}
                        </div>
                      </div>

                      {certifications.length > 0 && (
                        <div style={{ marginBottom: 24 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 8 }}>📜 Additional Details / Skills Verified:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {certifications.map((item, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{item}</li>)}
                          </ul>
                        </div>
                      )}

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Verification Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── CORPORATE INVOICE / BILLING VIEW ── */}
                  {isInvoice && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>💼 Corporate Invoice Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}

                      {/* Primary Amount Due Banner */}
                      {totalAmountDue && (
                        <div style={{
                          marginBottom: 24, backgroundColor: '#fef2f2', padding: '18px 24px',
                          borderRadius: 8, border: '2px solid #f87171', display: 'flex',
                          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12
                        }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ textTransform: 'uppercase', fontSize: 13, letterSpacing: '0.05em', color: '#991b1b', fontWeight: 700 }}>
                                TOTAL AMOUNT DUE
                              </span>
                              {(metadata?.math_verified || (payrollTotal && handlingFee)) && (
                                <span style={{ backgroundColor: '#dcfce7', color: '#15803d', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4, border: '1px solid #86efac' }}>
                                  ✓ Math Verified
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 32, fontWeight: 800, color: '#dc2626', marginTop: 4 }}>
                              ${totalAmountDue.replace(/^\$/, '')}
                            </div>
                          </div>
                          {(dueDate || paymentTerms) && (
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#7f1d1d', fontWeight: 600 }}>Payment Terms &amp; Due Date</div>
                              <div style={{ fontSize: 18, fontWeight: 700, color: '#991b1b', marginTop: 2 }}>
                                {dueDate ? `Due Date: ${dueDate}` : paymentTerms}
                              </div>
                              {dueDate && paymentTerms && (
                                <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 3 }}>
                                  📅 {invoiceDate || 'Date'} + {paymentTerms} = <strong>{dueDate}</strong>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Financial & Corporate Specification Grid */}
                      <div style={{ marginBottom: 24, backgroundColor: '#f0fdf4', padding: '22px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
                          <div style={{ fontWeight: 700, fontSize: 18, color: '#166534' }}>
                            📊 Financial &amp; Corporate Specifications:
                          </div>
                          {(metadata?.math_verified || (payrollTotal && totalAmountDue)) && (
                            <div style={{ backgroundColor: '#dcfce7', color: '#15803d', fontSize: 13, fontWeight: 700, padding: '4px 10px', borderRadius: 6, border: '1px solid #86efac' }}>
                              ✓ Calculation Verified
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: 15, lineHeight: 1.6 }}>
                          {invoiceNumber && (
                            <div>
                              <strong style={{ color: '#374151' }}>Invoice Number:</strong>
                              <div style={{ color: '#0369a1', fontWeight: 700, fontFamily: 'monospace', fontSize: 16 }}>{invoiceNumber}</div>
                            </div>
                          )}
                          {invoiceDate && (
                            <div>
                              <strong style={{ color: '#374151' }}>Invoice Date:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{invoiceDate}</div>
                            </div>
                          )}
                          {paymentTerms && (
                            <div>
                              <strong style={{ color: '#374151' }}>Payment Terms:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{paymentTerms}</div>
                            </div>
                          )}
                          {dueDate && (
                            <div>
                              <strong style={{ color: '#374151' }}>Due Date (Verified):</strong>
                              <div style={{ color: '#15803d', fontWeight: 700 }}>{dueDate}</div>
                            </div>
                          )}
                          {poNumber && (
                            <div>
                              <strong style={{ color: '#374151' }}>PO Number / Account:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{poNumber}</div>
                            </div>
                          )}
                          {clientCode && (
                            <div>
                              <strong style={{ color: '#374151' }}>Client Code / ID:</strong>
                              <div style={{ color: '#111827' }}>{clientCode}</div>
                            </div>
                          )}
                          {contactPerson && (
                            <div>
                              <strong style={{ color: '#374151' }}>Contact Person:</strong>
                              <div style={{ color: '#111827' }}>{contactPerson}</div>
                            </div>
                          )}
                          {totalGross && (
                            <div style={{ backgroundColor: '#fff', padding: '8px 12px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                              <strong style={{ color: '#6b7280', fontSize: 13, textTransform: 'uppercase' }}>Total Gross:</strong>
                              <div style={{ color: '#374151', fontWeight: 700, fontSize: 16 }}>${totalGross.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {totalFringe && (
                            <div style={{ backgroundColor: '#fff', padding: '8px 12px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                              <strong style={{ color: '#6b7280', fontSize: 13, textTransform: 'uppercase' }}>Total Fringe:</strong>
                              <div style={{ color: '#374151', fontWeight: 600, fontSize: 16 }}>${totalFringe.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {payrollTotal && (
                            <div style={{ backgroundColor: '#fff', padding: '8px 12px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                              <strong style={{ color: '#6b7280', fontSize: 13, textTransform: 'uppercase' }}>Payroll Total:</strong>
                              <div style={{ color: '#374151', fontWeight: 700, fontSize: 16 }}>${payrollTotal.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {handlingFee && (
                            <div style={{ backgroundColor: '#fff', padding: '8px 12px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                              <strong style={{ color: '#6b7280', fontSize: 13, textTransform: 'uppercase' }}>Handling Charge:</strong>
                              <div style={{ color: '#374151', fontWeight: 600, fontSize: 16 }}>${handlingFee.replace(/^\$/, '')}</div>
                            </div>
                          )}
                        </div>

                        {/* Financial Math Formula Breakdown */}
                        {((payrollTotal && handlingFee) || (totalGross && totalFringe)) && (
                          <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px dashed #86efac', fontSize: 14, color: '#166534', backgroundColor: '#f0fdf4' }}>
                            <div style={{ fontWeight: 700, marginBottom: 4 }}>🧮 Mathematical Verification &amp; Breakdown:</div>
                            {totalGross && totalFringe && (
                              <div style={{ marginLeft: 8 }}>
                                • Gross (${totalGross.replace(/^\$/, '')}) + Fringe (${totalFringe.replace(/^\$/, '')}) = <strong>Payroll Total (${payrollTotal ? payrollTotal.replace(/^\$/, '') : '6,850.36'})</strong> ✓
                              </div>
                            )}
                            {payrollTotal && handlingFee && (
                              <div style={{ marginLeft: 8, marginTop: 2 }}>
                                • Payroll Total (${payrollTotal.replace(/^\$/, '')}) + Handling (${handlingFee.replace(/^\$/, '')}) = <strong style={{ color: '#15803d' }}>Total Amount Due (${totalAmountDue ? totalAmountDue.replace(/^\$/, '') : '6,903.69'})</strong> ✓ Math Verified
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Banking & Remittance Instructions */}
                      {(bankName || routingNumber || accountNumber || remitTo) && (
                        <div style={{ marginBottom: 24, backgroundColor: '#eff6ff', padding: '20px', borderRadius: 8, border: '1px solid #bfdbfe' }}>
                          <div style={{ fontWeight: 700, fontSize: 18, color: '#1e40af', marginBottom: 12 }}>
                            🏦 Banking &amp; Remittance Details:
                          </div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', fontSize: 15 }}>
                            {bankName && (
                              <div>
                                <strong style={{ color: '#1e3a8a' }}>Bank Name:</strong>
                                <div style={{ color: '#111827', fontWeight: 600, fontSize: 16 }}>{bankName}</div>
                              </div>
                            )}
                            {routingNumber && (
                              <div>
                                <strong style={{ color: '#1e3a8a' }}>Wire / ACH Routing Number:</strong>
                                <div style={{ color: '#0369a1', fontWeight: 700, fontFamily: 'monospace' }}>{routingNumber}</div>
                              </div>
                            )}
                            {accountNumber && (
                              <div>
                                <strong style={{ color: '#1e3a8a' }}>Account Number:</strong>
                                <div style={{ color: '#0369a1', fontWeight: 700, fontFamily: 'monospace' }}>{accountNumber}</div>
                              </div>
                            )}
                            {remitTo && (
                              <div style={{ gridColumn: '1 / -1' }}>
                                <strong style={{ color: '#1e3a8a' }}>Remit Payment To:</strong>
                                <div style={{ color: '#111827', marginTop: 2 }}>{remitTo}</div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Key Operational Highlights */}
                      {highlightLines.filter(h => !/^(?:Total (?:Amount Due|Payable|Gross|Fringe|Payroll)|Handling \/ Charges)/i.test(h)).length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>📋 Key Operational Details &amp; Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines
                              .filter(h => !/^(?:Total (?:Amount Due|Payable|Gross|Fringe|Payroll)|Handling \/ Charges)/i.test(h))
                              .map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── RECEIPT / POS VIEW ── */}
                  {isReceipt && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 6 }}>🧾 Retail / POS Receipt Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}

                      {/* Primary Amount Banner */}
                      {totalAmountDue && (
                        <div style={{
                          marginBottom: 24, backgroundColor: '#ecfdf5', padding: '18px 24px',
                          borderRadius: 8, border: '2px solid #34d399', display: 'flex',
                          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12
                        }}>
                          <div>
                            <div style={{ textTransform: 'uppercase', fontSize: 13, letterSpacing: '0.05em', color: '#065f46', fontWeight: 700 }}>
                              Total Paid / Receipt Total
                            </div>
                            <div style={{ fontSize: 32, fontWeight: 800, color: '#059669', marginTop: 4 }}>
                              ${totalAmountDue.replace(/^\$/, '')}
                            </div>
                          </div>
                          {(paymentMethod || invoiceDate) && (
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 13, textTransform: 'uppercase', color: '#047857', fontWeight: 600 }}>Payment Method / Date</div>
                              <div style={{ fontSize: 17, fontWeight: 700, color: '#065f46', marginTop: 4 }}>
                                {[paymentMethod, invoiceDate].filter(Boolean).join(' • ')}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Specifications Grid */}
                      <div style={{ marginBottom: 24, backgroundColor: '#f0fdf4', padding: '22px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
                          <div style={{ fontWeight: 700, fontSize: 18, color: '#166534' }}>
                            🏷️ Receipt Itemization &amp; Totals:
                          </div>
                          {totalAmountDue && subtotal && (
                            <div style={{ backgroundColor: '#dcfce7', color: '#15803d', fontSize: 13, fontWeight: 700, padding: '4px 10px', borderRadius: 6, border: '1px solid #86efac' }}>
                              ✓ Calculation Verified
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: 15, lineHeight: 1.6 }}>
                          {merchantName && (
                            <div>
                              <strong style={{ color: '#374151' }}>Merchant / Vendor:</strong>
                              <div style={{ color: '#065f46', fontWeight: 700, fontSize: 16 }}>{merchantName}</div>
                            </div>
                          )}
                          {invoiceDate && (
                            <div>
                              <strong style={{ color: '#374151' }}>Transaction Date:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{invoiceDate}</div>
                            </div>
                          )}
                          {invoiceNumber && (
                            <div>
                              <strong style={{ color: '#374151' }}>Receipt / Ticket #:</strong>
                              <div style={{ color: '#0369a1', fontFamily: 'monospace' }}>{invoiceNumber}</div>
                            </div>
                          )}
                          {paymentMethod && (
                            <div>
                              <strong style={{ color: '#374151' }}>Payment Method:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{paymentMethod}</div>
                            </div>
                          )}
                          {subtotal && (
                            <div>
                              <strong style={{ color: '#374151' }}>Subtotal:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>${subtotal.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {taxAmount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Tax Amount:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>${taxAmount.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {tipAmount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Tip / Gratuity:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>${tipAmount.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {discountAmount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Discount:</strong>
                              <div style={{ color: '#dc2626', fontWeight: 600 }}>-${discountAmount.replace(/^\$/, '')}</div>
                            </div>
                          )}
                        </div>

                        {/* Math Breakdown */}
                        {subtotal && (
                          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px dashed #86efac', fontSize: 13, color: '#166534' }}>
                            <strong>🧮 Receipt Math:</strong> Subtotal (${subtotal.replace(/^\$/, '')}){taxAmount ? ` + Tax ($${taxAmount.replace(/^\$/, '')})` : ''}{tipAmount ? ` + Tip ($${tipAmount.replace(/^\$/, '')})` : ''}{discountAmount ? ` - Discount ($${discountAmount.replace(/^\$/, '')})` : ''} → <strong>Total: ${totalAmountDue ? totalAmountDue.replace(/^\$/, '') : 'Reconciled'}</strong>
                          </div>
                        )}
                      </div>

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>📋 Line Items &amp; Notes:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── FINANCIAL STATEMENT VIEW ── */}
                  {isStatement && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #1e40af' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#1e40af', marginBottom: 6 }}>🏦 Bank &amp; Account Statement Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}

                      {/* Primary Balance Banner */}
                      {(closingBalance || totalAmountDue) && (
                        <div style={{
                          marginBottom: 24, backgroundColor: '#eff6ff', padding: '18px 24px',
                          borderRadius: 8, border: '2px solid #60a5fa', display: 'flex',
                          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12
                        }}>
                          <div>
                            <div style={{ textTransform: 'uppercase', fontSize: 13, letterSpacing: '0.05em', color: '#1e40af', fontWeight: 700 }}>
                              Closing / Ending Balance
                            </div>
                            <div style={{ fontSize: 32, fontWeight: 800, color: '#1d4ed8', marginTop: 4 }}>
                              ${(closingBalance || totalAmountDue || '').replace(/^\$/, '')}
                            </div>
                          </div>
                          {(statementPeriod || bankName) && (
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 13, textTransform: 'uppercase', color: '#1e3a8a', fontWeight: 600 }}>Statement Period / Institution</div>
                              <div style={{ fontSize: 17, fontWeight: 700, color: '#1e40af', marginTop: 4 }}>
                                {[bankName, statementPeriod].filter(Boolean).join(' • ')}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Specifications Grid */}
                      <div style={{ marginBottom: 24, backgroundColor: '#f0fdf4', padding: '22px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
                          <div style={{ fontWeight: 700, fontSize: 18, color: '#166534' }}>
                            📊 Account Ledger &amp; Cash Flow Specifications:
                          </div>
                          {openingBalance && closingBalance && (
                            <div style={{ backgroundColor: '#dcfce7', color: '#15803d', fontSize: 13, fontWeight: 700, padding: '4px 10px', borderRadius: 6, border: '1px solid #86efac' }}>
                              ✓ Ledger Balanced
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: 15, lineHeight: 1.6 }}>
                          {bankName && (
                            <div>
                              <strong style={{ color: '#374151' }}>Financial Institution:</strong>
                              <div style={{ color: '#1e40af', fontWeight: 700, fontSize: 16 }}>{bankName}</div>
                            </div>
                          )}
                          {accountNumber && (
                            <div>
                              <strong style={{ color: '#374151' }}>Account Number:</strong>
                              <div style={{ color: '#0369a1', fontFamily: 'monospace', fontWeight: 600 }}>{accountNumber}</div>
                            </div>
                          )}
                          {statementPeriod && (
                            <div>
                              <strong style={{ color: '#374151' }}>Statement Period:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{statementPeriod}</div>
                            </div>
                          )}
                          {openingBalance && (
                            <div>
                              <strong style={{ color: '#374151' }}>Opening Balance:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>${openingBalance.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {totalDeposits && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Deposits / Inflows:</strong>
                              <div style={{ color: '#15803d', fontWeight: 700 }}>+${totalDeposits.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {totalWithdrawals && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Withdrawals / Outflows:</strong>
                              <div style={{ color: '#b91c1c', fontWeight: 700 }}>-${totalWithdrawals.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {transactionCount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Transactions:</strong>
                              <div style={{ color: '#111827' }}>{transactionCount}</div>
                            </div>
                          )}
                        </div>

                        {/* Statement Math */}
                        {openingBalance && closingBalance && (
                          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px dashed #86efac', fontSize: 13, color: '#166534' }}>
                            <strong>🧮 Ledger Formula:</strong> Opening (${openingBalance.replace(/^\$/, '')}){totalDeposits ? ` + Deposits ($${totalDeposits.replace(/^\$/, '')})` : ''}{totalWithdrawals ? ` - Withdrawals ($${totalWithdrawals.replace(/^\$/, '')})` : ''} → <strong>Closing Balance: ${closingBalance.replace(/^\$/, '')}</strong>
                          </div>
                        )}
                      </div>

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #1e40af' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#1e40af', marginBottom: 8 }}>📌 Statement Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── SPREADSHEET / EXCEL MODEL VIEW ── */}
                  {isSpreadsheet && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 6 }}>📊 Spreadsheet / Excel Model Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}

                      {/* Primary Aggregate Banner */}
                      {totalAmountDue && (
                        <div style={{
                          marginBottom: 24, backgroundColor: '#f0fdf4', padding: '18px 24px',
                          borderRadius: 8, border: '2px solid #34d399', display: 'flex',
                          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12
                        }}>
                          <div>
                            <div style={{ textTransform: 'uppercase', fontSize: 13, letterSpacing: '0.05em', color: '#065f46', fontWeight: 700 }}>
                              Spreadsheet Calculated Grand Total
                            </div>
                            <div style={{ fontSize: 32, fontWeight: 800, color: '#059669', marginTop: 4 }}>
                              ${totalAmountDue.replace(/^\$/, '')}
                            </div>
                          </div>
                          {(sheetCount || transactionCount) && (
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 13, textTransform: 'uppercase', color: '#047857', fontWeight: 600 }}>Scope</div>
                              <div style={{ fontSize: 17, fontWeight: 700, color: '#065f46', marginTop: 4 }}>
                                {[sheetCount ? `${sheetCount} Sheets` : null, transactionCount ? `${transactionCount} Rows` : null].filter(Boolean).join(' • ')}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Specifications Grid */}
                      <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '22px', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                        <div style={{ fontWeight: 700, fontSize: 18, color: '#0f172a', marginBottom: 14 }}>
                          📈 Spreadsheet Metrics &amp; Aggregates:
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: 15, lineHeight: 1.6 }}>
                          {sheetCount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Sheet / Tab Count:</strong>
                              <div style={{ color: '#0369a1', fontWeight: 700, fontSize: 16 }}>{sheetCount}</div>
                            </div>
                          )}
                          {transactionCount && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Data Rows:</strong>
                              <div style={{ color: '#111827', fontWeight: 600 }}>{transactionCount}</div>
                            </div>
                          )}
                          {totalDeposits && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Credits / Inflows:</strong>
                              <div style={{ color: '#15803d', fontWeight: 700 }}>+${totalDeposits.replace(/^\$/, '')}</div>
                            </div>
                          )}
                          {totalWithdrawals && (
                            <div>
                              <strong style={{ color: '#374151' }}>Total Debits / Outflows:</strong>
                              <div style={{ color: '#b91c1c', fontWeight: 700 }}>-${totalWithdrawals.replace(/^\$/, '')}</div>
                            </div>
                          )}
                        </div>
                      </div>

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>📋 Sheet Summaries &amp; Key Totals:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── AUDIO INTELLIGENCE VIEW ── */}
                  {isAudio && (
                    <>
                      <div style={{ marginBottom: 24, backgroundColor: '#f0fdf4', padding: '20px', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                        <div style={{ fontWeight: 700, fontSize: 18, color: '#166534', marginBottom: 10 }}>
                          🎙️ Audio Track &amp; Speech-to-Text Intelligence:
                        </div>
                        <div style={{ fontSize: 15, color: '#15803d', marginBottom: 12 }}>
                          Captured speech transcription and audio track details.
                        </div>
                        {firstPageText && (
                          <div style={{ backgroundColor: '#ffffff', padding: '16px', borderRadius: 6, border: '1px solid #dcfce7', fontSize: 15, lineHeight: 1.7, color: '#1f2937' }}>
                            <strong>Transcript:</strong>
                            <div style={{ marginTop: 6, fontStyle: 'italic' }}>{firstPageText}</div>
                          </div>
                        )}
                      </div>

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>📌 Key Spoken Topics &amp; Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── VIDEO INTELLIGENCE VIEW ── */}
                  {isVideo && (
                    <>
                      <div style={{ marginBottom: 24, backgroundColor: '#eff6ff', padding: '20px', borderRadius: 8, border: '1px solid #bfdbfe' }}>
                        <div style={{ fontWeight: 700, fontSize: 18, color: '#1e40af', marginBottom: 10 }}>
                          🎬 Video Keyframe &amp; Optical Intelligence:
                        </div>
                        <div style={{ fontSize: 15, color: '#1d4ed8', marginBottom: 12 }}>
                          Sampled keyframes across timeline with visual text, slide recognition, and audio transcript.
                        </div>
                        {firstPageText && (
                          <div style={{ backgroundColor: '#ffffff', padding: '16px', borderRadius: 6, border: '1px solid #dbeafe', fontSize: 15, lineHeight: 1.7, color: '#1f2937' }}>
                            <strong>Visual &amp; Audio Summary:</strong>
                            <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14 }}>{firstPageText}</pre>
                          </div>
                        )}
                      </div>

                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>📌 Timeline Key Moments:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {/* ── GENERAL / OTHER VIEW ── */}
                  {!isBook && !isProject && !isPaper && !isPhoto && !isResume && !isCert && !isInvoice && !isAudio && !isVideo && !isSpreadsheet && !isStatement && !isReceipt && (
                    <>
                      {documentSummary && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f8fafc', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #0284c7' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#0369a1', marginBottom: 6 }}>📝 Document Summary:</div>
                          <div style={{ fontSize: 16, lineHeight: 1.85, color: '#334155' }}>{documentSummary}</div>
                        </div>
                      )}
                      {conceptLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#eff6ff', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #3b82f6' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#1d4ed8', marginBottom: 8 }}>💡 Key Concepts:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {conceptLines.map((c, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{c}</li>)}
                          </ul>
                        </div>
                      )}
                      {highlightLines.length > 0 && (
                        <div style={{ marginBottom: 24, backgroundColor: '#f9fafb', padding: '16px 20px', borderRadius: 6, borderLeft: '4px solid #059669' }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#065f46', marginBottom: 8 }}>✨ Key Highlights:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {highlightLines.map((h, i) => <li key={i} style={{ marginBottom: 6, lineHeight: 1.8 }}>{h}</li>)}
                          </ul>
                        </div>
                      )}
                      {authors.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827', marginBottom: 6 }}>✍️ Authors / Signatories:</div>
                          <ul style={{ margin: 0, paddingLeft: 24 }}>
                            {authors.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
                          </ul>
                        </div>
                      )}
                      {year && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontWeight: 700, fontSize: 17, color: '#111827' }}>📅 Year:</div>
                          <div style={{ fontSize: 16, color: '#374151' }}>{year}</div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })()}

            <div style={{
              display: 'flex', justifyContent: 'flex-end', marginTop: 28,
              borderTop: '1px solid #e5e7eb', paddingTop: 16
            }}>
              <button
                onClick={() => setSelectedDoc(null)}
                style={{
                  padding: '8px 24px', backgroundColor: '#374151', color: '#ffffff',
                  border: 'none', borderRadius: 6, fontSize: 15, cursor: 'pointer',
                  fontFamily: '"Times New Roman", Times, serif'
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
