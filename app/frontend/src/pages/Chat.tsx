import { useEffect, useState, useRef } from 'react'
import {
  MessageSquare, Send, Bot, User, Sparkles, CheckCircle2,
  FileText, ShieldCheck, CornerDownLeft, RefreshCw, AlertCircle
} from 'lucide-react'
import { chatApi, documentsApi, type DocumentRecord, type ChatResponse, type ChatSource } from '../api/client'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  model?: string
  confidence?: number
  timestamp: string
}

const QUICK_PROMPTS = [
  'What is the total amount due?',
  'When is the due date and what are the payment terms?',
  'Summarize this document',
  'Show the financial breakdown and line items',
  'Who is the vendor and who is billed?',
  'What is the invoice number and PO number?'
]

export function Chat() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [selectedDocId, setSelectedDocId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello! I am your **Offline Document Assistant**. You can ask me any questions about your uploaded documents, invoices, receipts, and reports.\n\nAll answers are calculated and grounded locally on this machine with **zero internet connection**.',
      model: 'Offline Grounded Engine (100% Local)',
      confidence: 1.0,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadDocuments()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const loadDocuments = async () => {
    try {
      const res = await documentsApi.list({ limit: 100 })
      setDocuments(res.documents || [])
      if (res.documents && res.documents.length > 0 && !selectedDocId) {
        setSelectedDocId(res.documents[0].id)
      }
    } catch (e: any) {
      console.error('Failed to load documents for chat', e)
    }
  }

  const handleSend = async (textToSend?: string) => {
    const q = (textToSend || input).trim()
    if (!q || loading) return

    const userMsg: Message = {
      id: String(Date.now()),
      role: 'user',
      content: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const history = messages
        .filter(m => m.id !== 'welcome')
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }))

      const res: ChatResponse = await chatApi.ask(q, selectedDocId || undefined, history)

      const assistantMsg: Message = {
        id: String(Date.now() + 1),
        role: 'assistant',
        content: res.answer,
        sources: res.sources,
        model: res.model_used,
        confidence: res.confidence,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err: any) {
      setError(err?.message || 'Failed to get an answer from offline assistant')
    } finally {
      setLoading(false)
    }
  }

  const formatMarkdown = (text: string) => {
    // Basic formatting for bold, lists, and quotes
    const lines = text.split('\n')
    return lines.map((line, idx) => {
      let content = line

      // Headers
      if (content.startsWith('### ')) {
        return <h4 key={idx} style={{ margin: '10px 0 6px', fontWeight: 700, fontSize: 14 }}>{content.replace('### ', '')}</h4>
      }
      if (content.startsWith('## ')) {
        return <h3 key={idx} style={{ margin: '12px 0 6px', fontWeight: 700, fontSize: 15 }}>{content.replace('## ', '')}</h3>
      }

      // Blockquotes
      if (content.startsWith('> ')) {
        return (
          <blockquote key={idx} style={{
            borderLeft: '3px solid var(--color-primary, #6366f1)',
            paddingLeft: 12,
            margin: '6px 0',
            color: 'var(--color-text-muted, #94a3b8)',
            fontStyle: 'italic',
            fontSize: 13
          }}>
            {content.replace('> ', '')}
          </blockquote>
        )
      }

      // Format bold text **text**
      const parts = content.split(/(\*\*[^*]+\*\*)/g)
      const renderedLine = parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={pIdx} style={{ color: 'var(--color-text, #f8fafc)' }}>{part.slice(2, -2)}</strong>
        }
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={pIdx} style={{ background: 'rgba(255,255,255,0.08)', padding: '2px 4px', borderRadius: 3, fontSize: '0.9em' }}>{part.slice(1, -1)}</code>
        }
        return part
      })

      // Bullet lists
      if (content.trim().startsWith('- ')) {
        return (
          <div key={idx} style={{ marginLeft: 16, display: 'flex', gap: 6, margin: '2px 0' }}>
            <span style={{ color: 'var(--color-primary, #6366f1)' }}>•</span>
            <div>{renderedLine.slice(1)}</div>
          </div>
        )
      }

      return <p key={idx} style={{ margin: '4px 0', minHeight: content ? 'auto' : 8 }}>{renderedLine}</p>
    })
  }

  const selectedDoc = documents.find(d => d.id === selectedDocId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 48px)', maxWidth: 1000, margin: '0 auto', gap: 12 }}>
      {/* Header */}
      <div className="card" style={{ padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(99, 102, 241, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Bot size={20} color="var(--color-primary, #6366f1)" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              Document Assistant
              <span className="badge badge-success" style={{ fontSize: 10, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <ShieldCheck size={11} /> 100% Offline Mode
              </span>
            </div>
            <div className="text-muted text-xs">
              Zero network calls. Verified extraction &amp; mathematical reasoning.
            </div>
          </div>
        </div>

        {/* Document Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-muted)' }}>Target Document:</span>
          <select
            className="input"
            style={{ padding: '6px 12px', fontSize: 12, minWidth: 220, borderRadius: 6 }}
            value={selectedDocId}
            onChange={e => setSelectedDocId(e.target.value)}
          >
            <option value="">Auto (Most Recent Document)</option>
            {documents.map(d => (
              <option key={d.id} value={d.id}>
                {d.original_filename} ({d.file_type.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Messages Stream */}
      <div
        className="card"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          background: 'rgba(15, 23, 42, 0.4)'
        }}
      >
        {messages.map(m => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              gap: 12,
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '85%'
            }}
          >
            {m.role === 'assistant' && (
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: 'rgba(99, 102, 241, 0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, marginTop: 2
              }}>
                <Bot size={16} color="var(--color-primary, #6366f1)" />
              </div>
            )}

            <div style={{
              background: m.role === 'user' ? 'var(--color-primary, #6366f1)' : 'var(--color-surface, #1e293b)',
              color: m.role === 'user' ? '#ffffff' : 'inherit',
              padding: '12px 16px',
              borderRadius: 10,
              fontSize: 13.5,
              lineHeight: 1.55,
              border: m.role === 'user' ? 'none' : '1px solid var(--color-border, #334155)',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
            }}>
              <div>{formatMarkdown(m.content)}</div>

              {/* Source Snippets & Badges */}
              {m.sources && m.sources.length > 0 && (
                <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {m.sources.map((src, sIdx) => (
                    <div
                      key={sIdx}
                      style={{
                        background: 'rgba(99, 102, 241, 0.12)',
                        border: '1px solid rgba(99, 102, 241, 0.25)',
                        padding: '3px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 5
                      }}
                      title={src.snippet}
                    >
                      <CheckCircle2 size={11} color="var(--color-primary, #6366f1)" />
                      <span>{src.label ? `${src.label}: ` : ''}{src.value || (src.page ? `Page ${src.page}` : 'Verified Source')}</span>
                    </div>
                  ))}
                </div>
              )}

              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: 6,
                fontSize: 10,
                color: m.role === 'user' ? 'rgba(255,255,255,0.7)' : 'var(--color-text-muted, #94a3b8)'
              }}>
                {m.model && <span>{m.model}</span>}
                <span style={{ marginLeft: 'auto' }}>{m.timestamp}</span>
              </div>
            </div>

            {m.role === 'user' && (
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: 'rgba(255, 255, 255, 0.1)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, marginTop: 2
              }}>
                <User size={16} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(99, 102, 241, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={16} color="var(--color-primary, #6366f1)" />
            </div>
            <div className="card" style={{ padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <RefreshCw size={13} className="spinner" />
              <span>Analyzing document offline…</span>
            </div>
          </div>
        )}

        {error && (
          <div className="card" style={{ borderColor: 'var(--color-error)', backgroundColor: 'rgba(239, 68, 68, 0.08)', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertCircle size={15} color="var(--color-error)" />
            <span style={{ fontSize: 12, color: 'var(--color-error)' }}>{error}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick Prompts */}
      <div style={{ display: 'flex', gap: 6, overflowX: 'auto', padding: '2px 0' }}>
        {QUICK_PROMPTS.map((prompt, pIdx) => (
          <button
            key={pIdx}
            className="btn btn-secondary btn-sm"
            style={{
              whiteSpace: 'nowrap',
              fontSize: 11,
              padding: '4px 10px',
              borderRadius: 16,
              background: 'rgba(30, 41, 59, 0.7)'
            }}
            onClick={() => handleSend(prompt)}
            disabled={loading}
          >
            <Sparkles size={11} style={{ marginRight: 4, color: 'var(--color-primary)' }} />
            {prompt}
          </button>
        ))}
      </div>

      {/* Input Field */}
      <div className="card" style={{ padding: 8 }}>
        <form
          onSubmit={e => { e.preventDefault(); handleSend() }}
          style={{ display: 'flex', gap: 8, alignItems: 'center' }}
        >
          <input
            type="text"
            className="input"
            placeholder={selectedDoc ? `Ask any question about ${selectedDoc.original_filename}…` : 'Ask any question about your documents…'}
            value={input}
            onChange={e => setInput(e.target.value)}
            disabled={loading}
            style={{ flex: 1, padding: '10px 14px', fontSize: 13, border: 'none', background: 'transparent' }}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!input.trim() || loading}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px', fontWeight: 600 }}
          >
            {loading ? <RefreshCw size={14} className="spinner" /> : <Send size={14} />}
            <span>Ask</span>
          </button>
        </form>
      </div>
    </div>
  )
}
