import { useEffect, useState } from 'react'
import { Cpu, Play, CheckCircle, AlertTriangle, Clock } from 'lucide-react'
import { documentsApi, processingApi, type DocumentRecord, type ProcessingStatus } from '../api/client'

export function Process() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [processing, setProcessing] = useState(false)
  const [statusMap, setStatusMap] = useState<Record<string, ProcessingStatus>>({})
  const [error, setError] = useState<string | null>(null)
  const [createProfile, setCreateProfile] = useState(true)

  useEffect(() => {
    documentsApi.list({ limit: 100 }).then(r => setDocuments(r.documents)).catch(console.error)
  }, [])

  const pendingDocs = documents.filter(d => d.processing_status === 'pending')
  const processedDocs = documents.filter(d => d.processing_status === 'completed')

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const selectAll = () => {
    setSelectedIds(new Set(pendingDocs.map(d => d.id)))
  }

  const startProcessing = async () => {
    if (selectedIds.size === 0) {
      setError('Select at least one document to process.')
      return
    }
    setProcessing(true)
    setError(null)

    try {
      const job = await processingApi.start(Array.from(selectedIds), createProfile)

      // Poll status every 2 seconds
      const poll = setInterval(async () => {
        let allDone = true
        for (const docId of selectedIds) {
          try {
            const s = await processingApi.getStatus(docId)
            setStatusMap(prev => ({ ...prev, [docId]: s }))
            if (s.status === 'processing' || s.status === 'pending') {
              allDone = false
            }
          } catch {}
        }
        if (allDone) {
          clearInterval(poll)
          setProcessing(false)
          // Reload documents
          documentsApi.list({ limit: 100 }).then(r => setDocuments(r.documents)).catch(console.error)
        }
      }, 2000)

    } catch (e: any) {
      setError(e.message)
      setProcessing(false)
    }
  }

  const getDocStatus = (docId: string) => statusMap[docId]

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Process Documents</h1>
        <p className="page-subtitle">
          Select pending documents to run text extraction, OCR, and AI analysis.
          All processing happens locally.
        </p>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Controls */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <div className="flex items-center gap-md">
            <button className="btn btn-secondary btn-sm" onClick={selectAll}>
              Select All Pending ({pendingDocs.length})
            </button>
            <label className="flex items-center gap-sm" style={{ cursor: 'pointer', fontSize: 13 }}>
              <input
                type="checkbox"
                checked={createProfile}
                onChange={e => setCreateProfile(e.target.checked)}
              />
              Generate consolidated profile after processing
            </label>
          </div>
          <button
            className="btn btn-primary"
            onClick={startProcessing}
            disabled={processing || selectedIds.size === 0}
          >
            {processing ? (
              <><div className="spinner" style={{ width: 14, height: 14 }} /> Processing…</>
            ) : (
              <><Play size={14} /> Process {selectedIds.size > 0 ? `${selectedIds.size} Documents` : 'Selected'}</>
            )}
          </button>
        </div>

        <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
          <strong>Pipeline:</strong> Uploading → Reading → Extracting → Analyzing → Validating → Completed
        </div>
      </div>

      {/* Document List */}
      {pendingDocs.length === 0 && !processing ? (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <CheckCircle size={32} style={{ color: 'var(--color-success)', marginBottom: 12 }} />
          <div style={{ fontWeight: 600, marginBottom: 4 }}>All documents processed</div>
          <div className="text-muted text-sm">Upload new documents in the Documents tab</div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 40 }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.size === pendingDocs.length && pendingDocs.length > 0}
                    onChange={e => e.target.checked ? selectAll() : setSelectedIds(new Set())}
                  />
                </th>
                <th>Document</th>
                <th>Type</th>
                <th>Size</th>
                <th>Pipeline Stage</th>
                <th>Verification &amp; Result</th>
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => {
                const status = getDocStatus(doc.id)
                const isSelected = selectedIds.has(doc.id)
                const isPending = doc.processing_status === 'pending'
                let meta: any = null
                if (doc.metadata_json) {
                  try { meta = JSON.parse(doc.metadata_json) } catch {}
                }

                const latestStage = status?.processing_stages?.[0]?.stage
                const stageLabel = latestStage ? (
                  latestStage === 'reading' || latestStage === 'text_extraction' ? 'Reading' :
                  latestStage === 'extracting' ? 'Extracting' :
                  latestStage === 'analyzing' || latestStage === 'llm_extraction' ? 'Analyzing' :
                  latestStage === 'validating' ? 'Validating' :
                  latestStage === 'completed' ? 'Completed' : latestStage
                ) : null

                return (
                  <tr
                    key={doc.id}
                    onClick={() => isPending && toggleSelect(doc.id)}
                    style={{ cursor: isPending ? 'pointer' : 'default', opacity: isPending ? 1 : 0.85 }}
                  >
                    <td>
                      {isPending && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(doc.id)}
                          onClick={e => e.stopPropagation()}
                        />
                      )}
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{doc.original_filename}</div>
                      <div className="text-xs text-muted font-mono">{doc.id.slice(0, 8)}…</div>
                    </td>
                    <td>
                      <span className="badge badge-neutral">{doc.file_type.toUpperCase()}</span>
                      {doc.document_type && (
                        <span className="badge badge-info" style={{ marginLeft: 4, fontSize: 10 }}>
                          {doc.document_type}
                        </span>
                      )}
                    </td>
                    <td className="text-muted text-sm">
                      {(doc.file_size / 1024).toFixed(0)} KB
                    </td>
                    <td>
                      {doc.processing_status === 'processing' ? (
                        <div className="flex items-center gap-xs">
                          <div className="spinner" style={{ width: 12, height: 12 }} />
                          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-primary)' }}>
                            {stageLabel || 'Extracting'}…
                          </span>
                        </div>
                      ) : doc.processing_status === 'completed' ? (
                        <span style={{ fontSize: 12, color: 'var(--color-success)', fontWeight: 500 }}>
                          ✓ Completed
                        </span>
                      ) : (
                        <span className="text-muted text-sm">—</span>
                      )}
                    </td>
                    <td>
                      {doc.processing_status === 'completed' && (
                        <div>
                          <div className="flex items-center gap-xs flex-wrap">
                            <span className="badge badge-success">Done</span>
                            {meta?.math_verified && (
                              <span className="badge" style={{ backgroundColor: '#dcfce7', color: '#15803d', border: '1px solid #86efac', fontSize: 10, fontWeight: 700 }}>
                                ✓ Math Verified
                              </span>
                            )}
                          </div>
                          {meta?.total_amount_due && (
                            <div className="text-xs mt-xs" style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                              Total Due: ${String(meta.total_amount_due).replace(/^\$/, '')}
                            </div>
                          )}
                          {meta?.due_date && (
                            <div className="text-xs text-muted">
                              Due: {meta.due_date}
                            </div>
                          )}
                        </div>
                      )}
                      {doc.processing_status === 'failed' && (
                        <span className="badge badge-error" title={doc.error_message ?? ''}>Failed</span>
                      )}
                      {doc.processing_status === 'processing' && (
                        <div className="flex items-center gap-sm">
                          <div className="spinner" style={{ width: 12, height: 12 }} />
                          <span className="badge badge-info">Running</span>
                        </div>
                      )}
                      {doc.processing_status === 'pending' && <span className="badge badge-neutral">Pending</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
